"""Independent finite arc native-shaped topology; these are not CAD acceptance."""

import math
import random

import pytest

from solidworks_mcp.cad_arc_brep import ARC_BREP_SCOPE, finite_arc_body_snapshot
from solidworks_mcp.cad_analytical_brep import analytical_body_snapshot
from solidworks_mcp.cad_planar_brep import PlanarBrepError
from test_planar_brep_v2 import make_body
from test_cylinder_brep_v2 import Surface


class Arc:
    def __init__(self, centre, radius):
        self.centre, self.radius = centre, radius
    def IsLine(self): return False
    def IsCircle(self): return True
    @property
    def CircleParams(self): return self.centre+(0.,0.,1.,self.radius)
    def Evaluate2(self, parameter, derivatives):
        assert derivatives==1
        r=self.radius
        return (self.centre[0]+r*math.cos(parameter),self.centre[1]+r*math.sin(parameter),self.centre[2],
            -r*math.sin(parameter),r*math.cos(parameter),0.)
    def GetLength3(self, start, end): return self.radius*(end-start)


class Trim:
    CurveType=3002
    Sense=True
    UMinValue=math.pi
    UMaxValue=1.5*math.pi
    def __init__(self, edge): self.edge=edge
    @property
    def StartPoint(self): return self.edge.start.point
    @property
    def EndPoint(self): return self.edge.end.point


def rounded_body(width=.04,height=.02,depth=.01,radius=.002):
    # Counterclockwise physical cross-section, with a concave-in-rectangle
    # quarter-circle boundary replacing the lower-left corner.
    profile=[(radius,0.),(width,0.),(width,height),(0.,height),(0.,radius)]
    points=[(x,y,z) for z in (0.,depth) for x,y in profile]
    polygons=[list(reversed(range(5))),list(range(5,10))]
    polygons.extend([[i,(i+1)%5,(i+1)%5+5,i+5] for i in range(5)])
    body=make_body(points,polygons)
    for face in body.faces:
        face.surface=Surface('plane',face.surface.params)
    body.faces[-1].surface=Surface('cylinder',(radius,radius,0.,0.,0.,1.,radius))
    for edge in body.edges:
        if {edge.start.point[:2],edge.end.point[:2]}=={(0.,radius),(radius,0.)}:
            # Canonical native parameter direction independent of face traversal.
            if edge.start.point[0]!=0.: edge.start,edge.end=edge.end,edge.start
            edge.curve=Arc((radius,radius,edge.start.point[2]),radius)
            edge.parameter_data=Trim(edge)
        else:
            edge.curve.IsCircle=lambda: False
    # make_body's old coedge senses reflected its original edge orientation.
    for face,polygon in zip(body.faces,polygons):
        for use,start in zip(face.loops[0].ordered,polygon):
            use.sense=use.edge.start is body.vertices[start]
    return body


def read(body): return finite_arc_body_snapshot(body,identity=lambda obj:[obj.ident])


def transform_body(body,rotation,translation):
    """Rigid proper transform of independent native-shaped geometry."""
    def vector(p):return tuple(math.fsum(p[j]*rotation[j][i] for j in range(3)) for i in range(3))
    def point(p):return tuple(v+t for v,t in zip(vector(p),translation))
    class TransformedArc:
        def __init__(self,original):self.original=original
        def IsLine(self):return False
        def IsCircle(self):return True
        @property
        def CircleParams(self):
            p=self.original.CircleParams
            return point(p[:3])+vector(p[3:6])+(p[6],)
        def Evaluate2(self,u,d):
            p=self.original.Evaluate2(u,d)
            return point(p[:3])+vector(p[3:6])
        def GetLength3(self,a,b):return self.original.GetLength3(a,b)
    for vertex in body.vertices:vertex.point=point(vertex.point)
    for edge in body.edges:
        if isinstance(edge.curve,Arc):edge.curve=TransformedArc(edge.curve)
    for face in body.faces:
        p=face.surface.params
        face.surface.params=(vector(p[:3])+point(p[3:6]) if face.surface.kind=='plane'
            else point(p[:3])+vector(p[3:6])+(p[6],))
    return body


def test_complete_rounded_body_not_a_chord_polygon_or_mass_signature():
    body=rounded_body()
    result=read(body)
    assert result['scope']==ARC_BREP_SCOPE
    assert (len(result['vertices']),len(result['edges']),len(result['faces']))==(10,15,7)
    arcs=[edge for edge in result['edges'] if edge['kind']=='arc']
    assert len(arcs)==2
    assert all(len(edge['coedges'])==2 for edge in result['edges'])
    assert all(len(edge['trimmed_curve']['evaluations_si'])==2 for edge in arcs)
    assert analytical_body_snapshot(body,identity=lambda obj:[obj.ident])==result
    assert read(rounded_body(radius=.003))!=result


def test_root_enumeration_and_cycle_start_do_not_change_complete_snapshot():
    body=rounded_body(); before=read(body)
    rng=random.Random(71)
    for array in (body.vertices,body.edges,body.faces): rng.shuffle(array)
    for face in body.faces:
        face.loops[0].shift=3
        face.loops[0].reverse_array=True
    assert read(body)==before


@pytest.mark.parametrize('mutation',[
    lambda body: setattr(next(e for e in body.edges if isinstance(e.curve,Arc)).parameter_data,'UMaxValue',2.*math.pi),
    lambda body: setattr(next(e for e in body.edges if isinstance(e.curve,Arc)).parameter_data,'Sense',False),
    lambda body: setattr(next(e for e in body.edges if isinstance(e.curve,Arc)).curve,'GetLength3',lambda a,b:1.),
    lambda body: setattr(next(e for e in body.edges if isinstance(e.curve,Arc)).curve,'Evaluate2',lambda u,d:(0.,)*6),
    lambda body: setattr(next(e for e in body.edges if isinstance(e.curve,Arc)).curve,'radius',.003),
    lambda body: setattr(body.faces[-1],'sense',True),
    lambda body: setattr(body.faces[-1].surface,'params',(.003,.002,0.,0.,0.,1.,.002)),
    lambda body: setattr(body.edges[0],'GetCoEdges',lambda:()),
    lambda body: setattr(body.edges[0].coedges[0],'GetCurve',lambda:object()),
    lambda body: setattr(body.faces[0],'body',rounded_body()),
    lambda body: setattr(body.vertices[0],'GetEdges',lambda:()),
])
def test_incomplete_or_inconsistent_native_arc_and_manifold_evidence_rejected(mutation):
    body=rounded_body(); mutation(body)
    with pytest.raises(PlanarBrepError): read(body)


def test_complete_quarter_arc_evidence_retains_native_parameter_phase():
    body=rounded_body()
    before=read(body)
    arc=next(e for e in body.edges if isinstance(e.curve,Arc))
    arc.parameter_data.UMinValue+=2.*math.pi
    arc.parameter_data.UMaxValue+=2.*math.pi
    assert read(body)!=before

