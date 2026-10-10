"""Verifier assertions reject missing native evidence and deletion claims."""

import ast
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify_feature_dependencies.py'
TREE = ast.parse(SCRIPT.read_text(encoding='utf8'))
HELPERS = [node for node in TREE.body if isinstance(node, ast.FunctionDef)
           and node.name in ('verify_box_relations', 'verify_options')]
NS = {}
exec(compile(ast.Module(body=HELPERS, type_ignores=[]), str(SCRIPT), 'exec'), NS)


def graph():
    return {'nodes': [
        {'node_index': 0, 'native_id': 40, 'feature_type': 'Extrusion', 'owner_native_id': None,
         'object_id': 'obj_owner', 'persistent_reference_supported': True},
        {'node_index': 1, 'native_id': 41, 'feature_type': 'ProfileFeature', 'owner_native_id': 40,
         'object_id': 'obj_sketch', 'persistent_reference_supported': True},
    ], 'relations': {'parent_links': [[1, 0]], 'child_links': [[1, 0]], 'absorbed_links': [[0, 1]]},
        'all_reported_native_relations_captured': True,
        'deletion_impact_complete': False, 'deletion_authorized': False}


def result(children, absorbed):
    rows = deepcopy(graph()['nodes'])
    return {'options': {'include_children': children, 'include_absorbed': absorbed},
        'native_delete_options': int(children) + 2 * int(absorbed),
        'structural_candidate_nodes': rows if absorbed else rows[:1],
        'deletion_impact_complete': False, 'deletion_authorized': False,
        'native_deletion_result_predicted': False, 'structural_links_complete': True,
        'blockers': [{'code': 'unverified_impact_scope', 'scope': scope} for scope in (
            'other_configurations', 'dimensions_and_equations', 'annotations_and_drawings',
            'external_files_and_in_context_references', 'native_deletion_effects_and_restoration')]}


def test_independent_parent_child_and_owner_evidence_matches():
    owner, sketch = NS['verify_box_relations'](graph(), 40, 41, {41}, {40})
    assert owner['object_id'] == 'obj_owner' and sketch['object_id'] == 'obj_sketch'


@pytest.mark.parametrize('change', ['parent_links', 'child_links', 'absorbed_links', 'persistent', 'authorize'])
def test_graph_missing_or_unsafe_evidence_rejected(change):
    value = graph()
    if change in value['relations']:
        value['relations'][change] = []
    elif change == 'persistent':
        value['nodes'][1]['object_id'] = None
    else:
        value['deletion_authorized'] = True
    with pytest.raises(AssertionError):
        NS['verify_box_relations'](value, 40, 41, {41}, {40})


@pytest.mark.parametrize('children,absorbed', [(False, False), (True, False), (False, True), (True, True)])
def test_four_explicit_native_option_combinations(children, absorbed):
    owner, sketch = graph()['nodes']
    NS['verify_options'](result(children, absorbed), owner, sketch, children, absorbed)


@pytest.mark.parametrize('change', ['missing_absorbed', 'extra_candidate', 'missing_blocker', 'native_prediction'])
def test_structural_mismatch_and_unsupported_authority_rejected(change):
    owner, sketch = graph()['nodes']
    absorbed = change != 'extra_candidate'
    value = result(False, absorbed)
    if change == 'missing_absorbed':
        value['structural_candidate_nodes'] = [owner]
    elif change == 'extra_candidate':
        value['structural_candidate_nodes'].append(sketch)
    elif change == 'missing_blocker':
        value['blockers'].pop()
    else:
        value['native_deletion_result_predicted'] = True
    with pytest.raises(AssertionError):
        NS['verify_options'](value, owner, sketch, False, absorbed)
