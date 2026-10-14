"""Finite numerics for an infinite line certified by exact body supports."""
import math
from .documents import rejected
from .point_measurement import point3

AXIS_TOLERANCE_M = 1e-8


def unit_direction(value):
    values = point3(value, 'invalid_measurement_axis')
    scale = max(abs(x) for x in values)
    if scale == 0.:raise rejected('invalid_measurement_axis', 'Axis direction must be nonzero.')
    scaled = [x/scale for x in values]
    length = math.hypot(*scaled)
    return [x/length for x in scaled]


def dot(a, b):
    try:result = math.fsum(x*y for x, y in zip(a, b))
    except (ValueError, OverflowError) as exc:
        raise rejected('measurement_numeric_overflow', 'Axis projection overflowed.') from exc
    if not math.isfinite(result):raise rejected('measurement_numeric_overflow', 'Axis projection must be finite.')
    return result


def anchor_axis(origin_m, direction, near_m):
    along = dot([b-a for a, b in zip(origin_m, near_m)], direction)
    anchor = point3([a+along*d for a, d in zip(origin_m, direction)], 'measurement_numeric_overflow')
    # A remote input origin must not silently lose the perpendicular offset.
    residual = [a-o for a, o in zip(anchor, origin_m)]
    projected = dot(residual, direction)
    if math.hypot(*(x-projected*d for x, d in zip(residual, direction))) > AXIS_TOLERANCE_M:
        raise rejected('measurement_numeric_overflow', 'Axis reanchoring lost its line coordinates.')
    return anchor


def bracket_axis(anchor, direction, supports):
    if not supports or any(not math.isfinite(x) for pair in supports for x in pair):
        raise rejected('native_axis_support_unavailable', 'Finite supports for every solid required.')
    if any(low > high+AXIS_TOLERANCE_M for low, high in supports):
        raise rejected('native_axis_support_unavailable', 'Directional minimum exceeds maximum.')
    low = min(pair[0] for pair in supports);high = max(pair[1] for pair in supports)
    margin = max(1e-6, (high-low)*1e-6, 32.*max(math.ulp(x) for x in (*anchor, low, high)))
    ends = [point3([a+t*d for a, d in zip(anchor, direction)], 'measurement_numeric_overflow')
            for t in (low-margin, high+margin)]
    if math.dist(*ends) <= AXIS_TOLERANCE_M:
        raise rejected('native_axis_support_unavailable', 'Temporary edge must have a positive finite span.')
    return ends, [low, high]


def check_axis_witnesses(points_m, anchor, direction, support_range):
    component, axis = points_m
    delta = [x-a for x, a in zip(axis, anchor)];along = dot(delta, direction)
    if (not math.isfinite(along) or
            math.hypot(*(x-along*d for x, d in zip(delta, direction))) > AXIS_TOLERANCE_M or
            not support_range[0]-AXIS_TOLERANCE_M <= along <= support_range[1]+AXIS_TOLERANCE_M or
            abs(dot([a-b for a, b in zip(component, axis)], direction)) > AXIS_TOLERANCE_M):
        raise rejected('component_axis_distance_inconsistent', 'Native witnesses must belong to the infinite line and certified solid projection interval.')
