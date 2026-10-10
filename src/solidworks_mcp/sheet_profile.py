"""Explicit empty-part folded sheet mutation, full geometry and ownership proof."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import math

from .dimensions import DimensionCatalog
from .documents import rejected
from .jobs import _json
from .mutations import PreparedMutation
from .part_creation import PartCreationCatalog,validated_plane_transform
from .sketches import persistent_sketch_members
from .sheet_profile_definition import (AUXILIARY_SCHEMA,SCOPE,SheetLProfile,
    sheet_l_body_matches,sheet_l_sketch_matches,sheet_l_native_parameters_match)


class SheetProfileCatalog(PartCreationCatalog):
    def prepare_l_profile(self,document_id,configuration,**parameters):
        definition=SheetLProfile.validate(**parameters)
        public=self._prepare_base(document_id,configuration,definition,SCOPE)
        capture=self.dimensions._paired_capture(document_id,configuration)
        entry=capture.state[0]
        empty=self.adapter.sheet_profile_empty_state(entry.model)
        self.dimensions._close_native_proof(entry,capture.event_sequence)
        if capture.state[4]!=public['dimension_revision']:
            raise rejected('sheet_changed_after_preparation','Complete empty-part state changed before sheet preparation closed.')
        if empty!=dict(sheet_folder_present=False,flat_folder_present=False):
            raise rejected('sheet_template_not_empty','Existing sheet/flat template folders are outside the initial empty-part scope.')
        public['expected_geometry']=definition.expected_geometry(public['plane_transform'])
        public['sheet_template_state']=empty
        payload={key:value for key,value in public.items() if key!='revision'}
        public['revision']='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        return public

    def _inspect(self,document_id,configuration,receipt):
        captures=[]
        for _ in range(2):
            capture=self.dimensions._capture(document_id,configuration)
            evidence,members=self.adapter.sheet_profile_evidence(capture.state[0].model,receipt)
            captures.append((capture,evidence,members))
        first,second=captures;rows=[]
        for _,evidence,_ in captures:
            row=deepcopy(evidence);row.pop('volume_mm3',None);row.pop('surface_area_mm2',None);rows.append(row)
        same=(self.dimensions._same_capture(first[0],second[0]) and rows[0]==rows[1]
            and persistent_sketch_members(first[2])==persistent_sketch_members(second[2]))
        for key in ('volume_mm3','surface_area_mm2'):
            if key in first[1] or key in second[1]:
                same=same and math.isclose(first[1].get(key,-1.),second[1].get(key,-2.),rel_tol=1e-10,abs_tol=1e-8)
        self.dimensions._close_native_proof(second[0].state[0],second[0].event_sequence)
        if not same:raise rejected('sheet_changed_during_inspection','Complete body, profile, native parameters or owned members changed during closing captures.')
        return dict(semantic=second[0].state[3],revision=second[0].state[4],created=second[1])

    @staticmethod
    def _baseline_unchanged(before,after):
        old=before['semantic'];current=deepcopy(after['semantic'])
        ids={row['native_id'] for row in old['tree']['features']}
        current['tree']['features']=[row for row in current['tree']['features'] if row['native_id'] in ids]
        current['dimensions']=[]
        return DimensionCatalog._comparable(old,ignore_geometry=True)==DimensionCatalog._comparable(current,ignore_geometry=True)

    @staticmethod
    def _owned_features(before,after,definition):
        evidence=after['created'];auxiliary=evidence.get('auxiliary',[])
        if len(auxiliary)!=10 or {row['role'] for row in auxiliary}!=set(AUXILIARY_SCHEMA):return False
        old_ids={row['native_id'] for row in before['semantic']['tree']['features']}
        expected={evidence['sketch_native_id']:(definition.sketch_name,'ProfileFeature',False),
            evidence['base_native_id']:(definition.feature_name,'SMBaseFlange',False)}
        owned_ids=set(expected)
        for row in auxiliary:
            if (row['native_id'] in old_ids or row['native_id'] in owned_ids or row['error_code'] or row['is_warning']
                    or (row['name'],row['feature_type'],row['suppressed'])!=AUXILIARY_SCHEMA[row['role']]):return False
            owned_ids.add(row['native_id'])
            strategy='owned_absorption_v1' if row['role']=='fold_sketch_folder' else 'owned_persistent_feature_v1'
            if row['reference_strategy']!=strategy or (strategy=='owned_persistent_feature_v1' and not row['pid_hex']):return False
            if row['role'] not in ('sheet_folder','flat_folder'):
                expected[row['native_id']]=AUXILIARY_SCHEMA[row['role']]
        if owned_ids & old_ids:return False
        added=[row for row in after['semantic']['tree']['features'] if row['native_id'] not in old_ids]
        return (len(added)==len(expected) and not any(row['error_code'] or row['is_warning'] for row in added)
            and {row['native_id']:(row['name'],row['feature_type'],row['suppressed']) for row in added}==expected)

    @staticmethod
    def _valid_profile(before,after,definition,configuration):
        evidence=after['created'];rows=after['semantic']['dimensions']
        if len(rows)!=3 or not sheet_l_sketch_matches(evidence['sketch'],after['semantic'],configuration,definition,
                before['plane_persistent_id_hex'],before['plane_transform'],evidence['base_native_id']):return False
        length=[row for row in rows if row['name']=='Длина профиля']
        if len(length)!=1:return False
        row=length[0]
        return (row['owner'] is not None and row['owner']['native_id']==evidence['base_native_id']
            and row['owner']['feature_type']=='SMBaseFlange' and row['unit']=='mm' and row['driven_state']==2
            and not any(row[key] for key in ('read_only','reference','linked','design_table'))
            and not set(row['write_blockers'])-{'owner_type_not_accepted'}
            and math.isfinite(row['values_si'][configuration])
            and abs(row['values_si'][configuration]-definition.length_mm/1000.)<=1e-12)

    def _verify(self,before,after,definition,configuration):
        evidence=after['created']
        return (evidence.get('complete') is True and evidence.get('fully_defined') is True
            and evidence['controls']==before['creation_controls'] and evidence['body_name']==definition.body_name
            and bool(evidence['body_pid_hex']) and self._baseline_unchanged(before,after)
            and self._owned_features(before,after,definition) and self._valid_profile(before,after,definition,configuration)
            and sheet_l_body_matches(after['semantic']['geometry'],before['expected_geometry'])
            and sheet_l_native_parameters_match(evidence['base_parameters'],evidence['sheet_parameters'],definition)
            and math.isclose(evidence['volume_mm3'],definition.volume_mm3,rel_tol=1e-7,abs_tol=1e-8)
            and math.isclose(evidence['surface_area_mm2'],definition.surface_area_mm2,rel_tol=1e-7,abs_tol=1e-8))

    def create_l_profile(self,operation_id,document_id,configuration,expected_revision,**parameters):
        definition=SheetLProfile.validate(**parameters)
        if self.dimensions.mutation_guard is None:raise rejected('mutation_guard_unavailable','An owning-STA native model guard is required.')
        target={}
        def prepare():
            public=self.prepare_l_profile(document_id,configuration,**asdict(definition))
            capture=self.dimensions._paired_capture(document_id,configuration)
            entry,identity,_,semantic,revision=capture.state
            features=self.adapter.features(entry.model)
            if revision!=public['dimension_revision'] or tuple(self.adapter.identity(f) for f in features)!=capture.feature_identities:
                raise rejected('sheet_changed_after_preparation','Exact complete native membership changed after preparation.')
            plane,reference=self.features._resolve(entry,configuration,identity,features,definition.plane_object_id)
            if (reference.persistent_id.hex()!=public['plane_persistent_id_hex']
                    or list(validated_plane_transform(self.adapter.reference_plane_transform(plane)))!=public['plane_transform']
                    or self.adapter.sheet_profile_empty_state(entry.model)!=public['sheet_template_state']):
                raise rejected('sheet_changed_after_preparation','The explicit plane or empty sheet-template state changed.')
            receipt=self.adapter.new_sheet_profile_receipt(entry.model,features,public['creation_controls'])
            self.dimensions._close_native_proof(entry,capture.event_sequence)
            target.update(entry=entry,plane=plane,receipt=receipt)
            return PreparedMutation(public['revision'],dict(scope=SCOPE,definition=asdict(definition),semantic=semantic,
                plane_persistent_id_hex=public['plane_persistent_id_hex'],plane_transform=public['plane_transform'],
                creation_controls=public['creation_controls'],expected_geometry=public['expected_geometry'],
                sheet_template_state=public['sheet_template_state']))
        def apply(prepared):
            entry=target['entry'];entry.features['mutation_sequence']=entry.features.get('mutation_sequence',0)+1
            self.adapter.create_sheet_l_profile(entry.model,target['plane'],definition,target['receipt'])
            return dict(sketch_name=definition.sketch_name,feature_name=definition.feature_name,body_name=definition.body_name,k_factor=definition.k_factor)
        def restore(before,prepared):
            after=self._inspect(document_id,configuration,target['receipt'])
            if not self._verify(before,after,definition,configuration):
                raise rejected('sheet_restore_unsafe','Only the complete proved own folded profile can authorize bundle deletion.')
            self.adapter.restore_sheet_profile(target['entry'].model,target['receipt'])
        return self.dimensions.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=prepare,
            validate=lambda prepared:self.prepare_l_profile(document_id,configuration,**asdict(definition))['revision']==prepared.revision,
            apply=apply,inspect=lambda prepared:self._inspect(document_id,configuration,target['receipt']),
            verify=lambda before,after,value:self._verify(before,after,definition,configuration),restore=restore,
            verify_restored=lambda before,after:after['created'].get('restored') is True
                and DimensionCatalog._comparable(before['semantic'])==DimensionCatalog._comparable(after['semantic']),
            guard=lambda prepared:self.dimensions.mutation_guard(target['entry'].model))
