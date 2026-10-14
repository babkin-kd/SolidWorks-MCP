"""Child-owned control with real Runtime/SQLite and artificial CAD, never native Q."""
import asyncio
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from solidworks_mcp import __version__
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobStore
from solidworks_mcp.runtime_v2 import Runtime
from test_dimension_domain_v2 import setup
from test_b4_dimension_return import prepared
from test_b4_installed_finish import PythonWorker


spec = importlib.util.spec_from_file_location('_b4_dimension_control_tests',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_b4_installed_dimension_control.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def seeded_root(tmp_path, monkeypatch):
    monkeypatch.setattr(helper, 'private_root', lambda: tmp_path)
    root = tmp_path / 'original-child'
    root.mkdir()
    lineage = dict(package_version=__version__, git_sha='a' * 40, wheel_sha256='b' * 64,
        source_digest='c' * 64, nonce='d' * 64, owner_pid=os.getpid(), state_root=str(root.resolve()))
    helper.owned._write(root / 'launch-spec.json', dict(state_dir=str(root.resolve()), nonce=lineage['nonce'],
        candidate=dict(wheel={key: lineage[key] for key in
            ('package_version', 'git_sha', 'wheel_sha256', 'source_digest')})))
    return root, lineage


def no_authority(value):
    for key, expected in helper.authority().items():
        assert value[key] == expected


@pytest.fixture
def owner(prepared, tmp_path, monkeypatch):
    root, lineage = seeded_root(tmp_path, monkeypatch)
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    control = helper.InstalledDimensionControl(module, state_root=root, lineage=lineage).install()
    proxy = module.JobStore(control.seam.path)
    prepared.adapter.mutation_guard = prepared.catalog.mutation_guard
    runtime = module.Runtime(proxy, worker_factory=PythonWorker,
                             catalog_factory=lambda: DocumentCatalog(prepared.adapter))
    discovery = asyncio.run(runtime.read('original-discovery', 'document.list', {}, timeout_s=5))
    assert discovery['status'] == 'succeeded'
    doc_id = discovery['result']['documents'][0]['document_id']
    listed = asyncio.run(runtime.read('original-dimensions', 'dimension.list',
        dict(document_id=doc_id, configuration='Основная'), timeout_s=5))
    assert listed['status'] == 'succeeded'
    page = listed['result']
    context = dict(document_id=doc_id, configuration='Основная', object_id=page['items'][0]['object_id'],
                   expected_revision=page['revision'])
    payload = dict(arguments=dict(context, value=12., unit='mm'), context=context, mutates=True)
    value = SimpleNamespace(control=control, module=module, proxy=proxy, runtime=runtime,
                            payload=payload, lineage=lineage, prepared=prepared, root=root)
    yield value
    # Only fixture-owned pure workers are drained. No kill/cancel/native cleanup.
    if proxy.barrier is not None and proxy.barrier.state == 'waiting':
        proxy.release(runtime=runtime)
    if control.observer is not None and control.observer._installed:
        if runtime._runner is not None:
            runtime._runner.worker.submit(lambda: None).result(timeout=5)
        control.observer.uninstall()
    if not runtime._closed:
        assert runtime.shutdown()
    if control.seam._installed:
        control.seam.uninstall()


def arm(owner, **changes):
    values = dict(runtime=owner.runtime, lineage=owner.lineage, request_id='original-target',
                  operation='dimension.set_value', payload=owner.payload)
    values.update(changes)
    return owner.control.arm(**values)


def dispatch(owner):
    return asyncio.run(owner.runtime.mutate('original-target', 'dimension.set_value',
                                          owner.payload['arguments'], timeout_s=0))


def test_normal_unarmed_server_factory_shape_retains_original_closed_pointers(tmp_path, monkeypatch):
    root, lineage = seeded_root(tmp_path, monkeypatch)
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime)

    def main():
        store = module.JobStore(root / 'server' / 'jobs.sqlite')
        runtime = module.Runtime(store, worker_factory=lambda: pytest.fail('No metadata worker'))
        assert runtime._runner is runtime._catalog is runtime._dimensions is None
        assert store.state == 'unarmed'
        assert runtime.shutdown()

    module.main = main
    control = helper.InstalledDimensionControl(module, state_root=root, lineage=lineage).install()
    module.main()  # Actual server's factory/lifecycle shape, no SDK/process/CAD.
    original_runtime, original_proxy = control.runtime, control.proxy
    receipt = control.complete_normal()
    state = control.inspect_state()
    assert state['phase'] == 'closed' and state['fault'] is state['target'] is None
    assert state['receipts'] == dict(callback=None, finish=None)
    assert state['persist_attempted'] == dict(callback=False, finish=False)
    assert state['return_observation'] is state['barrier_state'] is None
    assert control.runtime is original_runtime and control.proxy is original_proxy
    assert original_proxy._owner._original_owned_store._db is None
    assert receipt['journal'] == [] and receipt['target'] is None
    assert receipt['original_factories_restored'] is True
    assert module.JobStore is JobStore and module.Runtime is Runtime
    assert not (root / 'callback-return.json').exists() and not (root / 'finish-barrier.json').exists()
    assert helper.owned._read(root / 'dimension-control-closed.json') == receipt
    no_authority(receipt)
    no_authority(state)


def test_actual_domain_return_then_finish_durable_rows_and_explicit_normal_close(owner, monkeypatch):
    control, proxy, runtime = owner.control, owner.proxy, owner.runtime
    before = helper.finished._barrier._read_journal(proxy.path)
    original_count = owner.prepared.store._db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
    # The arm seam may only inspect cached Python data, never recapture CAD.
    with monkeypatch.context() as patch:
        patch.setattr(runtime._dimensions, '_capture', lambda *a: pytest.fail('Arm recaptured CAD'))
        patch.setattr(runtime._catalog, 'resolve', lambda *a: pytest.fail('Arm resolved CAD'))
        arm_receipt = arm(owner)
    assert helper.finished._barrier._read_journal(proxy.path) == before
    assert owner.prepared.adapter.dimension_writes == []
    no_authority(arm_receipt)
    job = dispatch(owner)
    assert proxy.wait_reached(5), control.inspect_state()
    state = control.inspect_state()
    assert state['phase'] == 'armed' and state['barrier_state'] == 'waiting'
    assert state['return_observation']['persisted'] is True
    assert state['return_observation']['callback_live'] is False
    callback = helper.owned._read(owner.root / 'callback-return.json')
    finish = helper.owned._read(owner.root / 'finish-barrier.json')
    actual = helper.finished._barrier._read_journal(proxy.path)
    assert callback['journal'] == finish['journal'] == actual
    assert len(actual) == 3 and actual[-1]['status'] == 'running'
    assert actual[-1]['mutation']['phase'] == 'prepared'
    assert callback['original_receipt']['operation_id'] == finish['original_receipt']['operation_id'] == job['operation_id']
    assert callback['original_receipt']['return_result'] == finish['original_receipt']['return_result']
    assert callback['lineage'] == finish['lineage'] == owner.lineage
    assert callback['target'] == finish['target'] == control.target
    assert state['receipts'] == dict(callback=callback, finish=finish)
    assert owner.prepared.application.CommandInProgress is False
    assert len(owner.prepared.adapter.dimension_writes) == 1
    assert owner.prepared.store._db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == original_count
    no_authority(callback)
    no_authority(finish)
    no_authority(control.release(runtime=runtime, lineage=owner.lineage))
    final = asyncio.run(runtime._runner.wait(job['operation_id'], 5))
    assert final['status'] == 'succeeded' and final['mutation']['phase'] == 'committed'
    no_authority(control.prepare_normal_shutdown())
    assert runtime.shutdown()
    closed = control.complete_normal()
    assert closed['journal'][-1]['status'] == 'succeeded'
    assert control.inspect_state()['phase'] == 'closed'
    assert helper.owned._read(owner.root / 'callback-return.json') == callback
    assert helper.owned._read(owner.root / 'finish-barrier.json') == finish


@pytest.mark.parametrize('field', ['owner_pid', 'state_root', 'nonce', 'package_version', 'wheel_sha256', 'extra'])
def test_constructor_foreign_child_root_or_manifest_rejected_before_install(tmp_path, monkeypatch, field):
    root, lineage = seeded_root(tmp_path, monkeypatch)
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    lineage[field] = {'owner_pid': os.getpid()+1, 'state_root': str(tmp_path), 'nonce': 'e'*64,
                     'package_version': 'foreign', 'wheel_sha256': 'e'*64, 'extra': True}[field]
    with pytest.raises(helper.DimensionControlError):
        helper.InstalledDimensionControl(module, state_root=root, lineage=lineage)
    assert module.JobStore is JobStore and module.Runtime is Runtime


@pytest.mark.parametrize('kind', ['queued', 'running', 'unknown', 'failed', 'foreign_target'])
def test_whole_actual_journal_not_just_target_must_be_terminal_original_reads(owner, kind):
    arguments = dict(document_id='foreign', configuration='Основная') if kind == 'foreign_target' else {}
    row, _ = owner.proxy.create('other-job', 'dimension.list', arguments, {}, mutates=False)
    if kind != 'queued':
        owner.proxy.start(row['operation_id'])
    if kind in ('unknown', 'failed'):
        owner.proxy.finish(row['operation_id'], kind, error=dict(code='pure-failure', message='Own test'))
    if kind == 'foreign_target':
        owner.proxy.finish(row['operation_id'], 'succeeded', result=dict(pure_foreign=True))
    before = helper.finished._barrier._read_journal(owner.proxy.path)
    with pytest.raises(helper.DimensionControlError) as caught:
        arm(owner)
    assert caught.value.retained_owner is owner.control
    assert helper.finished._barrier._read_journal(owner.proxy.path) == before
    assert owner.control.inspect_state()['phase'] == 'failed'
    assert owner.control.observer is None and owner.proxy.barrier is None
    with pytest.raises(helper.DimensionControlError):
        arm(owner, request_id='another-target')
    assert not owner.prepared.adapter.dimension_writes


@pytest.mark.parametrize('change', ['runtime', 'runner_store', 'raw_store', 'server_factory', 'nonce',
                                    'object', 'revision', 'configuration', 'operation', 'existing_request', 'missing_cache',
                                    'cached_configuration'])
def test_arm_foreign_wiring_preparation_or_target_latches_without_dispatch(owner, change):
    restore = lambda: None
    kwargs = {}
    payload = deepcopy(owner.payload)
    if change == 'runtime':
        kwargs['runtime'] = SimpleNamespace(store=owner.proxy, _runner=None)
    elif change == 'runner_store':
        old = owner.runtime._runner.store
        owner.runtime._runner.store = SimpleNamespace()
        restore = lambda: setattr(owner.runtime._runner, 'store', old)
    elif change == 'raw_store':
        old = owner.proxy._store
        owner.proxy._store = SimpleNamespace()
        restore = lambda: setattr(owner.proxy, '_store', old)
    elif change == 'server_factory':
        old = owner.module.JobStore
        owner.module.JobStore = JobStore
        restore = lambda: setattr(owner.module, 'JobStore', old)
    elif change == 'nonce':
        kwargs['lineage'] = dict(owner.lineage, nonce='f'*64)
    elif change in ('object', 'revision', 'configuration'):
        field = dict(object='object_id', revision='expected_revision', configuration='configuration')[change]
        payload['context'][field] = payload['arguments'][field] = 'foreign'
        kwargs['payload'] = payload
    elif change == 'operation':
        kwargs['operation'] = 'feature.rename'
    elif change == 'existing_request':
        kwargs['request_id'] = 'original-dimensions'
    elif change == 'missing_cache':
        owner.runtime._catalog._entries[0].features['dimensions']['references'].clear()
    else:
        ref = owner.runtime._catalog._entries[0].features['dimensions']['references'][payload['context']['object_id']]
        ref.configuration = 'foreign'
    before = helper.finished._barrier._read_journal(owner.control.seam.path)
    try:
        with pytest.raises(helper.DimensionControlError) as caught:
            arm(owner, **kwargs)
        assert caught.value.retained_owner is owner.control
        assert owner.control.inspect_state()['phase'] == 'failed'
        assert owner.proxy.barrier is None
        assert not owner.prepared.adapter.dimension_writes
        assert helper.finished._barrier._read_journal(owner.control.seam.path) == before
    finally:
        restore()


def test_original_runtime_queued_read_blocks_arm_without_cancellation_or_adoption(owner):
    entered, proceed = Event(), Event()

    def own_python_hold():
        entered.set()
        assert proceed.wait(5)

    blocking = owner.runtime._runner.worker.submit(own_python_hold)
    assert entered.wait(5)
    try:
        queued = asyncio.run(owner.runtime.read('queued-original-read', 'dimension.get',
            {key: owner.payload['arguments'][key] for key in ('document_id', 'configuration', 'object_id')}, timeout_s=0))
        assert queued['status'] == 'queued'
        before = helper.finished._barrier._read_journal(owner.proxy.path)
        with pytest.raises(helper.DimensionControlError, match='terminal'):
            arm(owner)
        assert helper.finished._barrier._read_journal(owner.proxy.path) == before
        assert owner.proxy.barrier is None and owner.control.observer is None
    finally:
        proceed.set()  # Original own Python callback normal return, no cancellation.
        blocking.result(timeout=5)
    final = asyncio.run(owner.runtime._runner.wait(queued['operation_id'], 5))
    assert final['status'] == 'succeeded' and not owner.prepared.adapter.dimension_writes


@pytest.mark.parametrize('filename', ['callback-return.json', 'finish-barrier.json', 'dimension-control-closed.json'])
def test_existing_receipt_path_is_not_adopted_or_overwritten(tmp_path, monkeypatch, filename):
    root, lineage = seeded_root(tmp_path, monkeypatch)
    path = root / filename
    path.write_text('original-owned-hold', encoding='utf8')
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    with pytest.raises(helper.DimensionControlError, match='no receipt adoption'):
        helper.InstalledDimensionControl(module, state_root=root, lineage=lineage)
    assert path.read_text(encoding='utf8') == 'original-owned-hold'
    assert module.JobStore is JobStore and module.Runtime is Runtime


def test_launch_manifest_drift_after_install_latches_without_new_target_or_receipts(owner):
    spec = helper.owned._read(owner.root / 'launch-spec.json')
    spec['nonce'] = 'e' * 64
    # Deliberate own test artifact corruption, not an owner recovery/retry.
    (owner.root / 'launch-spec.json').write_text(helper._json(spec), encoding='utf8')
    before = helper.finished._barrier._read_journal(owner.proxy.path)
    with pytest.raises(helper.DimensionControlError, match='manifest changed'):
        arm(owner)
    assert owner.control.inspect_state()['phase'] == 'failed'
    assert owner.control.observer is None and owner.proxy.barrier is None
    assert helper.finished._barrier._read_journal(owner.proxy.path) == before
    assert not (owner.root / 'callback-return.json').exists()
    assert not (owner.root / 'finish-barrier.json').exists()


def test_repeated_arm_does_not_replace_original_observer_or_barrier(owner):
    arm(owner)
    original = owner.control.observer, owner.proxy.barrier
    with pytest.raises(helper.DimensionControlError, match='one-shot'):
        arm(owner, request_id='other-target')
    assert (owner.control.observer, owner.proxy.barrier) == original
    with pytest.raises(helper.DimensionControlError):
        owner.control.release(runtime=owner.runtime, lineage=owner.lineage)
    assert owner.control.inspect_state()['phase'] == 'failed'


@pytest.mark.parametrize('kind', ['callback', 'finish'])
@pytest.mark.parametrize('failure', ['before_write', 'fsync', 'exclusive'])
def test_durable_receipt_failure_latches_no_retry_no_false_waiting_receipt(owner, monkeypatch, kind, failure):
    arm(owner)
    name = 'callback-return.json' if kind == 'callback' else 'finish-barrier.json'
    original_write = helper.owned._write
    calls = []

    def failing_write(path, value):
        if Path(path).name == name:
            calls.append(name)
            if failure == 'before_write':
                raise OSError('Own persistence failure')
            if failure == 'exclusive':
                Path(path).write_text('original-owned-conflict', encoding='utf8')
                return original_write(path, value)
            with monkeypatch.context() as patch:
                patch.setattr(helper.owned.os, 'fsync', lambda fd: (_ for _ in ()).throw(OSError('Own fsync failure')))
                return original_write(path, value)
        return original_write(path, value)

    monkeypatch.setattr(helper.owned, '_write', failing_write)
    job = dispatch(owner)
    # Drain the original Python worker normally, including its failure path.
    owner.runtime._runner.worker.submit(lambda: None).result(timeout=5)
    state = owner.control.inspect_state()
    assert state['phase'] == 'failed' and state['persist_attempted'][kind] is True
    assert state['receipts'][kind] is None and calls == [name]
    assert not owner.proxy.wait_reached(0)
    row = owner.proxy.get(job['operation_id'])
    assert row['status'] in ('running', 'unknown')
    assert row['mutation']['phase'] in ('prepared', 'unresolved')
    if failure == 'exclusive':
        assert (owner.root / name).read_text(encoding='utf8') == 'original-owned-conflict'
    with pytest.raises(helper.DimensionControlError):
        owner.control.release(runtime=owner.runtime, lineage=owner.lineage)
    with pytest.raises(helper.DimensionControlError):
        arm(owner, request_id='new-target')
    assert calls == [name] and len(owner.prepared.adapter.dimension_writes) == 1
    no_authority(state)


def test_waiting_finish_does_not_authorize_early_shutdown_or_release_with_foreign_lineage(owner):
    arm(owner)
    dispatch(owner)
    assert owner.proxy.wait_reached(5)
    with pytest.raises(helper.DimensionControlError, match='must complete first'):
        owner.control.prepare_normal_shutdown()
    assert owner.proxy.barrier.state == 'waiting'
    with pytest.raises(helper.DimensionControlError):
        owner.control.release(runtime=owner.runtime, lineage=dict(owner.lineage, nonce='e'*64))
    assert owner.proxy.barrier.state == 'waiting'


def test_normal_close_is_one_shot_and_durable_failure_retains_owner(tmp_path, monkeypatch):
    root, lineage = seeded_root(tmp_path, monkeypatch)
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    control = helper.InstalledDimensionControl(module, state_root=root, lineage=lineage).install()
    runtime = module.Runtime(module.JobStore(control.seam.path))
    assert runtime.shutdown()
    monkeypatch.setattr(helper.owned, '_write', lambda *a: (_ for _ in ()).throw(OSError('Own close fsync')))
    with pytest.raises(helper.DimensionControlError) as caught:
        control.complete_normal()
    assert caught.value.retained_owner is control
    assert control.runtime is runtime and control.proxy._store._db is None
    assert module.JobStore is JobStore and module.Runtime is Runtime
    assert control.inspect_state()['phase'] == 'failed'
    with pytest.raises(helper.DimensionControlError):
        control.complete_normal()
