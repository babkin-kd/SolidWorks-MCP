"""Malformed open evidence never permits cleanup; pure JSON/fakes only."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest


PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_native_open.py'
spec = importlib.util.spec_from_file_location('_native_open_evidence_test', PATH)
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


def before(count=2):
    return dict(scope='native_document_open_resolved_v1', native_file_id='native_file_exact',
        source=dict(path='C:/Контрольная деталь.SLDPRT', bytes=23, sha256='abc',
                    identity=[1, 2], mtime_ns=3, ctime_ns=4),
        semantic={'documents': [{'document_id': f'doc_{index}'} for index in range(count)],
                  'active_document_id': 'doc_0' if count else None})


def guard(count=2, phase=False):
    return dict(scope='application_document_open_guard_v1', original_command_in_progress=False,
        acquired=True, released=True, selection_preserved=True,
        model_guards=[dict(original_state=0, locked_state=2, released_state=0) for _ in range(count)],
        baseline_document_ids=[f'doc_{index}' for index in range(count)],
        activation_ui_release=dict(attempted=phase, verified=phase))


def receipt(**updates):
    return dict(native_call_attempted=True, native_call_returned=True, pending_open=False,
                returned_model_retained=True, returned_new_identity=True, acknowledgement_valid=True,
                errors=0, warnings=0) | updates


def ledger(*, count=2, outcome='committed', extra=(), returned=None):
    baseline = before(count)
    pairs = [('open_native', dict(native_file_id=baseline['native_file_id'], source=deepcopy(baseline['source'])),
              receipt() if returned is None else returned)] + list(extra)
    steps = []
    for name, pending, result in pairs:
        steps.append(dict(sequence=len(steps) + 1, name=name, phase='pending', evidence=pending))
        steps.append(dict(sequence=len(steps) + 1, name=name, phase='returned', evidence=result))
    return dict(outcome=outcome, evidence={}, native_steps=steps), baseline


def release(count=2):
    return ('release_baseline_ui', {'baseline_document_ids': [f'doc_{index}' for index in range(count)]}, {'verified': True})


def activation(name='activate_native', *, attempted=True, code=0, document_id='doc_0'):
    return (name, {'document_id': document_id},
            dict(native_call_attempted=attempted, native_call_returned=attempted, native_error=code))


def cleanup(count=2):
    impact = dict(target_document_id='doc_new', native_name='Контрольная деталь.SLDPRT',
        retiring_document_ids=['doc_hidden', 'doc_new'], hidden_document_ids=['doc_hidden'],
        survivor_document_ids=[f'doc_{index}' for index in range(count)], retiring_window_handles=[2 ** 40],
        active_after_document_id='doc_0' if count else None, policy='require_clean', data_unload_claimed=False)
    return ('rollback_close_native', {'impact': impact},
            {'native_call_returned': True, 'acknowledgement_valid': True})


@pytest.mark.parametrize('count', [0, 1, 2, 4999])
def test_exact_guard_count_accepts_zero_baseline_and_budget_boundary(count):
    assert helper.released_open_guard(guard(count), before(count)) is True


def test_verified_activation_ui_phase_requires_nonempty_baseline():
    assert helper.released_open_guard(guard(2, True), before()) is True
    assert helper.released_open_guard(guard(0, True), before(0)) is False


@pytest.mark.parametrize('scope', ['application_document_create_guard_v1',
                                  'application_document_close_guard_v1', 'application_model_mutation_guard_v1', None])
def test_other_guard_scope_never_substitutes_open_scope(scope):
    value = guard()
    value['scope'] = scope
    assert helper.released_open_guard(value, before()) is False


@pytest.mark.parametrize('scope', ['native_document_close_clean_v1', 'new_empty_part_document_v1', None])
def test_wrong_before_scope_rejects_guard_and_steps(scope):
    value, baseline = ledger()
    baseline['scope'] = scope
    assert helper.released_open_guard(guard(), baseline) is False
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('key', ['original_command_in_progress', 'acquired', 'released', 'selection_preserved'])
@pytest.mark.parametrize('value', [None, 0, 1, 'true'])
def test_guard_booleans_are_exact_not_truthy(key, value):
    candidate = guard()
    candidate[key] = value
    assert helper.released_open_guard(candidate, before()) is False


@pytest.mark.parametrize('mutation', ['extra', 'missing', 'model_missing', 'model_extra', 'model_bool',
                                     'model_unreleased', 'ids_reordered', 'ids_tuple', 'ids_duplicate',
                                     'release_half', 'release_int', 'release_extra'])
def test_incomplete_or_extra_guard_evidence_fails(mutation):
    candidate = guard()
    if mutation == 'extra': candidate['retired'] = True
    if mutation == 'missing': del candidate['released']
    if mutation == 'model_missing': candidate['model_guards'].pop()
    if mutation == 'model_extra': candidate['model_guards'].append(dict(candidate['model_guards'][0]))
    if mutation == 'model_bool': candidate['model_guards'][0]['original_state'] = False
    if mutation == 'model_unreleased': candidate['model_guards'][0]['released_state'] = 2
    if mutation == 'ids_reordered': candidate['baseline_document_ids'].reverse()
    if mutation == 'ids_tuple': candidate['baseline_document_ids'] = tuple(candidate['baseline_document_ids'])
    if mutation == 'ids_duplicate': candidate['baseline_document_ids'][1] = candidate['baseline_document_ids'][0]
    if mutation == 'release_half': candidate['activation_ui_release']['attempted'] = True
    if mutation == 'release_int': candidate['activation_ui_release'] = dict(attempted=0, verified=0)
    if mutation == 'release_extra': candidate['activation_ui_release']['ignored'] = False
    assert helper.released_open_guard(candidate, before()) is False


@pytest.mark.parametrize('documents', [None, {}, (), [None], [{}], [{'document_id': ''}],
    [{'document_id': ' '}], [{'document_id': 1}], [{'document_id': 'same'}] * 2,
    [{'document_id': f'doc_{index}'} for index in range(5000)]])
def test_malformed_before_documents_rejects_both_predicates(documents):
    value, baseline = ledger()
    baseline['semantic']['documents'] = documents
    assert helper.released_open_guard(guard(), baseline) is False
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('count', [0, 2])
def test_normally_returned_owned_open_pair_committed(count):
    value, baseline = ledger(count=count)
    assert helper.verified_open_native_steps(value, baseline) is True


@pytest.mark.parametrize('outcome', [None, 'not_started', 'unresolved', 'reconciled', False, 1])
def test_only_explicit_final_outcomes_admissible(outcome):
    value, baseline = ledger(outcome=outcome)
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('missing', ['outcome', 'evidence', 'native_steps'])
def test_no_default_ledger_or_outcome_proof(missing):
    value, baseline = ledger()
    del value[missing]
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('returned', [
    receipt(returned_model_retained=False, returned_new_identity=False, errors=2),
    receipt(acknowledgement_valid=False, returned_model_retained=False, returned_new_identity=False, errors=None, warnings=None),
    receipt(acknowledgement_valid=False, warnings=None),
    receipt(native_call_attempted=False, native_call_returned=False, returned_model_retained=False,
            returned_new_identity=False, acknowledgement_valid=False, errors=None, warnings=None)])
def test_null_malformed_or_precall_abort_only_with_explicit_rolled_back(returned):
    value, baseline = ledger(outcome='rolled_back', returned=returned)
    assert helper.verified_open_native_steps(value, baseline) is True
    value['outcome'] = 'committed'
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('key', ['native_call_attempted', 'native_call_returned', 'pending_open',
                                 'returned_model_retained', 'returned_new_identity', 'acknowledgement_valid'])
@pytest.mark.parametrize('invalid', [0, 1, None, 'false'])
def test_open_flags_require_exact_booleans(key, invalid):
    value, baseline = ledger(returned=receipt(**{key: invalid}), outcome='rolled_back')
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('key', ['errors', 'warnings'])
@pytest.mark.parametrize('invalid', [True, False, -1, 2 ** 31, 0., '0', float('nan')])
def test_error_outputs_are_bounded_exact_integers_or_explicit_null(key, invalid):
    value, baseline = ledger(returned=receipt(**{key: invalid}), outcome='rolled_back')
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('updates', [dict(pending_open=True), dict(native_call_returned=False),
    dict(native_call_attempted=False), dict(returned_model_retained=False), dict(errors=None), dict(warnings=None)])
def test_inconsistent_attempt_ack_or_retention_fails_even_rolled_back(updates):
    value, baseline = ledger(returned=receipt(**updates), outcome='rolled_back')
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('mutation', ['pending_only', 'returned_first', 'sequence_bool', 'sequence_gap',
    'unknown_name', 'first_not_open', 'name_mismatch', 'phase_mismatch', 'duplicate',
    'step_extra', 'pending_extra', 'returned_extra', 'wrong_file', 'wrong_source', 'bool_source', 'tuple_steps'])
def test_exact_step_shape_order_pair_and_source_binding(mutation):
    value, baseline = ledger()
    steps = value['native_steps']
    if mutation == 'pending_only': steps.pop()
    if mutation == 'returned_first': steps.reverse()
    if mutation == 'sequence_bool': steps[0]['sequence'] = True
    if mutation == 'sequence_gap': steps[1]['sequence'] = 3
    if mutation == 'unknown_name': steps[0]['name'] = steps[1]['name'] = 'save_native'
    if mutation == 'first_not_open': steps[0]['name'] = steps[1]['name'] = 'activate_native'
    if mutation == 'name_mismatch': steps[1]['name'] = 'activate_native'
    if mutation == 'phase_mismatch': steps[0]['phase'] = 'returned'
    if mutation == 'duplicate':
        steps.extend(deepcopy(steps))
        for index, step in enumerate(steps): step['sequence'] = index + 1
    if mutation == 'step_extra': steps[0]['ignored'] = True
    if mutation == 'pending_extra': steps[0]['evidence']['ignored'] = True
    if mutation == 'returned_extra': steps[1]['evidence']['ignored'] = True
    if mutation == 'wrong_file': steps[0]['evidence']['native_file_id'] = 'other'
    if mutation == 'wrong_source': steps[0]['evidence']['source']['bytes'] = 99
    if mutation == 'bool_source':
        baseline['source']['bytes'] = 0
        steps[0]['evidence']['source']['bytes'] = False
    if mutation == 'tuple_steps': value['native_steps'] = tuple(steps)
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('code', [0, 2])
def test_normal_activation_after_verified_release(code):
    value, baseline = ledger(extra=[release(), activation(code=code)])
    assert helper.verified_open_native_steps(value, baseline) is True


def test_empty_baseline_activation_needs_no_release():
    value, baseline = ledger(count=0, extra=[activation(document_id='doc_new')])
    assert helper.verified_open_native_steps(value, baseline) is True


@pytest.mark.parametrize('extra', [
    [cleanup()], [cleanup(), release(), activation('rollback_activate_native')],
    [release(), activation(attempted=False, code=None), cleanup(), activation('rollback_activate_native')],
    [release(), activation(), cleanup()]])
def test_rollback_sequences_are_completed_one_shot_pairs(extra):
    value, baseline = ledger(outcome='rolled_back', extra=extra)
    assert helper.verified_open_native_steps(value, baseline) is True
    value['outcome'] = 'committed'
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('extra', [
    [activation()], [release(), release()], [release(), activation(), activation()],
    [release(), activation(code=True)], [release(), activation(code=7)],
    [release(), activation(attempted=False, code=None)],
    [release(), activation('rollback_activate_native')],
    [cleanup(), release(), activation()],
    [('release_baseline_ui', {'baseline_document_ids': ['foreign']}, {'verified': True})],
    [('release_baseline_ui', {'baseline_document_ids': ['doc_0', 'doc_1']}, {'verified': 1})],
    [('rollback_close_native', {'impact': {'target_document_id': 'doc_new'}},
      {'native_call_returned': True, 'acknowledgement_valid': False})]])
def test_bad_activation_release_or_cleanup_evidence_rejected(extra):
    value, baseline = ledger(extra=extra)
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('extra', [[release()], [activation('rollback_activate_native', document_id='foreign')]])
def test_empty_baseline_disallows_release_and_rollback_activation(extra):
    value, baseline = ledger(count=0, outcome='rolled_back', extra=extra)
    assert helper.verified_open_native_steps(value, baseline) is False


def test_malformed_or_null_open_receipt_cannot_grant_following_native_steps():
    value, baseline = ledger(outcome='rolled_back', returned=receipt(returned_model_retained=False,
        returned_new_identity=False, errors=2), extra=[cleanup()])
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('value', [None, [], {}, {'outcome': 'committed'}, float('nan')])
def test_malformed_top_level_returns_false_without_throwing(value):
    assert helper.released_open_guard(value, before()) is False
    assert helper.verified_open_native_steps(value, before()) is False
    assert helper.released_open_guard(guard(), value) is False
    assert helper.verified_open_native_steps(ledger()[0], value) is False


def test_nonfinite_or_nonjson_evidence_does_not_pass_finite_source_binding():
    value, baseline = ledger()
    value['evidence']['not_finite'] = float('inf')
    assert helper.verified_open_native_steps(value, baseline) is False
    value['evidence']['not_finite'] = object()
    assert helper.verified_open_native_steps(value, baseline) is False


def busy_guard(count=2):
    return guard(count) | dict(original_command_in_progress=True, acquired=False,
                               released=False, selection_preserved=(count == 0), model_guards=[])


def test_raced_busy_open_has_separate_untouched_gate_not_a_release_claim():
    candidate, baseline = busy_guard(), before()
    assert helper.untouched_busy_open_guard(candidate, baseline) is True
    assert helper.released_open_guard(candidate, baseline) is False
    assert helper.untouched_busy_open_guard(guard(), baseline) is False


@pytest.mark.parametrize('key,value', [
    ('scope', 'application_model_mutation_guard_v1'), ('acquired', True), ('released', True),
    ('original_command_in_progress', False), ('original_command_in_progress', 1),
    ('selection_preserved', True), ('selection_preserved', 0), ('model_guards', ()),
    ('model_guards', [dict(original_state=0, locked_state=2, released_state=0)]),
    ('baseline_document_ids', ['doc_1', 'doc_0']),
    ('activation_ui_release', dict(attempted=True, verified=True)),
    ('activation_ui_release', dict(attempted=0, verified=0))])
def test_busy_gate_cannot_borrow_native_writes_release_or_foreign_shape(key, value):
    candidate = busy_guard()
    candidate[key] = value
    assert helper.untouched_busy_open_guard(candidate, before()) is False


@pytest.mark.parametrize('malformed', [None, [], {}, dict(scope='native_document_close_clean_v1')])
def test_busy_gate_requires_complete_current_open_baseline(malformed):
    assert helper.untouched_busy_open_guard(busy_guard(), malformed) is False


@pytest.mark.parametrize('count', [0, 2])
def test_busy_selection_is_exact_vacuous_empty_or_nonempty_baseline(count):
    candidate, baseline = busy_guard(count), before(count)
    assert helper.untouched_busy_open_guard(candidate, baseline) is True
    candidate['selection_preserved'] = not candidate['selection_preserved']
    assert helper.untouched_busy_open_guard(candidate, baseline) is False


@pytest.mark.parametrize('count', [0, 2])
def test_actual_busy_open_guard_shape_matches_strict_prewrite_predicate(count):
    from types import SimpleNamespace
    from solidworks_mcp.application_open_guard import ApplicationOpenGuard
    from solidworks_mcp.jobs import ExecutionFailure
    baseline = before(count)
    ids = [row['document_id'] for row in baseline['semantic']['documents']]
    value = ApplicationOpenGuard(SimpleNamespace(CommandInProgress=True),
        [object() for _ in ids], lambda *args: pytest.fail('Busy guard cannot enter selection.'), ids)
    with pytest.raises(ExecutionFailure) as error:
        value.__enter__()
    assert error.value.code == 'application_busy' and error.value.uncertain is False
    assert helper.untouched_busy_open_guard(value.evidence, baseline) is True
    assert helper.released_open_guard(value.evidence, baseline) is False


@pytest.mark.parametrize('key,invalid', [('native_call_returned', False), ('native_call_returned', 1),
                                      ('acknowledgement_valid', False), ('acknowledgement_valid', 1)])
def test_rollback_close_requires_exact_normal_and_valid_ack(key, invalid):
    value, baseline = ledger(outcome='rolled_back', extra=[cleanup()])
    value['native_steps'][-1]['evidence'][key] = invalid
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('extra', [
    [cleanup(), cleanup()], [cleanup(), release(), activation('rollback_activate_native', document_id='foreign')],
    [release(), cleanup(), activation(), activation('rollback_activate_native')]])
def test_rollback_duplicate_or_out_of_order_activation_never_passes(extra):
    value, baseline = ledger(outcome='rolled_back', extra=extra)
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('malformed', [{1: 'numeric JSON key'}, ('not', 'JSON array')])
def test_nested_source_json_does_not_coerce_keys_or_collections(malformed):
    value, baseline = ledger()
    baseline['source']['malformed'] = malformed
    value['native_steps'][0]['evidence']['source']['malformed'] = deepcopy(malformed)
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('count', [0, 2])
def test_strict_owned_cleanup_impact_accepts_zero_or_exact_survivors(count):
    value, baseline = ledger(count=count, outcome='rolled_back', extra=[cleanup(count)])
    assert helper.verified_open_native_steps(value, baseline) is True


@pytest.mark.parametrize('mutation', ['extra', 'missing', 'target_foreign', 'target_bool', 'name_empty',
    'retiring_empty', 'retiring_duplicate', 'retiring_borrowed', 'hidden_missing', 'hidden_extra',
    'survivors_missing', 'survivors_reordered', 'policy_dirty', 'unload_int', 'active_foreign',
    'active_bool', 'handles_bool', 'handles_zero', 'handles_negative', 'handles_duplicate',
    'handles_tuple', 'handles_int64_overflow', 'handles_budget', 'retiring_budget'])
def test_rollback_pending_impact_cannot_authorize_foreign_or_untyped_retirement(mutation):
    value, baseline = ledger(outcome='rolled_back', extra=[cleanup()])
    impact = value['native_steps'][-2]['evidence']['impact']
    if mutation == 'extra': impact['ignored'] = True
    if mutation == 'missing': del impact['native_name']
    if mutation == 'target_foreign': impact['target_document_id'] = 'foreign'
    if mutation == 'target_bool': impact['target_document_id'] = True
    if mutation == 'name_empty': impact['native_name'] = '  '
    if mutation == 'retiring_empty': impact['retiring_document_ids'] = []
    if mutation == 'retiring_duplicate': impact['retiring_document_ids'].append('doc_new')
    if mutation == 'retiring_borrowed': impact['retiring_document_ids'].append('doc_0'); impact['hidden_document_ids'].append('doc_0')
    if mutation == 'hidden_missing': impact['hidden_document_ids'] = []
    if mutation == 'hidden_extra': impact['hidden_document_ids'].append('foreign')
    if mutation == 'survivors_missing': impact['survivor_document_ids'].pop()
    if mutation == 'survivors_reordered': impact['survivor_document_ids'].reverse()
    if mutation == 'policy_dirty': impact['policy'] = 'discard_owned'
    if mutation == 'unload_int': impact['data_unload_claimed'] = 0
    if mutation == 'active_foreign': impact['active_after_document_id'] = 'foreign'
    if mutation == 'active_bool': impact['active_after_document_id'] = False
    if mutation == 'handles_bool': impact['retiring_window_handles'] = [True]
    if mutation == 'handles_zero': impact['retiring_window_handles'] = [0]
    if mutation == 'handles_negative': impact['retiring_window_handles'] = [-1]
    if mutation == 'handles_duplicate': impact['retiring_window_handles'] *= 2
    if mutation == 'handles_tuple': impact['retiring_window_handles'] = tuple(impact['retiring_window_handles'])
    if mutation == 'handles_int64_overflow': impact['retiring_window_handles'] = [2 ** 63]
    if mutation == 'handles_budget': impact['retiring_window_handles'] = list(range(1, 5002))
    if mutation == 'retiring_budget':
        impact['retiring_document_ids'] = [f'new_{index}' for index in range(5001)]
        impact['target_document_id'] = 'new_0'
        impact['hidden_document_ids'] = impact['retiring_document_ids'][1:]
    assert helper.verified_open_native_steps(value, baseline) is False


@pytest.mark.parametrize('name', ['activate_native', 'rollback_activate_native'])
def test_even_another_live_baseline_model_cannot_replace_original_active_target(name):
    extra = [release()]
    if name == 'rollback_activate_native': extra.append(cleanup())
    extra.append(activation(name, document_id='doc_1'))
    value, baseline = ledger(outcome='rolled_back' if name.startswith('rollback') else 'committed', extra=extra)
    assert helper.verified_open_native_steps(value, baseline) is False


def test_rollback_activation_requires_an_original_active_model_not_just_baseline_ids():
    value, baseline = ledger(outcome='rolled_back', extra=[cleanup(), release(), activation('rollback_activate_native')])
    baseline['semantic']['active_document_id'] = None
    assert helper.verified_open_native_steps(value, baseline) is False
