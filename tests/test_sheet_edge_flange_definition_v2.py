"""Independent native-shaped two-bend U fixture; not native CAD acceptance."""

from copy import deepcopy
from dataclasses import replace
import math
import random
import struct

import pytest

from solidworks_mcp.cad_analytical_brep import analytical_body_snapshot
from solidworks_mcp.sheet_edge_flange_definition import EdgeFlangeOnL,sheet_u_body_matches,l_flange_edge_points,flange_revision
from solidworks_mcp.jobs import ExecutionFailure
from test_sheet_profile_definition_v2 import definition
from test_part_creation_v2 import IDENTITY
from test_planar_brep_v2 import make_body,CurveParamData
from test_cylinder_brep_v2 import Surface
from test_arc_brep_v2 import Arc,read,transform_body
from test_part_creation_domain_v2 import setup as part_setup


def u_body(upper_radius=.0025,flange=.015):
    # Independent physical coordinates and five material strips. Neither the
    # production expected_geometry nor its vertices/loops constructs this body.
    p=[(0.,.02-upper_radius-.002),(0.,.004),(.004,0.),(.04,0.),(.04,.002),(.004,.002),
        (.002,.004),(.002,.02-upper_radius-.002),(upper_radius+.002,.018),(.015,.018),(.015,.02),(upper_radius+.002,.02)]
    p[9]=(flange,.018);p[10]=(flange,.02)
    strips=[[0,1,6,7],[1,2,5,6],[2,3,4,5],[7,8,11,0],[8,9,10,11]]
    polygons=[list(reversed(face)) for face in strips]+[[i+12 for i in face] for face in strips]
    polygons += [[i,(i+1)%12,(i+1)%12+12,i+12] for i in range(12)]
    body=make_body([(x,y,z) for z in (0.,.03) for x,y in p],polygons)
    for face in body.faces:face.surface=Surface('plane',face.surface.params)
    for index in range(10):body.faces[index].surface=Surface('plane',(0.,0.,-1. if index<5 else 1.,0.,0.,0. if index<5 else .03))
    for index,cx,cy,radius,inward,minimum in (
            (1,.004,.004,.004,False,math.pi),(5,.004,.004,.002,True,math.pi),
            (7,upper_radius+.002,.02-upper_radius-.002,upper_radius,True,math.pi/2.),
            (11,upper_radius+.002,.02-upper_radius-.002,upper_radius+.002,False,math.pi/2.)):
        body.faces[10+index].surface=Surface('cylinder',(cx,cy,0.,0.,0.,1.,radius));body.faces[10+index].sense=inward
        ends={p[index],p[(index+1)%12]}
        for edge in body.edges:
            if {edge.start.point[:2],edge.end.point[:2]}!=ends:continue
            edge.curve=Arc((cx,cy,edge.start.point[2]),radius)
            class Trim(CurveParamData):
                CurveType=3002
            trim=Trim(edge);trim.UMinValue=minimum;trim.UMaxValue=minimum+math.pi/2.
            trim.Sense=edge.start.point[0]<cx if minimum==math.pi else edge.start.point[0]==cx
            edge.parameter_data=trim
            edge.Evaluate2=lambda u,d,curve=edge.curve:curve.Evaluate2(u,d)+(struct.unpack('<d',struct.pack('<ii',1,32766))[0],)
    for edge in body.edges:
        if not isinstance(edge.curve,Arc):edge.curve.IsCircle=lambda:False
    return body


def flange(**changes):return EdgeFlangeOnL.validate(definition(),**{**dict(flange_length_mm=15.,bend_radius_mm=2.5,k_factor=.38),**changes})


def test_complete_two_bend_boundary_and_independent_area_and_allowance():
    d=flange();expected=d.expected_geometry(IDENTITY);body=u_body();snapshot=read(body)
    assert sheet_u_body_matches({'bodies':[snapshot]},expected)
    assert analytical_body_snapshot(body,identity=lambda obj:[obj.ident])==snapshot
    assert (len(snapshot['vertices']),len(snapshot['edges']),len(snapshot['faces']))==(24,44,22)
    assert len([e for e in snapshot['edges'] if e['kind']=='arc'])==8
    assert len([f for f in snapshot['faces'] if f['surface_type']=='cylinder'])==4
    section=2.*(75.-8.-9.)+math.pi/4.*(16.-4.+20.25-6.25)
    perimeter=2.*(75.-8.-9.)+4.+math.pi/2.*(4.+2.+4.5+2.5)
    assert d.volume_mm3==pytest.approx(section*30.)
    assert d.surface_area_mm2==pytest.approx(2.*section+perimeter*30.)
    assert d.developed_length_mm==pytest.approx(58.+math.pi/2.*(2.+.42*2.+2.5+.38*2.))


def test_full_boundary_survives_native_root_permutation_and_rotated_plane():
    rotation=((0.,1.,0.),(0.,0.,1.),(1.,0.,0.));origin=(0.,0.,0.)
    frame=[*rotation[0],*rotation[1],*rotation[2],*origin,1.,0.,0.,0.]
    body=transform_body(u_body(),rotation,origin);before=read(body);rng=random.Random(28)
    for roots in (body.vertices,body.edges,body.faces):rng.shuffle(roots)
    for face in body.faces:face.loops[0].shift=2;face.loops[0].reverse_array=True
    assert read(body)==before
    assert sheet_u_body_matches({'bodies':[before]},flange().expected_geometry(frame))


def test_displaced_plane_remains_explicitly_outside_existing_source_scope():
    frame=list(IDENTITY);frame[9]=.07
    with pytest.raises(ExecutionFailure,match='origin'):flange().expected_geometry(frame)


@pytest.mark.parametrize('kind',['vertex','radius','cylinder_normal','cap_normal','edge_removed','face_removed','second_body'])
def test_same_overall_census_or_mass_never_substitutes_for_complete_boundary(kind):
    expected=flange().expected_geometry(IDENTITY);s=read(u_body());g={'bodies':[s]}
    if kind=='vertex':s['vertices'][0][0]=(.0002).hex()
    elif kind=='radius':next(e for e in s['edges'] if e['kind']=='arc')['circle_parameters'][-1]=(.009).hex()
    elif kind=='cylinder_normal':
        f=next(f for f in s['faces'] if f['surface_type']=='cylinder');f['normal_opposes_surface']=not f['normal_opposes_surface']
    elif kind=='cap_normal':next(f for f in s['faces'] if f['surface_type']=='plane')['normal_opposes_surface']=True
    elif kind=='edge_removed':s['edges'].pop()
    elif kind=='face_removed':s['faces'].pop()
    else:g['bodies'].append(deepcopy(s))
    assert not sheet_u_body_matches(g,expected)


@pytest.mark.parametrize('radius,length',[(2.,15.),(3.5,18.),(.5,9.)])
def test_explicit_second_radius_and_length_match_independent_fixture(radius,length):
    d=EdgeFlangeOnL.validate(definition(),length,radius,.38)
    assert sheet_u_body_matches({'bodies':[read(u_body(radius/1000.,length/1000.))]},d.expected_geometry(IDENTITY))


def test_two_explicit_k_factors_change_neutral_length_but_not_folded_boundary():
    first=flange();second=replace(first,k_factor=.55)
    assert first.volume_mm3==second.volume_mm3
    assert first.developed_length_mm!=second.developed_length_mm
    assert sheet_u_body_matches({'bodies':[read(u_body())]},second.expected_geometry(IDENTITY))


@pytest.mark.parametrize('length,radius,k',[(0.,2.,.38),(-1.,2.,.38),(15.,0.,.38),(15.,True,.38),
    (True,2.,.38),(15.,2.,True),(15.,2.,'0.38'),(15.,2.,math.nan),(15.,2.,math.inf),(15.,2.,-.01),
    (15.,2.,1.01),(15.,15.,.38),(4.,2.,.38),(10000001.,2.,.38),(15.,10000001.,.38)])
def test_invalid_or_colliding_material_rejected_before_native_access(length,radius,k):
    with pytest.raises(ExecutionFailure):EdgeFlangeOnL.validate(definition(),length,radius,k)


@pytest.mark.parametrize('name',['Flange','', 'Отбортовка@1'])
def test_new_feature_requires_valid_russian_name(name):
    with pytest.raises(ExecutionFailure):EdgeFlangeOnL.validate(definition(),15.,2.,.38,feature_name=name)


def test_full_selected_edge_accepts_either_native_orientation_and_rotated_frame():
    edge=((.002,.02,0.),(.002,.02,.03))
    for points in (edge,tuple(reversed(edge))):assert l_flange_edge_points(points,definition(),IDENTITY)==edge
    frame=[0.,1.,0.,0.,0.,1.,1.,0.,0.,0.,0.,0.,1.,0.,0.,0.]
    world=((0.,.002,.02),(.03,.002,.02))
    assert l_flange_edge_points(world,definition(),frame)==world
    outer=((0.,.02,0.),(0.,.02,.03))
    assert l_flange_edge_points(outer,definition(),IDENTITY,edge_side='outer')==outer


@pytest.mark.parametrize('points',[
    ((0.,.02,0.),(0.,.02,.03)), # opposite face chooses a different fold direction
    ((0.,.004,0.),(0.,.004,.03)), # lower bend seam
    ((0.,.02,0.),(0.,.02,.01)), # partial source edge
    ((0.,.02,0.),(.002,.02,0.)), # transverse thickness edge
    ((0.,.02,0.),(0.,.02,.03),(0.,.02,.03)),
    ((0.,.02,0.),(0.,.02,math.nan)),((0.,.02,0.),(0.,.02,True)),
    ((0.,.02),(0.,.02,.03)),((0.,.02,0.),(0.,.02,'0.03'))])
def test_other_edges_or_invalid_native_coordinates_are_refused(points):
    with pytest.raises(ExecutionFailure):l_flange_edge_points(points,definition(),IDENTITY)


def revision(state,**changes):
    args=dict(document_id='doc_exact',configuration='Основная',base_object_id='feat_'+'a'*32,
        edge_pid_hex='ab12',points=((.002,.02,0.),(.002,.02,.03)),controls={'dimension_input':False})
    args.update(changes);return flange_revision(state,flange(),**args)


def test_revision_excludes_only_redundant_tolerance_checked_mass(part_setup):
    from test_sheet_parameters_v2 import material_state
    from solidworks_mcp.sheet_parameters import SheetParameterCatalog
    state,source=material_state(part_setup);other=deepcopy(state)
    other['evidence']['volume_mm3']+=4e-13;other['evidence']['area_mm2']+=4e-13
    for value in (state,other):SheetParameterCatalog._source(value,'Основная',source.plane_object_id)
    assert revision(state)==revision(other)
    assert state!=other # helper must leave its caller's complete evidence intact
    assert revision(state)!=revision(state,edge_pid_hex='cd34')
    assert revision(state)!=revision(state,controls={'dimension_input':True})
    assert revision(state)!=revision(state,configuration='Другая')


@pytest.mark.parametrize('change',['body_vertex','member_name','base_radius','driver','relief'])
def test_full_source_changes_remain_in_revision(part_setup,change):
    from test_sheet_parameters_v2 import material_state
    state,_=material_state(part_setup);other=deepcopy(state)
    if change=='body_vertex':other['semantic']['geometry']['bodies'][0]['vertices'][0][0]=(.005).hex()
    elif change=='member_name':other['evidence']['members'][0]['name']='Чужое имя'
    elif change=='base_radius':other['evidence']['base_parameters']['BendRadius']=.003
    elif change=='driver':other['dimension_revision']='rev_foreign'
    else:other['evidence']['parameter_options']['template']['ReliefRatio']=.9
    assert revision(state)!=revision(other)


def test_flat_source_refused_before_edge_flange_revision(part_setup):
    from test_sheet_parameters_v2 import material_state
    state,_=material_state(part_setup,flattened=True)
    with pytest.raises(ExecutionFailure,match='folded'):revision(state)
