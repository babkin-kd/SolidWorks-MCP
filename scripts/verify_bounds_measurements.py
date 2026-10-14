"""Sequential installed internal/public bounds proof, own disposable BREP only."""
import argparse
import asyncio
from contextlib import asynccontextmanager
from concurrent.futures import Future
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import uuid

import pythoncom
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from solidworks_mcp.jobs import JobRunner,JobStore
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.bounds_measurement import BoundsMeasurementCatalog
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from verify_geometry_reads import fixtures
from verify_document_reads import native_snapshot
from verify_mass_properties import source_state,confirm_source
from verify_export_operations import application_preferences,activate_owned
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_installed_metadata import installed_identity,verify_metadata
from verify_wheel_artifact import validate_wheel
from verify_dimension_mcp import SessionCleanupGate,call,succeeded,require_native_cleanup
from verifier_lifecycle import ToolSpec,open_supervised_session

SPECS={
    'document_list':ToolSpec('document.list',False),
    'body_list':ToolSpec('geometry.list',False,constant_args={'kind':'body'},argument_defaults={'body_type':'all','limit':100,'cursor':''}),
    'measurement_get_bounds':ToolSpec('measurement.bounds',False,argument_defaults={'body_id':None,'body_type':'all','coordinate_frame':None}),
}
BOXES=[((0.,0.,0.),(20.,10.,5.)),((40.,0.,0.),(60.,10.,5.)),((80.,0.,0.),(95.,10.,0.))]


def frame(tilted=False):
    c,s=math.cos(math.pi/6),math.sin(math.pi/6)
    return dict(origin_mm=[10.,-20.,3.],axes_in_model=([[c,0.,-s],[0.,1.,0.],[s,0.,c]] if tilted else [[c,s,0.],[-s,c,0.],[0.,0.,1.]]))


def analytical(boxes=None,coordinate_frame=None,cylinder=False):
    f=coordinate_frame or dict(origin_mm=[0.,0.,0.],axes_in_model=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    low=[];high=[]
    for axis in f['axes_in_model']:
        offset=sum(a*b for a,b in zip(axis,f['origin_mm']))
        if cylinder:
            radial=6.*math.hypot(axis[0],axis[2])
            low.append(-radial+min(0.,30.*axis[1])-offset)
            high.append(radial+max(0.,30.*axis[1])-offset)
        else:
            values=[sum(a*b for a,b in zip(axis,p))-offset for minimum,maximum in boxes
                    for p in itertools.product(*zip(minimum,maximum))]
            low.append(min(values));high.append(max(values))
    return dict(min_mm=low,max_mm=high,size_mm=[b-a for a,b in zip(low,high)])


def check(result,expected,count):
    assert result['body_count']==count and result['measurement_scope']=='part_native_support_bounds_v1'
    assert result['approximate_body_box_used'] is False and result['model_geometry_modified'] is False
    for key,values in expected.items():
        assert all(math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-6) for a,b in zip(result['bounding_box_mm'][key],values)),key


class InlineSta:
    def submit(self,function):
        future=Future()
        try:future.set_result(function())
        except BaseException as exc:future.set_exception(exc)
        return future


async def cases(read,context,list_bodies,safe,sw,module,owned,session,report,persist,public=False):
    first,other,cylinder=owned
    async def case(label,model=first,boxes=BOXES,count=3,cyl=False,error=None,**args):
        await safe()
        ctx=await context(model)
        before=source_state(sw,module)
        result=await read({**ctx,**args})
        await safe()
        if error:
            assert result['status']=='failed' and result['error']['code']==error,(label,result['error'])
        else:check(succeeded(result),analytical(boxes,args.get('coordinate_frame'),cyl),count)
        confirm_source(before,source_state(sw,module))
        assert sw.CommandInProgress is False and all(model.GetBlockingState()==0 for model in owned)
        report['cases'].append(dict(label=label,passed=True,status=result['status'],operation_id=result['operation_id'],error=result['error']))
        persist();return result
    ctx=await context(first)
    objects=await list_bodies(ctx)
    solids=sorted((x for x in objects if x['body_type']=='solid'),key=lambda x:x['bounding_box_mm']['min_mm'][0])
    surface=next(x for x in objects if x['body_type']=='surface')
    assert len(solids)==2
    await case('all_solids_and_surface')
    await case('explicit_second_in_rotated_shifted_frame',boxes=[BOXES[1]],count=1,
               body_id=solids[1]['object_id'],coordinate_frame=frame())
    await case('planar_surface_zero_extent',boxes=[BOXES[2]],count=1,body_id=surface['object_id'])
    await case('curved_cylinder_tilted_shifted_frame',model=cylinder,count=1,cyl=True,coordinate_frame=frame(True))
    await case('foreign_body_rejected',model=other,body_id=solids[0]['object_id'],error='object_reference_not_found')
    if public:
        await safe();ctx=await context(first)
        response=await read({**ctx,'request_id':'replay-bounds','body_type':'solid'})
        check(succeeded(response),analytical(BOXES[:2]),2)
        repeated=await read({**ctx,'request_id':'replay-bounds','body_type':'solid'})
        assert response['operation_id']==repeated['operation_id'] and succeeded(response)==succeeded(repeated)
        await safe()
        report['cases'].append(dict(label='request_replay_one_read',passed=True,status='succeeded',operation_id=response['operation_id'],error=None));persist()
        return
    await case('solid_filter',boxes=BOXES[:2],count=2,body_type='solid')
    await case('surface_filter_tilted',boxes=[BOXES[2]],count=1,body_type='surface',coordinate_frame=frame(True))
    await case('wrong_body_type_rejected',body_id=surface['object_id'],body_type='solid',error='unsupported_body_type')
    stale=await read({**ctx,'expected_observation_revision':'obsolete'})
    assert stale['status']=='failed' and stale['error']['code']=='observation_revision_mismatch'
    report['cases'].append(dict(label='stale_observation_pre_read',passed=True));persist()
    await case('reflection_rejected',coordinate_frame=dict(origin_mm=[0.,0.,0.],axes_in_model=[[1.,0.,0.],[0.,1.,0.],[0.,0.,-1.]]),error='invalid_measurement_frame')
    await safe()
    adapter=SolidWorksDocuments()
    try:
        native=sorted(adapter.bodies(first,'solid'),key=lambda body:body.GetBodyBox()[0])
        assert sw.CommandInProgress is False
        sw.CommandInProgress=True;assert sw.CommandInProgress is True
        try:native[1].HideBody(True);assert native[1].Visible is False
        finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
        await case('hidden_solid_included',boxes=BOXES[:2],count=2,body_type='solid')
        await safe()
        sw.CommandInProgress=True;assert sw.CommandInProgress is True
        try:
            activate_owned(sw,first,first.GetTitle());session._model=first
            assert first.ShowConfiguration2('Вариант')
            feature=next(f for f in session._iter_features() if f.Name=='Контрольный блок 2')
            assert feature.SetSuppression2(0,1,None) and first.ForceRebuild3(False)
            assert len(adapter.bodies(first,'solid'))==1
        finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
        await case('variant_different_geometry',boxes=[BOXES[0]],count=1,body_type='solid')
        await case('other_configuration_reference_rejected',body_id=solids[0]['object_id'],error='object_configuration_mismatch')
        inactive={**(await context(first)),'configuration':'Основная'}
        rejected=await read(inactive)
        assert rejected['status']=='failed' and rejected['error']['code']=='configuration_not_active'
        report['cases'].append(dict(label='inactive_configuration_no_switch',passed=True));persist()
    finally:adapter.close()


async def internal(state,sw,module,owned,session,report,persist):
    adapter=SolidWorksDocuments();documents=DocumentCatalog(adapter);catalog=BoundsMeasurementCatalog(documents)
    store=JobStore(state/'jobs.sqlite');runner=JobRunner(store,InlineSta())
    async def read(args):
        args=dict(args);request=args.pop('request_id',uuid.uuid4().hex)
        job=runner.submit(request,'measurement.bounds',args,lambda:catalog.measure(**args),context={k:args[k] for k in ('document_id','configuration','expected_observation_revision')},mutates=False)
        return dict(status=job['status'],operation_id=job['operation_id'],data=job['result'],error=job['error'])
    async def context(model):
        item=next(row for row in documents.list()['documents'] if row['title']==model.GetTitle())
        return dict(document_id=item['document_id'],configuration=item['active_configuration'],expected_observation_revision=item['observation_revision'])
    async def bodies(ctx):return catalog.list(**ctx)['items']
    async def safe():assert all(row['status'] in ('succeeded','failed') and row['payload']['mutates'] is False for row in store.list(limit=100)['items'])
    try:
        await cases(read,context,bodies,safe,sw,module,owned,session,report,persist)
        await safe();assert not store.mutation_blockers('closing','closing')
    finally:adapter.close();store.close()


async def public(entry,state,sw,module,owned,session,report,persist,gate):
    params=StdioServerParameters(command=str(entry),args=['--state-dir',str(state/'server')],env={**os.environ,'PYTHONPATH':'','PYTHONNOUSERSITE':'1'})
    @asynccontextmanager
    async def factory():
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as raw:
                await raw.initialize();info=succeeded(await call(raw,'system_get_info'))
                report['metadata']=verify_metadata((await raw.list_tools()).tools,info,report['wheel']);persist();yield raw
    async with open_supervised_session(factory,tool_specs=SPECS,journal_path=state/'server/jobs.sqlite',on_hold=lambda info:report.update(lifecycle_hold=True)) as client:
        gate.add(client)
        async def read(args):return await call(client,'measurement_get_bounds',**args,timeout_s=0.)
        async def context(model):
            rows=succeeded(await call(client,'document_list'))['documents']
            item=next(row for row in rows if row['title']==model.GetTitle())
            return dict(document_id=item['document_id'],configuration=item['active_configuration'],expected_observation_revision=item['observation_revision'])
        async def bodies(ctx):return succeeded(await call(client,'body_list',**ctx))['items']
        async def safe():await require_native_cleanup(client,gate)
        # First document_list gives the supervisor its initial acknowledged read.
        await context(owned[0]);await safe()
        await cases(read,context,bodies,safe,sw,module,owned,session,report,persist,True)
        await safe()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks',action='store_true');parser.add_argument('--public',action='store_true')
    parser.add_argument('--internal-report',type=Path)
    parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--expected-version',required=True)
    parser.add_argument('--expected-git-sha',required=True);parser.add_argument('--state-dir',type=Path,required=True)
    args=parser.parse_args()
    if not args.run_solidworks:parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    wheel=validate_wheel(args.wheel,expected_version=args.expected_version,expected_git_sha=args.expected_git_sha);entry=installed_identity(wheel)
    if args.public:
        assert args.internal_report
        prior=json.loads(args.internal_report.read_text(encoding='utf8'))
        assert prior['accepted'] and prior['scope']=='internal_part_native_support_bounds_v1' and len(prior['cases'])==14
        assert all(prior['wheel'][k]==wheel[k] for k in ('git_sha','source_digest','package_version','wheel_sha256'))
        assert prior['verifier_sha256']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    private=Path(__file__).resolve().parents[1]/'work';state=args.state_dir.resolve()
    assert state.is_relative_to(private) and state!=private and not state.exists();state.mkdir(parents=True)
    report=dict(accepted=False,scope=('public' if args.public else 'internal')+'_part_native_support_bounds_v1',wheel=wheel,cases=[],
                verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    def persist():(state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    pythoncom.CoInitialize();sw=None;owns_setup=False;gate=SessionCleanupGate()
    try:
        sw=binding.connect(show=False);module=binding.module()
        assert not sw.GetDocuments() and sw.CommandInProgress is False
        baseline=native_snapshot();preferences=application_preferences(sw);report['solidworks_revision']=str(sw.RevisionNumber())
        sw.CommandInProgress=True;assert sw.CommandInProgress is True;owns_setup=True
        with fixtures(cleanup_gate=lambda:report.get('cleanup_confirmed') is True) as (session,owned,_):
            session.new_part();cylinder=session._model;owned.append(cylinder)
            assert cylinder.SetTitle2('Контрольный цилиндр габаритов '+uuid.uuid4().hex[:8])
            dimension_preference=sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
            sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE,False)
            assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is False
            try:session.add_cylinder(12.,30.,name='Контрольный цилиндр')
            finally:
                sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE,dimension_preference)
                assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)==dimension_preference
            for index,feature in enumerate(session._iter_features()):
                if feature.GetTypeName2() in ('RefPlane','ProfileFeature'):
                    name=('Контрольная плоскость ' if feature.GetTypeName2()=='RefPlane' else 'Контрольный эскиз ')+str(index)
                    feature.Name=name;assert feature.Name==name
            assert cylinder.ForceRebuild3(False)
            body=binding.wrap(binding.wrap(cylinder,module.IPartDoc).GetBodies2(0,False)[0],module.IBody2)
            body.Name='Контрольное тело цилиндра';assert body.Name=='Контрольное тело цилиндра'
            assert math.isclose(body.GetMassProperties(1.)[3]*1e9,math.pi*6.**2*30.,rel_tol=1e-9)
            report['owned_documents']=[dict(title=m.GetTitle(),path=m.GetPathName()) for m in owned];persist()
            sw.CommandInProgress=False;assert sw.CommandInProgress is False;owns_setup=False
            if args.public:asyncio.run(public(entry,state,sw,module,owned,session,report,persist,gate))
            else:asyncio.run(internal(state,sw,module,owned,session,report,persist))
            assert len(report['cases'])==(6 if args.public else 14)
            assert not args.public or gate.can_cleanup()
            current=tuple(binding.wrap(raw,module.IModelDoc2) for raw in sw.GetDocuments() or ())
            assert len(current)==len(owned)==3 and sw.CommandInProgress is False
            tokens=tuple(m._oleobj_.QueryInterface(pythoncom.IID_IUnknown) for m in owned)
            assert all(any(m._oleobj_.QueryInterface(pythoncom.IID_IUnknown)==token for token in tokens) for m in current)
            assert all(not m.GetPathName() and m.GetBlockingState()==0 for m in current)
            assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'fixture_preferences')
            report['cleanup_confirmed']=True;persist()
        assert native_snapshot()==baseline and not sw.GetDocuments() and sw.CommandInProgress is False
        assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'restored_preferences')
        report['fixtures_closed']=True;report['baseline_restored']=True;report['accepted']=True
    except BaseException as exc:report['error_type']=type(exc).__name__;report['error']=str(exc);raise
    finally:
        try:
            if owns_setup:
                assert sw.CommandInProgress is True;sw.CommandInProgress=False;assert sw.CommandInProgress is False
        finally:persist();pythoncom.CoUninitialize()
    print(json.dumps(dict(accepted=report['accepted'],cases=len(report['cases']),scope=report['scope'])))


if __name__=='__main__':main()
