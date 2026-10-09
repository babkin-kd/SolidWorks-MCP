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
from solidworks_mcp.server_v2 import create_app


ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'status', 'operation_id', 'context', 'data', 'diagnostics', 'error'}
TOOLS = {'system_get_info', 'job_get', 'job_list', 'job_cancel', 'document_list', 'document_get',
         'body_list', 'face_list', 'edge_list', 'geometry_get'}


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
                    assert info['data']['capabilities']['cad_mutations'] is False
                    guide = await client.read_resource('solidworks://guide/v2')
                    assert 'русские названия' in guide.contents[0].text
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
