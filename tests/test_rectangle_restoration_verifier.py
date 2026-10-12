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
