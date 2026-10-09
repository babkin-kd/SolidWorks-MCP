"""Job lifecycle tests exercise races, crash recovery and live-owner exclusion."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import threading

import pytest

from solidworks_mcp.jobs import ExecutionFailure, JobError, JobRunner, JobStore


class Worker:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)

    def submit(self, function):
        return self.pool.submit(function)

    def shutdown(self, timeout_s=5):
        self.pool.shutdown(wait=True)
        return True


@pytest.fixture
def runner(tmp_path):
    value = JobRunner(JobStore(tmp_path / 'jobs.sqlite'), Worker())
    yield value
    value.shutdown()


def settled(runner, operation_id):
    return asyncio.run(runner.wait(operation_id, timeout_s=2))


def test_retries_execute_exactly_once_even_after_late_completion(runner):
    started, release = threading.Event(), threading.Event()
    calls = []
    def build():
        calls.append('feature')
        started.set()
        assert release.wait(2)
        return {'name': 'Кронштейн'}
    job = runner.submit('create-1', 'part.create', {'width_mm': 80}, build,
                        mutates=True, verify=lambda r: r['name'] == 'Кронштейн')
    try:
        assert started.wait(1)
        timed_out = asyncio.run(runner.wait(job['operation_id'], 0.01))
        assert timed_out['status'] == 'running'
        retry = runner.submit('create-1', 'part.create', {'width_mm': 80}, build,
                              mutates=True, verify=lambda _: True)
        assert retry['operation_id'] == job['operation_id']
        assert runner.store.cancel(job['operation_id'])['cancelled'] is False
    finally:
        release.set()
    finished = settled(runner, job['operation_id'])
    assert finished['status'] == 'succeeded'
    assert finished['result']['name'] == 'Кронштейн'
    assert runner.submit('create-1', 'part.create', {'width_mm': 80}, build,
                         mutates=True, verify=lambda _: True)['result'] == finished['result']
    assert calls == ['feature']


def test_cancelled_queued_job_never_executes(runner):
    started, release = threading.Event(), threading.Event()
    calls = []
    first = runner.submit('first', 'test.wait', {}, lambda: (started.set(), release.wait(2)))
    try:
        assert started.wait(1)
        second = runner.submit('second', 'part.create', {}, lambda: calls.append('wrong'),
                               mutates=True, verify=lambda _: True)
        assert runner.store.cancel(second['operation_id'])['cancelled'] is True
        assert runner.store.get(second['operation_id'])['status'] == 'cancelled'
    finally:
        release.set()
    settled(runner, first['operation_id'])
    assert settled(runner, second['operation_id'])['status'] == 'cancelled'
    assert calls == []


def test_same_id_different_operation_arguments_or_revision_are_rejected(runner):
    runner.submit('id', 'part.create', {'size': 1}, lambda: {}, context={'expected_revision': 'a'})
    for operation, arguments, context in [
        ('part.delete', {'size': 1}, {'expected_revision': 'a'}),
        ('part.create', {'size': 2}, {'expected_revision': 'a'}),
        ('part.create', {'size': 1}, {'expected_revision': 'b'}),
    ]:
        with pytest.raises(JobError, match='different parameters'):
            runner.submit('id', operation, arguments, lambda: pytest.fail('Executed conflict'), context=context)


def test_waiter_cancellation_does_not_cancel_running_operation(runner):
    started, release = threading.Event(), threading.Event()
    def build():
        started.set()
        assert release.wait(2)
        return {'verified': True}
    job = runner.submit('wait-cancel', 'part.create', {}, build, mutates=True, verify=lambda _: True)
    async def cancel_wait():
        task = asyncio.create_task(runner.wait(job['operation_id'], 1))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    try:
        assert started.wait(1)
        asyncio.run(cancel_wait())
        assert runner.store.get(job['operation_id'])['status'] == 'running'
    finally:
        release.set()
    assert settled(runner, job['operation_id'])['status'] == 'succeeded'


def test_json_failure_or_unverified_mutation_never_reports_success(runner):
    with pytest.raises(JobError, match='verifier'):
        runner.submit('unverified', 'part.create', {}, lambda: {}, mutates=True)
    bad = runner.submit('postcondition', 'part.create', {}, lambda: {'name': 'a'},
                        mutates=True, verify=lambda _: False)
    invalid = runner.submit('bad-result', 'part.create', {}, lambda: {'object': object()},
                            mutates=True, verify=lambda _: True)
    for job in (bad, invalid):
        result = settled(runner, job['operation_id'])
        assert result['status'] == 'unknown'
        assert result['error']['requires_reconciliation']


def test_domain_can_report_verified_rollback_but_unknown_exceptions_stay_uncertain(runner):
    def rolled_back():
        raise ExecutionFailure('rebuild_failed', 'Rollback verified', uncertain=False)
    def crash():
        raise RuntimeError('unexpected COM failure')
    safe = runner.submit('rollback', 'part.create', {}, rolled_back, mutates=True, verify=lambda _: True)
    uncertain = runner.submit('crash', 'part.create', {}, crash, mutates=True, verify=lambda _: True)
    assert settled(runner, safe['operation_id'])['status'] == 'failed'
    assert settled(runner, uncertain['operation_id'])['status'] == 'unknown'


def test_legacy_ok_false_is_not_success(runner):
    job = runner.submit('fail', 'read', {}, lambda: {'ok': False, 'error': 'Bad geometry'})
    result = settled(runner, job['operation_id'])
    assert result['status'] == 'failed'
    assert result['error']['message'] == 'Bad geometry'


def test_canonical_json_retries_and_detached_payloads(runner):
    values = {'b': [2], 'a': 1}
    a, created = runner.store.create('canonical', 'read', values)
    values['b'].append(3)
    b, created_again = runner.store.create('canonical', 'read', {'a': 1, 'b': [2]})
    assert created and not created_again and a['operation_id'] == b['operation_id']
    assert b['payload']['arguments']['b'] == [2]


@pytest.mark.parametrize('payload', [{'x': float('nan')}, {'x': float('inf')}, {1: 'key'}, {'x': object()}])
def test_invalid_payload_is_rejected_before_dispatch(runner, payload):
    with pytest.raises(JobError):
        runner.submit('invalid', 'read', payload, lambda: pytest.fail('Executed bad input'))
    assert not runner.store.list()['items']


def test_live_owner_prevents_recovery_from_stealing_jobs(tmp_path):
    path = tmp_path / 'jobs.sqlite'
    owner = JobStore(path)
    try:
        job, _ = owner.create('pending', 'part.create', {})
        owner.start(job['operation_id'])
        with pytest.raises(JobError, match='Another runtime'):
            JobStore(path)
        assert owner.get(job['operation_id'])['status'] == 'running'
    finally:
        owner.close()


def test_process_crash_recovers_unknown_without_replay_and_preserves_success(tmp_path):
    path = tmp_path / 'jobs.sqlite'
    probe = '''
import os, sys
from solidworks_mcp.jobs import JobStore
s = JobStore(sys.argv[1])
for key in ('queued', 'running', 'succeeded'):
    j, _ = s.create(key, 'part.create', {'name': 'Деталь'})
    if key != 'queued': s.start(j['operation_id'])
    if key == 'succeeded': s.finish(j['operation_id'], 'succeeded', result={'saved': True})
os._exit(0)
'''
    subprocess.run([sys.executable, '-c', probe, str(path)], check=True, timeout=10)
    recovered = JobStore(path)
    try:
        jobs = {item['request_id']: item for item in recovered.list()['items']}
        assert jobs['queued']['status'] == jobs['running']['status'] == 'unknown'
        assert jobs['succeeded']['result'] == {'saved': True}
        for key in ('queued', 'running'):
            same, created = recovered.create(key, 'part.create', {'name': 'Деталь'})
            assert not created and same['status'] == 'unknown'
    finally:
        recovered.close()


def test_pagination_does_not_drop_jobs_with_identical_timestamps(runner, monkeypatch):
    monkeypatch.setattr('solidworks_mcp.jobs.time.time', lambda: 10)
    ids = {runner.store.create(f'page-{i}', 'read', {})[0]['operation_id'] for i in range(7)}
    seen, cursor = set(), None
    while True:
        page = runner.store.list(limit=2, before_created_at=cursor['created_at'] if cursor else None,
                                 before_operation_id=cursor['operation_id'] if cursor else '')
        received = {item['operation_id'] for item in page['items']}
        assert not (seen & received)
        seen |= received
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert seen == ids


@pytest.mark.parametrize('timestamp,identifier', [(None, 'id'), (float('nan'), 'id'), (1, ''), (True, 'id')])
def test_partial_or_nonfinite_cursor_is_rejected(runner, timestamp, identifier):
    with pytest.raises(JobError, match='cursor|timestamp'):
        runner.store.list(before_created_at=timestamp, before_operation_id=identifier)


def test_concurrent_requests_with_one_id_only_dispatch_once(runner):
    calls = []
    def submit(_):
        return runner.submit('concurrent', 'part.create', {'name': 'Кронштейн'},
                             lambda: (calls.append('created'), {'name': 'Кронштейн'})[1],
                             mutates=True, verify=lambda _: True)
    with ThreadPoolExecutor(max_workers=8) as callers:
        jobs = list(callers.map(submit, range(24)))
    assert len({job['operation_id'] for job in jobs}) == 1
    assert settled(runner, jobs[0]['operation_id'])['status'] == 'succeeded'
    assert calls == ['created']
