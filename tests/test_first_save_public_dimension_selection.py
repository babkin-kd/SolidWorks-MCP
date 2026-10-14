"""Fixture-only selection gate; no COM, MCP process or CAD operation."""
import ast
from copy import deepcopy
import math
from pathlib import Path

import pytest


tree = ast.parse((Path(__file__).resolve().parents[1] / 'scripts/verifier_first_save_public_contract.py').read_text(encoding='utf-8'))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'fixture_depth_dimension')
namespace = {'math': math}
exec(compile(ast.Module(body=[function], type_ignores=[]), 'fixture_depth', 'exec'), namespace)
select = namespace['fixture_depth_dimension']


@pytest.fixture
def captured():
    def row(value, owner, identifier, blockers):
        return dict(unit='mm', owner={'feature_type': owner}, write_blockers=blockers,
                    persistent_reference_supported=True, object_id=identifier, values={'Основная': value})
    return dict(configuration='Основная', next_cursor=None, total_count=3,
                items=[row(40., 'ProfileFeature', 'width', ['sketch_dimension']),
                       row(12., 'Boss', 'depth', []), row(20., 'ProfileFeature', 'height', ['sketch_dimension'])])


def test_dimension_is_selected_from_bound_supported_role_and_value_not_order(captured):
    for items in (captured['items'], list(reversed(captured['items']))):
        current = {**captured, 'items': items}
        assert select(current, 'Основная', 12.)['object_id'] == 'depth'


@pytest.mark.parametrize('fault', ['partial', 'count', 'configuration', 'blocker', 'no_pid', 'no_id',
                                 'duplicate', 'wrong_owner', 'nonfinite', 'boolean_value', 'changed_value'])
def test_unavailable_changed_or_ambiguous_depth_cannot_fall_back_to_name(captured, fault):
    data = deepcopy(captured)
    row = data['items'][1]
    if fault == 'partial':data['next_cursor'] = 'more'
    elif fault == 'count':data['total_count'] = True
    elif fault == 'configuration':data['configuration'] = 'Другая'
    elif fault == 'blocker':row['write_blockers'] = ['linked']
    elif fault == 'no_pid':row['persistent_reference_supported'] = False
    elif fault == 'no_id':row['object_id'] = None
    elif fault == 'duplicate':data['items'][0] = deepcopy(row)
    elif fault == 'wrong_owner':row['owner']['feature_type'] = 'ProfileFeature'
    elif fault == 'nonfinite':row['values']['Основная'] = float('nan')
    elif fault == 'boolean_value':row['values']['Основная'] = True
    elif fault == 'changed_value':row['values']['Основная'] = 14.
    with pytest.raises(ValueError):
        select(data, 'Основная', 12.)
