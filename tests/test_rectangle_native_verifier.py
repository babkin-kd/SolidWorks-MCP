"""Detached external gate on actual JobStore/coordinator and artificial CAD."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path

import pytest

from solidworks_mcp.jobs import _json
from test_rectangle_construction_execution import execution,sketch_proof,extrusion_proof,empty_adapter,run


path=Path(__file__).resolve().parents[1]/'scripts/verifier_rectangle_stages.py'
spec=importlib.util.spec_from_file_location('rectangle_gate',path)
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)


@pytest.fixture
def proof_job(execution,monkeypatch):
    x=execution
    original=x.catalog.prepare_sketch
    def prepare(*args,**kwargs):
        result=original(*args,**kwargs)
        result['scope']='empty_part_rectangle_sketch_v1' if x.kind=='sketch' else 'closed_rectangle_blind_extrusion_v1'
        payload=dict(scope=result['scope'],connection_epoch=x.catalog.connection_epoch,document_id='target',
            configuration='Основная',definition=vars(x.definition),baseline=result['baseline'],
            reference_persistent_id_hex=result['reference_persistent_id_hex'],plane_transform=result['plane_transform'])
        result['revision']='rev_'+hashlib.sha256(_json(payload).encode()).hexdigest()
        return result
    monkeypatch.setattr(x.catalog,'prepare_sketch',prepare)
    monkeypatch.setattr(x.catalog,'prepare_extrusion',prepare)
    monkeypatch.setattr(x.catalog,'_prepare',lambda *args,**kwargs:prepare())
    class NativeShapedGuard:
        def __init__(self,ids):
            self.evidence=dict(scope='application_document_open_guard_v1',original_command_in_progress=False,
                acquired=False,released=False,model_guards=[],selection_preserved=False,
                baseline_document_ids=list(ids),activation_ui_release=dict(attempted=False,verified=False))
        def __enter__(self):
            assert not x.adapter.busy
            assert x.store.get(x.adapter.operation_id)['mutation']['before_state']['_mutation_effect_scope']=='application'
            x.adapter.busy=True
            self.evidence.update(acquired=True,model_guards=[dict(original_state=0,locked_state=2,released_state=None)
                for _ in self.evidence['baseline_document_ids']])
            return self
        def __exit__(self,*args):
            x.adapter.busy=False
            for row in self.evidence['model_guards']:row['released_state']=0
            self.evidence.update(released=True,selection_preserved=True)
    monkeypatch.setattr(x.adapter,'native_open_guard',lambda models,ids:NativeShapedGuard(ids))
    submit=x.runner.submit
    def route(request_id,operation,*args,**kwargs):
        operation={'rectangle.sketch':'sketch.create_rectangle','rectangle.extrusion':'part.extrude_rectangle'}.get(operation,operation)
        return submit(request_id,operation,*args,**kwargs)
    monkeypatch.setattr(x.runner,'submit',route)
    job=run(x)
    assert job['status']=='succeeded',job.get('error')
    assert gate.verified_rectangle_job(job)
    return job


def test_actual_durable_job_with_full_independent_artificial_geometry_is_accepted(proof_job):
    assert gate.verified_rectangle_job(proof_job)


@pytest.mark.parametrize('fault',['pending','unknown','unverified','wrong_revision','wrong_scope','foreign_target',
    'missing_snapshot','neighbor_change','files','missing_release','unreleased_ui','wrong_members',
    'journal_failed','reference_pending','pending_step','missing_ledger_return','ledger_replay','step_boolean',
    'false_final_check','missing_object_id','wrong_id','wrong_created_id','missing_receipt','opaque'])
def test_partial_unsafe_or_unbound_reports_never_authorize_native_success(proof_job,fault):
    job=deepcopy(proof_job)
    before,after,guard=job['result']['before'],job['result']['after'],job['result']['execution_guard']
    if fault=='pending':job['status']='running'
    elif fault=='unknown':job['status']='unknown';job['mutation']['phase']='unresolved'
    elif fault=='unverified':job['result']['verified']=False
    elif fault=='wrong_revision':job['mutation']['expected_revision']='rev_foreign'
    elif fault=='wrong_scope':before['scope']='invented'
    elif fault=='foreign_target':job['payload']['arguments']['document_id']='foreign'
    elif fault=='missing_snapshot':after['state']['snapshots'].pop('neighbor')
    elif fault=='neighbor_change':after['state']['snapshots']['neighbor']={'foreign':'change'}
    elif fault=='files':after['original_files']={'foreign':'bytes'}
    elif fault=='missing_release':guard['guard_released']=False
    elif fault=='unreleased_ui':guard['native_guards'][0]['model_guards'][0]['released_state']=2
    elif fault=='wrong_members':guard['native_guards'][0]['baseline_document_ids'][0]='foreign'
    elif fault=='journal_failed':guard['journal_failed']=True
    elif fault=='reference_pending':guard['reference_binding_unconfirmed']=True
    elif fault=='pending_step':after['receipt']['pending_native_step']='extrude'
    elif fault=='missing_ledger_return':job['mutation']['verification']['native_steps'].pop()
    elif fault=='ledger_replay':job['mutation']['verification']['native_steps'][2]['name']='rectangle_execution_guard'
    elif fault=='step_boolean':job['mutation']['verification']['native_steps'][0]['sequence']=True
    elif fault=='false_final_check':job['mutation']['verification']['native_steps'][-1]['evidence']['verified']=False
    elif fault=='missing_object_id':job['result']['value'].pop('object_id')
    elif fault=='wrong_id':job['result']['value']['object_id']='named-sketch'
    elif fault=='wrong_created_id':job['result']['value']['created_native_id']=0
    elif fault=='missing_receipt':after['receipt']=None
    else:job['result']['native_proxy']=object()
    assert not gate.verified_rectangle_job(job)
