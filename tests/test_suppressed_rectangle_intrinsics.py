"""Semantic delta proofs over an artificial full base, no native admission."""
from copy import deepcopy
import json

import pytest

from solidworks_mcp.jobs import ExecutionFailure, _json
from solidworks_mcp.suppressed_rectangle_intrinsics import (
    normalized_sketch_relations,normalized_suppressed_configuration,normalized_suppressed_intrinsics)
from test_rectangle_extrusion_postconditions import proof


@pytest.fixture
def observations(proof):
    _,after,_ = proof
    base = json.loads(_json(after['snapshots']['target']))
    qualified=[dict(full_name='Ширина@Эскиз@Деталь.Part',role='dimension:width'),
        dict(full_name='Высота@Эскиз@Деталь.Part',role='dimension:height'),
        dict(full_name='Толщина@Основание@Деталь.Part',role='dimension:depth')]
    base['native_observations']['qualified_dimensions'] = qualified
    names={row['role']:row['full_name'] for row in qualified}
    keys=('extrusion','sketch','properties','configuration_state','auxiliary_data','display_data','controls')
    current={key:deepcopy(base['clone_state'][key]) for key in keys}
    for row in current['sketch']['relations']:
        if row.get('dimension_full_name') is not None:
            row['dimension_full_name'] = names[row['dimension_full_name']['reference_role']]
    current['configuration_state']['parameters'] = sorted(
        current['configuration_state']['parameters'] + [['$СОСТОЯНИЕ@Основание','Пог']])
    return base,current


def test_exact_measured_suppression_delta_normalizes_without_mutating_evidence(observations):
    base,current = observations
    saved=deepcopy(current)
    result=normalized_suppressed_intrinsics(base,current,'Основание')
    assert result == {key:base['clone_state'][key] for key in result}
    assert current==saved and current['configuration_state']['parameters']!=result['configuration_state']['parameters']


@pytest.mark.parametrize('key', ['extrusion','sketch','properties','configuration_state',
                                'auxiliary_data','display_data','controls'])
def test_missing_native_intrinsic_cannot_be_filled_from_baseline(observations,key):
    base,current=observations;current.pop(key)
    with pytest.raises(ExecutionFailure): normalized_suppressed_intrinsics(base,current,'Основание')


@pytest.mark.parametrize('fault', ['foreign_owner','foreign_value','missing_parameter','other_parameter',
    'duplicate_parameter','foreign_description','unknown_locale','non_suppressed'])
def test_only_exact_own_configuration_suppression_parameter_is_allowed(observations,fault):
    base,current=observations;cfg=current['configuration_state'];params=cfg['parameters']
    row=next(row for row in params if row[0]=='$СОСТОЯНИЕ@Основание')
    if fault=='foreign_owner': row[0]='$СОСТОЯНИЕ@Чужая операция'
    elif fault=='foreign_value': row[1]='Неизвестно'
    elif fault=='missing_parameter': params.remove(row)
    elif fault=='other_parameter': params.append(['$ЦВЕТ','changed'])
    elif fault=='duplicate_parameter': params.append(deepcopy(row))
    elif fault=='foreign_description': cfg['Description']='Изменено'
    elif fault=='unknown_locale': row[:]=['$STATE@Основание','S']
    else: row[1]='Разрешён'
    with pytest.raises(ExecutionFailure): normalized_suppressed_intrinsics(base,current,'Основание')


@pytest.mark.parametrize('fault', ['unknown_name','depth_relation','duplicate_name','duplicate_role','missing_role'])
def test_sketch_relation_normalization_uses_complete_exact_original_namespace(observations,fault):
    base,current=observations;qualified=base['native_observations']['qualified_dimensions']
    if fault=='unknown_name': current['sketch']['relations'].append({'dimension_full_name':'Ширина@Чужой эскиз@Деталь.Part'})
    elif fault=='depth_relation': current['sketch']['relations'].append({'dimension_full_name':qualified[2]['full_name']})
    elif fault=='duplicate_name': qualified[1]['full_name']=qualified[0]['full_name']
    elif fault=='duplicate_role': qualified[1]['role']=qualified[0]['role']
    else: qualified.pop()
    with pytest.raises(ExecutionFailure): normalized_suppressed_intrinsics(base,current,'Основание')


@pytest.mark.parametrize('key', ['extrusion','sketch','properties','auxiliary_data','display_data','controls'])
def test_other_intrinsic_change_is_preserved_and_refused_not_masked(observations,key):
    base,current=observations;current[key]['unrelated_change']='foreign'
    with pytest.raises(ExecutionFailure): normalized_suppressed_intrinsics(base,current,'Основание')
    assert current[key]['unrelated_change']=='foreign'
