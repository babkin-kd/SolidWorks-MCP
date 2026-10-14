"""Bounded durable-export diagnostics, extracted without any CAD/native imports."""
import ast
from copy import deepcopy
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_internal_exports.py'
NAMES = {'_diagnostic_code', 'bounded_exception_chain', 'record_export_failure_diagnostic'}


def definitions():
    tree = ast.parse(SCRIPT.read_text(encoding='utf8'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
    namespace = {'math': math, 're': re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCRIPT), 'exec'), namespace)
    return namespace


class DomainError(RuntimeError):
    def __init__(self, code, message, uncertain=False):
        super().__init__(message)
        self.code, self.uncertain = code, uncertain
    def __str__(self):
        raise AssertionError('Diagnostics must never stringify native exception values.')


def job(status='unknown'):
    return {'operation_id': 'job_' + 'a' * 32, 'status': status,
        'error': {'code': 'mutation_rollback_unconfirmed', 'message': 'C:/private/template.SLDPRT <COM pointer 0xABC>',
                  'requires_reconciliation': True},
        'mutation': {'phase': 'unresolved', 'before_state': {'_mutation_effect_scope': 'application',
            'scope': 'part_export_source_v1', 'destination': 'C:/private/export.stl', 'raw_brep': 'x' * 90000,
            'preferences': {'stl_deviation_m': 9.15190966989661e-7, 'private': 'C:/private'},
            'source': {'export_profile': {'desired_application_preferences': {'stl_deviation_m': .0001}},
                       'raw_brep': 'y' * 90000}},
            'verification': {'outcome': 'unresolved', 'evidence': {'execution_guard': {
                'original_state': 0, 'locked_state': 2, 'released_state': 0}, 'after': 'z' * 90000}}},
        'result': None}


def test_unknown_snapshot_records_cause_checkpoint_and_desired_dependencies_without_paths_or_geometry():
    ns, report, snapshot = definitions(), {}, job()
    original = deepcopy(snapshot)
    ns['record_export_failure_diagnostic'](report, job=snapshot, cleanup_allowed=False)
    fact = report['job_failure_diagnostics'][0]
    assert fact['status'] == 'unknown' and fact['phase'] == 'unresolved'
    assert fact['error'] == {'code': 'mutation_rollback_unconfirmed', 'requires_reconciliation': True, 'message_omitted': True}
    assert math.isclose(fact['dependencies']['checkpoint_stl_deviation_um'], .915190966989661, abs_tol=1e-12)
    assert fact['dependencies']['desired_stl_deviation_um'] == 100.
    assert fact['dependencies']['current_preferences_measured'] is False
    assert fact['dependencies']['effect_scope'] == 'application'
    assert fact['execution_guard'] == {'original_state': 0, 'locked_state': 2, 'released_state': 0}
    encoded = json.dumps(report, allow_nan=False)
    assert len(encoded) < 1500 and 'C:/private' not in encoded and '0xABC' not in encoded and 'raw_brep' not in encoded
    assert snapshot == original


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), True, '100', 10**1000])
def test_malformed_numeric_dependencies_never_produce_nonfinite_json_or_coerced_values(value):
    ns, report, snapshot = definitions(), {}, job()
    snapshot['mutation']['before_state']['preferences']['stl_deviation_m'] = value
    ns['record_export_failure_diagnostic'](report, job=snapshot, cleanup_allowed=False)
    assert report['job_failure_diagnostics'][0]['dependencies']['checkpoint_stl_deviation_um'] is None
    json.dumps(report, allow_nan=False)


def test_bounded_history_keeps_latest_failure_and_does_not_infer_success_from_held_success_status():
    ns, report = definitions(), {}
    for i in range(12):
        snapshot = job('succeeded')
        snapshot['operation_id'] = 'op_' + f'{i:032x}'
        ns['record_export_failure_diagnostic'](report, job=snapshot, cleanup_allowed=False)
    assert len(report['job_failure_diagnostics']) == 8
    assert report['job_failure_diagnostics'][0]['operation_id'] == 'op_' + f'{4:032x}'
    assert report['job_failure_diagnostics'][-1]['status'] == 'succeeded'
    assert report['job_failure_diagnostics'][-1]['cleanup_allowed'] is False
    assert len(json.dumps(report)) < 10000
    before = deepcopy(report)
    ns['record_export_failure_diagnostic'](report, job=job('succeeded'), cleanup_allowed=True)
    assert report == before


def test_exception_chain_contains_all_available_domain_codes_without_stringifying_or_private_arguments():
    ns = definitions()
    setter = DomainError('export_preference_write_failed', 'C:/private <pointer 0x123>')
    restore = DomainError('export_preferences_restore_unconfirmed', 'C:/private preference details')
    outer = DomainError('mutation_rollback_unconfirmed', 'large private native data', True)
    restore.__cause__, outer.__cause__ = setter, restore
    report = {}
    ns['record_export_failure_diagnostic'](report, error=outer)
    items = report['operation_exception_chain']['items']
    assert [item['error_code'] for item in items] == ['mutation_rollback_unconfirmed',
        'export_preferences_restore_unconfirmed', 'export_preference_write_failed']
    assert items[0]['uncertain'] is True
    assert 'private' not in json.dumps(report) and '0x' not in json.dumps(report)
    setter.__cause__ = outer
    assert ns['bounded_exception_chain'](outer)['truncated_or_cycle'] is True


def test_chain_budget_and_suppressed_context_are_respected():
    ns = definitions()
    error = DomainError('outer_error', 'ignored')
    current = error
    for _ in range(30):
        current.__cause__ = DomainError('nested_error', 'ignored')
        current = current.__cause__
    assert len(ns['bounded_exception_chain'](error)['items']) == 8
    isolated = ValueError('C:/private')
    isolated.__context__ = error
    isolated.__suppress_context__ = True
    assert len(ns['bounded_exception_chain'](isolated)['items']) == 1


@pytest.mark.parametrize('status', ['unknown', 'succeeded'])
def test_actual_submit_records_returned_durable_failure_before_held_gate_and_preserves_primary(status):
    ns, report = definitions(), {}
    tree = ast.parse(SCRIPT.read_text(encoding='utf8'))
    submit = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'submit'
                  and [arg.arg for arg in node.args.args] == ['request', 'arguments'])
    error = DomainError('export_preference_write_failed', 'C:/private pointer')
    outer = DomainError('mutation_rollback_unconfirmed', 'ignored', True)
    outer.__cause__ = error
    primary = RuntimeError('held fixture')
    snapshot = job(status)
    gate = SimpleNamespace(can_cleanup=lambda: False)
    exports = SimpleNamespace(expected_operation=None)
    def execute(operation, **arguments):
        if status == 'unknown':
            raise outer
        return {'verified': True}
    def guarded(*args, **kwargs):
        operation = args[6]
        try:
            operation(snapshot['operation_id'])
        except DomainError as caught:
            assert caught is outer
        return snapshot
    def require(received):
        assert received is gate
        assert report['job_failure_diagnostics'][-1]['status'] == status
        assert exports.expected_operation is None
        if status == 'unknown':
            assert report['operation_exception_chain']['items'][1]['error_code'] == 'export_preference_write_failed'
        raise primary
    ns.update(report=report, fixture_cleanup_gate=gate, runner=object(), store=object(), exports=exports,
        catalog=SimpleNamespace(execute=execute), guarded_inline_submit=guarded, require_fixture_native_access=require)
    exec(compile(ast.Module(body=[submit], type_ignores=[]), str(SCRIPT), 'exec'), ns)
    args = {'document_id': 'owned', 'configuration': 'Основная', 'expected_revision': 'rev'}
    with pytest.raises(RuntimeError) as raised:
        ns['submit']('request', args)
    assert raised.value is primary


def test_diagnostic_formatter_failure_never_replaces_original_exception():
    ns = definitions()
    class Report(dict):
        def __setitem__(self, key, value):
            raise OSError('report cannot be stored')
    ns['record_export_failure_diagnostic'](Report(), error=DomainError('known_error', 'ignored'))
    report = {'job_failure_diagnostics': object()}
    ns['record_export_failure_diagnostic'](report, job=job(), cleanup_allowed=False)
    assert report['failure_diagnostic_formatting_failed'] is True
