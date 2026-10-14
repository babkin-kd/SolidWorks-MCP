"""Native relation collector with artificial wrappers; no CAD or native acceptance."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.jobs import ExecutionFailure


SOURCE = Path(__file__).resolve().parents[1] / 'src/solidworks_mcp/cad_features.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf8'))
CLASS = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'CadFeaturesMixin')
METHOD = next(node for node in CLASS.body if isinstance(node, ast.FunctionDef) and node.name == 'feature_dependencies')


class Native:
    def __init__(self, identifier, identity=None, *, parents=None, children=None, owner=None):
        self.identifier = identifier
        self.token = identifier if identity is None else identity
        self.parents, self.children, self.owner = parents, children, owner
        self.calls = []
    def GetID(self):
        self.calls.append('GetID')
        return self.identifier
    def GetParents(self):
        self.calls.append('GetParents')
        return self.parents
    def GetChildren(self):
        self.calls.append('GetChildren')
        return self.children
    def GetOwnerFeature(self):
        self.calls.append('GetOwnerFeature')
        return self.owner
    @property
    def Name(self):
        raise AssertionError('Names cannot prove dependency membership.')


class Canonical:
    __hash__ = None
    def __init__(self, token, calls):
        self.token, self.calls = token, calls
    def __eq__(self, other):
        self.calls.append('canonical_compare')
        return isinstance(other, Canonical) and self.token == other.token


def collector():
    namespace = {'binding': SimpleNamespace(wrap=lambda raw, cls: raw), 'rejected': rejected}
    cls = ast.ClassDef(name='Collector', bases=[], keywords=[], body=[deepcopy(METHOD)], decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), str(SOURCE), 'exec'), namespace)
    adapter = namespace['Collector']()
    adapter._module = SimpleNamespace(IFeature=Native)
    calls = []
    adapter.identity = lambda feature: Canonical(feature.token, calls)
    return adapter, calls


def test_dependency_links_and_absorption_are_separate_native_relations():
    adapter, calls = collector()
    plane, sketch, extrude = Native(10), Native(20), Native(30)
    plane.children = [Native(20)]
    sketch.parents, sketch.children, sketch.owner = [Native(10)], [Native(30)], Native(30)
    extrude.parents = [Native(20)]
    snapshot = adapter.feature_dependencies([plane, sketch, extrude])
    assert snapshot['parent_links'] == snapshot['child_links'] == [[0, 1], [1, 2]]
    assert snapshot['absorbed_links'] == [[2, 1]]
    assert snapshot['parent_links_without_child_confirmation'] == []
    assert snapshot['child_links_without_parent_confirmation'] == []
    assert snapshot['relations_read'] == len(calls) == 5


def test_nonreciprocal_relations_are_explicit_not_silently_dropped():
    adapter, _ = collector()
    a, b, c = Native(1), Native(2), Native(3)
    b.parents, b.children = [Native(1)], [Native(3)]
    snapshot = adapter.feature_dependencies([a, b, c])
    assert snapshot['parent_links_without_child_confirmation'] == [[0, 1]]
    assert snapshot['child_links_without_parent_confirmation'] == [[1, 2]]


@pytest.mark.parametrize('relation', ['parents', 'children', 'owner'])
@pytest.mark.parametrize('foreign', [Native(99), Native(2, identity='different object')])
def test_foreign_or_colliding_native_links_rejected(relation, foreign):
    adapter, _ = collector()
    a, b = Native(1), Native(2)
    setattr(a, relation, foreign if relation == 'owner' else [foreign])
    with pytest.raises(ExecutionFailure) as error:
        adapter.feature_dependencies([a, b])
    assert error.value.code in ('feature_dependency_outside_tree', 'feature_identity_collision')


@pytest.mark.parametrize('value', [False, 0, 'feature', Native(1), [None], [Native(1)] * 5001])
@pytest.mark.parametrize('relation', ['parents', 'children'])
def test_malformed_native_arrays_are_not_treated_as_empty(value, relation):
    adapter, _ = collector()
    feature = Native(1)
    setattr(feature, relation, value)
    with pytest.raises(ExecutionFailure) as error:
        adapter.feature_dependencies([feature])
    assert error.value.code == 'feature_dependency_read_failed'


@pytest.mark.parametrize('rows', [[Native(1), Native(1)], [Native(True)], [Native('1')], [Native(1)] * 5001])
def test_invalid_source_rows_rejected_before_relation_reads(rows):
    adapter, _ = collector()
    with pytest.raises(ExecutionFailure):
        adapter.feature_dependencies(rows)
    assert all(not {'GetParents', 'GetChildren', 'GetOwnerFeature'} & set(row.calls) for row in rows)


def test_duplicate_native_relations_do_not_duplicate_links():
    adapter, calls = collector()
    a, b = Native(1), Native(2, parents=[Native(1), Native(1)])
    assert adapter.feature_dependencies([a, b])['parent_links'] == [[0, 1]]
    assert len(calls) == 2


def test_native_cycles_are_captured_without_recursive_walk():
    adapter, _ = collector()
    a, b = Native(1, children=[Native(2)]), Native(2, children=[Native(1)])
    assert adapter.feature_dependencies([a, b])['child_links'] == [[0, 1], [1, 0]]


def test_relation_budget_counts_duplicates_as_work():
    adapter, _ = collector()
    rows = [Native(index) for index in range(21)]
    for row in rows:
        row.parents = [Native(0)] * 5000
    with pytest.raises(ExecutionFailure) as error:
        adapter.feature_dependencies(rows)
    assert error.value.code == 'feature_dependency_budget_exceeded'
