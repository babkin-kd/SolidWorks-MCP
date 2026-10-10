"""Internal mass-read candidate; all COM proxies are local to the owning STA.

The explicit mass scope uses a temporary native selection list; the original
objects and marks must be restored before returning. Configuration, document
settings and overrides are not changed. Native
acceptance is required before wiring this candidate into the public runtime.
"""

import pythoncom
import win32com.client

from . import binding
from .documents import rejected
from .jobs import ExecutionFailure


class CadMassPropertiesMixin:
    def mass_properties(self, model, bodies):
        if not bodies:
            raise rejected('no_solid_bodies', 'An explicit nonempty solid-body scope is required.')
        if getattr(self, '_mass_selection_reconciliation_required', False):
            raise ExecutionFailure('mass_selection_reconciliation_required',
                'A previous temporary selection list was not restored; reconcile state before another calculation.',
                uncertain=True)
        selection = binding.wrap(model.SelectionManager, self._module.ISelectionMgr)
        if selection is None:
            raise rejected('mass_selection_unavailable', 'Selection ownership cannot be established.')
        original = self._mass_selection_snapshot(selection)
        self._mass_selection_reconciliation_required = True
        try:
            suspended = selection.SuspendSelectionList()
        except BaseException as exc:
            raise ExecutionFailure('mass_selection_suspend_unconfirmed',
                'Selection suspension failed; no calculation or blind resume attempted.', uncertain=True) from exc
        if type(suspended) is not int or suspended != int(bool(original)):
            raise ExecutionFailure('mass_selection_suspend_unconfirmed',
                'Selection suspension did not acknowledge the original list.', uncertain=True)
        primary = None
        try:
            if self._mass_selection_snapshot(selection):
                raise rejected('mass_selection_scope_unconfirmed', 'Temporary selection list is not empty.')
            return self._calculate_mass_properties(model, bodies)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            try:
                selection.ResumeSelectionList()  # Native void; attempt once, verify exact objects/marks.
                if self._mass_selection_snapshot(selection) != original:
                    raise RuntimeError('Original selection objects or marks were not restored.')
            except BaseException as exc:
                failure = ExecutionFailure('mass_selection_restore_unconfirmed',
                    'Original selection restoration was not confirmed; do not repeat the calculation.', uncertain=True)
                if primary is not None:
                    failure.add_note('Primary calculation error: ' + repr(primary))
                raise failure from exc
            self._mass_selection_reconciliation_required = False

    def _mass_selection_snapshot(self, selection):
        count = int(selection.GetSelectedObjectCount2(-1))
        items = []
        for index in range(1, count + 1):
            item = selection.GetSelectedObject6(index, -1)
            if item is None:
                raise RuntimeError('Selected native object is unavailable.')
            items.append((self.identity(item), int(selection.GetSelectedObjectMark(index))))
        if int(selection.GetSelectedObjectCount2(-1)) != count:
            raise RuntimeError('Selection changed during inventory.')
        return tuple(items)

    def _calculate_mass_properties(self, model, bodies):
        mp = binding.wrap(self._extension(model).CreateMassProperty2(), self._module.IMassProperty2)
        if mp is None:
            raise rejected('mass_properties_unavailable', 'SolidWorks did not create a mass calculation object.')
        mp.UseSystemUnits = True
        mp.IncludeHiddenBodiesOrComponents = True
        mp.ShowWeldBeadMass = False
        if not mp.UseSystemUnits or not mp.IncludeHiddenBodiesOrComponents or mp.ShowWeldBeadMass:
            raise rejected('mass_properties_scope_unconfirmed', 'SI, hidden-body or weld-bead scope was not confirmed.')
        mp.SelectedItems = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
                                                  [body._oleobj_ for body in bodies])
        self._confirm_mass_scope(mp, bodies)
        overrides = binding.wrap(mp.GetOverrideOptions(), self._module.IMassPropertyOverrideOptions)
        if overrides is None or overrides.OverrideMass or overrides.OverrideCenterOfMass:
            raise rejected('mass_properties_overridden', 'Calculated mass/center cannot be proved without unambiguous override status.')
        utility = binding.wrap(self._sw.GetMathUtility(), self._module.IMathUtility)
        if utility is None:
            raise rejected('mass_properties_unavailable', 'Model coordinate transform is unavailable.')
        transform = binding.wrap(utility.CreateTransform(win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8,
            [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.])), self._module.IMathTransform)
        if transform is None or not mp.SetCoordinateSystem(transform):
            raise rejected('mass_properties_scope_unconfirmed', 'Model coordinate frame was not confirmed.')
        if not mp.Recalculate():
            raise rejected('mass_properties_read_failed', 'SolidWorks mass recalculation failed.')
        self._confirm_mass_scope(mp, bodies)
        if not mp.UseSystemUnits or not mp.IncludeHiddenBodiesOrComponents or mp.ShowWeldBeadMass:
            raise rejected('mass_properties_scope_unconfirmed', 'Mass calculation scope changed during recalculation.')
        if overrides.OverrideMass or overrides.OverrideCenterOfMass:
            raise rejected('mass_properties_overridden', 'Mass/center override changed during recalculation.')
        center = mp.CenterOfMass
        return {'volume_m3': mp.Volume, 'surface_area_m2': mp.SurfaceArea, 'mass_kg': mp.Mass,
                'density_kg_m3': mp.Density, 'center_of_mass_m': None if center is None else tuple(center)}

    def _confirm_mass_scope(self, mp, bodies):
        actual = tuple(mp.SelectedItems or ())
        if len(actual) != len(bodies):
            raise rejected('mass_properties_scope_unconfirmed', 'SolidWorks changed the explicit body scope.')
        remaining = list(bodies)
        for raw in actual:
            token = self.identity(raw)
            for index, body in enumerate(remaining):
                if token == self.identity(body):
                    remaining.pop(index)
                    break
            else:
                raise rejected('mass_properties_scope_unconfirmed', 'Mass properties refer to a different native body.')
