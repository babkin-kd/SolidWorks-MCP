"""Pure engineering input and full shape matching; no native writer/MCP acceptance."""

from copy import deepcopy
import math

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.part_hole import ThroughHole, hole_body_matches
from test_hole_brep_v2 import plate, read, circles


FRAME = [1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]
PARAMETERS = {'object_id':'feat_'+'a'*32,'plane_object_id':'feat_'+'b'*32,
              'centre_x_mm':500.,'centre_y_mm':500.,'diameter_mm':200.}
BASE = {'width_m':1.,'height_m':1.,'depth_m':1.,'plane_transform':FRAME}


def definition(**changes):
    return ThroughHole.validate(**(PARAMETERS|changes))


def test_engineering_definition_retains_explicit_targets_and_russian_names():
    value = definition()
    assert value.object_id == PARAMETERS['object_id']
    assert value.plane_object_id == PARAMETERS['plane_object_id']
    assert value.sketch_name=='Эскиз отверстия' and value.feature_name=='Сквозное отверстие'
    expected = value.expected_geometry(BASE)
    assert expected['volume_mm3']==(1.-math.pi*.1**2)*1e9
    assert math.isclose(expected['surface_area_mm2'],(6.-2.*math.pi*.1**2+2.*math.pi*.1)*1e6)
    assert [expected[k] for k in ('vertex_count','edge_count','face_count')]==[8,14,7]
    assert expected['circle_centres_si']==[[v.hex() for v in p] for p in ((.5,.5,0.),(.5,.5,1.))]
    assert definition(centre_x_mm=500,centre_y_mm=500,diameter_mm=200)==value


@pytest.mark.parametrize('parameter',['centre_x_mm','centre_y_mm','diameter_mm'])
@pytest.mark.parametrize('value',[True,False,None,'5',0.,-1.,.00099,math.nan,math.inf,-math.inf,10**400,10000001.])
def test_invalid_engineering_lengths_are_rejected_without_native_access(parameter,value):
    with pytest.raises(ExecutionFailure): definition(**{parameter:value})


@pytest.mark.parametrize('parameter',['object_id','plane_object_id'])
@pytest.mark.parametrize('value',[None,True,'','Front Plane','feat_1234','doc_'+'a'*32])
def test_base_and_plane_must_be_explicit_opaque_feature_references(parameter,value):
    with pytest.raises(ExecutionFailure): definition(**{parameter:value})


@pytest.mark.parametrize('changes',[{'sketch_name':'Circle'},{'feature_name':'Hole'},
    {'sketch_name':'Отверстие','feature_name':'отверстие'}])
def test_new_display_names_must_be_russian_and_distinct(changes):
    with pytest.raises(ExecutionFailure): definition(**changes)


@pytest.mark.parametrize('changes',[
    {'centre_x_mm':100.},{'centre_x_mm':99.}, {'centre_x_mm':900.},
    {'centre_y_mm':100.},{'centre_y_mm':900.},{'diameter_mm':1000.},
])
def test_whole_circle_requires_material_margin_on_all_four_sides(changes):
    with pytest.raises(ExecutionFailure) as error: definition(**changes).expected_geometry(BASE)
    assert error.value.code=='hole_outside_material'


@pytest.mark.parametrize('key',['width_m','height_m','depth_m'])
@pytest.mark.parametrize('value',[True,0.,math.nan,math.inf,.0000009,10001.])
def test_unsupported_base_extents_are_rejected(key,value):
    with pytest.raises(ExecutionFailure): definition().expected_geometry(BASE|{key:value})


def test_complete_reader_result_matches_requested_single_hole():
    expected = definition().expected_geometry(BASE)
    assert hole_body_matches({'bodies':[read(plate())]},expected)
    assert not hole_body_matches({'bodies':[read(plate(((.25,.5,.08),(.75,.5,.1))))]},expected)


@pytest.mark.parametrize('hole',[(.4,.5,.1),(.5,.4,.1),(.5,.5,.11)])
def test_different_valid_native_hole_shape_is_rejected(hole):
    # All these are complete valid solid boundaries with the same 8/14/7 census.
    assert not hole_body_matches({'bodies':[read(plate((hole,)))]},definition().expected_geometry(BASE))


def test_rotated_reference_plane_is_matched_in_full_model_coordinates():
    rotate = lambda p:(-p[1],p[2],-p[0])
    frame = [*rotate((1.,0.,0.)),*rotate((0.,1.,0.)),*rotate((0.,0.,1.)),0.,0.,0.,1.,0.,0.,0.]
    body = plate()
    for vertex in body.vertices:
        vertex.point = rotate(vertex.point)
    for face in body.faces:
        p = face.surface.params
        face.surface.params = (rotate(p[:3])+rotate(p[3:]) if face.surface.IsPlane()
                               else rotate(p[:3])+rotate(p[3:6])+(p[6],))
    for edge in circles(body):
        p = edge.curve.parameters
        edge.curve.parameters = rotate(p[:3])+rotate(p[3:6])+(p[6],)
        edge.trim.StartPoint = rotate(edge.trim.StartPoint)
        edge.trim.EndPoint = rotate(edge.trim.EndPoint)
    result = {'bodies':[read(body)]}
    assert hole_body_matches(result,definition().expected_geometry(BASE|{'plane_transform':frame}))
    assert not hole_body_matches(result,definition().expected_geometry(BASE))


@pytest.mark.parametrize('fault',['missing_body','two_bodies','wrong_scope','missing_vertex',
    'wrong_vertex','missing_edge','wrong_edge','extra_face','wrong_plane','wrong_normal',
    'wrong_wall_radius','wrong_wall_axis','wrong_wall_origin','outward_wall',
    'missing_inner','wrong_inner','wrong_outer','wrong_circle_centre','wrong_circle_radius',
    'wrong_circle_axis','wrong_wall_loop','unknown_surface','malformed'])
def test_shape_proof_does_not_accept_mass_census_or_partial_boundaries(fault):
    geometry = {'bodies':[deepcopy(read(plate()))]}
    body = geometry['bodies'][0]
    wall = next(face for face in body['faces'] if face['surface_type']=='cylinder')
    cap = next(face for face in body['faces'] if any(not loop['outer'] for loop in face['loops']))
    circle = next(edge for edge in body['edges'] if edge['kind']=='circle')
    if fault=='missing_body': geometry['bodies']=[]
    if fault=='two_bodies': geometry['bodies'].append(deepcopy(body))
    if fault=='wrong_scope': body['scope']='mass_only'
    if fault=='missing_vertex': body['vertices'].pop()
    if fault=='wrong_vertex': body['vertices'][0][0]=(.02).hex()
    if fault=='missing_edge': body['edges'].pop()
    if fault=='wrong_edge': body['edges'][0]['end']=body['edges'][0]['start']
    if fault=='extra_face': body['faces'].append(deepcopy(wall))
    if fault=='wrong_plane': cap['surface_parameters'][5]=(.02).hex()
    if fault=='wrong_normal': cap['surface_parameters'][:3]=[0.0.hex(),1.0.hex(),0.0.hex()]
    if fault=='wrong_wall_radius': wall['surface_parameters'][6]=(.11).hex()
    if fault=='wrong_wall_axis': wall['surface_parameters'][3:6]=[0.0.hex(),1.0.hex(),0.0.hex()]
    if fault=='wrong_wall_origin': wall['surface_parameters'][0]=(.6).hex()
    if fault=='outward_wall': wall['normal_opposes_surface']=False
    if fault=='missing_inner': cap['loops']=[loop for loop in cap['loops'] if loop['outer']]
    if fault=='wrong_inner': next(loop for loop in cap['loops'] if not loop['outer'])['coedges'][0]['edge']=0
    if fault=='wrong_outer':
        use = next(loop for loop in cap['loops'] if loop['outer'])['coedges'][0]
        use['start'] = (use['start']+1)%8
    if fault=='wrong_circle_centre': circle['circle_parameters'][0]=(.4).hex()
    if fault=='wrong_circle_radius': circle['circle_parameters'][6]=(.11).hex()
    if fault=='wrong_circle_axis': circle['circle_parameters'][3:6]=[0.0.hex(),1.0.hex(),0.0.hex()]
    if fault=='wrong_wall_loop': wall['loops'].pop()
    if fault=='unknown_surface': cap['surface_type']='cone'
    if fault=='malformed': del body['edges']
    assert not hole_body_matches(geometry,definition().expected_geometry(BASE))
