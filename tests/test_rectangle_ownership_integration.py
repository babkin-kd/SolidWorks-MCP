"""Actual coordinator/runner/registry over artificial native geometry bindings."""
from copy import deepcopy

import pytest

from solidworks_mcp.jobs import ExecutionFailure, _json
from solidworks_mcp.owned_rectangle_feature import OwnedRectangleFeatureRegistry, PROFILES
from test_rectangle_construction_execution import execution, sketch_proof, extrusion_proof, empty_adapter


@pytest.fixture
def integrated(execution):
    state = execution
    adapter, catalog = state.adapter, state.catalog
    entry, _ = catalog.documents.resolve('target', 'Основная')
    identities = {}
    def identity(current):
        return identities.setdefault(id(current), object())
    adapter.identity = identity
    entry.identity = identity(entry.model)
    configuration_identity = adapter.configuration_identity(entry.model, 'Основная')
    def context(*args):
        row = next(r for r in adapter.state['semantic']['documents'] if r['document_id'] == 'target')
        return entry, {**deepcopy(row), 'document_type': 'part', 'path': '',
                       'active_configuration': 'Основная', 'configurations': ['Основная']}
    catalog.documents.resolve = context
    catalog.documents._entries = [entry]
    catalog.documents._refresh = lambda: None
    original_receipt = adapter.new_rectangle_stage_receipt
    def receipt(*args, **kwargs):
        result = original_receipt(*args, **kwargs)
        result.model_identity = entry.identity
        result.configuration_identity = configuration_identity
        return result
    adapter.new_rectangle_stage_receipt = receipt
    original_create = adapter.create_rectangle_sketch
    def create(current, *args):
        result = original_create(current, *args)
        retained = args[-1]
        feature = getattr(retained, state.kind)
        if feature is not None:
            setattr(retained, state.kind + '_identity', identity(feature))
            feature.GetID = lambda: feature.native_id
        return result
    adapter.create_rectangle_sketch = adapter.extrude_rectangle_sketch = create
    original_prepare = catalog.prepare_sketch
    state.operation = 'sketch.create_rectangle' if state.kind == 'sketch' else 'part.extrude_rectangle'
    def prepare(*args, **kwargs):
        result = original_prepare(*args, **kwargs)
        result['scope'] = PROFILES[state.operation][1]
        return result
    catalog.prepare_sketch = catalog.prepare_extrusion = prepare
    catalog.ownership = OwnedRectangleFeatureRegistry(catalog.documents,state.store,'construction_epoch')
    return state


def run(state, request_id='ownership'):
    args = dict(document_id='target',configuration='Основная',**vars(state.definition))
    prepare = state.catalog.prepare_sketch if state.kind == 'sketch' else state.catalog.prepare_extrusion
    args['expected_revision'] = prepare(**{k:v for k,v in args.items()})['revision']
    method = state.catalog.create_sketch if state.kind == 'sketch' else state.catalog.create_extrusion
    def execute(oid):
        state.adapter.operation_id = oid
        return method(oid,**args)
    job = state.runner.submit(request_id,state.operation,args,execute,context=args,
        mutates=True,pass_operation_id=True,verify=lambda value:value['verified'] is True)
    return state.store.get(job['operation_id'])


def test_successful_creation_registers_and_admits_only_its_terminal_owned_binding(integrated):
    state = integrated
    job = run(state)
    assert job['status'] == 'succeeded',job.get('error')
    binding, feature = state.catalog.ownership.resolve('target','Основная',
        job['result']['value']['object_id'],connection_epoch='construction_epoch')
    assert binding.creation_operation_id == job['operation_id'] and binding.feature is feature
    assert _json(binding.baseline_target_snapshot) == _json(state.before['snapshots']['target'])
    assert _json(binding.created_target_snapshot) == _json(state.after['snapshots']['target'])
    assert not state.catalog.receipts
    assert run(state) == job and state.adapter.dispatches == 1


def test_post_commit_ownership_failure_is_unknown_without_inverse_or_replay(integrated):
    state = integrated
    calls = []
    def fail(*args,**kwargs):
        calls.append(True)
        raise RuntimeError('Late ownership native getter normally failed.')
    state.catalog.ownership.register = fail
    job = run(state)
    assert job['status'] == 'unknown' and job['error']['code'] == 'rectangle_ownership_registration_unconfirmed'
    assert state.adapter.dispatches == 1 and state.adapter.inverses == 0 and state.adapter.busy is False
    assert job['mutation']['phase'] == 'unresolved'
    assert state.catalog.receipts[job['operation_id']]['verified_mode'] == 'effect'
    assert state.store.mutation_blockers('construction_epoch','target')
    assert run(state) == job and len(calls) == 1 and state.adapter.dispatches == 1


def test_ownership_capacity_refuses_before_guard_or_native_write(integrated):
    def fail(document_id):
        raise ExecutionFailure('owned_rectangle_budget','Prewrite bounded ownership budget exhausted.')
    integrated.catalog.ownership.check_capacity = fail
    job = run(integrated)
    assert job['status'] == 'failed' and job['error']['code'] == 'owned_rectangle_budget'
    assert integrated.adapter.dispatches == integrated.adapter.inverses == integrated.adapter.guard_count == 0
