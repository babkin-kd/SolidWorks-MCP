"""Independent native entry/exit parsing, malformed evidence and transform math."""
import pytest
from solidworks_mcp.point_measurement import classify_native_rays, RAY_DIRECTIONS, component_local_point_m, assembly_point_mm
from test_components_v2 import fails


ORIGIN=[.01,.005,.0025]


def hits(flags=33):
    values=[]
    for i,d in enumerate(RAY_DIRECTIONS):values.extend([0.,float(i),float(flags),*(x+.002*a for x,a in zip(ORIGIN,d)),1.,0.,0.])
    return 3,values


def test_native_entry_exit_and_empty_rays():
    assert classify_native_rays(hits(33),ORIGIN)=='inside'
    assert classify_native_rays(hits(17),ORIGIN)=='outside'
    assert classify_native_rays((0,None),ORIGIN)=='outside'
    count,values=hits();assert classify_native_rays((count,values[18:]+values[:18]),ORIGIN)=='inside'


@pytest.mark.parametrize('raw',[None,(),(-1,None),(True,None),(100001,None),(1,None),(0,[0.]*9),(1,[float('nan')]*9)])
def test_invalid_native_ray_records(raw):fails('point_classification_unavailable',lambda:classify_native_rays(raw,ORIGIN))


@pytest.mark.parametrize('index,value',[(0,1.),(1,3.),(1,.5),(2,True),(2,64.),(2,49.),(2,1.),(3,1.)])
def test_foreign_flags_or_wrong_line_rejected(index,value):
    count,values=hits();values[index]=value
    fails('point_classification_unavailable',lambda:classify_native_rays((count,values),ORIGIN))


def test_independent_directions_must_agree_and_duplicate_nearest_flags_must_not_conflict():
    count,values=hits();values[2]=17.
    fails('point_classification_unavailable',lambda:classify_native_rays((count,values),ORIGIN))
    count,values=hits();duplicate=values[:9];duplicate[2]=17.
    fails('point_classification_unavailable',lambda:classify_native_rays((4,values+duplicate),ORIGIN))


def test_component_inverse_forward_rotation_and_mirrored_axes():
    t={'origin_mm':[50.,10.,20.],'axes_in_assembly':[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]}
    local=component_local_point_m(t,[45.,20.,22.5]);assert local==pytest.approx(ORIGIN)
    assert assembly_point_mm(t,local)==pytest.approx([45.,20.,22.5])
    t['axes_in_assembly'][2][2]=-1.
    local=component_local_point_m(t,[45.,20.,22.5]);assert local==pytest.approx([.01,.005,-.0025])
    assert assembly_point_mm(t,local)==pytest.approx([45.,20.,22.5])
