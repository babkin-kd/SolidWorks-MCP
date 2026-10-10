"""Native-shaped periodic topology tests; artificial, not CAD acceptance."""

from copy import deepcopy
import json
import math

import pytest

from solidworks_mcp.cad_cylinder_brep import CYLINDER_BREP_SCOPE, cylinder_body_snapshot
from solidworks_mcp.cad_planar_brep import PlanarBrepError
from test_planar_brep_v2 import Entity, Body, Face, Loop, Coedge


class Circle:
    def __init__(self, parameters): self.parameters = parameters
    def IsCircle(self): return True
    def IsLine(self): return False
    @property
    def CircleParams(self): return self.parameters


class Trim:
    CurveType = 3002
    Sense = True
    UMinValue = 0.
    UMaxValue = 2.*math.pi
    def __init__(self, point): self.StartPoint = self.EndPoint = point


class Edge(Entity):
    def __init__(self, body, circle, point):
        super().__init__()
        self.body, self.curve, self.trim = body, Circle(circle), Trim(point)
        self.coedges = []
    def GetBody(self): return self.body
    def GetCurve(self): return self.curve
    def GetCurveParams3(self): return self.trim
    def GetStartVertex(self): return None
    def GetEndVertex(self): return None
    def GetCoEdges(self): return tuple(self.coedges)
    def IsTolerant(self): return False, 0.


class Surface:
    def __init__(self, kind, params): self.kind, self.params = kind, params
    def IsPlane(self): return self.kind == 'plane'
    def IsCylinder(self): return self.kind == 'cylinder'
    @property
    def PlaneParams(self): return self.params
    @property
    def CylinderParams(self): return self.params


class PeriodicLoop(Loop):
    def GetVertices(self): return ()
    def GetVertexCount(self): return 0


def cylinder(*, origin=(0.,0.,0.), axis=(0.,0.,1.), radial=(1.,0.,0.), radius=.01, height=.03):
    body = Body()
    top = tuple(value+height*direction for value,direction in zip(origin,axis))
    ends = (origin,top)
    for index, centre in enumerate(ends):
        normal = axis if index == 0 else tuple(-v for v in axis)
        point = tuple(v+radius*d for v,d in zip(centre,radial))
        body.edges.append(Edge(body,centre+normal+(radius,),point))
    bottom, top_face, side = (Face(body,[]) for _ in range(3))
    bottom.surface = Surface('plane',tuple(-v for v in axis)+origin)
    top_face.surface = Surface('plane',axis+top)
    side.surface = Surface('cylinder',origin+axis+(radius,))
    body.faces = [bottom,top_face,side]
    for cap, edge in zip(body.faces[:2],body.edges):
        cap_loop, side_loop = PeriodicLoop(cap,True), PeriodicLoop(side,True)
        cap.loops.append(cap_loop)
        side.loops.append(side_loop)
        cap_loop.ordered = [Coedge(edge,cap_loop,False)]
        side_loop.ordered = [Coedge(edge,side_loop,True)]
    return body


def read(body):
    return cylinder_body_snapshot(body,identity=lambda entity:entity.ident)


def test_complete_native_periodic_surface_curves_and_census_preserved_exactly():
    body = cylinder()
    snapshot = read(body)
    assert snapshot['scope'] == CYLINDER_BREP_SCOPE and snapshot['vertices'] == []
    assert len(snapshot['edges']) == 2 and len(snapshot['faces']) == 3
    assert all(edge['start'] is edge['end'] is None for edge in snapshot['edges'])
    assert {face['surface_type'] for face in snapshot['faces']} == {'plane','cylinder'}
    assert sorted(len(face['loops']) for face in snapshot['faces']) == [1,1,2]
    assert all(float.fromhex(edge['trim']['interval'][1])-float.fromhex(edge['trim']['interval'][0])
               == 2.*math.pi for edge in snapshot['edges'])
    assert snapshot == read(body)
    assert json.loads(json.dumps(snapshot)) == snapshot


def test_canonical_census_independent_of_enumeration_order_and_loop_first_pointer():
    body = cylinder()
    expected = read(body)
    body.edges.reverse()
    body.faces.reverse()
    body.faces[0].loops.reverse()
    assert read(body) == expected


def test_rotated_translated_cylinder_retains_full_model_coordinates():
    body = cylinder(origin=(.2,-.1,.3),axis=(0.,1.,0.),radial=(0.,0.,1.))
    result = read(body)
    circles = [[float.fromhex(value) for value in edge['circle_parameters']] for edge in result['edges']]
    assert {tuple(row[:3]) for row in circles} == {(.2,-.1,.3),(.2,-.07,.3)}
    assert all(row[6] == .01 for row in circles)


def test_opposed_edge_curve_sense_retained_with_correct_coedge_winding():
    body = cylinder()
    for edge in body.edges:
        edge.trim.Sense = False
        edge.trim.UMinValue, edge.trim.UMaxValue = -2.*math.pi,0.
        for use in edge.coedges: use.sense = not use.sense
    result = read(body)
    assert all(edge['trim']['same_direction_as_edge'] is False for edge in result['edges'])
    assert all(edge['trim']['interval'][0] == (-2.*math.pi).hex() for edge in result['edges'])


@pytest.mark.parametrize('fault',['half_circle','open_trim','radius','axis','foreign_edge_body',
    'wrong_cap_plane','inward_cap','inner_cylinder','missing_coedge','wrong_partner','wrong_next',
    'sewing','singular','foreign_loop','vertices','count','bad_curve_type','duplicate_face'])
def test_incomplete_or_foreign_boundary_never_yields_partial_snapshot(fault):
    body = cylinder()
    edge, cap, side = body.edges[0], body.faces[0], body.faces[2]
    if fault == 'half_circle': edge.trim.UMaxValue = math.pi
    if fault == 'open_trim': edge.trim.EndPoint = (.01,.001,0.)
    if fault == 'radius': edge.curve.parameters = edge.curve.parameters[:-1]+(.011,)
    if fault == 'axis': edge.curve.parameters = edge.curve.parameters[:3]+(0.,1.,0.,.01)
    if fault == 'foreign_edge_body': edge.body = Body()
    if fault == 'wrong_cap_plane': cap.surface.params = (0.,0.,-1.,0.,0.,.001)
    if fault == 'inward_cap': cap.sense = True
    if fault == 'inner_cylinder': side.sense = True
    if fault == 'missing_coedge': edge.coedges.pop()
    if fault == 'wrong_partner': edge.coedges[0].GetPartner = lambda:body.edges[1].coedges[0]
    if fault == 'wrong_next': edge.coedges[0].GetNext = lambda:body.edges[1].coedges[0]
    if fault == 'sewing': edge.coedges[0].GetCurve = lambda:object()
    if fault == 'singular': cap.loops[0].IsSingular = lambda:True
    if fault == 'foreign_loop': cap.loops[0].face = side
    if fault == 'vertices': body.vertices.append(Entity())
    if fault == 'count': body.GetEdgeCount = lambda:1
    if fault == 'bad_curve_type': edge.trim.CurveType = True
    if fault == 'duplicate_face': body.faces[1] = body.faces[0]
    with pytest.raises(PlanarBrepError): read(body)


def test_identical_face_replacement_at_closing_census_is_rejected():
    body = cylinder()
    original = body.GetFaces
    reads = 0
    def late():
        nonlocal reads
        reads += 1
        if reads == 2:
            old = body.faces[0]
            replacement = deepcopy(old)
            replacement.ident += 100000
            body.faces[0] = replacement
        return original()
    body.GetFaces = late
    with pytest.raises(PlanarBrepError) as error: read(body)
    assert error.value.code == 'cylindrical_brep_changed_during_read'
