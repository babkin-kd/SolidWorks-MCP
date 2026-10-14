"""Dependency snapshots with artificial native identities; no CAD acceptance."""

import asyncio
from concurrent.futures import Future
from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp.feature_dependency_graph import SCOPE, relation_semantics
from solidworks_mcp.jobs import ExecutionFailure, JobError
from solidworks_mcp.runtime_v2 import Runtime
from test_feature_domain_v2 import setup, feature


def captured(owner=False):
    return {'scope': 'native_feature_relation_capture_v1', 'feature_count': 2,
            'parent_links': [[1, 0]], 'child_links': [[1, 0]],
            'absorbed_links': [[0, 1]] if owner else [],
            'parent_links_without_child_confirmation': [], 'child_links_without_parent_confirmation': [],
            'relations_read': 3 if owner else 2}


def install(adapter, *, owner=False, change=None):
    calls = []
    if owner:
        adapter.models[0].features[1].state['owner_native_id'] = 1
    def read(native):
        calls.append('capture')
        result = captured(owner)
        if change:
            change(len(calls), result)
        return result
    adapter.feature_dependencies = read
    return calls


def test_two_full_captures_persistent_nodes_separate_ownership_and_stable_revision(setup):
    adapter, documents, catalog, store, ids = setup
    calls = install(adapter, owner=True)
    first = catalog.dependencies(ids[0], 'Основная')
    second = catalog.dependencies(ids[0], 'Основная')
    assert first == second and calls == ['capture'] * 4
    assert first['revision_scope'] == SCOPE and first['revision'] != first['feature_tree_revision']
    assert first['relations']['parent_links'] == [[1, 0]] and first['relations']['absorbed_links'] == [[0, 1]]
    assert len({row['object_id'] for row in first['nodes']}) == 2
    assert all(row['persistent_reference_supported'] for row in first['nodes'])
    assert first['all_reported_native_relations_captured'] is True
    assert first['deletion_authorized'] is first['deletion_impact_complete'] is False
    assert adapter.writes == [] and store.list()['items'] == []


def test_builtin_without_native_persistent_reference_stays_readonly(setup):
    adapter, documents, catalog, store, ids = setup
    install(adapter)
    adapter.pid_fault = 'missing'
    result = catalog.dependencies(ids[0], 'Основная')
    assert result['relations']['parent_links'] == [[1, 0]]
    assert all(row['object_id'] is None and not row['persistent_reference_supported'] for row in result['nodes'])
    assert all(row['reference_error']['code'] == 'persistent_reference_unavailable' for row in result['nodes'])


def test_native_id_reuse_with_same_name_and_pid_changes_graph_incarnation(setup):
    adapter, documents, catalog, store, ids = setup
    install(adapter)
    before = catalog.dependencies(ids[0], 'Основная')
    previous = adapter.models[0].features[0]
    replacement = feature(1, previous.state['name'], pid=previous.pid)
    replacement.state = deepcopy(previous.state)
    adapter.models[0].features[0] = replacement
    after = catalog.dependencies(ids[0], 'Основная')
    assert before['feature_tree_revision'] == after['feature_tree_revision']
    assert before['revision'] != after['revision']
    assert adapter.writes == []


@pytest.mark.parametrize('fault', ['links', 'ownership', 'identity', 'configuration', 'late_notification'])
def test_changed_during_second_capture_never_returns_partial_graph(setup, fault):
    adapter, documents, catalog, store, ids = setup
    def change(number, result):
        if number != 2:
            return
        if fault == 'links':
            result.update(parent_links=[], child_links=[])
        elif fault == 'ownership':
            result.update(absorbed_links=[[0, 1]], relations_read=3)
        elif fault == 'identity':
            adapter.models[0].features[0].identity = object()
        elif fault == 'configuration':
            adapter.config_identity['Основная'] = object()
        else:
            adapter.watches[id(adapter.models[0].identity)].sequence += 1
    install(adapter, change=change)
    with pytest.raises(ExecutionFailure) as raised:
        catalog.dependencies(ids[0], 'Основная')
    assert raised.value.code == 'document_changed_during_read'
    assert not documents._entries[0].features.get('dependency_incarnations')
    assert adapter.writes == []


@pytest.mark.parametrize('change', [
    {'feature_count': True}, {'relations_read': True}, {'relations_read': 1},
    {'parent_links': [[True, 0]]}, {'parent_links': [[2, 0]]},
    {'parent_links': [[1, 0], [1, 0]]}, {'parent_links_without_child_confirmation': [[1, 0]]},
    {'absorbed_links': [[0, 1]], 'relations_read': 3}, {'extra': 'unsupported'},
])
def test_invalid_or_inconsistent_native_capture_rejected(setup, change):
    adapter, documents, catalog, store, ids = setup
    value = captured()
    value.update(change)
    with pytest.raises(ExecutionFailure):
        relation_semantics(value, [row.state for row in adapter.models[0].features])


def test_duplicate_relation_work_counts_do_not_change_semantic_revision(setup):
    adapter, documents, catalog, store, ids = setup
    install(adapter)
    before = catalog.dependencies(ids[0], 'Основная')
    adapter.feature_dependencies = lambda native: {**captured(), 'relations_read': 4}
    after = catalog.dependencies(ids[0], 'Основная')
    assert before['revision'] == after['revision']
    assert after['native_relation_work'] == [4, 4]


@pytest.mark.parametrize('late_event', [False, True])
def test_fresh_unhashable_canonical_wrappers_and_late_comparison_event(setup, late_event):
    adapter, documents, catalog, store, ids = setup
    armed = [False]
    class Canonical:
        __hash__ = None
        def __init__(self, token):
            self.token = token
        def __eq__(self, other):
            if armed[0]:
                armed[0] = False
                adapter.watches[id(adapter.models[0].identity)].sequence += 1
            return isinstance(other, Canonical) and self.token == other.token
    original_identity = adapter.identity
    def identity(obj):
        value = original_identity(obj)
        return Canonical(value) if hasattr(obj, 'pid') else value
    adapter.identity = identity
    def change(number, result):
        if late_event and number == 2:
            armed[0] = True
    install(adapter, change=change)
    if late_event:
        with pytest.raises(ExecutionFailure) as raised:
            catalog.dependencies(ids[0], 'Основная')
        assert raised.value.code == 'document_changed_during_read'
    else:
        first = catalog.dependencies(ids[0], 'Основная')
        assert catalog.dependencies(ids[0], 'Основная')['revision'] == first['revision']


def test_nonreciprocal_links_are_reported_without_deletion_authorization(setup):
    adapter, documents, catalog, store, ids = setup
    adapter.feature_dependencies = lambda native: {
        **captured(), 'child_links': [], 'parent_links_without_child_confirmation': [[1, 0]],
        'relations_read': 1}
    result = catalog.dependencies(ids[0], 'Основная')
    assert result['relations']['parent_links_without_child_confirmation'] == [[1, 0]]
    assert result['deletion_impact_complete'] is result['deletion_authorized'] is False


def test_runtime_routes_graph_as_durable_read_and_never_a_mutation(setup):
    adapter, documents, catalog, store, ids = setup
    install(adapter)
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
    arguments = {'document_id': ids[0], 'configuration': 'Основная'}
    async def exercise():
        with pytest.raises(JobError) as error:
            await runtime.mutate('write', 'feature.dependencies', arguments)
        assert error.value.code == 'unsupported_operation' and runtime._runner is None
        job = await runtime.read('graph', 'feature.dependencies', arguments)
        assert job['status'] == 'succeeded' and job['result']['revision_scope'] == SCOPE
        assert job['payload']['mutates'] is False
        assert job['payload']['context'] == arguments
        assert 'mutation' not in store.get(job['operation_id'])
        retry = await runtime.read('graph', 'feature.dependencies', arguments)
        assert retry['operation_id'] == job['operation_id']
    try:
        asyncio.run(exercise())
    finally:
        runtime.shutdown()
