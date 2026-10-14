"""Independent folded-sheet native-shaped topology, not CAD acceptance."""

from copy import deepcopy
import math
import random
import struct

import pytest

from solidworks_mcp.cad_analytical_brep import analytical_body_snapshot
from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.sheet_profile_definition import SheetLProfile,sheet_l_body_matches
from test_planar_brep_v2 import make_body,CurveParamData
from test_cylinder_brep_v2 import Surface
from test_arc_brep_v2 import Arc,read,transform_body
from test_part_creation_v2 import IDENTITY


def definition(**changes):
    return SheetLProfile.validate(**{**dict(plane_object_id='feat_'+'a'*32,leg_x_mm=40.,leg_y_mm=20.,
        length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42),**changes})


def folded_body(w=.04,h=.02,length=.03,thickness=.002,radius=.002):
    outer=radius+thickness
    profile=[(0.,h),(0.,outer),(outer,0.),(w,0.),(w,thickness),(outer,thickness),(thickness,outer),(thickness,h)]
    points=[(x,y,z) for z in (0.,length) for x,y in profile]
    sections=[[0,1,6,7],[1,2,5,6],[2,3,4,5]]
    polygons=[list(reversed(p)) for p in sections]+[[v+8 for v in p] for p in sections]+[[i,(i+1)%8,(i+1)%8+8,i+8] for i in range(8)]
    body=make_body(points,polygons)
    for face in body.faces:face.surface=Surface('plane',face.surface.params)
    # Set complete oriented cap normals independently of local chord corners.
    for index in range(3):body.faces[index].surface=Surface('plane',(0.,0.,-1.,0.,0.,0.))
    for index in range(3,6):body.faces[index].surface=Surface('plane',(0.,0.,1.,0.,0.,length))
    for segment,r,inward in ((1,outer,False),(5,radius,True)):
        body.faces[6+segment].surface=Surface('cylinder',(outer,outer,0.,0.,0.,1.,r))
        body.faces[6+segment].sense=inward
        ends={profile[segment],profile[segment+1]}
        for edge in body.edges:
            if {edge.start.point[:2],edge.end.point[:2]}!=ends:continue
            edge.curve=Arc((outer,outer,edge.start.point[2]),r)
            class Trim(CurveParamData):
                CurveType=3002
                UMinValue=math.pi
                UMaxValue=1.5*math.pi
            edge.parameter_data=Trim(edge)
            edge.parameter_data.Sense=edge.start.point[0]<outer
            edge.Evaluate2=lambda u,d,curve=edge.curve:curve.Evaluate2(u,d)+(struct.unpack('<d',struct.pack('<ii',1,32766))[0],)
    for edge in body.edges:
        if not isinstance(edge.curve,Arc):edge.curve.IsCircle=lambda:False
    return body


def test_both_inner_and_outer_native_cylinders_and_all_four_arcs_are_matched():
    expected=definition().expected_geometry(IDENTITY);body=folded_body();snapshot=read(body)
    assert sheet_l_body_matches({'bodies':[snapshot]},expected)
    assert analytical_body_snapshot(body,identity=lambda obj:[obj.ident])==snapshot
    assert (len(snapshot['vertices']),len(snapshot['edges']),len(snapshot['faces']))==(16,28,14)
    assert len([e for e in snapshot['edges'] if e['kind']=='arc'])==4
    assert {f['normal_opposes_surface'] for f in snapshot['faces'] if f['surface_type']=='cylinder'}=={False,True}
    assert expected['volume_mm3']==pytest.approx((2.*(40.+20.-8.)+math.pi/4.*(16.-4.))*30.)
    assert expected['neutral_axis_developed_length_mm']==pytest.approx(52.+math.pi/2.*2.84)


def test_full_shape_matches_rotated_plane_and_root_enumeration_permutation():
    rotation=((0.,1.,0.),(0.,0.,1.),(1.,0.,0.))
    frame=[*rotation[0],*rotation[1],*rotation[2],0.,0.,0.,1.,0.,0.,0.]
    body=transform_body(folded_body(),rotation,(0.,0.,0.));before=read(body)
    rng=random.Random(18)
    for array in (body.vertices,body.edges,body.faces):rng.shuffle(array)
    for face in body.faces:
        face.loops[0].shift=3;face.loops[0].reverse_array=True
    assert read(body)==before
    assert sheet_l_body_matches({'bodies':[before]},definition().expected_geometry(frame))


@pytest.mark.parametrize('body',[lambda:folded_body(thickness=.0015),lambda:folded_body(radius=.003),
    lambda:folded_body(length=.031),lambda:folded_body(w=.041)])
def test_wrong_thickness_radius_length_or_leg_never_matches_expected_sheet(body):
    assert not sheet_l_body_matches({'bodies':[read(body())]},definition().expected_geometry(IDENTITY))


@pytest.mark.parametrize('fault',['inner_orientation','outer_radius','arc_radius','wrong_face','arc_span','line_pair'])
def test_correct_census_cannot_substitute_for_full_material_boundaries(fault):
    geometry={'bodies':[read(folded_body())]};body=geometry['bodies'][0]
    cylinders=[f for f in body['faces'] if f['surface_type']=='cylinder']
    inner=next(f for f in cylinders if f['normal_opposes_surface'])
    outer=next(f for f in cylinders if not f['normal_opposes_surface'])
    arc=next(e for e in body['edges'] if e['kind']=='arc')
    if fault=='inner_orientation':inner['normal_opposes_surface']=False
    elif fault=='outer_radius':outer['surface_parameters'][6]=(.005).hex()
    elif fault=='arc_radius':arc['circle_parameters'][6]=(.001).hex()
    elif fault=='wrong_face':inner['loops']=deepcopy(outer['loops'])
    elif fault=='arc_span':arc['trimmed_curve']['u_max']=(float.fromhex(arc['trimmed_curve']['u_max'])+.001).hex()
    else:body['edges'][0]['start']=body['edges'][0]['end']
    assert not sheet_l_body_matches(geometry,definition().expected_geometry(IDENTITY))


@pytest.mark.parametrize('changes',[dict(plane_object_id='first'),dict(thickness_mm=True),dict(bend_radius_mm=0.),
    dict(k_factor=True),dict(k_factor=float('nan')),dict(k_factor=-.01),dict(k_factor=1.01),dict(k_factor=10**400),dict(feature_name='SheetMetal'),
    dict(leg_x_mm=4.),dict(leg_y_mm=3.9)])
def test_invalid_or_self_intersecting_input_rejected_before_cad(changes):
    with pytest.raises(ExecutionFailure):definition(**changes)


def test_k_factor_is_required_and_changes_development_without_changing_folded_body():
    with pytest.raises(TypeError):SheetLProfile.validate(plane_object_id='feat_'+'a'*32,leg_x_mm=40.,leg_y_mm=20.,
        length_mm=30.,thickness_mm=2.,bend_radius_mm=2.)
    a,b=definition(k_factor=.3),definition(k_factor=.6)
    assert a.volume_mm3==b.volume_mm3 and a.developed_length_mm!=b.developed_length_mm
    assert sheet_l_body_matches({'bodies':[read(folded_body())]},b.expected_geometry(IDENTITY))
