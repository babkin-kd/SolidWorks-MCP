"""Analytic geometry and forged DTOs only; no CAD or installed acceptance."""
from copy import deepcopy
import importlib.util
import math
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('b3_bounds_oracle',
    Path(__file__).resolve().parents[1] / 'scripts/verifier_b3_bounds_oracle.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
CTX = dict(document_id='doc', configuration='Основная', expected_observation_revision='obs')


def result(*, frame=None, boxes=helper.BOXES, cylinder=False, body_ids=None, body_id=None):
    ids = body_ids or (['cylinder'] if cylinder else ['solid_a', 'solid_b', 'surface'])
    return dict(document_id='doc', configuration='Основная', observation_revision='obs',
                body_id=body_id, body_type='all', body_ids=list(ids), body_count=len(ids),
                length_unit='mm', measurement_scope='part_native_support_bounds_v1',
                method='native_extreme_points', includes_hidden_bodies=True,
                approximate_body_box_used=False, model_geometry_modified=False,
                read_postconditions=dict(body_membership_confirmed=True, repeated_extrema_confirmed=True),
                coordinate_frame=dict(kind='model' if frame is None else 'explicit_rigid',
                    **(frame or dict(origin_mm=[0., 0., 0.],
                    axes_in_model=[[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]))),
                bounding_box_mm=helper.support_bounds(boxes=boxes, cylinder=cylinder, frame=frame))


def validate(value, **args):
    defaults = dict(context=CTX, body_ids=['solid_a', 'solid_b', 'surface'])
    defaults.update(args)
    return helper.validate_bounds(value, **defaults)


def test_fixed_model_union_has_known_support():
    assert helper.support_bounds() == dict(min_mm=[0., 0., 0.], max_mm=[95., 10., 5.],
                                          size_mm=[95., 10., 5.])
    evidence = validate(result())
    assert evidence['receipt_validated'] is True
    assert evidence['native_b3_accepted'] is evidence['cleanup_authorized'] is False


def test_planar_zero_extent_is_supported():
    boxes = (helper.BOXES[2],)
    value = result(boxes=boxes, body_ids=['surface'], body_id='surface')
    evidence = validate(value, boxes=boxes, body_ids=['surface'], body_id='surface')
    assert evidence['expected']['size_mm'] == [15., 10., 0.]


def test_shifted_rotated_second_block_independent_values():
    frame = dict(origin_mm=[10., -20., 3.], axes_in_model=[[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]])
    boxes = (helper.BOXES[1],)
    bounds = helper.support_bounds(boxes=boxes, frame=frame)
    assert bounds == dict(min_mm=[20., -50., -3.], max_mm=[30., -30., 2.], size_mm=[10., 20., 5.])
    validate(result(frame=frame, boxes=boxes, body_ids=['solid_b'], body_id='solid_b'),
             frame=frame, boxes=boxes, body_ids=['solid_b'], body_id='solid_b')


def test_tilted_circular_support_rejects_aabb_corner_substitute():
    c = math.sqrt(.5)
    frame = dict(origin_mm=[0., 0., 0.], axes_in_model=[[c, 0., c], [0., 1., 0.], [-c, 0., c]])
    value = result(frame=frame, cylinder=True)
    assert value['bounding_box_mm']['size_mm'] == pytest.approx([12., 30., 12.])
    validate(value, frame=frame, cylinder=True, body_ids=['cylinder'])
    forged = deepcopy(value)
    forged['bounding_box_mm'] = helper.support_bounds(boxes=(((-6., 0., -6.), (6., 30., 6.)),), frame=frame)
    with pytest.raises(ValueError): validate(forged, frame=frame, cylinder=True, body_ids=['cylinder'])


@pytest.mark.parametrize('fault', ['short_min', 'short_max', 'short_size', 'nonfinite', 'bool',
                                  'relative_tolerance', 'method', 'units', 'document', 'revision',
                                  'count', 'bool_count', 'duplicate_ids', 'foreign_id', 'missing_body',
                                  'approximate', 'modified', 'hidden', 'missing_postcondition',
                                  'numeric_postcondition', 'extra_postcondition', 'frame_kind',
                                  'frame_origin', 'frame_bool', 'extra_bounds'])
def test_strict_bounds_receipt_refuses_false_positive(fault):
    value = result()
    if fault.startswith('short_'): value['bounding_box_mm'][fault[6:] + '_mm'] = [0., 0.]
    elif fault == 'nonfinite': value['bounding_box_mm']['min_mm'][0] = float('nan')
    elif fault == 'bool': value['bounding_box_mm']['min_mm'][0] = False
    elif fault == 'relative_tolerance': value['bounding_box_mm']['max_mm'][0] += 2e-6
    elif fault == 'method': value['method'] = 'body_box'
    elif fault == 'units': value['length_unit'] = 'm'
    elif fault == 'document': value['document_id'] = 'foreign'
    elif fault == 'revision': value['observation_revision'] = 'old'
    elif fault == 'count': value['body_count'] = 4
    elif fault == 'bool_count': value['body_count'] = True
    elif fault == 'duplicate_ids': value['body_ids'] = ['solid_a', 'solid_a', 'surface']
    elif fault == 'foreign_id': value['body_ids'][0] = 'foreign'
    elif fault == 'missing_body': value['body_ids'].pop()
    elif fault == 'approximate': value['approximate_body_box_used'] = True
    elif fault == 'modified': value['model_geometry_modified'] = True
    elif fault == 'hidden': value['includes_hidden_bodies'] = False
    elif fault == 'missing_postcondition': value['read_postconditions'].pop('repeated_extrema_confirmed')
    elif fault == 'numeric_postcondition': value['read_postconditions']['body_membership_confirmed'] = 1
    elif fault == 'extra_postcondition': value['read_postconditions']['unexpected'] = True
    elif fault == 'frame_kind': value['coordinate_frame']['kind'] = 'explicit_rigid'
    elif fault == 'frame_origin': value['coordinate_frame']['origin_mm'][0] = 1.
    elif fault == 'frame_bool': value['coordinate_frame']['axes_in_model'][0][0] = True
    elif fault == 'extra_bounds': value['bounding_box_mm']['unexpected'] = []
    with pytest.raises(ValueError): validate(value)


@pytest.mark.parametrize('frame', [{}, dict(origin_mm=[0., 0., 0.],
                    axes_in_model=[[1., 0., 0.], [0., 1., 0.], [0., 0., -1.]])])
def test_invalid_explicit_frame_cannot_silently_become_model(frame):
    with pytest.raises(ValueError): helper.support_bounds(frame=frame)


@pytest.mark.parametrize('boxes', [[], [([0., 0.], [1., 1.])],
                                  [([1., 0., 0.], [0., 1., 1.])],
                                  [([False, 0., 0.], [1., 1., 1.])]])
def test_incomplete_analytic_fixture_refused(boxes):
    with pytest.raises(ValueError): helper.support_bounds(boxes=boxes)


def test_explicit_single_body_scope_bound_to_census():
    with pytest.raises(ValueError): validate(result(), body_id='solid_b')
