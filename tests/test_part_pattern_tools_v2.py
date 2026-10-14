"""MCP schema validation and dispatch; no native acceptance claim."""

import asyncio

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.part_pattern_tools_v2 import register_part_pattern_tools
from test_dimension_tools_v2 import Runtime


TOOLS=('part_prepare_linear_hole_pattern','part_create_linear_hole_pattern')


@pytest.fixture
def setup():
    app,runtime=FastMCP('pattern-test'),Runtime()
    register_part_pattern_tools(app,runtime,lambda **kw:ResponseEnvelope(diagnostics=[],**kw),
                                lambda exc:pytest.fail(str(exc)))
    return app,runtime


def arguments(tool):
    value=dict(request_id='pattern',document_id='doc_explicit',configuration='Основная',
        base_object_id='feat_'+'a'*32,object_id='feat_'+'b'*32,seed_object_id='feat_'+'c'*32,
        direction_edge_id='obj_'+'d'*32,count=3,spacing_mm=10.,timeout_s=0.)
    if tool==TOOLS[1]:value['expected_revision']='rev_explicit'
    return value


@pytest.mark.parametrize('tool',TOOLS)
def test_complete_targets_defaults_and_revision_are_dispatched(setup,tool):
    app,runtime=setup
    args=arguments(tool)
    _,result=asyncio.run(app.call_tool(tool,args))
    payload={key:value for key,value in args.items() if key not in ('request_id','timeout_s')}
    payload['feature_name']='Линейный массив отверстий'
    mutate=tool==TOOLS[1]
    assert runtime.calls==[('mutate' if mutate else 'read','pattern',
        'part.create_linear_hole_pattern' if mutate else 'part.prepare_linear_hole_pattern',payload,0.)]
    assert result['status']=='succeeded'


@pytest.mark.parametrize('tool',TOOLS)
@pytest.mark.parametrize('key,value',[('count',True),('count','3'),('count',3.),('count',1),('count',65),
    ('spacing_mm',True),('spacing_mm','10'),('spacing_mm',float('nan')),('spacing_mm',0.),
    ('timeout_s',True),('timeout_s',121.)])
def test_invalid_count_length_or_wait_never_dispatches(setup,tool,key,value):
    app,runtime=setup
    args={**arguments(tool),key:value}
    with pytest.raises(ToolError):asyncio.run(app.call_tool(tool,args))
    assert runtime.calls==[]


@pytest.mark.parametrize('key',['document_id','configuration','base_object_id','object_id','seed_object_id',
                                'direction_edge_id','count','spacing_mm','expected_revision'])
def test_creation_never_infers_omitted_target_or_parameter(setup,key):
    app,runtime=setup
    args=arguments(TOOLS[1]);del args[key]
    with pytest.raises(ToolError):asyncio.run(app.call_tool(TOOLS[1],args))
    assert runtime.calls==[]
