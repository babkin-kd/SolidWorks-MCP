"""Public verifier protocol/preflight; no actual CAD or process started."""
import importlib
import json
from pathlib import Path
import pytest


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    module=importlib.import_module('verify_mass_mcp')
    monkeypatch.setattr(module.binding,'connect',lambda **kw:pytest.fail('No native connection'))
    monkeypatch.delenv('PYTHONPATH',raising=False)
    return module


def test_supervisor_payload_matches_public_mass_optional_defaults(verifier):
    args=dict(request_id='r',document_id='doc',configuration='Основная',expected_observation_revision='obs',timeout_s=0.)
    prepare=verifier.SPECS['measurement_prepare_mass'].payload(args)
    measure=verifier.SPECS['measurement_get_mass'].payload({**args,'expected_revision':'rev'})
    assert prepare['arguments']=={k:v for k,v in args.items() if k not in ('request_id','timeout_s')}|{'body_id':None}
    assert not prepare['mutates'] and measure['mutates'] and measure['context']['expected_revision']=='rev'
    body=verifier.SPECS['body_list'].payload(args)
    assert body['arguments']['kind']=='body' and body['arguments']['body_type']=='all'


def test_explicit_opt_in_before_wheel_or_native(verifier,monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['verify_mass_mcp','--wheel','missing.whl','--expected-version','dev',
        '--expected-git-sha','a'*40,'--internal-report','missing.json','--state-dir',str(tmp_path/'state')])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *a,**kw:pytest.fail('No wheel before opt-in'))
    with pytest.raises(SystemExit) as error:verifier.main()
    assert error.value.code==2


@pytest.mark.parametrize('invalid',['unaccepted','wrong_scope','different_wheel'])
def test_internal_candidate_gate_before_any_native_effect(verifier,monkeypatch,tmp_path,invalid):
    wheel=dict(git_sha='a'*40,source_digest='b'*64,package_version='dev',wheel_sha256='c'*64)
    report=dict(accepted=True,scope='internal_guarded_part_mass_native_v1',cases=[{}]*22,wheel=wheel.copy())
    if invalid=='unaccepted':report['accepted']=False
    if invalid=='wrong_scope':report['scope']='internal_part_mass_read_native_v1'
    if invalid=='different_wheel':report['wheel']['git_sha']='d'*40
    path=tmp_path/'internal.json';path.write_text(json.dumps(report))
    state=tmp_path/'state'
    monkeypatch.setattr('sys.argv',['verify_mass_mcp','--run-solidworks','--wheel','candidate.whl','--expected-version','dev',
        '--expected-git-sha','a'*40,'--internal-report',str(path),'--state-dir',str(state)])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *a,**kw:wheel)
    monkeypatch.setattr(verifier,'installed_identity',lambda *a:tmp_path/'entry.exe')
    with pytest.raises(AssertionError):verifier.main()
    assert not state.exists()
