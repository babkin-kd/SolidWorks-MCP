"""Independent two-bend flat material fixtures; not native CAD acceptance."""

from copy import deepcopy
from dataclasses import replace
import math

import pytest

from solidworks_mcp.sheet_flange_flat_geometry import (
    expected_flat_u_geometry,flat_u_body_matches,fixed_u_leg_from_face)
from solidworks_mcp.sheet_edge_flange_definition import EdgeFlangeOnL
from solidworks_mcp.jobs import ExecutionFailure
from test_sheet_profile_definition_v2 import definition
from test_part_creation_v2 import IDENTITY
from test_sheet_flat_geometry_v2 import POLYGONS
from test_planar_brep_v2 import make_body,snapshot


def u_definition(k1=.42,k2=.38,r1=2.,r2=2.5):
    return EdgeFlangeOnL.validate(replace(definition(),k_factor=k1,bend_radius_mm=r1),15.,r2,k2)


def flat_material(k1=.42,k2=.38,r1=2.,r2=2.5,frame=IDENTITY):
    # Three tangent strips: W-(r1+t), H-(r1+t)-(r2+t), F-(r2+t).
    straight=(40.-r1-2.)+(20.-r1-2.-r2-2.)+(15.-r2-2.)
    length=(straight+math.pi/2.*(r1+k1*2.)+math.pi/2.*(r2+k2*2.))/1000.
    points=[tuple(x*frame[i]+y*frame[3+i]+z*frame[6+i] for i in range(3))
        for x in (.040-length,.040) for y in (0.,.002) for z in (0.,.030)]
    return make_body(points,POLYGONS),length


@pytest.mark.parametrize('k1',[0.,.42,1.])
@pytest.mark.parametrize('k2',[0.,.38,1.])
@pytest.mark.parametrize('r1,r2',[(2.,2.5),(3.,1.5)])
def test_both_explicit_allowances_and_full_material_box(k1,k2,r1,r2):
    body,length=flat_material(k1,k2,r1,r2);expected=expected_flat_u_geometry(u_definition(k1,k2,r1,r2),IDENTITY)
    assert flat_u_body_matches(dict(bodies=[snapshot(body)]),expected)
    assert expected['developed_length_mm']==pytest.approx(length*1000.)
    assert expected['volume_mm3']==pytest.approx(length*.002*.030*1e9)
    assert expected['surface_area_mm2']==pytest.approx(2.*(length*.002+length*.030+.002*.030)*1e6)
    assert expected['k_factors']==[k1,k2]


def test_rotated_flat_keeps_original_fixed_free_end():
    frame=(0.,1.,0.,0.,0.,1.,1.,0.,0.,0.,0.,0.,1.,0.,0.,0.)
    body,_=flat_material(frame=frame)
    expected=expected_flat_u_geometry(u_definition(),frame)
    assert flat_u_body_matches(dict(bodies=[snapshot(body)]),expected)
    assert not flat_u_body_matches(dict(bodies=[snapshot(body)]),expected_flat_u_geometry(u_definition(),IDENTITY))


@pytest.mark.parametrize('k1,k2',[(.5,.38),(.42,.5)])
def test_wrong_allowance_on_either_bend_cannot_match(k1,k2):
    body,_=flat_material()
    assert not flat_u_body_matches(dict(bodies=[snapshot(body)]),expected_flat_u_geometry(u_definition(k1,k2),IDENTITY))


@pytest.mark.parametrize('flattened',[False,True])
@pytest.mark.parametrize('side',[0,1])
def test_full_original_horizontal_fixed_face_in_each_state(flattened,side):
    _,length=flat_material();low=.040-length if flattened else .004
    points=[[x,side*.002,z] for x in (low,.040) for z in (0.,.030)]
    face=dict(pid_hex='native-reference',owner_body_is_current=True,is_plane=True,
        normal_opposes_surface=False,vertices=points,plane_parameters=[0.,1. if side else -1.,0.]+points[0])
    assert fixed_u_leg_from_face(face,u_definition(),IDENTITY,flattened=flattened)=='x'
    moved=deepcopy(face);moved['vertices'][0][0]+=.001
    with pytest.raises(ExecutionFailure):fixed_u_leg_from_face(moved,u_definition(),IDENTITY,flattened=flattened)
    with pytest.raises(ExecutionFailure):fixed_u_leg_from_face(face,u_definition(),IDENTITY,flattened=not flattened)


def test_foreign_incomplete_boundary_does_not_match_same_volume():
    body,_=flat_material();geometry=dict(bodies=[snapshot(body)]);expected=expected_flat_u_geometry(u_definition(),IDENTITY)
    geometry['bodies'][0]['faces'][0]['normal_opposes_surface']=not geometry['bodies'][0]['faces'][0]['normal_opposes_surface']
    assert not flat_u_body_matches(geometry,expected)
