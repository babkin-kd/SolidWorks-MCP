"""Real coordinator stale refusal, artificial geometry and no CAD access."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from test_rectangle_native_verifier import configured,execution,sketch_proof,extrusion_proof,empty_adapter
from test_rectangle_construction_execution import run


path=Path(__file__).resolve().parents[1]/'scripts/verifier_rectangle_prewrite.py'
spec=importlib.util.spec_from_file_location('rectangle_prewrite_gate',path)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


@pytest.fixture
def stale(configured):
    x=configured;before=deepcopy(x.adapter.state)
    job=run(x,revision='rev_stale')
    assert job['status']=='failed' and job['error']['code']=='stale_revision'
    assert job.get('mutation') is None and x.adapter.dispatches==0 and x.adapter.guard_count==0
    assert x.adapter.state==before
    return job


def test_actual_precheckpoint_stale_refusal_binds_exact_request(stale):
    assert helper.verified_rectangle_prewrite(stale,expected_code='stale_revision',
        expected_arguments=stale['payload']['arguments'])


@pytest.mark.parametrize('fault',['unknown','wrong_code','untrusted_code','wrong_arguments','checkpoint',
    'requires_reconciliation','opaque','success','wrong_operation'])
def test_unconfirmed_or_other_request_is_not_prewrite_admission(stale,fault):
    job=deepcopy(stale);args=deepcopy(stale['payload']['arguments']);code='stale_revision'
    if fault=='unknown':job['status']='unknown'
    elif fault=='wrong_code':job['error']['code']='native_failed'
    elif fault=='untrusted_code':code=job['error']['code']='native_failed'
    elif fault=='wrong_arguments':args['document_id']='foreign'
    elif fault=='checkpoint':job['mutation']={'phase':'not_started'}
    elif fault=='requires_reconciliation':job['error']['requires_reconciliation']=True
    elif fault=='opaque':job['native']=object()
    elif fault=='success':job['status']='succeeded'
    else:job['operation']='document.close_native'
    assert not helper.verified_rectangle_prewrite(job,expected_code=code,expected_arguments=args)
