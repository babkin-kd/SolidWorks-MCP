"""Closed existing L-sheet parameter domain and scoped durable mutation."""

from copy import deepcopy
from dataclasses import asdict,replace
import hashlib
import math

from .dimensions import DimensionCatalog
from .documents import rejected
from .jobs import _json,ExecutionFailure
from .mutations import PreparedMutation
from .part_creation import _positive_length
from .sheet_flat_geometry import expected_flat_l_geometry
from .sheet_flat_state import SheetFlatStateCatalog
from .sheet_profile_definition import SheetLProfile,sheet_l_native_parameters_match
from .cad_sheet_parameters import BASE_OPTION_NAMES,SHEET_OPTION_NAMES,TEMPLATE_OPTION_NAMES


SCOPE='single_l_sheet_parameters_v1'


def parameter_values(thickness_mm,bend_radius_mm,k_factor):
    thickness=_positive_length(thickness_mm,'thickness_mm')
    radius=_positive_length(bend_radius_mm,'bend_radius_mm')
    if max(thickness,radius)>10000000.:
        raise rejected('sheet_parameter_out_of_range','Parameters exceed complete native capture bounds.')
    # Reuse the independent definition's strict finite K contract, without
    # imposing fictitious W/H dimensions before the actual source is captured.
    if type(k_factor) not in (float,int) or not math.isfinite(k_factor) or not 0.<=k_factor<=1.:
        raise rejected('invalid_sheet_k_factor','Explicit finite K-factor must be between zero and one.')
    return dict(thickness_mm=thickness,bend_radius_mm=radius,k_factor=float(k_factor))


def parameter_definition(source,values):
    definition=SheetLProfile.validate(plane_object_id=source.plane_object_id,
        leg_x_mm=source.leg_x_mm,leg_y_mm=source.leg_y_mm,length_mm=source.length_mm,**values)
    return replace(definition,sketch_name=source.sketch_name,feature_name=source.feature_name,body_name=source.body_name)


class SheetParameterCatalog(SheetFlatStateCatalog):
    @staticmethod
    def _validate_options(options):
        try:
            if (set(options)!= {'base','sheet','template','gauge'} or set(options['base'])!=set(BASE_OPTION_NAMES)
                    or set(options['sheet'])!=set(SHEET_OPTION_NAMES) or set(options['template'])!=set(TEMPLATE_OPTION_NAMES)):raise ValueError()
            gauge=options['gauge']
            if (set(gauge)!= {'result_code','enabled','file_name'} or type(gauge['result_code']) is not int
                    or gauge['result_code']!=0 or gauge['enabled'] is not False
                    or gauge['file_name'] is not None and type(gauge['file_name']) is not str):raise ValueError()
            # SW2023 help: the filename is valid only when enabled=True. Keep
            # dormant/null data in the revision, but never infer an active
            # table or fabricate an empty-string success from it.
            for section,bools,ints in (('base',{'UseDefaultBendRelief','UseReliefRatio'},{'ReliefType'}),
                    ('sheet',{'UseAutoRelief'},{'AutoReliefType'}),
                    ('template',{'UseAutoRelief','UseMaterialSheetMetalParameters'},{'AutoReliefType','AllowanceType'})):
                for key,value in options[section].items():
                    if key in bools:
                        if type(value) is not bool:raise ValueError()
                    elif key in ints:
                        if type(value) is not int:raise ValueError()
                    elif type(value) not in (float,int) or not math.isfinite(value):raise ValueError()
            template=options['template']
            if template['AllowanceType']!=2 or template['UseMaterialSheetMetalParameters'] is not False:raise ValueError()
        except (KeyError,TypeError,ValueError):
            raise rejected('sheet_parameter_options_unconfirmed','Complete finite native relief options and a confirmed disabled gauge table are required.')

    def _capture_once(self,*args,**kwargs):
        captured=super()._capture_once(*args,**kwargs)
        entry=captured[0].state[0]
        captured[2]['evidence']['parameter_options']=self.adapter.sheet_parameter_options(entry.model,captured[1])
        self._validate_options(captured[2]['evidence']['parameter_options'])
        template=captured[2]['evidence']['parameter_options']['template'];definition=captured[4]
        if any(not math.isclose(template[key],value,rel_tol=0.,abs_tol=1e-12) for key,value in (
                ('Thickness',definition.thickness_mm/1000.),('BendRadius',definition.bend_radius_mm/1000.),('KFactor',definition.k_factor))):
            raise rejected('sheet_parameter_default_mismatch','The exact default template and body sheet parameters must agree in this scope.')
        self.dimensions._close_native_proof(entry,captured[0].event_sequence)
        return captured

    def _prepare_parameters(self,document_id,configuration,base_object_id,thickness_mm,bend_radius_mm,k_factor,retained=None):
        self._arguments(base_object_id,False)
        values=parameter_values(thickness_mm,bend_radius_mm,k_factor)
        captured=self._capture(document_id,configuration,base_object_id,retained)
        definition=parameter_definition(captured[4],values)
        evidence=captured[2]['evidence'];frame=evidence['plane_transform']
        flat=expected_flat_l_geometry(definition,frame,evidence['fixed_leg']);fold=definition.expected_geometry(frame)
        payload=self._payload(captured,document_id,configuration,base_object_id,evidence['flattened'])
        payload.update(scope=SCOPE,parameters=values,definition=asdict(definition),expected_flat=flat,expected_fold=fold)
        revision='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        current=dict(thickness_mm=captured[4].thickness_mm,bend_radius_mm=captured[4].bend_radius_mm,k_factor=captured[4].k_factor)
        public=dict(document_id=document_id,configuration=configuration,base_object_id=base_object_id,
            revision_scope=SCOPE,revision=revision,current_parameters=current,parameters=values,flattened=evidence['flattened'],
            expected_geometry=flat if evidence['flattened'] else fold,
            native_change_available=callable(getattr(self.adapter,'sheet_modify_parameters',None)))
        return public,captured,definition

    def prepare_parameters(self,document_id,configuration,base_object_id,thickness_mm,bend_radius_mm,k_factor):
        return self._prepare_parameters(document_id,configuration,base_object_id,thickness_mm,bend_radius_mm,k_factor)[0]

    @staticmethod
    def _parameter_transition(before,after,definition,*,allow_names=False):
        """Inputs must be independently validated complete closing captures.

        Only t/r/K, their material boundary and native fixed-face footprint may
        change. Drivers, allowances/options, state and exact memberships remain.
        A mass or body box alone never validates either input capture.
        """
        try:
            a,b=deepcopy(before['evidence']),deepcopy(after['evidence'])
            SheetParameterCatalog._validate_options(a['parameter_options']);SheetParameterCatalog._validate_options(b['parameter_options'])
            if not sheet_l_native_parameters_match(b['base_parameters'],b['sheet_parameters'],definition):return False
            for key,value in (('Thickness',definition.thickness_mm/1000.),('BendRadius',definition.bend_radius_mm/1000.),('KFactor',definition.k_factor)):
                if not math.isclose(b['parameter_options']['template'][key],value,rel_tol=0.,abs_tol=1e-12):return False
                b['parameter_options']['template'][key]=a['parameter_options']['template'][key]
            def normal(face):
                sign=-1. if face['normal_opposes_surface'] else 1.
                return [sign*v for v in face['plane_parameters'][:3]]
            na,nb=normal(a['fixed_face']),normal(b['fixed_face'])
            if len(na)!=3 or len(nb)!=3 or any(not math.isclose(x,y,rel_tol=0.,abs_tol=1e-12) for x,y in zip(na,nb)):return False
            for key in ('fixed_face','volume_mm3','area_mm2'):
                a.pop(key);b.pop(key)
            for key in ('Thickness','BendRadius'):b['base_parameters'][key]=a['base_parameters'][key]
            for key in ('thickness','radius','k_factor'):b['sheet_parameters'][key]=a['sheet_parameters'][key]
            previous={r['role']:r for r in a['members']}
            if allow_names:
                b['body_name']=a['body_name']
                for row in b['members']:
                    if row['role']=='cut_list':row['name']=previous['cut_list']['name']
            if a!=b:return False
            a=DimensionCatalog._comparable(before['semantic'],ignore_geometry=True)
            b=DimensionCatalog._comparable(after['semantic'],ignore_geometry=True)
            if allow_names:
                cut=previous['cut_list']['native_id'];original=next(r['name'] for r in a['tree']['features'] if r['native_id']==cut)
                for row in b['tree']['features']:
                    if row['native_id']==cut:row['name']=original
            return a==b
        except (KeyError,TypeError,ValueError,IndexError,StopIteration,ExecutionFailure):return False

    def set_parameters(self,operation_id,document_id,configuration,base_object_id,thickness_mm,bend_radius_mm,k_factor,expected_revision):
        self._arguments(base_object_id,False);parameter_values(thickness_mm,bend_radius_mm,k_factor)
        if self.dimensions.mutation_guard is None:raise rejected('mutation_guard_unavailable','An owning-STA mutation guard is required.')
        if not callable(getattr(self.adapter,'sheet_modify_parameters',None)):
            raise rejected('sheet_parameter_native_unavailable','The native parameter writer is not connected.')
        args=dict(document_id=document_id,configuration=configuration,base_object_id=base_object_id,
            thickness_mm=thickness_mm,bend_radius_mm=bend_radius_mm,k_factor=k_factor);target={}
        def prepare():
            public,captured,definition=self._prepare_parameters(**args)
            target.update(captured=captured,definition=definition)
            return PreparedMutation(public['revision'],captured[2])
        def validate(prepared):
            public,captured,_=self._prepare_parameters(**args,retained=target['captured'][1])
            from .sketches import persistent_sketch_members
            return public['revision']==prepared.revision and persistent_sketch_members(captured[3])==persistent_sketch_members(target['captured'][3])
        def inspect(prepared):return self._capture(document_id,configuration,base_object_id,target['captured'][1])[2]
        def change_and_names(before,definition):
            captured=target['captured'];model=captured[0].state[0].model
            self.adapter.sheet_modify_parameters(model,captured[1],definition)
            current=inspect(None)
            if not self._parameter_transition(before,current,definition,allow_names=True):
                raise rejected('sheet_parameter_transition_unproved','Only the complete intended parameter transition authorizes preserving own names.')
            original=before['evidence'];cut=next(row['name'] for row in original['members'] if row['role']=='cut_list')
            self.adapter.sheet_preserve_flat_names(model,captured[1],original['body_name'],cut)
        def apply(prepared):
            entry=target['captured'][0].state[0];entry.features['mutation_sequence']=entry.features.get('mutation_sequence',0)+1
            change_and_names(prepared.before,target['definition'])
            return dict(parameters=parameter_values(thickness_mm,bend_radius_mm,k_factor),flattened=prepared.before['evidence']['flattened'])
        def restore(before,prepared):
            current=inspect(None);original=target['captured'][4]
            # Do not adopt arbitrary intermediate or foreign parameters as own.
            if not any(self._parameter_transition(before,current,d,allow_names=True) for d in (original,target['definition'])):
                raise rejected('sheet_parameter_restore_unsafe','The complete original or intended material state is required for scoped restoration.')
            change_and_names(before,original)
        return self.dimensions.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=prepare,validate=validate,apply=apply,inspect=inspect,
            verify=lambda before,after,value:self._parameter_transition(before,after,target['definition']),restore=restore,
            verify_restored=lambda before,after:self._parameter_transition(before,after,target['captured'][4]),
            guard=lambda prepared:self.dimensions.mutation_guard(target['captured'][0].state[0].model))
