"""Closed native L-sheet flat/fold state and scoped durable mutation."""

import hashlib
from copy import deepcopy
from dataclasses import asdict,replace
import math
import re

from .jobs import _json
from .documents import rejected
from .dimensions import DimensionCatalog
from .mutations import PreparedMutation
from .sheet_profile import SheetProfileCatalog
from .sheet_profile_definition import AUXILIARY_SCHEMA,SheetLProfile,sheet_l_body_matches,sheet_l_native_parameters_match
from .sheet_flat_geometry import fixed_l_leg_from_face,expected_flat_l_geometry,flat_l_body_matches
from .sketches import persistent_sketch_members


SCOPE='single_l_sheet_flat_state_v1'
STATE_ROLES=frozenset(('flat','flat_sketch_2','fold_sketch_folder','flat_folder'))
ROLE_TYPES={**{role:row[1] for role,row in AUXILIARY_SCHEMA.items()},'base':'SMBaseFlange','sketch':'ProfileFeature'}


def flat_state_revision(capture):
    """Bind the complete closed CAD capture, not redundant mass round-off.

The full material BREP, tree/drivers, parameters, fixed-face reference, controls
and native dimension revision are retained. Independent mass/area values must
still be tolerance-checked at capture/postcondition boundaries; they are not
exact native identity or authoritative geometry and cannot enter an exact hash.
"""
    payload={key:value for key,value in capture.items() if key not in ('volume_mm3','area_mm2')}
    return 'rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest()


class SheetFlatStateCatalog:
    def __init__(self,dimensions):
        self.dimensions=dimensions;self.adapter=dimensions.adapter;self.features=dimensions.features

    @staticmethod
    def _arguments(base_object_id,flattened):
        if not isinstance(base_object_id,str) or not re.fullmatch(r'feat_[0-9a-f]{32}',base_object_id):
            raise rejected('invalid_sheet_base_reference','An explicit opaque base feature reference is required.')
        if type(flattened) is not bool:raise rejected('invalid_sheet_flat_state','flattened must be an explicit boolean.')

    @staticmethod
    def _source(state,configuration,plane_object_id):
        semantic=state['semantic'];e=state['evidence'];tree=semantic['tree'];context=semantic['context']
        if (len(tree['document']['configurations'])!=1 or not context['configuration_geometry_complete']
                or tree['needs_rebuild'] or any(context['configuration_needs_rebuild'].values())
                or not context['active_document'] or context['read_only'] or context['editing_sketch']
                or context['external_reference_count'] or context['equation_count'] or context['equations_linked']
                or context['design_table'] or context['unsafe_feature_types']):
            raise rejected('sheet_state_context_unsupported','An active writable rebuilt one-configuration independent L-sheet is required.')
        members=e['members'];by_role={row['role']:row for row in members}
        if len(members)!=12 or set(by_role)!=set(ROLE_TYPES) or len({r['native_id'] for r in members})!=12:
            raise rejected('sheet_state_source_mismatch','The complete exact sheet/base/flat/cut-list bundle is required.')
        for role,row in by_role.items():
            expected_suppressed=not e['flattened'] if role in STATE_ROLES else False
            if (row['feature_type']!=ROLE_TYPES[role] or row['suppressed'] is not expected_suppressed or row['error_code'] or row['is_warning']
                    or (role!='fold_sketch_folder' and not row['pid_hex'])):
                raise rejected('sheet_state_source_mismatch','Native bundle types, suppression, errors or references are outside the L-sheet scope.')
        required={r['native_id']:r for r in members if r['role'] not in ('sheet_folder','flat_folder')}
        actual={r['native_id']:r for r in tree['features'] if r['feature_type'] in set(ROLE_TYPES.values())-{'TemplateSheetMetal','TemplateFlatPattern'}}
        if set(actual)!=set(required) or any(actual[i]!= {k:v for k,v in required[i].items() if k not in ('role','pid_hex','reference_strategy')} for i in actual):
            raise rejected('sheet_state_source_mismatch','Unconfirmed additional geometric nodes or incomplete native membership are outside scope.')
        if any(row['error_code'] or row['is_warning'] for row in tree['features']):raise rejected('sheet_state_source_error','Resolve all native feature errors before switching sheet state.')
        if e['controls']['add_to_db'] or e['controls']['dimension_input']:
            raise rejected('sheet_state_controls_unsupported','Interactive sketch controls must be disabled.')
        regular=[p for p in e['sketch']['points'] if p['implicit'] is False]
        coordinates=[tuple(float.fromhex(v) for v in p['coordinates_si']) for p in regular]
        if len(coordinates)!=3:raise rejected('sheet_state_source_mismatch','The exact three-corner original open L-profile is required.')
        definition=SheetLProfile.validate(plane_object_id=plane_object_id,
            leg_x_mm=max(p[0] for p in coordinates)*1000.,leg_y_mm=max(p[1] for p in coordinates)*1000.,
            length_mm=e['base_parameters']['D1EndConditionDistance']*1000.,thickness_mm=e['sheet_parameters']['thickness']*1000.,
            bend_radius_mm=e['sheet_parameters']['radius']*1000.,k_factor=e['sheet_parameters']['k_factor'])
        # Existing display names are preserved; this operation creates no user
        # nodes and does not translate existing library/file identifiers.
        definition=replace(definition,sketch_name=by_role['sketch']['name'],feature_name=by_role['base']['name'],body_name=e['body_name'])
        before=dict(plane_persistent_id_hex=e['plane_pid_hex'],plane_transform=e['plane_transform'])
        profile=dict(semantic=semantic,created=dict(sketch=e['sketch'],base_native_id=e['base_native_id']))
        if (e['base_native_id']!=by_role['base']['native_id'] or e['sketch_native_id']!=by_role['sketch']['native_id']
                or not SheetProfileCatalog._valid_profile(before,profile,definition,configuration)
                or not sheet_l_native_parameters_match(e['base_parameters'],e['sheet_parameters'],definition)):
            raise rejected('sheet_state_source_mismatch','The complete original driving network and independent native sheet allowance must match.')
        leg=fixed_l_leg_from_face(e['fixed_face'],definition,e['plane_transform'],flattened=e['flattened'])
        flat=expected_flat_l_geometry(definition,e['plane_transform'],leg);fold=definition.expected_geometry(e['plane_transform'])
        matches=flat_l_body_matches(semantic['geometry'],flat) if e['flattened'] else sheet_l_body_matches(semantic['geometry'],fold)
        expected=flat if e['flattened'] else dict(volume_mm3=definition.volume_mm3,surface_area_mm2=definition.surface_area_mm2)
        if (not matches or not math.isclose(e['volume_mm3'],expected['volume_mm3'],rel_tol=1e-7,abs_tol=1e-8)
                or not math.isclose(e['area_mm2'],expected['surface_area_mm2'],rel_tol=1e-7,abs_tol=1e-8)):
            raise rejected('sheet_state_source_shape','The complete material boundary and independent mass must match this exact L-sheet state.')
        return definition,flat,fold

    def _capture_once(self,document_id,configuration,base_object_id,retained=None):
        capture=self.dimensions._capture(document_id,configuration);entry,identity,_,semantic,revision=capture.state
        objects=self.adapter.features(entry.model)
        if tuple(self.adapter.identity(f) for f in objects)!=capture.feature_identities:raise rejected('sheet_state_changed','Complete feature membership changed before resolution.')
        base,reference=self.features._resolve(entry,configuration,identity,objects,base_object_id)
        target,_=self.adapter.sheet_state_target(entry.model,base,retained)
        evidence,members=self.adapter.sheet_state_evidence(entry.model,target)
        plane_pid=bytes.fromhex(evidence['sketch']['reference_plane']['pid_hex'])
        planes=[f for f in objects if f.GetTypeName2()=='RefPlane' and self.adapter.same_persistent_id(entry.model,plane_pid,self.adapter.persistent_id(entry.model,f))]
        if len(planes)!=1:raise rejected('sheet_state_plane_changed','The original profile plane must bind one exact native reference.')
        plane=planes[0];plane_ref=self.features._register(entry,configuration,identity,plane)
        evidence.update(plane_pid_hex=plane_pid.hex(),plane_transform=list(self.adapter.reference_plane_transform(plane)))
        state=dict(semantic=semantic,dimension_revision=revision,evidence=evidence,base_pid_hex=reference.persistent_id.hex())
        definition,flat,fold=self._source(state,configuration,plane_ref.object_id)
        evidence['fixed_leg']=flat['fixed_leg']
        self.dimensions._close_native_proof(entry,capture.event_sequence)
        return capture,target,state,members,definition,flat,fold

    def _capture(self,document_id,configuration,base_object_id,retained=None):
        first=self._capture_once(document_id,configuration,base_object_id,retained)
        second=self._capture_once(document_id,configuration,base_object_id,first[1])
        a,b=deepcopy(first[2]),deepcopy(second[2]);same=True
        for key in ('volume_mm3','area_mm2'):
            same=same and math.isclose(a['evidence'].pop(key),b['evidence'].pop(key),rel_tol=1e-10,abs_tol=1e-8)
        same=same and a==b and persistent_sketch_members(first[3])==persistent_sketch_members(second[3])
        if not same:raise rejected('sheet_state_changed','Two closing complete native sheet-state captures disagree.')
        self.dimensions._close_capture_pair(first[0],second[0])
        return second

    @staticmethod
    def _payload(captured,document_id,configuration,base_object_id,flattened):
        state=deepcopy(captured[2]);state['evidence'].pop('volume_mm3');state['evidence'].pop('area_mm2')
        return dict(scope=SCOPE,document_id=document_id,configuration=configuration,base_object_id=base_object_id,
            flattened=flattened,state=state,definition=asdict(captured[4]),expected_flat=captured[5],expected_fold=captured[6])

    def _prepare(self,document_id,configuration,base_object_id,flattened,retained=None):
        self._arguments(base_object_id,flattened);captured=self._capture(document_id,configuration,base_object_id,retained)
        payload=self._payload(captured,document_id,configuration,base_object_id,flattened)
        revision='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        public=dict(document_id=document_id,configuration=configuration,base_object_id=base_object_id,flattened=flattened,
            current_flattened=captured[2]['evidence']['flattened'],revision_scope=SCOPE,revision=revision,
            k_factor=captured[4].k_factor,expected_geometry=captured[5] if flattened else captured[6],native_change_available=True)
        return public,captured

    def prepare_flat_state(self,document_id,configuration,base_object_id,flattened):
        return self._prepare(document_id,configuration,base_object_id,flattened)[0]

    @staticmethod
    def _transition(before,after,flattened,*,allow_names=False):
        try:
            old,new=before['evidence'],after['evidence']
            if new['flattened'] is not flattened:return False
            if any(old[k]!=new[k] for k in ('base_parameters','sheet_parameters','sketch','controls','options','plane_pid_hex','plane_transform',
                    'base_native_id','sketch_native_id','body_pid_hex','fixed_leg')):return False
            if not allow_names and old['body_name']!=new['body_name']:return False
            a,b=deepcopy(old['members']),deepcopy(new['members']);old_by={r['role']:r for r in a}
            for row in b:
                if row['role'] in STATE_ROLES:row['suppressed']=old_by[row['role']]['suppressed']
                if allow_names and row['role']=='cut_list':row['name']=old_by['cut_list']['name']
            if a!=b:return False
            a=DimensionCatalog._comparable(before['semantic'],ignore_geometry=True)
            b=DimensionCatalog._comparable(after['semantic'],ignore_geometry=True)
            changes={old_by[r]['native_id'] for r in STATE_ROLES};cut_id=old_by['cut_list']['native_id']
            previous={r['native_id']:r for r in a['tree']['features']}
            for row in b['tree']['features']:
                if row['native_id'] in changes:row['suppressed']=previous[row['native_id']]['suppressed']
                if allow_names and row['native_id']==cut_id:row['name']=previous[cut_id]['name']
            return a==b
        except (KeyError,TypeError,IndexError):return False

    def set_flat_state(self,operation_id,document_id,configuration,base_object_id,flattened,expected_revision):
        self._arguments(base_object_id,flattened)
        if self.dimensions.mutation_guard is None:raise rejected('mutation_guard_unavailable','An owning-STA mutation guard is required.')
        args=dict(document_id=document_id,configuration=configuration,base_object_id=base_object_id,flattened=flattened);target={}
        def prepare():
            public,captured=self._prepare(**args);target.update(captured=captured)
            return PreparedMutation(public['revision'],captured[2])
        def validate(prepared):
            public,captured=self._prepare(**args,retained=target['captured'][1])
            return public['revision']==prepared.revision and persistent_sketch_members(captured[3])==persistent_sketch_members(target['captured'][3])
        def inspect(prepared):return self._capture(document_id,configuration,base_object_id,target['captured'][1])[2]
        def change_and_names(before,state):
            captured=target['captured'];model=captured[0].state[0].model
            self.adapter.sheet_change_flat_state(model,captured[1],state)
            current=inspect(None)
            if not self._transition(before,current,state,allow_names=True):raise rejected('sheet_state_transition_unproved','Only the complete intended native transition authorizes own-name preservation.')
            old=before['evidence'];cut_name=next(row['name'] for row in old['members'] if row['role']=='cut_list')
            self.adapter.sheet_preserve_flat_names(model,captured[1],old['body_name'],cut_name)
        def apply(prepared):
            entry=target['captured'][0].state[0];entry.features['mutation_sequence']=entry.features.get('mutation_sequence',0)+1
            change_and_names(prepared.before,flattened);return dict(flattened=flattened,changed=prepared.before['evidence']['flattened']!=flattened)
        def restore(before,prepared):
            current=inspect(None)
            if not self._transition(before,current,current['evidence']['flattened'],allow_names=True):raise rejected('sheet_state_restore_unsafe','Foreign changes or an unproved material state prevent scoped restoration.')
            change_and_names(before,before['evidence']['flattened'])
        return self.dimensions.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=prepare,validate=validate,apply=apply,inspect=inspect,
            verify=lambda before,after,value:self._transition(before,after,flattened),restore=restore,
            verify_restored=lambda before,after:self._transition(before,after,before['evidence']['flattened']),
            guard=lambda prepared:self.dimensions.mutation_guard(target['captured'][0].state[0].model))
