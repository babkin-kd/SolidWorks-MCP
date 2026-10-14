"""Feature acceptance owner/cleanup contracts isolated from CAD and SDK processes."""
import ast
from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import anyio
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts' / 'verify_feature_operations.py'
spec = importlib.util.spec_from_file_location('_feature_verifier_lifecycle', ROOT / 'scripts' / 'verifier_lifecycle.py')
lifecycle = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lifecycle
spec.loader.exec_module(lifecycle)


def extracted(names, **extra):
    tree = ast.parse(SOURCE.read_text(encoding='utf8'))
    selected = [node for node in tree.body if getattr(node, 'name', None) in names
                or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
    namespace = {'ToolSpec': lifecycle.ToolSpec, 'anyio': anyio, 'asynccontextmanager': asynccontextmanager,
                 'Path': Path, 'json': json, 'uuid': uuid, **extra}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


HELPERS = {'EXPECTED_TOOL_COUNT', 'FEATURE_TOOLS', 'TOOL_SPECS', 'SessionCleanupGate',
           'response', 'call', 'success', 'metadata_session', 'require_native_cleanup',
           'owned_native', 'owned_active_document'}
PROVENANCE = {'package_version': 'dev', 'git_sha': 'a' * 40, 'source_dirty': False,
              'installed_source_digest': 'digest', 'installed_build_matches_package': True}


def test_payload_defaults_context_and_exact_rename_request():
    specs = extracted(HELPERS)['TOOL_SPECS']
    base = {'request_id': 'r', 'timeout_s': 0, 'document_id': 'd', 'configuration': 'Основная'}
    assert specs['feature_list'].payload(base) == {
        'arguments': {'document_id': 'd', 'configuration': 'Основная', 'limit': 100, 'cursor': ''},
        'context': {'document_id': 'd', 'configuration': 'Основная'}, 'mutates': False}
    inputs = {**base, 'object_id': 'feature', 'expected_revision': 'rev', 'name': 'Основание механизма'}
    expected = {k: v for k, v in inputs.items() if k not in ('request_id', 'timeout_s')}
    assert specs['feature_rename'].payload(inputs) == {'arguments': expected,
        'context': {k: expected[k] for k in ('document_id', 'configuration', 'object_id', 'expected_revision')},
        'mutates': True}
    assert specs['feature_get'].payload({**base, 'object_id': 'feature'})['arguments'] == {
        'document_id': 'd', 'configuration': 'Основная', 'object_id': 'feature'}
    assert specs['document_list'].payload({'request_id': 'r'}) == {'arguments': {}, 'context': {}, 'mutates': False}


@pytest.mark.parametrize('change', [{}, {'source_dirty': True}, {'source_dirty': 0},
    {'git_sha': 'bad'}, {'git_sha': 'A' * 40}, {'source_digest': 'foreign'}, {'package_version': 'old'}])
def test_provenance_verifies_actual_clean_installed_files(change):
    build = {'package_version': 'dev', 'git_sha': 'a' * 40, 'source_dirty': False, 'source_digest': 'digest', **change}
    deps = {'solidworks_mcp': SimpleNamespace(__file__='C:/venv/site-packages/solidworks_mcp/__init__.py', __version__='dev'),
            'os': SimpleNamespace(environ={}), 'source_digest': lambda package: 'digest',
            'resources': SimpleNamespace(files=lambda package: SimpleNamespace(joinpath=lambda name:
                SimpleNamespace(read_text=lambda **kwargs: json.dumps(build))))}
    ns = extracted({'_provenance'}, **deps)
    if change:
        with pytest.raises(AssertionError):
            ns['_provenance']()
    else:
        assert ns['_provenance']() == PROVENANCE


@pytest.mark.parametrize('tool_count,bad_digest', [(18, False), (13, False), (18, True)])
def test_factory_metadata_gate_before_any_durable_tool_yield(tool_count, bad_digest):
    async def scenario():
        events, metadata = [], {}
        names = ['document_list', 'feature_list', 'feature_get', 'feature_rename']
        names += [f'other-{i}' for i in range(tool_count - len(names))]
        info = {'package_version': 'dev', 'source_digest': 'bad' if bad_digest else 'digest',
                'build_matches_source': True, 'build': {'git_sha': 'a' * 40, 'source_dirty': False, 'source_digest': 'digest'},
                'implemented_mutations': ['feature.rename', 'dimension.set_value', 'export.execute']}
        class Raw:
            async def initialize(self):
                events.append('initialize')
            async def call_tool(self, name, arguments):
                assert name == 'system_get_info' and arguments == {}
                events.append('info')
                return SimpleNamespace(isError=False, structuredContent={'status': 'succeeded', 'data': info})
            async def list_tools(self):
                events.append('tools')
                return SimpleNamespace(tools=[SimpleNamespace(name=n, outputSchema={'type': 'object'}) for n in names])
        @asynccontextmanager
        async def stdio(params):
            try:
                yield ('read', 'write')
            finally:
                events.append('stdio-exit')
        @asynccontextmanager
        async def session(read, write):
            yield Raw()
        ns = extracted(HELPERS, stdio_client=stdio, ClientSession=session)
        gate = ns['SessionCleanupGate']()
        async def run():
            async with ns['metadata_session']('params', PROVENANCE, metadata):
                assert events == ['initialize', 'info', 'tools']
                events.append('yielded')
        if tool_count == 13 or bad_digest:
            with pytest.raises(AssertionError):
                await run()
            assert not metadata and 'yielded' not in events
        else:
            await run()
            assert metadata['info'] == info
        assert gate.can_cleanup() and events[-1] == 'stdio-exit'
    anyio.run(scenario)


@pytest.mark.parametrize('state', ['running', 'unknown', 'succeeded-but-held', 'known', 'native-error'])
def test_native_callback_requires_fresh_proof_and_retains_independent_failure(state):
    async def scenario():
        ns = extracted(HELPERS)
        calls = []
        owner = SimpleNamespace(cleanup_gate=lifecycle.CleanupGate())
        owner.cleanup_gate.decision = lifecycle.CleanupDecision(True, True, ())  # Earlier proof.
        async def observe():
            calls.append('fresh-observation')
            owner.cleanup_gate.decision = lifecycle.CleanupDecision(state != 'running', state in ('known', 'native-error'), ())
            return owner.cleanup_gate.decision
        owner.observe_once = observe
        owner.retain = lambda reason: setattr(owner.cleanup_gate, 'decision', lifecycle.CleanupDecision(True, False, (reason,)))
        gate = ns['SessionCleanupGate']()
        gate.add(owner)
        original = AssertionError('independent native readback mismatch')
        def native():
            calls.append('native')
            if state == 'native-error':
                raise original
            return 42
        if state in ('running', 'unknown', 'succeeded-but-held'):
            with pytest.raises(RuntimeError):
                await ns['owned_native'](owner, gate, native)
            assert calls == ['fresh-observation']
        elif state == 'native-error':
            with pytest.raises(AssertionError) as raised:
                await ns['owned_native'](owner, gate, native)
            assert raised.value is original and not gate.can_cleanup()
        else:
            assert await ns['owned_native'](owner, gate, native) == 42
            assert calls == ['fresh-observation', 'native']
    anyio.run(scenario)


@pytest.mark.parametrize('terminal,restore_error', [('failed', False), ('unknown', False), ('lost-ack', False), ('failed', True)])
def test_owned_activation_exception_drains_before_optional_restore_and_preserves_error(terminal, restore_error):
    async def scenario():
        ns = extracted(HELPERS)
        events, rows = [], []
        specs = ns['TOOL_SPECS']
        args = {'request_id': 'delete-read', 'document_id': 'd', 'configuration': 'Основная', 'object_id': 'feature'}
        original = OSError('lost acknowledgement') if terminal == 'lost-ack' else AssertionError('assertion after dispatch')
        class Raw:
            async def call_tool(self, name, arguments):
                assert name == 'feature_get'
                events.append('dispatch')
                rows.append({'operation_id': 'delete-op', 'request_id': args['request_id'], 'operation': 'feature.get',
                    'payload': specs[name].payload(arguments), 'status': 'running', 'result': None,
                    'error': None, 'mutation': None, 'created_at': 1.})
                if terminal == 'lost-ack':
                    raise original
                return SimpleNamespace(isError=False, structuredContent={'status': 'running', 'operation_id': 'delete-op'})
        def hold(decision):
            events.append('drain')
            rows[-1].update(status='unknown' if terminal == 'unknown' else 'failed',
                error={'code': 'object_deleted', 'requires_reconciliation': terminal == 'unknown'})
        owner = lifecycle.VerifierSupervisor(Raw(), tool_specs=specs, journal_reader=lambda: deepcopy(rows), on_hold=hold)
        gate = ns['SessionCleanupGate']()
        gate.add(owner)
        async with owner.inside_live_session():
            # Establish a coherent completed read before owned activation.
            read_args = {'request_id': 'initial-read'}
            owner.requests['initial-read'] = lifecycle.TrackedRequest('document_list', 'initial-read', read_args,
                specs['document_list'], specs['document_list'].payload(read_args), operation_id='initial-op')
            rows.append({'operation_id': 'initial-op', 'request_id': 'initial-read', 'operation': 'document.list',
                'payload': specs['document_list'].payload(read_args), 'status': 'succeeded', 'result': {},
                'error': None, 'mutation': None, 'created_at': 0.})
            def restore():
                assert gate.can_cleanup() and rows[-1]['status'] != 'running'
                events.append('restore')
                if restore_error:
                    raise RuntimeError('restoration failed')
            with pytest.raises(type(original)) as raised:
                async with ns['owned_active_document'](owner, gate, lambda: events.append('activate'), restore):
                    await owner.call_tool('feature_get', args)
                    raise original
            assert raised.value is original
        assert events == ['activate', 'dispatch', 'drain'] + (['restore'] if terminal == 'failed' else [])
        assert gate.can_cleanup() is (terminal == 'failed' and not restore_error)
        if restore_error:
            assert original.__notes__ and 'restoration failed' in original.__notes__[0]
    anyio.run(scenario)


def test_provenance_failure_stops_actual_check_before_first_native_getter():
    async def scenario():
        calls = []
        original = AssertionError('dirty wheel')
        def provenance():
            raise original
        ns = extracted({'check'}, _provenance=provenance, native_snapshot=lambda: calls.append('CAD'))
        with pytest.raises(AssertionError) as raised:
            await ns['check'](Path('unused'))
        assert raised.value is original and not calls
    anyio.run(scenario)


def test_actual_check_unknown_read_retains_fixtures_without_later_native_getters():
    async def scenario():
        trace, rows = [], []
        held = False
        def native(name, value=None):
            assert not held, f'Unexpected native getter {name} after unknown'
            trace.append(name)
            return value
        class Model:
            def __init__(self, title):
                self.title = title
            def GetTitle(self):
                return native('title', self.title)
            def GetPathName(self):
                return native('path', '')
        class Feature:
            @property
            def Name(self):
                return native('name', 'Контрольный блок 1')
            def GetID(self):
                return native('id', 42)
        @contextmanager
        def fixtures(*, cleanup_gate):
            try:
                yield (None, [Model('A'), Model('B')], None)
            finally:
                trace.append(('fixture-cleanup', cleanup_gate()))
        class Raw:
            async def call_tool(self, name, arguments):
                nonlocal held
                if name == 'document_list':
                    result = {'documents': [{'title': 'A', 'document_id': 'doc-a'}, {'title': 'B', 'document_id': 'doc-b'}]}
                    status = 'succeeded'
                else:
                    assert name == 'feature_list'
                    held, result, status = True, None, 'unknown'
                    trace.append('unknown-dispatch')
                request = owner.requests[arguments['request_id']]
                row = {'operation_id': f'op-{len(rows)}', 'request_id': arguments['request_id'],
                    'operation': request.spec.operation, 'payload': request.payload, 'status': status,
                    'result': result, 'error': None, 'mutation': None, 'created_at': float(len(rows))}
                rows.append(row)
                return SimpleNamespace(isError=False, structuredContent={'status': status, 'operation_id': row['operation_id'],
                    'data': result, 'error': None})
        @asynccontextmanager
        async def factory():
            try:
                yield Raw()
            finally:
                trace.append('sdk-exit')
        @asynccontextmanager
        async def supervised(unused_factory, **kwargs):
            nonlocal owner
            kwargs.pop('journal_path')
            async with lifecycle.open_supervised_session(factory, journal_reader=lambda: deepcopy(rows), **kwargs) as owner:
                try:
                    yield owner
                finally:
                    trace.append('body-end')
        owner = None
        ns = extracted(HELPERS | {'check'}, _provenance=lambda: dict(PROVENANCE),
            native_snapshot=lambda: native('snapshot', ('sw', None, 'active', ())),
            ui_snapshot=lambda *args: native('ui', {}), application_preferences=lambda *args: native('prefs', {}),
            user_file_metadata=lambda *args: native('files', {}), native_features=lambda *args: native('features', [Feature()]),
            binding=SimpleNamespace(connect=lambda **kwargs: object(), module=lambda: object()), fixtures=fixtures,
            StdioServerParameters=lambda **kwargs: object(), sys=SimpleNamespace(executable='C:/env/python.exe'),
            open_supervised_session=supervised)
        # The owner factory has already checked metadata in production; this
        # isolated hook supplies the same metadata without creating SDK objects.
        ns['metadata_session'] = lambda *args: None
        original_supervised = supervised
        @asynccontextmanager
        async def with_metadata(factory_argument, **kwargs):
            for cell in factory_argument.__closure__:
                if isinstance(cell.cell_contents, dict) and cell.cell_contents == {}:
                    cell.cell_contents.update(info={'package_version': 'dev'}, tools=[])
            async with original_supervised(factory_argument, **kwargs) as current:
                yield current
        ns['open_supervised_session'] = with_metadata
        with pytest.raises(AssertionError):
            await ns['check'](Path('unused'))
        assert trace[trace.index('unknown-dispatch') + 1:] == ['body-end', 'sdk-exit', ('fixture-cleanup', False)]
        assert owner.cleanup_gate.decision.child_can_close and not owner.cleanup_gate.can_cleanup()
    anyio.run(scenario)


def test_source_flow_preserves_feature_checks_while_owning_two_sdk_lifetimes():
    tree = ast.parse(SOURCE.read_text(encoding='utf8'))
    check = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'check')
    calls = [node for node in ast.walk(check) if isinstance(node, ast.Call)]
    name = lambda node: node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
    assert not any(name(node) in ('stdio_client', 'ClientSession', 'call_tool', 'fail_after') for node in calls)
    owners = sorted([node for node in calls if name(node) == 'open_supervised_session'], key=lambda n: n.lineno)
    assert len(owners) == 2
    assert next(k.value.value for k in owners[1].keywords if k.arg == 'readonly_restart') is True
    assert next(k.value.id for k in owners[1].keywords if k.arg == 'trusted_history') == 'history'
    assert len([node for node in calls if name(node) == 'add']) == 2
    history = next(node for node in ast.walk(check) if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'history' for t in node.targets))
    first_scope = next(node for node in ast.walk(check) if isinstance(node, ast.AsyncWith)
        and any(item.context_expr is owners[0] for item in node.items))
    assert not any(node is history for node in ast.walk(first_scope))
    assert history.lineno < owners[1].lineno
    guarded_names = {node.args[2].id for node in calls if name(node) == 'owned_native' and isinstance(node.args[2], ast.Name)}
    assert guarded_names == {'verify_initial', 'manual_edit', 'verify_manual_name', 'verify_rename',
                             'verify_other_document', 'delete_owned_feature'}
    constants = {node.value for node in ast.walk(check) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert {'part_feature_tree_v1', 'invalid_russian_name', 'feature_name_conflict', 'stale_revision',
        'object_reference_not_found', 'configuration_not_active', 'object_deleted', 'object_reference_invalid',
        'feature_not_current', 'application', 'committed', 'original_state', 'locked_state', 'released_state'} <= constants
