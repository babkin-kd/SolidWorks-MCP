"""Installed/internal and public native aggregate distance acceptance."""
import argparse,asyncio,hashlib,json,math,os,uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pythoncom
from win32com.client import gencache
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.component_aggregate_distance import ComponentAggregateDistanceCatalog
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
 'measurement_get_component_aggregate_distance':ToolSpec('measurement.component_aggregate_distance',False,argument_defaults={'frame':None}),
}
INTERNAL_CASES=19
PUBLIC_CASES=6


FRAME={'origin_mm':[50.,10.,20.],'axes_in_model':[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]}


def check_aggregate(value,expected,leaf_counts,solid_counts,frame=None):
    assert value['measurement_scope']=='resolved_component_aggregate_distance_v1'
    assert value['coordinate_frame']==('assembly_model' if frame is None else 'explicit_rigid_frame')
    assert value['length_unit']=='mm' and value['includes_hidden_bodies'] is True and value['includes_surface_bodies'] is False
    assert value['intersection_classification']=='not_provided'
    assert value['leaf_component_counts']==leaf_counts and value['solid_body_counts']==solid_counts
    assert value['evaluated_pair_count']==value['native_pair_count']+value['shared_instance_pair_count']
    assert value['evaluated_pair_count']==math.prod(value['solid_leaf_component_counts'])
    assert all(len(ids)==count for ids,count in zip(value['leaf_component_ids'],leaf_counts))
    assert all(value[f'nearest_component_{side}']['component_id'] in value['leaf_component_ids'][idx] for idx,side in enumerate(('a','b')))
    assert math.isclose(value['distance_mm'],expected,abs_tol=1e-6)
    for field in ('closest_points_mm','closest_points_assembly_mm'):
        points=value[field];assert len(points)==2 and all(len(p)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in p) for p in points)
        assert math.isclose(math.dist(*points),expected,abs_tol=1e-6)
    if frame is not None:
        for local,root in zip(value['closest_points_mm'],value['closest_points_assembly_mm']):
            expected_point=[sum(axis[k]*(root[k]-frame['origin_mm'][k]) for k in range(3)) for axis in frame['axes_in_model']]
            assert math.dist(local,expected_point)<1e-6


async def cases(read,context,safe,sw,module,owned,session,paths,report,persist,public=False):
    first,other,subasm,asm=owned
    await safe();ctx=await context(asm)
    rows=succeeded(await read('component_list',ctx))['items'];await safe();assert len(rows)==9
    roots=[r for r in rows if r['referenced_document_type']=='assembly'];assert len(roots)==2
    sub_a=next(r for r in roots if math.dist(r['transform']['origin_mm'],[100.,0.,0.])<1e-8)
    sub_b=next(r for r in roots if math.dist(r['transform']['origin_mm'],[250.,0.,0.])<1e-8)
    main=next(r for r in rows if Path(r['referenced_path']).resolve()==paths[0] and r['referenced_configuration']=='Основная' and r['parent_component_id'] is None)
    variant=next(r for r in rows if Path(r['referenced_path']).resolve()==paths[0] and r['parent_component_id'] is None and r['referenced_configuration']=='Вариант')
    child=next(r for r in rows if r['parent_component_id']==sub_a['component_id'] and Path(r['referenced_path']).resolve()==paths[0])
    hidden=next(r for r in rows if r['parent_component_id']==sub_a['component_id'] and Path(r['referenced_path']).resolve()==paths[1]);assert hidden['hidden'] is True
    async def invoke(label,a,b,expected=None,error=None,request_id=None,ctx_override=None,frame=None,leaf_counts=(2,2),solid_counts=(2,2)):
        await safe();before=source_state(sw,module)
        args={**(await context(asm) if ctx_override is None else ctx_override),'component_a_id':a['component_id'],'component_b_id':b['component_id'],'frame':frame}
        if request_id is not None:args['request_id']=request_id
        result=await read('measurement_get_component_aggregate_distance',args)
        await safe();assert source_state(sw,module)==before
        if error is not None:
            assert result['status']=='failed' and result['error']['code'] in ((error,) if isinstance(error,str) else error),result
        else:
            value=succeeded(result);check_aggregate(value,expected,list(leaf_counts),list(solid_counts),frame)
            assert value['component_a']['component_id']==a['component_id'] and value['component_b']['component_id']==b['component_id']
        report['cases'].append(dict(label=label,passed=True,result=result));persist();return result
    value=succeeded(await invoke('part_to_complete_subassembly_hidden_solid_surface_excluded',main,sub_a,70.,leaf_counts=(1,2),solid_counts=(2,2)))
    assert value['nearest_component_b']['component_id']==child['component_id']
    assert math.isclose(value['closest_points_assembly_mm'][0][0],60.,abs_tol=1e-6) and math.isclose(value['closest_points_assembly_mm'][1][0],130.,abs_tol=1e-6)
    value=succeeded(await invoke('repeated_subassemblies_all_four_pairs_hidden_cylinder_minimum',sub_a,sub_b,84.))
    assert value['evaluated_pair_count']==value['native_pair_count']==4 and value['nearest_component_a']['component_id']==hidden['component_id']
    assert math.isclose(value['closest_points_assembly_mm'][0][0],196.,abs_tol=1e-6) and math.isclose(value['closest_points_assembly_mm'][1][0],280.,abs_tol=1e-6)
    await invoke('explicit_rigid_frame_aggregate_witnesses',sub_a,sub_b,84.,frame=FRAME)
    value=succeeded(await invoke('aggregate_and_shared_descendant_exact_zero',sub_a,child,0.,leaf_counts=(2,1),solid_counts=(2,1)))
    assert value['shared_instance_pair_count']==1 and value['native_pair_count']==1
    assert value['nearest_component_a']['component_id']==value['nearest_component_b']['component_id']==child['component_id']
    request=uuid.uuid4().hex;original=await invoke('request_replay',sub_a,sub_b,84.,request_id=request)
    await safe();before=source_state(sw,module)
    repeated=await read('measurement_get_component_aggregate_distance',{**(await context(asm)),'component_a_id':sub_a['component_id'],'component_b_id':sub_b['component_id'],'frame':None,'request_id':request})
    await safe();assert repeated==original and source_state(sw,module)==before
    await invoke('inactive_root_config_refused',sub_a,sub_b,error='configuration_not_active',ctx_override={**(await context(asm)),'configuration':'Вариант'})
    if public:return
    await invoke('reversed_aggregate_targets_same_metric',sub_b,sub_a,84.)
    await invoke('part_pair_in_aggregate_contract',main,variant,15.,leaf_counts=(1,1),solid_counts=(2,1))
    await invoke('nested_aggregate_to_rotated_instance',sub_a,variant,math.sqrt(6625.),leaf_counts=(2,1),solid_counts=(2,1))
    await invoke('stale_observation_preflight',sub_a,sub_b,error='observation_revision_mismatch',ctx_override={**ctx,'expected_observation_revision':'stale'})
    await invoke('foreign_root_component_refs_refused',sub_a,sub_b,error='component_reference_not_found',ctx_override=await context(subasm))
    await invoke('same_explicit_target_refused',sub_a,sub_a,error='same_component_target')
    await safe()
    native=[binding.wrap(x,module.IComponent2) for x in binding.wrap(asm,module.IAssemblyDoc).GetComponents(False)]
    changed=next(c for c in native if c.Name2==sub_a['component_path']);native=None
    sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:changed.ReferencedConfiguration='Вариант';assert changed.ReferencedConfiguration=='Вариант';assert asm.ForceRebuild3(False)
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('changed_subassembly_configuration_old_target_rejected',sub_a,sub_b,error=('component_reference_context_changed','persistent_reference_mismatch'))
    await safe();fresh=succeeded(await read('component_list',await context(asm)))['items'];await safe()
    current=next(r for r in fresh if r['referenced_document_type']=='assembly' and r['referenced_configuration']=='Вариант')
    sibling=next(r for r in fresh if r['referenced_document_type']=='assembly' and math.dist(r['transform']['origin_mm'],[250.,0.,0.])<1e-8)
    if sibling['component_id']!=sub_b['component_id']:
        await invoke('post_change_related_sibling_old_reference_rejected',current,sub_b,error=('component_reference_context_changed','persistent_reference_mismatch','object_deleted','object_reference_invalid'))
    else:
        await invoke('post_change_related_sibling_reference_stable',current,sub_b,84.,solid_counts=(3,2))
    report['related_sibling_reference_refreshed']=sibling['component_id']!=sub_b['component_id'];persist();sub_b=sibling
    current_child=next(r for r in fresh if r['parent_component_id']==current['component_id'] and Path(r['referenced_path']).resolve()==paths[0])
    assert current_child['referenced_configuration']=='Основная'
    await invoke('fresh_configuration_complete_multibody_leaf_census',current,sub_b,84.,solid_counts=(3,2))
    await invoke('old_child_configuration_no_reassignment',sub_b,child,error=('component_reference_context_changed','persistent_reference_mismatch','object_deleted','object_suppressed','object_reference_invalid'))
    # Configuration changes invalidate traversal objects; reacquire the owned
    # native fixture target too, rather than modifying an old interface pointer.
    await safe()
    native=[binding.wrap(x,module.IComponent2) for x in binding.wrap(asm,module.IAssemblyDoc).GetComponents(False)]
    changed=next(c for c in native if c.Name2==current['component_path']);native=None
    await safe()
    tlb=pythoncom.LoadTypeLib(r'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb');guid,lcid,syskind,major,minor,flags=tlb.GetLibAttr()
    toggle=gencache.EnsureModule(guid,lcid,major,minor).constants.swExtRefUpdateCompNames
    preference=sw.GetUserPreferenceToggle(toggle);sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        activate_owned(sw,asm,asm.GetTitle());asm.ClearSelection2(True);assert changed.Select4(False,None,False)
        sw.SetUserPreferenceToggle(toggle,False);assert sw.GetUserPreferenceToggle(toggle) is False
        changed.Name2='Контрольная переименованная подсборка';assert changed.Name2.startswith('Контрольная переименованная подсборка')
        asm.ClearSelection2(True);assert asm.ForceRebuild3(False)
    finally:
        sw.SetUserPreferenceToggle(toggle,preference);assert sw.GetUserPreferenceToggle(toggle)==preference
        sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('native_ancestor_rename_preserves_aggregate_ids',current,sub_b,84.,solid_counts=(3,2))
    await safe();sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:session._model=asm;session._apply_transform(changed,200.,0.,0.,0.,0.,0.);assert asm.ForceRebuild3(False)
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('moved_parent_current_total_transforms',current,sub_b,0.,solid_counts=(3,2))
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
    await safe();final_rows=succeeded(await read('component_list',await context(asm)))['items'];await safe()
    empty_target=next(r for r in final_rows if r['referenced_document_type']=='assembly' and math.dist(r['transform']['origin_mm'],[200.,0.,0.])<1e-8)
    final_sibling=next(r for r in final_rows if r['referenced_document_type']=='assembly' and math.dist(r['transform']['origin_mm'],[250.,0.,0.])<1e-8)
    await invoke('native_aggregate_without_solid_leaves_refused',empty_target,final_sibling,error='component_has_no_solid_bodies')


async def internal(state,sw,module,owned,session,paths,report,persist):
    adapter=SolidWorksDocuments();documents=DocumentCatalog(adapter);catalog=ComponentAggregateDistanceCatalog(documents)
    store=JobStore(state/'jobs.sqlite');runner=JobRunner(store,InlineSta())
    async def read(tool,args):
        args=dict(args);request=args.pop('request_id',uuid.uuid4().hex);spec=SPECS[tool];args=spec.payload(dict(request_id=request,**args))['arguments']
        method={'component.list':catalog.list,'component.bodies':catalog.bodies,'measurement.component_aggregate_distance':catalog.measure_aggregate}[spec.operation]
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
        assert prior['accepted'] and prior['scope']=='internal_resolved_component_aggregate_distance_v1' and len(prior['cases'])==INTERNAL_CASES
        assert prior['verifier_sha256']==verifier_sha and prior['fixture_sha256']==fixture_sha and prior['base_fixture_sha256']==base_fixture_sha
        assert all(prior['wheel'][k]==wheel[k] for k in ('git_sha','source_digest','package_version','wheel_sha256'))
    private=Path(__file__).resolve().parents[1]/'work';state=args.state_dir.resolve();assert state.is_relative_to(private) and state!=private and not state.exists();state.mkdir(parents=True)
    report=dict(accepted=False,scope=('public' if args.public else 'internal')+'_resolved_component_aggregate_distance_v1',wheel=wheel,cases=[],verifier_sha256=verifier_sha,fixture_sha256=fixture_sha,base_fixture_sha256=base_fixture_sha)
    def persist():(state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    def record(owned):report['owned_documents']=[dict(title=m.GetTitle(),path=m.GetPathName(),type=m.GetType()) for m in owned];persist()
    pythoncom.CoInitialize();sw=None;owns_setup=False;gate=SessionCleanupGate()
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
        finally:persist();pythoncom.CoUninitialize()
    print(json.dumps(dict(accepted=report['accepted'],cases=len(report['cases']),scope=report['scope'])))


if __name__=='__main__':main()
