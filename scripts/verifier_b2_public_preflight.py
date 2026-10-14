"""Passive exact-candidate prerequisites for future public B2; no CAD/reconciliation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from solidworks_mcp.owned_leaf_deletion_postconditions import verified_owned_leaf_deletion
from verifier_b2_public_contract import durable_b2_job
from verifier_lifecycle import read_journal


SCOPE='b2_public_prerequisite_preflight_v1'
VERSION='2.0.0.dev97'
SUPPORTED_VERSIONS=frozenset(('2.0.0.dev96',VERSION))
POSITIVE_HELPERS=('verify_owned_leaf_deletion_positive.py','verify_rectangle_stages_positive.py',
    'verifier_rectangle_stages.py','probe_native_first_save_domain.py','verify_installed_metadata.py',
    'verify_wheel_artifact.py','verify_bounds_measurements.py','verify_export_operations.py',
    'verify_native_document_open.py','verify_native_first_save_rejections.py','verifier_dimension_diagnostics.py')
FAULT_HELPERS=('verify_owned_leaf_deletion_faults.py','verify_owned_leaf_deletion_positive.py',
    'verifier_b2_observation_fault.py','verifier_b2_public_contract.py','verifier_rectangle_positive_acceptance.py',
    'verifier_lifecycle.py','verifier_rectangle_public_contract.py','verifier_first_save_public_contract.py',
    'verifier_native_open.py','verifier_native_part_activation.py','verifier_native_first_save.py',
    'verifier_rectangle_restoration.py',*POSITIVE_HELPERS[1:])
FAULT_CASES=('leaf_stale','leaf_foreign','leaf_no_effect','leaf_observation_unknown','leaf_unknown_new_request_blocked')


def _require(condition,message):
    if not condition: raise ValueError(message)


def _same(left,right):
    return _json(left)==_json(right)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _private(path):
    value=Path(path).resolve(strict=True)
    _require(value.is_relative_to((Path.cwd()/'work').resolve()),'Prerequisite reports must stay in private work/.')
    _require(value.is_file(),'An actual prerequisite report file is required.')
    return value


def _report(path,expected_hash):
    path=_private(path)
    _require(type(expected_hash) is str and len(expected_hash)==64 and _sha(path)==expected_hash,
             'Actual prerequisite report SHA256 mismatch.')
    row=json.loads(path.read_text(encoding='utf8'))
    _json(row)
    _require(type(row) is dict,'Actual complete report object required.')
    return path,row


def _manifest(row,names,scripts):
    value=row['verifier_hashes']
    _require(type(value) is dict and set(value)==set(names),'Fixed helper manifest has omissions/additions.')
    for name in names:
        _require(_sha(Path(scripts)/name)==value[name],'Current fixed helper SHA changed: '+name)
    return deepcopy(value)


def _driver():
    # Import only its passive functions; no CLI, native driver, COM or cleanup.
    import verify_owned_leaf_deletion_faults
    return verify_owned_leaf_deletion_faults


def _parent(path,row,wheel,hashes):
    parent_path=path.with_name('report.json')
    _require(_sha(parent_path)==row['parent_final_report_sha256'],'Actual parent report SHA mismatch.')
    parent=json.loads(parent_path.read_text(encoding='utf8'))
    _require(_same(parent,row['parent_final_report']),'Embedded parent differs from actual report.')
    _require(parent['phase']=='terminal' and parent['native_calls_live'] is False
        and parent['positive_case_passed'] is True and parent['baseline_restored'] is True
        and parent['own_cleanup_verified'] is True and parent['owned_documents']==[]
        and parent.get('retained_process',False) is False
        and _same(parent['wheel'],wheel)
        and _same(parent['original_baseline'],parent['restored_baseline'])
        and _same(parent['original_application'],parent['restored_application']),
        'Actual complete parent cleanup/original baseline is unconfirmed.')
    _require(set(parent['verifier_hashes'])==set(POSITIVE_HELPERS[1:])
        and parent['verifier_hashes']=={name:hashes[name] for name in POSITIVE_HELPERS[1:]},
        'Fixed complete parent helper manifest required.')
    from verifier_rectangle_positive_acceptance import validate_positive_report
    validate_positive_report(parent,wheel,parent['verifier_hashes'])
    return parent


def _job(rows,dto,*,prewrite_refusal=False):
    _require(type(dto) is dict and dto['operation_id'] in rows,'Actual coherent SQL job missing.')
    persisted=rows[dto['operation_id']]
    if prewrite_refusal:
        # read_journal annotates every absent mutation row with None, including
        # failed mutation admissions. These three finite before-write refusals
        # have no checkpoint; committed/rolled-back/unknown jobs never enter here.
        _require(persisted['status']=='failed' and persisted['result'] is None
            and type(persisted['error']) is dict and persisted['payload']['mutates'] is True
            and 'mutation' not in dto and persisted.get('mutation') is None,
            'Exact failed before-write SQL row without a mutation checkpoint required.')
        digest=hashlib.sha256((persisted['operation']+'\n'+_json(persisted['payload'])).encode('utf8')).hexdigest()
        _require(persisted['digest']==digest,'Actual failed before-write request digest differs.')
        published={key:value for key,value in persisted.items() if key not in ('digest','mutation')}
        _require(_same(published,dto),'Exact whole failed admission DTO differs from actual SQL.')
        return deepcopy(persisted)
    return durable_b2_job(dto,persisted)


def _scope(job,label,context):
    args=job['payload']['arguments']
    _require(job['request_id']==label and job['operation']=='feature.delete_leaf'
        and job['payload']['mutates'] is True and job['error'] is not None
        and set(args)=={'document_id','configuration','object_id','expected_revision'}
        and _same(job['payload']['context'],args)
        and args['document_id']==context['document_id'] and args['configuration']==context['configuration'],
        'Finite fault job request/operation/context differs.')
    return args


def _preparation(prepared,creation):
    fields={'scope','connection_epoch','document_id','configuration','object_id',
        'creation_operation_id','feature_native_id','feature_pid_hex','current_definition','baseline',
        'expected_after_profile','expected_solid_body_count','application_command_in_progress','preview'}
    extras={'revision','revision_scope','delete_authorized','native_execution_available'}
    _require(type(prepared) is dict and set(prepared)==fields|extras,
             'Complete exact current leaf preparation schema required.')
    _require(prepared['scope']==prepared['revision_scope']=='owned_rectangular_leaf_extrusion_deletion_v1'
        and prepared['creation_operation_id']==creation['operation_id']
        and prepared['connection_epoch']==creation['mutation']['connection_epoch']
        and prepared['object_id']==creation['result']['value']['feature_object_id']
        and prepared['document_id']==creation['payload']['arguments']['document_id']
        and prepared['configuration']==creation['payload']['arguments']['configuration']
        and type(prepared['feature_native_id']) is int
        and prepared['feature_native_id']==creation['result']['value']['created_native_id']
        and prepared['application_command_in_progress'] is False and prepared['delete_authorized'] is False
        and prepared['native_execution_available'] is True
        and prepared['expected_after_profile']=='closed_rectangular_sketch_v1'
        and type(prepared['expected_solid_body_count']) is int and prepared['expected_solid_body_count']==0,
        'Current preparation must bind the exact original creation/epoch/native feature.')
    payload={key:prepared[key] for key in fields}
    _require(prepared['revision']=='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest(),
             'Actual complete preparation revision digest differs.')
    definition=BlindRectangleExtrusion.validate(**prepared['current_definition'])
    _require(_same(prepared['preview'],dict(deleted_feature_object_ids=[prepared['object_id']],
        preserved_sketch_object_id=definition.sketch_object_id,remaining_dimension_roles=['dimension:width','dimension:height'],
        expected_solid_body_count=0,geometry_references_require_refresh=True)),
        'Exact finite leaf deletion preview required.')
    for state in (prepared['baseline'],creation['result']['after']['state']):
        snapshot=state['snapshots'][prepared['document_id']]
        _require(snapshot['configuration']==prepared['configuration'] and snapshot['configurations']==[prepared['configuration']],
                 'Exact one-configuration current and creation target required.')
        features=snapshot['clone_state']['features']
        index=next(index for index,feature in enumerate(features) if feature['native_id']==prepared['feature_native_id'])
        pid=next(reference['token'] for reference in snapshot['references']
                 if reference['kind']=='feature' and reference['role']=='feature:'+str(index))
        _require(pid==prepared['feature_pid_hex'] and bytes.fromhex(pid).hex()==pid,
                 'Current preparation PID must remain the exact original feature PID.')
    return {key:prepared[key] for key in ('scope','baseline','feature_native_id','feature_pid_hex','object_id','current_definition')}


def _checkpoint(job,prepared,checkpoint):
    mutation=job['mutation']
    _require(mutation['document_id']==prepared['document_id'] and mutation['configuration']==prepared['configuration']
        and mutation['connection_epoch']==prepared['connection_epoch']
        and mutation['expected_revision']==prepared['revision']
        and job['payload']['arguments']['expected_revision']==prepared['revision']
        and job['payload']['arguments']['object_id']==prepared['object_id']
        and _same(mutation['before_state'],dict(**checkpoint,_mutation_effect_scope='application')),
        'Actual fault checkpoint must exactly project the complete initial preparation/revision.')


def _guard_ledger(job,natives):
    steps=_driver().paired_steps(job)
    _require(steps[0]['name']=='leaf_execution_guard' and len(natives)==1,
             'One normally completed own execution guard required.')
    release=[step['evidence'] for step in steps
             if step['name']=='leaf_guard_release' and step['phase']=='returned']
    _require(_same(release,natives),'Actual released native guard differs from its durable acknowledgement.')
    return steps


def fault_preflight(path,expected_hash,wheel,scripts,positive_proof):
    """Inspect terminal finite fault artifact and SQLite in mode=ro only.

Unknown remains unknown/unresolved with reconciliation=None and an application
hold. Verified physical own cleanup does not reconcile its historical job.
"""
    path,row=_report(path,expected_hash)
    _require(row['scope']=='installed_owned_leaf_deletion_faults_only_v1' and row['phase']=='terminal'
        and row['fault_cases_passed'] is True and row['native_calls_live'] is False
        and row['accepted'] is False and row['native_b2_accepted'] is False and row['public_mcp_accepted'] is False
        and row.get('parent_retained_sta_required',False) is False and row['baseline_restored'] is True
        and row['own_cleanup_verified'] is True and row['reconciled'] is False and _same(row['wheel'],wheel)
        and row['unknown_sql_status_after_cleanup']=='unknown' and row['unknown_sql_phase_after_cleanup']=='unresolved',
        'Terminal same-wheel finite faults prerequisite required, never whole acceptance.')
    hashes=_manifest(row,FAULT_HELPERS,scripts)
    _require(row['positive_report_gate_verified'] is True
        and row['positive_report_sha256']==positive_proof['positive_report_sha256']
        and Path(row['positive_report_path']).resolve()==Path(positive_proof['positive_report_path']).resolve()
        and row['positive_helper_hashes']==positive_proof['positive_helper_hashes'],
        'Faults must reference the exact actual positive prerequisite.')
    _require(type(row['cases']) is list and [case['label'] for case in row['cases']]==list(FAULT_CASES)
        and all(set(case)=={'label','passed'} and case['passed'] is True for case in row['cases']),
        'Exact five finite fault cases required.')
    parent=_parent(path,row,wheel,hashes)
    journal=read_journal(path.with_name('jobs.sqlite'))
    rows={job['operation_id']:job for job in journal}
    _require(len(rows)==len(journal),'Duplicate operation IDs in coherent journal.')
    originals=row['original_creation_jobs']
    _require(type(originals) is list and len(originals)==2
        and _same(originals,[parent['sketch_job'],parent['extrusion_job']])
        and row['original_creation_jobs_unchanged'] is True
        and _same(row['original_creation_receipt_before'],row['original_creation_receipt_after']),
        'Original succeeded B1 history/receipt must survive all finite faults.')
    for original in originals: _job(rows,original)
    prepared=row['initial_preparation']
    checkpoint=_preparation(prepared,originals[1])
    context={key:prepared[key] for key in ('document_id','configuration','object_id')}
    cases={label:_job(rows,row[label],prewrite_refusal=label in
        ('leaf_stale','leaf_foreign','leaf_unknown_new_request_blocked')) for label in FAULT_CASES}
    for label in FAULT_CASES[:2]:
        job=cases[label];args=_scope(job,label,context)
        _require(job['status']=='failed' and job.get('mutation') is None,'Prewrite refusal must have no checkpoint.')
        _require(_same(row[label],row[label+'_replay']),'Failed replay changed the original job.')
        if label=='leaf_stale':
            _require(args['object_id']==context['object_id'] and args['expected_revision']=='rev_stale'
                and job['error']['code']=='stale_revision','Exact stale prewrite refusal required.')
        else:
            _require(args['object_id']!=context['object_id'] and args['expected_revision']==prepared['revision'],
                     'Exact foreign owned-object prewrite refusal required.')
    driver=_driver()
    no_effect=cases['leaf_no_effect'];_scope(no_effect,'leaf_no_effect',context)
    _checkpoint(no_effect,prepared,checkpoint)
    mutation=no_effect['mutation'];verification=mutation['verification']
    after=verification['evidence']['after'];guard=verification['evidence']['execution_guard']
    _require(no_effect['status']=='failed' and mutation['phase']=='rolled_back' and verification['outcome']=='rolled_back'
        and mutation['reconciliation'] is None and after['pending'] is False and after['guard_released'] is True
        and _same(after['state'],mutation['before_state']['baseline'])
        and guard['guard_released'] is True and guard['pending_release'] is False and guard['journal_failed'] is False
        and guard['full_release_check']=='no_effect' and _same(row['leaf_no_effect'],row['leaf_no_effect_replay']),
        'Actual known no-effect rollback/replay requires complete released unchanged state.')
    ids=[item['document_id'] for item in mutation['before_state']['baseline']['semantic']['documents']]
    for native in guard['native_guards']: driver.released_native_guard(native,ids)
    _require(len(guard['native_guards'])==1,'Exactly one no-effect execution guard required.')
    _guard_ledger(no_effect,guard['native_guards'])
    facts=row['no_effect_hook']
    _require(facts['scope']=='owned_leaf_controlled_python_no_effect_v1'
        and all(type(facts[key]) is int and facts[key]==1 for key in ('injected_faults','bridge_dispatches','bridge_attempts'))
        and type(facts['normal_bridge_returns']) is int and facts['normal_bridge_returns']==0
        and facts['pending_bridge'] is False and facts['pending_snapshot'] is False and facts['detached'] is True
        and facts['fault_before_native_bridge'] is True,'Actual detached Python no-effect hook required.')
    unknown=cases['leaf_observation_unknown'];args=_scope(unknown,'leaf_observation_unknown',context)
    _checkpoint(unknown,prepared,checkpoint)
    mutation=unknown['mutation'];before=mutation['before_state']
    _require(unknown['status']=='unknown' and unknown['result'] is None and mutation['phase']=='unresolved'
        and mutation['reconciliation'] is None and mutation['before_state']['_mutation_effect_scope']=='application'
        and mutation['verification']['outcome'] is None and mutation['verification']['evidence']=={}
        and _same(row['leaf_observation_unknown'],row['leaf_observation_unknown_replay'])
        and _same(row['unknown_job_retained'],row['leaf_observation_unknown'])
        and args['object_id']==context['object_id'],'Actual historical unknown application hold must remain unchanged.')
    driver.paired_steps(unknown)
    q=row['unknown_quiescence'];native=q['native_action'];hook=q['fault_hook']
    _require(q['full_delta_verified'] is True and q['reconciliation_authorized'] is False
        and q['cleanup_scope']=='only_original_owned_test_documents'
        and _same(q['first_full_current'],q['second_full_current'])
        and _same(q['native_steps'],mutation['verification']['native_steps'])
        and _same(q['second_full_current']['snapshots'][context['document_id']],hook['actual_after_snapshot'])
        and _same(row['physical_bridge_calls'],[dict(attempted=True,returned=True)]),
        'One normally completed bridge/full independent current effect is required.')
    _require(native['attempted'] is True and native['bridge_returned'] is True
        and native['bridge_exception_returned'] is False and native['deletion_attempted'] is True
        and native['deletion_bridge_verified'] is True and native['pending_apply'] is False
        and native['pending_native_step'] is None and native['journal_failed'] is False
        and native['selection_uncertain'] is False and native['view_state_uncertain'] is False,
        'No pending native/receipt flags may authorize own cleanup.')
    _require(hook['scope']=='owned_leaf_controlled_python_observation_fault_v1'
        and all(type(hook[key]) is int and hook[key]==1 for key in
            ('normal_bridge_returns','bridge_attempts','bridge_dispatches','injected_faults'))
        and all(hook[key] is False for key in ('pending_bridge','pending_snapshot','armed',
            'bridge_exception_returned','snapshot_exception_returned','native_acceptance','cleanup_authorized','reconciliation_authorized')),
        'Exactly one controlled Python fault after normal native completion required.')
    ids=[item['document_id'] for item in before['baseline']['semantic']['documents']]
    _require(len(q['native_guards'])==1,'Exactly one normally released unknown execution guard required.')
    for native in q['native_guards']: driver.released_native_guard(native,ids)
    _guard_ledger(unknown,q['native_guards'])
    definition=BlindRectangleExtrusion.validate(**before['current_definition'])
    _require(verified_owned_leaf_deletion(before['baseline'],q['second_full_current'],**context,
        feature_native_id=before['feature_native_id'],feature_pid_hex=before['feature_pid_hex'],current_definition=definition),
        'Actual complete production BASE→SKETCH effect is unconfirmed.')
    old=q['old_feature_pid']
    _require(type(old['state']) is int and old['state'] in (1,4) and old['object_is_null'] is True,
             'Normally returned old PID invalid/deleted state and null object required.')
    sketch_id=before['baseline']['snapshots'][context['document_id']]['clone_state']['sketch']['feature_native_id']
    snapshot=before['baseline']['snapshots'][context['document_id']]
    index=next(index for index,item in enumerate(snapshot['clone_state']['features']) if item['native_id']==sketch_id)
    pid=next(item['token'] for item in snapshot['references'] if item['kind']=='feature' and item['role']=='feature:'+str(index))
    _require(q['original_sketch_pid_hex']==pid,'Original borrowed sketch PID must match the actual checkpoint.')
    blocked=cases['leaf_unknown_new_request_blocked'];blocked_args=_scope(blocked,'leaf_unknown_new_request_blocked',context)
    _require(blocked['status']=='failed' and blocked.get('mutation') is None
        and blocked['error']['code']=='document_mutation_blocked' and _same(blocked_args,args),
        'Actual new request must remain blocked without a checkpoint/dispatch.')
    unresolved=[job['mutation'] for job in journal if job.get('mutation')
                and job['mutation']['phase'] in ('prepared','unresolved')]
    _require(len(unresolved)==1 and _same(unresolved[0],mutation)
        and _same(row['unresolved_hold_before_cleanup'],unresolved),
        'Actual coherent SQL application hold differs or was reconciled.')
    return dict(scope='b2_leaf_faults_prerequisite_v1',fault_report_sha256=expected_hash,
        fault_report_path=str(path),fault_report_gate_verified=True,verified_cases=list(FAULT_CASES),
        unknown_operation_id=unknown['operation_id'],unknown_remains_unresolved=True,
        accepted=False,native_b2_accepted=False,public_mcp_accepted=False)


def preflight(args,*,package_provider=None):
    """Metadata83/27/exact wheel + actual positive/finite faults before native setup."""
    _require(type(args.expected_version) is str and args.expected_version in SUPPORTED_VERSIONS,
             'Public B2 prerequisite requires an explicitly supported candidate version.')
    positive_path,positive_row=_report(args.positive_report,args.positive_report_sha256)
    faults_path,_=_report(args.faults_report,args.faults_report_sha256)
    state=Path(args.state_dir).resolve()
    _require(state.is_relative_to((Path.cwd()/'work').resolve())
        and not (state/'jobs.sqlite').exists() and not (state/'metadata-state').exists(),
        'Fresh private public state without a previous journal/metadata session required.')
    wheel=positive_row['wheel']
    _require(wheel['package_version']==args.expected_version and wheel['git_sha']==args.expected_git_sha,
             'Prerequisite reports must bind the requested exact candidate version/build.')
    scripts=Path(__file__).resolve().parent
    positive=_driver().positive_preflight(positive_path,args.positive_report_sha256,wheel,scripts)
    _require(positive['positive_report_gate_verified'] is True,'Actual positive preflight failed.')
    faults=fault_preflight(faults_path,args.faults_report_sha256,wheel,scripts,positive)
    if package_provider is None:
        from probe_native_first_save_domain import package_evidence
        package_provider=package_evidence
    package=package_provider(args,installed=True)
    catalog=package['metadata_catalog']
    _require(package['package_origin_verified'] is True and _same(package['wheel'],wheel)
        and catalog['public_tool_count']==83
        and type(catalog['public_tool_count']) is int and catalog['output_schemas_verified'] is True
        and catalog['build_matches_installed_wheel'] is True,
        'Exact installed candidate metadata83/current-wheel evidence required.')
    # Existing installed metadata verifier checks the exact 27 implemented
    # mutation names; its returned catalog has no invented mutation_count key.
    return dict(**package,scope=SCOPE,positive_preflight=positive,faults_preflight=faults,
        prerequisite_gate_verified=True,metadata_mutation_count=27,accepted=False,
        native_b2_accepted=False,public_mcp_accepted=False,open_gates=['B2-N5-dependent-linked-impact'])
