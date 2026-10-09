"""Future installed-wheel MCP dimension acceptance, only on owned fixtures.

Preparation is not acceptance evidence. Root runs this sequentially after the
internal native dimension proof and public tool integration. No original CAD
document is edited or saved; journals/reports belong in private work/ paths.
Waiting timeout is not cancellation. Only terminal jobs permit native readback.
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
from importlib import resources
import json
import math
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
from verify_export_operations import application_preferences, exact_solid, native_extrema_m, ui_snapshot, user_file_metadata
from verify_geometry_reads import fixtures
from verifier_lifecycle import ToolSpec, open_supervised_session


TOOLS = {'dimension_list', 'dimension_get', 'dimension_set_value'}
GUARD = {'original_state': 0, 'locked_state': 2, 'released_state': 0}
TOOL_SPECS = {
    'document_list': ToolSpec('document.list', False),
    'dimension_list': ToolSpec('dimension.list', False, argument_defaults={'limit': 100, 'cursor': ''}),
    'dimension_get': ToolSpec('dimension.get', False),
    'dimension_set_value': ToolSpec('dimension.set_value', True, float_arguments=frozenset({'value'}),
        prewrite_failure_codes=frozenset({'object_reference_not_found', 'dimension_unit_mismatch',
            'invalid_dimension_unit', 'unsupported_signed_dimension', 'dimension_not_writable',
            'document_not_active', 'stale_revision'})),
}


class SessionCleanupGate:
    """Only metadata can fail before an owner exists; all later owners must prove safety."""
    def __init__(self):
        self.owners = []

    def add(self, owner):
        self.owners.append(owner)

    def can_cleanup(self):
        return all(owner.cleanup_gate.can_cleanup() is True for owner in self.owners)


@asynccontextmanager
async def metadata_session(params, provenance, metadata):
    """No durable/CAD tool dispatch before the supervisor is installed."""
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as raw:
            await raw.initialize()
            info = succeeded(await response(raw, 'system_get_info', {}))
            assert info['build_matches_source'] is True and info['build']['source_dirty'] is False
            assert info['package_version'] == provenance['package_version']
            assert info['build']['git_sha'] == provenance['git_sha']
            assert info['source_digest'] == provenance['installed_source_digest']
            assert info['build']['source_digest'] == provenance['installed_source_digest']
            assert 'dimension.set_value' in info['implemented_mutations']
            tools = (await raw.list_tools()).tools
            assert TOOLS <= {tool.name for tool in tools}, 'Dimension tools are not published yet.'
            assert all(tool.outputSchema for tool in tools)
            metadata.update(info=info, tools=tools)
            yield raw


async def require_native_cleanup(owner, aggregate):
    """A cached earlier gate never authorizes a later native read/activation."""
    with anyio.CancelScope(shield=True):
        decision = await owner.observe_once()
    if not decision.child_can_close or not aggregate.can_cleanup():
        raise RuntimeError('Unconfirmed job state: retain owned fixtures without native readback/activation.')


@asynccontextmanager
async def inactive_owned_document(owner, aggregate, activate_other, restore_target):
    await require_native_cleanup(owner, aggregate)
    try:
        activate_other()
        yield
    except BaseException as original:
        # Lost acknowledgement may still mean queued/running COM. Drain keeps
        # the SDK owner alive, then only positive fixture proof allows Activate.
        await owner.drain()
        if aggregate.can_cleanup():
            try:
                restore_target()
            except BaseException as restoration_error:
                owner.retain('owned activation restoration failed')
                original.add_note(f'Owned activation restoration failed: {type(restoration_error).__name__}')
        raise
    else:
        await require_native_cleanup(owner, aggregate)
        try:
            restore_target()
        except BaseException:
            owner.retain('owned activation restoration failed')
            raise


async def response(client, tool, arguments):
    raw = await client.call_tool(tool, arguments)
    assert not raw.isError, raw
    value = raw.structuredContent
    assert isinstance(value, dict) and 'status' in value, raw
    return value


async def terminal_job(client, operation_id):
    # No local wait timeout pretends to cancel native COM. Root supervises this
    # verifier; keep polling until an actual terminal journal state is known.
    while True:
        value = await response(client, 'job_get', {'operation_id': operation_id})
        if value['status'] not in ('queued', 'running'):
            return value
        await asyncio.sleep(.25)


async def call(client, tool, **arguments):
    if tool not in ('system_get_info', 'job_get'):
        arguments.setdefault('request_id', uuid.uuid4().hex)
    value = await response(client, tool, arguments)
    if value['status'] in ('queued', 'running'):
        job = await terminal_job(client, value['operation_id'])
        return {**job, 'data': job['data'] if tool == 'job_get' else job['data']['result']}
    return value


def succeeded(value):
    assert value['status'] == 'succeeded', value
    return value['data']


def failed(value, code):
    assert value['status'] == 'failed' and value['error']['code'] == code, value


def _provenance():
    """Verify this installed wheel before any CAD snapshot or connection."""
    package = Path(solidworks_mcp.__file__).resolve().parent
    assert 'site-packages' in package.parts, 'Use an installed wheel, never source PYTHONPATH.'
    assert not os.environ.get('PYTHONPATH'), 'Unset PYTHONPATH before native acceptance.'
    build = json.loads(resources.files('solidworks_mcp').joinpath('build_info.json').read_text(encoding='utf8'))
    actual_digest = source_digest(package)
    assert build.get('package_version') == solidworks_mcp.__version__
    assert build.get('source_digest') == actual_digest, 'Installed build metadata does not match its files.'
    assert build.get('source_dirty') is False, 'Native acceptance requires a clean installed build.'
    sha = build.get('git_sha')
    assert isinstance(sha, str) and len(sha) == 40 and all(c in '0123456789abcdef' for c in sha), \
        'Installed build must identify its exact clean commit.'
    return {'package_version': solidworks_mcp.__version__, 'git_sha': sha,
            'source_dirty': False, 'installed_source_digest': actual_digest,
            'installed_build_matches_package': True}


def _require_internal_acceptance(internal, current):
    """Accept only a fresh same-wheel report, never a historical sidecar."""
    assert internal.get('accepted') is True, 'Internal native dimension acceptance did not pass.'
    for key in ('package_version', 'git_sha', 'installed_source_digest'):
        assert internal.get(key) == current[key], f'Internal report is for a different installed build: {key}'
    assert internal.get('source_dirty') is False, 'Internal report must certify a clean build.'
    assert internal.get('installed_build_matches_package') is True, 'Internal report lacks verified installed provenance.'
    for gate in ('native_typed_configuration_setter', 'explicit_dimension_reference_survives_rebuild',
                 'verified_scoped_restoration_after_injected_error', 'original_document_baseline_restored'):
        assert internal.get(gate) is True, f'Internal native gate is missing: {gate}'


async def check(state, internal_report):
    provenance = _provenance()
    internal = json.loads(internal_report.read_text(encoding='utf8'))
    _require_internal_acceptance(internal, provenance)
    original = native_snapshot()
    original_files = user_file_metadata(original)
    sw, module = binding.connect(show=False), binding.module()
    original_ui, original_preferences = ui_snapshot(sw, module), application_preferences(sw)
    report = {**provenance, 'public_mcp_dimension_acceptance': False}
    params = StdioServerParameters(command=str(Path(sys.executable).with_name('solidworks-mcp-v2.exe')),
                                   args=['--state-dir', str(state)])
    cleanup = SessionCleanupGate()
    metadata = {}
    session_factory = lambda: metadata_session(params, provenance, metadata)
    with fixtures(cleanup_gate=cleanup.can_cleanup) as (_, owned, _):
        model = owned[1]
        assert not model.GetPathName(), 'Only an unsaved owned fixture may be changed.'
        assert tuple(model.GetConfigurationNames()) == ('Основная',)
        titles = [str(item.GetTitle()) for item in owned]
        setup = native_snapshot()
        setup_ui, setup_preferences = ui_snapshot(sw, module), application_preferences(sw)
        target_identity = model._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
        assert setup[2] == target_identity
        other_states = [row for row in setup[3] if row[0] != target_identity]

        def physical(depth):
            body = exact_solid(model, module)
            bounds = native_extrema_m(body)
            size = [1000 * (high - low) for low, high in zip(bounds['min'], bounds['max'])]
            assert all(math.isclose(actual, expected, abs_tol=1e-7)
                       for actual, expected in zip(size, [5., 6., depth])), size
            assert all(math.isclose(value, 0., abs_tol=1e-10) for value in bounds['min']), bounds
            volume = float(body.GetMassProperties(1.)[3]) * 1e9
            assert math.isclose(volume, 5. * 6. * depth, abs_tol=1e-5), volume
            current = native_snapshot()
            assert current[2] == target_identity, 'MCP implicitly activated another document.'
            assert [row for row in current[3] if row[0] != target_identity] == other_states
            assert ui_snapshot(sw, module) == setup_ui
            assert application_preferences(sw) == setup_preferences
            return {'dimensions_mm': size, 'volume_mm3': volume}

        async def physical_proven(owner, depth):
            await require_native_cleanup(owner, cleanup)
            try:
                return physical(depth)
            except BaseException:
                owner.retain('independent geometry/UI verification failed')
                raise

        async with open_supervised_session(session_factory, tool_specs=TOOL_SPECS,
                journal_path=state / 'jobs.sqlite') as client:
            cleanup.add(client)
            info, tools = metadata['info'], metadata['tools']
            docs = succeeded(await call(client, 'document_list'))['documents']
            other, target_document = [next(row for row in docs if row['title'] == title) for title in titles]
            context = {'document_id': target_document['document_id'], 'configuration': 'Основная'}
            page = succeeded(await call(client, 'dimension_list', **context, limit=200))
            assert page['revision_scope'] == 'part_dimension_values_v1' and page['total_count'] == 3
            assert all(math.isclose(actual, expected, abs_tol=1e-8) for actual, expected in
                       zip(sorted(row['values']['Основная'] for row in page['items']), [5., 6., 7.]))
            assert all(row['object_id'] and row['persistent_reference_supported']
                       and row['reference_anchor']['strategy'] == 'display_dimension_v1' for row in page['items'])
            target = next(row for row in page['items'] if row['owner']['feature_type'] == 'Extrusion')
            assert not target['write_blockers']
            sketches = [row for row in page['items'] if row['owner']['feature_type'] == 'ProfileFeature']
            assert len(sketches) == 2
            assert all('sketch_geometry_snapshot_not_implemented' in row['write_blockers'] for row in sketches)
            initial_refs = {row['object_id'] for row in page['items']}
            assert succeeded(await call(client, 'dimension_list', **context))['revision'] == page['revision']
            short = succeeded(await call(client, 'dimension_list', **context, limit=1))
            paged_ids = [row['object_id'] for row in short['items']]
            while short['next_cursor']:
                short = succeeded(await call(client, 'dimension_list', **context, limit=1, cursor=short['next_cursor']))
                paged_ids.extend(row['object_id'] for row in short['items'])
            assert len(paged_ids) == 3 and set(paged_ids) == initial_refs
            args = {**context, 'object_id': target['object_id'], 'expected_revision': page['revision'],
                    'value': 9., 'unit': 'mm'}
            failed(await call(client, 'dimension_set_value', **{**args, 'document_id': other['document_id']}),
                   'object_reference_not_found')
            # Test inactive configuration independently of a foreign ID:
            # namespace rejection is intentionally earlier for mutations.
            failed(await call(client, 'dimension_list', document_id=other['document_id'],
                   configuration='Вариант'), 'configuration_not_active')
            failed(await call(client, 'dimension_set_value', **{**args, 'unit': 'deg'}), 'dimension_unit_mismatch')
            failed(await call(client, 'dimension_set_value', **{**args, 'unit': 'inch'}), 'invalid_dimension_unit')
            failed(await call(client, 'dimension_set_value', **{**args, 'value': -9.}), 'unsupported_signed_dimension')
            failed(await call(client, 'dimension_set_value', **{**args, 'object_id': sketches[0]['object_id']}),
                   'dimension_not_writable')
            await physical_proven(client, 7.)

            # Activate only another exact owned document, then restore our
            # owned target before any later setter/native physical reads.
            def activate_owned(title):
                activated, _ = sw.ActivateDoc3(title, False, 1, 0)
                assert activated is not None
            async with inactive_owned_document(client, cleanup,
                    lambda: activate_owned(titles[0]), lambda: activate_owned(titles[1])):
                failed(await call(client, 'dimension_set_value', **args), 'document_not_active')
            await physical_proven(client, 7.)
            fresh = succeeded(await call(client, 'dimension_list', **context))
            write_args = {**args, 'expected_revision': fresh['revision'],
                          'request_id': 'owned-native-dimension-depth', 'timeout_s': 0}
            pending = await response(client, 'dimension_set_value', write_args)
            repeated = await response(client, 'dimension_set_value', write_args)
            assert repeated['operation_id'] == pending['operation_id']
            finished = await terminal_job(client, pending['operation_id'])
            proof = succeeded(finished)
            assert proof['mutation']['phase'] == 'committed' and proof['result']['verified'] is True
            assert math.isclose(proof['mutation']['before_state']['value_si'], .007, abs_tol=1e-10)
            assert proof['mutation']['before_state']['_mutation_effect_scope'] == 'application'
            assert proof['result']['execution_guard'] == GUARD
            assert proof['mutation']['verification']['evidence']['execution_guard'] == GUARD
            assert proof['result']['value']['native_status'] == 0
            report['changed_geometry'] = await physical_proven(client, 9.)
            after = succeeded(await call(client, 'dimension_list', **context))
            assert {row['object_id'] for row in after['items']} == initial_refs
            readback = succeeded(await call(client, 'dimension_get', **context, object_id=target['object_id']))
            assert math.isclose(readback['dimension']['values']['Основная'], 9., abs_tol=1e-8)
            assert readback['dimension']['reference_anchor'] == target['reference_anchor']
            assert readback['dimension']['native_incarnation'] == target['native_incarnation']
            failed(await call(client, 'dimension_set_value', **{**args, 'value': 11.}), 'stale_revision')
            replay = await response(client, 'dimension_set_value', write_args)
            assert replay['operation_id'] == pending['operation_id']
            replay_job = await terminal_job(client, replay['operation_id'])
            assert succeeded(replay_job) == proof
            journal = succeeded(await response(client, 'job_list', {'limit': 1000}))
            assert journal['next_cursor'] is None
            matches = [job for job in journal['items'] if job['request_id'] == write_args['request_id']]
            assert len(matches) == 1 and matches[0]['operation_id'] == pending['operation_id']
            assert succeeded(await call(client, 'dimension_list', **context))['revision'] == after['revision']
            await physical_proven(client, 9.)
            report.update(package_version=info['package_version'], git_sha=info['build']['git_sha'],
                source_dirty=False, build_matches_source=True, solidworks_revision=original[0], tool_count=len(tools),
                timeout_zero_initial_status=pending['status'], native_status=0,
                compound_reference_survives_rebuild=True, sketch_dimensions_read_only=True,
                independent_geometry_verified=True, same_request_does_not_duplicate_write=True,
                stale_wrong_document_inactive_and_unit_errors_rejected=True,
                durable_application_checkpoint_and_guard_release=True)

        history = client.history_seed()

        # Restart validates durable proof without trying to resume/repeat COM.
        async with open_supervised_session(session_factory, tool_specs=TOOL_SPECS,
                journal_path=state / 'jobs.sqlite', trusted_history=history, readonly_restart=True) as client:
            cleanup.add(client)
            assert succeeded(await terminal_job(client, pending['operation_id'])) == proof
            reopened = succeeded(await call(client, 'document_list'))['documents']
            new_document = next(row for row in reopened if row['title'] == titles[1])
            assert new_document['document_id'] != context['document_id']
            failed(await call(client, 'dimension_get', **context, object_id=target['object_id']), 'document_not_open')
            new_page = succeeded(await call(client, 'dimension_list', document_id=new_document['document_id'],
                                            configuration='Основная'))
            assert initial_refs.isdisjoint({row['object_id'] for row in new_page['items']})
            failed(await call(client, 'dimension_get', document_id=new_document['document_id'],
                   configuration='Основная', object_id=target['object_id']), 'object_reference_not_found')
            await physical_proven(client, 9.)
        report.update(historical_job_survives_restart=True, restart_invalidates_document_and_dimension_ids=True)

    assert cleanup.can_cleanup(), 'Retain fixtures without original native baseline reads.'
    assert native_snapshot() == original
    assert ui_snapshot(sw, module) == original_ui
    assert application_preferences(sw) == original_preferences
    assert user_file_metadata(original) == original_files
    report.update(public_mcp_dimension_acceptance=True, original_document_baseline_restored=True,
                  original_preferences_and_ui_restored=True, actual_native_failure_or_rollback_tested_via_mcp=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--internal-report', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    private_root = Path(__file__).resolve().parent.parent / 'work'
    for path in (args.state_dir, args.internal_report, args.report):
        assert path.resolve().is_relative_to(private_root), 'Keep native journals/reports inside private work/.'
    assert not args.state_dir.exists() and not args.report.exists(), 'Use fresh private paths.'
    assert args.internal_report.is_file()
    args.state_dir.mkdir(parents=True)
    pythoncom.CoInitialize()
    try:
        result = asyncio.run(check(args.state_dir.resolve(), args.internal_report.resolve()))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
        print(json.dumps(result, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
