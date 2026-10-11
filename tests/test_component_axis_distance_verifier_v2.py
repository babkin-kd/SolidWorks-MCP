"""Native opt-in and public axis acceptance protocol/oracle without CAD."""
import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    v=importlib.import_module('verify_component_axis_distance');monkeypatch.delenv('PYTHONPATH',raising=False)
    monkeypatch.setattr(v.binding,'connect',lambda **kwargs:pytest.fail('No CAD in pure tests'))
    return v


def test_optin_before_wheel_or_cad(verifier,monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['axis','--wheel','missing','--expected-version','dev','--expected-git-sha','a'*40,'--state-dir',str(tmp_path/'state')])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *a,**kw:pytest.fail('No wheel before optin'))
    with pytest.raises(SystemExit) as exc:verifier.main()
    assert exc.value.code==2 and not (tmp_path/'state').exists()


def result(origin,direction,distance=5.,frame=None,cid='variant'):
    points=[[50.,10.,22.5],[55.,10.,22.5]] if frame is None else [[20.,5.,2.5],[25.,5.,2.5]]
    if distance==2.:points=[[156.,15.,0.],[158.,15.,0.]]
    root=points if frame is None else [[45.,30.,22.5],[45.,35.,22.5]]
    return dict(measurement_scope='resolved_part_component_axis_distance_v1',coordinate_frame='assembly_model' if frame is None else 'explicit_rigid_frame',
        length_unit='mm',axis_semantics='infinite_line',includes_hidden_bodies=True,includes_surface_bodies=False,
        intersection_classification='not_provided',distance_mm=distance,axis_origin_mm=origin,axis_direction=direction,
        closest_points_mm=points,closest_points_assembly_mm=root,component={'component_id':cid})


@pytest.mark.parametrize('change',[{'axis_semantics':'finite_segment'},{'axis_direction':[0.,2.,0.]},{'distance_mm':8.},
    {'closest_points_mm':[[50.,10.,22.5],[55.,10.,23.5]]},{'includes_surface_bodies':True}])
def test_oracle_refuses_wrong_geometry_or_semantics(verifier,change):
    origin=[55.,0.,22.5];direction=[0.,1.,0.];good=result(origin,direction)
    verifier.check_axis(good,5.,origin,direction)
    with pytest.raises(AssertionError):verifier.check_axis({**good,**change},5.,origin,direction)


def test_public_protocol_replay_defaults_and_failure_count(verifier,monkeypatch,tmp_path):
    paths=[(tmp_path/name).resolve() for name in ('Деталь.sldprt','Цилиндр.sldprt','Подсборка.sldasm')]
    rows=[dict(component_id='main',referenced_path=str(paths[0]),referenced_configuration='Основная',component_path='Деталь-1',referenced_document_type='part'),
        dict(component_id='variant',referenced_path=str(paths[0]),referenced_configuration='Вариант',component_path='Деталь-2',referenced_document_type='part',hidden=True),
        dict(component_id='nested',referenced_path=str(paths[0]),referenced_configuration='Вариант',component_path='Подсборка-1/Деталь-1',referenced_document_type='part'),
        dict(component_id='curve',referenced_path=str(paths[1]),referenced_configuration='Основная',component_path='Цилиндр-1',referenced_document_type='part'),
        dict(component_id='sub',referenced_path=str(paths[2]),referenced_configuration='Основная',component_path='Подсборка-1',referenced_document_type='assembly')]
    calls=[];saved={}
    async def context(model):return dict(document_id='d',configuration='Основная',expected_observation_revision='o')
    async def safe():pass
    async def read(tool,args):
        calls.append((tool,args));request=args.get('request_id',str(len(calls)))
        if request in saved:return saved[request]
        if tool=='component_list':value=dict(status='succeeded',data={'items':rows},error=None)
        else:
            assert tool=='measurement_get_component_axis_distance'
            if args['axis_direction']==[0.,0.,0.]:value=dict(status='failed',data=None,error={'code':'invalid_measurement_axis'})
            elif args['component_id']=='sub':value=dict(status='failed',data=None,error={'code':'unsupported_component_type'})
            else:value=dict(status='succeeded',error=None,data=result(args['axis_origin_mm'],args['axis_direction'],2. if args['component_id']=='curve' else 5.,args['frame'],args['component_id']))
        value['operation_id']=request;saved[request]=value;return value
    monkeypatch.setattr(verifier,'source_state',lambda *a:None);report={'cases':[]}
    asyncio.run(verifier.cases(read,context,safe,None,None,[NS() for _ in range(4)],None,paths,report,lambda:None,True))
    assert len(report['cases'])==verifier.PUBLIC_CASES==6 and len(saved)==7
    spec=verifier.SPECS['measurement_get_component_axis_distance']
    assert spec.payload({'request_id':'r','axis_origin_mm':[0.]*3,'axis_direction':[0.,1.,0.]})['arguments']['frame'] is None
