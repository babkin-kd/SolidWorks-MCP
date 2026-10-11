"""Closed own flange profile; no named-plane fallback in the general reader.

The caller proves the owning sketch, configuration and anonymous plane frame.
Before factory, the projection definition is the explicit prepared CAD edge;
after factory, SolidWorks reports its exact own internal projection segment.
"""
import math
import json
from copy import deepcopy

from .documents import rejected
from .jobs import ExecutionFailure
from .linear_sketch import LinearSketchReader,_identifier,_integer
from .part_creation import validated_plane_transform


SCOPE='owned_edge_flange_input_sketch_v1'


def edge_flange_profile_preserved(before,after,before_members,after_members):
    """Compare independently proved captures across the documented factory step."""
    try:
        left,right=deepcopy(before),deepcopy(after)
        if left['factory_phase']!='before_factory' or right['factory_phase']!='after_factory':return False
        right['factory_phase']='before_factory'
        old_driver=next(r['dimension_full_name'] for r in left['relations'] if r['type']==1)
        for relation in right['relations']:
            if relation['type']==32:relation['definitions'][0]='prepared_source_edge'
            if relation['type']==1:relation['dimension_full_name']=old_driver
        for capture in (left,right):capture['relations'].sort(key=lambda r:json.dumps(r,sort_keys=True))
        def members(rows):
            return tuple(sorted(('dimension:height' if key.startswith('dimension:') else key,token)
                for key,token in rows if not key.startswith('relation:') and key!='prepared_source_edge'))
        return left==right and members(before_members)==members(after_members)
    except (KeyError,TypeError,ValueError,IndexError,StopIteration):return False


class EdgeFlangeSketchReader(LinearSketchReader):
    scope=SCOPE

    def __init__(self,sketch,*,wrap,identity,phase,source_definition=None):
        if phase not in ('before_factory','after_factory') or phase=='before_factory' and not callable(source_definition):
            raise rejected('sheet_flange_profile_phase','An explicit phase and source-edge binder are required.')
        self.sketch,self.wrap,self.identity=sketch,wrap,identity
        self.sketch_token=identity(sketch);self.origin_token=object();self.origin_snapshot=None
        self.points,self.lines,self.members={},{},{'sketch':self.sketch_token}
        self.phase,self.source_definition=phase,source_definition;self.internal=[]
        self.driver_display=None

    def _entity(self,kind,raw):
        if kind==3:
            segment=self.wrap(raw,'ISketchSegment')
            key='line:'+':'.join(map(str,_identifier(segment)))
            if key not in self.lines:
                if self.internal:raise rejected('sheet_flange_profile_external','Only one exact own internal projection segment is supported.')
                points=set(self.points)
                self._read_segment(segment)
                if set(self.points)!=points:
                    raise rejected('sheet_flange_profile_external','Projection endpoints must be the same canonical enumerated user points.')
                self.internal.append(key)
        return super()._entity(kind,raw)

    def _relation_entities(self,relation,kinds,entities,definitions):
        if _integer(relation.GetRelationType(),high=4096)!=32:
            if relation.GetRelationType()==1:
                self.driver_display=self.wrap(relation.GetDisplayDimension(),'IDisplayDimension')
            return super()._relation_entities(relation,kinds,entities,definitions)
        if tuple(kinds)!=(3,3):raise rejected('sheet_flange_profile_projection','One complete two-segment projection is required.')
        keys=[self._entity(kind,raw) for kind,raw in zip(kinds,entities)]
        if self.phase=='before_factory':
            token=self.source_definition(definitions[0])
            if token is None:raise rejected('sheet_flange_profile_projection','The projection must bind the prepared native CAD edge.')
            self.members['prepared_source_edge']=token
            return keys,['prepared_source_edge',self._entity(3,definitions[1])]
        return keys,[self._entity(3,raw) for raw in definitions]

    def read(self):
        snapshot,members=super().read()
        if len(snapshot['points'])!=4 or len(snapshot['segments'])!=5 or len(self.internal)!=1:
            raise rejected('sheet_flange_profile_scope','Four user points, four lines and one own internal projection are required.')
        for line in snapshot['segments']:line['projection_internal']=line['key']==self.internal[0]
        snapshot.update(factory_phase=self.phase,reference_policy='owned_anonymous_plane_geometry_v1')
        return snapshot,members


def edge_flange_sketch_matches(snapshot,definition,frame):
    """Full rectangle and five-relation topology, not status/box alone.

Dimension ownership, native identity and finite system value are independently
checked by the caller's complete dimension capture and receipt.
"""
    try:
        decode=lambda values:tuple(float.fromhex(v) for v in values)
        close=lambda a,b:len(a)==len(b) and all(math.isfinite(x) and math.isfinite(y) and abs(x-y)<=1e-9 for x,y in zip(a,b))
        if (snapshot['scope']!=SCOPE or snapshot['is_3d'] is not False or type(snapshot['constraint_status']) is not int
                or snapshot['constraint_status']!=3 or snapshot['reference_policy']!='owned_anonymous_plane_geometry_v1'):return False
        frame=validated_plane_transform(frame);local=decode(snapshot['model_to_sketch'])
        rigid=list(local);rigid[9:12]=[0.,0.,0.];validated_plane_transform(rigid)
        # The positive sketch Y direction must create material towards source X;
        # either orientation of the longitudinal source Z edge is admissible.
        sign=next((s for s in (1.,-1.) if close(local[:9],tuple(v for i in range(3)
            for v in (s*frame[6+i],frame[i],s*frame[3+i])))),None)
        if sign is None:return False
        def world(v):return tuple(sum(v[k]*frame[3*k+j] for k in range(3))+frame[9+j] for j in range(3))
        def to_sketch(v):return tuple(sum(v[k]*local[3*k+j] for k in range(3))+local[9+j] for j in range(3))
        t=definition.source.thickness_mm/1000.;h=definition.source.leg_y_mm/1000.;length=definition.source.length_mm/1000.
        base=[to_sketch(world((t,h,z))) for z in (0.,length)]
        if not all(close(p[1:],(0.,0.)) for p in base) or not any(abs(p[0])<=1e-9 for p in base):return False
        if not math.isclose(abs(base[0][0]-base[1][0]),length,rel_tol=0.,abs_tol=1e-9):return False
        height=definition.profile_height_mm/1000.
        wanted=[*base,*( (p[0],height,0.) for p in base)]
        points={p['key']:p for p in snapshot['points']}
        if len(points)!=4 or len(snapshot['points'])!=4:return False
        mapping={}
        for key,p in points.items():
            if p['point_type']!=0 or type(p['constraint_status']) is not int or p['constraint_status']!=2 or p['implicit'] is not False:return False
            matches=[i for i,v in enumerate(wanted) if close(decode(p['coordinates_si']),v)]
            if len(matches)!=1 or matches[0] in mapping.values():return False
            mapping[key]=matches[0]
        lines={line['key']:line for line in snapshot['segments']}
        if len(lines)!=5 or len(snapshot['segments'])!=5:return False
        pairs={};internal=[]
        for key,line in lines.items():
            if (line['kind']!='line' or line['construction'] is not False or line['infinite'] is not False
                    or type(line['constraint_status']) is not int or line['constraint_status']!=2
                    or line['start'] not in mapping or line['end'] not in mapping
                    or type(line['projection_internal']) is not bool):return False
            pair=frozenset((mapping[line['start']],mapping[line['end']]))
            if line['projection_internal']:
                if pair!=frozenset((0,1)):return False
                internal.append(key)
            else:
                if pair in pairs:return False
                pairs[pair]=key
        required={frozenset(p) for p in ((0,1),(0,2),(1,3),(2,3))}
        if len(internal)!=1 or set(pairs)!=required:return False
        bottom=pairs[frozenset((0,1))];top=pairs[frozenset((2,3))]
        vertical={pairs[frozenset((0,2))],pairs[frozenset((1,3))]}
        anchor=lines[bottom]['end'];corner=mapping[anchor]+2
        raised=next(key for key,index in mapping.items() if index==corner)
        relations=snapshot['relations']
        if len(relations)!=5 or any(r['suppressed'] is not False or r['entities']!=r['definitions'] and r['type']!=32 for r in relations):return False
        def plain(r):return r['dimension_full_name'] is None and r['display_type'] is None
        projection=[r for r in relations if r['type']==32]
        phase=snapshot['factory_phase']
        if phase not in ('before_factory','after_factory') or len(projection)!=1:return False
        definitions=['prepared_source_edge',bottom] if phase=='before_factory' else [internal[0],bottom]
        if projection[0]['entities']!=[internal[0],bottom] or projection[0]['definitions']!=definitions or not plain(projection[0]):return False
        vr=[r for r in relations if r['type']==5]
        hr=[r for r in relations if r['type']==4];dr=[r for r in relations if r['type']==1]
        if len(vr)!=2 or any(len(r['entities'])!=1 or not plain(r) for r in vr) or {r['entities'][0] for r in vr}!=vertical:return False
        if len(hr)!=1 or hr[0]['entities']!=[top] or not plain(hr[0]):return False
        return (len(dr)==1 and dr[0]['entities']==[raised,anchor] and dr[0]['display_type']==12
            and type(dr[0]['dimension_full_name']) is str and dr[0]['dimension_full_name'].startswith('Вылет от внутреннего ребра@'))
    except (KeyError,TypeError,ValueError,IndexError,StopIteration,ExecutionFailure,OverflowError):return False
