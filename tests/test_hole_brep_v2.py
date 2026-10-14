"""Artificial complete native-shaped boundaries; no CAD acceptance claim."""

from copy import deepcopy
import json
import math
import random

import pytest

from solidworks_mcp.cad_hole_brep import HOLE_BREP_SCOPE, hole_body_snapshot
from solidworks_mcp.cad_planar_brep import PlanarBrepError, PlanarBrepLimits
from test_planar_brep_v2 import Body, Face, Coedge, make_body
from test_cylinder_brep_v2 import Edge, Surface, PeriodicLoop


def plate(holes=((.5,.5,.1),)):
    body = make_body()
    for edge in body.edges:
        edge.curve.IsCircle = lambda:False
    for face in body.faces:
        face.surface.IsCylinder = lambda:False
    for x,y,radius in holes:
        wall = Face(body, ())
        wall.surface = Surface('cylinder',(x,y,-.2,0.,0.,1.,radius))
        wall.sense = True
        body.faces.append(wall)
        for z, cap in zip((0.,1.),body.faces[:2]):
            normal = (0.,0.,-1.) if z == 0. else (0.,0.,1.)
            edge = Edge(body,(x,y,z)+normal+(radius,),(x+radius,y,z))
            body.edges.append(edge)
            inner, outer = PeriodicLoop(cap,False), PeriodicLoop(wall,True)
            cap.loops.append(inner)
            wall.loops.append(outer)
            inner.ordered = [Coedge(edge,inner,False)]
            outer.ordered = [Coedge(edge,outer,True)]
    return body


def read(body, **kwargs):
    return hole_body_snapshot(body,identity=lambda obj:[obj.ident],**kwargs)


def circles(body):
    return [edge for edge in body.edges if edge.curve.IsCircle()]


def test_complete_native_boundary_preserves_full_circles_and_internal_wall():
    body = plate()
    result = read(body)
    assert result['scope'] == HOLE_BREP_SCOPE
    assert len(result['vertices']) == 8
    assert len(result['edges']) == 14
    assert len(result['faces']) == 7
    assert [edge['kind'] for edge in result['edges']].count('circle') == 2
    wall = next(face for face in result['faces'] if face['surface_type']=='cylinder')
    assert wall['normal_opposes_surface'] is True
    assert len(wall['loops']) == 2 and all(loop['outer'] for loop in wall['loops'])
    assert sum(not loop['outer'] for face in result['faces'] for loop in face['loops']) == 2
    for edge in result['edges']:
        assert len(edge['coedges']) == 2
        if edge['kind'] == 'circle':
            assert edge['start'] is edge['end'] is None
            trim = edge['trimmed_curve']
            assert float.fromhex(trim['u_max'])-float.fromhex(trim['u_min']) == 2.*math.pi
    assert json.loads(json.dumps(result)) == result == read(body)


def test_every_coedge_partner_maps_back_to_the_same_complete_edge():
    result = read(plate())
    for face in result['faces']:
        for loop in face['loops']:
            for use in loop['coedges']:
                f,l,c = use['partner']
                partner = result['faces'][f]['loops'][l]['coedges'][c]
                assert partner['edge'] == use['edge']
                assert partner['same_direction_as_edge'] is not use['same_direction_as_edge']


@pytest.mark.parametrize('seed',range(8))
def test_canonical_enumeration_and_first_pointers_do_not_change_revision(seed):
    body = plate(((.25,.5,.08),(.75,.5,.1)))
    expected = read(body)
    rng = random.Random(seed)
    for array in (body.vertices,body.edges,body.faces):
        rng.shuffle(array)
    for face in body.faces:
        rng.shuffle(face.loops)
        for loop in face.loops:
            loop.shift = rng.randrange(len(loop.ordered))
            loop.reverse_array = True
    assert read(body) == expected


def test_multiple_holes_have_complete_separate_walls_and_inner_loops():
    result = read(plate(((.25,.5,.08),(.75,.5,.1))))
    assert len(result['vertices']) == 8
    assert len(result['edges']) == 16
    assert len(result['faces']) == 8
    assert sum(face['surface_type']=='cylinder' for face in result['faces']) == 2
    assert sum(not loop['outer'] for face in result['faces'] for loop in face['loops']) == 4


def test_rotated_translated_boundary_retains_exact_native_model_coordinates():
    body = plate()
    rotate = lambda p:(-p[1],p[2],-p[0])  # proper rigid rotation
    transform = lambda p:tuple(v+t for v,t in zip(rotate(p),(.2,-.3,.4)))
    for vertex in body.vertices:
        vertex.point = transform(vertex.point)
    for face in body.faces:
        p = face.surface.params
        face.surface.params = ((rotate(p[:3])+transform(p[3:])) if face.surface.IsPlane()
                               else transform(p[:3])+rotate(p[3:6])+(p[6],))
    for edge in circles(body):
        p = edge.curve.parameters
        edge.curve.parameters = transform(p[:3])+rotate(p[3:6])+(p[6],)
        edge.trim.StartPoint, edge.trim.EndPoint = transform(edge.trim.StartPoint),transform(edge.trim.EndPoint)
    result = read(body)
    centres = {tuple(float.fromhex(x) for x in edge['circle_parameters'][:3])
               for edge in result['edges'] if edge['kind']=='circle'}
    assert centres == {transform((.5,.5,0.)),transform((.5,.5,1.))}


def test_opposed_circle_curve_sense_and_negative_complete_period_are_supported():
    body = plate()
    for edge in circles(body):
        edge.trim.Sense = False
        edge.trim.UMinValue,edge.trim.UMaxValue = -2.*math.pi,0.
        for use in edge.coedges:
            use.sense = not use.sense
    result = read(body)
    for edge in result['edges']:
        if edge['kind']=='circle':
            assert edge['trimmed_curve']['same_direction_as_edge'] is False
            assert edge['trimmed_curve']['u_min'] == (-2.*math.pi).hex()


def test_native_null_vertex_array_is_only_accepted_for_exact_zero_count():
    body = plate()
    for face in body.faces:
        for loop in face.loops:
            if isinstance(loop,PeriodicLoop):
                loop.GetVertices = lambda:None
    assert read(body)['scope'] == HOLE_BREP_SCOPE
    body.faces[0].loops[0].GetVertices = lambda:None
    with pytest.raises(PlanarBrepError): read(body)


@pytest.mark.parametrize('fault',[
    'half_circle','open_trim','zero_radius','radius_mismatch','circle_axis','wall_axis',
    'outward_wall','inward_cap','cap_circle_outer','wall_circle_inner','foreign_edge',
    'foreign_face','foreign_loop','missing_edge','missing_circle_use','wrong_partner',
    'same_sense','wrong_next','sewing','singular','mesh','not_solid','bad_count',
    'ambiguous_curve','ambiguous_surface','non_unit_plane','duplicate_face',
    'bad_trim_kind','bad_sense','nonfinite_radius','excessive_gap','tolerant',
    'bad_vertex_count','extra_vertex','duplicate_vertex','unaccounted_circle',
    'cap_off_plane','wall_radius_mismatch','wall_wrong_origin','cap_vertex_array',
    'missing_loop','repeated_loop','vertex_incidence','edge_body_changes',
    'line_trim_endpoint','line_trim_period','line_trim_type','line_curve',
    'face_edge_census','loop_edge_census','circle_has_vertex','bad_native_tolerance',
])
def test_incomplete_or_unsupported_boundary_never_returns_partial_revision(fault):
    body = plate()
    circle = circles(body)[0]
    wall,cap = body.faces[-1],body.faces[0]
    inner = cap.loops[-1]
    finite = body.edges[0]
    if fault=='half_circle': circle.trim.UMaxValue = math.pi
    if fault=='open_trim': circle.trim.EndPoint = (.6,.51,0.)
    if fault=='zero_radius': circle.curve.parameters = (.5,.5,0.,0.,0.,-1.,0.)
    if fault=='radius_mismatch': circle.curve.parameters = (.5,.5,0.,0.,0.,-1.,.11)
    if fault=='circle_axis': circle.curve.parameters = (.5,.5,0.,0.,1.,0.,.1)
    if fault=='wall_axis': wall.surface.params = (.5,.5,-.2,0.,1.,0.,.1)
    if fault=='outward_wall': wall.sense = False
    if fault=='inward_cap': cap.sense = True
    if fault=='cap_circle_outer': inner.outer = True
    if fault=='wall_circle_inner': wall.loops[0].outer = False
    if fault=='foreign_edge': circle.body = Body()
    if fault=='foreign_face': cap.body = Body()
    if fault=='foreign_loop': inner.face = wall
    if fault=='missing_edge': body.edges.remove(circle)
    if fault=='missing_circle_use': circle.coedges.pop()
    if fault=='wrong_partner': circle.coedges[0].GetPartner = lambda:finite.coedges[0]
    if fault=='same_sense': circle.coedges[0].sense = True
    if fault=='wrong_next': inner.ordered[0].GetNext = lambda:finite.coedges[0]
    if fault=='sewing': circle.coedges[0].GetCurve = lambda:circle.curve
    if fault=='singular': inner.IsSingular = lambda:True
    if fault=='mesh': body.IsMeshBody = lambda:True
    if fault=='not_solid': body.GetType = lambda:2
    if fault=='bad_count': body.GetEdgeCount = lambda:True
    if fault=='ambiguous_curve': circle.curve.IsLine = lambda:True
    if fault=='ambiguous_surface': wall.surface.IsPlane = lambda:True
    if fault=='non_unit_plane': cap.surface.params = (0.,0.,-2.,0.,0.,0.)
    if fault=='duplicate_face': body.faces.append(cap)
    if fault=='bad_trim_kind': circle.trim.CurveType = True
    if fault=='bad_sense': circle.trim.Sense = 1
    if fault=='nonfinite_radius': circle.curve.parameters = (.5,.5,0.,0.,0.,-1.,math.nan)
    if fault=='excessive_gap': circle.IsTolerant = lambda:(False,1e-8)
    if fault=='tolerant': circle.IsTolerant = lambda:(True,0.)
    if fault=='bad_vertex_count': inner.GetVertexCount = lambda:1
    if fault=='extra_vertex': inner.GetVertices = lambda:(body.vertices[0],)
    if fault=='duplicate_vertex': body.vertices.append(body.vertices[0])
    if fault=='unaccounted_circle': body.faces.remove(wall)
    if fault=='cap_off_plane': cap.surface.params = (0.,0.,-1.,0.,0.,.001)
    if fault=='wall_radius_mismatch': wall.surface.params = (.5,.5,-.2,0.,0.,1.,.11)
    if fault=='wall_wrong_origin': wall.surface.params = (.6,.5,-.2,0.,0.,1.,.1)
    if fault=='cap_vertex_array': cap.loops[0].GetVertices = lambda:(body.vertices[0],)*4
    if fault=='missing_loop': cap.loops.pop()
    if fault=='repeated_loop': cap.loops.append(inner)
    if fault=='vertex_incidence': body.vertices[0].edges.pop()
    if fault=='edge_body_changes': finite.GetBody = lambda:Body()
    if fault=='line_trim_endpoint':
        original = finite.parameter_data
        finite.parameter_data = type('BadTrim',(),{
            'CurveType':3001,'Sense':True,'UMinValue':0.,'UMaxValue':1.,
            'StartPoint':(99.,99.,99.),'EndPoint':original.EndPoint})()
    if fault=='line_trim_period': finite.parameter_data.UMaxValue = -1.
    if fault=='line_trim_type': finite.parameter_data.CurveType = 3002
    if fault=='line_curve': finite.curve.IsLine = lambda:False
    if fault=='face_edge_census': cap.GetEdges = lambda:()
    if fault=='loop_edge_census': inner.GetEdges = lambda:()
    if fault=='circle_has_vertex': circle.GetStartVertex = lambda:body.vertices[0]
    if fault=='bad_native_tolerance': circle.IsTolerant = lambda:(False,-1.)
    with pytest.raises(PlanarBrepError): read(body)


@pytest.mark.parametrize('holes',[
    ((-.1,.5,.05),), ((.1,.5,.1),), ((.9,.5,.11),),
    ((.4,.5,.15),(.6,.5,.15)), ((.5,.5,.2),(.5,.5,.1)),
    ((.3,.5,.2),(.7,.5,.2)),
])
def test_circle_outside_touching_intersecting_or_nested_is_rejected(holes):
    with pytest.raises(PlanarBrepError): read(plate(holes))


@pytest.mark.parametrize('getter,array',[
    ('GetVertices','vertices'),('GetEdges','edges'),('GetFaces','faces')])
def test_native_root_replacement_without_stamp_change_is_rejected(getter,array):
    body = plate()
    original = getattr(body,getter)
    calls = 0
    def late():
        nonlocal calls
        calls += 1
        if calls==2:
            items = getattr(body,array)
            replacement = deepcopy(items[0])
            replacement.ident += 100000
            items[0] = replacement
        return original()
    setattr(body,getter,late)
    with pytest.raises(PlanarBrepError) as error: read(body)
    assert error.value.code == 'hole_brep_changed_during_read'


@pytest.mark.parametrize('entity,getter,attribute',[
    ('face','GetLoops','loops'),('loop','GetCoEdges','ordered'),('edge','GetCoEdges','coedges')])
def test_native_interior_membership_replacement_at_closing_is_rejected(entity,getter,attribute):
    body = plate()
    target = {'face':body.faces[0], 'loop':body.faces[0].loops[-1], 'edge':circles(body)[0]}[entity]
    original = getattr(target,getter)
    calls = 0
    def late():
        nonlocal calls
        calls += 1
        if calls==2:
            items = getattr(target,attribute)
            replacement = deepcopy(items[0])
            replacement.ident += 100000
            items[0] = replacement
        return original()
    setattr(target,getter,late)
    with pytest.raises(PlanarBrepError) as error: read(body)
    assert error.value.code == 'hole_brep_changed_during_read'


def test_native_fault_check_is_repeated_at_closing():
    body = plate()
    class CheckedBody(Body):
        @property
        def Check3(self):
            self.check_reads += 1
            return None if self.check_reads==1 else type('Fault',(),{'Count':1})()
    body.__class__ = CheckedBody
    body.check_reads = 0
    with pytest.raises(PlanarBrepError): read(body)
    assert body.check_reads==2


@pytest.mark.parametrize('limits',[
    PlanarBrepLimits(max_vertices=7), PlanarBrepLimits(max_edges=13),
    PlanarBrepLimits(max_faces=6), PlanarBrepLimits(max_loops=9),
    PlanarBrepLimits(max_coedges=27), PlanarBrepLimits(max_loop_coedges=3),
    PlanarBrepLimits(max_polygon_comparisons=19),
])
def test_complete_body_and_polygon_work_is_bounded(limits):
    with pytest.raises(PlanarBrepError) as error: read(plate(),limits=limits)
    assert error.value.code.endswith('budget_exceeded')


def test_small_native_change_is_retained_without_rounding_or_tolerance_snapping():
    body = plate()
    baseline = read(body)
    edge = circles(body)[0]
    edge.trim.UMinValue = math.nextafter(0.,1.)
    changed = read(body)
    assert changed != baseline
    assert next(e for e in changed['edges'] if e['kind']=='circle')['trimmed_curve']['u_min'] == edge.trim.UMinValue.hex()


@pytest.mark.parametrize('stamp',[True,1.,'1',None,2])
def test_closing_update_stamp_must_be_exact_current_native_integer(stamp):
    body = plate()
    observations = iter((1,stamp))
    body.GetUpdateStamp = lambda:next(observations)
    with pytest.raises(PlanarBrepError) as error: read(body)
    assert error.value.code=='hole_brep_changed_during_read'


def test_individually_valid_disconnected_solid_shells_are_rejected():
    body,second = plate(),plate()
    for vertex in second.vertices:
        vertex.point = (vertex.point[0]+10.,*vertex.point[1:])
    for face in second.faces:
        face.body = body
        p = face.surface.params
        face.surface.params = ((p[:3]+(p[3]+10.,*p[4:])) if face.surface.IsPlane()
                               else (p[0]+10.,*p[1:]))
    for edge in second.edges:
        edge.body = body
    for edge in circles(second):
        p = edge.curve.parameters
        edge.curve.parameters = (p[0]+10.,*p[1:])
        edge.trim.StartPoint = (edge.trim.StartPoint[0]+10.,*edge.trim.StartPoint[1:])
        edge.trim.EndPoint = (edge.trim.EndPoint[0]+10.,*edge.trim.EndPoint[1:])
    body.vertices.extend(second.vertices)
    body.edges.extend(second.edges)
    body.faces.extend(second.faces)
    with pytest.raises(PlanarBrepError) as error: read(body)
    assert 'connected' in str(error.value)


def test_exact_native_gap_is_retained_and_is_not_used_as_a_geometry_tolerance():
    body = plate()
    baseline = read(body)
    edge = circles(body)[0]
    edge.IsTolerant = lambda:(False,1e-9)
    current = read(body)
    assert current!=baseline
    row = next(row for row in current['edges'] if row['kind']=='circle')
    assert row['native_tolerance']['gap_m']==(1e-9).hex()
    # A gap within the exact native class does not allow moving the wall.
    body.faces[-1].surface.params = (.5+5e-10,.5,-.2,0.,0.,1.,.1)
    with pytest.raises(PlanarBrepError): read(body)
