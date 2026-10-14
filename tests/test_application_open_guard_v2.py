"""Artificial baseline/activation guard failures, independent of CAD."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from solidworks_mcp.application_open_guard import ApplicationOpenGuard
from solidworks_mcp.jobs import ExecutionFailure
from test_application_close_guard_v2 import App, Survivor, selection_scope


def test_baseline_survives_open_and_one_unlock_phase_retains_selection_and_cip():
    events=[]; app=App(); models=[Survivor('first',events),Survivor('second',events)]
    guard=ApplicationOpenGuard(app,models,selection_scope(events),['doc_first','doc_second'])
    with guard:
        assert app.busy and all(model.block == 2 for model in models)
        models[0].selection=[]  # An artificial open/add-in effect, restored at exit.
        guard.release_baseline_ui_for_activation()
        assert app.busy and all(model.block == 0 for model in models)
        assert not any(event[1]=='selection_exit' for event in events)
        assert guard.evidence['activation_ui_release']==dict(attempted=True,verified=True)
        with pytest.raises(ExecutionFailure): guard.release_baseline_ui_for_activation()
    assert app.writes==[True,False]
    assert guard.evidence['released'] and guard.evidence['selection_preserved']
    assert all(model.selection==['original selection'] for model in models)
    assert [event for event in events if event[1]=='unlock']==[('second','unlock'),('first','unlock')]
    assert guard.evidence['scope']=='application_document_open_guard_v1'
    assert guard.evidence['baseline_document_ids']==['doc_first','doc_second']


def test_empty_baseline_holds_only_command_flag_and_never_invents_a_model():
    events=[]; app=App()
    with ApplicationOpenGuard(app,[],selection_scope(events),[]) as guard:
        assert app.busy and guard.evidence['model_guards']==[]
        with pytest.raises(ExecutionFailure): guard.release_baseline_ui_for_activation()
    assert app.writes==[True,False] and events==[]
    assert guard.evidence['selection_preserved'] and guard.evidence['activation_ui_release']==dict(attempted=False,verified=False)


def test_busy_application_never_borrowed():
    events=[]; app=App(busy=True); model=Survivor('before',events)
    guard=ApplicationOpenGuard(app,[model],selection_scope(events),['doc_before'])
    with pytest.raises(ExecutionFailure) as error:
        with guard: pytest.fail('An owned open cannot start under another command flag')
    assert error.value.code=='application_busy' and not error.value.uncertain
    assert app.writes==[] and events==[] and app.busy


def test_foreign_model_lock_not_released_or_borrowed():
    events=[]; app=App(); model=Survivor('before',events); model.block=3
    guard=ApplicationOpenGuard(app,[model],selection_scope(events),['doc_before'])
    with pytest.raises(ExecutionFailure) as error:
        with guard: pytest.fail('Open must not execute')
    assert error.value.code=='ui_guard_already_blocked' and not error.value.uncertain
    assert model.block==3 and events==[('before','get')] and app.writes==[True,False]


def test_throwing_unlock_is_never_retried_and_keeps_failed_phase_evidence():
    events=[]; app=App(); model=Survivor('before',events,unlock_error=True)
    guard=ApplicationOpenGuard(app,[model],selection_scope(events),['doc_before'])
    with pytest.raises(ExecutionFailure) as error:
        with guard: guard.release_baseline_ui_for_activation()
    assert error.value.uncertain and events.count(('before','unlock'))==1
    assert app.writes==[True,False] and guard.evidence['activation_ui_release']==dict(attempted=True,verified=False)


def test_lost_owned_flag_rejects_activation_release_without_native_unlock_retry():
    events=[]; app=App(); model=Survivor('before',events)
    guard=ApplicationOpenGuard(app,[model],selection_scope(events),['doc_before'])
    with pytest.raises(ExecutionFailure) as error:
        with guard:
            app.busy=False
            guard.release_baseline_ui_for_activation()
    assert error.value.uncertain and guard.evidence['activation_ui_release']==dict(attempted=True,verified=False)
    assert events.count(('before','unlock'))==1 and app.writes==[True]


def test_wrong_thread_release_has_no_native_effect():
    events=[]; app=App(); model=Survivor('before',events)
    with ApplicationOpenGuard(app,[model],selection_scope(events),['doc_before']) as guard:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(ExecutionFailure) as error: pool.submit(guard.release_baseline_ui_for_activation).result()
        assert error.value.code=='wrong_apartment' and model.block==2 and app.busy
        assert guard.evidence['activation_ui_release']==dict(attempted=False,verified=False)
    assert events.count(('before','unlock'))==1


@pytest.mark.parametrize('models,ids', [([],['doc']),([object()],[]),([object()],['']),([object()],[' ']),
    ([object()], [True]),([object(),object()],['same','same']),('bad',[]),([], 'bad')])
def test_invalid_baseline_addressing_rejected_before_flag_or_models(models,ids):
    app=App()
    with pytest.raises(ValueError): ApplicationOpenGuard(app,models,lambda *args:None,ids)
    assert app.writes==[]


def test_generator_census_is_bounded_and_leaves_capacity_for_new_document():
    app=App(); yielded=[]
    def models():
        for i in range(10000):
            yielded.append(i)
            yield object()
    with pytest.raises(ValueError): ApplicationOpenGuard(app,models(),lambda *args:None,(f'doc_{i}' for i in range(10000)))
    assert len(yielded)==5000 and app.writes==[]
