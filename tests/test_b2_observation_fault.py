"""Actual leaf coordinator/SQLite/receipt, changing artificial native handles."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path

import pytest

from solidworks_mcp.rectangle_snapshot import SKETCH
from test_owned_leaf_deletion_execution import execution, submit
from test_owned_leaf_deletion_catalog import leaf, extrusion_proof, proof, case, domain, receipt_evidence

path=Path(__file__).resolve().parents[1]/'scripts/verifier_b2_observation_fault.py'
spec=importlib.util.spec_from_file_location('_b2_observation_fault_test',path)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
LeafObservationFault,LeafNoEffectFault=helper.LeafObservationFault,helper.LeafNoEffectFault


def test_postreturn_python_failure_keeps_actual_delete_unknown_held_without_repeat(execution):
    x=execution
    original=receipt_evidence(x)
    hook=LeafObservationFault(x.c.adapter,x.binding).install()
    job=submit(x)
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved'
    facts=hook.evidence()
    assert facts['bridge_attempts']==facts['normal_bridge_returns']==facts['injected_faults']==1
    assert facts['bridge_dispatches']==1
    assert facts['pending_bridge'] is facts['pending_snapshot'] is facts['armed'] is False
    assert facts['actual_after_snapshot']['clone_state']['profile']==SKETCH
    assert facts['native_acceptance'] is facts['cleanup_authorized'] is facts['reconciliation_authorized'] is False
    assert x.deleted and x.bridge_calls==['restore_rectangle_extrusion'] and x.native_calls==['delete','rebuild']
    assert x.after_forbidden_calls==[] and receipt_evidence(x)==original
    assert x.store.mutation_blockers('epoch','neighbor')
    steps=job['mutation']['verification']['native_steps']
    assert len(steps)%2==0
    assert all(a['phase']=='pending' and b['phase']=='returned' and a['name']==b['name']
        for a,b in zip(steps[::2],steps[1::2]))
    arguments=job['payload']['arguments']
    replay=submit(x,revision=arguments['expected_revision'])
    assert replay['operation_id']==job['operation_id'] and replay['status']=='unknown'
    blocked=submit(x,request='blocked',revision=arguments['expected_revision'])
    assert blocked['status']=='failed' and blocked['error']['code']=='document_mutation_blocked'
    assert hook.injected_faults==1 and x.bridge_calls==['restore_rectangle_extrusion']
    assert hook.bridge_dispatches==1
    hook.detach()
    assert x.store.mutation_blockers('epoch','neighbor')
    with pytest.raises(ValueError):hook.install()
    with pytest.raises(ValueError):hook.detach()


@pytest.mark.parametrize('fault',['delete_pending','rebuild_pending'])
def test_a_pending_bridge_is_never_a_controlled_python_fault_or_detachable(execution,fault):
    x=execution;x.fault=fault
    hook=LeafObservationFault(x.c.adapter,x.binding).install()
    job=submit(x)
    assert job['status']=='unknown'
    assert hook.pending_bridge is hook.bridge_exception_returned is True
    assert hook.normal_bridge_returns==hook.injected_faults==0 and hook.after_snapshot is None
    with pytest.raises(ValueError):hook.detach()


def test_prewrite_stale_failure_never_arms_or_fakes_native_effect(execution):
    x=execution
    hook=LeafObservationFault(x.c.adapter,x.binding).install()
    job=submit(x,revision='stale')
    assert job['status']=='failed' and x.bridge_calls==[]
    assert hook.bridge_attempts==hook.injected_faults==0 and hook.after_snapshot is None
    with pytest.raises(ValueError):hook.detach()


def test_hook_cannot_be_used_from_another_apartment(execution):
    x=execution
    hook=LeafObservationFault(x.c.adapter,x.binding).install()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ValueError):pool.submit(hook.snapshot,x.c.model).result()
    assert hook.bridge_attempts==hook.injected_faults==0


def test_before_bridge_failure_requires_actual_domain_full_no_effect_and_release_proof(execution):
    x=execution
    original=receipt_evidence(x)
    hook=LeafNoEffectFault(x.c.adapter,x.binding).install()
    job=submit(x)
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back'
    after=job['mutation']['verification']['evidence']['after']
    assert after['guard_released'] is True and after['pending'] is False
    assert after['state']==job['mutation']['before_state']['baseline']
    assert not x.deleted and x.bridge_calls==x.native_calls==[]
    assert hook.bridge_dispatches==hook.bridge_attempts==hook.injected_faults==1
    assert hook.normal_bridge_returns==0 and hook.after_snapshot is None
    assert x.guard_count==x.releases==1 and x.leaf.receipts=={}
    assert not x.store.mutation_blockers('epoch','neighbor')
    assert receipt_evidence(x)==original and x.after_forbidden_calls==[]
    replay=submit(x,revision=job['payload']['arguments']['expected_revision'])
    assert replay['operation_id']==job['operation_id'] and replay['status']=='failed'
    assert hook.bridge_dispatches==1 and x.bridge_calls==[]
    hook.detach()
    assert x.c.adapter.restore_rectangle_extrusion==hook.original_bridge
    assert hook.evidence()['fault_before_native_bridge'] is True
