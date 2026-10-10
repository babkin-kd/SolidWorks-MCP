"""Strict facade validation and routing without CAD."""

import asyncio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.sheet_profile_tools_v2 import register_sheet_profile_tools
from test_dimension_tools_v2 import Runtime

TOOLS=('sheet_prepare_l_profile','sheet_create_l_profile')


@pytest.fixture
def setup():
    app,runtime=FastMCP('sheet-test'),Runtime()
    register_sheet_profile_tools(app,runtime,lambda **kw:ResponseEnvelope(diagnostics=[],**kw),lambda exc:pytest.fail(str(exc)))
    return app,runtime


def arguments(tool):
    args=dict(request_id='sheet',document_id='doc_explicit',configuration='Основная',plane_object_id='feat_'+'a'*32,
        leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42,timeout_s=0.)
    if tool==TOOLS[1]:args['expected_revision']='rev_explicit'
    return args


@pytest.mark.parametrize('tool',TOOLS)
def test_exact_target_required_k_revision_and_names_dispatched(setup,tool):
    app,runtime=setup;args=arguments(tool)
    _,result=asyncio.run(app.call_tool(tool,args))
    payload={k:v for k,v in args.items() if k not in ('request_id','timeout_s')}
    payload.update(sketch_name='Эскиз листового профиля',feature_name='Листовой уголок',body_name='Тело листового уголка')
    assert runtime.calls==[('mutate' if tool==TOOLS[1] else 'read','sheet',
        'sheet.create_l_profile' if tool==TOOLS[1] else 'sheet.prepare_l_profile',payload,0.)]
    assert result['status']=='succeeded'


@pytest.mark.parametrize('tool',TOOLS)
@pytest.mark.parametrize('key,value',[('leg_x_mm',True),('thickness_mm',0.),('bend_radius_mm',float('nan')),
    ('length_mm','30'),('k_factor',True),('k_factor',-.01),('k_factor',1.01),('k_factor',float('nan')),('timeout_s',True)])
def test_invalid_parameters_never_dispatch(setup,tool,key,value):
    app,runtime=setup
    with pytest.raises(ToolError):asyncio.run(app.call_tool(tool,{**arguments(tool),key:value}))
    assert runtime.calls==[]


@pytest.mark.parametrize('key',['document_id','configuration','plane_object_id','leg_x_mm','leg_y_mm','length_mm',
    'thickness_mm','bend_radius_mm','k_factor','expected_revision'])
def test_creation_has_no_implicit_target_dimension_or_k_default(setup,key):
    app,runtime=setup;args=arguments(TOOLS[1]);del args[key]
    with pytest.raises(ToolError):asyncio.run(app.call_tool(TOOLS[1],args))
    assert runtime.calls==[]
