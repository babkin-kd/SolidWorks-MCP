"""Native-shaped full-circle captures; artificial, not SolidWorks acceptance."""

from copy import deepcopy
import json
import math
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.circular_sketch import CircularSketchReader, SCOPE
from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.linear_sketch import LinearSketchReader, SketchEntityBinder
from test_linear_sketch_v2 import Point, Relation, Sketch


class Circle:
    ConstructionGeometry,Status = False,2
    def __init__(self,owner,number,centre,radius=.003):
        self.owner,self.number,self.centre,self.radius = owner,number,centre,radius
        self.start = self.end = None
        self.normal,self.rotation = (0.,0.,1.),1
    def GetType(self): return 1
    def GetID(self): return (self.number,self.number+1)
    def GetSketch(self): return self.owner
    def IsCircle(self): return 1
    def GetRadius(self): return self.radius
    def GetCenterPoint2(self): return self.centre
    def GetStartPoint2(self): return self.start
    def GetEndPoint2(self): return self.end
    def GetNormalVector(self): return self.normal
    def GetRotationDir(self): return self.rotation
    def GetCurve(self):
        return NS(IsCircle=lambda:True,IsLine=lambda:False,
            CircleParams=(self.centre.X,self.centre.Y,self.centre.Z,*self.normal,self.radius))


class CircleSketch(Sketch):
    def __init__(self):
        self.points = [Point(self,0,(.01,.01,0.))]
        self.origin = Point(object(),0,(0.,0.,0.),kind=1)
        self.projected = Point(self,1,(0.,0.,0.),kind=10)
        self.lines = [Circle(self,0,self.points[0])]
        self.dimensions = [NS(FullName=name+'@Эскиз отверстия') for name in ('Центр X','Центр Y','Диаметр')]
        self.relations = []
        for index,display_type in enumerate((11,12,6)):
            display = NS(Type2=display_type,GetDimension2=lambda slot,i=index:self.dimensions[i])
            if index<2:
                types,entities,definitions = [2,2],[self.points[0],self.projected],[self.points[0],self.origin]
            else:
                types,entities,definitions = [4],[self.lines[0]],[self.lines[0]]
            self.relations.append(Relation(15 if index==2 else 1,types,entities,definitions,display))
        self.RelationManager = NS(GetRelationsCount=lambda kind:len(self.relations),GetRelations=lambda kind:self.relations)


def capture(sketch):
    return CircularSketchReader(sketch,sketch.origin,wrap=lambda raw,name:raw,identity=id).read()


def test_full_circle_has_exact_radius_curve_normal_and_complete_dimension_definitions():
    sketch = CircleSketch()
    result,members = capture(sketch)
    assert result['scope']==SCOPE and len(result['segments'])==1
    circle = result['segments'][0]
    assert circle['kind']=='circle' and circle['centre']=='point:0:1'
    assert circle['start'] is circle['end'] is None
    assert circle['radius_si']==(.003).hex() and circle['rotation_direction']==1
    assert circle['normal_si']==[v.hex() for v in (0.,0.,1.)]
    assert circle['circle_parameters_si']==[v.hex() for v in (.01,.01,0.,0.,0.,1.,.003)]
    assert {row['display_type'] for row in result['relations']}=={11,12,6}
    diameter = next(row for row in result['relations'] if row['display_type']==6)
    assert diameter['entities']==diameter['definitions']==['circle:0:1']
    assert diameter['dimension_full_name']=='Диаметр@Эскиз отверстия'
    assert dict(members)['circle:0:1']==id(sketch.lines[0])
    assert json.loads(json.dumps(result))==result==capture(sketch)[0]


def test_full_circle_with_complete_native_coincident_seam_points_is_retained():
    sketch = CircleSketch()
    seam = Point(sketch,2,(.013,.01,0.))
    sketch.points.append(seam)
    sketch.lines[0].start = sketch.lines[0].end = seam
    row = capture(sketch)[0]['segments'][0]
    assert row['start']==row['end']=='point:2:3'


def test_native_periodic_handle_is_retained_without_inventing_an_enumerated_point():
    sketch = CircleSketch()
    handle = Point(sketch,2,(.013,.01,0.),kind=-1)
    handle.Status = 1
    sketch.lines[0].start = sketch.lines[0].end = handle
    snapshot,members = capture(sketch)
    circle = snapshot['segments'][0]
    assert circle['start'] is circle['end'] is None
    assert circle['periodic_endpoints'][0]==circle['periodic_endpoints'][1]
    assert circle['periodic_endpoints'][0]['point_type']==-1
    assert len(snapshot['points'])==2
    assert dict(members)['circle:0:1:periodic_endpoint']==id(handle)


@pytest.mark.parametrize('fault',['alias','mixed','foreign','off_circle','off_plane','enumerated','status','changed_state'])
def test_invalid_periodic_handle_is_rejected(fault):
    sketch = CircleSketch()
    handle = Point(sketch,2,(.013,.01,0.),kind=-1)
    handle.Status = 1
    sketch.lines[0].start = sketch.lines[0].end = handle
    if fault=='alias': sketch.lines[0].end=Point(sketch,2,(.013,.01,0.),kind=-1)
    if fault=='mixed': sketch.lines[0].end=Point(sketch,3,(.013,.01,0.))
    if fault=='foreign': handle.owner=object()
    if fault=='off_circle': handle.X=.014
    if fault=='off_plane': handle.Z=.001
    if fault=='enumerated': sketch.points.append(handle)
    if fault=='status': handle.Status=2
    if fault=='changed_state':
        class ChangingPoint(Point):
            reads=0
            @property
            def X(self):
                self.reads+=1
                return .013 if self.reads==1 else .014
            @X.setter
            def X(self,value): pass
        handle=ChangingPoint(sketch,2,(.013,.01,0.),kind=-1); handle.Status=1
        sketch.lines[0].start=sketch.lines[0].end=handle
    with pytest.raises(ExecutionFailure): capture(sketch)


def test_census_order_does_not_change_circle_or_relation_semantics():
    sketch = CircleSketch()
    result = capture(sketch)[0]
    sketch.relations.reverse()
    assert capture(sketch)[0]==result


def test_sub_tolerance_geometry_change_is_preserved_verbatim():
    sketch = CircleSketch()
    old = capture(sketch)[0]
    sketch.lines[0].radius = math.nextafter(.003,1.)
    current = capture(sketch)[0]
    assert current!=old and current['segments'][0]['radius_si']==sketch.lines[0].radius.hex()


@pytest.mark.parametrize('value',[True,False,'1',None,0,2,-1,1.])
def test_is_circle_is_registered_native_long_and_never_truthiness(value):
    sketch = CircleSketch()
    sketch.lines[0].IsCircle = lambda:value
    with pytest.raises(ExecutionFailure): capture(sketch)


@pytest.mark.parametrize('radius',[True,False,'1',None,0.,-1.,math.inf,math.nan,10001.,10**400])
def test_invalid_radius_is_rejected(radius):
    sketch = CircleSketch()
    sketch.lines[0].radius = radius
    with pytest.raises(ExecutionFailure): capture(sketch)


@pytest.mark.parametrize('fault',[
    'line','spline','foreign_owner','duplicate_circle','centre_missing','centre_alias',
    'foreign_centre','centre_origin','bad_normal','bad_rotation','bool_rotation','half_endpoints',
    'open_endpoints','seam_not_on_radius','origin_seam','missing_curve','not_circle_curve',
    'line_curve','curve_radius','curve_axis','foreign_relation_circle','relation_local_id_alias',
    'wrong_relation_enum','missing_relation_definitions','count','3d','blocks','pictures',
    'slot','hatch','text','nonfinite_centre','duplicate_relation','dimension_alias',
])
def test_incomplete_or_foreign_circle_capture_is_rejected(fault):
    sketch = CircleSketch()
    circle = sketch.lines[0]
    if fault=='line': circle.GetType=lambda:0
    if fault=='spline': circle.GetType=lambda:3
    if fault=='foreign_owner': circle.owner=object()
    if fault=='duplicate_circle': sketch.lines.append(circle)
    if fault=='centre_missing': sketch.points=[]
    if fault=='centre_alias': circle.centre=Point(sketch,0,(.01,.01,0.))
    if fault=='foreign_centre': circle.centre.owner=object()
    if fault=='centre_origin': circle.centre=sketch.origin
    if fault=='bad_normal': circle.normal=(0.,0.,2.)
    if fault=='bad_rotation': circle.rotation=0
    if fault=='bool_rotation': circle.rotation=True
    if fault in ('half_endpoints','open_endpoints','seam_not_on_radius','origin_seam'):
        seam = Point(sketch,2,(.013,.01,0.))
        sketch.points.append(seam)
        circle.start=circle.end=seam
        if fault=='half_endpoints': circle.end=None
        if fault=='open_endpoints':
            circle.end=Point(sketch,3,(.01,.013,0.))
            sketch.points.append(circle.end)
        if fault=='seam_not_on_radius': seam.X=.014
        if fault=='origin_seam': circle.start=circle.end=sketch.origin
    if fault=='missing_curve': circle.GetCurve=lambda:None
    if fault in ('not_circle_curve','line_curve','curve_radius','curve_axis'):
        curve=circle.GetCurve()
        circle.GetCurve=lambda:curve
        if fault=='not_circle_curve': curve.IsCircle=lambda:False
        if fault=='line_curve': curve.IsLine=lambda:True
        if fault=='curve_radius': curve.CircleParams=(*curve.CircleParams[:6],.004)
        if fault=='curve_axis': curve.CircleParams=(.01,.01,0.,0.,0.,2.,.003)
    if fault=='foreign_relation_circle': sketch.relations[-1].entities=[Circle(object(),0,circle.centre)]
    if fault=='relation_local_id_alias': sketch.relations[-1].definitions=[Circle(sketch,0,circle.centre)]
    if fault=='wrong_relation_enum': sketch.relations[-1].types=[3]
    if fault=='missing_relation_definitions': sketch.relations[-1].definitions=[]
    if fault=='count': sketch.GetSketchPointsCount2=lambda:2
    if fault=='3d': sketch.Is3D=lambda:True
    if fault=='blocks': sketch.GetSketchBlockInstanceCount=lambda:1
    if fault=='pictures': sketch.GetSketchPictureCount=lambda:1
    if fault=='slot': sketch.GetSketchSlotCount=lambda:1
    if fault=='hatch': sketch.GetSketchHatches=lambda:(object(),)
    if fault=='text': sketch.GetSketchTextSegments=lambda:(object(),)
    if fault=='nonfinite_centre': circle.centre.X=math.nan
    if fault=='duplicate_relation': sketch.relations.append(sketch.relations[0])
    if fault=='dimension_alias': sketch.relations[-1].display.GetDimension2=lambda slot:NS(FullName=sketch.dimensions[0].FullName)
    with pytest.raises(ExecutionFailure): capture(sketch)


def test_linear_reader_still_rejects_circle_and_circle_reader_rejects_rectangle():
    circle = CircleSketch()
    with pytest.raises(ExecutionFailure):
        LinearSketchReader(circle,circle.origin,wrap=lambda raw,name:raw,identity=id).read()
    with pytest.raises(ExecutionFailure): capture(Sketch())


def test_typed_arc_binds_exact_current_base_segment_before_exposing_arc_methods():
    sketch=CircleSketch()
    circle=sketch.lines[0]
    circle.pid=b'circle'
    typed=NS(GetRadius=circle.GetRadius,GetCenterPoint2=circle.GetCenterPoint2)
    binder=SketchEntityBinder(wrap=lambda raw,name:typed if name=='ISketchArc' else raw,
        reference=lambda raw:raw.pid,resolve=lambda pid,name:circle,identity=id)
    assert binder(circle,'ISketchArc') is typed and not hasattr(typed,'GetID')
    replacement=deepcopy(circle)
    binder.resolve=lambda pid,name:replacement
    with pytest.raises(ExecutionFailure): binder(circle,'ISketchArc')
