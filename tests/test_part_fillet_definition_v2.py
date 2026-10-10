"""Independent intended full rounded boundary and reject-only input checks."""

from copy import deepcopy
import math

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.part_fillet_definition import SelectedEdgeFillet, cuboid_edge, fillet_body_matches
from test_arc_brep_v2 import rounded_body,read,transform_body
from test_part_creation_v2 import IDENTITY


BASE=dict(width_m=.04,height_m=.02,depth_m=.01,plane_transform=IDENTITY)


def definition(**changes):
    return SelectedEdgeFillet.validate(**{**dict(object_id='feat_'+'a'*32,edge_id='obj_'+'b'*32,radius_mm=2.),**changes})


def test_full_independent_native_shaped_result_matches_all_requested_edges_faces_and_trims():
    expected=definition().expected_geometry(BASE,2,(0,0))
    geometry={'bodies':[read(rounded_body())]}
    assert fillet_body_matches(geometry,expected)
    assert expected['volume_mm3']==pytest.approx((.04*.02-(1-math.pi/4)*.002**2)*.01*1e9)
    assert not fillet_body_matches({'bodies':[read(rounded_body(radius=.003))]},expected)


@pytest.mark.parametrize('axis',range(3))
@pytest.mark.parametrize('corner',[(0,0),(0,1),(1,0),(1,1)])
def test_all_twelve_explicit_source_edges_have_distinct_full_expected_boundaries(axis,corner):
    extents=(.04,.02,.01);transverse=[i for i in range(3) if i!=axis]
    points=[]
    for z in (0.,extents[axis]):
        p=[0.,0.,0.];p[axis]=z
        for i,bit in zip(transverse,corner):p[i]=bit*extents[i]
        points.append(tuple(p))
    assert cuboid_edge(points,BASE)==(axis,corner)
    assert cuboid_edge(list(reversed(points)),BASE)==(axis,corner)
    expected=definition().expected_geometry(BASE,axis,corner)
    assert len(expected['vertices_si'])==10 and len(expected['edge_pairs'])==15
    # Construct each physical rounded body independently in the transverse
    # profile, then rigidly map it to the selected one of twelve base edges.
    parity=-1 if axis==1 else 1
    signs=[1-2*bit for bit in corner]+[parity*(1-2*corner[0])*(1-2*corner[1])]
    rotation=[];translation=[0.,0.,0.]
    for source,target in enumerate([*transverse,axis]):
        row=[0.,0.,0.];row[target]=float(signs[source]);rotation.append(row)
        translation[target]=extents[target] if signs[source]<0 else 0.
    body=rounded_body(width=extents[transverse[0]],height=extents[transverse[1]],depth=extents[axis])
    assert fillet_body_matches({'bodies':[read(transform_body(body,rotation,translation))]},expected)


def test_full_matching_in_rotated_native_reference_plane():
    rotation=((0.,1.,0.),(0.,0.,1.),(1.,0.,0.));translation=(0.,0.,0.)
    frame=[*rotation[0],*rotation[1],*rotation[2],*translation,1.,0.,0.,0.]
    expected=definition().expected_geometry({**BASE,'plane_transform':frame},2,(0,0))
    geometry={'bodies':[read(transform_body(rounded_body(),rotation,translation))]}
    assert fillet_body_matches(geometry,expected)


@pytest.mark.parametrize('fault',['vertex','line_pair','arc_span','circle_axis','cap_loop','wall_loop','plane_normal','wall_radius','wall_sense'])
def test_same_census_and_mass_cannot_replace_complete_target_geometry(fault):
    geometry={'bodies':[read(rounded_body())]};body=geometry['bodies'][0]
    arc=next(e for e in body['edges'] if e['kind']=='arc')
    plane=next(f for f in body['faces'] if f['surface_type']=='plane')
    wall=next(f for f in body['faces'] if f['surface_type']=='cylinder')
    if fault=='vertex':body['vertices'][0][0]=(.001).hex()
    elif fault=='line_pair':body['edges'][0]['start']=body['edges'][0]['end']
    elif fault=='arc_span':arc['trimmed_curve']['u_max']=(float.fromhex(arc['trimmed_curve']['u_max'])+.01).hex()
    elif fault=='circle_axis':arc['circle_parameters'][3:6]=[1..hex(),0..hex(),0..hex()]
    elif fault=='cap_loop':plane['loops'][0]['coedges'][0]['start']=plane['loops'][0]['coedges'][0]['end']
    elif fault=='wall_loop':wall['loops'][0]=deepcopy(plane['loops'][0])
    elif fault=='plane_normal':plane['normal_opposes_surface']=not plane['normal_opposes_surface']
    elif fault=='wall_radius':wall['surface_parameters'][6]=(.003).hex()
    else:wall['normal_opposes_surface']=True
    assert not fillet_body_matches(geometry,definition().expected_geometry(BASE,2,(0,0)))


@pytest.mark.parametrize('changes',[dict(object_id='first'),dict(edge_id='Edge1'),dict(radius_mm=True),
    dict(radius_mm=0),dict(radius_mm=float('nan')),dict(radius_mm=float('inf')),dict(feature_name='Fillet')])
def test_invalid_input_before_native_access(changes):
    with pytest.raises(ExecutionFailure):definition(**changes)


@pytest.mark.parametrize('points',[((0.,0.,0.),(.04,.02,0.)),((0.,0.,0.),(0.,0.,0.)),
    ((0.,0.,0.),(.02,0.,0.)),((0.,.01,0.),(.04,.01,0.)),((float('nan'),0.,0.),(.04,0.,0.))])
def test_partial_diagonal_internal_and_nonfinite_edges_rejected(points):
    with pytest.raises(ExecutionFailure):cuboid_edge(points,BASE)


def test_radius_leaving_no_transverse_material_rejected():
    with pytest.raises(ExecutionFailure):definition(radius_mm=10.).expected_geometry(BASE,2,(0,0))
