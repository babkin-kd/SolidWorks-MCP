"""Original command/controller host with artificial CAD and real Runtime/SQLite."""
import asyncio
import importlib.util
import json
import math
from pathlib import Path
from threading import Event
import time
from types import ModuleType, SimpleNamespace

import pytest

from test_b4_dimension_control_commands import (
    arm_args, command, control_owner, controller_module, helper as commands_module,
    receiver,
)
from test_b4_installed_dimension_control import no_authority, seeded_root
from test_b4_dimension_return import prepared
from test_dimension_domain_v2 import setup
from solidworks_mcp.jobs import JobStore
from solidworks_mcp.runtime_v2 import Runtime


spec = importlib.util.spec_from_file_location(
    '_b4_command_host_tests', Path(__file__).resolve().parents[1] /
    'scripts' / 'verifier_b4_dimension_command_host.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def observed(host, predicate, timeout_s=5):
    """Bounded Python-only observation; never submit another controller action."""
    deadline = time.monotonic() + timeout_s
    pause = Event()
    while True:
        state = host.inspect_state()
        if predicate(state):
            return state
        assert time.monotonic() < deadline, state
        pause.wait(.005)


def journal(owner):
    return controller_module.finished._barrier._read_journal(owner.proxy.path)


@pytest.fixture
def host_pair(control_owner):
    value = receiver(control_owner, 2)
    host = helper.DimensionCommandHost(value, command_module=commands_module, poll_interval_s=.001)
    yield value, host
    host.stop_waiting()
    if host._started:
        host._thread.join(5)
        assert not host._thread.is_alive(), host.inspect_state()


def test_atomic_publish_has_exact_complete_utf8_bytes_and_original_receiver(control_owner):
    value = receiver(control_owner, 1)
    data = command(value, 1, 'inspect')
    before = journal(control_owner)
    path = helper.publish_command(control_owner.root, data)
    assert path == value.command_path(1)
    assert path.read_bytes() == json.dumps(
        data, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf8')
    assert not path.with_name(path.name + '.publishing').exists()
    ack = value.handle_command()
    assert ack['command'] == 'inspect' and ack['sequence'] == 1
    assert ack['lineage'] == control_owner.lineage
    no_authority(ack)
    assert journal(control_owner) == before
    assert not control_owner.prepared.adapter.dimension_writes
    assert control_owner.runtime._closed is False


@pytest.mark.parametrize('existing', ['final', 'partial'])
def test_publication_never_overwrites_or_adopts_existing_bytes(control_owner, existing):
    value = receiver(control_owner, 1)
    final = value.command_path(1)
    partial = final.with_name(final.name + '.publishing')
    path = final if existing == 'final' else partial
    path.write_bytes(b'original-owned-diagnostic')
    before = journal(control_owner)
    with pytest.raises(helper.CommandHostError, match='no overwrite/adoption'):
        helper.publish_command(control_owner.root, command(value, 1, 'inspect'))
    assert path.read_bytes() == b'original-owned-diagnostic'
    assert not (partial if existing == 'final' else final).exists()
    assert journal(control_owner) == before
    assert value.inspect_state()['attempted'] == 0


@pytest.mark.parametrize('failure', ['fsync', 'rename', 'race'])
def test_publication_failure_retains_complete_partial_and_never_replaces_racing_final(
        control_owner, monkeypatch, failure):
    value = receiver(control_owner, 1)
    data = command(value, 1, 'inspect')
    path = value.command_path(1)
    partial = path.with_name(path.name + '.publishing')
    raw = json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf8')
    before = journal(control_owner)
    if failure == 'fsync':
        def failed_fsync(fd):
            raise OSError('Own test fsync failure')
        monkeypatch.setattr(helper.os, 'fsync', failed_fsync)
    else:
        publish_name = 'rename' if helper.os.name == 'nt' else 'link'
        original_publish = getattr(helper.os, publish_name)

        def failed_publish(source, destination):
            assert Path(source).read_bytes() == raw
            if failure == 'race':
                Path(destination).write_bytes(b'original-racing-command')
                return original_publish(source, destination)
            raise OSError('Own test publication failure')

        monkeypatch.setattr(helper.os, publish_name, failed_publish)
    with pytest.raises(OSError):
        helper.publish_command(control_owner.root, data)
    assert partial.read_bytes() == raw
    if failure == 'race':
        assert path.read_bytes() == b'original-racing-command'
    else:
        assert not path.exists()
    assert journal(control_owner) == before
    assert value.inspect_state()['attempted'] == 0
    assert not control_owner.prepared.adapter.dimension_writes


@pytest.mark.parametrize('change', ['boolean_sequence', 'zero', 'over_budget', 'root',
                                   'lineage_nonce', 'scope', 'extra', 'oversize', 'nan'])
def test_malformed_publication_refuses_before_creating_any_command(control_owner, change):
    value = receiver(control_owner, 1)
    data = command(value, 1, 'inspect')
    if change == 'boolean_sequence':
        data['sequence'] = True
    elif change == 'zero':
        data['sequence'] = 0
    elif change == 'over_budget':
        data['sequence'] = 65
    elif change == 'root':
        data['lineage']['state_root'] = str(control_owner.root.parent)
    elif change == 'lineage_nonce':
        data['lineage']['nonce'] = 'e' * 64
    elif change == 'scope':
        data['scope'] = 'foreign'
    elif change == 'extra':
        data['accepted'] = True
    elif change == 'oversize':
        data['arguments'] = {'diagnostic': 'x' * 32769}
    else:
        data['arguments'] = {'diagnostic': math.nan}
    with pytest.raises((helper.CommandHostError, ValueError)):
        helper.publish_command(control_owner.root, data)
    assert list(control_owner.root.glob('dimension-command-*')) == []
    assert value.inspect_state()['attempted'] == 0


def test_failed_partial_write_remains_diagnostic_and_host_does_not_read_it(
        control_owner, host_pair, monkeypatch):
    value, host = host_pair
    data = command(value, 1, 'inspect')
    final = value.command_path(1)
    partial = final.with_name(final.name + '.publishing')
    raw = json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf8')
    original_open = Path.open

    class FailedWrite:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def write(self, value):
            self.stream.write(value[:17])
            self.stream.flush()
            raise OSError('Own incomplete command write')

        def __exit__(self, *args):
            self.stream.close()

    def broken_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return FailedWrite(stream) if path == partial and args == ('xb',) else stream

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', broken_open)
        with pytest.raises(OSError, match='incomplete command write'):
            helper.publish_command(control_owner.root, data)
    assert partial.read_bytes() == raw[:17] and not final.exists()
    host.start()
    state = observed(host, lambda state: state['receiver_state'] is not None)
    assert state['phase'] == 'waiting' and state['fault'] is None
    assert host.wait(.01)['completed_commands'] == 0
    assert value.inspect_state()['attempted'] == 0
    assert not value.ack_path(1).exists()
    assert partial.read_bytes() == raw[:17]
    no_authority(state)


def test_host_handles_inspect_with_original_runtime_open_and_budget_finishes_exactly_once(
        control_owner, host_pair):
    value, host = host_pair
    before = journal(control_owner)
    original = (control_owner.control.runtime, control_owner.control.proxy,
                control_owner.runtime._runner, control_owner.runtime._dimensions)
    no_authority(host.inspect_state())
    assert host.start() is host
    with pytest.raises(helper.CommandHostError, match='starts once'):
        host.start()
    helper.publish_command(control_owner.root, command(value, 1, 'inspect'))
    first = observed(host, lambda state: state['completed_commands'] == 1)
    assert first['phase'] == 'waiting' and first['action_live'] is False
    assert value.inspect_state()['next_sequence'] == 2
    # A valid publication outside this receiver's two-command budget is never
    # consumed after its original finite limit completes.
    helper.publish_command(control_owner.root, command(value, 3, 'inspect'))
    helper.publish_command(control_owner.root, command(value, 2, 'inspect'))
    state = host.wait(5)
    assert state['phase'] == 'completed' and state['fault'] is None
    assert state['completed_commands'] == 2 and state['action_live'] is False
    assert state['runtime_open_at_last_action'] is True
    assert state['thread_return_observed'] is True
    received = value.inspect_state()
    assert received['closed'] is True
    assert received['attempted'] == received['action_completed'] == received['acknowledged'] == 2
    for sequence in (1, 2):
        ack = controller_module.owned._read(value.ack_path(sequence))
        assert ack['sequence'] == sequence and ack['lineage'] == control_owner.lineage
        no_authority(ack)
    assert original == (control_owner.control.runtime, control_owner.control.proxy,
                        control_owner.runtime._runner, control_owner.runtime._dimensions)
    assert control_owner.runtime._closed is False
    assert control_owner.proxy._store._db is not None
    assert not (control_owner.root / 'dimension-command-ack-0003.json').exists()
    assert journal(control_owner) == before
    assert not control_owner.prepared.adapter.dimension_writes
    no_authority(state)
    detached = host.inspect_state()
    detached['lineage']['nonce'] = 'f' * 64
    assert host.inspect_state()['lineage'] == control_owner.lineage


def test_missing_input_is_waiting_observation_without_attempt_failure_or_dispatch(control_owner, host_pair):
    value, host = host_pair
    before = journal(control_owner)
    host.start()
    state = observed(host, lambda state: state['receiver_state'] is not None)
    assert state['phase'] == 'waiting' and state['fault'] is None
    assert state['receiver_state']['attempted'] == 0
    assert state['runtime_open_at_last_action'] is None
    assert state['thread_return_observed'] is False
    assert host.wait(.01)['phase'] == 'waiting'
    assert value.inspect_state()['closed'] is False
    assert value.inspect_state()['attempted'] == 0
    assert journal(control_owner) == before
    assert list(control_owner.root.glob('dimension-command-ack-*')) == []
    assert not control_owner.prepared.adapter.dimension_writes
    no_authority(state)
    host.stop_waiting()
    stopped = host.wait(5)
    assert stopped['phase'] == 'stopped_incomplete' and stopped['fault'] is None
    assert stopped['completed_commands'] == 0
    assert stopped['thread_return_observed'] is True
    no_authority(stopped)
    with pytest.raises(helper.CommandHostError, match='starts once'):
        host.start()


def test_stop_waiting_does_not_interrupt_entered_original_controller_inspect(control_owner, host_pair):
    value, host = host_pair
    before = journal(control_owner)
    helper.publish_command(control_owner.root, command(value, 1, 'inspect'))
    # Hold only the actual pure controller RLock. Its unmodified inspect action
    # must enter the receiver and wait for this lock, then return normally.
    with control_owner.control._lock:
        host.start()
        entered = observed(host, lambda state: state['action_live'] is True)
        assert entered['phase'] == 'executing'
        stopped = host.stop_waiting()
        assert stopped['action_live'] is True and stopped['phase'] == 'executing'
        assert not host._done.is_set()
        assert stopped['thread_return_observed'] is False
        assert host.wait(0)['thread_return_observed'] is False
        assert not value.ack_path(1).exists()
        no_authority(stopped)
    final = host.wait(5)
    assert final['phase'] == 'stopped_incomplete' and final['fault'] is None
    assert final['action_live'] is False and final['completed_commands'] == 1
    assert final['runtime_open_at_last_action'] is True
    assert final['thread_return_observed'] is True
    assert value.inspect_state()['attempted'] == value.inspect_state()['acknowledged'] == 1
    ack = controller_module.owned._read(value.ack_path(1))
    assert ack['result']['phase'] == 'unarmed'
    no_authority(ack)
    assert not value.ack_path(2).exists()
    assert control_owner.runtime._closed is False
    assert journal(control_owner) == before
    assert not control_owner.prepared.adapter.dimension_writes


def test_second_host_cannot_adopt_or_restart_original_receiver(host_pair):
    value, original = host_pair
    with pytest.raises(helper.CommandHostError, match='One original host'):
        helper.DimensionCommandHost(value, command_module=commands_module)
    assert value._dimension_command_host is original
    assert original.inspect_state()['phase'] == 'new'


def test_python_thread_start_failure_latches_no_restart_or_action(control_owner, monkeypatch):
    value = receiver(control_owner, 1)
    host = helper.DimensionCommandHost(value, command_module=commands_module)

    def failed_start():
        raise OSError('Own Python thread start failure')

    monkeypatch.setattr(host._thread, 'start', failed_start)
    with pytest.raises(OSError, match='thread start failure'):
        host.start()
    state = host.wait(0)
    assert state['phase'] == 'fault' and 'OSError' in state['fault']
    assert state['completed_commands'] == 0 and state['action_live'] is False
    assert host._done.is_set() and not host._thread.is_alive()
    assert value.inspect_state()['attempted'] == 0
    with pytest.raises(helper.CommandHostError, match='starts once'):
        host.start()
    no_authority(state)


def test_existing_input_waits_for_original_runtime_then_inspects_open_runtime(tmp_path, monkeypatch):
    root, lineage = seeded_root(tmp_path, monkeypatch)
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    control = controller_module.InstalledDimensionControl(
        module, state_root=root, lineage=lineage).install()
    value = commands_module.DimensionControlCommands(
        control, command_limit=1, controller_module=controller_module, allowed_commands={'inspect'})
    host = helper.DimensionCommandHost(value, command_module=commands_module, poll_interval_s=.001)
    runtime = None
    try:
        helper.publish_command(root, command(value, 1, 'inspect'))
        host.start()
        state = observed(host, lambda state: state['receiver_state'] is not None)
        assert state['phase'] == 'waiting' and state['fault'] is None
        assert control.runtime is None and value.inspect_state()['attempted'] == 0
        assert host.wait(.01)['completed_commands'] == 0
        assert state['runtime_open_at_last_action'] is None
        runtime = module.Runtime(module.JobStore(control.seam.path))
        completed = host.wait(5)
        assert completed['phase'] == 'completed' and completed['fault'] is None
        assert completed['completed_commands'] == 1
        assert completed['runtime_open_at_last_action'] is True
        assert completed['thread_return_observed'] is True
        assert runtime is control.runtime and runtime._closed is False
        assert runtime._runner is runtime._catalog is runtime._dimensions is None
        assert controller_module.finished._barrier._read_journal(control.proxy.path) == []
        ack = controller_module.owned._read(value.ack_path(1))
        assert ack['controller_state']['target'] is None
        no_authority(ack)
        no_authority(completed)
    finally:
        host.stop_waiting()
        if host._started:
            host._thread.join(5)
            assert not host._thread.is_alive()
        if runtime is not None and not runtime._closed:
            assert runtime.shutdown()
        if control.seam._installed:
            control.seam.uninstall()


@pytest.mark.parametrize('interval', [True, 0, .0001, .2, math.inf, math.nan, '0.01'])
def test_invalid_poll_interval_has_no_host_binding(control_owner, interval):
    value = receiver(control_owner, 1)
    with pytest.raises(helper.CommandHostError, match='Finite wait interval'):
        helper.DimensionCommandHost(value, command_module=commands_module, poll_interval_s=interval)
    assert not hasattr(value, '_dimension_command_host')
    assert value.inspect_state()['attempted'] == 0


@pytest.mark.parametrize('timeout', [True, -1, 61, math.inf, math.nan, '0'])
def test_invalid_wait_is_observation_error_without_start_or_receiver_attempt(host_pair, timeout):
    value, host = host_pair
    with pytest.raises(helper.CommandHostError, match='Bounded observation wait'):
        host.wait(timeout)
    assert host.inspect_state()['phase'] == 'new'
    assert value.inspect_state()['attempted'] == 0


@pytest.mark.parametrize('change', ['shape_module', 'foreign_path', 'implementation', 'receiver_shape'])
def test_nonoriginal_module_receiver_or_implementation_is_rejected_at_construction(
        control_owner, monkeypatch, change):
    value = receiver(control_owner, 1)
    module = commands_module
    if change == 'shape_module':
        module = SimpleNamespace(__file__=commands_module.__file__, DimensionControlCommands=type(value))
    elif change == 'foreign_path':
        module = ModuleType('foreign_receiver')
        module.__file__ = str(control_owner.root / 'foreign.py')
        module.DimensionControlCommands = type(value)
    elif change == 'implementation':
        monkeypatch.setattr(commands_module.DimensionControlCommands, 'handle_command',
                            lambda self: pytest.fail('Foreign receiver must not dispatch'))
    else:
        value = SimpleNamespace(lineage=control_owner.lineage)
    with pytest.raises(helper.CommandHostError, match='module|implementation|receiver'):
        helper.DimensionCommandHost(value, command_module=module)
    assert not hasattr(value, '_dimension_command_host')


@pytest.mark.parametrize('change', ['receiver_lineage', 'owner_lineage', 'manifest', 'host_binding'])
def test_original_lineage_and_host_binding_drift_fault_before_action(control_owner, host_pair, change):
    value, host = host_pair
    before = journal(control_owner)
    if change == 'receiver_lineage':
        value.lineage['nonce'] = 'e' * 64
    elif change == 'owner_lineage':
        control_owner.control.lineage['nonce'] = 'e' * 64
    elif change == 'manifest':
        path = control_owner.root / 'launch-spec.json'
        manifest = controller_module.owned._read(path)
        manifest['nonce'] = 'e' * 64
        path.write_text(controller_module._json(manifest), encoding='utf8')
    else:
        value._dimension_command_host = object()
    host.start()
    state = host.wait(5)
    assert state['phase'] == 'fault' and state['fault']
    assert state['thread_return_observed'] is True
    assert state['action_live'] is False and state['completed_commands'] == 0
    assert value.inspect_state()['attempted'] == 0
    assert not value.ack_path(1).exists()
    assert journal(control_owner) == before
    assert not control_owner.prepared.adapter.dimension_writes
    no_authority(state)


@pytest.mark.parametrize('change', ['budget', 'allowlist', 'module_path', 'receiver_class',
                                   'receiver_implementation', 'instance_callback'])
def test_postconstruction_frozen_budget_and_receiver_module_drift_must_fault_before_dispatch(
        control_owner, host_pair, monkeypatch, change):
    value, host = host_pair
    before = journal(control_owner)
    helper.publish_command(control_owner.root, command(value, 1, 'inspect'))
    if change == 'budget':
        value._limit = 3
    elif change == 'allowlist':
        value._allowed_commands = frozenset({'inspect'})
    elif change == 'module_path':
        monkeypatch.setattr(commands_module, '__file__', str(control_owner.root / 'foreign.py'))
    elif change == 'receiver_class':
        monkeypatch.setattr(commands_module, 'DimensionControlCommands', type('ForeignReceiver', (), {}))
    elif change == 'receiver_implementation':
        monkeypatch.setattr(commands_module.DimensionControlCommands, 'handle_command',
                            lambda self: pytest.fail('Changed receiver implementation entered action'))
    else:
        value.handle_command = lambda: pytest.fail('Changed instance callback entered action')
    host.start()
    state = observed(host, lambda state: state['phase'] == 'fault' or state['completed_commands'] > 0)
    assert state['phase'] == 'fault' and state['completed_commands'] == 0
    assert value.inspect_state()['attempted'] == 0
    assert not value.ack_path(1).exists()
    assert journal(control_owner) == before
    assert not control_owner.prepared.adapter.dimension_writes
    no_authority(state)


def test_invalid_entered_command_faults_once_without_ack_or_retry(control_owner, host_pair):
    value, host = host_pair
    before = journal(control_owner)
    helper.publish_command(control_owner.root, command(value, 1, 'inspect', {'foreign': True}))
    host.start()
    state = host.wait(5)
    assert state['phase'] == 'fault' and state['fault']
    assert state['thread_return_observed'] is True
    assert state['completed_commands'] == 0 and state['action_live'] is False
    receiver_state = value.inspect_state()
    assert receiver_state['closed'] is True and receiver_state['attempted'] == 1
    assert receiver_state['action_completed'] == receiver_state['acknowledged'] == 0
    assert not value.ack_path(1).exists()
    assert journal(control_owner) == before
    assert control_owner.runtime._closed is False
    assert not control_owner.prepared.adapter.dimension_writes
    with pytest.raises(helper.CommandHostError, match='starts once'):
        host.start()
    no_authority(state)


def test_original_host_atomic_arm_domain_mutation_held_finish_release_and_normal_close(control_owner):
    """Source-only full original user control chain; artificial CAD is not native Q."""
    owner = control_owner
    value = receiver(owner, 3)
    host = helper.DimensionCommandHost(value, command_module=commands_module, poll_interval_s=.001)
    runtime, proxy, control = owner.runtime, owner.proxy, owner.control
    original = (runtime._runner, runtime._catalog, runtime._dimensions,
                proxy._store, control.seam, owner.prepared.adapter)
    original_factories = control.seam._original_store, control.seam._original_runtime
    before = journal(owner)
    assert len(before) == 2 and all(row['status'] == 'succeeded' for row in before)
    arm_arguments = arm_args(owner)
    try:
        helper.publish_command(owner.root, command(value, 1, 'arm', arm_arguments))
        host.start()
        armed = observed(host, lambda state: state['completed_commands'] == 1 or state['phase'] == 'fault')
        assert armed['phase'] == 'waiting' and armed['fault'] is None
        assert armed['runtime_open_at_last_action'] is True
        assert control.inspect_state()['phase'] == 'armed'
        assert journal(owner) == before and owner.prepared.adapter.dimension_writes == []
        arm_ack = controller_module.owned._read(value.ack_path(1))
        assert arm_ack['command'] == 'arm' and arm_ack['arguments'] == arm_arguments
        no_authority(arm_ack)
        observer, barrier = control.observer, proxy.barrier

        job = asyncio.run(runtime.mutate(arm_arguments['request_id'], 'dimension.set_value',
                                         owner.payload['arguments'], timeout_s=0))
        assert proxy.wait_reached(5), control.inspect_state()
        held = control.inspect_state()
        callback = controller_module.owned._read(owner.root / 'callback-return.json')
        finish = controller_module.owned._read(owner.root / 'finish-barrier.json')
        held_journal = journal(owner)
        assert held['barrier_state'] == 'waiting'
        assert held['return_observation']['callback_live'] is False
        assert held['return_observation']['persisted'] is True
        assert callback['journal'] == finish['journal'] == held_journal
        assert held_journal[:-1] == before and len(held_journal) == 3
        assert held_journal[-1]['operation_id'] == job['operation_id']
        assert held_journal[-1]['status'] == 'running'
        assert held_journal[-1]['mutation']['phase'] == 'prepared'
        assert callback['original_receipt']['operation_id'] == finish['original_receipt']['operation_id'] == job['operation_id']
        assert callback['original_receipt']['return_result'] == finish['original_receipt']['return_result']
        assert callback['lineage'] == finish['lineage'] == owner.lineage
        assert callback['target'] == finish['target'] == control.target
        assert held['receipts'] == dict(callback=callback, finish=finish)
        assert len(owner.prepared.adapter.dimension_writes) == 1
        assert owner.prepared.application.CommandInProgress is False
        assert control.runtime is runtime and control.proxy is proxy
        assert original == (runtime._runner, runtime._catalog, runtime._dimensions,
                            proxy._store, control.seam, owner.prepared.adapter)
        assert control.observer is observer and proxy.barrier is barrier
        for state in (armed, held, callback, finish):
            no_authority(state)

        helper.publish_command(owner.root, command(value, 2, 'release'))
        released = observed(host, lambda state: state['completed_commands'] == 2 or state['phase'] == 'fault')
        assert released['phase'] == 'waiting' and released['fault'] is None
        release_ack = controller_module.owned._read(value.ack_path(2))
        assert release_ack['command'] == 'release'
        final = asyncio.run(runtime._runner.wait(job['operation_id'], 5))
        assert final['status'] == 'succeeded' and final['mutation']['phase'] == 'committed'
        assert final['result']['verified'] is True
        terminal_journal = journal(owner)
        assert terminal_journal[:-1] == before and len(terminal_journal) == 3
        assert terminal_journal[-1]['status'] == 'succeeded'
        assert terminal_journal[-1]['mutation']['phase'] == 'committed'
        assert proxy.get(job['operation_id']) == final
        assert barrier.state == 'finished' and control.observer is observer and proxy.barrier is barrier

        # Repeating the original request returns the exact durable outcome and
        # cannot execute a second artificial native setter or add a journal row.
        replay = asyncio.run(runtime.mutate(arm_arguments['request_id'], 'dimension.set_value',
                                            owner.payload['arguments'], timeout_s=5))
        assert replay == final and journal(owner) == terminal_journal
        assert len(owner.prepared.adapter.dimension_writes) == 1
        assert controller_module.owned._read(owner.root / 'callback-return.json') == callback
        assert controller_module.owned._read(owner.root / 'finish-barrier.json') == finish
        assert original == (runtime._runner, runtime._catalog, runtime._dimensions,
                            proxy._store, control.seam, owner.prepared.adapter)
        no_authority(released)
        no_authority(release_ack)

        helper.publish_command(owner.root, command(value, 3, 'prepare_normal_shutdown'))
        completed = host.wait(5)
        assert completed['phase'] == 'completed' and completed['fault'] is None
        assert completed['completed_commands'] == 3 and completed['action_live'] is False
        assert completed['runtime_open_at_last_action'] is True
        assert completed['thread_return_observed'] is True and not host._thread.is_alive()
        receiver_state = value.inspect_state()
        assert receiver_state['closed'] is True and receiver_state['fault'] is None
        assert receiver_state['attempted'] == receiver_state['action_completed'] == receiver_state['acknowledged'] == 3
        assert control.inspect_state()['phase'] == 'ready_for_normal_shutdown'
        assert runtime._closed is False and control.runtime is runtime and control.proxy is proxy
        shutdown_ack = controller_module.owned._read(value.ack_path(3))
        assert shutdown_ack['command'] == 'prepare_normal_shutdown'
        for state in (completed, receiver_state, shutdown_ack):
            no_authority(state)

        assert runtime.shutdown() is True
        closed = control.complete_normal()
        assert closed['journal'] == terminal_journal
        assert closed['original_factories_restored'] is True
        assert owner.module.JobStore is original_factories[0]
        assert owner.module.Runtime is original_factories[1]
        assert control.runtime is runtime and control.proxy is proxy
        assert runtime._closed is True and proxy._store._db is None
        assert control.inspect_state()['phase'] == 'closed'
        assert len(owner.prepared.adapter.dimension_writes) == 1
        assert controller_module.owned._read(owner.root / 'dimension-control-closed.json') == closed
        assert controller_module.owned._read(owner.root / 'callback-return.json') == callback
        assert controller_module.owned._read(owner.root / 'finish-barrier.json') == finish
        no_authority(closed)
    finally:
        host.stop_waiting()
        if host._started:
            host._thread.join(5)
            assert not host._thread.is_alive(), host.inspect_state()
