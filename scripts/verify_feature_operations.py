"""Installed MCP stdio acceptance for persistent feature reads and guarded rename.

Only two exact, unsaved fixture documents are written. Direct COM changes to
owned fixtures exercise stale revisions and deletion. No user CAD models are
activated, saved or changed; native baseline/preferences are restored on exit.
"""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pythoncom

import solidworks_mcp
from solidworks_mcp import binding
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures


def native_features(model):
    feature = binding.wrap(model.FirstFeature(), binding.module().IFeature)
    result = []
    while feature is not None:
        result.append(feature)
        feature = binding.wrap(feature.GetNextFeature(), binding.module().IFeature)
    return result


async def check(state):
    assert 'site-packages' in solidworks_mcp.__file__, 'Use the installed wheel without PYTHONPATH.'
    original = native_snapshot()
    report = {}
    with fixtures() as (_, owned, _):
        setup = native_snapshot()
        titles = [str(model.GetTitle()) for model in owned]
        first_native = next(f for f in native_features(owned[0]) if f.Name == 'Контрольный блок 1')
        second_names = [(int(f.GetID()), str(f.Name)) for f in native_features(owned[1])]
        params = StdioServerParameters(command=str(Path(sys.executable).with_name('solidworks-mcp-v2.exe')),
                                       args=['--state-dir', str(state)])
        async def call(client, tool, **arguments):
            if tool not in ('system_get_info', 'job_get'):
                arguments.setdefault('request_id', uuid.uuid4().hex)
            value = (await client.call_tool(tool, arguments)).structuredContent
            while value['status'] in ('queued', 'running'):
                await asyncio.sleep(.25)
                job = (await client.call_tool('job_get', {'operation_id': value['operation_id']})).structuredContent
                value = {**job, 'data': job['data'] if tool == 'job_get' else job['data']['result']}
            return value
        def success(value):
            assert value['status'] == 'succeeded', value
            return value['data']
        with anyio.fail_after(600):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    info = success(await call(client, 'system_get_info'))
                    assert info['build_matches_source'] is True
                    assert info['implemented_mutations'] == ['feature.rename']
                    tools = (await client.list_tools()).tools
                    assert len(tools) == 13 and all(tool.outputSchema for tool in tools)
                    docs = success(await call(client, 'document_list'))['documents']
                    a, b = [next(d for d in docs if d['title'] == title) for title in titles]
                    context = {'document_id': a['document_id'], 'configuration': 'Основная'}
                    page = success(await call(client, 'feature_list', **context, limit=200))
                    assert page['revision_scope'] == 'part_feature_tree_v1'
                    target = next(item for item in page['items'] if item['name'] == 'Контрольный блок 1')
                    assert target['object_id'] and target['persistent_reference_supported']
                    assert target['native_id'] == first_native.GetID()
                    assert native_snapshot() == setup
                    short = success(await call(client, 'feature_list', **context, limit=2))
                    next_page = success(await call(client, 'feature_list', **context, limit=2, cursor=short['next_cursor']))
                    assert {i['native_id'] for i in short['items']}.isdisjoint({i['native_id'] for i in next_page['items']})
                    args = {**context, 'object_id': target['object_id'], 'expected_revision': page['revision']}
                    for name, error in [('Box', 'invalid_russian_name'), ('Контрольный блок 2', 'feature_name_conflict')]:
                        failed = await call(client, 'feature_rename', **args, name=name)
                        assert failed['status'] == 'failed' and failed['error']['code'] == error
                    foreign = await call(client, 'feature_rename', **{**args, 'document_id': b['document_id']}, name='Чужое имя')
                    assert foreign['status'] == 'failed' and foreign['error']['code'] == 'object_reference_not_found'
                    inactive = await call(client, 'feature_rename', **{**args, 'configuration': 'Вариант'}, name='Неактивное имя')
                    assert inactive['status'] == 'failed' and inactive['error']['code'] == 'configuration_not_active'
                    assert first_native.Name == 'Контрольный блок 1'

                    # Actual outside-MCP native name edit, with no reliance on
                    # update stamp increment for metadata changes.
                    stamp = int(owned[0].GetUpdateStamp())
                    first_native.Name = 'Ручное русское имя'
                    assert first_native.Name == 'Ручное русское имя'
                    manual_stamp_changed = int(owned[0].GetUpdateStamp()) != stamp
                    stale = await call(client, 'feature_rename', **args, name='Устаревшее имя')
                    assert stale['status'] == 'failed' and stale['error']['code'] == 'stale_revision'
                    assert first_native.Name == 'Ручное русское имя'
                    fresh = success(await call(client, 'feature_get', **context, object_id=target['object_id']))
                    assert fresh['feature']['name'] == 'Ручное русское имя'
                    rename_args = {**context, 'object_id': target['object_id'], 'expected_revision': fresh['revision'],
                                   'name': 'Основание механизма', 'request_id': 'owned-native-rename', 'timeout_s': 0}
                    pending = (await client.call_tool('feature_rename', rename_args)).structuredContent
                    retry = (await client.call_tool('feature_rename', rename_args)).structuredContent
                    assert pending['operation_id'] == retry['operation_id']
                    finished = await call(client, 'job_get', operation_id=pending['operation_id'])
                    assert finished['status'] == 'succeeded', finished
                    proof = finished['data']
                    assert proof['mutation']['phase'] == 'committed'
                    assert proof['mutation']['before_state']['name'] == 'Ручное русское имя'
                    assert first_native.Name == 'Основание механизма'
                    readback = success(await call(client, 'feature_get', **context, object_id=target['object_id']))
                    assert readback['feature']['native_id'] == target['native_id']
                    assert readback['feature']['name'] == 'Основание механизма'
                    renamed_tree = success(await call(client, 'feature_list', **context, limit=200))
                    assert renamed_tree['mutation_sequence'] == 1
                    assert renamed_tree['revision'] != fresh['revision']
                    assert [(int(f.GetID()), str(f.Name)) for f in native_features(owned[1])] == second_names
                    assert native_snapshot()[2] == setup[2], 'MCP rename activated an unrelated target.'

                    # Delete only the exact owned target; an old opaque reference
                    # must not fall back to a similarly named feature.
                    activated, _ = binding.connect(show=False).ActivateDoc3(titles[0], False, 1, 0)
                    assert activated is not None
                    owned[0].ClearSelection2(True)
                    assert first_native.Select2(False, 0)
                    owned[0].EditDelete()
                    deleted = await call(client, 'feature_get', **context, object_id=target['object_id'])
                    assert deleted['status'] == 'failed'
                    assert deleted['error']['code'] in ('object_deleted', 'object_reference_invalid', 'feature_not_current')
                    report = {'package_version': info['package_version'], 'git_sha': info['build']['git_sha'],
                        'source_dirty': info['build']['source_dirty'], 'build_matches_source': True,
                        'solidworks_revision': original[0], 'tool_count': len(tools), 'owned_fixture_documents': 2,
                        'native_mcp_feature_rename': True, 'persistent_reference_survives_rename': True,
                        'same_request_does_not_duplicate_write': True, 'timeout_zero_initial_status': pending['status'],
                        'durable_before_after_and_committed_hold': True, 'foreign_and_inactive_target_rejected': True,
                        'manual_name_edit_rejects_stale_revision': True,
                        'manual_name_edit_update_stamp_changed': manual_stamp_changed,
                        'second_document_features_unchanged': True, 'active_document_unchanged': True,
                        'deleted_reference_rejected': True, 'deleted_reference_error': deleted['error']['code'],
                        'revision_scope': 'part_feature_tree_v1', 'scope_not_all_cad_metadata': True}
    assert native_snapshot() == original
    report['original_document_baseline_restored'] = True
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    pythoncom.CoInitialize()
    try:
        print(json.dumps(asyncio.run(check(args.state_dir)), ensure_ascii=True, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
