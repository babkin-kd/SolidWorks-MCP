"""Detached rollback gate with real coordinator and artificial geometry."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

from test_rectangle_native_verifier import configured,execution,sketch_proof,extrusion_proof,empty_adapter
from test_rectangle_construction_execution import run


scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:
    spec=importlib.util.spec_from_file_location('rectangle_rollback_gate',scripts/'verifier_rectangle_restoration.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
finally:sys.path.remove(str(scripts))


@pytest.fixture
def rollback_job(configured):
    x=configured
    x.adapter.fault='inspect_once'
    job=run(x,'controlled-owned-rollback')
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back',job.get('error')
    assert helper.verified_rectangle_restoration(job)
    return job


def test_real_durable_owned_rollback_with_full_artificial_baseline_is_verified(rollback_job):
    assert helper.verified_rectangle_restoration(rollback_job)


@pytest.mark.parametrize('fault',['unknown','missing_inverse','one_guard','guard_not_released','pending',
    'missing_counter','dirty','neighbor','sketch_data','files','wrong_revision','unverified_final','order'])
def test_unsafe_or_incomplete_rollback_never_releases_native_fixtures(rollback_job,fault):
    job=deepcopy(rollback_job);verification=job['mutation']['verification']
    after=verification['evidence']['after'];guard=verification['evidence']['execution_guard']
    if fault=='unknown':job['status']='unknown';job['mutation']['phase']='unresolved'
    elif fault=='missing_inverse':after['receipt']['restored']=False
    elif fault=='one_guard':guard['native_guards'].pop()
    elif fault=='guard_not_released':guard['guard_released']=False
    elif fault=='pending':after['receipt']['pending_native_step']='delete'
    elif fault=='missing_counter':after['state']['semantic']['documents'][0].pop('observation_sequence')
    elif fault=='dirty':after['state']['semantic']['documents'][0]['needs_save']=False
    elif fault=='neighbor':after['state']['snapshots']['neighbor']={'foreign':'change'}
    elif fault=='sketch_data':after['state']['snapshots']['target']['clone_state']['material'][0]='changed'
    elif fault=='files':after['original_files']={'foreign':'bytes'}
    elif fault=='wrong_revision':job['mutation']['expected_revision']='rev_other'
    elif fault=='unverified_final':verification['native_steps'][-1]['evidence']['verified']=False
    else:verification['native_steps'][2]['name']='rectangle_restoration_guard'
    assert not helper.verified_rectangle_restoration(job)


def native_shaped_ledger(job, *, restore_views=True):
    """Expand artificial calls to the actual finite rectangle bridge sequence."""
    job=deepcopy(job);steps=job['mutation']['verification']['native_steps']
    sketch=job['operation']=='sketch.create_rectangle'
    creation=(['open_sketch','name_sketch','draw_rectangle','define_rectangle','close_sketch','rebuild_sketch']
        if sketch else ['extrude','name_extrusion','name_depth','rebuild','name_body'])
    binding=[f'bind_annotation_view_feature_{i}' for i in range(2 if sketch else 3)]
    inverse=(['restore_owned_sketch'] if sketch else ['restore_delete_extrusion','restore_rebuild'])
    inverse+=['restore_select_annotation_view','restore_delete_annotation_view']
    if restore_views:
        creation += ['restore_view_' + key for key in ('orientation','scale','translation')]
        inverse += ['inverse_restore_view_' + key for key in ('orientation','scale','translation')]
    expanded=[]
    for row in steps:
        labels=creation+binding if row['name']=='rectangle_construct_artificial' else (
            inverse if row['name']=='rectangle_restore_artificial' else None)
        if labels:
            if row['phase']=='pending':
                for label in labels:
                    for phase in ('pending','returned'):
                        expanded.append(dict(name='rectangle_'+label,phase=phase,
                            evidence={'native_call_returned':phase=='returned'}))
        else:expanded.append(deepcopy(row))
    for i,row in enumerate(expanded,1):row['sequence']=i
    job['mutation']['verification']['native_steps']=expanded
    return job


@pytest.mark.parametrize('restore_views', [False, True])
def test_exact_native_view_binding_and_retirement_ledger_fits_finite_stage_budget(rollback_job,restore_views):
    job=native_shaped_ledger(rollback_job,restore_views=restore_views)
    expected=(32 if job['operation']=='sketch.create_rectangle' else 34) + (12 if restore_views else 0)
    assert len(job['mutation']['verification']['native_steps'])==expected
    assert helper.verified_rectangle_restoration(job)


@pytest.mark.parametrize('fault',['extra_pair','duplicate_binding','lost_delete_ack'])
def test_view_inverse_ledger_overflow_duplicate_or_lost_ack_retains_fixtures(rollback_job,fault):
    job=native_shaped_ledger(rollback_job)
    steps=job['mutation']['verification']['native_steps']
    if fault=='extra_pair':
        for phase in ('pending','returned'):
            steps.insert(-2,dict(name='rectangle_unplanned_inverse',phase=phase,evidence={}))
    elif fault=='duplicate_binding':
        for row in steps:
            if row['name']=='rectangle_bind_annotation_view_feature_1':
                row['name']='rectangle_bind_annotation_view_feature_0'
    else:
        steps[:]=[row for row in steps if not (
            row['name']=='rectangle_restore_delete_annotation_view' and row['phase']=='returned')]
    for i,row in enumerate(steps,1):row['sequence']=i
    assert not helper.verified_rectangle_restoration(job)
