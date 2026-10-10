"""Independent full native-shaped boundaries; these are not CAD acceptance."""

from copy import deepcopy
import math

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.part_hole import hole_body_matches
from solidworks_mcp.part_pattern_definition import LinearHolePattern
from test_hole_brep_v2 import plate, read


BASE = dict(width_m=1., height_m=1., depth_m=1.,
            plane_transform=(1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.))
CIRCLE = dict(centre_x_m=.2, centre_y_m=.5, diameter_m=.1)


def definition(**changes):
    return LinearHolePattern.validate(**{**dict(base_object_id='feat_'+'a'*32,
        object_id='feat_'+'b'*32, seed_object_id='feat_'+'c'*32,
        direction_edge_id='obj_'+'d'*32, count=3, spacing_mm=200.), **changes})


@pytest.mark.parametrize('axis', [0, 1])
def test_expected_pattern_matches_independently_constructed_complete_boundary(axis):
    circle = {**CIRCLE, 'centre_y_m': .2}
    expected = definition().expected_geometry(BASE, circle, axis)
    holes = tuple((.2 + (i*.2 if axis==0 else 0.), .2 + (i*.2 if axis==1 else 0.), .05)
                  for i in range(3))
    geometry = {'bodies': [read(plate(holes))]}
    assert hole_body_matches(geometry, expected)
    assert expected['volume_mm3'] == pytest.approx((1.-3*math.pi*.05**2)*1e9)
    assert expected['surface_area_mm2'] == pytest.approx((6.-6*math.pi*.05**2+6*math.pi*.05)*1e6)
    assert (expected['vertex_count'],expected['edge_count'],expected['face_count']) == (8,18,9)


@pytest.mark.parametrize('holes', [
    ((.2,.5,.05),(.4,.5,.05),(.6,.55,.05)),  # same volume/area/census; shifted last hole
    ((.2,.5,.05),(.4,.5,.05),(.7,.5,.05)),   # incorrect step
    ((.2,.5,.05),(.4,.5,.06),(.6,.5,.05)),   # incorrect diameter
    ((.2,.5,.05),(.4,.5,.05)),              # missing instance
    ((.2,.5,.05),(.4,.5,.05),(.6,.5,.05),(.8,.5,.05)),
])
def test_matching_never_accepts_wrong_location_diameter_or_instance_count(holes):
    expected = definition().expected_geometry(BASE, CIRCLE, 0)
    assert not hole_body_matches({'bodies':[read(plate(holes))]}, expected)


@pytest.mark.parametrize('fault', ['wall_circle_swap', 'cap_circle_swap', 'duplicate_wall'])
def test_complete_graph_association_is_required_after_reader(fault):
    geometry = {'bodies':[read(plate(((.2,.5,.05),(.4,.5,.05),(.6,.5,.05))))]}
    body = geometry['bodies'][0]
    walls = [row for row in body['faces'] if row['surface_type']=='cylinder']
    caps = [row for row in body['faces'] if any(not loop['outer'] for loop in row['loops'])]
    if fault == 'wall_circle_swap':
        walls[0]['loops'][0], walls[1]['loops'][0] = walls[1]['loops'][0], walls[0]['loops'][0]
    elif fault == 'cap_circle_swap':
        loop = next(loop for loop in caps[0]['loops'] if not loop['outer'])
        other = next(loop for loop in caps[1]['loops'] if not loop['outer'])
        loop['coedges'],other['coedges'] = other['coedges'],loop['coedges']
    else:
        walls[1]['surface_parameters'] = deepcopy(walls[0]['surface_parameters'])
    assert not hole_body_matches(geometry, definition().expected_geometry(BASE, CIRCLE, 0))


@pytest.mark.parametrize('changes', [dict(count=True),dict(count=3.),dict(count=1),dict(count=65),
    dict(spacing_mm=0.),dict(spacing_mm=float('nan')),dict(spacing_mm=True),
    dict(base_object_id='first'),dict(direction_edge_id='Edge1'),
    dict(seed_object_id='feat_'+'b'*32),dict(feature_name='Pattern')])
def test_invalid_definition_rejects_before_native_access(changes):
    with pytest.raises(ExecutionFailure):
        definition(**changes)


@pytest.mark.parametrize('spacing,count', [(100.,3),(99.,3),(400.,3)])
def test_material_and_base_bounds_reject_even_positive_spacing(spacing,count):
    with pytest.raises(ExecutionFailure):
        definition(spacing_mm=spacing,count=count).expected_geometry(BASE,CIRCLE,0)
