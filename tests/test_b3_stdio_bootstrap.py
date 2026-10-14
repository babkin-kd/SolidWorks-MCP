"""Real Runtime/SQLite registrations on an artificial CAD adapter, never CAD."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobStore,_json
from test_geometry_v2 import GeometryAdapter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verifier_b3_stdio_bootstrap import RegistrationTraceRuntime,main


class Worker:
    def __init__(self):self.pool=ThreadPoolExecutor(max_workers=1)
    def submit(self,fn):return self.pool.submit(fn)
    def shutdown(self,timeout_s=5):self.pool.shutdown(wait=True);return True


@pytest.fixture
def world(tmp_path):
    trace=tmp_path/'trace';trace.mkdir()
    adapter=GeometryAdapter();adapter.body(faces=2)
    store=JobStore(tmp_path/'jobs.sqlite')
    runtime=RegistrationTraceRuntime(store,trace_dir=trace,worker_factory=Worker,
        catalog_factory=lambda:DocumentCatalog(adapter))
    yield runtime,trace
    runtime.shutdown()


def test_actual_ids_and_pid_tables_exported_after_tool_with_exact_result_and_no_replay_dispatch(world):
    runtime,trace=world
    async def run():
        listed=await runtime.read('list','document.list',{})
        target=listed['result']['documents'][0]
        args=dict(document_id=target['document_id'],configuration='Основная',
                  expected_observation_revision=target['observation_revision'])
        geometry=await runtime.read('bodies','geometry.list',args)
        assert geometry['status']=='succeeded'
        records=[json.loads(path.read_text(encoding='utf8')) for path in sorted(trace.glob('*.json'))]
        assert len(records)==2
        current=records[-1]
        assert current['operation']=='geometry.list' and current['arguments']==args
        assert current['operation_id']==geometry['operation_id'] and current['request_id']=='bodies'
        assert current['journal_status_at_capture']=='running'
        assert current['journal_payload_sha256']==hashlib.sha256(_json(geometry['payload']).encode('utf8')).hexdigest()
        assert current['result_sha256']==hashlib.sha256(_json(geometry['result']).encode('utf8')).hexdigest()
        refs=current['registered_references'][0]['rows']
        assert refs and refs[0]['object_id']==geometry['result']['items'][0]['object_id']
        assert current['accepted'] is current['current_membership_verified'] is False
        replay=await runtime.read('bodies','geometry.list',args)
        assert replay==geometry and len(list(trace.glob('*.json')))==2
        assert runtime.trace_error is None
    asyncio.run(run())


def test_trace_write_failure_preserves_actual_successful_job_and_does_not_retry(world):
    runtime,trace=world
    (trace/'0001.json').write_text('existing private evidence',encoding='utf8')
    async def run():
        job=await runtime.read('list','document.list',{})
        assert job['status']=='succeeded' and runtime.store.get(job['operation_id'])==job
        assert runtime.trace_error['type']=='FileExistsError'
        assert await runtime.read('list','document.list',{})==job
    asyncio.run(run())
    assert (trace/'0001.json').read_text(encoding='utf8')=='existing private evidence'
    assert runtime.trace_sequence==0


def test_domain_refusal_preserves_code_and_catalog_with_exception_receipt(world):
    runtime,trace=world
    async def run():
        await runtime.read('list','document.list',{})
        job=await runtime.read('missing','document.get',dict(document_id='missing',configuration='Основная'))
        assert job['status']=='failed' and job['error']['code']=='document_not_open'
        row=json.loads((trace/'0002.json').read_text(encoding='utf8'))
        assert row['status']=='exception_returned' and row['error']['code']=='document_not_open'
        assert row['operation_id']==job['operation_id'] and row['request_id']=='missing'
        assert row['registered_references']==[] and row['result_sha256'] is None
        assert runtime._catalog is not None
    asyncio.run(run())


def test_optional_window_mode_associates_actual_ids_by_canonical_not_names(world):
    runtime,trace=world
    runtime.expected_window_hwnds=(101,102)
    def catalog_factory():
        catalog=runtime._original_catalog_factory()
        catalog.adapter.native_close_windows=lambda:[(model,dict(hwnd=101+i,title='Одинаковое имя'))
            for i,model in enumerate(catalog.adapter.models)]
        return catalog
    runtime._original_catalog_factory=runtime._catalog_factory
    runtime._catalog_factory=catalog_factory
    job=asyncio.run(runtime.read('list','document.list',{}))
    row=json.loads((trace/'0001.json').read_text(encoding='utf8'))
    assert row['document_window_bindings']==[dict(document_id=item['document_id'],hwnd=101+i)
        for i,item in enumerate(job['result']['documents'])]
    assert row['whole_session_native_envelope_verified'] is row['original_birth_ownership_verified'] is False


@pytest.mark.parametrize('fault',['foreign_model','extra_window','window_swap','outside_hwnd'])
def test_window_mismatch_invalidates_trace_and_preserves_original_job(world,fault):
    runtime,trace=world;runtime.expected_window_hwnds=(101,102)
    original_factory=runtime._catalog_factory
    def factory():
        catalog=original_factory();adapter=catalog.adapter;calls=[]
        def windows():
            calls.append(True)
            pairs=[(model,dict(hwnd=101+i,title='ignored')) for i,model in enumerate(adapter.models)]
            if fault=='foreign_model':pairs[0]=(object(),pairs[0][1])
            elif fault=='extra_window':pairs.append(pairs[0])
            elif fault=='outside_hwnd':pairs[0][1]['hwnd']=999
            elif len(calls)==2:
                pairs=[(pairs[0][0],pairs[1][1]),(pairs[1][0],pairs[0][1])]
            return pairs
        adapter.native_close_windows=windows
        return catalog
    runtime._catalog_factory=factory
    job=asyncio.run(runtime.read('list','document.list',{}))
    assert job['status']=='succeeded' and runtime.trace_error is not None
    assert list(trace.glob('*.json'))==[]


def test_unconfirmed_shutdown_cannot_create_terminal_trace(world):
    runtime,trace=world
    class DeferredWorker(Worker):
        stopped=False
        def shutdown(self,timeout_s=5):
            if not self.stopped:self.stopped=True;return False
            return super().shutdown(timeout_s=timeout_s)
    runtime._worker_factory=DeferredWorker
    asyncio.run(runtime.read('list','document.list',{}))
    assert runtime.shutdown() is False and not (trace/'terminal.json').exists()
    assert runtime.shutdown() is True
    terminal=json.loads((trace/'terminal.json').read_text(encoding='utf8'))
    assert terminal['worker_shutdown_confirmed'] is True and terminal['records']==1
    assert terminal['accepted'] is terminal['cleanup_authorized'] is False


def test_ambiguous_running_job_refuses_binding_instead_of_guessing_by_payload(world):
    runtime,trace=world
    foreign,_=runtime.store.create('foreign-running','document.list',{}, {})
    assert runtime.store.start(foreign['operation_id'])
    job=asyncio.run(runtime.read('list','document.list',{}))
    assert job['status']=='succeeded' and runtime.trace_error['type']=='ValueError'
    assert runtime.store.get(foreign['operation_id'])['status']=='running'
    assert list(trace.glob('*.json'))==[]


@pytest.mark.parametrize('budget',['records','bytes'])
def test_exhausted_private_trace_budget_never_changes_public_job(world,budget):
    runtime,trace=world
    if budget=='records':runtime.trace_sequence=256
    else:runtime.trace_bytes=16*1024*1024
    job=asyncio.run(runtime.read('list','document.list',{}))
    assert job['status']=='succeeded' and runtime.trace_error['type']=='ValueError'
    assert list(trace.glob('*.json'))==[]


def test_bootstrap_rejects_external_trace_before_wheel_import_or_server():
    with tempfile.TemporaryDirectory(prefix='b3-external-trace-') as temporary:
        outside=Path(temporary)
        with pytest.raises(ValueError,match='Fresh private work trace'):
            main(['--trace-dir',str(outside/'trace'),'--wheel','missing.whl',
                  '--expected-version','invalid','--expected-git-sha','bad','--state-dir',str(outside/'server')])
        assert not (outside/'trace').exists()
