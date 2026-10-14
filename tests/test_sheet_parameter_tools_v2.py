"""Prototype strict parameter dispatch, not registered production capabilities."""

import asyncio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.sheet_parameter_tools_v2 import register_sheet_parameter_tools
from test_dimension_tools_v2 import Runtime


TOOLS=('sheet_prepare_parameters','sheet_set_parameters')


@pytest.fixture
def setup():
    app,runtime=FastMCP('sheet-parameter-prototype'),Runtime()
    register_sheet_parameter_tools(app,runtime,lambda **kw:ResponseEnvelope(diagnostics=[],**kw),lambda exc:pytest.fail(str(exc)))
    return app,runtime


def arguments(tool):
    values=dict(request_id='sheet-parameters',document_id='doc_explicit',configuration='Основная',base_object_id='feat_'+'a'*32,
        thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38,timeout_s=0.)
    if tool==TOOLS[1]:values['expected_revision']='rev_explicit'
    return values


@pytest.mark.parametrize('tool',TOOLS)
def test_explicit_parameter_set_routes_as_one_read_or_mutation(setup,tool):
    app,runtime=setup;args=arguments(tool);_,result=asyncio.run(app.call_tool(tool,args))
    assert result['status']=='succeeded'
    payload={key:value for key,value in args.items() if key not in ('request_id','timeout_s')}
    assert runtime.calls==[('mutate' if tool==TOOLS[1] else 'read','sheet-parameters',
        'sheet.set_parameters' if tool==TOOLS[1] else 'sheet.prepare_parameters',payload,0.)]


@pytest.mark.parametrize('tool',TOOLS)
@pytest.mark.parametrize('key,value',[('thickness_mm',True),('thickness_mm',0.),('thickness_mm',float('nan')),
    ('thickness_mm',1e8),('bend_radius_mm','3.5'),('bend_radius_mm',-1.),('k_factor',False),
    ('k_factor',float('inf')),('k_factor',1.01),('k_factor','0.38'),('timeout_s',True),('timeout_s',-1.)])
def test_invalid_parameters_or_wait_never_dispatch(setup,tool,key,value):
    app,runtime=setup
    with pytest.raises(ToolError):asyncio.run(app.call_tool(tool,{**arguments(tool),key:value}))
    assert not runtime.calls


@pytest.mark.parametrize('key',['document_id','configuration','base_object_id','thickness_mm','bend_radius_mm','k_factor','expected_revision'])
def test_mutation_has_no_implicit_target_or_parameter_default(setup,key):
    app,runtime=setup;args=arguments(TOOLS[1]);del args[key]
    with pytest.raises(ToolError):asyncio.run(app.call_tool(TOOLS[1],args))
    assert not runtime.calls
