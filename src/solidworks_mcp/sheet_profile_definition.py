"""Native ninety-degree sheet profile: explicit K-factor and full folded shape."""

from dataclasses import dataclass
import math
import re

from .cad_arc_brep import ARC_BREP_SCOPE
from .documents import rejected
from .features import russian_name
from .part_creation import _positive_length,validated_plane_transform


SCOPE='empty_part_sheet_l_profile_v1'
TOLERANCE_M=1e-12


@dataclass(frozen=True)
class SheetLProfile:
    plane_object_id:str
    leg_x_mm:float
    leg_y_mm:float
    length_mm:float
    thickness_mm:float
    bend_radius_mm:float
    k_factor:float
    sketch_name:str
    feature_name:str
    body_name:str

    @classmethod
    def validate(cls,*,plane_object_id,leg_x_mm,leg_y_mm,length_mm,thickness_mm,bend_radius_mm,k_factor,
            sketch_name='Эскиз листового профиля',feature_name='Листовой уголок',body_name='Тело листового уголка'):
        if not isinstance(plane_object_id,str) or not re.fullmatch(r'feat_[0-9a-f]{32}',plane_object_id):
            raise rejected('invalid_sheet_plane_reference','An explicit opaque native plane reference is required.')
        sizes=[_positive_length(value,label) for label,value in (('leg_x_mm',leg_x_mm),('leg_y_mm',leg_y_mm),
            ('length_mm',length_mm),('thickness_mm',thickness_mm),('bend_radius_mm',bend_radius_mm))]
        if max(sizes)>10000000.:raise rejected('sheet_parameter_out_of_range','Dimensions exceed complete native capture bounds.')
        if type(k_factor) not in (int,float) or not 0.<=k_factor<=1. or not math.isfinite(k_factor):
            raise rejected('invalid_sheet_k_factor','Explicit K-factor must be finite and between zero and one.')
        if min(sizes[0],sizes[1])-(sizes[3]+sizes[4])<.001:
            raise rejected('sheet_profile_no_straight_leg','Both legs must retain at least 0.001 mm beyond the outer bend radius.')
        names=tuple(map(russian_name,(sketch_name,feature_name,body_name)))
        if names[0].casefold()==names[1].casefold():raise rejected('sheet_name_collision','Sketch and base feature require distinct Russian names.')
        return cls(plane_object_id,*sizes,float(k_factor),*names)

    @property
    def profile_m(self):return ((0.,self.leg_y_mm/1000.),(0.,0.),(self.leg_x_mm/1000.,0.))

    @property
    def section_m2(self):
        w,h,t,r=(v/1000. for v in (self.leg_x_mm,self.leg_y_mm,self.thickness_mm,self.bend_radius_mm));outer=r+t
        return t*(w+h-2.*outer)+math.pi/4.*(outer**2-r**2)

    @property
    def volume_mm3(self):return self.section_m2*(self.length_mm/1000.)*1e9

    @property
    def surface_area_mm2(self):
        w,h,t,r=(v/1000. for v in (self.leg_x_mm,self.leg_y_mm,self.thickness_mm,self.bend_radius_mm));outer=r+t
        perimeter=2.*(w+h-2.*outer)+2.*t+math.pi/2.*(outer+r)
        return (2.*self.section_m2+perimeter*(self.length_mm/1000.))*1e6

    @property
    def developed_length_mm(self):
        outer=self.bend_radius_mm+self.thickness_mm
        return self.leg_x_mm+self.leg_y_mm-2.*outer+math.pi/2.*(self.bend_radius_mm+self.k_factor*self.thickness_mm)

    def expected_geometry(self,plane_transform):
        frame=validated_plane_transform(plane_transform)
        w,h,d,t,r=(v/1000. for v in (self.leg_x_mm,self.leg_y_mm,self.length_mm,self.thickness_mm,self.bend_radius_mm));outer=r+t
        profile=[(0.,h),(0.,outer),(outer,0.),(w,0.),(w,t),(outer,t),(t,outer),(t,h)]
        model=lambda p:[float(math.fsum([p[j]*frame[3*j+i] for j in range(3)]+[frame[9+i]])).hex() for i in range(3)]
        vertices=[model((x,y,z)) for z in (0.,d) for x,y in profile]
        # Native sheet metal preserves bend seams on both cap faces. Each cap
        # consists of two straight-leg rectangles and one annular bend sector.
        sections=[[0,1,6,7],[1,2,5,6],[2,3,4,5]]
        polygons=sections+[[v+8 for v in p] for p in sections]+[[i,(i+1)%8,(i+1)%8+8,i+8] for i in range(8)]
        pairs=sorted({tuple(sorted((a,b))) for polygon in polygons for a,b in zip(polygon,polygon[1:]+polygon[:1])})
        arc_pairs=[dict(pair=(a+8*end,b+8*end),radius_si=radius.hex(),centre_si=model((outer,outer,end*d)),role=role)
            for role,a,b,radius in (('outer',1,2,outer),('inner',5,6,r)) for end in (0,1)]
        surfaces=[]
        for end in (0,1):
            surfaces.extend([dict(kind='plane',normal_si=[((1. if end else -1.)*v).hex() for v in frame[6:9]],
                point_si=model((0.,0.,end*d))) for _ in sections])
        for i,(a,b) in enumerate(zip(profile,profile[1:]+profile[:1])):
            if i in (1,5):
                surfaces.append(dict(kind='cylinder',centre_si=model((outer,outer,0.)),
                    axis_si=[v.hex() for v in frame[6:9]],radius_si=(outer if i==1 else r).hex(),inward=i==5))
            else:
                dx,dy=b[0]-a[0],b[1]-a[1];norm=math.hypot(dx,dy)
                normal=[math.fsum((dy*frame[j],-dx*frame[3+j]))/norm for j in range(3)]
                surfaces.append(dict(kind='plane',normal_si=[v.hex() for v in normal],point_si=model((*a,0.))))
        return dict(volume_mm3=self.volume_mm3,surface_area_mm2=self.surface_area_mm2,solid_body_count=1,
            vertex_count=16,edge_count=28,face_count=14,vertices_si=vertices,edge_pairs=pairs,
            arc_pairs=arc_pairs,face_vertices=polygons,face_surfaces=surfaces,plane_transform_si=[v.hex() for v in frame],
            neutral_axis_developed_length_mm=self.developed_length_mm)


def sheet_l_body_matches(geometry,expected):
    """Match every native vertex, line, arc and oriented face of the folded L."""
    try:
        if len(geometry['bodies'])!=1:return False
        body=geometry['bodies'][0]
        if body['scope']!=ARC_BREP_SCOPE or any(len(body[k])!=expected[n] for k,n in
            (('vertices','vertex_count'),('edges','edge_count'),('faces','face_count'))):return False
        decode=lambda raw:tuple(float.fromhex(v) for v in raw)
        close=lambda a,b:len(a)==len(b) and all(abs(x-y)<=TOLERANCE_M for x,y in zip(a,b))
        delta=lambda a,b:tuple(x-y for x,y in zip(a,b))
        dot=lambda a,b:math.fsum(x*y for x,y in zip(a,b))
        wanted=[decode(p) for p in expected['vertices_si']];mapping={}
        for i,p in enumerate(body['vertices']):
            matches=[j for j,q in enumerate(wanted) if close(decode(p),q)]
            if len(matches)!=1 or matches[0] in mapping.values():return False
            mapping[i]=matches[0]
        pairs=[frozenset((mapping[e['start']],mapping[e['end']])) for e in body['edges']]
        if len(set(pairs))!=expected['edge_count'] or set(pairs)!={frozenset(pair) for pair in expected['edge_pairs']}:return False
        arcs={frozenset(row['pair']):row for row in expected['arc_pairs']}
        frame=decode(expected['plane_transform_si']);axis=frame[6:9]
        for edge,pair in zip(body['edges'],pairs):
            if edge['kind']!=('arc' if pair in arcs else 'line'):return False
            if pair in arcs:
                target=arcs[pair];p=decode(edge['circle_parameters']);trim=edge['trimmed_curve']
                span=float.fromhex(trim['u_max'])-float.fromhex(trim['u_min'])
                if (not close(p[:3],decode(target['centre_si'])) or abs(p[6]-float.fromhex(target['radius_si']))>TOLERANCE_M
                        or abs(abs(dot(p[3:6],axis))-1.)>1e-12 or abs(span-math.pi/2.)>1e-12):return False
        faces={frozenset(poly):(poly,surface) for poly,surface in zip(expected['face_vertices'],expected['face_surfaces'])}
        for face in body['faces']:
            if len(face['loops'])!=1 or face['loops'][0]['outer'] is not True:return False
            uses=face['loops'][0]['coedges'];vertices=frozenset(mapping[u['start']] for u in uses)
            found=faces.pop(vertices,None)
            if found is None:return False
            polygon,surface=found
            if len(uses)!=len(polygon) or {pairs[u['edge']] for u in uses}!={frozenset((a,b)) for a,b in zip(polygon,polygon[1:]+polygon[:1])}:return False
            if face['surface_type']!=surface['kind']:return False
            p=decode(face['surface_parameters'])
            if surface['kind']=='plane':
                normal=tuple(-v if face['normal_opposes_surface'] else v for v in p[:3])
                if not close(normal,decode(surface['normal_si'])) or abs(dot(delta(p[3:6],decode(surface['point_si'])),normal))>TOLERANCE_M:return False
            else:
                displacement=delta(p[:3],decode(surface['centre_si']));z=dot(displacement,p[3:6])
                if (face['normal_opposes_surface'] is not surface['inward'] or abs(p[6]-float.fromhex(surface['radius_si']))>TOLERANCE_M
                    or abs(abs(dot(p[3:6],decode(surface['axis_si'])))-1.)>1e-12
                    or any(abs(v-z*n)>TOLERANCE_M for v,n in zip(displacement,p[3:6]))):return False
        return not faces
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):return False


def sheet_l_sketch_matches(snapshot,semantic,configuration,definition,plane_pid_hex,plane_transform,base_native_id):
    """Prove the complete two-line, five-relation network and its two drivers."""
    try:
        decode=lambda raw:tuple(float.fromhex(value) for value in raw)
        close=lambda a,b:len(a)==len(b) and all(math.isfinite(x) and abs(x-y)<=TOLERANCE_M for x,y in zip(a,b))
        frame=validated_plane_transform(plane_transform)
        if (snapshot['constraint_status']!=3 or snapshot['is_3d'] is not False
                or snapshot['reference_plane']['pid_hex']!=plane_pid_hex
                or decode(snapshot['reference_plane']['transform'])!=frame):return False
        local=validated_plane_transform(decode(snapshot['model_to_sketch']))
        if any(abs(local[3*i+j]-frame[3*j+i])>TOLERANCE_M for i in range(3) for j in range(3)):return False
        origin=snapshot['model_origin_point']
        if origin['point_type']!=1 or origin['constraint_status']!=2 or not close(decode(origin['coordinates_si']),(0.,0.,0.)):return False
        points={point['key']:point for point in snapshot['points']}
        if len(points)!=len(snapshot['points']) or len(points)!=4 or any(p['constraint_status']!=2 for p in points.values()):return False
        implicit=[key for key,p in points.items() if p['implicit'] is True]
        regular=[key for key,p in points.items() if p['implicit'] is False]
        if len(implicit)!=1 or len(regular)!=3:return False
        projected=implicit[0]
        if points[projected]['point_type']!=10 or not close(decode(points[projected]['coordinates_si']),(0.,0.,0.)):return False
        wanted=[(*p,0.) for p in definition.profile_m];mapping={}
        for key in regular:
            if points[key]['point_type']!=0:return False
            matches=[i for i,p in enumerate(wanted) if close(decode(points[key]['coordinates_si']),p)]
            if len(matches)!=1 or matches[0] in mapping.values():return False
            mapping[key]=matches[0]
        if set(mapping.values())!={0,1,2}:return False
        corners={v:k for k,v in mapping.items()};lines={line['key']:line for line in snapshot['segments']}
        if len(lines)!=len(snapshot['segments']) or len(lines)!=2:return False
        line_for_pair={}
        for key,line in lines.items():
            if (line['kind']!='line' or line['construction'] is not False or line['infinite'] is not False
                    or line['constraint_status']!=2 or line['start'] not in regular or line['end'] not in regular):return False
            pair=frozenset((mapping[line['start']],mapping[line['end']]))
            if pair in line_for_pair:return False
            line_for_pair[pair]=key
        if set(line_for_pair)!={frozenset((0,1)),frozenset((1,2))}:return False
        rows=[row for row in semantic['dimensions'] if row['owner'] and row['owner']['native_id']==snapshot['feature_native_id']]
        if len(rows)!=2 or len({row['full_name'] for row in rows})!=2:return False
        by_name={row['full_name']:row for row in rows};seen=set()
        if len(snapshot['relations'])!=5:return False
        for relation in snapshot['relations']:
            if relation['suppressed'] is not False:return False
            kind,entities,definitions=relation['type'],relation['entities'],relation['definitions']
            if kind in (4,5):
                segment=line_for_pair[frozenset((1,2) if kind==4 else (0,1))]
                role='horizontal' if kind==4 else 'vertical'
                if entities!=[segment] or definitions!=[segment] or relation['dimension_full_name'] is not None:return False
            elif kind==9:
                role='origin'
                if (len(entities)!=2 or set(entities)!={projected,corners[1]} or len(definitions)!=2
                        or set(definitions)!={'model_origin',corners[1]} or relation['dimension_full_name'] is not None):return False
            elif kind==1:
                axis={11:('width',2,definition.leg_x_mm/1000.,'Ширина полки'),12:('height',0,definition.leg_y_mm/1000.,'Высота полки')}.get(relation['display_type'])
                row=by_name.get(relation['dimension_full_name'])
                if axis is None or row is None:return False
                role,index,size,name=axis
                if (len(entities)!=2 or set(entities)!={projected,corners[index]} or len(definitions)!=2
                        or set(definitions)!={'model_origin',corners[index]} or row['name']!=name or row['unit']!='mm'
                        or row['owner']['owner_native_id']!=base_native_id or row['driven_state']!=2
                        or row['read_only'] or row['reference'] or row['linked'] or row['design_table']
                        or set(row['write_blockers'])-{'sketch_geometry_snapshot_not_implemented'}
                        or not math.isfinite(row['values_si'][configuration]) or abs(row['values_si'][configuration]-size)>TOLERANCE_M):return False
            else:return False
            if role in seen:return False
            seen.add(role)
        return seen=={'horizontal','vertical','origin','width','height'}
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):return False


def sheet_l_native_parameters_match(base,sheet,definition):
    """K-factor is independent native evidence; folded geometry cannot prove it.

    These readbacks are the SW2023 open-profile base-flange representation.
    Native blind direction 1 is reported as D1EndConditionType=1 by this factory.
    Other native/API representations need their own explicit interpretation.
    """
    try:
        exact_number=lambda value,wanted:type(value) in (float,int) and math.isfinite(value) and abs(value-wanted)<=1e-12
        if (base['ReverseThickness'] is not True or base['ReverseDirection'] is not False
                or base['SymmetricThickness'] is not False or base['UseDefaultBendAllowance'] is not False
                or base['UseGaugeTable'] is not False or base['UseMaterialSheetMetalParameters'] is not False
                or type(base['D1EndConditionType']) is not int or base['D1EndConditionType']!=1
                or sheet['use_material'] is not False or type(sheet['allowance_type']) is not int or sheet['allowance_type']!=2):return False
        return all(exact_number(value,wanted) for value,wanted in (
            (base['Thickness'],definition.thickness_mm/1000.),(base['BendRadius'],definition.bend_radius_mm/1000.),
            (base['D1EndConditionDistance'],definition.length_mm/1000.),(sheet['thickness'],definition.thickness_mm/1000.),
            (sheet['radius'],definition.bend_radius_mm/1000.),(sheet['k_factor'],definition.k_factor)))
    except (KeyError,TypeError,ValueError,OverflowError):return False
