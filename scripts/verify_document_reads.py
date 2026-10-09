"""Read-only native acceptance through the installed v2 MCP console entry point.

Run with the dev environment Python, without PYTHONPATH. Private journal stays
in --state-dir. Report never includes user CAD paths, titles or configurations.
No documents are created, activated, switched, saved, closed or rebuilt.
"""

import argparse
import asyncio
from importlib import metadata
import json
from pathlib import Path
import sys
import uuid

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pythoncom
import win32com.client
from win32com.client import gencache

import solidworks_mcp


def native_snapshot():
    """Independent native observations, not the adapter under test."""
    raw = win32com.client.GetActiveObject('SldWorks.Application')
    revision = win32com.client.dynamic.DumbDispatch(raw._oleobj_).RevisionNumber
    module = gencache.EnsureModule('{83A33D31-27C5-11CE-BFD4-00400513BB57}', 0,
                                   int(revision.split('.')[0]), 0)
    sw = module.ISldWorks(raw._oleobj_)
    active = sw.ActiveDoc
    active_identity = active._oleobj_.QueryInterface(pythoncom.IID_IUnknown) if active else None
    states = []
    for raw in sw.GetDocuments() or ():
        model = module.IModelDoc2(raw._oleobj_)
        configuration = model.GetActiveConfiguration()
        states.append((model._oleobj_.QueryInterface(pythoncom.IID_IUnknown),
                       model.GetTitle(), model.GetPathName(), model.GetUpdateStamp(),
                       bool(model.GetSaveFlag()), tuple(model.GetConfigurationNames() or ()),
                       module.IConfiguration(configuration._oleobj_).Name if configuration else ''))
    return revision, bool(sw.Visible), active_identity, states


async def check(state):
    assert 'site-packages' in solidworks_mcp.__file__, 'Verify the installed wheel without PYTHONPATH.'
    before = native_snapshot()
    params = StdioServerParameters(command=str(Path(sys.executable).with_name('solidworks-mcp-v2.exe')),
                                   args=['--state-dir', str(state)])
    async def call(client, tool, arguments):
        response = (await client.call_tool(tool, arguments)).structuredContent
        while response['status'] in ('queued', 'running'):
            await asyncio.sleep(0.25)
            job = (await client.call_tool('job_get', {'operation_id': response['operation_id']})).structuredContent
            response = {**job, 'data': job['data']['result']}
        return response
    with anyio.fail_after(90):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                assert {tool.name for tool in tools} == {
                    'system_get_info', 'job_get', 'job_list', 'job_cancel', 'document_list', 'document_get'}
                assert all(tool.outputSchema for tool in tools)
                info = (await client.call_tool('system_get_info')).structuredContent['data']
                assert info['build_matches_source'] is True
                assert info['capabilities']['cad_documents'] is True
                assert info['capabilities']['cad_mutations'] is False
                request_id = uuid.uuid4().hex
                listed = await call(client, 'document_list', {'request_id': request_id, 'timeout_s': 0})
                assert listed['status'] == 'succeeded', listed['error']
                documents = listed['data']['documents']
                assert len(documents) == len(before[3])
                assert len({d['document_id'] for d in documents}) == len(documents)
                assert len(documents) >= 2, 'At least two open documents required for explicit targeting acceptance.'
                repeat = await call(client, 'document_list', {'request_id': request_id})
                assert repeat['operation_id'] == listed['operation_id'] and repeat['data'] == listed['data']
                for document in documents[:2]:
                    configuration = document['configurations'][0] if document['configurations'] else ''
                    result = await call(client, 'document_get', {'request_id': uuid.uuid4().hex,
                        'document_id': document['document_id'], 'configuration': configuration})
                    assert result['status'] == 'succeeded', result['error']
                    assert result['data']['document_id'] == document['document_id']
                    assert result['data']['path'] == document['path']
                    assert result['data']['observation_revision'] == document['observation_revision']
                bad = await call(client, 'document_get', {'request_id': uuid.uuid4().hex,
                    'document_id': documents[0]['document_id'], 'configuration': 'missing_' + uuid.uuid4().hex})
                assert bad['error']['code'] == 'configuration_not_found'
                bad = await call(client, 'document_get', {'request_id': uuid.uuid4().hex,
                    'document_id': 'doc_missing', 'configuration': ''})
                assert bad['error']['code'] == 'document_not_open'
                fresh = await call(client, 'document_list', {'request_id': uuid.uuid4().hex})
                assert fresh['data'] == listed['data']
        # Server restart: historical jobs survive, but document IDs must not.
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                old = (await client.call_tool('job_get', {'operation_id': listed['operation_id']})).structuredContent
                assert old['status'] == 'succeeded' and old['data']['result'] == listed['data']
                fresh = await call(client, 'document_list', {'request_id': uuid.uuid4().hex})
                assert {d['document_id'] for d in fresh['data']['documents']}.isdisjoint(
                    {d['document_id'] for d in documents})
                stale = await call(client, 'document_get', {'request_id': uuid.uuid4().hex,
                    'document_id': documents[0]['document_id'], 'configuration': documents[0]['active_configuration']})
                assert stale['error']['code'] == 'document_not_open'
    after = native_snapshot()
    assert before == after, 'Native document state changed during read-only acceptance.'
    return {'package_version': metadata.version('solidworks-mcp'), 'git_sha': info['build']['git_sha'],
            'build_matches_source': True, 'source_dirty': info['build']['source_dirty'],
            'solidworks_revision': before[0], 'open_documents': len(before[3]),
            'explicit_targets_verified': 2, 'tool_count': len(tools),
            'idempotent_read': True, 'restart_invalidates_ids': True,
            'historical_results_survive': True, 'native_state_unchanged': True,
            'scope': 'read_only_document_metadata; no mutation, geometry or inactive configuration acceptance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    pythoncom.CoInitialize()
    try:
        print(json.dumps(asyncio.run(check(args.state_dir.resolve())), ensure_ascii=True))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
