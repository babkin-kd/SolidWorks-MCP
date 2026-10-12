"""Actual durable coordinator plus independent artificial geometry admission.

This tests the domain protocol, not an installed facade or native CAD operation.
"""
from copy import deepcopy
import hashlib
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_rectangle_construction import CadRectangleConstructionMixin, NativeRectangleStageReceipt
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore, _json
from solidworks_mcp.rectangle_construction_catalog import RectangleConstructionCatalog
from test_rectangle_postconditions import proof as sketch_proof, empty_adapter
from test_rectangle_extrusion_postconditions import proof as extrusion_proof
from test_native_document_close_v2 import Worker


@pytest.fixture(params=['sketch', 'extrusion'])
def execution(request, sketch_proof, extrusion_proof, tmp_path):
    kind = request.param
    before, after, definition = sketch_proof if kind == 'sketch' else extrusion_proof
    adapter = NS(state=deepcopy(before), busy=False, dispatches=0, inverses=0, releases=0,
                 fault=None, guard_count=0)
    model, neighbor, cfg = object(), object(), object()
    reference = NS(native_id=0 if kind == 'sketch' else 4)
    entry = NS(document_id='target', model=model, identity=id(model), features={})
    other = NS(document_id='neighbor', model=neighbor, identity=id(neighbor), features={})
    adapter.application_busy = lambda: adapter.busy
    adapter.configuration_identity = lambda *args: cfg
    adapter.features = lambda current: [reference]
    adapter.identity = id
    adapter.feature_summary = lambda current: {'native_id': current.native_id}
    store = JobStore(tmp_path/'construction.sqlite')
    documents = NS(adapter=adapter, resolve=lambda *args: (entry, {}))
    catalog = RectangleConstructionCatalog(documents, store, 'construction_epoch')
    catalog.features._resolve = lambda *args: (reference, NS(persistent_id=b'exact-reference'))
    catalog.sessions.census._disk_files = lambda semantic: deepcopy(adapter.state['semantic']['files'])

    def capture(target_id, guarded_ids=()):
        assert bool(guarded_ids) == adapter.busy
        if adapter.fault == 'inspect_once' and adapter.dispatches and not adapter.busy:
            adapter.fault = None
            raise RuntimeError('Artificial failed first observation after guard release')
        return [entry, other], deepcopy(adapter.state['semantic']), deepcopy(adapter.state['snapshots'])
    catalog._capture = capture

    def prepared(*args, **kwargs):
        return dict(scope='construction_artificial_test_v1', revision='rev_'+hashlib.sha256(
            _json(before).encode()).hexdigest(), baseline=deepcopy(before),
            reference_persistent_id_hex=b'exact-reference'.hex(), plane_transform=[1.,0.,0.])
    catalog.prepare_sketch = catalog.prepare_extrusion = prepared
    catalog._prepare = lambda *args, **kwargs: {
        **prepared(), 'revision': prepared()['revision'] if adapter.state == before else 'rev_changed'}

    def receipt(current, features, controls, *, sketch=None, recorder=None):
        result = NativeRectangleStageReceipt(id(model), id(cfg), (), deepcopy(controls))
        result.native_step_recorder = recorder
        result.borrowed_sketch = sketch
        return result
    adapter.new_rectangle_stage_receipt = receipt

    def create(current, *args):
        owned = args[-1]
        assert adapter.busy
        assert store.get(adapter.operation_id)['mutation']['phase'] == 'prepared'
        owned.attempted = True
        def effect():
            assert store.get(adapter.operation_id)['mutation']['verification']['native_steps'][-1]['phase'] == 'pending'
            adapter.dispatches += 1
            adapter.state = deepcopy(after)
            if adapter.fault == 'lost_ack':
                owned.pending_creation = True
                raise RuntimeError('Artificial lost native response after effect')
            created = NS(native_id=4 if kind == 'sketch' else 5)
            setattr(owned, kind, created)
            setattr(owned, kind+'_identity', id(created))
            owned.native_call_returned = True
            owned.sketch_closed = kind == 'sketch'
            if adapter.fault == 'neighbor':
                adapter.state['snapshots']['neighbor'] = {'foreign':'changed'}
            return created
        CadRectangleConstructionMixin._rectangle_native_step(owned, 'construct_artificial', effect)
    adapter.create_rectangle_sketch = adapter.extrude_rectangle_sketch = create

    def inverse(current, owned):
        assert adapter.busy
        def effect():
            adapter.inverses += 1
            adapter.state = deepcopy(before)
            owned.restored, owned.restore_attempted = True, True
            if adapter.fault == 'bad_restored_counter':
                adapter.state['semantic']['documents'][0].pop('observation_sequence')
            elif adapter.fault == 'bad_restored_stamp':
                if kind == 'extrusion':
                    adapter.state['snapshots']['target']['clone_state']['dimensions'][0].pop('owner_update_stamp')
                else:
                    adapter.state['snapshots']['target']['clone_state']['origin'].pop('native_id')
        CadRectangleConstructionMixin._rectangle_native_step(owned, 'restore_artificial', effect)
    adapter.restore_rectangle_sketch = adapter.restore_rectangle_extrusion = inverse

    class Guard:
        def __init__(self): self.evidence = {'scope':'artificial_guard', 'released':False}
        def __enter__(self):
            assert not adapter.busy
            assert store.get(adapter.operation_id)['mutation']['before_state']['_mutation_effect_scope'] == 'application'
            adapter.busy=True
            adapter.guard_count += 1
            if adapter.fault == 'stale_in_guard':
                adapter.state['snapshots']['neighbor'] = {'foreign':'concurrent edit'}
            return self
        def __exit__(self,*args):
            adapter.busy=False
            adapter.releases += 1
            self.evidence['released']=True
            if adapter.fault == 'release_lost': raise RuntimeError('Artificial lost release acknowledgement')
    adapter.native_open_guard = lambda *args: Guard()
    runner = JobRunner(store, Worker())
    value = NS(kind=kind, before=before, after=after, definition=definition, adapter=adapter,
               store=store,catalog=catalog,runner=runner)
    yield value
    store.close()


def run(value, request_id='construction', revision=None):
    args = dict(document_id='target', configuration='Основная',
                expected_revision=revision or value.catalog.prepare_sketch()['revision'], **vars(value.definition))
    method = value.catalog.create_sketch if value.kind == 'sketch' else value.catalog.create_extrusion
    def execute(operation_id):
        value.adapter.operation_id = operation_id
        return method(operation_id, **args)
    job = value.runner.submit(request_id, 'rectangle.'+value.kind, args, execute,
        context=args, mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
    return value.store.get(job['operation_id'])


def test_full_domain_success_is_proved_after_guard_release_and_journal_is_durable(execution):
    job = run(execution)
    assert job['status'] == 'succeeded', job.get('error')
    assert job['mutation']['phase'] == 'committed'
    assert execution.adapter.dispatches == 1 and not execution.adapter.busy
    assert execution.adapter.state == execution.after
    steps = job['mutation']['verification']['native_steps']
    assert steps[-1]['name'] == 'rectangle_released_check' and steps[-1]['evidence']['verified'] is True
    assert job['result']['after']['guard_released'] is True
    assert job['result']['execution_guard']['full_release_check'] == 'effect'
    assert not execution.catalog.receipts


def test_replay_reuses_actual_job_without_another_effect(execution):
    first = run(execution)
    assert run(execution) == first and execution.adapter.dispatches == 1


def test_wrong_revision_is_rejected_before_guard_or_native_dispatch(execution):
    job = run(execution, revision='rev_stale')
    assert job['status'] == 'failed' and job['error']['code'] == 'stale_revision'
    assert execution.adapter.dispatches == execution.adapter.guard_count == 0


def test_prewrite_concurrent_edit_is_not_undone(execution):
    execution.adapter.fault = 'stale_in_guard'
    job = run(execution)
    assert job['status'] == 'failed' and job['mutation']['phase'] == 'not_started', job
    assert execution.adapter.dispatches == execution.adapter.inverses == 0
    assert execution.adapter.state['snapshots']['neighbor'] == {'foreign':'concurrent edit'}


@pytest.mark.parametrize('fault', ['lost_ack','neighbor','release_lost'])
def test_unconfirmed_or_foreign_effect_is_retained_without_retry_or_inverse(execution, fault):
    execution.adapter.fault = fault
    job = run(execution)
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved', job
    assert execution.adapter.dispatches == 1 and execution.adapter.inverses == 0
    assert execution.catalog.receipts
    assert run(execution) == job and execution.adapter.dispatches == 1
    next_job = run(execution, 'new-request')
    assert next_job['status'] == 'failed' and execution.adapter.dispatches == 1


def test_proved_owned_effect_can_restore_under_a_new_guard_after_released_observation_failure(execution):
    execution.adapter.fault = 'inspect_once'
    job = run(execution)
    assert job['status'] == 'failed' and job['mutation']['phase'] == 'rolled_back', job
    assert execution.adapter.guard_count == execution.adapter.releases == 2
    assert execution.adapter.inverses == 1 and execution.adapter.state == execution.before
    assert not execution.catalog.receipts and not execution.adapter.busy


@pytest.mark.parametrize('phase',['pending','returned'])
def test_durable_step_failure_never_turns_into_success_or_automatic_inverse(execution, phase, monkeypatch):
    original = execution.store.record_mutation_step
    def broken(operation_id, *, name, phase: str, evidence):
        if name == 'rectangle_construct_artificial' and phase == failure_phase:
            raise OSError('Artificial durable journal failure')
        return original(operation_id,name=name,phase=phase,evidence=evidence)
    failure_phase=phase
    monkeypatch.setattr(execution.store,'record_mutation_step',broken)
    job=run(execution)
    assert job['status']=='unknown' and execution.adapter.inverses==0
    assert execution.adapter.dispatches==(0 if phase=='pending' else 1)


def test_request_payload_conflict_never_reuses_or_repeats_a_native_effect(execution):
    from solidworks_mcp.jobs import JobError
    first=run(execution)
    with pytest.raises(JobError): run(execution,revision='rev_different_payload')
    assert execution.adapter.dispatches==1 and first['status']=='succeeded'


@pytest.mark.parametrize('fault',['bad_restored_counter','bad_restored_stamp'])
def test_partial_restoration_does_not_hide_missing_observation_fields(execution,fault,monkeypatch):
    original=execution.catalog._capture
    calls=[0]
    def capture(*args,**kwargs):
        if execution.adapter.dispatches and not execution.adapter.busy and not calls[0]:
            calls[0]+=1
            execution.adapter.fault=fault
            raise RuntimeError('Artificial post-release observation failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(execution.catalog,'_capture',capture)
    job=run(execution)
    assert execution.adapter.inverses==1
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved'
