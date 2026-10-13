"""Installed public-driver preflight and terminal report safety; no CAD."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from test_b2_public_route import final_evidence,original
from test_b2_public_contract import leaf_jobs,execution,leaf,extrusion_proof,proof,case,domain

scripts=str(Path(__file__).resolve().parents[1]/'scripts')
sys.path.insert(0,scripts)
try:
    import verify_b2_public as helper
finally:sys.path.remove(scripts)


@pytest.fixture
def completed(final_evidence):
    evidence=final_evidence
    labels=['B2-public-depth12-full9600','B2-public-Russian-name-same-reference',
        'B2-public-suppress-full-state','B2-public-return-full-state',
        'B2-public-leaf-preview-delete-replay-retired-ID']
    evidence['cases']=[dict(label=label,passed=True) for label in labels]
    return dict(phase='terminal',native_calls_live=False,public_rectangle_passed=True,
        own_cleanup_verified=True,baseline_restored=True,supervised_cleanup_verified=True,
        owned_documents=[],original_baseline=dict(documents=[]),restored_baseline=dict(documents=[]),
        original_application=dict(visible=True),restored_application=dict(visible=True),
        captures=[dict(status='returned')],after_base_extension=evidence,extrusion_job=original(evidence))


def test_terminal_positive_never_accepts_whole_b2_or_authorizes_another_mutation(completed,monkeypatch):
    monkeypatch.syspath_prepend(scripts)
    from verifier_b2_public_route import compare_b2_state
    preserved=deepcopy(completed)
    # Artificial domain fixtures use their declared synthetic metadata; the
    # actual native path uses the separate self-hash/canonical mapping gate.
    outcome=helper.complete_public_positive(completed,state_comparator=compare_b2_state)
    assert outcome==dict(accepted=False,native_b2_accepted=False,public_mcp_accepted=False,
                         public_positive_case_passed=True)
    assert completed==preserved


def test_native_default_never_adopts_artificial_counter_metadata_as_native_proof(completed,monkeypatch):
    monkeypatch.syspath_prepend(scripts)
    # The artificial leaf domain uses literal target IDs/metadata. It proves
    # domain behavior, but cannot pass the actual native hash/mapping gate.
    with pytest.raises(ValueError):helper.complete_public_positive(completed)


@pytest.mark.parametrize('fault',['running','live','retained','held','no_cleanup','no_baseline',
    'sdk_live','foreign_document','changed_baseline','changed_application','pending_capture',
    'duplicate_case','failed_case','missing_case','extension_not_completed'])
def test_terminal_flags_or_partial_cases_cannot_claim_public_positive(completed,fault):
    row=completed
    if fault=='running':row['phase']='leaf_delete'
    elif fault=='live':row['native_calls_live']=True
    elif fault=='retained':row['retained_process']=True
    elif fault=='held':row['lifecycle_hold']=True
    elif fault=='no_cleanup':row['own_cleanup_verified']=False
    elif fault=='no_baseline':row['baseline_restored']=False
    elif fault=='sdk_live':row['supervised_cleanup_verified']=False
    elif fault=='foreign_document':row['owned_documents']=['unclosed-control']
    elif fault=='changed_baseline':row['restored_baseline']['foreign']=True
    elif fault=='changed_application':row['restored_application']['visible']=False
    elif fault=='pending_capture':row['captures'][0]['status']='running'
    elif fault=='duplicate_case':row['after_base_extension']['cases'][0]=deepcopy(row['after_base_extension']['cases'][1])
    elif fault=='failed_case':row['after_base_extension']['cases'][0]['passed']=False
    elif fault=='missing_case':row['after_base_extension']['cases'].pop()
    else:row['after_base_extension']['positive_case_passed']=False
    with pytest.raises(ValueError):helper.complete_public_positive(row)


def arguments(state):
    return ['--run-solidworks','--state-dir',str(state),'--wheel','unused.whl',
        '--expected-version','2.0.0.dev96','--expected-git-sha','f'*40,
        '--positive-report','unused-positive.json','--positive-report-sha256','a'*64,
        '--faults-report','unused-faults.json','--faults-report-sha256','b'*64]


@pytest.mark.parametrize('captures',[[],None,({'status':'returned'},),[{}],[None]])
def test_absent_or_malformed_capture_evidence_cannot_pass_public_completion(completed,captures):
    completed['captures']=captures
    with pytest.raises(ValueError,match='Nonempty normally returned native captures'):
        helper.complete_public_positive(completed,
            state_comparator=lambda *_:pytest.fail('Missing captures must fail before final state comparison'))


def test_missing_opt_in_prevents_even_state_directory_or_native_setup(tmp_path):
    state=tmp_path/'untouched'
    with pytest.raises(ValueError,match='Explicit'):
        helper.main(arguments(state)[1:])
    assert not state.exists()


def test_rejected_installed_preflight_never_enters_native_owner(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'work').mkdir()
    state=tmp_path/'work'/'public-test'
    def reject(*args,**kwargs):raise ValueError('Exact wheel/report mismatch')
    monkeypatch.setitem(sys.modules,'verifier_b2_public_preflight',NS(preflight=reject))
    monkeypatch.syspath_prepend(scripts)
    import verify_rectangle_stages_public
    events=[]
    monkeypatch.setattr(verify_rectangle_stages_public,'_native_run',lambda *_a,**_k:events.append('native'))
    with pytest.raises(ValueError,match='wheel/report mismatch'):helper.main(arguments(state))
    assert events==[]
    report=json.loads((state/'report.json').read_text(encoding='utf8'))
    assert report['phase']=='preflight_failed' and report['accepted'] is False
    assert report['native_calls_live'] is False and report['owned_documents']==[]


def test_prerequisite_scope_never_overwrites_installed_public_report_identity(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'work').mkdir()
    state=tmp_path/'work'/'public-scope'
    monkeypatch.syspath_prepend(scripts)
    evidence=dict(scope='b2_public_prerequisite_preflight_v1',accepted=False,prerequisite_gate_verified=True)
    monkeypatch.setitem(sys.modules,'verifier_b2_public_preflight',NS(preflight=lambda _:deepcopy(evidence)))
    import verify_rectangle_stages_public
    def native(*args,**kwargs):
        assert kwargs['terminal_acceptance'] is False
        raise RuntimeError('Synthetic native boundary, no CAD')
    monkeypatch.setattr(verify_rectangle_stages_public,'_native_run',native)
    with pytest.raises(RuntimeError,match='Synthetic native boundary'):helper.main(arguments(state))
    report=json.loads((state/'report.json').read_text(encoding='utf8'))
    assert report['scope']=='installed_b2_public_positive_only_v1'
    assert report['prerequisite_preflight']==evidence
    assert report['accepted'] is False
