"""Installed/internal and public require-clean CloseDoc on exact owned fixtures."""
import argparse,asyncio,hashlib,json,os,time,uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pythoncom
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.native_document_close import NativeDocumentCloseCatalog
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
from verify_native_document_save import physical_state
from verifier_lifecycle import ToolSpec,open_supervised_session

SPECS={'document_list':ToolSpec('document.list',False),'document_get':ToolSpec('document.get',False),
       'document_prepare_close_native':ToolSpec('document.prepare_close_native',False),
       'document_close_native':ToolSpec('document.close_native',True,prewrite_failure_codes=frozenset({'stale_revision'}))}
INTERNAL_CASES=12
PUBLIC_CASES=10


def setup(session,owned,state,sw,module,record):
    assert len(owned)==2 and sw.CommandInProgress is True
    first,second=owned
    for index,model in enumerate(owned):
        activate_owned(sw,model,model.GetTitle());session._model=model
        session.save_part(str(state/f'Контрольная деталь закрытия {index+1}.SLDPRT'));record(owned)
    session.new_part();hidden=session._model;owned.append(hidden);record(owned)
    assert hidden.SetTitle2('Скрытая контрольная деталь закрытия')
    binding.wrap(hidden.GetActiveConfiguration(),module.IConfiguration).Name='Основная'
    session.save_part(str(state/'Скрытая контрольная деталь.SLDPRT'));record(owned)
    session.new_assembly();assembly=session._model;owned.append(assembly);record(owned)
    assert assembly.SetTitle2('Контрольная сборка закрытия')
    binding.wrap(assembly.GetActiveConfiguration(),module.IConfiguration).Name='Основная'
    session.insert_component(first.GetPathName(),fixed=False);assert assembly.ForceRebuild3(False)
    session.save_assembly(str(state/'Контрольная сборка закрытия.SLDASM'));record(owned)
    template=sw.GetUserPreferenceStringValue(10);assert template and Path(template).is_file()
    raw=sw.NewDocument(template,0,0,0);assert raw is not None
    drawing=binding.wrap(raw,module.IModelDoc2);owned.append(drawing);record(owned)
    assert drawing.GetType()==3 and drawing.SetTitle2('Контрольный чертёж закрытия')
    assert drawing.SaveAs3(str(state/'Контрольный чертёж закрытия.SLDDRW'),0,1)==0;record(owned)
    # Component insertion may mark its source part dirty. Finish the exact owned
    # setup before intentionally making the neighbour dirty for the close test.
    for model in owned:
        if model.GetSaveFlag():assert model.Save3(1,0,0)==(True,0,0)
    assert all(model.GetSaveFlag() is False for model in owned)
    assert second.AddCustomInfo3('','Несохранённое контрольное свойство',30,'Сохранить только после проверки соседей')
    second.SetSaveFlag();assert second.GetSaveFlag() is True
    hidden.Visible=False;assert hidden.Visible is False
    assert native_identity(binding.wrap(sw.ActiveDoc,module.IModelDoc2))==native_identity(drawing)
    return first,second,hidden,assembly,drawing


async def cases(read,context,safe,sw,module,targets,owned,report,persist,record,public=False):
    first,second,hidden,assembly,drawing=targets
    contexts=[await context(model) for model in targets]
    first_args,second_args,hidden_args,asm_args,draw_args=contexts
    hidden_id=hidden_args['document_id']
    files={model.GetPathName():hashlib.sha256(Path(model.GetPathName()).read_bytes()).hexdigest() for model in owned}
    report['baseline_owned_files']=dict(files);persist()
    def disk_unchanged():
        assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in files.items())
    def add(label,result):report['cases'].append(dict(label=label,passed=True,result=result));persist()
    async def refused(label,args,code,tool='document_prepare_close_native'):
        await safe();before=native_snapshot();physical=physical_state(sw,module)
        result=await read(tool,args);await safe()
        assert result['status']=='failed' and result['error']['code']==code,result
        assert native_snapshot()==before and physical_state(sw,module)==physical;disk_unchanged();add(label,result)
    if not public:
        await refused('inactive_configuration_refused',{**first_args,'configuration':'Вариант','allowed_hidden_document_ids':[hidden_id]},'configuration_not_active')
        await refused('foreign_document_refused',dict(document_id='doc_foreign',configuration='Основная'),'document_not_open')
    await refused('hidden_collateral_requires_exact_allowlist',asm_args,'native_close_hidden_impact_not_allowed')
    await refused('dirty_target_refused',{**second_args,'allowed_hidden_document_ids':[hidden_id]},'native_close_dirty_document')
    await refused('referenced_data_scope_refused',{**first_args,'allowed_hidden_document_ids':[hidden_id]},'native_close_referenced_data_unsupported')

    async def close(label,args,retiring,request=None):
        await safe();before=physical_state(sw,module)
        retired=[native_identity(model) for model in retiring]
        prepared=succeeded(await read('document_prepare_close_native',args));await safe()
        assert physical_state(sw,module)==before
        expected_ids=[(await context(model))['document_id'] for model in retiring]
        assert set(prepared['impact']['retiring_document_ids'])==set(expected_ids)
        data={**args,'expected_revision':prepared['revision']}
        if request:data['request_id']=request
        result=await read('document_close_native',data);await safe();value=succeeded(result)
        assert value['verified'] and value['value']['ui_closed'] and value['value']['data_unload_claimed'] is False
        assert value['value']['native']=={'native_call_returned':True}
        assert set(value['value']['retiring_document_ids'])==set(expected_ids)
        for model in retiring:
            # Object identity removal only: no native getter on retired targets.
            owned[:]=[current for current in owned if current is not model]
        record(owned)
        after=physical_state(sw,module)
        assert after[0]==tuple(row for row in before[0] if row[0] not in retired)
        assert after[2:]==before[2:] and all(token!=after[1] for token in retired)
        disk_unchanged();assert not owned or second.GetSaveFlag() is True
        add(label,result);return result,data

    request=uuid.uuid4().hex
    original,replay_args=await close('inactive_assembly_and_explicit_hidden_retirement',
        {**asm_args,'allowed_hidden_document_ids':[hidden_id]},[assembly,hidden],request)
    await safe();before=physical_state(sw,module)
    replay=await read('document_close_native',replay_args);await safe()
    assert replay['operation_id']==original['operation_id'] and replay['data']==original['data']
    assert physical_state(sw,module)==before;disk_unchanged();add('request_replay_no_second_close',replay)
    await refused('retired_document_id_invalid',asm_args,'document_not_open',tool='document_get')
    draw_policy={**draw_args,'active_after_document_id':first_args['document_id']}
    await refused('stale_close_revision_prewrite',{**draw_policy,'expected_revision':'rev_stale'},'stale_revision',tool='document_close_native')
    await close('active_drawing_explicit_survivor',draw_policy,[drawing])
    await close('active_part_preserves_dirty_neighbor',{**first_args,'active_after_document_id':second_args['document_id']},[first])
    await safe();assert len(owned)==1 and owned[0] is second and second.GetSaveFlag() is True
    # Owned fixture preparation, not MCP save/first-save acceptance.
    assert second.Save3(1,0,0)==(True,0,0) and second.GetSaveFlag() is False
    files[second.GetPathName()]=hashlib.sha256(Path(second.GetPathName()).read_bytes()).hexdigest()
    report['last_fixture_cleaned_by_native_setup']=True;persist()
    assert sw.UserControl is True
    await close('last_clean_document_user_controlled_session',second_args,[second])
    assert not sw.GetDocuments() and not owned


async def internal(state,sw,module,targets,owned,report,persist,record):
    adapter=SolidWorksDocuments();docs=DocumentCatalog(adapter);store=JobStore(state/'jobs.sqlite')
    runner=JobRunner(store,InlineSta());catalog=NativeDocumentCloseCatalog(docs,store,'native-close-test')
    async def read(tool,args):
        args=dict(args);request=args.pop('request_id',uuid.uuid4().hex);spec=SPECS[tool]
        method={'document_list':docs.list,'document_get':docs.get,
                'document_prepare_close_native':catalog.prepare_close,'document_close_native':catalog.close}[tool]
        context_args={key:args[key] for key in ('document_id','configuration','expected_revision') if key in args}
        job=runner.submit(request,spec.operation,args,lambda op:method(op,**args) if spec.mutates else method(**args),
            context=context_args,mutates=spec.mutates,pass_operation_id=True,
            verify=(lambda value:value['verified'] is True) if spec.mutates else None)
        return dict(status=job['status'],operation_id=job['operation_id'],data=job['result'],error=job['error'],mutation=job.get('mutation'))
    async def context(model):
        row=next(row for row in docs.list()['documents'] if row['path']==model.GetPathName())
        return dict(document_id=row['document_id'],configuration=row['active_configuration'])
    async def safe():
        assert all(row['status'] in ('succeeded','failed') for row in store.list(limit=100)['items'])
        assert not store.mutation_blockers('native-close-test','any',effect_scope='application')
    try:await cases(read,context,safe,sw,module,targets,owned,report,persist,record)
    finally:docs.close();store.close()


async def public(entry,state,sw,module,targets,owned,report,persist,record,gate):
    params=StdioServerParameters(command=str(entry),args=['--state-dir',str(state/'server')],
                                env={**os.environ,'PYTHONPATH':'','PYTHONNOUSERSITE':'1'})
    @asynccontextmanager
    async def factory():
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as raw:
                await raw.initialize();info=succeeded(await call(raw,'system_get_info'))
                report['metadata']=verify_metadata((await raw.list_tools()).tools,info,report['wheel']);persist();yield raw
    async with open_supervised_session(factory,tool_specs=SPECS,journal_path=state/'server/jobs.sqlite',
                                       on_hold=lambda info:report.update(lifecycle_hold=True)) as client:
        gate.add(client)
        async def read(tool,args):return await call(client,tool,**args,timeout_s=0.)
        async def context(model):
            row=next(row for row in succeeded(await call(client,'document_list'))['documents'] if row['path']==model.GetPathName())
            return dict(document_id=row['document_id'],configuration=row['active_configuration'])
        async def safe():await require_native_cleanup(client,gate)
        await context(targets[0]);await safe()
        await cases(read,context,safe,sw,module,targets,owned,report,persist,record,True);await safe()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks',action='store_true');parser.add_argument('--public',action='store_true')
    parser.add_argument('--internal-report',type=Path);parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--expected-version',required=True);parser.add_argument('--expected-git-sha',required=True)
    parser.add_argument('--state-dir',type=Path,required=True);args=parser.parse_args()
    if not args.run_solidworks:parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    wheel=validate_wheel(args.wheel,expected_version=args.expected_version,expected_git_sha=args.expected_git_sha)
    entry=installed_identity(wheel)
    hashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in
            ('verify_native_document_close.py','verify_geometry_reads.py','verify_native_document_save.py','verifier_lifecycle.py')}
    if args.public:
        assert args.internal_report;prior=json.loads(args.internal_report.read_text(encoding='utf8'))
        assert prior['accepted'] and prior['scope']=='internal_native_close_clean_v1' and len(prior['cases'])==INTERNAL_CASES
        assert all(case.get('passed') is True for case in prior['cases'])
        assert prior['verifier_hashes']==hashes
        assert all(prior['wheel'][key]==wheel[key] for key in ('git_sha','source_digest','package_version','wheel_sha256'))
    private=Path(__file__).resolve().parents[1]/'work';state=args.state_dir.resolve()
    assert state.is_relative_to(private) and state!=private and not state.exists();state.mkdir(parents=True)
    report=dict(accepted=False,scope=('public' if args.public else 'internal')+'_native_close_clean_v1',
                wheel=wheel,cases=[],verifier_hashes=hashes,state_dir=str(state))
    def persist():(state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    def record(owned):report['owned_documents']=[dict(title=model.GetTitle(),path=model.GetPathName(),type=model.GetType()) for model in owned];persist()
    start=time.perf_counter();pythoncom.CoInitialize();sw=None;owns_setup=False;gate=SessionCleanupGate()
    try:
        sw=binding.connect(show=False);module=binding.module()
        assert not sw.GetDocuments() and sw.CommandInProgress is False and sw.UserControl is True
        baseline=native_snapshot();preferences=application_preferences(sw)
        app_baseline=SolidWorksDocuments().native_close_application_context()
        report['solidworks_revision']=str(sw.RevisionNumber());persist()
        sw.CommandInProgress=True;assert sw.CommandInProgress is True;owns_setup=True
        with fixtures(cleanup_gate=lambda:report.get('cleanup_confirmed') is True,on_owned_change=record) as (session,owned,_):
            targets=setup(session,owned,state,sw,module,record)
            sw.CommandInProgress=False;assert sw.CommandInProgress is False;owns_setup=False
            if args.public:asyncio.run(public(entry,state,sw,module,targets,owned,report,persist,record,gate))
            else:asyncio.run(internal(state,sw,module,targets,owned,report,persist,record))
            assert len(report['cases'])==(PUBLIC_CASES if args.public else INTERNAL_CASES)
            assert not args.public or gate.can_cleanup()
            assert not owned and not sw.GetDocuments() and sw.CommandInProgress is False
            assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'fixture_preferences')
            report['cleanup_confirmed']=True;persist()
        assert native_snapshot()==baseline and sw.CommandInProgress is False
        assert SolidWorksDocuments().native_close_application_context()==app_baseline
        assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'restored_preferences')
        report.update(fixtures_closed=True,baseline_restored=True,accepted=True)
    except BaseException as exc:report.update(error_type=type(exc).__name__,error=str(exc));raise
    finally:
        try:
            if owns_setup:assert sw.CommandInProgress is True;sw.CommandInProgress=False;assert sw.CommandInProgress is False
        finally:report['elapsed_seconds']=time.perf_counter()-start;persist();pythoncom.CoUninitialize()
    print(json.dumps(dict(accepted=report['accepted'],cases=len(report['cases']),scope=report['scope'])))


if __name__=='__main__':main()
