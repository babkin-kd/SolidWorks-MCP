"""Future installed MCP stdio acceptance for features in the public 18-tool catalog.

Only two exact, unsaved fixture documents are written. Direct COM changes to
owned fixtures exercise stale revisions and deletion. No user CAD models are
activated, saved or changed; uncertain outcomes retain fixtures and journals.
Preparation is not acceptance evidence; SDK lifetime has no suite deadline.
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
from importlib import resources
import json
import os
from pathlib import Path
import sys
import uuid

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pythoncom

import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures
from verify_export_operations import application_preferences, ui_snapshot, user_file_metadata
from verifier_lifecycle import ToolSpec, open_supervised_session


EXPECTED_TOOL_COUNT = 18
FEATURE_TOOLS = {'document_list', 'feature_list', 'feature_get', 'feature_rename'}
TOOL_SPECS = {
    'document_list': ToolSpec('document.list', False),
    'feature_list': ToolSpec('feature.list', False, argument_defaults={'limit': 100, 'cursor': ''}),
    'feature_get': ToolSpec('feature.get', False),
    'feature_rename': ToolSpec('feature.rename', True,
        prewrite_failure_codes=frozenset({'invalid_russian_name', 'feature_name_conflict',
            'object_reference_not_found', 'configuration_not_active', 'stale_revision'})),
}


class SessionCleanupGate:
    def __init__(self):
        self.owners = []

    def add(self, owner):
        self.owners.append(owner)

    def can_cleanup(self):
        # Before ownership only init/metadata may run; later owners all need proof.
        return all(owner.cleanup_gate.can_cleanup() is True for owner in self.owners)


def _provenance():
    package = Path(solidworks_mcp.__file__).resolve().parent
    assert 'site-packages' in package.parts, 'Use the installed wheel without source PYTHONPATH.'
    assert not os.environ.get('PYTHONPATH'), 'Unset PYTHONPATH before native acceptance.'
    build = json.loads(resources.files('solidworks_mcp').joinpath('build_info.json').read_text(encoding='utf8'))
    actual = source_digest(package)
    assert build.get('package_version') == solidworks_mcp.__version__
    assert build.get('source_digest') == actual
    assert build.get('source_dirty') is False, 'Native acceptance requires a clean installed wheel.'
    sha = build.get('git_sha')
    assert isinstance(sha, str) and len(sha) == 40 and all(c in '0123456789abcdef' for c in sha)
    return {'package_version': solidworks_mcp.__version__, 'git_sha': sha, 'source_dirty': False,
            'installed_source_digest': actual, 'installed_build_matches_package': True}


async def response(client, tool, arguments):
    raw = await client.call_tool(tool, arguments)
    assert not raw.isError, raw
    value = raw.structuredContent
    assert isinstance(value, dict) and 'status' in value, raw
    return value


async def call(client, tool, **arguments):
    if tool not in ('system_get_info', 'job_get', 'job_list'):
        arguments.setdefault('request_id', uuid.uuid4().hex)
    value = await response(client, tool, arguments)
    while value['status'] in ('queued', 'running'):
        await asyncio.sleep(.25)
        job = await response(client, 'job_get', {'operation_id': value['operation_id']})
        value = {**job, 'data': job['data'] if tool == 'job_get' else job['data']['result']}
    return value


def success(value):
    assert value['status'] == 'succeeded', value
    return value['data']


@asynccontextmanager
async def metadata_session(params, provenance, metadata):
    """No durable/CAD tool dispatch before the supervisor is installed."""
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as raw:
            await raw.initialize()
            info = success(await response(raw, 'system_get_info', {}))
            assert info['build_matches_source'] is True and info['build']['source_dirty'] is False
            assert info['package_version'] == provenance['package_version']
            assert info['build']['git_sha'] == provenance['git_sha']
            assert info['source_digest'] == provenance['installed_source_digest']
            assert info['build']['source_digest'] == provenance['installed_source_digest']
            assert 'feature.rename' in info['implemented_mutations']
            tools = (await raw.list_tools()).tools
            assert len(tools) == EXPECTED_TOOL_COUNT and all(tool.outputSchema for tool in tools)
            assert FEATURE_TOOLS <= {tool.name for tool in tools}
            metadata.update(info=info, tools=tools)
            yield raw


async def require_native_cleanup(owner, aggregate):
    with anyio.CancelScope(shield=True):
        decision = await owner.observe_once()
    if not decision.child_can_close or not aggregate.can_cleanup():
        raise RuntimeError('Retain owned fixtures: native read/activation requires fresh coherent job proof.')


async def owned_native(owner, aggregate, function):
    """A cached earlier gate never authorizes a later getter/write."""
    await require_native_cleanup(owner, aggregate)
    try:
        return function()
    except BaseException:
        owner.retain('independent native feature/UI check failed')
        raise


@asynccontextmanager
async def owned_active_document(owner, aggregate, activate, restore):
    await require_native_cleanup(owner, aggregate)
    try:
        activate()
        yield
    except BaseException as original:
        await owner.drain()
        if aggregate.can_cleanup():
            try:
                restore()
            except BaseException as error:
                owner.retain('owned activation restoration failed')
                original.add_note(f'Owned activation restoration failed: {type(error).__name__}')
        raise
    else:
        await require_native_cleanup(owner, aggregate)
        try:
            restore()
        except BaseException:
            owner.retain('owned activation restoration failed')
            raise


def native_features(model):
    feature = binding.wrap(model.FirstFeature(), binding.module().IFeature)
    result = []
    while feature is not None:
        result.append(feature)
        feature = binding.wrap(feature.GetNextFeature(), binding.module().IFeature)
    return result


async def check(state):
    provenance = _provenance()  # Before all CAD reads/fixture setup.
    original = native_snapshot()
    sw = binding.connect(show=False)
    module = binding.module()
    original_ui = ui_snapshot(sw, module)
    original_preferences, original_files = application_preferences(sw), user_file_metadata(original)
    report = {**provenance, 'accepted': False}
    cleanup, metadata = SessionCleanupGate(), {}
    with fixtures(cleanup_gate=cleanup.can_cleanup) as (_, owned, _):
        setup = native_snapshot()
        setup_ui = ui_snapshot(sw, module)
        titles = [str(model.GetTitle()) for model in owned]
        assert all(not model.GetPathName() for model in owned), 'Only unsaved owned fixtures may be changed.'
        first_native = next(f for f in native_features(owned[0]) if f.Name == 'Контрольный блок 1')
        second_names = [(int(f.GetID()), str(f.Name)) for f in native_features(owned[1])]
        params = StdioServerParameters(command=str(Path(sys.executable).with_name('solidworks-mcp-v2.exe')),
                                       args=['--state-dir', str(state)])
        factory = lambda: metadata_session(params, provenance, metadata)
        async with open_supervised_session(factory, tool_specs=TOOL_SPECS,
                journal_path=state / 'jobs.sqlite') as client:
            cleanup.add(client)
            info, tools = metadata['info'], metadata['tools']
            docs = success(await call(client, 'document_list'))['documents']
            a, b = [next(d for d in docs if d['title'] == title) for title in titles]
            context = {'document_id': a['document_id'], 'configuration': 'Основная'}
            page = success(await call(client, 'feature_list', **context, limit=200))
            assert page['revision_scope'] == 'part_feature_tree_v1'
            target = next(item for item in page['items'] if item['name'] == 'Контрольный блок 1')
            assert target['object_id'] and target['persistent_reference_supported']
            def verify_initial():
                assert target['native_id'] == first_native.GetID()
                assert native_snapshot() == setup
            await owned_native(client, cleanup, verify_initial)
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
            # An actual outside-MCP owned name edit, not a stamp-only test.
            def manual_edit():
                assert first_native.Name == 'Контрольный блок 1'
                stamp = int(owned[0].GetUpdateStamp())
                first_native.Name = 'Ручное русское имя'
                assert first_native.Name == 'Ручное русское имя'
                return int(owned[0].GetUpdateStamp()) != stamp
            manual_stamp_changed = await owned_native(client, cleanup, manual_edit)
            stale = await call(client, 'feature_rename', **args, name='Устаревшее имя')
            assert stale['status'] == 'failed' and stale['error']['code'] == 'stale_revision'
            def verify_manual_name():
                assert first_native.Name == 'Ручное русское имя'
            await owned_native(client, cleanup, verify_manual_name)
            fresh = success(await call(client, 'feature_get', **context, object_id=target['object_id']))
            assert fresh['feature']['name'] == 'Ручное русское имя'
            rename_args = {**context, 'object_id': target['object_id'], 'expected_revision': fresh['revision'],
                           'name': 'Основание механизма', 'request_id': 'owned-native-rename', 'timeout_s': 0}
            pending = await response(client, 'feature_rename', rename_args)
            retry = await response(client, 'feature_rename', rename_args)
            assert pending['operation_id'] == retry['operation_id']
            finished = await call(client, 'job_get', operation_id=pending['operation_id'])
            assert finished['status'] == 'succeeded', finished
            proof = finished['data']
            assert proof['mutation']['phase'] == 'committed'
            assert proof['mutation']['before_state']['name'] == 'Ручное русское имя'
            assert proof['mutation']['before_state']['_mutation_effect_scope'] == 'application'
            guard_evidence = {'original_state': 0, 'locked_state': 2, 'released_state': 0}
            assert proof['result']['execution_guard'] == guard_evidence
            assert proof['mutation']['verification']['evidence']['execution_guard'] == guard_evidence
            def verify_rename():
                assert ui_snapshot(sw, module) == setup_ui, 'MCP changed blocking/selection state.'
                assert first_native.Name == 'Основание механизма'
            await owned_native(client, cleanup, verify_rename)
            readback = success(await call(client, 'feature_get', **context, object_id=target['object_id']))
            assert readback['feature']['native_id'] == target['native_id']
            assert readback['feature']['name'] == 'Основание механизма'
            renamed_tree = success(await call(client, 'feature_list', **context, limit=200))
            assert renamed_tree['mutation_sequence'] == 1
            assert renamed_tree['revision'] != fresh['revision']
            def verify_other_document():
                assert [(int(f.GetID()), str(f.Name)) for f in native_features(owned[1])] == second_names
                assert native_snapshot()[2] == setup[2], 'MCP rename activated an unrelated target.'
            await owned_native(client, cleanup, verify_other_document)

            def activate_owned(title):
                activated, _ = sw.ActivateDoc3(title, False, 1, 0)
                assert activated is not None
            def delete_owned_feature():
                owned[0].ClearSelection2(True)
                assert first_native.Select2(False, 0)
                owned[0].EditDelete()
            # Exact owned deletion and activation; restoration after fresh proof
            # or shielded drain, with no name fallback for the obsolete ID.
            async with owned_active_document(client, cleanup,
                    lambda: activate_owned(titles[0]), lambda: activate_owned(titles[1])):
                await owned_native(client, cleanup, delete_owned_feature)
                deleted = await call(client, 'feature_get', **context, object_id=target['object_id'])
                assert deleted['status'] == 'failed'
                assert deleted['error']['code'] in ('object_deleted', 'object_reference_invalid', 'feature_not_current')
            report.update({'package_version': info['package_version'], 'git_sha': info['build']['git_sha'],
                'source_dirty': info['build']['source_dirty'], 'build_matches_source': True,
                'solidworks_revision': original[0], 'tool_count': len(tools), 'owned_fixture_documents': 2,
                'native_mcp_feature_rename': True, 'persistent_reference_survives_rename': True,
                'same_request_does_not_duplicate_write': True, 'timeout_zero_initial_status': pending['status'],
                'durable_before_after_and_committed_hold': True, 'foreign_and_inactive_target_rejected': True,
                'native_ui_guard_release_verified_and_durable': True,
                'original_ui_blocking_and_selection_unchanged': True,
                'manual_name_edit_rejects_stale_revision': True,
                'manual_name_edit_update_stamp_changed': manual_stamp_changed,
                'second_document_features_unchanged': True, 'active_document_unchanged': True,
                'deleted_reference_rejected': True, 'deleted_reference_error': deleted['error']['code'],
                'revision_scope': 'part_feature_tree_v1', 'scope_not_all_cad_metadata': True})
        history = client.history_seed()
        # Observe exact issued history without resuming/repeating any mutation.
        async with open_supervised_session(factory, tool_specs=TOOL_SPECS,
                journal_path=state / 'jobs.sqlite', trusted_history=history, readonly_restart=True) as client:
            cleanup.add(client)
            assert success(await call(client, 'job_get', operation_id=pending['operation_id'])) == proof
            reopened = success(await call(client, 'document_list'))['documents']
            new_document = next(d for d in reopened if d['title'] == titles[0])
            assert new_document['document_id'] != context['document_id']
            obsolete = await call(client, 'feature_get', **context, object_id=target['object_id'])
            assert obsolete['status'] == 'failed' and obsolete['error']['code'] == 'document_not_open'
            obsolete = await call(client, 'feature_get', document_id=new_document['document_id'],
                                  configuration='Основная', object_id=target['object_id'])
            assert obsolete['status'] == 'failed' and obsolete['error']['code'] == 'object_reference_not_found'
            await owned_native(client, cleanup, lambda: None)
        report.update(historical_job_survives_readonly_restart=True, restart_invalidates_document_and_feature_ids=True)
    assert cleanup.can_cleanup(), 'Retain fixtures without original native baseline reads.'
    assert native_snapshot() == original
    assert ui_snapshot(sw, module) == original_ui
    assert application_preferences(sw) == original_preferences
    assert user_file_metadata(original) == original_files
    report.update(accepted=True, original_document_baseline_restored=True, original_preferences_and_ui_restored=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    private_root = Path(__file__).resolve().parent.parent / 'work'
    assert args.state_dir.resolve().is_relative_to(private_root), 'Keep native journals in private work/.'
    assert not args.state_dir.exists(), 'Use a fresh journal, never recover an uncertain previous run.'
    args.state_dir.mkdir(parents=True)
    pythoncom.CoInitialize()
    try:
        print(json.dumps(asyncio.run(check(args.state_dir)), ensure_ascii=True, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
