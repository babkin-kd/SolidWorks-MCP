"""Explicit existing U-sheet unfold/refold, complete capture and scoped restore."""

from copy import deepcopy
from dataclasses import asdict,replace
import hashlib
import math

from .jobs import _json
from .documents import rejected
from .dimensions import DimensionCatalog
from .mutations import PreparedMutation
from .sheet_flat_state import SheetFlatStateCatalog,ROLE_TYPES,STATE_ROLES
from .sheet_profile import SheetProfileCatalog
from .sheet_profile_definition import SheetLProfile,sheet_l_native_parameters_match
from .sheet_edge_flange_definition import EdgeFlangeOnL,sheet_u_body_matches
from .sheet_edge_flange_parameters import native_flange_parameters_match
from .sheet_flange_flat_geometry import expected_flat_u_geometry,flat_u_body_matches,fixed_u_leg_from_face
from .edge_flange_sketch import edge_flange_sketch_matches
from .sketches import persistent_sketch_members


SCOPE='single_u_sheet_flat_state_v1'
U_ROLE_TYPES={**ROLE_TYPES,'flange':'EdgeFlange','flange_sketch':'ProfileFeature',
    'flange_bend':'OneBend','flange_flat_bend':'UiBend'}


def flange_flat_arguments(base_object_id,flange_object_id,flattened):
    SheetFlatStateCatalog._arguments(base_object_id,flattened)
    SheetFlatStateCatalog._arguments(flange_object_id,flattened)
    if base_object_id==flange_object_id:
        raise rejected('sheet_u_target_collision','The explicit base and flange must be distinct references.')


def definition_from_seed(seed,plane_object_id):
    regular=[p for p in seed['sketch']['points'] if p['implicit'] is False]
    if len(regular)!=3:raise rejected('sheet_u_source_profile','The full original open L-profile is required.')
    coordinates=[tuple(float.fromhex(v) for v in p['coordinates_si']) for p in regular]
    source_parameters=seed['source_parameters'];base=source_parameters['base'];sheet=source_parameters['sheet']
    source=SheetLProfile.validate(plane_object_id=plane_object_id,
        leg_x_mm=max(p[0] for p in coordinates)*1000.,leg_y_mm=max(p[1] for p in coordinates)*1000.,
        length_mm=base['D1EndConditionDistance']*1000.,thickness_mm=sheet['thickness']*1000.,
        bend_radius_mm=sheet['radius']*1000.,k_factor=sheet['k_factor'])
    names=seed['names'];source=replace(source,sketch_name=names['sketch'],feature_name=names['base'])
    flange=seed['flange_parameters']
    return EdgeFlangeOnL.validate(source,flange['OffsetDistance']*1000.,flange['BendRadius']*1000.,flange['k_factor'],
        names['flange_sketch'],names['flange'])


def own_u_dimensions_match(rows,members,profile,definition,configuration):
    """Exactly the profile height plus the native bend radius and right angle."""
    by={r['role']:r for r in members};sketch=by['flange_sketch'];bend=by['flange_bend']
    expected_ids={sketch['native_id'],bend['native_id']}
    own=[r for r in rows if r['owner'] and r['owner']['native_id'] in expected_ids]
    if len(own)!=3:return False
    heights=[r for r in own if r['owner']['native_id']==sketch['native_id']]
    angles=[r for r in own if r['owner']['native_id']==bend['native_id'] and r['parameter_type']==1]
    radii=[r for r in own if r['owner']['native_id']==bend['native_id'] and r['parameter_type']==0]
    if not all(len(group)==1 for group in (heights,angles,radii)):return False
    relation=next(r for r in profile['relations'] if r['type']==1)
    if heights[0]['full_name']!=relation['dimension_full_name']:return False
    for row,owner,kind,unit,value,display in (
            (heights[0],sketch,0,'mm',definition.profile_height_mm/1000.,2),
            (radii[0],bend,0,'mm',definition.bend_radius_mm/1000.,5),
            (angles[0],bend,1,'deg',math.pi/2.,3)):
        if (type(row['parameter_type']) is not int or row['parameter_type']!=kind or row['unit']!=unit
                or row['driven_state']!=2 or any(row[k] for k in ('read_only','reference','design_table','linked'))
                or row['owner']['frozen'] or row['owner']['rolled_back']
                or any(row['owner'][k]!=owner[k] for k in ('native_id','name','feature_type','owner_native_id','suppressed','error_code','is_warning'))
                or set(row['values_si'])!={configuration}
                or not math.isclose(row['values_si'][configuration],value,rel_tol=0.,abs_tol=1e-12)
                or row['display_dimensions']!=[dict(type=display,linked=False,linked_text='')]
                or row['tolerance']!=dict(type=0,values_si=[])):return False
    return True


class SheetFlangeFlatStateCatalog:
    def __init__(self,dimensions):
        self.dimensions=dimensions;self.adapter=dimensions.adapter;self.features=dimensions.features

    @staticmethod
    def _source(state,definition,configuration):
        semantic=state['semantic'];e=state['evidence'];tree=semantic['tree'];context=semantic['context']
        if (tree['document']['configurations']!=[configuration] or not context['configuration_geometry_complete']
                or tree['needs_rebuild'] or any(context['configuration_needs_rebuild'].values())
                or not context['active_document'] or context['read_only'] or context['editing_sketch']
                or context['external_reference_count'] or context['equation_count'] or context['equations_linked']
                or context['design_table'] or context['unsafe_feature_types']):
            raise rejected('sheet_u_context_unsupported','One writable active rebuilt independent configuration is required.')
        members=e['members'];by={r['role']:r for r in members}
        if len(members)!=16 or set(by)!=set(U_ROLE_TYPES) or len({r['native_id'] for r in members})!=16:
            raise rejected('sheet_u_source_mismatch','The complete original and flange U graph is required.')
        for role,row in by.items():
            suppressed=not e['flattened'] if role in STATE_ROLES else False
            if (row['feature_type']!=U_ROLE_TYPES[role] or row['suppressed'] is not suppressed or row['error_code'] or row['is_warning']
                    or role!='fold_sketch_folder' and not row['pid_hex']):
                raise rejected('sheet_u_source_mismatch','Types, suppression, errors and strong references must match every U member.')
        required={r['native_id']:r for r in members if r['role'] not in ('sheet_folder','flat_folder')}
        actual={r['native_id']:r for r in tree['features'] if r['feature_type'] in set(U_ROLE_TYPES.values())-{'TemplateSheetMetal','TemplateFlatPattern'}}
        if set(actual)!=set(required) or any(actual[i]!={k:v for k,v in required[i].items() if k not in ('role','pid_hex','reference_strategy')} for i in actual):
            raise rejected('sheet_u_source_mismatch','Unconfirmed additional geometric nodes or incomplete membership are outside scope.')
        if any(r['error_code'] or r['is_warning'] for r in tree['features']):
            raise rejected('sheet_u_source_error','All native feature errors must be resolved first.')
        if e['controls']['add_to_db'] or e['controls']['dimension_input']:
            raise rejected('sheet_u_controls_unsupported','Interactive sketch controls must be disabled.')
        owner_expected={'sketch':'base','bend':'base','flat_sketch_1':'flat','flat_sketch_2':'flat',
            'ui_bend':'flat','fold_sketch_folder':'flat','flange_sketch':'flange','flange_bend':'flange','flange_flat_bend':'flat'}
        if any(row['owner_native_id']!=(by[owner_expected[role]]['native_id'] if role in owner_expected else None)
                for role,row in by.items() if role!='cut_list'):
            raise rejected('sheet_u_source_mismatch','Every complete member must bind its exact expected native owner.')
        profile=e['flange_profile'];frame=e['plane_transform']
        if (not edge_flange_sketch_matches(profile,definition,frame)
                or not math.isclose(float.fromhex(profile['driver_value_si']),definition.profile_height_mm/1000.,rel_tol=0.,abs_tol=1e-12)
                or not own_u_dimensions_match(semantic['dimensions'],members,profile,definition,configuration)
                or not native_flange_parameters_match(e['flange_parameters'],definition)):
            raise rejected('sheet_u_flange_mismatch','The complete flange profile, all three own dimensions and independent allowance must match.')
        original_semantic=deepcopy(semantic)
        own_ids={by[role]['native_id'] for role in ('flange_sketch','flange_bend')}
        original_semantic['dimensions']=[r for r in original_semantic['dimensions'] if not(r['owner'] and r['owner']['native_id'] in own_ids)]
        original=dict(semantic=original_semantic,created=dict(sketch=e['sketch'],base_native_id=e['base_native_id']))
        plane=dict(plane_persistent_id_hex=e['plane_pid_hex'],plane_transform=frame)
        if (e['base_native_id']!=by['base']['native_id'] or e['sketch_native_id']!=by['sketch']['native_id']
                or not SheetProfileCatalog._valid_profile(plane,original,definition.source,configuration)
                or not sheet_l_native_parameters_match(e['base_parameters'],e['sheet_parameters'],definition.source)):
            raise rejected('sheet_u_original_mismatch','The original complete L-profile network and first native allowance must remain intact.')
        fixed_u_leg_from_face(e['fixed_face'],definition,frame,flattened=e['flattened'])
        flat=expected_flat_u_geometry(definition,frame);fold=definition.expected_geometry(frame)
        matches=flat_u_body_matches(semantic['geometry'],flat) if e['flattened'] else sheet_u_body_matches(semantic['geometry'],fold)
        expected=flat if e['flattened'] else dict(volume_mm3=definition.volume_mm3,surface_area_mm2=definition.surface_area_mm2)
        if (not matches or not math.isclose(e['volume_mm3'],expected['volume_mm3'],rel_tol=1e-7,abs_tol=1e-8)
                or not math.isclose(e['area_mm2'],expected['surface_area_mm2'],rel_tol=1e-7,abs_tol=1e-8)):
            raise rejected('sheet_u_state_shape','The complete intended material boundary and independent mass must match.')
        return flat,fold

    def _capture_once(self,document_id,configuration,base_object_id,flange_object_id,retained=None):
        capture=self.dimensions._capture(document_id,configuration);entry,identity,_,semantic,revision=capture.state
        objects=self.adapter.features(entry.model)
        if tuple(self.adapter.identity(f) for f in objects)!=capture.feature_identities:
            raise rejected('sheet_u_changed','Complete native feature membership changed before target resolution.')
        base,base_ref=self.features._resolve(entry,configuration,identity,objects,base_object_id)
        flange,flange_ref=self.features._resolve(entry,configuration,identity,objects,flange_object_id)
        target,_=self.adapter.sheet_flange_flat_target(entry.model,base,flange,retained)
        seed=self.adapter.sheet_flange_flat_seed(entry.model,target)
        plane_pid=bytes.fromhex(seed['plane_pid_hex'])
        planes=[f for f in objects if f.GetTypeName2()=='RefPlane' and self.adapter.same_persistent_id(entry.model,plane_pid,self.adapter.persistent_id(entry.model,f))]
        if len(planes)!=1:raise rejected('sheet_u_plane_changed','The complete original plane must bind one exact current reference.')
        plane_ref=self.features._register(entry,configuration,identity,planes[0])
        definition=definition_from_seed(seed,plane_ref.object_id)
        evidence,members=self.adapter.sheet_flange_flat_evidence(entry.model,target,definition,seed['plane_transform'])
        actual_pid=bytes.fromhex(evidence['sketch']['reference_plane']['pid_hex'])
        if not self.adapter.same_persistent_id(entry.model,plane_pid,actual_pid):
            raise rejected('sheet_u_plane_changed','The original sketch plane reference changed after its parameter seed.')
        evidence.update(plane_pid_hex=plane_pid.hex(),plane_transform=list(self.adapter.reference_plane_transform(planes[0])))
        state=dict(semantic=semantic,dimension_revision=revision,evidence=evidence,
            base_pid_hex=base_ref.persistent_id.hex(),flange_pid_hex=flange_ref.persistent_id.hex())
        flat,fold=self._source(state,definition,configuration)
        self.dimensions._close_native_proof(entry,capture.event_sequence)
        return capture,target,state,members,definition,flat,fold

    def _capture(self,document_id,configuration,base_object_id,flange_object_id,retained=None):
        args=(document_id,configuration,base_object_id,flange_object_id)
        first=self._capture_once(*args,retained);second=self._capture_once(*args,first[1])
        a,b=deepcopy(first[2]),deepcopy(second[2]);same=True
        for key in ('volume_mm3','area_mm2'):
            same=same and math.isclose(a['evidence'].pop(key),b['evidence'].pop(key),rel_tol=1e-10,abs_tol=1e-8)
        if not same or a!=b or persistent_sketch_members(first[3])!=persistent_sketch_members(second[3]):
            raise rejected('sheet_u_changed','Two complete closing U-state captures disagree.')
        self.dimensions._close_capture_pair(first[0],second[0]);return second

    def _prepare(self,document_id,configuration,base_object_id,flange_object_id,flattened,retained=None):
        flange_flat_arguments(base_object_id,flange_object_id,flattened)
        captured=self._capture(document_id,configuration,base_object_id,flange_object_id,retained)
        state=deepcopy(captured[2]);state['evidence'].pop('volume_mm3');state['evidence'].pop('area_mm2')
        payload=dict(scope=SCOPE,document_id=document_id,configuration=configuration,base_object_id=base_object_id,
            flange_object_id=flange_object_id,flattened=flattened,state=state,definition=asdict(captured[4]),
            expected_flat=captured[5],expected_fold=captured[6])
        revision='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        public=dict(document_id=document_id,configuration=configuration,base_object_id=base_object_id,
            flange_object_id=flange_object_id,flattened=flattened,current_flattened=captured[2]['evidence']['flattened'],
            revision_scope=SCOPE,revision=revision,k_factors=[captured[4].source.k_factor,captured[4].k_factor],
            expected_geometry=captured[5] if flattened else captured[6],native_change_available=True)
        return public,captured

    def prepare_flat_state(self,document_id,configuration,base_object_id,flange_object_id,flattened):
        return self._prepare(document_id,configuration,base_object_id,flange_object_id,flattened)[0]

    @staticmethod
    def _transition(before,after,flattened,*,allow_names=False):
        try:
            old,new=before['evidence'],after['evidence']
            if new['flattened'] is not flattened:return False
            for key in ('base_parameters','sheet_parameters','sketch','flange_profile','flange_parameters','parameter_options',
                    'controls','options','plane_pid_hex','plane_transform','base_native_id','sketch_native_id','body_pid_hex'):
                if old[key]!=new[key]:return False
            if before['base_pid_hex']!=after['base_pid_hex'] or before['flange_pid_hex']!=after['flange_pid_hex']:return False
            if not allow_names and old['body_name']!=new['body_name']:return False
            a,b=deepcopy(old['members']),deepcopy(new['members']);old_by={r['role']:r for r in a}
            for row in b:
                if row['role'] in STATE_ROLES:row['suppressed']=old_by[row['role']]['suppressed']
                if allow_names and row['role']=='cut_list':row['name']=old_by['cut_list']['name']
            if a!=b:return False
            previous=DimensionCatalog._comparable(before['semantic'],ignore_geometry=True)
            current=DimensionCatalog._comparable(after['semantic'],ignore_geometry=True)
            changes={old_by[role]['native_id'] for role in STATE_ROLES};cut_id=old_by['cut_list']['native_id']
            rows={r['native_id']:r for r in previous['tree']['features']}
            for row in current['tree']['features']:
                if row['native_id'] in changes:row['suppressed']=rows[row['native_id']]['suppressed']
                if allow_names and row['native_id']==cut_id:row['name']=rows[cut_id]['name']
            return previous==current
        except (KeyError,TypeError,IndexError):return False

    def set_flat_state(self,operation_id,document_id,configuration,base_object_id,flange_object_id,flattened,expected_revision):
        flange_flat_arguments(base_object_id,flange_object_id,flattened)
        if self.dimensions.mutation_guard is None:raise rejected('mutation_guard_unavailable','An owning-STA mutation guard is required.')
        args=dict(document_id=document_id,configuration=configuration,base_object_id=base_object_id,
            flange_object_id=flange_object_id,flattened=flattened);target={}
        def prepare():
            public,captured=self._prepare(**args);target['captured']=captured
            return PreparedMutation(public['revision'],captured[2])
        def validate(prepared):
            public,captured=self._prepare(**args,retained=target['captured'][1])
            return public['revision']==prepared.revision and persistent_sketch_members(captured[3])==persistent_sketch_members(target['captured'][3])
        def inspect(prepared):return self._capture(document_id,configuration,base_object_id,flange_object_id,target['captured'][1])[2]
        def change_and_names(before,state):
            captured=target['captured'];model=captured[0].state[0].model
            self.adapter.sheet_change_flange_flat_state(model,captured[1],state)
            current=inspect(None)
            if not self._transition(before,current,state,allow_names=True):
                raise rejected('sheet_u_transition_unproved','Only the complete intended U-state transition authorizes original-name preservation.')
            old=before['evidence'];cut=next(r['name'] for r in old['members'] if r['role']=='cut_list')
            self.adapter.sheet_preserve_flange_flat_names(model,captured[1],old['body_name'],cut)
        def apply(prepared):
            entry=target['captured'][0].state[0];entry.features['mutation_sequence']=entry.features.get('mutation_sequence',0)+1
            change_and_names(prepared.before,flattened)
            return dict(flattened=flattened,changed=prepared.before['evidence']['flattened']!=flattened)
        def restore(before,prepared):
            current=inspect(None)
            if not self._transition(before,current,current['evidence']['flattened'],allow_names=True):
                raise rejected('sheet_u_restore_unsafe','Foreign changes or an unproved material state prevent scoped restoration.')
            change_and_names(before,before['evidence']['flattened'])
        return self.dimensions.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=prepare,validate=validate,apply=apply,inspect=inspect,
            verify=lambda before,after,value:self._transition(before,after,flattened),restore=restore,
            verify_restored=lambda before,after:self._transition(before,after,before['evidence']['flattened']),
            guard=lambda prepared:self.dimensions.mutation_guard(target['captured'][0].state[0].model))
