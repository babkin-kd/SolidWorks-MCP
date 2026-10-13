"""Real coordinator/runner/SQLite/leaf action; changing artificial native state."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_owned_leaf_deletion import NativeOwnedLeafDeletion
from solidworks_mcp.cad_rectangle_construction import CadRectangleConstructionMixin
from solidworks_mcp.cad_rectangle_model_view import RectangleModelView
from solidworks_mcp.cad_rectangle_view_retirement import NativeView, RectangleViewReceipt
from solidworks_mcp.jobs import ExecutionFailure, _json
from solidworks_mcp.owned_leaf_deletion_postconditions import verified_owned_leaf_deletion
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from test_owned_leaf_deletion_catalog import leaf, extrusion_proof, proof, case, domain, receipt_evidence


@pytest.fixture
def execution(leaf,monkeypatch):
    state=leaf
    c=state.c
    adapter=c.adapter
    state.deleted=False
    state.fault=None
    state.bridge_calls=[]
    state.native_calls=[]
    state.after_forbidden_calls=[]
    state.stage=None
    state.after_snapshot=None
    state.view_identity=object()
    state.entries[0].features={'references':{state.binding.object_id:object(),'borrowed_sketch':object()}}
    state.entries[0].features['reference_index']={
        ('Основная',state.binding.persistent_id):NS(object_id=state.binding.object_id),
        ('Основная',b'sketch'):NS(object_id='borrowed_sketch')}
    receipt=state.binding.receipt
    original_sketch=state.binding.baseline_target_snapshot
    display=original_sketch['clone_state']['display_data']['annotation_views']
    receipt.annotation_views=RectangleViewReceipt(state.binding.model_identity,
        tuple(NativeView(NS(identity=object()),object(),deepcopy(row)) for row in display),
        owned=[(NativeView(NS(identity=object()),object(),{'owned_depth_view':True}),NS(identity=object()))],
        binding_attempted=True,bound=True)
    receipt.model_view=RectangleModelView(state.binding.model_identity,object(),{'creation_view':'original'})
    receipt.borrowed_sketch_snapshot=deepcopy(original_sketch['clone_state']['sketch'])
    def factory(registry,binding,*,recorder):
        return NativeOwnedLeafDeletion(registry,binding,recorder=recorder,
            capture_view=lambda model:RectangleModelView(adapter.identity(model),state.view_identity,
                                                        deepcopy(adapter.document_view_snapshot(model))))
    monkeypatch.setattr('solidworks_mcp.owned_leaf_deletion_execution.NativeOwnedLeafDeletion',factory)
    for name in ('GetID','GetChildren','IsSuppressed2'):
        original=getattr(state.binding.feature,name)
        def current(*args,name=name,original=original):
            if state.deleted:
                state.after_forbidden_calls.append(name)
                raise AssertionError('Deleted extrusion native calls are forbidden: '+name)
            return original(*args)
        setattr(state.binding.feature,name,current)
    original_identity=adapter.identity
    def identity(value):
        if value is state.binding.feature and state.deleted:
            state.after_forbidden_calls.append('identity')
            raise AssertionError('Deleted extrusion IUnknown query is forbidden')
        return original_identity(value)
    adapter.identity=identity
    original_snapshot=adapter.rectangle_construction_snapshot
    def snapshot(model):
        if state.deleted and model is c.model:
            return deepcopy(state.after_snapshot)
        return original_snapshot(model)
    adapter.rectangle_construction_snapshot=snapshot
    original_extension=adapter._extension
    def extension(model):
        original=original_extension(model)
        def raw(pid):
            if state.deleted and pid==state.binding.persistent_id:
                return None,1  # Actual normally returned SWInvalid=1 observation.
            return original.GetObjectByPersistReference3(pid)
        return NS(GetObjectByPersistReference3=raw)
    adapter._extension=extension
    def changed():
        state.deleted=True
        c.features.remove(state.binding.feature)
        c.bodies=[]
        c.records=[record for record in c.records if record.owner is receipt.borrowed_sketch]
        receipt.borrowed_sketch.row['owner_native_id']=None
        for record in c.records: record.summary['owner']['owner_native_id']=None
        state.after_snapshot=deepcopy(original_sketch)
        state.sequence+=1
        if state.fault=='bad_after_data':
            state.after_snapshot['references']=[row for row in state.after_snapshot['references']
                                                if row['role']!='dimension:width']
    def delete_call():
        state.native_calls.append('delete')
        if state.fault=='delete_pending': raise RuntimeError('Artificial missing delete acknowledgement')
        if state.fault!='false_noeffect': changed()
        return state.fault not in ('false_noeffect','false_effect')
    def rebuild_call():
        state.native_calls.append('rebuild')
        if state.fault=='rebuild_pending': raise RuntimeError('Artificial missing rebuild acknowledgement')
        return True
    def bridge(model,stage):
        assert state.busy and model is c.model and stage is not receipt
        assert stage.extrusion is state.binding.feature
        assert stage.borrowed_sketch is receipt.borrowed_sketch
        assert stage.annotation_views is not receipt.annotation_views
        assert stage.annotation_views.owned is not receipt.annotation_views.owned
        assert stage.annotation_views.owned[0][0].view is receipt.annotation_views.owned[0][0].view
        assert stage.annotation_views.owned[0][1] is receipt.annotation_views.owned[0][1]
        assert stage.model_view.baseline==adapter.document_view_snapshot(model)
        state.bridge_calls.append('restore_rectangle_extrusion')
        state.stage=stage
        stage.restore_attempted=True
        if CadRectangleConstructionMixin._rectangle_native_step(stage,'restore_delete_extrusion',delete_call) is not True:
            raise ExecutionFailure('construction_restore_unconfirmed','Normally returned false delete.',uncertain=True)
        if CadRectangleConstructionMixin._rectangle_native_step(stage,'restore_rebuild',rebuild_call) is not True:
            raise ExecutionFailure('construction_restore_unconfirmed','Normally returned false rebuild.',uncertain=True)
        stage.annotation_views.retirement_attempted=True
        stage.annotation_views.retired=True
        stage.deleted.append(state.binding.feature)
        stage.restored=True
    adapter.restore_rectangle_extrusion=bridge
    adapter.Undo=lambda *args:pytest.fail('Automatic Undo is forbidden')
    adapter.extrude_rectangle_sketch=lambda *args:pytest.fail('Automatic recreation is forbidden')
    return state


def submit(state,*,request='delete',revision=None,document_id='target',object_id=None):
    revision=revision or state.leaf.prepare('target','Основная',state.binding.object_id)['revision']
    arguments=dict(document_id=document_id,configuration='Основная',object_id=object_id or state.binding.object_id,
                   expected_revision=revision)
    job=state.runner.submit(request,'feature.delete_leaf',arguments,
        lambda operation_id:state.leaf.delete(operation_id,**arguments),context=arguments,
        mutates=True,verify=lambda result:result.get('verified') is True,pass_operation_id=True)
    return state.store.get(job['operation_id'])


def test_real_commit_replay_preserves_original_receipt_borrowed_sketch_and_retires_only_owned_handles(execution):
    state=execution
    original=receipt_evidence(state)
    views=deepcopy((state.binding.receipt.annotation_views.baseline[0].data,
        state.binding.receipt.annotation_views.owned[0][0].data,state.binding.receipt.model_view.baseline))
    creation=state.store.get(state.binding.creation_operation_id)
    job=submit(state)
    assert job['status']=='succeeded',job.get('error')
    assert job['mutation']['phase']=='committed'
    result=job['result']
    assert verified_owned_leaf_deletion(result['before']['baseline'],result['after']['state'],
        document_id='target',configuration='Основная',object_id=state.binding.object_id,
        feature_native_id=state.binding.native_id,feature_pid_hex=state.binding.persistent_id.hex(),
        current_definition=BlindRectangleExtrusion.validate(**result['before']['current_definition']))
    assert result['after']['old_feature_pid']==dict(native_state=1,native_state_is_integer=True,native_object_is_null=True)
    assert result['after']['sketch_canonical_and_pid_confirmed'] is True
    assert result['value']['preserved_sketch_object_id']==result['before']['current_definition']['sketch_object_id']
    assert state.binding.receipt.borrowed_sketch in state.c.features
    assert len(state.c.records)==2 and state.c.bodies==[]
    assert state.bridge_calls==['restore_rectangle_extrusion'] and state.native_calls==['delete','rebuild']
    assert state.after_forbidden_calls==[] and state.guard_count==state.releases==1
    assert state.entries[0].geometry=={} and state.binding.object_id not in state.entries[0].features['references']
    assert 'borrowed_sketch' in state.entries[0].features['references']
    assert list(state.entries[0].features['reference_index'])==[('Основная',b'sketch')]
    assert (state.binding.document_id,state.binding.object_id) not in state.ownership._bindings
    assert state.leaf.receipts=={} and state.store.get(creation['operation_id'])==creation
    assert receipt_evidence(state)==original
    assert views==(state.binding.receipt.annotation_views.baseline[0].data,
        state.binding.receipt.annotation_views.owned[0][0].data,state.binding.receipt.model_view.baseline)
    assert state.binding.receipt.annotation_views.retired is False
    replay=submit(state,revision=job['payload']['arguments']['expected_revision'])
    assert replay['operation_id']==job['operation_id'] and replay['status']=='succeeded'
    assert state.bridge_calls==['restore_rectangle_extrusion'] and state.after_forbidden_calls==[]


def test_normally_returned_false_without_effect_is_known_failure_without_native_inverse(execution):
    state=execution
    state.fault='false_noeffect'
    original=receipt_evidence(state)
    job=submit(state)
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back',job.get('error')
    assert state.bridge_calls==['restore_rectangle_extrusion'] and state.native_calls==['delete']
    assert not state.deleted and receipt_evidence(state)==original
    assert not state.store.mutation_blockers('epoch','neighbor')
    assert state.guard_count==state.releases==1 and state.leaf.receipts=={}


@pytest.mark.parametrize('fault',['stale','foreign_document','foreign_object'])
def test_foreign_or_stale_targets_refuse_before_guard_and_native_delete(execution,fault):
    state=execution
    revision=state.leaf.prepare('target','Основная',state.binding.object_id)['revision']
    job=submit(state,revision='stale' if fault=='stale' else revision,
        document_id='foreign' if fault=='foreign_document' else 'target',
        object_id='feat_'+'f'*32 if fault=='foreign_object' else None)
    assert job['status']=='failed' and state.guard_count==0 and state.bridge_calls==[]
    assert state.store.mutation_blockers('epoch','target')==[]


@pytest.mark.parametrize('fault',['delete_pending','rebuild_pending','false_effect','bad_after_data',
    'journal_delete_pending','journal_delete_returned','journal_rebuild_pending','journal_rebuild_returned'])
def test_pending_changed_or_partial_outcome_is_unknown_held_without_inverse_recreation_retry(execution,fault,monkeypatch):
    state=execution
    original=receipt_evidence(state)
    failures=[]
    if fault.startswith('journal_'):
        _,step,phase=fault.split('_')
        label='leaf_restore_delete_extrusion' if step=='delete' else 'leaf_restore_rebuild'
        original_record=state.store.record_mutation_step
        def record(operation_id,*,name,phase,evidence):
            if name==label and phase==fault.rsplit('_',1)[1]:
                failures.append(name)
                raise OSError('Artificial native ledger write loss')
            return original_record(operation_id,name=name,phase=phase,evidence=evidence)
        monkeypatch.setattr(state.store,'record_mutation_step',record)
    else: state.fault=fault
    job=submit(state)
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved',job.get('error')
    if fault.startswith('journal_'): assert len(failures)==1
    assert state.store.mutation_blockers('epoch','neighbor')
    assert state.bridge_calls==['restore_rectangle_extrusion']
    assert state.after_forbidden_calls==[] and receipt_evidence(state)==original
    assert state.entries[0].geometry=={}
    calls=list(state.native_calls)
    replay=submit(state,revision=job['payload']['arguments']['expected_revision'])
    assert replay['operation_id']==job['operation_id'] and replay['status']=='unknown'
    blocked=submit(state,request='new_delete',revision=job['payload']['arguments']['expected_revision'])
    assert blocked['status']=='failed' and blocked['error']['code']=='document_mutation_blocked'
    assert state.native_calls==calls and state.bridge_calls==['restore_rectangle_extrusion']


@pytest.mark.parametrize('boundary',['commit','retirement','terminal_finish'])
def test_late_journal_or_ownership_retirement_failure_never_inverts_deletion(execution,boundary,monkeypatch):
    state=execution
    if boundary=='commit':
        original=state.store.verify_mutation
        def verify(operation_id,*,outcome,evidence):
            if outcome=='committed': raise OSError('Artificial late domain commit loss')
            return original(operation_id,outcome=outcome,evidence=evidence)
        monkeypatch.setattr(state.store,'verify_mutation',verify)
    elif boundary=='retirement':
        def retire(binding): raise RuntimeError('Artificial exact ownership retirement failure')
        monkeypatch.setattr(state.ownership,'forget_feature',retire)
    else:
        original=state.store.finish
        def finish(operation_id,status,**kwargs):
            if status=='succeeded': raise OSError('Artificial terminal journal acknowledgement loss')
            return original(operation_id,status,**kwargs)
        monkeypatch.setattr(state.store,'finish',finish)
    job=submit(state)
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved',job.get('error')
    assert state.deleted and state.native_calls==['delete','rebuild']
    assert state.bridge_calls==['restore_rectangle_extrusion'] and state.after_forbidden_calls==[]
    assert state.store.mutation_blockers('epoch','neighbor')
