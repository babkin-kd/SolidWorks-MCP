"""Original B1 jobs and independent comparison operands; no CAD lifecycle."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest
from solidworks_mcp.jobs import ExecutionFailure

from test_rectangle_native_verifier import (
    configured,execution,sketch_proof,extrusion_proof,empty_adapter,proof_job)
from test_b2_native_observer import namespace
from test_b2_session_mapping import integrated

scripts=str(Path(__file__).resolve().parents[1]/'scripts')
sys.path.insert(0,scripts)
try:
    import verifier_b2_public_observation as helper
    from verifier_rectangle_stages import verified_rectangle_job
finally:sys.path.remove(scripts)


def test_original_created_id_binds_one_complete_structural_pid_without_job_changes(proof_job):
    job=proof_job
    preserved=deepcopy(job)
    role=helper.feature_role(job)
    assert role['creation_operation_id']==job['operation_id']
    assert role['object_id']==job['result']['value']['object_id']
    assert bytes.fromhex(role['persistent_id_hex'])
    assert job==preserved


@pytest.mark.parametrize('fault',['unknown','foreign_id','wrong_alias','wrong_kind','missing_anchor','missing_job'])
def test_original_feature_role_cannot_be_rebuilt_from_names_or_partial_job(proof_job,fault):
    job=deepcopy(proof_job)
    value=job['result']['value']
    if fault=='unknown':job['status']='unknown'
    elif fault=='foreign_id':value['object_id']='feat_'+'f'*32
    elif fault=='wrong_alias':value['sketch_object_id' if value['kind']=='sketch' else 'feature_object_id']='foreign'
    elif fault=='wrong_kind':value['kind']='foreign'
    elif fault=='missing_anchor':job['result']['after']['state']['snapshots']['target']['references']=[]
    elif fault=='missing_job':job.pop('mutation')
    with pytest.raises((ValueError,KeyError)):helper.feature_role(job)


@pytest.mark.parametrize('execution',['extrusion'],indirect=True)
def test_comparison_operand_uses_full_independent_views_and_never_rewrites_durable_job(proof_job,monkeypatch):
    monkeypatch.syspath_prepend(scripts)
    job=proof_job
    preserved=deepcopy(job)
    before=namespace(job['result']['before']['baseline']['snapshots']['target'])
    after=namespace(job['result']['after']['state']['snapshots']['target'])
    operand=helper.independent_creation_operand(job,before,after)
    assert operand['scope']=='b2_independent_creation_comparison_operand_v1'
    assert 'digest' not in operand and 'operation_id' not in operand
    assert not verified_rectangle_job(operand)
    assert all(operand[key] is False for key in ('accepted','native_acceptance','cleanup_authorized','mutation_authorized'))
    assert operand['result']['before']['baseline']['snapshots']['target']==before
    assert operand['result']['after']['state']['snapshots']['target']==after
    assert job==preserved


@pytest.mark.parametrize('fault',['wrong_brep','lost_borrowed_view','changed_sketch_anchor'])
@pytest.mark.parametrize('execution',['extrusion'],indirect=True)
def test_cross_namespace_operand_requires_complete_original_stage_bijection(proof_job,monkeypatch,fault):
    monkeypatch.syspath_prepend(scripts)
    before=namespace(proof_job['result']['before']['baseline']['snapshots']['target'])
    after=namespace(proof_job['result']['after']['state']['snapshots']['target'])
    if fault=='wrong_brep':after['clone_state']['geometry']['bodies']=[]
    elif fault=='lost_borrowed_view':after['native_observations']['annotation_view_bindings']['dimension_views']['width']='av_'+'f'*32
    else:next(row for row in before['references'] if row['kind']=='dimension')['token']='ffff'
    with pytest.raises((ValueError,ExecutionFailure)):helper.independent_creation_operand(proof_job,before,after)


def test_native_route_compares_actual_independent_counters_without_copying_server_history(integrated,monkeypatch):
    monkeypatch.syspath_prepend(scripts)
    from verifier_b2_session_mapping import compare_mapped_session
    from verifier_b2_public_route import compare_b2_observed_state
    x=integrated
    preserved=deepcopy((x.actual,x.server))
    proof=compare_mapped_session(x.actual,x.server,native_entries=x.native_entries,bridges=x.bridges)
    assert compare_b2_observed_state(proof['mapped_state'],x.server) is True
    assert proof['server_revision_copied'] is False
    assert (x.actual,x.server)==preserved
    changed=deepcopy(proof['mapped_state'])
    changed['semantic']['documents'][0]['observation_revision']='obs_'+'0'*64
    with pytest.raises(ValueError):compare_b2_observed_state(changed,x.server)
