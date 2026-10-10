"""Mock COM contracts only; no real mass API or CAD session is used."""

from types import SimpleNamespace

import pytest

from solidworks_mcp.cad_mass_properties import CadMassPropertiesMixin
from solidworks_mcp.jobs import ExecutionFailure
import solidworks_mcp.cad_mass_properties as native


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
    body = SimpleNamespace(token=['body'])
    body._oleobj_ = body
    monkeypatch.setattr(native.binding, 'wrap', lambda value, cls: value)
    monkeypatch.setattr(native.win32com.client, 'VARIANT', lambda kind, values: tuple(values))
    adapter = CadMassPropertiesMixin()
    adapter._module = SimpleNamespace(IMassProperty2=object(), IMassPropertyOverrideOptions=object(),
                                      IMathUtility=object(), IMathTransform=object())
    adapter.identity = lambda obj: obj.token  # Deliberately unhashable canonical tokens.
    adapter._extension = lambda model: SimpleNamespace(CreateMassProperty2=lambda: mp)
    utility = SimpleNamespace(CreateTransform=lambda values: values)
    adapter._sw = SimpleNamespace(GetMathUtility=lambda: utility)
    return adapter, mp, body


def test_fresh_calculation_has_explicit_si_body_scope_and_identity_frame(candidate):
    adapter, mp, body = candidate
    output = adapter.mass_properties(object(), (body,))
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
    with pytest.raises(ExecutionFailure): adapter.mass_properties(object(), (body,))


@pytest.mark.parametrize('override', ['OverrideMass', 'OverrideCenterOfMass', None])
def test_overrides_reject_without_document_edit(candidate, override):
    adapter, mp, body = candidate
    if override is None: mp.override = None
    else: setattr(mp.override, override, True)
    with pytest.raises(ExecutionFailure) as error: adapter.mass_properties(object(), (body,))
    assert error.value.code == 'mass_properties_overridden'
    assert not mp.recalculated


def test_no_mass_object_fails_without_fallback(candidate):
    adapter, _, body = candidate
    adapter._extension = lambda model: SimpleNamespace(CreateMassProperty2=lambda: None)
    with pytest.raises(ExecutionFailure) as error: adapter.mass_properties(object(), (body,))
    assert error.value.code == 'mass_properties_unavailable'


def test_empty_scope_does_not_create_calculation(candidate):
    adapter, _, _ = candidate
    adapter._extension = lambda model: pytest.fail('No implicit UI-selected calculation')
    with pytest.raises(ExecutionFailure) as error: adapter.mass_properties(object(), ())
    assert error.value.code == 'no_solid_bodies'
