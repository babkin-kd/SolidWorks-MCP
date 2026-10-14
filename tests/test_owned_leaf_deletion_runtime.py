"""Actual Runtime/JobStore/public dispatch; artificial leaf catalogs, never CAD."""
import asyncio
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event, get_ident
from types import SimpleNamespace as NS

from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.jobs import ExecutionFailure, JobError, JobStore
from solidworks_mcp.runtime_v2 import Runtime, READ_OPERATIONS, MUTATING_OPERATIONS
from solidworks_mcp.server_v2 import create_app


READ = 'feature.prepare_leaf_deletion'
WRITE = 'feature.delete_leaf'
OBJECT = 'feat_' + 'a' * 32
SKETCH = 'feat_' + 'b' * 32
SCOPE = 'owned_rectangular_leaf_extrusion_deletion_v1'


class Worker:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.closed = False

    def submit(self, function):
        return self.pool.submit(function)

    def shutdown(self, timeout_s=5):
        self.pool.shutdown(wait=True)
        self.closed = True
        return True


@pytest.fixture
def integrated(tmp_path, monkeypatch):
    store = JobStore(tmp_path / 'leaf-jobs.sqlite')
    x = NS(store=store, rectangles=[], deletions=[], workers=[], threads=[], catalog_calls=[],
           close_threads=[], deleted=False, writes=0, fault=None, pause=False,
           started=Event(), release=Event())
    documents = NS(adapter=object(), close=lambda: x.close_threads.append(get_ident()))

    class Construction:
        def __init__(self, catalog, journal, epoch):
            assert catalog is documents and journal is store
            self.documents, self.store, self.connection_epoch = catalog, journal, epoch
            self.ownership = NS(artificial_targets={OBJECT}, preserved_sketch=SKETCH)
            x.rectangles.append(self)
            x.threads.append(get_ident())

        def prepare_extrusion(self, **arguments):
            x.threads.append(get_ident())
            return dict(revision='artificial_rectangle_revision')

    class Deletion:
        def __init__(self, catalog, journal, epoch, ownership):
            assert catalog is documents and journal is store
            assert ownership is x.rectangles[0].ownership
            self.documents, self.store, self.connection_epoch, self.ownership = catalog, journal, epoch, ownership
            self.preparations, self.executions = [], []
            x.deletions.append(self)
            x.threads.append(get_ident())

        def prepare(self, **arguments):
            assert arguments['object_id'] in self.ownership.artificial_targets
            self.preparations.append(deepcopy(arguments))
            x.threads.append(get_ident())
            return dict(revision='artificial_full_leaf_revision', revision_scope=SCOPE,
                        delete_authorized=False, preserved_sketch_object_id=SKETCH)

        def delete(self, operation_id, **arguments):
            x.threads.append(get_ident())
            self.executions.append((operation_id, deepcopy(arguments)))
            if store.mutation_blockers(self.connection_epoch, arguments['document_id']):
                raise rejected('document_mutation_blocked', 'Artificial durable application hold.')
            assert arguments['object_id'] in self.ownership.artificial_targets
            job = store.get(operation_id)
            assert job['status'] == 'running' and job['payload']['mutates'] is True
            assert job['payload']['context']['object_id'] == OBJECT
            context = {key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')}
            store.prepare_mutation(operation_id, connection_epoch=self.connection_epoch,
                **context, before_state=dict(artificial_profile='BASE'), effect_scope='application')
            if x.pause:
                x.started.set()
                assert x.release.wait(5), 'Own artificial callback was not drained.'
            x.writes += 1
            if x.fault == 'unknown':
                raise ExecutionFailure('artificial_leaf_delete_unconfirmed', 'Artificial outcome.', uncertain=True)
            x.deleted = True
            self.ownership.artificial_targets.remove(OBJECT)
            store.verify_mutation(operation_id, outcome='committed',
                                  evidence=dict(artificial_profile='SKETCH', preserved_sketch=SKETCH))
            return dict(verified=True, artificial_deleted=True, preserved_sketch_object_id=SKETCH)

    def forbidden_generic_features(*args, **kwargs):
        raise AssertionError('Leaf routes must dispatch their own catalog before generic feature routing.')

    monkeypatch.setattr('solidworks_mcp.runtime_v2.RectangleConstructionCatalog', Construction)
    monkeypatch.setattr('solidworks_mcp.runtime_v2.OwnLeafDeletionCatalog', Deletion)
    monkeypatch.setattr('solidworks_mcp.runtime_v2.FeatureCatalog', forbidden_generic_features)

    def factory():
        x.catalog_calls.append(get_ident())
        return documents

    def worker_factory():
        worker = Worker()
        x.workers.append(worker)
        return worker

    runtime = Runtime(store, worker_factory=worker_factory, catalog_factory=factory)
    x.runtime, x.app = runtime, create_app(store, runtime)
    yield x
    x.release.set()
    assert runtime.shutdown()


def args(*, write=False):
    value = dict(document_id='doc_owned', configuration='Основная', object_id=OBJECT)
    if write:
        value['expected_revision'] = 'artificial_full_leaf_revision'
    return value


def call(x, tool, request, arguments, **extra):
    return asyncio.run(x.app.call_tool(tool, {'request_id': request, **arguments, **extra}))[1]


def test_exact_leaf_tools_and_lazy_metadata_start_no_worker_catalog_or_journal(integrated):
    x = integrated
    tools = {tool.name: tool for tool in asyncio.run(x.app.list_tools())}
    for name in ('feature_prepare_leaf_deletion', 'feature_delete_leaf'):
        schema = tools[name].inputSchema
        assert {'request_id', 'document_id', 'configuration', 'object_id'} <= set(schema['required'])
        assert schema['properties']['timeout_s']['default'] == 10.
        assert 'suppressed' not in schema['properties']
    assert 'expected_revision' in tools['feature_delete_leaf'].inputSchema['required']
    assert 'expected_revision' not in tools['feature_prepare_leaf_deletion'].inputSchema['properties']
    info = asyncio.run(x.app.call_tool('system_get_info', {}))[1]['data']
    assert WRITE in info['implemented_mutations'] and READ not in info['implemented_mutations']
    assert SCOPE in info['mutation_revision_scopes']
    assert 'feature.delete' not in info['implemented_mutations']
    assert set(info['implemented_mutations']) == set(MUTATING_OPERATIONS)
    assert not x.workers and not x.catalog_calls and not x.threads and not x.store.list()['items']
    assert x.runtime._runner is x.runtime._owned_leaf_deletion is x.runtime._rectangle_construction is None


@pytest.mark.parametrize('first', ['preview', 'construction'])
def test_preview_first_or_construction_first_reuses_one_original_ownership_and_sta(integrated, first):
    x = integrated

    async def exercise():
        async def preview():
            return await x.runtime.read('leaf-preview', READ, args())

        async def rectangle():
            return await x.runtime.read('rectangle-preview', 'part.prepare_rectangle_extrusion',
                dict(document_id='doc_owned', configuration='Основная', sketch_object_id=SKETCH, depth_mm=10.))

        await (preview if first == 'preview' else rectangle)()
        await (rectangle if first == 'preview' else preview)()
        changed = await x.runtime.mutate('delete', WRITE, args(write=True))
        assert changed['status'] == 'succeeded'
        assert len(x.rectangles) == len(x.deletions) == len(x.catalog_calls) == len(x.workers) == 1
        assert x.runtime._owned_leaf_deletion is x.deletions[0]
        assert x.runtime._rectangle_construction is x.rectangles[0]
        assert x.deletions[0].ownership is x.rectangles[0].ownership
        assert x.deletions[0].ownership.preserved_sketch == SKETCH
        assert x.deletions[0].connection_epoch == x.rectangles[0].connection_epoch == x.runtime._connection_epoch

    asyncio.run(exercise())
    assert len(set(x.threads + x.catalog_calls)) == 1 and x.threads[0] != get_ident()


def test_public_preview_delete_replay_conflict_bind_original_request_and_exact_context(integrated):
    x = integrated
    prepared = call(x, 'feature_prepare_leaf_deletion', 'preview', args())
    assert prepared['status'] == 'succeeded' and prepared['data']['delete_authorized'] is False
    preview = x.store.get(prepared['operation_id'])
    assert preview['operation'] == READ and preview['payload']['mutates'] is False
    assert preview['payload']['arguments'] == args() and 'mutation' not in preview
    assert x.deletions[0].preparations == [args()]
    arguments = args(write=True)
    changed = call(x, 'feature_delete_leaf', 'delete-original', arguments)
    assert changed['status'] == 'succeeded' and x.deleted is True
    job = x.store.get(changed['operation_id'])
    assert job['operation'] == WRITE and job['request_id'] == 'delete-original'
    assert job['payload']['arguments'] == arguments and job['payload']['mutates'] is True
    assert changed['context'] == arguments
    assert job['mutation']['phase'] == 'committed'
    assert job['mutation']['before_state']['_mutation_effect_scope'] == 'application'
    assert job['mutation']['expected_revision'] == arguments['expected_revision']
    assert x.deletions[0].executions == [(changed['operation_id'], arguments)]
    assert call(x, 'feature_delete_leaf', 'delete-original', arguments) == changed
    assert x.writes == 1 and len(x.deletions[0].executions) == 1
    conflict = call(x, 'feature_delete_leaf', 'delete-original', {**arguments, 'expected_revision': 'different'})
    assert conflict['status'] == 'failed' and conflict['error']['code'] == 'request_conflict'
    assert x.writes == 1 and len(x.store.list()['items']) == 2


def test_unknown_delete_replay_retains_application_hold_for_other_documents(integrated):
    x = integrated
    x.fault = 'unknown'
    first = call(x, 'feature_delete_leaf', 'unknown-original', args(write=True))
    assert first['status'] == 'unknown' and first['error']['requires_reconciliation'] is True
    assert x.store.get(first['operation_id'])['mutation']['phase'] == 'unresolved'
    assert call(x, 'feature_delete_leaf', 'unknown-original', args(write=True)) == first
    assert x.store.mutation_blockers(x.runtime._connection_epoch, 'different_document')
    held = call(x, 'feature_delete_leaf', 'new-other-doc', {**args(write=True), 'document_id': 'different_document'})
    assert held['status'] == 'failed' and held['error']['code'] == 'document_mutation_blocked'
    assert x.writes == 1 and x.deleted is False
    assert len(x.deletions[0].executions) == 2


def test_timeout_keeps_same_running_delete_then_public_job_get_returns_late_result(integrated):
    x = integrated
    x.pause = True

    async def exercise():
        first = await x.runtime.mutate('late-original', WRITE, args(write=True), timeout_s=0.)
        assert first['status'] in ('queued', 'running') and x.started.wait(5)
        original = first['operation_id']
        replay = await x.runtime.mutate('late-original', WRITE, args(write=True), timeout_s=0.)
        assert replay['operation_id'] == original and replay['status'] == 'running'
        assert x.store.cancel(original)['cancelled'] is False
        x.release.set()
        terminal = await x.runtime._runner.wait(original, timeout_s=5.)
        assert terminal['status'] == 'succeeded' and terminal['operation_id'] == original
        public = (await x.app.call_tool('job_get', {'operation_id': original}))[1]
        assert public['status'] == 'succeeded' and public['data']['result'] == terminal['result']
        assert public['data']['mutation']['phase'] == 'committed'
        assert x.writes == 1 and len(x.deletions[0].executions) == 1

    try:
        asyncio.run(exercise())
    finally:
        x.release.set()


@pytest.mark.parametrize('operation,wrong_method', [(READ, 'mutate'), (WRITE, 'read')])
def test_leaf_read_mutate_whitelists_reject_swapped_routes_before_worker_or_job(integrated, operation, wrong_method):
    x = integrated
    assert READ in READ_OPERATIONS and READ not in MUTATING_OPERATIONS
    assert WRITE in MUTATING_OPERATIONS and WRITE not in READ_OPERATIONS
    with pytest.raises(JobError) as error:
        asyncio.run(getattr(x.runtime, wrong_method)('wrong', operation, args(write=True)))
    assert error.value.code == 'unsupported_operation'
    assert not x.workers and not x.catalog_calls and not x.store.list()['items']


@pytest.mark.parametrize('tool,missing', [('feature_prepare_leaf_deletion', 'request_id'),
    ('feature_prepare_leaf_deletion', 'document_id'), ('feature_prepare_leaf_deletion', 'configuration'),
    ('feature_prepare_leaf_deletion', 'object_id'), ('feature_delete_leaf', 'expected_revision')])
def test_public_explicit_required_fields_cannot_default_or_create_jobs(integrated, tool, missing):
    x = integrated
    arguments = dict(request_id='invalid', **args(write=tool == 'feature_delete_leaf'))
    arguments.pop(missing)
    with pytest.raises(ToolError):
        asyncio.run(x.app.call_tool(tool, arguments))
    assert not x.workers and not x.store.list()['items']


@pytest.mark.parametrize('invalid', [-1., 121., float('inf'), float('nan'), '5', True])
def test_public_wait_validation_prevents_durable_dispatch(integrated, invalid):
    x = integrated
    with pytest.raises(ToolError):
        call(x, 'feature_delete_leaf', 'invalid-wait', args(write=True), timeout_s=invalid)
    assert not x.workers and not x.store.list()['items']


def test_leaf_catalog_original_registry_and_document_release_in_owning_worker(integrated):
    x = integrated
    call(x, 'feature_prepare_leaf_deletion', 'preview', args())
    assert x.runtime.shutdown()
    assert x.runtime._owned_leaf_deletion is x.runtime._rectangle_construction is None
    assert x.runtime._catalog is x.runtime._connection_epoch is None
    assert x.close_threads == [x.threads[0]] and x.close_threads[0] != get_ident()
    assert x.workers[0].closed is True
    with pytest.raises(JobError) as error:
        asyncio.run(x.runtime.read('after-shutdown', READ, args()))
    assert error.value.code == 'runtime_stopped'
    assert len(x.workers) == 1
