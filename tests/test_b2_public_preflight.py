"""Actual artificial domain/runner/SQLite prerequisite reports; no native CAD."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_rectangle_construction import NativeRectangleStageReceipt
from solidworks_mcp.jobs import _json
from solidworks_mcp.mutations import MutationCoordinator,PreparedMutation
from solidworks_mcp.owned_rectangle_feature import OwnedRectangleFeatureRegistry,RECEIPT_FIELDS
from solidworks_mcp.rectangle_construction import RectangleSketch,BlindRectangleExtrusion
from solidworks_mcp.rectangle_postconditions import verified_rectangle_sketch
from solidworks_mcp.rectangle_extrusion_postconditions import verified_rectangle_extrusion
from test_owned_leaf_deletion_execution import execution,leaf,extrusion_proof,proof,case,domain
from test_rectangle_postconditions import proof as sketch_proof,empty_adapter
from test_b2_impact_fixture import b2_private_dir,b2_outside_dir

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:
    import verifier_b2_public_preflight as helper
    import verify_owned_leaf_deletion_faults as driver
    from verifier_rectangle_positive_acceptance import POSITIVE_LABELS
    from verifier_rectangle_stages import verified_rectangle_job
    from test_owned_leaf_deletion_faults import faults
finally:sys.path.remove(str(scripts))

_ARTIFACTS={}


def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf8')
    return helper._sha(path)


def guard(ids):
    return dict(scope='application_document_open_guard_v1',original_command_in_progress=False,
        acquired=True,released=True,selection_preserved=True,baseline_document_ids=list(ids),
        activation_ui_release=dict(attempted=False,verified=False),
        model_guards=[dict(original_state=0,locked_state=2,released_state=0) for _ in ids])


def stage(state,kind,before,after,definition,object_id):
    """Actual coordinator and genuine full classifier over changing fake state."""
    scope='empty_part_rectangle_sketch_v1' if kind=='sketch' else 'closed_rectangle_blind_extrusion_v1'
    native_id=4 if kind=='sketch' else 5
    old=before['snapshots']['target']['clone_state']
    role=old['sketch']['feature_pid_hex']['reference_role'] if kind=='extrusion' else 'feature:0'
    pid=next(row['token'] for row in before['snapshots']['target']['references'] if row['kind']=='feature' and row['role']==role)
    frame=[float.fromhex(value) for value in after['snapshots']['target']['clone_state']['sketch']['reference_plane']['transform']]
    payload=dict(scope=scope,connection_epoch='epoch',document_id='target',configuration='Основная',
        definition=vars(definition),baseline=before,reference_persistent_id_hex=pid,plane_transform=frame)
    revision='rev_'+__import__('hashlib').sha256(_json(payload).encode('utf8')).hexdigest()
    checkpoint=dict(scope=scope,baseline=before,definition=vars(definition),
        reference_persistent_id_hex=pid,reference_native_id=4 if kind=='extrusion' else 0,plane_transform=frame)
    args=dict(document_id='target',configuration='Основная',expected_revision=revision,**vars(definition))
    observed=deepcopy(before)
    stage_guard=guard([row['document_id'] for row in before['semantic']['documents']])
    execution_guard=dict(scope='rectangle_construction_guard_v1',native_guards=[stage_guard],
        guard_released=True,pending_release=False,journal_failed=False,reference_binding_unconfirmed=False,full_release_check='effect')
    facts={key:False for key in RECEIPT_FIELDS}
    facts.update(attempted=True,native_call_returned=True,pending_native_step=None,sketch_closed=kind=='sketch')
    oracle=verified_rectangle_sketch if kind=='sketch' else verified_rectangle_extrusion
    def execute(operation_id):
        def record(name,phase,evidence): state.store.record_mutation_step(operation_id,name=name,phase=phase,evidence=evidence)
        class Guard:
            evidence=execution_guard
            def __enter__(self):
                record('rectangle_execution_guard','pending',dict(attempted=True))
                record('rectangle_execution_guard','returned',stage_guard)
            def __exit__(self,*args): return False
        def apply(prepared):
            nonlocal observed
            record('rectangle_construct_artificial','pending',dict(attempted=True))
            observed=deepcopy(after)
            record('rectangle_construct_artificial','returned',dict(native_call_returned=True))
            record('rectangle_guard_release_1','pending',dict(attempted=True))
            record('rectangle_guard_release_1','returned',stage_guard)
            return dict(document_id='target',configuration='Основная',kind=kind,created_native_id=native_id,
                object_id=object_id,**{('sketch_object_id' if kind=='sketch' else 'feature_object_id'):object_id})
        def inspect(prepared):
            return dict(state=deepcopy(observed),receipt=deepcopy(facts),original_files=before['semantic']['files'],
                        pending=False,guard_released=True)
        def verify(old,current,value):
            passed=oracle(old['baseline'],current['state'],'target',definition,native_id)
            record('rectangle_released_check','pending',dict(attempted=True))
            record('rectangle_released_check','returned',dict(verified=passed,observed=current))
            return passed
        return MutationCoordinator(state.store,'epoch').execute(operation_id,document_id='target',configuration='Основная',
            expected_revision=revision,prepare=lambda:PreparedMutation(revision,checkpoint,effect_scope='application'),
            validate=lambda _:True,apply=apply,inspect=inspect,verify=verify,
            restore=lambda *args:pytest.fail('Fixture native inverse is forbidden'),verify_restored=lambda *args:False,
            guard=lambda _:Guard())
    job=state.runner.submit('b1_'+kind,'sketch.create_rectangle' if kind=='sketch' else 'part.extrude_rectangle',args,
        execute,context=args,mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
    assert job['status']=='succeeded',job.get('error')
    assert verified_rectangle_job(job)
    return job


def rebind_creations(state,sketch_proof):
    old=state.binding
    sketch_before,sketch_after,sketch_def=deepcopy(sketch_proof)
    sketch_job=stage(state,'sketch',sketch_before,sketch_after,sketch_def,'feat_'+'a'*32)
    before=deepcopy(old.creation_result['before']['baseline'])
    after=deepcopy(old.creation_result['after']['state'])
    definition=BlindRectangleExtrusion.validate(**old.creation_result['before']['definition'])
    extrusion_job=stage(state,'extrusion',before,after,definition,old.object_id)
    registry=OwnedRectangleFeatureRegistry(state.ownership.documents,state.store,'epoch')
    state.binding=registry.register(extrusion_job['operation_id'],document_id='target',configuration='Основная',
        result=extrusion_job['result'],receipt=old.receipt)
    state.c.binding=state.binding
    state.ownership=state.leaf.ownership=state.leaf.observations.ownership=registry
    return [sketch_job,extrusion_job]


def parent_report(state,creations,wheel):
    hashes={name:helper._sha(scripts/name) for name in helper.POSITIVE_HELPERS[1:]}
    return dict(scope='installed_rectangle_stages_positive_only',accepted=False,artificial_fixture=True,
        wheel=wheel,package_origin_verified=True,phase='terminal',native_calls_live=False,positive_case_passed=True,
        own_cleanup_verified=True,baseline_restored=True,independent_native_readback_verified=True,owned_documents=[],
        original_baseline=[],restored_baseline=[],original_application=state.application,restored_application=state.application,
        cases=[dict(label=label,passed=True) for label in POSITIVE_LABELS],captures=[dict(status='returned',artificial=True)],
        sketch_job=creations[0],extrusion_job=creations[1],verifier_hashes=hashes,independent_volume_mm3=8000.,
        independent_sketch=creations[1]['result']['before']['baseline']['snapshots']['target'],
        independent_base=creations[1]['result']['after']['state']['snapshots']['target'])


def detached_artifacts(data,private_dir):
    positive_dir=private_dir/'positive';positive_dir.mkdir()
    fault_dir=private_dir/'faults';fault_dir.mkdir()
    positive=deepcopy(data['positive']);row=deepcopy(data['row']);package=deepcopy(data['package'])
    (positive_dir/'jobs.sqlite').write_bytes(data['positive_sql'])
    (fault_dir/'jobs.sqlite').write_bytes(data['fault_sql'])
    write(positive_dir/'report.json',positive['parent_final_report'])
    write(fault_dir/'report.json',row['parent_final_report'])
    positive_path=positive_dir/'leaf-positive-report.json';positive_hash=write(positive_path,positive)
    proof=driver.positive_preflight(positive_path,positive_hash,package['wheel'],scripts)
    row.update(proof)
    fault_path=fault_dir/'leaf-faults-report.json';fault_hash=write(fault_path,row)
    args=NS(state_dir=private_dir/'future_public',wheel=private_dir/'not-opened.whl',expected_version=helper.VERSION,
        expected_git_sha=package['wheel']['git_sha'],positive_report=positive_path,positive_report_sha256=positive_hash,
        faults_report=fault_path,faults_report_sha256=fault_hash)
    return NS(args=args,package=package,row=row,positive=positive,proof=proof,
        fault_path=fault_path,positive_path=positive_path)


@pytest.fixture
def artifacts(faults,sketch_proof,b2_private_dir,request):
    # Build each genuine artificial native mode once. Each hostile scenario
    # receives separate report bytes and SQLite files; no checker is mocked.
    key=request.node.callspec.params['case']
    if key in _ARTIFACTS:return detached_artifacts(_ARTIFACTS[key],b2_private_dir)
    state=faults
    wheel=dict(package_version=helper.VERSION,git_sha='a'*40,wheel_sha256='b'*64,source_digest='c'*64)
    creations=rebind_creations(state,sketch_proof)
    positive_dir=b2_private_dir/'positive';positive_dir.mkdir()
    positive_db=positive_dir/'jobs.sqlite'
    sqlite3.connect(positive_db).close()
    positive_store=state.store
    # Reuse the actual same native-shaped adapter/ownership, and then back up
    # its committed positive journal before the separate controlled fault run.
    args=dict(document_id='target',configuration='Основная',object_id=state.binding.object_id)
    prepared=state.runner.submit('positive_prepare','feature.prepare_leaf_deletion',args,
        lambda:state.leaf.prepare(**args),context=args,mutates=False)
    deletion_args={**args,'expected_revision':prepared['result']['revision']}
    original_members=(list(state.c.features),list(state.c.records),list(state.c.bodies))
    original_rows=[(feature,deepcopy(feature.row)) for feature in state.c.features]
    original_dimensions=[(record,deepcopy(record.summary)) for record in state.c.records]
    original_cache={key:dict(value) for key,value in state.entries[0].features.items()}
    original_geometry=dict(state.entries[0].geometry)
    positive=state.runner.submit('positive_delete','feature.delete_leaf',deletion_args,
        lambda operation_id:state.leaf.delete(operation_id,**deletion_args),context=deletion_args,
        mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
    assert positive['status']=='succeeded',positive.get('error')
    with sqlite3.connect(positive_db) as backup: state.store._db.backup(backup)
    parent=parent_report(state,creations,wheel)
    parent_hash=write(positive_dir/'report.json',parent)
    positive_row=dict(scope='installed_owned_leaf_deletion_positive_only_v1',phase='terminal',artificial_fixture=True,
        positive_case_passed=True,native_calls_live=False,accepted=False,native_b2_accepted=False,public_mcp_accepted=False,
        baseline_restored=True,own_cleanup_verified=True,package_origin_verified=True,wheel=wheel,
        verifier_hashes={name:helper._sha(scripts/name) for name in helper.POSITIVE_HELPERS},
        prepare_job=prepared,delete_job=positive,replay_job=deepcopy(positive),
        parent_final_report=parent,parent_final_report_sha256=parent_hash)
    positive_path=positive_dir/'leaf-positive-report.json';positive_hash=write(positive_path,positive_row)
    proof=driver.positive_preflight(positive_path,positive_hash,wheel,scripts)
    # Reset only this artificial model to its pre-delete fixture state; no
    # native reset/recreation/Undo is executed or exposed by preflight.
    state.deleted=False
    state.c.features,state.c.records,state.c.bodies=original_members
    for feature,row in original_rows: feature.row=deepcopy(row)
    for record,summary in original_dimensions: record.summary=deepcopy(summary)
    state.entries[0].features=original_cache
    state.entries[0].geometry=original_geometry
    # A fresh registry is needed because a successful positive deletion retired
    # only its own binding. This is artificial setup for a separate fault run.
    registry=OwnedRectangleFeatureRegistry(state.ownership.documents,state.store,'epoch')
    state.binding=registry.register(creations[1]['operation_id'],document_id='target',configuration='Основная',
        result=creations[1]['result'],receipt=state.binding.receipt)
    state.c.binding=state.binding;state.ownership=state.leaf.ownership=state.leaf.observations.ownership=registry
    state.bridge_calls.clear();state.native_calls.clear();state.guard_count=state.releases=0
    state.leaf.receipts.clear()
    state.report=dict(native_calls_live=False,original_creation_jobs=creations,cases=[],
        original_creation_receipt_before=driver.receipt_facts(state.binding.receipt))
    state.run()
    fault_dir=b2_private_dir/'faults';fault_dir.mkdir()
    with sqlite3.connect(fault_dir/'jobs.sqlite') as backup: state.store._db.backup(backup)
    fault_parent=parent_report(state,creations,wheel)
    parent_sha=write(fault_dir/'report.json',fault_parent)
    report={**state.report,**proof,**dict(scope='installed_owned_leaf_deletion_faults_only_v1',artificial_fixture=True,
        accepted=False,native_b2_accepted=False,public_mcp_accepted=False,fault_cases_passed=True,phase='terminal',
        baseline_restored=True,own_cleanup_verified=True,reconciled=False,
        unknown_sql_status_after_cleanup='unknown',unknown_sql_phase_after_cleanup='unresolved',
        parent_final_report=fault_parent,parent_final_report_sha256=parent_sha,
        verifier_hashes={name:helper._sha(scripts/name) for name in helper.FAULT_HELPERS})}
    fault_path=fault_dir/'leaf-faults-report.json';fault_hash=write(fault_path,report)
    package=dict(wheel=wheel,package_origin_verified=True,metadata_catalog=dict(public_tool_count=83,
        output_schemas_verified=True,build_matches_installed_wheel=True))
    _ARTIFACTS[key]=dict(package=package,row=report,positive=positive_row,
        positive_sql=positive_db.read_bytes(),fault_sql=(fault_dir/'jobs.sqlite').read_bytes())
    # This first scenario can reuse its own files; following scenarios receive
    # independent detached copies, keeping SQL tampering isolated.
    args=NS(state_dir=b2_private_dir/'future_public',wheel=b2_private_dir/'not-opened.whl',expected_version=helper.VERSION,
        expected_git_sha=wheel['git_sha'],positive_report=positive_path,positive_report_sha256=positive_hash,
        faults_report=fault_path,faults_report_sha256=fault_hash)
    return NS(args=args,package=package,row=report,positive=positive_row,proof=proof,
        fault_path=fault_path,positive_path=positive_path)


def test_passive_actual_positive_and_faults_reports_and_readonly_sql_gate_only_prerequisites(artifacts):
    x=artifacts
    journal=x.fault_path.with_name('jobs.sqlite');unchanged=helper._sha(journal)
    result=helper.preflight(x.args,package_provider=lambda *args,**kwargs:x.package)
    assert result['prerequisite_gate_verified'] is True and result['metadata_mutation_count']==27
    assert result['accepted'] is result['native_b2_accepted'] is result['public_mcp_accepted'] is False
    assert result['faults_preflight']['unknown_remains_unresolved'] is True
    assert result['open_gates']==['B2-N5-dependent-linked-impact']
    assert helper._sha(journal)==unchanged
    rows=helper.read_journal(journal)
    assert next(job for job in rows if job['operation_id']==x.row['unknown_job_retained']['operation_id'])['status']=='unknown'


def test_public_preflight_outside_work_rejects_before_package_or_native(artifacts,b2_outside_dir):
    x=artifacts;x.args.state_dir=b2_outside_dir/'outside_public';calls=[]
    def provider(*args,**kwargs):calls.append('package');pytest.fail('Outside work must refuse before package/native imports')
    with pytest.raises(ValueError,match='Fresh private public state'):
        helper.preflight(x.args,package_provider=provider)
    assert calls==[] and not x.args.state_dir.exists()


@pytest.mark.parametrize('fault',['hash','wheel','phase','manifest_missing','manifest_extra','cleanup','parent',
    'cases','unknown_claim','physical_pending','full_delta','receipt','unknown_reconciled_sql','blocked_sql',
    'preparation_revision','preparation_scope','preparation_pid','preparation_extra','prewrite_extra_dto',
    'prewrite_synthetic_false','unknown_old_pid_boolean','unknown_guard_foreign_to_sql'])
def test_fault_report_sha_schema_parent_full_effect_and_actual_sql_must_all_match(artifacts,fault):
    x=artifacts
    row=x.row
    if fault=='hash': x.args.faults_report_sha256='0'*64
    elif fault=='wheel': row['wheel']={**row['wheel'],'wheel_sha256':'0'*64}
    elif fault=='phase': row['phase']='leaf_observation_unknown'
    elif fault=='manifest_missing': row['verifier_hashes'].pop(helper.FAULT_HELPERS[0])
    elif fault=='manifest_extra': row['verifier_hashes']['foreign.py']='0'*64
    elif fault=='cleanup': row['own_cleanup_verified']=False
    elif fault=='parent': row['parent_final_report']['restored_application']={}
    elif fault=='cases': row['cases'].pop()
    elif fault=='unknown_claim': row['unknown_sql_status_after_cleanup']='succeeded'
    elif fault=='physical_pending': row['unknown_quiescence']['native_action']['pending_native_step']='rebuild'
    elif fault=='full_delta': row['unknown_quiescence']['second_full_current']['snapshots']['target']['clone_state']['sketch']['points'][0]['coordinates_si'][0]=(.1).hex()
    elif fault=='receipt': row['original_creation_receipt_after']['flags']['restored']=True
    elif fault=='preparation_revision':row['initial_preparation']['revision']='rev_foreign'
    elif fault=='preparation_scope':row['initial_preparation']['creation_operation_id']='job_foreign'
    elif fault=='preparation_pid':row['initial_preparation']['feature_pid_hex']='deadbeef'
    elif fault=='preparation_extra':row['initial_preparation']['invented']=None
    elif fault=='prewrite_extra_dto':row['leaf_stale']['invented']=None
    elif fault=='prewrite_synthetic_false':row['leaf_stale']['mutation']=None
    elif fault=='unknown_old_pid_boolean':row['unknown_quiescence']['old_feature_pid']['state']=True
    elif fault=='unknown_guard_foreign_to_sql':
        row['unknown_quiescence']['native_guards'][0]['baseline_document_ids'].reverse()
    else:
        with sqlite3.connect(x.fault_path.with_name('jobs.sqlite')) as db:
            if fault=='unknown_reconciled_sql':
                db.execute("UPDATE mutations SET phase='reconciled',reconciliation='{}' WHERE operation_id=?",
                           (row['unknown_job_retained']['operation_id'],))
            else: db.execute("UPDATE jobs SET status='succeeded' WHERE operation_id=?",(row['leaf_unknown_new_request_blocked']['operation_id'],))
    if fault not in ('hash','unknown_reconciled_sql','blocked_sql'):
        x.args.faults_report_sha256=write(x.fault_path,row)
    def forbidden_provider(*args,**kwargs):pytest.fail('Invalid artifact must reject before package/native imports')
    with pytest.raises(ValueError): helper.preflight(x.args,package_provider=forbidden_provider)


@pytest.mark.parametrize('fault',['version','historical_version','boolean_version','count','boolean_count','schemas','origin','wheel','git','previous_journal',
                                'previous_metadata','positive_sha','positive_helpers'])
def test_exact_installed_metadata_and_fresh_private_session_are_required(artifacts,fault):
    x=artifacts;calls=[]
    if fault=='version':x.args.expected_version='2.0.0.dev95'
    elif fault=='historical_version':x.args.expected_version='2.0.0.dev96'
    elif fault=='boolean_version':x.args.expected_version=True
    elif fault=='count':x.package['metadata_catalog']['public_tool_count']=82
    elif fault=='boolean_count':x.package['metadata_catalog']['public_tool_count']=True
    elif fault=='schemas':x.package['metadata_catalog']['output_schemas_verified']=False
    elif fault=='origin':x.package['package_origin_verified']=False
    elif fault=='wheel':x.package['wheel']['wheel_sha256']='0'*64
    elif fault=='git':x.args.expected_git_sha='f'*40
    elif fault in ('previous_journal','previous_metadata'):
        x.args.state_dir.mkdir()
        if fault=='previous_journal':(x.args.state_dir/'jobs.sqlite').write_bytes(b'old')
        else:(x.args.state_dir/'metadata-state').mkdir()
    elif fault=='positive_sha':x.args.positive_report_sha256='0'*64
    else:
        x.positive['verifier_hashes'].pop(helper.POSITIVE_HELPERS[0])
        x.args.positive_report_sha256=write(x.positive_path,x.positive)
    def provider(args,*,installed):
        calls.append(installed);return x.package
    with pytest.raises(ValueError):helper.preflight(x.args,package_provider=provider)
    assert calls==([True] if fault in ('count','boolean_count','schemas','origin','wheel') else [])
