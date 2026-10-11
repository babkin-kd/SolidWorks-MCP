"""Explicit edge flange on a proved folded L sheet and scoped durable mutation."""

import math
import re
from dataclasses import asdict
from copy import deepcopy

from .documents import rejected
from .features import russian_name
from .geometry import GeometryCatalog
from .part_creation import _positive_length
from .sheet_parameters import SheetParameterCatalog
from .sheet_edge_flange_definition import EdgeFlangeOnL,SCOPE,flange_revision,l_flange_edge_points
from .sheet_edge_flange_definition import sheet_u_body_matches
from .sheet_profile_definition import sheet_l_body_matches
from .sheet_edge_flange_parameters import native_flange_parameters_match
from .edge_flange_sketch import edge_flange_sketch_matches
from .dimensions import DimensionCatalog
from .jobs import ExecutionFailure
from .mutations import PreparedMutation
from .sketches import persistent_sketch_members


def flange_request(base_object_id,edge_id,flange_length_mm,bend_radius_mm,k_factor,
        sketch_name='Эскиз отбортовки',feature_name='Отбортовка'):
    SheetParameterCatalog._arguments(base_object_id,False)
    if type(edge_id) is not str or re.fullmatch(r'obj_[0-9a-f]{32}',edge_id) is None:
        raise rejected('invalid_sheet_flange_edge','An explicit opaque current edge reference is required.')
    length=_positive_length(flange_length_mm,'flange_length_mm')
    radius=_positive_length(bend_radius_mm,'bend_radius_mm')
    if max(length,radius)>10000000.:
        raise rejected('sheet_parameter_out_of_range','Flange parameters exceed the bounded native capture.')
    if type(k_factor) not in (float,int) or not math.isfinite(k_factor) or not 0.<=k_factor<=1.:
        raise rejected('invalid_sheet_k_factor','An explicit finite second-bend K-factor between zero and one is required.')
    names=[russian_name(sketch_name),russian_name(feature_name),'Сгиб отбортовки','Развёртка сгиба отбортовки']
    if len({name.casefold() for name in names})!=4:
        raise rejected('sheet_name_collision','All four created nodes must have distinct Russian names.')
    return dict(base_object_id=base_object_id,edge_id=edge_id,flange_length_mm=length,
        bend_radius_mm=radius,k_factor=float(k_factor),sketch_name=names[0],feature_name=names[1])


class SheetEdgeFlangeCatalog(SheetParameterCatalog):
    def __init__(self,dimensions):
        super().__init__(dimensions)
        self.geometry=GeometryCatalog(dimensions.documents)

    def _prepare_edge_flange(self,document_id,configuration,*,retained=None,**arguments):
        request=flange_request(**arguments)
        captured=self._capture(document_id,configuration,request['base_object_id'],retained)
        capture,target,state,_,source,_,_=captured
        if state['evidence']['flattened'] is not False:
            raise rejected('sheet_flange_source_flat','Fold the explicitly targeted L sheet before creating an edge flange.')
        if state['evidence']['fixed_leg']!='x':
            raise rejected('sheet_flange_fixed_face_unsupported','This first flange scope requires the original horizontal fixed leg.')
        definition=EdgeFlangeOnL.validate(source,request['flange_length_mm'],request['bend_radius_mm'],request['k_factor'],
            request['sketch_name'],request['feature_name'])
        names={row['name'].casefold() for row in state['semantic']['tree']['features']}
        if any(name.casefold() in names for name in (definition.sketch_name,definition.feature_name,
                'Сгиб отбортовки','Развёртка сгиба отбортовки')):
            raise rejected('sheet_name_collision','A requested new Russian node name already exists in the model.')
        entry,identity=capture.state[:2]
        edge,reference=self.geometry._resolve(entry,request['edge_id'],configuration,identity,'edge')
        body=self.adapter.resolve_persistent_id(entry.model,target.body_pid,'body')
        if reference.body_id is None or self.adapter.identity(self.adapter.owner_body(edge,'edge'))!=self.adapter.identity(body):
            raise rejected('sheet_flange_edge_membership','The explicit edge must bind the same retained sole source body.')
        points=self.adapter.pattern_edge_points(edge)
        frame=state['evidence']['plane_transform'];controls=state['evidence']['controls']
        if not l_flange_edge_points(points,source,frame):
            raise rejected('sheet_flange_edge_unsupported','Select the full longitudinal free edge on the inner face of the vertical leg.')
        revision=flange_revision(state,definition,document_id=document_id,configuration=configuration,
            base_object_id=request['base_object_id'],edge_pid_hex=reference.persistent_id.hex(),points=points,controls=controls)
        self.dimensions._close_native_proof(entry,capture.event_sequence)
        available=callable(getattr(self,'create_edge_flange',None)) and all(callable(getattr(self.adapter,name,None)) for name in (
            'new_sheet_flange_receipt','create_sheet_edge_flange','sheet_flange_bundle','sheet_flange_preserve_names',
            'sheet_edge_flange_evidence','restore_sheet_edge_flange'))
        public=dict(document_id=document_id,configuration=configuration,**request,revision_scope=SCOPE,revision=revision,
            source_parameters=asdict(source),expected_geometry=definition.expected_geometry(frame),
            expected_volume_mm3=definition.volume_mm3,expected_area_mm2=definition.surface_area_mm2,
            native_change_available=available)
        return public,captured,definition,edge,reference

    def prepare_edge_flange(self,document_id,configuration,**arguments):
        return self._prepare_edge_flange(document_id,configuration,**arguments)[0]

    def _inspect_flange(self,document_id,configuration,captured,definition,receipt,base_object_id):
        if receipt is not None and any(getattr(receipt,key,False) for key in ('pending_creation','pending_deletion','selection_uncertain')):
            raise rejected('sheet_flange_outcome_unconfirmed','Pending creation, deletion or selection cannot be adopted as an unchanged original state.')
        if receipt is None or receipt.restored or receipt.sketch is None:
            return dict(phase='original',state=self._capture(document_id,configuration,
                base_object_id,captured[1])[2])
        results=[]
        for _ in range(2):
            current=self.dimensions._capture(document_id,configuration)
            evidence,members=self.adapter.sheet_edge_flange_evidence(current.state[0].model,receipt,definition,
                captured[2]['evidence']['plane_transform'])
            results.append((current,evidence,members))
        a,b=results;left,right=deepcopy(a[1]),deepcopy(b[1])
        same=self.dimensions._same_capture(a[0],b[0]) and persistent_sketch_members(a[2])==persistent_sketch_members(b[2])
        for key in ('volume_mm3','area_mm2'):
            same=same and math.isclose(left['source'].pop(key),right['source'].pop(key),rel_tol=1e-10,abs_tol=1e-8)
        self.dimensions._close_capture_pair(a[0],b[0])
        if not same or left!=right:raise rejected('sheet_flange_changed','Two complete closing flange captures disagree.')
        return dict(phase=b[1]['created']['phase'],semantic=b[0].state[3],evidence=b[1])

    @staticmethod
    def _transition(before,after,definition,configuration,*,allow_names=False):
        try:
            phase=after['phase'];created=after['evidence']['created'];source=after['evidence']['source']
            if phase not in ('input','completed') or created['phase']!=phase or created['complete'] is not True:return False
            frame=before['evidence']['plane_transform']
            if not edge_flange_sketch_matches(created['profile'],definition,frame):return False
            if not math.isclose(float.fromhex(created['profile']['driver_value_si']),definition.profile_height_mm/1000.,rel_tol=0.,abs_tol=1e-12):return False
            original=deepcopy(before['evidence']);current=deepcopy(source)
            original.pop('fixed_leg')
            for row in (original,current):row.pop('volume_mm3');row.pop('area_mm2')
            if allow_names:
                current['body_name']=original['body_name']
                for m in current['members']:
                    if m['role']=='cut_list':m['name']=next(r['name'] for r in original['members'] if r['role']=='cut_list')
            if original!=current:return False
            own=created['owned'];by_role={r['role']:r for r in own}
            required={'profile':'ProfileFeature'} if phase=='input' else dict(profile='ProfileFeature',flange='EdgeFlange',bend='OneBend',flat_bend='UiBend')
            if len(own)!=len(required) or set(by_role)!=set(required) or len({r['native_id'] for r in own})!=len(own):return False
            if any(r['feature_type']!=required[r['role']] or not r['pid_hex'] or r['error_code'] or r['is_warning'] or r['suppressed'] for r in own):return False
            if phase=='completed':
                flange=by_role['flange']['native_id'];flat=next(r['native_id'] for r in source['members'] if r['role']=='flat')
                if (by_role['flange']['owner_native_id'] is not None or by_role['profile']['owner_native_id']!=flange
                        or by_role['bend']['owner_native_id']!=flange or by_role['flat_bend']['owner_native_id']!=flat
                        or not native_flange_parameters_match(created['parameters'],definition)):return False
                if not allow_names and any(by_role[role]['name']!=name for role,name in dict(profile=definition.sketch_name,
                        flange=definition.feature_name,bend='Сгиб отбортовки',flat_bend='Развёртка сгиба отбортовки').items()):return False
                expected=definition.expected_geometry(frame)
                if not sheet_u_body_matches(after['semantic']['geometry'],expected):return False
                volume,area=definition.volume_mm3,definition.surface_area_mm2
            else:
                if by_role['profile']['owner_native_id'] is not None or created['parameters'] is not None:return False
                if not sheet_l_body_matches(after['semantic']['geometry'],definition.source.expected_geometry(frame)):return False
                volume,area=definition.source.volume_mm3,definition.source.surface_area_mm2
            if (not math.isclose(source['volume_mm3'],volume,rel_tol=1e-7,abs_tol=1e-8)
                    or not math.isclose(source['area_mm2'],area,rel_tol=1e-7,abs_tol=1e-8)):return False
            previous=DimensionCatalog._comparable(before['semantic'],ignore_geometry=True)
            semantic=DimensionCatalog._comparable(after['semantic'],ignore_geometry=True)
            ids={r['native_id'] for r in own};old_ids={r['native_id'] for r in previous['tree']['features']}
            rows=semantic['tree']['features'];extra=[r for r in rows if r['native_id'] not in old_ids]
            if sorted(extra,key=lambda r:r['native_id'])!=sorted(({k:v for k,v in r.items() if k not in ('role','pid_hex')} for r in own),key=lambda r:r['native_id']):return False
            semantic['tree']['features']=[r for r in rows if r['native_id'] not in ids]
            profile_id=by_role['profile']['native_id'];drivers=[r for r in semantic['dimensions'] if r['owner'] and r['owner']['native_id']==profile_id]
            if len(drivers)!=1:return False
            driver=drivers[0];relation=next(r for r in created['profile']['relations'] if r['type']==1)
            if (driver['full_name']!=relation['dimension_full_name'] or driver['unit']!='mm' or driver['driven_state']!=2
                    or any(driver[k] for k in ('read_only','reference','design_table','linked'))
                    or not math.isclose(driver['values_si'][configuration],definition.profile_height_mm/1000.,rel_tol=0.,abs_tol=1e-12)):return False
            own_dimensions=list(drivers)
            if phase=='completed':
                bend=by_role['bend']
                bend_dimensions=[r for r in semantic['dimensions'] if r['owner'] and r['owner']['native_id']==bend['native_id']]
                if len(bend_dimensions)!=2 or sorted(r['parameter_type'] for r in bend_dimensions)!=[0,1]:return False
                for row in bend_dimensions:
                    kind=row['parameter_type'];owner=row['owner']
                    if type(kind) is not int or any(owner[k]!=bend[k] for k in ('native_id','name','feature_type',
                            'owner_native_id','suppressed','error_code','is_warning')):return False
                    if owner['frozen'] or owner['rolled_back'] or row['driven_state']!=2:return False
                    if any(row[k] for k in ('read_only','reference','design_table','linked')):return False
                    expected_value=definition.bend_radius_mm/1000. if kind==0 else math.pi/2.
                    if (row['unit']!=('mm' if kind==0 else 'deg')
                            or set(row['values_si'])!={configuration}
                            or not math.isclose(row['values_si'][configuration],expected_value,rel_tol=0.,abs_tol=1e-12)
                            or row['display_dimensions']!=[dict(type=5 if kind==0 else 3,linked=False,linked_text='')]
                            or row['tolerance']!=dict(type=0,values_si=[])):return False
                own_dimensions.extend(bend_dimensions)
            semantic['dimensions']=[r for r in semantic['dimensions'] if r not in own_dimensions]
            if allow_names:
                cut=next(r['native_id'] for r in original['members'] if r['role']=='cut_list')
                for row in semantic['tree']['features']:
                    if row['native_id']==cut:row['name']=next(r['name'] for r in previous['tree']['features'] if r['native_id']==cut)
            return semantic==previous
        except (KeyError,TypeError,ValueError,IndexError,StopIteration,ExecutionFailure,OverflowError):return False

    def create_edge_flange(self,operation_id,document_id,configuration,expected_revision,**arguments):
        request=flange_request(**arguments)
        if self.dimensions.mutation_guard is None:raise rejected('mutation_guard_unavailable','An owning-STA mutation guard is required.')
        target={}
        def prepare():
            public,captured,definition,edge,reference=self._prepare_edge_flange(document_id,configuration,**request)
            if not public['native_change_available']:raise rejected('sheet_flange_native_unavailable','The complete native flange implementation is not connected.')
            target.update(captured=captured,definition=definition,edge=edge,edge_reference=reference)
            return PreparedMutation(public['revision'],captured[2])
        def validate(prepared):
            public,captured,_,edge,reference=self._prepare_edge_flange(document_id,configuration,retained=target['captured'][1],**request)
            return (public['revision']==prepared.revision and self.adapter.identity(edge)==self.adapter.identity(target['edge'])
                and self.adapter.same_persistent_id(captured[0].state[0].model,reference.persistent_id,target['edge_reference'].persistent_id)
                and persistent_sketch_members(captured[3])==persistent_sketch_members(target['captured'][3]))
        def inspect(prepared):return self._inspect_flange(document_id,configuration,target['captured'],target['definition'],target.get('receipt'),request['base_object_id'])
        def apply(prepared):
            captured=target['captured'];model=captured[0].state[0].model
            target['receipt']=self.adapter.new_sheet_flange_receipt(model,captured[1],target['edge'])
            captured[0].state[0].features['mutation_sequence']=captured[0].state[0].features.get('mutation_sequence',0)+1
            self.adapter.create_sheet_edge_flange(model,target['definition'],prepared.before['evidence']['plane_transform'],target['receipt'])
            current=inspect(prepared)
            if not self._transition(prepared.before,current,target['definition'],configuration,allow_names=True):
                raise rejected('sheet_flange_transition_unproved','The full intended flange transition must precede name preservation.')
            old=prepared.before['evidence'];cut=next(r['name'] for r in old['members'] if r['role']=='cut_list')
            self.adapter.sheet_flange_preserve_names(model,target['receipt'],target['definition'],old['plane_transform'],old['body_name'],cut)
            return dict(**request,source_k_factor=target['definition'].source.k_factor)
        def restore(before,prepared):
            receipt=target.get('receipt')
            current=inspect(prepared)
            if current['phase']=='original':
                if not self._parameter_transition(before,current['state'],target['captured'][4]):raise rejected('sheet_flange_restore_unsafe','The original state changed.')
                return
            if receipt is None:raise rejected('sheet_flange_restore_unsafe','A missing receipt cannot authorize deletion.')
            if not self._transition(before,current,target['definition'],configuration,allow_names=True):raise rejected('sheet_flange_restore_unsafe','Only the complete proved own transition permits scoped restoration.')
            old=before['evidence'];cut=next(r['name'] for r in old['members'] if r['role']=='cut_list')
            self.adapter.restore_sheet_edge_flange(target['captured'][0].state[0].model,receipt,target['definition'],old['plane_transform'],old['body_name'],cut)
        return self.dimensions.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=prepare,validate=validate,apply=apply,inspect=inspect,
            verify=lambda before,after,value:after['phase']=='completed' and self._transition(before,after,target['definition'],configuration),restore=restore,
            verify_restored=lambda before,after:after['phase']=='original' and self._parameter_transition(before,after['state'],target['captured'][4]),
            guard=lambda prepared:self.dimensions.mutation_guard(target['captured'][0].state[0].model))
