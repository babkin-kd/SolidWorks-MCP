"""Installed/native exact-instance catalog acceptance, own disposable CAD only."""
import argparse,asyncio,hashlib,json,math,os,uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pythoncom
from win32com.client import gencache
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.components import ComponentCatalog
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
from verifier_lifecycle import ToolSpec,open_supervised_session

SPECS={
 'document_list':ToolSpec('document.list',False),
 'component_list':ToolSpec('component.list',False,argument_defaults={'limit':100,'cursor':''}),
 'component_get':ToolSpec('component.get',False),
 'component_body_list':ToolSpec('component.bodies',False,argument_defaults={'body_type':'all'}),
 'component_body_get':ToolSpec('component.bodies',False),
}
INTERNAL_CASES=15
PUBLIC_CASES=6


def native_identity(obj):return obj._oleobj_.QueryInterface(pythoncom.IID_IUnknown)


def source_state(sw,module):
    """Independent native selections/views, instance data and actual local support."""
    rows=[]
    for raw in sw.GetDocuments() or ():
        model=binding.wrap(raw,module.IModelDoc2)
        sel=binding.wrap(model.SelectionManager,module.ISelectionMgr)
        selected=tuple((native_identity(sel.GetSelectedObject6(i,-1)),sel.GetSelectedObjectMark(i))
            for i in range(1,sel.GetSelectedObjectCount2(-1)+1))
        view=binding.wrap(model.ActiveView,module.IModelView)
        view_state=None if view is None else (tuple(binding.wrap(view.Orientation3,module.IMathTransform).ArrayData),
            tuple(binding.wrap(view.Translation3,module.IMathVector).ArrayData),view.Scale2)
        if model.GetType()==1:
            bodies=[binding.wrap(x,module.IBody2) for x in binding.wrap(model,module.IPartDoc).GetBodies2(-1,False) or ()]
            facts=tuple((native_identity(b),b.GetType(),b.Name,b.Visible,tuple(b.GetBodyBox())) for b in bodies)
        else:
            components=[binding.wrap(x,module.IComponent2) for x in binding.wrap(model,module.IAssemblyDoc).GetComponents(False) or ()]
            facts=tuple(sorted((c.Name2,native_identity(c),c.ReferencedConfiguration,c.GetSuppression2(),c.IsHidden(False),
                tuple(binding.wrap(c.GetTotalTransform(False),module.IMathTransform).ArrayData)) for c in components))
        rows.append((native_identity(model),model.GetBlockingState(),selected,view_state,facts))
    return native_snapshot(),tuple(rows),sw.CommandInProgress


def check_hierarchy(result,first_path,sub_path):
    assert result['scope']=='resolved_assembly_instance_reads_v1' and result['length_unit']=='mm'
    assert result['transform_target_frame']=='assembly_model' and result['implicit_resolution'] is False
    rows=result['items'];assert result['total_count']==len(rows)==4
    assert len({r['component_id'] for r in rows})==4
    parts=[r for r in rows if Path(r['referenced_path']).resolve()==first_path]
    assert len(parts)==3 and {r['referenced_configuration'] for r in parts}=={'Основная','Вариант'}
    sub=next(r for r in rows if Path(r['referenced_path']).resolve()==sub_path)
    nested=next(r for r in parts if '/' in r['component_path'])
    assert nested['parent_component_id']==sub['component_id'] and sub['parent_component_id'] is None
    # Top-level variant: 90° Z rotation and shift (50,10,20)mm.
    rotated=next(r for r in parts if '/' not in r['component_path'] and r['referenced_configuration']=='Вариант')
    assert rotated['transform']['origin_mm']==[50.,10.,20.]
    expected=[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]
    assert all(math.isclose(a,b,abs_tol=1e-10) for aa,bb in zip(rotated['transform']['axes_in_assembly'],expected) for a,b in zip(aa,bb))
    # Nested part shifted30 in the saved subassembly; parent shifted100 in root.
    assert all(math.isclose(a,b,abs_tol=1e-7) for a,b in zip(nested['transform']['origin_mm'],[130.,0.,0.]))
    return parts,sub


def check_bodies(value,configuration):
    assert value['body_coordinate_frame']=='component_model' and value['includes_hidden_bodies'] is True
    assert value['total_count']==(3 if configuration=='Основная' else 2)
    assert sum(x['body_type']=='solid' for x in value['items'])==(2 if configuration=='Основная' else 1)
    assert sum(x['body_type']=='surface' for x in value['items'])==1
    assert len({x['body_id'] for x in value['items']})==value['total_count']
    solid=min((x for x in value['items'] if x['body_type']=='solid'),key=lambda x:x['bounding_box_mm']['min_mm'][0])
    assert solid['bounding_box_mm']['approximate'] is True
    assert all(math.isclose(a,b,abs_tol=1e-5) for a,b in zip(solid['bounding_box_mm']['min_mm'],[0.,0.,0.]))
    assert all(math.isclose(a,b,abs_tol=1e-5) for a,b in zip(solid['bounding_box_mm']['max_mm'],[20.,10.,5.]))


async def cases(read,context,safe,sw,module,owned,session,paths,report,persist,public=False):
    first,other,subasm,asm=owned
    async def invoke(label,tool,ctx=None,error=None,**args):
        await safe();ctx=await context(asm) if ctx is None else ctx
        before=source_state(sw,module)
        result=await read(tool,{**ctx,**args})
        await safe();assert source_state(sw,module)==before,'Passive component read changed CAD/UI state.'
        if error:assert result['status']=='failed' and result['error']['code'] in ((error,) if isinstance(error,str) else error),(label,result['error'])
        else:assert result['status']=='succeeded',result['error']
        report['cases'].append(dict(label=label,passed=True,status=result['status'],operation_id=result['operation_id'],error=result['error']));persist()
        return result
    # Public chain handles all four entry points and read replay; detailed native
    # rejection/mutation diagnostics stay internal to avoid a duplicated matrix.
    value=succeeded(await invoke('complete_native_instance_hierarchy','component_list'))
    parts,sub=check_hierarchy(value,paths[0],paths[2])
    main=next(r for r in parts if r['referenced_configuration']=='Основная')
    variant=next(r for r in parts if r['referenced_configuration']=='Вариант' and '/' not in r['component_path'])
    got=succeeded(await invoke('exact_instance_readback','component_get',component_id=variant['component_id']))
    assert got['component']==variant
    bv=succeeded(await invoke('variant_native_solid_surface_bodies','component_body_list',component_id=variant['component_id']))
    check_bodies(bv,'Вариант')
    body=bv['items'][0]
    one=succeeded(await invoke('exact_instance_body_roundtrip','component_body_get',component_id=variant['component_id'],body_id=body['body_id']))
    assert one['items']==[body]
    await invoke('foreign_instance_body_rejected','component_body_get',component_id=main['component_id'],body_id=body['body_id'],error='object_component_mismatch')
    request=uuid.uuid4().hex
    original=await invoke('request_replay_same_operation','component_body_get',component_id=variant['component_id'],body_id=body['body_id'],request_id=request)
    await safe();repeat=await read('component_body_get',{**(await context(asm)), 'component_id':variant['component_id'],'body_id':body['body_id'],'request_id':request})
    await safe();assert repeat['operation_id']==original['operation_id'] and repeat['data']==original['data']
    if public:return
    await invoke('part_context_rejected','component_list',ctx=await context(first),error='unsupported_document_type')
    await invoke('inactive_configuration_no_switch','component_list',ctx={**(await context(asm)),'configuration':'Вариант'},error='configuration_not_active')
    await invoke('stale_observation_before_read','component_list',ctx={**(await context(asm)),'expected_observation_revision':'stale'},error='observation_revision_mismatch')
    bm=succeeded(await invoke('main_configuration_multibody','component_body_list',component_id=main['component_id']))
    check_bodies(bm,'Основная')
    assert {b['body_id'] for b in bm['items']}.isdisjoint(b['body_id'] for b in bv['items'])
    await invoke('subassembly_body_scope_rejected','component_body_list',component_id=sub['component_id'],error='unsupported_component_type')
    await invoke('foreign_assembly_reference_rejected','component_get',ctx=await context(subasm),component_id=main['component_id'],error='component_reference_not_found')
    await safe()
    page=succeeded(await read('component_list',{**(await context(asm)),'limit':1}))
    await safe()
    native=[binding.wrap(x,module.IComponent2) for x in binding.wrap(asm,module.IAssemblyDoc).GetComponents(False)]
    target=next(c for c in native if c.Name2==variant['component_path'])
    # Only exact owned setup, after all jobs terminal. Name2 needs selection and
    # swExtRefUpdateCompNames=False; derive enum from installed primary typelib.
    tlb=pythoncom.LoadTypeLib(r'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb')
    guid,lcid,syskind,major,minor,flags=tlb.GetLibAttr()
    constants=gencache.EnsureModule(guid,lcid,major,minor)
    toggle=constants.swExtRefUpdateCompNames
    preference=sw.GetUserPreferenceToggle(toggle)
    sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        activate_owned(sw,asm,asm.GetTitle());asm.ClearSelection2(True)
        assert target.Select4(False,None,False)
        sw.SetUserPreferenceToggle(toggle,False);assert sw.GetUserPreferenceToggle(toggle) is False
        target.Name2='Переименованный контрольный экземпляр'
        assert target.Name2.startswith('Переименованный контрольный экземпляр')
        asm.ClearSelection2(True)
    finally:
        sw.SetUserPreferenceToggle(toggle,preference);assert sw.GetUserPreferenceToggle(toggle)==preference
        sw.CommandInProgress=False;assert sw.CommandInProgress is False
    got=succeeded(await invoke('native_rename_original_reference','component_get',component_id=variant['component_id']))
    assert got['component']['component_path']==target.Name2
    # Changed native observation invalidates an earlier page; no stale response.
    await invoke('changed_native_page_rejected','component_list',cursor=page['next_cursor'],error=('invalid_component_cursor','stale_component_cursor'))
    await safe();sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        target.ReferencedConfiguration='Основная';assert target.ReferencedConfiguration=='Основная'
        assert asm.ForceRebuild3(False)
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('changed_referenced_configuration_rejected','component_get',component_id=variant['component_id'],error='component_reference_context_changed')


async def internal(state,sw,module,owned,session,paths,report,persist):
    adapter=SolidWorksDocuments();documents=DocumentCatalog(adapter);catalog=ComponentCatalog(documents)
    store=JobStore(state/'jobs.sqlite');runner=JobRunner(store,InlineSta())
    async def read(tool,args):
        args=dict(args);request=args.pop('request_id',uuid.uuid4().hex)
        spec=SPECS[tool];payload=spec.payload(dict(request_id=request,**args))
        args=payload['arguments'];method={'component.list':catalog.list,'component.get':catalog.get,'component.bodies':catalog.bodies}[spec.operation]
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
        await context(owned[0]);await safe()
        await cases(read,context,safe,sw,module,owned,session,paths,report,persist,True)
        await safe()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks',action='store_true');parser.add_argument('--public',action='store_true')
    parser.add_argument('--internal-report',type=Path);parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--expected-version',required=True);parser.add_argument('--expected-git-sha',required=True);parser.add_argument('--state-dir',type=Path,required=True)
    args=parser.parse_args()
    if not args.run_solidworks:parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    wheel=validate_wheel(args.wheel,expected_version=args.expected_version,expected_git_sha=args.expected_git_sha);entry=installed_identity(wheel)
    verifier_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if args.public:
        assert args.internal_report
        prior=json.loads(args.internal_report.read_text(encoding='utf8'))
        assert prior['accepted'] and prior['scope']=='internal_resolved_assembly_instance_reads_v1' and len(prior['cases'])==INTERNAL_CASES
        assert prior['verifier_sha256']==verifier_sha
        assert all(prior['wheel'][k]==wheel[k] for k in ('git_sha','source_digest','package_version','wheel_sha256'))
    private=Path(__file__).resolve().parents[1]/'work';state=args.state_dir.resolve()
    assert state.is_relative_to(private) and state!=private and not state.exists();state.mkdir(parents=True)
    report=dict(accepted=False,scope=('public' if args.public else 'internal')+'_resolved_assembly_instance_reads_v1',wheel=wheel,cases=[],verifier_sha256=verifier_sha)
    def persist():(state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    def owned_change(owned):
        report['owned_documents']=[dict(title=m.GetTitle(),path=m.GetPathName(),type=m.GetType()) for m in owned];persist()
    pythoncom.CoInitialize();sw=None;owns_setup=False;gate=SessionCleanupGate()
    try:
        sw=binding.connect(show=False);module=binding.module()
        assert not sw.GetDocuments() and sw.CommandInProgress is False
        baseline=native_snapshot();preferences=application_preferences(sw);report['solidworks_revision']=str(sw.RevisionNumber())
        sw.CommandInProgress=True;assert sw.CommandInProgress is True;owns_setup=True
        with fixtures(cleanup_gate=lambda:report.get('cleanup_confirmed') is True,on_owned_change=owned_change) as (session,owned,_):
            first,other=owned
            activate_owned(sw,first,first.GetTitle());session._model=first
            assert first.ShowConfiguration2('Вариант')
            f=next(f for f in session._iter_features() if f.Name=='Контрольный блок 2')
            assert f.SetSuppression2(0,1,None) and first.ForceRebuild3(False)
            assert first.ShowConfiguration2('Основная') and first.ForceRebuild3(False)
            paths=[state/'Контрольная деталь.sldprt',state/'Чужая контрольная деталь.sldprt',state/'Контрольная подсборка.sldasm']
            for model,path in zip((first,other),paths):
                activate_owned(sw,model,model.GetTitle());session._model=model;session.save_part(str(path));owned_change(owned)
                assert Path(model.GetPathName()).resolve()==path
            session.new_assembly();subasm=session._model;owned.append(subasm);owned_change(owned)
            assert subasm.SetTitle2('Контрольная подсборка '+uuid.uuid4().hex[:8]);owned_change(owned)
            binding.wrap(subasm.GetActiveConfiguration(),module.IConfiguration).Name='Основная'
            session.insert_component(str(paths[0]),x_mm=30.,fixed=False)
            child=binding.wrap(binding.wrap(subasm,module.IAssemblyDoc).GetComponents(False)[0],module.IComponent2)
            child.ReferencedConfiguration='Вариант';assert child.ReferencedConfiguration=='Вариант'
            assert subasm.ForceRebuild3(False);session.save_assembly(str(paths[2]));owned_change(owned)
            session.new_assembly();asm=session._model;owned.append(asm);owned_change(owned)
            assert asm.SetTitle2('Контрольная сборка адресации '+uuid.uuid4().hex[:8]);owned_change(owned)
            binding.wrap(asm.GetActiveConfiguration(),module.IConfiguration).Name='Основная'
            assert asm.AddConfiguration3('Вариант','','',128) is not None
            for path,x in ((paths[0],0.),(paths[0],50.),(paths[2],100.)):
                session.insert_component(str(path),x_mm=x,fixed=False)
            top=[binding.wrap(x,module.IComponent2) for x in binding.wrap(asm,module.IAssemblyDoc).GetComponents(True)]
            target=next(c for c in top if Path(c.GetPathName()).resolve()==paths[0] and math.isclose(binding.wrap(c.Transform2,module.IMathTransform).ArrayData[9],.05))
            target.ReferencedConfiguration='Вариант';assert target.ReferencedConfiguration=='Вариант'
            session._apply_transform(target,50.,10.,20.,0.,0.,90.)
            assert asm.ForceRebuild3(False);owned_change(owned)
            sw.CommandInProgress=False;assert sw.CommandInProgress is False;owns_setup=False
            if args.public:asyncio.run(public(entry,state,sw,module,owned,session,paths,report,persist,gate))
            else:asyncio.run(internal(state,sw,module,owned,session,paths,report,persist))
            assert len(report['cases'])==(PUBLIC_CASES if args.public else INTERNAL_CASES)
            assert not args.public or gate.can_cleanup()
            current=[binding.wrap(x,module.IModelDoc2) for x in sw.GetDocuments() or ()]
            assert len(current)==len(owned)==4 and sw.CommandInProgress is False
            assert all(any(native_identity(m)==native_identity(x) for x in owned) and m.GetBlockingState()==0 for m in current)
            assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'fixture_preferences')
            report['cleanup_confirmed']=True;persist()
        assert not sw.GetDocuments() and native_snapshot()==baseline and sw.CommandInProgress is False
        assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'restored_preferences')
        report.update(fixtures_closed=True,baseline_restored=True,accepted=True)
    except BaseException as exc:report['error_type']=type(exc).__name__;report['error']=str(exc);raise
    finally:
        try:
            if owns_setup:
                assert sw.CommandInProgress is True;sw.CommandInProgress=False;assert sw.CommandInProgress is False
        finally:persist();pythoncom.CoUninitialize()
    print(json.dumps(dict(accepted=report['accepted'],cases=len(report['cases']),scope=report['scope'])))


if __name__=='__main__':main()
