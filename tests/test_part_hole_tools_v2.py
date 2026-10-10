"""Real MCP facade validation over an artificial runtime, no CAD calls."""

import asyncio

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.part_hole_tools_v2 import register_part_hole_tools
from test_dimension_tools_v2 import Runtime


@pytest.fixture
def setup():
    app,runtime=FastMCP('hole-test'),Runtime()
    register_part_hole_tools(app,runtime,lambda **kw:ResponseEnvelope(diagnostics=[],**kw),
        lambda exc:pytest.fail(str(exc)))
    return app,runtime


def arguments(tool):
    result={'request_id':'hole-request','document_id':'doc_explicit','configuration':'Основная',
        'object_id':'feat_'+'a'*32,'plane_object_id':'feat_'+'b'*32,
        'centre_x_mm':10.,'centre_y_mm':10.,'diameter_mm':6.,'timeout_s':0.}
    if tool=='part_create_through_hole':result['expected_revision']='rev_explicit'
    return result


@pytest.mark.parametrize('tool,method,operation',[
    ('part_prepare_through_hole','read','part.prepare_through_hole'),
    ('part_create_through_hole','mutate','part.create_through_hole')])
def test_explicit_engineering_parameters_and_russian_names_are_dispatched(setup,tool,method,operation):
    app,runtime=setup
    _,result=asyncio.run(app.call_tool(tool,arguments(tool)))
    payload={key:value for key,value in arguments(tool).items() if key not in ('request_id','timeout_s')}
    payload.update(sketch_name='Эскиз отверстия',feature_name='Сквозное отверстие')
    assert runtime.calls==[(method,'hole-request',operation,payload,0.)]
    assert result['status']=='succeeded'


@pytest.mark.parametrize('tool',['part_prepare_through_hole','part_create_through_hole'])
@pytest.mark.parametrize('key,value',[
    ('centre_x_mm',True),('centre_y_mm','10'),('diameter_mm',False),
    ('centre_x_mm',float('nan')),('diameter_mm',float('inf')),('centre_y_mm',.0001),
    ('diameter_mm',10000001.),('timeout_s',121.),('timeout_s',True)])
def test_invalid_lengths_or_wait_never_dispatch(setup,tool,key,value):
    app,runtime=setup
    payload=arguments(tool)
    payload[key]=value
    with pytest.raises(ToolError):asyncio.run(app.call_tool(tool,payload))
    assert runtime.calls==[]


@pytest.mark.parametrize('key',['document_id','configuration','object_id','plane_object_id','expected_revision'])
def test_creation_never_infers_an_omitted_target_or_revision(setup,key):
    app,runtime=setup
    payload=arguments('part_create_through_hole')
    del payload[key]
    with pytest.raises(ToolError):asyncio.run(app.call_tool('part_create_through_hole',payload))
    assert runtime.calls==[]


@pytest.mark.parametrize('tool,method,operation',[
    ('part_prepare_hole_dimension_change','read','part.prepare_hole_dimension_change'),
    ('part_set_hole_dimension','mutate','part.set_hole_dimension')])
def test_hole_edit_explicit_targets_are_dispatched(setup,tool,method,operation):
    app,runtime=setup
    args={'request_id':'edit','document_id':'doc_explicit','configuration':'Основная',
        'base_object_id':'feat_'+'a'*32,'object_id':'feat_'+'b'*32,
        'dimension_id':'dim_'+'c'*32,'value_mm':8.,'timeout_s':0.}
    if method=='mutate':args['expected_revision']='rev_explicit'
    _,result=asyncio.run(app.call_tool(tool,args))
    assert runtime.calls==[(method,'edit',operation,{key:value for key,value in args.items()
        if key not in ('request_id','timeout_s')},0.)]
    assert result['status']=='succeeded'


@pytest.mark.parametrize('tool',['part_prepare_hole_dimension_change','part_set_hole_dimension'])
@pytest.mark.parametrize('value',[True,'8',float('nan'),float('inf'),.0001,10000001.])
def test_hole_edit_invalid_length_never_dispatches(setup,tool,value):
    app,runtime=setup
    args={'request_id':'edit','document_id':'doc','configuration':'Основная',
        'base_object_id':'feat_base','object_id':'feat_circle','dimension_id':'dim_circle',
        'value_mm':value,'expected_revision':'rev_explicit'}
    with pytest.raises(ToolError):asyncio.run(app.call_tool(tool,args))
    assert runtime.calls==[]
