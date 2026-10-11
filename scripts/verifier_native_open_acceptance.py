"""Passive same-wheel internal-to-public report gate; no native effect oracle.

Only detached report data is inspected. Passing this validator does not prove
CAD effects, replace runtime postconditions or accept historical native calls
for a different wheel/verifier. Expected labels and hashes come from the
trusted current verifier, never from the prior report itself.
"""

import json
import re


SCOPE = 'internal_native_open_resolved_v1'
MAX_CASES = 5000
WHEEL_FIELDS = ('git_sha', 'source_digest', 'package_version', 'wheel_sha256')
FINAL_GATES = ('fixtures_closed', 'baseline_restored', 'cleanup_confirmed')


def _finite_json(value):
    def validate(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError('Report JSON keys must be strings.')
            for child in item.values():
                validate(child)
        elif type(item) is list:
            for child in item:
                validate(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ValueError('Detached report values must be JSON types.')
    validate(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def _nonempty_string(value):
    return type(value) is str and bool(value.strip())


def _wheel(wheel):
    if type(wheel) is not dict:
        raise ValueError('An exact wheel identity mapping is required.')
    for key in WHEEL_FIELDS:
        if not _nonempty_string(wheel.get(key)):
            raise ValueError(f'Missing or untyped wheel identity: {key}.')
    for key, width in (('git_sha', 40), ('source_digest', 64), ('wheel_sha256', 64)):
        if re.fullmatch(r'[0-9a-fA-F]{' + str(width) + '}', wheel[key]) is None:
            raise ValueError(f'Invalid wheel identity digest: {key}.')


def _hashes(values):
    if type(values) is not dict or not values or len(values) > MAX_CASES:
        raise ValueError('A nonempty bounded exact verifier hash mapping is required.')
    if any(not _nonempty_string(key) or type(value) is not str
           or re.fullmatch(r'[0-9a-fA-F]{64}', value) is None for key, value in values.items()):
        raise ValueError('Verifier hashes must be named SHA256 hex strings.')


def _clear_flags(value):
    if 'error' in value and value['error'] is not None:
        raise ValueError('Report/case error prohibits acceptance.')
    for key, flag in value.items():
        # Only final report/case-level flags. A passed negative case can retain
        # failed response evidence and completed historical pending ledger rows.
        if key == 'lifecycle_hold' or key.startswith('pending') or key.endswith('_pending'):
            if flag is not False:
                raise ValueError(f'Unconfirmed final lifecycle flag: {key}.')


def validate_internal_report(prior, wheel, verifier_hashes, expected_labels):
    """Return a detached accepted report or raise ValueError before public CAD.

    No files, CAD/JobStore handles or processes are queried. This gate binds the
    exact internal case list, final fixture restoration, wheel and verifier.
    It deliberately allows result.status='failed' for passed negative cases.
    """
    try:
        if (type(expected_labels) is not list or not 1 <= len(expected_labels) <= MAX_CASES
                or any(not _nonempty_string(label) for label in expected_labels)
                or len(set(expected_labels)) != len(expected_labels)):
            raise ValueError('Trusted expected labels must be a nonempty unique bounded list.')
        if type(prior) is not dict:
            raise ValueError('An exact internal report mapping is required.')
        encoded = _finite_json(prior)
        _finite_json(wheel)
        _finite_json(verifier_hashes)
        if prior.get('scope') != SCOPE or prior.get('accepted') is not True:
            raise ValueError('Only an accepted internal native-open report can authorize public preflight.')
        if any(prior.get(key) is not True for key in FINAL_GATES):
            raise ValueError('Exact fixture closure, baseline restoration and cleanup gates are required.')
        _clear_flags(prior)
        _wheel(wheel)
        actual_wheel = prior.get('wheel')
        _wheel(actual_wheel)
        if any(actual_wheel[key] != wheel[key] for key in WHEEL_FIELDS):
            raise ValueError('Internal report belongs to a different wheel/source identity.')
        _hashes(verifier_hashes)
        actual_hashes = prior.get('verifier_hashes')
        _hashes(actual_hashes)
        if actual_hashes != verifier_hashes:
            raise ValueError('Internal report belongs to different verifier hashes.')
        cases = prior.get('cases')
        if type(cases) is not list or len(cases) != len(expected_labels):
            raise ValueError('The complete exact ordered internal case list is required.')
        for index, case in enumerate(cases):
            if (type(case) is not dict or type(case.get('label')) is not str
                    or case['label'] != expected_labels[index] or case.get('passed') is not True):
                raise ValueError('Every exact internal label must be passed=True in its expected order.')
            _clear_flags(case)
            if 'status' in case and case['status'] not in ('passed', 'succeeded'):
                raise ValueError('Explicit non-passed case status prohibits acceptance.')
            for flag in ('skipped', 'not_run', 'failed', 'unknown'):
                if flag in case and case[flag] is not False:
                    raise ValueError(f'Case flag prohibits acceptance: {flag}.')
        return json.loads(encoded)
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError('Malformed non-JSON acceptance evidence.') from exc
