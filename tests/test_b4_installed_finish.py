"""Real SQLite/JobRunner and Python worker; no native Q/CAD acceptance."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.runtime_v2 import Runtime


spec = importlib.util.spec_from_file_location('_b4_installed_finish_tests',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_b4_installed_finish.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

CONTEXT = dict(document_id='pure-original-part', configuration='Основная', expected_revision='pure-before',
               dimension_id='pure-original-dimension')
ARGUMENTS = dict(CONTEXT, value=12, unit='mm')
PAYLOAD = dict(arguments=ARGUMENTS, context=CONTEXT, mutates=True)


class PythonWorker:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)

    def submit(self, function):
        return self.pool.submit(function)

    def shutdown(self, timeout_s=5):
        self.pool.shutdown(wait=True)
        return True


@pytest.fixture
def owner(tmp_path):
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    persisted = []
    seam = helper.InstalledFinishSeam(module, journal_path=tmp_path / 'jobs.sqlite', persist=persisted.append)
    seam.install()
    store = module.JobStore(tmp_path / 'jobs.sqlite')
    runtime = module.Runtime(store, worker_factory=PythonWorker)
    yield seam, module, store, runtime, persisted
    if store.barrier is not None and store.barrier.state == 'waiting':
        store.release(runtime=runtime)
    # Pure callback worker only; explicit release above belongs to this fixture.
    assert runtime.shutdown() is True
    if seam._installed:
        seam.uninstall()


def arm(owner, **kwargs):
    seam, _, store, runtime, _ = owner
    return store.arm(runtime=runtime, request_id='new-pure-target', operation='dimension.set_value',
                     payload=deepcopy(PAYLOAD), **kwargs)


def committed(store, oid):
    store.prepare_mutation(oid, connection_epoch='pure-epoch', **{key: CONTEXT[key] for key in
        ('document_id', 'configuration', 'expected_revision')}, before_state={'pure': 'before'}, effect_scope='application')
    store.verify_mutation(oid, outcome='committed', evidence={'pure_callback': 'returned'})
    return {'verified': True, 'value': 12, 'synthetic_cad_free': True}


def test_unarmed_proxy_delegates_real_store_and_nonmatching_finish(owner):
    _, _, store, runtime, _ = owner
    runtime._runner = JobRunner(store, PythonWorker())
    job = runtime._runner.submit('unarmed-read', 'dimension.get', {}, lambda: {'pure': 'metadata'})
    row = asyncio.run(runtime._runner.wait(job['operation_id'], 5))
    assert row['status'] == 'succeeded' and row['result'] == {'pure': 'metadata'}
    assert store.state == 'unarmed' and store.barrier is None
    arm(owner)
    other = runtime._runner.submit('other-read', 'dimension.get', {}, lambda: {'pure': 'other'})
    assert asyncio.run(runtime._runner.wait(other['operation_id'], 5))['status'] == 'succeeded'
    assert store.state == 'armed'


def test_real_runtime_prepare_then_arm_target_holds_original_finish_and_explicit_release(owner):
    seam, _, store, runtime, persisted = owner
    calls = []
    finish_calls = []
    original_finish = store._store.finish

    def count_original_finish(operation_id, status, **kwargs):
        finish_calls.append((operation_id, status))
        return original_finish(operation_id, status, **kwargs)

    store._store.finish = count_original_finish  # Actual JobStore implementation still executes.

    def execute(operation, arguments, operation_id=None):
        calls.append(operation)
        if operation == 'dimension.get':
            return dict(CONTEXT, pure_prepare=True)
        return committed(store, operation_id)

    runtime._execute = execute  # Own artificial domain callback, no COM catalog.
    prepared = asyncio.run(runtime.read('pure-prepare', 'dimension.get', {}, timeout_s=5))
    assert prepared['status'] == 'succeeded'
    observed = prepared['result']
    arguments = {key: observed[key] for key in CONTEXT}
    arguments.update(value=12, unit='mm')
    payload = dict(arguments=arguments, context={key: observed[key] for key in CONTEXT}, mutates=True)
    result = store.arm(runtime=runtime, request_id='new-pure-target', operation='dimension.set_value', payload=payload)
    assert not result['accepted'] and result['native_q'] == 'not_run'
    job = asyncio.run(runtime.mutate('new-pure-target', 'dimension.set_value', arguments, timeout_s=0))
    assert store.wait_reached(5)
    held = store.get(job['operation_id'])
    assert held['status'] == 'running' and held['result'] is None
    assert held['mutation']['phase'] == 'prepared' and held['mutation']['verification']['outcome'] == 'committed'
    assert len(persisted) == 1 and persisted[0] == store.barrier.receipt
    assert len(persisted[0]['journal']) == 2  # Includes real preparation history.
    assert persisted[0]['native_quiescence_proven'] is False
    with pytest.raises(helper.InstalledFinishError, match='Cannot close'):
        store.close()
    with pytest.raises(helper.InstalledFinishError, match='Cannot unwire'):
        seam.uninstall()
    store.release(runtime=runtime)
    settled = asyncio.run(runtime._runner.wait(job['operation_id'], 5))
    assert settled['status'] == 'succeeded' and settled['mutation']['phase'] == 'committed'
    assert settled['result']['value'] == 12 and store.barrier.state == 'finished'
    assert calls == ['dimension.get', 'dimension.set_value']
    assert finish_calls == [(prepared['operation_id'], 'succeeded'), (job['operation_id'], 'succeeded')]
    with pytest.raises(helper._barrier.FinishBarrierError, match='Release requires'):
        store.release(runtime=runtime)


@pytest.mark.parametrize('change', ['operation', 'value', 'revision', 'object'])
def test_armed_payload_change_rejected_before_real_job_creation(owner, change):
    _, _, store, _, _ = owner
    arm(owner)
    operation, payload = 'dimension.set_value', deepcopy(PAYLOAD)
    if change == 'operation': operation = 'feature.rename'
    elif change == 'value': payload['arguments']['value'] = 13
    elif change == 'revision': payload['context']['expected_revision'] = 'foreign'
    else: payload['arguments']['dimension_id'] = 'foreign'
    before = helper._barrier._read_journal(store.path)
    with pytest.raises(helper.InstalledFinishError, match='payload changed'):
        store.create('new-pure-target', operation, payload['arguments'], payload['context'], mutates=True)
    assert helper._barrier._read_journal(store.path) == before == []


@pytest.mark.parametrize('status', ['queued', 'running', 'succeeded'])
def test_existing_target_cannot_be_adopted_at_arm(owner, status):
    _, _, store, runtime, _ = owner
    job, _ = store.create('new-pure-target', 'dimension.set_value', ARGUMENTS, CONTEXT, mutates=True)
    if status != 'queued': store.start(job['operation_id'])
    if status == 'succeeded':
        result = committed(store, job['operation_id'])
        store.finish(job['operation_id'], 'succeeded', result=result)
    before = helper._barrier._read_journal(store.path)
    with pytest.raises(helper.InstalledFinishError, match='already exists'):
        arm(owner)
    assert store.state == 'arm_failed' and store.barrier is None
    assert helper._barrier._read_journal(store.path) == before
    with pytest.raises(helper.InstalledFinishError, match='Failed arm'):
        store.create('another-mutation', 'dimension.set_value', ARGUMENTS, CONTEXT, mutates=True)


def test_repeated_arm_is_latched_without_replacing_original_barrier(owner):
    _, _, store, _, _ = owner
    arm(owner)
    original = store.barrier
    with pytest.raises(helper.InstalledFinishError, match='one-shot'):
        arm(owner)
    assert store.barrier is original


@pytest.mark.parametrize('foreign', ['runtime', 'runtime_store', 'runner_store', 'server_factory'])
def test_foreign_runtime_store_runner_or_removed_wiring_refuses_arm(owner, foreign):
    seam, module, store, runtime, _ = owner
    original = None
    passed_runtime = runtime
    if foreign == 'runtime': passed_runtime = SimpleNamespace(store=store, _runner=None)
    elif foreign == 'runtime_store':
        original, runtime.store = runtime.store, SimpleNamespace()
    elif foreign == 'runner_store': runtime._runner = SimpleNamespace(store=SimpleNamespace())
    else: original, module.JobStore = module.JobStore, JobStore
    try:
        with pytest.raises(helper.InstalledFinishError):
            store.arm(runtime=passed_runtime, request_id='new-pure-target', operation='dimension.set_value', payload=PAYLOAD)
        assert store.state == 'arm_failed' and store.barrier is None
    finally:
        if foreign == 'runtime_store': runtime.store = original
        elif foreign == 'runner_store': runtime._runner = None
        elif foreign == 'server_factory': module.JobStore = original


@pytest.mark.parametrize('missing', ['document_id', 'configuration', 'expected_revision', 'dimension_id'])
def test_unprepared_missing_context_or_object_fails_arm(owner, missing):
    _, _, store, runtime, _ = owner
    payload = deepcopy(PAYLOAD)
    payload['context'].pop(missing, None)
    payload['arguments'].pop(missing, None)
    with pytest.raises((helper.InstalledFinishError, helper._barrier.FinishBarrierError)):
        store.arm(runtime=runtime, request_id='new-pure-target', operation='dimension.set_value', payload=payload)
    assert store.state == 'arm_failed' and store.barrier is None


def test_factory_shape_wraps_exact_server_store_before_runtime(tmp_path):
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime)

    def main():
        store = module.JobStore(tmp_path / 'server' / 'jobs.sqlite')
        runtime = module.Runtime(store, worker_factory=PythonWorker)
        assert isinstance(store, helper.ArmableFinishStore)
        assert runtime.store is store and store.state == 'unarmed'
        assert runtime.shutdown()

    module.main = main
    seam = helper.InstalledFinishSeam(module, journal_path=tmp_path / 'server' / 'jobs.sqlite', persist=lambda receipt: None)
    seam.install()
    module.main()  # Same construction order as installed server_v2.main; no CAD.
    seam.uninstall()
    assert module.JobStore is JobStore and module.Runtime is Runtime


def test_factory_rejects_foreign_store_path_second_store_runtime_and_repeat_install(owner, tmp_path):
    seam, module, store, runtime, _ = owner
    with pytest.raises(helper.InstalledFinishError, match='one-shot'):
        seam.install()
    with pytest.raises(helper.InstalledFinishError, match='one original'):
        module.JobStore(tmp_path / 'foreign.sqlite')
    with pytest.raises(helper.InstalledFinishError, match='exactly one Runtime'):
        module.Runtime(store)
    with pytest.raises(helper.InstalledFinishError, match='exactly one Runtime'):
        module.Runtime(SimpleNamespace())


def test_waiting_observation_is_not_native_admission_or_stop_authority(owner):
    _, _, store, _, _ = owner
    assert not store.wait_reached(0)
    assert all(value is False for key, value in helper.authority().items() if key not in ('native_q', 'native_admission'))
    assert helper.authority()['native_q'] == helper.authority()['native_admission'] == 'not_run'


@pytest.mark.parametrize('timeout', [-1, True, 61, '1'])
def test_wait_observation_invalid_limits_no_arm_or_release(owner, timeout):
    store = owner[2]
    with pytest.raises(helper.InstalledFinishError, match='Bounded'):
        store.wait_reached(timeout)
    assert store.barrier is None and store.state == 'unarmed'


def test_target_already_in_real_jobrunner_callback_refuses_arm_without_cancel_or_adoption(owner):
    _, _, store, runtime, _ = owner
    runtime._runner = JobRunner(store, PythonWorker())
    started, finish_callback = Event(), Event()
    callback_calls = []

    def callback(operation_id):
        callback_calls.append(operation_id)
        started.set()
        assert finish_callback.wait(5)
        return committed(store, operation_id)

    job = runtime._runner.submit('new-pure-target', 'dimension.set_value', ARGUMENTS, callback,
        context=CONTEXT, mutates=True, verify=lambda result: result['verified'] is True, pass_operation_id=True)
    try:
        assert started.wait(5)
        before = helper._barrier._read_journal(store.path)
        with pytest.raises(helper.InstalledFinishError, match='already exists'):
            arm(owner)
        assert store.barrier is None and store.state == 'arm_failed'
        assert helper._barrier._read_journal(store.path) == before
        assert store.get(job['operation_id'])['status'] == 'running'
    finally:
        finish_callback.set()  # Own pure callback normal return; no cancellation.
    row = asyncio.run(runtime._runner.wait(job['operation_id'], 5))
    assert row['status'] == 'succeeded' and callback_calls == [job['operation_id']]


def test_changed_target_is_rejected_by_real_jobrunner_before_worker_dispatch(owner):
    _, _, store, runtime, _ = owner
    runtime._runner = JobRunner(store, PythonWorker())
    arm(owner)
    calls = []
    changed = dict(ARGUMENTS, value=13)
    with pytest.raises(helper.InstalledFinishError, match='payload changed'):
        runtime._runner.submit('new-pure-target', 'dimension.set_value', changed,
            lambda: calls.append('must-not-run'), context=CONTEXT, mutates=True, verify=lambda result: True)
    assert calls == [] and helper._barrier._read_journal(store.path) == []


def test_initial_arm_rejects_contradictory_prepared_object_scope(owner):
    _, _, store, runtime, _ = owner
    payload = deepcopy(PAYLOAD)
    payload['arguments']['dimension_id'] = 'foreign-object'
    with pytest.raises(helper.InstalledFinishError, match='object identity differs'):
        store.arm(runtime=runtime, request_id='new-pure-target', operation='dimension.set_value', payload=payload)
    assert store.barrier is None and store.state == 'arm_failed'


def test_inner_original_store_replacement_is_not_valid_factory_wiring(owner, tmp_path):
    _, _, proxy, runtime, _ = owner
    foreign = JobStore(tmp_path / 'foreign-owned.sqlite')
    original = proxy._store
    proxy._store = foreign
    try:
        with pytest.raises(helper.InstalledFinishError, match='factory wiring required'):
            proxy.arm(runtime=runtime, request_id='new-pure-target', operation='dimension.set_value', payload=PAYLOAD)
        assert proxy.barrier is None
    finally:
        proxy._store = original
        foreign.close()


def test_arbitrary_boolean_owner_cannot_construct_armable_proxy(tmp_path):
    store = JobStore(tmp_path / 'own.sqlite')
    try:
        with pytest.raises(helper.InstalledFinishError, match='Original installed factory owner'):
            helper.ArmableFinishStore(store, owner=SimpleNamespace(assert_wired=lambda runtime: True))
    finally:
        store.close()
