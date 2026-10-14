"""Point acceptance opt-in, protocol mapping and analytical coordinate oracles."""
import asyncio
import importlib
import math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    v=importlib.import_module('verify_component_point_distance');monkeypatch.delenv('PYTHONPATH',raising=False)
    monkeypatch.setattr(v.binding,'connect',lambda **kwargs:pytest.fail('No CAD in pure verifier tests'))
    return v


def test_native_optin_before_any_wheel_or_cad(verifier,monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['point','--wheel','missing','--expected-version','dev','--expected-git-sha','a'*40,'--state-dir',str(tmp_path/'state')])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *args,**kwargs:pytest.fail('No wheel before optin'))
    with pytest.raises(SystemExit) as exc:verifier.main()
    assert exc.value.code==2 and not (tmp_path/'state').exists()


def test_fixture_already_active_requires_readback_without_redundant_switch(verifier,monkeypatch):
    monkeypatch.setattr(verifier.binding,'wrap',lambda obj,cls:obj)
    model=NS(GetActiveConfiguration=lambda:NS(Name='Основная'),ShowConfiguration2=lambda name:pytest.fail('No redundant switch'))
    verifier.ensure_fixture_configuration(model,NS(IConfiguration=object),'Основная')


def test_fixture_switches_only_when_needed_and_confirms_readback(verifier,monkeypatch):
    monkeypatch.setattr(verifier.binding,'wrap',lambda obj,cls:obj)
    state=NS(Name='Вариант');calls=[]
    def switch(name):calls.append(name);state.Name=name;return True
    model=NS(GetActiveConfiguration=lambda:state,ShowConfiguration2=switch)
    verifier.ensure_fixture_configuration(model,NS(IConfiguration=object),'Основная')
    assert calls==['Основная']


@pytest.mark.parametrize('returns',[False,True])
def test_fixture_wrong_config_is_never_accepted_from_return_value(verifier,monkeypatch,returns):
    monkeypatch.setattr(verifier.binding,'wrap',lambda obj,cls:obj)
    model=NS(GetActiveConfiguration=lambda:NS(Name='Вариант'),ShowConfiguration2=lambda name:returns)
    with pytest.raises(AssertionError):verifier.ensure_fixture_configuration(model,NS(IConfiguration=object),'Основная')


def test_point_spec_maps_frame_default_and_explicit_context(verifier):
    args=dict(request_id='r',timeout_s=0.,document_id='d',configuration='Основная',expected_observation_revision='o',component_id='c',point_mm=[1.,2.,3.])
    spec=verifier.SPECS['measurement_get_component_point_distance'];payload=spec.payload(args)
    assert spec.operation=='measurement.component_point_distance' and payload['mutates'] is False
    assert payload['arguments']=={**{k:v for k,v in args.items() if k not in ('request_id','timeout_s')},'frame':None}


def result(point,nearest,location,distance,frame=None):
    def root(p):return p if frame is None else [50.-p[1],10.+p[0],20.+p[2]]
    return dict(measurement_scope='resolved_part_component_point_distance_v1',length_unit='mm',
        coordinate_frame='assembly_model' if frame is None else 'explicit_rigid_frame',includes_hidden_bodies=True,
        includes_surface_bodies=False,distance_semantics='minimum_to_individual_solid_boundary',
        point_location=location,inside=True if location=='inside' else False if location=='outside' else None,
        boundary_tolerance_mm=1e-5,distance_mm=distance,point_mm=point,nearest_mm=nearest,
        nearest_assembly_mm=root(nearest),point_assembly_mm=root(point),nearest_body_id='body',nearest_face_id='face',
        frame=frame,component={'component_id':'variant'},solid_body_count=1,face_count=6)


def test_oracle_positive_inside_boundary_and_trimmed_corner(verifier):
    good=result([45.,20.,22.5],[45.,20.,20.],'inside',2.5)
    verifier.check_point(good,2.5,'inside',good['point_mm'])
    with pytest.raises(AssertionError):verifier.check_point(dict(good,distance_mm=0.),2.5,'inside',good['point_mm'])
    boundary=result([50.,20.,22.5],[50.,20.,22.5],'boundary',0.)
    verifier.check_point(boundary,0.,'boundary',boundary['point_mm'])
    with pytest.raises(AssertionError):verifier.check_point(dict(boundary,inside=False),0.,'boundary',boundary['point_mm'])
    frame=verifier.FRAME;corner=result([30.,20.,20.],[20.,10.,5.],'outside',math.sqrt(425.),frame)
    verifier.check_point(corner,math.sqrt(425.),'outside',corner['point_mm'],[20.,10.,5.],frame)


def test_public_protocol_chain_before_native(verifier,monkeypatch,tmp_path):
    paths=[(tmp_path/name).resolve() for name in ('Деталь.sldprt','Цилиндр.sldprt','Подсборка.sldasm')]
    rows=[dict(component_id='main',referenced_path=str(paths[0]),referenced_configuration='Основная',component_path='Деталь-1',referenced_document_type='part'),
        dict(component_id='variant',referenced_path=str(paths[0]),referenced_configuration='Вариант',component_path='Деталь-2',referenced_document_type='part',hidden=True,transform={'origin_mm':[50.,10.,20.]}),
        dict(component_id='nested',referenced_path=str(paths[0]),referenced_configuration='Вариант',component_path='Подсборка-1/Деталь-1',referenced_document_type='part'),
        dict(component_id='curve',referenced_path=str(paths[1]),referenced_configuration='Основная',component_path='Цилиндр-1',referenced_document_type='part'),
        dict(component_id='sub',referenced_path=str(paths[2]),referenced_configuration='Основная',component_path='Подсборка-1',referenced_document_type='assembly')]
    calls=[];saved={}
    async def context(model):return dict(document_id='d',configuration='Основная',expected_observation_revision='o')
    async def safe():pass
    async def read(tool,args):
        calls.append((tool,args));request=args.get('request_id',str(len(calls)))
        if request in saved:return saved[request]
        if tool=='component_list':data={'items':rows}
        elif tool=='component_topology_get':data={'object':{'kind':'face','component_id':'variant','body_id':'body'}}
        else:
            assert tool=='measurement_get_component_point_distance'
            point=args['point_mm'];frame=args['frame']
            if frame is not None:data=result(point,[20.,10.,5.],'outside',math.sqrt(425.),frame)
            elif point==[55.,20.,22.5]:data=result(point,[50.,20.,22.5],'outside',5.)
            elif point==[45.,20.,22.5]:data=result(point,[45.,20.,20.],'inside',2.5)
            else:data=result(point,point,'boundary',0.)
        value=dict(status='succeeded',data=data,error=None,operation_id=request);saved[request]=value;return value
    monkeypatch.setattr(verifier,'source_state',lambda *args:None);report={'cases':[]}
    asyncio.run(verifier.cases(read,context,safe,None,None,[NS() for _ in range(4)],None,paths,report,lambda:None,True))
    assert len(report['cases'])==verifier.PUBLIC_CASES==6 and len(saved)==7
