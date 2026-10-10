"""Real MCP stdio and uniform responses for the v2 development entry point."""

import asyncio
from pathlib import Path
import sqlite3
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from solidworks_mcp import __version__
from solidworks_mcp.jobs import JobStore
from solidworks_mcp.runtime_v2 import Runtime
from solidworks_mcp.server_v2 import create_app


ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'status', 'operation_id', 'context', 'data', 'diagnostics', 'error'}
TOOLS = {'system_get_info', 'job_get', 'job_list', 'job_cancel', 'document_list', 'document_get',
         'body_list', 'face_list', 'edge_list', 'geometry_get', 'feature_list', 'feature_get', 'feature_rename',
         'dimension_list', 'dimension_get', 'dimension_set_value', 'export_prepare', 'export_part',
         'part_prepare_base_extrusion', 'part_create_base_extrusion',
         'document_list_templates', 'document_prepare_create_part', 'document_create_part', 'sketch_get', 'sketch_prepare_dimension_change', 'sketch_set_dimension', 'part_prepare_corner_cut', 'part_create_corner_cut', 'part_prepare_base_revolve', 'part_create_base_revolve', 'part_prepare_through_hole', 'part_create_through_hole', 'part_prepare_hole_dimension_change', 'part_set_hole_dimension'}


def test_v2_stdio_discovery_unicode_guide_and_journal_survive_restart(tmp_path):
    directory = tmp_path / 'state'
    store = JobStore(directory / 'jobs.sqlite')
    queued, _ = store.create('old-running', 'part.create', {'name': 'Кронштейн'})
    store.start(queued['operation_id'])
    store.close()
    async def exercise():
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'solidworks_mcp.server_v2', '--state-dir', str(directory)],
            env={'PYTHONPATH': str(ROOT / 'src')})
        with anyio.fail_after(10):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    assert {tool.name for tool in tools.tools} == TOOLS
                    assert all(tool.outputSchema and tool.outputSchema['type'] == 'object'
                               and set(tool.outputSchema['properties']) == FIELDS for tool in tools.tools)
                    info = (await client.call_tool('system_get_info')).structuredContent
                    assert set(info) == FIELDS
                    assert info['data']['api_version'] == 2
                    assert info['data']['package_version'] == __version__
                    assert len(info['data']['schema_hash']) == 64
                    assert info['data']['capabilities']['cad_mutations'] is True
                    assert info['data']['implemented_mutations'] == [
                        'feature.rename', 'dimension.set_value', 'export.execute', 'part.create_base_extrusion', 'document.create_part', 'sketch.set_dimension', 'part.create_corner_cut', 'part.create_base_revolve', 'part.create_through_hole', 'part.set_hole_dimension']
                    assert info['data']['mutation_revision_scopes'] == [
                        'part_feature_tree_v1', 'part_dimension_values_v1', 'part_solid_brep_export_v1', 'empty_part_base_rectangle_v1', 'new_empty_part_document_v1', 'part_rectangular_sketch_dimension_v1', 'single_base_rectangular_corner_through_cut_v1', 'empty_part_full_turn_cylinder_revolve_v1', 'single_base_circular_through_hole_v1', 'single_base_circular_through_hole_dimension_v1']
                    assert info['data']['export_output_configured'] is False
                    unavailable = (await client.call_tool('export_prepare', {
                        'request_id': 'no-output', 'document_id': 'doc_explicit', 'configuration': 'Основная',
                        'file_format': 'stl', 'filename': 'Контрольная деталь.stl', 'units': 'mm',
                    })).structuredContent
                    assert unavailable['status'] == 'failed'
                    assert unavailable['operation_id'] is None
                    assert unavailable['error']['code'] == 'export_output_not_configured'
                    guide = await client.read_resource('solidworks://guide/v2')
                    assert 'русские названия' in guide.contents[0].text
                    assert all(f'`{name}`' in guide.contents[0].text for name in TOOLS)
                    old = (await client.call_tool('job_get', {'operation_id': queued['operation_id']})).structuredContent
                    assert old['status'] == 'unknown' and old['data']['request_id'] == 'old-running'
                    assert old['data']['payload']['arguments']['name'] == 'Кронштейн'
                    assert old['error']['code'] == 'runtime_restarted'
                    page = (await client.call_tool('job_list', {'limit': 1})).structuredContent
                    assert len(page['data']['items']) == 1
                    cancellation = (await client.call_tool('job_cancel', {'operation_id': queued['operation_id']})).structuredContent
                    assert cancellation['data']['cancelled'] is False
                    missing = (await client.call_tool('job_get', {'operation_id': 'missing'})).structuredContent
                    assert missing['status'] == 'failed' and missing['error']['code'] == 'job_not_found'
    asyncio.run(exercise())


def test_v2_catalog_hash_is_stable_and_no_legacy_tools_leak(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    try:
        app = create_app(store)
        async def exercise():
            assert {tool.name for tool in await app.list_tools()} == TOOLS
            # call_tool returns (content, structured result) in FastMCP 1.x.
            _, first = await app.call_tool('system_get_info', {})
            _, second = await app.call_tool('system_get_info', {})
            assert first['data']['schema_hash'] == second['data']['schema_hash']
            _, bad = await app.call_tool('job_list', {'limit': 0})
            assert bad['status'] == 'failed' and bad['error']['code'] == 'invalid_limit'
        asyncio.run(exercise())
    finally:
        store.close()


def test_journal_io_error_still_has_typed_response(tmp_path, monkeypatch):
    store = JobStore(tmp_path / 'jobs.sqlite')
    try:
        app = create_app(store)
        def broken(*args, **kwargs):
            raise sqlite3.OperationalError('disk I/O error')
        monkeypatch.setattr(store, 'get', broken)
        async def exercise():
            _, result = await app.call_tool('job_get', {'operation_id': 'some-job'})
            assert set(result) == FIELDS
            assert result['status'] == 'failed'
            assert result['error']['code'] == 'journal_unavailable'
        asyncio.run(exercise())
    finally:
        store.close()


def test_export_configuration_discovery_and_missing_root_fail_before_cad(tmp_path):
    def forbidden():
        raise AssertionError('Discovery and missing export configuration must not start CAD.')
    store = JobStore(tmp_path / 'jobs.sqlite')
    runtime = Runtime(store, worker_factory=forbidden, catalog_factory=forbidden)
    try:
        app = create_app(store, runtime)
        async def exercise():
            _, info = await app.call_tool('system_get_info', {})
            assert info['data']['export_output_configured'] is False
            assert info['data']['capabilities']['part_exports'] is True
            for tool in ('export_prepare', 'export_part'):
                arguments = {'request_id': tool, 'document_id': 'explicit', 'configuration': 'Основная',
                             'file_format': 'stl', 'filename': 'Деталь.stl', 'units': 'mm'}
                if tool == 'export_part':
                    arguments['expected_revision'] = 'explicit'
                _, result = await app.call_tool(tool, arguments)
                assert result['status'] == 'failed' and result['operation_id'] is None
                assert result['error']['code'] == 'export_output_not_configured'
            assert store.list()['items'] == [] and runtime._runner is None
        asyncio.run(exercise())
    finally:
        runtime.shutdown()
