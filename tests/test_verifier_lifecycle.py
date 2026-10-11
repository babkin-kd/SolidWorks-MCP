"""Full-census native-save release proof; no COM, SDK process or CAD access."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest


HELPER = Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_lifecycle.py'
spec = importlib.util.spec_from_file_location('_native_save_lifecycle_test', HELPER)
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)

MODEL_GUARD = dict(original_state=0, locked_state=2, released_state=0)


def guard(count):
    return dict(scope='application_model_mutation_guard_v1',
                original_command_in_progress=False, acquired=True, released=True,
                selection_preserved=True, model_guards=[dict(MODEL_GUARD) for _ in range(count)])


def checkpoint(*, census_count=4, guard_count=4, operation='document.save_native',
               scope='native_document_current_file_save_v1'):
    arguments = dict(request_id='save-request', document_id='doc_0', configuration='Основная',
                     expected_revision='revision', timeout_s=0.)
    tool = helper.ToolSpec(operation, True)
    payload = tool.payload(arguments)
    owner = helper.VerifierSupervisor(object(), tool_specs={'save': tool}, journal_reader=lambda: [])
    owner._fresh = True
    owner.requests[arguments['request_id']] = helper.TrackedRequest(
        'save', arguments['request_id'], arguments, tool, deepcopy(payload),
        operation_id='save-operation', send_attempts=1)
    row = dict(operation_id='save-operation', request_id='save-request', operation=operation,
               payload=payload, status='succeeded', error=None, result={'verified': True},
               mutation=dict(phase='committed', before_state=dict(
                   _mutation_effect_scope='application', scope=scope,
                   semantic=dict(documents=[{'document_id': f'doc_{index}'} for index in range(census_count)])),
                   verification=dict(outcome='committed', evidence=dict(execution_guard=guard(guard_count)))))
    return owner, row


def decision(owner, row):
    owner._bind([row])
    return owner._decide([row])


def test_four_saved_baseline_models_require_four_released_guards():
    owner, row = checkpoint()
    result = decision(owner, row)
    assert result.child_can_close and result.fixture_can_cleanup and result.reasons == ()


@pytest.mark.parametrize('guard_count', [0, 1, 3, 5])
def test_incomplete_or_excess_guard_census_retains_fixtures(guard_count):
    owner, row = checkpoint(guard_count=guard_count)
    result = decision(owner, row)
    assert result.child_can_close and not result.fixture_can_cleanup
    assert 'UI release unconfirmed' in result.reasons


@pytest.mark.parametrize('documents', [
    [{'document_id': 'doc_0'}] * 4,
    [{'document_id': 'doc_0'}, {'document_id': 'doc_1'}, {'document_id': 'doc_2'}, {}],
    [{'document_id': 'doc_0'}, {'document_id': 'doc_1'}, {'document_id': 'doc_2'}, {'document_id': ''}],
    [{'document_id': 'doc_0'}, {'document_id': 'doc_1'}, {'document_id': 'doc_2'}, {'document_id': 4}],
    [{'document_id': 'doc_0'}, {'document_id': 'doc_1'}, {'document_id': 'doc_2'}, 'not a record'],
    None, {}, [],
])
def test_invalid_or_duplicate_document_census_does_not_prove_release(documents):
    owner, row = checkpoint()
    row['mutation']['before_state']['semantic']['documents'] = deepcopy(documents)
    result = decision(owner, row)
    assert result.child_can_close and not result.fixture_can_cleanup
    assert 'UI release unconfirmed' in result.reasons


def test_missing_save_census_cannot_fall_back_to_single_model_acceptance():
    owner, row = checkpoint(guard_count=1)
    del row['mutation']['before_state']['semantic']['documents']
    assert not decision(owner, row).fixture_can_cleanup


@pytest.mark.parametrize('operation,scope', [
    ('document.save_native', 'other_scope'),
    ('document.save_native', None),
    ('dimension.set_value', 'native_document_current_file_save_v1'),
    ('document.save_native_alias', 'native_document_current_file_save_v1'),
])
def test_only_exact_save_operation_and_scope_authorize_full_census(operation, scope):
    owner, row = checkpoint(operation=operation, scope=scope)
    result = decision(owner, row)
    assert result.child_can_close and not result.fixture_can_cleanup
    assert 'UI release unconfirmed' in result.reasons


def test_default_guard_policy_still_rejects_multiple_models():
    assert not helper.released_execution_guard(guard(4))
    assert helper.released_execution_guard(guard(1))


@pytest.mark.parametrize('count', [1, 4, 1001, 5000])
def test_save_accepts_exact_complete_census_through_its_document_budget(count):
    owner, row = checkpoint(census_count=count, guard_count=count)
    assert decision(owner, row).fixture_can_cleanup


def test_over_budget_save_census_is_not_release_proof():
    owner, row = checkpoint(census_count=5001, guard_count=5001)
    result = decision(owner, row)
    assert result.child_can_close and not result.fixture_can_cleanup


@pytest.mark.parametrize('expected_count', [0, -1, 5001, True, 4., '4', None])
def test_guard_requires_explicit_integer_expected_count_within_budget(expected_count):
    assert not helper.released_execution_guard(guard(4), expected_model_count=expected_count)


@pytest.mark.parametrize('change', ['locked_last_model', 'boolean_release_state',
                                  'unreleased_application', 'selection_not_preserved'])
def test_complete_guard_count_does_not_substitute_actual_release_evidence(change):
    owner, row = checkpoint()
    evidence = row['mutation']['verification']['evidence']['execution_guard']
    if change == 'locked_last_model':
        evidence['model_guards'][-1]['released_state'] = 2
    elif change == 'boolean_release_state':
        evidence['model_guards'][-1]['released_state'] = False
    elif change == 'unreleased_application':
        evidence['released'] = False
    else:
        evidence['selection_preserved'] = False
    assert not decision(owner, row).fixture_can_cleanup


def test_other_operation_retains_original_single_model_policy():
    owner, row = checkpoint(operation='dimension.set_value', scope='part_dimension_values_v1', guard_count=1)
    assert decision(owner, row).fixture_can_cleanup
