"""Check the native verifier control plane and public chain before spending CAD."""
import asyncio,importlib
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    v=importlib.import_module('verify_component_reads')
    monkeypatch.delenv('PYTHONPATH',raising=False)
    monkeypatch.setattr(v.binding,'connect',lambda **kw:pytest.fail('No CAD in pure verifier tests'))
    return v


def test_native_optin_precedes_wheel_and_filesystem_effects(verifier,monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['components','--wheel','missing','--expected-version','dev','--expected-git-sha','a'*40,'--state-dir',str(tmp_path/'state')])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *a,**kw:pytest.fail('No wheel before optin'))
    with pytest.raises(SystemExit) as exc:verifier.main()
    assert exc.value.code==2 and not (tmp_path/'state').exists()


def test_body_get_spec_omits_implicit_instance_and_never_mutates(verifier):
    p=verifier.SPECS['component_body_get'].payload(dict(request_id='r',timeout_s=0.,document_id='d',configuration='Основная',
        expected_observation_revision='o',component_id='c',body_id='b'))
    assert p['mutates'] is False and p['arguments']['component_id']=='c' and p['arguments']['body_id']=='b'
    assert 'request_id' not in p['arguments'] and 'timeout_s' not in p['arguments']


def test_whole_public_flow_payload_checks_with_protocol_fake(verifier,monkeypatch,tmp_path):
    paths=[(tmp_path/name).resolve() for name in ('Деталь.sldprt','Чужая.sldprt','Подсборка.sldasm')]
    rows=[dict(component_id='main',component_path='Деталь-1',referenced_path=str(paths[0]),referenced_configuration='Основная',parent_component_id=None),
        dict(component_id='variant',component_path='Деталь-2',referenced_path=str(paths[0]),referenced_configuration='Вариант',parent_component_id=None,
            transform=dict(origin_mm=[50.,10.,20.],axes_in_assembly=[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]])),
        dict(component_id='sub',component_path='Подсборка-1',referenced_path=str(paths[2]),referenced_configuration='Основная',parent_component_id=None),
        dict(component_id='nested',component_path='Подсборка-1/Деталь-1',referenced_path=str(paths[0]),referenced_configuration='Вариант',parent_component_id='sub',transform=dict(origin_mm=[130.,0.,0.]))]
    body=dict(body_id='solid',component_id='variant',body_type='solid',bounding_box_mm=dict(approximate=True,min_mm=[0.,0.,0.],max_mm=[20.,10.,5.]))
    surface=dict(body_id='surface',component_id='variant',body_type='surface')
    calls=[];store={};models=[NS(identity=object(),GetTitle=lambda:'Контрольная модель') for _ in range(4)]
    async def context(model):return dict(document_id='doc',configuration='Основная',expected_observation_revision='obs')
    async def safe():pass
    async def read(tool,args):
        calls.append((tool,args));request=args.get('request_id',str(len(calls)))
        if request in store:return store[request]
        error=None
        if tool=='component_list':data=dict(scope='resolved_assembly_instance_reads_v1',length_unit='mm',transform_target_frame='assembly_model',implicit_resolution=False,total_count=4,items=rows)
        elif tool=='component_get':data=dict(component=rows[1])
        elif tool=='component_body_list':data=dict(body_coordinate_frame='component_model',includes_hidden_bodies=True,total_count=2,items=[body,surface])
        elif tool=='component_body_get':
            data=dict(items=[body])
            if args['component_id']=='main':error=dict(code='object_component_mismatch')
        else:pytest.fail(tool)
        result=dict(status='failed' if error else 'succeeded',operation_id=request,data=None if error else data,error=error);store[request]=result;return result
    monkeypatch.setattr(verifier,'source_state',lambda *args:None)
    report={'cases':[]}
    asyncio.run(verifier.cases(read,context,safe,None,None,models,None,paths,report,lambda:None,True))
    assert len(report['cases'])==verifier.PUBLIC_CASES==6 and len(calls)==7
    assert calls[-1][1]==calls[-2][1]
