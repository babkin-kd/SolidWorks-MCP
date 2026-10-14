"""Metric-preserving witness tampering must fail independent frame/axis oracles."""
from copy import deepcopy
import math
from pathlib import Path
import sys

import pytest


scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_witnesses as helper
finally:
    sys.path.remove(scripts)

FRAME = dict(origin_mm=[50., 10., 20.], axes_in_model=[[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]])


def axis(*, aggregate=False):
    value = dict(measurement_scope=('resolved_component_aggregate_' if aggregate else 'resolved_part_component_') + 'axis_distance_v1',
        coordinate_frame='explicit_rigid_frame', length_unit='mm', distance_mm=2.,
        includes_hidden_bodies=True, includes_surface_bodies=False,
        intersection_classification='not_provided', axis_semantics='infinite_line',
        axis_origin_mm=[0., 0., 0.], axis_direction=[0., 1., 0.],
        axis_origin_assembly_mm=[50., 10., 20.], axis_direction_assembly=[-1., 0., 0.],
        closest_points_mm=[[2., 3., 0.], [0., 3., 0.]],
        closest_points_assembly_mm=[[47., 12., 20.], [47., 10., 20.]])
    args = dict(kind='axis', expected_mm=2., frame=FRAME, aggregate=aggregate,
                axis_origin_mm=[0., 0., 0.], axis_direction=[0., 5., 0.])
    return value, args


@pytest.mark.parametrize('aggregate', [False, True])
def test_independent_shift_rotation_and_nonunit_axis_input(aggregate):
    value, args = axis(aggregate=aggregate)
    helper.check_witnesses(value, **args)


def test_equal_distance_after_root_translation_still_rejects_wrong_frame():
    value, args = axis()
    for point in value['closest_points_assembly_mm']:point[0] += 1.
    assert math.dist(*value['closest_points_assembly_mm']) == 2.
    with pytest.raises(ValueError, match='coordinates'):helper.check_witnesses(value, **args)


def test_swapped_equal_metric_witnesses_reject_wrong_axis_membership():
    value, args = axis()
    value['closest_points_mm'].reverse()
    value['closest_points_assembly_mm'].reverse()
    with pytest.raises(ValueError, match='input line'):helper.check_witnesses(value, **args)


def test_nonperpendicular_equal_metric_witnesses_rejected():
    value, args = axis()
    value['closest_points_mm'] = [[0., 5., 0.], [0., 3., 0.]]
    value['closest_points_assembly_mm'] = [[45., 10., 20.], [47., 10., 20.]]
    with pytest.raises(ValueError, match='perpendicular'):helper.check_witnesses(value, **args)


@pytest.mark.parametrize('field,bad', [('distance_mm', True), ('distance_mm', math.nan),
    ('length_unit', 'm'), ('axis_direction', [0., 5., 0.]),
    ('includes_surface_bodies', True), ('includes_hidden_bodies', False),
    ('intersection_classification', 'clearance_safe'), ('axis_semantics', 'ray')])
def test_wrong_semantics_units_and_nonfinite_data_rejected(field, bad):
    value, args = axis()
    value[field] = bad
    with pytest.raises(ValueError):helper.check_witnesses(value, **args)


@pytest.mark.parametrize('direction', [[0., 0., 0.], [True, 0., 0.], [math.inf, 0., 0.], [1.7e308] * 3])
def test_invalid_independent_axis_input_rejected(direction):
    value, args = axis()
    args['axis_direction'] = direction
    with pytest.raises(ValueError):helper.check_witnesses(value, **args)


def test_point_inside_measures_boundary_distance_with_exact_classification():
    value = dict(measurement_scope='resolved_component_aggregate_point_distance_v1',
        coordinate_frame='explicit_rigid_frame', length_unit='mm', distance_mm=6.,
        includes_hidden_bodies=True, includes_surface_bodies=False,
        distance_semantics='minimum_to_individual_solid_boundary',
        point_mm=[0., 0., 0.], nearest_mm=[6., 0., 0.],
        point_assembly_mm=[50., 10., 20.], nearest_assembly_mm=[50., 16., 20.],
        point_location='inside', inside=True)
    args = dict(kind='point', expected_mm=6., frame=FRAME, aggregate=True,
                point_mm=[0., 0., 0.], expected_location='inside')
    helper.check_witnesses(value, **args)
    value['inside'] = False
    with pytest.raises(ValueError, match='classifier'):helper.check_witnesses(value, **args)


def test_pair_in_root_has_no_frame_and_metric_does_not_classify_interference():
    value = dict(measurement_scope='resolved_part_component_distance_v1',
        coordinate_frame='assembly_model', length_unit='mm', distance_mm=15.,
        includes_hidden_bodies=True, includes_surface_bodies=False,
        intersection_classification='not_provided', closest_points_mm=[[0., 0., 0.], [15., 0., 0.]])
    helper.check_witnesses(value, kind='pair', expected_mm=15.)
    with pytest.raises(ValueError, match='only root'):
        helper.check_witnesses(value, kind='pair', expected_mm=15., frame=FRAME)


def test_aggregate_pair_checks_both_root_witnesses_against_explicit_frame():
    value = dict(measurement_scope='resolved_component_aggregate_distance_v1',
        coordinate_frame='explicit_rigid_frame', length_unit='mm', distance_mm=84.,
        includes_hidden_bodies=True, includes_surface_bodies=False,
        intersection_classification='not_provided',
        closest_points_mm=[[0., 0., 0.], [84., 0., 0.]],
        closest_points_assembly_mm=[[50., 10., 20.], [50., 94., 20.]])
    helper.check_witnesses(value, kind='pair', aggregate=True, expected_mm=84., frame=FRAME)
    value['closest_points_assembly_mm'][1][2] = 21.
    with pytest.raises(ValueError):
        helper.check_witnesses(value, kind='pair', aggregate=True, expected_mm=84., frame=FRAME)
