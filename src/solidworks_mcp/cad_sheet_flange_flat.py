"""Explicit existing U-sheet graph and state; never a creation/deletion receipt."""

from dataclasses import dataclass
from types import SimpleNamespace

from . import binding
from .documents import rejected
from .cad_sheet_flat import NativeSheetStateTarget
from .cad_sheet_profile import NativeSheetMember
from .cad_sheet_edge_flange import _same_identities


@dataclass
class NativeFlangeFlatTarget(NativeSheetStateTarget):
    flange:object=None


class CadSheetFlangeFlatMixin:
    def _u_flat_canonical(self,model,view):
        """Resolve alternate views; census/ID/name alone never binds a member."""
        if view is None:raise rejected('sheet_u_member_reference','A complete native feature view is required.')
        pid=self.persistent_id(model,view)
        if not pid:raise rejected('sheet_u_member_reference','A native feature reference is required.')
        raw,status=self._extension(model).GetObjectByPersistReference3(self._persistent_variant(pid))
        feature=binding.wrap(raw,self._module.IFeature)
        permitted=2 if self.feature_summary(view)['suppressed'] else 0
        if (type(status) is not int or status!=permitted or feature is None
                or not self._sheet_flange_feature_view_matches(model,view,feature)):
            raise rejected('sheet_u_member_reference','The full native feature view must bind its canonical persistent member.')
        return feature

    def sheet_flange_flat_target(self,model,base,flange,retained=None):
        bodies=self.bodies(model,'all')
        if (len(bodies)!=1 or type(bodies[0].GetType()) is not int or bodies[0].GetType()!=0 or bodies[0].IsSheetMetal() is not True
                or base.GetTypeName2()!='SMBaseFlange' or flange.GetTypeName2()!='EdgeFlange'):
            raise rejected('sheet_u_target_unsupported','One exact native sheet base, flange and current solid body are required.')
        body=bodies[0];pid=self.persistent_id(model,body)
        if not pid or self.identity(self.resolve_persistent_id(model,pid,'body'))!=self.identity(body):
            raise rejected('sheet_u_body_reference','The exact current sheet body must round-trip.')
        if retained is None:
            config=binding.wrap(model.GetActiveConfiguration(),self._module.IConfiguration)
            target=NativeFlangeFlatTarget(self.identity(model),self.identity(config),base,pid,flange=flange)
        else:
            target=retained
            if (self.identity(base)!=self.identity(target.base) or self.identity(flange)!=self.identity(target.flange)
                    or not self.same_persistent_id(model,pid,target.body_pid)
                    or self.identity(self.resolve_persistent_id(model,target.body_pid,'body'))!=self.identity(body)):
                raise rejected('sheet_u_target_changed','The explicit base, flange or body was replaced.')
        self._sheet_state_target_current(model,target)
        def one(items,kind):
            found=[f for f in items if f.GetTypeName2()==kind]
            if len(found)!=1:raise rejected('sheet_u_membership','Exactly one '+kind+' member is required.')
            return found[0]
        body_views=[binding.wrap(raw,self._module.IFeature) for raw in body.GetFeatures() or ()]
        current_base=self._u_flat_canonical(model,one(body_views,'SMBaseFlange'))
        current_flange=self._u_flat_canonical(model,one(body_views,'EdgeFlange'))
        if self.identity(current_base)!=self.identity(base) or self.identity(current_flange)!=self.identity(flange):
            raise rejected('sheet_u_membership','Both explicit features must bind this exact current body.')
        sheet=self._u_flat_canonical(model,one(body_views,'SheetMetal'))
        flat=self._u_flat_canonical(model,one(body_views,'FlatPattern'))
        derived=[];folders={};factory=binding.wrap(model.FeatureManager,self._module.IFeatureManager)
        for getter,interface,count,membership,expected,kind,role in (
                ('GetSheetMetalFolder','ISheetMetalFolder','GetSheetMetalCount','GetSheetMetals',sheet,'TemplateSheetMetal','sheet_folder'),
                ('GetFlatPatternFolder','IFlatPatternFolder','GetFlatPatternCount','GetFlatPatterns',flat,'TemplateFlatPattern','flat_folder')):
            folder=binding.wrap(getattr(factory,getter)(),getattr(self._module,interface))
            if folder is None:raise rejected('sheet_u_folder_missing','Both singleton native sheet folders are required.')
            total=getattr(folder,count)();items=[binding.wrap(raw,self._module.IFeature) for raw in getattr(folder,membership)() or ()]
            feature=self._u_flat_canonical(model,binding.wrap(folder.GetFeature(),self._module.IFeature))
            if (type(total) is not int or total!=1 or len(items)!=1 or feature.GetTypeName2()!=kind
                    or not self._sheet_flange_feature_view_matches(model,items[0],expected)):
                raise rejected('sheet_u_folder_membership','Both singleton folders must bind the exact retained body features.')
            folders[role]=feature;derived.append((role,feature,None))
        flattened=not self.feature_summary(flat)['suppressed']
        expected=[base,sheet,flat,flange]+([folders['flat_folder']] if flattened else [])
        actual=self._sheet_flange_coalesce_features(model,body_views,expected,target)
        if not _same_identities([self.identity(f) for f in actual],[self.identity(f) for f in expected]):
            raise rejected('sheet_u_body_membership','The complete native body feature membership must match this U graph.')
        base_children=self._sheet_absorbed(base);flange_children=self._sheet_absorbed(flange)
        if len(base_children)!=2 or len(flange_children)!=2:
            raise rejected('sheet_u_absorption','The base and flange each require exactly their own profile and bend.')
        sketch=one(base_children,'ProfileFeature');bend=one(base_children,'SketchBend')
        flange_sketch=one(flange_children,'ProfileFeature');flange_bend=one(flange_children,'OneBend')
        direct=self._sheet_absorbed(flat);profiles=[f for f in direct if f.GetTypeName2()=='ProfileFeature']
        if len(direct)!=4 or len(profiles)!=2:
            raise rejected('sheet_u_absorption','The original complete four-node flat absorption is required.')
        profiles.sort(key=lambda f:int(f.GetID()));ui=one(direct,'UiBend');fold_folder=one(direct,'FoldUpDownSketchFolder')
        features=self.features(model)
        extra_ui=[f for f in features if f.GetTypeName2()=='UiBend' and not self._sheet_flange_feature_view_matches(model,f,ui)]
        if len(extra_ui)!=1:raise rejected('sheet_u_flat_bend','Exactly one additional native derived UiBend is required.')
        extra=self._u_flat_canonical(model,extra_ui[0])
        owner=binding.wrap(extra.GetOwnerFeature(),self._module.IFeature)
        parents=[binding.wrap(raw,self._module.IFeature) for raw in extra.GetParents() or ()]
        if (not self._sheet_flange_feature_view_matches(model,owner,flat) or len(parents)!=1
                or not self._sheet_flange_feature_view_matches(model,parents[0],flange_bend) or extra.GetChildren()):
            raise rejected('sheet_u_flat_bend','The extra leaf flat bend requires the exact flange bend parent and flat owner.')
        cuts=[]
        for feature in features:
            if feature.GetTypeName2()!='CutListFolder':continue
            folder=binding.wrap(feature.GetSpecificFeature2(),self._module.IBodyFolder)
            members=[] if folder is None else [binding.wrap(raw,self._module.IBody2) for raw in folder.GetBodies() or ()]
            if len(members)==1 and self.identity(members[0])==self.identity(body):cuts.append(feature)
        if len(cuts)!=1:raise rejected('sheet_u_cut_list','One exact cut list must contain this sole current body.')
        derived.extend([('base',base,None),('sketch',sketch,base),('sheet',sheet,None),('flat',flat,None),('bend',bend,base),
            ('flat_sketch_1',profiles[0],flat),('flat_sketch_2',profiles[1],flat),('ui_bend',ui,flat),
            ('fold_sketch_folder',fold_folder,flat),('cut_list',cuts[0],None),('flange',flange,None),
            ('flange_sketch',flange_sketch,flange),('flange_bend',flange_bend,flange),('flange_flat_bend',extra,flat)])
        tokens=[self.identity(f) for _,f,_ in derived]
        if not _same_identities(tokens,tokens):raise rejected('sheet_u_member_collision','Every U-sheet member must be distinct.')
        if not target.members:
            for role,feature,owner in derived:
                strategy='owned_absorption_v1' if role=='fold_sketch_folder' else 'owned_persistent_feature_v1'
                reference=b'' if role=='fold_sketch_folder' else self.persistent_id(model,feature)
                target.members.append(NativeSheetMember(role,feature,self.identity(feature),reference,strategy,owner))
        if len(target.members)!=16 or {m.role for m in target.members}!={role for role,_,_ in derived}:
            raise rejected('sheet_u_member_changed','The complete retained U graph must remain unchanged.')
        for member in target.members:
            feature=next(f for role,f,_ in derived if role==member.role)
            if not self._sheet_flange_feature_view_matches(model,feature,member.feature):
                raise rejected('sheet_u_member_changed','A native U member changed.')
            self._sheet_member_reference(model,member)
        self._sheet_state_target_current(model,target)
        return target,body

    def sheet_flange_flat_seed(self,model,target):
        """Parameter/profile seed only; it never authorizes a state change."""
        target,_=self.sheet_flange_flat_target(model,target.base,target.flange,target)
        sketch=next(m.feature for m in target.members if m.role=='sketch')
        original,_=self.sketch_snapshot(model,sketch)
        plane_pid=bytes.fromhex(original['reference_plane']['pid_hex'])
        plane=self.resolve_persistent_id(model,plane_pid,'feature')
        return dict(sketch=original,plane_pid_hex=plane_pid.hex(),plane_transform=list(self.reference_plane_transform(plane)),
            source_parameters=self._sheet_flange_source_parameters(model,target),
            flange_parameters=self.sheet_flange_parameters(target.flange),
            names={m.role:str(m.feature.Name) for m in target.members})

    def sheet_flange_flat_evidence(self,model,target,definition,frame):
        target,body=self.sheet_flange_flat_target(model,target.base,target.flange,target)
        get=lambda role:next(m.feature for m in target.members if m.role==role)
        original,original_members=self.sketch_snapshot(model,get('sketch'))
        own=get('flange_sketch');native=binding.wrap(own.GetSpecificFeature2(),self._module.ISketch)
        dimensions=self.dimensions(model,[own])
        if len(dimensions)!=1:raise rejected('sheet_u_profile_driver','Exactly one own profile driver is required.')
        driver=self.dimension_object(dimensions[0])
        # This read-only descriptor is not a creation receipt or deletion authority.
        descriptor=SimpleNamespace(source_target=target,sketch=own,sketch_identity=self.identity(own),
            sketch_pid=self.persistent_id(model,own),native_sketch=native,driver=driver,driver_identity=self.identity(driver),
            flange=target.flange,edge_pid=b'')
        profile,profile_members=self.sheet_flange_sketch_snapshot(model,descriptor,definition,frame,'after_factory')
        fixed=self._sheet_flat_fixed_face_read(model,get('flat'),body)
        source=self._sheet_flange_source_parameters(model,target);mass=self.rectangle_body_measurements(model)
        from .sketches import persistent_sketch_members
        members=tuple(('original:'+key,value) for key,value in persistent_sketch_members(original_members))+profile_members
        evidence=dict(base_native_id=int(target.base.GetID()),sketch_native_id=int(get('sketch').GetID()),sketch=original,
            members=[dict(role=m.role,pid_hex=m.persistent_id.hex(),reference_strategy=m.reference_strategy,**self.feature_summary(m.feature)) for m in target.members],
            body_pid_hex=target.body_pid.hex(),body_name=str(body.Name),base_parameters=source['base'],sheet_parameters=source['sheet'],
            parameter_options=source['options'],flange_parameters=self.sheet_flange_parameters(target.flange),flange_profile=profile,
            fixed_face=fixed['face'],options=fixed['options'],controls=self.part_creation_controls(model),
            flattened=not self.feature_summary(get('flat'))['suppressed'],volume_mm3=mass['volume_mm3'],area_mm2=mass['surface_area_mm2'])
        self.sheet_flange_flat_target(model,target.base,target.flange,target)
        return evidence,members

    def sheet_change_flange_flat_state(self,model,target,flattened):
        if type(flattened) is not bool:raise rejected('invalid_sheet_flat_state','An explicit boolean is required.')
        target,_=self.sheet_flange_flat_target(model,target.base,target.flange,target)
        flat=next(m.feature for m in target.members if m.role=='flat')
        if (not self.feature_summary(flat)['suppressed'])==flattened:return False
        if flat.SetSuppression2(1 if flattened else 0,1,None) is not True:
            raise rejected('sheet_u_state_native_failed','The exact native flat-state setter did not confirm success.')
        if model.ForceRebuild3(False) is not True:raise rejected('sheet_u_state_rebuild_failed','The U-sheet rebuild was not confirmed.')
        return True

    def sheet_preserve_flange_flat_names(self,model,target,body_name,cut_list_name):
        target,body=self.sheet_flange_flat_target(model,target.base,target.flange,target)
        cut=next(m.feature for m in target.members if m.role=='cut_list')
        if str(body.Name)!=body_name:body.Name=body_name
        if str(cut.Name)!=cut_list_name:cut.Name=cut_list_name
        if str(body.Name)!=body_name or str(cut.Name)!=cut_list_name:
            raise rejected('sheet_u_state_name_failed','The exact original body and cut-list names were not preserved.')
