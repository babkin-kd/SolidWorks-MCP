"""Same-wheel report gate only; synthetic data does not establish CAD success."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest


PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_native_open_acceptance.py'
spec = importlib.util.spec_from_file_location('_native_open_acceptance_test', PATH)
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)

LABELS = ['part_config2_open', 'request_replay', 'stale_refused', 'assembly_borrowed_refs']
WHEEL = dict(git_sha='a' * 40, source_digest='b' * 64, package_version='2.0.0.dev86',
             wheel_sha256='c' * 64)
HASHES = {'verify_native_document_open.py': 'd' * 64, 'verifier_native_open.py': 'e' * 64}


def report():
    return dict(scope='internal_native_open_resolved_v1', accepted=True,
        wheel=deepcopy(WHEEL), verifier_hashes=deepcopy(HASHES),
        fixtures_closed=True, baseline_restored=True, cleanup_confirmed=True,
        cases=[dict(label=label, passed=True, result={'status': 'succeeded'}) for label in LABELS])


def validate(prior, **updates):
    kwargs = dict(wheel=deepcopy(WHEEL), verifier_hashes=deepcopy(HASHES), expected_labels=LABELS.copy())
    kwargs.update(updates)
    return helper.validate_internal_report(prior, **kwargs)


def test_exact_accepted_report_returns_detached_copy():
    original = report()
    result = validate(original)
    assert result == original and result is not original
    result['cases'][0]['passed'] = False
    assert original['cases'][0]['passed'] is True


def test_passed_negative_case_retains_failed_response_and_completed_pending_history():
    value = report()
    value['cases'][2]['result'] = dict(status='failed', error={'code': 'stale_revision'},
        mutation={'verification': {'outcome': 'rolled_back', 'native_steps': [
            {'name': 'open_native', 'phase': 'pending'}, {'name': 'open_native', 'phase': 'returned'}]}})
    assert validate(value) == value


@pytest.mark.parametrize('scope', [None, 'public_native_open_resolved_v1',
    'internal_native_close_clean_v1', True, ''])
def test_scope_cannot_be_public_foreign_or_missing(scope):
    value = report()
    value['scope'] = scope
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('key', ['accepted', 'fixtures_closed', 'baseline_restored', 'cleanup_confirmed'])
@pytest.mark.parametrize('value', [False, None, 0, 1, 'true'])
def test_acceptance_and_final_gates_require_exact_true_not_coercion(key, value):
    candidate = report()
    candidate[key] = value
    with pytest.raises(ValueError): validate(candidate)


@pytest.mark.parametrize('key', ['accepted', 'fixtures_closed', 'baseline_restored', 'cleanup_confirmed',
                              'wheel', 'verifier_hashes', 'cases'])
def test_missing_final_fields_never_default_to_acceptance(key):
    value = report()
    del value[key]
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('key', helper.WHEEL_FIELDS)
def test_each_stale_wheel_identity_rejects_before_public(key):
    value = report()
    value['wheel'][key] = ('f' * (40 if key == 'git_sha' else 64)
                           if key != 'package_version' else '2.0.0.dev_old')
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('target', ['prior', 'trusted'])
@pytest.mark.parametrize('key', helper.WHEEL_FIELDS)
@pytest.mark.parametrize('invalid', [None, False, 0, 1, '', [], {}])
def test_wheel_fields_are_required_nonempty_typed_strings(target, key, invalid):
    value, wheel = report(), deepcopy(WHEEL)
    if target == 'prior': value['wheel'][key] = invalid
    else: wheel[key] = invalid
    with pytest.raises(ValueError): validate(value, wheel=wheel)


@pytest.mark.parametrize('target', ['prior', 'trusted'])
def test_missing_wheel_field_on_either_side_rejected(target):
    value, wheel = report(), deepcopy(WHEEL)
    if target == 'prior': del value['wheel']['git_sha']
    else: del wheel['git_sha']
    with pytest.raises(ValueError): validate(value, wheel=wheel)


@pytest.mark.parametrize('mutation', ['stale', 'missing', 'extra', 'empty', 'not_hash',
                                     'number', 'boolean', 'short', 'missing_name'])
def test_verifier_hashes_need_exact_sha256_mapping(mutation):
    value = report()
    hashes = value['verifier_hashes']
    if mutation == 'stale': hashes['verifier_native_open.py'] = 'f' * 64
    if mutation == 'missing': del hashes['verifier_native_open.py']
    if mutation == 'extra': hashes['unexpected.py'] = 'f' * 64
    if mutation == 'empty': value['verifier_hashes'] = {}
    if mutation == 'not_hash': hashes['verifier_native_open.py'] = 'g' * 64
    if mutation == 'number': hashes['verifier_native_open.py'] = 0
    if mutation == 'boolean': hashes['verifier_native_open.py'] = False
    if mutation == 'short': hashes['verifier_native_open.py'] = 'f' * 63
    if mutation == 'missing_name': hashes[''] = 'f' * 64
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('invalid', [{}, None, [], {'name': True}, {'': 'f' * 64},
                                   {'name': float('nan')}, {'name': 'not-a-sha256'}])
def test_invalid_trusted_hash_mapping_also_rejected(invalid):
    with pytest.raises(ValueError): validate(report(), verifier_hashes=invalid)


@pytest.mark.parametrize('invalid', [[], None, (), 'one_label', [None], [True], [0], [''], ['  '],
                                   ['duplicate', 'duplicate'], [f'case_{i}' for i in range(5001)]])
def test_expected_labels_are_trusted_nonempty_unique_bounded_list(invalid):
    with pytest.raises(ValueError): validate(report(), expected_labels=invalid)


@pytest.mark.parametrize('mutation', ['empty', 'missing', 'extra', 'reordered', 'duplicate', 'foreign',
                                     'wrong_type', 'tuple', 'missing_label', 'missing_passed'])
def test_case_labels_and_count_must_match_the_exact_manifest(mutation):
    value = report()
    cases = value['cases']
    if mutation == 'empty': cases.clear()
    if mutation == 'missing': cases.pop()
    if mutation == 'extra': cases.append(dict(label='not_expected', passed=True))
    if mutation == 'reordered': cases.reverse()
    if mutation == 'duplicate': cases[1] = deepcopy(cases[0])
    if mutation == 'foreign': cases[0]['label'] = 'not_expected'
    if mutation == 'wrong_type': cases[0] = None
    if mutation == 'tuple': value['cases'] = tuple(cases)
    if mutation == 'missing_label': del cases[0]['label']
    if mutation == 'missing_passed': del cases[0]['passed']
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('invalid', [False, None, 0, 1, 'passed'])
def test_case_passed_requires_exact_true(invalid):
    value = report()
    value['cases'][0]['passed'] = invalid
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('status', ['skipped', 'not_run', 'failed', 'unknown', 'running', None, True])
def test_explicit_nonpassed_case_status_rejects_even_with_passed_true(status):
    value = report()
    value['cases'][0]['status'] = status
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('flag', ['skipped', 'not_run', 'failed', 'unknown'])
@pytest.mark.parametrize('invalid', [True, 0, None])
def test_skip_or_unknown_case_flags_are_exact_false_or_absent(flag, invalid):
    value = report()
    value['cases'][0][flag] = invalid
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('level', ['report', 'case'])
@pytest.mark.parametrize('error', ['native failure', {}, False, '', ['failure']])
def test_report_or_case_error_prevents_acceptance(level, error):
    value = report()
    target = value if level == 'report' else value['cases'][0]
    target['error'] = error
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('level', ['report', 'case'])
@pytest.mark.parametrize('flag', ['lifecycle_hold', 'pending', 'pending_open', 'pending_activation',
                                'pending_cleanup', 'native_call_pending'])
@pytest.mark.parametrize('invalid', [True, None, 0, 'false'])
def test_final_hold_or_pending_flags_do_not_use_truthiness(level, flag, invalid):
    value = report()
    target = value if level == 'report' else value['cases'][0]
    target[flag] = invalid
    with pytest.raises(ValueError): validate(value)


def test_explicit_clear_flags_and_error_none_are_accepted():
    value = report()
    value.update(error=None, lifecycle_hold=False, pending_open=False)
    value['cases'][0].update(error=None, pending_activation=False, status='passed', skipped=False)
    assert validate(value) == value


@pytest.mark.parametrize('invalid', [None, [], (), 1, False])
def test_malformed_report_top_level_raises_value_error(invalid):
    with pytest.raises(ValueError): validate(invalid)


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), object(), ('not', 'JSON'), {1: 'bad key'}])
def test_nested_nonfinite_or_nonjson_report_data_rejected(invalid):
    value = report()
    value['cases'][0]['result']['invalid'] = invalid
    with pytest.raises(ValueError): validate(value)


def test_validator_is_passive_does_not_access_paths_or_modify_inputs(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('A passive validator cannot read verifier/CAD files.')
    monkeypatch.setattr(Path, 'read_text', forbidden)
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    value, wheel, hashes, labels = report(), deepcopy(WHEEL), deepcopy(HASHES), LABELS.copy()
    snapshots = deepcopy((value, wheel, hashes, labels))
    helper.validate_internal_report(value, wheel, hashes, labels)
    assert (value, wheel, hashes, labels) == snapshots
