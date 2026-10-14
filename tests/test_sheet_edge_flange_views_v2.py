"""Alternate native views require PID roundtrips and complete ownership proof."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_sheet_edge_flange import CadSheetEdgeFlangeMixin
from solidworks_mcp.jobs import ExecutionFailure


@pytest.fixture
def views(monkeypatch):
    from solidworks_mcp import binding
    monkeypatch.setattr(binding,'wrap',lambda value,interface:value)
    a=CadSheetEdgeFlangeMixin();a._module=NS(IFeature=object);a.identity=id
    a.same_persistent_id=lambda model,left,right:left==right
    a._persistent_variant=lambda value:value
    def feature(native_id,kind='FlatPattern',suppressed=True,owner=None):
        summary=dict(native_id=native_id,name=kind,feature_type=kind,suppressed=suppressed,
            owner_native_id=owner.GetID() if owner else None,error_code=0,is_warning=False)
        return NS(GetID=lambda:native_id,GetOwnerFeature=lambda:owner,summary=summary,pid=str(native_id).encode())
    old=feature(48);view=feature(48)
    resolved={b'48':(old,2)}
    a.feature_summary=lambda f:deepcopy(f.summary)
    a.persistent_id=lambda model,f:f.pid
    a._extension=lambda model:NS(GetObjectByPersistReference3=lambda pid:resolved[pid])
    target=NS(members=[]);a._sheet_state_target_current=lambda model,target:None
    return a,object(),old,view,resolved,target,feature


def test_suppressed_equivalent_view_binds_retained_canonical_entity(views):
    a,model,old,view,_,target,_=views
    assert a.identity(old)!=a.identity(view)
    assert a._sheet_flange_coalesce_features(model,[view],[old],target)==[old]


@pytest.fixture
def fixed_body(views):
    a,model,flat,view,resolved,target,feature=views
    base=feature(49,'SMBaseFlange',False);sheet=feature(37,'SheetMetal',False);flange=feature(67,'EdgeFlange',False)
    member=NS(role='flat',feature=flat)
    target.members=[NS(role='base',feature=base),NS(role='sheet',feature=sheet),member];target.body_pid=b'body'
    current=[base,sheet,view,flange];body=NS(GetFeatures=lambda:current)
    a.resolve_persistent_id=lambda m,p,k:body
    events=[]
    def read(m,f,b):
        assert m is model and f is flat and b is body
        events.append('read');return dict(face={'complete':'native fixed face'},options={})
    a._sheet_flat_fixed_face_read=read
    a._sheet_member_reference=lambda m,ref:events.append('member')
    return a,model,NS(source_target=target,flange=flange),body,current,events,resolved,feature


def test_expanded_fixed_face_binds_alias_and_closes_full_body_membership(fixed_body):
    a,model,receipt,body,_,events,_,_=fixed_body
    assert a._sheet_flange_fixed_face(model,receipt,body)['face']=={'complete':'native fixed face'}
    assert events==['member','read','member']


@pytest.mark.parametrize('fault',['missing_flat','duplicate_flat','extra_feature','replaced_body','pid_retarget','late_retarget','late_feature'])
def test_fixed_face_never_accepts_id_only_alias_or_late_foreign_membership(fixed_body,fault):
    a,model,receipt,body,current,events,resolved,feature=fixed_body
    if fault=='missing_flat':current.pop(2)
    elif fault=='duplicate_flat':current.append(current[2])
    elif fault=='extra_feature':current.append(feature(999,'Fillet',False))
    elif fault=='replaced_body':a.resolve_persistent_id=lambda *args:object()
    elif fault=='pid_retarget':resolved[b'48']=(feature(48),2)
    else:
        read=a._sheet_flat_fixed_face_read
        def changing(*args):
            value=read(*args)
            if fault=='late_retarget':resolved[b'48']=(feature(48),2)
            else:current.append(feature(999,'Fillet',False))
            return value
        a._sheet_flat_fixed_face_read=changing
    with pytest.raises(ExecutionFailure):a._sheet_flange_fixed_face(model,receipt,body)
    if not fault.startswith('late_'):assert 'read' not in events


@pytest.mark.parametrize('defect',['retarget','unsupported_status','bool_status','null',
    'different_pid','different_name','different_suppression','different_error','different_owner'])
def test_matching_id_or_descriptor_never_replaces_native_proof(views,defect):
    a,model,old,view,resolved,_,feature=views
    if defect=='retarget':resolved[b'48']=(feature(48),2)
    elif defect=='unsupported_status':resolved[b'48']=(old,1)
    elif defect=='bool_status':resolved[b'48']=(old,True)
    elif defect=='null':resolved[b'48']=(None,2)
    elif defect=='different_pid':view.pid=b'foreign'
    elif defect=='different_name':view.summary['name']='Другое'
    elif defect=='different_suppression':view.summary['suppressed']=False
    elif defect=='different_error':view.summary['error_code']=1
    else:
        owner=feature(33);view.GetOwnerFeature=lambda:owner
    assert not a._sheet_flange_feature_view_matches(model,view,old)


def test_recursive_owner_alias_is_proved_and_pid_retarget_during_read_is_rejected(views):
    a,model,old,view,resolved,_,feature=views
    owner=feature(33,suppressed=False);owner_view=feature(33,suppressed=False)
    for f in (old,view):f.summary['owner_native_id']=33
    old.GetOwnerFeature=lambda:owner;view.GetOwnerFeature=lambda:owner_view
    resolved[b'33']=(owner,0)
    assert a._sheet_flange_feature_view_matches(model,view,old)
    def retarget():
        resolved[b'48']=(feature(48),2)
        return owner_view
    view.GetOwnerFeature=retarget
    assert not a._sheet_flange_feature_view_matches(model,view,old)


def test_complete_view_rejects_duplicate_canonical_aliases(views):
    a,model,old,view,_,target,_=views
    with pytest.raises(ExecutionFailure,match='Duplicate canonical'):
        a._sheet_flange_coalesce_features(model,[view,old],[old],target)


def test_closing_context_cannot_retarget_a_previously_matching_alias(views):
    a,model,old,view,resolved,target,feature=views
    a._sheet_state_target_current=lambda *args:resolved.update({b'48':(feature(48),2)})
    with pytest.raises(ExecutionFailure,match='binding changed'):
        a._sheet_flange_coalesce_features(model,[view],[old],target)


@pytest.mark.parametrize('change',['descriptor','reference'])
def test_closing_getters_reject_changes_without_a_native_event(views,change):
    a,model,old,view,_,_,_=views
    def mutate():
        if change=='descriptor':view.summary['name']='Заменённая развёртка'
        else:view.pid=b'other'
        return None
    view.GetOwnerFeature=mutate
    assert not a._sheet_flange_feature_view_matches(model,view,old)


def test_equal_native_id_with_multiple_proved_retained_candidates_is_rejected(views):
    a,model,old,view,_,target,feature=views
    duplicate=feature(48)
    # Deliberate injected native resolver ambiguity, not a valid CAD state.
    a._sheet_flange_feature_view_matches=lambda *args:True
    with pytest.raises(ExecutionFailure,match='multiple retained'):
        a._sheet_flange_coalesce_features(model,[view],[old,duplicate],target)


@pytest.mark.parametrize('defect',[None,'missing_absorption','duplicate_absorption','wrong_owner','descriptor'])
def test_folder_misleading_pid_only_uses_exact_owned_absorption(views,defect):
    a,model,owner,owner_view,resolved,target,feature=views
    folder=feature(56,'FoldUpDownSketchFolder',False,owner)
    folder_view=feature(56,'FoldUpDownSketchFolder',False,owner_view)
    # Native API can claim equal PIDs while resolving a different feature.
    resolved[b'56']=(feature(56),0)
    assert not a._sheet_flange_feature_view_matches(model,folder_view,folder)
    member=NS(role='fold_sketch_folder',feature=folder,identity=id(folder),owner=owner)
    target.members=[member];checks=[]
    a._sheet_member_reference=lambda model,m:checks.append(m)
    a._sheet_absorbed=lambda f:[folder]
    if defect=='missing_absorption':a._sheet_absorbed=lambda f:[]
    elif defect=='duplicate_absorption':a._sheet_absorbed=lambda f:[folder,folder]
    elif defect=='wrong_owner':folder_view.GetOwnerFeature=lambda:feature(57)
    elif defect=='descriptor':folder_view.summary['name']='Чужая папка'
    result=a._sheet_flange_coalesce_features(model,[folder_view],[folder],target)
    assert result==[folder if defect is None else folder_view]
    assert checks
