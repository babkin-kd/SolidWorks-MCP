"""Temporary wire validation; no persistent CAD entity or UI calls."""
from types import SimpleNamespace as NS
import pytest
import solidworks_mcp.cad_components as native
from test_components_v2 import fails


def scene(monkeypatch):
    monkeypatch.setattr(native,'VARIANT',lambda tag,values:values)
    monkeypatch.setattr(native.binding,'wrap',lambda obj,cls:obj)
    ends=[[.025,-1e-6,.0025],[.025,.010001,.0025]];calls=[];component=object()
    edge=NS(GetStartVertex=lambda:NS(GetPoint=lambda:ends[0]),GetEndVertex=lambda:NS(GetPoint=lambda:ends[1]))
    wire=NS(IsTemporaryBody=lambda:True,GetType=lambda:2,GetEdges=lambda:[edge])
    trimmed=NS(IsLine=lambda:True,CreateWireBody=lambda:wire)
    def trim(*args):calls.append(('trim',args));return trimmed
    curve=NS(IsLine=lambda:True,CreateTrimmedCurve2=trim)
    def line(*args):calls.append(('line',args));return curve
    modeler=NS(CreateLine=line)
    def closest(*args):calls.append(('closest',args));return .005,[.02,.005,.0025],[.025,.005,.0025]
    model=NS(ClosestDistance=closest)
    adapter=native.CadComponentsMixin();adapter._sw=NS(GetModeler=lambda:modeler)
    adapter._module=NS(IModeler=object,ICurve=object,IBody2=object,IEdge=object,IVertex=object)
    return adapter,model,component,ends,calls,curve,trimmed,wire,edge


def test_only_memory_curve_trim_wire_and_explicit_native_targets(monkeypatch):
    adapter,model,component,ends,calls,curve,trimmed,wire,edge=scene(monkeypatch)
    assert adapter.component_axis_distance(model,component,ends,[0.,1.,0.])[0]==.005
    assert calls==[('line',(ends[0],[0.,1.,0.])),('trim',tuple(ends[0]+ends[1])),('closest',(component,edge))]


@pytest.mark.parametrize('change',['curve','trim','temporary','type','noedges','twoedges','nullvertex','wrongvertex','nonfinite'])
def test_invalid_native_temporary_entity_never_reaches_distance(monkeypatch,change):
    adapter,model,component,ends,calls,curve,trimmed,wire,edge=scene(monkeypatch)
    if change=='curve':curve.IsLine=lambda:False
    elif change=='trim':trimmed.IsLine=lambda:False
    elif change=='temporary':wire.IsTemporaryBody=lambda:False
    elif change=='type':wire.GetType=lambda:0
    elif change=='noedges':wire.GetEdges=lambda:None
    elif change=='twoedges':wire.GetEdges=lambda:[edge,edge]
    elif change=='nullvertex':edge.GetStartVertex=lambda:None
    elif change=='wrongvertex':edge.GetStartVertex=lambda:NS(GetPoint=lambda:[0.]*3)
    elif change=='nonfinite':edge.GetStartVertex=lambda:NS(GetPoint=lambda:[float('nan'),0.,0.])
    fails('temporary_axis_unavailable',lambda:adapter.component_axis_distance(model,component,ends,[0.,1.,0.]))
    assert not any(name=='closest' for name,_ in calls)


def test_reversed_native_vertices_permitted(monkeypatch):
    adapter,model,component,ends,calls,curve,trimmed,wire,edge=scene(monkeypatch)
    edge.GetStartVertex=lambda:NS(GetPoint=lambda:ends[1]);edge.GetEndVertex=lambda:NS(GetPoint=lambda:ends[0])
    assert adapter.component_axis_distance(model,component,ends,[0.,1.,0.])[0]==.005
