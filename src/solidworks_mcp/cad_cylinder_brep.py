"""Complete right-cylinder boundary candidate; zero-vertex periodic topology.

Retains both full circle curves/trims, two planar caps, cylindrical surface and
all ordered loop/coedge memberships. No tessellation, bounds or partial fallback.
Seamed/split cylinders and other curved surfaces require separate extensions.
The caller supplies the complete document/configuration/event closing proof.
"""

import math

from .cad_planar_brep import PlanarBrepError, PlanarBrepLimits, _Reader, _hex


CYLINDER_BREP_SCOPE = 'right_circular_cylinder_brep_v1'


def _fail(message, code='cylindrical_brep_incomplete'):
    raise PlanarBrepError(code, message)


def _dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


def _subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _unit(vector):
    if not math.isclose(_dot(vector, vector), 1., rel_tol=0., abs_tol=1e-12):
        _fail('Analytical surface/curve axis must have native unit length.')


def cylinder_body_snapshot(body, *, identity, wrap=None, limits=None):
    r = _Reader(identity, wrap, limits or PlanarBrepLimits())
    body = r.obj(body, 'IBody2')
    body_key = r.key(body, 'IBody2')
    body_type = r.call(body, 'GetType')
    if type(body_type) is not int or body_type != 0 or r.flag(r.call(body, 'IsMeshBody'), 'IsMeshBody'):
        _fail('Only an exact solid cylinder is supported.', 'cylindrical_brep_unsupported')
    r.check_body(body)
    stamp = r.call(body, 'GetUpdateStamp')
    if type(stamp) is not int:
        _fail('Invalid native body stamp.')

    def counts():
        return (r.count(body, 'GetVertexCount', r.limits.max_vertices, 0),
                r.count(body, 'GetEdgeCount', r.limits.max_edges, 0),
                r.count(body, 'GetFaceCount', r.limits.max_faces, 0))

    if counts() != (0, 2, 3):
        _fail('This complete cylinder scope requires zero vertices, two circular edges and three faces.',
              'cylindrical_brep_unsupported')
    if r.call(body, 'GetVertices') not in (None, (), []):
        _fail('Zero vertex count disagrees with the complete vertex array.')
    edges, edge_keys = r.array(body, 'GetEdges', 'IEdge', 2)
    faces, face_keys = r.array(body, 'GetFaces', 'IFace2', 3)
    edge_data, uses = {}, {}
    tolerance = r.limits.consistency_tolerance_m
    for edge, key in zip(edges, edge_keys):
        if r.key(r.obj(r.call(edge, 'GetBody'), 'IBody2'), 'IBody2') != body_key:
            _fail('A circle belongs to another body.')
        if r.call(edge, 'GetStartVertex') is not None or r.call(edge, 'GetEndVertex') is not None:
            _fail('Periodic circles in this scope have no finite endpoint vertices.')
        curve = r.obj(r.call(edge, 'GetCurve'), 'ICurve')
        if not r.flag(r.call(curve, 'IsCircle'), 'IsCircle') or r.flag(r.call(curve, 'IsLine'), 'IsLine'):
            _fail('Every boundary edge must be an exact circle.', 'cylindrical_brep_unsupported')
        circle = r.numbers(r.prop(curve, 'CircleParams'), 7, 'circle parameters')
        _unit(circle[3:6])
        if circle[6] <= 0:
            _fail('Circle radius is not positive.')
        params = r.obj(r.call(edge, 'GetCurveParams3'), 'ICurveParamData')
        curve_type = r.prop(params, 'CurveType')
        if type(curve_type) is not int or curve_type != 3002:
            _fail('Native trimmed curve type must be CIRCLE_TYPE.')
        sense = r.flag(r.prop(params, 'Sense'), 'curve/edge Sense')
        interval = r.numbers((r.prop(params, 'UMinValue'), r.prop(params, 'UMaxValue')), 2, 'circle interval')
        if interval[0] >= interval[1] or not math.isclose(interval[1]-interval[0], 2.*math.pi,
                                                       rel_tol=0., abs_tol=1e-12):
            _fail('A full circle must retain exactly one complete native parameter period.')
        start = r.numbers(r.prop(params, 'StartPoint'), 3, 'circle trim start')
        end = r.numbers(r.prop(params, 'EndPoint'), 3, 'circle trim end')
        if any(abs(a-b) > tolerance for a, b in zip(start, end)):
            _fail('Full-circle trim endpoints do not close.')
        for point in (start, end):
            delta = _subtract(point, circle[:3])
            if (abs(_dot(delta, circle[3:6])) > tolerance
                    or not math.isclose(math.sqrt(_dot(delta, delta)), circle[6], rel_tol=0., abs_tol=tolerance)):
                _fail('Trim endpoint does not lie on the exact native circle.')
        _, declared = r.array(edge, 'GetCoEdges', 'ICoEdge', 2)
        edge_data[key] = {'circle': circle, 'tolerance': r.tolerance(edge), 'declared': set(declared),
                         'trim': {'curve_type': curve_type, 'same_direction_as_edge': sense,
                                  'interval': list(_hex(interval)), 'start': list(_hex(start)), 'end': list(_hex(end))}}
        uses[key] = []

    face_data, coedges, loop_members = {}, {}, set()
    for face, key in zip(faces, face_keys):
        if r.key(r.obj(r.call(face, 'GetBody'), 'IBody2'), 'IBody2') != body_key:
            _fail('A face belongs to another body.')
        surface = r.obj(r.call(face, 'GetSurface'), 'ISurface')
        plane = r.flag(r.call(surface, 'IsPlane'), 'IsPlane')
        cylinder = r.flag(r.call(surface, 'IsCylinder'), 'IsCylinder')
        if plane == cylinder:
            _fail('Each face must be exactly planar or cylindrical.', 'cylindrical_brep_unsupported')
        kind = 'plane' if plane else 'cylinder'
        parameters = r.numbers(r.prop(surface, 'PlaneParams' if plane else 'CylinderParams'),
                               6 if plane else 7, 'surface parameters')
        _unit(parameters[:3] if plane else parameters[3:6])
        sense = r.flag(r.call(face, 'FaceInSurfaceSense'), 'FaceInSurfaceSense')
        if cylinder and (parameters[6] <= 0 or sense):
            _fail('A positive outward cylindrical surface is required in this initial scope.')
        count = r.count(face, 'GetLoopCount', 2)
        if count != (1 if plane else 2):
            _fail('Caps need one circular loop; the periodic side needs two boundary loops.')
        loops, loop_keys = r.array(face, 'GetLoops', 'ILoop2', count)
        linked, current = [], r.obj(r.call(face, 'GetFirstLoop'), 'ILoop2')
        for _ in range(count):
            loop_key = r.key(current, 'ILoop2')
            if loop_key in linked: _fail('Loop traversal repeats early.')
            linked.append(loop_key)
            current = r.call(current, 'GetNext')
            if current is not None: current = r.obj(current, 'ILoop2')
        if current is not None or set(linked) != set(loop_keys):
            _fail('Linked loop census disagrees with the complete native array.')
        rows, face_edges = [], set()
        for loop, loop_key in zip(loops, loop_keys):
            if loop_key in loop_members: _fail('Different faces share a native loop.')
            loop_members.add(loop_key)
            if r.key(r.obj(r.call(loop, 'GetFace'), 'IFace2'), 'IFace2') != key:
                _fail('A loop belongs to another face.')
            if (not r.flag(r.call(loop, 'IsOuter'), 'IsOuter')
                    or r.flag(r.call(loop, 'IsSingular'), 'IsSingular')):
                _fail('Exact complete cylinder boundary loops must be outer and nonsingular.')
            if (r.count(loop, 'GetCoEdgeCount', 1) != 1 or r.count(loop, 'GetEdgeCount', 1) != 1
                    or r.count(loop, 'GetVertexCount', 1, 0) != 0
                    or r.call(loop, 'GetVertices') not in (None, (), [])):
                _fail('A periodic boundary loop needs one whole circle and no vertices.')
            native_uses, use_keys = r.array(loop, 'GetCoEdges', 'ICoEdge', 1)
            use, use_key = native_uses[0], use_keys[0]
            if use_key in coedges: _fail('Coedge membership is duplicated.')
            if (r.key(r.obj(r.call(loop, 'GetFirstCoEdge'), 'ICoEdge'), 'ICoEdge') != use_key
                    or r.key(r.obj(r.call(use, 'GetNext'), 'ICoEdge'), 'ICoEdge') != use_key
                    or r.key(r.obj(r.call(use, 'GetLoop'), 'ILoop2'), 'ILoop2') != loop_key):
                _fail('The full circular coedge cycle is inconsistent.')
            if r.call(use, 'GetCurve') is not None:
                _fail('Imprecisely sewn coedge geometry is unsupported.', 'cylindrical_brep_unsupported')
            edge_key = r.key(r.obj(r.call(use, 'GetEdge'), 'IEdge'), 'IEdge')
            if edge_key not in edge_data or edge_key in face_edges:
                _fail('A foreign or repeated edge appears in one face boundary.')
            _, declared = r.array(loop, 'GetEdges', 'IEdge', 1)
            if declared != [edge_key]: _fail('Loop edge array disagrees with the exact coedge.')
            face_edges.add(edge_key)
            use_sense = r.flag(r.call(use, 'GetSense'), 'GetSense')
            partner = r.key(r.obj(r.call(use, 'GetPartner'), 'ICoEdge'), 'ICoEdge')
            coedges[use_key] = {'face': key, 'edge': edge_key, 'sense': use_sense, 'partner': partner}
            uses[edge_key].append(use_key)
            rows.append(use_key)
        _, declared = r.array(face, 'GetEdges', 'IEdge', r.count(face, 'GetEdgeCount', 2))
        if set(declared) != face_edges: _fail('Complete face edge census disagrees with its loops.')
        face_data[key] = {'kind': kind, 'parameters': parameters, 'sense': sense, 'uses': rows}

    cylindrical = [key for key in face_keys if face_data[key]['kind'] == 'cylinder']
    caps = [key for key in face_keys if face_data[key]['kind'] == 'plane']
    if len(cylindrical) != 1 or len(caps) != 2:
        _fail('The entire solid must consist of one cylindrical side and two planar caps.')
    cylindrical_key = cylindrical[0]
    cylinder = face_data[cylindrical_key]['parameters']
    axis, origin, radius = cylinder[3:6], cylinder[:3], cylinder[6]
    centres = sorted(((_dot(_subtract(edge_data[key]['circle'][:3], origin), axis), key)
                      for key in edge_keys))
    height = centres[1][0]-centres[0][0]
    if height <= tolerance:
        _fail('Two distinct cap centres must bound a positive cylinder length.')
    for position, key in centres:
        circle = edge_data[key]['circle']
        delta = _subtract(circle[:3], origin)
        if (any(abs(value-position*direction) > tolerance for value, direction in zip(delta, axis))
                or not math.isclose(abs(_dot(circle[3:6], axis)), 1., rel_tol=0., abs_tol=1e-12)
                or abs(circle[6]-radius) > tolerance):
            _fail('Complete circles do not bound this exact cylindrical surface.')
        members = uses[key]
        if len(members) != 2 or set(members) != edge_data[key]['declared']:
            _fail('Each complete circle must have two exact declared uses.')
        a, b = (coedges[member] for member in members)
        if (a['face'] == b['face'] or a['sense'] == b['sense']
                or a['partner'] != members[1] or b['partner'] != members[0]
                or cylindrical_key not in (a['face'], b['face'])):
            _fail('Native circle partners, orientation or cap/side incidence are inconsistent.')
        cap_use = next(member for member in members if coedges[member]['face'] != cylindrical_key)
        cap = face_data[coedges[cap_use]['face']]
        normal = tuple(-v if cap['sense'] else v for v in cap['parameters'][:3])
        outward = -1. if key == centres[0][1] else 1.
        if (not math.isclose(_dot(normal, axis), outward, rel_tol=0., abs_tol=1e-12)
                or abs(_dot(_subtract(circle[:3], cap['parameters'][3:6]), normal)) > tolerance):
            _fail('Planar cap surface does not bound the expected end of the solid cylinder.')
        direction = 1. if coedges[cap_use]['sense'] == edge_data[key]['trim']['same_direction_as_edge'] else -1.
        if not math.isclose(_dot(circle[3:6], normal)*direction, 1., rel_tol=0., abs_tol=1e-12):
            _fail('Cap circular coedge winding disagrees with its outward normal.')

    # Close every root membership after analytical/topological reads. Identical
    # replacement geometry cannot silently replace the retained native census.
    r.check_body(body)
    _, closing_edges = r.array(body, 'GetEdges', 'IEdge', 2)
    _, closing_faces = r.array(body, 'GetFaces', 'IFace2', 3)
    if (set(closing_edges) != set(edge_keys) or set(closing_faces) != set(face_keys)
            or counts() != (0, 2, 3) or r.call(body, 'GetUpdateStamp') != stamp
            or r.call(body, 'GetVertices') not in (None, (), [])):
        _fail('Native cylinder census or body stamp changed during collection.', 'cylindrical_brep_changed_during_read')
    ordered_edges = sorted(edge_keys, key=lambda key:(edge_data[key]['circle'], edge_data[key]['trim']['interval']))
    ordered_faces = sorted(face_keys, key=lambda key:(face_data[key]['kind'], face_data[key]['parameters'], face_data[key]['sense']))
    edge_index = {key:index for index,key in enumerate(ordered_edges)}
    face_index = {key:index for index,key in enumerate(ordered_faces)}
    loop_positions = {}
    ordered_loops = {}
    for key in ordered_faces:
        ordered_loops[key] = sorted(face_data[key]['uses'], key=lambda use:edge_index[coedges[use]['edge']])
        for index,use in enumerate(ordered_loops[key]): loop_positions[use] = [face_index[key],index,0]
    return {'scope': CYLINDER_BREP_SCOPE, 'coordinate_frame':'part_model', 'length_unit':'m',
        'number_encoding':'ieee754_binary64_hex_exact', 'vertices':[], 'vertex_tolerances':[],
        'edges':[{'kind':'circle','circle_parameters':list(_hex(edge_data[key]['circle'])),
                  'trim':edge_data[key]['trim'],'tolerance':edge_data[key]['tolerance'],
                  'start':None,'end':None,'uses':sorted(loop_positions[use] for use in uses[key])} for key in ordered_edges],
        'faces':[{'surface_type':face_data[key]['kind'], 'surface_parameters':list(_hex(face_data[key]['parameters'])),
                  'normal_opposes_surface':face_data[key]['sense'],
                  'loops':[{'outer':True,'coedges':[{'edge':edge_index[coedges[use]['edge']],
                      'same_direction_as_edge':coedges[use]['sense'],'start':None,'end':None,
                      'partner':loop_positions[coedges[use]['partner']]}]} for use in ordered_loops[key]]}
                 for key in ordered_faces]}
