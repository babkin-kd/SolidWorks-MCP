"""Actual API-shaped artificial captures; not SolidWorks acceptance."""

from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.linear_sketch import LinearSketchReader


class Point:
    def __init__(self, owner, number, coordinates, kind=0):
        self.owner, self.number = owner, number
        self.X, self.Y, self.Z = coordinates
        self.Type, self.Status = kind, 2
    def GetID(self): return (self.number, self.number+1)
    def GetSketch(self): return self.owner


class Line:
    ConstructionGeometry, Infinite, Status = False, False, 2
    def __init__(self, owner, number, start, end):
        self.owner, self.number, self.start, self.end = owner, number, start, end
    def GetID(self): return (self.number, self.number+1)
    def GetSketch(self): return self.owner
    def GetType(self): return 0
    def GetStartPoint2(self): return self.start
    def GetEndPoint2(self): return self.end


class Relation:
    Suppressed = False
    def __init__(self, kind, types, entities, definitions=None, display=None):
        self.kind, self.types, self.entities = kind, types, entities
        self.definitions = entities if definitions is None else definitions
        self.display = display
    def GetRelationType(self): return self.kind
    def GetEntitiesType(self): return self.types
    def GetEntities(self): return self.entities
    def GetDefinitionEntities2(self): return self.definitions
    def GetEntitiesCount(self): return len(self.entities)
    def GetDisplayDimension(self): return self.display


class Sketch:
    def __init__(self, width=.04, height=.02):
        self.points = [Point(self, i, xyz) for i, xyz in enumerate(((0.,0.,0.),(width,0.,0.),(width,height,0.),(0.,height,0.)))]
        self.origin = Point(object(), 0, (0.,0.,0.), kind=1)
        self.projected = Point(self, 4, (0.,0.,0.), kind=10)
        self.lines = [Line(self, i, self.points[i], self.points[(i+1)%4]) for i in range(4)]
        self.dimensions = [NS(FullName='D1@Основание'), NS(FullName='D2@Основание')]
        self.relations = [Relation(9, [2,2], [self.projected,self.points[0]], [self.origin,self.points[0]])]
        self.relations += [Relation(4 if i%2==0 else 5, [3], [line]) for i,line in enumerate(self.lines)]
        for i, axis in enumerate((11,12)):
            display = NS(Type2=axis, GetType=lambda: 2, GetDimension2=lambda slot, i=i: self.dimensions[i])
            self.relations.append(Relation(1,[2,2],[self.points[i+1],self.projected],[self.points[i+1],self.origin],display))
        self.RelationManager = NS(GetRelationsCount=lambda kind:len(self.relations), GetRelations=lambda kind:self.relations)
    def Is3D(self): return False
    def GetSketchBlockInstanceCount(self): return 0
    def GetSketchPictureCount(self): return 0
    def GetSketchSlotCount(self): return 0
    def GetSketchHatches(self): return None
    def GetSketchTextSegments(self): return None
    def GetSketchPoints2(self): return self.points
    def GetSketchPointsCount2(self): return len(self.points)
    def GetSketchSegments(self): return self.lines
    def GetConstrainedStatus(self): return 3


def capture(sketch):
    return LinearSketchReader(sketch,sketch.origin,wrap=lambda raw,name:raw,identity=id).read()


def test_real_origin_definitions_and_projected_entities_are_distinct_and_complete():
    sketch = Sketch()
    snapshot, members = capture(sketch)
    assert len(snapshot['points']) == 5 and len(snapshot['relations']) == 7
    assert {row['display_type'] for row in snapshot['relations'] if row['type']==1} == {11,12}
    coincidence = next(row for row in snapshot['relations'] if row['type']==9)
    assert coincidence['entities'] == ['point:4:5','point:0:1']
    assert coincidence['definitions'] == ['model_origin','point:0:1']
    assert dict(members)['model_origin'] == id(sketch.origin)
    assert snapshot == capture(sketch)[0]


@pytest.mark.parametrize('fault', ['foreign_origin','aliased_point','foreign_line','curve','missing_point',
    'missing_definition','blocks','3d','count','nan','repeated_line','repeated_relation','dimension_alias'])
def test_incomplete_or_foreign_native_capture_is_rejected_without_partial_result(fault):
    sketch = Sketch()
    if fault=='foreign_origin': sketch.relations[0].definitions[0] = Point(object(),0,(0.,0.,0.),1)
    if fault=='aliased_point': sketch.lines[0].start = Point(sketch,0,(0.,0.,0.))
    if fault=='foreign_line': sketch.lines[0].owner = object()
    if fault=='curve': sketch.lines[0].GetType = lambda:1
    if fault=='missing_point': sketch.points.pop()
    if fault=='missing_definition': sketch.relations[0].definitions.pop()
    if fault=='blocks': sketch.GetSketchBlockInstanceCount = lambda:1
    if fault=='3d': sketch.Is3D = lambda:True
    if fault=='count': sketch.GetSketchPointsCount2 = lambda:6
    if fault=='nan': sketch.points[1].X = float('nan')
    if fault=='repeated_line': sketch.lines.append(sketch.lines[0])
    if fault=='repeated_relation': sketch.relations.append(sketch.relations[0])
    if fault=='dimension_alias':
        sketch.relations[-1].display.GetDimension2 = lambda slot:NS(FullName=sketch.dimensions[0].FullName)
    with pytest.raises(ExecutionFailure): capture(sketch)


def test_native_point_ids_are_local_hints_not_canonical_identity():
    first, second = Sketch(), Sketch()
    assert capture(first)[0] == capture(second)[0]
    assert capture(first)[1] != capture(second)[1]


def test_mutated_coordinate_changes_exact_capture_even_by_one_ulp():
    import math
    sketch = Sketch()
    old = capture(sketch)[0]
    sketch.points[1].X = math.nextafter(sketch.points[1].X,1.)
    assert old != capture(sketch)[0]
