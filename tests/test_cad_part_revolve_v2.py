"""Axis reference round trips on artificial native interfaces, not CAD acceptance."""

from types import SimpleNamespace as NS
from copy import copy

import pytest

from solidworks_mcp.cad_part_revolve import CadPartRevolveMixin
from solidworks_mcp.jobs import ExecutionFailure
import solidworks_mcp.cad_part_revolve as native


@pytest.fixture
def axis(monkeypatch):
    monkeypatch.setattr(native.binding,'wrap',lambda raw,cls:raw)
    sketch = NS(token=object())
    segment = NS(token=object(),GetSketch=lambda:sketch,GetType=lambda:0,ConstructionGeometry=False,
                 GetStartPoint2=lambda:NS(X=0.,Y=.03,Z=0.),GetEndPoint2=lambda:NS(X=0.,Y=0.,Z=0.))
    extension = NS(GetObjectByPersistReference3=lambda pid:(segment,0))
    class Adapter(CadPartRevolveMixin):
        _module = NS(ISketchSegment=object(),ISketch=object(),ISketchLine=object(),ISketchPoint=object())
        def identity(self,obj): return obj.token
        def _extension(self,model): return extension
        def _persistent_variant(self,pid): return pid
    receipt = NS(axis_segment=segment,axis_pid=b'owned-axis',axis_identity=segment.token,
                 native_sketch_identity=sketch.token,axis_height_m=.03)
    return Adapter(),receipt,segment,extension


def test_exact_own_y_edge_has_current_persistent_reference(axis):
    adapter,receipt,segment,_ = axis
    assert adapter._revolve_axis_current(None,receipt) is segment


@pytest.mark.parametrize('foreign',[False,True])
def test_alternate_selection_interface_requires_verified_reference_and_same_native_state(axis,foreign):
    adapter,_,segment,_ = axis
    segment.GetID = lambda:(7,8)
    segment.Status = 2
    adapter.persistent_id = lambda model,obj:b'owned-axis'
    alternate = copy(segment)
    alternate.token = object()
    if foreign: alternate.GetSketch = lambda:NS(token=object())
    if foreign:
        with pytest.raises(ExecutionFailure): adapter._bind_revolve_segment(None,alternate)
    else:
        assert adapter._bind_revolve_segment(None,alternate) is segment


@pytest.mark.parametrize('fault',['missing_pid','replacement','status','foreign_sketch','wrong_end','curve','construction','bool_type'])
def test_names_and_equal_coordinates_do_not_adopt_foreign_or_wrong_axis(axis,fault):
    adapter,receipt,segment,extension = axis
    if fault == 'missing_pid': receipt.axis_pid = b''
    if fault == 'replacement': receipt.axis_identity = object()
    if fault == 'status': extension.GetObjectByPersistReference3 = lambda pid:(segment,4)
    if fault == 'foreign_sketch': segment.GetSketch = lambda:NS(token=object())
    if fault == 'wrong_end': segment.GetEndPoint2 = lambda:NS(X=.001,Y=0.,Z=0.)
    if fault == 'curve': segment.GetType = lambda:1
    if fault == 'construction': segment.ConstructionGeometry = True
    if fault == 'bool_type': segment.GetType = lambda:False
    with pytest.raises(ExecutionFailure): adapter._revolve_axis_current(None,receipt)
