"""Actual MCP schema/routing to artificial runtime; no native CAD."""

import asyncio

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.document_creation_tools_v2 import register_document_creation_tools
from test_dimension_tools_v2 import Runtime


@pytest.fixture
def setup():
    app, runtime = FastMCP('document-creation-test'), Runtime()
    register_document_creation_tools(app, runtime, lambda **kwargs: ResponseEnvelope(diagnostics=[], **kwargs),
                                    lambda error: pytest.fail(str(error)))
    return app, runtime


@pytest.mark.parametrize('tool,method,operation,arguments,domain', [
    ('document_list_templates', 'read', 'document.list_templates', {}, {}),
    ('document_prepare_create_part', 'read', 'document.prepare_create_part',
        {'template_id': 'template_exact', 'name': 'Новая деталь'},
        {'template_id': 'template_exact', 'name': 'Новая деталь', 'configuration_name': 'Основная'}),
    ('document_create_part', 'mutate', 'document.create_part',
        {'application_id': 'app_exact', 'expected_revision': 'rev_exact', 'template_id': 'template_exact', 'name': 'Новая деталь'},
        {'document_id': 'app_exact', 'configuration': '', 'expected_revision': 'rev_exact',
         'template_id': 'template_exact', 'name': 'Новая деталь', 'configuration_name': 'Основная'})])
def test_explicit_application_target_maps_to_durable_context_without_wait_timeout(setup, tool, method, operation, arguments, domain):
    app, runtime = setup
    _, result = asyncio.run(app.call_tool(tool, {'request_id': 'new-part', 'timeout_s': 0., **arguments}))
    assert runtime.calls == [(method, 'new-part', operation, domain, 0.)]
    assert set(result) == {'status', 'operation_id', 'context', 'data', 'diagnostics', 'error'}


def test_missing_explicit_application_target_never_dispatches(setup):
    app, runtime = setup
    with pytest.raises(ToolError):
        asyncio.run(app.call_tool('document_create_part', {'request_id': 'r', 'expected_revision': 'rev',
            'template_id': 'template', 'name': 'Деталь'}))
    assert runtime.calls == []
