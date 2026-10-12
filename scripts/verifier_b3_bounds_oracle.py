"""Independent analytic B3-I08 support oracle, never approximate AABB corners.

Fixed fixtures: two 20x10x5 blocks, a 15x10 plane and a radius-6 cylinder
along model Y of length 30. The native producer separately proves those exact
owned geometries and complete body membership. This module does not call CAD.
"""
import itertools
import math

from solidworks_mcp.measurement_frames import RigidMeasurementFrame


BOXES = (((0., 0., 0.), (20., 10., 5.)),
         ((40., 0., 0.), (60., 10., 5.)),
         ((80., 0., 0.), (95., 10., 0.)))
TOLERANCE_MM = 1e-6


def support_bounds(*, boxes=BOXES, cylinder=False, frame=None):
    """Compute exact support in a validated explicit right-handed rigid frame."""
    validated = RigidMeasurementFrame.model_validate({
        'origin_mm': [0., 0., 0.],
        'axes_in_model': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]} if frame is None else frame)
    if type(cylinder) is not bool:
        raise ValueError('Explicit fixture kind required.')
    if not cylinder:
        if type(boxes) not in (list, tuple) or not boxes:
            raise ValueError('Nonempty exact analytic fixture required.')
        for box in boxes:
            if type(box) not in (list, tuple) or len(box) != 2:
                raise ValueError('Complete analytic box required.')
            for point in box:
                if (type(point) not in (list, tuple) or len(point) != 3
                        or any(type(x) not in (int, float) or not math.isfinite(x) for x in point)):
                    raise ValueError('Three finite analytic coordinates required.')
            if any(a > b for a, b in zip(*box)):
                raise ValueError('Analytic box bounds reversed.')
    low, high = [], []
    for axis in validated.axes_in_model:
        offset = sum(a * x for a, x in zip(axis, validated.origin_mm))
        if cylinder:
            # Support of the circular cross-section, not its model-space box.
            radial = 6. * math.hypot(axis[0], axis[2])
            lo = -radial + min(0., 30. * axis[1]) - offset
            hi = radial + max(0., 30. * axis[1]) - offset
        else:
            values = [sum(a*x for a, x in zip(axis, point)) - offset
                      for minimum, maximum in boxes
                      for point in itertools.product(*zip(minimum, maximum))]
            lo, hi = min(values), max(values)
        if not math.isfinite(lo) or not math.isfinite(hi) or not math.isfinite(hi - lo):
            raise ValueError('Analytic support overflow.')
        low.append(lo); high.append(hi)
    return dict(min_mm=low, max_mm=high, size_mm=[b-a for a, b in zip(low, high)])


def validate_bounds(result, *, context, body_ids, body_id=None, body_type='all',
                    boxes=BOXES, cylinder=False, frame=None):
    """Bind exact native bounds DTO to the explicit query and independent support.

All three coordinates, full distinct body census and read postconditions are
required. A truncated vector must not pass zip-based comparisons. Returns
analytic evidence only; full native before/after and exact ownership stay with
the concrete driver, and this result never accepts B3 or authorizes cleanup.
"""
    if type(result) is not dict or type(context) is not dict:
        raise ValueError('Actual structured bounds and explicit context required.')
    if (set(context) != {'document_id', 'configuration', 'expected_observation_revision'}
            or any(type(value) is not str or not value for value in context.values())):
        raise ValueError('Exact explicit context required.')
    if (type(body_ids) not in (list, tuple) or not body_ids
            or any(type(value) is not str or not value for value in body_ids)
            or len(set(body_ids)) != len(body_ids)):
        raise ValueError('Independent complete distinct native body references required.')
    if body_id is not None and (type(body_id) is not str or list(body_ids) != [body_id]):
        raise ValueError('Explicit single body scope differs.')
    if body_type not in ('all', 'solid', 'surface'):
        raise ValueError('Invalid analytic body scope.')
    for field, expected in (
        ('document_id', context['document_id']), ('configuration', context['configuration']),
        ('observation_revision', context['expected_observation_revision']),
        ('body_id', body_id), ('body_type', body_type), ('length_unit', 'mm'),
        ('measurement_scope', 'part_native_support_bounds_v1'),
        ('method', 'native_extreme_points')):
        if result.get(field) != expected:
            raise ValueError('Bounds context, native scope or method differs.')
    observed = result.get('body_ids')
    if (type(result.get('body_count')) is not int or result['body_count'] != len(body_ids)
            or type(observed) is not list or len(observed) != len(body_ids)
            or any(type(value) is not str for value in observed)
            or set(observed) != set(body_ids)):
        raise ValueError('Bounds complete body census differs.')
    postconditions = result.get('read_postconditions')
    if (result.get('includes_hidden_bodies') is not True
            or result.get('approximate_body_box_used') is not False
            or result.get('model_geometry_modified') is not False
            or type(postconditions) is not dict
            or set(postconditions) != {'body_membership_confirmed', 'repeated_extrema_confirmed'}
            or any(value is not True for value in postconditions.values())):
        raise ValueError('Native support or read postconditions not confirmed.')
    validated = RigidMeasurementFrame.model_validate({
        'origin_mm': [0., 0., 0.],
        'axes_in_model': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]} if frame is None else frame)
    expected_frame = dict(kind='model' if frame is None else 'explicit_rigid',
                          **validated.model_dump(mode='json'))
    actual_frame = result.get('coordinate_frame')
    if (type(actual_frame) is not dict or set(actual_frame) != set(expected_frame)
            or actual_frame['kind'] != expected_frame['kind']):
        raise ValueError('Bounds frame differs from the explicit query.')
    actual_validated = RigidMeasurementFrame.model_validate({
        key: actual_frame[key] for key in ('origin_mm', 'axes_in_model')})
    if actual_validated.model_dump(mode='json') != validated.model_dump(mode='json'):
        raise ValueError('Bounds frame differs from the explicit query.')
    expected = support_bounds(boxes=boxes, cylinder=cylinder, frame=frame)
    actual = result.get('bounding_box_mm')
    if type(actual) is not dict or set(actual) != set(expected):
        raise ValueError('Complete three-vector bounds required.')
    for key, wanted in expected.items():
        vector = actual[key]
        if (type(vector) is not list or len(vector) != 3
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)
                or any(not math.isclose(x, y, rel_tol=0., abs_tol=TOLERANCE_MM)
                       for x, y in zip(vector, wanted))):
            raise ValueError('Native support differs from independent analytic extrema.')
    return dict(scope='bounded_b3_i08_analytic_bounds_v1', expected=expected,
                tolerance_mm=TOLERANCE_MM, receipt_validated=True,
                native_b3_accepted=False, cleanup_authorized=False)
