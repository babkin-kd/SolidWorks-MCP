"""Pure lifecycle regressions: AST isolate the verifier; never import CAD or verifier modules."""
import ast
import asyncio
from contextlib import asynccontextmanager, contextmanager, ExitStack
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid
from types import SimpleNamespace

import anyio
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verifier_lifecycle import ToolSpec, VerifierSupervisor, open_supervised_session

SOURCE = ROOT / 'scripts/verify_export_operations.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf8'))


def definitions(*names, extra=None):
    nodes = [deepcopy(node) for node in TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names]
    namespace = {'anyio': anyio, 'asynccontextmanager': asynccontextmanager, 'json': json,
                 'Path': Path, 'ToolSpec': ToolSpec, **(extra or {})}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(SOURCE), 'exec'), namespace)
    return namespace


PROVENANCE = {'package_version': 'version', 'git_sha': 'a' * 40, 'installed_source_digest': 'b' * 64}


def internal_report():
    report = {**PROVENANCE, 'source_dirty': False, 'owned_fixture_cleanup_retained': False,
        'actual_native_export_count': 5, 'saveas_attempt_count': 5, 'independently_confirmed_export_count': 5,
        'retained_empty_staging_directories_count': 0}
    for key in ('installed_build_matches_package', 'internal_native_export_acceptance',
        'full_supported_source_snapshot_unchanged', 'global_preferences_restored',
        'ui_guard_and_selection_restored', 'original_user_document_baseline_restored',
        'original_user_file_metadata_unchanged', 'journal_reopen_retains_committed_results',
        'committed_request_after_reopen_does_not_dispatch', 'owned_fixture_cleanup_allowed',
        'retained_staging_cleanup_independently_verified'):
        report[key] = True
    report['native_internal_exports'] = [{'format': format, 'requested_units': units,
        'durable_application_checkpoint_and_ui_guard': True, 'same_request_does_not_replay': True,
        'analytical_geometry_scope': 'planar_polyhedral_brep_v1', 'revision_scope': 'part_solid_brep_export_v1',
        'staging_cleanup_verified': True, 'staging_cleanup_status': 'removed'}
        for format, units in [('stl', 'mm'), ('stl', 'm'), ('stl', 'in'), ('step', ''), ('parasolid', '')]]
    return report


def test_same_wheel_internal_gate_accepts_existing_success_contract_without_invented_accepted_key():
    definitions('_require_internal_acceptance')['_require_internal_acceptance'](internal_report(), PROVENANCE)


@pytest.mark.parametrize('key,bad', [(key, 'other') for key in PROVENANCE] + [
    ('source_dirty', True), ('internal_native_export_acceptance', False), ('accepted', False),
    ('saveas_attempt_count', True), ('actual_native_export_count', 4), ('owned_fixture_cleanup_retained', True),
    ('original_user_document_baseline_restored', False), ('ui_guard_and_selection_restored', False),
    ('retained_staging_cleanup_independently_verified', False),
    ('retained_empty_staging_directories_count', True), ('retained_empty_staging_directories_count', 1)])
def test_same_wheel_gate_rejects_historical_dirty_failed_incomplete_reports(key, bad):
    report = internal_report()
    report[key] = bad
    with pytest.raises(AssertionError):
        definitions('_require_internal_acceptance')['_require_internal_acceptance'](report, PROVENANCE)


@pytest.mark.parametrize('fault', ['missing_format', 'wrong_units', 'different_geometry', 'missing_guard'])
def test_internal_gate_requires_all_five_supported_formats_and_actual_guards(fault):
    report = internal_report()
    if fault == 'missing_format':
        report['native_internal_exports'].pop()
    elif fault == 'wrong_units':
        report['native_internal_exports'][0]['requested_units'] = 'm'
    elif fault == 'different_geometry':
        report['native_internal_exports'][0]['analytical_geometry_scope'] = 'opaque_bytes'
    else:
        report['native_internal_exports'][0]['durable_application_checkpoint_and_ui_guard'] = False
    with pytest.raises(AssertionError):
        definitions('_require_internal_acceptance')['_require_internal_acceptance'](report, PROVENANCE)


def test_export_specs_match_domain_payload_and_stale_prewrite_outcome_only():
    node = next(node for node in TREE.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'TOOL_SPECS' for target in node.targets))
    namespace = {'ToolSpec': ToolSpec}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    specs = namespace['TOOL_SPECS']
    args = {'request_id': 'r', 'document_id': 'd', 'configuration': 'c', 'file_format': 'stl',
            'filename': 'f.stl', 'expected_revision': 'rev', 'units': 'mm', 'timeout_s': 0}
    payload = specs['export_part'].payload(args)
    assert payload == {'arguments': {'document_id': 'd', 'configuration': 'c', 'format': 'stl',
        'filename': 'f.stl', 'expected_revision': 'rev', 'units': 'mm'},
        'context': {'document_id': 'd', 'configuration': 'c', 'expected_revision': 'rev'}, 'mutates': True}
    assert specs['export_part'].prewrite_failure_codes == frozenset({'stale_revision'})
    assert specs['export_prepare'].operation == 'export.prepare' and specs['export_prepare'].mutates is False
    assert specs['export_prepare'].payload({'file_format': 'step', 'filename': 'f.step'})['arguments']['units'] == ''


@pytest.mark.parametrize('fault', ['none', 'source_dirty', 'different_build', 'different_digest', 'missing_tool',
                                  'missing_output_configuration', 'output_not_configured'])
def test_real_metadata_factory_checks_child_wheel_and_schemas_without_cad_dispatch(fault):
    events, metadata = [], {}
    info = {'build_matches_source': True, 'package_version': 'version',
        'build': {'source_dirty': False, 'git_sha': 'a' * 40, 'source_digest': 'b' * 64},
        'source_digest': 'b' * 64, 'implemented_mutations': ['export.execute'], 'export_output_configured': True}
    tools = [SimpleNamespace(name=name, outputSchema={'type': 'object'})
             for name in ('export_prepare', 'export_part', 'document_list', 'job_get')]
    if fault == 'source_dirty':
        info['build']['source_dirty'] = True
    elif fault == 'different_build':
        info['build']['git_sha'] = 'c' * 40
    elif fault == 'different_digest':
        info['source_digest'] = 'c' * 64
    elif fault == 'missing_tool':
        tools.pop(0)
    elif fault == 'missing_output_configuration':
        info.pop('export_output_configured')
    elif fault == 'output_not_configured':
        info['export_output_configured'] = False
    class Raw:
        async def initialize(self):
            events.append('initialize')
        async def call_tool(self, tool, arguments):
            assert tool == 'system_get_info' and arguments == {}, 'No durable/CAD call from factory'
            events.append(tool)
            return SimpleNamespace(structuredContent={'status': 'succeeded', 'operation_id': None,
                'context': {}, 'data': info, 'error': None, 'diagnostics': []})
        async def list_tools(self):
            events.append('list_tools')
            return SimpleNamespace(tools=tools)
    @asynccontextmanager
    async def transport(params):
        events.append('transport-enter')
        try:
            yield None, None
        finally:
            events.append('transport-exit')
    @asynccontextmanager
    async def session(read, write):
        yield Raw()
    namespace = definitions('metadata_session', 'settle', 'succeeded', extra={
        'stdio_client': transport, 'ClientSession': session,
        'TOOLS': {'export_prepare', 'export_part', 'document_list', 'job_get'}})
    async def run():
        if fault == 'none':
            async with namespace['metadata_session'](None, PROVENANCE, metadata) as raw:
                assert metadata == {'info': info, 'tools': tools}
        else:
            with pytest.raises(AssertionError):
                async with namespace['metadata_session'](None, PROVENANCE, metadata):
                    pytest.fail('A mismatched/unpublished wheel must not reach supervisor/CAD')
            assert metadata == {}
    asyncio.run(run())
    assert events[0] == 'transport-enter' and events[-1] == 'transport-exit'
    assert events.count('system_get_info') == 1


def owner(allowed=True):
    states = {'allowed': allowed}
    async def observe():
        return SimpleNamespace(child_can_close=states['allowed'])
    def retain(reason):
        states['allowed'] = False
    return SimpleNamespace(observe_once=observe, retain=retain,
                           cleanup_gate=SimpleNamespace(can_cleanup=lambda: states['allowed']))


@pytest.mark.parametrize('allowed', [False, True])
def test_native_action_observes_fresh_proof_before_every_direct_group(allowed):
    controls = definitions('SessionCleanupGate', 'require_native_cleanup', 'native_action')
    aggregate, current, events = controls['SessionCleanupGate'](), owner(allowed), []
    aggregate.add(current)
    async def run():
        if allowed:
            assert await controls['native_action'](current, aggregate, lambda: events.append('native')) is None
            current.retain('late external unresolved effect')
        with pytest.raises(RuntimeError):
            await controls['native_action'](current, aggregate, lambda: events.append('unsafe'))
    asyncio.run(run())
    assert events == (['native'] if allowed else [])


def test_independent_readback_error_sticky_retains_and_preserves_primary():
    controls = definitions('SessionCleanupGate', 'require_native_cleanup', 'native_action')
    aggregate, current, original = controls['SessionCleanupGate'](), owner(), ValueError('strict mismatch')
    aggregate.add(current)
    def fail():
        raise original
    async def run():
        with pytest.raises(ValueError) as error:
            await controls['native_action'](current, aggregate, fail)
        assert error.value is original and aggregate.can_cleanup() is False
    asyncio.run(run())


class FakePath:
    parents = ()
    def __init__(self, label, report=None):
        self.label, self.report = label, report
    def __str__(self):
        return self.label
    def resolve(self):
        return self
    def exists(self):
        return False
    def mkdir(self, **kwargs):
        pass
    def __truediv__(self, child):
        return FakePath(self.label + '/' + child)
    def read_text(self, **kwargs):
        return json.dumps(self.report)


@pytest.mark.parametrize('fault', ['none', 'body_known_failure', 'body_unknown', 'sdk_shutdown'])
def test_actual_proposal_context_order_drains_and_exits_sdk_before_gate_controlled_fixture_cleanup(fault):
    controls = definitions('SessionCleanupGate', 'require_native_cleanup')
    current, events, facts = owner(), [], {}
    original = RuntimeError('primary body failure')
    @asynccontextmanager
    async def supervised(factory, **kwargs):
        await factory()  # Metadata-only fake, before any native snapshot/fixture.
        events.append('sdk-enter')
        try:
            yield current
        finally:
            events.append('sdk-exit')
            if fault == 'sdk_shutdown':
                current.retain('SDK shutdown unconfirmed')
                raise original
    @contextmanager
    def fixture(*, cleanup_gate):
        events.append('fixture-enter')
        try:
            yield None, [object(), object()], None
        finally:
            events.append(('fixture-cleanup', cleanup_gate()))
    async def run_body(body, **kwargs):
        assert kwargs == {}
        events.append('body')
        if fault.startswith('body_'):
            if fault == 'body_unknown':
                current.retain('terminal unknown')
            raise original
    async def drain():
        events.append('drain')
    async def metadata(params, provenance, destination):
        events.append('metadata')
        destination.update(info={}, tools=[])
    current.run_body, current.drain = run_body, drain
    async def initial_read(*args):
        events.append('tracked-preflight-read')
        return {'status': 'succeeded', 'data': {'documents': []}}
    def baseline():
        assert current.cleanup_gate.can_cleanup(), 'No native read after unknown/shutdown hold'
        events.append('native-snapshot')
        return ('baseline',)
    namespace = {'_provenance': lambda: PROVENANCE, '_require_internal_acceptance':
        definitions('_require_internal_acceptance')['_require_internal_acceptance'],
        'json': json, 'sys': sys, 'Path': Path, 'ExitStack': ExitStack, 'uuid': uuid,
        'settle': initial_read, 'succeeded': lambda value: value['data'],
        'StdioServerParameters': lambda **kwargs: kwargs, 'TOOL_SPECS': {},
        'SessionCleanupGate': controls['SessionCleanupGate'], 'metadata_session': metadata,
        'open_supervised_session': supervised, 'require_native_cleanup': controls['require_native_cleanup'],
        'native_snapshot': baseline, 'binding': SimpleNamespace(connect=lambda **kwargs: None, module=lambda: None),
        'application_preferences': lambda sw: {}, 'ui_snapshot': lambda *args: [],
        'user_file_metadata': lambda state: {}, 'fixtures': fixture,
        'capture_ui_difference': lambda reader, before, report, field: reader(),
        'ui_snapshot_unmeasured': lambda before: {'after_snapshot_read': False}}
    check = deepcopy(next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'check'))
    body = next(node for node in ast.walk(check) if isinstance(node, ast.AsyncFunctionDef) and node.name == 'body')
    body.body = ast.parse('pass').body  # Native checks already separately tested; retain real ownership scopes.
    exec(compile(ast.fix_missing_locations(ast.Module(body=[check], type_ignores=[])), str(SOURCE), 'exec'), namespace)
    async def run():
        if fault == 'none':
            result = await namespace['check'](FakePath('state'), FakePath('output'),
                        FakePath('internal', internal_report()), failure_report=facts)
            assert result['public_mcp_export_acceptance'] is True
        else:
            with pytest.raises(RuntimeError) as error:
                await namespace['check'](FakePath('state'), FakePath('output'),
                        FakePath('internal', internal_report()), failure_report=facts)
            assert error.value is original and facts['public_mcp_export_acceptance'] is False
    asyncio.run(run())
    assert events.index('metadata') < events.index('native-snapshot') < events.index('fixture-enter')
    assert events.index('drain') < events.index('sdk-exit') < next(
        index for index, event in enumerate(events) if isinstance(event, tuple))
    held = fault in ('body_unknown', 'sdk_shutdown')
    assert ('fixture-cleanup', not held) in events
    if held:
        assert events.count('native-snapshot') == 1
        assert facts['owned_fixture_cleanup_retained_count'] == 2
        assert facts['original_ui_snapshot_unmeasured']['after_snapshot_read'] is False


def test_same_wheel_rejection_occurs_before_metadata_sdk_or_any_native_reader():
    namespace = definitions('check', '_require_internal_acceptance', extra={
        '_provenance': lambda: PROVENANCE, 'native_snapshot': lambda: pytest.fail('No native read'),
        'metadata_session': lambda *args: pytest.fail('No SDK')})
    report = internal_report()
    report['git_sha'] = 'c' * 40
    with pytest.raises(AssertionError):
        asyncio.run(namespace['check'](None, None, FakePath('internal', report)))


def test_actual_supervisor_initial_tracked_read_precedes_native_and_proves_empty_journal_is_not_enough(monkeypatch):
    events, rows = [], []
    original_drain = VerifierSupervisor.drain
    async def guarded_real_drain(self):
        # Fail quickly on the historical empty-tracker bug rather than hanging
        # a test in its intentionally unbounded drain. All actual policy remains.
        assert self.requests, 'Empty tracker cannot drain or authorize fixture cleanup'
        return await original_drain(self)
    monkeypatch.setattr(VerifierSupervisor, 'drain', guarded_real_drain)
    class Client:
        async def call_tool(self, name, arguments):
            assert name == 'document_list'
            events.append('tracked-read')
            rows.append({'request_id': arguments['request_id'], 'operation_id': 'preflight-job',
                'operation': 'document.list', 'payload': {'arguments': {}, 'context': {}, 'mutates': False},
                'status': 'succeeded', 'result': {'documents': []}, 'error': None,
                'created_at': 1., 'mutation': None})
            return SimpleNamespace(structuredContent={'status': 'succeeded', 'operation_id': 'preflight-job',
                'context': {}, 'data': {'documents': []}, 'error': None, 'diagnostics': []})
    @asynccontextmanager
    async def metadata(params, provenance, destination):
        events.append('metadata')
        destination.update(info={}, tools=[])
        try:
            yield Client()
        finally:
            events.append('sdk-exit')
    @asynccontextmanager
    async def supervised(factory, **kwargs):
        kwargs.pop('journal_path')
        async with open_supervised_session(factory, journal_reader=lambda: deepcopy(rows),
                poll_interval=.001, **kwargs) as supervisor:
            # Initial journal is empty, but tracker is not yet dispatch proof.
            initial = await supervisor.observe_once()
            assert initial.child_can_close is False and initial.fixture_can_cleanup is False
            yield supervisor
    @contextmanager
    def fixtures(*, cleanup_gate):
        events.append('fixtures')
        try:
            yield None, [object(), object()], None
        finally:
            assert cleanup_gate() is True
            events.append('fixture-cleanup')
    def native_read():
        assert rows and rows[0]['request_id'].startswith('export-preflight-')
        events.append('native-read')
        return ('baseline',)
    controls = definitions('SessionCleanupGate', 'require_native_cleanup', 'settle', 'succeeded', '_require_internal_acceptance')
    namespace = {**controls, '_provenance': lambda: PROVENANCE, 'sys': sys, 'uuid': uuid,
        'ExitStack': ExitStack, 'StdioServerParameters': lambda **kwargs: kwargs,
        'TOOL_SPECS': {'document_list': ToolSpec('document.list', False)},
        'metadata_session': metadata, 'open_supervised_session': supervised,
        'native_snapshot': native_read, 'binding': SimpleNamespace(connect=lambda **kwargs: None, module=lambda: None),
        'application_preferences': lambda *args: {}, 'ui_snapshot': lambda *args: [],
        'user_file_metadata': lambda *args: {}, 'fixtures': fixtures,
        'capture_ui_difference': lambda reader, before, report, field: reader()}
    check = deepcopy(next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'check'))
    body = next(node for node in ast.walk(check) if isinstance(node, ast.AsyncFunctionDef) and node.name == 'body')
    body.body = ast.parse('pass').body
    exec(compile(ast.fix_missing_locations(ast.Module(body=[check], type_ignores=[])), str(SOURCE), 'exec'), namespace)
    result = asyncio.run(namespace['check'](FakePath('state'), FakePath('output'), FakePath('report', internal_report())))
    assert result['public_mcp_export_acceptance'] is True  # Fake context proof, no CAD acceptance.
    assert events.index('metadata') < events.index('tracked-read') < events.index('native-read') < events.index('fixtures')
    assert events.index('sdk-exit') < events.index('fixture-cleanup')
    assert len(rows) == 1 and events.count('tracked-read') == 1
