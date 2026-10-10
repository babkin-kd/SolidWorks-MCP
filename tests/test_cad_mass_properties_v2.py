"""Mock COM contracts only; no real mass API or CAD session is used."""

from types import SimpleNamespace

import pytest

from solidworks_mcp.cad_mass_properties import CadMassPropertiesMixin
from solidworks_mcp.jobs import ExecutionFailure
import solidworks_mcp.cad_mass_properties as native


class Selection:
    def __init__(self):
        self.current = [(SimpleNamespace(token=['original']), 7)]
        self.saved = None
        self.calls = []
        self.fault = None

    def GetSelectedObjectCount2(self, mark): return len(self.current)
    def GetSelectedObject6(self, index, mark): return self.current[index - 1][0]
    def GetSelectedObjectMark(self, index): return self.current[index - 1][1]
    def SuspendSelectionList(self):
        self.calls.append('suspend')
        if self.fault == 'suspend': raise RuntimeError('Native suspension error')
        self.saved = self.current
        self.current = []
        return int(bool(self.saved))
    def ResumeSelectionList(self):
        self.calls.append('resume')
        if self.fault == 'resume': raise RuntimeError('Native resume error')
        if self.fault == 'no_resume': return
        self.current = self.saved
        if self.fault == 'mark': self.current = [(item, mark + 1) for item, mark in self.current]


class Mass:
    Volume = 2e-6
    SurfaceArea = .01
    Mass = .0157
    Density = 7850.
    CenterOfMass = (-.001, .002, 0.)

    def __init__(self):
        self.fault = None
        self.override = SimpleNamespace(OverrideMass=False, OverrideCenterOfMass=False)
        self.recalculated = False
        self.calls = []

    def __setattr__(self, name, value):
        if name == 'UseSystemUnits' and self.fault == 'units': value = False
        if name == 'IncludeHiddenBodiesOrComponents' and self.fault == 'hidden': value = False
        if name == 'ShowWeldBeadMass' and self.fault == 'weld': value = True
        if name == 'SelectedItems' and self.fault == 'foreign': value = (SimpleNamespace(token=['foreign']),)
        if name == 'SelectedItems' and self.fault == 'empty': value = ()
        object.__setattr__(self, name, value)
        if name == 'SelectedItems': self.selection.current = [(item, 0) for item in value]

    def GetOverrideOptions(self): return self.override

    def SetCoordinateSystem(self, transform):
        self.calls.append(('frame', transform))
        return self.fault != 'frame'

    def Recalculate(self):
        self.calls.append(('recalculate',))
        self.recalculated = True
        if self.fault == 'recalc_scope': self.SelectedItems = ()
        if self.fault == 'recalc_units': self.UseSystemUnits = False
        if self.fault == 'recalc_override': self.override.OverrideMass = True
        return self.fault != 'recalc'


@pytest.fixture
def candidate(monkeypatch):
    mp = Mass()
    selection = Selection()
    mp.selection = selection
    body = SimpleNamespace(token=['body'])
    body._oleobj_ = body
    monkeypatch.setattr(native.binding, 'wrap', lambda value, cls: value)
    monkeypatch.setattr(native.win32com.client, 'VARIANT', lambda kind, values: tuple(values))
    adapter = CadMassPropertiesMixin()
    adapter._module = SimpleNamespace(IMassProperty2=object(), IMassPropertyOverrideOptions=object(),
                                      IMathUtility=object(), IMathTransform=object(), ISelectionMgr=object())
    adapter.model = SimpleNamespace(SelectionManager=selection)
    adapter.identity = lambda obj: obj.token  # Deliberately unhashable canonical tokens.
    adapter._extension = lambda model: SimpleNamespace(CreateMassProperty2=lambda: mp)
    utility = SimpleNamespace(CreateTransform=lambda values: values)
    adapter._sw = SimpleNamespace(GetMathUtility=lambda: utility)
    return adapter, mp, body


def test_fresh_calculation_has_explicit_si_body_scope_and_identity_frame(candidate):
    adapter, mp, body = candidate
    output = adapter.mass_properties(adapter.model, (body,))
    assert output['volume_m3'] == 2e-6 and output['mass_kg'] == .0157
    assert mp.SelectedItems == (body,)
    assert mp.UseSystemUnits and mp.IncludeHiddenBodiesOrComponents and not mp.ShowWeldBeadMass
    assert mp.calls[0] == ('frame', (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.))
    assert mp.calls[1] == ('recalculate',)


@pytest.mark.parametrize('fault', ['units', 'hidden', 'weld', 'foreign', 'empty', 'frame',
                                  'recalc', 'recalc_scope', 'recalc_units', 'recalc_override'])
def test_unconfirmed_scope_never_returns_values(candidate, fault):
    adapter, mp, body = candidate
    mp.fault = fault
    with pytest.raises(ExecutionFailure): adapter.mass_properties(adapter.model, (body,))


@pytest.mark.parametrize('override', ['OverrideMass', 'OverrideCenterOfMass', None])
def test_overrides_reject_without_document_edit(candidate, override):
    adapter, mp, body = candidate
    if override is None: mp.override = None
    else: setattr(mp.override, override, True)
    with pytest.raises(ExecutionFailure) as error: adapter.mass_properties(adapter.model, (body,))
    assert error.value.code == 'mass_properties_overridden'
    assert not mp.recalculated


def test_no_mass_object_fails_without_fallback(candidate):
    adapter, _, body = candidate
    adapter._extension = lambda model: SimpleNamespace(CreateMassProperty2=lambda: None)
    with pytest.raises(ExecutionFailure) as error: adapter.mass_properties(adapter.model, (body,))
    assert error.value.code == 'mass_properties_unavailable'


def test_empty_scope_does_not_create_calculation(candidate):
    adapter, _, _ = candidate
    adapter._extension = lambda model: pytest.fail('No implicit UI-selected calculation')
    with pytest.raises(ExecutionFailure) as error: adapter.mass_properties(adapter.model, ())
    assert error.value.code == 'no_solid_bodies'


@pytest.mark.parametrize('empty', [False, True])
def test_mass_scope_restores_exact_original_objects_and_marks(candidate, empty):
    adapter, mp, body = candidate
    if empty: mp.selection.current = []
    original = list(mp.selection.current)
    adapter.mass_properties(adapter.model, (body,))
    assert mp.selection.current == original
    assert mp.selection.calls == ['suspend', 'resume']
    assert adapter._mass_selection_reconciliation_required is False


def test_calculation_error_restores_selection_without_repeating(candidate):
    adapter, mp, body = candidate
    original = list(mp.selection.current)
    mp.fault = 'recalc'
    with pytest.raises(ExecutionFailure) as error:
        adapter.mass_properties(adapter.model, (body,))
    assert error.value.code == 'mass_properties_read_failed' and error.value.uncertain is False
    assert mp.selection.current == original and mp.selection.calls == ['suspend', 'resume']
    assert adapter._mass_selection_reconciliation_required is False


@pytest.mark.parametrize('fault', ['resume', 'no_resume', 'mark'])
def test_unconfirmed_restoration_blocks_another_calculation(candidate, fault):
    adapter, mp, body = candidate
    mp.selection.fault = fault
    with pytest.raises(ExecutionFailure) as error:
        adapter.mass_properties(adapter.model, (body,))
    assert error.value.code == 'mass_selection_restore_unconfirmed' and error.value.uncertain is True
    assert mp.selection.calls == ['suspend', 'resume']
    with pytest.raises(ExecutionFailure) as error:
        adapter.mass_properties(adapter.model, (body,))
    assert error.value.code == 'mass_selection_reconciliation_required'
    assert mp.selection.calls == ['suspend', 'resume']


def test_throwing_suspend_does_not_trigger_blind_resume_or_calculation(candidate):
    adapter, mp, body = candidate
    mp.selection.fault = 'suspend'
    adapter._extension = lambda model: pytest.fail('Unconfirmed suspension must stop before calculation.')
    with pytest.raises(ExecutionFailure) as error:
        adapter.mass_properties(adapter.model, (body,))
    assert error.value.code == 'mass_selection_suspend_unconfirmed' and error.value.uncertain is True
    assert mp.selection.calls == ['suspend']


def test_restore_failure_retains_primary_error_in_diagnostics(candidate):
    adapter, mp, body = candidate
    mp.fault = 'recalc'
    mp.selection.fault = 'resume'
    with pytest.raises(ExecutionFailure) as error:
        adapter.mass_properties(adapter.model, (body,))
    assert error.value.code == 'mass_selection_restore_unconfirmed'
    assert 'mass recalculation failed' in error.value.__notes__[0]


def test_invalid_suspend_acknowledgement_is_not_borrowed(candidate):
    adapter, mp, body = candidate
    mp.selection.SuspendSelectionList = lambda: False
    with pytest.raises(ExecutionFailure) as error:
        adapter.mass_properties(adapter.model, (body,))
    assert error.value.code == 'mass_selection_suspend_unconfirmed'
    assert mp.selection.calls == [] and not mp.recalculated
