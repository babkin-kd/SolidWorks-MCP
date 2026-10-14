"""Durable document holds and trusted STA mutation orchestration, without CAD."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import subprocess
import sys
import threading

import pytest

from solidworks_mcp.jobs import ExecutionFailure, JobError, JobRunner, JobStore
from solidworks_mcp.mutations import MutationCoordinator, PreparedMutation


class Worker:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)

    def submit(self, function):
        return self.pool.submit(function)

    def shutdown(self, timeout_s=5):
        self.pool.shutdown(wait=True)
        return True


def context(document='doc_a', revision='rev_1', configuration='Основная'):
    return {'document_id': document, 'configuration': configuration, 'expected_revision': revision}


def prepared_job(store, request='r1', *, epoch='connection_1', document='doc_a'):
    job, _ = store.create(request, 'feature.rename', {'name': 'Кронштейн'},
                          context(document), mutates=True)
    store.start(job['operation_id'])
    store.prepare_mutation(job['operation_id'], connection_epoch=epoch,
                            **context(document), before_state={'name': 'Исходное имя'})
    return job['operation_id']


@pytest.fixture
def store(tmp_path):
    value = JobStore(tmp_path / 'jobs.sqlite')
    yield value
    value.close()


@pytest.mark.parametrize('status,outcome,phase', [
    ('succeeded', 'committed', 'committed'),
    ('failed', 'rolled_back', 'rolled_back'),
    ('failed', 'not_started', 'not_started'),
    ('unknown', 'committed', 'unresolved'),
    ('unknown', 'rolled_back', 'unresolved'),
])
def test_only_matching_verified_terminal_outcome_releases_hold(store, status, outcome, phase):
    job_id = prepared_job(store)
    assert store.mutation_blockers('connection_1', 'doc_a')
    store.verify_mutation(job_id, outcome=outcome, evidence={'native_checked': True})
    # Verification by itself is NOT an unlock before the job is durably terminal.
    assert store.mutation_blockers('connection_1', 'doc_a')
    finished = store.finish(job_id, status)
    assert finished['mutation']['phase'] == phase
    assert bool(store.mutation_blockers('connection_1', 'doc_a')) == (phase == 'unresolved')


@pytest.mark.parametrize('status,outcome', [
    ('succeeded', None), ('failed', None), ('succeeded', 'rolled_back'),
    ('succeeded', 'not_started'), ('failed', 'committed'),
])
def test_unverified_success_or_failed_status_cannot_unlock(store, status, outcome):
    job_id = prepared_job(store)
    if outcome:
        store.verify_mutation(job_id, outcome=outcome, evidence={'checked': True})
    result = store.finish(job_id, status, result={'fake': 'success'})
    assert result['status'] == 'unknown'
    assert result['result'] is None
    assert result['error']['code'] == 'mutation_confirmation_missing'
    assert result['mutation']['phase'] == 'unresolved'


def test_same_connection_blocks_only_exact_document_but_reconnect_blocks_all(store):
    job_id = prepared_job(store)
    assert store.mutation_blockers('connection_1', 'doc_a')
    assert store.mutation_blockers('connection_1', 'doc_b') == []
    assert store.mutation_blockers('connection_2', 'doc_b')
    # A configuration change cannot evade a document-wide hold.
    other, _ = store.create('other-config', 'feature.rename', {},
                           context(configuration='Вариант'), mutates=True)
    store.start(other['operation_id'])
    with pytest.raises(JobError) as failure:
        store.prepare_mutation(other['operation_id'], connection_epoch='connection_1',
                               **context(configuration='Вариант'), before_state={})
    assert failure.value.code == 'document_mutation_blocked'
    assert store.get(job_id)['status'] == 'running'
    prepared_job(store, 'unrelated', document='doc_b')


def test_checkpoint_json_is_detached_and_job_get_and_list_expose_evidence(store):
    job, _ = store.create('r', 'rename', {}, context(), mutates=True)
    store.start(job['operation_id'])
    before = {'names': ['Деталь']}
    store.prepare_mutation(job['operation_id'], connection_epoch='connection_1',
                           **context(), before_state=before)
    before['names'].append('Изменено')
    assert store.get(job['operation_id'])['mutation']['before_state'] == {'names': ['Деталь']}
    assert store.list()['items'][0]['mutation']['before_state'] == {'names': ['Деталь']}
    with pytest.raises(JobError):
        store.prepare_mutation(job['operation_id'], connection_epoch='connection_1',
                               **context(), before_state={})


@pytest.mark.parametrize('kind', ['queued', 'readonly', 'wrong_document', 'wrong_revision'])
def test_checkpoint_requires_running_mutation_and_exact_durable_target(store, kind):
    job, _ = store.create('r', 'rename', {}, context(), mutates=kind != 'readonly')
    if kind != 'queued':
        store.start(job['operation_id'])
    target = context(document='other' if kind == 'wrong_document' else 'doc_a',
                     revision='wrong' if kind == 'wrong_revision' else 'rev_1')
    with pytest.raises(JobError):
        store.prepare_mutation(job['operation_id'], connection_epoch='epoch', **target, before_state={})
    assert 'mutation' not in store.get(job['operation_id'])


def test_terminal_job_and_hold_roll_back_atomically_if_storage_write_fails(store):
    job_id = prepared_job(store)
    store.verify_mutation(job_id, outcome='committed', evidence={'native_checked': True})
    store._db.execute("CREATE TRIGGER fail_finish BEFORE UPDATE OF status ON jobs "
                      "WHEN NEW.status='succeeded' BEGIN SELECT RAISE(ABORT,'disk test'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.finish(job_id, 'succeeded')
    assert store.get(job_id)['status'] == 'running'
    assert store.get(job_id)['mutation']['phase'] == 'prepared'
    assert store.mutation_blockers('connection_1', 'doc_a')
    store._db.execute('DROP TRIGGER fail_finish')
    assert store.finish(job_id, 'succeeded')['mutation']['phase'] == 'committed'


@pytest.mark.parametrize('verify_before_crash', [False, True])
def test_process_crash_recovers_hold_without_replay(tmp_path, verify_before_crash):
    path = tmp_path / 'crash.sqlite'
    probe = '''
import os,sys
from solidworks_mcp.jobs import JobStore
s=JobStore(sys.argv[1])
c={'document_id':'doc_a','configuration':'Основная','expected_revision':'rev_1'}
j,_=s.create('crash','rename',{},c,mutates=True)
s.start(j['operation_id'])
s.prepare_mutation(j['operation_id'],connection_epoch='old',before_state={'name':'До'},**c)
if sys.argv[2]=='yes': s.verify_mutation(j['operation_id'],outcome='committed',evidence={'name':'После'})
os._exit(0)
'''
    subprocess.run([sys.executable, '-c', probe, str(path), 'yes' if verify_before_crash else 'no'],
                   check=True, timeout=10)
    value = JobStore(path)
    try:
        job = value.list()['items'][0]
        assert job['status'] == 'unknown'
        assert job['mutation']['phase'] == 'unresolved'
        assert value.mutation_blockers('new', 'any_new_document')
        prior, created = value.create('crash', 'rename', {}, context(), mutates=True)
        assert not created and prior['status'] == 'unknown'
        reconciled = value.reconcile_mutation(job['operation_id'], resolution='accept_current_state',
                                              evidence={'native_observation': {'name': 'После'}})
        assert reconciled['status'] == 'unknown'  # Never rewrite historical uncertainty as success.
        assert reconciled['mutation']['phase'] == 'reconciled'
        assert value.mutation_blockers('new', 'any_new_document') == []
    finally:
        value.close()


def test_reconciliation_does_not_unlock_running_job_or_other_uncertain_hold(store):
    first = prepared_job(store)
    second = prepared_job(store, 'r2', document='doc_b')
    with pytest.raises(JobError):
        store.reconcile_mutation(first, resolution='accept_current_state', evidence={'checked': True})
    for job_id in (first, second):
        store.finish(job_id, 'unknown')
    store.reconcile_mutation(first, resolution='restored_before', evidence={'name': 'До'})
    assert len(store.mutation_blockers('reconnected', 'new')) == 1
    assert store.mutation_blockers('reconnected', 'new')[0]['operation_id'] == second


def test_v1_migration_preserves_jobs_and_imports_unbound_uncertain_mutations(tmp_path):
    path = tmp_path / 'old.sqlite'
    db = sqlite3.connect(path)
    db.executescript('''CREATE TABLE jobs (operation_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
        digest TEXT NOT NULL, operation TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
        created_at REAL NOT NULL, updated_at REAL NOT NULL, result TEXT, error TEXT);
        PRAGMA user_version=1;''')
    for key, mutates, status in [('old_write', True, 'unknown'), ('old_read', False, 'running'),
                                ('old_ok', True, 'succeeded'), ('old_queued', True, 'queued')]:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)', (key, key, 'digest', 'test',
            json.dumps({'mutates': mutates, 'context': {}, 'arguments': {}}), status, 1, 1, None, None))
    db.commit()
    db.close()
    value = JobStore(path)
    try:
        assert value._db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert len(value.list()['items']) == 4
        assert value.get('old_ok')['status'] == 'succeeded'
        assert 'mutation' not in value.get('old_read')
        blockers = value.mutation_blockers('fresh', 'fresh_doc')
        assert {row['operation_id'] for row in blockers} == {'old_write', 'old_queued'}
        assert all(row['before_state']['checkpoint_unavailable'] for row in blockers)
    finally:
        value.close()


def test_unbound_uncertainty_creates_global_hold_without_waiting_for_restart(store):
    job, _ = store.create('unbound', 'old.mutation', {}, mutates=True)
    store.start(job['operation_id'])
    result = store.finish(job['operation_id'], 'unknown')
    assert result['mutation']['before_state']['checkpoint_unavailable'] is True
    assert store.mutation_blockers('current', 'any_document')
    # Uncertain reads do not create CAD write holds.
    read, _ = store.create('read', 'document.get', {})
    store.start(read['operation_id'])
    assert 'mutation' not in store.finish(read['operation_id'], 'unknown')


@pytest.fixture
def runner(store):
    value = JobRunner(store, Worker())
    yield value
    value.shutdown()


def execute(runner, request='r', *, revision='rev_1', current='rev_1', validate=True,
            fault=None, restoration=True, document='doc_a'):
    state = {'name': 'До'}
    events = []
    coordinator = MutationCoordinator(runner.store, 'connection_1')
    def prepare():
        events.append('prepare')
        return PreparedMutation(current, state.copy())
    def apply(prepared):
        events.append('apply')
        assert runner.store.get(job_id['value'])['mutation']['before_state'] == {'name': 'До'}
        state['name'] = 'После'
        if fault == 'exception':
            raise RuntimeError('COM write returned after changing the value')
        return {'name': state['name']} if fault != 'json' else object()
    def restore(before, prepared):
        events.append('restore')
        if restoration:
            state.update(before)
    job_id = {}
    entered = threading.Event()
    def run():
        assert entered.wait(2)
        return coordinator.execute(job_id['value'], document_id=document, configuration='Основная',
            expected_revision=revision, prepare=prepare, validate=lambda _: validate, apply=apply,
            inspect=lambda _: state.copy(), verify=lambda b, a, v: fault != 'postcondition',
            restore=restore, verify_restored=lambda b, a: b == a)
    job = runner.submit(request, 'feature.rename', {'name': 'После'}, run,
                        context=context(document, revision), mutates=True,
                        verify=lambda r: r['verified'] is True)
    job_id['value'] = job['operation_id']
    entered.set()
    return asyncio.run(runner.wait(job['operation_id'], 2)), state, events


def test_coordinator_checks_revision_before_any_native_write(runner):
    result, state, events = execute(runner, current='manually_changed')
    assert result['status'] == 'failed'
    assert result['error']['code'] == 'stale_revision'
    assert 'mutation' not in result
    assert state['name'] == 'До' and events == ['prepare']


def test_prewrite_recheck_failure_does_not_restore_concurrent_user_work(runner):
    result, state, events = execute(runner, validate=False)
    assert result['status'] == 'failed'
    assert result['mutation']['phase'] == 'not_started'
    assert state['name'] == 'До' and events == ['prepare']
    assert runner.store.mutation_blockers('connection_1', 'doc_a') == []


def test_success_keeps_before_after_proof_and_releases_document(runner):
    result, state, events = execute(runner)
    assert result['status'] == 'succeeded'
    assert result['mutation']['phase'] == 'committed'
    assert result['result']['before'] == {'name': 'До'}
    assert result['result']['after'] == {'name': 'После'}
    assert state['name'] == 'После' and events == ['prepare', 'apply']


@pytest.mark.parametrize('fault', ['exception', 'postcondition', 'json'])
def test_native_failure_postcondition_or_nonjson_result_restores_exact_prior_value(runner, fault):
    result, state, events = execute(runner, fault=fault)
    assert result['status'] == 'failed'
    assert result['mutation']['phase'] == 'rolled_back'
    assert state['name'] == 'До'
    assert events == ['prepare', 'apply', 'restore']


def test_unconfirmed_restoration_blocks_next_write_but_different_document_is_available(runner):
    uncertain, state, events = execute(runner, fault='exception', restoration=False)
    assert uncertain['status'] == 'unknown'
    assert uncertain['mutation']['phase'] == 'unresolved'
    assert state['name'] == 'После'
    blocked, unchanged, events = execute(runner, 'blocked')
    assert blocked['status'] == 'failed' and blocked['error']['code'] == 'document_mutation_blocked'
    assert unchanged['name'] == 'До' and events == []
    other, _, _ = execute(runner, 'other', document='doc_b')
    assert other['status'] == 'succeeded'


def test_verification_storage_failure_after_success_does_not_trigger_native_restoration(runner, monkeypatch):
    monkeypatch.setattr(runner.store, 'verify_mutation',
                        lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError('disk unavailable')))
    result, state, events = execute(runner)
    assert result['status'] == 'unknown'
    assert state['name'] == 'После' and events == ['prepare', 'apply']
    assert runner.store.mutation_blockers('connection_1', 'doc_a')
