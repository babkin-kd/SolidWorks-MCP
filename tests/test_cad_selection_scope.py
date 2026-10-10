"""Selection ownership across native effects, including transient managers."""

from types import SimpleNamespace

import pytest

from solidworks_mcp.cad_selection_scope import preserved_selection
from solidworks_mcp.jobs import ExecutionFailure
import solidworks_mcp.cad_selection_scope as native


class Document:
    def __init__(self):
        self.current = [(object(), 7), (object(), 3)]
        self.saved = None
        self.epoch = 0
        self.fault = None
        self.calls = []

    @property
    def SelectionManager(self):
        doc, epoch = self, self.epoch
        def live():
            if epoch != doc.epoch: raise RuntimeError('A transient selection manager was reused.')
        def suspend():
            live()
            doc.calls.append('suspend')
            if doc.fault == 'suspend_throw': raise RuntimeError('Native suspension may have taken effect.')
            doc.saved, doc.current = doc.current, []
            doc.epoch += 1
            return True if doc.fault == 'bad_ack' else int(bool(doc.saved))
        def resume():
            live()
            doc.calls.append('resume')
            doc.current = doc.saved
            doc.epoch += 1
            if doc.fault == 'resume_throw': raise RuntimeError('Resume outcome is unknown.')
            if doc.fault == 'wrong_mark': doc.current = [(token, mark + 1) for token, mark in doc.current]
        def snapshot():
            live()
            return tuple(doc.current)
        return SimpleNamespace(SuspendSelectionList=suspend, ResumeSelectionList=resume, snapshot=snapshot)


class Adapter:
    _module = SimpleNamespace(ISelectionMgr=object())
    def _mass_selection_snapshot(self, manager): return manager.snapshot()


@pytest.fixture(autouse=True)
def wrap(monkeypatch):
    monkeypatch.setattr(native.binding, 'wrap', lambda raw, cls: raw)


def test_native_effects_use_fresh_managers_and_restore_objects_order_and_marks():
    doc = Document()
    original = tuple(doc.current)
    state = SimpleNamespace(selection_uncertain=False)
    with preserved_selection(Adapter(), doc, state=state):
        assert doc.current == []
        doc.current = [(object(), 0)]
        doc.epoch += 1  # A setter/rebuild invalidates the old manager.
    assert tuple(doc.current) == original and state.selection_uncertain is False
    assert doc.calls == ['suspend', 'resume']


@pytest.mark.parametrize('fault', ['suspend_throw', 'bad_ack'])
def test_unknown_suspension_is_not_blindly_resumed_or_retried(fault):
    doc = Document()
    doc.fault = fault
    state = SimpleNamespace(selection_uncertain=False)
    with pytest.raises(ExecutionFailure) as error:
        with preserved_selection(Adapter(), doc, state=state): pytest.fail('Scope must not enter')
    assert error.value.uncertain and doc.calls == ['suspend'] and state.selection_uncertain
    with pytest.raises(ExecutionFailure):
        with preserved_selection(Adapter(), doc, state=state): pytest.fail('Scope must not reenter')
    assert doc.calls == ['suspend']


@pytest.mark.parametrize('fault', ['resume_throw', 'wrong_mark'])
def test_unconfirmed_resume_is_sticky_even_if_geometry_work_completed(fault):
    doc = Document()
    doc.fault = fault
    state = SimpleNamespace(selection_uncertain=False)
    with pytest.raises(ExecutionFailure) as error:
        with preserved_selection(Adapter(), doc, state=state): pass
    assert error.value.uncertain and state.selection_uncertain
    assert doc.calls == ['suspend', 'resume']


def test_known_primary_error_is_preserved_after_verified_selection_restoration():
    doc = Document()
    original = tuple(doc.current)
    with pytest.raises(ValueError, match='Primary native error'):
        with preserved_selection(Adapter(), doc): raise ValueError('Primary native error')
    assert tuple(doc.current) == original and doc.calls == ['suspend', 'resume']
