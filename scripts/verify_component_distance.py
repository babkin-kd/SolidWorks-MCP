"""Installed/internal and public MCP proof of native part-instance distances."""
import argparse,asyncio,hashlib,json,math,os,uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pythoncom
from win32com.client import gencache
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.component_distance import ComponentDistanceCatalog
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
from verifier_component_fixtures import setup_component_fixtures
from verifier_lifecycle import ToolSpec,open_supervised_session

SPECS={**COMPONENT_SPECS,
 'measurement_get_component_distance':ToolSpec('measurement.component_distance',False),
}
INTERNAL_CASES=13
PUBLIC_CASES=6


def check_distance(value,expected):
    assert value['measurement_scope']=='resolved_part_component_distance_v1'
    assert value['coordinate_frame']=='assembly_model' and value['length_unit']=='mm'
    assert value['includes_hidden_bodies'] is True and value['includes_surface_bodies'] is False
    assert value['intersection_classification']=='not_provided'
    assert math.isclose(value['distance_mm'],expected,abs_tol=1e-6)
    points=value['closest_points_mm'];assert len(points)==2
    assert all(len(p)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in p) for p in points)
    assert math.isclose(math.dist(*points),expected,abs_tol=1e-6)


def box_point(point,low,high):
    assert all(lo-1e-6<=x<=hi+1e-6 for x,lo,hi in zip(point,low,high))


async def cases(read,context,safe,sw,module,owned,session,paths,report,persist,public=False):
    first,other,subasm,asm=owned
    await safe();ctx=await context(asm)
    allrows=succeeded(await read('component_list',ctx))['items'];await safe();assert len(allrows)==5
    parts=[r for r in allrows if Path(r['referenced_path']).resolve()==paths[0]]
    main=next(r for r in parts if r['referenced_configuration']=='Основная')
    variant=next(r for r in parts if r['referenced_configuration']=='Вариант' and '/' not in r['component_path'])
    child=next(r for r in parts if '/' in r['component_path'])
    curved=next(r for r in allrows if Path(r['referenced_path']).resolve()==paths[1])
    sub=next(r for r in allrows if r['referenced_document_type']=='assembly')
    assert variant['hidden'] is True and variant['transform']['origin_mm']==[50.,10.,20.]
    async def invoke(label,a,b,expected=None,error=None,request_id=None,ctx_override=None):
        await safe();before=source_state(sw,module)
        args={**(await context(asm) if ctx_override is None else ctx_override),
              'component_a_id':a['component_id'],'component_b_id':b['component_id']}
        if request_id is not None:args['request_id']=request_id
        result=await read('measurement_get_component_distance',args)
        await safe();assert source_state(sw,module)==before
        if error is not None:
            assert result['status']=='failed' and result['error']['code'] in ((error,) if isinstance(error,str) else error),result
        else:
            value=succeeded(result);check_distance(value,expected)
            assert value['component_a']['component_id']==a['component_id'] and value['component_b']['component_id']==b['component_id']
        report['cases'].append(dict(label=label,passed=True,result=result));persist();return result
    value=succeeded(await invoke('hidden_rotated_multibody_solids_only',main,variant,15.))
    assert value['solid_body_counts']==[2,1]
    box_point(value['closest_points_mm'][0],[40.,0.,0.],[60.,10.,5.])
    box_point(value['closest_points_mm'][1],[40.,10.,20.],[50.,30.,25.])
    value=succeeded(await invoke('nested_total_transform_surface_excluded',main,child,70.))
    assert value['solid_body_counts']==[2,1]
    assert math.isclose(value['closest_points_mm'][0][0],60.,abs_tol=1e-6)
    assert math.isclose(value['closest_points_mm'][1][0],130.,abs_tol=1e-6)
    await invoke('curved_overlap_native_zero',child,curved,0.)
    await invoke('reversed_targets_same_metric',variant,main,15.)
    request=uuid.uuid4().hex
    original=await invoke('request_replay',main,variant,15.,request_id=request)
    await safe();before=source_state(sw,module)
    repeated=await read('measurement_get_component_distance',{**(await context(asm)),
        'component_a_id':main['component_id'],'component_b_id':variant['component_id'],'request_id':request})
    await safe();assert repeated==original and source_state(sw,module)==before
    await invoke('subassembly_target_refused',main,sub,error='unsupported_component_type')
    if public:return
    await invoke('stale_observation_preflight',main,variant,error='observation_revision_mismatch',ctx_override={**ctx,'expected_observation_revision':'stale'})
    await invoke('inactive_assembly_config_refused',main,variant,error='configuration_not_active',ctx_override={**(await context(asm)),'configuration':'Вариант'})
    await invoke('foreign_assembly_refs_refused',main,variant,error='component_reference_not_found',ctx_override=await context(subasm))
    await safe()
    native=[binding.wrap(x,module.IComponent2) for x in binding.wrap(asm,module.IAssemblyDoc).GetComponents(False)]
    changed=next(c for c in native if c.Name2==curved['component_path'])
    def move(x):
        sw.CommandInProgress=True;assert sw.CommandInProgress is True
        try:
            session._model=asm;session._apply_transform(changed,x,0.,0.,0.,0.,0.);assert asm.ForceRebuild3(False)
        finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    move(170.)
    value=succeeded(await invoke('moved_instance_current_root_coordinates',child,curved,14.))
    assert math.isclose(value['closest_points_mm'][0][0],150.,abs_tol=1e-6)
    assert math.isclose(value['closest_points_mm'][1][0],164.,abs_tol=1e-6)
    await safe();move(156.)
    await invoke('native_curved_tangency_zero',child,curved,0.)
    await safe();move(170.)
    sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        session._model=asm;session.insert_component(str(paths[1]),x_mm=206.,fixed=False);assert asm.ForceRebuild3(False)
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await safe();newrows=succeeded(await read('component_list',await context(asm)))['items'];await safe();assert len(newrows)==6
    added=next(r for r in newrows if Path(r['referenced_path']).resolve()==paths[1] and r['transform']['origin_mm']==[206.,0.,0.])
    value=succeeded(await invoke('cylinder_surface_gap_not_axis_distance',curved,added,24.))
    for point,x in zip(value['closest_points_mm'],(176.,200.)):
        assert math.isclose(point[0],x,abs_tol=1e-6) and math.isclose(point[2],0.,abs_tol=1e-6) and -1e-6<=point[1]<=30.+1e-6
    await safe();target=next(c for c in native if c.Name2==variant['component_path'])
    sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:target.ReferencedConfiguration='Основная';assert target.ReferencedConfiguration=='Основная';assert asm.ForceRebuild3(False)
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('changed_referenced_config_no_reassignment',main,variant,error=('component_reference_context_changed','persistent_reference_mismatch'))


async def internal(state,sw,module,owned,session,paths,report,persist):
    adapter=SolidWorksDocuments();documents=DocumentCatalog(adapter);catalog=ComponentDistanceCatalog(documents)
    store=JobStore(state/'jobs.sqlite');runner=JobRunner(store,InlineSta())
    async def read(tool,args):
        args=dict(args);request=args.pop('request_id',uuid.uuid4().hex);spec=SPECS[tool];args=spec.payload(dict(request_id=request,**args))['arguments']
        method={'component.list':catalog.list,'component.bodies':catalog.bodies,'measurement.component_distance':catalog.measure}[spec.operation]
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
    fixture_sha=hashlib.sha256(Path(__file__).with_name('verifier_component_fixtures.py').read_bytes()).hexdigest()
    if args.public:
        assert args.internal_report;prior=json.loads(args.internal_report.read_text(encoding='utf8'))
        assert prior['accepted'] and prior['scope']=='internal_resolved_part_component_distance_v1' and len(prior['cases'])==INTERNAL_CASES
        assert prior['verifier_sha256']==verifier_sha and prior['fixture_sha256']==fixture_sha
        assert all(prior['wheel'][k]==wheel[k] for k in ('git_sha','source_digest','package_version','wheel_sha256'))
    private=Path(__file__).resolve().parents[1]/'work';state=args.state_dir.resolve();assert state.is_relative_to(private) and state!=private and not state.exists();state.mkdir(parents=True)
    report=dict(accepted=False,scope=('public' if args.public else 'internal')+'_resolved_part_component_distance_v1',wheel=wheel,cases=[],verifier_sha256=verifier_sha,fixture_sha256=fixture_sha)
    def persist():(state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    def record(owned):report['owned_documents']=[dict(title=m.GetTitle(),path=m.GetPathName(),type=m.GetType()) for m in owned];persist()
    pythoncom.CoInitialize();sw=None;owns_setup=False;gate=SessionCleanupGate()
    try:
        sw=binding.connect(show=False);module=binding.module();assert not sw.GetDocuments() and sw.CommandInProgress is False
        baseline=native_snapshot();preferences=application_preferences(sw);report['solidworks_revision']=str(sw.RevisionNumber())
        sw.CommandInProgress=True;assert sw.CommandInProgress is True;owns_setup=True
        with fixtures(cleanup_gate=lambda:report.get('cleanup_confirmed') is True,on_owned_change=record) as (session,owned,_):
            paths=setup_component_fixtures(session,owned,state,sw,module,record)
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
        finally:persist();pythoncom.CoUninitialize()
    print(json.dumps(dict(accepted=report['accepted'],cases=len(report['cases']),scope=report['scope'])))


if __name__=='__main__':main()
