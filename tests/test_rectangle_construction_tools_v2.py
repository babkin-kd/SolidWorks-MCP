"""Actual MCP validation and runtime routing, artificial domain evidence only."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace as NS

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from solidworks_mcp.jobs import JobError, JobStore
from solidworks_mcp.runtime_v2 import Runtime, READ_OPERATIONS, MUTATING_OPERATIONS
from solidworks_mcp.server_v2 import create_app
from solidworks_mcp.rectangle_construction_catalog import RectangleConstructionCatalog
from test_rectangle_construction_execution import execution, sketch_proof, extrusion_proof, empty_adapter


NAMES=('sketch_prepare_rectangle','sketch_create_rectangle',
       'part_prepare_rectangle_extrusion','part_extrude_rectangle')


@pytest.fixture
def public(execution, monkeypatch):
    x=execution
    threads=[]
    documents=x.catalog.documents
    documents.close=lambda:None
    original_prepare=x.catalog.prepare_sketch if x.kind=='sketch' else x.catalog.prepare_extrusion
    class Factory:
        def __new__(cls, catalog, store, epoch):
            assert catalog is documents and store is x.store
            threads.append(threading.get_ident())
            x.catalog.connection_epoch=epoch
            return x.catalog
    monkeypatch.setattr('solidworks_mcp.runtime_v2.RectangleConstructionCatalog',Factory)
    original_create=x.catalog.create_sketch if x.kind=='sketch' else x.catalog.create_extrusion
    def create(operation_id,**arguments):
        x.adapter.operation_id=operation_id
        return original_create(operation_id,**arguments)
    if x.kind=='sketch':x.catalog.create_sketch=create
    else:x.catalog.create_extrusion=create
    from test_runtime_v2 import Worker
    runtime=Runtime(x.store,worker_factory=Worker,catalog_factory=lambda:documents)
    state=NS(x=x,runtime=runtime,app=create_app(x.store,runtime),threads=threads)
    yield state
    assert runtime.shutdown()


def arguments(state, *, write=False):
    result=dict(document_id='target',configuration='Основная',**vars(state.x.definition))
    if write:result['expected_revision']=state.x.catalog.prepare_sketch()['revision']
    return result


def call(state,name,**args):
    return asyncio.run(state.app.call_tool(name,args))[1]


def tools(state):
    return asyncio.run(state.app.list_tools())


def pair(state):
    return NAMES[:2] if state.x.kind=='sketch' else NAMES[2:]


def test_discovery_exposes_only_explicit_implemented_contracts_without_cad(public):
    by_name={tool.name:tool for tool in tools(public)}
    assert all(name in by_name for name in NAMES)
    for name in NAMES:
        schema=by_name[name].inputSchema
        assert {'request_id','document_id','configuration'}<=set(schema['required'])
        assert by_name[name].outputSchema['type']=='object'
        assert schema['properties']['timeout_s']['default']==10.
    info=call(public,'system_get_info')
    assert {'sketch.create_rectangle','part.extrude_rectangle'}<=set(info['data']['implemented_mutations'])
    assert not public.threads and public.runtime._rectangle_construction is None
    assert public.x.store.list()['items']==[]


def test_public_prepare_write_replay_and_conflict_use_one_runtime_domain(public):
    prepare,create=pair(public)
    p=call(public,prepare,request_id='prepare',**arguments(public))
    assert p['status']=='succeeded',p
    args={**arguments(public), 'expected_revision':p['data']['revision']}
    result=call(public,create,request_id='create',**args)
    assert result['status']=='succeeded',result
    assert result['data']['value']['object_id'].startswith('feat_')
    assert call(public,create,request_id='create',**args)==result
    conflict=call(public,create,request_id='create',**{**args,'expected_revision':'rev_other'})
    assert conflict['status']=='failed' and conflict['error']['code']=='request_conflict'
    assert public.x.adapter.dispatches==1 and len(public.threads)==1
    assert public.threads[0]!=threading.get_ident()
    assert public.runtime._rectangle_construction.documents is public.runtime._catalog
    assert public.x.store.get(result['operation_id'])['mutation']['phase']=='committed'


def test_unknown_replay_and_new_request_preserve_application_hold(public):
    _,create=pair(public)
    public.x.adapter.fault='lost_ack'
    args=arguments(public,write=True)
    first=call(public,create,request_id='unknown',**args)
    assert first['status']=='unknown',first
    assert call(public,create,request_id='unknown',**args)==first
    held=call(public,create,request_id='held',**args)
    assert held['status']=='failed' and held['error']['code']=='document_mutation_blocked'
    assert public.x.adapter.dispatches==1


@pytest.mark.parametrize('invalid',[True,'10',-1.,121.,float('inf'),float('nan')])
def test_invalid_timeout_never_reaches_runtime(public,invalid):
    prepare,_=pair(public)
    with pytest.raises(ToolError):
        call(public,prepare,request_id='invalid',timeout_s=invalid,**arguments(public))
    assert not public.threads and public.x.store.list()['items']==[]


@pytest.mark.parametrize('invalid',[True,'10',0.,-1.,float('inf'),float('nan')])
def test_invalid_length_never_reaches_runtime(public,invalid):
    prepare,_=pair(public)
    args=arguments(public)
    args['width_mm' if public.x.kind=='sketch' else 'depth_mm']=invalid
    with pytest.raises(ToolError):call(public,prepare,request_id='invalid',**args)
    assert not public.threads and public.x.store.list()['items']==[]


def test_read_and_write_routes_cannot_be_swapped(public):
    for operation in ('sketch.create_rectangle','part.extrude_rectangle'):
        assert operation in MUTATING_OPERATIONS and operation not in READ_OPERATIONS
        with pytest.raises(JobError):asyncio.run(public.runtime.read('wrong',operation,{}))
    for operation in ('sketch.prepare_rectangle','part.prepare_rectangle_extrusion'):
        assert operation in READ_OPERATIONS and operation not in MUTATING_OPERATIONS
        with pytest.raises(JobError):asyncio.run(public.runtime.mutate('wrong',operation,{}))
    assert not public.threads
