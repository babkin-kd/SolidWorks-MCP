"""Candidate facade against a fake runtime, not installed acceptance."""

import asyncio

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.part_revolve_tools_v2 import register_part_revolve_tools
from test_dimension_tools_v2 import Runtime


@pytest.fixture
def setup():
    app,runtime = FastMCP('revolve-test'),Runtime()
    register_part_revolve_tools(app,runtime,lambda **kw:ResponseEnvelope(diagnostics=[],**kw),
                               lambda exc:pytest.fail(str(exc)))
    return app,runtime


def arguments(tool):
    values = dict(request_id='revolve-request',document_id='doc_explicit',configuration='Основная',
                  plane_object_id='feat_'+'a'*32,radius_mm=10.,height_mm=30.,axis='profile_y',timeout_s=0.)
    if tool == 'part_create_base_revolve': values['expected_revision'] = 'rev_explicit'
    return values


@pytest.mark.parametrize('tool,method,operation',[
    ('part_prepare_base_revolve','read','part.prepare_base_revolve'),
    ('part_create_base_revolve','mutate','part.create_base_revolve')])
def test_exact_plane_axis_revision_and_russian_names_dispatched(setup,tool,method,operation):
    app,runtime = setup
    _,result = asyncio.run(app.call_tool(tool,arguments(tool)))
    expected = {key:value for key,value in arguments(tool).items() if key not in ('request_id','timeout_s')}
    expected.update(sketch_name='Эскиз вращения',feature_name='Вращение основания',body_name='Тело вращения')
    assert runtime.calls == [(method,'revolve-request',operation,expected,0.)]
    assert result['status'] == 'succeeded'


@pytest.mark.parametrize('tool',['part_prepare_base_revolve','part_create_base_revolve'])
@pytest.mark.parametrize('key,value',[('axis','first'),('radius_mm',True),('height_mm','30'),
    ('radius_mm',float('nan')),('height_mm',float('inf')),('radius_mm',0.),('height_mm',10000001.),('timeout_s',121.)])
def test_invalid_native_parameters_never_dispatch(setup,tool,key,value):
    app,runtime = setup
    values = arguments(tool)
    values[key] = value
    with pytest.raises(ToolError): asyncio.run(app.call_tool(tool,values))
    assert runtime.calls == []
