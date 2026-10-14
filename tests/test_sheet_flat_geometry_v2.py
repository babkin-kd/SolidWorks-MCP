"""Independent native-shaped flat boxes; these tests are not CAD acceptance."""

from copy import deepcopy
import math
import random

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.sheet_flat_geometry import expected_flat_l_geometry,flat_l_body_matches,fixed_l_leg_from_face
from test_part_creation_v2 import IDENTITY
from test_sheet_profile_definition_v2 import definition
from test_planar_brep_v2 import make_body,snapshot


POLYGONS=[[0,1,3,2],[4,6,7,5],[0,4,5,1],[2,3,7,6],[0,2,6,4],[1,5,7,3]]


def native_flat(leg='x',k=.42,frame=IDENTITY):
    # Independent fixture: straight legs 36+16, neutral arc 90 degrees,
    # thickness 2 and longitudinal length 30. Free end of the fixed leg stays.
    developed=.052+math.pi/2.*(.002+k*.002)
    ranges=((.040-developed,.040),(0.,.002),(0.,.030)) if leg=='x' else ((0.,.002),(.020-developed,.020),(0.,.030))
    points=[tuple(x*frame[i]+y*frame[3+i]+z*frame[6+i] for i in range(3))
        for x in ranges[0] for y in ranges[1] for z in ranges[2]]
    return make_body(points,POLYGONS)


@pytest.mark.parametrize('leg',['x','y'])
@pytest.mark.parametrize('k',[0.,.42,.5,1.])
def test_complete_flat_material_boundary_uses_explicit_k_and_native_fixed_leg(leg,k):
    expected=expected_flat_l_geometry(definition(k_factor=k),IDENTITY,leg)
    geometry=dict(bodies=[snapshot(native_flat(leg,k))])
    assert flat_l_body_matches(geometry,expected)
    assert expected['developed_length_mm']==pytest.approx(52.+math.pi/2.*(2.+2.*k))
    assert expected['volume_mm3']==pytest.approx((52.+math.pi/2.*(2.+2.*k))*2.*30.)
    assert not flat_l_body_matches(geometry,expected_flat_l_geometry(definition(k_factor=k),IDENTITY,'y' if leg=='x' else 'x'))


def test_flat_volume_is_not_the_folded_volume_invariant_for_arbitrary_k():
    assert expected_flat_l_geometry(definition(k_factor=.5),IDENTITY,'x')['volume_mm3']==pytest.approx(definition(k_factor=.5).volume_mm3)
    assert abs(expected_flat_l_geometry(definition(),IDENTITY,'x')['volume_mm3']-definition().volume_mm3)>15.
    assert not flat_l_body_matches(dict(bodies=[snapshot(native_flat(k=.5))]),expected_flat_l_geometry(definition(),IDENTITY,'x'))


@pytest.mark.parametrize('leg',['x','y'])
def test_native_frame_and_enumeration_are_bound_without_model_axis_assumption(leg):
    frame=(0.,1.,0.,0.,0.,1.,1.,0.,0.,0.,0.,0.,1.,0.,0.,0.)
    body=native_flat(leg,frame=frame);rng=random.Random(64)
    rng.shuffle(body.vertices);rng.shuffle(body.edges);rng.shuffle(body.faces)
    for face in body.faces:
        loop=face.loops[0];loop.ordered=loop.ordered[2:]+loop.ordered[:2]
    geometry=dict(bodies=[snapshot(body)])
    assert flat_l_body_matches(geometry,expected_flat_l_geometry(definition(),frame,leg))
    assert not flat_l_body_matches(geometry,expected_flat_l_geometry(definition(),IDENTITY,leg))


@pytest.mark.parametrize('fault',['extra_body','missing_edge','edge_pair','duplicate_vertex','position','face_normal','face_position','face_loop','wrong_face','wrong_coedge','broken_cycle','wrong_scope'])
def test_same_census_or_box_does_not_replace_full_intended_boundary(fault):
    geometry=dict(bodies=[snapshot(native_flat())]);body=geometry['bodies'][0]
    if fault=='extra_body':geometry['bodies'].append(deepcopy(body))
    elif fault=='missing_edge':body['edges'].pop()
    elif fault=='edge_pair':body['edges'][0]['end']=body['edges'][0]['start']
    elif fault=='duplicate_vertex':body['vertices'][0]=list(body['vertices'][1])
    elif fault=='position':body['vertices'][0][0]=(float.fromhex(body['vertices'][0][0])+1e-6).hex()
    elif fault=='face_normal':body['faces'][0]['normal_opposes_surface']=not body['faces'][0]['normal_opposes_surface']
    elif fault=='face_position':body['faces'][0]['plane_parameters'][3:6]=[(v+1e-3).hex() for v in map(float.fromhex,body['faces'][0]['plane_parameters'][:3])]
    elif fault=='face_loop':body['faces'][0]['loops'].append(deepcopy(body['faces'][0]['loops'][0]))
    elif fault=='wrong_face':body['faces'][0]=deepcopy(body['faces'][1])
    elif fault=='wrong_coedge':body['faces'][0]['loops'][0]['coedges'][0]['edge']=body['faces'][0]['loops'][0]['coedges'][1]['edge']
    elif fault=='broken_cycle':body['faces'][0]['loops'][0]['coedges'][0]['end']=body['faces'][0]['loops'][0]['coedges'][0]['start']
    elif fault=='wrong_scope':body['scope']='counts_only'
    assert not flat_l_body_matches(geometry,expected_flat_l_geometry(definition(),IDENTITY,'x'))


@pytest.mark.parametrize('leg',[None,True,'','X','unknown',[]])
def test_unproved_fixed_leg_is_rejected_before_any_native_call(leg):
    with pytest.raises(ExecutionFailure) as error:expected_flat_l_geometry(definition(),IDENTITY,leg)
    assert error.value.code=='sheet_fixed_face_unsupported'


def fixed_face(leg='x',side=0,flattened=False,frame=IDENTITY):
    # Fixture source is a full straight leg face, not the computed flat DTO.
    varying=0 if leg=='x' else 1;constant=1-varying
    end=.040 if leg=='x' else .020
    low=end-(.052+math.pi/2.*.00284) if flattened else .004
    points=[]
    for location in (low,end):
        for z in (0.,.030):
            local=[0.,0.,z];local[varying]=location;local[constant]=side*.002
            points.append([sum(local[j]*frame[3*j+i] for j in range(3)) for i in range(3)])
    normal=[(1. if side else -1.)*v for v in frame[3*constant:3*constant+3]]
    return dict(pid_hex='strong_native_face_reference',owner_body_is_current=True,is_plane=True,
        normal_opposes_surface=False,vertices=points,plane_parameters=normal+points[0])


@pytest.mark.parametrize('leg',['x','y'])
@pytest.mark.parametrize('side',[0,1])
@pytest.mark.parametrize('flattened',[False,True])
def test_fixed_face_proof_binds_complete_corners_position_normal_and_free_end(leg,side,flattened):
    face=fixed_face(leg,side,flattened)
    assert fixed_l_leg_from_face(face,definition(),IDENTITY,flattened=flattened)==leg
    with pytest.raises(ExecutionFailure):fixed_l_leg_from_face(face,definition(),IDENTITY,flattened=not flattened)
    face['normal_opposes_surface']=True;face['plane_parameters'][:3]=[-v for v in face['plane_parameters'][:3]]
    assert fixed_l_leg_from_face(face,definition(),IDENTITY,flattened=flattened)==leg


def test_rotated_native_fixed_face_is_not_inferred_from_model_axis_or_body_box():
    frame=(0.,1.,0.,0.,0.,1.,1.,0.,0.,0.,0.,0.,1.,0.,0.,0.)
    face=fixed_face('y',1,False,frame)
    assert fixed_l_leg_from_face(face,definition(),frame)=='y'
    with pytest.raises(ExecutionFailure):fixed_l_leg_from_face(face,definition(),IDENTITY)


@pytest.mark.parametrize('fault',['not_current','missing_pid','not_plane','sense_unknown','extra_corner','missing_corner','moved_corner','wrong_end','normal','plane','nonfinite','empty','boolean_coordinate'])
def test_unbound_or_partial_fixed_face_does_not_authorize_flattening(fault):
    face=fixed_face()
    if fault=='not_current':face['owner_body_is_current']=False
    elif fault=='missing_pid':face['pid_hex']=''
    elif fault=='not_plane':face['is_plane']=False
    elif fault=='sense_unknown':face['normal_opposes_surface']=None
    elif fault=='extra_corner':face['vertices'].append([0.,0.,0.])
    elif fault=='missing_corner':face['vertices'].pop()
    elif fault=='moved_corner':face['vertices'][0][0]+=.001
    elif fault=='wrong_end':
        for point in face['vertices']:point[0]+=.001
    elif fault=='normal':face['plane_parameters'][:3]=[1.,0.,0.]
    elif fault=='plane':face['plane_parameters'][4]=.001
    elif fault=='nonfinite':face['vertices'][0][0]=float('nan')
    elif fault=='empty':face={}
    elif fault=='boolean_coordinate':face['vertices'][0][0]=True
    with pytest.raises(ExecutionFailure) as error:fixed_l_leg_from_face(face,definition(),IDENTITY)
    assert error.value.code=='sheet_fixed_face_unsupported'
