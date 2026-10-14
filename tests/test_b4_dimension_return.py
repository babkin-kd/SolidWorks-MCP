"""Original Runtime/domain/guard/SQLite with artificial CAD; not native Q."""
import asyncio
from concurrent.futures import Future
from contextlib import nullcontext
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from solidworks_mcp.application_guard import ApplicationModelMutationGuard
from solidworks_mcp.runtime_v2 import Runtime
from test_dimension_domain_v2 import setup


spec = importlib.util.spec_from_file_location('_b4_dimension_return_tests',
    Path(__file__).resolve().parents[1] / 'scripts/verifier_b4_dimension_return.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class InlineWorker:
    def submit(self, function):
        result = Future()
        try:
            result.set_result(function())
        except BaseException as error:
            result.set_exception(error)
        return result

    def shutdown(self, timeout_s=5):
        return True


@pytest.fixture
def prepared(setup):
    adapter, catalog, store, ids = setup
    application = SimpleNamespace(CommandInProgress=False)
    guards = []

    def guard(model):
        blocking = [0]
        model.GetBlockingState = lambda: blocking[0]
        model.Lock = lambda: blocking.__setitem__(0, 2)
        model.UnLock = lambda: blocking.__setitem__(0, 0)
        instance = ApplicationModelMutationGuard(application, [model], lambda model, state: nullcontext())
        guards.append(instance)
        return instance

    catalog.mutation_guard = guard
    runtime = Runtime(store, worker_factory=InlineWorker)
    runtime._catalog = catalog.documents
    runtime._dimensions = catalog
    runtime._connection_epoch = catalog.connection_epoch
    page = catalog.list(ids[0], 'Основная')
    context = dict(document_id=ids[0], configuration='Основная', object_id=page['items'][0]['object_id'],
                   expected_revision=page['revision'])
    arguments = dict(context, value=12., unit='mm')
    payload = dict(arguments=arguments, context=context, mutates=True)
    yield SimpleNamespace(runtime=runtime, store=store, catalog=catalog, adapter=adapter,
                          application=application, guards=guards, payload=payload)
    assert runtime.shutdown() is True


def observer(data, persist):
    return helper.DimensionReturnObserver(data.runtime, request_id='original-target',
                                         payload=deepcopy(data.payload), persist=persist).install()


def dispatch(data, request='original-target', arguments=None):
    return asyncio.run(data.runtime.mutate(request, 'dimension.set_value',
                    data.payload['arguments'] if arguments is None else arguments, timeout_s=0))


def test_original_callback_guard_and_unfinished_checkpoint_observed_before_finish(prepared):
    data = prepared
    receipts = []
    original_execute, original_guard = data.runtime._execute, data.catalog.mutation_guard
    owner = observer(data, receipts.append)
    job = dispatch(data)
    assert job['status'] == 'succeeded', job.get('error')
    assert len(data.adapter.dimension_writes) == len(data.guards) == len(receipts) == 1
    assert data.application.CommandInProgress is False
    receipt = receipts[0]
    assert receipt['journal_row_before_finish']['status'] == 'running'
    assert receipt['journal_row_before_finish']['mutation']['phase'] == 'prepared'
    assert receipt['journal_row_before_finish']['mutation']['verification']['outcome'] == 'committed'
    assert receipt['return_result'] == job['result']
    assert receipt['operation_id'] == job['operation_id']
    assert receipt['guard_completed'] is True and receipt['accepted'] is False
    observation = owner.observation()
    assert observation['callback_live'] is False and observation['persisted'] is True
    assert observation['native_q'] == 'not_run'
    assert observation['process_stop_authorized'] is observation['restart_authorized'] is False
    owner.uninstall()
    assert data.runtime._execute == original_execute and data.catalog.mutation_guard is original_guard


@pytest.mark.parametrize('fault', ['request', 'payload', 'foreign_guard'])
def test_foreign_target_or_guard_cannot_produce_return_receipt(prepared, fault):
    data = prepared
    receipts = []
    if fault == 'foreign_guard':
        data.catalog.mutation_guard = lambda model: nullcontext()
    owner = observer(data, receipts.append)
    arguments = deepcopy(data.payload['arguments'])
    if fault == 'payload':
        arguments['value'] = 13.
    job = dispatch(data, request='other-request' if fault == 'request' else 'original-target', arguments=arguments)
    assert job['status'] != 'succeeded'
    assert receipts == [] and data.adapter.dimension_writes == []
    assert owner.observation()['persisted'] is False
    assert data.application.CommandInProgress is False
    if fault == 'foreign_guard':
        # Original Runtime retired its catalog after the unexpected callback
        # exception; that foreign/released wiring must not be silently adopted.
        assert data.runtime._dimensions is None
        with pytest.raises(helper.ReturnObservationError, match='wiring changed'):
            owner.uninstall()
    else:
        owner.uninstall()


def test_lost_receipt_acknowledgement_never_becomes_success_or_retries(prepared):
    data = prepared
    receipts = []

    def failing_persist(receipt):
        receipts.append(receipt)
        raise OSError('Artificial receipt acknowledgement lost after original callback return.')

    owner = observer(data, failing_persist)
    job = dispatch(data)
    assert job['status'] == 'unknown'
    assert job['mutation']['phase'] == 'unresolved'
    assert job['mutation']['verification']['outcome'] == 'committed'
    assert len(receipts) == len(data.adapter.dimension_writes) == 1
    observation = owner.observation()
    assert observation['original_callback_returned'] is True
    assert observation['persist_attempted'] is True and observation['persisted'] is False
    assert observation['callback_live'] is False and data.application.CommandInProgress is False
    replay = dispatch(data)
    assert replay == job and len(receipts) == len(data.adapter.dimension_writes) == 1
    owner.uninstall()


def test_deferred_persistence_acknowledgement_is_not_accepted(prepared):
    async def deferred():
        pass

    owner = observer(prepared, lambda receipt: deferred())
    job = dispatch(prepared)
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved'
    assert owner.observation()['persist_attempted'] is True
    assert owner.observation()['persisted'] is False
    assert prepared.application.CommandInProgress is False
    owner.uninstall()


def test_observer_cannot_adopt_replaced_original_callback(prepared):
    data = prepared
    data.runtime._execute = lambda *args: {'verified': True}
    with pytest.raises(helper.ReturnObservationError, match='Original Runtime callback'):
        observer(data, lambda value: None)


def test_observer_install_is_one_shot_and_cannot_unwire_live_callback(prepared):
    owner = observer(prepared, lambda value: None)
    with pytest.raises(helper.ReturnObservationError, match='one-shot'):
        owner.install()
    owner._live = True  # Artificial in-progress owner, not native evidence.
    with pytest.raises(helper.ReturnObservationError, match='live original callback'):
        owner.uninstall()
    owner._live = False
    owner.uninstall()
