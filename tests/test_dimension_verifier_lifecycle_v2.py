"""Actual verifier functions isolated by AST; no CAD imports, SDK or processes."""
import ast
from contextlib import asynccontextmanager
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import anyio
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_helper(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lifecycle = load_helper('verifier_lifecycle')
inline = load_helper('verifier_fixture_cleanup')


def extracted(script, names, dependencies):
    tree = ast.parse((ROOT / 'scripts' / script).read_text(encoding='utf8'))
    selected = [node for node in tree.body if getattr(node, 'name', None) in names
                or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
    namespace = dict(dependencies)
    exec(compile(ast.Module(body=selected, type_ignores=[]), script, 'exec'), namespace)
    return namespace


PUBLIC_NAMES = {'TOOL_SPECS', 'TOOLS', 'SessionCleanupGate', 'metadata_session',
                'require_native_cleanup', 'inactive_owned_document', 'response', 'succeeded'}


def public(**extra):
    return extracted('verify_dimension_mcp.py', PUBLIC_NAMES,
        {'ToolSpec': lifecycle.ToolSpec, 'anyio': anyio, 'asynccontextmanager': asynccontextmanager, **extra})


def test_payload_schema_defaults_strict_numeric_normalization_and_context_are_exact():
    specs = public()['TOOL_SPECS']
    base = {'request_id': 'r', 'timeout_s': 0, 'document_id': 'd', 'configuration': 'Основная'}
    expected = {'document_id': 'd', 'configuration': 'Основная', 'limit': 100, 'cursor': ''}
    assert specs['dimension_list'].payload(base) == {
        'arguments': expected, 'context': {'document_id': 'd', 'configuration': 'Основная'}, 'mutates': False}
    inputs = {**base, 'object_id': 'dim', 'expected_revision': 'rev', 'value': 9, 'unit': 'mm'}
    payload = specs['dimension_set_value'].payload(inputs)
    assert type(payload['arguments']['value']) is float and payload['arguments']['value'] == 9.
    assert payload['context'] == {k: inputs[k] for k in ('document_id', 'configuration', 'object_id', 'expected_revision')}
    for value in (True, '9'):
        assert type(specs['dimension_set_value'].payload({**inputs, 'value': value})['arguments']['value']) is type(value)
    assert specs['document_list'].payload({'request_id': 'r'}) == {'arguments': {}, 'context': {}, 'mutates': False}


@pytest.mark.parametrize('fail_metadata', [False, True])
def test_factory_only_metadata_before_yield_and_fixture_gate_allows_metadata_failure(fail_metadata):
    async def scenario():
        events, metadata = [], {}
        provenance = {'package_version': 'dev', 'git_sha': 'a' * 40, 'installed_source_digest': 'digest'}
        info = {'build_matches_source': True, 'package_version': 'dev', 'source_digest': 'digest',
                'build': {'git_sha': 'a' * 40, 'source_dirty': False, 'source_digest': 'digest'},
                'implemented_mutations': ['dimension.set_value']}
        class Raw:
            async def initialize(self):
                events.append('initialize')
            async def call_tool(self, name, arguments):
                assert name == 'system_get_info' and arguments == {}
                events.append('info')
                if fail_metadata:
                    raise OSError('metadata unavailable')
                return SimpleNamespace(isError=False, structuredContent={'status': 'succeeded', 'data': info})
            async def list_tools(self):
                events.append('tools')
                return SimpleNamespace(tools=[SimpleNamespace(name=n, outputSchema={'type': 'object'})
                                               for n in ('dimension_list', 'dimension_get', 'dimension_set_value')])
        @asynccontextmanager
        async def stdio(params):
            events.append('stdio-enter')
            try:
                yield ('read', 'write')
            finally:
                events.append('stdio-exit')
        @asynccontextmanager
        async def session(read, write):
            assert (read, write) == ('read', 'write')
            yield Raw()
        ns = public(stdio_client=stdio, ClientSession=session)
        gate = ns['SessionCleanupGate']()
        async def run():
            async with ns['metadata_session']('params', provenance, metadata):
                assert events == ['stdio-enter', 'initialize', 'info', 'tools']
                events.append('yielded')
        if fail_metadata:
            with pytest.raises(OSError):
                await run()
            assert not metadata and 'yielded' not in events
        else:
            await run()
            assert metadata['info'] == info
        assert gate.can_cleanup() and events[-1] == 'stdio-exit'
        owner = SimpleNamespace(cleanup_gate=lifecycle.CleanupGate())
        gate.add(owner)
        assert not gate.can_cleanup()
    anyio.run(scenario)


@pytest.mark.parametrize('outcome', ['normal', 'assertion-running', 'lost-ack', 'unknown'])
def test_inactive_activation_is_restored_only_after_fresh_coherent_drain(outcome):
    async def scenario():
        ns = public()
        events, rows = [], []
        specs = ns['TOOL_SPECS']
        args = {'request_id': 'change', 'document_id': 'd', 'configuration': 'Основная',
                'object_id': 'dim', 'expected_revision': 'rev', 'value': 9, 'unit': 'mm'}
        row = {'operation_id': 'op', 'request_id': 'change', 'operation': 'dimension.set_value',
               'payload': specs['dimension_set_value'].payload(args), 'status': 'running',
               'result': None, 'error': None, 'mutation': None, 'created_at': 1.}
        original = AssertionError('post-dispatch assertion')
        class Raw:
            async def call_tool(self, name, arguments):
                events.append('dispatch')
                assert not owner.cleanup_gate.can_cleanup()
                if outcome == 'lost-ack':
                    rows.clear()
                    raise OSError('lost acknowledgement')
                rows[:] = [deepcopy(row)]
                if outcome == 'normal':
                    finish()
                return SimpleNamespace(structuredContent={'status': 'running', 'operation_id': 'op'})
        def finish():
            if not rows:
                rows[:] = [deepcopy(row)]
            current = rows[0]
            if outcome == 'unknown':
                current.update(status='unknown', error={'requires_reconciliation': True})
                current['mutation'] = {'phase': 'unresolved', 'before_state': {}, 'verification': {}}
            else:
                current.update(status='failed', error={'code': 'document_not_active', 'requires_reconciliation': False})
        def hold(decision):
            events.append('drain-pending')
            finish()
        owner = lifecycle.VerifierSupervisor(Raw(), tool_specs=specs, journal_reader=lambda: deepcopy(rows),
            on_hold=hold, poll_interval=.001)
        gate = ns['SessionCleanupGate']()
        gate.add(owner)
        # Establish an initial tracked read before owned activation.
        owner.requests['read'] = lifecycle.TrackedRequest('document_list', 'read', {'request_id': 'read'},
            specs['document_list'], specs['document_list'].payload({'request_id': 'read'}), operation_id='read-op')
        read = {'operation_id': 'read-op', 'request_id': 'read', 'operation': 'document.list',
                'payload': specs['document_list'].payload({'request_id': 'read'}), 'status': 'succeeded',
                'result': {}, 'error': None, 'mutation': None, 'created_at': 0.}
        # Fresh snapshot was empty before the fixture's first tracked read.
        owner._entered = True
        owner._fresh = True
        original_finish = finish
        def finish():
            original_finish()
            if not any(item['operation_id'] == 'read-op' for item in rows):
                rows.append(read)
        rows[:] = [read]
        def activate():
            assert owner.cleanup_gate.can_cleanup()
            events.append('activate-other')
        def restore():
            assert owner.cleanup_gate.can_cleanup() and all(item['status'] != 'running' for item in rows)
            events.append('restore-target')
        async def run():
            async with ns['inactive_owned_document'](owner, gate, activate, restore):
                await owner.call_tool('dimension_set_value', args)
                if outcome != 'normal':
                    raise original
        try:
            if outcome == 'normal':
                await run()
            elif outcome == 'lost-ack':
                with pytest.raises(OSError):
                    await run()
            else:
                with pytest.raises(AssertionError) as raised:
                    await run()
                assert raised.value is original
            assert ('restore-target' in events) is (outcome in ('normal', 'assertion-running'))
            if outcome == 'assertion-running':
                assert events.index('drain-pending') < events.index('restore-target')
            if outcome in ('lost-ack', 'unknown'):
                assert not gate.can_cleanup()
        finally:
            finish()
            await owner.drain()
    anyio.run(scenario)


def test_fresh_hold_prevents_native_callback_even_after_prior_gate_true():
    async def scenario():
        ns = public()
        owner = SimpleNamespace(cleanup_gate=lifecycle.CleanupGate())
        owner.cleanup_gate.decision = lifecycle.CleanupDecision(True, True, ())
        async def observe():
            owner.cleanup_gate.decision = lifecycle.CleanupDecision(False, False, ('running',))
            return owner.cleanup_gate.decision
        owner.observe_once = observe
        gate = ns['SessionCleanupGate']()
        gate.add(owner)
        callbacks = []
        with pytest.raises(RuntimeError):
            async with ns['inactive_owned_document'](owner, gate,
                    lambda: callbacks.append('activate'), lambda: callbacks.append('restore')):
                pytest.fail('Held owner must not enter native test body')
        assert not callbacks
    anyio.run(scenario)


def test_public_source_has_two_supervised_owners_and_readonly_exact_history_restart():
    tree = ast.parse((ROOT / 'scripts' / 'verify_dimension_mcp.py').read_text(encoding='utf8'))
    check = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'check')
    names = lambda node: node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
    calls = [node for node in ast.walk(check) if isinstance(node, ast.Call)]
    owners = [node for node in calls if names(node) == 'open_supervised_session']
    assert len(owners) == 2
    assert not any(names(node) in ('stdio_client', 'ClientSession', 'call_tool') for node in calls)
    second = max(owners, key=lambda node: node.lineno)
    assert next(k.value.value for k in second.keywords if k.arg == 'readonly_restart') is True
    assert next(k.value.id for k in second.keywords if k.arg == 'trusted_history') == 'history'
    history = next(node for node in ast.walk(check) if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'history' for t in node.targets))
    assert names(history.value) == 'history_seed' and history.lineno < second.lineno
    first_owner_context = next(node for node in ast.walk(check) if isinstance(node, ast.AsyncWith)
                               and any(item.context_expr is min(owners, key=lambda n: n.lineno) for item in node.items))
    assert not any(node is history for node in ast.walk(first_owner_context))
    assert len([node for node in calls if names(node) == 'add']) == 2
    fixtures = next(node for node in calls if names(node) == 'fixtures')
    assert next(k.value.attr for k in fixtures.keywords if k.arg == 'cleanup_gate') == 'can_cleanup'


@pytest.mark.parametrize('held', [False, True])
def test_internal_failure_baseline_is_real_only_when_cleanup_is_proven(held):
    calls = []
    gate = inline.InlineFixtureCleanupGate()
    if held:
        gate.retain()
    ns = extracted('verify_dimension_operations.py', {'failure_baseline'},
                   {'native_snapshot': lambda: calls.append('native') or 'baseline'})
    assert ns['failure_baseline'](gate, 'baseline') is (None if held else True)
    assert calls == ([] if held else ['native'])


@pytest.mark.parametrize('outcome', ['unknown', 'dispatch-error', 'known-physical-mismatch'])
def test_actual_internal_check_uses_guarded_submit_and_has_no_post_hold_native_reads(outcome):
    trace, context = [], {}
    held = False
    gate = inline.InlineFixtureCleanupGate()
    original = OSError('native dispatch observation failed')
    def getter(name):
        assert not held, f'Native {name} after hold'
        trace.append(name)
        return 'baseline'
    class Model:
        def GetTitle(self):
            getter('title')
            return 'owned'
    @asynccontextmanager
    async def unused():
        yield
    from contextlib import contextmanager
    @contextmanager
    def fixtures(*, cleanup_gate):
        try:
            yield (None, [Model(), Model()], None)
        finally:
            trace.append(('fixture-cleanup', cleanup_gate()))
    class Adapter:
        _sw = object()
        mutation_guard = object()
        native_write_count = native_rebuild_count = 0
        def snapshot(self, model):
            return getter('document-snapshot')
    class Documents:
        def __init__(self, adapter):
            pass
        def list(self):
            getter('documents')
            return {'documents': [{'title': 'owned', 'document_id': 'd'}]}
        def close(self):
            trace.append('documents-close')
    class Store:
        def __init__(self, path):
            pass
        def close(self):
            trace.append('store-close')
    class Catalog:
        capture_seconds = []
        def __init__(self, *args, **kwargs):
            pass
        def list(self, *args):
            getter('dimensions')
            return {'total_count': 3, 'revision': 'rev', 'revision_scope': 'part_dimension_values_v1',
                'items': [{'object_id': 'dim', 'owner': {'feature_type': 'Extrusion'}, 'write_blockers': [],
                    'reference_anchor': {'strategy': 'display_dimension_v1'}, 'values': {'Основная': 7.}}]}
    class Body:
        def GetMassProperties(self, value):
            getter('mass')
            return [0, 0, 0, 210e-9]
    def submit(received_gate, runner, store, *args, **kwargs):
        nonlocal held
        assert received_gate is gate
        assert args[:2] == ('change', 'dimension.set_value')
        assert kwargs['mutates'] is True and kwargs['pass_operation_id'] is True
        trace.append('guarded-dispatch')
        if outcome == 'known-physical-mismatch':
            return {'status': 'succeeded', 'operation_id': 'op', 'mutation': {
                'phase': 'committed', 'before_state': {'_mutation_effect_scope': 'application'}},
                'result': {'execution_guard': {'original_state': 0, 'locked_state': 2, 'released_state': 0}}}
        gate.retain()
        held = True
        if outcome == 'dispatch-error':
            raise original
        return {'status': 'unknown', 'operation_id': 'op'}
    build = {'package_version': 'dev', 'source_digest': 'digest', 'git_sha': 'a' * 40, 'source_dirty': False}
    ns = extracted('verify_dimension_operations.py', {'check', 'require_inline_cleanup', 'close_inline_resources'}, {
        'InlineFixtureCleanupGate': inline.InlineFixtureCleanupGate,
        'solidworks_mcp': SimpleNamespace(__file__='C:/venv/site-packages/solidworks_mcp/__init__.py', __version__='dev'),
        'Path': Path, 'resources': SimpleNamespace(files=lambda package: SimpleNamespace(joinpath=lambda name:
            SimpleNamespace(read_text=lambda **kw: json.dumps(build)))),
        'json': json, 'math': __import__('math'), 'source_digest': lambda package: 'digest',
        'native_snapshot': lambda: getter('baseline'), 'fixtures': fixtures, 'Adapter': Adapter,
        'DocumentCatalog': Documents, 'JobStore': Store, 'TimedCatalog': Catalog,
        'binding': SimpleNamespace(module=lambda: object()), 'ui_snapshot': lambda *args: getter('ui'),
        'JobRunner': lambda *args: object(), 'Worker': lambda: object(), 'guarded_inline_submit': submit,
        'exact_solid': lambda *args: getter('body') and Body(),
        'native_extrema_m': lambda body: getter('extrema') and {'min': [0, 0, 0], 'max': [.005, .006, .007]},
    })
    error_type = {'dispatch-error': OSError, 'unknown': RuntimeError, 'known-physical-mismatch': AssertionError}[outcome]
    with pytest.raises(error_type) as raised:
        ns['check'](Path('unused'), cleanup_gate=gate, failure_report=context)
    if outcome == 'dispatch-error':
        assert raised.value is original
    after = trace[trace.index('guarded-dispatch') + 1:]
    if outcome == 'known-physical-mismatch':
        assert after[:2] == ['body', 'extrema']
        after = after[2:]
    assert after == ['documents-close', 'store-close', ('fixture-cleanup', False)]
    assert context['owned_fixtures_retained'] is True and context['retained_owned_fixture_count'] == 2
    assert context['git_sha'] == 'a' * 40 and context['installed_source_digest'] == 'digest'


@pytest.mark.parametrize('original_error', [None, AssertionError('original operation failed')])
def test_internal_resource_closure_attempts_both_retains_and_preserves_original(original_error):
    calls = []
    gate = inline.InlineFixtureCleanupGate()
    first, second = OSError('document watcher close failed'), RuntimeError('store close failed')
    class Resource:
        def __init__(self, name, error):
            self.name, self.error = name, error
        def close(self):
            calls.append(self.name)
            raise self.error
    ns = extracted('verify_dimension_operations.py', {'close_inline_resources'}, {})
    def close():
        ns['close_inline_resources'](Resource('documents', first), Resource('store', second), gate, original_error)
    if original_error is None:
        with pytest.raises(OSError) as raised:
            close()
        assert raised.value is first and first.__notes__
    else:
        close()
        assert len(original_error.__notes__) == 2
    assert calls == ['documents', 'store'] and not gate.can_cleanup()
