"""Original typed facade/domain/worker/store integration; artificial CAD only."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

from mcp.types import JSONRPCMessage
from solidworks_mcp.dimension_tools_v2 import register_dimension_tools
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobStore
from solidworks_mcp.runtime_v2 import Runtime
from solidworks_mcp.server_v2 import response, failure
from test_dimension_domain_v2 import setup
from test_b4_dimension_return import prepared, helper as returned
from test_b4_installed_finish import helper as finished, PythonWorker
from test_b4_native_admission import helper as admitted


class Registry:
    def __init__(self):
        self.functions = {}

    def tool(self):
        def collect(function):
            self.functions[function.__name__] = function
            return function
        return collect


def rpc_reply(rpc_id, envelope):
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=rpc_id, result=dict(
        content=[], structuredContent=envelope.model_dump(mode='json'))))


def request(rpc_id, name, arguments):
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=rpc_id, method='tools/call',
                                             params=dict(name=name, arguments=arguments)))


def test_original_facade_return_proof_bound_poll_and_explicit_finish_release(prepared, tmp_path):
    # Borrow only artificial model data; this new owner creates its own actual
    # JobStore/Runtime. No existing store, job or runtime is adopted by the seam.
    original_count = prepared.store._db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    barrier_receipts, return_receipts, pipe = [], [], []
    seam = finished.InstalledFinishSeam(module, journal_path=tmp_path / 'new-owner.sqlite',
                                       persist=barrier_receipts.append).install()
    store = module.JobStore(seam.path)
    prepared.adapter.mutation_guard = prepared.catalog.mutation_guard
    runtime = module.Runtime(store, worker_factory=PythonWorker,
                             catalog_factory=lambda: DocumentCatalog(prepared.adapter))
    discovery = asyncio.run(runtime.read('own-documents', 'document.list', {}, timeout_s=5))
    assert discovery['status'] == 'succeeded'
    document_id = discovery['result']['documents'][0]['document_id']
    listed = asyncio.run(runtime.read('own-dimensions', 'dimension.list',
        dict(document_id=document_id, configuration='Основная'), timeout_s=5))
    assert listed['status'] == 'succeeded'
    page = listed['result']
    context = dict(document_id=document_id, configuration='Основная',
                   object_id=page['items'][0]['object_id'], expected_revision=page['revision'])
    arguments = dict(context, value=12., unit='mm')
    payload = dict(arguments=arguments, context=context, mutates=True)
    request_id = 'original-integration-target'
    proof = returned.DimensionReturnObserver(runtime, request_id=request_id, payload=payload,
                                            persist=return_receipts.append).install()
    arm = store.arm(runtime=runtime, request_id=request_id, operation='dimension.set_value', payload=payload)
    cad_arguments = dict(arguments, request_id=request_id, timeout_s=0.)
    controller = admitted.DimensionAdmission(cad_requests=(dict(name='dimension_set_value', arguments=cad_arguments),),
        observation_requests=(), target_operation='dimension.set_value', target_payload=payload, target_poll_limit=2)
    registry = Registry()
    register_dimension_tools(registry, runtime, response, failure)

    def write(value):
        pipe.append(value)
        return len(value)

    try:
        controller.write_message(request(1, 'dimension_set_value', cad_arguments), write, lambda: None)
        raw = asyncio.run(registry.functions['dimension_set_value'](**cad_arguments))
        assert raw.status in ('queued', 'running')
        controller.observe_response(rpc_reply(1, raw))
        assert store.wait_reached(5), (store.get(raw.operation_id), proof.observation())
        assert proof.observation()['persisted'] is True
        assert proof.observation()['callback_live'] is False
        assert len(prepared.adapter.dimension_writes) == len(return_receipts) == len(barrier_receipts) == 1
        assert prepared.application.CommandInProgress is False
        job = store.get(raw.operation_id)
        assert job['status'] == 'running' and job['mutation']['phase'] == 'prepared'
        assert job['mutation']['verification']['outcome'] == 'committed'
        assert return_receipts[0]['operation_id'] == barrier_receipts[0]['operation_id'] == raw.operation_id
        assert return_receipts[0]['return_result'] == barrier_receipts[0]['return_result']
        controller.close_admission()
        controller.write_message(request(2, 'job_get', {'operation_id': raw.operation_id}), write, lambda: None)
        controller.observe_response(rpc_reply(2, response(status=job['status'], operation_id=raw.operation_id,
                                                        context=job['payload']['context'], data=job, error=job['error'])))
        assert controller.receipt()['target_job_observation_binding']['operation_id'] == raw.operation_id
        assert controller.receipt()['native_q'] == proof.observation()['native_q'] == 'not_run'
        assert arm['process_stop_authorized'] is controller.receipt()['process_stop_authorized'] is False
        store.release(runtime=runtime)  # Explicit control path, never crash/recovery.
        final = asyncio.run(runtime._runner.wait(raw.operation_id, timeout_s=5))
        assert final['status'] == 'succeeded' and final['mutation']['phase'] == 'committed'
        replay = asyncio.run(registry.functions['dimension_set_value'](**cad_arguments))
        assert replay.operation_id == raw.operation_id and replay.status == 'succeeded'
        assert len(prepared.adapter.dimension_writes) == len(return_receipts) == len(barrier_receipts) == 1
        assert prepared.store._db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == original_count
        assert len(pipe) == 2
    finally:
        if store.barrier.state == 'waiting':
            store.release(runtime=runtime)  # Own pure worker only, not native cleanup.
        proof.uninstall()
        assert runtime.shutdown() is True
        seam.uninstall()
