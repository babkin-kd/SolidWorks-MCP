"""Read-only exact FlatPattern fixed face for the working sheet-state domain."""

from dataclasses import dataclass,field
import math

from . import binding
from .documents import rejected
from .cad_sheet_profile import NativeSheetMember


@dataclass
class NativeSheetStateTarget:
    model_identity:object
    configuration_identity:object
    base:object
    body_pid:bytes
    members:list=field(default_factory=list)


class CadSheetFlatMixin:
    """Exact existing-sheet state bridge; no deletion or generic Undo."""
    def _sheet_state_target_current(self,model,target):
        active=binding.wrap(self._sw.ActiveDoc,self._module.IModelDoc2)
        config=binding.wrap(model.GetActiveConfiguration(),self._module.IConfiguration)
        if (self.identity(model)!=target.model_identity or active is None or self.identity(active)!=target.model_identity
                or self.identity(config)!=target.configuration_identity):
            raise rejected('sheet_state_target_changed','The explicit active document/configuration changed.')

    def sheet_state_target(self,model,base,retained=None):
        bodies=self.bodies(model,'all')
        if len(bodies)!=1:raise rejected('sheet_state_body_unsupported','Exactly one native L-sheet body is required.')
        body=bodies[0];body_type=body.GetType()
        if type(body_type) is not int or body_type!=0 or body.IsSheetMetal() is not True or base.GetTypeName2()!='SMBaseFlange':
            raise rejected('sheet_state_body_unsupported','One exact sheet-metal base and current solid body are required.')
        pid=self.persistent_id(model,body)
        if not pid or self.identity(self.resolve_persistent_id(model,pid,'body'))!=self.identity(body):
            raise rejected('sheet_state_body_reference','The current body reference must round-trip canonically.')
        if retained is None:
            config=binding.wrap(model.GetActiveConfiguration(),self._module.IConfiguration)
            target=NativeSheetStateTarget(self.identity(model),self.identity(config),base,pid)
        else:
            target=retained
            if (self.identity(base)!=self.identity(target.base) or not self.same_persistent_id(model,target.body_pid,pid)
                    or self.identity(self.resolve_persistent_id(model,target.body_pid,'body'))!=self.identity(body)):
                raise rejected('sheet_state_body_reference','The target body was replaced outside the persistent sheet-state scope.')
        self._sheet_state_target_current(model,target)
        cls=self._module.IFeature;factory=binding.wrap(model.FeatureManager,self._module.IFeatureManager)
        body_features=[binding.wrap(raw,cls) for raw in body.GetFeatures() or ()]
        def one(items,kind):
            found=[f for f in items if f.GetTypeName2()==kind]
            if len(found)!=1:raise rejected('sheet_state_membership','Expected one exact native '+kind+' member.')
            return found[0]
        current_base=one(body_features,'SMBaseFlange');sheet=one(body_features,'SheetMetal');flat=one(body_features,'FlatPattern')
        if self.identity(current_base)!=self.identity(base):raise rejected('sheet_state_membership','The explicit base does not bind the exact current sheet body.')
        derived=[];folders={}
        for getter,interface,count,membership,expected,kind,role in (
                ('GetSheetMetalFolder','ISheetMetalFolder','GetSheetMetalCount','GetSheetMetals',sheet,'TemplateSheetMetal','sheet_folder'),
                ('GetFlatPatternFolder','IFlatPatternFolder','GetFlatPatternCount','GetFlatPatterns',flat,'TemplateFlatPattern','flat_folder')):
            folder=binding.wrap(getattr(factory,getter)(),getattr(self._module,interface))
            if folder is None:raise rejected('sheet_state_folder_missing','The documented singleton sheet/flat folder is required.')
            total=getattr(folder,count)();items=[binding.wrap(raw,cls) for raw in getattr(folder,membership)() or ()]
            feature=binding.wrap(folder.GetFeature(),cls)
            if (type(total) is not int or total!=1 or len(items)!=1 or self.identity(items[0])!=self.identity(expected)
                    or feature is None or feature.GetTypeName2()!=kind):
                raise rejected('sheet_state_folder_membership','The exact native singleton folder must bind this sheet body feature.')
            folders[role]=feature;derived.append((role,feature,None))
        flattened=not self.feature_summary(flat)['suppressed']
        expected_body_members=[base,sheet,flat]+([folders['flat_folder']] if flattened else [])
        if (len(body_features)!=len(expected_body_members) or any(sum(self.identity(f)==self.identity(v) for f in body_features)!=1 for v in expected_body_members)):
            raise rejected('sheet_state_membership','Unconfirmed additional body features are outside the native L-sheet state scope.')
        absorbed=self._sheet_absorbed(base)
        if len(absorbed)!=2:raise rejected('sheet_state_absorption','The base requires exactly one original profile and one sketch bend.')
        sketch=one(absorbed,'ProfileFeature');bend=one(absorbed,'SketchBend')
        children=self._sheet_absorbed(flat);profiles=[f for f in children if f.GetTypeName2()=='ProfileFeature']
        if len(children)!=4 or len(profiles)!=2:raise rejected('sheet_state_absorption','The exact four-node flat absorption is required.')
        profiles.sort(key=lambda f:int(f.GetID()))
        ui=one(children,'UiBend');fold_folder=one(children,'FoldUpDownSketchFolder')
        cut_lists=[]
        for feature in self.features(model):
            if feature.GetTypeName2()!='CutListFolder':continue
            folder=binding.wrap(feature.GetSpecificFeature2(),self._module.IBodyFolder)
            members=[] if folder is None else [binding.wrap(raw,self._module.IBody2) for raw in folder.GetBodies() or ()]
            if len(members)==1 and self.identity(members[0])==self.identity(body):cut_lists.append(feature)
        if len(cut_lists)!=1:raise rejected('sheet_state_cut_list','One exact cut-list folder must uniquely contain this current body.')
        derived+=[('base',base,None),('sketch',sketch,base),('sheet',sheet,None),('flat',flat,None),('bend',bend,base),
            ('flat_sketch_1',profiles[0],flat),('flat_sketch_2',profiles[1],flat),('ui_bend',ui,flat),
            ('fold_sketch_folder',fold_folder,flat),('cut_list',cut_lists[0],None)]
        tokens=[self.identity(f) for _,f,_ in derived]
        if any(token==old for i,token in enumerate(tokens) for old in tokens[:i]):raise rejected('sheet_state_member_collision','All sheet-state members must be distinct exact native features.')
        if not target.members:
            for role,feature,owner in derived:
                strategy='owned_absorption_v1' if role=='fold_sketch_folder' else 'owned_persistent_feature_v1'
                reference=b'' if strategy=='owned_absorption_v1' else self.persistent_id(model,feature)
                if strategy!='owned_absorption_v1' and not reference:raise rejected('sheet_state_member_reference','Every target member requires a strong native reference.')
                target.members.append(NativeSheetMember(role,feature,self.identity(feature),reference,strategy,owner))
        if {m.role for m in target.members}!={role for role,_,_ in derived}:raise rejected('sheet_state_member_changed','Retained sheet-state membership changed.')
        for member in target.members:
            feature=next(f for role,f,_ in derived if role==member.role)
            if self.identity(feature)!=member.identity:raise rejected('sheet_state_member_changed','An exact retained sheet-state feature changed.')
            self._sheet_member_reference(model,member)
        return target,body

    def sheet_state_evidence(self,model,target):
        target,body=self.sheet_state_target(model,target.base,target)
        get=lambda role:next(m.feature for m in target.members if m.role==role)
        # Reuse the independently read native definitions, not a creation receipt
        # or any creation/deletion authority.
        from types import SimpleNamespace
        parameters=self.sheet_profile_parameters(SimpleNamespace(extrusion=target.base,auxiliary=target.members))
        sketch,members=self.sketch_snapshot(model,get('sketch'))
        face=self.sheet_flat_fixed_face(model,get('flat'),body);mass=body.GetMassProperties(1.)
        return dict(base_native_id=int(target.base.GetID()),sketch_native_id=int(get('sketch').GetID()),sketch=sketch,
            members=[dict(role=m.role,pid_hex=m.persistent_id.hex(),reference_strategy=m.reference_strategy,**self.feature_summary(m.feature)) for m in target.members],
            body_pid_hex=target.body_pid.hex(),body_name=str(body.Name),base_parameters=parameters[0],sheet_parameters=parameters[1],
            fixed_face=face['face'],options=face['options'],controls=self.part_creation_controls(model),
            flattened=not self.feature_summary(get('flat'))['suppressed'],volume_mm3=float(mass[3])*1e9,area_mm2=float(mass[4])*1e6),members

    def sheet_change_flat_state(self,model,target,flattened):
        target,_=self.sheet_state_target(model,target.base,target)
        flat=next(m.feature for m in target.members if m.role=='flat')
        if (not self.feature_summary(flat)['suppressed'])==flattened:return False
        if flat.SetSuppression2(1 if flattened else 0,1,None) is not True:
            raise rejected('sheet_state_native_failed','The exact native flat-state setter did not confirm success.')
        if model.ForceRebuild3(False) is not True:
            raise rejected('sheet_state_rebuild_failed','Native sheet-state rebuilding was not confirmed.')
        return True

    def sheet_preserve_flat_names(self,model,target,body_name,cut_list_name):
        # Domain must prove the entire intended transition before this callback.
        target,body=self.sheet_state_target(model,target.base,target)
        cut_list=next(m.feature for m in target.members if m.role=='cut_list')
        if str(body.Name)!=body_name:body.Name=body_name
        if str(cut_list.Name)!=cut_list_name:cut_list.Name=cut_list_name
        if str(body.Name)!=body_name or str(cut_list.Name)!=cut_list_name:
            raise rejected('sheet_state_name_failed','Exact original body/cut-list names were not retained.')


class CadSheetFlatReadMixin:
    def sheet_flat_fixed_face(self,model,flat,body):
        """No AccessSelections/rollback, suppression, rebuild or UI setters.

        Called within the domain's full paired capture. A name or a normal alone
        never establishes the target: body membership, current topology and the
        native face persistent-reference round trip are all required.
        """
        body_type=body.GetType()
        if (flat.GetTypeName2()!='FlatPattern' or type(body_type) is not int or body_type!=0 or body.IsSheetMetal() is not True
                or not self.body_is_current(model,body)):
            raise rejected('sheet_flat_target_unsupported','One current native sheet-metal body and exact FlatPattern are required.')
        members=[binding.wrap(raw,self._module.IFeature) for raw in body.GetFeatures() or ()]
        if sum(self.identity(item)==self.identity(flat) for item in members)!=1:
            raise rejected('sheet_flat_membership_changed','The explicit flat feature must belong uniquely to the current sheet body.')
        data=binding.wrap(flat.GetDefinition(),self._module.IFlatPatternFeatureData)
        if data is None:raise rejected('sheet_flat_definition_unavailable','The native flat definition is required.')
        face=binding.wrap(data.FixedFace2,self._module.IFace2)
        if face is None:raise rejected('sheet_fixed_face_unavailable','The native fixed face cannot be inferred from a body box.')
        pid=self.persistent_id(model,face)
        if not pid:raise rejected('sheet_fixed_face_unavailable','The native fixed face requires a strong persistent reference.')
        resolved=self.resolve_persistent_id(model,pid,'face')
        owner=binding.wrap(face.GetBody(),self._module.IBody2)
        if (self.identity(resolved)!=self.identity(face) or self.identity(owner)!=self.identity(body)
                or not self.topology_is_current(body,face,'face')
                or not self.same_persistent_id(model,pid,self.persistent_id(model,resolved))):
            raise rejected('sheet_fixed_face_changed','The exact current fixed face and persistent reference disagree.')
        surface=binding.wrap(face.GetSurface(),self._module.ISurface)
        if surface is None or surface.IsPlane() is not True:
            raise rejected('sheet_fixed_face_unsupported','The initial L-profile scope requires one complete native planar fixed face.')
        edges=[binding.wrap(raw,self._module.IEdge) for raw in face.GetEdges() or ()]
        if len(edges)!=4 or any(self.identity(edge)==self.identity(old) for i,edge in enumerate(edges) for old in edges[:i]):
            raise rejected('sheet_fixed_face_unsupported','Exactly four distinct fixed-face boundary edges are required.')
        vertices=[]
        for edge in edges:
            for raw in (edge.GetStartVertex(),edge.GetEndVertex()):
                vertex=binding.wrap(raw,self._module.IVertex)
                if vertex is None:raise rejected('sheet_fixed_face_unsupported','The fixed face must have finite straight boundary endpoints.')
                point=tuple(vertex.GetPoint())
                if len(point)!=3 or any(type(v) not in (float,int) or not math.isfinite(v) for v in point):
                    raise rejected('sheet_fixed_face_unsupported','Every exact fixed-face corner must be finite.')
                token=self.identity(vertex);prior=[p for identity,p in vertices if token==identity]
                if prior:
                    if prior!=[point]:raise rejected('sheet_fixed_face_changed','A retained fixed-face corner changed during collection.')
                else:
                    if any(point==p for _,p in vertices):raise rejected('sheet_fixed_face_unsupported','Distinct native corners cannot collapse.')
                    vertices.append((token,point))
        if len(vertices)!=4:raise rejected('sheet_fixed_face_unsupported','Four exact fixed-face corners are required.')
        parameters=surface.PlaneParams;parameters=parameters() if callable(parameters) else parameters
        parameters=list(parameters);sense=face.FaceInSurfaceSense()
        options={name:getattr(data,name) for name in ('MergeFace','SimplifyBends','ShowSlitInCornerRelief')}
        if (len(parameters)!=6 or any(type(v) not in (float,int) or not math.isfinite(v) for v in parameters)
                or type(sense) is not bool or any(type(v) is not bool for v in options.values())):
            raise rejected('sheet_flat_definition_unsupported','Complete finite native plane and unambiguous flat options are required.')
        return dict(face=dict(pid_hex=pid.hex(),vertices=[list(p) for p in sorted(p for _,p in vertices)],
            is_plane=True,plane_parameters=parameters,normal_opposes_surface=sense,owner_body_is_current=True),options=options)
