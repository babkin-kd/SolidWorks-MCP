"""COM apartment ownership and worker lifecycle without launching CAD."""

import asyncio
import threading

import pytest

from solidworks_mcp.com_worker import ComWorker
from solidworks_mcp.errors import SolidWorksError
from solidworks_mcp.jobs import JobError, JobRunner, JobStore


def test_com_initialization_failure_returns_instead_of_hanging(monkeypatch):
    def fail():
        raise OSError('Apartment initialization failed')
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoInitialize', fail)
    with pytest.raises(SolidWorksError, match='Apartment initialization failed'):
        ComWorker()


def test_same_sta_for_apartment_and_all_calls_and_drain_before_shutdown(monkeypatch):
    events = []
    main_thread = threading.get_ident()
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoInitialize',
                        lambda: events.append(('init', threading.get_ident())))
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoUninitialize',
                        lambda: events.append(('release', threading.get_ident())))
    worker = ComWorker()
    futures = [worker.submit(lambda: events.append(('call', threading.get_ident()))) for _ in range(5)]
    assert worker.shutdown()
    assert all(future.done() for future in futures)
    assert [kind for kind, _ in events] == ['init'] + ['call'] * 5 + ['release']
    assert len({identity for _, identity in events}) == 1
    assert events[0][1] != main_thread
    with pytest.raises(SolidWorksError, match='shut down'):
        worker.submit(lambda: None)
    assert worker.shutdown()


def test_late_sta_completion_retains_journal_ownership_during_shutdown(tmp_path, monkeypatch):
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoInitialize', lambda: None)
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoUninitialize', lambda: None)
    path = tmp_path / 'jobs.sqlite'
    runner = JobRunner(JobStore(path), ComWorker())
    started, release = threading.Event(), threading.Event()
    def build():
        started.set()
        assert release.wait(2)
        return {'name': 'Деталь'}
    job = runner.submit('late-stop', 'part.create', {}, build, mutates=True, verify=lambda _: True)
    try:
        assert started.wait(1)
        assert runner.shutdown(timeout_s=0.01) is False
        assert runner.store.get(job['operation_id'])['status'] == 'running'
        with pytest.raises(JobError, match='Another runtime'):
            JobStore(path)
    finally:
        release.set()
    assert asyncio.run(runner.wait(job['operation_id'], 2))['status'] == 'succeeded'
    assert runner.shutdown()
    reopened = JobStore(path)
    try:
        assert reopened.get(job['operation_id'])['status'] == 'succeeded'
    finally:
        reopened.close()


def test_message_pump_runs_while_idle_and_finalizers_release_on_sta(monkeypatch):
    events = []
    pumped = threading.Event()
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoInitialize',
                        lambda: events.append(('init', threading.get_ident())))
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoUninitialize',
                        lambda: events.append(('uninit', threading.get_ident())))
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.PumpWaitingMessages',
                        lambda: (pumped.set(), 0)[1])
    worker = ComWorker(pump_messages=True)
    worker.add_finalizer(lambda: events.append(('close_watch', threading.get_ident())))
    assert pumped.wait(1)
    assert worker.shutdown()
    assert [name for name, _ in events] == ['init', 'close_watch', 'uninit']
    assert len({thread for _, thread in events}) == 1


def test_failing_pump_finishes_unstarted_jobs_and_releases_on_sta(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    should_fail = threading.Event()
    closed = threading.Event()
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoInitialize', lambda: None)
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.CoUninitialize', lambda: None)
    monkeypatch.setattr('solidworks_mcp.com_worker.pythoncom.PumpWaitingMessages',
                        lambda: int(should_fail.is_set()))
    store = JobStore(tmp_path / 'jobs.sqlite')
    worker = ComWorker(pump_messages=True)
    worker.add_finalizer(closed.set)
    runner = JobRunner(store, worker)
    first = runner.submit('busy', 'test', {}, lambda: (entered.set(), release.wait(2), {})[2])
    try:
        assert entered.wait(1)
        waiting = runner.submit('waiting', 'read', {}, lambda: pytest.fail('Must not run after WM_QUIT.'))
        should_fail.set()
    finally:
        release.set()
    assert closed.wait(2)
    assert store.get(first['operation_id'])['status'] == 'succeeded'
    result = store.get(waiting['operation_id'])
    assert result['status'] == 'failed' and result['error']['code'] == 'dispatch_failed'
    assert runner.shutdown()
