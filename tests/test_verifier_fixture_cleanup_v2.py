"""Fixture retention and durable cleanup gates; AST-isolated, no native imports."""

import ast
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
import sys
from types import SimpleNamespace

import pytest

from test_export_verifier_helpers_v2 import SCRIPTS, extracted_functions, pure_cleanup_utility


utility = pure_cleanup_utility()
Gate = utility['InlineFixtureCleanupGate']
submit = utility['guarded_inline_submit']
proven = utility['inline_job_cleanup_proven']
GUARD = {'original_state': 0, 'locked_state': 2, 'released_state': 0}


def terminal(status='succeeded', phase='committed'):
    return {'operation_id': 'owned-operation', 'status': status,
        'error': None if status == 'succeeded' else {'requires_reconciliation': False},
        'result': {'verified': True, 'execution_guard': deepcopy(GUARD)},
        'mutation': {'phase': phase, 'before_state': {'_mutation_effect_scope': 'application'},
                     'verification': {'outcome': phase, 'evidence': {'execution_guard': deepcopy(GUARD)}}}}


@pytest.mark.parametrize('status,phase', [('succeeded', 'committed'), ('failed', 'rolled_back'),
                                       ('failed', 'not_started')])
def test_only_aligned_known_terminal_full_guard_proof_allows_cleanup(status, phase):
    gate = Gate()
    assert gate.can_cleanup() is True
    gate.before_submit()
    assert gate.can_cleanup() is False
    gate.observe_terminal(terminal(status, phase))
    assert gate.can_cleanup() is True


@pytest.mark.parametrize('status,error,expected', [
    ('failed', {'requires_reconciliation': False}, True), ('cancelled', None, True),
    ('failed', {}, False), ('failed', {'requires_reconciliation': 0}, False),
    ('failed', {'requires_reconciliation': True}, False), ('succeeded', None, False),
    ('cancelled', {'requires_reconciliation': True}, False),
])
def test_prewrite_without_checkpoint_requires_explicit_known_proof(status, error, expected):
    assert proven({'status': status, 'error': error, 'mutation': None}) is expected


@pytest.mark.parametrize('part', ['original_state', 'locked_state', 'released_state'])
@pytest.mark.parametrize('wrong', [True, False, None, '0', 0.0, 3])
def test_every_guard_state_is_required_typed_integer_not_bool_float_or_string(part, wrong):
    job = terminal()
    job['mutation']['verification']['evidence']['execution_guard'][part] = wrong
    assert proven(job) is False


@pytest.mark.parametrize('change', ['queued', 'running', 'unknown', 'prepared', 'unresolved',
                                  'mismatch', 'missing_guard', 'missing_state', 'unverified',
                                  'result_guard_mismatch', 'error_reconciliation', 'wrong_scope'])
def test_missing_or_contradictory_terminal_durable_proof_is_sticky(change):
    job = terminal()
    if change in ('queued', 'running', 'unknown'):
        job['status'] = change
    elif change in ('prepared', 'unresolved'):
        job['mutation']['phase'] = change
    elif change == 'mismatch':
        job['mutation']['verification']['outcome'] = 'rolled_back'
    elif change == 'missing_guard':
        job['mutation']['verification']['evidence'] = {}
    elif change == 'missing_state':
        del job['mutation']['verification']['evidence']['execution_guard']['locked_state']
    elif change == 'unverified':
        job['result']['verified'] = 1
    elif change == 'result_guard_mismatch':
        job['result']['execution_guard']['original_state'] = True
    elif change == 'error_reconciliation':
        job['error'] = {'requires_reconciliation': True}
    else:
        job['mutation']['before_state']['_mutation_effect_scope'] = 'document'
    gate = Gate()
    gate.before_submit()
    gate.observe_terminal(job)
    assert gate.can_cleanup() is False
    gate.before_submit()
    gate.observe_terminal(terminal())
    assert gate.can_cleanup() is False  # A later known job never erases uncertainty.


@pytest.mark.parametrize('fault', ['submit_throw', 'durable_read_throw', 'different_durable_job',
                                  'prepared_other_job', 'invalid_blockers'])
def test_dispatch_holds_first_and_only_exact_durable_quiescence_releases(fault):
    gate, events, original = Gate(), [], RuntimeError('Injected durable observation loss')
    job = terminal()
    def dispatch(*args, **kwargs):
        assert gate.can_cleanup() is False
        events.append('dispatch')
        if fault == 'submit_throw':
            raise original
        return job
    def read(operation_id):
        assert operation_id == job['operation_id']
        events.append('durable-read')
        if fault == 'durable_read_throw':
            raise original
        return {**job, 'status': 'unknown'} if fault == 'different_durable_job' else deepcopy(job)
    def blockers(*args, **kwargs):
        assert kwargs['effect_scope'] == 'application'
        return [{'phase': 'prepared'}] if fault == 'prepared_other_job' else None if fault == 'invalid_blockers' else []
    runner, store = SimpleNamespace(submit=dispatch), SimpleNamespace(get=read, mutation_blockers=blockers)
    if fault.endswith('throw'):
        with pytest.raises(RuntimeError) as error:
            submit(gate, runner, store, 'request')
        assert error.value is original
    else:
        assert submit(gate, runner, store, 'request') is job
    assert gate.can_cleanup() is False
    previous = list(events)
    with pytest.raises(RuntimeError, match='earlier work'):
        submit(gate, runner, store, 'later-request')
    assert events == previous  # No subsequent dispatch or native write.


@pytest.mark.parametrize('status,phase', [('succeeded', 'committed'), ('failed', 'rolled_back'),
                                       ('failed', 'not_started')])
def test_dispatch_releases_only_after_durable_record_and_all_application_holds_are_checked(status, phase):
    gate, calls, job = Gate(), [], terminal(status, phase)
    def dispatch():
        assert gate.can_cleanup() is False
        calls.append('dispatch')
        return job
    def get(operation_id):
        assert gate.can_cleanup() is False
        calls.append('durable-get')
        return deepcopy(job)
    def blockers(*args, **kwargs):
        assert gate.can_cleanup() is False and kwargs == {'effect_scope': 'application'}
        calls.append('all-holds')
        return []
    assert submit(gate, SimpleNamespace(submit=dispatch),
                  SimpleNamespace(get=get, mutation_blockers=blockers)) is job
    assert gate.can_cleanup() is True and calls == ['dispatch', 'durable-get', 'all-holds']


def cleanup_context(gate, calls, *, close_error=None):
    """Execute the real fixtures except/finally, replacing native setup with yield."""
    path = SCRIPTS / 'verify_geometry_reads.py'
    tree = ast.parse(path.read_text(encoding='utf8'), filename=str(path))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'fixtures')
    final_try = deepcopy(next(node for node in function.body if isinstance(node, ast.Try)))
    assert not any(isinstance(node, ast.Return) for branch in final_try.finalbody for node in ast.walk(branch))
    final_try.body = ast.parse('yield session, owned, before').body
    prefix = ast.parse("session = fake_session\nsw = fake_sw\nowned = fake_owned\nbefore = 'baseline'\n"
                       "original_title = 'Original'\ndimension_preference = True\nprimary_failure = None").body
    function = deepcopy(function)
    function.body = [*prefix, final_try]
    def title(name):
        calls.append(('title', name))
        return name
    def close(name):
        calls.append(('close', name))
        if close_error:
            raise close_error
    def set_pref(*args):
        calls.append(('preference-write',))
    def activate(*args):
        calls.append(('activate',))
        return object(), 0
    def snapshot():
        calls.append(('snapshot',))
        return 'baseline'
    def get_pref(*args):
        calls.append(('preference-read',))
        return True
    namespace = {'contextmanager': contextmanager, 'json': json,
        'fixture_cleanup_allowed': utility['fixture_cleanup_allowed'],
        'fake_session': SimpleNamespace(_model='owned'),
        'fake_owned': [SimpleNamespace(GetTitle=lambda: title('Первый')),
                       SimpleNamespace(GetTitle=lambda: title('Второй'))],
        'fake_sw': SimpleNamespace(CloseDoc=close, SetUserPreferenceToggle=set_pref,
                                   ActivateDoc3=activate, GetUserPreferenceToggle=get_pref),
        'native_snapshot': snapshot, 'SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE': 999}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                 str(path), 'exec'), namespace)
    return namespace['fixtures'](cleanup_gate=gate)


@pytest.mark.parametrize('gate_value', [False, None, 0, 1, '', object()])
def test_gate_non_exact_true_retains_all_owned_without_even_native_getters(gate_value, capsys):
    calls, original = [], RuntimeError('Primary operation failure')
    with pytest.raises(RuntimeError) as error:
        with cleanup_context(lambda: gate_value, calls):
            raise original
    assert error.value is original and calls == []
    printed = capsys.readouterr().out
    assert len(printed) < 150 and json.loads(printed) == {
        'phase': 'fixture_retained', 'owned_fixture_document_count': 2}


def test_raising_gate_and_even_raising_notice_do_not_mask_original_error(monkeypatch):
    original, calls = RuntimeError('Primary failure'), []
    def bad_gate():
        raise ValueError('Gate observation failed')
    def bad_print(*args, **kwargs):
        raise OSError('Notice unavailable')
    context = cleanup_context(bad_gate, calls)
    monkeypatch.setattr('builtins.print', bad_print)
    with pytest.raises(RuntimeError) as error:
        with context:
            raise original
    assert error.value is original and calls == []


@pytest.mark.parametrize('gate', [None, lambda: True])
def test_default_and_exact_true_keep_owned_cleanup_and_baseline_checks(gate):
    calls = []
    with cleanup_context(gate, calls):
        pass
    assert calls == [('title', 'Второй'), ('close', 'Второй'), ('title', 'Первый'), ('close', 'Первый'),
                     ('preference-write',), ('activate',), ('snapshot',), ('preference-read',)]


def test_cleanup_error_never_replaces_primary_body_error_but_standalone_error_propagates():
    original, cleanup_error = RuntimeError('Original operation'), ValueError('Cleanup failed')
    with pytest.raises(RuntimeError) as error:
        with cleanup_context(lambda: True, [], close_error=cleanup_error):
            raise original
    assert error.value is original
    with pytest.raises(ValueError) as error:
        with cleanup_context(lambda: True, [], close_error=cleanup_error):
            pass
    assert error.value is cleanup_error


def test_internal_failure_reports_retained_owned_count_and_skips_all_posthold_native_baseline_getters():
    calls, gates, original_error = [], [], RuntimeError('Uncertain owned operation')
    def new_gate():
        gate = Gate()
        gates.append(gate)
        return gate
    @contextmanager
    def fixtures(*, cleanup_gate):
        try:
            yield None, [object(), object()], None
        finally:
            assert cleanup_gate() is False
            calls.append('fixtures-retained')
    def initial_reader(name, value):
        def read(*args):
            assert not gates or gates[0].can_cleanup() is True, 'Native read after unknown hold'
            calls.append(name)
            return value
        return read
    def fail_adapter():
        gates[0].retain()  # Artificial unknown result; no actual native work.
        raise original_error
    namespace = {'ExitStack': ExitStack, '_provenance': lambda: {},
        'sys': sys,
        'native_snapshot': initial_reader('docs', ('original',)),
        'binding': SimpleNamespace(connect=lambda **kwargs: object(), module=lambda: object()),
        'application_preferences': initial_reader('preferences', {'native': 'original'}),
        'ui_snapshot': initial_reader('ui', [('original', 0)]),
        'user_file_metadata': initial_reader('files', {}),
        'fixtures': fixtures, 'InlineFixtureCleanupGate': new_gate,
        'close_resources_with_gate': pure_cleanup_utility('verifier_export_diagnostics.py')['close_resources_with_gate'],
        'ui_snapshot_unmeasured': pure_cleanup_utility('verifier_export_diagnostics.py')['ui_snapshot_unmeasured'],
        'SolidWorksDocuments': fail_adapter}
    check = extracted_functions('verify_internal_exports.py', {'check', 'cleanup_baseline_flags'}, namespace)['check']
    failure = {}
    with pytest.raises(RuntimeError) as error:
        check(None, None, failure_report=failure)
    assert error.value is original_error
    assert calls == ['docs', 'preferences', 'ui', 'files', 'fixtures-retained']
    assert failure['owned_fixture_cleanup_allowed'] is False
    assert failure['owned_fixture_cleanup_retained'] is True
    assert failure['owned_fixture_cleanup_retained_count'] == 2
    assert failure['original_user_document_baseline_restored'] is False
    assert failure['original_preferences_restored'] is None
    assert failure['original_ui_blocking_and_selection_restored'] is None
    assert failure['original_user_file_metadata_unchanged'] is None
    assert failure['cleanup_baseline_reads_skipped_due_to_hold'] is True
    assert failure['saveas_attempt_count'] == failure['native_export_adapter_call_count'] == 0
