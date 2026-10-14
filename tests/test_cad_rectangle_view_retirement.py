"""Native-shaped ownership/selection/one-shot inverses; no CAD acceptance."""
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import binding
from solidworks_mcp.cad_rectangle_view_retirement import (
    capture_rectangle_views, retain_rectangle_view, retire_rectangle_view)
from solidworks_mcp.jobs import ExecutionFailure


class View:
    Always2D = False
    FlatPatternView = False
    AngleMadeWithViewHorizontal = 0.
    AnnotationCount = 0
    def __init__(self, unassigned=False):
        self.UnassignedView = unassigned
        self.shown = unassigned
        self.retired = False
    def IsShown(self):
        assert not self.retired, 'Getter on a retired native view'
        return self.shown
    def GetViewRotation(self): return [1., 0., 0., 0., 1., 0., 0., 0., 1.]
    def GetAnnotations2(self, a, b): return None


class Feature:
    def __init__(self, adapter, view): self.adapter, self.view = adapter, view
    def GetTypeName2(self): return 'AnnotationViewFeat'
    def Select2(self, append, mark):
        self.adapter.selected = self.view
        self.adapter.selects += 1
        return self.adapter.select_ack


class Node:
    def __init__(self, obj=None): self.Object, self.child, self.next = obj, None, None
    @property
    def ObjectType(self): return 1 if self.Object is not None else 0
    def GetFirstChild(self): return self.child
    def GetNext(self): return self.next


class Extension:
    def __init__(self, adapter): self.adapter = adapter
    @property
    def AnnotationViews(self): return list(self.adapter.views)
    @property
    def AnnotationViewCount(self): return len(self.adapter.views)
    def DeleteSelection2(self, flags):
        assert flags == 0
        self.adapter.deletes += 1
        if self.adapter.delete_mode == 'throw': raise RuntimeError('Lost native ACK')
        target = self.adapter.selected
        self.adapter.views.remove(target)
        target.retired = True
        return self.adapter.delete_mode == 'normal'


@pytest.fixture
def native(monkeypatch):
    monkeypatch.setattr(binding, 'wrap', lambda raw, cls: raw)
    a = NS(_module=NS(**{k: object for k in ('IAnnotationView', 'IAnnotation',
        'ISelectionMgr', 'IFeature', 'IFeatureManager', 'ITreeControlItem')}),
        identity=id, views=[View(True)], selected=None, selects=0, select_ack=True,
        deletes=0, delete_mode='normal', events=[], linked=[])
    a.extension = Extension(a)
    a._extension = lambda model: a.extension
    a.owner = object()
    a.features = lambda model: [a.owner]
    a.dimensions = lambda model, features: a.linked[:]
    a.root = Node()
    a.model = NS(FeatureManager=NS(GetFeatureTreeRootItem2=lambda pane: a.root),
        SelectionManager=NS(GetSelectedObjectCount2=lambda mark: int(a.selected is not None),
            GetSelectedObjectType3=lambda i, mark: 139,
            GetSelectedObject6=lambda i, mark: a.selected))
    a.receipt = capture_rectangle_views(a, a.model)
    a.created = View()
    a.views.append(a.created)
    a.dimension = NS(owner=a.owner, owner_tree_identity=id(a.owner),
        displays=[NS(GetAnnotation=lambda: NS(AnnotationView=a.created))])
    a.linked.append(a.dimension)
    a.owned_feature = Feature(a, a.created)
    a.root.child = Node(Feature(a, a.views[0]))
    a.root.child.next = Node(a.owned_feature)
    def step(name, call, *args):
        a.events.append((name, 'pending'))
        value = call(*args)
        a.events.append((name, 'returned'))
        return value
    a.step = step
    return a


def retain(a, **kwargs):
    retain_rectangle_view(a, a.model, a.receipt, a.owner, step=a.step,
        dimension_count=kwargs.get('dimension_count', 1))


def retire(a):
    retire_rectangle_view(a, a.model, a.receipt, step=a.step)


def test_exact_selected_view_binds_feature_and_inverse_preserves_baseline(native):
    a = native
    retain(a)
    assert a.receipt.bound and a.receipt.owned[0][1] is a.owned_feature
    labels = [label for label, phase in a.events if phase == 'pending']
    assert labels == ['bind_annotation_view_feature_0', 'bind_annotation_view_feature_1']
    a.linked.clear()  # Caller independently proves the owned geometry was removed.
    retire(a)
    assert a.receipt.retired and a.views == [a.receipt.baseline[0].view] and a.deletes == 1
    assert a.events[-4:] == [('restore_select_annotation_view', 'pending'),
        ('restore_select_annotation_view', 'returned'),
        ('restore_delete_annotation_view', 'pending'), ('restore_delete_annotation_view', 'returned')]
    with pytest.raises(ExecutionFailure): retire(a)
    assert a.deletes == 1


def test_two_owned_dimensions_must_bind_the_same_new_view(native):
    a = native
    a.linked.append(NS(owner=a.owner,owner_tree_identity=id(a.owner),displays=list(a.dimension.displays)))
    retain(a, dimension_count=2)
    assert a.receipt.bound


def borrowed_dimensions(a):
    """Native-shaped extrusion chain: own depth plus absorbed width/height."""
    sketch=object()
    baseline_view=View()
    a.views=[a.views[0],baseline_view]
    a.receipt=capture_rectangle_views(a,a.model)
    a.views.append(a.created)
    a.features=lambda model:[sketch,a.owner]
    rows=[NS(owner=sketch,owner_tree_identity=id(sketch),
        displays=[NS(GetAnnotation=lambda:NS(AnnotationView=baseline_view))]) for _ in range(2)]
    a.linked[:]=[a.dimension,*rows]
    def dimensions(model,features):
        assert features==[sketch,a.owner], 'A singleton cannot prove absorbed owners'
        return a.linked[:]
    a.dimensions=dimensions
    return rows


def test_extrusion_binds_only_own_depth_and_preserves_absorbed_baseline_views(native):
    a=native
    borrowed=borrowed_dimensions(a)
    retain(a)
    assert a.receipt.bound
    a.linked[:]=borrowed  # Geometry inverse retains the borrowed sketch.
    retire(a)
    assert a.receipt.retired and len(a.views)==2 and a.deletes==1


@pytest.mark.parametrize('fault',['unproved_owner','foreign_owner','own_new_view','missing_annotation'])
def test_absorbed_dimension_uncertainty_cannot_authorize_owned_view_binding(native,fault):
    a=native
    rows=borrowed_dimensions(a)
    if fault=='unproved_owner':rows[0].owner_tree_identity=None
    elif fault=='foreign_owner':rows[0].owner=object()
    elif fault=='own_new_view':rows[0].displays=[NS(GetAnnotation=lambda:NS(AnnotationView=a.created))]
    else:rows[0].displays=[NS(GetAnnotation=lambda:None)]
    with pytest.raises(ExecutionFailure):retain(a)
    assert not a.receipt.bound and a.deletes==a.selects==0


@pytest.mark.parametrize('fault', ['foreign_model', 'baseline_changed', 'extra_view',
    'foreign_owner', 'foreign_annotation', 'absent_dimension', 'shown', 'wrong_selection',
    'duplicate_feature', 'sibling_cycle', 'missing_root'])
def test_binding_uncertainty_never_authorizes_retirement_or_retry(native, fault):
    a = native
    if fault == 'foreign_model': a.receipt.model_token = -1
    elif fault == 'baseline_changed': a.views[0].shown = False
    elif fault == 'extra_view': a.views.append(View())
    elif fault == 'foreign_owner': a.dimension.owner_tree_identity = -1
    elif fault == 'foreign_annotation': a.dimension.displays = [NS(GetAnnotation=lambda: NS(AnnotationView=a.views[0]))]
    elif fault == 'absent_dimension': a.linked.clear()
    elif fault == 'shown': a.created.shown = True
    elif fault == 'wrong_selection': a.owned_feature.view = a.views[0]
    elif fault == 'duplicate_feature': a.root.child.next.next = Node(a.owned_feature)
    elif fault == 'sibling_cycle': a.root.child.next.next = a.root.child.next
    elif fault == 'missing_root': a.root = None
    with pytest.raises(ExecutionFailure): retain(a)
    assert not a.receipt.bound
    before = a.selects
    with pytest.raises(ExecutionFailure): retain(a)
    with pytest.raises(ExecutionFailure): retire(a)
    assert a.selects == before and a.deletes == 0


@pytest.mark.parametrize('ack', [False, None, 1, 'true'])
def test_malformed_selection_ack_never_authorizes_delete(native, ack):
    a = native
    a.select_ack = ack
    with pytest.raises(ExecutionFailure): retain(a)
    assert a.deletes == 0 and not a.receipt.bound


@pytest.mark.parametrize('count', [True, False, 0, 3, None, '1'])
def test_dimension_contract_is_typed_and_checked_before_selection(native, count):
    a = native
    with pytest.raises(ExecutionFailure): retain(a, dimension_count=count)
    assert a.selects == a.deletes == 0


@pytest.mark.parametrize('fault', ['linked', 'baseline_changed', 'extra_view', 'replaced_view',
    'wrong_selection', 'changed_metadata'])
def test_retirement_revalidates_membership_and_usage_before_delete(native, fault):
    a = native
    retain(a)
    if fault != 'linked': a.linked.clear()
    if fault == 'baseline_changed': a.views[0].shown = False
    elif fault == 'extra_view': a.views.append(View())
    elif fault == 'replaced_view': a.views[1] = View()
    elif fault == 'wrong_selection': a.owned_feature.view = a.views[0]
    elif fault == 'changed_metadata': a.created.shown = True
    with pytest.raises(ExecutionFailure): retire(a)
    assert a.deletes == 0
    with pytest.raises(ExecutionFailure): retire(a)
    assert a.deletes == 0


@pytest.mark.parametrize('mode', ['false', 'throw'])
def test_unconfirmed_delete_stays_one_shot_without_retired_getters(native, mode):
    a = native
    retain(a)
    a.linked.clear()
    a.delete_mode = mode
    with pytest.raises((ExecutionFailure, RuntimeError)): retire(a)
    assert a.deletes == 1 and not a.receipt.retired
    with pytest.raises(ExecutionFailure): retire(a)
    assert a.deletes == 1


def test_missing_view_inventory_refuses_before_construction(native):
    a = native
    a.views.clear()
    with pytest.raises(ExecutionFailure): capture_rectangle_views(a, a.model)
