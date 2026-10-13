"""Artificial first-retire driver with actual JobRunner/SQLite, no native CAD."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import JobRunner, JobStore, ExecutionFailure


path = Path(__file__).resolve().parents[1] / 'scripts/verify_owned_leaf_deletion_positive.py'
spec = importlib.util.spec_from_file_location('owned_leaf_positive_driver', path)
helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)


class Inline:
    def submit(self, function):
        from concurrent.futures import Future
        future = Future()
        try: future.set_result(function())
        except BaseException as error: future.set_exception(error)
        return future


@pytest.fixture
def artificial(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    state = NS(deleted=False, fault=None, deletes=0, prepares=0, delegations=[], flag_sets=[], persists=[])
    class Application:
        _command = True
        def __init__(self): self.token = object()
        @property
        def CommandInProgress(self): return self._command
        @CommandInProgress.setter
        def CommandInProgress(self, value):
            state.flag_sets.append(value)
            if state.fault == 'flag_release_throw' and value is False:
                raise RuntimeError('artificial release missing acknowledgement')
            if state.fault == 'flag_reacquire_throw' and value is True:
                raise RuntimeError('artificial reacquisition missing acknowledgement')
            self._command = value
    sw = Application()
    target, neighbor = NS(token=object()), NS(token=object(), GetSaveFlag=lambda: True)
    feature, borrowed = NS(token=object()), NS(token=object())
    owned = [target, neighbor]
    base = dict(clone_state=dict(profile='BASE'), solid_body_count=1, evidence='artificial-full-base')
    after_snapshot = dict(clone_state=dict(profile='SKETCH'), solid_body_count=0, evidence='artificial-full-sketch')
    neighbor_snapshot = {'evidence': 'artificial-full-neighbor'}
    def identity(value):
        if value is feature and state.deleted:
            raise AssertionError('Deleted feature cannot be queried after deletion.')
        return value.token
    adapter = NS(_sw=sw, identity=identity, active_document=lambda: target, documents=lambda: list(owned),
        first_save_part_snapshot=lambda model: deepcopy(neighbor_snapshot),
        rectangle_construction_snapshot=lambda model: deepcopy(after_snapshot if state.deleted else base))
    documents = NS(resolve=lambda identifier, cfg: (NS(identity=target.token), dict(document_type='part',
        path='', active_configuration=cfg, configurations=[cfg])))
    receipt = NS(attempted=True, native_call_returned=True, pending_creation=False,
        pending_sketch_close=False, sketch_closed=False, selection_uncertain=False,
        restore_attempted=False, restored=False, pending_native_step=None, native_step_journal_failed=False,
        view_state_uncertain=False, controls={'artificial': False}, baseline_features=[(object(), {'native_id': 3})],
        deleted=[], borrowed_sketch_snapshot={'artificial': 'borrowed'},
        annotation_views=NS(baseline=[NS(view=object(), token=object(), data={'artificial': 'view'})],
            owned=[(NS(view=object(), token=object(), data={'artificial': 'owned-view'}), object())], binding_attempted=True,
            bound=True, retirement_attempted=False, retired=False), model_view=NS(baseline={'artificial': 'viewport'}),
        extrusion=feature, extrusion_identity=feature.token, borrowed_sketch=borrowed,
        borrowed_sketch_identity=borrowed.token, model_identity=target.token,
        configuration_identity=object(), native_step_recorder=lambda *args: None)
    object_id, sketch_id = 'feat_original_extrusion', 'feat_original_sketch'
    binding = NS(kind='extrusion', model=target, model_identity=target.token, feature_identity=feature.token,
        receipt=receipt, native_id=5, persistent_id=b'artificial-pid', creation_operation_id=None)
    sketch_binding = NS(feature_identity=borrowed.token)
    registry = NS(_bindings={('target', object_id): binding, ('target', sketch_id): sketch_binding})
    def resolve(document, configuration, identifier, **kwargs):
        assert document == 'target' and configuration == 'Основная' and kwargs['connection_epoch'] == 'epoch'
        held = registry._bindings[(document, identifier)]
        return held, feature if held is binding else borrowed
    registry.resolve = resolve
    original = NS(adapter=adapter, store=store, documents=documents, connection_epoch='epoch',
        ownership=registry, receipts={})
    runner = JobRunner(store, Inline())
    def committed(operation_id, arguments, result):
        store.prepare_mutation(operation_id, connection_epoch='epoch', document_id='target',
            configuration='Основная', expected_revision=arguments['expected_revision'],
            before_state={}, effect_scope='application')
        store.verify_mutation(operation_id, outcome='committed', evidence={'after': result.get('after', {})})
        return result
    def creation(request, operation, identifier, sketch_reference=None):
        args = dict(document_id='target', configuration='Основная', expected_revision='rev_artificial')
        if sketch_reference: args['sketch_object_id'] = sketch_reference
        result = dict(verified=True, artificial_creation_proof=True, value={
            'feature_object_id' if operation == 'part.extrude_rectangle' else 'sketch_object_id': identifier})
        return runner.submit(request, operation, args, lambda op: committed(op, args, result), context=args,
            mutates=True, pass_operation_id=True, verify=lambda value: value['verified'] is True)
    sketch_job = creation('original-sketch', 'sketch.create_rectangle', sketch_id)
    extrusion_job = creation('original-extrusion', 'part.extrude_rectangle', object_id, sketch_id)
    binding.creation_operation_id = extrusion_job['operation_id']
    parent = dict(phase='owned_cleanup', native_calls_live=False, independent_native_readback_verified=True,
        package_origin_verified=True, independent_volume_mm3=8000., wheel={'artificial': 'candidate'},
        captures=[dict(status='returned')], independent_base=deepcopy(base), independent_neighbor=neighbor_snapshot,
        cases=[dict(label=label, passed=True) for label in ('B1-N1-separate-sketch-and-replay',
            'B1-N1-separate-extrusion-and-replay', 'B1-N2-N3-exact-native-base-and-neighbor')],
        sketch_job=sketch_job, extrusion_job=extrusion_job)
    def write_parent():
        (tmp_path / 'report.json').write_text(json.dumps(parent, ensure_ascii=False), encoding='utf8')
    write_parent()
    def delegate(application, module, root, retiring, owned_models, record):
        assert application.CommandInProgress is True
        state.delegations.append(root)
        owned_models.remove(root)
        if state.fault == 'delegated_close_pending': raise RuntimeError('artificial close postcondition unknown')
        record(owned_models)
    driver = NS(RectangleConstructionCatalog=lambda *args: original, retire_owned=delegate,
        verified_rectangle_job=lambda row: row['status'] == 'succeeded' and row['result'].get('artificial_creation_proof') is True,
        validated_rectangle_snapshot=lambda row: deepcopy(row), validated_part_snapshot=lambda row: deepcopy(row),
        BASE='BASE', SKETCH='SKETCH', InlineSta=Inline)
    class Leaf:
        def __init__(self, docs, current_store, epoch, ownership):
            self.documents, self.store, self.ownership = docs, current_store, ownership
            self.receipts = {}
        def prepare(self, **context):
            assert sw.CommandInProgress is False
            state.prepares += 1
            if state.fault == 'prepare_failed': raise ExecutionFailure('artificial', 'unsupported', uncertain=False)
            return dict(delete_authorized=False, native_execution_available=True,
                revision='rev_leaf', baseline=dict(snapshots={'target': deepcopy(base)}))
        def delete(self, operation_id, **arguments):
            state.deletes += 1
            if state.fault == 'delete_pending': raise ExecutionFailure('artificial', 'pending', uncertain=True)
            if state.fault == 'delete_failed': raise ExecutionFailure('artificial', 'no effect', uncertain=False)
            state.deleted = True
            del registry._bindings[('target', object_id)]
            if state.fault == 'receipt_changed': receipt.restore_attempted = True
            if state.fault == 'view_binding_changed':
                original_view, _ = receipt.annotation_views.owned[0]
                receipt.annotation_views.owned[0] = (original_view, object())
            result = dict(verified=True, value=dict(preserved_sketch_object_id=sketch_id),
                after=dict(pending=False, guard_released=True, receipt=dict(bridge_returned=True,
                    deletion_bridge_verified=True), sketch_canonical_and_pid_confirmed=True,
                    target_canonical_absent=True, state=dict(snapshots={'target': deepcopy(after_snapshot)})))
            return committed(operation_id, arguments, result)
    report = dict(native_calls_live=False, accepted=False, native_b2_accepted=False, public_mcp_accepted=False)
    def persist(): state.persists.append(deepcopy(report))
    hook = helper.OwnLeafPositiveHook(driver, tmp_path, report, persist, leaf_factory=Leaf, runner_factory=JobRunner)
    assert hook.construction(documents, store, 'epoch') is original
    state.hook, state.parent, state.report, state.store = hook, parent, report, store
    state.sw, state.target, state.neighbor, state.owned = sw, target, neighbor, owned
    state.original, state.receipt, state.write_parent = original, receipt, write_parent
    state.call = lambda root=target: hook.retire(sw, None, root, [root], owned, lambda models: None)
    yield state
    store.close()


def test_first_retire_runs_actual_sqlite_commit_replay_once_then_delegates_own_cleanup(artificial):
    a = artificial
    original = a.store.get(a.parent['extrusion_job']['operation_id'])
    a.call()
    assert a.hook.completed is True and a.deletes == a.prepares == 1
    assert a.flag_sets == [False, True]
    assert a.delegations == [a.target]
    assert a.report['delete_job'] == a.report['replay_job']
    assert a.report['delete_job']['mutation']['phase'] == 'committed'
    assert a.store.get(original['operation_id']) == original
    assert a.report['original_creation_receipt_before'] == a.report['original_creation_receipt_after']
    assert a.report['original_creation_receipt_before']['annotation_views']['owned'] == [
        dict(view={'artificial': 'owned-view'}, bound_feature_retained=True)]
    assert a.report['independent_after']['clone_state']['profile'] == 'SKETCH'
    a.call(a.neighbor)
    assert a.delegations == [a.target, a.neighbor] and a.deletes == 1
    with pytest.raises(ValueError): a.call(a.neighbor)
    assert a.deletes == 1 and len(a.delegations) == 2
    assert a.report['accepted'] is a.report['native_b2_accepted'] is a.report['public_mcp_accepted'] is False


@pytest.mark.parametrize('fault', ['not_independent', 'wrong_volume', 'partial_capture', 'wrong_phase',
    'foreign_target', 'sqlite_changed', 'busy_not_owned', 'incomplete_original'])
def test_admission_refuses_before_flag_release_delete_or_cleanup(artificial, fault):
    a = artificial
    root = a.target
    if fault == 'not_independent': a.parent['independent_native_readback_verified'] = False
    elif fault == 'wrong_volume': a.parent['independent_volume_mm3'] = 9600.
    elif fault == 'partial_capture': a.parent['captures'][0]['status'] = 'running'
    elif fault == 'wrong_phase': a.parent['phase'] = 'independent_base'
    elif fault == 'foreign_target': root = NS(token=object())
    elif fault == 'sqlite_changed': a.parent['extrusion_job']['result']['value']['feature_object_id'] = 'foreign'
    elif fault == 'busy_not_owned': a.sw._command = False
    else: a.original.receipts['pending'] = object()
    a.write_parent()
    with pytest.raises((ValueError, KeyError)): a.call(root)
    assert a.deletes == 0 and a.delegations == [] and a.flag_sets == []
    with pytest.raises(ValueError): a.call()
    assert a.deletes == 0 and a.delegations == []


@pytest.mark.parametrize('fault,deletes,sets', [('prepare_failed', 0, [False]),
    ('delete_failed', 1, [False]), ('delete_pending', 1, [False]),
    ('receipt_changed', 1, [False]), ('view_binding_changed', 1, [False]), ('flag_release_throw', 0, [False]),
    ('flag_reacquire_throw', 1, [False, True])])
def test_failure_pending_or_changed_receipt_never_delegates_retries_or_resets_parent_flag(artificial, fault, deletes, sets):
    a = artificial; a.fault = fault
    with pytest.raises((ValueError, RuntimeError)): a.call()
    assert a.deletes == deletes and a.flag_sets == sets and a.delegations == []
    assert a.report['parent_retained_sta_required'] is True
    with pytest.raises(ValueError): a.call()
    assert a.deletes == deletes and a.flag_sets == sets and a.delegations == []
    if fault == 'delete_pending': assert a.report['delete_job']['status'] == 'unknown'


def test_singular_original_catalog_cannot_be_recreated(artificial):
    with pytest.raises(ValueError): artificial.hook.construction(None, None, 'other')
    assert artificial.deletes == 0 and len(artificial.hook.domains) == 1


def test_distinct_application_proxies_with_same_canonical_identity_are_admitted(artificial):
    a = artificial
    a.original.adapter._sw = NS(token=a.sw.token)
    assert a.original.adapter._sw is not a.sw
    a.call()
    assert a.hook.completed is True and a.deletes == 1 and a.delegations == [a.target]


def test_foreign_application_canonical_identity_is_rejected_before_flag_or_mutation(artificial):
    a = artificial
    a.original.adapter._sw = NS(token=object())
    with pytest.raises(ValueError): a.call()
    assert a.deletes == 0 and a.prepares == 0 and a.flag_sets == [] and a.delegations == []


def test_unknown_delegated_close_forbids_subsequent_neighbor_cleanup(artificial):
    a = artificial; a.fault = 'delegated_close_pending'
    with pytest.raises(RuntimeError): a.call()
    assert a.hook.completed is True and a.deletes == 1 and a.owned == [a.neighbor]
    with pytest.raises(ValueError): a.call(a.neighbor)
    assert a.delegations == [a.target] and a.owned == [a.neighbor] and a.deletes == 1
