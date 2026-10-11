"""Read-only preparation contract on a complete artificial L-sheet fixture."""

from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.sheet_parameters import SheetParameterCatalog
from test_part_creation_domain_v2 import setup as part_setup
from test_sheet_parameters_v2 import material_state

from solidworks_mcp import sheet_edge_flange as draft


@pytest.fixture
def prepared(part_setup):
    state,source=material_state(part_setup)
    SheetParameterCatalog._source(state,'Основная',source.plane_object_id)
    calls=[];model=object();body=object();edge=object();entry=NS(model=model)
    adapter=NS(identity=lambda obj:[id(obj)],resolve_persistent_id=lambda m,p,k:body,
        owner_body=lambda e,k:body,pattern_edge_points=lambda e:[(.002,.02,0.),(.002,.02,.03)])
    dimensions=NS(adapter=adapter,documents=NS(adapter=adapter),features=None,
        _close_native_proof=lambda e,s:calls.append('close'))
    catalog=draft.SheetEdgeFlangeCatalog(dimensions)
    target=NS(body_pid=b'body');capture=NS(state=(entry,object()),event_sequence=1)
    def capture_source(*args):calls.append('capture');return capture,target,state,(),source,{},{}
    catalog._capture=capture_source
    reference=NS(body_id='obj_'+'b'*32,persistent_id=b'edge')
    def resolve(*args):calls.append('edge');return edge,reference
    catalog.geometry._resolve=resolve
    arguments=dict(document_id='doc_'+'a'*32,configuration='Основная',base_object_id='feat_'+'c'*32,
        edge_id='obj_'+'d'*32,flange_length_mm=15.,bend_radius_mm=2.5,k_factor=.38)
    return catalog,arguments,state,source,calls,reference,adapter


def test_preparation_binds_exact_source_and_edge_but_performs_no_mutation(prepared):
    catalog,args,_,source,calls,_,_=prepared
    result=catalog.prepare_edge_flange(**args)
    assert calls==['capture','edge','close']
    assert result['revision_scope']=='single_l_sheet_edge_flange_v1'
    assert result['revision'].startswith('rev_') and result['native_change_available'] is False
    assert result['source_parameters']['k_factor']==source.k_factor==.42
    assert result['k_factor']==.38 and result['edge_id']==args['edge_id']
    assert tuple(result['expected_geometry'][key] for key in ('vertex_count','edge_count','face_count'))==(24,44,22)


@pytest.mark.parametrize('name,value',[
    ('base_object_id','active'),('edge_id','feat_'+'a'*32),('edge_id','obj_a'),
    ('flange_length_mm',True),('flange_length_mm',0.),('flange_length_mm',float('inf')),
    ('bend_radius_mm',-1.),('bend_radius_mm',10000001.),('k_factor',True),
    ('k_factor',float('nan')),('k_factor',1.1),('k_factor',-.01),
    ('sketch_name','Sketch'),('feature_name','Flange'),('sketch_name','Сгиб отбортовки'),
    ('feature_name','Развёртка сгиба отбортовки')])
def test_invalid_requests_are_rejected_before_native_capture(prepared,name,value):
    catalog,args,_,_,calls,_,_=prepared;args[name]=value
    with pytest.raises(ExecutionFailure):catalog.prepare_edge_flange(**args)
    assert calls==[]


@pytest.mark.parametrize('defect',['flat','no_straight_flange','no_body_reference','foreign_body','wrong_side','partial_edge','name_conflict'])
def test_geometric_or_ownership_failure_never_returns_a_prepared_revision(prepared,defect):
    catalog,args,state,_,calls,reference,adapter=prepared
    if defect=='flat':state['evidence']['flattened']=True
    elif defect=='no_straight_flange':args['flange_length_mm']=4.
    elif defect=='no_body_reference':reference.body_id=None
    elif defect=='foreign_body':adapter.owner_body=lambda e,k:object()
    elif defect=='wrong_side':adapter.pattern_edge_points=lambda e:[(0.,.02,0.),(0.,.02,.03)]
    elif defect=='partial_edge':adapter.pattern_edge_points=lambda e:[(.002,.02,0.),(.002,.02,.02)]
    else:state['semantic']['tree']['features'][0]['name']='Отбортовка'
    with pytest.raises(ExecutionFailure):catalog.prepare_edge_flange(**args)
    assert 'close' not in calls


def test_request_revision_changes_for_native_edge_or_requested_effect(prepared):
    catalog,args,_,_,_,reference,_=prepared
    original=catalog.prepare_edge_flange(**args)['revision']
    reference.persistent_id=b'other-edge'
    assert catalog.prepare_edge_flange(**args)['revision']!=original
    reference.persistent_id=b'edge';args['k_factor']=.39
    assert catalog.prepare_edge_flange(**args)['revision']!=original


def test_existing_namespace_error_is_propagated_without_guessing_an_edge(prepared):
    catalog,args,_,_,calls,_,_=prepared
    def resolve(*args):raise ExecutionFailure('object_configuration_mismatch','The native edge belongs to another configuration.',uncertain=False)
    catalog.geometry._resolve=resolve
    with pytest.raises(ExecutionFailure) as error:catalog.prepare_edge_flange(**args)
    assert error.value.code=='object_configuration_mismatch' and calls==['capture']
