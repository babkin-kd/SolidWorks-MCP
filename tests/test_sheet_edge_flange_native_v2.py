"""Strict native bridge contract on artificial COM stand-ins; no CAD calls."""

from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_sheet_edge_flange import (CadSheetEdgeFlangeMixin,
    NativeEdgeFlangeReceipt,flange_options,native_flange_parameters_match)
from solidworks_mcp.cad_sheet_edge_flange import _same_identities,_flange_profile_corners
from solidworks_mcp.sheet_edge_flange_definition import EdgeFlangeOnL
from solidworks_mcp.jobs import ExecutionFailure
from test_sheet_profile_definition_v2 import definition
from test_part_creation_v2 import IDENTITY


@pytest.fixture
def flange():return EdgeFlangeOnL.validate(definition(),15.,2.5,.38)


def parameters(flange):return {**flange_options(flange),'allowance_type':2,'k_factor':.38,'edge_count':1}


def test_profile_height_is_from_inner_edge_while_native_length_is_outer_sharp(flange):
    assert flange.profile_height_mm==13. and flange_options(flange)['OffsetDistance']==.015
    changed=EdgeFlangeOnL.validate(definition(thickness_mm=2.5),17.,3.,.4)
    assert changed.profile_height_mm==14.5 and flange_options(changed)['OffsetDistance']==.017


def test_native_converted_line_endpoint_order_keeps_the_same_rectangle_and_offset():
    forward=_flange_profile_corners((-.03,0.,0.),(0.,0.,0.),.03,.013)
    reverse=_flange_profile_corners((0.,0.,0.),(-.03,0.,0.),.03,.013)
    assert set(forward)==set(reverse)
    assert {point[1] for point in forward}=={0.,.013}


@pytest.mark.parametrize('end',[(-.02,0.,0.),(-.03,.001,0.),(-.03,0.,.001),(float('nan'),0.,0.)])
def test_native_converted_line_must_be_full_straight_and_on_its_sketch_plane(end):
    with pytest.raises(ExecutionFailure):_flange_profile_corners((0.,0.,0.),end,.03,.013)


@pytest.mark.parametrize('key,value',[
    ('OffsetDistance',.017),('PositionType',2),('OffsetDimType',2),('ReverseOffset',True),
    ('UseDefaultBendAllowance',True),('UseDefaultBendRadius',True),('BendRadius',.002),
    ('k_factor',.42),('allowance_type',1),('edge_count',2),('LockAngle',False),
    ('GapDistance',float('nan')),('BendAngle',float('inf')),('UseDefaultBendRelief',False),
    ('OffsetType',True),('edge_count',True),('allowance_type',2.),('k_factor',True),
    ('OffsetDistance',True),('ReverseOffset',0),('LockAngle',1)])
def test_mass_or_factory_success_does_not_hide_wrong_native_options(flange,key,value):
    actual=parameters(flange);actual[key]=value
    assert not native_flange_parameters_match(actual,flange)


def test_every_native_option_is_required_but_numeric_roundoff_is_permitted(flange):
    actual=parameters(flange);actual['OffsetDistance']-=1.4e-17
    assert native_flange_parameters_match(actual,flange)
    for key in actual:
        incomplete=actual.copy();incomplete.pop(key)
        assert not native_flange_parameters_match(incomplete,flange)
    assert not native_flange_parameters_match({**actual,'unknown_option':False},flange)


@pytest.fixture
def bridge(monkeypatch,flange):
    from solidworks_mcp import binding
    monkeypatch.setattr(binding,'wrap',lambda value,interface:value)
    a=CadSheetEdgeFlangeMixin();a._module=NS(IEdgeFlangeFeatureData=object,ICustomBendAllowance=object,
        IEdge=object,IVertex=object,ISketch=object,IFeature=object,IBodyFolder=object,IBody2=object)
    a.identity=id;a.same_persistent_id=lambda m,p,q:p==q
    data=NS(**flange_options(flange));data.GetCustomBendAllowance=lambda:NS(Type=2,KFactor=.38)
    data.GetEdgeCount=lambda:1
    feature=NS(GetTypeName2=lambda:'EdgeFlange',GetDefinition=lambda:data)
    return a,data,feature


def test_actual_definition_getters_supply_independent_complete_readback(bridge,flange):
    a,data,feature=bridge
    assert a.sheet_flange_parameters(feature)==parameters(flange)
    data.OffsetDistance=.017
    assert not native_flange_parameters_match(a.sheet_flange_parameters(feature),flange)


@pytest.mark.parametrize('defect',['missing_definition','missing_allowance','wrong_feature'])
def test_missing_native_readback_is_not_inferred_from_shape(bridge,defect):
    a,data,feature=bridge
    if defect=='missing_definition':feature.GetDefinition=lambda:None
    elif defect=='missing_allowance':data.GetCustomBendAllowance=lambda:None
    else:feature.GetTypeName2=lambda:'SMBaseFlange'
    with pytest.raises(ExecutionFailure):a.sheet_flange_parameters(feature)


@pytest.fixture
def edge_bridge(bridge):
    a,_,_=bridge;calls=[];model=object()
    edge=NS(GetStartVertex=lambda:NS(GetPoint=lambda:[.002,.02,0.]),
        GetEndVertex=lambda:NS(GetPoint=lambda:[.002,.02,.03]))
    body=NS(IsSheetMetal=lambda:True,GetEdges=lambda:[edge]);target=NS(body_pid=b'body')
    receipt=NativeEdgeFlangeReceipt(target,{},edge,id(edge),b'edge',(),{})
    a._sheet_state_target_current=lambda m,t:calls.append('context')
    refs={b'edge':edge,b'body':body};a.resolve_persistent_id=lambda m,p,k:refs[p]
    a.bodies=lambda m,k:[body]
    return a,model,edge,body,receipt,refs,calls


def test_exact_edge_endpoints_also_require_body_and_context_ownership(edge_bridge,flange):
    a,model,edge,_,receipt,_,calls=edge_bridge
    assert a._sheet_flange_edge_current(model,receipt,flange,IDENTITY) is edge
    assert calls==['context']


@pytest.mark.parametrize('defect',['foreign_edge','foreign_body','duplicate_edge','second_body','wrong_side','partial_edge','missing_vertex'])
def test_geometrically_plausible_wrong_membership_cannot_authorize_creation(edge_bridge,flange,defect):
    a,model,edge,body,receipt,refs,_=edge_bridge
    if defect=='foreign_edge':refs[b'edge']=deepcopy(edge)
    elif defect=='foreign_body':a.bodies=lambda m,k:[object()]
    elif defect=='duplicate_edge':body.GetEdges=lambda:[edge,edge]
    elif defect=='second_body':a.bodies=lambda m,k:[body,object()]
    elif defect=='wrong_side':edge.GetStartVertex=lambda:NS(GetPoint=lambda:[0.,.02,0.])
    elif defect=='partial_edge':edge.GetEndVertex=lambda:NS(GetPoint=lambda:[.002,.02,.02])
    else:edge.GetStartVertex=lambda:None
    with pytest.raises(ExecutionFailure):a._sheet_flange_edge_current(model,receipt,flange,IDENTITY)


def test_pending_creation_cannot_be_replayed_even_if_native_handle_is_missing(bridge,flange):
    a,_,_=bridge;receipt=NativeEdgeFlangeReceipt(object(),{},object(),1,b'x',(),{},pending_creation=True)
    with pytest.raises(ExecutionFailure,match='fresh receipt'):
        a.create_sheet_edge_flange(object(),flange,IDENTITY,receipt)


@pytest.fixture
def bundle_bridge(bridge):
    a,_,flange=bridge;model=object();events=[]
    def node(kind):
        feature=NS(GetTypeName2=lambda:kind)
        feature.GetID=lambda:id(feature)
        return feature
    base,sheet,flat,cut,profile,bend,ui=map(node,('SMBaseFlange','SheetMetal','FlatPattern','CutListFolder','ProfileFeature','OneBend','UiBend'))
    old_flat=[node('ProfileFeature'),node('ProfileFeature'),node('UiBend'),node('FoldUpDownSketchFolder')]
    baseline=[base,sheet,flat,cut,*old_flat];refs={}
    members=[NS(role=role,feature=f,identity=id(f),owner=None) for role,f in zip(('base','sheet','flat','cut_list'),baseline)]
    members.extend(NS(role=role,feature=f,identity=id(f),owner=flat) for role,f in zip(
        ('flat_sketch_1','flat_sketch_2','ui_bend','fold_sketch_folder'),old_flat))
    ui.GetOwnerFeature=lambda:flat
    ui.GetParents=lambda:[bend];ui.GetChildren=lambda:None
    body=NS(IsSheetMetal=lambda:True,GetFeatures=lambda:[base,sheet,flat,flange])
    cut.GetSpecificFeature2=lambda:NS(GetBodies=lambda:[body]);target=NS(members=members,body_pid=b'body')
    receipt=NativeEdgeFlangeReceipt(target,{},object(),1,b'edge',tuple(baseline),{'k_factor':.42},
        sketch=profile,sketch_identity=id(profile),flange=flange,flange_identity=id(flange),
        owned_children=[(profile,id(profile),b'profile','ProfileFeature'),(bend,id(bend),b'bend','OneBend')])
    a._sheet_state_target_current=lambda m,t:events.append('context')
    a._sheet_flange_children=lambda m,r:[profile,bend]
    a._sheet_member_reference=lambda m,r:events.append('member_'+r.role)
    a._sheet_absorbed=lambda f:[*old_flat,ui]
    a.persistent_id=lambda m,f:b'new-ui'
    a.resolve_persistent_id=lambda m,p,k:body
    a.features=lambda m:[*baseline,flange,profile,bend,ui]
    a.bodies=lambda m,k:[body]
    a._sheet_flange_source_parameters=lambda m,t:{'k_factor':.42}
    return a,model,receipt,body,ui,events


def test_full_bundle_proof_preserves_original_members_and_retains_suppressed_bend(bundle_bridge):
    a,model,receipt,body,ui,events=bundle_bridge
    result=a.sheet_flange_bundle(model,receipt)
    assert result['body'] is body and result['flat_bend'] is ui
    assert receipt.flat_bend_member.identity==id(ui)
    assert 'member_flange_flat_bend' in events
    # Suppressed UiBend is checked using its retained native-member reference,
    # not the general geometry resolver that rejects suppression status 2.
    a.sheet_flange_bundle(model,receipt)
    assert events.count('member_flange_flat_bend')==2


def test_derived_bend_need_not_appear_in_direct_subfeature_view(bundle_bridge):
    a,model,receipt,_,ui,_=bundle_bridge
    flat=next(m.feature for m in receipt.source_target.members if m.role=='flat')
    original=a._sheet_absorbed(flat)[:-1]
    a._sheet_absorbed=lambda f:original
    assert a.sheet_flange_bundle(model,receipt)['flat_bend'] is ui
    assert receipt.flat_bend_member.owner is flat


@pytest.mark.parametrize('defect',['foreign_owner','foreign_parent','second_parent','nonleaf','partial_parents','partial_children'])
def test_derived_bend_must_bind_exact_flat_and_own_one_bend_with_complete_dependencies(bundle_bridge,defect):
    a,model,receipt,_,ui,_=bundle_bridge
    if defect=='foreign_owner':ui.GetOwnerFeature=lambda:object()
    elif defect=='foreign_parent':ui.GetParents=lambda:[object()]
    elif defect=='second_parent':ui.GetParents=lambda:[object(),object()]
    elif defect=='nonleaf':ui.GetChildren=lambda:[object()]
    elif defect=='partial_parents':ui.GetParents=lambda:False
    else:ui.GetChildren=lambda:False
    with pytest.raises(ExecutionFailure):a.sheet_flange_bundle(model,receipt)


@pytest.mark.parametrize('defect',['extra_feature','removed_baseline','foreign_body_member','foreign_cut_body','original_K_changed','replaced_flat_bend','partial_flat_children'])
def test_full_mass_matching_bundle_still_rejects_foreign_graph_or_original_K(bundle_bridge,defect):
    a,model,receipt,body,ui,_=bundle_bridge
    if defect in ('extra_feature','removed_baseline'):
        actual=a.features(model)
        if defect=='extra_feature':actual.append(NS(GetID=lambda:500,GetTypeName2=lambda:'Fillet'))
        else:actual.pop(0)
        a.features=lambda m:actual
    elif defect=='foreign_body_member':body.GetFeatures=lambda:[object(),object(),object(),receipt.flange]
    elif defect=='foreign_cut_body':
        cut=next(m.feature for m in receipt.source_target.members if m.role=='cut_list')
        cut.GetSpecificFeature2=lambda:NS(GetBodies=lambda:[object()])
    elif defect=='original_K_changed':a._sheet_flange_source_parameters=lambda m,t:{'k_factor':.38}
    elif defect=='replaced_flat_bend':receipt.flat_bend_member=NS(identity=1)
    else:a._sheet_absorbed=lambda f:[ui]
    with pytest.raises(ExecutionFailure):a.sheet_flange_bundle(model,receipt)


def test_native_identity_comparison_accepts_unhashable_canonical_tokens_and_rejects_duplicates():
    assert _same_identities([[1],[2]],[[2],[1]])
    for left,right in (([[1],[1]],[[1],[2]]),([[1],[2]],[[1],[1]]),([[1]],[[2]])):
        assert not _same_identities(left,right)


def test_bundle_roundtrip_uses_native_token_equality_instead_of_hashing(bundle_bridge):
    a,model,receipt,_,_,_=bundle_bridge
    a.identity=lambda obj:[id(obj)]
    for member in receipt.source_target.members:member.identity=[member.identity]
    receipt.flange_identity=[receipt.flange_identity];receipt.sketch_identity=[receipt.sketch_identity]
    assert a.sheet_flange_bundle(model,receipt)['body'] is not None


@pytest.mark.parametrize('flag',['pending_creation','pending_deletion','selection_uncertain','restored'])
def test_completed_restoration_never_deletes_unconfirmed_or_already_restored_state(bridge,flange,flag):
    a,_,_=bridge;receipt=NativeEdgeFlangeReceipt(object(),{},object(),1,b'edge',(),{})
    setattr(receipt,flag,True)
    with pytest.raises(ExecutionFailure,match='cannot authorize deletion'):
        a.restore_completed_sheet_flange(object(),receipt,flange,IDENTITY,'Тело','Список вырезов')


@pytest.fixture
def children_bridge(bridge):
    a,_,flange=bridge;model=object()
    sketch=NS(GetConstrainedStatus=lambda:3)
    profile=NS(GetTypeName2=lambda:'ProfileFeature',GetSpecificFeature2=lambda:sketch)
    bend=NS(GetTypeName2=lambda:'OneBend')
    refs={b'flange':flange,b'profile':profile,b'bend':bend}
    a.identity=lambda obj:[id(obj)]
    a.persistent_id=lambda m,f:next(p for p,v in refs.items() if v is f)
    a.resolve_persistent_id=lambda m,p,k:refs[p]
    a._sheet_absorbed=lambda f:[profile,bend]
    receipt=NativeEdgeFlangeReceipt(object(),{},object(),[],b'edge',(),{},
        sketch=profile,sketch_identity=a.identity(profile),sketch_pid=b'profile',native_sketch=sketch,
        flange=flange,flange_identity=a.identity(flange),flange_pid=b'flange')
    return a,model,receipt,refs,sketch,profile,bend


def test_absorbed_profile_is_same_fully_defined_input_with_unhashable_native_identity(children_bridge):
    a,model,receipt,_,_,profile,bend=children_bridge
    assert a._sheet_flange_children(model,receipt)==[profile,bend]
    assert len(receipt.owned_children)==2
    assert a._sheet_flange_children(model,receipt)==[profile,bend]


@pytest.mark.parametrize('defect',['underdefined','bool_status','foreign_sketch','wrong_pid','extra_child','replaced_bend'])
def test_complete_shape_does_not_authorize_adopting_foreign_or_underdefined_profile(children_bridge,defect):
    a,model,receipt,refs,sketch,profile,bend=children_bridge
    if defect=='underdefined':sketch.GetConstrainedStatus=lambda:2
    elif defect=='bool_status':sketch.GetConstrainedStatus=lambda:True
    elif defect=='foreign_sketch':profile.GetSpecificFeature2=lambda:NS(GetConstrainedStatus=lambda:3)
    elif defect=='wrong_pid':refs[b'profile']=NS(GetTypeName2=lambda:'ProfileFeature')
    elif defect=='extra_child':a._sheet_absorbed=lambda f:[profile,bend,bend]
    else:
        a._sheet_flange_children(model,receipt)
        replacement=NS(GetTypeName2=lambda:'OneBend');refs[b'new-bend']=replacement
        a._sheet_absorbed=lambda f:[profile,replacement]
    with pytest.raises(ExecutionFailure):a._sheet_flange_children(model,receipt)
