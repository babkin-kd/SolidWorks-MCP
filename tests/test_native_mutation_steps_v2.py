"""Durable acknowledgement is distinct from verified effects and guard release."""

import json
import sqlite3

import pytest

from solidworks_mcp.jobs import JobError, JobStore
from test_mutation_journal_v2 import prepared_job


@pytest.fixture
def setup(tmp_path):
    path=tmp_path/'jobs.sqlite'; store=JobStore(path); job_id=prepared_job(store)
    yield store,job_id,path
    store.close()


def test_native_events_are_durable_and_do_not_edit_before_or_release_hold(setup):
    store,job,path=setup; before=store.get(job)['mutation']['before_state']
    data={'native_file_id':'native_file_one'}
    store.record_mutation_step(job,name='open_native',phase='pending',evidence=data)
    data['native_file_id']='caller mutation cannot rewrite ledger'
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True) as reader:
        raw=reader.execute('SELECT before_state,verification FROM mutations WHERE operation_id=?',(job,)).fetchone()
    assert json.loads(raw[0])==before
    verification=json.loads(raw[1])
    assert verification['outcome'] is None
    assert verification['native_steps']==[dict(sequence=1,name='open_native',phase='pending',evidence={'native_file_id':'native_file_one'})]
    assert store.mutation_blockers('connection_1','doc_a')
    store.record_mutation_step(job,name='open_native',phase='returned',evidence={'native_call_returned':True})
    assert store.get(job)['mutation']['verification']['outcome'] is None
    assert store.mutation_blockers('connection_1','doc_a')
    result=store.finish(job,'succeeded',result={'verified':True})
    assert result['status']=='unknown' and result['mutation']['phase']=='unresolved'


@pytest.mark.parametrize('outcome',['committed','rolled_back','not_started'])
def test_pending_step_cannot_be_finalized_by_oracle_claim(setup,outcome):
    store,job,_=setup
    store.record_mutation_step(job,name='open_native',phase='pending',evidence={'native_file_id':'file'})
    with pytest.raises(JobError) as error:store.verify_mutation(job,outcome=outcome,evidence={'pretend_checked':True})
    assert error.value.code=='native_step_unresolved'
    assert store.get(job)['mutation']['verification']['outcome'] is None


def test_final_oracle_and_guard_update_preserve_native_history(setup):
    store,job,_=setup
    for name in ('open_native','activate_native'):
        store.record_mutation_step(job,name=name,phase='pending',evidence={'target':'exact'})
        store.record_mutation_step(job,name=name,phase='returned',evidence={'native_call_returned':True})
    steps=store.get(job)['mutation']['verification']['native_steps']
    store.verify_mutation(job,outcome='committed',evidence={'after':{'exact_models':True}})
    store.verify_mutation(job,outcome='committed',evidence={'after':{'exact_models':True},'execution_guard':{'released':True}})
    assert store.get(job)['mutation']['verification']['native_steps']==steps
    with pytest.raises(JobError):store.record_mutation_step(job,name='unexpected',phase='pending',evidence={'bad':True})
    assert store.finish(job,'succeeded',result={'verified':True})['status']=='succeeded'
    assert store.mutation_blockers('connection_1','doc_a')==[]


@pytest.mark.parametrize('phase,name',[('returned','open_native'),('pending','open_native'),('returned','other_native')])
def test_no_overlap_replay_or_mismatched_return(setup,phase,name):
    store,job,_=setup
    if name=='open_native' and phase=='returned':
        # No pending call exists at all.
        pass
    else:store.record_mutation_step(job,name='open_native',phase='pending',evidence={'target':'exact'})
    with pytest.raises(JobError) as error:store.record_mutation_step(job,name=name,phase=phase,evidence={'target':'exact'})
    assert error.value.code=='invalid_native_step'


def test_completed_name_cannot_be_called_again(setup):
    store,job,_=setup
    for phase in ('pending','returned'):store.record_mutation_step(job,name='open_native',phase=phase,evidence={'target':'exact'})
    with pytest.raises(JobError):store.record_mutation_step(job,name='open_native',phase='pending',evidence={'target':'exact'})
    assert len(store.get(job)['mutation']['verification']['native_steps'])==2


@pytest.mark.parametrize('name,phase,evidence',[(True,'pending',{'x':True}),('','pending',{'x':True}),('x'*129,'pending',{'x':True}),
    ('open','done',{'x':True}),('open','pending',{}),('open','pending',[]),('open','pending',{'x':float('nan')})])
def test_invalid_event_rejects_before_writing(setup,name,phase,evidence):
    store,job,_=setup
    with pytest.raises(JobError):store.record_mutation_step(job,name=name,phase=phase,evidence=evidence)
    assert store.get(job)['mutation']['verification'] is None


def test_restart_retains_pending_receipt_and_unknown_hold_without_replay(setup):
    store,job,path=setup
    store.record_mutation_step(job,name='open_native',phase='pending',evidence={'target':'exact'})
    store.close()
    reopened=JobStore(path)
    try:
        result=reopened.get(job)
        assert result['status']=='unknown' and result['mutation']['phase']=='unresolved'
        assert result['mutation']['verification']['native_steps'][0]['phase']=='pending'
        assert reopened.mutation_blockers('new_epoch','any_document')
        with pytest.raises(JobError):reopened.record_mutation_step(job,name='open_native',phase='returned',evidence={'bad':True})
    finally:reopened.close()


def test_event_budget_is_bounded_and_transaction_remains_usable(setup):
    store,job,_=setup
    for index in range(16):
        for phase in ('pending','returned'):store.record_mutation_step(job,name=f'native_{index}',phase=phase,evidence={'index':index})
    with pytest.raises(JobError) as error:store.record_mutation_step(job,name='extra',phase='pending',evidence={'x':True})
    assert error.value.code=='native_step_budget_exceeded'
    store.verify_mutation(job,outcome='rolled_back',evidence={'full_baseline':True})
    assert store.finish(job,'failed')['status']=='failed'
