"""Survivor-only close lifecycle with artificial native state; no CAD claim."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from solidworks_mcp.application_close_guard import ApplicationCloseGuard
from solidworks_mcp.application_guard import ApplicationDocumentGuard
from solidworks_mcp.jobs import ExecutionFailure


class App:
    def __init__(self, *, busy=False, release_error=False):
        self.busy = busy
        self.release_error = release_error
        self.writes = []
        self.reads = 0

    @property
    def CommandInProgress(self):
        self.reads += 1
        return self.busy

    @CommandInProgress.setter
    def CommandInProgress(self, value):
        self.writes.append(value)
        self.busy = value
        if value is False and self.release_error:
            raise RuntimeError('Release acknowledgement lost.')


class Survivor:
    def __init__(self, name, events, *, unlock_error=False):
        self.name = name
        self.events = events
        self.block = 0
        self.unlock_error = unlock_error
        self.selection = ['original selection']

    def GetBlockingState(self):
        self.events.append((self.name, 'get'))
        return self.block

    def Lock(self):
        self.events.append((self.name, 'lock'))
        self.block = 2

    def UnLock(self):
        self.events.append((self.name, 'unlock'))
        self.block = 0
        if self.unlock_error:
            raise RuntimeError('Survivor unlock acknowledgement lost.')


class RetiringTarget:
    """Calling a method after native destruction is forbidden."""

    destroyed = False
    calls = 0

    def GetBlockingState(self):
        self.calls += 1
        if self.destroyed:
            raise RuntimeError('Retired native handle.')
        return 0

    def Lock(self):
        self.calls += 1
        raise AssertionError('Closing targets must never be locked by this guard.')

    def UnLock(self):
        self.calls += 1
        raise AssertionError('Closing targets must never be released by this guard.')


def selection_scope(events):
    @contextmanager
    def selection(model, state):
        assert model.block == 2
        saved = model.selection.copy()
        state.selection_uncertain = True
        events.append((model.name, 'selection_enter'))
        try:
            yield
        finally:
            model.selection = saved
            state.selection_uncertain = False
            events.append((model.name, 'selection_exit'))
    return selection


def test_destroyed_targets_never_enter_survivor_guards_and_survivors_restore_in_reverse_order():
    events = []
    app = App()
    survivors = [Survivor('first', events), Survivor('second', events)]
    target = RetiringTarget()
    guard = ApplicationCloseGuard(app, survivors, selection_scope(events), ['doc_retiring'])
    assert isinstance(guard, ApplicationDocumentGuard)
    assert guard.models == tuple(survivors)
    with guard as entered:
        assert entered is guard and app.busy is True
        assert all(model.block == 2 for model in survivors)
        target.destroyed = True  # Stand-in for a normally returned CloseDoc.
        survivors[0].selection = ['changed during operation']
    assert target.calls == 0
    assert app.writes == [True, False]
    assert all(model.block == 0 and model.selection == ['original selection'] for model in survivors)
    assert [event for event in events if event[1] != 'get'] == [
        ('first', 'lock'), ('first', 'selection_enter'),
        ('second', 'lock'), ('second', 'selection_enter'),
        ('second', 'selection_exit'), ('second', 'unlock'),
        ('first', 'selection_exit'), ('first', 'unlock')]
    assert guard.evidence == {
        'scope': 'application_document_close_guard_v1',
        'original_command_in_progress': False, 'acquired': True, 'released': True,
        'model_guards': [{'original_state': 0, 'locked_state': 2, 'released_state': 0}] * 2,
        'selection_preserved': True, 'retiring_document_ids': ['doc_retiring'],
        'retiring_targets_locked_during_close': False}
    assert not any(key in guard.evidence for key in ('retired', 'documents_closed', 'close_verified'))


def test_last_document_guard_does_not_read_or_change_user_control_and_has_no_model_scopes():
    app = App()
    events = []
    target = RetiringTarget()
    with ApplicationCloseGuard(app, [], selection_scope(events), ['doc_only']) as guard:
        target.destroyed = True
    assert app.writes == [True, False] and events == [] and target.calls == 0
    assert guard.evidence['model_guards'] == []
    assert guard.evidence['selection_preserved'] is True
    assert guard.evidence['released'] is True


def test_existing_busy_flag_never_borrowed_and_survivors_not_touched():
    events = []
    app = App(busy=True)
    survivor = Survivor('survivor', events)
    guard = ApplicationCloseGuard(app, [survivor], selection_scope(events), ['doc_target'])
    with pytest.raises(ExecutionFailure) as error:
        with guard:
            pytest.fail('Busy session must not execute CloseDoc.')
    assert error.value.code == 'application_busy' and error.value.uncertain is False
    assert app.busy is True and app.writes == [] and events == []
    assert guard.evidence['acquired'] is False and guard.evidence['released'] is False


def test_survivor_release_failure_remains_uncertain_but_releases_owned_cip_and_other_survivor():
    events = []
    app = App()
    first = Survivor('first', events)
    faulty = Survivor('faulty', events, unlock_error=True)
    target = RetiringTarget()
    guard = ApplicationCloseGuard(app, [first, faulty], selection_scope(events), ['doc_target'])
    with pytest.raises(ExecutionFailure) as error:
        with guard:
            target.destroyed = True
    assert error.value.code == 'ui_guard_cleanup_unconfirmed' and error.value.uncertain is True
    assert target.calls == 0 and app.writes == [True, False] and app.busy is False
    assert first.block == 0 and faulty.block == 0
    assert events.count(('faulty', 'unlock')) == 1 and events.count(('first', 'unlock')) == 1
    assert guard.evidence['released'] is True
    assert guard.state == 'closed'


def test_survivor_acquisition_failure_does_not_unlock_preexisting_model_lock():
    events = []
    app = App()
    survivor = Survivor('borrowed', events)
    survivor.block = 3
    guard = ApplicationCloseGuard(app, [survivor], selection_scope(events), ['doc_target'])
    with pytest.raises(ExecutionFailure) as error:
        with guard:
            pytest.fail('Preexisting lock must reject before close.')
    assert error.value.code == 'ui_guard_already_blocked' and error.value.uncertain is False
    assert events == [('borrowed', 'get')] and survivor.block == 3
    assert app.writes == [True, False] and app.busy is False


def test_body_failure_restores_survivor_selection_and_preserves_original_exception():
    events = []
    app = App()
    survivor = Survivor('survivor', events)
    original = ValueError('Close-domain rejection.')
    guard = ApplicationCloseGuard(app, [survivor], selection_scope(events), ['doc_target'])
    with pytest.raises(ValueError) as error:
        with guard:
            survivor.selection = []
            raise original
    assert error.value is original and app.writes == [True, False]
    assert survivor.selection == ['original selection'] and survivor.block == 0
    assert guard.evidence['selection_preserved'] is True


def test_ambiguous_cip_release_is_not_retried_or_reported_as_released():
    app = App(release_error=True)
    guard = ApplicationCloseGuard(app, [], selection_scope([]), ['doc_target'])
    with pytest.raises(ExecutionFailure) as error:
        with guard:
            pass
    assert error.value.code == 'application_guard_release_unconfirmed' and error.value.uncertain is True
    assert app.writes == [True, False] and guard.evidence['released'] is False
    with pytest.raises(ExecutionFailure) as repeated:
        guard.__enter__()
    assert repeated.value.code == 'application_guard_reentry'
    assert app.writes == [True, False]


def test_wrong_thread_cannot_acquire_or_release_and_owner_completes_cleanup():
    app = App()
    guard = ApplicationCloseGuard(app, [], selection_scope([]), ['doc_target'])
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ExecutionFailure) as error:
            pool.submit(guard.__enter__).result(timeout=2)
        assert error.value.code == 'wrong_apartment' and error.value.uncertain is False
        assert app.writes == []
        guard.__enter__()
        with pytest.raises(ExecutionFailure) as error:
            pool.submit(guard.__exit__, None, None, None).result(timeout=2)
        assert error.value.code == 'wrong_apartment' and error.value.uncertain is True
        assert app.writes == [True] and app.busy is True
    guard.__exit__(None, None, None)
    assert app.writes == [True, False]


@pytest.mark.parametrize('retiring', [[], [''], ['  '], ['doc_a', 'doc_a'], [1], [True],
                                      [None], ['doc_a', []], 'doc_a', b'doc_a', None])
def test_invalid_retiring_ids_rejected_before_any_native_access(retiring):
    app = App()
    with pytest.raises(ValueError):
        ApplicationCloseGuard(app, [], selection_scope([]), retiring)
    assert app.reads == 0 and app.writes == []


def test_combined_budget_boundary_and_bounded_iterable_rejection_are_native_free():
    app = App()
    guard = ApplicationCloseGuard(app, [], selection_scope([]), (f'doc_{i}' for i in range(5000)))
    assert len(guard.retiring_document_ids) == 5000 and app.reads == 0
    survivor = object()  # No model method is read during construction.
    with pytest.raises(ValueError, match='budget'):
        ApplicationCloseGuard(app, [survivor], selection_scope([]), (f'doc_{i}' for i in range(5000)))
    produced = []
    def excessive():
        for index in range(10000):
            produced.append(index)
            yield f'doc_{index}'
    with pytest.raises(ValueError, match='budget'):
        ApplicationCloseGuard(app, [], selection_scope([]), excessive())
    assert len(produced) == 5001
    with pytest.raises(ValueError, match='budget'):
        ApplicationCloseGuard(app, (object() for _ in range(5001)), selection_scope([]), ['doc_target'])
    assert app.reads == 0 and app.writes == []


def test_evidence_and_constructor_inputs_do_not_mutate_retirement_ids():
    app = App()
    retiring = ['doc_a', 'doc_b']
    survivors = []
    guard = ApplicationCloseGuard(app, survivors, selection_scope([]), retiring)
    retiring.append('doc_later')
    survivors.append(object())
    evidence = guard.evidence
    evidence['retiring_document_ids'].append('doc_injected')
    assert guard.models == () and guard.retiring_document_ids == ('doc_a', 'doc_b')
    assert guard.evidence['retiring_document_ids'] == ['doc_a', 'doc_b']
    assert guard.evidence['retiring_targets_locked_during_close'] is False
