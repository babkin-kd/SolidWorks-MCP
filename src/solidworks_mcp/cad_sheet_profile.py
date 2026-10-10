"""Owning-STA sheet base construction; explicit profile and custom bend allowance."""

from dataclasses import dataclass,field
import math

from . import binding
from .cad_part_creation import NativeBaseReceipt
from .documents import rejected
from .jobs import ExecutionFailure


@dataclass
class NativeSheetReceipt(NativeBaseReceipt):
    auxiliary:list=field(default_factory=list)
    body_pid:bytes=b''


@dataclass
class NativeSheetMember:
    role:str
    feature:object
    identity:object
    persistent_id:bytes
    reference_strategy:str
    owner:object=None


class CadSheetProfileMixin:
    def new_sheet_profile_receipt(self,model,features,controls):
        base=self.new_base_receipt(model,features,controls)
        return NativeSheetReceipt(base.model_identity,base.configuration_identity,base.baseline_features,base.controls)

    def _sheet_body_current(self,model,receipt):
        bodies=self.bodies(model,'all')
        if len(bodies)!=1 or not receipt.body_pid:
            raise rejected('sheet_body_changed','The exact owned single sheet-metal body is required.')
        current=self.resolve_persistent_id(model,receipt.body_pid,'body')
        fresh_pid=self.persistent_id(model,bodies[0])
        if (self.identity(current)!=self.identity(bodies[0]) or self.identity(current)!=receipt.body_identity
                or not fresh_pid or not self.same_persistent_id(model,receipt.body_pid,fresh_pid)
                or bodies[0].GetType()!=0 or bodies[0].IsSheetMetal() is not True):
            raise rejected('sheet_body_changed','Owned body persistent reference and exact current native identity disagree.')
        return bodies[0]

    def _sheet_member_reference(self,model,member):
        feature=member.feature
        if self.identity(feature)!=member.identity:
            raise rejected('sheet_auxiliary_changed','An exact retained auxiliary handle changed.')
        if member.reference_strategy=='owned_absorption_v1':
            # SW2023 returns a misleading PID for FoldUpDownSketchFolder.
            # Its exact retained handle is proved through the owning flat
            # pattern and its complete documented absorption traversal.
            owner=binding.wrap(feature.GetOwnerFeature(),self._module.IFeature)
            if owner is None or self.identity(owner)!=self.identity(member.owner):
                raise rejected('sheet_auxiliary_changed','The owned absorbed folder lost its exact parent.')
            current=self._sheet_absorbed(member.owner)
            if sum(self.identity(item)==member.identity for item in current)!=1:
                raise rejected('sheet_auxiliary_changed','The exact absorbed folder is not uniquely current.')
            return
        raw,status=self._extension(model).GetObjectByPersistReference3(self._persistent_variant(member.persistent_id))
        resolved=binding.wrap(raw,self._module.IFeature)
        summary=self.feature_summary(feature)
        permitted_status=2 if summary['suppressed'] else 0
        if type(status) is not int or status!=permitted_status or resolved is None or self.identity(resolved)!=member.identity:
            raise rejected('sheet_auxiliary_changed','Owned feature reference or native suppression state did not round-trip.')

    def _sheet_absorbed(self,parent):
        result=[];current=binding.wrap(parent.GetFirstSubFeature(),self._module.IFeature)
        while current is not None:
            if len(result)>=12 or any(self.identity(item)==self.identity(current) for item in result):
                raise rejected('sheet_absorption_invalid','Own base/flat absorption must be complete, bounded and acyclic.')
            owner=binding.wrap(current.GetOwnerFeature(),self._module.IFeature)
            if owner is None or self.identity(owner)!=self.identity(parent):
                raise rejected('sheet_absorption_invalid','An absorbed feature does not bind the exact parent.')
            result.append(current)
            current=binding.wrap(current.GetNextSubFeature(),self._module.IFeature)
        return result

    def _sheet_bundle(self,model,receipt):
        """Derive ownership through body membership/getters/absorption, not names."""
        self._base_target(model,receipt)
        body=self._sheet_body_current(model,receipt)
        cls=self._module.IFeature;factory=binding.wrap(model.FeatureManager,self._module.IFeatureManager)
        features=self.features(model);body_features=[binding.wrap(raw,cls) for raw in body.GetFeatures() or ()]
        if len(body_features)!=3 or len({int(f.GetID()) for f in body_features})!=3:
            raise rejected('sheet_body_membership_changed','The own single-bend body requires exactly its sheet/base/flat features.')
        def exact_kind(items,kind):
            matches=[f for f in items if f.GetTypeName2()==kind]
            if len(matches)!=1:raise rejected('sheet_bundle_unsupported','Expected one exact native '+kind+' member.')
            return matches[0]
        base=exact_kind(body_features,'SMBaseFlange');sheet=exact_kind(body_features,'SheetMetal');flat=exact_kind(body_features,'FlatPattern')
        if self.identity(base)!=receipt.extrusion_identity:
            raise rejected('sheet_body_membership_changed','Body membership does not bind the exact returned base feature.')
        folders=[]
        for getter,interface,count,members,expected,kind,role in (
                ('GetSheetMetalFolder','ISheetMetalFolder','GetSheetMetalCount','GetSheetMetals',sheet,'TemplateSheetMetal','sheet_folder'),
                ('GetFlatPatternFolder','IFlatPatternFolder','GetFlatPatternCount','GetFlatPatterns',flat,'TemplateFlatPattern','flat_folder')):
            folder=binding.wrap(getattr(factory,getter)(),getattr(self._module,interface))
            if folder is None:raise rejected('sheet_folder_unavailable','The documented native sheet/flat folder is required.')
            count_value=getattr(folder,count)();items=[binding.wrap(raw,cls) for raw in getattr(folder,members)() or ()]
            feature=binding.wrap(folder.GetFeature(),cls)
            if (type(count_value) is not int or count_value!=1 or len(items)!=1 or self.identity(items[0])!=self.identity(expected)
                    or feature is None or feature.GetTypeName2()!=kind):
                raise rejected('sheet_folder_membership_changed','The native folder must uniquely contain the exact owned body feature.')
            folders.append((role,feature,None))
        absorbed_base=self._sheet_absorbed(base)
        if len(absorbed_base)!=2 or not any(self.identity(f)==receipt.sketch_identity for f in absorbed_base):
            raise rejected('sheet_absorption_invalid','The exact own base profile and one sketch bend are required.')
        bend=exact_kind(absorbed_base,'SketchBend')
        absorbed_flat=self._sheet_absorbed(flat)
        profiles=[f for f in absorbed_flat if f.GetTypeName2()=='ProfileFeature']
        if len(absorbed_flat)!=4 or len(profiles)!=2:
            raise rejected('sheet_absorption_invalid','The own folded flat pattern requires its complete four-node absorption.')
        ui_bend=exact_kind(absorbed_flat,'UiBend');fold_folder=exact_kind(absorbed_flat,'FoldUpDownSketchFolder')
        # Enumeration can assign display names to already proven own handles;
        # it never resolves a client target or establishes ownership.
        profiles.sort(key=lambda f:int(f.GetID()))
        cut_lists=[]
        for feature in features:
            if feature.GetTypeName2()!='CutListFolder':continue
            folder=binding.wrap(feature.GetSpecificFeature2(),self._module.IBodyFolder)
            members=[binding.wrap(raw,self._module.IBody2) for raw in folder.GetBodies() or ()]
            if len(members)==1 and self.identity(members[0])==receipt.body_identity:cut_lists.append(feature)
        if len(cut_lists)!=1:raise rejected('sheet_cut_list_unsupported','One exact cut-list folder must uniquely contain the own body.')
        derived=[('sheet',sheet,None),('flat',flat,None),('bend',bend,base),('flat_sketch_1',profiles[0],flat),
            ('flat_sketch_2',profiles[1],flat),('ui_bend',ui_bend,flat),('fold_sketch_folder',fold_folder,flat),
            ('cut_list',cut_lists[0],None),*folders]
        owned=[receipt.sketch,receipt.extrusion]+[f for _,f,_ in derived]
        tokens=[self.identity(f) for f in owned]
        if any(token==other for i,token in enumerate(tokens) for other in tokens[:i]):
            raise rejected('sheet_ownership_collision','Every owned profile/base/auxiliary must be a distinct exact native feature.')
        if any(token==old for token in tokens for old,_ in receipt.baseline_features):
            raise rejected('sheet_ownership_collision','An existing baseline node cannot become an owned auxiliary.')
        # All ownership was derived independently above. Tree differences only
        # detect residual foreign state and never supply candidate handles.
        added=[f for f in features if not any(self.identity(f)==old for old,_ in receipt.baseline_features)]
        enumerated=[receipt.sketch,base,sheet,flat,bend,*profiles,ui_bend,fold_folder,cut_lists[0]]
        if (len(added)!=len(enumerated) or any(sum(self.identity(f)==self.identity(candidate) for candidate in added)!=1 for f in enumerated)):
            raise rejected('sheet_foreign_features','Unowned new state prevents naming or deletion of the own bundle.')
        allowed=tokens+[old for old,_ in receipt.baseline_features]
        for f in owned:
            for method in ('GetParents','GetChildren'):
                related=getattr(f,method)() or ()
                if len(related)>12 or any(not any(self.identity(binding.wrap(raw,cls))==token for token in allowed) for raw in related):
                    raise rejected('sheet_foreign_dependencies','Unowned native dependencies prevent bundle changes.')
        if not receipt.auxiliary:
            for role,feature,owner in derived:
                strategy='owned_absorption_v1' if role=='fold_sketch_folder' else 'owned_persistent_feature_v1'
                pid=b'' if strategy=='owned_absorption_v1' else self.persistent_id(model,feature)
                if strategy!='owned_absorption_v1' and not pid:raise rejected('sheet_reference_unavailable','Owned auxiliary requires a native persistent reference.')
                member=NativeSheetMember(role,feature,self.identity(feature),pid,strategy,owner)
                self._sheet_member_reference(model,member)
                receipt.auxiliary.append(member)
        else:
            if {member.role for member in receipt.auxiliary}!={role for role,_,_ in derived}:
                raise rejected('sheet_auxiliary_changed','The retained bundle is incomplete.')
            for member in receipt.auxiliary:
                current=next(f for role,f,_ in derived if role==member.role)
                if self.identity(current)!=member.identity:raise rejected('sheet_auxiliary_changed','Native membership replaced an owned handle.')
                self._sheet_member_reference(model,member)
        return receipt.auxiliary

    def sheet_profile_parameters(self,receipt):
        base=binding.wrap(receipt.extrusion.GetDefinition(),self._module.IBaseFlangeFeatureData)
        feature=next(member.feature for member in receipt.auxiliary if member.role=='sheet')
        sheet=binding.wrap(feature.GetDefinition(),self._module.ISheetMetalFeatureData)
        allowance=binding.wrap(sheet.GetCustomBendAllowance(),self._module.ICustomBendAllowance)
        if base is None or sheet is None or allowance is None:
            raise rejected('sheet_native_definition_unavailable','Independent native base and sheet allowance definitions are required.')
        base_parameters={name:getattr(base,name) for name in ('Thickness','BendRadius','ReverseThickness','ReverseDirection',
            'D1EndConditionDistance','D1EndConditionType','D2EndConditionDistance','D2EndConditionType','UseDefaultBendAllowance',
            'UseGaugeTable','UseMaterialSheetMetalParameters','OverrideDefaultSheetMetalParameters','SymmetricThickness')}
        sheet_parameters=dict(thickness=sheet.Thickness,radius=sheet.BendRadius,allowance_type=allowance.Type,
            k_factor=allowance.KFactor,use_material=sheet.UseMaterialSheetMetalParameters)
        return base_parameters,sheet_parameters

    def _name_sheet_bundle(self,model,receipt):
        names=dict(sheet='Параметры листового тела',flat='Развёртка листового тела',bend='Сгиб профиля',
            flat_sketch_1='Служебный эскиз развёртки 1',flat_sketch_2='Служебный эскиз развёртки 2',
            ui_bend='Сгиб развёртки',fold_sketch_folder='Эскизы сгиба',cut_list='Список вырезов',
            sheet_folder='Параметры листового металла',flat_folder='Развёртки листового металла')
        if {member.role for member in receipt.auxiliary}!=set(names):
            raise rejected('sheet_names_unconfirmed','An incomplete auxiliary bundle cannot authorize naming.')
        baseline_names={summary['name'].casefold() for _,summary in receipt.baseline_features}
        if baseline_names & {name.casefold() for name in names.values()}:
            raise rejected('sheet_name_collision','An auxiliary Russian name conflicts with a baseline node.')
        for member in receipt.auxiliary:
            self._sheet_member_reference(model,member)
            member.feature.Name=names[member.role]
            if member.feature.Name!=names[member.role]:raise rejected('sheet_name_mismatch','Owned auxiliary did not retain its Russian name.')

    def create_sheet_l_profile(self,model,plane,definition,receipt):
        self._base_target(model,receipt)
        if self.part_creation_controls(model)!=receipt.controls or self.bodies(model,'all'):
            raise rejected('sheet_target_changed','Only the prepared empty native part is writable.')
        manager=binding.wrap(model.SketchManager,self._module.ISketchManager)
        if manager.ActiveSketch is not None:raise rejected('sheet_open_sketch','An unrelated active sketch prevents creation.')
        from .session import SolidWorksSession
        from .sketch_constraints import SketchDefiner
        with self._base_selection(model,receipt):
            if not plane.Select2(False,0):raise rejected('sheet_plane_select_failed','The explicit plane could not be selected.')
            receipt.pending_creation=True
            manager.InsertSketch(True)
            sketch=binding.wrap(manager.ActiveSketch,self._module.ISketch)
            if sketch is None:raise ExecutionFailure('sheet_sketch_unconfirmed','No exact native active sketch returned.',uncertain=True)
            receipt.native_sketch,receipt.native_sketch_identity=sketch,self.identity(sketch)
            feature=self._retain_base_feature(model,receipt,'sketch',self._feature_for_exact_sketch(model,sketch))
            feature.Name=definition.sketch_name
            if feature.Name!=definition.sketch_name:raise rejected('sheet_name_mismatch','Russian sketch name was not retained.')
            lines=SolidWorksSession._draw_polyline(manager,definition.profile_m,closed=False)
            origins=[item for item in self.features(model) if item.GetTypeName2()=='OriginProfileFeature']
            if len(origins)!=1:raise rejected('sheet_origin_unavailable','The unique exact native origin is required.')
            points=binding.wrap(origins[0].GetSpecificFeature2(),self._module.ISketch).GetSketchPoints2()
            if points is None or len(points)!=1:raise rejected('sheet_origin_unavailable','The unique native origin point is required.')
            names={(axis,i):name for axis,name in (('x','Ширина полки'),('y','Высота полки')) for i in range(8)}
            definer=SketchDefiner(model,self._module,manager,sketch,binding.wrap(points[0],self._module.ISketchPoint))
            definer.define(lines,names=names,origin_mm=(0.,0.))
            if definer.fully_defined() is not True:raise rejected('sheet_underdefined','Both profile lines must be fully defined.')
            self._base_target(model,receipt)
            active=binding.wrap(manager.ActiveSketch,self._module.ISketch)
            if active is None or self.identity(active)!=receipt.native_sketch_identity:
                raise rejected('sheet_sketch_changed','The owned sketch changed before closing.')
            manager.InsertSketch(True)
            if manager.ActiveSketch is not None or not feature.Select2(False,0):
                raise rejected('sheet_profile_select_failed','The exact own closed sketch could not be selected.')
            factory=binding.wrap(model.FeatureManager,self._module.IFeatureManager)
            allowance=binding.wrap(factory.CreateCustomBendAllowance(),self._module.ICustomBendAllowance)
            if allowance is None:raise rejected('sheet_allowance_unavailable','No native custom bend allowance returned.')
            allowance.Type=2
            allowance.KFactor=definition.k_factor
            if allowance.Type!=2 or abs(float(allowance.KFactor)-definition.k_factor)>1e-12:
                raise rejected('sheet_allowance_mismatch','The explicit K-factor was not retained by the custom allowance.')
            self._base_target(model,receipt)
            receipt.pending_creation=True
            # SW2023 still exposes this established factory. Relief ratio .5
            # is independent of the mandatory K-factor supplied through PCBA.
            raw=factory.InsertSheetMetalBaseFlange2(definition.thickness_mm/1000.,True,definition.bend_radius_mm/1000.,
                definition.length_mm/1000.,0.,False,0,0,1,allowance,False,2,.0001,.0001,.5,True,False,True,True)
            base=self._retain_base_feature(model,receipt,'extrusion',raw)
            if base.GetTypeName2()!='SMBaseFlange':raise rejected('sheet_native_type_mismatch','Only a native sheet-metal base flange is accepted.')
            base.Name=definition.feature_name
            if base.Name!=definition.feature_name:raise rejected('sheet_name_mismatch','Russian base feature name was not retained.')
            if not self.rebuild_dimension_document(model):raise rejected('sheet_rebuild_failed','Native rebuild did not finish.')
            bodies=self.bodies(model,'all')
            if len(bodies)!=1 or bodies[0].GetType()!=0 or bodies[0].IsSheetMetal() is not True:
                raise rejected('sheet_body_mismatch','Exactly one native solid sheet-metal body is required.')
            receipt.body,receipt.body_identity=bodies[0],self.identity(bodies[0])
            receipt.body_pid=self.persistent_id(model,bodies[0])
            receipt.body.Name=definition.body_name
            if receipt.body.Name!=definition.body_name:raise rejected('sheet_name_mismatch','Russian body name was not retained.')
            from .sheet_profile_definition import sheet_l_body_matches,sheet_l_native_parameters_match
            frame=self.reference_plane_transform(plane)
            if not sheet_l_body_matches(self.dimension_geometry_snapshot(model),definition.expected_geometry(frame)):
                raise rejected('sheet_shape_unconfirmed','The complete folded material boundaries must match before auxiliary writes.')
            self._sheet_bundle(model,receipt)
            parameters=self.sheet_profile_parameters(receipt)
            if not sheet_l_native_parameters_match(*parameters,definition):
                raise rejected('sheet_parameters_unconfirmed','Native thickness/radius/direction/custom K must match before auxiliary writes.')
            # D2 is the native base-flange longitudinal parameter in the
            # established SW2023 factory; prove exact owner, type and value.
            dimension=binding.wrap(base.Parameter('D2'),self._module.IDimension)
            owner=binding.wrap(dimension.GetFeatureOwner(),self._module.IFeature) if dimension is not None else None
            configuration=binding.wrap(model.GetActiveConfiguration(),self._module.IConfiguration).Name
            values=dimension.GetSystemValue3(3,self._named_configuration(configuration)) if dimension is not None else None
            if (dimension is None or owner is None or self.identity(owner)!=receipt.extrusion_identity
                    or dimension.GetType()!=0 or values is None or len(values)!=1
                    or not math.isfinite(float(values[0])) or abs(float(values[0])-definition.length_mm/1000.)>1e-12):
                raise rejected('sheet_length_dimension_unconfirmed','The exact own native longitudinal driver is required.')
            dimension.Name='Длина профиля'
            if dimension.Name!='Длина профиля':raise rejected('sheet_name_mismatch','The owned length dimension did not retain its Russian name.')
            self._name_sheet_bundle(model,receipt)
        if self.part_creation_controls(model)!=receipt.controls:raise rejected('sheet_controls_changed','Original sketch controls were not restored.')

    def sheet_profile_evidence(self,model,receipt):
        evidence=self.base_rectangle_evidence(model,receipt)
        if receipt.restored:return evidence,()
        if evidence.get('complete') is not True:
            return {**evidence,'controls':self.part_creation_controls(model)},()
        members=self._sheet_bundle(model,receipt)
        snapshot,sketch_members=self.sketch_snapshot(model,receipt.sketch)
        base_parameters,sheet_parameters=self.sheet_profile_parameters(receipt)
        evidence.update(base_native_id=int(receipt.extrusion.GetID()),sketch=snapshot,
            auxiliary=[dict(role=member.role,reference_strategy=member.reference_strategy,
                pid_hex=member.persistent_id.hex(),**self.feature_summary(member.feature)) for member in members],
            base_parameters=base_parameters,sheet_parameters=sheet_parameters,body_pid_hex=receipt.body_pid.hex())
        evidence.pop('extrusion_native_id',None)
        return evidence,sketch_members

    def restore_sheet_profile(self,model,receipt):
        """Delete only a fully proved own bundle; domain full proof is mandatory."""
        self._base_target(model,receipt)
        if receipt.pending_creation or receipt.selection_uncertain or receipt.restored:
            raise rejected('sheet_restore_unsafe','Unknown creation, selection or already restored state cannot authorize deletion.')
        members=self._sheet_bundle(model,receipt)
        if self.part_creation_controls(model)!=receipt.controls:
            raise rejected('sheet_restore_unsafe','Native controls differ from the prepared baseline.')
        manager=binding.wrap(model.SketchManager,self._module.ISketchManager)
        if manager.ActiveSketch is not None:
            raise rejected('sheet_restore_unsafe','Never close an unrelated sketch during bundle restoration.')
        roots=[member.feature for member in members if member.role in ('sheet','flat','cut_list','sheet_folder','flat_folder')]
        roots.append(receipt.extrusion)
        tokens=[receipt.sketch_identity,receipt.extrusion_identity]+[member.identity for member in members]
        with self._base_selection(model,receipt):
            model.ClearSelection2(True)
            for index,feature in enumerate(roots):
                if not feature.Select2(index!=0,0):raise rejected('sheet_restore_unsafe','Selection of an exact own root failed.')
            selections=binding.wrap(model.SelectionManager,self._module.ISelectionMgr)
            selected=[binding.wrap(selections.GetSelectedObject6(i,0),self._module.IFeature)
                for i in range(1,selections.GetSelectedObjectCount2(0)+1)]
            if (len(selected)!=len(roots) or selections.GetSelectedObjectCount2(-1)!=len(roots)
                    or any(sum(self.identity(item)==self.identity(root) for item in selected)!=1 for root in roots)):
                raise rejected('sheet_restore_unsafe','Only the exact own base/sheet/flat/cut-list roots may be selected.')
            # Absorbed nodes are exclusively ours. No delete-children flag.
            if self._extension(model).DeleteSelection2(2) is not True:
                raise rejected('sheet_restore_unsafe','Native deletion of the selected owned bundle failed.')
            if not self.rebuild_dimension_document(model):raise rejected('sheet_restore_unsafe','Scoped rebuild failed.')
        if self.bodies(model,'all') or self.part_creation_controls(model)!=receipt.controls:
            raise rejected('sheet_restore_unsafe','Empty body scope or original controls were not restored.')
        remaining=self.features(model)
        if any(any(self.identity(feature)==token for token in tokens) for feature in remaining):
            raise rejected('sheet_restore_unsafe','An owned feature remained after scoped deletion.')
        factory=binding.wrap(model.FeatureManager,self._module.IFeatureManager)
        if factory.GetSheetMetalFolder() is not None or factory.GetFlatPatternFolder() is not None:
            raise rejected('sheet_restore_unsafe','Owned sheet/flat folders did not disappear; restoration is unconfirmed.')
        receipt.restored=True
