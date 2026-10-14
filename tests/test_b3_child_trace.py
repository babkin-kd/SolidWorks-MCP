"""Real Runtime/SQL/window-mode child records on an artificial CAD adapter."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS

import pytest
from test_b3_stdio_bootstrap import Worker,RegistrationTraceRuntime
from test_geometry_v2 import GeometryAdapter
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobStore
from solidworks_mcp.server_v2 import create_app

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verifier_b3_child_trace import ChildTrace
from verifier_b3_reader import B3Reader


class Client:
    """Actual public facade with artificial supervisor, never native proof."""
    def __init__(self,runtime):
        self.app=create_app(runtime.store,runtime);self.runtime=runtime;self.retained=[];self.calls=[]
    async def call_tool(self,tool,args):
        self.calls.append(tool)
        envelope=await self.app._tool_manager.get_tool(tool).fn(**args)
        return NS(isError=False,structuredContent=envelope.model_dump(mode='json'))
    async def observe_once(self):
        safe=not self.retained and all(job['status'] in ('succeeded','failed')
            for job in self.runtime.store.list()['items'])
        return NS(child_can_close=safe,fixture_can_cleanup=safe)
    def retain(self,reason):self.retained.append(reason)


@pytest.fixture
def world():
    private=Path(__file__).resolve().parents[1]/'work';private.mkdir(exist_ok=True)
    state=Path(tempfile.mkdtemp(prefix='b3-child-trace-pure-',dir=private))
    trace=state/'trace';trace.mkdir()
    adapter=GeometryAdapter();adapter.body(faces=2)
    adapter.native_close_windows=lambda:[(model,dict(hwnd=101+i,title='ignored')) for i,model in enumerate(adapter.models)]
    runtime=RegistrationTraceRuntime(JobStore(state/'jobs.sqlite'),trace_dir=trace,
        expected_window_hwnds=(101,102),worker_factory=Worker,catalog_factory=lambda:DocumentCatalog(adapter))
    job=asyncio.run(runtime.read('list','document.list',{}))
    yield runtime,job,trace
    runtime.shutdown()


def test_actual_terminal_job_binds_opaque_ids_and_window_records_without_native_claim(world):
    runtime,job,path=world;bridge=ChildTrace(path)
    proof=bridge.bind(job)
    assert proof['trace']['document_window_bindings'][0]['document_id']==job['result']['documents'][0]['document_id']
    assert proof['accepted'] is proof['current_membership_verified'] is False
    replay=asyncio.run(runtime.read('list','document.list',{}))
    assert bridge.bind(replay)==proof and bridge.sequence==1


@pytest.mark.parametrize('fault',['job_id','request','payload','result','epoch','window','claims','replay_bytes'])
def test_mismatched_or_rewritten_child_evidence_refuses(world,fault):
    runtime,job,path=world;bridge=ChildTrace(path);file=path/'0001.json'
    if fault=='replay_bytes':bridge.bind(job)
    row=json.loads(file.read_text(encoding='utf8'))
    if fault=='job_id':row['operation_id']='foreign'
    elif fault=='request':row['request_id']='foreign'
    elif fault=='payload':row['journal_payload_sha256']='0'*64
    elif fault=='result':row['result_sha256']='0'*64
    elif fault=='epoch':row['connection_epoch']=None
    elif fault=='window':row['document_window_bindings'][0]['hwnd']=True
    elif fault=='claims':row['current_membership_verified']=True
    else:row['changed_private_bytes']=True
    file.write_text(json.dumps(row),encoding='utf8')
    with pytest.raises(ValueError):bridge.bind(job)


def test_known_domain_refusal_binds_to_exact_error_without_adopting_namespace(world):
    runtime,job,path=world;bridge=ChildTrace(path);bridge.bind(job)
    refused=asyncio.run(runtime.read('missing','document.get',dict(document_id='missing',configuration='Основная')))
    proof=bridge.bind(refused)
    assert proof['trace']['error']['code']=='document_not_open'
    assert proof['trace']['registered_references']==[]


def test_connection_replacement_refuses_even_if_second_job_is_successful(world):
    runtime,job,path=world;bridge=ChildTrace(path);bridge.bind(job)
    next_job=asyncio.run(runtime.read('second','document.list',{}))
    file=path/'0002.json';row=json.loads(file.read_text(encoding='utf8'))
    row['connection_epoch']='connection_'+'a'*32
    file.write_text(json.dumps(row),encoding='utf8')
    with pytest.raises(ValueError,match='epoch'):bridge.bind(next_job)


def test_reader_connects_actual_tool_runtime_sql_and_child_namespace_with_replay(world):
    runtime,job,path=world;client=Client(runtime);receipts=[]
    reader=B3Reader(client,runtime.store.path,assert_before_dispatch=lambda:None,
        persist=lambda rows:receipts.append(rows),child_trace=ChildTrace(path))
    async def run():
        listed=await reader.read('document_list',dict(request_id='list'))
        observed=listed['result']['documents'][0]
        args=dict(request_id='body',document_id=observed['document_id'],configuration='Основная',
            expected_observation_revision=observed['observation_revision'])
        body=await reader.read('body_list',args)
        assert await reader.read('body_list',args)==body
        assert reader.child_trace.sequence==2
        exported=receipts[-1][-1]['child_trace']['trace']['registered_references'][0]['rows']
        assert exported[0]['object_id']==body['result']['items'][0]['object_id']
        assert client.retained==[] and len(list(path.glob('*.json')))==2
    asyncio.run(run())


def test_reader_retains_after_rewritten_trace_and_blocks_further_dispatch(world):
    runtime,job,path=world;client=Client(runtime)
    (path/'0001.json').write_text('{}',encoding='utf8')
    reader=B3Reader(client,runtime.store.path,assert_before_dispatch=lambda:None,
        persist=lambda rows:None,child_trace=ChildTrace(path))
    with pytest.raises(ValueError):asyncio.run(reader.read('document_list',dict(request_id='list')))
    calls=client.calls[:]
    with pytest.raises(RuntimeError):asyncio.run(reader.read('document_list',dict(request_id='new')))
    assert client.retained and client.calls==calls
    assert runtime.store.get(job['operation_id'])['status']=='succeeded'
