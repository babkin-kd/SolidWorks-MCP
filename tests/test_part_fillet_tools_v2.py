"""MCP facade validation and explicit dispatch; no native acceptance claim."""

import asyncio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.part_fillet_tools_v2 import register_part_fillet_tools
from test_dimension_tools_v2 import Runtime


TOOLS=('part_prepare_edge_fillet','part_create_edge_fillet')


@pytest.fixture
def setup():
    app,runtime=FastMCP('fillet-test'),Runtime()
    register_part_fillet_tools(app,runtime,lambda **kw:ResponseEnvelope(diagnostics=[],**kw),lambda exc:pytest.fail(str(exc)))
    return app,runtime


def arguments(tool):
    args=dict(request_id='fillet',document_id='doc_explicit',configuration='Основная',object_id='feat_'+'a'*32,
        edge_id='obj_'+'b'*32,radius_mm=2.,timeout_s=0.)
    if tool==TOOLS[1]:args['expected_revision']='rev_explicit'
    return args


@pytest.mark.parametrize('tool',TOOLS)
def test_target_revision_and_russian_default_dispatched(setup,tool):
    app,runtime=setup;args=arguments(tool)
    _,result=asyncio.run(app.call_tool(tool,args))
    payload={k:v for k,v in args.items() if k not in ('request_id','timeout_s')};payload['feature_name']='Скругление ребра'
    mutate=tool==TOOLS[1]
    assert runtime.calls==[('mutate' if mutate else 'read','fillet',
        'part.create_edge_fillet' if mutate else 'part.prepare_edge_fillet',payload,0.)]
    assert result['status']=='succeeded'


@pytest.mark.parametrize('tool',TOOLS)
@pytest.mark.parametrize('key,value',[('radius_mm',True),('radius_mm','2'),('radius_mm',0.),
    ('radius_mm',float('nan')),('timeout_s',True),('timeout_s',121.)])
def test_invalid_length_or_wait_never_dispatches(setup,tool,key,value):
    app,runtime=setup
    with pytest.raises(ToolError):asyncio.run(app.call_tool(tool,{**arguments(tool),key:value}))
    assert runtime.calls==[]


@pytest.mark.parametrize('key',['document_id','configuration','object_id','edge_id','radius_mm','expected_revision'])
def test_creation_requires_every_explicit_target_parameter_and_revision(setup,key):
    app,runtime=setup;args=arguments(TOOLS[1]);del args[key]
    with pytest.raises(ToolError):asyncio.run(app.call_tool(TOOLS[1],args))
    assert runtime.calls==[]
