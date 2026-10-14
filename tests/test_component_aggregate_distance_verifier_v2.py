"""Opt-in/protocol and independent pair-count/frame oracles without CAD."""
import asyncio
import importlib
import math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    v=importlib.import_module('verify_component_aggregate_distance');monkeypatch.delenv('PYTHONPATH',raising=False)
    monkeypatch.setattr(v.binding,'connect',lambda **kwargs:pytest.fail('No CAD in pure tests'))
    return v


def test_explicit_native_optin_before_wheel_or_cad(verifier,monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['aggregate','--wheel','missing','--expected-version','dev','--expected-git-sha','a'*40,'--state-dir',str(tmp_path/'state')])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *a,**kw:pytest.fail('No wheel before opt-in'))
    with pytest.raises(SystemExit) as exc:verifier.main()
    assert exc.value.code==2 and not (tmp_path/'state').exists()


def value(ids,nearest,points,frame=None,solid_counts=None,shared=0):
    local=points if frame is None else [[sum(axis[k]*(p[k]-frame['origin_mm'][k]) for k in range(3)) for axis in frame['axes_in_model']] for p in points]
    counts=[len(x) for x in ids];pairs=math.prod(counts)
    return dict(measurement_scope='resolved_component_aggregate_distance_v1',coordinate_frame='assembly_model' if frame is None else 'explicit_rigid_frame',
        length_unit='mm',includes_hidden_bodies=True,includes_surface_bodies=False,intersection_classification='not_provided',
        distance_mm=math.dist(*points),closest_points_mm=local,closest_points_assembly_mm=points,leaf_component_ids=ids,
        leaf_component_counts=counts,solid_leaf_component_counts=counts,solid_body_counts=solid_counts or counts,
        evaluated_pair_count=pairs,native_pair_count=pairs-shared,shared_instance_pair_count=shared,
        nearest_component_a={'component_id':nearest[0]},nearest_component_b={'component_id':nearest[1]})


@pytest.mark.parametrize('change',[{'evaluated_pair_count':1},{'distance_mm':130.},{'coordinate_frame':'component_model'},
    {'nearest_component_a':{'component_id':'foreign'}},{'solid_body_counts':[1,1]},
    {'closest_points_assembly_mm':[[196.,0.,0.],[300.,0.,0.]]}])
def test_oracle_rejects_partial_pair_minimum_wrong_source_and_witnesses(verifier,change):
    good=value([['child_a','cylinder_a'],['child_b','cylinder_b']],['cylinder_a','child_b'],[[196.,0.,0.],[280.,0.,0.]])
    verifier.check_aggregate(good,84.,[2,2],[2,2])
    with pytest.raises(AssertionError):verifier.check_aggregate({**good,**change},84.,[2,2],[2,2])


def test_public_protocol_complete_targets_shared_zero_and_replay(verifier,monkeypatch,tmp_path):
    paths=[(tmp_path/name).resolve() for name in ('Деталь.sldprt','Цилиндр.sldprt','Подсборка.sldasm')]
    def row(cid,path,cfg,name,*,parent=None,x=0.,assembly=False,hidden=False):
        return dict(component_id=cid,referenced_path=str(path),referenced_configuration=cfg,component_path=name,
            referenced_document_type='assembly' if assembly else 'part',parent_component_id=parent,transform={'origin_mm':[x,0.,0.]},hidden=hidden)
    rows=[row('main',paths[0],'Основная','Деталь-1'),row('var',paths[0],'Вариант','Деталь-2'),
        row('a',paths[2],'Основная','Подсборка-1',x=99.99999999999999,assembly=True),row('b',paths[2],'Основная','Подсборка-2',x=250.,assembly=True),
        row('child_a',paths[0],'Вариант','Подсборка-1/Деталь-1',parent='a',x=130.),row('cylinder_a',paths[1],'Основная','Подсборка-1/Цилиндр-1',parent='a',x=190.,hidden=True),
        row('child_b',paths[0],'Вариант','Подсборка-2/Деталь-1',parent='b',x=280.),row('cylinder_b',paths[1],'Основная','Подсборка-2/Цилиндр-1',parent='b',x=340.),row('root_cylinder',paths[1],'Основная','Цилиндр-1',x=150.)]
    saved={};calls=[]
    async def context(model):return dict(document_id='d',configuration='Основная',expected_observation_revision='o')
    async def safe():pass
    async def read(tool,args):
        calls.append((tool,args));request=args.get('request_id',str(len(calls)))
        if request in saved:return saved[request]
        if tool=='component_list':data={'items':rows}
        elif args['configuration']=='Вариант':
            result={'status':'failed','operation_id':request,'data':None,'error':{'code':'configuration_not_active'}};saved[request]=result;return result
        else:
            assert tool=='measurement_get_component_aggregate_distance'
            a,b=args['component_a_id'],args['component_b_id']
            if a=='main':data=value([['main'],['child_a','cylinder_a']],['main','child_a'],[[60.,0.,0.],[130.,0.,0.]],solid_counts=[2,2])
            elif b=='child_a':data=value([['child_a','cylinder_a'],['child_a']],['child_a','child_a'],[[150.,0.,0.],[150.,0.,0.]],shared=1)
            else:data=value([['child_a','cylinder_a'],['child_b','cylinder_b']],['cylinder_a','child_b'],[[196.,0.,0.],[280.,0.,0.]],frame=args['frame'])
            data.update(component_a={'component_id':a},component_b={'component_id':b})
        result={'status':'succeeded','operation_id':request,'data':data,'error':None};saved[request]=result;return result
    monkeypatch.setattr(verifier,'source_state',lambda *a:None);report={'cases':[]}
    asyncio.run(verifier.cases(read,context,safe,None,None,[NS() for _ in range(4)],None,paths,report,lambda:None,True))
    assert len(report['cases'])==verifier.PUBLIC_CASES==6 and len(saved)==7
    spec=verifier.SPECS['measurement_get_component_aggregate_distance']
    assert spec.operation=='measurement.component_aggregate_distance' and spec.payload({'request_id':'r'})['arguments']['frame'] is None
