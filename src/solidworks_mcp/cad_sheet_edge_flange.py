"""Internal owning-STA edge-flange primitive; not a registered MCP operation.

The caller owns the durable checkpoint, guard and complete source revision.
This bridge retains exact native handles even when a creation fails. A receipt
is not a deletion permission: restoration needs a separately proved graph.
"""

from dataclasses import dataclass,field
from copy import deepcopy
from types import SimpleNamespace
import math

import pythoncom
from win32com.client import VARIANT

from . import binding
from .documents import rejected
from .jobs import ExecutionFailure
from .cad_sheet_profile import NativeSheetMember
from .cad_selection_scope import preserved_selection
from .sheet_edge_flange_definition import l_flange_edge_points,sheet_u_body_matches
from .sheet_profile_definition import sheet_l_body_matches,sheet_l_native_parameters_match
from .edge_flange_sketch import EdgeFlangeSketchReader,edge_flange_sketch_matches,edge_flange_profile_preserved
from .linear_sketch import SketchEntityBinder,_coordinates
from .sketch_constraints import (SketchDefiner,SW_CONSTRAINT_COINCIDENT,
    SW_CONSTRAINT_VERTICAL,SW_CONSTRAINT_HORIZONTAL)


OPTION_NAMES=('UseDefaultBendRadius','BendRadius','GapDistance','BendAngle','LockAngle',
    'OffsetType','OffsetDistance','OffsetDimType','PositionType','UsePositionOffset',
    'ReverseOffset','UseDefaultBendAllowance','UseDefaultBendRelief')


def _same_identities(left,right):
    """Canonical PyIUnknown tokens support equality, not hashing."""
    return (len(left)==len(right)
        and not any(token==old for i,token in enumerate(left) for old in left[:i])
        and all(sum(token==other for other in right)==1 for token in left))


def _flange_profile_corners(p0,p1,length_m,height_m):
    if (len(p0)!=3 or len(p1)!=3
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in (*p0,*p1,length_m,height_m))
            or height_m<=0. or length_m<=0.
            or not math.isclose(abs(p1[0]-p0[0]),length_m,rel_tol=0.,abs_tol=1e-12)
            or not math.isclose(p1[1],p0[1],rel_tol=0.,abs_tol=1e-12)
            or abs(p0[2])>1e-12 or abs(p1[2])>1e-12):
        raise rejected('sheet_flange_profile_unconfirmed','The full horizontal converted edge must match the native sketch plane and source length.')
    # A native converted line can enumerate its endpoints in either order.
    # Direction never changes the positive height above the converted edge.
    return p0,p1,(p1[0],p1[1]+height_m,0.),(p0[0],p0[1]+height_m,0.)


def flange_options(definition):
    return dict(UseDefaultBendRadius=False,BendRadius=definition.bend_radius_mm/1000.,
        GapDistance=.001,BendAngle=math.pi/2.,LockAngle=True,OffsetType=1,
        OffsetDistance=definition.flange_length_mm/1000.,OffsetDimType=1,
        PositionType=1,UsePositionOffset=False,ReverseOffset=False,
        UseDefaultBendAllowance=False,UseDefaultBendRelief=True)


def native_flange_parameters_match(parameters,definition):
    """Strict complete readback, never inferred from CreateFeature/rebuild."""
    try:
        expected=flange_options(definition)
        if set(parameters)!= {*expected,'allowance_type','k_factor','edge_count'}:return False
        for name,value in expected.items():
            actual=parameters[name]
            if type(value) in (bool,int):
                if type(actual) is not type(value) or actual!=value:return False
            elif type(actual) not in (float,int) or not math.isfinite(actual) or not math.isclose(actual,value,rel_tol=0.,abs_tol=1e-12):return False
        return (type(parameters['allowance_type']) is int and parameters['allowance_type']==2
            and type(parameters['edge_count']) is int and parameters['edge_count']==1
            and type(parameters['k_factor']) in (float,int) and math.isfinite(parameters['k_factor'])
            and math.isclose(parameters['k_factor'],definition.k_factor,rel_tol=0.,abs_tol=1e-12))
    except (KeyError,TypeError,ValueError):return False


@dataclass
class NativeEdgeFlangeReceipt:
    source_target:object
    controls:dict
    edge:object
    edge_identity:object
    edge_pid:bytes
    baseline_features:tuple
    original_parameters:dict
    source_edge_points:tuple=()
    sketch:object=None
    sketch_identity:object=None
    sketch_pid:bytes=b''
    native_sketch:object=None
    flange:object=None
    flange_identity:object=None
    flange_pid:bytes=b''
    pending_creation:bool=False
    owned_children:list=field(default_factory=list)
    driver_name:str=''
    driver:object=None
    driver_identity:object=None
    profile_before:object=None
    profile_before_members:tuple=()
    flat_bend_member:object=None
    pending_deletion:bool=False
    selection_uncertain:bool=False
    restored:bool=False


class CadSheetEdgeFlangeMixin:
    def sheet_flange_sketch_snapshot(self,model,receipt,definition,frame,phase):
        """Fresh own profile and driver proof; automatic plane is not a target."""
        self._sheet_state_target_current(model,receipt.source_target)
        feature=self._sheet_flange_feature_current(model,receipt.sketch,receipt.sketch_identity,receipt.sketch_pid,'ProfileFeature')
        sketch=binding.wrap(feature.GetSpecificFeature2(),self._module.ISketch)
        if sketch is None or self.identity(sketch)!=self.identity(receipt.native_sketch):
            raise rejected('sheet_flange_profile_changed','The exact returned input sketch must remain current.')
        if (phase=='before_factory')!=(receipt.flange is None):
            raise rejected('sheet_flange_profile_phase','The reader phase must match the exact factory receipt.')
        reference,kind=sketch.GetReferenceEntity(0)
        if type(kind) is not int or kind!=4 or reference is None:
            raise rejected('sheet_flange_profile_reference','The native automatic planar reference is required.')
        reference_identity=self.identity(reference)
        def resolve(pid,name):
            raw,status=self._extension(model).GetObjectByPersistReference3(self._persistent_variant(pid))
            if type(status) is not int or status!=0 or raw is None:
                raise rejected('sheet_flange_profile_changed','A current own sketch entity reference must round-trip.')
            return binding.wrap(raw,getattr(self._module,name))
        binder=SketchEntityBinder(wrap=lambda raw,name:binding.wrap(raw,getattr(self._module,name)),
            reference=lambda obj:self.persistent_id(model,obj),resolve=resolve,identity=self.identity,coalesce=True)
        def source_definition(raw):
            selected=self._sheet_flange_profile_edge_current(model,receipt,definition,frame)
            edge=binding.wrap(raw,self._module.IEdge)
            if edge is None:return None
            pid=self.persistent_id(model,edge)
            if not pid or not self.same_persistent_id(model,pid,receipt.edge_pid):return None
            resolved=self.resolve_persistent_id(model,pid,'edge')
            owner=binding.wrap(edge.GetBody(),self._module.IBody2)
            owner_pid=self.persistent_id(model,owner) if owner is not None else b''
            points=self.pattern_edge_points(edge)
            if (self.identity(resolved)!=self.identity(selected) or not owner_pid
                    or not self.same_persistent_id(model,owner_pid,receipt.source_target.body_pid)
                    or not l_flange_edge_points(points,definition.source,frame)
                    or not l_flange_edge_points(self.pattern_edge_points(resolved),definition.source,frame)):
                return None
            body=self.resolve_persistent_id(model,owner_pid,'body')
            if self.identity(body)!=self.identity(self.resolve_persistent_id(model,receipt.source_target.body_pid,'body')):return None
            return self.identity(selected)
        reader=EdgeFlangeSketchReader(sketch,wrap=binder,identity=self.identity,phase=phase,source_definition=source_definition)
        snapshot,members=reader.read();binder.close()
        transform=binding.wrap(sketch.ModelToSketchTransform,self._module.IMathTransform)
        if transform is None:raise rejected('sheet_flange_profile_reference','The complete native model-to-sketch transform is required.')
        snapshot.update(model_to_sketch=_coordinates(transform.ArrayData,16),feature_native_id=int(feature.GetID()),
            feature_pid_hex=self.persistent_id(model,feature).hex(),prepared_edge_pid_hex=receipt.edge_pid.hex())
        drivers=[(key,token) for key,token in members if key.startswith('dimension:')]
        if (len(drivers)!=1 or receipt.driver is None or self.identity(receipt.driver)!=receipt.driver_identity
                or drivers[0][1]!=receipt.driver_identity):
            raise rejected('sheet_flange_driver_changed','The exact own native height driver must remain in the complete network.')
        configuration=str(binding.wrap(model.GetActiveConfiguration(),self._module.IConfiguration).Name)
        raw=receipt.driver.GetSystemValue3(3,self._named_configuration(configuration))
        if (type(raw) not in (tuple,list) or len(raw)!=1 or type(raw[0]) not in (float,int) or not math.isfinite(raw[0])
                or not math.isclose(raw[0],definition.profile_height_mm/1000.,rel_tol=0.,abs_tol=1e-12)
                or int(receipt.driver.GetType())!=0 or int(receipt.driver.DrivenState)!=2
                or bool(receipt.driver.ReadOnly) or bool(receipt.driver.IsReference()) or bool(receipt.driver.IsDesignTableDimension())):
            raise rejected('sheet_flange_driver_changed','The own driving height must independently match the finite requested SI value.')
        snapshot['driver_value_si']=float(raw[0]).hex()
        if (reader.driver_display is None or bool(reader.driver_display.IsLinked)
                or str(reader.driver_display.GetLinkedText() or '') or int(receipt.driver.GetToleranceType())!=0):
            raise rejected('sheet_flange_driver_changed','Linked display overrides or driver tolerances are outside this own-input scope.')
        if not edge_flange_sketch_matches(snapshot,definition,frame):
            raise rejected('sheet_flange_profile_unconfirmed','The entire rectangle, projection, transform and driving network must match.')
        closing_reference,closing_kind=sketch.GetReferenceEntity(0)
        if (closing_reference is None or type(closing_kind) is not int or closing_kind!=kind
                or self.identity(closing_reference)!=reference_identity
                or _coordinates(binding.wrap(sketch.ModelToSketchTransform,self._module.IMathTransform).ArrayData,16)!=snapshot['model_to_sketch']):
            raise rejected('sheet_flange_profile_changed','The anonymous native plane or transform changed within the read boundary.')
        self._sheet_flange_feature_current(model,feature,receipt.sketch_identity,receipt.sketch_pid,'ProfileFeature')
        if phase=='before_factory':self._sheet_flange_profile_edge_current(model,receipt,definition,frame)
        self._sheet_state_target_current(model,receipt.source_target)
        return snapshot,members

    def _sheet_flange_profile_current(self,model,receipt,definition,frame):
        if receipt.profile_before is None:
            raise rejected('sheet_flange_profile_unconfirmed','A fully proved own pre-factory profile is required.')
        snapshot,members=self.sheet_flange_sketch_snapshot(model,receipt,definition,frame,'after_factory')
        if not edge_flange_profile_preserved(receipt.profile_before,snapshot,receipt.profile_before_members,members):
            raise rejected('sheet_flange_profile_changed','Factory may migrate projection definitions and names, not native input geometry or driver identities.')
        return snapshot,members

    def _sheet_flange_feature_view_matches(self,model,view,retained,*,depth=0):
        """Bind alternate suppressed-feature views with native PID proof.

        IDs route candidates; they never authorize equivalence. The PID must
        resolve to the retained canonical entity, with equal complete feature
        descriptors and independently bound ownership at this read boundary.
        """
        if view is None or retained is None or depth>12:return False
        if self.identity(view)==self.identity(retained):return True
        summary=self.feature_summary(retained)
        if self.feature_summary(view)!=summary:return False
        left=self.persistent_id(model,view);right=self.persistent_id(model,retained)
        if not left or not right or not self.same_persistent_id(model,left,right):return False
        expected=self.identity(retained)
        permitted=2 if summary['suppressed'] else 0
        for pid in (left,right):
            raw,status=self._extension(model).GetObjectByPersistReference3(self._persistent_variant(pid))
            resolved=binding.wrap(raw,self._module.IFeature)
            if type(status) is not int or status!=permitted or resolved is None or self.identity(resolved)!=expected:return False
        a=binding.wrap(view.GetOwnerFeature(),self._module.IFeature)
        b=binding.wrap(retained.GetOwnerFeature(),self._module.IFeature)
        if not (a is None and b is None or a is not None and b is not None
                and self._sheet_flange_feature_view_matches(model,a,b,depth=depth+1)):return False
        # Close event-free getter races, including a PID retarget while reading
        # the owner. This is evidence for this capture, never an alias cache.
        if self.feature_summary(view)!=summary or self.feature_summary(retained)!=summary:return False
        for feature,pid in ((view,left),(retained,right)):
            closing=self.persistent_id(model,feature)
            if not closing or not self.same_persistent_id(model,pid,closing):return False
            raw,status=self._extension(model).GetObjectByPersistReference3(self._persistent_variant(closing))
            resolved=binding.wrap(raw,self._module.IFeature)
            if type(status) is not int or status!=permitted or resolved is None or self.identity(resolved)!=expected:return False
        return True

    def _sheet_flange_absorbed_view_matches(self,model,view,folder):
        self._sheet_member_reference(model,folder)
        owner=binding.wrap(view.GetOwnerFeature(),self._module.IFeature)
        return (self.feature_summary(view)==self.feature_summary(folder.feature)
            and self._sheet_flange_feature_view_matches(model,owner,folder.owner)
            and sum(self.identity(f)==folder.identity for f in self._sheet_absorbed(folder.owner))==1)

    def _sheet_flange_coalesce_features(self,model,views,known,target):
        """One-shot binding; no cross-capture alias cache or PID-less fallback."""
        by_id={}
        for feature in known:by_id.setdefault(int(feature.GetID()),[]).append(feature)
        result=[];bindings=[]
        folder=next((m for m in target.members if m.role=='fold_sketch_folder'),None)
        for view in views:
            candidates=by_id.get(int(view.GetID()),[]);matches=[]
            for retained in candidates:
                if self.identity(view)==self.identity(retained):matches.append(retained);continue
                if folder is not None and self.identity(retained)==folder.identity:
                    # This folder's native PID resolves to another feature in
                    # SW2023. Its unique current absorption and exact PID-bound
                    # owner provide the documented retained-member strategy.
                    if self._sheet_flange_absorbed_view_matches(model,view,folder):
                        matches.append(retained)
                elif self._sheet_flange_feature_view_matches(model,view,retained):matches.append(retained)
            if len(matches)>1:raise rejected('sheet_flange_feature_collision','Alternate feature view binds multiple retained entities.')
            result.append(matches[0] if matches else view)
            if matches and self.identity(view)!=self.identity(matches[0]):bindings.append((view,matches[0]))
        if not _same_identities([self.identity(f) for f in result],[self.identity(f) for f in result]):
            raise rejected('sheet_flange_feature_collision','Duplicate canonical entities in the complete feature view.')
        self._sheet_state_target_current(model,target)
        for view,retained in bindings:
            valid=(self._sheet_flange_absorbed_view_matches(model,view,folder)
                if folder is not None and self.identity(retained)==folder.identity
                else self._sheet_flange_feature_view_matches(model,view,retained))
            if not valid:raise rejected('sheet_flange_feature_changed','An alternate feature binding changed during the capture.')
        return result

    def _sheet_flange_source_parameters(self,model,target):
        base,sheet=self.sheet_profile_parameters(SimpleNamespace(extrusion=target.base,auxiliary=target.members))
        return dict(base=base,sheet=sheet,options=self.sheet_parameter_options_retained(model,target))

    def new_sheet_flange_receipt(self,model,target,edge):
        target,_=self.sheet_state_target(model,target.base,target)
        pid=self.persistent_id(model,edge)
        if not pid or self.identity(self.resolve_persistent_id(model,pid,'edge'))!=self.identity(edge):
            raise rejected('sheet_flange_edge_changed','The explicit edge needs a canonical persistent reference.')
        return NativeEdgeFlangeReceipt(target,deepcopy(self.part_creation_controls(model)),edge,
            self.identity(edge),pid,tuple(self.features(model)),deepcopy(self._sheet_flange_source_parameters(model,target)),
            source_edge_points=tuple(tuple(p) for p in self.pattern_edge_points(edge)))

    def _sheet_flange_flat_bend(self,model,receipt):
        target=receipt.source_target;flat=next(m.feature for m in target.members if m.role=='flat')
        direct=self._sheet_absorbed(flat)
        original=[m.feature for m in target.members if m.owner is not None and self.identity(m.owner)==self.identity(flat)]
        known=[*receipt.baseline_features,receipt.flange,*(row[0] for row in receipt.owned_children)]
        current=self._sheet_flange_coalesce_features(model,self.features(model),known,target)
        extra=[f for f in current if not any(self.identity(f)==self.identity(old) for old in known)]
        if len(extra)!=1 or extra[0].GetTypeName2()!='UiBend':
            actual=[(int(f.GetID()),str(f.GetTypeName2())) for f in extra]
            raise rejected('sheet_flange_flat_membership','Exactly one new derived UiBend may extend the complete feature census. '
                f'Readback actual={actual}, unmatched_count={len(extra)}.')
        ui=extra[0];owner=binding.wrap(ui.GetOwnerFeature(),self._module.IFeature)
        if not self._sheet_flange_feature_view_matches(model,owner,flat):
            raise rejected('sheet_flange_flat_membership','The new derived bend must have the exact original FlatPattern native owner.')
        allowed=[*original,ui] if any(self.identity(f)==self.identity(ui) for f in direct) else original
        if not _same_identities([self.identity(f) for f in direct],[self.identity(f) for f in allowed]):
            raise rejected('sheet_flange_flat_membership','All original direct flat children must remain exact; only the proved derived bend may be added.')
        parents=ui.GetParents();children=ui.GetChildren()
        if (parents is not None and not isinstance(parents,(list,tuple))
                or children is not None and not isinstance(children,(list,tuple))):
            raise rejected('sheet_flange_flat_membership','Complete native derived-bend dependency arrays are required.')
        parents=[binding.wrap(raw,self._module.IFeature) for raw in parents or ()]
        bend=next(f for f,_,_,kind in receipt.owned_children if kind=='OneBend')
        if len(parents)!=1 or not self._sheet_flange_feature_view_matches(model,parents[0],bend) or children:
            raise rejected('sheet_flange_flat_membership','The exact own OneBend must be the sole parent of the leaf derived UiBend.')
        member=receipt.flat_bend_member
        if member is None:
            pid=self.persistent_id(model,ui)
            if not pid:raise rejected('sheet_flange_flat_membership','The new suppressed native bend needs a strong feature reference.')
            member=NativeSheetMember('flange_flat_bend',ui,self.identity(ui),pid,'owned_persistent_feature_v1',flat)
            self._sheet_member_reference(model,member);receipt.flat_bend_member=member
        else:
            if self.identity(ui)!=member.identity or not self._sheet_flange_feature_view_matches(model,owner,member.owner):
                raise rejected('sheet_flange_flat_membership','A replaced or reparented flat bend cannot become owned.')
            self._sheet_member_reference(model,member)
        return ui

    def _sheet_flange_edge_current(self,model,receipt,definition,frame):
        self._sheet_state_target_current(model,receipt.source_target)
        edge=self.resolve_persistent_id(model,receipt.edge_pid,'edge')
        if not receipt.edge_pid or self.identity(edge)!=receipt.edge_identity:
            raise rejected('sheet_flange_edge_changed','The exact retained edge reference must round-trip.')
        body=self.resolve_persistent_id(model,receipt.source_target.body_pid,'body')
        bodies=self.bodies(model,'all')
        edges=[] if body is None else [binding.wrap(e,self._module.IEdge) for e in body.GetEdges() or ()]
        if (len(bodies)!=1 or body is None or self.identity(body)!=self.identity(bodies[0])
                or body.IsSheetMetal() is not True or sum(self.identity(e)==receipt.edge_identity for e in edges)!=1):
            raise rejected('sheet_flange_edge_membership','The explicit edge must belong uniquely to the retained sole sheet body.')
        points=[]
        for getter in ('GetStartVertex','GetEndVertex'):
            vertex=binding.wrap(getattr(edge,getter)(),self._module.IVertex)
            if vertex is None:raise rejected('sheet_flange_edge_unsupported','The full straight free edge requires two exact endpoints.')
            points.append(vertex.GetPoint())
        if not l_flange_edge_points(points,definition.source,frame):
            raise rejected('sheet_flange_edge_unsupported','Only the full longitudinal free edge on the inner face is supported.')
        return edge

    def _sheet_flange_profile_edge_current(self,model,receipt,definition,frame):
        """Resolve the source edge inside the exact own pre-factory sketch phase.

        Native sketch insertion may refresh topology interfaces. This is not a
        client-reference upgrade or a cross-request alias: the original PID,
        the captured pre-write descriptor, current topology and the entire source
        body/feature/parameter baseline must still agree in this capture.
        """
        if (receipt.sketch is None or receipt.native_sketch is None or receipt.flange is not None
                or receipt.pending_creation or receipt.pending_deletion or receipt.selection_uncertain or receipt.restored):
            raise rejected('sheet_flange_source_phase','Only the exact completed own input sketch permits this source capture.')
        self._sheet_state_target_current(model,receipt.source_target)
        self._sheet_flange_feature_current(model,receipt.sketch,receipt.sketch_identity,receipt.sketch_pid,'ProfileFeature')
        native=binding.wrap(receipt.sketch.GetSpecificFeature2(),self._module.ISketch)
        status=native.GetConstrainedStatus() if native is not None else None
        manager=binding.wrap(model.SketchManager,self._module.ISketchManager)
        if (native is None or self.identity(native)!=self.identity(receipt.native_sketch)
                or type(status) is not int or status!=3 or manager.ActiveSketch is not None):
            raise rejected('sheet_flange_source_phase','Only the same fully defined closed own input sketch permits source binding.')
        if (self.part_creation_controls(model)!=receipt.controls
                or self._sheet_flange_source_parameters(model,receipt.source_target)!=receipt.original_parameters
                or not sheet_l_body_matches(self.dimension_geometry_snapshot(model),definition.source.expected_geometry(frame))):
            raise rejected('sheet_flange_source_changed','The complete original L material, parameters and controls must remain unchanged.')
        allowed=[*receipt.baseline_features,receipt.sketch]
        current=self._sheet_flange_coalesce_features(model,self.features(model),allowed,receipt.source_target)
        if not _same_identities([self.identity(f) for f in current],[self.identity(f) for f in allowed]):
            raise rejected('sheet_flange_source_changed','Only the exact own input sketch may extend the entire baseline census.')
        for member in receipt.source_target.members:self._sheet_member_reference(model,member)
        retained_pid=self.persistent_id(model,receipt.edge)
        if not retained_pid or not self.same_persistent_id(model,retained_pid,receipt.edge_pid):
            raise rejected('sheet_flange_edge_changed','The retained source edge must still report the prepared native PID.')
        edge=self.resolve_persistent_id(model,receipt.edge_pid,'edge');pid=self.persistent_id(model,edge)
        if (not pid or not self.same_persistent_id(model,pid,retained_pid)
                or not l_flange_edge_points(receipt.source_edge_points,definition.source,frame)
                or not l_flange_edge_points(self.pattern_edge_points(edge),definition.source,frame)):
            raise rejected('sheet_flange_edge_changed','Both complete finite source-edge descriptors and native PIDs must agree.')
        body=self.resolve_persistent_id(model,receipt.source_target.body_pid,'body');bodies=self.bodies(model,'all')
        edges=[binding.wrap(raw,self._module.IEdge) for raw in body.GetEdges() or ()]
        token=self.identity(edge)
        if (len(bodies)!=1 or self.identity(body)!=self.identity(bodies[0]) or body.IsSheetMetal() is not True
                or sum(self.identity(e)==token for e in edges)!=1):
            raise rejected('sheet_flange_edge_membership','The resolved source edge must occur exactly once in the sole retained current sheet body.')
        for view in (receipt.edge,edge):
            owner=binding.wrap(view.GetBody(),self._module.IBody2)
            owner_pid=self.persistent_id(model,owner) if owner is not None else b''
            if (not owner_pid or not self.same_persistent_id(model,owner_pid,receipt.source_target.body_pid)
                    or self.identity(self.resolve_persistent_id(model,owner_pid,'body'))!=self.identity(body)):
                raise rejected('sheet_flange_edge_membership','Both source-edge views must bind the exact current owner body by native PID.')
        if self.identity(self.resolve_persistent_id(model,pid,'edge'))!=token:
            raise rejected('sheet_flange_edge_changed','The refreshed source-edge reference changed before capture closed.')
        self._sheet_state_target_current(model,receipt.source_target)
        return edge

    def sheet_flange_parameters(self,feature):
        if feature is None or feature.GetTypeName2()!='EdgeFlange':
            raise rejected('sheet_flange_definition_unavailable','An exact native EdgeFlange definition is required.')
        data=binding.wrap(feature.GetDefinition(),self._module.IEdgeFlangeFeatureData)
        if data is None:raise rejected('sheet_flange_definition_unavailable','The native flange definition is missing.')
        allowance=binding.wrap(data.GetCustomBendAllowance(),self._module.ICustomBendAllowance)
        if allowance is None:raise rejected('sheet_flange_definition_unavailable','Independent custom allowance readback is required.')
        return {**{name:getattr(data,name) for name in OPTION_NAMES},
            'allowance_type':allowance.Type,'k_factor':allowance.KFactor,'edge_count':data.GetEdgeCount()}

    def _sheet_flange_feature_current(self,model,feature,identity,pid,kind):
        current=self.resolve_persistent_id(model,pid,'feature') if pid else None
        if (current is None or self.identity(feature)!=identity or self.identity(current)!=identity
                or feature.GetTypeName2()!=kind):
            raise rejected('sheet_flange_feature_changed','The exact owned '+kind+' reference must round-trip.')
        return current

    def _sheet_flange_children(self,model,receipt):
        flange=self._sheet_flange_feature_current(model,receipt.flange,receipt.flange_identity,receipt.flange_pid,'EdgeFlange')
        children=self._sheet_absorbed(flange)
        if len(children)!=2 or sorted(c.GetTypeName2() for c in children)!=['OneBend','ProfileFeature']:
            raise rejected('sheet_flange_absorption','The flange requires exactly its own profile and one native bend.')
        sketch=next(c for c in children if c.GetTypeName2()=='ProfileFeature')
        if self.identity(sketch)!=receipt.sketch_identity:
            raise rejected('sheet_flange_absorption','A foreign profile cannot be adopted as the created sketch.')
        self._sheet_flange_feature_current(model,receipt.sketch,receipt.sketch_identity,receipt.sketch_pid,'ProfileFeature')
        actual=binding.wrap(sketch.GetSpecificFeature2(),self._module.ISketch)
        status=actual.GetConstrainedStatus() if actual is not None else None
        if (actual is None or self.identity(actual)!=self.identity(receipt.native_sketch)
                or type(status) is not int or status!=3):
            raise rejected('sheet_flange_sketch_unconfirmed','The exact absorbed input sketch must remain fully constrained.')
        retained=receipt.owned_children
        current=[]
        for child in children:
            pid=self.persistent_id(model,child);identity=self.identity(child);kind=child.GetTypeName2()
            self._sheet_flange_feature_current(model,child,identity,pid,kind)
            current.append((child,identity,pid,kind))
        if retained and (not _same_identities([(i,k) for _,i,_,k in retained],[(i,k) for _,i,_,k in current])
                or any(not self.same_persistent_id(model,p,q) for _,i,p,k in retained for _,j,q,l in current if i==j and k==l)):
            raise rejected('sheet_flange_absorption','Owned children changed after the first exact receipt.')
        if not retained:receipt.owned_children=current
        return children

    def sheet_flange_bundle(self,model,receipt):
        """Prove the complete expanded native graph before any naming/deletion."""
        target=receipt.source_target;self._sheet_state_target_current(model,target)
        children=self._sheet_flange_children(model,receipt)
        for member in target.members:self._sheet_member_reference(model,member)
        ui=self._sheet_flange_flat_bend(model,receipt)
        allowed=[*receipt.baseline_features,receipt.flange,*children,ui]
        features=self._sheet_flange_coalesce_features(model,self.features(model),allowed,target)
        identities=[self.identity(f) for f in allowed]
        if not receipt.baseline_features or not _same_identities([self.identity(f) for f in features],identities):
            raise rejected('sheet_flange_foreign_features','Unowned added or missing features prevent adopting the flange graph.')
        body=self.resolve_persistent_id(model,target.body_pid,'body');bodies=self.bodies(model,'all')
        if body is None or len(bodies)!=1 or self.identity(body)!=self.identity(bodies[0]) or body.IsSheetMetal() is not True:
            raise rejected('sheet_flange_body_changed','The exact retained sole sheet body must remain current.')
        actual=[binding.wrap(raw,self._module.IFeature) for raw in body.GetFeatures() or ()]
        expected=[next(m.feature for m in target.members if m.role==role) for role in ('base','sheet','flat')]+[receipt.flange]
        actual=self._sheet_flange_coalesce_features(model,actual,expected,target)
        if not _same_identities([self.identity(f) for f in actual],[self.identity(f) for f in expected]):
            raise rejected('sheet_flange_body_membership','The sole sheet body must bind exactly the original base/sheet/flat and new flange.')
        cut=next(m.feature for m in target.members if m.role=='cut_list')
        folder=binding.wrap(cut.GetSpecificFeature2(),self._module.IBodyFolder)
        members=[] if folder is None else [binding.wrap(v,self._module.IBody2) for v in folder.GetBodies() or ()]
        if len(members)!=1 or self.identity(members[0])!=self.identity(body):
            raise rejected('sheet_flange_cut_list_membership','The exact original cut list must uniquely contain this body.')
        if self._sheet_flange_source_parameters(model,target)!=receipt.original_parameters:
            raise rejected('sheet_flange_source_parameters_changed','Original base/sheet/template, relief, gauge and K-factor must remain unchanged.')
        return dict(body=body,cut_list=cut,children=children,flat_bend=ui)

    def sheet_flange_preserve_names(self,model,receipt,definition,frame,body_name,cut_list_name):
        if (receipt.pending_creation or not native_flange_parameters_match(self.sheet_flange_parameters(receipt.flange),definition)
                or not sheet_u_body_matches(self.dimension_geometry_snapshot(model),definition.expected_geometry(frame))):
            raise rejected('sheet_flange_effect_unconfirmed','Complete U shape and independent parameter readback must precede naming.')
        bundle=self.sheet_flange_bundle(model,receipt)
        self._sheet_flange_profile_current(model,receipt,definition,frame)
        desired=[(receipt.flange,definition.feature_name),(receipt.sketch,definition.sketch_name),
            (next(f for f in bundle['children'] if f.GetTypeName2()=='OneBend'),'Сгиб отбортовки'),
            (bundle['flat_bend'],'Развёртка сгиба отбортовки'),(bundle['cut_list'],cut_list_name)]
        owned=[self.identity(f) for f,_ in desired];names=[n.casefold() for _,n in desired]
        known=[*receipt.baseline_features,receipt.flange,*bundle['children'],bundle['flat_bend']]
        current=self._sheet_flange_coalesce_features(model,self.features(model),known,receipt.source_target)
        others={str(f.Name).casefold() for f in current if not any(self.identity(f)==token for token in owned)}
        if len(set(names))!=len(names) or any(n in others for n in names):
            raise rejected('sheet_name_collision','Russian own-node names cannot collide with preserved model nodes.')
        for feature,name in desired:
            feature.Name=name
            if feature.Name!=name:raise rejected('sheet_name_mismatch','An exact owned node did not retain its requested name.')
        bundle['body'].Name=body_name
        if bundle['body'].Name!=body_name:raise rejected('sheet_name_mismatch','The original native body name was not retained.')
        self.sheet_flange_bundle(model,receipt)
        self._sheet_flange_profile_current(model,receipt,definition,frame)

    def restore_completed_sheet_flange(self,model,receipt,definition,frame,body_name,cut_list_name):
        """Delete one fully proved own flange; partial/unknown writes stay held.

        This is only the completed-U restoration path. It must not be used as
        a generic cleanup of an interrupted sketch or an unconfirmed factory.
        The domain must separately verify its entire original semantic capture.
        """
        if (receipt.pending_creation or receipt.pending_deletion or receipt.selection_uncertain or receipt.restored
                or self.part_creation_controls(model)!=receipt.controls):
            raise rejected('sheet_flange_restore_unsafe','Unknown, already restored or changed-control state cannot authorize deletion.')
        manager=binding.wrap(model.SketchManager,self._module.ISketchManager)
        if manager.ActiveSketch is not None:
            raise rejected('sheet_flange_restore_unsafe','Never close an unrelated or incomplete sketch as completed-U restoration.')
        if (not native_flange_parameters_match(self.sheet_flange_parameters(receipt.flange),definition)
                or not sheet_u_body_matches(self.dimension_geometry_snapshot(model),definition.expected_geometry(frame))):
            raise rejected('sheet_flange_restore_unsafe','Only the complete intended U state authorizes this scoped deletion.')
        self.sheet_flange_bundle(model,receipt)
        self._sheet_flange_profile_current(model,receipt,definition,frame)
        with preserved_selection(self,model,state=receipt,label='sheet_flange_restore'):
            model.ClearSelection2(True)
            if receipt.flange.Select2(False,0) is not True:
                raise rejected('sheet_flange_restore_unsafe','The exact owned flange could not be selected.')
            selections=binding.wrap(model.SelectionManager,self._module.ISelectionMgr)
            selected=binding.wrap(selections.GetSelectedObject6(1,0),self._module.IFeature)
            if (selections.GetSelectedObjectCount2(-1)!=1 or selections.GetSelectedObjectCount2(0)!=1
                    or selected is None or self.identity(selected)!=receipt.flange_identity):
                raise rejected('sheet_flange_restore_unsafe','Only the exact own flange may be selected for scoped deletion.')
            receipt.pending_deletion=True
            # Only absorbed own children; no delete-children/dependants flag.
            if self._extension(model).DeleteSelection2(2) is not True:
                raise ExecutionFailure('sheet_flange_deletion_unconfirmed','Native own-flange deletion was not confirmed.',uncertain=True)
            receipt.pending_deletion=False
            if model.ForceRebuild3(False) is not True:
                raise rejected('sheet_flange_restore_unsafe','The original L-sheet rebuild was not confirmed.')
        target,body=self.sheet_state_target(model,receipt.source_target.base,receipt.source_target)
        current=self._sheet_flange_coalesce_features(model,self.features(model),receipt.baseline_features,target)
        if (not sheet_l_body_matches(self.dimension_geometry_snapshot(model),definition.source.expected_geometry(frame))
                or self._sheet_flange_source_parameters(model,target)!=receipt.original_parameters
                or not _same_identities([self.identity(f) for f in current],[self.identity(f) for f in receipt.baseline_features])):
            raise rejected('sheet_flange_restore_unsafe','The exact baseline features, original allowances and full L geometry must all return.')
        cut=next(m.feature for m in target.members if m.role=='cut_list')
        body.Name=body_name;cut.Name=cut_list_name
        if (body.Name!=body_name or cut.Name!=cut_list_name
                or self.part_creation_controls(model)!=receipt.controls):
            raise rejected('sheet_flange_restore_unsafe','Original names and controls were not restored.')
        receipt.restored=True

    def create_sheet_edge_flange(self,model,definition,frame,receipt):
        """One native write attempt; no retry, cleanup, Undo or success journal."""
        if (receipt.pending_creation or receipt.pending_deletion or receipt.restored or receipt.sketch is not None or receipt.flange is not None
                or self.part_creation_controls(model)!=receipt.controls):
            raise rejected('sheet_flange_receipt_unavailable','A fresh receipt with unchanged native controls is required.')
        target,body=self.sheet_state_target(model,receipt.source_target.base,receipt.source_target)
        if (not receipt.baseline_features
                or not _same_identities([self.identity(f) for f in self.features(model)],[self.identity(f) for f in receipt.baseline_features])
                or self._sheet_flange_source_parameters(model,target)!=receipt.original_parameters):
            raise rejected('sheet_flange_baseline_changed','The complete retained feature and original parameter baseline changed.')
        if (not sheet_l_body_matches(self.dimension_geometry_snapshot(model),definition.source.expected_geometry(frame))
                or not sheet_l_native_parameters_match(*self.sheet_profile_parameters(
                    SimpleNamespace(extrusion=target.base,auxiliary=target.members)),definition.source)):
            raise rejected('sheet_flange_source_unconfirmed','The entire folded source shape and original bend allowance must match.')
        edge=self._sheet_flange_edge_current(model,receipt,definition,frame)
        manager=binding.wrap(model.SketchManager,self._module.ISketchManager)
        if manager.ActiveSketch is not None:
            raise rejected('sheet_flange_open_sketch','An unrelated active sketch prevents creation.')
        names={str(f.Name).casefold() for f in self.features(model)}
        if any(n.casefold() in names for n in (definition.sketch_name,definition.feature_name,'Сгиб отбортовки')):
            raise rejected('sheet_name_collision','New Russian names must not replace existing model nodes.')
        model.ClearSelection2(True)
        receipt.pending_creation=True
        feature=binding.wrap(model.InsertSketchForEdgeFlange(edge,math.pi/2.,False),self._module.IFeature)
        if feature is None:raise ExecutionFailure('sheet_flange_creation_unconfirmed','No exact sketch returned.',uncertain=True)
        receipt.sketch=feature;receipt.sketch_identity=self.identity(feature);receipt.sketch_pid=self.persistent_id(model,feature)
        receipt.pending_creation=False
        self._sheet_flange_feature_current(model,feature,receipt.sketch_identity,receipt.sketch_pid,'ProfileFeature')
        if feature.Select2(False,0) is not True:raise rejected('sheet_flange_sketch_select_failed','The own sketch could not be selected.')
        model.EditSketch();sketch=binding.wrap(manager.ActiveSketch,self._module.ISketch)
        if sketch is None:raise ExecutionFailure('sheet_flange_creation_unconfirmed','No exact active sketch returned.',uncertain=True)
        receipt.native_sketch=sketch
        specific=binding.wrap(feature.GetSpecificFeature2(),self._module.ISketch)
        if specific is None or self.identity(specific)!=self.identity(sketch):
            raise rejected('sheet_flange_sketch_changed','The active sketch must be the exact returned profile.')
        entity=binding.wrap(edge,self._module.IEntity)
        if entity.Select4(False,None) is not True or manager.SketchUseEdge(False) is not True:
            raise rejected('sheet_flange_edge_conversion_failed','The exact prepared native edge must be converted.')
        segments=list(sketch.GetSketchSegments() or ())
        if len(segments)!=1:raise rejected('sheet_flange_profile_unconfirmed','Exactly one converted source segment is required.')
        line=binding.wrap(segments[0],self._module.ISketchLine)
        def point(segment,getter):return binding.wrap(getattr(segment,getter)(),self._module.ISketchPoint)
        start=point(line,'GetStartPoint2');end=point(line,'GetEndPoint2')
        p0=(start.X,start.Y,0.);p1=(end.X,end.Y,0.)
        p0,p1,p2,p3=_flange_profile_corners(p0,p1,definition.source.length_mm/1000.,definition.profile_height_mm/1000.)
        add,display=manager.AddToDB,manager.DisplayWhenAdded;lines=[]
        try:
            manager.AddToDB=True;manager.DisplayWhenAdded=False
            for left,right in ((p1,p2),(p2,p3),(p3,p0)):
                segment=binding.wrap(manager.CreateLine(*left,*right),self._module.ISketchLine)
                if segment is None:raise rejected('sheet_flange_profile_unconfirmed','A complete closed own profile is required.')
                lines.append(segment)
        finally:manager.AddToDB=add;manager.DisplayWhenAdded=display
        definer=SketchDefiner(model,self._module,manager,sketch,end);paused=definer._pause()
        try:
            chain=[line,*lines]
            for left,right in zip(chain,chain[1:]+chain[:1]):
                a=point(left,'GetEndPoint2');b=point(right,'GetStartPoint2')
                if tuple(a.GetID())!=tuple(b.GetID()):definer._relate(SW_CONSTRAINT_COINCIDENT,'coincident',a,b)
            for segment in (lines[0],lines[2]):definer._relate(SW_CONSTRAINT_VERTICAL,'vertical',segment)
            definer._relate(SW_CONSTRAINT_HORIZONTAL,'horizontal',lines[1])
            receipt.driver_name=definer._dimension(model.AddVerticalDimension2,point(lines[0],'GetEndPoint2'),'Вылет от внутреннего ребра')
        finally:definer._resume(paused)
        if definer.fully_defined() is not True:raise rejected('sheet_flange_underdefined','The own input profile must be fully constrained.')
        manager.InsertSketch(True)
        if manager.ActiveSketch is not None:raise rejected('sheet_flange_sketch_changed','The own sketch did not close.')
        receipt.driver=binding.wrap(model.Parameter(receipt.driver_name),self._module.IDimension)
        if receipt.driver is None:raise rejected('sheet_flange_driver_changed','The exact own height driver must be retained before factory.')
        receipt.driver_identity=self.identity(receipt.driver)
        receipt.profile_before,receipt.profile_before_members=self.sheet_flange_sketch_snapshot(model,receipt,definition,frame,'before_factory')
        edge=self._sheet_flange_profile_edge_current(model,receipt,definition,frame)
        factory=binding.wrap(model.FeatureManager,self._module.IFeatureManager)
        data=binding.wrap(factory.CreateDefinition(37),self._module.IEdgeFlangeFeatureData)
        if data is None:raise rejected('sheet_flange_definition_unavailable','The native EdgeFlange factory definition is required.')
        code=data.AddEdges(VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_DISPATCH,[edge]),
            VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_DISPATCH,[sketch]))
        if type(code) is not int or code!=0:raise rejected('sheet_flange_add_edges_failed','Native typed edge/profile binding was rejected.')
        for key,value in flange_options(definition).items():setattr(data,key,value)
        allowance=binding.wrap(data.GetCustomBendAllowance(),self._module.ICustomBendAllowance)
        if allowance is None:raise rejected('sheet_flange_definition_unavailable','Explicit custom K-factor definition is required.')
        allowance.Type=2;allowance.KFactor=definition.k_factor;data.SetCustomBendAllowance(allowance)
        self._sheet_state_target_current(model,target);receipt.pending_creation=True
        flange=binding.wrap(factory.CreateFeature(data),self._module.IFeature)
        if flange is None:raise ExecutionFailure('sheet_flange_creation_unconfirmed','No exact flange returned.',uncertain=True)
        receipt.flange=flange;receipt.flange_identity=self.identity(flange);receipt.flange_pid=self.persistent_id(model,flange)
        receipt.pending_creation=False
        self._sheet_flange_feature_current(model,flange,receipt.flange_identity,receipt.flange_pid,'EdgeFlange')
        if model.ForceRebuild3(False) is not True:raise rejected('sheet_flange_rebuild_failed','Native rebuilding was not confirmed.')
        if (not native_flange_parameters_match(self.sheet_flange_parameters(flange),definition)
                or not sheet_u_body_matches(self.dimension_geometry_snapshot(model),definition.expected_geometry(frame))):
            raise rejected('sheet_flange_effect_unconfirmed','Independent requested parameters and complete U geometry must both match.')
        self._sheet_flange_children(model,receipt)
        self.sheet_flange_bundle(model,receipt)
        self._sheet_flange_profile_current(model,receipt,definition,frame)
        if self.part_creation_controls(model)!=receipt.controls:
            raise rejected('sheet_flange_controls_changed','The original native sketch controls were not restored.')
