"""Detached same-wheel L3 internal preflight; never substitutes CAD/file witnesses."""
from copy import deepcopy
import re

from verifier_native_first_save import _json, verified_committed_first_save
from verifier_first_save_race import verified_race_rollback
from verifier_first_save_faults import COPY_FAULTS


WHEEL_FIELDS = ('package_version', 'git_sha', 'source_digest', 'wheel_sha256')
BASE_SCOPES = {
    'positive': ('installed_first_save_domain_positive_only', 'positive_case_passed'),
    'rejections': ('installed_first_save_rejections_only', 'rejection_cases_passed'),
    'race': ('installed_first_save_destination_race_only', 'race_case_passed'),
}
REJECTION_LABELS = ['existing_destination_prewrite', 'renamed_source_stale_revision_prewrite',
                    'owned_fixture_cleanup_baseline_restored']
RACE_LABELS = ['destination_race_after_native_readback_no_overwrite', 'owned_fixture_cleanup_baseline_restored']
FAULT_LABELS = ['controlled_after_copy_unknown_hold_no_retry', 'independent_terminal_owner_reconciliation',
                'owned_fixture_cleanup_baseline_restored']


def _report(report, wheel, hashes, scope, passed_flag, expected_public_tool_count):
    _json(report)
    if (report.get('scope') != scope or report.get('phase') != 'terminal'
            or report.get(passed_flag) is not True or report.get('accepted') is not False
            or report.get('error') is not None
            or not (report.get('retained_process') is None or report.get('retained_process') is False)
            or report.get('owned_documents') != [] or report.get('native_calls_live') is not False
            or report.get('baseline_restored') is not True or report.get('own_cleanup_verified') is not True
            or report.get('package_origin_verified') is not True
            or type(report.get('metadata_catalog', {}).get('public_tool_count')) is not int
            or report['metadata_catalog']['public_tool_count'] != expected_public_tool_count
            or report.get('metadata_catalog', {}).get('output_schemas_verified') is not True):
        raise ValueError('A complete terminal installed case with restored baseline is required.')
    if any(report.get('wheel', {}).get(key) != wheel[key] for key in WHEEL_FIELDS):
        raise ValueError('Internal cases must belong to the exact same wheel/source identity.')
    if (type(hashes) is not dict or not hashes
            or any(type(key) is not str or type(value) is not str or re.fullmatch(r'[a-f0-9]{64}', value) is None
                   for key, value in hashes.items()) or report.get('verifier_hashes') != hashes):
        raise ValueError('Case helpers must match the complete trusted current hash inventory.')
    for key, value in report.items():
        if (key == 'lifecycle_hold' or key.startswith('pending') or key.endswith('_pending')) and value is not False:
            raise ValueError('Pending or held case cannot authorize public CAD.')


def _cases(report, labels):
    cases = report.get('cases')
    if (type(cases) is not list or len(cases) != len(labels)
            or any(type(case) is not dict or case.get('label') != label or case.get('passed') is not True
                   for case, label in zip(cases, labels))):
        raise ValueError('Every exact ordered internal case must be passed; skipped is not passed.')
    return cases


def validate_internal_cases(reports, wheel, trusted_hashes, *, expected_public_tool_count=73):
    """Require I1/I2/I3 and all four controlled I4 modes before public dispatch.

    trusted_hashes comes from the current driver, never a prior report inventory.
    The retained staged CAD files and detailed oracles remain private evidence.
    This function reads detached data only; it neither clears holds nor edits CAD.
    """
    _json(reports)
    _json(wheel)
    _json(trusted_hashes)
    if type(expected_public_tool_count) is not int or not 1 <= expected_public_tool_count <= 512:
        raise ValueError('Use the complete trusted metadata catalog count for the candidate.')
    expected = set(BASE_SCOPES) | set(COPY_FAULTS)
    if type(reports) is not dict or set(reports) != expected or set(trusted_hashes) != expected:
        raise ValueError('The finite internal case set, including every controlled fault mode, is required.')
    for key, (scope, flag) in BASE_SCOPES.items():
        _report(reports[key], wheel, trusted_hashes[key], scope, flag, expected_public_tool_count)
    if not verified_committed_first_save(reports['positive']['job']):
        raise ValueError('Positive first-save native protocol is unconfirmed.')
    rejections = _cases(reports['rejections'], REJECTION_LABELS)
    for case, code in zip(rejections[:2], ('first_save_destination_exists', 'stale_revision')):
        if (type(case.get('copy_calls')) is not int or case['copy_calls'] != 0
                or case['job']['status'] != 'failed' or case['job']['error']['code'] != code):
            raise ValueError('Both prewrite rejections require zero Copy and the exact failure.')
    race = _cases(reports['race'], RACE_LABELS)[0]
    if (not verified_race_rollback(race['job'], race['foreign_file']) or race.get('replay_verified') is not True
            or any(type(race.get(key)) is not int or race[key] != 1
                   for key in ('copy_calls', 'open_calls', 'close_calls', 'publication_calls'))):
        raise ValueError('Real no-replace collision and single-effect rollback/replay are required.')
    for fault in COPY_FAULTS:
        report = reports[fault]
        _report(report, wheel, trusted_hashes[fault], 'installed_first_save_controlled_fault_only', 'fault_case_passed', expected_public_tool_count)
        cases = _cases(report, FAULT_LABELS)
        original = report['original_native_copy_receipt']
        if (report.get('fault') != fault or report.get('actual_com_failure_injected') is not False
                or report.get('injection_applied') is not True or original['success'] is not True
                or original['native_call_returned'] is not True or original['pending_copy'] is not False
                or any(type(original[key]) is not int or original[key] != 0 for key in ('errors', 'warnings'))
                or cases[0]['job']['status'] != 'unknown' or cases[0]['job']['mutation']['phase'] != 'unresolved'
                or cases[0].get('replay_verified') is not True
                or cases[0]['hold_blocked_job']['error']['code'] != 'document_mutation_blocked'
                or cases[1].get('independent_native_clone_verified') is not True
                or cases[1].get('stage_file_retained') is not True
                or report['reconciliation']['status'] != 'unknown'
                or report['reconciliation']['mutation']['phase'] != 'reconciled'
                or type(report.get('recovery_reference_mapping')) is not list
                or len(report['recovery_reference_mapping']) != 41):
            raise ValueError('Every controlled fault requires original normal receipt, hold/replay and independent reconciliation.')
    return deepcopy(reports)
