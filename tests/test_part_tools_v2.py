"""Actual MCP validation/dispatch against an artificial runtime, without CAD."""

import asyncio

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.part_tools_v2 import register_part_tools
from test_dimension_tools_v2 import Runtime


@pytest.fixture
def setup():
    app, runtime = FastMCP('parts-test'), Runtime()
    register_part_tools(app, runtime, lambda **kwargs: ResponseEnvelope(diagnostics=[], **kwargs),
                        lambda error: pytest.fail(str(error)))
    return app, runtime


def args(tool):
    value = dict(request_id='plate-request', document_id='doc_explicit', configuration='Основная',
                 plane_object_id='feat_' + 'a' * 32, width_mm=40., height_mm=20., depth_mm=10., timeout_s=0.)
    if tool == 'part_create_base_extrusion': value['expected_revision'] = 'rev_explicit'
    return value


@pytest.mark.parametrize('tool,method,operation', [
    ('part_prepare_base_extrusion', 'read', 'part.prepare_base_extrusion'),
    ('part_create_base_extrusion', 'mutate', 'part.create_base_extrusion')])
def test_tools_route_exact_targets_and_russian_defaults_without_timeout_in_job_payload(setup, tool, method, operation):
    app, runtime = setup
    _, result = asyncio.run(app.call_tool(tool, args(tool)))
    sent = {key: value for key, value in args(tool).items() if key not in ('request_id', 'timeout_s')}
    sent.update(sketch_name='Эскиз основания', feature_name='Основание', body_name='Тело основания')
    assert runtime.calls == [(method, 'plate-request', operation, sent, 0.)]
    assert set(result) == {'status', 'operation_id', 'context', 'data', 'diagnostics', 'error'}


@pytest.mark.parametrize('parameter,value', [('width_mm', True), ('height_mm', '20'),
    ('depth_mm', float('nan')), ('depth_mm', float('inf')), ('depth_mm', .0001)])
def test_invalid_lengths_are_rejected_by_mcp_before_runtime_dispatch(setup, parameter, value):
    app, runtime = setup
    payload = args('part_create_base_extrusion')
    payload[parameter] = value
    with pytest.raises(ToolError): asyncio.run(app.call_tool('part_create_base_extrusion', payload))
    assert runtime.calls == []
