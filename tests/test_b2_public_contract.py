"""Passive B2 contracts + actual SQLite artificial-domain evidence; no CAD."""
from copy import deepcopy
import hashlib
import inspect
from pathlib import Path
import sys

import pytest

from solidworks_mcp.jobs import _json
from test_owned_leaf_deletion_execution import execution, leaf, extrusion_proof, proof, case, domain
from test_b3_public_contract import app_and_runner

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:
    from verifier_b2_public_contract import SPECS, verified_b2_job, durable_b2_job, b2_contract_result
    from verifier_rectangle_public_contract import SPECS as B1_SPECS
    from verifier_lifecycle import DIRECT_QUERIES, CONTEXT_KEYS
finally: sys.path.remove(str(scripts))


INPUTS=dict(request_id='b2-request',document_id='doc_explicit',configuration='Основная',object_id='feat_'+'a'*32,
    expected_revision='rev_exact',suppressed=True,name='Контрольное выдавливание',application_id='app_explicit',
    template_id='template_explicit',plane_object_id='feat_'+'b'*32,sketch_object_id='feat_'+'c'*32,
    width_mm=40,height_mm=20,depth_mm=10,value=12,dimension_id='dim_explicit',unit='mm')

_SUPPRESSION_ROWS={}
_LEAF_ROWS={}


def persisted(state,dto):
    digest=state.store._db.execute('SELECT digest FROM jobs WHERE operation_id=?',(dto['operation_id'],)).fetchone()[0]
    return durable_b2_job(dto,{**deepcopy(dto),'digest':digest})


def native_guard(state):
    original=state.c.adapter.native_open_guard
    def factory(models,ids):
        wrapped=original(models,ids)
        class Guard:
            def __init__(self):
                self.evidence=dict(scope='application_document_open_guard_v1',original_command_in_progress=False,
                    acquired=False,released=False,selection_preserved=True,baseline_document_ids=list(ids),
                    activation_ui_release=dict(attempted=False,verified=False),model_guards=[])
            def __enter__(self):
                wrapped.__enter__()
                self.evidence.update(acquired=True,model_guards=[dict(original_state=0,locked_state=2,released_state=None)
                                                                for _ in models])
            def __exit__(self,*args):
                result=wrapped.__exit__(*args)
                self.evidence['released']=True
                for row in self.evidence['model_guards']: row['released_state']=0
                return result
        return Guard()
    state.c.adapter.native_open_guard=factory


def preparation(state,operation,arguments,catalog):
    job=state.runner.submit('prepare_'+str(len(state.store.list()['items'])),operation,arguments,
        lambda:catalog.prepare(**arguments),context={key:arguments[key] for key in ('document_id','configuration','object_id')},
        mutates=False)
    assert job['status']=='succeeded',job.get('error')
    return persisted(state,state.store.get(job['operation_id']))


@pytest.fixture
def suppression_jobs(domain,request):
    state=domain
    key=request.node.callspec.params['case']
    if key in _SUPPRESSION_ROWS:
        return (None,*deepcopy(_SUPPRESSION_ROWS[key]))
    native_guard(state)
    args=dict(document_id='target',configuration='Основная',object_id=state.binding.object_id,suppressed=True)
    first_prep=preparation(state,'feature.prepare_suppression',args,state.catalog)
    def mutate(arguments,request):
        job=state.runner.submit(request,'feature.set_suppressed',arguments,
            lambda operation_id:state.catalog.set_suppressed(operation_id,**arguments),
            context={key:arguments[key] for key in CONTEXT_KEYS if key in arguments},mutates=True,
            verify=lambda result:result.get('verified') is True,pass_operation_id=True)
        return persisted(state,state.store.get(job['operation_id']))
    first=mutate({**args,'expected_revision':first_prep['result']['revision']},'suppress')
    assert first['status']=='succeeded',first.get('error')
    last_prep=preparation(state,'feature.prepare_suppression',{**args,'suppressed':False},state.catalog)
    last=mutate({**args,'suppressed':False,'expected_revision':last_prep['result']['revision']},'return')
    assert last['status']=='succeeded',last.get('error')
    _SUPPRESSION_ROWS[key]=deepcopy((first_prep,first,last_prep,last))
    return state,first_prep,first,last_prep,last


@pytest.fixture
def leaf_jobs(execution,request):
    state=execution
    key=request.node.callspec.params['case']
    if key in _LEAF_ROWS:
        return (None,*deepcopy(_LEAF_ROWS[key]))
    native_guard(state)
    args=dict(document_id='target',configuration='Основная',object_id=state.binding.object_id)
    prepared=preparation(state,'feature.prepare_leaf_deletion',args,state.leaf)
    arguments={**args,'expected_revision':prepared['result']['revision']}
    job=state.runner.submit('delete','feature.delete_leaf',arguments,
        lambda operation_id:state.leaf.delete(operation_id,**arguments),context=arguments,
        mutates=True,verify=lambda result:result.get('verified') is True,pass_operation_id=True)
    result=persisted(state,state.store.get(job['operation_id']))
    assert result['status']=='succeeded',result.get('error')
    _LEAF_ROWS[key]=deepcopy((prepared,result))
    return state,prepared,result


def redigest(row):
    row['digest']=hashlib.sha256((row['operation']+'\n'+_json(row['payload'])).encode('utf8')).hexdigest()


def mirror_after(row):
    row['mutation']['verification']['evidence']['after']=deepcopy(row['result']['after'])
    row['mutation']['verification']['native_steps'][-1]['evidence']['observed']=deepcopy(row['result']['after'])


def test_finite_chain_specs_keep_bootstrap_and_job_reads_under_supervisor():
    assert set(SPECS)==set(B1_SPECS)|{'dimension_list','dimension_get','dimension_set_value','feature_rename',
        'feature_prepare_suppression','feature_set_suppressed','feature_prepare_leaf_deletion','feature_delete_leaf'}
    assert {name:SPECS[name] for name in B1_SPECS}==B1_SPECS
    assert {'job_get','job_list'}<=DIRECT_QUERIES and not {'job_get','job_list'}&set(SPECS)
    assert SPECS['dimension_set_value'].float_arguments==frozenset({'value'})
    assert SPECS['feature_set_suppressed'].operation=='feature.set_suppressed'
    assert SPECS['feature_delete_leaf'].operation=='feature.delete_leaf'


@pytest.mark.parametrize('tool',sorted(SPECS))
def test_specs_match_actual_public_facade_runtime_payload_without_worker_or_cad(app_and_runner,tool):
    app,runner=app_and_runner
    params=inspect.signature(app._tool_manager.get_tool(tool).fn).parameters
    arguments={key:deepcopy(INPUTS[key]) for key,param in params.items() if param.default is inspect.Parameter.empty}
    original=deepcopy(arguments)
    import asyncio
    asyncio.run(app.call_tool(tool,arguments))
    actual=runner.calls[-1]
    assert actual['operation']==SPECS[tool].operation
    assert _json(actual['job']['payload'])==_json(SPECS[tool].payload(arguments))
    assert actual['request_id']==arguments['request_id']
    assert actual['pass_operation_id'] is SPECS[tool].mutates
    assert arguments==original


def test_actual_committed_suppression_and_return_require_explicit_prepare_and_original_lineage(suppression_jobs):
    state,prepared,first,return_prepared,last=suppression_jobs
    assert verified_b2_job(prepared) and verified_b2_job(return_prepared)
    assert verified_b2_job(first,preparation_job=prepared)
    assert verified_b2_job(last,preparation_job=return_prepared,original_suppression_job=first)
    assert not verified_b2_job(first) and not verified_b2_job(last,preparation_job=return_prepared)
    result=b2_contract_result(last,preparation_job=return_prepared,original_suppression_job=first)
    assert result['job_verified'] is True and result['accepted'] is result['native_b2'] is False


def test_actual_committed_leaf_deletion_requires_prepare_full_geometry_pid_and_sketch(leaf_jobs):
    state,prepared,job=leaf_jobs
    assert verified_b2_job(prepared)
    assert verified_b2_job(job,preparation_job=prepared)
    assert not verified_b2_job(job)
    assert job['result']['after']['old_feature_pid']['native_state']==1
    result=b2_contract_result(job,preparation_job=prepared)
    assert result['job_verified'] is True and result['accepted'] is result['native_b2'] is False


@pytest.mark.parametrize('fault',['digest','request','context','arguments','status','phase','epoch','checkpoint',
    'result_evidence','guard_evidence','pending','action_pending','action_result','guard_not_released',
    'native_guard_count','native_guard_ids','ledger_pending','ledger_sequence','ledger_missing',
    'ledger_duplicate','full_snapshot','foreign_refs','neighbor_data','files','action_bool_coercion','release_evidence'])
def test_forged_partial_or_divergent_committed_suppression_rows_fail_closed(suppression_jobs,fault):
    state,prepared,original,_,_=suppression_jobs
    job=deepcopy(original)
    if fault=='digest': job['digest']='foreign'
    elif fault=='request': job['request_id']=''
    elif fault=='context': job['payload']['context']['object_id']='feat_'+'f'*32;redigest(job)
    elif fault=='arguments': job['payload']['arguments']['suppressed']=1;redigest(job)
    elif fault=='status': job['status']='unknown'
    elif fault=='phase': job['mutation']['phase']='unresolved'
    elif fault=='epoch': job['mutation']['connection_epoch']='reconnected'
    elif fault=='checkpoint': job['mutation']['before_state']['feature_pid_hex']='ff'
    elif fault=='result_evidence': job['mutation']['verification']['evidence']['after']['pending']=True
    elif fault=='guard_evidence': job['mutation']['verification']['evidence']['execution_guard']['journal_failed']=True
    elif fault in ('pending','action_pending','action_result','action_bool_coercion','full_snapshot','foreign_refs','neighbor_data','files'):
        after=job['result']['after']
        if fault=='pending': after['pending']=True
        elif fault=='action_pending': after['native_actions'][0]['pending_native_step']='rebuild'
        elif fault=='action_result': after['native_actions'][0]['steps'][0]['result']=False
        elif fault=='action_bool_coercion': after['native_actions'][0]['attempted']=1
        elif fault=='full_snapshot': after['state']['snapshots']['target']['clone_state']['parameters']['width_m']=.05
        elif fault=='foreign_refs': after['state']['snapshots']['target']['references'][0]['token']='foreign'
        elif fault=='neighbor_data': after['state']['snapshots']['neighbor']['clone_state']['material']=['foreign','']
        else: after['original_files']=['foreign']
        mirror_after(job)
    elif fault in ('guard_not_released','native_guard_count','native_guard_ids'):
        guard=job['result']['execution_guard']
        if fault=='guard_not_released': guard['guard_released']=False
        elif fault=='native_guard_count': guard['native_guards'][0]['model_guards'].pop()
        else: guard['native_guards'][0]['baseline_document_ids']=['foreign']
        job['mutation']['verification']['evidence']['execution_guard']=deepcopy(guard)
    else:
        steps=job['mutation']['verification']['native_steps']
        if fault=='ledger_pending': steps[-1]['phase']='pending'
        elif fault=='ledger_sequence': steps[0]['sequence']=True
        elif fault=='ledger_missing': steps.pop(3)
        elif fault=='release_evidence': next(row for row in steps if row['name']=='suppression_guard_release_1'
                                             and row['phase']=='returned')['evidence']={}
        else: steps[2]['name']=steps[3]['name']=steps[0]['name']
    assert not verified_b2_job(job,preparation_job=prepared)


@pytest.mark.parametrize('fault',['wrong_ancestor','epoch','object','original_base','uncommitted','pid'])
def test_return_ancestry_is_an_explicit_original_durable_result_not_a_guessed_job(suppression_jobs,fault):
    _,_,old,prepared,job=suppression_jobs
    ancestor=deepcopy(old)
    if fault=='wrong_ancestor': ancestor['operation_id']='foreign'
    elif fault=='epoch': ancestor['mutation']['connection_epoch']='foreign'
    elif fault=='object':
        ancestor['payload']['arguments']['object_id']='feat_'+'f'*32
        ancestor['payload']['context']['object_id']='feat_'+'f'*32
        redigest(ancestor)
    elif fault=='original_base': ancestor['result']['before']['original_base']['snapshots']['target']['clone_state']['material']=['foreign','']
    elif fault=='uncommitted': ancestor['mutation']['phase']='prepared'
    else: ancestor['result']['before']['feature_pid_hex']='ff'
    assert not verified_b2_job(job,preparation_job=prepared,original_suppression_job=ancestor)


@pytest.mark.parametrize('fault',['native_pid_state','pid_not_null','sketch_unproven','canonical_present',
    'bridge_pending','sketch_geometry','remaining_depth','returned_value','release','native_steps','bridge_bool_coercion','pid_bool_coercion'])
def test_leaf_boolean_success_cannot_replace_complete_detached_native_and_geometric_proofs(leaf_jobs,fault):
    _,prepared,original=leaf_jobs
    job=deepcopy(original)
    after=job['result']['after']
    if fault=='native_pid_state': after['old_feature_pid']['native_state']=2
    elif fault=='pid_not_null': after['old_feature_pid']['native_object_is_null']=False
    elif fault=='sketch_unproven': after['sketch_canonical_and_pid_confirmed']=False
    elif fault=='canonical_present': after['target_canonical_absent']=False
    elif fault=='bridge_pending': after['receipt']['pending_native_step']='restore_delete_extrusion'
    elif fault=='bridge_bool_coercion': after['receipt']['bridge_returned']=1
    elif fault=='pid_bool_coercion': after['old_feature_pid']['native_object_is_null']=1
    elif fault=='sketch_geometry': after['state']['snapshots']['target']['clone_state']['sketch']['points'][0]['coordinates_si'][0]=(.1).hex()
    elif fault=='remaining_depth':
        data=after['state']['snapshots']['target']['clone_state']
        data['dimensions'].append(deepcopy(job['result']['before']['baseline']['snapshots']['target']['clone_state']['dimensions'][2]))
    elif fault=='returned_value': job['result']['value']['preserved_sketch_object_id']='feat_'+'f'*32
    elif fault=='release': after['guard_released']=False
    else: job['mutation']['verification']['native_steps'][3]['evidence']['native_call_returned']=False
    mirror_after(job)
    assert not verified_b2_job(job,preparation_job=prepared)


@pytest.mark.parametrize('fault',['revision','creator','scope','typed_bool','input','epoch','baseline','lineage'])
def test_actual_prepare_digest_and_scope_must_match_every_projected_checkpoint_field(suppression_jobs,fault):
    _,original,job,_,_=suppression_jobs
    prepared=deepcopy(original)
    value=prepared['result']
    if fault=='revision': value['revision']='rev_foreign'
    elif fault=='creator': value['creation_operation_id']='foreign'
    elif fault=='scope': value['scope']='foreign'
    elif fault=='typed_bool': value['suppressed']=1
    elif fault=='input': prepared['payload']['arguments']['object_id']='feat_'+'f'*32;redigest(prepared)
    elif fault=='epoch': value['connection_epoch']='foreign'
    elif fault=='baseline': value['baseline']['snapshots']['target']['clone_state']['parameters']['depth_m']=.02
    else: value['original_suppression_operation_id']='invented'
    assert not verified_b2_job(job,preparation_job=prepared)


@pytest.mark.parametrize('fault',['digest','missing_field','extra_field','request','result'])
def test_public_dto_is_exactly_bound_to_sqlite_except_private_digest(suppression_jobs,fault):
    _,_,persisted_row,_,_=suppression_jobs
    dto={key:deepcopy(value) for key,value in persisted_row.items() if key!='digest'}
    row=deepcopy(persisted_row)
    if fault=='digest': row['digest']='foreign'
    elif fault=='missing_field': dto.pop('created_at')
    elif fault=='extra_field': dto['invented']=True
    elif fault=='request': dto['request_id']='foreign'
    else: dto['result']['verified']=False
    with pytest.raises(ValueError): durable_b2_job(dto,row)


def test_only_explicit_synthetic_null_read_checkpoint_is_normalized(suppression_jobs):
    _,prepared,_,_,_=suppression_jobs
    dto={key:deepcopy(value) for key,value in prepared.items() if key!='digest'}
    assert 'mutation' not in dto
    sql={**deepcopy(prepared),'mutation':None}
    assert durable_b2_job(dto,sql)==sql
    assert verified_b2_job(sql)
    for synthetic in (False,{},dict(phase='committed')):
        with pytest.raises(ValueError): durable_b2_job(dto,{**sql,'mutation':synthetic})
    for changed in ({key:value for key,value in dto.items() if key!='created_at'}, {**dto,'extra':True}):
        with pytest.raises(ValueError): durable_b2_job(changed,sql)


@pytest.mark.parametrize('label',['leaf_bind_annotation_view_feature_0',
    'leaf_bind_annotation_view_feature_15','leaf_bind_annotation_view_feature_16','leaf_unobserved_native_step'])
def test_optional_view_binding_ledger_uses_only_the_existing_finite_native_bridge_labels(leaf_jobs,label):
    _,prepared,original=leaf_jobs
    job=deepcopy(original)
    steps=job['mutation']['verification']['native_steps']
    insert=len(steps)-2
    steps[insert:insert]=[dict(sequence=0,name=label,phase='pending',evidence=dict(native_call_returned=False)),
        dict(sequence=0,name=label,phase='returned',evidence=dict(native_call_returned=True))]
    for index,row in enumerate(steps): row['sequence']=index+1
    assert verified_b2_job(job,preparation_job=prepared) is (label.endswith('_0') or label.endswith('_15'))


@pytest.mark.parametrize('event_count',[32,34])
def test_b2_native_step_budget_matches_default_actual_jobstore_cap_with_coherent_unique_pairs(leaf_jobs,event_count):
    _,prepared,original=leaf_jobs
    job=deepcopy(original)
    steps=job['mutation']['verification']['native_steps']
    extra=[]
    for index in range((event_count-len(steps))//2):
        name='leaf_bind_annotation_view_feature_'+str(index)
        extra.extend([dict(sequence=0,name=name,phase='pending',evidence=dict(native_call_returned=False)),
            dict(sequence=0,name=name,phase='returned',evidence=dict(native_call_returned=True))])
    steps[-2:-2]=extra
    for index,row in enumerate(steps): row['sequence']=index+1
    assert len(steps)==event_count
    assert len({row['name'] for row in steps})==event_count//2
    assert all(row['sequence']==index+1 and row['phase']==('pending' if index%2==0 else 'returned')
               for index,row in enumerate(steps))
    assert verified_b2_job(job,preparation_job=prepared) is (event_count==32)
