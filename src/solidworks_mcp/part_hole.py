"""Engineering definition and full-boundary proof for a future through-hole tool.

This module performs no CAD writes and is not registered in the MCP catalog.
The native writer, circular sketch proof and durable execution remain separate
requirements before publication or installed-wheel acceptance.
"""

from dataclasses import dataclass
import math
import re

from .cad_hole_brep import HOLE_BREP_SCOPE
from .documents import rejected
from .features import russian_name
from .part_creation import _positive_length, validated_plane_transform


SCOPE = 'single_base_circular_through_hole_v1'
MATERIAL_MARGIN_M = 1e-6
GEOMETRY_TOLERANCE_M = 1e-12  # Reject-only consistency; never round revision data.


@dataclass(frozen=True)
class ThroughHole:
    object_id: str
    plane_object_id: str
    centre_x_mm: float
    centre_y_mm: float
    diameter_mm: float
    sketch_name: str
    feature_name: str

    @classmethod
    def validate(cls, *, object_id, plane_object_id, centre_x_mm, centre_y_mm,
                 diameter_mm, sketch_name='Эскиз отверстия', feature_name='Сквозное отверстие'):
        for value in (object_id,plane_object_id):
            if not isinstance(value,str) or not re.fullmatch(r'feat_[0-9a-f]{32}',value):
                raise rejected('invalid_hole_reference','Explicit opaque base sketch and plane references are required.')
        values = [_positive_length(value,label) for value,label in (
            (centre_x_mm,'centre_x_mm'),(centre_y_mm,'centre_y_mm'),(diameter_mm,'diameter_mm'))]
        if max(values) > 10000000.:
            raise rejected('hole_parameter_out_of_range','Hole dimensions exceed the complete native capture bound.')
        sketch_name,feature_name = map(russian_name,(sketch_name,feature_name))
        if sketch_name.casefold()==feature_name.casefold():
            raise rejected('hole_name_collision','The circle sketch and cut need distinct Russian display names.')
        return cls(object_id,plane_object_id,*values,sketch_name,feature_name)

    def expected_geometry(self,base):
        w,h,d = (base[key] for key in ('width_m','height_m','depth_m'))
        if any(type(value) not in (int,float) or not math.isfinite(value)
               or value < 1e-6 or value > 10000. for value in (w,h,d)):
            raise rejected('unsupported_hole_base','Finite positive supported base extents are required.')
        frame = validated_plane_transform(base['plane_transform'])
        x,y,r = self.centre_x_mm/1000.,self.centre_y_mm/1000.,self.diameter_mm/2000.
        if min(x-r,y-r,w-x-r,h-y-r) < MATERIAL_MARGIN_M:
            raise rejected('hole_outside_material','The entire circular hole must leave at least one micrometre of material at all four base sides.')
        section = w*h-math.pi*r*r
        volume = section*d*1e9
        area = (2.*section+2.*(w+h)*d+2.*math.pi*r*d)*1e6
        if not all(math.isfinite(value) and value>0 for value in (volume,area)):
            raise rejected('hole_geometry_unrepresentable','The complete remaining solid must have finite positive measures.')
        point = lambda a,b,c:tuple(a*frame[i]+b*frame[3+i]+c*frame[6+i]+frame[9+i] for i in range(3))
        return {'volume_mm3':volume,'surface_area_mm2':area,'solid_body_count':1,
            'vertex_count':8,'edge_count':14,'face_count':7,
            'vertices_si':[[value.hex() for value in point(a,b,c)]
                           for a in (0.,w) for b in (0.,h) for c in (0.,d)],
            'circle_centres_si':[[value.hex() for value in point(x,y,z)] for z in (0.,d)],
            'axis_si':[value.hex() for value in frame[6:9]],'radius_si':r.hex(),
            'base_extents_si':[float(value).hex() for value in (w,h,d)],
            'plane_transform_si':[value.hex() for value in frame]}


def hole_body_matches(geometry,expected):
    """Match a complete reader-validated boundary, not mass/bounds/census alone.

    The required reader has already proved all native coedge partners, trims,
    loop winding, solid checks and connected manifold incidence. This check
    additionally identifies the requested cuboid, cap planes, cylindrical wall
    and the two inner circles in their complete model-space coordinates.
    """
    try:
        bodies = geometry['bodies']
        if len(bodies)!=1:
            return False
        body = bodies[0]
        if body['scope']!=HOLE_BREP_SCOPE or any(len(body[key])!=expected[count] for key,count in
                (('vertices','vertex_count'),('edges','edge_count'),('faces','face_count'))):
            return False
        point = lambda raw:tuple(float.fromhex(value) for value in raw)
        close = lambda a,b:len(a)==len(b) and all(abs(x-y)<=GEOMETRY_TOLERANCE_M for x,y in zip(a,b))
        dot = lambda a,b:math.fsum(x*y for x,y in zip(a,b))
        delta = lambda a,b:tuple(x-y for x,y in zip(a,b))
        vertices = [point(row) for row in body['vertices']]
        wanted = [point(row) for row in expected['vertices_si']]
        mapping = {}
        for index,value in enumerate(vertices):
            matches = [i for i,row in enumerate(wanted) if close(value,row)]
            if len(matches)!=1 or matches[0] in mapping.values():
                return False
            mapping[index] = matches[0]
        # Expected vertex index is x*4+y*2+z; each finite edge changes one bit.
        finite = [edge for edge in body['edges'] if edge['kind']=='line']
        circular = [edge for edge in body['edges'] if edge['kind']=='circle']
        pairs = [frozenset((mapping[edge['start']],mapping[edge['end']])) for edge in finite]
        wanted_pairs = {frozenset((i,i^bit)) for i in range(8) for bit in (1,2,4)}
        if len(pairs)!=12 or len(set(pairs))!=12 or set(pairs)!=wanted_pairs or len(circular)!=2:
            return False
        centres = [point(row) for row in expected['circle_centres_si']]
        axis,radius = point(expected['axis_si']),float.fromhex(expected['radius_si'])
        ends = {}
        for index,edge in enumerate(body['edges']):
            if edge['kind']!='circle':
                continue
            p = point(edge['circle_parameters'])
            matches = [i for i,centre in enumerate(centres) if close(p[:3],centre)]
            if (len(matches)!=1 or matches[0] in ends.values() or abs(p[6]-radius)>GEOMETRY_TOLERANCE_M
                    or abs(abs(dot(p[3:6],axis))-1.)>1e-12):
                return False
            ends[index] = matches[0]
        if set(ends.values())!={0,1}:
            return False
        frame = point(expected['plane_transform_si'])
        axes = (frame[:3],frame[3:6],frame[6:9])
        extents = point(expected['base_extents_si'])
        remaining = {(i,end) for i in range(3) for end in (0,1)}
        walls = 0
        for face in body['faces']:
            p = point(face['surface_parameters'])
            if face['surface_type']=='cylinder':
                walls += 1
                if (face['normal_opposes_surface'] is not True or abs(p[6]-radius)>GEOMETRY_TOLERANCE_M
                        or abs(abs(dot(p[3:6],axis))-1.)>1e-12):
                    return False
                displacement = delta(p[:3],centres[0])
                projected = dot(displacement,axis)
                if any(abs(value-projected*direction)>GEOMETRY_TOLERANCE_M
                       for value,direction in zip(displacement,axis)):
                    return False
                loops = face['loops']
                if (len(loops)!=2 or any(loop['outer'] is not True or len(loop['coedges'])!=1 for loop in loops)
                        or {use['edge'] for loop in loops for use in loop['coedges']}!=set(ends)):
                    return False
                continue
            if face['surface_type']!='plane':
                return False
            normal = tuple(-value if face['normal_opposes_surface'] else value for value in p[:3])
            candidates = [(i,end) for i,end in remaining if close(normal,tuple((1. if end else -1.)*v for v in axes[i]))
                and abs(dot(delta(p[3:6],frame[9:12]),axes[i])-extents[i]*end)<=GEOMETRY_TOLERANCE_M]
            if len(candidates)!=1:
                return False
            plane,end = candidates[0]
            remaining.remove((plane,end))
            outer = [loop for loop in face['loops'] if loop['outer'] is True]
            inner = [loop for loop in face['loops'] if loop['outer'] is False]
            if len(outer)!=1 or len(outer[0]['coedges'])!=4 or len(inner)!=(1 if plane==2 else 0):
                return False
            bit = (4,2,1)[plane]
            expected_vertices = {i for i in range(8) if bool(i&bit)==bool(end)}
            uses = outer[0]['coedges']
            if ({mapping[use['start']] for use in uses}!=expected_vertices
                    or any(body['edges'][use['edge']]['kind']!='line' for use in uses)):
                return False
            if inner:
                uses = inner[0]['coedges']
                if len(uses)!=1 or ends.get(uses[0]['edge'])!=end:
                    return False
        return not remaining and walls==1
    except (KeyError,IndexError,TypeError,ValueError,OverflowError):
        return False
