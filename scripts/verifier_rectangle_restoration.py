"""Exact detached owned rollback admission, with no COM/cleanup actions."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_construction import RectangleSketch,BlindRectangleExtrusion
# Resolve this passive sibling for standalone and path-based loading without
# changing the process-wide import path or relying on a cached named module.
_stages_spec = importlib.util.spec_from_file_location('_rectangle_restoration_stages',
    Path(__file__).with_name('verifier_rectangle_stages.py'))
_stages = importlib.util.module_from_spec(_stages_spec)
_stages_spec.loader.exec_module(_stages)
released_rectangle_guard = _stages.released_rectangle_guard


def verified_rectangle_restoration(job):
    try:
        _json(job)
        mutation=job['mutation'];before=mutation['before_state'];verification=mutation['verification']
        after=verification['evidence']['after'];guard=verification['evidence']['execution_guard']
        args=job['payload']['arguments'];target,cfg=args['document_id'],args['configuration']
        kind={'sketch.create_rectangle':'sketch','part.extrude_rectangle':'extrusion'}[job['operation']]
        scope='empty_part_rectangle_sketch_v1' if kind=='sketch' else 'closed_rectangle_blind_extrusion_v1'
        if (job['status']!='failed' or job['result'] is not None or job['payload']['mutates'] is not True
                or job['error']['requires_reconciliation'] is not False
                or mutation['phase']!='rolled_back' or verification['outcome']!='rolled_back'
                or before['_mutation_effect_scope']!='application' or before['scope']!=scope
                or mutation['document_id']!=target or mutation['configuration']!=cfg
                or after['pending'] is not False or after['guard_released'] is not True):return False
        definition=(RectangleSketch if kind=='sketch' else BlindRectangleExtrusion).validate(**before['definition'])
        payload=dict(scope=scope,connection_epoch=mutation['connection_epoch'],document_id=target,configuration=cfg,
            definition=vars(definition),baseline=before['baseline'],
            reference_persistent_id_hex=before['reference_persistent_id_hex'],plane_transform=before['plane_transform'])
        if (mutation['expected_revision']!='rev_'+hashlib.sha256(_json(payload).encode()).hexdigest()
                or args!={**vars(definition),'document_id':target,'configuration':cfg,'expected_revision':mutation['expected_revision']}):return False
        ids=[r['document_id'] for r in before['baseline']['semantic']['documents']]
        if len(set(ids))!=len(ids) or target not in ids or not released_rectangle_guard(guard,ids,mode='restored'):return False
        receipt=after['receipt']
        if (receipt['restored'] is not True or receipt['restore_attempted'] is not True
                or any(receipt[k] is not False for k in ('pending_creation','pending_sketch_close','selection_uncertain','native_step_journal_failed'))
                or receipt['pending_native_step'] is not None
                or after['original_files']!=before['baseline']['semantic']['files']):return False
        a,b=deepcopy(before['baseline']),deepcopy(after['state'])
        old=next(r for r in a['semantic']['documents'] if r['document_id']==target)
        new=next(r for r in b['semantic']['documents'] if r['document_id']==target)
        if set(old)!=set(new):return False
        for row in (old,new):
            if (type(row['update_stamp']) is not int or type(row['observation_sequence']) is not int
                    or type(row['observation_revision']) is not str or not row['observation_revision']):return False
            for key in ('update_stamp','observation_sequence','observation_revision'):row.pop(key)
        first=a['snapshots'][target]['clone_state']['dimensions'];last=b['snapshots'][target]['clone_state']['dimensions']
        if len(first)!=len(last) or any(set(x)!=set(y) for x,y in zip(first,last)):return False
        for row in [*first,*last]:
            if 'owner_update_stamp' in row:
                if type(row['owner_update_stamp']) is not int:return False
                row.pop('owner_update_stamp')
        if _json(a)!=_json(b):return False
        steps=verification['native_steps'];names=[]
        # Extrusion owns five construction calls, three view-feature bindings,
        # two initial guard calls, and seven inverse/release/proof calls: 34
        # pending/returned rows. Sketch owns at most 32 in its bounded profile.
        maximum_steps=32 if kind=='sketch' else 34
        if type(steps) is not list or not 12<=len(steps)<=maximum_steps or len(steps)%2:return False
        for i in range(0,len(steps),2):
            pending,returned=steps[i:i+2]
            if (set(pending)!={'sequence','name','phase','evidence'} or set(returned)!=set(pending)
                    or type(pending['sequence']) is not int or pending['sequence']!=i+1
                    or type(returned['sequence']) is not int or returned['sequence']!=i+2
                    or pending['phase']!='pending' or returned['phase']!='returned'
                    or pending['name']!=returned['name'] or pending['name'] in names
                    or type(pending['evidence']) is not dict or type(returned['evidence']) is not dict):return False
            names.append(pending['name'])
        if (names[0]!='rectangle_execution_guard' or names[-1]!='rectangle_restored_release_check'
                or not {'rectangle_guard_release_1','rectangle_restoration_guard','rectangle_guard_release_2'}<=set(names)
                or names.index('rectangle_guard_release_1')>names.index('rectangle_restoration_guard')
                or names.index('rectangle_restoration_guard')>names.index('rectangle_guard_release_2')
                or steps[-1]['evidence']['verified'] is not True
                or _json(steps[-1]['evidence']['observed'])!=_json(after)):return False
        return True
    except Exception:return False
