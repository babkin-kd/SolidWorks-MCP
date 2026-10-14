"""Exact owned model-view preservation for separate rectangle stages.

The first native solid may trigger isometric/zoom changes. Preserve the explicit
target's original view under its mutation guard; never admit that change as a
volatile observation or write another model's view. Only typed double SAFEARRAYs
may enter MathUtility: Python lists otherwise become VARIANT-element arrays.
"""
from copy import deepcopy
from dataclasses import dataclass

import pythoncom
import win32com.client

from . import binding
from .jobs import ExecutionFailure


@dataclass
class RectangleModelView:
    model_identity: object
    view_identity: object
    baseline: dict


def capture_model_view(adapter, model):
    view = binding.wrap(model.ActiveView, adapter._module.IModelView)
    state = adapter.document_view_snapshot(model)
    if view is None or state is None:
        raise ExecutionFailure('construction_view_unavailable', 'An exact complete target model view is required.')
    return RectangleModelView(adapter.identity(model), adapter.identity(view), deepcopy(state))


def restore_model_view(adapter, model, receipt, *, inverse=False):
    state = receipt.model_view
    if state is None or receipt.view_state_uncertain:
        raise ExecutionFailure('construction_view_unconfirmed', 'Missing or uncertain model-view receipt.', uncertain=True)
    view = binding.wrap(model.ActiveView, adapter._module.IModelView)
    if (adapter.identity(model) != state.model_identity or view is None
            or adapter.identity(view) != state.view_identity):
        raise ExecutionFailure('construction_view_changed', 'The original target/view incarnation is required.', uncertain=True)
    if adapter.document_view_snapshot(model) == state.baseline:
        return
    receipt.view_state_uncertain = True
    mathutil = binding.wrap(adapter._sw.GetMathUtility(), adapter._module.IMathUtility)
    if mathutil is None:
        raise ExecutionFailure('construction_view_unconfirmed', 'Registered MathUtility is required.', uncertain=True)
    prefix = 'inverse_restore_view_' if inverse else 'restore_view_'
    for key, prop, size, factory, interface in (
        ('orientation', 'Orientation3', 16, mathutil.CreateTransform, adapter._module.IMathTransform),
        ('scale', 'Scale2', 1, None, None),
        ('translation', 'Translation3', 3, mathutil.CreateVector, adapter._module.IMathVector),
    ):
        # Orientation/scale setters may alter translation. Re-read immediately;
        # each original property is attempted at most once in this phase.
        if adapter.document_view_snapshot(model)[key] == state.baseline[key]:
            continue
        value = state.baseline[key]
        if factory is not None:
            array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(value))
            value = binding.wrap(factory(array), interface)
            if value is None or list(value.ArrayData) != state.baseline[key] or len(value.ArrayData) != size:
                raise ExecutionFailure('construction_view_math_unconfirmed', 'Exact typed native math data is required.', uncertain=True)
        adapter._rectangle_native_step(receipt, prefix + key, setattr, view, prop, value)
    current = binding.wrap(model.ActiveView, adapter._module.IModelView)
    if (current is None or adapter.identity(current) != state.view_identity
            or adapter.document_view_snapshot(model) != state.baseline):
        raise ExecutionFailure('construction_view_restore_unconfirmed', 'Original target view readback differs.', uncertain=True)
    receipt.view_state_uncertain = False
