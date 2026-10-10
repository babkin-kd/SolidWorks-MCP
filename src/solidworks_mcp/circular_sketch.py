"""Complete bounded full-circle planar sketches; no COM imports or CAD writes.

Shares the accepted complete point/relation/definition capture with the linear
reader. Partial arcs, mixed profiles and unsupported auxiliary geometry fail.
The native caller still proves persistent references and brackets paired reads
with complete document/configuration/event proof.
"""

from copy import deepcopy
import math

from .documents import rejected
from .dimensions import DimensionCatalog, close_value
from .linear_sketch import LinearSketchReader, _boolean, _coordinates, _identifier, _integer


SCOPE = 'circular_planar_sketch_geometry_v1'


class CircularSketchReader(LinearSketchReader):
    scope = SCOPE

    def _entity(self, kind, raw):
        if kind == 2:
            return self._point(raw, allow_implicit=True)
        if kind != 4:  # swSketchRelationEntityType_Arc, not swSketchEntityType_e
            raise rejected('sketch_relation_entity_unsupported','Only own full circles, points and the exact native origin are supported.')
        segment = self.wrap(raw,'ISketchSegment')
        key = 'circle:' + ':'.join(map(str,_identifier(segment)))
        if key not in self.lines or self.members[key] != self.identity(segment):
            raise rejected('sketch_relation_entity_unsupported','Relation circle is outside the complete current segment capture.')
        return key

    def _read_segment(self, raw):
        segment = self.wrap(raw,'ISketchSegment')
        if _integer(segment.GetType(),high=1000) != 1:
            raise rejected('sketch_curve_unsupported','The circular scope requires complete native circles; no mixed/partial result.')
        owner = self.wrap(segment.GetSketch(),'ISketch')
        if owner is None or self.identity(owner) != self.sketch_token:
            raise rejected('sketch_external_entity_unsupported','A circle belongs to another sketch.')
        arc = self.wrap(segment,'ISketchArc')
        # Registered SW2023 ISketchArc.IsCircle returns LONG, not BOOL.
        if _integer(arc.IsCircle(),high=1) != 1:
            raise rejected('sketch_curve_unsupported','Partial arcs require their own complete capture.')
        identifier = _identifier(segment)
        key = 'circle:' + ':'.join(map(str,identifier))
        if key in self.lines:
            raise rejected('sketch_entity_identity_collision','Repeated/colliding native circle in the complete array.')
        centre = self._point(arc.GetCenterPoint2())
        if centre == 'model_origin':
            raise rejected('sketch_capture_invalid','A full circle requires its own enumerated centre point.')
        radius = arc.GetRadius()
        if type(radius) not in (int,float):
            raise rejected('sketch_capture_invalid','A full native circle requires a finite positive bounded radius.')
        try:
            radius = float(radius)
        except OverflowError as exc:
            raise rejected('sketch_capture_invalid','The native circle radius is not representable.') from exc
        if not math.isfinite(radius) or not 0. < radius <= 10000.:
            raise rejected('sketch_capture_invalid','A full native circle requires a finite positive bounded radius.')
        normal = _coordinates(arc.GetNormalVector(),3)
        if not math.isclose(math.fsum(float.fromhex(v)**2 for v in normal),1.,rel_tol=0.,abs_tol=1e-12):
            raise rejected('sketch_capture_invalid','Complete native circle normal must be a unit vector.')
        rotation = _integer(arc.GetRotationDir(),low=-1,high=1)
        if rotation == 0:
            raise rejected('sketch_capture_invalid','Native circle rotation direction must be exactly -1 or 1.')
        curve = self.wrap(segment.GetCurve(),'ICurve')
        if curve is None or not _boolean(curve.IsCircle()) or _boolean(curve.IsLine()):
            raise rejected('sketch_capture_invalid','The full sketch circle requires its exact underlying native circle curve.')
        parameters = _coordinates(curve.CircleParams,7)
        p = [float.fromhex(value) for value in parameters]
        if (abs(p[6]-radius)>1e-12 or not math.isclose(math.fsum(v*v for v in p[3:6]),1.,rel_tol=0.,abs_tol=1e-12)):
            raise rejected('sketch_capture_invalid','Native circle curve radius/axis disagrees with a full analytical circle.')
        start_raw,end_raw = arc.GetStartPoint2(),arc.GetEndPoint2()
        if (start_raw is None)!=(end_raw is None):
            raise rejected('sketch_capture_invalid','Circle native endpoint evidence must be complete.')
        start = end = None
        periodic_endpoints = None
        if start_raw is not None:
            endpoints = [self.wrap(raw,'ISketchPoint') for raw in (start_raw,end_raw)]
            kinds = [_integer(point.Type,low=-1,high=1000) for point in endpoints]
            if -1 in kinds:
                # Native SW2023 exposes paired persistent periodic handles;
                # these are not enumerated sketch points or dimension targets.
                if kinds!=[-1,-1] or self.identity(endpoints[0])!=self.identity(endpoints[1]):
                    raise rejected('sketch_capture_invalid','Periodic circle endpoints must be the same exact native handle.')
                periodic_endpoints = []
                for index,point in enumerate(endpoints):
                    token = self.identity(point)
                    owner = self.wrap(point.GetSketch(),'ISketch')
                    identifier = _identifier(point)
                    coordinates = _coordinates((point.X,point.Y,point.Z),3)
                    xyz = tuple(float.fromhex(v) for v in coordinates)
                    centre_xyz = tuple(float.fromhex(v) for v in self.points[centre]['coordinates_si'])
                    if (owner is None or self.identity(owner)!=self.sketch_token
                            or _integer(point.Status,high=10)!=1
                            or token in self.members.values()
                            or 'point:'+':'.join(map(str,identifier)) in self.points
                            or not math.isclose(math.dist(xyz,centre_xyz),radius,rel_tol=0.,abs_tol=1e-12)
                            or abs(math.fsum((a-b)*float.fromhex(n) for a,b,n in zip(xyz,centre_xyz,normal)))>1e-12):
                        raise rejected('sketch_capture_invalid','Periodic handle must be separate, own and on the complete native circle.')
                    periodic_endpoints.append({'native_id':identifier,'point_type':-1,'constraint_status':1,'coordinates_si':coordinates})
                if periodic_endpoints[0]!=periodic_endpoints[1]:
                    raise rejected('sketch_capture_invalid','Periodic endpoint states must close exactly.')
                self.members[key+':periodic_endpoint'] = self.identity(endpoints[0])
            else:
                start,end = self._point(start_raw),self._point(end_raw)
        if start is not None:
            if 'model_origin' in (start,end):
                raise rejected('sketch_capture_invalid','Circle endpoints cannot alias the model origin.')
            a,b,c = (tuple(float.fromhex(value) for value in self.points[name]['coordinates_si']) for name in (start,end,centre))
            if any(abs(x-y)>1e-12 for x,y in zip(a,b)) or not math.isclose(math.dist(a,c),radius,rel_tol=0.,abs_tol=1e-12):
                raise rejected('sketch_capture_invalid','Full-circle endpoint points must close on the complete circle radius.')
        self.lines[key] = {'key':key,'native_id':identifier,'kind':'circle',
            'construction':_boolean(segment.ConstructionGeometry),'constraint_status':_integer(segment.Status,high=10),
            'centre':centre,'start':start,'end':end,'radius_si':radius.hex(),
            'normal_si':normal,'rotation_direction':rotation,'circle_parameters_si':parameters,
            'periodic_endpoints':periodic_endpoints}
        self.members[key] = self.identity(segment)


def circle_profile_parameters(snapshot, semantic, configuration):
    """Identify one independent X/Y/diameter network by actual native entities.

    Names are labels; relation type/Type2 and full definition entities prove the
    independent drivers. This first creation scope has one centre and no seam
    points. General full-circle reads remain a separate, broader operation.
    """
    fail = lambda message:rejected('unsupported_circular_sketch',message)
    if snapshot['scope']!=SCOPE or snapshot['is_3d'] or snapshot['constraint_status']!=3:
        raise fail('The requested circle requires a complete fully defined planar capture.')
    origin = snapshot['model_origin_point']
    if (origin['point_type']!=1 or origin['constraint_status']!=2
            or any(abs(float.fromhex(v))>1e-12 for v in origin['coordinates_si'])):
        raise fail('The exact fully constrained native model origin is required.')
    points = {point['key']:point for point in snapshot['points']}
    regular = {key:point for key,point in points.items() if not point['implicit']}
    implicit = {key:point for key,point in points.items() if point['implicit']}
    if (len(points)!=len(snapshot['points']) or len(regular)!=1 or len(implicit)!=1
            or any(point['constraint_status']!=2 for point in points.values())):
        raise fail('The initial circle profile needs one own centre and one exact origin projection.')
    centre,projected = next(iter(regular)),next(iter(implicit))
    if (regular[centre]['point_type']!=0 or implicit[projected]['point_type']!=10
            or any(abs(float.fromhex(v))>1e-12 for v in implicit[projected]['coordinates_si'])):
        raise fail('The centre and native projected model origin have unsupported point semantics.')
    xyz = tuple(float.fromhex(v) for v in regular[centre]['coordinates_si'])
    if xyz[0]<1e-6 or xyz[1]<1e-6 or abs(xyz[2])>1e-12:
        raise fail('The first profile has positive X/Y at least one micrometre in its plane.')
    if len(snapshot['segments'])!=1:
        raise fail('Exactly one fully captured native circle is required.')
    circle = snapshot['segments'][0]
    if (circle['kind']!='circle' or circle['centre']!=centre or circle['construction']
            or circle['constraint_status']!=2 or circle['start'] is not None or circle['end'] is not None):
        raise fail('The supported profile is one fully defined nonconstruction circle without seam points.')
    radius = float.fromhex(circle['radius_si'])
    parameters = tuple(float.fromhex(v) for v in circle['circle_parameters_si'])
    normal = tuple(float.fromhex(v) for v in circle['normal_si'])
    if (radius<5e-7 or not math.isfinite(radius) or abs(parameters[6]-radius)>1e-12
            or any(abs(a-b)>1e-12 for a,b in zip(parameters[:3],xyz))
            or abs(normal[0])>1e-12 or abs(normal[1])>1e-12 or abs(abs(normal[2])-1.)>1e-12
            or abs(parameters[3])>1e-12 or abs(parameters[4])>1e-12 or abs(abs(parameters[5])-1.)>1e-12):
        raise fail('The complete underlying native curve must be the requested planar circle in sketch space.')
    rows = [row for row in semantic['dimensions'] if row['owner']
            and row['owner']['native_id']==snapshot['feature_native_id']]
    if len(rows)!=3 or len({row['full_name'] for row in rows})!=3:
        raise fail('Exactly three independent own driving dimensions are required.')
    by_name = {row['full_name']:row for row in rows}
    axes = {}
    for relation in snapshot['relations']:
        role = {11:'centre_x',12:'centre_y',6:'diameter'}.get(relation['display_type'])
        name = relation['dimension_full_name']
        if (relation['type']!=(15 if role=='diameter' else 1) or relation['suppressed'] or role is None
                or role in axes or name not in by_name or name in axes.values()):
            raise fail('Only one unsuppressed X/Y/diameter dimension relation per independent driver is supported.')
        entities,definitions = relation['entities'],relation['definitions']
        if role=='diameter':
            if entities!=[circle['key']] or definitions!=[circle['key']]:
                raise fail('The diameter relation must bind the exact own native circle.')
            value = 2.*radius
        else:
            if (len(entities)!=2 or len(definitions)!=2 or set(entities)!={centre,projected}
                    or set(definitions)!={centre,'model_origin'}):
                raise fail('Centre dimensions must bind the exact own centre and native model-origin definitions.')
            value = xyz[0 if role=='centre_x' else 1]
        if not close_value(by_name[name]['values_si'][configuration],value):
            raise fail('The independent driving value disagrees with the complete circle geometry.')
        axes[role] = name
    if len(snapshot['relations'])!=3 or set(axes)!={'centre_x','centre_y','diameter'}:
        raise fail('The complete supported circle constraint network has exactly three independent relations.')
    for row in rows:
        checked = deepcopy(row)
        checked['write_blockers'] = [item for item in checked['write_blockers'] if item!='sketch_geometry_snapshot_not_implemented']
        DimensionCatalog._writable(semantic,checked,'mm')
    return {'centre_x_m':xyz[0],'centre_y_m':xyz[1],'radius_m':radius,'diameter_m':2.*radius,'axes':axes}
