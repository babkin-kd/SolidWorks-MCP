"""Native interface-shaped reference checks; no SolidWorks calls."""
from types import SimpleNamespace as NS
import pytest
from solidworks_mcp.cad_sketches import CadSketchesMixin
from solidworks_mcp.jobs import ExecutionFailure
from test_linear_sketch_v2 import Sketch
from test_part_creation_v2 import IDENTITY
import solidworks_mcp.cad_sketches as native


class Adapter(CadSketchesMixin):
    _module=NS(ISketch=object(),ISketchPoint=object(),IMathTransform=object(),ISketchSegment=object(),
        ISketchLine=object(),ISketchRelation=object(),ISketchRelationManager=object(),IDisplayDimension=object(),IDimension=object())
    def features(self, model):return model
    def identity(self, obj):return id(obj)
    def persistent_id(self, model, obj):return obj.pid
    def resolve_persistent_id(self, model, pid, kind):return next(item for item in model if item.pid==pid)
    def reference_plane_transform(self, plane):return IDENTITY
    def _persistent_variant(self, pid):return pid
    def _extension(self, model):
        sketch=model[0].GetSpecificFeature2()
        members={item.pid:item for item in sketch.points+[sketch.origin,sketch.projected]+sketch.lines}
        return NS(GetObjectByPersistReference3=lambda pid:(members.get(pid),0))


def fixture():
    sketch=Sketch()
    for i,item in enumerate(sketch.points+[sketch.origin,sketch.projected]+sketch.lines):item.pid=str(i).encode()
    raw_plane=NS(pid=b'plane')
    sketch.GetReferenceEntity=lambda kind:(raw_plane,4)
    sketch.ModelToSketchTransform=NS(ArrayData=IDENTITY)
    def feature(pid, kind, specific, number):
        return NS(pid=pid,GetTypeName2=lambda:kind,GetSpecificFeature2=lambda:specific,GetID=lambda:number)
    profile=feature(b'profile','ProfileFeature',sketch,10)
    plane=feature(b'plane','RefPlane',object(),2)
    origin=feature(b'origin','OriginProfileFeature',NS(GetSketchPoints2=lambda:[sketch.origin]),5)
    return [profile,plane,origin],profile,raw_plane


def test_plane_resolves_through_native_pid_despite_distinct_specific_interfaces(monkeypatch):
    monkeypatch.setattr(native.binding,'wrap',lambda raw,cls:raw)
    model,profile,raw=fixture()
    assert Adapter().identity(raw)!=Adapter().identity(model[1].GetSpecificFeature2())
    snapshot,members=Adapter().sketch_snapshot(model,profile)
    assert snapshot['reference_plane']['pid_hex']==b'plane'.hex()
    assert dict(members)['plane']==id(model[1])


@pytest.mark.parametrize('fault',['missing','duplicate','retargeted','wrong_roundtrip'])
def test_ambiguous_or_retargeted_reference_is_rejected(monkeypatch,fault):
    monkeypatch.setattr(native.binding,'wrap',lambda raw,cls:raw)
    model,profile,raw=fixture()
    adapter=Adapter()
    if fault=='missing':raw.pid=b''
    if fault=='duplicate':model.append(NS(**model[1].__dict__))
    if fault=='retargeted':raw.pid=b'foreign'
    if fault=='wrong_roundtrip':adapter.resolve_persistent_id=lambda *args:NS()
    with pytest.raises(ExecutionFailure):adapter.sketch_snapshot(model,profile)


def circle_fixture():
    from test_circular_sketch_v2 import CircleSketch
    model,profile,raw=fixture()
    sketch=CircleSketch()
    for index,item in enumerate(sketch.points+[sketch.origin,sketch.projected]+sketch.lines):
        item.pid=('circle-entity:'+str(index)).encode()
    sketch.GetReferenceEntity=lambda kind:(raw,4)
    sketch.ModelToSketchTransform=NS(ArrayData=IDENTITY)
    profile.GetSpecificFeature2=lambda:sketch
    model[2].GetSpecificFeature2=lambda:NS(GetSketchPoints2=lambda:[sketch.origin])
    return model,profile,sketch


def test_circle_uses_the_same_exact_plane_origin_and_persistent_entity_proof(monkeypatch):
    monkeypatch.setattr(native.binding,'wrap',lambda raw,cls:raw)
    monkeypatch.setattr(Adapter._module,'ISketchArc',object(),raising=False)
    monkeypatch.setattr(Adapter._module,'ICurve',object(),raising=False)
    model,profile,sketch=circle_fixture()
    snapshot,members=Adapter().circular_sketch_snapshot(model,profile)
    assert snapshot['scope']=='circular_planar_sketch_geometry_v1'
    assert snapshot['reference_plane']['pid_hex']==b'plane'.hex()
    assert dict(members)['circle:0:1']==id(sketch.lines[0])
    assert {row['kind'] for row in snapshot['entity_references']}=={'point','segment'}
    with pytest.raises(ExecutionFailure):Adapter().sketch_snapshot(model,profile)


@pytest.mark.parametrize('fault',['missing_circle_pid','retargeted_plane','missing_origin','foreign_circle_owner'])
def test_circle_adapter_rejects_unproven_exact_context(monkeypatch,fault):
    monkeypatch.setattr(native.binding,'wrap',lambda raw,cls:raw)
    monkeypatch.setattr(Adapter._module,'ISketchArc',object(),raising=False)
    monkeypatch.setattr(Adapter._module,'ICurve',object(),raising=False)
    model,profile,sketch=circle_fixture()
    if fault=='missing_circle_pid':sketch.lines[0].pid=b''
    if fault=='retargeted_plane':sketch.GetReferenceEntity=lambda kind:(NS(pid=b'other-plane'),4)
    if fault=='missing_origin':model.pop()
    if fault=='foreign_circle_owner':sketch.lines[0].owner=object()
    with pytest.raises(ExecutionFailure):Adapter().circular_sketch_snapshot(model,profile)
