"""Durable flag/lock lifecycle: artificial COM-shaped state, not native proof."""

from contextlib import contextmanager

import pytest

from solidworks_mcp.application_guard import ApplicationModelMutationGuard
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.mutations import MutationCoordinator, PreparedMutation
from test_mutation_guards_v2 import InlineWorker


def exercise(store, *, fault=None):
    state={'name':'До'}
    events=[]
    target={'document_id':'doc_a','configuration':'Основная','expected_revision':'rev_1'}

    class App:
        busy = fault=='busy'
        @property
        def CommandInProgress(self): return self.busy
        @CommandInProgress.setter
        def CommandInProgress(self,value):
            job=store.list()['items'][0]
            assert job['status']=='running'
            assert job['mutation']['before_state']['_mutation_effect_scope']=='application'
            assert store.mutation_blockers('another_epoch','unrelated_document')
            events.append('flag:'+str(value))
            if fault=='acquire_before' and value: raise RuntimeError('Setter rejected')
            self.busy=value
            if fault==('acquire_after' if value else 'release'): raise RuntimeError('Acknowledgement lost')

    class Model:
        block=0
        def GetBlockingState(self): return self.block
        def Lock(self):
            assert app.busy is True
            events.append('lock'); self.block=2
        def UnLock(self):
            assert app.busy is True
            events.append('unlock'); self.block=0

    @contextmanager
    def selection(model,selection_state):
        assert app.busy and model.block==2
        events.append('selection_enter')
        selection_state.selection_uncertain=True
        try: yield
        finally:
            events.append('selection_exit')
            selection_state.selection_uncertain=False

    app,model=App(),Model()
    coordinator=MutationCoordinator(store,'epoch')
    def validate(prepared):
        assert app.busy and model.block==2
        events.append('validate'); return fault!='stale'
    def apply(prepared):
        assert app.busy and model.block==2
        events.append('apply'); state['name']='После'
        if fault=='body': raise RuntimeError('Known native error after write')
        return state.copy()
    def restore(before,prepared):
        assert app.busy and model.block==2
        events.append('restore'); state.update(before)
    def run(operation_id):
        return coordinator.execute(operation_id,**target,
            prepare=lambda:PreparedMutation('rev_1',state.copy()),validate=validate,apply=apply,
            inspect=lambda _:state.copy(),verify=lambda b,a,v:a==v,
            restore=restore,verify_restored=lambda b,a:b==a,
            guard=lambda _:ApplicationModelMutationGuard(app,[model],selection))
    runner=JobRunner(store,InlineWorker())
    kwargs=dict(context=target,mutates=True,pass_operation_id=True,verify=lambda r:r['verified'] is True)
    result=runner.submit('same_request','test.model_change',{},run,**kwargs)
    before_repeat=events.copy()
    assert runner.submit('same_request','test.model_change',{},run,**kwargs)==result
    assert events==before_repeat
    return result,app,model,state,events


@pytest.fixture
def store(tmp_path):
    value=JobStore(tmp_path/'jobs.sqlite')
    try: yield value
    finally: value.close()


def test_complete_sequence_has_checkpoint_before_first_flag_write_and_durable_release(store):
    result,app,model,state,events=exercise(store)
    assert result['status']=='succeeded' and state['name']=='После'
    assert app.busy is False and model.block==0
    assert events==['flag:True','lock','selection_enter','validate','apply','selection_exit','unlock','flag:False']
    evidence=result['result']['execution_guard']
    assert evidence=={'scope':'application_model_mutation_guard_v1','original_command_in_progress':False,
        'acquired':True,'released':True,'model_guards':[{'original_state':0,'locked_state':2,'released_state':0}],
        'selection_preserved':True}
    assert result['mutation']['verification']['evidence']['execution_guard']==evidence
    assert not store.mutation_blockers('fresh_epoch','doc_other')


@pytest.mark.parametrize('fault',['body','stale'])
def test_known_error_releases_owned_flag_after_scoped_restoration_or_prewrite_rejection(store,fault):
    result,app,model,state,events=exercise(store,fault=fault)
    assert result['status']=='failed' and state['name']=='До'
    assert app.busy is False and model.block==0
    assert events[-3:]==['selection_exit','unlock','flag:False']
    assert ('restore' in events)==(fault=='body')
    assert result['mutation']['verification']['evidence']['execution_guard']['released'] is True
    assert not store.mutation_blockers('fresh_epoch','doc_other')


def test_foreign_command_is_never_borrowed_reset_or_used_for_model_writes(store):
    result,app,model,state,events=exercise(store,fault='busy')
    assert result['status']=='failed' and result['error']['code']=='application_busy'
    assert app.busy is True and model.block==0 and state['name']=='До' and events==[]
    assert not store.mutation_blockers('fresh_epoch','doc_other')


@pytest.mark.parametrize('fault',['acquire_before','acquire_after','release'])
def test_uncertain_acknowledgement_keeps_application_hold_and_never_repeats_setter(store,fault):
    result,app,model,state,events=exercise(store,fault=fault)
    assert result['status']=='unknown' and model.block==0
    assert events.count('flag:True')==1
    assert events.count('flag:False')==(0 if fault=='acquire_before' else 1)
    assert app.busy is False
    assert state['name']==('После' if fault=='release' else 'До')
    assert store.mutation_blockers('fresh_epoch','unrelated_document')
