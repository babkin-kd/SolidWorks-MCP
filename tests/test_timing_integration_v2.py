"""Optional measurements preserve real journal races and error semantics."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading

import pytest

from solidworks_mcp.jobs import JobStore,JobRunner,ExecutionFailure
from solidworks_mcp.mutations import MutationCoordinator,PreparedMutation
from solidworks_mcp.timings_v2 import TimingRecorder,TimingConfig
from solidworks_mcp.server_v2 import create_app
from solidworks_mcp.runtime_v2 import Runtime,READ_OPERATIONS,MUTATING_OPERATIONS

BUILD=dict(package_version='2.0.0.dev68',git_sha='a'*40,source_digest='b'*64)


class Worker:
    def __init__(self):self.pool=ThreadPoolExecutor(max_workers=1)
    def submit(self,function):return self.pool.submit(function)
    def shutdown(self,timeout_s=5):self.pool.shutdown(wait=True);return True


def recorder(tmp_path):
    return TimingRecorder(tmp_path/'timings.sqlite',config=TimingConfig(enabled=True),
        build=BUILD,operations=('test.read','test.write')+READ_OPERATIONS+MUTATING_OPERATIONS)


def rows(tmp_path):
    with sqlite3.connect(tmp_path/'timings.sqlite') as db:
        return [json.loads(row[0]) for row in db.execute('SELECT record FROM timings')]


def test_timeout_replay_and_polling_do_not_complete_or_duplicate_native_record(tmp_path):
    t=recorder(tmp_path);runner=JobRunner(JobStore(tmp_path/'jobs.sqlite'),Worker(),timings=t)
    entered,release=threading.Event(),threading.Event();calls=[]
    def read():
        calls.append(1);entered.set();assert release.wait(3);return {'private_path':'never measured'}
    try:
        job=runner.submit('private-request','test.read',{'document':'private model'},read)
        assert entered.wait(1)
        assert asyncio.run(runner.wait(job['operation_id'],.001))['status']=='running'
        assert t.report()['sample_count']==0
        assert runner.submit('private-request','test.read',{'document':'private model'},read)['operation_id']==job['operation_id']
        release.set()
        assert asyncio.run(runner.wait(job['operation_id'],2))['status']=='succeeded'
        runner.shutdown()
        data=rows(tmp_path)
        assert len(data)==1 and data[0]['operation_id']==job['operation_id']
        assert data[0]['outcome']=='succeeded' and 'queue' in data[0]['phases']
        assert calls==[1]
        assert 'private-request' not in json.dumps(data) and 'private model' not in json.dumps(data)
        assert 'private_path' not in json.dumps(data)
    finally:release.set();runner.shutdown();t.close()


def test_queued_cancellation_never_calls_function_and_records_cancelled(tmp_path):
    t=recorder(tmp_path);worker=Worker();release=threading.Event()
    worker.submit(lambda:release.wait(3))
    runner=JobRunner(JobStore(tmp_path/'jobs.sqlite'),worker,timings=t)
    try:
        job=runner.submit('cancel','test.read',{},lambda:pytest.fail('Cancelled function executed'))
        assert runner.store.cancel(job['operation_id'])['cancelled'] is True
        release.set();runner.shutdown()
        assert rows(tmp_path)[0]['outcome']=='cancelled'
    finally:release.set();runner.shutdown();t.close()


@pytest.mark.parametrize('uncertain,expected',[(False,'failed'),(True,'unknown')])
def test_job_failure_outcome_matches_journal_even_if_optional_storage_is_broken(tmp_path,uncertain,expected):
    t=recorder(tmp_path);t._db.close()  # Existing store fails, mandatory journal is independent.
    runner=JobRunner(JobStore(tmp_path/'jobs.sqlite'),Worker(),timings=t)
    def fail():raise ExecutionFailure('real_failure','private native error',uncertain=uncertain)
    try:
        job=runner.submit('fail','test.write',{},fail,mutates=True,verify=lambda _:True)
        final=asyncio.run(runner.wait(job['operation_id'],2))
        assert final['status']==expected and final['error']['code']=='real_failure'
        runner.shutdown()
        assert t.dropped_records==1 and t.storage_failures==1
    finally:runner.shutdown();t.close()


def test_dispatch_failure_is_separate_terminal_failed_record(tmp_path):
    class Broken(Worker):
        def submit(self,function):raise RuntimeError('dispatch unavailable')
    t=recorder(tmp_path);runner=JobRunner(JobStore(tmp_path/'jobs.sqlite'),Broken(),timings=t)
    try:
        job=runner.submit('dispatch','test.read',{},lambda:pytest.fail('Executed'))
        assert job['status']=='failed' and job['error']['code']=='dispatch_failed'
        assert rows(tmp_path)[0]['outcome']=='failed'
    finally:runner.shutdown();t.close()


@pytest.mark.parametrize('fail_apply,fail_restore,outcome',[(False,False,'succeeded'),(True,False,'failed'),(True,True,'unknown')])
def test_mutation_phase_measurements_keep_verified_restore_and_unknown_holds(tmp_path,fail_apply,fail_restore,outcome):
    t=recorder(tmp_path);store=JobStore(tmp_path/'jobs.sqlite');runner=JobRunner(store,Worker(),timings=t)
    coordinator=MutationCoordinator(store,'connection_test');state={'value':1}
    def apply(_):
        state['value']=2
        if fail_apply:raise ValueError('original failure')
        return 2
    def restore(before,_):
        if fail_restore:raise ValueError('restore failed')
        state.update(before)
    def execute(job_id):
        return coordinator.execute(job_id,document_id='doc_test',configuration='private config',expected_revision='revision',
            prepare=lambda:PreparedMutation('revision',dict(state)),validate=lambda _:True,
            apply=apply,inspect=lambda _:dict(state),verify=lambda b,a,v:a['value']==v,
            restore=restore,verify_restored=lambda b,a:b==a)
    try:
        job=runner.submit('mutate','test.write',{},execute,mutates=True,verify=lambda r:r['verified'],pass_operation_id=True,
            context=dict(document_id='doc_test',configuration='private config',expected_revision='revision'))
        final=asyncio.run(runner.wait(job['operation_id'],2));assert final['status']==outcome
        assert bool(store.mutation_blockers('connection_test','doc_test'))==(outcome=='unknown')
        runner.shutdown();data=rows(tmp_path)[0]
        assert data['outcome']==outcome
        assert {'queue','prepare','validate','apply_bundle','journal'}<=data['phases'].keys()
        assert ('restoration' in data['phases'])==fail_apply
        assert 'private config' not in json.dumps(data)
    finally:runner.shutdown();t.close()


def test_post_native_journal_failure_stays_unknown_in_diagnostics(tmp_path):
    t=recorder(tmp_path);store=JobStore(tmp_path/'jobs.sqlite');runner=JobRunner(store,Worker(),timings=t)
    original=store.finish;calls=[]
    def broken(*args,**kwargs):raise sqlite3.OperationalError('journal broken')
    store.finish=broken
    try:
        job=runner.submit('journal-failed','test.write',{},lambda:calls.append(1) or {'verified':True},
            mutates=True,verify=lambda r:r['verified'])
        runner.shutdown();data=rows(tmp_path)
        assert len(data)==1 and data[0]['outcome']=='unknown' and calls==[1]
    finally:store.finish=original;runner.shutdown();t.close()


def test_public_facade_has_envelope_and_no_cad_queue_or_payload_collection(tmp_path):
    t=recorder(tmp_path);store=JobStore(tmp_path/'jobs.sqlite')
    runtime=Runtime(store,worker_factory=lambda:pytest.fail('Diagnostics started CAD'),timings=t)
    app=create_app(store,runtime,timings=t)
    async def exercise():
        tools=await app.list_tools();schema=next(x for x in tools if x.name=='diagnostics_get_timings')
        assert set(schema.outputSchema['properties'])=={'status','operation_id','context','data','diagnostics','error'}
        result=await app.call_tool('job_get',{'operation_id':'private-missing'})
        assert result[1]['status']=='failed'
        _,content=await app.call_tool('diagnostics_get_timings',dict(period_s=60.,kind='poll'))
        assert content['data']['sample_count']==1
        group=content['data']['groups'][0]
        assert group['operation']=='job_get' and group['outcome']=='failed' and group['kind']=='poll'
        _,invalid=await app.call_tool('diagnostics_get_timings',dict(period_s=-1.))
        assert invalid['error']['code']=='invalid_timing_filter'
        assert t.report()['sample_count']==1  # No self-observation writes.
        assert 'private-missing' not in json.dumps(rows(tmp_path))
    try:asyncio.run(exercise())
    finally:runtime.shutdown();t.close()


def test_disabled_public_facade_validates_filters_without_creating_storage_or_cad(tmp_path):
    store=JobStore(tmp_path/'jobs.sqlite');runtime=Runtime(store,worker_factory=lambda:pytest.fail('CAD'))
    app=create_app(store,runtime)
    async def exercise():
        _,result=await app.call_tool('diagnostics_get_timings',dict(operation='document_list'))
        assert result['data']==dict(enabled=False,available=False,sample_count=0,groups=[])
        _,invalid=await app.call_tool('diagnostics_get_timings',dict(operation='private-model'))
        assert invalid['status']=='failed'
        assert not (tmp_path/'timings.sqlite').exists()
    try:asyncio.run(exercise())
    finally:runtime.shutdown()


def test_cancelled_public_wait_preserves_late_native_result_and_separate_measurements(tmp_path):
    t=recorder(tmp_path);store=JobStore(tmp_path/'jobs.sqlite')
    entered,release=threading.Event(),threading.Event()
    class Catalog:
        def list(self):entered.set();assert release.wait(3);return {'documents':[]}
        def close(self):pass
    runtime=Runtime(store,worker_factory=Worker,catalog_factory=Catalog,timings=t)
    app=create_app(store,runtime,timings=t)
    async def exercise():
        pending=asyncio.create_task(app.call_tool('document_list',dict(request_id='cancel-wait',timeout_s=2.)))
        await asyncio.to_thread(entered.wait,1)
        assert entered.is_set();pending.cancel()
        with pytest.raises(asyncio.CancelledError):await pending
        public=t.report(kind='mcp_call')['groups']
        assert len(public)==1 and public[0]['outcome']=='cancelled'
        assert t.report(kind='job')['sample_count']==0
        job=store.list(limit=1)['items'][0];assert job['status']=='running'
        release.set()
        final=await runtime._runner.wait(job['operation_id'],2)
        assert final['status']=='succeeded'
    try:asyncio.run(exercise());runtime.shutdown();assert t.report(kind='job')['groups'][0]['outcome']=='succeeded'
    finally:release.set();runtime.shutdown();t.close()


def test_concurrent_public_calls_keep_task_and_worker_phase_contexts_separate(tmp_path):
    t=recorder(tmp_path);store=JobStore(tmp_path/'jobs.sqlite')
    class Catalog:
        def list(self):return {'documents':[]}
        def close(self):pass
    runtime=Runtime(store,worker_factory=Worker,catalog_factory=Catalog,timings=t)
    app=create_app(store,runtime,timings=t)
    async def exercise():
        results=await asyncio.gather(*(app.call_tool('document_list',dict(
            request_id=f'private-concurrent-{i}',timeout_s=2.)) for i in range(3)))
        assert all(result[1]['status']=='succeeded' for result in results)
    try:
        asyncio.run(exercise());runtime.shutdown();data=rows(tmp_path)
        jobs=[r for r in data if r['kind']=='job'];public=[r for r in data if r['kind']=='mcp_call']
        assert len(jobs)==len(public)==3
        assert len({r['operation_id'] for r in jobs})==3
        assert all({'queue','read_bundle','journal'}<=r['phases'].keys() for r in jobs)
        assert all('journal' in r['phases'] and 'queue' not in r['phases'] for r in public)
        assert 'private-concurrent' not in json.dumps(data)
    finally:runtime.shutdown();t.close()
