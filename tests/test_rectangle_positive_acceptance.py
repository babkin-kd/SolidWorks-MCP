"""Manifest/wheel/chain preflight; CAD or stage oracle acceptance is separate."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:
    spec=importlib.util.spec_from_file_location('rectangle_positive_preflight',scripts/'verifier_rectangle_positive_acceptance.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
finally:sys.path.remove(str(scripts))


@pytest.fixture
def evidence(monkeypatch):
    # This suite isolates the preflight. Real JobStore/admission and native-shaped
    # snapshots are covered by test_rectangle_native_verifier/snapshot suites.
    monkeypatch.setattr(helper,'verified_rectangle_job',lambda row:row.get('exact_stage_proof') is True)
    monkeypatch.setattr(helper,'validated_rectangle_snapshot',lambda row:row)
    wheel=dict(package_version='2.0.0.dev91',git_sha='a'*40,source_digest='b'*64)
    hashes={'trusted-helper.py':'c'*64}
    prior=dict(scope='installed_rectangle_stages_positive_only',accepted=False,
        positive_case_passed=True,phase='terminal',native_calls_live=False,
        wheel=deepcopy(wheel),package_origin_verified=True,verifier_hashes=hashes.copy(),
        own_cleanup_verified=True,baseline_restored=True,independent_native_readback_verified=True,
        owned_documents=[],original_baseline=['full baseline'],restored_baseline=['full baseline'],
        original_application={'current_directory':'original'},restored_application={'current_directory':'original'},
        cases=[dict(label=label,passed=True) for label in helper.POSITIVE_LABELS],
        captures=[dict(status='returned')],independent_volume_mm3=8000.,
        independent_sketch=dict(clone_state=dict(profile=helper.SKETCH),solid_body_count=0),
        independent_base=dict(clone_state=dict(profile=helper.BASE),solid_body_count=1),
        sketch_job=dict(exact_stage_proof=True,operation='sketch.create_rectangle',
            payload=dict(arguments=dict(document_id='target')),result=dict(value=dict(sketch_object_id='exact_sketch'))),
        extrusion_job=dict(exact_stage_proof=True,operation='part.extrude_rectangle',
            payload=dict(arguments=dict(document_id='target',sketch_object_id='exact_sketch'))))
    return prior,wheel,hashes


def test_terminal_finite_same_wheel_report_authorizes_only_next_native_cases(evidence):
    result=helper.validate_positive_report(*evidence)
    assert result['accepted'] and result['native_b1_accepted'] is False


@pytest.mark.parametrize('fault',['running','pending','retained','cleanup','baseline','application',
    'wheel','hashes','manifest','partial_capture','missing_stage_proof','foreign_sketch',
    'foreign_document','wrong_profile','extra_body','volume_bool','wrong_volume','premature_b1_acceptance'])
def test_partial_or_foreign_positive_evidence_cannot_start_new_native_cases(evidence,fault):
    prior,wheel,hashes=evidence
    if fault=='running':prior['phase']='sketch_job'
    elif fault=='pending':prior['native_calls_live']=True
    elif fault=='retained':prior['retained_process']=True
    elif fault=='cleanup':prior['owned_documents']=[{'document':'still retained'}]
    elif fault=='baseline':prior['restored_baseline']=['other']
    elif fault=='application':prior['restored_application']={}
    elif fault=='wheel':wheel['package_version']='2.0.0.dev90'
    elif fault=='hashes':hashes['trusted-helper.py']='changed'
    elif fault=='manifest':prior['cases'].pop()
    elif fault=='partial_capture':prior['captures'].append(dict(status='running'))
    elif fault=='missing_stage_proof':prior['extrusion_job']['exact_stage_proof']=False
    elif fault=='foreign_sketch':prior['extrusion_job']['payload']['arguments']['sketch_object_id']='foreign'
    elif fault=='foreign_document':prior['extrusion_job']['payload']['arguments']['document_id']='foreign'
    elif fault=='wrong_profile':prior['independent_sketch']['clone_state']['profile']=helper.BASE
    elif fault=='extra_body':prior['independent_base']['solid_body_count']=2
    elif fault=='volume_bool':prior['independent_volume_mm3']=True
    elif fault=='wrong_volume':prior['independent_volume_mm3']=9600.
    else:prior['accepted']=True
    with pytest.raises(ValueError):helper.validate_positive_report(prior,wheel,hashes)
