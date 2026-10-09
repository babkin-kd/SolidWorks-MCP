"""Private UI evidence and resource unwind regressions; no native imports."""

import ast
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
import sys
from types import SimpleNamespace

import pytest

from test_export_verifier_helpers_v2 import SCRIPTS, pure_cleanup_utility


helpers = pure_cleanup_utility('verifier_export_diagnostics.py')
delta = helpers['ui_snapshot_difference']
capture = helpers['capture_ui_difference']
close = helpers['close_resources_with_gate']
guard = helpers['independent_baseline_check']
Gate = pure_cleanup_utility()['InlineFixtureCleanupGate']


class Canonical:
    __hash__ = None
    def __init__(self, token):
        self.token = token
    def __eq__(self, other):
        return self.token == other.token
    def __str__(self):
        raise AssertionError('Never stringify native identities into a report.')


def rows(*tokens):
    return [(Canonical(token), 0, index + 5) for index, token in enumerate(tokens)]


def test_order_only_difference_is_reported_without_normalizing_the_strict_snapshot():
    before = rows('secret title A', 'secret path B')
    after = [(Canonical('secret path B'), 0, 6), (Canonical('secret title A'), 0, 5)]
    evidence = delta(before, after)
    assert after != before
    assert evidence['identity_order_changed'] is True and evidence['changed_counts'] == []
    assert [row['identity_index'] for row in evidence['after_rows']] == [1, 0]
    assert evidence['missing_before_row_indices'] == evidence['added_after_row_indices'] == []
    encoded = json.dumps(evidence)
    assert 'secret' not in encoded and evidence['cause_inferred'] is False


def test_missing_added_and_raw_blocking_selection_changes_match_retained_canonical_rows():
    before = rows('A', 'B')
    after = [(Canonical('B'), 2, 17), (Canonical('C'), 0, 0)]
    evidence = delta(before, after)
    assert evidence['before_row_count'] == evidence['after_row_count'] == 2
    assert evidence['missing_before_row_indices'] == [0] and evidence['added_after_row_indices'] == [1]
    assert evidence['changed_counts'] == [{'identity_index': 1, 'before_row_index': 1,
        'after_row_index': 0, 'before_blocking_state': 0, 'after_blocking_state': 2,
        'before_selection_count': 6, 'after_selection_count': 17}]
    assert evidence['after_rows'][0]['selection_count'] == 17


def test_fresh_canonical_wrappers_and_duplicate_identity_are_not_pointer_or_hash_matched():
    evidence = delta(rows('A', 'B'), rows('A', 'B'))
    assert evidence['identity_order_changed'] is False and evidence['changed_counts'] == []
    assert evidence['duplicate_identity_rows'] is False
    assert delta(rows('A', 'A'), rows('A'))['duplicate_identity_rows'] is True


def test_report_is_bounded_without_truncating_actual_row_counts_or_inventing_cause():
    evidence = delta(rows(*range(100)), rows(*range(100)), max_rows=2)
    assert evidence['before_row_count'] == evidence['after_row_count'] == 100
    assert len(evidence['before_rows']) == len(evidence['after_rows']) == 2
    assert evidence['rows_truncated'] is True and evidence['cause_inferred'] is False
    assert len(json.dumps(evidence)) < 1200
    with pytest.raises(ValueError, match='comparison budget'):
        delta(rows('A', 'B'), rows('A', 'B'), max_comparisons=1)


def test_capture_reads_ui_once_and_preserves_strict_failure_and_raw_counts():
    before, after, reads, report = rows('A'), [(Canonical('A'), 2, 19)], [], {}
    def reader():
        reads.append(True)
        return after
    observed = capture(reader, before, report, 'ui')
    assert observed is after and reads == [True]
    with pytest.raises(AssertionError):
        assert observed == before
    assert report['ui']['after_rows'][0] == {'row_index': 0, 'identity_index': 0,
                                          'blocking_state': 2, 'selection_count': 19}


def test_capture_read_failure_keeps_original_exception_without_sensitive_error_message():
    original, report = RuntimeError('private title/path must stay out of diagnostics'), {}
    def reader():
        raise original
    with pytest.raises(RuntimeError) as error:
        capture(reader, rows('A'), report, 'ui')
    assert error.value is original
    assert report['ui'] == {'snapshot_read_error_type': 'RuntimeError', 'cause_inferred': False}


def test_invalid_snapshot_diagnostics_do_not_replace_caller_strict_mismatch():
    report = {}
    observed = capture(lambda: None, rows('A'), report, 'ui')
    assert observed is None
    assert report['ui'] == {'diagnostic_error_type': 'ValueError', 'cause_inferred': False,
                            'before_row_count': 1, 'after_row_count': None}
    with pytest.raises(AssertionError):
        assert observed == rows('A')


def test_held_original_ui_report_uses_only_retained_raw_counts_without_equality_or_getters():
    class NoEquality(Canonical):
        def __eq__(self, other):
            raise AssertionError('No native equality after hold')
    result = helpers['ui_snapshot_unmeasured']([(NoEquality('A'), 2, 23)])
    assert result['before_rows'] == [{'row_index': 0, 'blocking_state': 2, 'selection_count': 23}]
    assert result['after_row_count'] is None and result['after_snapshot_read'] is False
    assert 'A' not in json.dumps(result)


@pytest.mark.parametrize('native_activity', [False, True])
@pytest.mark.parametrize('which', ['source', 'ui', 'preferences'])
def test_independent_strict_mismatch_holds_only_after_native_adapter_activity(native_activity, which):
    gate, original = Gate(), AssertionError(which + ' mismatch')
    def checker():
        raise original
    with pytest.raises(AssertionError) as error:
        guard(checker, gate, native_activity=native_activity)
    assert error.value is original and gate.can_cleanup() is (not native_activity)
    if native_activity:
        with pytest.raises(RuntimeError, match='Held fixture'):
            guard(lambda: pytest.fail('No checker after a hold'), gate, native_activity=native_activity)
    else:
        assert guard(lambda: 'known', gate, native_activity=native_activity) == 'known'
    assert gate.can_cleanup() is (not native_activity)  # Success never reauthorizes a hold.


def test_already_held_gate_denies_independent_checker_before_any_native_read():
    gate = Gate()
    gate.retain()
    with pytest.raises(RuntimeError, match='Held fixture'):
        guard(lambda: pytest.fail('Native checker must never run'), gate, native_activity=False)
    assert gate.can_cleanup() is False


@pytest.mark.parametrize('hold_reason', ['different_durable_job', 'foreign_blocker', 'missing_guard'])
def test_real_internal_submit_denies_succeeded_but_held_before_return_to_native_flow(hold_reason):
    from test_verifier_fixture_cleanup_v2 import terminal
    gate, events, job = Gate(), [], terminal()
    if hold_reason == 'missing_guard':
        del job['mutation']['verification']['evidence']['execution_guard']
    def dispatch(*args, **kwargs):
        events.append('submit')
        return job
    def get(operation_id):
        assert operation_id == job['operation_id']
        events.append('durable-get')
        return {**job, 'status': 'unknown'} if hold_reason == 'different_durable_job' else deepcopy(job)
    def blockers(*args, **kwargs):
        events.append('all-holds')
        return [{'phase': 'prepared'}] if hold_reason == 'foreign_blocker' else []
    path = SCRIPTS / 'verify_internal_exports.py'
    tree = ast.parse(path.read_text(encoding='utf8'), filename=str(path))
    submit_function = deepcopy(next(node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == 'submit'
        and [argument.arg for argument in node.args.args] == ['request', 'arguments']))
    namespace = {'fixture_cleanup_gate': gate, 'runner': SimpleNamespace(submit=dispatch),
        'store': SimpleNamespace(get=get, mutation_blockers=blockers),
        'guarded_inline_submit': pure_cleanup_utility()['guarded_inline_submit'],
        'require_fixture_native_access': helpers['require_fixture_native_access']}
    # The real submit now records a bounded durable diagnostic before its
    # unchanged denial gate. Supply its actual pure helpers to this AST harness.
    from test_export_failure_diagnostics_v2 import definitions
    namespace.update(definitions())
    namespace['report'] = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[submit_function], type_ignores=[])), str(path), 'exec'), namespace)
    with pytest.raises(RuntimeError, match='Held fixture'):
        result = namespace['submit']('request', {'document_id': 'owned',
            'configuration': 'Основная', 'expected_revision': 'revision'})
        assert result['status'] == 'succeeded'
        pytest.fail('No success assertions/prepare/Activate/native work after held submit')
    assert events == ['submit', 'durable-get', 'all-holds'] and gate.can_cleanup() is False


@pytest.mark.parametrize('primary_present', [False, True])
def test_both_resource_closes_are_attempted_and_gate_retained_before_next_close(primary_present):
    gate, diagnostics, calls = Gate(), [], []
    first, second, original = ValueError('First resource'), OSError('Second resource'), RuntimeError('Original body')
    def first_close():
        calls.append(('documents', gate.can_cleanup()))
        raise first
    def second_close():
        calls.append(('store', gate.can_cleanup()))
        raise second
    resources = [('documents', SimpleNamespace(close=first_close)), ('store', SimpleNamespace(close=second_close))]
    if primary_present:
        close(resources, gate, diagnostics, primary_error=original)
    else:
        with pytest.raises(ValueError) as error:
            close(resources, gate, diagnostics)
        assert error.value is first
    assert calls == [('documents', True), ('store', False)] and gate.can_cleanup() is False
    assert diagnostics == [{'resource': 'documents', 'error_type': 'ValueError'},
                           {'resource': 'store', 'error_type': 'OSError'}]


def test_real_check_exitstack_does_not_replace_body_error_and_retains_before_fixture_unwind():
    original, calls, failure, gates = RuntimeError('Original body'), [], {}, []
    def new_gate():
        gate = Gate()
        gates.append(gate)
        return gate
    @contextmanager
    def fixtures(*, cleanup_gate):
        try:
            yield None, [object(), object()], None
        finally:
            calls.append(('fixture-cleanup-allowed', cleanup_gate()))
    def resource(name):
        def broken():
            calls.append((name, gates[0].can_cleanup()))
            raise ValueError(name + ' failure')
        return SimpleNamespace(close=broken)
    path = SCRIPTS / 'verify_internal_exports.py'
    tree = ast.parse(path.read_text(encoding='utf8'), filename=str(path))
    check = deepcopy(next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'check'))
    owned_with = next(node for node in ast.walk(check) if isinstance(node, ast.With))
    # Replace only native body/setup. Keep real callback, outer exception/finally
    # and failure reporting, exercising sys.exc_info inside ExitStack.__exit__.
    owned_with.body = ast.parse('owned_fixture_count = len(owned)\ncleanup.callback(close_resources)\n'
                               'documents = fake_documents\nstore = fake_store\nraise original_error').body
    baseline = rows('A')
    def initial(name, value):
        def read(*args):
            assert not gates or gates[0].can_cleanup(), 'No native baseline read after cleanup failure'
            calls.append(name)
            return value
        return read
    namespace = {'sys': sys, 'ExitStack': ExitStack, '_provenance': lambda: {},
        'native_snapshot': initial('docs-read', ('original',)),
        'binding': SimpleNamespace(connect=lambda **kwargs: object(), module=lambda: object()),
        'application_preferences': initial('prefs-read', {}), 'ui_snapshot': initial('ui-read', baseline),
        'user_file_metadata': initial('files-read', {}), 'fixtures': fixtures,
        'InlineFixtureCleanupGate': new_gate, 'close_resources_with_gate': close,
        'ui_snapshot_unmeasured': helpers['ui_snapshot_unmeasured'],
        'fake_documents': resource('documents'), 'fake_store': resource('store'),
        'original_error': original}
    flags = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'cleanup_baseline_flags')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[flags, check], type_ignores=[])), str(path), 'exec'), namespace)
    with pytest.raises(RuntimeError) as error:
        namespace['check'](None, None, failure_report=failure)
    assert error.value is original
    assert calls == ['docs-read', 'prefs-read', 'ui-read', 'files-read', ('documents', True),
                     ('store', False), ('fixture-cleanup-allowed', False)]
    assert failure['resource_cleanup_errors'] == [{'resource': 'documents', 'error_type': 'ValueError'},
                                                 {'resource': 'store', 'error_type': 'ValueError'}]
    assert failure['owned_fixture_cleanup_retained_count'] == 2
    assert failure['original_user_document_baseline_restored'] is False
    assert failure['original_preferences_restored'] is None
    assert failure['original_ui_snapshot_difference']['after_snapshot_read'] is False
