"""Installed/internal and public native Save3 acceptance on owned CAD files."""
import argparse,asyncio,hashlib,json,math,os,shutil,time,uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pythoncom
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.native_document_save import NativeDocumentSaveCatalog
from solidworks_mcp.jobs import JobRunner,JobStore
from verify_geometry_reads import fixtures
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences,activate_owned
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_installed_metadata import installed_identity,verify_metadata
from verify_wheel_artifact import validate_wheel
from verify_dimension_mcp import SessionCleanupGate,call,succeeded,require_native_cleanup
from verify_bounds_measurements import InlineSta
from verify_component_reads import native_identity
from verifier_lifecycle import ToolSpec,open_supervised_session

SPECS={'document_list':ToolSpec('document.list',False),
       'document_prepare_save_native':ToolSpec('document.prepare_save_native',False),
       'document_save_native':ToolSpec('document.save_native',True)}
INTERNAL_CASES=10
PUBLIC_CASES=5


def physical_state(sw,module):
    rows=[]
    for raw in sw.GetDocuments() or ():
        model=binding.wrap(raw,module.IModelDoc2);sel=binding.wrap(model.SelectionManager,module.ISelectionMgr)
        selection=tuple((native_identity(sel.GetSelectedObject6(i,-1)),sel.GetSelectedObjectMark(i)) for i in range(1,sel.GetSelectedObjectCount2(-1)+1))
        view=binding.wrap(model.ActiveView,module.IModelView)
        geometry_view=None if view is None else (tuple(binding.wrap(view.Orientation3,module.IMathTransform).ArrayData),tuple(binding.wrap(view.Translation3,module.IMathVector).ArrayData),view.Scale2)
        if model.GetType()==1:
            bodies=[binding.wrap(x,module.IBody2) for x in binding.wrap(model,module.IPartDoc).GetBodies2(-1,False) or ()]
            facts=tuple((b.GetType(),b.Name,b.Visible,tuple(b.GetBodyBox())) for b in bodies)
        elif model.GetType()==2:
            components=[binding.wrap(x,module.IComponent2) for x in binding.wrap(model,module.IAssemblyDoc).GetComponents(False) or ()]
            facts=tuple((c.Name2,native_identity(c),c.ReferencedConfiguration,tuple(binding.wrap(c.GetTotalTransform(False),module.IMathTransform).ArrayData)) for c in components)
        else:facts=tuple(binding.wrap(model,module.IDrawingDoc).GetSheetNames() or ())
        rows.append((native_identity(model),model.GetBlockingState(),selection,geometry_view,facts,model.GetTitle(),model.GetPathName()))
    active=binding.wrap(sw.ActiveDoc,module.IModelDoc2)
    return tuple(rows),None if active is None else native_identity(active),sw.CommandInProgress,sw.Visible


def setup(session,owned,state,sw,module,record):
    assert len(owned)==2 and sw.CommandInProgress is True
    for index,model in enumerate(owned):
        activate_owned(sw,model,model.GetTitle());session._model=model
        session.save_part(str(state/f'Контрольная деталь {index+1}.SLDPRT'));record(owned)
    session.new_assembly();assembly=session._model;owned.append(assembly);record(owned)
    assert assembly.SetTitle2('Контрольная сборка сохранения')
    binding.wrap(assembly.GetActiveConfiguration(),module.IConfiguration).Name='Основная'
    session.insert_component(owned[0].GetPathName(),fixed=False);assert assembly.ForceRebuild3(False)
    session.save_assembly(str(state/'Контрольная сборка.SLDASM'));record(owned)
    template=sw.GetUserPreferenceStringValue(10) # installed swDefaultTemplateDrawing
    assert template and Path(template).is_file(),'Configured drawing template required.'
    raw=sw.NewDocument(template,0,0,0);assert raw is not None
    drawing=binding.wrap(raw,module.IModelDoc2);owned.append(drawing);record(owned)
    assert drawing.GetType()==3 and drawing.SetTitle2('Контрольный чертёж сохранения')
    assert drawing.SaveAs3(str(state/'Контрольный чертёж.SLDDRW'),0,1)==0;record(owned)
    # Real native edits belong to this setup, not to the public v2 tool.
    first=owned[0];activate_owned(sw,first,first.GetTitle())
    dimension=binding.wrap(first.Parameter('D1@Контрольный блок 1'),module.IDimension);assert dimension is not None
    names=__import__('win32com.client',fromlist=['VARIANT']).VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_BSTR,['Основная'])
    assert dimension.SetSystemValue3(.007,3,names)==0 and first.ForceRebuild3(False)
    activate_owned(sw,assembly,assembly.GetTitle());assert assembly.ForceRebuild3(False)
    assert assembly.AddCustomInfo3('','Контроль сохранения',30,'Сборка после изменения')
    activate_owned(sw,drawing,drawing.GetTitle())
    sheet=binding.wrap(binding.wrap(drawing,module.IDrawingDoc).GetCurrentSheet(),module.ISheet)
    sheet.SetName('Лист после сохранения')
    assert 'Лист после сохранения' in binding.wrap(drawing,module.IDrawingDoc).GetSheetNames()
    assert all(model.GetSaveFlag() for model in (first,assembly,drawing))
    return first,assembly,drawing


def roundtrip(sw,module,model,state,kind,report,persist):
    """Independent owned copy/reload evidence, not a v2 open/close claim."""
    before=native_snapshot();physical=physical_state(sw,module);models=[binding.wrap(raw,module.IModelDoc2) for raw in sw.GetDocuments() or ()]
    source=Path(model.GetPathName());copy=state/('Перечитанная '+kind+source.suffix);assert not copy.exists()
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest();shutil.copyfile(source,copy)
    cfg='Основная' if model.GetType()!=3 else ''
    report['pending_roundtrip']=str(copy);persist()
    raw,errors,warnings=sw.OpenDoc6(str(copy),model.GetType(),1,cfg,0,0)
    assert raw is not None
    clone=binding.wrap(raw,module.IModelDoc2);report['roundtrip_owned']=dict(path=clone.GetPathName(),title=clone.GetTitle());persist()
    assert errors==0 and warnings==0 and Path(clone.GetPathName()).resolve()==copy
    assert all(native_identity(clone)!=native_identity(existing) for existing in models)
    if kind=='деталь':
        actual=binding.wrap(clone.Parameter('D1@Контрольный блок 1'),module.IDimension).SystemValue
        assert math.isclose(actual,.007,abs_tol=1e-12)
    elif kind=='сборка':assert clone.GetCustomInfoValue('','Контроль сохранения')=='Сборка после изменения'
    else:assert 'Лист после сохранения' in binding.wrap(clone,module.IDrawingDoc).GetSheetNames()
    current=[binding.wrap(raw,module.IModelDoc2) for raw in sw.GetDocuments() or ()]
    assert len(current)==len(models)+1 and all(any(native_identity(item)==native_identity(allowed) for allowed in models+[clone]) for item in current)
    assert clone.GetBlockingState()==0 and clone.GetSaveFlag() is False
    sw.CloseDoc(clone.GetTitle());assert not any(native_identity(item)==native_identity(clone) for item in [binding.wrap(raw,module.IModelDoc2) for raw in sw.GetDocuments() or ()])
    original=next(item for item in models if native_identity(item)==physical[1]);activate_owned(sw,original,original.GetTitle())
    assert native_snapshot()==before and physical_state(sw,module)==physical and hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    report.pop('pending_roundtrip');report.pop('roundtrip_owned');report.setdefault('native_roundtrips',[]).append(dict(kind=kind,verified=True));persist()


async def cases(read,context,safe,sw,module,targets,report,persist,public=False):
    first,assembly,drawing=targets
    async def save(label,model,error=None,revision=None,request=None,arguments=None):
        await safe();before=physical_state(sw,module)
        args=arguments or await context(model)
        prepared=succeeded(await read('document_prepare_save_native',args));await safe();assert physical_state(sw,module)==before
        call_args={**args,'expected_revision':revision or prepared['revision']}
        if request is not None:call_args['request_id']=request
        result=await read('document_save_native',call_args);await safe();assert physical_state(sw,module)==before
        if error:assert result['status']=='failed' and result['error']['code']==error,result
        else:
            value=succeeded(result);assert value['verified'] and result.get('mutation',{}).get('phase','committed')=='committed'
            assert value['value']['native']=={'success':True,'errors':0,'warnings':0} and model.GetSaveFlag() is False
            expected=next(row for row in value['after']['semantic']['documents'] if row['document_id']==args['document_id'])
            assert expected['file']['sha256']==hashlib.sha256(Path(model.GetPathName()).read_bytes()).hexdigest()
        report['cases'].append(dict(label=label,passed=True,result=result));persist();return result,call_args
    request=uuid.uuid4().hex
    original,replay_args=await save('real_part_file_save',first,request=request)
    await save('real_referenced_assembly_file_save',assembly)
    await save('real_drawing_sheet_file_save',drawing)
    before=physical_state(sw,module);repeat=await read('document_save_native',dict(replay_args,request_id=request));await safe()
    assert repeat['operation_id']==original['operation_id'] and repeat['data']==original['data'] and physical_state(sw,module)==before
    report['cases'].append(dict(label='save_request_replay_no_second_write',passed=True,result=repeat));persist()
    await save('stale_save_revision_before_native_refused',first,error='stale_revision',revision='rev_stale')
    if public:return
    for model,kind in ((first,'деталь'),(assembly,'сборка'),(drawing,'чертёж')):
        await safe();roundtrip(sw,module,model,Path(report['state_dir']),kind,report,persist)
        report['cases'].append(dict(label=kind+'_disk_content_native_reload',passed=True));persist()
    for label,args,expected in [('inactive_configuration_refused',{**(await context(first)),'configuration':'Вариант'},'configuration_not_active'),
                                ('foreign_document_refused',{'document_id':'doc_foreign','configuration':'Основная'},'document_not_open')]:
        before=physical_state(sw,module);result=await read('document_prepare_save_native',args);await safe()
        assert result['status']=='failed' and result['error']['code']==expected and physical_state(sw,module)==before
        report['cases'].append(dict(label=label,passed=True,result=result));persist()


async def internal(state,sw,module,targets,report,persist):
    adapter=SolidWorksDocuments();docs=DocumentCatalog(adapter);store=JobStore(state/'jobs.sqlite');runner=JobRunner(store,InlineSta());catalog=NativeDocumentSaveCatalog(docs,store,'native-save-test')
    async def read(tool,args):
        args=dict(args);request=args.pop('request_id',uuid.uuid4().hex);spec=SPECS[tool]
        method=catalog.save if spec.mutates else catalog.prepare_save
        context_args={key:args[key] for key in ('document_id','configuration','expected_revision') if key in args}
        job=runner.submit(request,spec.operation,args,lambda op:method(op,**args) if spec.mutates else method(**args),context=context_args,
                          mutates=spec.mutates,pass_operation_id=True,verify=(lambda value:value['verified'] is True) if spec.mutates else None)
        return dict(status=job['status'],operation_id=job['operation_id'],data=job['result'],error=job['error'],mutation=job.get('mutation'))
    async def context(model):
        item=next(row for row in docs.list()['documents'] if row['title']==model.GetTitle())
        return dict(document_id=item['document_id'],configuration=item['active_configuration'])
    async def safe():
        assert all(row['status'] in ('succeeded','failed') for row in store.list(limit=100)['items'])
        assert not store.mutation_blockers('native-save-test','any',effect_scope='application')
    try:await cases(read,context,safe,sw,module,targets,report,persist)
    finally:docs.close();store.close()


async def public(entry,state,sw,module,targets,report,persist,gate):
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
            item=next(row for row in succeeded(await call(client,'document_list'))['documents'] if row['title']==model.GetTitle())
            return dict(document_id=item['document_id'],configuration=item['active_configuration'])
        async def safe():await require_native_cleanup(client,gate)
        await context(targets[0]);await safe();await cases(read,context,safe,sw,module,targets,report,persist,True);await safe()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks',action='store_true');parser.add_argument('--public',action='store_true');parser.add_argument('--internal-report',type=Path)
    parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--expected-version',required=True);parser.add_argument('--expected-git-sha',required=True);parser.add_argument('--state-dir',type=Path,required=True)
    args=parser.parse_args()
    if not args.run_solidworks:parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    wheel=validate_wheel(args.wheel,expected_version=args.expected_version,expected_git_sha=args.expected_git_sha);entry=installed_identity(wheel)
    verifier_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();fixture_sha=hashlib.sha256(Path(__file__).with_name('verify_geometry_reads.py').read_bytes()).hexdigest()
    if args.public:
        assert args.internal_report;prior=json.loads(args.internal_report.read_text(encoding='utf8'))
        assert prior['accepted'] and prior['scope']=='internal_native_current_file_save_v1' and len(prior['cases'])==INTERNAL_CASES and prior['verifier_sha256']==verifier_sha and prior['fixture_sha256']==fixture_sha
        assert all(prior['wheel'][key]==wheel[key] for key in ('git_sha','source_digest','package_version','wheel_sha256'))
    private=Path(__file__).resolve().parents[1]/'work';state=args.state_dir.resolve();assert state.is_relative_to(private) and state!=private and not state.exists();state.mkdir(parents=True)
    report=dict(accepted=False,scope=('public' if args.public else 'internal')+'_native_current_file_save_v1',wheel=wheel,cases=[],
                verifier_sha256=verifier_sha,fixture_sha256=fixture_sha,state_dir=str(state))
    def persist():(state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    def record(owned):report['owned_documents']=[dict(title=model.GetTitle(),path=model.GetPathName(),type=model.GetType()) for model in owned];persist()
    start=time.perf_counter();pythoncom.CoInitialize();sw=None;owns_setup=False;gate=SessionCleanupGate()
    try:
        sw=binding.connect(show=False);module=binding.module();assert not sw.GetDocuments() and sw.CommandInProgress is False
        baseline=native_snapshot();preferences=application_preferences(sw);report['solidworks_revision']=str(sw.RevisionNumber())
        sw.CommandInProgress=True;assert sw.CommandInProgress is True;owns_setup=True
        with fixtures(cleanup_gate=lambda:report.get('cleanup_confirmed') is True,on_owned_change=record) as (session,owned,_):
            targets=setup(session,owned,state,sw,module,record)
            sw.CommandInProgress=False;assert sw.CommandInProgress is False;owns_setup=False
            if args.public:asyncio.run(public(entry,state,sw,module,targets,report,persist,gate))
            else:asyncio.run(internal(state,sw,module,targets,report,persist))
            assert len(report['cases'])==(PUBLIC_CASES if args.public else INTERNAL_CASES)
            assert not args.public or gate.can_cleanup()
            current=[binding.wrap(raw,module.IModelDoc2) for raw in sw.GetDocuments() or ()]
            assert len(current)==len(owned)==4 and sw.CommandInProgress is False and not report.get('pending_roundtrip')
            assert all(any(native_identity(item)==native_identity(model) for model in owned) and item.GetBlockingState()==0 for item in current)
            assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'fixture_preferences');report['cleanup_confirmed']=True;persist()
        assert not sw.GetDocuments() and native_snapshot()==baseline and sw.CommandInProgress is False
        assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'restored_preferences')
        report.update(fixtures_closed=True,baseline_restored=True,accepted=True)
    except BaseException as exc:report.update(error_type=type(exc).__name__,error=str(exc));raise
    finally:
        try:
            if owns_setup:assert sw.CommandInProgress is True;sw.CommandInProgress=False;assert sw.CommandInProgress is False
        finally:report['elapsed_seconds']=time.perf_counter()-start;persist();pythoncom.CoUninitialize()
    print(json.dumps(dict(accepted=report['accepted'],cases=len(report['cases']),scope=report['scope'])))


if __name__=='__main__':main()
