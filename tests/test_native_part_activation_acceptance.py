"""Manufactured finite report admission; domain/ledger predicates stay real."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

from test_native_part_activation import setup, capture, run
from test_native_part_activation_protocol import native_shaped


scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
from verifier_native_part_activation_acceptance import validate_internal_activation, LABELS
sys.path.pop(0)


@pytest.fixture
def reports(setup):
    positive = native_shaped(run(setup))
    noop = native_shaped(run(setup, request_id='noop'))
    wheel = dict(package_version='2.0.0.dev89', git_sha='a'*40, source_digest='b'*64, wheel_sha256='c'*64)
    trusted = {key: {'trusted_helper.py': 'd'*64} for key in LABELS}
    base = dict(accepted=False, phase='terminal', owned_documents=[], native_calls_live=False,
                baseline_restored=True, own_cleanup_verified=True, independent_native_readback_verified=True,
                package_origin_verified=True, metadata_catalog=dict(public_tool_count=75, output_schemas_verified=True),
                wheel=wheel, original_baseline=[[], [], []], restored_baseline=[[], [], []],
                original_application=dict(user_control=True, visible=True, current_directory='/root', search_folders=''),
                restored_application=dict(user_control=True, visible=True, current_directory='/root', search_folders=''),
                captures=[dict(status='returned')])
    result = {}
    for key, labels in LABELS.items():
        report = deepcopy(base)
        report['verifier_hashes'] = deepcopy(trusted[key])
        report['cases'] = [dict(label=label, passed=True) for label in labels]
        if key == 'positive':
            report.update(scope='installed_native_part_activation_positive_only', activation_positive_passed=True, job=positive)
        else:
            report.update(scope='installed_native_part_activation_case_only', case=key, activation_case_passed=True)
        result[key] = report
    result['already_active']['job'] = noop
    stale = result['stale']
    stale.update(job=dict(status='failed', error=dict(code='stale_revision')),
                 independent_before=[{'name': 'before'}], independent_before_after_owned_rename=[{'name': 'after'}])
    for case, code in zip(stale['cases'][:2], ('document_not_open', 'configuration_not_found')):
        case['job'] = dict(status='failed', error=dict(code=code, requires_reconciliation=False))
    fault = result['controlled_after_call']
    fault.update(actual_com_failure_injected=False, injection_applied=True,
                 original_activation_receipt=dict(native_call_attempted=True, native_call_returned=True,
                                                  pending_activation=False, native_error=0),
                 job=dict(operation_id='job_own', status='unknown', mutation=dict(phase='unresolved')),
                 held_job=dict(error=dict(code='document_mutation_blocked')),
                 released_execution_guard=dict(released=True, selection_preserved=True),
                 reconciliation=dict(operation_id='job_own', status='unknown',
                     mutation=dict(phase='reconciled', reconciliation=dict(resolution='accept_current_state'))))
    return result, wheel, trusted


def test_all_finite_same_wheel_cases_admit_public_dispatch_but_not_whole_acceptance(reports):
    result = validate_internal_activation(*reports)
    assert result['internal_activation_cases_verified'] is True
    assert result['public_activation_accepted'] is False and result['whole_activation_accepted'] is False


@pytest.mark.parametrize('fault', ['missing_report', 'wheel', 'helpers', 'untrusted_empty', 'partial_labels',
                                  'not_passed', 'not_terminal', 'owned', 'native_live', 'missing_baseline',
                                  'changed_application', 'running_capture', 'retained_int', 'wrong_noop',
                                  'stale_did_not_change', 'foreign_wrong_error', 'actual_com_claim',
                                  'pending_original', 'native_error_bool', 'history_success', 'other_job_reconcile'])
def test_partial_unbound_or_unconfirmed_reports_are_refused(reports, fault):
    data, wheel, trusted = reports
    p, stale, unknown = data['positive'], data['stale'], data['controlled_after_call']
    if fault == 'missing_report': data.pop('stale')
    if fault == 'wheel': p['wheel'] = {**wheel, 'wheel_sha256': 'e'*64}
    if fault == 'helpers': p['verifier_hashes']['trusted_helper.py'] = 'e'*64
    if fault == 'untrusted_empty': trusted['positive'] = {}; p['verifier_hashes'] = {}
    if fault == 'partial_labels': p['cases'].pop()
    if fault == 'not_passed': p['cases'][0]['passed'] = False
    if fault == 'not_terminal': p['phase'] = 'running'
    if fault == 'owned': p['owned_documents'] = [{'title': 'own'}]
    if fault == 'native_live': p['native_calls_live'] = True
    if fault == 'missing_baseline': p['original_baseline'] = p['restored_baseline'] = None
    if fault == 'changed_application': p['restored_application']['current_directory'] = '/foreign'
    if fault == 'running_capture': p['captures'][0]['status'] = 'running'
    if fault == 'retained_int': p['retained_process'] = 0
    if fault == 'wrong_noop': data['already_active']['job'] = p['job']
    if fault == 'stale_did_not_change': stale['independent_before_after_owned_rename'] = stale['independent_before']
    if fault == 'foreign_wrong_error': stale['cases'][0]['job']['error']['code'] = 'other'
    if fault == 'actual_com_claim': unknown['actual_com_failure_injected'] = True
    if fault == 'pending_original': unknown['original_activation_receipt']['pending_activation'] = True
    if fault == 'native_error_bool': unknown['original_activation_receipt']['native_error'] = False
    if fault == 'history_success': unknown['reconciliation']['status'] = 'succeeded'
    if fault == 'other_job_reconcile': unknown['reconciliation']['operation_id'] = 'job_foreign'
    with pytest.raises(ValueError):
        validate_internal_activation(data, wheel, trusted)
