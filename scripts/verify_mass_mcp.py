"""Installed public guarded mass acceptance on two explicitly owned fixtures."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import uuid

import pythoncom
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from solidworks_mcp import binding
from verify_installed_metadata import installed_identity,verify_metadata
from verify_wheel_artifact import validate_wheel
from verify_mass_properties import source_state,confirm_source,check_analytical
from verify_geometry_reads import fixtures
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_dimension_mcp import SessionCleanupGate,call,succeeded,require_native_cleanup
from verifier_lifecycle import ToolSpec,open_supervised_session

SPECS={
    'document_list':ToolSpec('document.list',False),
    'body_list':ToolSpec('geometry.list',False,argument_defaults={'body_type':'all','limit':100,'cursor':''},
                         constant_args={'kind':'body'}),
    'measurement_prepare_mass':ToolSpec('measurement.prepare_mass',False,argument_defaults={'body_id':None}),
    'measurement_get_mass':ToolSpec('measurement.mass',True,argument_defaults={'body_id':None},
        prewrite_failure_codes=frozenset({'stale_revision','object_reference_not_found','observation_revision_mismatch'})),
}


async def exercise(entry,state,sw,module,owned,report,persist,gate):
    params=StdioServerParameters(command=str(entry),args=['--state-dir',str(state/'server')],
        env={**os.environ,'PYTHONPATH':'','PYTHONNOUSERSITE':'1'})
    @asynccontextmanager
    async def session():
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as raw:
                await raw.initialize()
                info=succeeded(await call(raw,'system_get_info'))
                tools=(await raw.list_tools()).tools
                report['metadata']=verify_metadata(tools,info,report['wheel']);persist()
                yield raw
    async with open_supervised_session(session,tool_specs=SPECS,journal_path=state/'server/jobs.sqlite',
                                       on_hold=lambda info:report.update(lifecycle_hold=True)) as client:
        gate.add(client)
        async def record(label,response):
            await require_native_cleanup(client,gate)
            assert response['status'] in ('succeeded','failed')
            report['cases'].append({'label':label,'passed':True,'operation_id':response['operation_id'],
                                     'status':response['status'],'error':response['error']});persist()
        async def context(model):
            docs=succeeded(await call(client,'document_list'))['documents']
            item=next(row for row in docs if row['title']==model.GetTitle())
            return dict(document_id=item['document_id'],configuration=item['active_configuration'],
                        expected_observation_revision=item['observation_revision'])
        target,other=owned
        ctx=await context(target)
        bodies=succeeded(await call(client,'body_list',**ctx))['items']
        solids=sorted((row for row in bodies if row['body_type']=='solid'),key=lambda row:row['bounding_box_mm']['min_mm'][0])
        assert len(solids)==2
        async def measure(label,ctx,body_id=None,count=2,x=30.,error=None):
            await require_native_cleanup(client,gate)
            before=source_state(sw,module)
            args={**ctx,'body_id':body_id}
            prepared=succeeded(await call(client,'measurement_prepare_mass',**args))
            request='mass-'+uuid.uuid4().hex
            response=await call(client,'measurement_get_mass',**args,expected_revision=prepared['revision'],request_id=request,timeout_s=0.)
            await require_native_cleanup(client,gate)
            if error:
                assert response['status']=='failed' and response['error']['code']==error
            else:
                result=succeeded(response);check_analytical(result,count,x)
                assert result['verified'] and result['model_geometry_modified'] is False
                guard=result['execution_guard']
                assert guard['released'] and guard['selection_preserved'] and guard['original_command_in_progress'] is False
                assert guard['model_guards']==[{'original_state':0,'locked_state':2,'released_state':0}]
            confirm_source(before,source_state(sw,module))
            assert sw.CommandInProgress is False
            await record(label,response)
            return args,prepared,request,response
        args,prepared,request,first=await measure('public_all_solids',ctx)
        again=await call(client,'measurement_get_mass',**args,expected_revision=prepared['revision'],request_id=request,timeout_s=0.)
        assert again['operation_id']==first['operation_id'] and succeeded(again)==succeeded(first)
        await record('request_replay_one_calculation',again)
        await measure('public_explicit_second_solid',ctx,solids[1]['object_id'],1,50.)
        stale=await call(client,'measurement_get_mass',**ctx,expected_revision='rev_obsolete',timeout_s=0.)
        assert stale['status']=='failed' and stale['error']['code']=='stale_revision'
        await record('public_stale_prewrite',stale)
        foreign=await call(client,'measurement_prepare_mass',**(await context(other)),body_id=solids[0]['object_id'])
        assert foreign['status']=='failed' and foreign['error']['code']=='object_reference_not_found'
        await record('public_foreign_body_prewrite',foreign)
        # Change only exact owned fixture selection after a terminal protocol proof.
        await require_native_cleanup(client,gate)
        from solidworks_mcp.cad_documents import SolidWorksDocuments
        adapter=SolidWorksDocuments()
        try:
            actual=sorted(adapter.bodies(target,'solid'),key=lambda body:body.GetBodyBox()[0])
            target.ClearSelection2(True)
            assert actual[0].Select2(False,None)
        finally:adapter.close()
        await measure('public_selected_other_body_restored',await context(target),solids[1]['object_id'],1,50.)
        await require_native_cleanup(client,gate)
        report['public_suite_passed']=True;persist()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks',action='store_true')
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--expected-version',required=True)
    parser.add_argument('--expected-git-sha',required=True)
    parser.add_argument('--internal-report',type=Path,required=True)
    parser.add_argument('--state-dir',type=Path,required=True)
    args=parser.parse_args()
    if not args.run_solidworks:parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    wheel=validate_wheel(args.wheel,expected_version=args.expected_version,expected_git_sha=args.expected_git_sha)
    entry=installed_identity(wheel)
    internal=json.loads(args.internal_report.read_text(encoding='utf8'))
    assert internal['accepted'] and internal['scope']=='internal_guarded_part_mass_native_v1' and len(internal['cases'])==22
    assert all(internal['wheel'][key]==wheel[key] for key in ('git_sha','source_digest','package_version','wheel_sha256'))
    assert internal['verifier_sha256']==hashlib.sha256(Path(__file__).with_name('verify_mass_properties.py').read_bytes()).hexdigest()
    private=Path(__file__).resolve().parents[1]/'work'
    state=args.state_dir.resolve()
    assert state.is_relative_to(private) and state!=private and not state.exists()
    state.mkdir(parents=True)
    report={'accepted':False,'scope':'public_guarded_part_mass_native_v1','wheel':wheel,'cases':[],
            'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def persist():(state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    gate=SessionCleanupGate();pythoncom.CoInitialize()
    sw=None;owns_setup_flag=False
    try:
        sw=binding.connect(show=False);module=binding.module()
        assert not sw.GetDocuments() and sw.CommandInProgress is False
        baseline=native_snapshot();preferences=application_preferences(sw)
        sw.CommandInProgress=True
        assert sw.CommandInProgress is True
        owns_setup_flag=True
        with fixtures(cleanup_gate=lambda:report.get('cleanup_confirmed') is True) as (_,owned,_):
            report['owned_documents']=[{'title':model.GetTitle(),'path':model.GetPathName()} for model in owned];persist()
            assert owns_setup_flag and sw.CommandInProgress is True
            sw.CommandInProgress=False
            assert sw.CommandInProgress is False
            owns_setup_flag=False
            asyncio.run(exercise(entry,state,sw,module,owned,report,persist,gate))
            assert gate.can_cleanup() and report['public_suite_passed'] and sw.CommandInProgress is False
            current=tuple(binding.wrap(raw,module.IModelDoc2) for raw in sw.GetDocuments() or ())
            tokens=tuple(model._oleobj_.QueryInterface(pythoncom.IID_IUnknown) for model in owned)
            assert len(current)==len(owned)==2
            assert all(any(model._oleobj_.QueryInterface(pythoncom.IID_IUnknown)==token for token in tokens) for model in current)
            assert all(not model.GetPathName() and model.GetBlockingState()==0 for model in current)
            assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'fixture_preferences')
            report['cleanup_confirmed']=True;persist()
        assert native_snapshot()==baseline and not sw.GetDocuments() and sw.CommandInProgress is False
        assert_non_stl_preferences(lambda:application_preferences(sw),preferences,report,'restored_preferences')
        report['fixtures_closed']=True;report['baseline_restored']=True;report['accepted']=True
    except BaseException as exc:
        report['error_type']=type(exc).__name__;report['error']=str(exc);raise
    finally:
        if owns_setup_flag:
            assert sw.CommandInProgress is True
            sw.CommandInProgress=False
            assert sw.CommandInProgress is False
        persist();pythoncom.CoUninitialize()
    print(json.dumps({'accepted':report['accepted'],'cases':len(report['cases'])}))


if __name__=='__main__':main()
