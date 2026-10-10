"""Artificial strong-reference native reader scenarios; no CAD acceptance."""

from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_sheet_flat import CadSheetFlatReadMixin
from solidworks_mcp.jobs import ExecutionFailure


class Entity:
    def __init__(self,token):self.token=[token]


class Vertex(Entity):
    def __init__(self,token,point):super().__init__(token);self.point=point
    def GetPoint(self):return self.point


class Edge(Entity):
    def __init__(self,token,a,b):super().__init__(token);self.a,self.b=a,b
    def GetStartVertex(self):return self.a
    def GetEndVertex(self):return self.b


class Adapter(CadSheetFlatReadMixin):
    def identity(self,obj):return obj.token
    def body_is_current(self,model,body):return body is self.body and self.current
    def topology_is_current(self,body,face,kind):return self.face_current and face is self.face and kind=='face'
    def persistent_id(self,model,obj):return self.pid
    def resolve_persistent_id(self,model,pid,kind):assert kind=='face';return self.resolved
    def same_persistent_id(self,model,left,right):return self.pid_same and left==right


def setup(monkeypatch):
    monkeypatch.setattr('solidworks_mcp.cad_sheet_flat.binding.wrap',lambda raw,cls:raw)
    a=Adapter();a._module=NS(**{k:k for k in ('IFeature','IFlatPatternFeatureData','IFace2','IBody2','ISurface','IEdge','IVertex')})
    a.current=a.face_current=a.pid_same=True;a.pid=b'strong_fixed_face'
    a.flat=Entity('flat');a.flat.GetTypeName2=lambda:'FlatPattern'
    a.body=Entity('body');a.body.GetType=lambda:0;a.body.IsSheetMetal=lambda:True
    a.body.GetFeatures=lambda:[Entity('sheet'),Entity('base'),a.flat]
    a.face=Entity('face');a.resolved=a.face;a.face.GetBody=lambda:a.body
    a.surface=NS(IsPlane=lambda:True,PlaneParams=(0.,1.,0.,0.,.002,.03));a.face.GetSurface=lambda:a.surface
    a.face.FaceInSurfaceSense=lambda:False
    corners=[(.004,.002,0.),(.040,.002,0.),(.040,.002,.030),(.004,.002,.030)]
    a.vertices=[Vertex(i,point) for i,point in enumerate(corners)]
    a.edges=[Edge('edge'+str(i),a.vertices[i],a.vertices[(i+1)%4]) for i in range(4)];a.face.GetEdges=lambda:a.edges
    a.data=NS(FixedFace2=a.face,MergeFace=True,SimplifyBends=True,ShowSlitInCornerRelief=True)
    def no_ui(*args):pytest.fail('Read-only fixed-face preparation cannot change selections/rollback/suppression.')
    a.data.AccessSelections=a.data.IAccessSelections2=no_ui;a.flat.SetSuppression2=no_ui
    a.flat.GetDefinition=lambda:a.data
    return a


def test_only_exact_current_strongly_referenced_native_fixed_face_can_supply_corners(monkeypatch):
    a=setup(monkeypatch);proof=a.sheet_flat_fixed_face(object(),a.flat,a.body)
    assert proof['face']['pid_hex']==a.pid.hex() and proof['face']['owner_body_is_current'] is True
    assert proof['face']['vertices']==[list(v.point) for v in sorted(a.vertices,key=lambda v:v.point)]
    assert proof['options']==dict(MergeFace=True,SimplifyBends=True,ShowSlitInCornerRelief=True)


@pytest.mark.parametrize('fault',['not_current_body','not_sheet','not_solid','ambiguous_body_type','wrong_flat','foreign_flat','missing_definition','missing_face','missing_pid','wrong_resolved','wrong_owner','not_current_face','wrong_pid','cylinder','missing_edge','duplicate_edge','missing_vertex','same_point','nonfinite','unknown_sense','invalid_plane','unknown_option'])
def test_unproved_reference_membership_or_boundary_is_rejected_without_ui_writes(monkeypatch,fault):
    a=setup(monkeypatch)
    if fault=='not_current_body':a.current=False
    elif fault=='not_sheet':a.body.IsSheetMetal=lambda:False
    elif fault=='not_solid':a.body.GetType=lambda:1
    elif fault=='ambiguous_body_type':a.body.GetType=lambda:False
    elif fault=='wrong_flat':a.flat.GetTypeName2=lambda:'Boss'
    elif fault=='foreign_flat':a.body.GetFeatures=lambda:[Entity('foreign')]
    elif fault=='missing_definition':a.flat.GetDefinition=lambda:None
    elif fault=='missing_face':a.data.FixedFace2=None
    elif fault=='missing_pid':a.pid=b''
    elif fault=='wrong_resolved':a.resolved=Entity('wrong face')
    elif fault=='wrong_owner':a.face.GetBody=lambda:Entity('another body')
    elif fault=='not_current_face':a.face_current=False
    elif fault=='wrong_pid':a.pid_same=False
    elif fault=='cylinder':a.surface.IsPlane=lambda:False
    elif fault=='missing_edge':a.edges.pop()
    elif fault=='duplicate_edge':a.edges[0]=a.edges[1]
    elif fault=='missing_vertex':a.edges[0].a=None
    elif fault=='same_point':a.vertices[0].point=a.vertices[1].point
    elif fault=='nonfinite':a.vertices[0].point=(float('nan'),.002,0.)
    elif fault=='unknown_sense':a.face.FaceInSurfaceSense=lambda:None
    elif fault=='invalid_plane':a.surface.PlaneParams=(0.,1.,0.)
    elif fault=='unknown_option':a.data.MergeFace=1
    with pytest.raises(ExecutionFailure):a.sheet_flat_fixed_face(object(),a.flat,a.body)
