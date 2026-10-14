"""Early-bound native batching and no stale cache/budget fallback."""
from types import SimpleNamespace as NS
import pytest
import solidworks_mcp.cad_components as native
from solidworks_mcp.point_measurement import RAY_DIRECTIONS


@pytest.mark.parametrize('count',[0,-1,100001,True,3.])
def test_invalid_empty_or_excessive_count_never_reads_previous_cache(monkeypatch,count):
    monkeypatch.setattr(native,'VARIANT',lambda tag,values:values)
    monkeypatch.setattr(native.binding,'wrap',lambda obj,cls:obj)
    model=NS(Extension=NS(RayIntersections=lambda *args:count),GetRayIntersectionsPoints=lambda:pytest.fail('No stale/oversize cache getter'))
    adapter=native.CadComponentsMixin();adapter._module=NS(IModelDocExtension=object)
    assert adapter.body_point_rays(model,object(),[.01,.005,.0025])==(count,None)


def test_three_local_rays_are_one_explicit_high_precision_call(monkeypatch):
    monkeypatch.setattr(native,'VARIANT',lambda tag,values:values)
    monkeypatch.setattr(native.binding,'wrap',lambda obj,cls:obj)
    calls=[];body=object();point=[.01,.005,.0025];values=[0.]*27
    def rays(*args):calls.append(args);return 3
    model=NS(Extension=NS(RayIntersections=rays),GetRayIntersectionsPoints=lambda:values)
    adapter=native.CadComponentsMixin();adapter._module=NS(IModelDocExtension=object)
    assert adapter.body_point_rays(model,body,point)==(3,values)
    assert calls==[([body],point*3,[x for d in RAY_DIRECTIONS for x in d],5,0.,1e-8,True)]
    face=NS(GetClosestPointOn=lambda *args:[*args,0.,0.])
    assert adapter.face_closest_point(face,point)==[*point,0.,0.]
