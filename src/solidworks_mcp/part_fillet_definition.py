"""One explicit cuboid edge round: full intended boundary, not a mass proxy."""

from dataclasses import dataclass
import math
import re

from .cad_arc_brep import ARC_BREP_SCOPE
from .cad_planar_brep import PLANAR_BREP_SCOPE
from .documents import rejected
from .features import russian_name
from .part_creation import _positive_length, validated_plane_transform


SCOPE='single_base_selected_edge_fillet_v1'
TOLERANCE_M=1e-12


def cuboid_body_matches(geometry,base):
    """Prove every native base edge and planar face before selecting one edge."""
    try:
        if len(geometry['bodies'])!=1:return False
        body=geometry['bodies'][0]
        if body['scope']!=PLANAR_BREP_SCOPE or tuple(len(body[k]) for k in ('vertices','edges','faces'))!=(8,12,6):return False
        frame=validated_plane_transform(base['plane_transform']);axes=(frame[:3],frame[3:6],frame[6:9])
        extents=tuple(base[k] for k in ('width_m','height_m','depth_m'))
        decode=lambda raw:tuple(float.fromhex(v) for v in raw)
        dot=lambda a,b:math.fsum(x*y for x,y in zip(a,b))
        close=lambda a,b:len(a)==len(b) and all(abs(x-y)<=TOLERANCE_M for x,y in zip(a,b))
        wanted=[tuple(math.fsum((x*frame[i],y*frame[3+i],z*frame[6+i],frame[9+i])) for i in range(3))
            for x in (0.,extents[0]) for y in (0.,extents[1]) for z in (0.,extents[2])]
        mapping={}
        for index,raw in enumerate(body['vertices']):
            matches=[i for i,p in enumerate(wanted) if close(decode(raw),p)]
            if len(matches)!=1 or matches[0] in mapping.values():return False
            mapping[index]=matches[0]
        pairs=[frozenset((mapping[e['start']],mapping[e['end']])) for e in body['edges']]
        if len(set(pairs))!=12 or set(pairs)!={frozenset((i,i^bit)) for i in range(8) for bit in (1,2,4)}:return False
        remaining={(i,end) for i in range(3) for end in (0,1)}
        for face in body['faces']:
            if face.get('surface_type','plane')!='plane' or len(face['loops'])!=1:return False
            loop=face['loops'][0]
            if loop['outer'] is not True or len(loop['coedges'])!=4:return False
            # The planar reader serializes plane_parameters, unlike mixed bodies.
            p=decode(face['plane_parameters']);normal=tuple(-v if face['normal_opposes_surface'] else v for v in p[:3])
            delta=tuple(v-o for v,o in zip(p[3:6],frame[9:12]))
            candidates=[(i,end) for i,end in remaining if close(normal,tuple((1. if end else -1.)*v for v in axes[i]))
                and abs(dot(delta,axes[i])-end*extents[i])<=TOLERANCE_M]
            if len(candidates)!=1:return False
            i,end=candidates[0];remaining.remove((i,end));bit=(4,2,1)[i]
            if {mapping[u['start']] for u in loop['coedges']}!={j for j in range(8) if bool(j&bit)==bool(end)}:return False
        return not remaining
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):return False


def cuboid_edge(points,base):
    frame=validated_plane_transform(base['plane_transform'])
    axes=(frame[:3],frame[3:6],frame[6:9])
    extents=tuple(base[k] for k in ('width_m','height_m','depth_m'))
    if len(points)!=2: raise rejected('unsupported_fillet_edge','Two exact finite endpoints are required.')
    bits=[]
    for point in points:
        if len(point)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point):
            raise rejected('unsupported_fillet_edge','Finite model-space endpoints are required.')
        local=[math.fsum((point[i]-frame[9+i])*a[i] for i in range(3)) for a in axes]
        row=[]
        for value,extent in zip(local,extents):
            matches=[end for end in (0,1) if abs(value-end*extent)<=TOLERANCE_M]
            if len(matches)!=1: raise rejected('unsupported_fillet_edge','The selected edge must be an entire current cuboid edge.')
            row.append(matches[0])
        bits.append(row)
    changed=[axis for axis in range(3) if bits[0][axis]!=bits[1][axis]]
    if len(changed)!=1: raise rejected('unsupported_fillet_edge','Exactly one cuboid edge axis is required.')
    axis=changed[0]
    return axis,tuple(bits[0][i] for i in range(3) if i!=axis)


@dataclass(frozen=True)
class SelectedEdgeFillet:
    object_id:str
    edge_id:str
    radius_mm:float
    feature_name:str

    @classmethod
    def validate(cls,*,object_id,edge_id,radius_mm,feature_name='Скругление ребра'):
        if not isinstance(object_id,str) or not re.fullmatch(r'feat_[0-9a-f]{32}',object_id):
            raise rejected('invalid_fillet_reference','An explicit opaque base sketch feature is required.')
        if not isinstance(edge_id,str) or not re.fullmatch(r'obj_[0-9a-f]{32}',edge_id):
            raise rejected('invalid_fillet_reference','An explicit current body edge reference is required.')
        radius=_positive_length(radius_mm,'radius_mm')
        if radius>10000000.: raise rejected('fillet_parameter_out_of_range','Radius exceeds complete native capture bounds.')
        return cls(object_id,edge_id,radius,russian_name(feature_name))

    def expected_geometry(self,base,axis,corner):
        if type(axis) is not int or axis not in (0,1,2) or len(corner)!=2 or any(type(x) is not int or x not in (0,1) for x in corner):
            raise rejected('unsupported_fillet_edge','A single explicit cuboid edge axis/corner is required.')
        extents=tuple(base[k] for k in ('width_m','height_m','depth_m'))
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 1e-6<=v<=10000. for v in extents):
            raise rejected('unsupported_fillet_base','Supported finite positive cuboid extents are required.')
        frame=validated_plane_transform(base['plane_transform'])
        transverse=[i for i in range(3) if i!=axis]
        w,h=map(extents.__getitem__,transverse);depth=extents[axis];r=self.radius_mm/1000.
        if min(w,h)-2.*r<1e-6:
            raise rejected('fillet_radius_outside_material','Radius must leave a micrometre beyond half each transverse extent.')
        section=w*h-(1.-math.pi/4.)*r*r
        volume=section*depth*1e9
        area=(2.*section+(2.*(w+h)-(2.-math.pi/2.)*r)*depth)*1e6
        if not all(math.isfinite(v) and v>0 for v in (volume,area)):
            raise rejected('fillet_geometry_unrepresentable','Complete rounded solid measures must be finite and positive.')
        profile=[(r,0.),(w,0.),(w,h),(0.,h),(0.,r)]
        profile=[tuple((extent-value if bit else value) for value,extent,bit in zip(p,(w,h),corner)) for p in profile]
        def local(x,y,z):
            result=[0.,0.,0.];result[transverse[0]]=x;result[transverse[1]]=y;result[axis]=z
            return result
        def model(p): return [float(math.fsum([p[j]*frame[3*j+i] for j in range(3)]+[frame[9+i]])).hex() for i in range(3)]
        local_points=[local(x,y,z) for z in (0.,depth) for x,y in profile]
        polygons=[list(range(5)),list(range(5,10))]+[[i,(i+1)%5,(i+1)%5+5,i+5] for i in range(5)]
        pairs=sorted({tuple(sorted((a,b))) for poly in polygons for a,b in zip(poly,poly[1:]+poly[:1])})
        centre=[(extent-r if bit else r) for extent,bit in zip((w,h),corner)]
        return dict(volume_mm3=volume,surface_area_mm2=area,solid_body_count=1,
            vertex_count=10,edge_count=15,face_count=7,
            vertices_si=[model(p) for p in local_points],edge_pairs=pairs,
            arc_pairs=[(0,4),(5,9)],face_vertices=polygons,
            circle_centres_si=[model(local(*centre,z)) for z in (0.,depth)],
            axis_si=[float(v).hex() for v in frame[3*axis:3*axis+3]],radius_si=r.hex(),
            base_extents_si=[float(v).hex() for v in extents],plane_transform_si=[v.hex() for v in frame],
            local_vertices_si=[[float(v).hex() for v in p] for p in local_points],axis=axis)


def fillet_body_matches(geometry,expected):
    """Match every edge and face of the complete reader-validated rounded solid."""
    try:
        if len(geometry['bodies'])!=1:return False
        body=geometry['bodies'][0]
        if body['scope']!=ARC_BREP_SCOPE or any(len(body[key])!=expected[count] for key,count in
                (('vertices','vertex_count'),('edges','edge_count'),('faces','face_count'))):return False
        decode=lambda raw:tuple(float.fromhex(x) for x in raw)
        close=lambda a,b:len(a)==len(b) and all(abs(x-y)<=TOLERANCE_M for x,y in zip(a,b))
        dot=lambda a,b:math.fsum(x*y for x,y in zip(a,b))
        delta=lambda a,b:tuple(x-y for x,y in zip(a,b))
        wanted=[decode(p) for p in expected['vertices_si']];mapping={}
        for index,p in enumerate(body['vertices']):
            matches=[i for i,q in enumerate(wanted) if close(decode(p),q)]
            if len(matches)!=1 or matches[0] in mapping.values():return False
            mapping[index]=matches[0]
        arc_pairs={frozenset(p) for p in expected['arc_pairs']}
        pairs=[frozenset((mapping[e['start']],mapping[e['end']])) for e in body['edges']]
        if len(set(pairs))!=15 or set(pairs)!={frozenset(p) for p in expected['edge_pairs']}:return False
        axis=decode(expected['axis_si']);radius=float.fromhex(expected['radius_si'])
        centres=[decode(p) for p in expected['circle_centres_si']]
        for edge,pair in zip(body['edges'],pairs):
            if edge['kind']!=('arc' if pair in arc_pairs else 'line'):return False
            if edge['kind']=='arc':
                p=decode(edge['circle_parameters']);end=0 if min(pair)<5 else 1
                trim=edge['trimmed_curve'];span=float.fromhex(trim['u_max'])-float.fromhex(trim['u_min'])
                if (not close(p[:3],centres[end]) or abs(p[6]-radius)>TOLERANCE_M
                        or abs(abs(dot(p[3:6],axis))-1.)>1e-12 or abs(span-math.pi/2.)>1e-12):return False
        frame=decode(expected['plane_transform_si']);axes=(frame[:3],frame[3:6],frame[6:9])
        extents=decode(expected['base_extents_si']);local=[decode(p) for p in expected['local_vertices_si']]
        remaining={frozenset(poly):poly for poly in expected['face_vertices']}
        planes=set();cylinders=0
        for face in body['faces']:
            loops=face['loops']
            if len(loops)!=1 or loops[0]['outer'] is not True:return False
            uses=loops[0]['coedges'];vertices=frozenset(mapping[u['start']] for u in uses)
            poly=remaining.pop(vertices,None)
            if poly is None or len(uses)!=len(poly):return False
            expected_pairs={frozenset((a,b)) for a,b in zip(poly,poly[1:]+poly[:1])}
            if {pairs[u['edge']] for u in uses}!=expected_pairs:return False
            p=decode(face['surface_parameters'])
            if vertices==frozenset(expected['face_vertices'][-1]):
                if face['surface_type']!='cylinder' or face['normal_opposes_surface'] is not False:return False
                displacement=delta(p[:3],centres[0]);z=dot(displacement,p[3:6])
                if (abs(p[6]-radius)>TOLERANCE_M or abs(abs(dot(p[3:6],axis))-1.)>1e-12
                        or any(abs(v-z*n)>TOLERANCE_M for v,n in zip(displacement,p[3:6]))):return False
                cylinders+=1
            else:
                if face['surface_type']!='plane':return False
                normal=tuple(-v if face['normal_opposes_surface'] else v for v in p[:3])
                candidates=[(i,end) for i in range(3) for end in (0,1)
                    if all(abs(local[k][i]-end*extents[i])<=TOLERANCE_M for k in poly)
                    and close(normal,tuple((1. if end else -1.)*v for v in axes[i]))
                    and abs(dot(delta(p[3:6],frame[9:12]),axes[i])-end*extents[i])<=TOLERANCE_M]
                if len(candidates)!=1 or candidates[0] in planes:return False
                planes.add(candidates[0])
        return not remaining and cylinders==1 and len(planes)==6
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):return False
