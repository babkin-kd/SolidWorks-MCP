"""Installed/internal and public MCP proof of exact instance face/edge addressing."""
import argparse,asyncio,hashlib,json,math,os,uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pythoncom
from win32com.client import gencache
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.component_topology import ComponentTopologyCatalog
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
 'component_face_list':ToolSpec('component.topology_list',False,constant_args={'kind':'face'},argument_defaults={'limit':100,'cursor':''}),
 'component_edge_list':ToolSpec('component.topology_list',False,constant_args={'kind':'edge'},argument_defaults={'limit':100,'cursor':''}),
 'component_topology_get':ToolSpec('component.topology_get',False),
}
INTERNAL_CASES=21
PUBLIC_CASES=8


def check_topology(value,kind,shape='box',offset=0.):
    assert value['topology_scope']=='resolved_assembly_instance_topology_reads_v1'
    assert value['object_coordinate_frame']=='component_model' and value['length_unit']=='mm' and value['area_unit']=='mm2'
    items=value['items'];count={'box':{'face':6,'edge':12},'surface':{'face':1,'edge':4},'cylinder':{'face':3,'edge':2}}[shape][kind]
    assert value['total_count']==len(items)==count and len({x['object_id'] for x in items})==count
    assert all(x['component_id']==value['component']['component_id'] and x['body_id']==value['body_id'] and x['kind']==kind for x in items)
    if kind=='face':
        expected={'box':[50.,50.,100.,100.,200.,200.],'surface':[150.],
                  'cylinder':[math.pi*36.,math.pi*36.,math.pi*360.]}[shape]
        assert all(math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-6) for a,b in zip(sorted(x['area_mm2'] for x in items),expected))
    else:
        expected={'box':[5.]*4+[10.]*4+[20.]*4,'surface':[10.,10.,15.,15.],'cylinder':[math.pi*12.]*2}[shape]
        assert all(math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-6) for a,b in zip(sorted(x['length_mm'] for x in items),expected))
        for item in items:
            for point in (item['start_mm'],item['end_mm']):
                assert len(point)==3 and all(math.isfinite(v) for v in point)
                if shape=='box':assert offset-1e-6<=point[0]<=offset+20.+1e-6 and -1e-6<=point[1]<=10.+1e-6 and -1e-6<=point[2]<=5.+1e-6
                elif shape=='surface':assert 80.-1e-6<=point[0]<=95.+1e-6 and -1e-6<=point[1]<=10.+1e-6 and abs(point[2])<1e-6
                else:assert math.isclose(math.hypot(point[0],point[2]),6.,abs_tol=1e-6) and any(math.isclose(point[1],y,abs_tol=1e-6) for y in (0.,30.))
            if shape=='cylinder':assert item['curve_type']=='circle' and all(math.isclose(a,b,abs_tol=1e-6) for a,b in zip(item['start_mm'],item['end_mm']))


async def cases(read,context,safe,sw,module,owned,session,paths,report,persist,public=False):
    first,other,subasm,asm=owned
    await safe();ctx=await context(asm)
    allrows=succeeded(await read('component_list',ctx))['items'];await safe();assert len(allrows)==5
    parts=[r for r in allrows if Path(r['referenced_path']).resolve()==paths[0]]
    main=next(r for r in parts if r['referenced_configuration']=='Основная')
    variant=next(r for r in parts if r['referenced_configuration']=='Вариант' and '/' not in r['component_path'])
    curved=next(r for r in allrows if Path(r['referenced_path']).resolve()==paths[1])
    assert variant['hidden'] is True and variant['transform']['origin_mm']==[50.,10.,20.]
    async def body_rows(row):
        await safe();values=succeeded(await read('component_body_list',{**ctx,'component_id':row['component_id']}))['items'];await safe();return values
    variant_bodies=await body_rows(variant);main_bodies=await body_rows(main);curve_bodies=await body_rows(curved)
    solid=next(x for x in variant_bodies if x['body_type']=='solid');surface=next(x for x in variant_bodies if x['body_type']=='surface')
    hidden=max((x for x in main_bodies if x['body_type']=='solid'),key=lambda x:x['bounding_box_mm']['min_mm'][0])
    curve=curve_bodies[0]
    target=dict(component_id=variant['component_id'],body_id=solid['body_id'])
    async def invoke(label,tool,error=None,custom_ctx=None,**args):
        await safe();current=await context(asm) if custom_ctx is None else custom_ctx
        before=source_state(sw,module);result=await read(tool,{**current,**args});await safe()
        assert source_state(sw,module)==before,'Passive topology read changed model/UI.'
        if error:assert result['status']=='failed' and result['error']['code'] in ((error,) if isinstance(error,str) else error),(label,result['error'])
        else:assert result['status']=='succeeded',(label,result['error'])
        report['cases'].append(dict(label=label,passed=True,status=result['status'],operation_id=result['operation_id'],error=result['error']));persist();return result
    faces=succeeded(await invoke('hidden_rotated_instance_faces','component_face_list',**target));check_topology(faces,'face')
    edges=succeeded(await invoke('hidden_rotated_instance_local_edges','component_edge_list',**target));check_topology(edges,'edge')
    face=faces['items'][0];edge=edges['items'][0]
    got=succeeded(await invoke('face_reference_roundtrip','component_topology_get',**target,object_id=face['object_id']));assert got['object']==face
    got=succeeded(await invoke('edge_reference_roundtrip','component_topology_get',**target,object_id=edge['object_id']));assert got['object']==edge
    own_main=min((x for x in main_bodies if x['body_type']=='solid'),key=lambda x:x['bounding_box_mm']['min_mm'][0])
    await invoke('foreign_same_file_instance_rejected','component_topology_get',component_id=main['component_id'],body_id=own_main['body_id'],object_id=face['object_id'],error='object_component_mismatch')
    surftarget=dict(component_id=variant['component_id'],body_id=surface['body_id'])
    check_topology(succeeded(await invoke('surface_native_face','component_face_list',**surftarget)),'face','surface')
    check_topology(succeeded(await invoke('surface_native_edges','component_edge_list',**surftarget)),'edge','surface')
    request=uuid.uuid4().hex
    original=await invoke('topology_request_replay','component_topology_get',**target,object_id=edge['object_id'],request_id=request)
    await safe();repeat=await read('component_topology_get',{**(await context(asm)),**target,'object_id':edge['object_id'],'request_id':request});await safe()
    assert repeat['operation_id']==original['operation_id'] and repeat['data']==original['data']
    if public:return
    hidden_target=dict(component_id=main['component_id'],body_id=hidden['body_id'])
    check_topology(succeeded(await invoke('hidden_multibody_faces','component_face_list',**hidden_target)),'face')
    check_topology(succeeded(await invoke('hidden_multibody_local_edges','component_edge_list',**hidden_target)),'edge',offset=40.)
    curve_target=dict(component_id=curved['component_id'],body_id=curve['body_id'])
    curve_faces=succeeded(await invoke('cylinder_native_faces','component_face_list',**curve_target));check_topology(curve_faces,'face','cylinder')
    check_topology(succeeded(await invoke('closed_circle_native_edges','component_edge_list',**curve_target)),'edge','cylinder')
    await invoke('wrong_body_same_instance_rejected','component_topology_get',**surftarget,object_id=face['object_id'],error='object_body_mismatch')
    await invoke('stale_observation_pre_read','component_face_list',**target,custom_ctx={**ctx,'expected_observation_revision':'stale'},error='observation_revision_mismatch')
    await invoke('inactive_assembly_configuration','component_face_list',**target,custom_ctx={**ctx,'configuration':'Вариант'},error='configuration_not_active')
    await invoke('foreign_assembly_reference','component_face_list',**target,custom_ctx=await context(subasm),error='component_reference_not_found')
    await safe();before=source_state(sw,module);values=[];cursor=''
    while True:
        page=succeeded(await read('component_face_list',{**(await context(asm)),**target,'limit':2,'cursor':cursor}));await safe()
        values+=page['items'];cursor=page['next_cursor']
        if not cursor:break
    assert len(values)==6 and len({x['object_id'] for x in values})==6 and {x['object_id'] for x in values}=={x['object_id'] for x in faces['items']}
    assert source_state(sw,module)==before;report['cases'].append(dict(label='complete_persistent_face_pagination',passed=True));persist()
    await safe();native=[binding.wrap(x,module.IComponent2) for x in binding.wrap(asm,module.IAssemblyDoc).GetComponents(False)]
    changed=next(c for c in native if c.Name2==variant['component_path'])
    tlb=pythoncom.LoadTypeLib(r'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb');guid,lcid,syskind,major,minor,flags=tlb.GetLibAttr()
    toggle=gencache.EnsureModule(guid,lcid,major,minor).constants.swExtRefUpdateCompNames
    preference=sw.GetUserPreferenceToggle(toggle);sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        activate_owned(sw,asm,asm.GetTitle());asm.ClearSelection2(True);assert changed.Select4(False,None,False)
        sw.SetUserPreferenceToggle(toggle,False);assert sw.GetUserPreferenceToggle(toggle) is False
        changed.Name2='Переименованный экземпляр топологии';assert changed.Name2.startswith('Переименованный экземпляр топологии')
        asm.ClearSelection2(True)
    finally:
        sw.SetUserPreferenceToggle(toggle,preference);assert sw.GetUserPreferenceToggle(toggle)==preference
        sw.CommandInProgress=False;assert sw.CommandInProgress is False
    got=succeeded(await invoke('native_rename_original_face_reference','component_topology_get',**target,object_id=face['object_id']));assert got['object']==face
    await safe();sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        changed.ReferencedConfiguration='Основная';assert changed.ReferencedConfiguration=='Основная';assert asm.ForceRebuild3(False)
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('changed_referenced_config_no_reassignment','component_topology_get',**target,object_id=face['object_id'],error=('component_reference_context_changed','persistent_reference_mismatch'))
    # Exact owned component removal, then a fresh instance of the same saved file.
    # This exercises reference rejection only; no public deletion tool is claimed.
    await safe();old_curve=next(c for c in native if c.Name2==curved['component_path']);sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        asm.ClearSelection2(True);assert old_curve.Select4(False,None,False)
        assert binding.wrap(asm.Extension,module.IModelDocExtension).DeleteSelection2(0) is True
        asm.ClearSelection2(True);assert asm.ForceRebuild3(False)
        assert len(binding.wrap(asm,module.IAssemblyDoc).GetComponents(False))==4
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('native_deleted_instance_topology_rejected','component_topology_get',**curve_target,object_id=curve_faces['items'][0]['object_id'],error=('object_deleted','object_reference_invalid','component_not_in_active_configuration'))
    await safe();sw.CommandInProgress=True;assert sw.CommandInProgress is True
    try:
        session._model=asm;session.insert_component(str(paths[1]),x_mm=150.,fixed=False);assert asm.ForceRebuild3(False)
        assert len(binding.wrap(asm,module.IAssemblyDoc).GetComponents(False))==5
    finally:sw.CommandInProgress=False;assert sw.CommandInProgress is False
    await invoke('native_recreated_file_old_topology_rejected','component_topology_get',**curve_target,object_id=curve_faces['items'][0]['object_id'],error=('object_deleted','object_reference_invalid','component_not_in_active_configuration','persistent_reference_mismatch'))


async def internal(state,sw,module,owned,session,paths,report,persist):
    adapter=SolidWorksDocuments();documents=DocumentCatalog(adapter);catalog=ComponentTopologyCatalog(documents)
    store=JobStore(state/'jobs.sqlite');runner=JobRunner(store,InlineSta())
    async def read(tool,args):
        args=dict(args);request=args.pop('request_id',uuid.uuid4().hex);spec=SPECS[tool];args=spec.payload(dict(request_id=request,**args))['arguments']
        method={'component.list':catalog.list,'component.bodies':catalog.bodies,'component.topology_list':catalog.list_topology,'component.topology_get':catalog.get_topology}[spec.operation]
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
        assert prior['accepted'] and prior['scope']=='internal_resolved_assembly_instance_topology_reads_v1' and len(prior['cases'])==INTERNAL_CASES
        assert prior['verifier_sha256']==verifier_sha and prior['fixture_sha256']==fixture_sha
        assert all(prior['wheel'][k]==wheel[k] for k in ('git_sha','source_digest','package_version','wheel_sha256'))
    private=Path(__file__).resolve().parents[1]/'work';state=args.state_dir.resolve();assert state.is_relative_to(private) and state!=private and not state.exists();state.mkdir(parents=True)
    report=dict(accepted=False,scope=('public' if args.public else 'internal')+'_resolved_assembly_instance_topology_reads_v1',wheel=wheel,cases=[],verifier_sha256=verifier_sha,fixture_sha256=fixture_sha)
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
