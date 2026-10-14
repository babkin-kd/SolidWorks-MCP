"""Passive finite B2 public contracts and detached journal evidence, no CAD.

Scalar 10→12/9600 and Russian rename keep separate validator callbacks supplied
by the native owner. Job reads use the lifecycle supervisor's DIRECT_QUERIES.
These observations never declare native B2/wheel acceptance or authorize cleanup.
"""
from copy import deepcopy
import hashlib
import re

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from solidworks_mcp.owned_suppression_postconditions import verified_owned_suppression, verified_owned_return
from solidworks_mcp.owned_leaf_deletion_postconditions import verified_owned_leaf_deletion
from verifier_lifecycle import ToolSpec, CONTEXT_KEYS
from verifier_rectangle_public_contract import SPECS as B1_SPECS
from verifier_first_save_public_contract import SPECS as DIMENSION_SPECS
from verifier_rectangle_stages import released_rectangle_guard


SCOPE='b2_public_contract_candidate_v1'
SUPPRESSION_SCOPE='owned_rectangular_blind_base_suppression_v1'
LEAF_SCOPE='owned_rectangular_leaf_extrusion_deletion_v1'
SPECS={**B1_SPECS,**{name:DIMENSION_SPECS[name] for name in
    ('dimension_list','dimension_get','dimension_set_value')},
    'feature_rename':ToolSpec('feature.rename',True,prewrite_failure_codes=frozenset({'stale_revision'})),
    'feature_prepare_suppression':ToolSpec('feature.prepare_suppression',False),
    'feature_set_suppressed':ToolSpec('feature.set_suppressed',True,prewrite_failure_codes=frozenset({'stale_revision'})),
    'feature_prepare_leaf_deletion':ToolSpec('feature.prepare_leaf_deletion',False),
    'feature_delete_leaf':ToolSpec('feature.delete_leaf',True,prewrite_failure_codes=frozenset({'stale_revision'})),
}


def _require(condition):
    if not condition: raise ValueError('Incomplete or mismatched detached B2 evidence.')


def _digest(operation,payload):
    return hashlib.sha256((operation+'\n'+_json(payload)).encode('utf8')).hexdigest()


def _durable(row):
    _json(row)
    _require(type(row) is dict and type(row['operation_id']) is str and bool(row['operation_id'])
        and type(row['request_id']) is str and bool(row['request_id'])
        and row['digest']==_digest(row['operation'],row['payload'])
        and row['status']=='succeeded' and row['error'] is None)
    payload=row['payload']
    _require(type(payload) is dict and set(payload)=={'arguments','context','mutates'}
        and type(payload['arguments']) is dict and type(payload['context']) is dict
        and type(payload['mutates']) is bool)
    args=payload['arguments']
    _require(_json(payload['context'])==_json({key:args[key] for key in CONTEXT_KEYS if key in args}))
    _require(all(type(args[key]) is str and bool(args[key].strip()) for key in
        ('document_id','configuration','object_id'))
        and re.fullmatch(r'feat_[0-9a-f]{32}',args['object_id']) is not None)
    return args


def durable_b2_job(public_dto,persisted):
    """Bind every published field to one independently read coherent SQL row.

    JobStore DTO deliberately omits digest. read_journal additionally annotates
    read rows with synthetic mutation=None; recognize precisely that derived
    absent-checkpoint annotation, never drop any actual SQL/DTO column.
The owner obtains the persisted row through supervisor/read_journal mode=ro.
"""
    _require(persisted['digest']==_digest(persisted['operation'],persisted['payload']))
    published={key:value for key,value in persisted.items() if key!='digest'}
    if ('mutation' not in public_dto and published.get('mutation') is None
            and published['payload']['mutates'] is False):
        published.pop('mutation',None)
    _require(_json(published)==_json(public_dto))
    return deepcopy(persisted)


def _preparation(row):
    args=_durable(row)
    operation=row['operation']
    suppression=operation=='feature.prepare_suppression'
    _require(suppression or operation=='feature.prepare_leaf_deletion')
    _require(row['payload']['mutates'] is False and row.get('mutation') is None)
    _require(set(args)==({'document_id','configuration','object_id','suppressed'} if suppression
                         else {'document_id','configuration','object_id'}))
    prepared=row['result']
    fields=({'scope','connection_epoch','document_id','configuration','object_id','suppressed',
        'original_suppressed','feature_pid_hex','creation_operation_id','original_suppression_operation_id','baseline'}
        if suppression else {'scope','connection_epoch','document_id','configuration','object_id',
        'creation_operation_id','feature_native_id','feature_pid_hex','current_definition','baseline',
        'expected_after_profile','expected_solid_body_count','application_command_in_progress','preview'})
    extras=({'revision','revision_scope','expected_solid_body_count'} if suppression
            else {'revision','revision_scope','delete_authorized','native_execution_available'})
    _require(type(prepared) is dict and set(prepared)==fields|extras)
    _require(prepared['scope']==prepared['revision_scope']==(SUPPRESSION_SCOPE if suppression else LEAF_SCOPE)
        and all(prepared[key]==args[key] for key in ('document_id','configuration','object_id'))
        and type(prepared['connection_epoch']) is str and bool(prepared['connection_epoch'])
        and type(prepared['creation_operation_id']) is str and bool(prepared['creation_operation_id']))
    pid=bytes.fromhex(prepared['feature_pid_hex'])
    _require(bool(pid) and pid.hex()==prepared['feature_pid_hex'])
    payload={key:prepared[key] for key in fields}
    _require(prepared['revision']=='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest())
    ids=[row['document_id'] for row in prepared['baseline']['semantic']['documents']]
    _require(0<len(ids)<=32 and all(type(value) is str and bool(value) for value in ids)
        and len(set(ids))==len(ids) and args['document_id'] in ids
        and set(prepared['baseline']['snapshots'])==set(ids))
    snapshot=prepared['baseline']['snapshots'][args['document_id']]
    _require(snapshot['configuration']==args['configuration'] and snapshot['configurations']==[args['configuration']])
    if suppression:
        _require(type(args['suppressed']) is bool and prepared['suppressed'] is args['suppressed']
            and prepared['original_suppressed'] is not args['suppressed']
            and type(prepared['original_suppressed']) is bool
            and type(prepared['expected_solid_body_count']) is int
            and prepared['expected_solid_body_count']==(0 if args['suppressed'] else 1))
        ancestor=prepared['original_suppression_operation_id']
        _require(ancestor is None if args['suppressed'] else type(ancestor) is str and bool(ancestor))
    else:
        definition=BlindRectangleExtrusion.validate(**prepared['current_definition'])
        _require(type(prepared['feature_native_id']) is int
            and prepared['expected_after_profile']=='closed_rectangular_sketch_v1'
            and type(prepared['expected_solid_body_count']) is int and prepared['expected_solid_body_count']==0
            and prepared['application_command_in_progress'] is False and prepared['delete_authorized'] is False
            and type(prepared['native_execution_available']) is bool
            and _json(prepared['preview'])==_json(dict(deleted_feature_object_ids=[args['object_id']],
                preserved_sketch_object_id=definition.sketch_object_id,remaining_dimension_roles=['dimension:width','dimension:height'],
                expected_solid_body_count=0,geometry_references_require_refresh=True)))
    return prepared


def _native_id(state,document_id,pid):
    snapshot=state['snapshots'][document_id]
    matches=[]
    for index,feature in enumerate(snapshot['clone_state']['features']):
        if any(row['kind']=='feature' and row['role']=='feature:'+str(index) and row['token']==pid
               for row in snapshot['references']): matches.append(feature['native_id'])
    _require(len(matches)==1 and type(matches[0]) is int)
    return matches[0]


def _guard(guard,ids,scope,mode,count):
    _require(type(guard) is dict and set(guard)=={'scope','native_guards','guard_released',
        'pending_release','journal_failed','full_release_check'}
        and guard['scope']==scope and guard['guard_released'] is True
        and guard['pending_release'] is False and guard['journal_failed'] is False
        and guard['full_release_check']==mode and type(guard['native_guards']) is list
        and len(guard['native_guards'])==count)
    for native in guard['native_guards']:
        _require(_json(native['activation_ui_release'])==_json(dict(attempted=False,verified=False)))
        _require(released_rectangle_guard(dict(scope='rectangle_construction_guard_v1',
            native_guards=[native],guard_released=True,pending_release=False,journal_failed=False,
            reference_binding_unconfirmed=False,full_release_check='effect'),ids))


def _pairs(steps,prefix,after):
    _require(type(steps) is list and 10<=len(steps)<=32 and len(steps)%2==0)
    pairs={}
    for index in range(0,len(steps),2):
        first,last=steps[index:index+2]
        _require(set(first)==set(last)=={'sequence','name','phase','evidence'}
            and type(first['sequence']) is int and first['sequence']==index+1
            and type(last['sequence']) is int and last['sequence']==index+2
            and first['phase']=='pending' and last['phase']=='returned' and first['name']==last['name']
            and type(first['name']) is str and first['name'].startswith(prefix)
            and first['name'] not in pairs and type(first['evidence']) is dict and type(last['evidence']) is dict)
        pairs[first['name']]=(first['evidence'],last['evidence'])
    _require(steps[0]['name']==prefix+'execution_guard' and steps[-1]['name']==prefix+'released_check')
    last=steps[-1]['evidence']
    _require(set(last)=={'verified','observed'} and last['verified'] is True and _json(last['observed'])==_json(after))
    return pairs


def _guard_steps(pairs,ids,guard,prefix):
    starts=[prefix+'execution_guard']+([prefix+'body_name_guard'] if len(guard['native_guards'])==2 else [])
    releases=([prefix+'guard_release_'+str(index+1) for index in range(len(starts))]
              if prefix=='suppression_' else ['leaf_guard_release'])
    for start,release,native in zip(starts,releases,guard['native_guards']):
        for pending in (pairs[start][0],pairs[release][0]):
            _require(set(pending)=={'document_ids'} and type(pending['document_ids']) is list
                and len(pending['document_ids'])==len(ids) and set(pending['document_ids'])==set(ids))
        acquired=pairs[start][1]
        _require(acquired['scope']==native['scope'] and acquired['acquired'] is True and acquired['released'] is False
            and acquired['original_command_in_progress'] is False
            and _json(acquired['baseline_document_ids'])==_json(native['baseline_document_ids']))
        _require(_json(pairs[release][1])==_json(native))


def _committed(row):
    args=_durable(row)
    mutation,result=row['mutation'],row['result']
    before,after=result['before'],result['after']
    verification=mutation['verification']
    _require(row['payload']['mutates'] is True and mutation['operation_id']==row['operation_id']
        and mutation['phase']=='committed' and verification['outcome']=='committed'
        and mutation['reconciliation'] is None and result['verified'] is True
        and mutation['document_id']==args['document_id'] and mutation['configuration']==args['configuration']
        and mutation['expected_revision']==args['expected_revision']
        and mutation['before_state']['_mutation_effect_scope']=='application'
        and _json(before)==_json({key:value for key,value in mutation['before_state'].items() if key!='_mutation_effect_scope'})
        and set(verification['evidence'])=={'after','execution_guard'}
        and _json(after)==_json(verification['evidence']['after'])
        and _json(result['execution_guard'])==_json(verification['evidence']['execution_guard'])
        and after['pending'] is False and after['guard_released'] is True
        and after['original_files']==before['baseline']['semantic']['files'])
    return args,mutation,before,after,result['value'],result['execution_guard'],verification['native_steps']


def _suppression(row):
    args,mutation,before,after,value,guard,steps=_committed(row)
    _require(row['operation']=='feature.set_suppressed' and set(args)=={'document_id','configuration',
        'object_id','suppressed','expected_revision'} and type(args['suppressed']) is bool
        and before['scope']==SUPPRESSION_SCOPE and before['object_id']==args['object_id']
        and before['suppressed'] is args['suppressed'] and before['original_suppressed'] is not args['suppressed']
        and type(before['original_suppressed']) is bool
        and _json(value)==_json({key:args[key] for key in ('document_id','configuration','object_id','suppressed')}))
    native_id=_native_id(before['original_base'],args['document_id'],before['feature_pid_hex'])
    oracle=verified_owned_suppression if args['suppressed'] else verified_owned_return
    _require(oracle(before['original_base'],after['state'],args['document_id'],native_id)
             if args['suppressed'] else oracle(before['original_base'],after['state'],args['document_id']))
    actions=after['native_actions']
    _require(type(actions) is list and len(actions)==1)
    action=actions[0]
    expected=[dict(name=name,native_call_returned=True,result=True,result_is_boolean=True)
              for name in ('set_suppressed','rebuild')]
    _require(_json(action)==_json(dict(suppressed=args['suppressed'],original_suppressed=not args['suppressed'],
        attempted=True,pending_native_step=None,journal_failed=False,steps=expected)))
    pairs=_pairs(steps,'suppression_',after)
    names=set(pairs)
    basic={'suppression_execution_guard','suppression_apply_set_suppressed','suppression_apply_rebuild',
           'suppression_guard_release_1','suppression_released_check'}
    extra={'suppression_body_name_guard','suppression_body_name','suppression_guard_release_2'}
    _require(names==basic or (args['suppressed'] is False and names==basic|extra))
    for item in expected:
        _require(_json(pairs['suppression_apply_'+item['name']][1])==_json(item))
    ids=[item['document_id'] for item in before['baseline']['semantic']['documents']]
    _guard(guard,ids,'owned_feature_suppression_guard_v1','effect',2 if names==basic|extra else 1)
    _guard_steps(pairs,ids,guard,'suppression_')
    return args,mutation,before,after


def verified_b2_job(job,*,preparation_job=None,original_suppression_job=None):
    """Require exact coherent durable rows; mutation digest needs actual prepare.

No fallback to names/GetID, fake verified flags, mass-only checks or guessed
ancestor IDs. Return preparation requires its original committed suppression
row as an explicit separate observation. Live canonical ownership is enforced
inside the production server and independently checked by the native owner.
"""
    try:
        if job['operation'] in ('feature.prepare_suppression','feature.prepare_leaf_deletion'):
            _preparation(job)
            return True
        _require(preparation_job is not None)
        prepared=_preparation(preparation_job)
        args,mutation,before,after,value,guard,steps=_committed(job)
        _require(prepared['connection_epoch']==mutation['connection_epoch']
            and prepared['revision']==args['expected_revision']
            and all(prepared[key]==args[key] for key in ('document_id','configuration','object_id'))
            and _json(prepared['baseline'])==_json(before['baseline']))
        if job['operation']=='feature.set_suppressed':
            _require(preparation_job['operation']=='feature.prepare_suppression'
                and prepared['suppressed'] is args['suppressed'])
            _suppression(job)
            projected={key:prepared[key] for key in ('scope','baseline','object_id','suppressed',
                'original_suppressed','feature_pid_hex')}
            _require(set(before)==set(projected)|{'original_base'}
                and _json({key:before[key] for key in projected})==_json(projected))
            if args['suppressed']:
                _require(_json(before['original_base'])==_json(before['baseline']))
            else:
                _require(original_suppression_job is not None
                    and original_suppression_job['operation_id']==prepared['original_suppression_operation_id'])
                old_args,old_mutation,old_before,old_after=_suppression(original_suppression_job)
                _require(old_args['suppressed'] is True and old_mutation['connection_epoch']==mutation['connection_epoch']
                    and all(old_args[key]==args[key] for key in ('document_id','configuration','object_id'))
                    and old_before['feature_pid_hex']==before['feature_pid_hex']
                    and _json(old_before['original_base'])==_json(before['original_base'])
                    and _json(old_after['state'])==_json(before['baseline']))
            return True
        _require(job['operation']=='feature.delete_leaf' and preparation_job['operation']=='feature.prepare_leaf_deletion'
            and set(args)=={'document_id','configuration','object_id','expected_revision'})
        projected={key:prepared[key] for key in ('scope','baseline','feature_native_id','feature_pid_hex',
                                                'object_id','current_definition')}
        _require(_json(before)==_json(projected))
        _require(_json(value)==_json(dict(document_id=args['document_id'],configuration=args['configuration'],
            deleted_feature_object_ids=[args['object_id']],preserved_sketch_object_id=prepared['current_definition']['sketch_object_id'],
            geometry_references_require_refresh=True)))
        _require(_json(after['receipt'])==_json(dict(attempted=True,bridge_returned=True,bridge_exception_returned=False,
            pending_apply=False,deletion_attempted=True,deletion_bridge_verified=True,pending_native_step=None,
            journal_failed=False,selection_uncertain=False,view_state_uncertain=False))
            and after['sketch_canonical_and_pid_confirmed'] is True and after['target_canonical_absent'] is True
            and _json(after['old_feature_pid']) in [_json(dict(native_state=state,native_state_is_integer=True,native_object_is_null=True))
                                           for state in (1,4)]
            and type(after['old_feature_pid']['native_state']) is int)
        pairs=_pairs(steps,'leaf_',after)
        names=set(pairs)
        mandatory={'leaf_execution_guard','leaf_restore_delete_extrusion','leaf_restore_rebuild',
                   'leaf_guard_release','leaf_released_check'}
        optional={'leaf_restore_select_annotation_view','leaf_restore_delete_annotation_view',
                  'leaf_inverse_restore_view_orientation','leaf_inverse_restore_view_scale','leaf_inverse_restore_view_translation'}
        # The existing view bridge probes at most 16 complete tree candidates;
        # these are journal labels, never feature addressing or guessed counts.
        optional|={'leaf_bind_annotation_view_feature_'+str(index) for index in range(16)}
        _require(mandatory<=names<=mandatory|optional)
        for name in ('leaf_restore_delete_extrusion','leaf_restore_rebuild'):
            _require(pairs[name][1]==dict(native_call_returned=True))
        for name in names&optional:
            _require(_json(pairs[name][1])==_json(dict(native_call_returned=True)))
        ids=[item['document_id'] for item in before['baseline']['semantic']['documents']]
        _guard(guard,ids,'owned_leaf_deletion_guard_v1','deleted',1)
        _guard_steps(pairs,ids,guard,'leaf_')
        return verified_owned_leaf_deletion(before['baseline'],after['state'],document_id=args['document_id'],
            configuration=args['configuration'],object_id=args['object_id'],feature_native_id=before['feature_native_id'],
            feature_pid_hex=before['feature_pid_hex'],current_definition=BlindRectangleExtrusion.validate(**before['current_definition']))
    except Exception:
        return False


def b2_contract_result(job,**evidence):
    return dict(scope=SCOPE,job_verified=verified_b2_job(job,**evidence),accepted=False,native_b2=False)
