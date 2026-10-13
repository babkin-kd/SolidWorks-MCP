"""Passive public route safety gates with actual artificial-domain evidence."""
from copy import deepcopy
import asyncio
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from solidworks_mcp.jobs import ExecutionFailure, _json

from test_b2_public_contract import (
    leaf_jobs, execution, leaf, extrusion_proof, proof, case, domain)
from test_b2_native_observer import namespace

scripts=str(Path(__file__).resolve().parents[1]/'scripts')
sys.path.insert(0,scripts)
try:
    import verifier_b2_public_route as helper
finally:
    sys.path.remove(scripts)


@pytest.fixture
def final_evidence(leaf_jobs):
    _,prepared,deleted=leaf_jobs
    return dict(scope='b2_public_positive_extension_v1',accepted=False,
        native_b2_accepted=False,positive_case_passed=True,
        final_job=deleted,final_preparation_job=prepared,
        independent_final_state=deepcopy(deleted['result']['after']['state']))


def original(evidence):
    preparation=evidence['final_preparation_job']['result']
    args=evidence['final_job']['payload']['arguments']
    return dict(operation_id=preparation['creation_operation_id'],
        payload=dict(arguments=dict(document_id=args['document_id'],configuration=args['configuration'],
            sketch_object_id=evidence['final_job']['result']['value']['preserved_sketch_object_id'])),
        result=dict(value=dict(feature_object_id=args['object_id'])))


def test_final_cleanup_state_requires_actual_committed_leaf_and_full_independent_session(final_evidence):
    evidence=final_evidence
    preserved=deepcopy(evidence)
    result=helper.extension_final_state(evidence,original(evidence))
    assert result==evidence['final_job']['result']['after']['state']
    assert evidence==preserved
    result['semantic']['files'].append('changed-only-returned-copy')
    assert evidence==preserved


def test_cross_adapter_view_namespaces_require_full_rows_axis_bijection(final_evidence):
    evidence=final_evidence
    state=evidence['independent_final_state']
    for doc,snapshot in list(state['snapshots'].items()):
        state['snapshots'][doc]=namespace(snapshot,reverse=True)
    assert helper.extension_final_state(evidence,original(evidence))


@pytest.mark.parametrize('fault',['incomplete_session','missing_neighbor','changed_neighbor',
    'changed_application','changed_window','changed_files','changed_graph','changed_active',
    'changed_view_row','premature_acceptance','not_committed','foreign_creation','foreign_sketch'])
def test_final_extension_rejects_incomplete_foreign_or_changed_evidence(final_evidence,fault):
    evidence=final_evidence
    state=evidence['independent_final_state']
    creation=original(evidence)
    target=evidence['final_job']['payload']['arguments']['document_id']
    neighbor=next(key for key in state['snapshots'] if key!=target)
    if fault=='incomplete_session':state['semantic'].pop('application')
    elif fault=='missing_neighbor':state['snapshots'].pop(neighbor)
    elif fault=='changed_neighbor':state['snapshots'][neighbor]['selection_count']=1
    elif fault=='changed_application':state['semantic']['application']['visible']=False
    elif fault=='changed_window':state['semantic']['windows'].append(dict(hwnd=991))
    elif fault=='changed_files':state['semantic']['files'].append('foreign')
    elif fault=='changed_graph':state['semantic']['reference_graph'].append(dict(foreign=True))
    elif fault=='changed_active':state['semantic']['active_document_id']=neighbor
    elif fault=='changed_view_row':
        state['snapshots'][target]['clone_state']['display_data']['annotation_views'][0]['foreign']=True
    elif fault=='premature_acceptance':evidence['accepted']=True
    elif fault=='not_committed':evidence['final_job']['mutation']['phase']='unresolved'
    elif fault=='foreign_creation':creation['operation_id']='another-creation'
    elif fault=='foreign_sketch':creation['payload']['arguments']['sketch_object_id']='another-sketch'
    with pytest.raises((ValueError,KeyError,ExecutionFailure)):
        helper.extension_final_state(evidence,creation)


def test_missing_snapshot_and_forged_semantic_shape_cannot_certify_empty_scope():
    state=dict(semantic={},snapshots={})
    with pytest.raises(ValueError):helper.compare_b2_state(state,deepcopy(state))


def test_dispatch_adds_only_own_row_and_replay_preserves_full_durable_history(leaf_jobs):
    _,preparation,deleted=leaf_jobs
    before=[preparation]
    after=[deepcopy(preparation),deleted]
    preserved=deepcopy((before,after))
    assert helper.preserved_journal(before,after,deleted['operation_id'])
    assert helper.preserved_journal(after,deepcopy(after),deleted['operation_id'])
    assert (before,after)==preserved


@pytest.mark.parametrize('fault',['lost_creation','changed_payload','changed_result',
    'changed_checkpoint','changed_digest','foreign_job','duplicate','missing_dispatched'])
def test_dispatch_cannot_rewrite_original_jobs_or_hide_extra_writes(leaf_jobs,fault):
    _,preparation,deleted=leaf_jobs
    before=[deepcopy(preparation),deepcopy(deleted)]
    after=deepcopy(before)
    if fault=='lost_creation':after.pop(0)
    elif fault=='changed_payload':after[0]['payload']['arguments']['object_id']='foreign'
    elif fault=='changed_result':after[0]['result']['revision']='foreign'
    elif fault=='changed_checkpoint':after[1]['mutation']['phase']='unresolved'
    elif fault=='changed_digest':after[0]['digest']='0'*64
    elif fault=='foreign_job':after.append({**deepcopy(deleted),'operation_id':'foreign'})
    elif fault=='duplicate':after.append(deepcopy(deleted))
    elif fault=='missing_dispatched':after.pop(1)
    with pytest.raises(ValueError):helper.preserved_journal(before,after,deleted['operation_id'])


@pytest.mark.parametrize('step',['depth','rename'])
@pytest.mark.parametrize('unproved',[False,None,1])
def test_public_route_retains_and_stops_dispatch_on_unproved_independent_delta(
        final_evidence,monkeypatch,step,unproved):
    """Synthetic public transport only; no claim about scalar CAD correctness."""
    monkeypatch.syspath_prepend(scripts)
    import verifier_lifecycle
    import verify_dimension_mcp
    import verify_rectangle_stages_public
    state=final_evidence['final_preparation_job']['result']['baseline']
    context=dict(document_id='target',configuration='Основная')
    creation=original(final_evidence)
    creation['result']['after']=dict(state=deepcopy(state))
    rows=[]
    calls=[]
    held=[]
    async def cleanup(*_):pass
    async def invoke(client,gate,report,persist,tool,**arguments):
        calls.append(tool)
        request=arguments.pop('request_id')
        if tool=='dimension_list':
            data=dict(configuration='Основная',total_count=3,next_cursor=None,items=[
                dict(object_id='dim_depth',unit='mm',owner=dict(feature_type='Boss'),write_blockers=[],
                    persistent_reference_supported=True,values={'Основная':10.}),
                dict(object_id='dim_width',unit='mm',owner=dict(feature_type='ProfileFeature')),
                dict(object_id='dim_height',unit='mm',owner=dict(feature_type='ProfileFeature'))])
        elif tool in ('dimension_get','feature_get'):data=dict(revision='rev_current')
        else:data=dict(verified=True)
        operation={'dimension_list':'dimension.list','dimension_get':'dimension.get',
            'dimension_set_value':'dimension.set_value','feature_get':'feature.get',
            'feature_rename':'feature.rename'}[tool]
        mutates=tool in ('dimension_set_value','feature_rename')
        existing=next((row for row in rows if row['request_id']==request),None)
        if existing is None:
            payload=dict(arguments=deepcopy(arguments),mutates=mutates,
                context={key:arguments[key] for key in ('document_id','configuration','object_id') if key in arguments})
            row=dict(operation_id='operation-'+request,operation=operation,request_id=request,
                payload=payload,status='succeeded',error=None,result=data,
                mutation=dict(phase='committed') if mutates else None)
            row['digest']=hashlib.sha256((operation+'\n'+_json(payload)).encode()).hexdigest()
            rows.append(row)
        else:row=existing
        return dict(status='succeeded',operation_id=row['operation_id'],data=deepcopy(row['result']))
    class Client:
        async def call_tool(self,name,arguments):
            assert name=='job_get'
            row=next(row for row in rows if row['operation_id']==arguments['operation_id'])
            return NS(isError=False,structuredContent=dict(status='succeeded',
                data={key:deepcopy(value) for key,value in row.items() if key!='digest'}))
        def retain(self,reason):held.append(reason)
    monkeypatch.setattr(verifier_lifecycle,'read_journal',lambda _:deepcopy(rows))
    monkeypatch.setattr(verify_dimension_mcp,'require_native_cleanup',cleanup)
    monkeypatch.setattr(verify_rectangle_stages_public,'public_invoke',invoke)
    with pytest.raises(ValueError,match='Independent complete'):
        asyncio.run(helper.run_b2_positive(client=Client(),gate=object(),journal_path='synthetic',
            context=context,extrusion_job=creation,observe=lambda *_:deepcopy(state),
            verify_depth=lambda *_:unproved if step=='depth' else True,
            verify_rename=lambda *_:unproved,report={},persist=lambda:None))
    assert len(held)==1
    assert calls[-1]==('dimension_set_value' if step=='depth' else 'feature_rename')
    assert not set(calls)&{'feature_prepare_suppression','feature_prepare_leaf_deletion','feature_delete_leaf'}
