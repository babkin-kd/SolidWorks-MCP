"""Complete planar solid boundary with unseamed cylindrical through holes.

Reads real native censuses, line/circle trims, planar/cylindrical surfaces and
every ordered loop/coedge. No projected/fake body, bounds, mass or partial BREP.
Each planar face has one linear outer loop and zero or more full-circle inner
loops; every inward cylinder connects two such loops on perpendicular planes.
The caller still brackets two full reads with document/configuration/events.
"""

from fractions import Fraction
import math

from .cad_planar_brep import (PlanarBrepError, PlanarBrepLimits, _Reader, _hex,
    _line_consistent, _plane_consistent, _points_consistent, _inside, _validate_polygons)
from .cad_cylinder_brep import _dot, _subtract, _unit


HOLE_BREP_SCOPE = 'planar_body_cylindrical_through_holes_brep_v1'


def _fail(message, code='hole_brep_incomplete'):
    raise PlanarBrepError(code,message)


def _comparison(r):
    r.polygon_comparisons += 1
    if r.polygon_comparisons > r.limits.max_polygon_comparisons:
        _fail('Complete hole/polygon validation budget exceeded.', 'hole_brep_budget_exceeded')


def _loop_vertices(r, loop, count):
    # Native periodic loops may report null rather than an empty SAFEARRAY.
    # Null is permitted only after the exact native zero-count check.
    raw = r.call(loop, 'GetVertices')
    if raw is None and count == 0:
        return []
    if not isinstance(raw, (tuple, list)) or len(raw) != count:
        _fail('Complete loop vertex array disagrees with its native count.')
    keys = [r.key(r.obj(item, 'IVertex'), 'IVertex') for item in raw]
    if len(set(keys)) != len(keys):
        _fail('The native loop vertex array repeats an entity.')
    return keys


def _line(r, edge, points, vertex_index):
    curve = r.obj(r.call(edge,'GetCurve'),'ICurve')
    parameters = r.numbers(r.prop(curve,'LineParams'),6,'line parameters')
    if not any(parameters[3:]):
        _fail('A finite line requires a nonzero direction.')
    a = r.key(r.obj(r.call(edge,'GetStartVertex'),'IVertex'),'IVertex')
    b = r.key(r.obj(r.call(edge,'GetEndVertex'),'IVertex'),'IVertex')
    if a not in points or b not in points or a == b:
        _fail('Line endpoints must be two distinct vertices from the complete body.')
    for point in (points[a],points[b]):
        if not _line_consistent(point,parameters,r.limits.consistency_tolerance_m):
            _fail('A line endpoint is inconsistent with the native curve.')
    trim = r.obj(r.call(edge,'GetCurveParams3'),'ICurveParamData')
    kind = r.prop(trim,'CurveType')
    if type(kind) is not int or kind != 3001:
        _fail('A line requires an exact native LINE_TYPE trim.')
    sense = r.flag(r.prop(trim,'Sense'),'curve Sense')
    start = r.numbers(r.prop(trim,'StartPoint'),3,'trim start')
    end = r.numbers(r.prop(trim,'EndPoint'),3,'trim end')
    interval = r.numbers((r.prop(trim,'UMinValue'),r.prop(trim,'UMaxValue')),2,'trim interval')
    expected = (points[a],points[b]) if sense else (points[b],points[a])
    if interval[0] >= interval[1] or start == end:
        _fail('Finite line trims must retain a positive interval and distinct endpoints.')
    for point,reference in zip((start,end),expected):
        if (not _line_consistent(point,parameters,r.limits.consistency_tolerance_m)
                or not _points_consistent(point,reference,r.limits.consistency_tolerance_m)):
            _fail('Native line trim and endpoint sense are inconsistent.')
    return {'kind':'line','parameters':parameters,'start':a,'end':b,
        'trim':{'curve_type':kind,'same_direction_as_edge':sense,'start_point':list(_hex(start)),
                'end_point':list(_hex(end)),'u_min':interval[0].hex(),'u_max':interval[1].hex()},
        'key':(0,tuple(sorted((vertex_index[a],vertex_index[b]))))}


def _circle(r, edge):
    if r.call(edge,'GetStartVertex') is not None or r.call(edge,'GetEndVertex') is not None:
        _fail('This periodic circle scope has no finite endpoint vertices.','hole_brep_unsupported')
    curve = r.obj(r.call(edge,'GetCurve'),'ICurve')
    circle = r.numbers(r.prop(curve,'CircleParams'),7,'circle parameters')
    _unit(circle[3:6])
    if circle[6] <= 0:
        _fail('A circle requires a positive radius.')
    trim = r.obj(r.call(edge,'GetCurveParams3'),'ICurveParamData')
    kind = r.prop(trim,'CurveType')
    if type(kind) is not int or kind != 3002:
        _fail('A full circle requires an exact native CIRCLE_TYPE trim.')
    sense = r.flag(r.prop(trim,'Sense'),'curve Sense')
    interval = r.numbers((r.prop(trim,'UMinValue'),r.prop(trim,'UMaxValue')),2,'circle interval')
    if interval[0] >= interval[1] or not math.isclose(interval[1]-interval[0],2.*math.pi,rel_tol=0.,abs_tol=1e-12):
        _fail('Every periodic boundary must retain one complete native circle period.')
    start = r.numbers(r.prop(trim,'StartPoint'),3,'circle trim start')
    end = r.numbers(r.prop(trim,'EndPoint'),3,'circle trim end')
    if not _points_consistent(start,end,r.limits.consistency_tolerance_m):
        _fail('Full-circle endpoints do not close.')
    for point in (start,end):
        delta = _subtract(point,circle[:3])
        if (abs(_dot(delta,circle[3:6])) > r.limits.consistency_tolerance_m
                or not math.isclose(math.sqrt(_dot(delta,delta)),circle[6],rel_tol=0.,abs_tol=r.limits.consistency_tolerance_m)):
            _fail('A native trim endpoint does not lie on the exact circle.')
    return {'kind':'circle','parameters':circle,'start':None,'end':None,
        'trim':{'curve_type':kind,'same_direction_as_edge':sense,'start_point':list(_hex(start)),
                'end_point':list(_hex(end)),'u_min':interval[0].hex(),'u_max':interval[1].hex()},
        'key':(1,_hex(circle),_hex(interval),sense)}


def _circle_inside(r, circle, polygon, normal):
    """Exact binary-rational containment, with a conservative rejection margin."""
    axis = max(range(3),key=lambda i:abs(normal[i]))
    axes = ((1,2),(2,0),(0,1))[axis]
    centre = tuple(Fraction(value) for value in circle[:3])
    vertices = [tuple(Fraction(value) for value in point) for point in polygon]
    for _ in vertices:
        _comparison(r)
    if not _inside(tuple(centre[i] for i in axes),[tuple(point[i] for i in axes) for point in vertices]):
        _fail('A circular inner loop must lie inside its complete linear outer loop.')
    radius = Fraction(circle[6])+Fraction(r.limits.consistency_tolerance_m)
    for a,b in zip(vertices,vertices[1:]+vertices[:1]):
        vector = tuple(y-x for x,y in zip(a,b))
        delta = tuple(c-x for c,x in zip(centre,a))
        length = sum(v*v for v in vector)
        if length == 0:
            _fail('A finite polygon edge cannot collapse.')
        t = min(Fraction(1),max(Fraction(0),sum(x*y for x,y in zip(delta,vector))/length))
        distance = sum((d-t*v)**2 for d,v in zip(delta,vector))
        if distance <= radius**2:
            _fail('A full inner circle intersects or touches the linear outer boundary.')


def hole_body_snapshot(body, *, identity, wrap=None, limits=None):
    return _mixed_body_snapshot(body,identity=identity,wrap=wrap,limits=limits)


def _mixed_body_snapshot(body, *, identity, wrap=None, limits=None, finite_arcs=False):
    if finite_arcs:
        from .cad_arc_brep import _arc, _validate_planar_arcs, _validate_cylinder_quad, ARC_BREP_SCOPE
    r = _Reader(identity,wrap,limits or PlanarBrepLimits())
    body = r.obj(body,'IBody2')
    body_key = r.key(body,'IBody2')
    kind = r.call(body,'GetType')
    if type(kind) is not int or kind != 0 or r.flag(r.call(body,'IsMeshBody'),'IsMeshBody'):
        _fail('Only native solid analytical bodies are supported.','hole_brep_unsupported')
    r.check_body(body)
    stamp = r.call(body,'GetUpdateStamp')
    if type(stamp) is not int:
        _fail('The native body update stamp is invalid.')
    def census():
        return (r.count(body,'GetVertexCount',r.limits.max_vertices,4),
                r.count(body,'GetEdgeCount',r.limits.max_edges,8),
                r.count(body,'GetFaceCount',r.limits.max_faces,5))
    counts = census()
    vertices,vertex_keys = r.array(body,'GetVertices','IVertex',counts[0])
    edges,edge_keys = r.array(body,'GetEdges','IEdge',counts[1])
    faces,face_keys = r.array(body,'GetFaces','IFace2',counts[2])
    points = {key:r.numbers(r.call(vertex,'GetPoint'),3,'vertex') for vertex,key in zip(vertices,vertex_keys)}
    tolerances = {key:r.tolerance(vertex) for vertex,key in zip(vertices,vertex_keys)}
    if len(set(points.values())) != len(points):
        _fail('Distinct native vertices coincide; coordinate merging is forbidden.')
    vertex_order = sorted(vertex_keys,key=lambda key:_hex(points[key]))
    vertex_index = {key:index for index,key in enumerate(vertex_order)}
    incidence = {key:set() for key in vertex_keys}
    edge_data, pairs = {},set()
    for edge,key in zip(edges,edge_keys):
        if r.key(r.obj(r.call(edge,'GetBody'),'IBody2'),'IBody2') != body_key:
            _fail('An edge belongs to a foreign body.')
        curve = r.obj(r.call(edge,'GetCurve'),'ICurve')
        line,circle = r.flag(r.call(curve,'IsLine'),'IsLine'),r.flag(r.call(curve,'IsCircle'),'IsCircle')
        if line == circle:
            _fail('Every native boundary edge must be exactly a line or full circle.','hole_brep_unsupported')
        record = _line(r,edge,points,vertex_index) if line else (
            _arc(r,edge,points,vertex_index) if finite_arcs else _circle(r,edge))
        record.update(tolerance=r.tolerance(edge),uses=[])
        if line or finite_arcs:
            if record['key'] in pairs:
                _fail('Distinct finite native edges have identical endpoints.')
            pairs.add(record['key'])
            incidence[record['start']].add(key)
            incidence[record['end']].add(key)
        edge_data[key] = record
    if not any(row['kind']==('arc' if finite_arcs else 'circle') for row in edge_data.values()):
        _fail('This scope requires at least one cylindrical through hole.','hole_brep_unsupported')
    edge_order = sorted(edge_keys,key=lambda key:edge_data[key]['key'])
    if len({edge_data[key]['key'] for key in edge_keys}) != len(edge_keys):
        _fail('The complete native edge descriptions are ambiguous.')
    edge_index = {key:index for index,key in enumerate(edge_order)}
    for vertex,key in zip(vertices,vertex_keys):
        _,declared = r.array(vertex,'GetEdges','IEdge',maximum=r.limits.max_edges)
        if set(declared) != incidence[key]:
            _fail('Complete vertex incidence disagrees with the finite boundary edges.')
    face_data,loop_data,coedges = {},{},{}
    for face,face_key in zip(faces,face_keys):
        if r.key(r.obj(r.call(face,'GetBody'),'IBody2'),'IBody2') != body_key:
            _fail('A face belongs to a foreign body.')
        surface = r.obj(r.call(face,'GetSurface'),'ISurface')
        plane,cylinder = r.flag(r.call(surface,'IsPlane'),'IsPlane'),r.flag(r.call(surface,'IsCylinder'),'IsCylinder')
        if plane == cylinder:
            _fail('Every native surface must be exactly planar or cylindrical.','hole_brep_unsupported')
        surface_kind = 'plane' if plane else 'cylinder'
        parameters = r.numbers(r.prop(surface,'PlaneParams' if plane else 'CylinderParams'),6 if plane else 7,'surface parameters')
        _unit(parameters[:3] if plane else parameters[3:6])
        sense = r.flag(r.call(face,'FaceInSurfaceSense'),'FaceInSurfaceSense')
        if cylinder and ((not finite_arcs and not sense) or parameters[6] <= 0):
            _fail('A through-hole cylinder requires a positive radius and inward native orientation.','hole_brep_unsupported')
        count = r.count(face,'GetLoopCount',r.limits.max_loops)
        if len(loop_data)+count > r.limits.max_loops:
            _fail('Complete loop budget exceeded.','hole_brep_budget_exceeded')
        loops,loop_keys = r.array(face,'GetLoops','ILoop2',count)
        traversed,current = [],r.obj(r.call(face,'GetFirstLoop'),'ILoop2')
        for _ in range(count):
            key = r.key(current,'ILoop2')
            if key in traversed:
                _fail('Face loop traversal repeats before the complete census.')
            traversed.append(key)
            raw = r.call(current,'GetNext')
            current = r.obj(raw,'ILoop2') if raw is not None else None
        if current is not None or set(traversed) != set(loop_keys):
            _fail('Linked face-loop traversal disagrees with its complete array.')
        face_edges,face_loops = set(),[]
        for loop,loop_key in zip(loops,loop_keys):
            if loop_key in loop_data or r.key(r.obj(r.call(loop,'GetFace'),'IFace2'),'IFace2') != face_key:
                _fail('A loop is shared or belongs to another native face.')
            if r.flag(r.call(loop,'IsSingular'),'IsSingular'):
                _fail('Singular boundary loops require a separate complete scope.','hole_brep_unsupported')
            outer = r.flag(r.call(loop,'IsOuter'),'IsOuter')
            count = r.count(loop,'GetCoEdgeCount',r.limits.max_loop_coedges)
            if len(coedges)+count > r.limits.max_coedges:
                _fail('Complete coedge budget exceeded.','hole_brep_budget_exceeded')
            if count == 2:
                _fail('Complete loop must be a polygon or one periodic circle.','hole_brep_unsupported')
            _,declared = r.array(loop,'GetCoEdges','ICoEdge',count)
            current = r.obj(r.call(loop,'GetFirstCoEdge'),'ICoEdge')
            first = r.key(current,'ICoEdge')
            ordered = []
            for _ in range(count):
                key = r.key(current,'ICoEdge')
                if key in coedges or key in ordered or r.key(r.obj(r.call(current,'GetLoop'),'ILoop2'),'ILoop2') != loop_key:
                    _fail('Native coedge cycle repeats or has a foreign owner.')
                if r.call(current,'GetCurve') is not None:
                    _fail('Imprecisely sewn coedges require their own complete curve capture.','hole_brep_unsupported')
                edge_key = r.key(r.obj(r.call(current,'GetEdge'),'IEdge'),'IEdge')
                if edge_key not in edge_data or edge_key in face_edges:
                    _fail('A face includes a foreign or repeated native edge.')
                face_edges.add(edge_key)
                edge = edge_data[edge_key]
                coedge_sense = r.flag(r.call(current,'GetSense'),'GetSense')
                a,b = (edge['start'],edge['end']) if coedge_sense else (edge['end'],edge['start'])
                partner = r.key(r.obj(r.call(current,'GetPartner'),'ICoEdge'),'ICoEdge')
                coedges[key] = {'edge':edge_key,'face':face_key,'loop':loop_key,'sense':coedge_sense,
                                'start':a,'end':b,'partner':partner}
                edge['uses'].append(key)
                ordered.append(key)
                current = r.obj(r.call(current,'GetNext'),'ICoEdge')
            if r.key(current,'ICoEdge') != first or set(ordered) != set(declared):
                _fail('The complete oriented coedge cycle disagrees with enumeration.')
            periodic = count == 1
            if (periodic and edge_data[coedges[ordered[0]]['edge']]['kind'] != 'circle') or (
                    not periodic and not finite_arcs and any(edge_data[coedges[key]['edge']]['kind'] != 'line' for key in ordered)):
                _fail('A supported loop is one full circle or a complete finite linear polygon.','hole_brep_unsupported')
            loop_vertices = [] if periodic else [coedges[key]['start'] for key in ordered]
            if not periodic:
                if len(set(loop_vertices)) != count or not outer or (not finite_arcs and not plane):
                    _fail('A planar finite outer loop must visit every native vertex exactly once.','hole_brep_unsupported')
                for a,b in zip(ordered,ordered[1:]+ordered[:1]):
                    if coedges[a]['end'] != coedges[b]['start']:
                        _fail('Native finite coedges do not form a continuous oriented loop.')
                if plane and any(not _plane_consistent(points[key],parameters,r.limits.consistency_tolerance_m) for key in loop_vertices):
                    _fail('A polygon vertex does not lie on its exact planar surface.')
            elif outer != cylinder:
                _fail('Circular cap loops must be inner; the cylindrical boundaries must be outer.')
            _,declared_edges = r.array(loop,'GetEdges','IEdge',r.count(loop,'GetEdgeCount',r.limits.max_loop_coedges))
            declared_vertices = _loop_vertices(r,loop,r.count(loop,'GetVertexCount',r.limits.max_loop_coedges,0))
            if (set(declared_edges) != {coedges[key]['edge'] for key in ordered}
                    or set(declared_vertices) != set(loop_vertices)):
                _fail('Complete loop edge/vertex arrays disagree with ordered coedges.')
            tokens = [(edge_index[coedges[key]['edge']],coedges[key]['sense']) for key in ordered]
            rotation = min(range(count),key=lambda index:tokens[index])
            ordered,tokens = ordered[rotation:]+ordered[:rotation],tokens[rotation:]+tokens[:rotation]
            loop_data[loop_key] = {'outer':outer,'periodic':periodic,'ordered':ordered,'vertices':loop_vertices,
                                   'face':face_key,'native':loop,'key':(outer,tuple(tokens))}
            face_loops.append(loop_key)
        _,declared = r.array(face,'GetEdges','IEdge',r.count(face,'GetEdgeCount',r.limits.max_edges))
        if set(declared) != face_edges:
            _fail('The complete face edge array disagrees with all its loops.')
        linear = [loop_data[key] for key in face_loops if not loop_data[key]['periodic']]
        if plane:
            if len(linear) != 1:
                _fail('Each planar face requires one complete finite outer polygon.','hole_brep_unsupported')
            _validate_polygons(r,linear,parameters[:3],sense,points)
            if finite_arcs:
                _validate_planar_arcs(r,linear[0],parameters,sense,coedges,edge_data)
            circles = [edge_data[coedges[loop_data[key]['ordered'][0]]['edge']]['parameters']
                       for key in face_loops if loop_data[key]['periodic']]
            outward = tuple(-value if sense else value for value in parameters[:3])
            for circle in circles:
                if (not _plane_consistent(circle[:3],parameters,r.limits.consistency_tolerance_m)
                        or not math.isclose(abs(_dot(circle[3:6],outward)),1.,rel_tol=0.,abs_tol=1e-12)):
                    _fail('The entire inner circle must lie on its exact planar cap.')
                _circle_inside(r,circle,[points[key] for key in linear[0]['vertices']],outward)
            for index,a in enumerate(circles):
                for b in circles[index+1:]:
                    _comparison(r)
                    delta = [Fraction(x)-Fraction(y) for x,y in zip(a[:3],b[:3])]
                    radius = Fraction(a[6])+Fraction(b[6])+Fraction(r.limits.consistency_tolerance_m)
                    if sum(value*value for value in delta) <= radius**2:
                        _fail('Circular inner loops overlap, nest or touch.')
        elif finite_arcs:
            if len(linear)!=1 or len(face_loops)!=1:
                _fail('Finite cylindrical wall requires one complete closed outer loop.','arc_brep_unsupported')
            _validate_cylinder_quad(r,linear[0],parameters,sense,points,coedges,edge_data)
        elif linear or len(face_loops) != 2:
            _fail('A periodic cylindrical wall must have exactly two full circular boundary loops.','hole_brep_unsupported')
        face_loops.sort(key=lambda key:loop_data[key]['key'])
        face_data[face_key] = {'kind':surface_kind,'parameters':parameters,'sense':sense,'loops':face_loops,
            'native':face,'edges':face_edges,'key':(0 if plane else 1,_hex(parameters),sense,tuple(loop_data[key]['key'] for key in face_loops))}

    if not finite_arcs:
        _validate_holes(r,face_data,loop_data,coedges,edge_data)
    for edge,key in zip(edges,edge_keys):
        uses = edge_data[key]['uses']
        _,declared = r.array(edge,'GetCoEdges','ICoEdge',2)
        if len(uses) != 2 or set(uses) != set(declared):
            _fail('Every native solid edge must have two complete declared uses.')
        a,b = (coedges[use] for use in uses)
        if (a['face'] == b['face'] or a['sense'] == b['sense'] or a['partner'] != uses[1] or b['partner'] != uses[0]):
            _fail('Native edge incidence, partner pointers or orientation are inconsistent.')
    _validate_fans(incidence,edge_data,coedges)
    face_order = sorted(face_keys,key=lambda key:face_data[key]['key'])
    if len({face_data[key]['key'] for key in face_keys}) != len(face_keys):
        _fail('Different native faces have duplicate complete boundary descriptions.')
    face_index = {key:index for index,key in enumerate(face_order)}
    positions = {use:[face_index[face],index,offset] for face in face_order
                 for index,loop in enumerate(face_data[face]['loops']) for offset,use in enumerate(loop_data[loop]['ordered'])}
    _close_census(r,body,census,counts,stamp,vertices,vertex_keys,edges,edge_keys,faces,face_keys,face_data,loop_data,coedges)
    return {'scope':ARC_BREP_SCOPE if finite_arcs else HOLE_BREP_SCOPE,'coordinate_frame':'part_model','length_unit':'m',
        'number_encoding':'ieee754_binary64_hex_exact','vertices':[list(_hex(points[key])) for key in vertex_order],
        'vertex_tolerances':[tolerances[key] for key in vertex_order],
        'edges':[{'kind':edge_data[key]['kind'],
            'start':vertex_index[edge_data[key]['start']] if edge_data[key]['start'] is not None else None,
            'end':vertex_index[edge_data[key]['end']] if edge_data[key]['end'] is not None else None,
            ('line_parameters' if edge_data[key]['kind']=='line' else 'circle_parameters'):list(_hex(edge_data[key]['parameters'])),
            'trimmed_curve':edge_data[key]['trim'],'native_tolerance':edge_data[key]['tolerance'],
            'coedges':sorted(positions[use] for use in edge_data[key]['uses'])} for key in edge_order],
        'faces':[{'surface_type':face_data[key]['kind'],'surface_parameters':list(_hex(face_data[key]['parameters'])),
            'normal_opposes_surface':face_data[key]['sense'],'loops':[{'outer':loop_data[loop]['outer'],
                'coedges':[{'edge':edge_index[coedges[use]['edge']],'same_direction_as_edge':coedges[use]['sense'],
                    'start':vertex_index[coedges[use]['start']] if coedges[use]['start'] is not None else None,
                    'end':vertex_index[coedges[use]['end']] if coedges[use]['end'] is not None else None,
                    'partner':positions[coedges[use]['partner']]} for use in loop_data[loop]['ordered']]}
                for loop in face_data[key]['loops']]} for key in face_order]}


def _validate_holes(r,faces,loops,coedges,edges):
    cylinders = [key for key,face in faces.items() if face['kind']=='cylinder']
    if not cylinders:
        _fail('This complete scope requires at least one inward cylindrical wall.','hole_brep_unsupported')
    accounted = set()
    for key in cylinders:
        wall = faces[key]
        origin,axis,radius = wall['parameters'][:3],wall['parameters'][3:6],wall['parameters'][6]
        uses = [loops[loop]['ordered'][0] for loop in wall['loops']]
        positions = sorted((_dot(_subtract(edges[coedges[use]['edge']]['parameters'][:3],origin),axis),use) for use in uses)
        if positions[1][0]-positions[0][0] <= r.limits.consistency_tolerance_m:
            _fail('The full cylinder must connect two distinct cap planes.')
        caps = set()
        for index,(position,use) in enumerate(positions):
            edge = edges[coedges[use]['edge']]
            circle = edge['parameters']
            delta = _subtract(circle[:3],origin)
            if (edge['kind'] != 'circle' or abs(circle[6]-radius) > r.limits.consistency_tolerance_m
                    or abs(abs(_dot(circle[3:6],axis))-1.) > 1e-12
                    or any(abs(value-position*direction) > r.limits.consistency_tolerance_m for value,direction in zip(delta,axis))):
                _fail('Both complete circle curves must bound this exact cylindrical surface.')
            partner_key = coedges[use]['partner']
            if partner_key not in coedges:
                _fail('A circular wall use lacks its exact cap partner.')
            partner = coedges[partner_key]
            cap = faces[partner['face']]
            if (cap['kind'] != 'plane' or loops[partner['loop']]['outer'] or partner['edge'] != coedges[use]['edge']):
                _fail('Each cylindrical boundary must connect to the same circle in a planar inner loop.')
            caps.add(partner['face'])
            normal = tuple(-value if cap['sense'] else value for value in cap['parameters'][:3])
            if not math.isclose(_dot(normal,axis),-1. if index==0 else 1.,rel_tol=0.,abs_tol=1e-12):
                _fail('Planar cap orientation disagrees with the two ends of the internal cylinder.')
            direction = 1. if partner['sense']==edge['trim']['same_direction_as_edge'] else -1.
            if not math.isclose(_dot(circle[3:6],normal)*direction,-1.,rel_tol=0.,abs_tol=1e-12):
                _fail('The cap inner-circle winding disagrees with its outward planar normal.')
            if coedges[use]['edge'] in accounted:
                _fail('Different cylindrical walls share the same complete circular boundary.')
            accounted.add(coedges[use]['edge'])
        if len(caps) != 2:
            _fail('A through hole must connect two distinct exact native planar faces.')
    if accounted != {key for key,edge in edges.items() if edge['kind']=='circle'}:
        _fail('The full circle census contains an unaccounted or unsupported curved boundary.')


def _validate_fans(incidence,edges,coedges):
    complete_graph = {}
    for edge in edges.values():
        a,b = (coedges[use]['face'] for use in edge['uses'])
        complete_graph.setdefault(a,set()).add(b)
        complete_graph.setdefault(b,set()).add(a)
    def connected(graph):
        visited,pending = set(),[next(iter(graph))]
        while pending:
            key = pending.pop()
            if key not in visited:
                visited.add(key)
                pending.extend(graph[key])
        return len(visited)==len(graph)
    if not complete_graph or not connected(complete_graph):
        _fail('The entire native face boundary must be connected.')
    for incident in incidence.values():
        graph = {}
        for key in incident:
            a,b = (coedges[use]['face'] for use in edges[key]['uses'])
            graph.setdefault(a,[]).append(b)
            graph.setdefault(b,[]).append(a)
        if not graph or any(len(row)!=2 for row in graph.values()) or not connected(graph):
            _fail('Each finite vertex requires one closed connected manifold face fan.')


def _close_census(r,body,census,counts,stamp,vertices,vertex_keys,edges,edge_keys,faces,face_keys,face_data,loops,coedges):
    r.check_body(body)
    edge_uses = {key:set() for key in edge_keys}
    for use,row in coedges.items():
        edge_uses[row['edge']].add(use)
    for edge,key in zip(edges,edge_keys):
        _,declared = r.array(edge,'GetCoEdges','ICoEdge',2)
        if set(declared) != edge_uses[key]:
            _fail('Native edge membership changed before closing.','hole_brep_changed_during_read')
    for face,key in zip(faces,face_keys):
        count = r.count(face,'GetLoopCount',r.limits.max_loops)
        _,declared = r.array(face,'GetLoops','ILoop2',count)
        if set(declared) != set(face_data[key]['loops']):
            _fail('Native face loop membership changed before closing.','hole_brep_changed_during_read')
    for row in loops.values():
        count = r.count(row['native'],'GetCoEdgeCount',r.limits.max_loop_coedges)
        _,declared = r.array(row['native'],'GetCoEdges','ICoEdge',count)
        if set(declared) != set(row['ordered']):
            _fail('Native loop coedge membership changed before closing.','hole_brep_changed_during_read')
    _,closing_vertices = r.array(body,'GetVertices','IVertex',counts[0])
    _,closing_edges = r.array(body,'GetEdges','IEdge',counts[1])
    _,closing_faces = r.array(body,'GetFaces','IFace2',counts[2])
    closing_stamp = r.call(body,'GetUpdateStamp')
    if (set(closing_vertices)!=set(vertex_keys) or set(closing_edges)!=set(edge_keys)
            or set(closing_faces)!=set(face_keys) or census()!=counts
            or type(closing_stamp) is not int or closing_stamp!=stamp):
        _fail('The exact native root census changed during collection.','hole_brep_changed_during_read')
