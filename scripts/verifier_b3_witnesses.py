"""Independent metric/frame oracles for the six existing component reads.

Pure numerical validation only. Native target membership, complete census and
actual boundary witnesses must also be established by the owning CAD driver.
A consistent pair of points alone never proves a minimum or native acceptance.
"""
import math

from solidworks_mcp.measurement_frames import RigidMeasurementFrame


TOLERANCE_MM = 1e-6


def vector(value):
    if (type(value) not in (list, tuple) or len(value) != 3
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise ValueError('Exactly three finite numeric coordinates required.')
    return tuple(float(x) for x in value)


def close_vector(left, right):
    if math.dist(vector(left), vector(right)) > TOLERANCE_MM:
        raise ValueError('Independent witness/frame coordinates differ.')


def model_point(local, frame):
    point = vector(local)
    if frame is None:
        return point
    f = RigidMeasurementFrame.model_validate(frame)
    return tuple(f.origin_mm[i] + sum(f.axes_in_model[j][i] * point[j] for j in range(3))
                 for i in range(3))


def model_direction(local, frame):
    direction = vector(local)
    if frame is None:
        return direction
    f = RigidMeasurementFrame.model_validate(frame)
    return tuple(sum(f.axes_in_model[j][i] * direction[j] for j in range(3)) for i in range(3))


def unit(value):
    result = vector(value)
    norm = math.hypot(*result)
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError('Nonzero axis direction required.')
    return tuple(x / norm for x in result)


def check_witnesses(value, *, kind, expected_mm, frame=None, aggregate=False,
                    point_mm=None, axis_origin_mm=None, axis_direction=None,
                    expected_location=None):
    if kind not in ('pair', 'point', 'axis') or type(aggregate) is not bool:
        raise ValueError('Existing pair/point/axis scope required.')
    if type(expected_mm) not in (int, float) or not math.isfinite(expected_mm) or expected_mm < 0:
        raise ValueError('Independent nonnegative analytic distance required.')
    if kind == 'pair' and not aggregate and frame is not None:
        raise ValueError('Part-instance pair has only root assembly frame.')
    suffix = '' if kind == 'pair' else kind + '_'
    prefix = 'resolved_component_aggregate_' if aggregate else 'resolved_part_component_'
    if (value['measurement_scope'] != prefix + suffix + 'distance_v1'
            or value['coordinate_frame'] != ('assembly_model' if frame is None else 'explicit_rigid_frame')
            or value['length_unit'] != 'mm'
            or value['includes_hidden_bodies'] is not True or value['includes_surface_bodies'] is not False):
        raise ValueError('Exact native measurement scope, frame and units required.')
    actual = value['distance_mm']
    if (type(actual) not in (int, float) or not math.isfinite(actual)
            or not math.isclose(actual, expected_mm, abs_tol=TOLERANCE_MM, rel_tol=0.)):
        raise ValueError('Native metric differs from independent analytic distance.')
    if kind == 'point':
        if value['distance_semantics'] != 'minimum_to_individual_solid_boundary':
            raise ValueError('Point-to-boundary semantics required.')
        close_vector(value['point_mm'], point_mm)
        local = (vector(value['point_mm']), vector(value['nearest_mm']))
        root = (vector(value['point_assembly_mm']), vector(value['nearest_assembly_mm']))
        if expected_location not in ('inside', 'outside', 'boundary') or value['point_location'] != expected_location:
            raise ValueError('Independent native point location required.')
        expected_inside = (True if expected_location == 'inside'
                           else False if expected_location == 'outside' else None)
        if value['inside'] is not expected_inside:
            raise ValueError('Point location and inside classifier disagree.')
    else:
        if value['intersection_classification'] != 'not_provided':
            raise ValueError('Distance does not classify interference.')
        local = value['closest_points_mm']
        root = value['closest_points_assembly_mm'] if aggregate or kind == 'axis' else local
        if type(local) not in (tuple, list) or type(root) not in (tuple, list) or len(local) != 2 or len(root) != 2:
            raise ValueError('Exactly two complete metric witnesses required.')
        local, root = tuple(map(vector, local)), tuple(map(vector, root))
    for coordinates in (local, root):
        if not math.isclose(math.dist(*coordinates), expected_mm, abs_tol=TOLERANCE_MM, rel_tol=0.):
            raise ValueError('Witness separation differs from analytic distance.')
    for point, transformed in zip(local, root):
        close_vector(model_point(point, frame), transformed)
    if kind == 'axis':
        if value['axis_semantics'] != 'infinite_line':
            raise ValueError('Axis must be an infinite line.')
        origin, direction = vector(axis_origin_mm), unit(axis_direction)
        close_vector(value['axis_origin_mm'], origin)
        if math.dist(vector(value['axis_direction']), direction) > 1e-12:
            raise ValueError('Axis direction is not the independently normalized input.')
        close_vector(value['axis_origin_assembly_mm'], model_point(origin, frame))
        close_vector(value['axis_direction_assembly'], model_direction(direction, frame))
        delta = tuple(x - y for x, y in zip(local[1], origin))
        along = sum(x * y for x, y in zip(delta, direction))
        if math.hypot(*(x - along * d for x, d in zip(delta, direction))) > TOLERANCE_MM:
            raise ValueError('Axis witness is not on the infinite input line.')
        if abs(sum((x - y) * d for x, y, d in zip(local[0], local[1], direction))) > TOLERANCE_MM:
            raise ValueError('Nearest separation is not perpendicular to the axis.')
