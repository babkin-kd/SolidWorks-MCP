"""Installed/internal and public native aggregate distance acceptance."""
import argparse,asyncio,hashlib,json,math,os,uuid,time
from contextlib import asynccontextmanager
from pathlib import Path
import pythoncom
from win32com.client import gencache
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.component_aggregate_probes import ComponentAggregateProbeCatalog as ComponentAggregateDistanceCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner,JobStore
from verify_geometry_reads import fixtures
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences,activate_owned
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_installed_metadata import installed_identity,verify_metadata
from verify_wheel_artifact import validate_wheel
from verify_dimension_mcp import SessionCleanupGate,call,succeeded,require_native_cleanup
from verify_bounds_measurements import InlineSta
from verify_component_reads import native_identity,source_state,SPECS as COMPONENT_SPECS
from verifier_aggregate_fixtures import setup_aggregate_fixtures
from verifier_lifecycle import ToolSpec,open_supervised_session

SPECS={**COMPONENT_SPECS,
 'measurement_get_component_aggregate_point_distance':ToolSpec('measurement.component_aggregate_point_distance',False,argument_defaults={'frame':None}),
 'measurement_get_component_aggregate_axis_distance':ToolSpec('measurement.component_aggregate_axis_distance',False,argument_defaults={'frame':None}),
 'measurement_get_component_point_distance':ToolSpec('measurement.component_point_distance',False,argument_defaults={'frame':None}),
 'measurement_get_component_axis_distance':ToolSpec('measurement.component_axis_distance',False,argument_defaults={'frame':None}),
}
INTERNAL_CASES=24
PUBLIC_CASES=8


FRAME={'origin_mm':[50.,10.,20.],'axes_in_model':[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]}


def check_probe(value,kind,expected,leaves=2,solids=2,location=None,frame=None):
    assert value['measurement_scope']=='resolved_component_aggregate_'+kind+'_distance_v1'
    assert value['coordinate_frame']==('assembly_model' if frame is None else 'explicit_rigid_frame')
    assert value['leaf_component_count']==len(value['leaf_component_ids'])==leaves
    assert value['solid_body_count']==solids and value['evaluated_leaf_count']==value['solid_leaf_component_count']
    assert value['nearest_component']['component_id'] in value['leaf_component_ids']
    assert value['includes_hidden_components'] is True and value['includes_hidden_bodies'] is True
    assert value['includes_surface_bodies'] is False and value['length_unit']=='mm'
    assert math.isclose(value['distance_mm'],expected,abs_tol=1e-6)
    if kind=='point':
        assert value['distance_semantics']=='minimum_to_individual_solid_boundary'
        assert value['point_location']==location
        assert value['inside'] is (True if location=='inside' else False if location=='outside' else None)
        assert len(value['body_locations'])==solids and all(row['component_id'] in value['leaf_component_ids'] for row in value['body_locations'])
        roots=[value['point_assembly_mm'],value['nearest_assembly_mm']]
        local=[value['point_mm'],value['nearest_mm']]
    else:
        assert value['axis_semantics']=='infinite_line' and value['intersection_classification']=='not_provided'
        roots=value['closest_points_assembly_mm'];local=value['closest_points_mm']
        origin=value['axis_origin_assembly_mm'];direction=value['axis_direction_assembly']
        delta=[x-y for x,y in zip(roots[1],origin)]
        projection=sum(x*y for x,y in zip(delta,direction))
        assert math.dist(delta,[projection*x for x in direction])<1e-6
    assert math.isclose(math.dist(*roots),expected,abs_tol=1e-6)
    assert math.isclose(math.dist(*local),expected,abs_tol=1e-6)
    if frame is not None:
        for source,root in zip(local,roots):
            expected_point=[sum(axis[k]*(root[k]-frame['origin_mm'][k]) for k in range(3)) for axis in frame['axes_in_model']]
            assert math.dist(source,expected_point)<1e-6


async def cases(read,context,safe,sw,module,owned,session,paths,report,persist,public=False):
    first,other,subasm,asm=owned
    await safe();rows=succeeded(await read('component_list',await context(asm)))['items'];await safe();assert len(rows)==9
    target=next(row for row in rows if row['referenced_document_type']=='assembly' and math.dist(row['transform']['origin_mm'],[100.,0.,0.])<1e-8)
    main=next(row for row in rows if Path(row['referenced_path']).resolve()==paths[0] and row['parent_component_id'] is None and row['referenced_configuration']=='Основная')
    hidden=next(row for row in rows if Path(row['referenced_path']).resolve()==paths[1] and row['parent_component_id']==target['component_id'])
    assert hidden['hidden'] is True
    async def invoke(label,kind,target=target,expected=None,error=None,point=None,origin=None,direction=None,frame=None,location=None,
                     request_id=None,ctx_override=None,leaves=2,solids=2,legacy=False):
        await safe();before=source_state(sw,module)
        args={**(await context(asm) if ctx_override is None else ctx_override),'component_id':target['component_id'],'frame':frame}
        if kind=='point':args['point_mm']=point
        else:args.update(axis_origin_mm=origin,axis_direction=direction)
        if request_id is not None:args['request_id']=request_id
        tool='measurement_get_component_'+('' if legacy else 'aggregate_')+kind+'_distance'
        started=time.perf_counter();result=await read(tool,args);elapsed=time.perf_counter()-started
        await safe();assert source_state(sw,module)==before
        if error is not None:
            assert result['status']=='failed' and result['error']['code'] in ((error,) if isinstance(error,str) else error),result
        elif legacy:
            value=succeeded(result)
            assert value['measurement_scope']=='resolved_part_component_'+kind+'_distance_v1'
            assert math.isclose(value['distance_mm'],expected,abs_tol=1e-6) and value['solid_body_count']==solids
        else:
            value=succeeded(result);check_probe(value,kind,expected,leaves,solids,location,frame)
            assert value['component']['component_id']==target['component_id']
        report['cases'].append(dict(label=label,passed=True,result=result,protocol_and_job_wait_seconds=elapsed));persist();return result
    point_request=uuid.uuid4().hex;axis_request=uuid.uuid4().hex
    point=succeeded(await invoke('hidden_nested_cylinder_point_outside','point',expected=3.,point=[199.,15.,0.],location='outside',request_id=point_request))
    assert point['nearest_component']['component_id']==hidden['component_id'] and math.isclose(point['nearest_assembly_mm'][0],196.,abs_tol=1e-6)
    assert point['face_count']==9
    await invoke('inside_hidden_cylinder_positive_boundary_distance','point',expected=6.,point=[190.,15.,0.],location='inside')
    await invoke('aggregate_point_explicit_frame','point',expected=3.,point=[5.,-149.,-20.],location='outside',frame=FRAME)
    axis=succeeded(await invoke('hidden_nested_cylinder_axis_surface_gap','axis',expected=2.,origin=[198.,0.,0.],direction=[0.,1.,0.],request_id=axis_request))
    assert axis['nearest_component']['component_id']==hidden['component_id'] and math.isclose(axis['closest_points_assembly_mm'][0][0],196.,abs_tol=1e-6)
    await invoke('aggregate_axis_explicit_frame','axis',expected=2.,origin=[-10.,-148.,-20.],direction=[1.,0.,0.],frame=FRAME)
    for kind,request,extra in [('point',point_request,{'point_mm':[199.,15.,0.]}),('axis',axis_request,{'axis_origin_mm':[198.,0.,0.],'axis_direction':[0.,1.,0.]})]:
        await safe();before=source_state(sw,module)
        replay=await read('measurement_get_component_aggregate_'+kind+'_distance',{**(await context(asm)),'component_id':target['component_id'],'frame':None,'request_id':request,**extra})
        await safe();assert source_state(sw,module)==before and replay['status']=='succeeded'
        original=report['cases'][0 if kind=='point' else 3]['result']
        assert replay['operation_id']==original['operation_id'] and replay['data']==original['data']
        report['cases'].append(dict(label=kind+'_request_replay',passed=True,result=replay));persist()
    await invoke('inactive_root_point_refused','point',point=[199.,15.,0.],error='configuration_not_active',ctx_override={**(await context(asm)),'configuration':'Вариант'})
    if public:return
    await invoke('shared_part_point_contract_regression','point',main,expected=5.,point=[65.,5.,2.5],solids=2,legacy=True)
    await invoke('shared_part_axis_contract_regression','axis',main,expected=5.,origin=[65.,0.,2.5],direction=[0.,1.,0.],solids=2,legacy=True)
    await invoke('axis_inside_cylinder_zero_all_leaves','axis',expected=0.,origin=[190.,0.,0.],direction=[0.,1.,0.])
    await invoke('point_boundary_native_tristate','point',expected=0.,point=[196.,15.,0.],location='boundary')
    await invoke('single_part_target_aggregate_point','point',main,expected=5.,point=[65.,5.,2.5],location='outside',leaves=1,solids=2)
    await invoke('single_part_target_aggregate_axis','axis',main,expected=5.,origin=[65.,0.,2.5],direction=[0.,1.,0.],leaves=1,solids=2)
    await invoke('far_origin_reversed_infinite_axis','axis',expected=2.,origin=[198.,1e6,0.],direction=[0.,-10.,0.])
    await invoke('zero_axis_before_solver_refused','axis',origin=[198.,0.,0.],direction=[0.,0.,0.],error='invalid_measurement_axis')
    await invoke('stale_point_observation_refused','point',point=[199.,15.,0.],error='observation_revision_mismatch',ctx_override={**(await context(asm)),'expected_observation_revision':'old'})
    await invoke('foreign_root_aggregate_ref_refused','point',point=[199.,15.,0.],error=('component_document_context_mismatch','component_reference_not_found'),ctx_override=await context(subasm))
    await invoke('inactive_root_axis_refused','axis',origin=[198.,0.,0.],direction=[0.,1.,0.],error='configuration_not_active',ctx_override={**(await context(asm)),'configuration':'Вариант'})
    await safe();sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        native=[binding.wrap(raw,module.IComponent2) for raw in binding.wrap(asm,module.IAssemblyDoc).GetComponents(False)]
        changed=next(row for row in native if Path(row.GetPathName()).resolve()==paths[2] and '/' not in row.Name2 and abs(binding.wrap(row.GetTotalTransform(False),module.IMathTransform).ArrayData[9]-.1)<1e-9)
        native=None;changed.ReferencedConfiguration='Вариант';assert changed.ReferencedConfiguration=='Вариант'
        assert asm.ForceRebuild3(False)
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('old_configuration_aggregate_ref_rejected','point',point=[199.,15.,0.],error=('component_configuration_changed','persistent_reference_mismatch','component_context_changed'))
    await safe();rows=succeeded(await read('component_list',await context(asm)))['items'];await safe()
    target=next(row for row in rows if row['referenced_document_type']=='assembly' and math.dist(row['transform']['origin_mm'],[100.,0.,0.])<1e-8)
    await invoke('fresh_multibody_configuration_point_complete','point',target,expected=5.,point=[165.,5.,2.5],location='outside',solids=3)
    await invoke('fresh_multibody_configuration_axis_complete','axis',target,expected=5.,origin=[165.,0.,2.5],direction=[0.,1.,0.],solids=3)
    await safe();sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        activate_owned(sw,first,first.GetTitle());session._model=first
        if str(binding.wrap(first.GetActiveConfiguration(),module.IConfiguration).Name)!='Основная':assert first.ShowConfiguration2('Основная')
        assert str(binding.wrap(first.GetActiveConfiguration(),module.IConfiguration).Name)=='Основная'
        found=[]
        for feature in session._iter_features():
            if feature.Name in ('Контрольный блок 1','Контрольный блок 2'):found.append(feature.Name);assert feature.SetSuppression2(0,1,None)
        assert len(found)==2 and first.ForceRebuild3(False)
        activate_owned(sw,other,other.GetTitle());session._model=other
        feature=next(f for f in session._iter_features() if f.Name=='Контрольный цилиндр топологии');assert feature.SetSuppression2(0,1,None) and other.ForceRebuild3(False)
        activate_owned(sw,subasm,subasm.GetTitle());session._model=subasm;assert subasm.ForceRebuild3(False)
        activate_owned(sw,asm,asm.GetTitle());session._model=asm;assert asm.ForceRebuild3(False)
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await safe();rows=succeeded(await read('component_list',await context(asm)))['items'];await safe()
    target=next(row for row in rows if row['referenced_document_type']=='assembly' and math.dist(row['transform']['origin_mm'],[100.,0.,0.])<1e-8)
    await invoke('aggregate_without_solids_point_refused','point',target,point=[199.,15.,0.],error='component_has_no_solid_bodies')
    await invoke('aggregate_without_solids_axis_refused','axis',target,origin=[198.,0.,0.],direction=[0.,1.,0.],error='component_has_no_solid_bodies')


async def internal(state,sw,module,owned,session,paths,report,persist):
    adapter=SolidWorksDocuments();documents=DocumentCatalog(adapter);catalog=ComponentAggregateDistanceCatalog(documents)
    store=JobStore(state/'jobs.sqlite');runner=JobRunner(store,InlineSta())
    async def read(tool,args):
        args=dict(args);request=args.pop('request_id',uuid.uuid4().hex);spec=SPECS[tool];args=spec.payload(dict(request_id=request,**args))['arguments']
        method={'component.list':catalog.list,'component.bodies':catalog.bodies,'measurement.component_aggregate_point_distance':catalog.measure_aggregate_point,'measurement.component_aggregate_axis_distance':catalog.measure_aggregate_axis,'measurement.component_point_distance':catalog.measure_point,'measurement.component_axis_distance':catalog.measure_axis}[spec.operation]
        job=runner.submit(request,spec.operation,args,lambda:method(**args),context={k:args[k] for k in ('document_id','configuration','expected_observation_revision')},mutates=False)
        return dict(status=job['status'],operation_id=job['operation_id'],data=job['result'],error=job['error'])
    async def context(model):
        item=next(r for r in documents.list()['documents'] if r['title']==model.GetTitle())
        return dict(document_id=item['document_id'],configuration=item['active_configuration'],expected_observation_revision=item['observation_revision'])
    async def safe():assert all(row['status'] in ('succeeded','failed') and row['payload']['mutates'] is False for row in store.list(limit=100)['items'])
    try:await cases(read,context,safe,sw,module,owned,session,paths,report,persist)
    finally:documents.close();store.close()


async def public(entry,state,sw,module,owned,session,paths,report,persist,gate):
    params=StdioServerParameters(command=str(entry),args=['--state-dir',str(state/'server')],env={**os.environ,'PYTHONPATH':'','PYTHONNOUSERSITE':'1'})
    @asynccontextmanager
    async def factory():
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as raw:
                await raw.initialize();info=succeeded(await call(raw,'system_get_info'))
                report['metadata']=verify_metadata((await raw.list_tools()).tools,info,report['wheel']);persist();yield raw
    async with open_supervised_session(factory,tool_specs=SPECS,journal_path=state/'server/jobs.sqlite',on_hold=lambda info:report.update(lifecycle_hold=True)) as client:
        gate.add(client)
        async def read(tool,args):return await call(client,tool,**args,timeout_s=0.)
        async def context(model):
            item=next(r for r in succeeded(await call(client,'document_list'))['documents'] if r['title']==model.GetTitle())
            return dict(document_id=item['document_id'],configuration=item['active_configuration'],expected_observation_revision=item['observation_revision'])
        async def safe():await require_native_cleanup(client,gate)
        await context(owned[0]);await safe();await cases(read,context,safe,sw,module,owned,session,paths,report,persist,True);await safe()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks',action='store_true');parser.add_argument('--public',action='store_true');parser.add_argument('--internal-report',type=Path)
    parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--expected-version',required=True);parser.add_argument('--expected-git-sha',required=True);parser.add_argument('--state-dir',type=Path,required=True)
    args=parser.parse_args()
    if not args.run_solidworks:parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    wheel=validate_wheel(args.wheel,expected_version=args.expected_version,expected_git_sha=args.expected_git_sha);entry=installed_identity(wheel)
    verifier_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    fixture_sha=hashlib.sha256(Path(__file__).with_name('verifier_aggregate_fixtures.py').read_bytes()).hexdigest()
    base_fixture_sha=hashlib.sha256(Path(__file__).with_name('verifier_component_fixtures.py').read_bytes()).hexdigest()
    if args.public:
        assert args.internal_report;prior=json.loads(args.internal_report.read_text(encoding='utf8'))
        assert prior['accepted'] and prior['scope']=='internal_resolved_component_aggregate_probes_v1' and len(prior['cases'])==INTERNAL_CASES
        assert prior['verifier_sha256']==verifier_sha and prior['fixture_sha256']==fixture_sha and prior['base_fixture_sha256']==base_fixture_sha
        assert all(prior['wheel'][k]==wheel[k] for k in ('git_sha','source_digest','package_version','wheel_sha256'))
    private=Path(__file__).resolve().parents[1]/'work';state=args.state_dir.resolve();assert state.is_relative_to(private) and state!=private and not state.exists();state.mkdir(parents=True)
    report=dict(accepted=False,scope=('public' if args.public else 'internal')+'_resolved_component_aggregate_probes_v1',wheel=wheel,cases=[],verifier_sha256=verifier_sha,fixture_sha256=fixture_sha,base_fixture_sha256=base_fixture_sha)
    def persist():(state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    def record(owned):report['owned_documents']=[dict(title=m.GetTitle(),path=m.GetPathName(),type=m.GetType()) for m in owned];persist()
    started=time.perf_counter();pythoncom.CoInitialize();sw=None;owns_setup=False;gate=SessionCleanupGate()
    try:
        sw=binding.connect(show=False);module=binding.module();assert not sw.GetDocuments() and sw.CommandInProgress is False
        baseline=native_snapshot();preferences=application_preferences(sw);report['solidworks_revision']=str(sw.RevisionNumber())
        sw.CommandInProgress=True;assert sw.CommandInProgress is True;owns_setup=True
        with fixtures(cleanup_gate=lambda:report.get('cleanup_confirmed') is True,on_owned_change=record) as (session,owned,_):
            paths=setup_aggregate_fixtures(session,owned,state,sw,module,record)
            sw.CommandInProgress=False;assert sw.CommandInProgress is False;owns_setup=False
            if args.public:asyncio.run(public(entry,state,sw,module,owned,session,paths,report,persist,gate))
            else:asyncio.run(internal(state,sw,module,owned,session,paths,report,persist))
            assert len(report['cases'])==(PUBLIC_CASES if args.public else INTERNAL_CASES);assert not args.public or gate.can_cleanup()
            current=[binding.wrap(x,module.IModelDoc2) for x in sw.GetDocuments() or ()]
            assert len(current)==len(owned)==4 and sw.CommandInProgress is False
            assert all(any(native_identity(m)==native_identity(x) for x in owned) and m.GetBlockingState()==0 for m in current)
            assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'fixture_preferences');report['cleanup_confirmed']=True;persist()
        assert not sw.GetDocuments() and native_snapshot()==baseline and sw.CommandInProgress is False
        assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'restored_preferences')
        report.update(fixtures_closed=True,baseline_restored=True,accepted=True)
    except BaseException as exc:report['error_type']=type(exc).__name__;report['error']=str(exc);raise
    finally:
        try:
            if owns_setup:assert sw.CommandInProgress is True;sw.CommandInProgress=False;assert sw.CommandInProgress is False
        finally:report['elapsed_seconds']=time.perf_counter()-started;persist();pythoncom.CoUninitialize()
    print(json.dumps(dict(accepted=report['accepted'],cases=len(report['cases']),scope=report['scope'])))


if __name__=='__main__':main()
