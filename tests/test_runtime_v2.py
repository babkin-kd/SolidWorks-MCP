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


def test_document_creation_runtime_uses_one_catalog_and_real_durable_application_context(tmp_path):
    from solidworks_mcp.documents import DocumentCatalog
    from test_document_creation_v2 import Adapter
    template = tmp_path / 'Деталь.prtdot'
    template.write_bytes(b'artificial template')
    adapter = Adapter(template)
    store = JobStore(tmp_path / 'documents.sqlite')
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=lambda: DocumentCatalog(adapter))
    async def exercise():
        listed = await runtime.read('templates', 'document.list_templates', {})
        template_id = listed['result']['templates'][0]['template_id']
        prepared = await runtime.read('prepare', 'document.prepare_create_part', {'template_id': template_id, 'name': 'Новая деталь'})
        arguments = dict(document_id=prepared['result']['application_id'], configuration='',
            template_id=template_id, name='Новая деталь', configuration_name='Основная', expected_revision=prepared['result']['revision'])
        created = await runtime.mutate('create', 'document.create_part', arguments)
        assert created['status'] == 'succeeded' and created['mutation']['phase'] == 'committed'
        assert created['payload']['context']['document_id'].startswith('app_')
        assert created['result']['after']['created_document_id'].startswith('doc_')
        assert await runtime.mutate('create', 'document.create_part', arguments) == created
        assert adapter.count == 1
    try: asyncio.run(exercise())
    finally: runtime.shutdown()


def test_export_without_trusted_directory_does_not_start_worker_or_record_job(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    runtime = Runtime(store, worker_factory=lambda: pytest.fail('No worker before trusted output root.'))
    try:
        with pytest.raises(JobError) as failure:
            asyncio.run(runtime.read('r', 'export.prepare', {'document_id': 'doc', 'configuration': 'Основная'}))
        assert failure.value.code == 'export_output_not_configured'
        assert store.list()['items'] == []
    finally:
        runtime.shutdown()


def test_priority_part_runtime_routes_preparation_and_single_durable_creation(tmp_path):
    from solidworks_mcp.documents import DocumentCatalog
    from test_part_construction_mutation_v2 import Adapter, feature, model
    adapter = Adapter()
    adapter.mutation_guard = adapter.guard
    part = model(title='Пластина', configurations=['Основная'])
    part.features, part.dimensions, part.displays = [feature(1, 'Передняя', kind='RefPlane')], [], []
    adapter.models = [part]
    adapter.context['configuration_needs_rebuild'] = {'Основная': False}
    store = JobStore(tmp_path / 'parts.sqlite')
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=lambda: DocumentCatalog(adapter))
    async def exercise():
        listing = await runtime.read('documents', 'document.list', {})
        context = dict(document_id=listing['result']['documents'][0]['document_id'], configuration='Основная')
        tree = await runtime.read('features', 'feature.list', context)
        args = dict(context, plane_object_id=tree['result']['items'][0]['object_id'], width_mm=40., height_mm=20., depth_mm=10.)
        prepared = await runtime.read('prepare', 'part.prepare_base_extrusion', args)
        assert prepared['status'] == 'succeeded'
        args['expected_revision'] = prepared['result']['revision']
        created = await runtime.mutate('create', 'part.create_base_extrusion', args)
        assert created['status'] == 'succeeded' and created['result']['verified']
        duplicate = await runtime.mutate('create', 'part.create_base_extrusion', args)
        assert duplicate['operation_id'] == created['operation_id'] and adapter.creation_count == 1
        assert runtime._parts is not None
    try:
        asyncio.run(exercise())
    finally:
        assert runtime.shutdown() is True
        store.close()
    assert runtime._parts is None


def test_internal_dimension_runtime_routes_durable_write_and_releases_on_sta(tmp_path):
    from solidworks_mcp.documents import DocumentCatalog
    from test_dimension_domain_v2 import Adapter, dimension, feature, model

    adapter = Adapter()
    adapter.mutation_guard = adapter.guard
    owned = model(title='Проверка размера')
    owned.features = [feature(1)]
    owned.dimensions = [dimension(1)]
    adapter.models = [owned]
    store = JobStore(tmp_path / 'jobs.sqlite')
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=lambda: DocumentCatalog(adapter))

    async def exercise():
        documents = await runtime.read('docs', 'document.list', {})
        doc_id = documents['result']['documents'][0]['document_id']
        context = {'document_id': doc_id, 'configuration': 'Основная'}
        page = await runtime.read('dims', 'dimension.list', context)
        assert page['status'] == 'succeeded'
        args = {**context, 'object_id': page['result']['items'][0]['object_id'],
                'expected_revision': page['result']['revision'], 'value': 25., 'unit': 'mm'}
        changed = await runtime.mutate('change', 'dimension.set_value', args)
        assert changed['status'] == 'succeeded'
        assert changed['mutation']['phase'] == 'committed'
        assert changed['mutation']['before_state']['_mutation_effect_scope'] == 'application'
        duplicate = await runtime.mutate('change', 'dimension.set_value', args)
        assert duplicate['operation_id'] == changed['operation_id']
        readback = await runtime.read('readback', 'dimension.get', {**context, 'object_id': args['object_id']})
        assert readback['result']['dimension']['values']['Основная'] == 25.
        assert len(adapter.dimension_writes) == adapter.guard_entries == 1
        assert runtime._dimensions is not None

    try:
        asyncio.run(exercise())
    finally:
        assert runtime.shutdown()
    assert runtime._dimensions is None and runtime._exports is None
    assert all(watch.closed for watch in adapter.watches.values())


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


def test_mutation_connection_failure_before_execution_does_not_create_uncertain_hold(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    def unavailable():
        raise JobError('cad_unavailable', 'CAD is not running.')
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=unavailable)
    try:
        result = asyncio.run(runtime.mutate('r', 'feature.rename', {
            'document_id': 'doc_a', 'configuration': 'Основная', 'object_id': 'feat_a',
            'expected_revision': 'rev_a', 'name': 'Деталь'}))
        assert result['status'] == 'failed'
        assert result['error']['code'] == 'cad_unavailable'
        assert store.mutation_blockers('connection', 'doc_a') == []
    finally:
        runtime.shutdown()


def test_actual_mcp_feature_tools_use_worker_and_real_durable_protocol(tmp_path):
    from solidworks_mcp.documents import DocumentCatalog
    from test_feature_domain_v2 import Adapter, feature, model
    adapter = Adapter()
    first, second = model(title='Первая'), model(title='Вторая')
    first.features, second.features = [feature(1)], [feature(1, 'Вторая операция')]
    adapter.models = [first, second]
    store = JobStore(tmp_path / 'jobs.sqlite')
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=lambda: DocumentCatalog(adapter))
    async def exercise():
        app = create_app(store, runtime)
        _, listed = await app.call_tool('document_list', {'request_id': 'documents'})
        doc_id = listed['data']['documents'][0]['document_id']
        _, page = await app.call_tool('feature_list', {'request_id': 'features',
            'document_id': doc_id, 'configuration': 'Основная'})
        args = {'request_id': 'rename', 'document_id': doc_id, 'configuration': 'Основная',
                'object_id': page['data']['items'][0]['object_id'], 'expected_revision': page['data']['revision'],
                'name': 'Основание'}
        _, result = await app.call_tool('feature_rename', args)
        assert result['status'] == 'succeeded'
        assert result['data']['value']['name'] == 'Основание'
        assert result['context']['expected_revision'] == page['data']['revision']
        _, duplicate = await app.call_tool('feature_rename', args)
        assert duplicate['operation_id'] == result['operation_id']
        _, proof = await app.call_tool('job_get', {'operation_id': result['operation_id']})
        assert proof['data']['mutation']['phase'] == 'committed'
        _, readback = await app.call_tool('feature_get', {'request_id': 'get',
            'document_id': doc_id, 'configuration': 'Основная', 'object_id': args['object_id']})
        assert readback['data']['feature']['name'] == 'Основание'
        assert adapter.writes == [(1, 'Основание')]
        assert second.features[0].state['name'] == 'Вторая операция'
    try:
        asyncio.run(exercise())
    finally:
        runtime.shutdown()
