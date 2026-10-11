"""Finite point transforms and evidence-based native ray classification."""
import math
from .documents import rejected

BOUNDARY_TOLERANCE_M = 1e-8
MAX_RAY_HITS = 100000
RAY_DIRECTIONS = tuple(tuple(x/math.hypot(*v) for x in v)
                       for v in ((1., .371, .233), (.173, 1., .419), (.283, .227, 1.)))


def point3(value, code='invalid_measurement_point'):
    if (not isinstance(value, (tuple, list)) or len(value) != 3
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise rejected(code, 'Expected three finite coordinates; no bool/string coercion.')
    return [float(x) for x in value]


def component_local_point_m(transform, point_mm):
    delta = [x-y for x, y in zip(point_mm, transform['origin_mm'])]
    return point3([sum(a*x for a, x in zip(axis, delta))*.001
                   for axis in transform['axes_in_assembly']], 'measurement_numeric_overflow')


def assembly_point_mm(transform, local_m):
    return point3([transform['origin_mm'][k]+1000.*sum(transform['axes_in_assembly'][i][k]*local_m[i] for i in range(3))
                   for k in range(3)], 'measurement_numeric_overflow')


def classify_native_rays(raw, origin):
    """All three independent directions must agree; ambiguous native flags fail."""
    code = 'point_classification_unavailable'
    if not isinstance(raw, (tuple, list)) or len(raw) != 2:
        raise rejected(code, 'Native ray count and hit records required.')
    count, values = raw
    if type(count) is not int or not 0 <= count <= MAX_RAY_HITS:
        raise rejected(code, 'Invalid native ray count or hit budget exceeded.')
    if values is None:values = ()
    if (not isinstance(values, (tuple, list)) or len(values) != count*9
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in values)):
        raise rejected(code, 'Expected nine finite values per native hit with requested normals.')
    hits = [[] for _ in RAY_DIRECTIONS]
    for offset in range(0, len(values), 9):
        body_index, ray_index, flags, *rest = values[offset:offset+9]
        if body_index != 0 or int(ray_index) != ray_index or not 0 <= ray_index < 3 or int(flags) != flags or not 0 <= flags <= 63:
            raise rejected(code, 'Native hit has a foreign body/ray index or invalid flags.')
        ray = int(ray_index);direction = RAY_DIRECTIONS[ray]
        delta = [x-y for x, y in zip(rest[:3], origin)]
        along = sum(a*x for a, x in zip(direction, delta))
        residual = math.hypot(*(x-along*a for x, a in zip(delta, direction)))
        if not math.isfinite(along) or along <= BOUNDARY_TOLERANCE_M or residual > BOUNDARY_TOLERANCE_M:
            raise rejected(code, 'Native hit is not a positive point on the requested zero-radius ray.')
        hits[ray].append((along, int(flags) & 48))
    locations = []
    for ray in hits:
        if not ray:
            locations.append('outside');continue
        ray.sort()
        first = ray[0][0]
        directions = {flags for along, flags in ray if along-first <= BOUNDARY_TOLERANCE_M}
        if directions not in ({16}, {32}):
            raise rejected(code, 'Closest ray hit lacks an unambiguous native entry/exit flag.')
        locations.append('outside' if directions == {16} else 'inside')
    if len(set(locations)) != 1:
        raise rejected(code, 'Independent native rays disagree; no heuristic fallback.')
    return locations[0]
