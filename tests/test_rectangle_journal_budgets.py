"""Finite rectangle inverse ledgers through the real durable store/coordinator.

Geometry is artificial: these tests neither connect to nor accept native CAD.
"""
from copy import deepcopy
import json
import sqlite3

import pytest

from solidworks_mcp.cad_rectangle_construction import CadRectangleConstructionMixin
from solidworks_mcp.jobs import JobError, JobStore
from test_rectangle_native_verifier import (
    configured, execution, sketch_proof, extrusion_proof, empty_adapter,
)
from test_rectangle_construction_execution import run
from test_rectangle_restoration_verifier import helper as restoration_gate


CASES = [('sketch.create_rectangle', 44), ('part.extrude_rectangle', 46)]


def stage_names(operation):
    sketch = operation == 'sketch.create_rectangle'
    creation = (['open_sketch', 'name_sketch', 'draw_rectangle', 'define_rectangle',
                 'close_sketch', 'rebuild_sketch'] if sketch else
                ['extrude', 'name_extrusion', 'name_depth', 'rebuild', 'name_body'])
    creation += [f'bind_annotation_view_feature_{i}' for i in range(2 if sketch else 3)]
    creation += ['restore_view_' + key for key in ('orientation', 'scale', 'translation')]
    inverse = (['restore_owned_sketch'] if sketch else
               ['restore_delete_extrusion', 'restore_rebuild'])
    inverse += ['restore_select_annotation_view', 'restore_delete_annotation_view']
    inverse += ['inverse_restore_view_' + key for key in ('orientation', 'scale', 'translation')]
    return creation, inverse


def ledger_names(operation):
    creation, inverse = stage_names(operation)
    return (['execution_guard'] + creation + ['guard_release_1', 'restoration_guard']
            + inverse + ['guard_release_2', 'restored_release_check'])


@pytest.fixture
def store(tmp_path):
    value = JobStore(tmp_path / 'jobs.sqlite')
    yield value
    value.close()


def prepare(store, operation, arguments=None):
    context = dict(document_id='target', configuration='Основная', expected_revision='rev_1')
    job, _ = store.create('request', operation, arguments or {}, context, mutates=True)
    job_id = job['operation_id']
    store.start(job_id)
    store.prepare_mutation(job_id, connection_epoch='epoch', **context,
                           before_state={'untouched_neighbor': True}, effect_scope='application')
    return job_id


def pair(store, job_id, name):
    for phase in ('pending', 'returned'):
        store.record_mutation_step(job_id, name='rectangle_' + name, phase=phase,
                                   evidence={'native_call_returned': phase == 'returned'})


def durable_verification(store, job_id):
    with sqlite3.connect(f'file:{store.path.as_posix()}?mode=ro', uri=True) as reader:
        return reader.execute('SELECT verification,updated_at FROM mutations WHERE operation_id=?',
                              (job_id,)).fetchone()


@pytest.mark.parametrize('operation,budget', CASES)
def test_full_owned_inverse_and_final_release_are_durable_at_finite_limit(store, operation, budget):
    job_id = prepare(store, operation)
    original = deepcopy(store.get(job_id)['mutation']['before_state'])
    for name in ledger_names(operation):
        pair(store, job_id, name)
    raw = durable_verification(store, job_id)
    steps = json.loads(raw[0])['native_steps']
    assert len(steps) == budget
    assert [row['sequence'] for row in steps] == list(range(1, budget + 1))
    assert steps[32]['name'].startswith('rectangle_')  # inverse continues beyond old cap
    assert steps[-1]['name'] == 'rectangle_restored_release_check'
    assert store.get(job_id)['mutation']['before_state'] == original
    assert store.mutation_blockers('epoch', 'neighbor')
    with pytest.raises(JobError) as error:
        pair(store, job_id, 'unplanned_extra_inverse')
    assert error.value.code == 'native_step_budget_exceeded'
    assert durable_verification(store, job_id) == raw  # rejection changes no row/timestamp
    store.verify_mutation(job_id, outcome='rolled_back', evidence={'full_baseline_verified': True})
    assert store.mutation_blockers('epoch', 'neighbor')
    final = store.finish(job_id, 'failed')
    assert final['mutation']['phase'] == 'rolled_back'
    assert final['mutation']['verification']['native_steps'] == steps
    assert not store.mutation_blockers('epoch', 'neighbor')


@pytest.mark.parametrize('operation,budget', CASES)
@pytest.mark.parametrize('invalid_phase,invalid_name', [
    ('pending', 'overlapping_inverse'), ('returned', 'wrong_inverse'),
])
def test_expanded_budget_keeps_exact_pending_pair_and_unresolved_hold(
        store, operation, budget, invalid_phase, invalid_name):
    job_id = prepare(store, operation)
    names = ledger_names(operation)
    for name in names[:-1]:
        pair(store, job_id, name)
    store.record_mutation_step(job_id, name='rectangle_' + names[-1], phase='pending',
                               evidence={'target': 'exact'})
    assert len(store.get(job_id)['mutation']['verification']['native_steps']) == budget - 1
    before = durable_verification(store, job_id)
    with pytest.raises(JobError) as error:
        store.record_mutation_step(job_id, name='rectangle_' + invalid_name, phase=invalid_phase,
                                   evidence={'target': 'exact'})
    assert error.value.code == 'invalid_native_step'
    assert durable_verification(store, job_id) == before
    with pytest.raises(JobError) as error:
        store.verify_mutation(job_id, outcome='rolled_back', evidence={'claimed_restored': True})
    assert error.value.code == 'native_step_unresolved'
    assert store.finish(job_id, 'failed')['mutation']['phase'] == 'unresolved'
    assert store.mutation_blockers('epoch', 'neighbor')


@pytest.mark.parametrize('operation', [
    'feature.rename', 'rectangle.sketch', 'rectangle.extrusion',
    'sketch.create_rectangle.extra', 'PART.EXTRUDE_RECTANGLE',
])
def test_generic_and_alias_operations_keep_32_despite_payload_budget_claim(store, operation):
    job_id = prepare(store, operation, {
        'operation': 'part.extrude_rectangle', 'native_step_budget': 1000,
        'scope': 'closed_rectangle_blind_extrusion_v1',
    })
    for index in range(16):
        pair(store, job_id, f'generic_{index}')
    before = durable_verification(store, job_id)
    with pytest.raises(JobError) as error:
        pair(store, job_id, 'extra')
    assert error.value.code == 'native_step_budget_exceeded'
    assert durable_verification(store, job_id) == before
    assert store.finish(job_id, 'failed')['mutation']['phase'] == 'unresolved'
    assert store.mutation_blockers('epoch', 'neighbor')


def test_actual_rectangle_execution_can_finish_maximal_owned_restoration(configured, monkeypatch):
    """Expand only fixture effects; production execution and final oracle stay real."""
    value = configured
    operation, budget = CASES[0 if value.kind == 'sketch' else 1]
    creation, inverse = stage_names(operation)
    native_step = CadRectangleConstructionMixin._rectangle_native_step

    def expanded_step(receipt, label, call, *args, **kwargs):
        labels = creation if label == 'construct_artificial' else (
            inverse if label == 'restore_artificial' else None)
        if labels is None:
            return native_step(receipt, label, call, *args, **kwargs)
        result = native_step(receipt, labels[0], call, *args, **kwargs)
        for expanded in labels[1:]:
            native_step(receipt, expanded, lambda: True)
        return result

    monkeypatch.setattr(CadRectangleConstructionMixin, '_rectangle_native_step', staticmethod(expanded_step))
    value.adapter.fault = 'inspect_once'
    job = run(value, 'maximal-owned-restoration')
    assert job['operation'] == operation
    assert job['status'] == 'failed', job.get('error')
    assert job['mutation']['phase'] == 'rolled_back'
    assert value.adapter.dispatches == value.adapter.inverses == 1
    assert not value.adapter.busy and value.adapter.state == value.before
    steps = job['mutation']['verification']['native_steps']
    assert len(steps) == budget
    assert steps[-1]['name'] == 'rectangle_restored_release_check'
    assert restoration_gate.verified_rectangle_restoration(job)
    assert not value.store.mutation_blockers(value.catalog.connection_epoch, 'neighbor')
    assert not value.catalog.receipts
    assert run(value, 'maximal-owned-restoration') == job
    assert value.adapter.dispatches == value.adapter.inverses == 1
