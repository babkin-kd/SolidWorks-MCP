"""Numeric JSON types must not be silently changed before journal/STA guards."""

import asyncio

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from solidworks_mcp.jobs import JobStore
from solidworks_mcp.runtime_v2 import Runtime
from solidworks_mcp.server_v2 import create_app


CONTEXT = {'request_id': 'strict', 'document_id': 'doc', 'configuration': 'Основная'}
CAD_TOOLS = [
    ('document_list', {'request_id': 'strict'}),
    ('document_get', CONTEXT),
    ('body_list', {**CONTEXT, 'expected_observation_revision': 'obs'}),
    ('face_list', {**CONTEXT, 'expected_observation_revision': 'obs', 'body_id': 'body'}),
    ('edge_list', {**CONTEXT, 'expected_observation_revision': 'obs', 'body_id': 'body'}),
    ('geometry_get', {**CONTEXT, 'expected_observation_revision': 'obs', 'object_id': 'body'}),
    ('feature_list', CONTEXT),
    ('feature_get', {**CONTEXT, 'object_id': 'feature'}),
    ('feature_rename', {**CONTEXT, 'object_id': 'feature', 'expected_revision': 'rev', 'name': 'Основание'}),
]


@pytest.mark.parametrize('tool,arguments', CAD_TOOLS)
@pytest.mark.parametrize('invalid', [True, False, '10'])
def test_timeout_types_are_rejected_before_journal_or_cad(tmp_path, tool, arguments, invalid):
    store = JobStore(tmp_path / 'jobs.sqlite')
    def forbidden():
        pytest.fail('Invalid scalar must not start a CAD worker.')
    runtime = Runtime(store, worker_factory=forbidden, catalog_factory=forbidden)
    try:
        app = create_app(store, runtime)
        with pytest.raises(ToolError):
            asyncio.run(app.call_tool(tool, {**arguments, 'timeout_s': invalid}))
        assert store.list()['items'] == [] and runtime._runner is None
    finally:
        runtime.shutdown()


@pytest.mark.parametrize('tool,arguments', [
    ('job_list', {}), ('body_list', CAD_TOOLS[2][1]),
    ('face_list', CAD_TOOLS[3][1]), ('edge_list', CAD_TOOLS[4][1]), ('feature_list', CONTEXT),
])
@pytest.mark.parametrize('invalid', [True, False, '1', 1.0])
def test_page_limit_types_are_rejected_before_journal_or_cad(tmp_path, tool, arguments, invalid):
    store = JobStore(tmp_path / 'jobs.sqlite')
    def forbidden():
        pytest.fail('Invalid scalar must not start a CAD worker.')
    runtime = Runtime(store, worker_factory=forbidden, catalog_factory=forbidden)
    try:
        app = create_app(store, runtime)
        with pytest.raises(ToolError):
            asyncio.run(app.call_tool(tool, {**arguments, 'limit': invalid}))
        assert store.list()['items'] == [] and runtime._runner is None
    finally:
        runtime.shutdown()


@pytest.mark.parametrize('invalid', [True, False, '1'])
def test_journal_cursor_keeps_numeric_type_validation(tmp_path, invalid):
    store = JobStore(tmp_path / 'jobs.sqlite')
    try:
        app = create_app(store)
        with pytest.raises(ToolError):
            asyncio.run(app.call_tool('job_list', {'before_created_at': invalid, 'before_operation_id': 'op'}))
        assert store.list()['items'] == []
    finally:
        store.close()
