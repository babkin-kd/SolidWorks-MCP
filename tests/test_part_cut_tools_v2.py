"""MCP facade contract and strict validation; artificial runtime, no CAD."""

import asyncio

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.part_cut_tools_v2 import register_part_cut_tools
from test_dimension_tools_v2 import Runtime


@pytest.fixture
def setup():
    app, runtime = FastMCP('cut-test'), Runtime()
    register_part_cut_tools(app, runtime, lambda **kw:ResponseEnvelope(diagnostics=[],**kw),
                            lambda exc:pytest.fail(str(exc)))
    return app, runtime


def arguments(tool):
    result = dict(request_id='cut-request',document_id='doc_explicit',configuration='Основная',
        object_id='feat_'+'a'*32,plane_object_id='feat_'+'b'*32,width_mm=10.,height_mm=5.,timeout_s=0.)
    if tool == 'part_create_corner_cut': result['expected_revision'] = 'rev_explicit'
    return result


@pytest.mark.parametrize('tool,method,operation',[
    ('part_prepare_corner_cut','read','part.prepare_corner_cut'),
    ('part_create_corner_cut','mutate','part.create_corner_cut')])
def test_exact_target_parameters_and_russian_defaults_dispatched(setup, tool, method, operation):
    app, runtime = setup
    _, result = asyncio.run(app.call_tool(tool, arguments(tool)))
    payload = {k:v for k,v in arguments(tool).items() if k not in ('request_id','timeout_s')}
    payload.update(sketch_name='Эскиз выреза',feature_name='Вырез угла')
    assert runtime.calls == [(method,'cut-request',operation,payload,0.)]
    assert result['status'] == 'succeeded'


@pytest.mark.parametrize('tool',['part_prepare_corner_cut','part_create_corner_cut'])
@pytest.mark.parametrize('key,value',[('width_mm',True),('height_mm','5'),('width_mm',float('nan')),
    ('height_mm',float('inf')),('width_mm',.0001),('width_mm',10000001.),('timeout_s',121.)])
def test_invalid_native_lengths_rejected_before_dispatch(setup, tool, key, value):
    app, runtime = setup
    payload = arguments(tool)
    payload[key] = value
    with pytest.raises(ToolError): asyncio.run(app.call_tool(tool,payload))
    assert runtime.calls == []
