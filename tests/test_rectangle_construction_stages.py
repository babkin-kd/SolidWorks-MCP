"""Separate-stage native contracts with artificial COM; not CAD acceptance."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_part_creation import CadPartCreationMixin
from solidworks_mcp.cad_rectangle_construction import CadRectangleConstructionMixin
from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion, RectangleSketch
from solidworks_mcp import binding


class Feature:
    def __init__(self, number, kind):
        self.number, self.kind = number, kind
        self.Name = 'Эскиз основания' if kind == 'ProfileFeature' else 'Плоскость'
        self.dimension = NS(Name='D1')
        self.children = []
        self.native_sketch = NS(GetConstrainedStatus=lambda: 3)
    def GetTypeName2(self): return self.kind
    def GetSpecificFeature2(self): return self.native_sketch
    def Select2(self, append, mark): return True
    def Parameter(self, name): assert name == 'D1'; return self.dimension
    def GetChildren(self): return self.children


class Adapter(CadRectangleConstructionMixin, CadPartCreationMixin):
    _module = NS(**{n: object for n in ['IModelDoc2', 'IConfiguration', 'ISketch',
        'IFeature', 'IFeatureManager', 'ISketchManager', 'IDimension']})
    def __init__(self):
        self.cfg = object()
        self.sketch = Feature(2, 'ProfileFeature')
        self.items = [Feature(1, 'RefPlane'), self.sketch]
        self.solid = []
        self.absorbed = None
        self.calls, self.deletions = [], []
        self.factory_mode = 'normal'
        self.delete_ack = True
        self.model = NS(SketchManager=NS(ActiveSketch=None),
            GetActiveConfiguration=lambda: self.cfg,
            FeatureManager=NS(FeatureExtrusion3=self.factory))
        self._sw = NS(ActiveDoc=self.model)
    def identity(self, obj): return id(obj)
    def features(self, model): return list(self.items)
    def bodies(self, model, kind): return list(self.solid)
    def part_creation_controls(self, model):
        return dict(add_to_db=False, auto_solve=True, display_when_added=True, dimension_input=False)
    def feature_summary(self, obj):
        return dict(native_id=obj.number, name=obj.Name, feature_type=obj.kind, suppressed=False, error_code=0)
    def persistent_id(self, model, obj): return str(id(obj)).encode()
    def resolve_persistent_id(self, model, token, kind):
        return next(obj for obj in self.items if self.persistent_id(model, obj) == token)
    def sketch_snapshot(self, model, sketch):
        assert sketch is self.sketch
        return deepcopy(dict(points=[(0., 0.), (.04, 0.), (.04, .02), (0., .02)],
            dimensions=[.04, .02], absorbed_by=self.absorbed)), []
    def _base_selection(self, model, receipt): return nullcontext()
    def rebuild_dimension_document(self, model): return True
    def factory(self, *args):
        self.calls.append(args)
        if self.factory_mode == 'null': return None
        if self.factory_mode == 'alias': return self.sketch
        result = Feature(3, 'Extrusion')
        self.items.append(result)
        self.solid = [NS(Name='', GetType=lambda: 0)]
        self.absorbed = 3
        if self.factory_mode == 'lost_ack': raise RuntimeError('after native effect')
        return result
    def _extension(self, model): return NS(DeleteSelection2=self.delete)
    def delete(self, flags):
        self.deletions.append(flags)
        self.items = [obj for obj in self.items if obj.kind != 'Extrusion']
        self.solid, self.absorbed = [], None
        if flags & 2: self.items.remove(self.sketch)
        return self.delete_ack
    def receipt(self):
        return self.new_rectangle_stage_receipt(self.model, self.items,
            self.part_creation_controls(self.model), sketch=self.sketch)


@pytest.fixture(autouse=True)
def wrappers(monkeypatch):
    monkeypatch.setattr(binding, 'wrap', lambda value, cls: value)
    # This suite isolates the geometry bridge. Native-shaped view inventory,
    # identity/selection and retirement are exercised in their dedicated suite.
    import solidworks_mcp.cad_rectangle_construction as bridge
    monkeypatch.setattr(bridge, 'capture_rectangle_views', lambda *args: NS(bound=False, retired=False))
    def retain(adapter, model, state, feature, **kwargs): state.bound = True
    def retire(adapter, model, state, **kwargs): state.retired = True
    monkeypatch.setattr(bridge, 'retain_rectangle_view', retain)
    monkeypatch.setattr(bridge, 'retire_rectangle_view', retire)


def extrusion(**changes):
    return BlindRectangleExtrusion.validate(sketch_object_id='feat_'+'a'*32,
        depth_mm=10., **changes)


def test_separate_inputs_keep_explicit_targets_russian_names_and_native_units():
    sketch = RectangleSketch.validate(plane_object_id='feat_'+'b'*32, width_mm=40., height_mm=20.)
    assert sketch.profile_m == ((0.,0.),(.04,0.),(.04,.02),(0.,.02))
    assert sketch.sketch_name == 'Эскиз основания'
    assert extrusion().depth_m == .01


@pytest.mark.parametrize('value', [True, None, '10', 0., -1., float('nan'), float('inf')])
def test_stage_lengths_reject_invalid_input_without_native_access(value):
    with pytest.raises(ExecutionFailure):
        BlindRectangleExtrusion.validate(sketch_object_id='feat_'+'a'*32, depth_mm=value)
    with pytest.raises(ExecutionFailure):
        RectangleSketch.validate(plane_object_id='feat_'+'a'*32, width_mm=value, height_mm=20.)


def test_unrepresentable_rectangle_area_is_rejected_before_construction():
    with pytest.raises(ExecutionFailure):
        RectangleSketch.validate(plane_object_id='feat_'+'a'*32, width_mm=1e308, height_mm=1e308)


def test_extrusion_restore_preserves_baseline_sketch_points_dimensions_and_identity():
    a = Adapter()
    before = a.sketch_snapshot(a.model, a.sketch)[0]
    r = a.receipt()
    a.extrude_rectangle_sketch(a.model, extrusion(), r)
    assert r.sketch is None and r.borrowed_sketch is a.sketch
    assert len(a.solid) == 1 and r.extrusion.Name == 'Основание'
    assert r.extrusion.dimension.Name == 'Толщина' and a.solid[0].Name == 'Тело основания'
    a.restore_rectangle_extrusion(a.model, r)
    assert a.deletions == [0] and a.sketch in a.items and not a.solid
    assert a.sketch_snapshot(a.model, a.sketch)[0] == before and r.restored is True
    assert r.annotation_views.bound and r.annotation_views.retired


def test_unbound_view_receipt_prohibits_geometry_deletion():
    a = Adapter(); r = a.receipt()
    a.extrude_rectangle_sketch(a.model, extrusion(), r)
    r.annotation_views.bound = False
    with pytest.raises(ExecutionFailure) as failure:
        a.restore_rectangle_extrusion(a.model, r)
    assert failure.value.uncertain and not a.deletions


def test_view_retirement_failure_does_not_claim_full_restoration(monkeypatch):
    import solidworks_mcp.cad_rectangle_construction as bridge
    a = Adapter(); r = a.receipt()
    a.extrude_rectangle_sketch(a.model, extrusion(), r)
    def fail(*args, **kwargs):
        assert a.deletions == [0] and a.sketch in a.items and not a.solid
        raise ExecutionFailure('view_inverse_lost', 'Artificial uncertainty', uncertain=True)
    monkeypatch.setattr(bridge, 'retire_rectangle_view', fail)
    with pytest.raises(ExecutionFailure): a.restore_rectangle_extrusion(a.model, r)
    assert not r.restored and r.restore_attempted
    with pytest.raises(ExecutionFailure): a.restore_rectangle_extrusion(a.model, r)
    assert a.deletions == [0]


def test_sketch_geometry_inverse_is_not_full_restoration_until_view_inverse(monkeypatch):
    import solidworks_mcp.cad_rectangle_construction as bridge
    a = Adapter()
    a.items.remove(a.sketch)
    r = a.new_rectangle_stage_receipt(a.model, a.items, a.part_creation_controls(a.model))
    r.sketch, r.sketch_identity = a.sketch, a.identity(a.sketch)
    r.annotation_views.bound = True
    a.items.append(a.sketch)
    def geometry_inverse(model, owned):
        assert owned is r and not owned.restored
        a.items.remove(a.sketch)
        owned.restored = True
    a.restore_base_rectangle = geometry_inverse
    def view_inverse(adapter, model, views, **kwargs):
        assert a.sketch not in a.items and not r.restored
        raise ExecutionFailure('view_inverse_lost', 'Artificial uncertainty', uncertain=True)
    monkeypatch.setattr(bridge, 'retire_rectangle_view', view_inverse)
    with pytest.raises(ExecutionFailure): a.restore_rectangle_sketch(a.model, r)
    assert not r.restored and r.restore_attempted
    with pytest.raises(ExecutionFailure): a.restore_rectangle_sketch(a.model, r)


def test_a_consumed_extrusion_receipt_cannot_dispatch_another_native_creation():
    a = Adapter(); r = a.receipt()
    a.extrude_rectangle_sketch(a.model, extrusion(), r)
    with pytest.raises(ExecutionFailure): a.extrude_rectangle_sketch(a.model, extrusion(), r)
    assert len(a.calls) == 1


@pytest.mark.parametrize('fault', ['null', 'alias', 'lost_ack'])
def test_unconfirmed_return_never_authorizes_delete_or_retry(fault):
    a = Adapter(); r = a.receipt(); a.factory_mode = fault
    with pytest.raises((ExecutionFailure, RuntimeError)):
        a.extrude_rectangle_sketch(a.model, extrusion(), r)
    assert r.pending_creation is True and len(a.calls) == 1
    with pytest.raises(ExecutionFailure) as failure: a.restore_rectangle_extrusion(a.model, r)
    assert failure.value.uncertain is True and not a.deletions
    with pytest.raises(ExecutionFailure): a.extrude_rectangle_sketch(a.model, extrusion(), r)
    assert len(a.calls) == 1


def test_changed_or_replaced_baseline_sketch_refuses_before_factory():
    a = Adapter(); r = a.receipt(); a.absorbed = 99
    with pytest.raises(ExecutionFailure): a.extrude_rectangle_sketch(a.model, extrusion(), r)
    assert not a.calls
    a.absorbed = None
    a.items.remove(a.sketch)
    with pytest.raises(ExecutionFailure): a.extrude_rectangle_sketch(a.model, extrusion(), r)
    assert not a.calls


def test_unrelated_dependency_prevents_restoration_before_delete():
    a = Adapter(); r = a.receipt(); a.extrude_rectangle_sketch(a.model, extrusion(), r)
    r.extrusion.children = [Feature(4, 'Extrusion')]
    with pytest.raises(ExecutionFailure): a.restore_rectangle_extrusion(a.model, r)
    assert not a.deletions and a.sketch in a.items


@pytest.mark.parametrize('children', [False, 0, '', {}])
def test_malformed_dependency_inventory_never_authorizes_delete(children):
    a = Adapter(); r = a.receipt(); a.extrude_rectangle_sketch(a.model, extrusion(), r)
    r.extrusion.children = children
    with pytest.raises(ExecutionFailure): a.restore_rectangle_extrusion(a.model, r)
    assert not a.deletions


@pytest.mark.parametrize('ack', [False, None, 0, 1, 'true'])
def test_false_or_malformed_delete_ack_after_effect_is_unknown_and_never_repeated(ack):
    a = Adapter(); r = a.receipt(); a.extrude_rectangle_sketch(a.model, extrusion(), r)
    a.delete_ack = ack
    with pytest.raises(ExecutionFailure) as failure: a.restore_rectangle_extrusion(a.model, r)
    assert failure.value.uncertain is True and r.restored is False
    with pytest.raises(ExecutionFailure): a.restore_rectangle_extrusion(a.model, r)
    assert a.deletions == [0] and a.sketch in a.items


def test_unknown_sketch_close_does_not_authorize_an_inverse_close_or_delete():
    a = Adapter()
    r = a.new_rectangle_stage_receipt(a.model, a.items, a.part_creation_controls(a.model))
    r.pending_sketch_close = True
    with pytest.raises(ExecutionFailure) as failure: a.restore_rectangle_sketch(a.model, r)
    assert failure.value.uncertain is True and not a.deletions
