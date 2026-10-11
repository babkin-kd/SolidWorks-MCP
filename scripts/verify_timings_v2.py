"""Exact installed timing facade and optional real empty-session document reads.

No model is created, edited, opened, saved or closed. Native opt-in requires an
empty/free session. A read timeout is drained through the existing supervisor;
the process is never killed to obtain a timing number. This is a diagnostics
acceptance scope, not a final stage-one CAD matrix or a geometry benchmark.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from verify_installed_metadata import installed_identity,verify_metadata
from verify_wheel_artifact import validate_wheel,require
from verifier_lifecycle import ToolSpec,open_supervised_session


def distribution(values):
    ordered=sorted(values);index=(len(ordered)-1)*.95;lower=int(index)
    return dict(sample_count=len(values),median_s=statistics.median(values),
        p95_s=ordered[lower]+(ordered[min(lower+1,len(ordered)-1)]-ordered[lower])*(index-lower))


def envelope(raw):
    require(not raw.isError and isinstance(raw.structuredContent,dict),'Missing envelope.')
    return raw.structuredContent


async def exercise(entry,state,wheel,enabled,native):
    args=['--state-dir',str(state)]
    if enabled:args+=['--enable-timings','--timings-max-records','1000','--timings-retention-days','1','--timings-max-mib','16']
    params=StdioServerParameters(command=str(entry),args=args,
        env={**os.environ,'PYTHONPATH':'','PYTHONNOUSERSITE':'1'})
    raw_session={};durations=[]
    @asynccontextmanager
    async def session():
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as raw:
                await raw.initialize();raw_session['client']=raw
                info=envelope(await raw.call_tool('system_get_info',{}))
                verify_metadata((await raw.list_tools()).tools,info['data'],wheel)
                yield raw
    @asynccontextmanager
    async def scoped_session():
        if native:
            async with open_supervised_session(session,
                    tool_specs={'document_list':ToolSpec('document.list',False)},journal_path=state/'jobs.sqlite') as client:
                yield client
        else:
            # No durable/CAD call is permitted in this branch; an empty tracker
            # intentionally cannot authorize native supervisor cleanup.
            async with session() as client:
                yield client
    async with scoped_session() as client:
        raw=raw_session['client']
        # Metadata workload and counts stay separate from native read workloads.
        for _ in range(20):
            start=time.perf_counter();result=envelope(await raw.call_tool('system_get_info',{}))
            durations.append(time.perf_counter()-start)
            require(result['status']=='succeeded','Metadata call failed.')
        missing=envelope(await raw.call_tool('job_get',{'operation_id':'job_missing_private_probe'}))
        require(missing['status']=='failed','Missing-job poll falsely succeeded.')
        native_durations=[]
        if native:
            for index in range(10):
                start=time.perf_counter()
                result=envelope(await client.call_tool('document_list',dict(
                    request_id=f'native-timings-{index}',timeout_s=0.)))
                while result['status'] in ('queued','running'):
                    await asyncio.sleep(.25)
                    result=envelope(await client.call_tool('job_get',{'operation_id':result['operation_id']}))
                native_durations.append(time.perf_counter()-start)
                require(result['status']=='succeeded','Native read did not succeed; do not repeat unknown work.')
                # document_list returns result directly; job_get exposes durable row.
                data=result['data']
                data=data['result'] if 'result' in data and 'payload' in data else data
                require(data['documents']==[],'Empty native baseline changed.')
        # Optional local diagnostic reads bypass the durable CAD dispatcher.
        measured=envelope(await raw.call_tool('diagnostics_get_timings',dict(period_s=3600.)))
        require(measured['status']=='succeeded','Timing facade failed.')
        result=measured['data'];require(result['enabled'] is enabled,'Operator configuration ignored.')
        if enabled:
            groups=result['groups'];expected_build={key:wheel[key] for key in ('package_version','git_sha','source_digest')}
            require(result['available'] and all(g['build']==expected_build for g in groups),'Wrong build grouping.')
            metadata=next(g for g in groups if g['operation']=='system_get_info')
            require(metadata['sample_count']==21 and metadata['kind']=='mcp_call','Completed metadata counts differ.')
            require(any(g['kind']=='poll' and g['outcome']=='failed' for g in groups),'Failed poll was mixed or missing.')
            if native:
                jobs=[g for g in groups if g['operation']=='document.list' and g['kind']=='job']
                require(len(jobs)==1 and jobs[0]['sample_count']==10 and jobs[0]['outcome']=='succeeded','Actual CAD read count differs.')
                require(jobs[0]['phases']['com']['interval_count']>=10,'Actual GetDocuments intervals were not recorded.')
            require('job_missing_private_probe' not in json.dumps(result),'Private request data leaked into aggregate.')
        else:
            require(result['sample_count']==0 and not (state/'timings.sqlite').exists(),'Disabled collection wrote storage.')
        invalid=envelope(await raw.call_tool('diagnostics_get_timings',dict(period_s=-1.)))
        require(invalid['status']=='failed' and invalid['error']['code']=='invalid_timing_filter','Invalid period accepted.')
        # drain() verifies the exact coherent job history before SDK shutdown.
    return dict(enabled=enabled,metadata_transport=distribution(durations),
        native_read_transport=distribution(native_durations) if native_durations else None,
        aggregates=result,supervisor_cleanup_verified=client.cleanup_gate.can_cleanup() if native else None,
        metadata_only_sdk_closed=not native)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--expected-version',required=True)
    parser.add_argument('--expected-git-sha',required=True)
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--run-solidworks',action='store_true')
    args=parser.parse_args();state=args.state_dir.resolve()
    private=Path(__file__).resolve().parents[1]/'work'
    require(state.is_relative_to(private) and state!=private and not state.exists(),'Use fresh private state.')
    require(not os.environ.get('PYTHONPATH'),'Installed package only.')
    wheel=validate_wheel(args.wheel,expected_version=args.expected_version,expected_git_sha=args.expected_git_sha)
    entry=installed_identity(wheel);state.mkdir(parents=True)
    report=dict(accepted=False,scope='installed_timing_facade_and_empty_native_reads_v1',wheel=wheel,
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),native_acceptance=False,
        model_mutations=0,modes=[])
    def persist():(state/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf8')
    sw=None;initialized=False
    try:
        if args.run_solidworks:
            import pythoncom
            from solidworks_mcp import binding
            from verify_document_reads import native_snapshot
            pythoncom.CoInitialize();initialized=True;sw=binding.connect(show=False)
            require(not sw.GetDocuments() and not sw.CommandInProgress,'Empty/free native baseline required.')
            baseline=native_snapshot();report['solidworks_revision']=sw.RevisionNumber()
        for enabled in (False,True):
            mode=state/('enabled' if enabled else 'disabled');mode.mkdir()
            report['modes'].append(asyncio.run(exercise(entry,mode,wheel,enabled,args.run_solidworks)))
            persist()
        if sw is not None:
            require(native_snapshot()==baseline and not sw.GetDocuments() and not sw.CommandInProgress,
                'Read-only native baseline not preserved.')
            report['native_acceptance']=True;report['native_baseline_preserved']=True
        report['accepted']=True;persist()
    except BaseException as exc:
        report['error_type']=type(exc).__name__;persist();raise
    finally:
        sw=None
        if initialized:pythoncom.CoUninitialize()
    print(json.dumps({key:report[key] for key in ('accepted','scope','native_acceptance','model_mutations')}))


if __name__=='__main__':main()
