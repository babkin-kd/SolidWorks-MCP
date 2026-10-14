"""Native-shaped sheet ownership proofs; no SolidWorks invocation."""

from types import SimpleNamespace

import pytest

from solidworks_mcp.cad_sheet_profile import CadSheetProfileMixin,NativeSheetReceipt
from solidworks_mcp.jobs import ExecutionFailure


class Feature:
    def __init__(self,native_id,kind,suppressed=False):
        self.native_id,self.kind,self.suppressed=native_id,kind,suppressed
        self.Name='Native node '+str(native_id)
        self.owner=None;self.subfeatures=[];self.parents=[];self.children=[];self.specific=None
    def GetID(self):return self.native_id
    def GetTypeName2(self):return self.kind
    def GetOwnerFeature(self):return self.owner
    def GetFirstSubFeature(self):return self.subfeatures[0] if self.subfeatures else None
    def GetNextSubFeature(self):
        siblings=self.owner.subfeatures;index=siblings.index(self)+1
        return siblings[index] if index<len(siblings) else None
    def GetParents(self):return self.parents
    def GetChildren(self):return self.children
    def GetSpecificFeature2(self):return self.specific


class Body:
    def __init__(self,features):self.features=features
    def GetType(self):return 0
    def IsSheetMetal(self):return True
    def GetFeatures(self):return self.features


class Folder:
    def __init__(self,feature,members):self.feature,self.members=feature,members
    def GetFeature(self):return self.feature
    def GetSheetMetalCount(self):return len(self.members)
    def GetSheetMetals(self):return self.members
    def GetFlatPatternCount(self):return len(self.members)
    def GetFlatPatterns(self):return self.members


class Adapter(CadSheetProfileMixin):
    def _base_target(self,model,receipt):pass
    def identity(self,obj):return obj
    def features(self,model):return self.tree
    def bodies(self,model,kind):return self.body_members
    def resolve_persistent_id(self,model,pid,kind):return self.references[pid]
    def persistent_id(self,model,obj):return next((pid for pid,current in self.references.items() if current is obj),b'')
    def same_persistent_id(self,model,left,right):return self.references.get(left) is self.references.get(right)
    def feature_summary(self,feature):return dict(suppressed=feature.suppressed)
    def _extension(self,model):return self
    def _persistent_variant(self,pid):return pid
    def GetObjectByPersistReference3(self,pid):
        feature=self.references[pid]
        return feature,2 if feature.suppressed else 0


def setup(monkeypatch):
    monkeypatch.setattr('solidworks_mcp.cad_sheet_profile.binding.wrap',lambda raw,cls:raw)
    f={key:Feature(number,kind,suppressed) for key,number,kind,suppressed in (
        ('plane',2,'RefPlane',False),('origin',5,'OriginProfileFeature',False),('body_folder',9,'SolidBodyFolder',False),
        ('sketch',26,'ProfileFeature',False),('sheet',37,'SheetMetal',False),('base',49,'SMBaseFlange',False),
        ('flat',48,'FlatPattern',True),('bend',55,'SketchBend',False),('flat_sketch_1',46,'ProfileFeature',False),
        ('flat_sketch_2',47,'ProfileFeature',True),('ui_bend',57,'UiBend',False),('fold_sketch_folder',56,'FoldUpDownSketchFolder',True),
        ('cut_list',58,'CutListFolder',False),('sheet_folder',33,'TemplateSheetMetal',False),('flat_folder',44,'TemplateFlatPattern',True))}
    for parent,children in (('base',['sketch','bend']),('flat',['flat_sketch_1','flat_sketch_2','ui_bend','fold_sketch_folder'])):
        f[parent].subfeatures=[f[key] for key in children]
        for key in children:f[key].owner=f[parent]
    f['cut_list'].owner=f['body_folder']
    for key,parents,children in (
        ('sketch',['plane','origin'],['base']),('sheet',['sheet_folder'],['base','flat']),
        ('base',['sheet_folder','sheet','sketch','plane'],['flat']),('bend',['base'],[]),
        ('flat',['sheet_folder','sheet','base'],[]),('ui_bend',['bend'],[])):
        f[key].parents=[f[name] for name in parents];f[key].children=[f[name] for name in children]
    body=Body([f['sheet'],f['base'],f['flat']]);f['cut_list'].specific=SimpleNamespace(GetBodies=lambda:[body])
    sheet_folder=Folder(f['sheet_folder'],[f['sheet']]);flat_folder=Folder(f['flat_folder'],[f['flat']])
    model=SimpleNamespace(FeatureManager=SimpleNamespace(GetSheetMetalFolder=lambda:sheet_folder,GetFlatPatternFolder=lambda:flat_folder))
    adapter=Adapter();adapter._module=SimpleNamespace(**{name:object for name in
        ('IFeature','IFeatureManager','ISheetMetalFolder','IFlatPatternFolder','IBody2','IBodyFolder')})
    baseline=['plane','origin','body_folder']
    adapter.tree=[f[key] for key in baseline]+[feature for key,feature in f.items() if key not in baseline+['sheet_folder','flat_folder']]
    adapter.body_members=[body];adapter.references={key.encode():feature for key,feature in f.items()};adapter.references[b'body']=body
    receipt=NativeSheetReceipt(model,object(),tuple((f[key],{'name':f[key].Name}) for key in baseline),{},sketch=f['sketch'],sketch_identity=f['sketch'],
        extrusion=f['base'],extrusion_identity=f['base'],body=body,body_identity=body,body_pid=b'body')
    return adapter,model,receipt,f,sheet_folder,flat_folder


def test_body_membership_folders_and_absorption_close_ownership(monkeypatch):
    adapter,model,receipt,features,_,_=setup(monkeypatch)
    # The real folder has a misleading reference; the explicit absorption
    # strategy must avoid consulting that reference instead of accepting it.
    adapter.references[b'fold_sketch_folder']=features['flat']
    members=adapter._sheet_bundle(model,receipt)
    assert len(members)==10
    folder=next(member for member in members if member.role=='fold_sketch_folder')
    assert folder.reference_strategy=='owned_absorption_v1' and folder.persistent_id==b''
    assert folder.feature is features['fold_sketch_folder']
    assert adapter._sheet_bundle(model,receipt) is members
    assert all(member.reference_strategy=='owned_persistent_feature_v1' for member in members if member is not folder)


@pytest.mark.parametrize('fault',['foreign_body','extra_body','body_feature_missing','body_feature_duplicate','returned_base_replaced',
    'foreign_sheet_folder','extra_sheet_member','foreign_flat_folder','missing_base_profile','extra_base_absorption',
    'wrong_absorbed_owner','missing_flat_sketch','extra_flat_absorption','wrong_bend_type','missing_cut_list',
    'extra_cut_list','foreign_tree_node','foreign_dependency','existing_cut_list','wrong_persistent_reference'])
def test_no_name_or_tree_difference_can_authorize_an_unproved_bundle(monkeypatch,fault):
    a,model,receipt,f,sheet_folder,flat_folder=setup(monkeypatch)
    foreign=Feature(999,'ProfileFeature')
    if fault=='foreign_body':a.references[b'body']=Body([])
    elif fault=='extra_body':a.body_members.append(Body([]))
    elif fault=='body_feature_missing':receipt.body.features.pop()
    elif fault=='body_feature_duplicate':receipt.body.features[1]=f['sheet']
    elif fault=='returned_base_replaced':receipt.extrusion_identity=foreign
    elif fault=='foreign_sheet_folder':sheet_folder.feature=foreign
    elif fault=='extra_sheet_member':sheet_folder.members.append(foreign)
    elif fault=='foreign_flat_folder':flat_folder.members=[foreign]
    elif fault=='missing_base_profile':f['base'].subfeatures.remove(f['sketch'])
    elif fault=='extra_base_absorption':foreign.owner=f['base'];f['base'].subfeatures.append(foreign)
    elif fault=='wrong_absorbed_owner':f['bend'].owner=f['flat']
    elif fault=='missing_flat_sketch':f['flat'].subfeatures.remove(f['flat_sketch_2'])
    elif fault=='extra_flat_absorption':foreign.owner=f['flat'];f['flat'].subfeatures.append(foreign)
    elif fault=='wrong_bend_type':f['bend'].kind='Feature'
    elif fault=='missing_cut_list':f['cut_list'].specific=SimpleNamespace(GetBodies=lambda:[])
    elif fault=='extra_cut_list':foreign.kind='CutListFolder';foreign.specific=f['cut_list'].specific;a.tree.append(foreign)
    elif fault=='foreign_tree_node':a.tree.append(foreign)
    elif fault=='foreign_dependency':f['base'].children.append(foreign)
    elif fault=='existing_cut_list':receipt.baseline_features+=((f['cut_list'],{}),)
    else:a.references[b'sheet']=foreign
    with pytest.raises(ExecutionFailure):a._sheet_bundle(model,receipt)


def test_bound_absorbed_folder_replacement_and_new_dependant_are_rejected(monkeypatch):
    a,model,receipt,f,_,_=setup(monkeypatch);a._sheet_bundle(model,receipt)
    f['fold_sketch_folder'].owner=f['base']
    with pytest.raises(ExecutionFailure):a._sheet_bundle(model,receipt)


def test_only_proved_auxiliaries_are_given_russian_names(monkeypatch):
    a,model,receipt,f,_,_=setup(monkeypatch)
    a._sheet_bundle(model,receipt);a._name_sheet_bundle(model,receipt)
    assert f['cut_list'].Name=='Список вырезов' and f['sheet_folder'].Name=='Параметры листового металла'
    assert f['fold_sketch_folder'].Name=='Эскизы сгиба'
    assert f['plane'].Name=='Native node 2' and f['body_folder'].Name=='Native node 9'


def test_name_collision_is_rejected_before_any_auxiliary_write(monkeypatch):
    a,model,receipt,f,_,_=setup(monkeypatch);a._sheet_bundle(model,receipt)
    receipt.baseline_features=((f['plane'],{'name':'список вырезов'}),)
    before={key:feature.Name for key,feature in f.items()}
    with pytest.raises(ExecutionFailure,match='conflicts'):a._name_sheet_bundle(model,receipt)
    assert before=={key:feature.Name for key,feature in f.items()}


def test_unknown_creation_never_authorizes_bundle_deletion(monkeypatch):
    a,model,receipt,_,_,_=setup(monkeypatch);receipt.pending_creation=True
    with pytest.raises(ExecutionFailure,match='Unknown creation'):a.restore_sheet_profile(model,receipt)
