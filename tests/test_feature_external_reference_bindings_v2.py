"""Direct native decoding and closed outgoing-reference binding invariants."""
from copy import deepcopy
import pytest

from solidworks_mcp import cad_deletion_context as native
from solidworks_mcp.feature_external_reference_bindings import feature_reference_semantics, outgoing_bindings, enforce_combined_text_budget
from solidworks_mcp.jobs import ExecutionFailure
from test_feature_deletion_context_v2 import capture, feature_capture, install_context, Driver
from test_feature_domain_v2 import setup
from test_feature_dependency_graph_v2 import install


class NativeFeature:
    def __init__(self, hint=1, rows=None):
        self.hint, self.rows, self.output_calls = hint, deepcopy(rows or []), 0
    def GetID(self): return self.hint
    def ListExternalFileReferencesCount(self): return len(self.rows)
    def ListExternalFileReferences2(self):
        self.output_calls += 1
        assert self.rows, 'Zero count must not read undefined feature OUT values'
        return tuple([row[field] for row in self.rows] if index < 7 else self.rows[0][field]
                     for index, field in enumerate(native.EXTERNAL_FIELDS))


def native_inventory(features):
    return Driver(capture()).feature_external_references(features)


def test_direct_feature_config_outputs_are_scalar_and_empty_nodes_have_no_undefined_out_reads():
    one = NativeFeature(rows=capture()['external_references']['rows'])
    empty = NativeFeature(2)
    actual = native_inventory([one, empty])
    assert actual['feature_count'] == 2 and actual['total_reference_rows'] == 1
    assert actual['features'][0]['rows'] == capture()['external_references']['rows']
    assert actual['features'][1]['rows'] == [] and empty.output_calls == 0
    assert one.output_calls == 1
    assert feature_reference_semantics(actual, [{'native_id':1},{'native_id':2}]) == actual


@pytest.mark.parametrize('fault', ['boolean_id','duplicate_id','boolean_count','closing_count','columns','config_array','config_boolean','config_object','missing_array','native_text_object','aggregate_rows','aggregate_text'])
def test_native_incomplete_reference_inventory_cannot_be_certified(fault):
    row = capture()['external_references']['rows'][0]
    one = NativeFeature(rows=[row])
    features = [one]
    if fault == 'boolean_id': one.hint=True
    elif fault == 'duplicate_id': features.append(NativeFeature(1))
    elif fault == 'boolean_count': one.ListExternalFileReferencesCount=lambda:True
    elif fault == 'closing_count':
        counts=iter([1,0]); one.ListExternalFileReferencesCount=lambda:next(counts)
    elif fault == 'columns': one.ListExternalFileReferences2=lambda:([],)
    elif fault in ('config_array','config_boolean','config_object','missing_array'):
        original=one.ListExternalFileReferences2
        def changed():
            values=list(original())
            if fault == 'config_array': values[7]=[1]
            elif fault == 'config_boolean': values[7]=True
            elif fault == 'config_object': values[8]=object()
            else: values[0]=[]
            return tuple(values)
        one.ListExternalFileReferences2=changed
    elif fault == 'native_text_object': one.rows[0]['data_type']=object()
    elif fault == 'aggregate_rows':
        one.rows=[]
        second=NativeFeature(2)
        one.ListExternalFileReferencesCount=lambda:0
        second.ListExternalFileReferencesCount=lambda:5001
        features.append(second)
    else:
        one.rows=[{**row,'row_index':i,'model_path':'x'*16384,'component_path':'y'*16384} for i in range(65)]
    with pytest.raises(ExecutionFailure): native_inventory(features)


def typed_capture():
    one=NativeFeature(rows=capture()['external_references']['rows'])
    return native_inventory([one, NativeFeature(2)])


@pytest.mark.parametrize('fault', ['scope','coverage','wrong_id','alias','count','total','boolean_index','column','status_boolean','native_object'])
def test_domain_rejects_forged_or_nonmatching_native_census(fault):
    value=typed_capture()
    if fault == 'scope': value['scope']='other'
    elif fault == 'coverage': value['features'].pop()
    elif fault == 'wrong_id': value['features'][0]['native_id']=99
    elif fault == 'alias': value['features'][1]['native_id']=1
    elif fault == 'count': value['features'][0]['count']=True
    elif fault == 'total': value['total_reference_rows']=0
    elif fault == 'boolean_index': value['features'][0]['rows'][0]['row_index']=False
    elif fault == 'column': value['features'][0]['rows'][0].pop('feature_name')
    elif fault == 'status_boolean': value['features'][0]['rows'][0]['status']=True
    else: value['features'][0]['rows'][0]['model_path']=object()
    with pytest.raises(ExecutionFailure): feature_reference_semantics(value,[{'native_id':1},{'native_id':2}])


def graph():
    return {'nodes':[{'native_id':1,'node_index':0,'object_id':'obj_first','name':'Независимое имя'},
                     {'native_id':2,'node_index':1,'object_id':'obj_second','name':'Другая операция'}]}


def test_binding_uses_direct_feature_census_instead_of_graph_display_name():
    result=outgoing_bindings(capture(),typed_capture(),graph())
    assert result['complete'] is True and result['blockers']==[]
    assert result['groups']==[{'document_row_indices':[0], 'feature_rows':[{
        'node_index':0,'native_id':1,'object_id':'obj_first','native_reference_row_indices':[0]}], 'match_status':'bound'}]
    assert result['names_and_indices_are_writable_anchors'] is False


@pytest.mark.parametrize('fault,code', [('unlisted','inventory_mismatch'),('missing','inventory_mismatch'),
    ('multiplicity','inventory_mismatch'),('two_features','ambiguous'),('persistent','persistent_target_unavailable')])
def test_ambiguous_missing_or_unwritable_bindings_are_explicit_not_arbitrary(fault,code):
    context,refs,nodes=capture(),typed_capture(),graph()
    if fault == 'unlisted': context['external_references'].update(count=0,rows=[])
    elif fault == 'missing': refs['features'][0].update(count=0,rows=[]); refs['total_reference_rows']=0
    elif fault == 'multiplicity':
        context['external_references']['rows'].append({**context['external_references']['rows'][0],'row_index':1})
        context['external_references']['count']=2
    elif fault == 'two_features':
        refs['features'][1].update(count=1,rows=deepcopy(refs['features'][0]['rows']))
        refs['total_reference_rows']=2
        context['external_references']['rows'].append({**context['external_references']['rows'][0],'row_index':1})
        context['external_references']['count']=2
    else: nodes['nodes'][0]['object_id']=None
    result=outgoing_bindings(context,refs,nodes)
    assert result['complete'] is False
    assert result['groups'][0]['match_status']==code
    assert result['blockers'][0]['code']=='external_reference_'+code


def test_identical_record_multiplicity_is_preserved_without_cross_product_or_duplicate_target():
    context,refs=capture(),typed_capture()
    rows=[{**context['external_references']['rows'][0],'row_index':index} for index in range(3)]
    context['external_references'].update(count=3,rows=deepcopy(rows))
    refs['features'][0].update(count=3,rows=deepcopy(rows));refs['total_reference_rows']=3
    result=outgoing_bindings(context,refs,graph())
    assert result['complete'] and len(result['groups'])==1
    assert result['groups'][0]['document_row_indices']==[0,1,2]
    assert result['groups'][0]['feature_rows'][0]['native_reference_row_indices']==[0,1,2]


def test_captures_sharing_text_budget_cannot_each_consume_full_allowance():
    context,refs=capture(),typed_capture()
    rows=[{**context['external_references']['rows'][0],'row_index':i,'model_path':'x'*16384,'component_path':'y'*16384} for i in range(60)]
    context['external_references'].update(count=60,rows=deepcopy(rows))
    refs['features'][0].update(count=60,rows=deepcopy(rows));refs['total_reference_rows']=60
    feature_reference_semantics(refs,[{'native_id':1},{'native_id':2}])
    with pytest.raises(ExecutionFailure) as error: enforce_combined_text_budget(context,refs)
    assert error.value.code=='feature_context_budget_exceeded'


def test_reference_change_without_stamp_or_global_inventory_changes_context_revision(setup):
    adapter,_,catalog,_,ids=setup
    install(adapter); install_context(adapter)
    value=feature_capture(adapter.models[0].features,capture()['external_references']['rows'])
    adapter.feature_external_references=lambda native:value
    first=catalog.deletion_context(ids[0],'Основная')
    value['features'][0]['rows'][0]['status']=3
    second=catalog.deletion_context(ids[0],'Основная')
    assert first['dependency_graph']==second['dependency_graph'] and first['native_context']==second['native_context']
    assert first['revision']!=second['revision']
    assert first['outgoing_reference_bindings']['complete'] and not second['outgoing_reference_bindings']['complete']
    assert second['deletion_authorized'] is second['deletion_impact_complete'] is False
    assert adapter.writes==[]


def test_changed_mutable_feature_capture_between_boundaries_is_not_shared_first_evidence(setup):
    adapter,_,catalog,_,ids=setup
    install(adapter); install_context(adapter)
    value=feature_capture(adapter.models[0].features,capture()['external_references']['rows'])
    calls=[]
    def read(native):
        calls.append(1)
        if len(calls)==2: value['features'][0]['rows'][0]['configuration_name']='Вариант'
        return value
    adapter.feature_external_references=read
    with pytest.raises(ExecutionFailure) as error:catalog.deletion_context(ids[0],'Основная')
    assert error.value.code=='document_changed_during_read' and adapter.writes==[]
