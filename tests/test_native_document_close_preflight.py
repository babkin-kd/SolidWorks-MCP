"""Exercise actual close verifier preflight up to its first native boundary."""
import argparse,ast,hashlib,json,os,sys,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_native_document_save_verifier import extract_function,NativeBoundaryReached


@pytest.fixture
def close_preflight(tmp_path,monkeypatch):
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    source=scripts/'verify_native_document_close.py';folder=tmp_path/'scripts';folder.mkdir()
    names=(source.name,'verify_geometry_reads.py','verify_native_document_save.py','verifier_lifecycle.py')
    for name in names:(folder/name).write_bytes((scripts/name).read_bytes())
    wheel=dict(package_version='2.0.0.dev83',git_sha='a'*40,source_digest='b'*64,wheel_sha256='c'*64)
    reached=[]
    def native():reached.append(True);raise NativeBoundaryReached
    namespace=dict(argparse=argparse,Path=Path,hashlib=hashlib,json=json,os=os,time=time,
        __file__=str(folder/source.name),validate_wheel=lambda *args,**kwargs:dict(wheel),
        installed_identity=lambda value:tmp_path/'entry.exe',pythoncom=SimpleNamespace(CoInitialize=native),
        INTERNAL_CASES=12,PUBLIC_CASES=10)
    main=extract_function(source,'main',namespace)
    report=dict(accepted=True,scope='internal_native_close_clean_v1',cases=[{'passed':True} for _ in range(12)],
        wheel=dict(wheel),verifier_hashes={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in names})
    prior=tmp_path/'prior.json';state=tmp_path/'work'/'new'
    monkeypatch.delenv('PYTHONPATH',raising=False)
    def args(optin=True,public=True):
        values=[str(source),'--wheel',str(tmp_path/'candidate.whl'),'--expected-version',wheel['package_version'],
                '--expected-git-sha',wheel['git_sha'],'--state-dir',str(state)]
        if optin:values.append('--run-solidworks')
        if public:values+=['--public','--internal-report',str(prior)]
        monkeypatch.setattr(sys,'argv',values)
        prior.write_text(json.dumps(report),encoding='utf8')
    return SimpleNamespace(main=main,args=args,report=report,state=state,reached=reached)


def test_valid_receipt_reaches_native_boundary(close_preflight):
    p=close_preflight;p.args()
    with pytest.raises(NativeBoundaryReached):p.main()
    assert p.state.is_dir() and p.reached==[True]


@pytest.mark.parametrize('fault',['optin','pythonpath','wheel','scope','count','failed_case','verifier_hash','existing_state'])
def test_invalid_close_preflight_never_enters_cad(close_preflight,monkeypatch,fault):
    p=close_preflight
    if fault=='wheel':p.report['wheel']['wheel_sha256']='d'*64
    if fault=='scope':p.report['scope']='public_native_close_clean_v1'
    if fault=='count':p.report['cases'].pop()
    if fault=='failed_case':p.report['cases'][0]['passed']=False
    if fault=='verifier_hash':p.report['verifier_hashes']['verifier_lifecycle.py']='d'*64
    if fault=='existing_state':p.state.mkdir(parents=True)
    p.args(optin=fault!='optin')
    if fault=='pythonpath':monkeypatch.setenv('PYTHONPATH','src')
    with pytest.raises((AssertionError,SystemExit)):p.main()
    assert not p.reached
