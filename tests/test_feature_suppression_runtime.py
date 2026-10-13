"""Real runtime/jobs/create_app dispatch, artificial catalogs only; no CAD."""
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


READ = 'feature.prepare_suppression'
WRITE = 'feature.set_suppressed'
OBJECT = 'feat_' + 'a' * 32


class Worker:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)
    def submit(self, function):
        return self.pool.submit(function)
    def shutdown(self, timeout_s=5):
        self.pool.shutdown(wait=True)
        return True


@pytest.fixture
def integrated(tmp_path, monkeypatch):
    store = JobStore(tmp_path / 'jobs.sqlite')
    x = NS(store=store, rectangles=[], suppressions=[], threads=[], catalog_calls=[], close_threads=[],
        suppressed=False, writes=0, fault=None, pause=False, started=Event(), release=Event())
    documents = NS(adapter=object(), close=lambda:x.close_threads.append(get_ident()))
    def write(operation_id, arguments):
        x.threads.append(get_ident())
        if store.mutation_blockers(x.runtime._connection_epoch, arguments['document_id']):
            raise rejected('document_mutation_blocked', 'Artificial durable application hold.')
        context = {key:arguments[key] for key in ('document_id','configuration','expected_revision')}
        assert store.get(operation_id)['status'] == 'running'
        assert store.get(operation_id)['payload']['context']['object_id'] == OBJECT
        store.prepare_mutation(operation_id, connection_epoch=x.runtime._connection_epoch,
            **context, before_state={'artificial_suppressed':x.suppressed}, effect_scope='application')
        if x.pause:
            x.started.set()
            assert x.release.wait(5), 'Own pure callback was not drained.'
        x.writes += 1
        if x.fault == 'unknown':
            raise ExecutionFailure('artificial_lost_confirmation', 'Pure artificial outcome.', uncertain=True)
        x.suppressed = arguments['suppressed']
        evidence = {'artificial_readback':x.suppressed}
        store.verify_mutation(operation_id, outcome='committed', evidence=evidence)
        return dict(verified=True, artificial_suppressed=x.suppressed)
    class Construction:
        def __init__(self, catalog, journal, epoch):
            assert catalog is documents and journal is store
            self.documents, self.store, self.connection_epoch = catalog, journal, epoch
            self.ownership = NS(artificial_targets={OBJECT})
            x.rectangles.append(self); x.threads.append(get_ident())
        def prepare_sketch(self, **arguments):
            return {'revision':'artificial_rectangle_revision'}
        def prepare_extrusion(self, **arguments):
            return {'revision':'artificial_rectangle_revision'}
    class Suppression:
        def __init__(self, catalog, journal, epoch, ownership):
            assert catalog is documents and journal is store
            assert ownership is x.rectangles[0].ownership
            self.documents, self.store, self.connection_epoch, self.ownership = catalog, journal, epoch, ownership
            self.preparations = []
            x.suppressions.append(self); x.threads.append(get_ident())
        def prepare(self, **arguments):
            assert arguments['object_id'] in self.ownership.artificial_targets
            self.preparations.append(deepcopy(arguments)); x.threads.append(get_ident())
            return dict(revision='artificial_full_revision', suppressed=x.suppressed,
                        requested_suppressed=arguments['suppressed'])
        def set_suppressed(self, operation_id, **arguments):
            assert arguments['object_id'] in self.ownership.artificial_targets
            return write(operation_id, arguments)
    monkeypatch.setattr('solidworks_mcp.runtime_v2.RectangleConstructionCatalog', Construction)
    monkeypatch.setattr('solidworks_mcp.runtime_v2.FeatureSuppressionCatalog', Suppression)
    def factory():
        x.catalog_calls.append(get_ident())
        return documents
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=factory)
    x.runtime, x.app = runtime, create_app(store, runtime)
    yield x
    x.release.set()
    assert runtime.shutdown()


def args(*, write=False, suppressed=True):
    result = dict(document_id='doc_owned', configuration='Основная', object_id=OBJECT, suppressed=suppressed)
    if write: result['expected_revision'] = 'artificial_full_revision'
    return result


def call(x, tool, request, arguments, **extra):
    return asyncio.run(x.app.call_tool(tool, {'request_id':request, **arguments, **extra}))[1]


def test_create_app_discovers_two_exact_tools_and_metadata_without_starting_catalog_or_worker(integrated):
    x = integrated
    tools = {tool.name:tool for tool in asyncio.run(x.app.list_tools())}
    for name in ('feature_prepare_suppression','feature_set_suppressed'):
        assert name in tools
        properties = tools[name].inputSchema['properties']
        assert properties['suppressed']['type'] == 'boolean'
        assert properties['timeout_s']['default'] == 10.
    assert 'expected_revision' in tools['feature_set_suppressed'].inputSchema['required']
    info = asyncio.run(x.app.call_tool('system_get_info', {}))[1]['data']
    assert WRITE in info['implemented_mutations'] and READ not in info['implemented_mutations']
    assert 'owned_rectangular_blind_base_suppression_v1' in info['mutation_revision_scopes']
    assert 'feature.delete' not in info['implemented_mutations']
    assert set(info['implemented_mutations']) == set(MUTATING_OPERATIONS)
    assert not x.catalog_calls and not x.threads and x.store.list()['items'] == []
    assert x.runtime._runner is None and x.runtime._feature_suppression is None and x.runtime._rectangle_construction is None


@pytest.mark.parametrize('first', ['suppression','construction'])
def test_lazy_suppression_and_rectangle_workflows_share_exact_single_owned_registry(integrated, first):
    x = integrated
    async def exercise():
        async def suppression():
            return await x.runtime.read('suppression_prepare', READ, args())
        async def rectangle():
            return await x.runtime.read('rectangle_prepare', 'part.prepare_rectangle_extrusion',
                dict(document_id='doc_owned', configuration='Основная', sketch_object_id=OBJECT, depth_mm=10.))
        await (suppression if first == 'suppression' else rectangle)()
        await (rectangle if first == 'suppression' else suppression)()
        changed = await x.runtime.mutate('write', WRITE, args(write=True))
        assert changed['status'] == 'succeeded'
        assert len(x.rectangles) == len(x.suppressions) == len(x.catalog_calls) == 1
        assert x.runtime._rectangle_construction is x.rectangles[0]
        assert x.runtime._feature_suppression is x.suppressions[0]
        assert x.suppressions[0].ownership is x.rectangles[0].ownership
        assert x.suppressions[0].connection_epoch == x.rectangles[0].connection_epoch == x.runtime._connection_epoch
    asyncio.run(exercise())
    assert len(set(x.threads)) == 1 and x.threads[0] != get_ident()


@pytest.mark.parametrize('suppressed', [False, True])
def test_public_prepare_mutate_replay_conflict_preserve_exact_durable_context_and_state(integrated, suppressed):
    x = integrated
    prepared = call(x, 'feature_prepare_suppression', 'prepare', args(suppressed=suppressed))
    assert prepared['status'] == 'succeeded' and prepared['data']['revision'] == 'artificial_full_revision'
    arguments = args(write=True, suppressed=suppressed)
    changed = call(x, 'feature_set_suppressed', 'write', arguments)
    assert changed['status'] == 'succeeded'
    job = x.store.get(changed['operation_id'])
    assert job['operation'] == WRITE and job['mutation']['phase'] == 'committed'
    assert job['payload']['arguments'] == arguments
    assert changed['context'] == {key:arguments[key] for key in ('document_id','configuration','object_id','expected_revision')}
    assert job['mutation']['before_state']['_mutation_effect_scope'] == 'application'
    assert call(x, 'feature_set_suppressed', 'write', arguments) == changed and x.writes == 1
    conflict = call(x, 'feature_set_suppressed', 'write', {**arguments, 'suppressed':not suppressed})
    assert conflict['status'] == 'failed' and conflict['error']['code'] == 'request_conflict'
    assert x.writes == 1


def test_unknown_replay_and_new_request_retain_existing_application_hold(integrated):
    x = integrated; x.fault = 'unknown'
    arguments = args(write=True)
    first = call(x, 'feature_set_suppressed', 'unknown', arguments)
    assert first['status'] == 'unknown' and first['error']['requires_reconciliation'] is True
    assert call(x, 'feature_set_suppressed', 'unknown', arguments) == first
    held = call(x, 'feature_set_suppressed', 'new_request', arguments)
    assert held['status'] == 'failed' and held['error']['code'] == 'document_mutation_blocked'
    assert x.writes == 1
    assert x.store.mutation_blockers(x.runtime._connection_epoch, 'another_document')


def test_wait_zero_preserves_late_same_operation_without_native_cancellation_or_second_dispatch(integrated):
    x = integrated; x.pause = True
    async def exercise():
        first = await x.runtime.mutate('late', WRITE, args(write=True), timeout_s=0.)
        assert first['status'] in ('queued','running')
        assert x.started.wait(5)
        original = first['operation_id']
        replay = await x.runtime.mutate('late', WRITE, args(write=True), timeout_s=0.)
        assert replay['operation_id'] == original and replay['status'] == 'running'
        assert x.store.cancel(original)['cancelled'] is False
        x.release.set()
        terminal = await x.runtime._runner.wait(original, timeout_s=5.)
        assert terminal['status'] == 'succeeded' and x.writes == 1
    try: asyncio.run(exercise())
    finally: x.release.set()


@pytest.mark.parametrize('operation,wrong_method', [(READ,'mutate'), (WRITE,'read')])
def test_read_mutate_whitelists_refuse_swapped_routes_before_recording_or_worker(integrated, operation, wrong_method):
    x = integrated
    assert READ in READ_OPERATIONS and READ not in MUTATING_OPERATIONS
    assert WRITE in MUTATING_OPERATIONS and WRITE not in READ_OPERATIONS
    with pytest.raises(JobError) as error:
        asyncio.run(getattr(x.runtime, wrong_method)('wrong', operation, args(write=True)))
    assert error.value.code == 'unsupported_operation'
    assert x.runtime._runner is None and not x.catalog_calls and x.store.list()['items'] == []


@pytest.mark.parametrize('invalid', [0, 1, None, 'true', {}])
def test_public_strict_state_validation_does_not_create_catalog_or_job(integrated, invalid):
    x = integrated
    with pytest.raises(ToolError): call(x, 'feature_set_suppressed', 'invalid', args(write=True, suppressed=invalid))
    assert x.runtime._runner is None and x.store.list()['items'] == []


def test_suppression_and_shared_ownership_release_only_in_the_owning_worker(integrated):
    x = integrated
    call(x, 'feature_prepare_suppression', 'prepare', args())
    assert x.runtime.shutdown()
    assert x.runtime._feature_suppression is None and x.runtime._rectangle_construction is None
    assert x.runtime._catalog is None and x.runtime._connection_epoch is None
    assert x.close_threads == [x.threads[0]] and x.close_threads[0] != get_ident()
