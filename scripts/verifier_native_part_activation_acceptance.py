"""Finite same-wheel internal ACT gate before public dispatch; detached only."""

from verifier_native_part_activation import _json, verified_committed_part_activation


WHEEL_FIELDS = ('package_version', 'git_sha', 'source_digest', 'wheel_sha256')
KEYS = {'positive', 'already_active', 'stale', 'controlled_after_call'}
LABELS = {
    'positive': ['ACT-N1-positive', 'ACT-N2-replay-only', 'ACT-N5-owned-cleanup'],
    'already_active': ['ACT-N2-already-active-and-replay', 'ACT-N5-owned-cleanup'],
    'stale': ['ACT-N3-foreign', 'ACT-N3-configuration', 'ACT-N3-stale-before-activation', 'ACT-N5-owned-cleanup'],
    'controlled_after_call': ['ACT-N4-controlled-after-call-unknown-hold-replay', 'ACT-N5-owned-cleanup'],
}


def validate_internal_activation(reports, wheel, trusted_hashes):
    """Current driver supplies complete trusted hash inventories, never report keys."""
    _json(reports)
    _json(wheel)
    _json(trusted_hashes)
    if type(reports) is not dict or set(reports) != KEYS or set(trusted_hashes) != KEYS:
        raise ValueError('All four finite internal ACT reports are required.')
    for key, report in reports.items():
        scope = ('installed_native_part_activation_positive_only' if key == 'positive'
                 else 'installed_native_part_activation_case_only')
        flag = 'activation_positive_passed' if key == 'positive' else 'activation_case_passed'
        if (report.get('scope') != scope or report.get('phase') != 'terminal' or report.get(flag) is not True
                or report.get('accepted') is not False or report.get('error') is not None
                or not (report.get('retained_process') is None or report.get('retained_process') is False)
                or report.get('owned_documents') != [] or report.get('native_calls_live') is not False
                or report.get('baseline_restored') is not True or report.get('own_cleanup_verified') is not True
                or report.get('independent_native_readback_verified') is not True
                or report.get('package_origin_verified') is not True
                or report.get('metadata_catalog', {}).get('public_tool_count') != 75
                or report.get('metadata_catalog', {}).get('output_schemas_verified') is not True
                or type(report.get('original_baseline')) is not list or len(report['original_baseline']) != 3
                or type(report.get('original_application')) is not dict
                or set(report['original_application']) != {'user_control', 'visible', 'current_directory', 'search_folders'}
                or type(report.get('captures')) is not list or not report['captures']
                or any(row.get('status') != 'returned' for row in report['captures'])
                or _json(report.get('original_baseline')) != _json(report.get('restored_baseline'))
                or _json(report.get('original_application')) != _json(report.get('restored_application'))
                or any(report.get('wheel', {}).get(field) != wheel[field] for field in WHEEL_FIELDS)
                or report.get('verifier_hashes') != trusted_hashes[key]):
            raise ValueError('Exact terminal installed evidence, release/cleanup and current helper hashes are required.')
        hashes = trusted_hashes[key]
        if (type(hashes) is not dict or not hashes
                or any(type(name) is not str or not name or type(value) is not str or len(value) != 64
                       or any(char not in '0123456789abcdef' for char in value) for name, value in hashes.items())):
            raise ValueError('The full current helper hash inventory is required.')
        cases = report.get('cases')
        if (type(cases) is not list or [case.get('label') for case in cases] != LABELS[key]
                or any(case.get('passed') is not True for case in cases)):
            raise ValueError('Every finite ordered case must be passed; partial/skipped is not acceptance.')
        if key != 'positive' and report.get('case') != key:
            raise ValueError('The exact selected case must match its report.')
        if key in ('positive', 'already_active'):
            if not verified_committed_part_activation(report['job']):
                raise ValueError('Committed activation/no-op protocol is unconfirmed.')
            if report['job']['result']['value']['already_active'] is not (key == 'already_active'):
                raise ValueError('Positive activation and already-active no-op are separate required cases.')
        if key == 'stale':
            job = report['job']
            if job['status'] != 'failed' or job['error']['code'] != 'stale_revision' or 'mutation' in job:
                raise ValueError('Real post-prepare change must be refused before mutation preparation.')
            for case, code in zip(cases[:2], ('document_not_open', 'configuration_not_found')):
                job = case['job']
                if (job['status'] != 'failed' or 'mutation' in job or job['error']['code'] != code
                        or job['error'].get('requires_reconciliation') is True):
                    raise ValueError('Foreign document/configuration are prewrite refusals.')
            if _json(report['independent_before']) == _json(report['independent_before_after_owned_rename']):
                raise ValueError('Both independent states must prove the actual post-prepare change.')
        if key == 'controlled_after_call':
            original, job, reconciled = report['original_activation_receipt'], report['job'], report['reconciliation']
            if (report.get('actual_com_failure_injected') is not False or report.get('injection_applied') is not True
                    or original['native_call_attempted'] is not True or original['native_call_returned'] is not True
                    or original['pending_activation'] is not False or type(original['native_error']) is not int
                    or original['native_error'] not in (0, 2)
                    or job['status'] != 'unknown' or job['mutation']['phase'] != 'unresolved'
                    or report['held_job']['error']['code'] != 'document_mutation_blocked'
                    or report['released_execution_guard']['released'] is not True
                    or report['released_execution_guard']['selection_preserved'] is not True
                    or reconciled['operation_id'] != job['operation_id'] or reconciled['status'] != 'unknown'
                    or reconciled['mutation']['phase'] != 'reconciled'
                    or reconciled['mutation']['reconciliation']['resolution'] != 'accept_current_state'):
                raise ValueError('Controlled fault needs actual original return, hold/no retry and exact terminal reconciliation.')
    return dict(internal_activation_cases_verified=True, public_activation_accepted=False,
                whole_activation_accepted=False, wheel={field: wheel[field] for field in WHEEL_FIELDS})
