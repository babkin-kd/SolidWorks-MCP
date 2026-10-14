"""Structural impact is bounded and honest about missing native deletion proof."""

from copy import deepcopy
import asyncio
from concurrent.futures import Future
import hashlib
import json

import pytest

from solidworks_mcp.feature_deletion_structure import SCOPE, structural_candidates, validate_request
from solidworks_mcp.feature_dependency_graph import SCOPE as GRAPH_SCOPE
from solidworks_mcp.jobs import ExecutionFailure, JobError
from solidworks_mcp.runtime_v2 import Runtime
from test_feature_domain_v2 import setup
from test_feature_dependency_graph_v2 import install


def graph(count=5, parents=((1, 0), (0, 2), (3, 2)), children=None, absorbed=((0, 1), (2, 3))):
    parents, children = set(parents), set(parents if children is None else children)
    absorbed = set(absorbed)
    owner = {right: left+1 for left, right in absorbed}
    nodes = [{'node_index': index, 'native_id': index+1, 'owner_native_id': owner.get(index),
              'name': f'Элемент {index}', 'feature_type': 'Boss', 'suppressed': False,
              'error_code': 0, 'is_warning': False, 'object_id': f'feat_{index}',
              'persistent_reference_supported': True, 'reference_error': None} for index in range(count)]
    relations = {'scope': 'native_feature_relation_capture_v1', 'feature_count': count,
        'parent_links': [list(edge) for edge in sorted(parents)],
        'child_links': [list(edge) for edge in sorted(children)],
        'absorbed_links': [list(edge) for edge in sorted(absorbed)],
        'parent_links_without_child_confirmation': [list(edge) for edge in sorted(parents-children)],
        'child_links_without_parent_confirmation': [list(edge) for edge in sorted(children-parents)]}
    return {'document_id': 'doc_owned', 'configuration': 'Основная', 'revision_scope': GRAPH_SCOPE,
        'revision': 'rev_'+hashlib.sha256(json.dumps([nodes, relations], sort_keys=True).encode()).hexdigest(),
        'nodes': nodes, 'relations': relations,
        'native_relation_work': [len(parents)+len(children)+len(absorbed)]*2,
        'all_reported_native_relations_captured': True, 'deletion_authorized': False,
        'deletion_impact_complete': False}


def indices(result):
    return [row['node_index'] for row in result['structural_candidate_nodes']]


@pytest.mark.parametrize('children,absorbed,expected,remaining,flags', [
    (False, False, [0], [1, 2, 3], 0),
    (True, False, [0, 2], [1, 3], 1),
    (False, True, [0, 1], [2, 3], 2),
    (True, True, [0, 1, 2, 3], [], 3),
])
def test_options_distinguish_dependencies_from_absorbed_ownership(children, absorbed, expected, remaining, flags):
    source = graph()
    result = structural_candidates(source, ['feat_0'], children, absorbed)
    assert indices(result) == expected and result['potentially_affected_survivor_node_indices'] == remaining
    assert result['native_delete_options'] == flags and result['revision_scope'] == SCOPE
    assert result['dependency_graph_revision'] == source['revision']
    assert result['cyclic_dependency_components'] == []  # Mixed ownership/dependency cycle is legitimate.
    assert result['structural_links_complete'] is True
    assert result['deletion_authorized'] is result['deletion_impact_complete'] is result['native_deletion_result_predicted'] is False
    assert {item['scope'] for item in result['blockers']} == {
        'other_configurations', 'dimensions_and_equations', 'annotations_and_drawings',
        'external_files_and_in_context_references', 'native_deletion_effects_and_restoration'}


def test_dependency_reasons_dangling_survivors_and_absorbed_nodes_are_explicit():
    result = structural_candidates(graph(), ['feat_0'], False, False)
    assert result['dependent_survivor_links'] == [[0, 2]] and result['absorbed_survivor_links'] == [[0, 1]]
    result = structural_candidates(graph(), ['feat_0'], True, True)
    row = next(row for row in result['structural_candidate_nodes'] if row['node_index'] == 2)
    assert row['explicitly_requested'] is False
    assert row['included_by'] == [
        {'from_node_index': 0, 'kind': 'dependent_feature', 'parent_confirmed': True, 'child_confirmed': True},
        {'from_node_index': 3, 'kind': 'dependent_feature', 'parent_confirmed': True, 'child_confirmed': True}]
    assert result['structural_candidate_nodes'][0]['explicitly_requested'] is True


def test_selection_order_is_semantic_and_options_graph_revision_and_targets_change_revision():
    source = graph()
    first = structural_candidates(source, ['feat_0', 'feat_4'], True, True)
    assert structural_candidates(source, ['feat_4', 'feat_0'], True, True) == first
    assert structural_candidates(source, ['feat_0'], True, True)['revision'] != first['revision']
    assert structural_candidates(source, ['feat_0', 'feat_4'], False, True)['revision'] != first['revision']
    source['revision'] = 'rev_'+'b'*64
    assert structural_candidates(source, ['feat_0', 'feat_4'], True, True)['revision'] != first['revision']


def test_parent_child_disagreement_is_conservative_and_blocks_exact_prediction():
    source = graph(children=((1, 0), (3, 2)))
    result = structural_candidates(source, ['feat_0'], True, False)
    assert indices(result) == [0, 2]
    assert any(item == {'code': 'nonreciprocal_native_relations', 'links': [[0, 2]]} for item in result['blockers'])
    row = result['structural_candidate_nodes'][1]
    assert row['included_by'] == [{'from_node_index': 0, 'kind': 'dependent_feature',
                                 'parent_confirmed': True, 'child_confirmed': False}]


def test_unreferenced_candidate_is_reported_without_fake_writable_id_or_alias():
    source = graph()
    source['nodes'][1].update(object_id=None, persistent_reference_supported=False,
                            reference_error={'code': 'persistent_reference_unavailable'})
    result = structural_candidates(source, ['feat_0'], True, True)
    assert result['structural_candidate_nodes'][1]['object_id'] is None
    assert any(row == {'code': 'candidate_persistent_reference_unavailable', 'node_indices': [1]}
               for row in result['blockers'])
    with pytest.raises(ExecutionFailure) as error:
        structural_candidates(source, ['1'], True, True)
    assert error.value.code == 'object_reference_not_found'
    before = deepcopy(source)
    result['structural_candidate_nodes'][1]['reference_error']['code'] = 'caller_edit'
    assert source == before


def test_cycles_self_links_deep_graph_and_unrelated_component_are_bounded():
    edges = {(index, index+1) for index in range(4999)} | {(4999, 0)}
    source = graph(5000, parents=edges, absorbed=())
    result = structural_candidates(source, ['feat_0'], True, False)
    assert indices(result) == list(range(5000))
    assert result['cyclic_dependency_components'] == [list(range(5000))]
    result = structural_candidates(graph(3, parents=((0, 0), (1, 2), (2, 1)), absorbed=()), ['feat_0'], True, True)
    assert result['cyclic_dependency_components'] == [[0]] and indices(result) == [0]


@pytest.mark.parametrize('targets,children,absorbed', [
    ([], True, True), (['feat_0']*2, True, True), (['feat_0']*201, True, True),
    ((['feat_0']), 1, True), (['feat_0'], True, None), (['feat_0'], 'false', True),
    ([False], True, True), ([''], True, True), (['x'*129], True, True),
])
def test_invalid_options_targets_fail_before_any_cad_graph_read(setup, targets, children, absorbed):
    adapter, documents, catalog, store, ids = setup
    catalog.dependencies = lambda *args: pytest.fail('Invalid request must not read CAD graph.')
    with pytest.raises(ExecutionFailure):
        catalog.deletion_structure(ids[0], 'Основная', targets, children, absorbed)
    assert adapter.writes == []


@pytest.mark.parametrize('fault', ['node_index', 'id_collision', 'native_collision', 'missing_reference',
                                  'bad_owner', 'bad_relation', 'work_count', 'unclosed', 'revision', 'context', 'ownership_cycle'])
def test_inconsistent_graph_cannot_produce_candidates(fault):
    source = graph()
    if fault == 'node_index':
        source['nodes'][0]['node_index'] = True
    elif fault == 'id_collision':
        source['nodes'][1]['object_id'] = 'feat_0'
    elif fault == 'native_collision':
        source['nodes'][1]['native_id'] = 1
    elif fault == 'missing_reference':
        source['nodes'][1]['object_id'] = None
    elif fault == 'bad_owner':
        source['nodes'][1]['owner_native_id'] = True
    elif fault == 'bad_relation':
        source['relations']['parent_links'].append([0, 999])
    elif fault == 'work_count':
        source['native_relation_work'][1] = 1
    elif fault == 'unclosed':
        source['all_reported_native_relations_captured'] = False
    elif fault == 'revision':
        source['revision'] = 'rev_not_an_opaque_digest'
    elif fault == 'context':
        source['document_id'] = None
    else:
        source = graph(2, parents=(), absorbed=((0, 1), (1, 0)))
    with pytest.raises(ExecutionFailure):
        structural_candidates(source, ['feat_0'], True, True)


def test_domain_uses_two_closed_native_captures_and_registered_references_without_write(setup):
    adapter, documents, catalog, store, ids = setup
    calls = install(adapter, owner=True)
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    result = catalog.deletion_structure(ids[0], 'Основная', [target], True, True)
    assert calls == ['capture', 'capture'] and indices(result) == [0, 1]
    assert result['deletion_authorized'] is False and adapter.writes == []
    assert store.list()['items'] == []


def test_runtime_records_idempotent_read_and_rejects_mutation_before_worker(setup):
    adapter, documents, catalog, store, ids = setup
    calls = install(adapter, owner=True)
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    class InlineWorker:
        def submit(self, function):
            future = Future()
            try:
                future.set_result(function())
            except BaseException as error:
                future.set_exception(error)
            return future
        def shutdown(self, timeout_s=5):
            return True
    runtime = Runtime(store, worker_factory=InlineWorker, catalog_factory=lambda: documents)
    arguments = {'document_id': ids[0], 'configuration': 'Основная', 'object_ids': [target],
                 'include_children': True, 'include_absorbed': True}
    async def exercise():
        with pytest.raises(JobError) as error:
            await runtime.mutate('not-a-write', 'feature.deletion_structure', arguments)
        assert error.value.code == 'unsupported_operation' and runtime._runner is None
        first = await runtime.read('structural-read', 'feature.deletion_structure', arguments)
        assert first['status'] == 'succeeded' and first['result']['revision_scope'] == SCOPE
        assert first['result']['deletion_authorized'] is False and first['payload']['mutates'] is False
        assert 'mutation' not in store.get(first['operation_id'])
        repeat = await runtime.read('structural-read', 'feature.deletion_structure', arguments)
        assert repeat['operation_id'] == first['operation_id'] and calls == ['capture', 'capture']
        assert adapter.writes == []
    try:
        asyncio.run(exercise())
    finally:
        runtime.shutdown()
