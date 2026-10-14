"""Artificial command flags/UI, not a claim of native SolidWorks acceptance."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from solidworks_mcp.application_guard import ApplicationDocumentGuard
from solidworks_mcp.jobs import ExecutionFailure


class App:
    def __init__(self, busy=False, fault=None):
        self.busy, self.fault, self.writes = busy, fault, []

    @property
    def CommandInProgress(self):
        return self.busy

    @CommandInProgress.setter
    def CommandInProgress(self, value):
        self.writes.append(value)
        self.busy = value
        if self.fault == ('acquire' if value else 'release'):
            raise RuntimeError('Lost native setter acknowledgement.')


class Model:
    def __init__(self): self.block = 0
    def GetBlockingState(self): return self.block
    def Lock(self): self.block = 2
    def UnLock(self): self.block = 0


@contextmanager
def selection(model, state):
    state.selection_uncertain = True
    try: yield
    finally: state.selection_uncertain = False


def test_owned_flag_locks_and_selections_released_after_body_failure():
    app, model = App(), Model()
    guard = ApplicationDocumentGuard(app, [model], selection)
    with pytest.raises(ValueError):
        with guard:
            assert app.busy and model.block == 2
            raise ValueError('Known failure')
    assert app.writes == [True, False] and model.block == 0
    assert guard.evidence == {'scope': 'application_document_create_guard_v1',
        'original_command_in_progress': False, 'acquired': True, 'released': True,
        'model_guards': [{'original_state': 0, 'locked_state': 2, 'released_state': 0}], 'selection_preserved': True}
    with pytest.raises(ExecutionFailure): guard.__enter__()
    assert app.writes == [True, False]


def test_existing_flag_never_borrowed_or_reset():
    app = App(busy=True)
    with pytest.raises(ExecutionFailure) as error:
        with ApplicationDocumentGuard(app, [], selection): pass
    assert error.value.uncertain is False and app.writes == []


@pytest.mark.parametrize('fault', ['acquire', 'release'])
def test_unknown_acknowledgement_retained_and_not_retried(fault):
    app = App(fault=fault)
    with pytest.raises(ExecutionFailure) as error:
        with ApplicationDocumentGuard(app, [], selection): pass
    assert error.value.uncertain is True and app.writes == [True, False]


def test_existing_model_lock_failure_releases_only_owned_app_flag():
    app, model = App(), Model()
    model.block = 3
    with pytest.raises(ExecutionFailure) as error:
        with ApplicationDocumentGuard(app, [model], selection): pass
    assert error.value.uncertain is False and model.block == 3 and app.writes == [True, False]
