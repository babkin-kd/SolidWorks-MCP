"""Pure native-shaped fixtures; no SolidWorks/COM invocation or acceptance claim."""

from copy import deepcopy
import itertools
import json
import math
import random

import pytest

from solidworks_mcp.cad_planar_brep import (PLANAR_BREP_SCOPE, PlanarBrepError,
    PlanarBrepLimits, planar_body_snapshot, planar_snapshot_digest)


_ids = itertools.count()


class Entity:
    def __init__(self):
        self.ident = next(_ids)


class Vertex(Entity):
    def __init__(self, point):
        super().__init__()
        self.point = tuple(point)
        self.edges = []
    def GetPoint(self): return self.point
    def GetEdges(self): return tuple(self.edges)
    def IsTolerant(self): return False, 0.0


class Curve:
    def __init__(self, edge): self.edge = edge
    def IsLine(self): return True
    @property
    def LineParams(self):
        a, b = self.edge.start.point, self.edge.end.point
        return a + tuple(y-x for x, y in zip(a, b))


class CurveParamData:
    CurveType = 3001
    Sense = True
    UMinValue = 0.0
    UMaxValue = 1.0
    def __init__(self, edge): self.edge = edge
    @property
    def StartPoint(self): return self.edge.start.point if self.Sense else self.edge.end.point
    @property
    def EndPoint(self): return self.edge.end.point if self.Sense else self.edge.start.point


class Edge(Entity):
    def __init__(self, body, start, end):
        super().__init__()
        self.body, self.start, self.end = body, start, end
        self.coedges = []
        self.curve = Curve(self)
        self.parameter_data = CurveParamData(self)
        start.edges.append(self)
        end.edges.append(self)
    def GetBody(self): return self.body
    def GetStartVertex(self): return self.start
    def GetEndVertex(self): return self.end
    def GetCurve(self): return self.curve
    def GetCoEdges(self): return tuple(self.coedges)
    def GetCurveParams3(self): return self.parameter_data
    def IsTolerant(self): return False, 0.0


class Coedge(Entity):
    def __init__(self, edge, loop, sense):
        super().__init__()
        self.edge, self.loop, self.sense = edge, loop, sense
        edge.coedges.append(self)
    def GetEdge(self): return self.edge
    def GetLoop(self): return self.loop
    def GetSense(self): return self.sense
    def GetCurve(self): return None
    def GetNext(self):
        coedges = self.loop.ordered
        return coedges[(coedges.index(self)+1) % len(coedges)]
    def GetPartner(self):
        return next(c for c in self.edge.coedges if c is not self)


class Loop(Entity):
    def __init__(self, face, outer):
        super().__init__()
        self.face, self.outer = face, outer
        self.ordered = []
        self.shift = 0
        self.reverse_array = False
    def GetFace(self): return self.face
    def IsOuter(self): return self.outer
    def IsSingular(self): return False
    def GetCoEdgeCount(self): return len(self.ordered)
    def GetCoEdges(self): return tuple(reversed(self.ordered) if self.reverse_array else self.ordered)
    def GetFirstCoEdge(self): return self.ordered[self.shift % len(self.ordered)]
    def GetNext(self):
        loops = self.face.loops
        index = loops.index(self)+1
        return loops[index] if index < len(loops) else None
    def GetEdges(self): return tuple(c.edge for c in self.ordered)
    def GetEdgeCount(self): return len(self.ordered)
    def GetVertices(self): return tuple(c.edge.start if c.sense else c.edge.end for c in self.ordered)
    def GetVertexCount(self): return len(self.ordered)


class Surface:
    def __init__(self, params): self.params = params
    def IsPlane(self): return True
    @property
    def PlaneParams(self): return self.params


class Face(Entity):
    def __init__(self, body, plane):
        super().__init__()
        self.body = body
        self.surface = Surface(tuple(plane))
        self.sense = False
        self.loops = []
    def GetBody(self): return self.body
    def GetSurface(self): return self.surface
    def FaceInSurfaceSense(self): return self.sense
    def GetLoops(self): return tuple(self.loops)
    def GetLoopCount(self): return len(self.loops)
    def GetFirstLoop(self): return self.loops[0]
    def GetEdges(self): return tuple(c.edge for loop in self.loops for c in loop.ordered)
    def GetEdgeCount(self): return len(self.GetEdges())


class Body(Entity):
    Check3 = None
    def __init__(self):
        super().__init__()
        self.vertices, self.edges, self.faces = [], [], []
        self.stamp = 123
    def GetType(self): return 0
    def IsMeshBody(self): return False
    def GetVertices(self): return tuple(self.vertices)
    def GetEdges(self): return tuple(self.edges)
    def GetFaces(self): return tuple(self.faces)
    def GetVertexCount(self): return len(self.vertices)
    def GetEdgeCount(self): return len(self.edges)
    def GetFaceCount(self): return len(self.faces)
    def GetUpdateStamp(self): return self.stamp


class FaultEntity:
    def __init__(self, count):
        self.Count = count


POINTS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
          (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
POLYGONS = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
            [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]


def make_body(points=POINTS, polygons=POLYGONS):
    body = Body()
    body.vertices = [Vertex(p) for p in points]
    edges = {}
    for face_loops in polygons:
        if isinstance(face_loops[0], int):
            face_loops = [face_loops]
        a, b, c = [points[i] for i in face_loops[0][:3]]
        u, v = [y-x for x, y in zip(a, b)], [y-x for x, y in zip(a, c)]
        normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        norm = math.hypot(*normal)
        normal = tuple(x/norm for x in normal) if norm else normal
        face = Face(body, normal + tuple(a))
        body.faces.append(face)
        for index, vertex_indices in enumerate(face_loops):
            loop = Loop(face, index == 0)
            face.loops.append(loop)
            for start, end in zip(vertex_indices, vertex_indices[1:] + vertex_indices[:1]):
                key = tuple(sorted((start, end)))
                if key not in edges:
                    edge = Edge(body, body.vertices[start], body.vertices[end])
                    edges[key] = edge
                    body.edges.append(edge)
                edge = edges[key]
                loop.ordered.append(Coedge(edge, loop, edge.start is body.vertices[start]))
    return body


def snapshot(body, **kwargs):
    # Deliberately unhashable canonical identity; never persisted.
    return planar_body_snapshot(body, identity=lambda obj: [obj.ident], **kwargs)


def digest(body): return planar_snapshot_digest(snapshot(body))


def assert_rejected(body, code=None, **kwargs):
    with pytest.raises(PlanarBrepError) as exc:
        snapshot(body, **kwargs)
    if code:
        assert exc.value.code == code


def test_complete_cube_snapshot_json_and_no_runtime_identity():
    data = snapshot(make_body())
    assert data['scope'] == PLANAR_BREP_SCOPE
    assert (len(data['vertices']), len(data['edges']), len(data['faces'])) == (8, 12, 6)
    assert all(len(edge['coedges']) == 2 for edge in data['edges'])
    assert len(json.loads(json.dumps(data))['faces']) == 6
    assert 'ident' not in json.dumps(data)
    assert data['vertices'][0][0].startswith('0x')
    assert digest(make_body()) == digest(make_body())


def test_native_enumeration_and_cycle_origin_independent():
    body = make_body()
    before = digest(body)
    rng = random.Random(42)
    rng.shuffle(body.vertices)
    rng.shuffle(body.edges)
    rng.shuffle(body.faces)
    for face in body.faces:
        for loop in face.loops:
            loop.shift = 2
            loop.reverse_array = True
    assert digest(body) == before
    # Fresh native identities, rather than only different wrapper ordering.
    other = deepcopy(body)
    for item in [other, *other.vertices, *other.edges, *other.faces,
                 *(loop for face in other.faces for loop in face.loops),
                 *(c for edge in other.edges for c in edge.coedges)]:
        item.ident = next(_ids)
    assert digest(other) == before


@pytest.mark.parametrize('transform', [lambda p: (p[0]+2, p[1]-3, p[2]+4),
                                      lambda p: (-p[1], p[0], p[2]),
                                      lambda p: (p[0], p[1], p[2]*2)])
def test_model_frame_translation_rotation_scale_detected(transform):
    assert digest(make_body()) != digest(make_body([transform(p) for p in POINTS]))


def test_split_planar_face_same_volume_and_bbox_detected():
    polygons = deepcopy(POLYGONS)
    polygons[1:2] = [[4, 5, 6], [4, 6, 7]]
    split = snapshot(make_body(polygons=polygons))
    plain = snapshot(make_body())
    assert split['vertices'] == plain['vertices']
    assert (len(split['faces']), len(split['edges'])) == (7, 13)
    assert planar_snapshot_digest(split) != planar_snapshot_digest(plain)


def test_internal_cavity_and_cavity_location_detected_without_bbox_fallback():
    inner = [(x*.25+.25, y*.25+.25, z*.25+.25) for x, y, z in POINTS]
    cavity_polygons = POLYGONS + [[i+8 for i in reversed(poly)] for poly in POLYGONS]
    hollow = make_body(POINTS + inner, cavity_polygons)
    moved = [(x+.125, y, z) for x, y, z in inner]
    assert digest(hollow) != digest(make_body())
    assert digest(hollow) != digest(make_body(POINTS + moved, cavity_polygons))


def test_inner_ordered_loops_complete_and_enumeration_independent():
    points = POINTS + [(x*.5+.25, y*.5+.25, z) for x, y, z in POINTS]
    polygons = [[[0, 3, 2, 1], [8, 9, 10, 11]],
                [[4, 5, 6, 7], [12, 15, 14, 13]], *POLYGONS[2:],
                [8, 12, 13, 9], [9, 13, 14, 10], [10, 14, 15, 11], [11, 15, 12, 8]]
    body = make_body(points, polygons)
    before = digest(body)
    assert sum(len(face['loops']) for face in snapshot(body)['faces']) == 12
    for face in body.faces:
        face.loops.reverse()
    assert digest(body) == before


def test_reversed_full_boundary_sense_detected():
    body = make_body()
    before = digest(body)
    for face in body.faces:
        face.sense = True
        for loop in face.loops:
            loop.ordered.reverse()
            for c in loop.ordered:
                c.sense = not c.sense
    assert digest(body) != before


def test_plane_and_line_parameters_are_exact_no_rounding():
    body = make_body()
    before = digest(body)
    plane = body.faces[1].surface.params
    # Different anchor on the SAME plane is intentionally a conservative conflict.
    body.faces[1].surface.params = plane[:3] + (math.nextafter(plane[3], 1), *plane[4:])
    assert digest(body) != before
    other = make_body([(x + 2**-45, y, z) for x, y, z in POINTS])
    assert digest(other) != before


@pytest.mark.parametrize('fault,code', [
    (lambda b: setattr(b, 'IsMeshBody', lambda: True), 'planar_brep_unsupported'),
    (lambda b: setattr(b, 'GetType', lambda: 1), 'planar_brep_unsupported'),
    (lambda b: setattr(b, 'Check3', FaultEntity(1)), 'planar_brep_invalid'),
    (lambda b: setattr(b.faces[0].surface, 'IsPlane', lambda: False), 'planar_brep_unsupported'),
    (lambda b: setattr(b.edges[0].curve, 'IsLine', lambda: False), 'planar_brep_unsupported'),
    (lambda b: setattr(b.edges[0].coedges[0], 'GetCurve', lambda: object()), 'planar_brep_unsupported'),
    (lambda b: setattr(b.vertices[0], 'point', (math.nan, 0, 0)), 'planar_brep_unsupported'),
    (lambda b: setattr(b.vertices[0], 'point', (math.inf, 0, 0)), 'planar_brep_unsupported'),
    (lambda b: setattr(b.vertices[0], 'point', b.vertices[1].point), 'planar_brep_ambiguous'),
    (lambda b: setattr(b.edges[0], 'GetStartVertex', lambda: None), 'planar_brep_incomplete'),
    (lambda b: setattr(b.edges[0], 'GetEndVertex', lambda: b.edges[0].start), 'planar_brep_incomplete'),
    (lambda b: setattr(b.edges[0], 'GetBody', lambda: Body()), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0], 'GetBody', lambda: Body()), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0].loops[0], 'IsSingular', lambda: True), 'planar_brep_degenerate'),
    (lambda b: setattr(b.faces[0].loops[0], 'GetCoEdgeCount', lambda: 5), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0].loops[0].ordered[0], 'GetNext', lambda: None), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0].loops[0].ordered[0], 'GetNext', lambda: b.faces[0].loops[0].ordered[0]), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0].loops[0].ordered[0], 'GetPartner', lambda: b.faces[0].loops[0].ordered[0]), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0].loops[0].ordered[0], 'GetLoop', lambda: b.faces[1].loops[0]), 'planar_brep_incomplete'),
    (lambda b: setattr(b.vertices[0], 'GetEdges', lambda: ()), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0], 'GetEdges', lambda: ()), 'planar_brep_incomplete'),
    (lambda b: setattr(b, 'GetFaces', lambda: (b.faces[0],)*6), 'planar_brep_ambiguous'),
    (lambda b: setattr(b, 'GetEdges', lambda: tuple(b.edges[:-1])), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0], 'sense', True), 'planar_brep_degenerate'),
    (lambda b: setattr(b.faces[0].loops[0], 'outer', False), 'planar_brep_degenerate'),
    (lambda b: setattr(b.faces[0].surface, 'params', (0, 0, 0, 0, 0, 0)), 'planar_brep_degenerate'),
    (lambda b: setattr(b.faces[0].surface, 'params', (0, 0, -1, 0, 0, .1)), 'planar_brep_incomplete'),
    (lambda b: setattr(b.faces[0].loops[0].ordered[0], 'sense', 1), 'planar_brep_incomplete'),
])
def test_rejects_unsupported_ambiguous_incomplete_and_degenerate(fault, code):
    body = make_body()
    fault(body)
    assert_rejected(body, code)


def test_budget_checked_before_native_arrays():
    body = make_body()
    body.GetVertexCount = lambda: 10**9
    body.GetVertices = lambda: pytest.fail('Array must not be read after excessive count')
    assert_rejected(body, 'planar_brep_budget_exceeded')


@pytest.mark.parametrize('limits', [PlanarBrepLimits(max_coedges=10),
                                  PlanarBrepLimits(max_loops=2),
                                  PlanarBrepLimits(max_identity_comparisons=10),
                                  PlanarBrepLimits(max_polygon_comparisons=1),
                                  PlanarBrepLimits(max_coordinate_m=.5)])
def test_global_budgets_and_coordinate_range(limits):
    assert_rejected(make_body(), 'planar_brep_budget_exceeded', limits=limits)


def test_native_getter_failure_explicit_and_cause_preserved():
    body = make_body()
    def fail(): raise RuntimeError('native unavailable')
    body.GetFaces = fail
    with pytest.raises(PlanarBrepError) as exc:
        snapshot(body)
    assert exc.value.code == 'planar_brep_native_read_failed'
    assert isinstance(exc.value.__cause__, RuntimeError)


def test_body_change_during_read_rejected():
    body = make_body()
    calls = itertools.count()
    body.GetUpdateStamp = lambda: next(calls)
    assert_rejected(body, 'planar_brep_changed_during_read')


def test_wrapper_interfaces_and_no_native_copy_or_save():
    body = make_body()
    body.Copy = body.Save = lambda *args: pytest.fail('Opaque serialization is prohibited')
    interfaces = set()
    def wrap(obj, interface):
        interfaces.add(interface)
        return obj
    snapshot(body, wrap=wrap)
    assert interfaces == {'IBody2', 'IVertex', 'IEdge', 'IFace2', 'ILoop2', 'ICoEdge',
                          'ICurve', 'ISurface', 'ICurveParamData'}


@pytest.mark.parametrize('kwargs', [{'max_edges': 0}, {'max_faces': True},
                                  {'consistency_tolerance_m': 1e-6},
                                  {'max_coordinate_m': math.inf}])
def test_invalid_limits_rejected(kwargs):
    with pytest.raises(ValueError): PlanarBrepLimits(**kwargs)


def test_digest_scope_validation():
    with pytest.raises(ValueError): planar_snapshot_digest({'scope': 'body_mass_box'})


def test_duplicate_coincident_edge_and_repeated_native_vertex_rejected():
    body = make_body()
    edge = body.edges[0]
    body.edges.append(Edge(body, edge.start, edge.end))
    assert_rejected(body, 'planar_brep_ambiguous')
    body = make_body()
    body.vertices.append(body.vertices[0])
    assert_rejected(body, 'planar_brep_ambiguous')


def test_self_crossing_boundary_and_open_shell_rejected():
    polygons = deepcopy(POLYGONS)
    polygons[1] = [4, 6, 5, 7]
    # The crossed face also introduces unpaired diagonal edges. Either native
    # partner rejection or polygon rejection is safe; neither yields a snapshot.
    assert_rejected(make_body(polygons=polygons))
    assert_rejected(make_body(polygons=POLYGONS[:-1]))


def test_malformed_native_line_and_parameter_arrays_rejected():
    body = make_body()
    body.edges[0].curve = type('BadLine', (), {'IsLine': lambda self: True,
                                             'LineParams': (0, 0, 0, 1, 0, 0)})()
    assert_rejected(body, 'planar_brep_incomplete')
    body = make_body()
    body.edges[0].curve = type('BadLine', (), {'IsLine': lambda self: True,
                                             'LineParams': (0, 0, 0, 0, 0, 0)})()
    assert_rejected(body, 'planar_brep_degenerate')
    body = make_body()
    body.faces[0].surface.params = (0, 0, 1)
    assert_rejected(body, 'planar_brep_incomplete')


def test_fractional_consistency_gate_does_not_underflow():
    body = make_body()
    # Float cross products underflow, while this direction is not collinear
    # with the edge at all. Exact consistency validation must still reject.
    edge = body.edges[0]
    edge.curve = type('TinyBadLine', (), {'IsLine': lambda self: True,
        'LineParams': (*edge.start.point, 1e-310, 1e-310, 0)})()
    assert_rejected(body, 'planar_brep_incomplete')


def test_face_loop_link_and_loop_incidence_must_agree():
    body = make_body()
    loop = body.faces[0].loops[0]
    loop.GetNext = lambda: loop
    assert_rejected(body, 'planar_brep_incomplete')
    body = make_body()
    body.faces[0].loops[0].GetVertices = lambda: tuple(body.vertices[4:8])
    assert_rejected(body, 'planar_brep_incomplete')


def test_coedge_sense_flip_is_not_canonicalized_away():
    body = make_body()
    body.edges[0].coedges[0].sense = not body.edges[0].coedges[0].sense
    assert_rejected(body, 'planar_brep_incomplete')


def test_complete_trim_and_reversed_native_curve_sense_are_retained():
    body = make_body()
    before = snapshot(body)
    assert all(edge['trimmed_curve']['curve_type'] == 3001 for edge in before['edges'])
    edge = body.edges[0]
    edge.parameter_data.Sense = False
    edge.parameter_data.UMinValue, edge.parameter_data.UMaxValue = -1.0, -0.0
    after = snapshot(body)
    trim = next(item['trimmed_curve'] for item in after['edges']
                if not item['trimmed_curve']['same_direction_as_edge'])
    assert trim['u_min'] == (-1.0).hex() and trim['u_max'] == (-0.0).hex()
    assert trim['start_point'] == [float(x).hex() for x in edge.end.point]
    assert trim['end_point'] == [float(x).hex() for x in edge.start.point]
    assert planar_snapshot_digest(after) != planar_snapshot_digest(before)


@pytest.mark.parametrize('change', ['interval', 'endpoint'])
def test_sub_tolerance_trim_change_is_never_same_snapshot(change):
    body = make_body()
    before = digest(body)
    edge = body.edges[0]
    if change == 'interval':
        edge.parameter_data.UMaxValue = math.nextafter(1.0, 2.0)
    else:
        # Keep body vertices and native LineParams fixed. The discrepancy is
        # smaller than the consistency gate and must still enter the digest.
        values = list(edge.end.point)
        axis = next(i for i, (x, y) in enumerate(zip(edge.start.point, values)) if x != y)
        values[axis] = math.nextafter(float(values[axis]), 2.0)
        data = edge.parameter_data
        edge.parameter_data = type('ChangedTrim', (), {
            'CurveType': data.CurveType, 'Sense': data.Sense,
            'UMinValue': data.UMinValue, 'UMaxValue': data.UMaxValue,
            'StartPoint': data.StartPoint, 'EndPoint': tuple(values)})()
    assert digest(body) != before


@pytest.mark.parametrize('field,value,code', [
    ('CurveType', 3002, 'planar_brep_unsupported'),
    ('CurveType', True, 'planar_brep_unsupported'),
    ('Sense', 1, 'planar_brep_incomplete'),
    ('UMinValue', math.nan, 'planar_brep_unsupported'),
    ('UMaxValue', math.inf, 'planar_brep_unsupported'),
    ('UMaxValue', 0.0, 'planar_brep_degenerate'),
    ('UMinValue', 2.0, 'planar_brep_degenerate'),
    ('StartPoint', (math.nan, 0, 0), 'planar_brep_unsupported'),
    ('EndPoint', (0, 0), 'planar_brep_incomplete'),
    ('StartPoint', (9, 9, 9), 'planar_brep_incomplete'),
])
def test_invalid_trim_parameter_data_rejected(field, value, code):
    body = make_body()
    data = body.edges[0].parameter_data
    values = {name: getattr(data, name) for name in ('CurveType', 'Sense', 'UMinValue',
                                                   'UMaxValue', 'StartPoint', 'EndPoint')}
    values[field] = value
    body.edges[0].parameter_data = type('BadTrim', (), values)()
    assert_rejected(body, code)


def test_trim_curve_sense_endpoint_mapping_and_degeneracy_rejected():
    body = make_body()
    data = body.edges[0].parameter_data
    values = {name: getattr(data, name) for name in ('CurveType', 'Sense', 'UMinValue',
                                                   'UMaxValue', 'StartPoint', 'EndPoint')}
    values['Sense'] = False  # Endpoints deliberately not swapped.
    body.edges[0].parameter_data = type('BadSense', (), values)()
    assert_rejected(body, 'planar_brep_incomplete')
    values['EndPoint'] = values['StartPoint']
    body.edges[0].parameter_data = type('CollapsedTrim', (), values)()
    assert_rejected(body, 'planar_brep_degenerate')


def test_trim_unavailable_is_not_replaced_with_packed_legacy_metadata():
    body = make_body()
    body.edges[0].GetCurveParams3 = lambda: None
    body.edges[0].GetCurveParams2 = lambda: pytest.fail('No packed metadata fallback')
    assert_rejected(body, 'planar_brep_incomplete')


@pytest.mark.parametrize('kind', ['vertex', 'edge'])
@pytest.mark.parametrize('result,code', [
    ((True, 0.0), 'planar_brep_unsupported'),
    ((True, 1e-15), 'planar_brep_unsupported'),
    ((False, 1e-6), 'planar_brep_unsupported'),
    ((False, -1e-15), 'planar_brep_incomplete'),
    ((False, math.nan), 'planar_brep_incomplete'),
    ((False, math.inf), 'planar_brep_incomplete'),
    ((False, -math.inf), 'planar_brep_incomplete'),
    ((False, None), 'planar_brep_incomplete'),
    ((False, True), 'planar_brep_incomplete'),
    ((0, 0.0), 'planar_brep_incomplete'),
    ((False,), 'planar_brep_incomplete'),
    ((False, 0.0, 1), 'planar_brep_incomplete'),
    ([False, 0.0], 'planar_brep_incomplete'),
    (False, 'planar_brep_incomplete'),
    (None, 'planar_brep_incomplete'),
])
def test_native_tolerance_flag_out_shape_and_values_fail_closed(kind, result, code):
    body = make_body()
    entity = body.vertices[-1] if kind == 'vertex' else body.edges[-1]
    entity.IsTolerant = lambda: result
    assert_rejected(body, code)


@pytest.mark.parametrize('kind', ['vertex', 'edge'])
def test_false_tolerance_tuple_and_small_gap_are_stored_exactly(kind):
    body = make_body()
    before = snapshot(body)
    assert all(item == {'is_tolerant': False, 'gap_m': (0.0).hex()}
               for item in before['vertex_tolerances'])
    assert all(item['native_tolerance'] == {'is_tolerant': False, 'gap_m': (0.0).hex()}
               for item in before['edges'])
    entity = body.vertices[0] if kind == 'vertex' else body.edges[0]
    entity.IsTolerant = lambda: (False, 1e-15)
    after = snapshot(body)
    values = after['vertex_tolerances'] if kind == 'vertex' else [edge['native_tolerance'] for edge in after['edges']]
    assert {'is_tolerant': False, 'gap_m': (1e-15).hex()} in values
    assert planar_snapshot_digest(after) != planar_snapshot_digest(before)
    entity.IsTolerant = lambda: (False, math.nextafter(1e-15, 1.0))
    assert planar_snapshot_digest(snapshot(body)) != planar_snapshot_digest(after)


@pytest.mark.parametrize('kind', ['vertex', 'edge'])
@pytest.mark.parametrize('mode', ['raises', 'missing_callable'])
def test_native_tolerance_missing_and_errors_do_not_become_zero(kind, mode):
    body = make_body()
    entity = body.vertices[0] if kind == 'vertex' else body.edges[0]
    def fail(): raise RuntimeError('native tolerance unavailable')
    entity.IsTolerant = fail if mode == 'raises' else None
    with pytest.raises(PlanarBrepError) as exc:
        snapshot(body)
    assert exc.value.code == 'planar_brep_native_read_failed'
    assert isinstance(exc.value.__cause__, RuntimeError if mode == 'raises' else TypeError)


def test_exact_native_tolerance_negative_zero_not_normalized():
    body = make_body()
    before = digest(body)
    body.vertices[0].IsTolerant = lambda: (False, -0.0)
    assert digest(body) != before
    assert {'is_tolerant': False, 'gap_m': (-0.0).hex()} in snapshot(body)['vertex_tolerances']


def test_tightened_native_gap_limit_is_enforced():
    body = make_body()
    body.edges[0].IsTolerant = lambda: (False, 1e-15)
    assert_rejected(body, 'planar_brep_unsupported',
                    limits=PlanarBrepLimits(max_native_gap_m=1e-16))


@pytest.mark.parametrize('kind', ['vertex', 'edge'])
def test_exact_native_gap_boundary_retained_without_rounding(kind):
    body = make_body()
    entity = body.vertices[0] if kind == 'vertex' else body.edges[0]
    entity.IsTolerant = lambda: (False, 5e-9)
    at_limit = snapshot(body)
    values = (at_limit['vertex_tolerances'] if kind == 'vertex'
              else [edge['native_tolerance'] for edge in at_limit['edges']])
    assert {'is_tolerant': False, 'gap_m': (5e-9).hex()} in values
    entity.IsTolerant = lambda: (False, math.nextafter(5e-9, 0.0))
    assert planar_snapshot_digest(snapshot(body)) != planar_snapshot_digest(at_limit)
    entity.IsTolerant = lambda: (False, math.nextafter(5e-9, math.inf))
    assert_rejected(body, 'planar_brep_unsupported')


def test_native_gap_gate_is_independent_of_stricter_geometry_consistency():
    body = make_body()
    for entity in body.vertices + body.edges:
        entity.IsTolerant = lambda: (False, 5e-9)
    # Exact coordinates pass even with a tightened analytical consistency gate.
    assert snapshot(body, limits=PlanarBrepLimits(consistency_tolerance_m=1e-16))
    # Native exact class and its allowed reported gap cannot authorize a larger
    # vertex-to-plane mismatch than the independent default 1e-12 m limit.
    face = body.faces[0]
    face.surface.params = face.surface.params[:3] + (0.0, 0.0, 2e-12)
    assert_rejected(body, 'planar_brep_incomplete')


@pytest.mark.parametrize('value', [True, False, 0.0, -1e-9, math.nan,
                                 math.inf, -math.inf, None, '5e-9',
                                 math.nextafter(5e-9, math.inf)])
def test_native_gap_limit_validation_never_loosens_supported_scope(value):
    with pytest.raises(ValueError):
        PlanarBrepLimits(max_native_gap_m=value)


def body_with_check_results(results):
    """Return separate pre/post Check3 observations, including read failures."""
    class CheckedBody(Body):
        @property
        def Check3(self):
            self.check_reads += 1
            result = next(self.check_results)
            if isinstance(result, Exception):
                raise result
            return result

    body = make_body()
    body.__class__ = CheckedBody
    body.check_results = iter(results)
    body.check_reads = 0
    return body


@pytest.mark.parametrize('checks', [(None, None), (FaultEntity(0), FaultEntity(0)),
                                   (None, FaultEntity(0)), (FaultEntity(0), None)])
def test_check3_none_and_zero_fault_count_accept_complete_snapshot(checks):
    body = body_with_check_results(checks)
    interfaces = []
    def wrap(raw, interface):
        if isinstance(raw, FaultEntity):
            interfaces.append(interface)
        return raw

    assert snapshot(body, wrap=wrap) == snapshot(make_body())
    assert body.check_reads == 2
    assert interfaces == ['IFaultEntity'] * sum(item is not None for item in checks)


@pytest.mark.parametrize('stage', [0, 1], ids=['before', 'after'])
@pytest.mark.parametrize('count,code', [(1, 'planar_brep_invalid'),
                                     (17, 'planar_brep_invalid'),
                                     (-1, 'planar_brep_incomplete'),
                                     (True, 'planar_brep_incomplete'),
                                     (False, 'planar_brep_incomplete'),
                                     (0.0, 'planar_brep_incomplete'),
                                     (1.0, 'planar_brep_incomplete'),
                                     (None, 'planar_brep_incomplete'),
                                     ('0', 'planar_brep_incomplete')])
def test_check3_fault_count_must_be_exact_nonnegative_integer(stage, count, code):
    checks = [None, None]
    checks[stage] = FaultEntity(count)
    body = body_with_check_results(checks)
    assert_rejected(body, code)
    assert body.check_reads == stage + 1


@pytest.mark.parametrize('stage', [0, 1], ids=['before', 'after'])
@pytest.mark.parametrize('mode', ['check_read', 'count_read', 'missing_count',
                                 'wrap_error', 'wrap_none'])
def test_check3_unreadable_or_unwrappable_faults_fail_closed(stage, mode):
    native_error = RuntimeError('native fault observation failed')
    class UnreadableFault:
        @property
        def Count(self):
            raise native_error

    checks = [None, None]
    checks[stage] = (native_error if mode == 'check_read' else
                     UnreadableFault() if mode == 'count_read' else
                     object() if mode == 'missing_count' else FaultEntity(0))
    body = body_with_check_results(checks)
    def wrap(raw, interface):
        if interface == 'IFaultEntity':
            if mode == 'wrap_error':
                raise native_error
            if mode == 'wrap_none':
                return None
        return raw

    with pytest.raises(PlanarBrepError) as exc:
        snapshot(body, wrap=wrap)
    assert exc.value.code == ('planar_brep_incomplete' if mode == 'wrap_none'
                              else 'planar_brep_native_read_failed')
    assert body.check_reads == stage + 1
    if mode in ('check_read', 'count_read', 'wrap_error'):
        assert exc.value.__cause__ is native_error
    elif mode == 'missing_count':
        assert isinstance(exc.value.__cause__, AttributeError)


@pytest.mark.parametrize('mode,code', [('missing', 'planar_brep_incomplete'),
                                     ('foreign', 'planar_brep_incomplete'),
                                     ('raises', 'planar_brep_native_read_failed')])
def test_public_getloop_requires_confirmed_native_owner_without_fallback(mode, code):
    body = make_body()
    coedge = body.faces[0].loops[0].ordered[0]
    native_error = RuntimeError('public GetLoop unavailable')
    def get_loop():
        if mode == 'raises':
            raise native_error
        return None if mode == 'missing' else body.faces[1].loops[0]

    coedge.GetLoop = get_loop
    # A seemingly usable private accessor must never bypass public failure.
    def private_accessor():
        pytest.fail('No fallback to IGetLoop2 is permitted.')
    coedge.IGetLoop2 = private_accessor
    with pytest.raises(PlanarBrepError) as exc:
        snapshot(body)
    assert exc.value.code == code
    if mode == 'raises':
        assert exc.value.__cause__ is native_error
