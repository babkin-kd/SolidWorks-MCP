"""Complete, conservative boundary snapshot for native planar polyhedral solids.

No COM imports, copies, serialization, tessellation, mass or box fallbacks.
Call on the owning STA; provide canonical (possibly unhashable) COM identity
and a ``wrap(raw, interface_name)`` callback for registered dispatch wrappers.
Exact native doubles are retained as float.hex(), without rounding. Numeric
consistency tolerances only REJECT malformed input; they never merge geometry.
The supported native exact class must report a gap <= 5e-9 m. That separate
classification gate never relaxes the 1e-12 m analytical consistency checks.
This is a narrow analytical scope, not an arbitrary BREP revision mechanism.
The caller must supply its document/configuration/event/UI consistency guard.
"""

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math


PLANAR_BREP_SCOPE = 'planar_polyhedral_brep_v1'


class PlanarBrepError(ValueError):
    """An unsupported, incomplete or inconsistent snapshot; never partial success."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PlanarBrepLimits:
    max_vertices: int = 2048
    max_edges: int = 4096
    max_faces: int = 2048
    max_loops: int = 4096
    max_coedges: int = 8192
    max_loop_coedges: int = 512
    max_identity_comparisons: int = 2_000_000
    max_polygon_comparisons: int = 1_000_000
    max_coordinate_m: float = 10_000.0
    consistency_tolerance_m: float = 1e-12
    max_native_gap_m: float = 5e-9

    def __post_init__(self):
        for name in ('max_vertices', 'max_edges', 'max_faces', 'max_loops',
                     'max_coedges', 'max_loop_coedges', 'max_identity_comparisons',
                     'max_polygon_comparisons'):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 2_000_000:
                raise ValueError(f'{name} must be an integer in [1, 2000000].')
        for name in ('max_coordinate_m', 'consistency_tolerance_m', 'max_native_gap_m'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive.')
        if self.max_coordinate_m > 10_000 or self.consistency_tolerance_m > 1e-12:
            raise ValueError('Limits may tighten, never loosen, the analytical consistency gate.')
        if self.max_native_gap_m > 5e-9:
            raise ValueError('Native gap limit may tighten, never exceed 5e-9 m.')


def _fail(code, message):
    raise PlanarBrepError(code, message)


def _hex(values):
    return tuple(float(value).hex() for value in values)


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def _norm_squared(values):
    return sum(value*value for value in values)


def _line_consistent(point, line, tolerance):
    direction = tuple(Fraction(x) for x in line[3:])
    delta = tuple(Fraction(x)-Fraction(y) for x, y in zip(point, line[:3]))
    # Exact arithmetic prevents overflow/underflow from silently accepting an
    # inconsistent extremely short edge. This gate never modifies stored data.
    return _norm_squared(_cross(delta, direction)) <= Fraction(tolerance)**2 * _norm_squared(direction)


def _plane_consistent(point, plane, tolerance):
    normal = tuple(Fraction(x) for x in plane[:3])
    delta = tuple(Fraction(x)-Fraction(y) for x, y in zip(point, plane[3:]))
    distance_numerator = sum(x*y for x, y in zip(normal, delta))
    return distance_numerator**2 <= Fraction(tolerance)**2 * _norm_squared(normal)


def _points_consistent(a, b, tolerance):
    return _norm_squared(tuple(Fraction(x)-Fraction(y) for x, y in zip(a, b))) <= Fraction(tolerance)**2


def _orient(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _on_segment(a, b, p):
    return (_orient(a, b, p) == 0 and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _intersects(a, b, c, d):
    ab_c, ab_d, cd_a, cd_b = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    return ((ab_c*ab_d < 0 and cd_a*cd_b < 0) or _on_segment(a, b, c)
            or _on_segment(a, b, d) or _on_segment(c, d, a) or _on_segment(c, d, b))


def _inside(p, polygon):
    # Exact binary-rational ray crossing; boundaries have already been rejected.
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if p[0] < x:
                inside = not inside
    return inside


class _Reader:
    def __init__(self, identity, wrap, limits):
        self.identity = identity
        self.wrap = wrap or (lambda obj, interface: obj)
        self.limits = limits
        self.identities = []  # Keep canonical IUnknowns alive, without hashing.
        self.identity_comparisons = 0
        self.polygon_comparisons = 0

    def call(self, obj, name):
        try:
            return getattr(obj, name)()
        except PlanarBrepError:
            raise
        except Exception as exc:
            raise PlanarBrepError('planar_brep_native_read_failed', f'{name} failed.') from exc

    def prop(self, obj, name):
        try:
            return getattr(obj, name)
        except Exception as exc:
            raise PlanarBrepError('planar_brep_native_read_failed', f'{name} failed.') from exc

    def check_body(self, body):
        # Check3 can return a valid IFaultEntity whose Count is zero. Presence
        # of the dispatch object alone is not evidence of a defective body.
        raw = self.prop(body, 'Check3')
        if raw is None:
            return
        faults = self.obj(raw, 'IFaultEntity')
        count = self.prop(faults, 'Count')
        if type(count) is not int or count < 0:
            _fail('planar_brep_incomplete', 'Native fault count is invalid.')
        if count > 0:
            _fail('planar_brep_invalid', 'Native body check returned faults; no repair is attempted.')

    def obj(self, obj, interface):
        if obj is None:
            _fail('planar_brep_incomplete', f'Missing {interface}.')
        try:
            result = self.wrap(obj, interface)
            if result is None:
                _fail('planar_brep_incomplete', f'Missing wrapped {interface}.')
            return result
        except PlanarBrepError:
            raise
        except Exception as exc:
            raise PlanarBrepError('planar_brep_native_read_failed', f'Cannot wrap {interface}.') from exc

    def key(self, obj):
        try:
            identity = self.identity(obj)
            if identity is None:
                _fail('planar_brep_incomplete', 'Missing canonical native identity.')
            for index, known in enumerate(self.identities):
                self.identity_comparisons += 1
                if self.identity_comparisons > self.limits.max_identity_comparisons:
                    _fail('planar_brep_budget_exceeded', 'Native identity comparison budget exceeded.')
                if identity == known:
                    return index
            self.identities.append(identity)
            return len(self.identities) - 1
        except PlanarBrepError:
            raise
        except Exception as exc:
            raise PlanarBrepError('planar_brep_native_read_failed', 'Native identity failed.') from exc

    def flag(self, value, label):
        if type(value) is not bool:
            _fail('planar_brep_incomplete', f'{label} is not a native boolean.')
        return value

    def count(self, obj, getter, maximum, minimum=1):
        count = self.call(obj, getter)
        if type(count) is not int or count < minimum:
            _fail('planar_brep_incomplete', f'{getter} returned an invalid count.')
        if count > maximum:
            _fail('planar_brep_budget_exceeded', f'{getter} exceeds the snapshot budget.')
        return count

    def array(self, obj, getter, interface, count=None, maximum=None):
        raw = self.call(obj, getter)
        if not isinstance(raw, (list, tuple)):
            _fail('planar_brep_incomplete', f'{getter} did not return a complete array.')
        if maximum is not None and len(raw) > maximum:
            _fail('planar_brep_budget_exceeded', f'{getter} exceeds the snapshot budget.')
        if count is not None and len(raw) != count:
            _fail('planar_brep_incomplete', f'{getter} length disagrees with native count.')
        result = [self.obj(item, interface) for item in raw]
        keys = [self.key(item) for item in result]
        if len(set(keys)) != len(keys):
            _fail('planar_brep_ambiguous', f'{getter} contains repeated native entities.')
        return result, keys

    def numbers(self, raw, size, label):
        if not isinstance(raw, (list, tuple)) or len(raw) != size:
            _fail('planar_brep_incomplete', f'{label} must contain {size} doubles.')
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in raw):
            _fail('planar_brep_unsupported', f'{label} contains nonfinite or invalid coordinates.')
        values = tuple(float(x) for x in raw)
        if any(abs(x) > self.limits.max_coordinate_m for x in values):
            _fail('planar_brep_budget_exceeded', f'{label} magnitude exceeds the analytical budget.')
        return values

    def tolerance(self, obj):
        # Registered IsTolerant supplies (BOOL return, DOUBLE out parameter).
        # bool(tuple) would incorrectly classify every successful native read.
        raw = self.call(obj, 'IsTolerant')
        if type(raw) is not tuple or len(raw) != 2 or type(raw[0]) is not bool:
            _fail('planar_brep_incomplete', 'IsTolerant must return (native boolean, tolerance).')
        tolerant, tolerance = raw
        if (type(tolerance) not in (int, float) or not math.isfinite(tolerance)
                or tolerance < 0):
            _fail('planar_brep_incomplete', 'Native tolerance is invalid, negative or nonfinite.')
        tolerance = float(tolerance)
        if tolerant or tolerance > self.limits.max_native_gap_m:
            _fail('planar_brep_unsupported', 'Tolerant or excessive-gap native geometry is unsupported.')
        # False is the native exact class, which can still have a small gap.
        # The reported gap gate is independent of analytical point/plane/line
        # consistency; accepting an exact class never relaxes those checks.
        # Preserve that gap verbatim; do not equate it with zero or snap points.
        return {'is_tolerant': False, 'gap_m': tolerance.hex()}

    def polygon_pair(self, a, b, c, d):
        self.polygon_comparisons += 1
        if self.polygon_comparisons > self.limits.max_polygon_comparisons:
            _fail('planar_brep_budget_exceeded', 'Polygon validation budget exceeded.')
        return _intersects(a, b, c, d)


def _validate_polygons(reader, loops, normal, reversed_normal, points):
    axis = max(range(3), key=lambda i: abs(normal[i]))
    # Cyclic projection keeps signed area consistent with the chosen axis.
    axes = ((1, 2), (2, 0), (0, 1))[axis]
    polygons = []
    for loop in loops:
        polygon = [tuple(Fraction(points[v][i]) for i in axes) for v in loop['vertices']]
        area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
        expected_sign = (-1 if reversed_normal else 1) * (1 if loop['outer'] else -1)
        if area == 0 or (area * Fraction(normal[axis]) > 0) != (expected_sign > 0):
            _fail('planar_brep_degenerate', 'Loop area/orientation disagrees with the face normal.')
        segments = list(zip(polygon, polygon[1:] + polygon[:1]))
        for i, (a, b) in enumerate(segments):
            for j in range(i+1, len(segments)):
                c, d = segments[j]
                if j == i+1 or (i == 0 and j == len(segments)-1):
                    # Collinear reversal overlaps an adjacent segment.
                    shared, p, q = (b, a, d) if j == i+1 else (a, b, c)
                    if _on_segment(shared, p, q) or _on_segment(shared, q, p):
                        _fail('planar_brep_degenerate', 'Adjacent loop edges overlap.')
                elif reader.polygon_pair(a, b, c, d):
                    _fail('planar_brep_degenerate', 'Loop is self-intersecting or touching.')
        polygons.append(polygon)
    outer_indices = [i for i, loop in enumerate(loops) if loop['outer']]
    if len(outer_indices) != 1:
        _fail('planar_brep_ambiguous', 'A supported face must have exactly one outer loop.')
    outer = outer_indices[0]
    for i in range(len(polygons)):
        for j in range(i+1, len(polygons)):
            for a, b in zip(polygons[i], polygons[i][1:] + polygons[i][:1]):
                for c, d in zip(polygons[j], polygons[j][1:] + polygons[j][:1]):
                    if reader.polygon_pair(a, b, c, d):
                        _fail('planar_brep_degenerate', 'Face loops intersect or touch.')
            if i != outer and j != outer and (_inside(polygons[i][0], polygons[j]) or _inside(polygons[j][0], polygons[i])):
                _fail('planar_brep_ambiguous', 'Nested inner loops are unsupported.')
    for i, polygon in enumerate(polygons):
        if i != outer and not _inside(polygon[0], polygons[outer]):
            _fail('planar_brep_incomplete', 'Inner loop lies outside the outer boundary.')


def planar_body_snapshot(body, *, identity, wrap=None, limits=None):
    """Return JSON-safe full analytical BREP; unsupported input raises explicitly.

    Native identifiers appear only in temporary membership maps. Polygon and
    manifold validation complements native Check3; none of these facts replace
    the retained full planes, line segments, vertices and ordered topology.
    """
    r = _Reader(identity, wrap, limits or PlanarBrepLimits())
    body = r.obj(body, 'IBody2')
    body_key = r.key(body)
    body_type = r.call(body, 'GetType')
    if type(body_type) is not int or body_type != 0:
        _fail('planar_brep_unsupported', 'Only native solid bodies are supported.')
    if r.flag(r.call(body, 'IsMeshBody'), 'IsMeshBody'):
        _fail('planar_brep_unsupported', 'Mesh bodies are unsupported.')
    r.check_body(body)
    stamp = r.call(body, 'GetUpdateStamp')
    if type(stamp) is not int:
        _fail('planar_brep_incomplete', 'Invalid body update stamp.')
    counts = (r.count(body, 'GetVertexCount', r.limits.max_vertices, 4),
              r.count(body, 'GetEdgeCount', r.limits.max_edges, 6),
              r.count(body, 'GetFaceCount', r.limits.max_faces, 4))
    vertices, vertex_keys = r.array(body, 'GetVertices', 'IVertex', counts[0])
    edges, edge_keys = r.array(body, 'GetEdges', 'IEdge', counts[1])
    faces, face_keys = r.array(body, 'GetFaces', 'IFace2', counts[2])
    points = {key: r.numbers(r.call(vertex, 'GetPoint'), 3, 'vertex') for vertex, key in zip(vertices, vertex_keys)}
    vertex_tolerances = {key: r.tolerance(vertex) for vertex, key in zip(vertices, vertex_keys)}
    if len(set(points.values())) != len(points):
        _fail('planar_brep_ambiguous', 'Distinct native vertices coincide; no coordinate merging is allowed.')
    vertex_order = sorted(vertex_keys, key=lambda key: _hex(points[key]))
    vertex_index = {key: index for index, key in enumerate(vertex_order)}
    edge_data = {}
    edge_pairs = set()
    vertex_incidence = {key: set() for key in vertex_keys}
    for edge, key in zip(edges, edge_keys):
        tolerance = r.tolerance(edge)
        if r.key(r.obj(r.call(edge, 'GetBody'), 'IBody2')) != body_key:
            _fail('planar_brep_incomplete', 'Edge belongs to another body.')
        curve = r.obj(r.call(edge, 'GetCurve'), 'ICurve')
        if not r.flag(r.call(curve, 'IsLine'), 'IsLine'):
            _fail('planar_brep_unsupported', 'Curved edges are unsupported.')
        line = r.numbers(r.prop(curve, 'LineParams'), 6, 'line parameters')
        if not any(line[3:]):
            _fail('planar_brep_degenerate', 'Zero line direction.')
        start = r.key(r.obj(r.call(edge, 'GetStartVertex'), 'IVertex'))
        end = r.key(r.obj(r.call(edge, 'GetEndVertex'), 'IVertex'))
        if start not in points or end not in points or start == end:
            _fail('planar_brep_incomplete', 'Missing, foreign or collapsed edge endpoints.')
        for point in (points[start], points[end]):
            if not _line_consistent(point, line, r.limits.consistency_tolerance_m):
                _fail('planar_brep_incomplete', 'Endpoint does not lie on its native straight line.')
        # Vertex coordinates alone do not describe the actual trimmed curve.
        # GetCurveParams3 avoids GetCurveParams2's packed double metadata and
        # supplies a registered, dispatch-valued ICurveParamData interface.
        parameter_data = r.obj(r.call(edge, 'GetCurveParams3'), 'ICurveParamData')
        curve_type = r.prop(parameter_data, 'CurveType')
        if type(curve_type) is not int or curve_type != 3001:  # swCurveTypes_e.LINE_TYPE
            _fail('planar_brep_unsupported', 'Trimmed edge parameter data is not a native line.')
        curve_sense = r.flag(r.prop(parameter_data, 'Sense'), 'curve/edge Sense')
        curve_start = r.numbers(r.prop(parameter_data, 'StartPoint'), 3, 'trimmed curve start')
        curve_end = r.numbers(r.prop(parameter_data, 'EndPoint'), 3, 'trimmed curve end')
        interval = r.numbers((r.prop(parameter_data, 'UMinValue'), r.prop(parameter_data, 'UMaxValue')),
                             2, 'trimmed curve interval')
        if interval[0] >= interval[1] or curve_start == curve_end:
            _fail('planar_brep_degenerate', 'Trimmed line interval/endpoints are collapsed or reversed.')
        expected_start, expected_end = ((points[start], points[end]) if curve_sense
                                        else (points[end], points[start]))
        for point, vertex_point in ((curve_start, expected_start), (curve_end, expected_end)):
            if (not _line_consistent(point, line, r.limits.consistency_tolerance_m)
                    or not _points_consistent(point, vertex_point, r.limits.consistency_tolerance_m)):
                _fail('planar_brep_incomplete', 'Native trimmed endpoints disagree with line/vertices and sense.')
        # Preserve even sub-tolerance discrepancies exactly. No native interval
        # normalization: reversed sense may use negative parameter space.
        trim = {'curve_type': curve_type, 'same_direction_as_edge': curve_sense,
                'start_point': list(_hex(curve_start)), 'end_point': list(_hex(curve_end)),
                'u_min': interval[0].hex(), 'u_max': interval[1].hex()}
        pair = tuple(sorted((vertex_index[start], vertex_index[end])))
        if pair in edge_pairs:
            _fail('planar_brep_ambiguous', 'Distinct native edges have identical endpoints.')
        edge_pairs.add(pair)
        edge_data[key] = {'start': start, 'end': end, 'line': line, 'trim': trim,
                          'tolerance': tolerance, 'pair': pair, 'uses': []}
        vertex_incidence[start].add(key)
        vertex_incidence[end].add(key)
    edge_order = sorted(edge_keys, key=lambda key: edge_data[key]['pair'])
    edge_index = {key: index for index, key in enumerate(edge_order)}
    for vertex, key in zip(vertices, vertex_keys):
        _, declared = r.array(vertex, 'GetEdges', 'IEdge', maximum=r.limits.max_edges)
        if set(declared) != vertex_incidence[key]:
            _fail('planar_brep_incomplete', 'Vertex incidence is incomplete or inconsistent.')
    face_data = {}
    loop_data = {}
    coedge_data = {}
    for face, face_key in zip(faces, face_keys):
        if r.key(r.obj(r.call(face, 'GetBody'), 'IBody2')) != body_key:
            _fail('planar_brep_incomplete', 'Face belongs to another body.')
        surface = r.obj(r.call(face, 'GetSurface'), 'ISurface')
        if not r.flag(r.call(surface, 'IsPlane'), 'IsPlane'):
            _fail('planar_brep_unsupported', 'Non-planar surfaces are unsupported.')
        plane = r.numbers(r.prop(surface, 'PlaneParams'), 6, 'plane parameters')
        if not any(plane[:3]):
            _fail('planar_brep_degenerate', 'Zero plane normal.')
        sense = r.flag(r.call(face, 'FaceInSurfaceSense'), 'FaceInSurfaceSense')
        count = r.count(face, 'GetLoopCount', r.limits.max_loops)
        if len(loop_data) + count > r.limits.max_loops:
            _fail('planar_brep_budget_exceeded', 'Total loop budget exceeded.')
        loops, loop_keys = r.array(face, 'GetLoops', 'ILoop2', count)
        # Also prove the linked traversal contains exactly the enumerated loops.
        next_loop = r.obj(r.call(face, 'GetFirstLoop'), 'ILoop2')
        traversed = []
        while next_loop is not None:
            next_key = r.key(next_loop)
            if next_key in traversed or len(traversed) >= count:
                _fail('planar_brep_incomplete', 'Face loop traversal is cyclic or overlong.')
            traversed.append(next_key)
            raw_next = r.call(next_loop, 'GetNext')
            next_loop = r.obj(raw_next, 'ILoop2') if raw_next is not None else None
        if set(traversed) != set(loop_keys):
            _fail('planar_brep_incomplete', 'Face loop traversal disagrees with enumeration.')
        face_edges = set()
        face_loops = []
        for loop, loop_key in zip(loops, loop_keys):
            if loop_key in loop_data or r.key(r.obj(r.call(loop, 'GetFace'), 'IFace2')) != face_key:
                _fail('planar_brep_incomplete', 'Loop ownership is inconsistent.')
            if r.flag(r.call(loop, 'IsSingular'), 'IsSingular'):
                _fail('planar_brep_degenerate', 'Singular loops are unsupported.')
            outer = r.flag(r.call(loop, 'IsOuter'), 'IsOuter')
            count = r.count(loop, 'GetCoEdgeCount', r.limits.max_loop_coedges, 3)
            if len(coedge_data) + count > r.limits.max_coedges:
                _fail('planar_brep_budget_exceeded', 'Total coedge budget exceeded.')
            _, declared = r.array(loop, 'GetCoEdges', 'ICoEdge', count)
            first = r.obj(r.call(loop, 'GetFirstCoEdge'), 'ICoEdge')
            first_key = r.key(first)
            current, ordered = first, []
            for _ in range(count):
                coedge_key = r.key(current)
                if coedge_key in coedge_data or coedge_key in ordered:
                    _fail('planar_brep_incomplete', 'Coedge traversal closes early or shares an entity.')
                if r.key(r.obj(r.call(current, 'GetLoop'), 'ILoop2')) != loop_key:
                    _fail('planar_brep_incomplete', 'Coedge belongs to another loop.')
                # A separate coedge curve denotes imprecise sewing; reject it.
                if r.call(current, 'GetCurve') is not None:
                    _fail('planar_brep_unsupported', 'Imprecisely sewn coedges are unsupported.')
                edge_key = r.key(r.obj(r.call(current, 'GetEdge'), 'IEdge'))
                if edge_key not in edge_data or edge_key in face_edges:
                    _fail('planar_brep_incomplete', 'Foreign or repeated edge in face loops.')
                face_edges.add(edge_key)
                coedge_sense = r.flag(r.call(current, 'GetSense'), 'GetSense')
                edge = edge_data[edge_key]
                start, end = (edge['start'], edge['end']) if coedge_sense else (edge['end'], edge['start'])
                partner = r.key(r.obj(r.call(current, 'GetPartner'), 'ICoEdge'))
                record = {'edge': edge_key, 'face': face_key, 'loop': loop_key, 'sense': coedge_sense,
                          'start': start, 'end': end, 'partner': partner}
                coedge_data[coedge_key] = record
                edge['uses'].append(coedge_key)
                ordered.append(coedge_key)
                current = r.obj(r.call(current, 'GetNext'), 'ICoEdge')
            if r.key(current) != first_key or set(ordered) != set(declared):
                _fail('planar_brep_incomplete', 'Coedge cycle is incomplete or disagrees with enumeration.')
            for a, b in zip(ordered, ordered[1:] + ordered[:1]):
                if coedge_data[a]['end'] != coedge_data[b]['start']:
                    _fail('planar_brep_incomplete', 'Coedges do not form a continuous oriented loop.')
            loop_vertices = [coedge_data[key]['start'] for key in ordered]
            if len(set(loop_vertices)) != len(loop_vertices):
                _fail('planar_brep_ambiguous', 'Loop revisits a native vertex.')
            for vertex_key in loop_vertices:
                if not _plane_consistent(points[vertex_key], plane, r.limits.consistency_tolerance_m):
                    _fail('planar_brep_incomplete', 'Loop vertex does not lie on its native plane.')
            _, declared_edges = r.array(loop, 'GetEdges', 'IEdge', r.count(loop, 'GetEdgeCount', r.limits.max_loop_coedges, 3))
            _, declared_vertices = r.array(loop, 'GetVertices', 'IVertex', r.count(loop, 'GetVertexCount', r.limits.max_loop_coedges, 3))
            if set(declared_edges) != {coedge_data[key]['edge'] for key in ordered} or set(declared_vertices) != set(loop_vertices):
                _fail('planar_brep_incomplete', 'Loop vertex/edge arrays disagree with ordered coedges.')
            tokens = [(edge_index[coedge_data[key]['edge']], coedge_data[key]['sense'],
                       vertex_index[coedge_data[key]['start']], vertex_index[coedge_data[key]['end']]) for key in ordered]
            rotation = min(range(len(tokens)), key=lambda i: tokens[i])  # Edges are unique within a loop.
            ordered = ordered[rotation:] + ordered[:rotation]
            tokens = tokens[rotation:] + tokens[:rotation]
            record = {'outer': outer, 'ordered': ordered, 'vertices': loop_vertices,
                      'key': (outer, tuple(tokens)), 'face': face_key}
            loop_data[loop_key] = record
            face_loops.append(loop_key)
        _, declared_edges = r.array(face, 'GetEdges', 'IEdge', r.count(face, 'GetEdgeCount', r.limits.max_edges, 3))
        if set(declared_edges) != face_edges:
            _fail('planar_brep_incomplete', 'Face edge incidence is incomplete.')
        _validate_polygons(r, [loop_data[key] for key in face_loops], plane[:3], sense, points)
        face_loops.sort(key=lambda key: loop_data[key]['key'])
        face_data[face_key] = {'plane': plane, 'sense': sense, 'loops': face_loops,
                               'key': (_hex(plane), sense, tuple(loop_data[key]['key'] for key in face_loops))}
    face_order = sorted(face_keys, key=lambda key: face_data[key]['key'])
    if len({face_data[key]['key'] for key in face_keys}) != len(face_keys):
        _fail('planar_brep_ambiguous', 'Duplicate coincident face descriptions.')
    face_index = {key: index for index, key in enumerate(face_order)}
    positions = {}
    for face_key in face_order:
        for loop_index, loop_key in enumerate(face_data[face_key]['loops']):
            for position, coedge_key in enumerate(loop_data[loop_key]['ordered']):
                positions[coedge_key] = (face_index[face_key], loop_index, position)
    for edge, edge_key in zip(edges, edge_keys):
        uses = edge_data[edge_key]['uses']
        _, declared = r.array(edge, 'GetCoEdges', 'ICoEdge', 2)
        if len(uses) != 2 or set(declared) != set(uses):
            _fail('planar_brep_incomplete', 'Solid edge must have exactly two declared coedge uses.')
        a, b = (coedge_data[key] for key in uses)
        if (a['face'] == b['face'] or a['sense'] == b['sense']
                or a['partner'] != uses[1] or b['partner'] != uses[0]):
            _fail('planar_brep_incomplete', 'Edge partners, incidence or orientation are inconsistent.')
    # Vertex links must form one connected face fan, excluding bow-tie vertices.
    for vertex_key, incident in vertex_incidence.items():
        graph = {}
        for edge_key in incident:
            a, b = (coedge_data[key]['face'] for key in edge_data[edge_key]['uses'])
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)
        if not graph or any(len(neighbours) != 2 for neighbours in graph.values()):
            _fail('planar_brep_degenerate', 'Vertex does not have a closed manifold face fan.')
        visited, pending = set(), [next(iter(graph))]
        while pending:
            face_key = pending.pop()
            if face_key not in visited:
                visited.add(face_key)
                pending.extend(graph[face_key])
        if len(visited) != len(graph):
            _fail('planar_brep_degenerate', 'Vertex has disconnected face fans.')
    after_counts = (r.count(body, 'GetVertexCount', r.limits.max_vertices, 4),
                    r.count(body, 'GetEdgeCount', r.limits.max_edges, 6),
                    r.count(body, 'GetFaceCount', r.limits.max_faces, 4))
    if after_counts != counts or r.call(body, 'GetUpdateStamp') != stamp:
        _fail('planar_brep_changed_during_read', 'Native body changed during boundary collection.')
    r.check_body(body)
    return {
        'scope': PLANAR_BREP_SCOPE, 'coordinate_frame': 'part_model', 'length_unit': 'm',
        'number_encoding': 'ieee754_binary64_hex_exact',
        'vertices': [list(_hex(points[key])) for key in vertex_order],
        'vertex_tolerances': [vertex_tolerances[key] for key in vertex_order],
        'edges': [{'start': vertex_index[edge_data[key]['start']], 'end': vertex_index[edge_data[key]['end']],
                   'line_parameters': list(_hex(edge_data[key]['line'])),
                   'trimmed_curve': edge_data[key]['trim'],
                   'native_tolerance': edge_data[key]['tolerance'],
                   'coedges': [list(positions[use]) for use in sorted(edge_data[key]['uses'], key=lambda use: positions[use])]}
                  for key in edge_order],
        'faces': [{'plane_parameters': list(_hex(face_data[key]['plane'])),
                   'normal_opposes_surface': face_data[key]['sense'],
                   'loops': [{'outer': loop_data[loop]['outer'],
                              'coedges': [{'edge': edge_index[coedge_data[use]['edge']],
                                           'same_direction_as_edge': coedge_data[use]['sense'],
                                           'start': vertex_index[coedge_data[use]['start']],
                                           'end': vertex_index[coedge_data[use]['end']],
                                           'partner': list(positions[coedge_data[use]['partner']])}
                                          for use in loop_data[loop]['ordered']]}
                             for loop in face_data[key]['loops']]}
                  for key in face_order],
    }


def planar_snapshot_digest(snapshot):
    """Hash the exact complete analytical snapshot, never a native save stream."""
    if not isinstance(snapshot, dict) or snapshot.get('scope') != PLANAR_BREP_SCOPE:
        raise ValueError('Not a planar polyhedral BREP snapshot.')
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
