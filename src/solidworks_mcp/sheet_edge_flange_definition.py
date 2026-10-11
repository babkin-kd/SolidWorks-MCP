"""Independent full two-bend U boundary for a native edge flange on an L sheet.

No CAD mutation or public tool registration. Outer-virtual-sharp length and
material-inside position are explicit; the base profile remains the source.
"""

from dataclasses import dataclass
from dataclasses import asdict
from copy import deepcopy
import hashlib
import math

from .documents import rejected
from .features import russian_name
from .part_creation import _positive_length,validated_plane_transform
from .sheet_profile_definition import SheetLProfile,sheet_l_body_matches
from .jobs import _json


SCOPE='single_l_sheet_edge_flange_v1'


@dataclass(frozen=True)
class EdgeFlangeOnL:
    source:SheetLProfile
    flange_length_mm:float
    bend_radius_mm:float
    k_factor:float
    sketch_name:str='Эскиз отбортовки'
    feature_name:str='Отбортовка'

    @classmethod
    def validate(cls,source,flange_length_mm,bend_radius_mm,k_factor,
            sketch_name='Эскиз отбортовки',feature_name='Отбортовка'):
        if not isinstance(source,SheetLProfile):raise rejected('invalid_sheet_flange_source','A complete proven L-sheet definition is required.')
        # Revalidate the material dimensions while retaining existing names.
        SheetLProfile.validate(plane_object_id=source.plane_object_id,leg_x_mm=source.leg_x_mm,
            leg_y_mm=source.leg_y_mm,length_mm=source.length_mm,thickness_mm=source.thickness_mm,
            bend_radius_mm=source.bend_radius_mm,k_factor=source.k_factor)
        length=_positive_length(flange_length_mm,'flange_length_mm');radius=_positive_length(bend_radius_mm,'bend_radius_mm')
        if max(length,radius)>10000000.:raise rejected('sheet_parameter_out_of_range','Flange dimensions exceed the bounded complete capture.')
        if type(k_factor) not in (int,float) or not math.isfinite(k_factor) or not 0.<=k_factor<=1.:
            raise rejected('invalid_sheet_k_factor','An explicit finite second-bend K-factor between zero and one is required.')
        lower=source.bend_radius_mm+source.thickness_mm;upper=radius+source.thickness_mm
        if source.leg_y_mm-lower-upper<.001 or length-upper<.001:
            raise rejected('sheet_flange_no_straight_leg','Both the shared vertical leg and new flange must retain at least 0.001 mm beyond the bends.')
        names=tuple(map(russian_name,(sketch_name,feature_name)))
        if names[0].casefold()==names[1].casefold():raise rejected('sheet_name_collision','The new sketch and flange require distinct Russian names.')
        return cls(source,length,radius,float(k_factor),*names)

    @property
    def profile_height_mm(self):
        """Height from the converted inner edge to the new outer end.

        Native OffsetDistance is driven by this profile, so seeding the outer
        virtual-sharp length directly would add one sheet thickness to it.
        """
        return self.flange_length_mm-self.source.thickness_mm

    @property
    def section_mm2(self):
        p=self.source;t=p.thickness_mm;r1=p.bend_radius_mm;r2=self.bend_radius_mm;s1=r1+t;s2=r2+t
        straight=p.leg_x_mm+p.leg_y_mm+self.flange_length_mm-2.*s1-2.*s2
        return t*straight+math.pi/4.*(s1*s1-r1*r1+s2*s2-r2*r2)

    @property
    def volume_mm3(self):return self.section_mm2*self.source.length_mm

    @property
    def surface_area_mm2(self):
        p=self.source;t=p.thickness_mm;r1=p.bend_radius_mm;r2=self.bend_radius_mm;s1=r1+t;s2=r2+t
        straight=p.leg_x_mm+p.leg_y_mm+self.flange_length_mm-2.*s1-2.*s2
        perimeter=2.*straight+2.*t+math.pi/2.*(s1+r1+s2+r2)
        return 2.*self.section_mm2+perimeter*p.length_mm

    @property
    def developed_length_mm(self):
        p=self.source;t=p.thickness_mm;r1=p.bend_radius_mm;r2=self.bend_radius_mm
        return (p.leg_x_mm+p.leg_y_mm+self.flange_length_mm-2.*(r1+t)-2.*(r2+t)
            +math.pi/2.*(r1+p.k_factor*t+r2+self.k_factor*t))

    def expected_geometry(self,plane_transform):
        frame=validated_plane_transform(plane_transform);p=self.source
        w,h,d,t,r1,r2,f=(v/1000. for v in (p.leg_x_mm,p.leg_y_mm,p.length_mm,p.thickness_mm,
            p.bend_radius_mm,self.bend_radius_mm,self.flange_length_mm));s1=r1+t;s2=r2+t
        profile=[(0.,h-s2),(0.,s1),(s1,0.),(w,0.),(w,t),(s1,t),(t,s1),
            (t,h-s2),(s2,h-t),(f,h-t),(f,h),(s2,h)]
        model=lambda q:[math.fsum([q[j]*frame[3*j+i] for j in range(3)]+[frame[9+i]]).hex() for i in range(3)]
        vertices=[model((x,y,z)) for z in (0.,d) for x,y in profile]
        sections=[[0,1,6,7],[1,2,5,6],[2,3,4,5],[7,8,11,0],[8,9,10,11]]
        polygons=sections+[[v+12 for v in face] for face in sections]+[[i,(i+1)%12,(i+1)%12+12,i+12] for i in range(12)]
        pairs=sorted({tuple(sorted((a,b))) for face in polygons for a,b in zip(face,face[1:]+face[:1])})
        curves={1:(s1,s1,s1,False),5:(s1,s1,r1,True),7:(s2,h-s2,r2,True),11:(s2,h-s2,s2,False)}
        arcs=[dict(pair=(i+12*end,(i+1)%12+12*end),radius_si=radius.hex(),
            centre_si=model((cx,cy,end*d)),role=('inner' if inward else 'outer'))
            for i,(cx,cy,radius,inward) in curves.items() for end in (0,1)]
        surfaces=[]
        for end in (0,1):surfaces.extend([dict(kind='plane',normal_si=[((1. if end else -1.)*v).hex() for v in frame[6:9]],
            point_si=model((0.,0.,end*d))) for _ in sections])
        for i,(a,b) in enumerate(zip(profile,profile[1:]+profile[:1])):
            if i in curves:
                cx,cy,radius,inward=curves[i]
                surfaces.append(dict(kind='cylinder',centre_si=model((cx,cy,0.)),axis_si=[v.hex() for v in frame[6:9]],
                    radius_si=radius.hex(),inward=inward))
            else:
                dx,dy=b[0]-a[0],b[1]-a[1];norm=math.hypot(dx,dy)
                surfaces.append(dict(kind='plane',normal_si=[(math.fsum((dy*frame[j],-dx*frame[3+j]))/norm).hex() for j in range(3)],
                    point_si=model((*a,0.))))
        return dict(volume_mm3=self.volume_mm3,surface_area_mm2=self.surface_area_mm2,solid_body_count=1,
            vertex_count=24,edge_count=44,face_count=22,vertices_si=vertices,edge_pairs=pairs,arc_pairs=arcs,
            face_vertices=polygons,face_surfaces=surfaces,plane_transform_si=[v.hex() for v in frame],
            neutral_axis_developed_length_mm=self.developed_length_mm)


def sheet_u_body_matches(geometry,expected):
    """The existing complete mixed-boundary matcher is independent of census."""
    if (expected.get('vertex_count'),expected.get('edge_count'),expected.get('face_count'))!=(24,44,22):return False
    return sheet_l_body_matches(geometry,expected)


def l_flange_edge_points(points,source,plane_transform,*,edge_side='inner'):
    """Prove a full longitudinal edge on the requested side of the free end.

    The caller must separately prove the complete source body and the selected
    edge's current persistent membership in that body. Coordinates alone never
    authorize a mutation. The U scenario selects the inner-face edge; the outer
    side is a separate direction. Bend seams and partial edges are refused.
    """
    frame=validated_plane_transform(plane_transform)
    try:
        if len(points)!=2 or any(len(point)!=3 for point in points):raise ValueError()
        actual=tuple(tuple(v for v in point) for point in points)
        if any(type(v) not in (int,float) or not math.isfinite(v) for point in actual for v in point):raise ValueError()
        if edge_side not in ('inner','outer'):raise ValueError()
        h,d=source.leg_y_mm/1000.,source.length_mm/1000.;x=source.thickness_mm/1000. if edge_side=='inner' else 0.
        model=lambda q:tuple(math.fsum([q[j]*frame[3*j+i] for j in range(3)]+[frame[9+i]]) for i in range(3))
        expected=(model((x,h,0.)),model((x,h,d)))
        close=lambda a,b:all(abs(x-y)<=1e-12 for x,y in zip(a,b))
        if not (all(close(a,b) for a,b in zip(actual,expected)) or all(close(a,b) for a,b in zip(actual,reversed(expected)))):raise ValueError()
        return expected
    except (ValueError,TypeError,AttributeError):
        raise rejected('sheet_flange_edge_unsupported','The exact full longitudinal edge on the requested side of the proven vertical free end is required.')


def flange_revision(state,definition,*,document_id,configuration,base_object_id,edge_pid_hex,points,controls):
    """Hash a fully proven closing L capture and the exact requested new effect.

    The caller validates both source captures and their independent mass/area
    before this helper. Redundant native mass round-off is not identity; the full
    analytical body, current members, drivers and all native options remain.
    """
    source=deepcopy(state)
    if source['evidence']['flattened'] is not False:
        raise rejected('sheet_flange_source_flat','Native edge-flange creation requires the source folded state.')
    source['evidence'].pop('volume_mm3');source['evidence'].pop('area_mm2')
    frame=source['evidence']['plane_transform'];l_flange_edge_points(points,definition.source,frame)
    payload=dict(scope=SCOPE,document_id=document_id,configuration=configuration,base_object_id=base_object_id,
        source=source,definition=asdict(definition),edge_pid_hex=edge_pid_hex,points=points,controls=controls,
        expected_geometry=definition.expected_geometry(frame))
    return 'rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
