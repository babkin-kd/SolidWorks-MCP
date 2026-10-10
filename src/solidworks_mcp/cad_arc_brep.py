"""Complete finite line/arc topology with planar caps and cylindrical quadrilaterals.

No seams, periodic inner loops, splines, toroidal/other surfaces or faceting.
Native evaluations prove partial trim positions and orientation; full native
loop/coedge/root censuses and solid checks are shared with the hole reader.
"""

import math

from .cad_planar_brep import PlanarBrepError, _hex, _cross, _plane_consistent, _points_consistent
from .cad_cylinder_brep import _dot, _subtract, _unit


ARC_BREP_SCOPE='finite_arc_cylinder_and_planar_solid_brep_v1'


def _fail(message,code='arc_brep_incomplete'):
    raise PlanarBrepError(code,message)


def finite_arc_body_snapshot(body,*,identity,wrap=None,limits=None):
    from .cad_hole_brep import _mixed_body_snapshot
    return _mixed_body_snapshot(body,identity=identity,wrap=wrap,limits=limits,finite_arcs=True)


def _arc(r,edge,points,vertex_index):
    curve=r.obj(r.call(edge,'GetCurve'),'ICurve')
    parameters=r.numbers(r.prop(curve,'CircleParams'),7,'arc circle parameters')
    _unit(parameters[3:6])
    radius=parameters[6]
    if radius<=0:_fail('Finite circular arcs require a positive radius.')
    a=r.key(r.obj(r.call(edge,'GetStartVertex'),'IVertex'),'IVertex')
    b=r.key(r.obj(r.call(edge,'GetEndVertex'),'IVertex'),'IVertex')
    if a==b or a not in points or b not in points:
        _fail('Finite arc endpoints require distinct current native body vertices.')
    trim=r.obj(r.call(edge,'GetCurveParams3'),'ICurveParamData')
    kind=r.prop(trim,'CurveType')
    if type(kind) is not int or kind!=3002:_fail('Exact native CIRCLE_TYPE is required.')
    sense=r.flag(r.prop(trim,'Sense'),'arc Sense')
    interval=r.numbers((r.prop(trim,'UMinValue'),r.prop(trim,'UMaxValue')),2,'arc trim interval')
    span=interval[1]-interval[0]
    if not 0.<span<math.pi:
        _fail('This finite arc scope supports nonzero spans smaller than pi.','arc_brep_unsupported')
    start=r.numbers(r.prop(trim,'StartPoint'),3,'arc trim start')
    end=r.numbers(r.prop(trim,'EndPoint'),3,'arc trim end')
    expected=(points[a],points[b]) if sense else (points[b],points[a])
    evaluated=[]
    signs=[]
    tolerance=r.limits.consistency_tolerance_m
    for value,point,vertex in zip(interval,(start,end),expected):
        if not _points_consistent(point,vertex,tolerance):_fail('Arc trim sense/endpoints disagree with native vertices.')
        radial=_subtract(point,parameters[:3])
        if abs(_dot(radial,parameters[3:6]))>tolerance or abs(math.sqrt(_dot(radial,radial))-radius)>tolerance:
            _fail('Arc trim endpoint does not lie on the full native circle.')
        raw=r.numbers(r.call(curve,'Evaluate2',value,1),6,'native arc point/tangent')
        if not _points_consistent(raw[:3],point,tolerance):_fail('Native parameter evaluation differs from trim endpoints.')
        tangent=raw[3:]
        reference=_cross(parameters[3:6],radial)
        dot=_dot(tangent,reference)
        sign=1 if dot>0. else -1
        if (abs(math.sqrt(_dot(tangent,tangent))-radius)>tolerance
                or not _points_consistent(tangent,tuple(sign*x for x in reference),tolerance)):
            _fail('Native circular tangent is not consistent with radius/axis.')
        signs.append(sign);evaluated.append(raw)
    if signs[0]!=signs[1]:_fail('Native arc orientation changes inside its trim.')
    va,vb=(_subtract(point,parameters[:3]) for point in (start,end))
    angle=math.atan2(_dot(_cross(va,vb),parameters[3:6]),_dot(va,vb))
    if abs(angle-signs[0]*span)>1e-12:_fail('Native trim interval selects a different circular arc.')
    length=r.numbers((r.call(curve,'GetLength3',*interval),),1,'native arc length')[0]
    if abs(length-radius*span)>tolerance:_fail('Native arc length differs from the retained trim.')
    return dict(kind='arc',parameters=parameters,start=a,end=b,
        trim=dict(curve_type=kind,same_direction_as_edge=sense,start_point=list(_hex(start)),
            end_point=list(_hex(end)),u_min=interval[0].hex(),u_max=interval[1].hex(),
            evaluations_si=[list(_hex(row)) for row in evaluated],length_si=length.hex(),
            parameter_direction=signs[0]),
        key=(1,tuple(sorted((vertex_index[a],vertex_index[b]))),_hex(parameters),_hex(interval),sense))


def _angular_step(edge,use,axis):
    trim=edge['trim']
    span=float.fromhex(trim['u_max'])-float.fromhex(trim['u_min'])
    direction=trim['parameter_direction']*(1 if trim['same_direction_as_edge'] else -1)*(1 if use['sense'] else -1)
    return direction*span*_dot(edge['parameters'][3:6],axis)


def _validate_planar_arcs(r,loop,parameters,sense,coedges,edges):
    arcs=[edges[coedges[key]['edge']] for key in loop['ordered'] if edges[coedges[key]['edge']]['kind']=='arc']
    for edge in arcs:
        circle=edge['parameters']
        if (not _plane_consistent(circle[:3],parameters,r.limits.consistency_tolerance_m)
                or abs(abs(_dot(circle[3:6],parameters[:3]))-1.)>1e-12):
            _fail('Every complete arc must lie on its exact planar face.')
    # The shared polygon proof rejects repeated vertices, intersecting chords,
    # wrong native winding and inconsistent plane orientation. Exact arc trims
    # remain in the snapshot; downstream engineering proof matches the complete
    # requested curved profile, never substitutes the chord polygon for it.


def _validate_cylinder_quad(r,loop,parameters,sense,points,coedges,edges):
    ordered=[coedges[key] for key in loop['ordered']]
    arcs=[(edges[use['edge']],use) for use in ordered if edges[use['edge']]['kind']=='arc']
    lines=[(edges[use['edge']],use) for use in ordered if edges[use['edge']]['kind']=='line']
    if len(ordered)!=4 or len(arcs)!=2 or len(lines)!=2:
        _fail('An unseamed finite cylindrical wall requires two complete arcs and two generators.','arc_brep_unsupported')
    origin,axis,radius=parameters[:3],parameters[3:6],parameters[6]
    tolerance=r.limits.consistency_tolerance_m
    for key in loop['vertices']:
        delta=_subtract(points[key],origin);z=_dot(delta,axis)
        radial=tuple(v-z*n for v,n in zip(delta,axis))
        if abs(math.sqrt(_dot(radial,radial))-radius)>tolerance:_fail('Cylinder vertex lies off its native surface.')
    heights=[]
    for edge,use in arcs:
        circle=edge['parameters'];delta=_subtract(circle[:3],origin);z=_dot(delta,axis)
        if (abs(circle[6]-radius)>tolerance or abs(abs(_dot(circle[3:6],axis))-1.)>1e-12
                or any(abs(v-z*n)>tolerance for v,n in zip(delta,axis))):
            _fail('Complete wall arcs must match its exact radius and axis.')
        heights.append(z)
    if abs(heights[0]-heights[1])<=tolerance:_fail('Distinct cylindrical end planes are required.')
    for edge,use in lines:
        vector=_subtract(points[use['end']],points[use['start']]);height=_dot(vector,axis)
        if abs(height)<=tolerance or any(abs(v-height*n)>tolerance for v,n in zip(vector,axis)):
            _fail('Cylindrical line edges must be exact nonzero generators.')
    steps=[_angular_step(edge,use,axis) for edge,use in arcs]
    if abs(sum(steps))>1e-12:_fail('Opposed cylindrical arcs do not delimit the same angular window.')
    theta=0.;area=0.
    for use in ordered:
        edge=edges[use['edge']]
        next_theta=theta+(_angular_step(edge,use,axis) if edge['kind']=='arc' else 0.)
        za=_dot(_subtract(points[use['start']],origin),axis)
        zb=_dot(_subtract(points[use['end']],origin),axis)
        area+=theta*zb-next_theta*za
        theta=next_theta
    if abs(theta)>1e-12 or area==0. or (area>0.)==sense:
        _fail('Native cylindrical loop winding disagrees with its outward surface orientation.')
