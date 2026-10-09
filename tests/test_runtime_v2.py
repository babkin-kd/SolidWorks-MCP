"""CAD reads enter one worker; inspection/cancellation never need that worker."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from solidworks_mcp.jobs import JobError, JobStore
from solidworks_mcp.runtime_v2 import Runtime
from solidworks_mcp.server_v2 import create_app


class Worker:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)

    def submit(self, fn):
        return self.pool.submit(fn)

    def shutdown(self, timeout_s=5):
        self.pool.shutdown(wait=True)
        return True


def test_read_timeout_duplicate_late_result_and_release_in_owning_thread(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    entered, release = threading.Event(), threading.Event()
    calls, threads = [], []
    class Catalog:
        def __init__(self):
            threads.append(threading.get_ident())
        def list(self):
            calls.append('list')
            entered.set()
            assert release.wait(5)
            return {'documents': [{'document_id': 'doc_a'}]}
        def get(self, **arguments):
            calls.append('get')
            return arguments
        def close(self):
            threads.append(threading.get_ident())
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=Catalog)
    async def exercise():
        first = await runtime.read('r1', 'document.list', {}, timeout_s=0)
        assert entered.wait(2)
        second = await runtime.read('r1', 'document.list', {}, timeout_s=0)
        assert first['operation_id'] == second['operation_id']
        assert second['status'] == 'running'
        app = create_app(store, runtime)
        _, inspected = await app.call_tool('job_get', {'operation_id': first['operation_id']})
        assert inspected['status'] == 'running'
        waiting = await runtime.read('r2', 'document.get', {'document_id': 'doc_a', 'configuration': 'Основная'}, timeout_s=0)
        _, cancelled = await app.call_tool('job_cancel', {'operation_id': waiting['operation_id']})
        assert cancelled['data']['cancelled'] is True
        with pytest.raises(JobError) as failure:
            await runtime.read('r1', 'document.get', {}, timeout_s=0)
        assert failure.value.code == 'request_conflict'
        release.set()
        result = await runtime.read('r1', 'document.list', {}, timeout_s=2)
        assert result['status'] == 'succeeded'
        assert result['result']['documents'][0]['document_id'] == 'doc_a'
    try:
        asyncio.run(exercise())
    finally:
        release.set()
        assert runtime.shutdown()
    assert calls == ['list']
    assert threads[0] == threads[1] != threading.get_ident()


def test_no_cad_connection_for_discovery_or_invalid_requests(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    def forbidden():
        pytest.fail('Worker must not start for journal-only tools or invalid timeout.')
    runtime = Runtime(store, worker_factory=forbidden, catalog_factory=forbidden)
    async def exercise():
        app = create_app(store, runtime)
        await app.list_tools()
        _, info = await app.call_tool('system_get_info', {})
        assert info['data']['capabilities']['cad_documents'] is True
        _, bad = await app.call_tool('document_list', {'request_id': 'r1', 'timeout_s': -1})
        assert bad['error']['code'] == 'invalid_timeout'
        with pytest.raises(JobError):
            await runtime.read('r1', 'arbitrary.native.method', {})
        assert store.list()['items'] == []
    try:
        asyncio.run(exercise())
    finally:
        runtime.shutdown()


def test_unavailable_connection_is_durable_failed_job_and_next_request_can_connect(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    calls = []
    def catalog():
        calls.append('connect')
        raise JobError('cad_unavailable', 'SolidWorks is not running.')
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=catalog)
    async def exercise():
        app = create_app(store, runtime)
        _, first = await app.call_tool('document_list', {'request_id': 'r1'})
        assert first['status'] == 'failed' and first['error']['code'] == 'cad_unavailable'
        _, repeated = await app.call_tool('document_list', {'request_id': 'r1'})
        assert repeated['operation_id'] == first['operation_id']
        assert calls == ['connect']
        await app.call_tool('document_list', {'request_id': 'r2'})
        assert calls == ['connect', 'connect']
    try:
        asyncio.run(exercise())
    finally:
        runtime.shutdown()


def test_document_get_returns_explicit_context_without_activating_other_targets(tmp_path):
    from solidworks_mcp.documents import DocumentCatalog
    from test_document_catalog_v2 import Adapter, model
    adapter = Adapter()
    adapter.models = [model(title='Первая'), model(title='Вторая')]
    store = JobStore(tmp_path / 'jobs.sqlite')
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=lambda: DocumentCatalog(adapter))
    async def exercise():
        app = create_app(store, runtime)
        _, listed = await app.call_tool('document_list', {'request_id': 'list'})
        document_id = listed['data']['documents'][1]['document_id']
        _, selected = await app.call_tool('document_get', {'request_id': 'get', 'document_id': document_id,
                                                         'configuration': 'Вариант'})
        assert selected['status'] == 'succeeded'
        assert selected['data']['title'] == 'Вторая'
        assert selected['context'] == {'document_id': document_id, 'configuration': 'Вариант'}
        assert selected['data']['configuration_is_active'] is False
        _, invalid = await app.call_tool('document_get', {'request_id': 'missing', 'document_id': document_id,
                                                        'configuration': 'Нет такой'})
        assert invalid['error']['code'] == 'configuration_not_found'
        assert invalid['status'] == 'failed'
    try:
        asyncio.run(exercise())
    finally:
        runtime.shutdown()


def test_shutdown_timeout_keeps_owner_and_releases_catalog_after_late_read(tmp_path, monkeypatch):
    from solidworks_mcp.com_worker import ComWorker
    import pythoncom
    monkeypatch.setattr(pythoncom, 'CoInitialize', lambda: None)
    monkeypatch.setattr(pythoncom, 'CoUninitialize', lambda: None)
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    thread_ids = []
    class Catalog:
        def list(self):
            thread_ids.append(threading.get_ident())
            entered.set()
            assert release.wait(5)
            return {'documents': []}
        def close(self):
            thread_ids.append(threading.get_ident())
            closed.set()
    path = tmp_path / 'jobs.sqlite'
    store = JobStore(path)
    runtime = Runtime(store, worker_factory=ComWorker, catalog_factory=Catalog)
    try:
        job = asyncio.run(runtime.read('late', 'document.list', {}, timeout_s=0))
        assert entered.wait(2)
        assert runtime.shutdown(timeout_s=0.01) is False
        with pytest.raises(JobError) as failure:
            JobStore(path)
        assert failure.value.code == 'journal_in_use'
        assert store.get(job['operation_id'])['status'] == 'running'
        release.set()
        assert closed.wait(2)
        assert store.get(job['operation_id'])['status'] == 'succeeded'
        assert runtime.shutdown() is True
    finally:
        release.set()
        runtime.shutdown()
    assert thread_ids[0] == thread_ids[1] != threading.get_ident()


def test_native_connection_failure_retires_ids_without_replaying_job(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    events = []
    class Catalog:
        def list(self):
            events.append('read')
            raise RuntimeError('Native connection ended.')
        def close(self):
            events.append('close')
    def connect():
        events.append('connect')
        return Catalog()
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=connect)
    try:
        first = asyncio.run(runtime.read('a', 'document.list', {}))
        assert first['status'] == 'failed'
        asyncio.run(runtime.read('a', 'document.list', {}))
        assert events == ['connect', 'read', 'close']
        asyncio.run(runtime.read('b', 'document.list', {}))
        assert events == ['connect', 'read', 'close'] * 2
    finally:
        runtime.shutdown()
