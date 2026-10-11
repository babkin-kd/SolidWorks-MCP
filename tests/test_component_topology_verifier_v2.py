"""Native verifier control plane and analytical local-coordinate/curve oracles."""
import asyncio,importlib,math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    v=importlib.import_module('verify_component_topology');monkeypatch.delenv('PYTHONPATH',raising=False)
    monkeypatch.setattr(v.binding,'connect',lambda **kwargs:pytest.fail('No CAD in pure verifier tests'))
    return v


def test_optin_precedes_wheel_and_native_effects(verifier,monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['topology','--wheel','missing','--expected-version','dev','--expected-git-sha','a'*40,'--state-dir',str(tmp_path/'state')])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *args,**kwargs:pytest.fail('No wheel before native optin'))
    with pytest.raises(SystemExit) as exc:verifier.main()
    assert exc.value.code==2 and not (tmp_path/'state').exists()


def test_topology_spec_owns_both_instance_and_body_and_is_read(verifier):
    for tool,kind in [('component_face_list','face'),('component_edge_list','edge')]:
        payload=verifier.SPECS[tool].payload(dict(request_id='r',timeout_s=0.,document_id='d',configuration='Основная',expected_observation_revision='o',component_id='c',body_id='b'))
        assert payload['mutates'] is False and payload['arguments']['kind']==kind
        assert payload['arguments']['component_id']=='c' and payload['arguments']['body_id']=='b'
        assert payload['arguments']['limit']==100 and payload['arguments']['cursor']==''


def cylinder(kind):
    common=dict(topology_scope='resolved_assembly_instance_topology_reads_v1',object_coordinate_frame='component_model',length_unit='mm',area_unit='mm2',component={'component_id':'c'},body_id='b')
    if kind=='edge':items=[dict(object_id=f'e{i}',component_id='c',body_id='b',kind=kind,curve_type='circle',length_mm=12.*math.pi,start_mm=[6.,y,0.],end_mm=[6.,y,0.]) for i,y in enumerate((0.,30.))]
    else:items=[dict(object_id=f'f{i}',component_id='c',body_id='b',kind=kind,area_mm2=area) for i,area in enumerate((36.*math.pi,36.*math.pi,360.*math.pi))]
    return dict(common,items=items,total_count=len(items))


def test_native_curve_oracle_closed_circle_length_and_local_axes(verifier):
    verifier.check_topology(cylinder('face'),'face','cylinder')
    value=cylinder('edge');verifier.check_topology(value,'edge','cylinder')
    value['items'][0]['start_mm'][0]+=50.
    with pytest.raises(AssertionError):verifier.check_topology(value,'edge','cylinder')


def test_public_chain_with_protocol_fake_before_native_run(verifier,monkeypatch,tmp_path):
    paths=[(tmp_path/x).resolve() for x in ['Деталь.sldprt','Цилиндр.sldprt','Подсборка.sldasm']]
    rows=[dict(component_id='main',referenced_path=str(paths[0]),referenced_configuration='Основная',component_path='Деталь-1'),
        dict(component_id='variant',referenced_path=str(paths[0]),referenced_configuration='Вариант',component_path='Деталь-2',hidden=True,transform=dict(origin_mm=[50.,10.,20.])),
        dict(component_id='nested',referenced_path=str(paths[0]),referenced_configuration='Вариант',component_path='Подсборка-1/Деталь-1'),
        dict(component_id='sub',referenced_path=str(paths[2]),referenced_configuration='Основная',component_path='Подсборка-1'),
        dict(component_id='curve',referenced_path=str(paths[1]),referenced_configuration='Основная',component_path='Цилиндр-1')]
    def bodies(cid):
        return [dict(body_id=cid+'_solid',body_type='solid',bounding_box_mm={'min_mm':[0.,0.,0.]}),dict(body_id=cid+'_surface',body_type='surface')] if cid!='curve' else [dict(body_id='curve_solid',body_type='solid')]
    def topology(kind,cid,bid):
        common=dict(topology_scope='resolved_assembly_instance_topology_reads_v1',object_coordinate_frame='component_model',length_unit='mm',area_unit='mm2',component={'component_id':cid},body_id=bid)
        surface=bid.endswith('surface')
        if kind=='face':items=[dict(object_id=f'{bid}_f{i}',kind=kind,component_id=cid,body_id=bid,area_mm2=area) for i,area in enumerate([150.] if surface else [50.,50.,100.,100.,200.,200.])]
        else:
            lengths=[10.,10.,15.,15.] if surface else [5.]*4+[10.]*4+[20.]*4
            points=([80.,0.,0.],[95.,0.,0.]) if surface else ([0.,0.,0.],[5.,0.,0.])
            items=[dict(object_id=f'{bid}_e{i}',kind=kind,component_id=cid,body_id=bid,length_mm=value,start_mm=list(points[0]),end_mm=list(points[1])) for i,value in enumerate(lengths)]
        return dict(common,items=items,total_count=len(items))
    calls=[];store={};objects={};models=[NS(identity=object()) for _ in range(4)]
    async def context(model):return dict(document_id='doc',configuration='Основная',expected_observation_revision='o')
    async def safe():pass
    async def read(tool,args):
        calls.append((tool,args));request=args.get('request_id',str(len(calls)))
        if request in store:return store[request]
        error=None
        if tool=='component_list':data={'items':rows}
        elif tool=='component_body_list':data={'items':bodies(args['component_id'])}
        elif tool in ('component_face_list','component_edge_list'):
            kind='face' if tool=='component_face_list' else 'edge';data=topology(kind,args['component_id'],args['body_id']);objects.update({x['object_id']:x for x in data['items']})
        elif tool=='component_topology_get':
            obj=objects[args['object_id']];data={'object':obj}
            if obj['component_id']!=args['component_id']:error={'code':'object_component_mismatch'}
        else:pytest.fail(tool)
        value=dict(status='failed' if error else 'succeeded',operation_id=request,data=None if error else data,error=error);store[request]=value;return value
    monkeypatch.setattr(verifier,'source_state',lambda *a:None);report={'cases':[]}
    asyncio.run(verifier.cases(read,context,safe,None,None,models,None,paths,report,lambda:None,True))
    assert len(report['cases'])==verifier.PUBLIC_CASES==8 and calls[-1][1]==calls[-2][1]
