"""Engineering input and complete native-shaped result; no CAD acceptance."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import math

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.part_revolve import BaseRevolve, PartRevolveCatalog, cylinder_body_matches
from test_cylinder_brep_v2 import cylinder, read
from test_part_creation_v2 import IDENTITY
from test_part_creation_domain_v2 import setup as part_setup


def definition(**changes):
    return BaseRevolve.validate(**{'plane_object_id':'feat_'+'a'*32,'radius_mm':10.,'height_mm':30.,**changes})


def geometry(**parameters):
    return {'bodies':[read(cylinder(axis=(0.,1.,0.),radial=(0.,0.,1.),**parameters))]}


def test_full_turn_engineering_values_and_russian_names_are_explicit():
    item = definition()
    assert item.profile_m == ((0.,0.),(.01,0.),(.01,.03),(0.,.03))
    assert item.axis == 'profile_y'
    assert item.volume_mm3 == pytest.approx(9424.777960769379)
    assert item.surface_area_mm2 == pytest.approx(2513.2741228718345)
    assert item.sketch_name == 'Эскиз вращения' and item.feature_name == 'Вращение основания'
    with pytest.raises(FrozenInstanceError): item.radius_mm = 20.


@pytest.mark.parametrize('changes',[{'radius_mm':True},{'height_mm':'30'},{'radius_mm':0.},
    {'radius_mm':float('nan')},{'radius_mm':10000001.},{'height_mm':10**400},
    {'axis':'first'},{'axis':'z'},{'plane_object_id':'Передняя'},
    {'sketch_name':'Sketch'},{'feature_name':'эскиз вращения'},{'body_name':'Body'}])
def test_invalid_input_rejected_before_native_preparation(changes):
    with pytest.raises(ExecutionFailure): definition(**changes)


def test_every_circle_and_surface_matches_exact_target_frame():
    assert cylinder_body_matches(geometry(),definition(),list(IDENTITY))
    frame = [0.,0.,1.,1.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.]
    body = read(cylinder(axis=(1.,0.,0.),radial=(0.,1.,0.)))
    assert cylinder_body_matches({'bodies':[body]},definition(),frame)


@pytest.mark.parametrize('fault',['radius','height','translation','circle_axis','side_radius','side_axis','side_offset',
    'cap_plane','cap_normal','missing_cap','second_body','wrong_scope'])
def test_equal_counts_and_reported_mass_do_not_accept_wrong_boundary(fault):
    candidate = geometry()
    body = candidate['bodies'][0]
    if fault in ('radius','height','translation'):
        candidate = geometry(**{'radius':.011} if fault=='radius' else {'height':.031} if fault=='height' else {'origin':(.001,0.,0.)})
    if fault == 'circle_axis': body['edges'][0]['circle_parameters'][3:6] = [v.hex() for v in (1.,0.,0.)]
    side = next(face for face in body['faces'] if face['surface_type']=='cylinder')
    cap = next(face for face in body['faces'] if face['surface_type']=='plane')
    if fault == 'side_radius': side['surface_parameters'][6] = .011.hex()
    if fault == 'side_axis': side['surface_parameters'][3:6] = [v.hex() for v in (1.,0.,0.)]
    if fault == 'side_offset': side['surface_parameters'][0] = .001.hex()
    if fault == 'cap_plane': cap['surface_parameters'][4] = .001.hex()
    if fault == 'cap_normal': cap['normal_opposes_surface'] = not cap['normal_opposes_surface']
    if fault == 'missing_cap': body['faces'].remove(cap)
    if fault == 'second_body': candidate['bodies'].append(deepcopy(body))
    if fault == 'wrong_scope': body['scope'] = 'partial_cylinder'
    assert not cylinder_body_matches(candidate,definition(),list(IDENTITY))


def test_read_preparation_binds_axis_and_lengths_and_preserves_empty_scope(part_setup):
    adapter,parts,ids,planes = part_setup
    catalog = PartRevolveCatalog(parts.dimensions)
    before = deepcopy([model.state for model in adapter.models])
    parameters = dict(plane_object_id=planes[0],radius_mm=10.,height_mm=30.)
    prepared = catalog.prepare_base_revolve(ids[0],'Основная',**parameters)
    assert prepared['revision_scope'] == 'empty_part_full_turn_cylinder_revolve_v1'
    assert prepared['definition']['axis'] == 'profile_y'
    assert prepared['expected_geometry']['volume_mm3'] == pytest.approx(3000.*math.pi)
    assert prepared == catalog.prepare_base_revolve(ids[0],'Основная',**parameters)
    assert prepared['revision'] != catalog.prepare_base_revolve(ids[0],'Основная',**dict(parameters,radius_mm=11.))['revision']
    assert before == [model.state for model in adapter.models]
