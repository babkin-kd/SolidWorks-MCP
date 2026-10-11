"""Strict bool/target/revision MCP routing, without CAD."""

import asyncio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.sheet_flange_flat_tools_v2 import register_sheet_flange_flat_tools
from test_dimension_tools_v2 import Runtime

TOOLS=('sheet_prepare_flange_flat_state','sheet_set_flange_flat_state')


@pytest.fixture
def setup():
    app,runtime=FastMCP('sheet-state-test'),Runtime()
    register_sheet_flange_flat_tools(app,runtime,lambda **kw:ResponseEnvelope(diagnostics=[],**kw),lambda exc:pytest.fail(str(exc)))
    return app,runtime


def arguments(tool):
    args=dict(request_id='sheet-state',document_id='doc_explicit',configuration='Основная',base_object_id='feat_'+'a'*32,
        flange_object_id='feat_'+'b'*32,flattened=True,timeout_s=0.)
    if tool==TOOLS[1]:args['expected_revision']='rev_explicit'
    return args


@pytest.mark.parametrize('tool',TOOLS)
@pytest.mark.parametrize('flattened',[False,True])
def test_exact_existing_base_state_and_revision_dispatch_without_k_override(setup,tool,flattened):
    app,runtime=setup;args={**arguments(tool),'flattened':flattened}
    _,result=asyncio.run(app.call_tool(tool,args))
    payload={k:v for k,v in args.items() if k not in ('request_id','timeout_s')}
    assert runtime.calls==[('mutate' if tool==TOOLS[1] else 'read','sheet-state',
        'sheet.set_flange_flat_state' if tool==TOOLS[1] else 'sheet.prepare_flange_flat_state',payload,0.)]
    assert result['status']=='succeeded'


@pytest.mark.parametrize('tool',TOOLS)
@pytest.mark.parametrize('key,value',[('flattened',1),('flattened',0),('flattened','true'),('flattened','false'),
    ('flattened',None),('timeout_s',True),('timeout_s',float('nan')),('timeout_s',-1.)])
def test_invalid_bool_or_wait_never_dispatches(setup,tool,key,value):
    app,runtime=setup
    with pytest.raises(ToolError):asyncio.run(app.call_tool(tool,{**arguments(tool),key:value}))
    assert runtime.calls==[]


@pytest.mark.parametrize('key',['document_id','configuration','base_object_id','flange_object_id','flattened','expected_revision'])
def test_mutation_has_no_implicit_target_or_state(setup,key):
    app,runtime=setup;args=arguments(TOOLS[1]);del args[key]
    with pytest.raises(ToolError):asyncio.run(app.call_tool(TOOLS[1],args))
    assert runtime.calls==[]
