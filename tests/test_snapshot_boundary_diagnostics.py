"""Pure diagnostic controls; synthetic metadata/events are not native evidence."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('snapshot_boundary_diagnostics',
    ROOT / 'scripts/verifier_snapshot_boundary_diagnostics.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

OPENING = dict(title='Контрольная деталь', path='', document_type='part', needs_save=True,
               configurations=['Основная'], active_configuration='Основная', update_stamp=7)


def diagnose(**overrides):
    arguments = dict(opening=deepcopy(OPENING), closing=deepcopy(OPENING),
        canonical_model_preserved=True, canonical_configuration_preserved=True,
        watch_before=3, watch_after=3, observed_events=[])
    arguments.update(overrides)
    return helper.diagnose_snapshot_boundary(**arguments)


def test_allowlist_matches_exact_actual_part_revision_watch_without_importing_native_module():
    tree = ast.parse((ROOT / 'src/solidworks_mcp/cad_features.py').read_text(encoding='utf8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'PartRevisionWatch')
    value = next(node.value for node in cls.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'EVENTS' for target in node.targets))
    assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'frozenset'
    assert helper.WATCH_EVENTS == frozenset(ast.literal_eval(value.args[0]))


def test_stable_supplied_boundary_still_never_accepts_native_cleanup_or_retry():
    result = diagnose()
    assert result['changed_metadata_fields'] == [] and result['event_delta'] == 0
    assert result['refusal_reasons'] == [] and result['boundary_violation_observed'] is False
    assert result['native_accepted'] is result['cleanup_authorized'] is result['retry_authorized'] is False


@pytest.mark.parametrize('field,value', [('title','Переименовано'), ('path','C:/part.sldprt'),
    ('document_type','assembly'), ('needs_save',False), ('configurations',['Основная','Вариант']),
    ('active_configuration','Вариант'), ('update_stamp',8)])
def test_each_actual_metadata_field_is_reported_without_normalization(field, value):
    opening = deepcopy(OPENING)
    if field == 'active_configuration': opening['configurations'].append('Вариант')
    closing = {**deepcopy(opening), field: value}
    result = diagnose(opening=opening, closing=closing)
    assert result['changed_metadata_fields'] == [field]
    assert result['refusal_reasons'] == [dict(kind='metadata', code='opening_closing_metadata_changed', fields=[field])]
    assert result['retry_authorized'] is False


@pytest.mark.parametrize('event', sorted(helper.WATCH_EVENTS))
def test_equal_endpoints_cannot_erase_aba_rebuild_or_any_actual_revision_event(event):
    result = diagnose(watch_after=4, observed_events=[event])
    assert result['changed_metadata_fields'] == [] and result['event_delta'] == 1
    assert result['equal_metadata_with_revision_evidence'] is True
    assert {row['kind'] for row in result['refusal_reasons']} == {'watch'}
    assert result['observed_events'] == [event] and result['retry_authorized'] is False


def test_all_canonical_metadata_watch_refusals_are_retained_together():
    result = diagnose(closing={**OPENING, 'update_stamp':9}, canonical_model_preserved=False,
        canonical_configuration_preserved=False, watch_after=5,
        observed_events=['OnUndoPostNotify','OnRedoPostNotify'])
    assert {row['kind'] for row in result['refusal_reasons']} == {'metadata','model','configuration','watch'}
    assert result['event_delta'] == 2 and result['observed_events'] == ['OnUndoPostNotify','OnRedoPostNotify']


@pytest.mark.parametrize('before,after,events,code', [(3,2,[],'revision_counter_regressed'),
    (3,3,['OnModifyNotify'],'counter_event_trace_inconsistent'),
    (3,5,[],'event_trace_incomplete_or_capped')])
def test_counter_trace_mismatch_is_explicit_refusal_never_a_reason_to_retry(before, after, events, code):
    result = diagnose(watch_before=before, watch_after=after, observed_events=events)
    assert code in {row['code'] for row in result['refusal_reasons']}
    assert result['retry_authorized'] is result['native_accepted'] is result['cleanup_authorized'] is False


def test_capped_event_trace_keeps_every_recorded_duplicate_and_larger_delta():
    events = ['OnRegenPostNotify'] * helper.MAX_OBSERVED_EVENTS
    result = diagnose(watch_before=0, watch_after=helper.MAX_OBSERVED_EVENTS + 1, observed_events=events)
    assert result['observed_events'] == events and result['event_delta'] == len(events) + 1
    assert 'event_trace_incomplete_or_capped' in {row['code'] for row in result['refusal_reasons']}
    events.clear()
    assert len(result['observed_events']) == helper.MAX_OBSERVED_EVENTS


@pytest.mark.parametrize('overrides', [dict(canonical_model_preserved=1), dict(canonical_configuration_preserved=0),
    dict(watch_before=True), dict(watch_after=1.), dict(watch_before=-1), dict(watch_after=None),
    dict(observed_events=('OnModifyNotify',)), dict(observed_events=['OnViewChangeNotify']),
    dict(observed_events=['OnRegenPostNotify2'] * (helper.MAX_OBSERVED_EVENTS + 1)),
    dict(observed_events=[True]), dict(opening=None), dict(closing={})])
def test_malformed_scalar_or_trace_input_fails_closed(overrides):
    with pytest.raises(ValueError): diagnose(**overrides)


@pytest.mark.parametrize('fault', ['missing','extra','bool_stamp','integer_dirty','config_null',
                                 'duplicate_config','inactive_config','title_nonstring'])
def test_partial_or_wrong_typed_native_metadata_never_uses_baseline_fill(fault):
    closing = deepcopy(OPENING)
    if fault == 'missing': closing.pop('update_stamp')
    elif fault == 'extra': closing['unavailable_field'] = None
    elif fault == 'bool_stamp': closing['update_stamp'] = True
    elif fault == 'integer_dirty': closing['needs_save'] = 1
    elif fault == 'config_null': closing['configurations'] = None
    elif fault == 'duplicate_config': closing['configurations'].append('Основная')
    elif fault == 'inactive_config': closing['active_configuration'] = 'Чужая'
    else: closing['title'] = object()
    with pytest.raises(ValueError): diagnose(closing=closing)


def test_raw_metadata_is_detached_and_never_modified_or_substituted():
    opening, closing = deepcopy(OPENING), {**deepcopy(OPENING), 'update_stamp':8}
    before = deepcopy((opening, closing))
    result = diagnose(opening=opening, closing=closing)
    assert (opening, closing) == before
    closing['configurations'].append('Позже')
    assert result['closing']['configurations'] == ['Основная']
