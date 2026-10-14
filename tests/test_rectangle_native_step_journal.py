"""Durable bridge ordering with artificial CAD only; not native acceptance."""
from copy import deepcopy

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from test_rectangle_construction_stages import Adapter, extrusion, wrappers


def receipt(adapter, recorder):
    return adapter.new_rectangle_stage_receipt(adapter.model, adapter.items,
        adapter.part_creation_controls(adapter.model), sketch=adapter.sketch, recorder=recorder)


def test_each_creation_and_owned_inverse_call_has_pending_before_effect_and_return_after():
    adapter, steps = Adapter(), []
    def record(label, phase, evidence):
        steps.append((label, phase, deepcopy(evidence)))
        if label == 'extrude':
            assert len(adapter.calls) == (0 if phase == 'pending' else 1)
        if label == 'restore_delete_extrusion':
            assert len(adapter.deletions) == (0 if phase == 'pending' else 1)
    owned = receipt(adapter, record)
    adapter.extrude_rectangle_sketch(adapter.model, extrusion(), owned)
    adapter.restore_rectangle_extrusion(adapter.model, owned)
    expected = ['extrude', 'name_extrusion', 'name_depth', 'rebuild', 'name_body',
                'restore_delete_extrusion', 'restore_rebuild']
    assert [(label, phase) for label, phase, _ in steps] == [
        (label, phase) for label in expected for phase in ('pending', 'returned')]
    assert all(evidence == {'native_call_returned': phase == 'returned'}
               for _, phase, evidence in steps)
    assert owned.pending_native_step is None and not owned.native_step_journal_failed


def test_lost_native_ack_keeps_pending_step_and_never_fabricates_return_or_deletes():
    adapter, steps = Adapter(), []
    owned = receipt(adapter, lambda *args: steps.append(args))
    adapter.factory_mode = 'lost_ack'
    with pytest.raises(RuntimeError):
        adapter.extrude_rectangle_sketch(adapter.model, extrusion(), owned)
    assert len(adapter.calls) == 1
    assert [(label, phase) for label, phase, _ in steps] == [('extrude', 'pending')]
    assert owned.pending_native_step == 'extrude'
    with pytest.raises(ExecutionFailure): adapter.restore_rectangle_extrusion(adapter.model, owned)
    assert not adapter.deletions


@pytest.mark.parametrize('phase', ['pending', 'returned'])
def test_storage_failure_keeps_uncertainty_and_never_repeats_call_or_inverse(phase):
    adapter, steps = Adapter(), []
    def record(label, current, evidence):
        steps.append((label, current))
        if current == phase: raise OSError('Artificial durable storage failure')
    owned = receipt(adapter, record)
    with pytest.raises(OSError): adapter.extrude_rectangle_sketch(adapter.model, extrusion(), owned)
    assert len(adapter.calls) == (0 if phase == 'pending' else 1)
    assert owned.pending_native_step == 'extrude' and owned.native_step_journal_failed
    count = len(steps)
    with pytest.raises(ExecutionFailure): adapter.extrude_rectangle_sketch(adapter.model, extrusion(), owned)
    with pytest.raises(ExecutionFailure): adapter.restore_rectangle_extrusion(adapter.model, owned)
    assert len(steps) == count and not adapter.deletions


def test_normal_null_return_is_journaled_as_returned_without_claiming_success():
    adapter, steps = Adapter(), []
    owned = receipt(adapter, lambda *args: steps.append(args))
    adapter.factory_mode = 'null'
    with pytest.raises(ExecutionFailure): adapter.extrude_rectangle_sketch(adapter.model, extrusion(), owned)
    assert [phase for _, phase, _ in steps] == ['pending', 'returned']
    assert owned.pending_creation and owned.pending_native_step is None
    with pytest.raises(ExecutionFailure): adapter.restore_rectangle_extrusion(adapter.model, owned)
    assert not adapter.deletions


def test_recorder_validation_precedes_any_native_receipt_observation():
    adapter = Adapter()
    adapter.new_base_receipt = lambda *args: pytest.fail('Unexpected native observation')
    with pytest.raises(ExecutionFailure): receipt(adapter, {'client': 'callback'})


def test_native_objects_are_not_serialized_or_inspected_for_journal_evidence():
    adapter, steps = Adapter(), []
    class Opaque:
        def __repr__(self): pytest.fail('Opaque native handle was stringified')
    owned = receipt(adapter, lambda *args: steps.append(args))
    result = Opaque()
    assert adapter._rectangle_native_step(owned, 'server_owned_probe', lambda: result) is result
    assert steps == [('server_owned_probe', 'pending', {'native_call_returned': False}),
                     ('server_owned_probe', 'returned', {'native_call_returned': True})]
