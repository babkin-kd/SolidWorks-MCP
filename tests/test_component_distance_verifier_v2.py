"""Acceptance control plane and independent analytical distance witnesses."""
import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    v=importlib.import_module('verify_component_distance');monkeypatch.delenv('PYTHONPATH',raising=False)
    monkeypatch.setattr(v.binding,'connect',lambda **kwargs:pytest.fail('No native effects in pure verifier tests'))
    return v


def test_optin_before_wheel_or_cad(verifier,monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['distance','--wheel','missing','--expected-version','dev','--expected-git-sha','a'*40,'--state-dir',str(tmp_path/'state')])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *args,**kwargs:pytest.fail('No wheel before optin'))
    with pytest.raises(SystemExit) as exc:verifier.main()
    assert exc.value.code==2 and not (tmp_path/'state').exists()


def test_spec_has_explicit_both_instances_and_is_passive(verifier):
    args=dict(request_id='r',document_id='d',configuration='Основная',expected_observation_revision='o',component_a_id='a',component_b_id='b',timeout_s=0.)
    payload=verifier.SPECS['measurement_get_component_distance'].payload(args)
    assert verifier.SPECS['measurement_get_component_distance'].operation=='measurement.component_distance' and payload['mutates'] is False
    assert payload['arguments']=={k:v for k,v in args.items() if k not in ('request_id','timeout_s')}


def value(distance,points):
    return dict(measurement_scope='resolved_part_component_distance_v1',coordinate_frame='assembly_model',length_unit='mm',
        includes_hidden_bodies=True,includes_surface_bodies=False,intersection_classification='not_provided',
        distance_mm=distance,closest_points_mm=points)


def test_oracle_rejects_axis_gap_wrong_frames_and_bad_witnesses(verifier):
    good=value(24.,[[176.,5.,0.],[200.,5.,0.]])
    verifier.check_distance(good,24.)
    for bad in [dict(good,distance_mm=36.),dict(good,coordinate_frame='component_model'),
                dict(good,closest_points_mm=[[176.,5.,0.],[201.,5.,0.]]),dict(good,includes_surface_bodies=True)]:
        with pytest.raises(AssertionError):verifier.check_distance(bad,24.)
    with pytest.raises(AssertionError):verifier.box_point([.05,.01,.02],[40.,10.,20.],[50.,30.,25.])


def test_public_protocol_chain_and_replay_without_native(verifier,monkeypatch,tmp_path):
    paths=[(tmp_path/x).resolve() for x in ['Деталь.sldprt','Цилиндр.sldprt','Подсборка.sldasm']]
    rows=[dict(component_id='main',referenced_path=str(paths[0]),referenced_configuration='Основная',component_path='Деталь-1',referenced_document_type='part'),
        dict(component_id='variant',referenced_path=str(paths[0]),referenced_configuration='Вариант',component_path='Деталь-2',hidden=True,transform=dict(origin_mm=[50.,10.,20.]),referenced_document_type='part'),
        dict(component_id='nested',referenced_path=str(paths[0]),referenced_configuration='Вариант',component_path='Подсборка-1/Деталь-1',referenced_document_type='part'),
        dict(component_id='sub',referenced_path=str(paths[2]),referenced_configuration='Основная',component_path='Подсборка-1',referenced_document_type='assembly'),
        dict(component_id='curve',referenced_path=str(paths[1]),referenced_configuration='Основная',component_path='Цилиндр-1',referenced_document_type='part')]
    byid={r['component_id']:r for r in rows};saved={};calls=[]
    async def context(model):return dict(document_id='doc',configuration='Основная',expected_observation_revision='o')
    async def safe():pass
    async def read(tool,args):
        calls.append((tool,args));request=args.get('request_id',str(len(calls)))
        if request in saved:return saved[request]
        error=None
        if tool=='component_list':data={'items':rows}
        else:
            assert tool=='measurement_get_component_distance'
            a,b=args['component_a_id'],args['component_b_id'];pair=(a,b)
            if b=='sub':data=None;error={'code':'unsupported_component_type'}
            else:
                distance,points={('main','variant'):(15.,[[45.,10.,5.],[45.,10.,20.]]),
                    ('variant','main'):(15.,[[45.,10.,20.],[45.,10.,5.]]),
                    ('main','nested'):(70.,[[60.,5.,2.5],[130.,5.,2.5]]),
                    ('nested','curve'):(0.,[[150.,0.,2.5],[150.,0.,2.5]])}[pair]
                data=value(distance,points);data.update(component_a=byid[a],component_b=byid[b],solid_body_counts=[2,1] if a=='main' else [1,1])
        result=dict(status='failed' if error else 'succeeded',data=data,error=error,operation_id=request)
        saved[request]=result;return result
    monkeypatch.setattr(verifier,'source_state',lambda *args:None);report={'cases':[]}
    asyncio.run(verifier.cases(read,context,safe,None,None,[NS() for _ in range(4)],None,paths,report,lambda:None,True))
    assert len(report['cases'])==verifier.PUBLIC_CASES==6
    assert calls[-2][1]['request_id']==calls[-3][1]['request_id']
