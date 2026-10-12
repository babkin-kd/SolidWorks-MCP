"""Detached journal/guard gates, never a substitute for native CAD readback."""
import hashlib
import re

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_construction import RectangleSketch, BlindRectangleExtrusion
from solidworks_mcp.rectangle_postconditions import verified_rectangle_sketch
from solidworks_mcp.rectangle_extrusion_postconditions import verified_rectangle_extrusion


def released_rectangle_guard(guard, ids, *, mode='effect'):
    try:
        if (type(guard) is not dict or set(guard)!={'scope','native_guards','guard_released',
                'pending_release','journal_failed','reference_binding_unconfirmed','full_release_check'}
                or guard['scope']!='rectangle_construction_guard_v1'
                or guard['guard_released'] is not True or guard['pending_release'] is not False
                or guard['journal_failed'] is not False or guard['reference_binding_unconfirmed'] is not False
                or guard['full_release_check']!=mode or type(guard['native_guards']) is not list
                or len(guard['native_guards'])!=(1 if mode=='effect' else 2)):
            return False
        keys={'scope','original_command_in_progress','acquired','released','model_guards',
              'selection_preserved','baseline_document_ids','activation_ui_release'}
        for native in guard['native_guards']:
            if (type(native) is not dict or set(native)!=keys or native['scope']!='application_document_open_guard_v1'
                    or native['original_command_in_progress'] is not False or native['acquired'] is not True
                    or native['released'] is not True or native['selection_preserved'] is not True
                    or type(native['baseline_document_ids']) is not list
                    or len(native['baseline_document_ids'])!=len(ids) or set(native['baseline_document_ids'])!=set(ids)
                    or native['activation_ui_release']!={'attempted':False,'verified':False}
                    or type(native['model_guards']) is not list or len(native['model_guards'])!=len(ids)):
                return False
            for model in native['model_guards']:
                if (type(model) is not dict or set(model)!={'original_state','locked_state','released_state'}
                        or any(type(model[k]) is not int or model[k]!=v for k,v in
                            (('original_state',0),('locked_state',2),('released_state',0)))):return False
        return True
    except (KeyError,TypeError,ValueError):return False


def verified_rectangle_job(job):
    """Exact committed rectangle protocol plus full detached geometric admission."""
    try:
        _json(job)
        mutation,result=job['mutation'],job['result']
        before,after,value=result['before'],result['after'],result['value']
        verification=mutation['verification']
        args=job['payload']['arguments']
        target,cfg=args['document_id'],args['configuration']
        kind={'sketch.create_rectangle':'sketch','part.extrude_rectangle':'extrusion'}[job['operation']]
        scope='empty_part_rectangle_sketch_v1' if kind=='sketch' else 'closed_rectangle_blind_extrusion_v1'
        if (job['status']!='succeeded' or job['error'] is not None or job['payload']['mutates'] is not True
                or mutation['phase']!='committed' or verification['outcome']!='committed'
                or result['verified'] is not True or before['scope']!=scope
                or mutation['before_state'].get('_mutation_effect_scope')!='application'
                or _json(before)!=_json({k:v for k,v in mutation['before_state'].items() if k!='_mutation_effect_scope'})
                or _json(after)!=_json(verification['evidence']['after'])
                or _json(result['execution_guard'])!=_json(verification['evidence']['execution_guard'])):return False
        ids=[row['document_id'] for row in before['baseline']['semantic']['documents']]
        if (len(ids)!=len(set(ids)) or target not in ids or set(before['baseline']['snapshots'])!=set(ids)
                or not released_rectangle_guard(result['execution_guard'],ids)
                or mutation['document_id']!=target or mutation['configuration']!=cfg
                or after['pending'] is not False or after['guard_released'] is not True
                or after['original_files']!=before['baseline']['semantic']['files']
                or value['document_id']!=target or value['configuration']!=cfg or value['kind']!=kind
                or type(value['created_native_id']) is not int
                or type(value['object_id']) is not str or re.fullmatch(r'feat_[0-9a-f]{32}',value['object_id']) is None
                or value['sketch_object_id' if kind=='sketch' else 'feature_object_id']!=value['object_id']):return False
        definition=(RectangleSketch if kind=='sketch' else BlindRectangleExtrusion).validate(**before['definition'])
        if args!={**vars(definition),'document_id':target,'configuration':cfg,'expected_revision':mutation['expected_revision']}:return False
        payload=dict(scope=scope,connection_epoch=mutation['connection_epoch'],document_id=target,configuration=cfg,
            definition=vars(definition),baseline=before['baseline'],
            reference_persistent_id_hex=before['reference_persistent_id_hex'],plane_transform=before['plane_transform'])
        if mutation['expected_revision']!='rev_'+hashlib.sha256(_json(payload).encode('utf-8')).hexdigest():return False
        receipt=after['receipt']
        if (receipt['attempted'] is not True or receipt['native_call_returned'] is not True
                or any(receipt[k] is not False for k in ('pending_creation','pending_sketch_close','selection_uncertain',
                    'restore_attempted','restored','native_step_journal_failed','view_state_uncertain'))
                or receipt['pending_native_step'] is not None
                or (kind=='sketch' and receipt['sketch_closed'] is not True)):return False
        steps=verification['native_steps']
        # Up to three one-shot, typed model-view setters add six rows to the
        # existing finite construction/view-binding/guard/readback profile.
        if type(steps) is not list or not 6<=len(steps)<=38 or len(steps)%2:return False
        names=set()
        for i in range(0,len(steps),2):
            a,b=steps[i:i+2]
            if (set(a)!= {'sequence','name','phase','evidence'} or set(b)!=set(a)
                    or type(a['sequence']) is not int or a['sequence']!=i+1
                    or type(b['sequence']) is not int or b['sequence']!=i+2
                    or a['phase']!='pending' or b['phase']!='returned' or a['name']!=b['name']
                    or a['name'] in names or type(a['evidence']) is not dict or type(b['evidence']) is not dict):return False
            names.add(a['name'])
        if (steps[0]['name']!='rectangle_execution_guard' or steps[-1]['name']!='rectangle_released_check'
                or steps[-1]['evidence']['verified'] is not True
                or _json(steps[-1]['evidence']['observed'])!=_json(after)
                or 'rectangle_guard_release_1' not in names):return False
        predicate=verified_rectangle_sketch if kind=='sketch' else verified_rectangle_extrusion
        return predicate(before['baseline'],after['state'],target,definition,value['created_native_id'])
    except Exception:return False
