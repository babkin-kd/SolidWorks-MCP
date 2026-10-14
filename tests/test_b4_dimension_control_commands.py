"""Finite own command protocol with actual controller/Runtime; fake CAD only."""
import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import JobStore
from solidworks_mcp.runtime_v2 import Runtime
from test_dimension_domain_v2 import setup
from test_b4_dimension_return import prepared
from test_b4_installed_dimension_control import (
    owner as control_owner, helper as controller_module, seeded_root, no_authority)


spec = importlib.util.spec_from_file_location('_b4_command_tests',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_b4_dimension_control_commands.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def receiver(owner, count=4, **kwargs):
    return helper.DimensionControlCommands(owner.control, command_limit=count,
                                          controller_module=controller_module, **kwargs)


def command(value, sequence, name, arguments=None):
    return dict(scope='b4_dimension_control_command_v1', sequence=sequence, nonce=value.lineage['nonce'],
                lineage=deepcopy(value.lineage), command=name, arguments=arguments or {})


def put(value, sequence, name, arguments=None):
    data = command(value, sequence, name, arguments)
    controller_module.owned._write(value.command_path(sequence), data)
    return data


def arm_args(owner):
    return dict(request_id='command-target', operation='dimension.set_value', payload=deepcopy(owner.payload))


def test_real_controller_commands_drive_arm_explicit_release_and_normal_shutdown(control_owner):
    owner = control_owner
    value = receiver(owner, 5)
    before = controller_module.finished._barrier._read_journal(owner.proxy.path)
    put(value, 1, 'inspect')
    first = value.handle_command()
    assert first['controller_state']['phase'] == 'unarmed'
    assert value.inspect_state()['next_sequence'] == 2
    put(value, 2, 'arm', arm_args(owner))
    armed = value.handle_command()
    assert armed['controller_state']['phase'] == 'armed'
    assert controller_module.finished._barrier._read_journal(owner.proxy.path) == before
    assert owner.prepared.adapter.dimension_writes == []
    job = asyncio.run(owner.runtime.mutate('command-target', 'dimension.set_value', owner.payload['arguments'], timeout_s=0))
    assert owner.proxy.wait_reached(5)
    put(value, 3, 'inspect')
    waiting = value.handle_command()
    assert waiting['controller_state']['barrier_state'] == 'waiting'
    assert waiting['controller_state']['return_observation']['callback_live'] is False
    put(value, 4, 'release')
    released = value.handle_command()
    assert released['controller_state']['phase'] == 'released'
    assert asyncio.run(owner.runtime._runner.wait(job['operation_id'], 5))['status'] == 'succeeded'
    put(value, 5, 'prepare_normal_shutdown')
    prepared_ack = value.handle_command()
    assert prepared_ack['controller_state']['phase'] == 'ready_for_normal_shutdown'
    state = value.inspect_state()
    assert state['closed'] is True and state['fault'] is None and state['next_sequence'] is None
    assert state['attempted'] == state['action_completed'] == state['acknowledged'] == 5
    assert len(owner.prepared.adapter.dimension_writes) == 1
    for seq, ack in enumerate((first, armed, waiting, released, prepared_ack), 1):
        assert controller_module.owned._read(value.ack_path(seq)) == ack
        assert ack['sequence'] == seq and ack['lineage'] == owner.lineage
        no_authority(ack)
    assert owner.runtime.shutdown()
    assert owner.control.complete_normal()['original_factories_restored'] is True
    with pytest.raises(helper.CommandReceiverError, match='closed'):
        value.handle_command()
    assert state['last_ack'] == prepared_ack


def test_metadata_inspect_only_immutable_allowlist_and_empty_journal(tmp_path, monkeypatch):
    root, lineage = seeded_root(tmp_path, monkeypatch)
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    control = controller_module.InstalledDimensionControl(module, state_root=root, lineage=lineage).install()
    runtime = module.Runtime(module.JobStore(control.seam.path))
    assert runtime.shutdown()  # Cold metadata path after original main return.
    allowed = {'inspect'}
    value = helper.DimensionControlCommands(control, command_limit=1, controller_module=controller_module,
                                           allowed_commands=allowed)
    allowed.add('arm')  # Owner caller collection cannot widen captured authority.
    put(value, 1, 'inspect')
    ack = value.handle_command()
    assert ack['controller_state']['target'] is None
    assert runtime._runner is runtime._catalog is runtime._dimensions is None
    assert value.inspect_state()['allowed_commands'] == ['inspect']
    assert value.inspect_state()['closed'] is True
    assert runtime._closed and control.proxy._store._db is None
    assert control.complete_normal()['journal'] == []
    assert not (root / 'callback-return.json').exists() and not (root / 'finish-barrier.json').exists()


@pytest.mark.parametrize('name', ['arm', 'release', 'prepare_normal_shutdown'])
def test_inspect_only_gate_is_checked_before_any_action(control_owner, name):
    value = receiver(control_owner, 2, allowed_commands={'inspect'})
    put(value, 1, name, arm_args(control_owner) if name == 'arm' else {})
    with pytest.raises(helper.CommandReceiverError, match='allowlist'):
        value.handle_command()
    assert value.inspect_state()['action_completed'] == 0
    assert control_owner.control.inspect_state()['phase'] == 'unarmed'
    assert control_owner.control.observer is None and control_owner.proxy.barrier is None


@pytest.mark.parametrize('change', ['sequence', 'bool_sequence', 'nonce', 'lineage', 'unknown_command', 'extra',
                                   'inspect_arguments', 'operation', 'payload_extra', 'arguments_extra',
                                   'context_drift', 'int_value', 'bad_unit'])
def test_foreign_duplicate_reordered_or_changed_typed_command_never_dispatches(control_owner, change):
    value = receiver(control_owner)
    data = command(value, 1, 'arm', arm_args(control_owner))
    if change == 'sequence': data['sequence'] = 2
    elif change == 'bool_sequence': data['sequence'] = True
    elif change == 'nonce': data['nonce'] = 'f'*64
    elif change == 'lineage': data['lineage']['owner_pid'] += 1
    elif change == 'unknown_command': data['command'] = 'kill'
    elif change == 'extra': data['exit'] = True
    elif change == 'inspect_arguments': data.update(command='inspect', arguments={'target': 'foreign'})
    elif change == 'operation': data['arguments']['operation'] = 'document.close'
    elif change == 'payload_extra': data['arguments']['payload']['cancel'] = True
    elif change == 'arguments_extra': data['arguments']['payload']['arguments']['timeout_s'] = 0.
    elif change == 'context_drift': data['arguments']['payload']['context']['object_id'] = 'foreign'
    elif change == 'int_value': data['arguments']['payload']['arguments']['value'] = 12
    else: data['arguments']['payload']['arguments']['unit'] = 'm'
    controller_module.owned._write(value.command_path(1), data)
    before = controller_module.finished._barrier._read_journal(control_owner.proxy.path)
    with pytest.raises(helper.CommandReceiverError) as caught:
        value.handle_command()
    assert caught.value.retained_receiver is value and caught.value.retained_owner is control_owner.control
    assert value.inspect_state()['closed'] is True and value.inspect_state()['action_completed'] == 0
    assert controller_module.finished._barrier._read_journal(control_owner.proxy.path) == before
    assert control_owner.control.observer is None and not control_owner.prepared.adapter.dimension_writes
    assert not value.ack_path(1).exists()
    with pytest.raises(helper.CommandReceiverError):
        value.handle_command()
    assert value.inspect_state()['attempted'] == 1


@pytest.mark.parametrize('failure', ['missing', 'json', 'duplicate_keys', 'oversize'])
def test_read_fault_permanently_closes_without_late_retry(control_owner, failure):
    value = receiver(control_owner)
    path = value.command_path(1)
    if failure == 'json': path.write_text('{', encoding='utf8')
    elif failure == 'duplicate_keys':
        path.write_text('{"scope":"x","scope":"b4_dimension_control_command_v1"}', encoding='utf8')
    elif failure == 'oversize': path.write_text(' '*32769, encoding='utf8')
    with pytest.raises(helper.CommandReceiverError):
        value.handle_command()
    assert value.inspect_state()['action_completed'] == 0
    path.write_text(controller_module._json(command(value, 1, 'inspect')), encoding='utf8')
    with pytest.raises(helper.CommandReceiverError, match='closed|JSON|size|No such|cannot find'):
        value.handle_command()
    assert not value.ack_path(1).exists()


def test_duplicate_sequence_in_next_file_does_not_repeat_previous_arm(control_owner):
    value = receiver(control_owner)
    first = put(value, 1, 'arm', arm_args(control_owner))
    value.handle_command()
    original = control_owner.control.observer, control_owner.proxy.barrier
    controller_module.owned._write(value.command_path(2), first)
    with pytest.raises(helper.CommandReceiverError, match='sequence'):
        value.handle_command()
    assert (control_owner.control.observer, control_owner.proxy.barrier) == original
    assert value.inspect_state()['action_completed'] == value.inspect_state()['acknowledged'] == 1
    assert not value.ack_path(2).exists()


def test_command_file_drift_after_arm_retains_action_and_prohibits_ack_or_retry(control_owner, monkeypatch):
    value = receiver(control_owner)
    put(value, 1, 'arm', arm_args(control_owner))
    original_read = helper._read_command
    reads = []

    def changed_second_read(path):
        reads.append(path)
        if len(reads) == 2:
            data = original_read(path)
            data['arguments']['payload']['arguments']['value'] = 13.
            path.write_text(controller_module._json(data), encoding='utf8')
        return original_read(path)

    monkeypatch.setattr(helper, '_read_command', changed_second_read)
    with pytest.raises(helper.CommandReceiverError, match='changed during action'):
        value.handle_command()
    state = value.inspect_state()
    assert state['action_completed'] == 1 and state['acknowledged'] == 0 and state['closed'] is True
    assert control_owner.control.target['payload']['arguments']['value'] == 12.
    original = control_owner.control.observer, control_owner.proxy.barrier
    with pytest.raises(helper.CommandReceiverError): value.handle_command()
    assert (control_owner.control.observer, control_owner.proxy.barrier) == original
    assert not value.ack_path(1).exists() and not control_owner.prepared.adapter.dimension_writes


@pytest.mark.parametrize('failure', ['before_write', 'fsync', 'exclusive'])
def test_ack_failure_after_original_arm_retains_completed_action_no_retry(control_owner, monkeypatch, failure):
    value = receiver(control_owner)
    put(value, 1, 'arm', arm_args(control_owner))
    original_write = controller_module.owned._write
    calls = []

    def failing_write(path, data):
        calls.append(Path(path).name)
        if failure == 'before_write': raise OSError('Own ack failure')
        if failure == 'exclusive': Path(path).write_text('original-owned-ack', encoding='utf8')
        if failure == 'fsync':
            with monkeypatch.context() as patch:
                patch.setattr(controller_module.owned.os, 'fsync', lambda fd: (_ for _ in ()).throw(OSError('Own ack fsync')))
                return original_write(path, data)
        return original_write(path, data)

    monkeypatch.setattr(controller_module.owned, '_write', failing_write)
    with pytest.raises(helper.CommandReceiverError) as caught:
        value.handle_command()
    assert caught.value.retained_owner is control_owner.control
    state = value.inspect_state()
    assert state['closed'] is True and state['action_completed'] == 1 and state['acknowledged'] == 0
    assert control_owner.control.inspect_state()['phase'] == 'armed'
    original = control_owner.control.observer, control_owner.proxy.barrier
    with pytest.raises(helper.CommandReceiverError): value.handle_command()
    assert (control_owner.control.observer, control_owner.proxy.barrier) == original
    assert calls == [value.ack_path(1).name] and not control_owner.prepared.adapter.dimension_writes
    if failure == 'exclusive': assert value.ack_path(1).read_text(encoding='utf8') == 'original-owned-ack'
    no_authority(state)


def test_original_controller_dispatch_error_has_no_ack_and_no_retry(control_owner):
    value = receiver(control_owner)
    put(value, 1, 'release')  # No original held finish exists.
    with pytest.raises(helper.CommandReceiverError): value.handle_command()
    assert control_owner.control.inspect_state()['phase'] == 'failed'
    assert value.inspect_state()['closed'] is True and value.inspect_state()['action_completed'] == 0
    assert not value.ack_path(1).exists()
    with pytest.raises(helper.CommandReceiverError): value.handle_command()


@pytest.mark.parametrize('change', ['nonce', 'manifest', 'callback', 'factory'])
def test_owner_identity_drift_latches_before_action(control_owner, change):
    value = receiver(control_owner)
    put(value, 1, 'inspect')
    restore = lambda: None
    if change == 'nonce': control_owner.control.lineage['nonce'] = 'e'*64
    elif change == 'manifest':
        path = control_owner.root / 'launch-spec.json'
        data = controller_module.owned._read(path)
        data['nonce'] = 'e'*64
        path.write_text(controller_module._json(data), encoding='utf8')
    elif change == 'callback':
        control_owner.control.arm = lambda **kwargs: pytest.fail('Foreign callback executed')
    else:
        original = control_owner.module.JobStore
        control_owner.module.JobStore = JobStore
        restore = lambda: setattr(control_owner.module, 'JobStore', original)
    try:
        with pytest.raises(helper.CommandReceiverError): value.handle_command()
        assert value.inspect_state()['action_completed'] == 0 and not value.ack_path(1).exists()
    finally: restore()


@pytest.mark.parametrize('limit', [0, 65, True, 1.0, '4'])
def test_nonfinite_limits_rejected_without_installing_any_receiver(control_owner, limit):
    with pytest.raises(helper.CommandReceiverError, match='limit'):
        receiver(control_owner, limit)
    assert control_owner.control.inspect_state()['phase'] == 'unarmed'


def test_foreign_module_or_owner_shape_cannot_be_adopted(control_owner):
    with pytest.raises(helper.CommandReceiverError, match='module'):
        helper.DimensionControlCommands(control_owner.control, command_limit=1,
            controller_module=SimpleNamespace(InstalledDimensionControl=type(control_owner.control)))
    with pytest.raises(helper.CommandReceiverError, match='instance'):
        helper.DimensionControlCommands(SimpleNamespace(lineage=control_owner.lineage), command_limit=1,
            controller_module=controller_module)


def test_preexisting_ack_refused_without_overwriting_original_owned_file(control_owner):
    path = control_owner.root / 'dimension-command-ack-0001.json'
    path.write_text('original-owned-ack', encoding='utf8')
    with pytest.raises(helper.CommandReceiverError, match='adoption'):
        receiver(control_owner)
    assert path.read_text(encoding='utf8') == 'original-owned-ack'


def test_second_receiver_cannot_reset_budget_or_adopt_faulted_original_owner(control_owner):
    value = receiver(control_owner, 1, allowed_commands={'inspect'})
    with pytest.raises(helper.CommandReceiverError, match='one original receiver'):
        receiver(control_owner, 64)
    with pytest.raises(AttributeError): value.limit = 64
    with pytest.raises(AttributeError): value.allowed_commands = frozenset({'arm'})
    with pytest.raises(helper.CommandReceiverError): value.handle_command()  # Own missing command fault.
    with pytest.raises(helper.CommandReceiverError, match='one original receiver'):
        receiver(control_owner, 64)
    assert value.inspect_state()['attempted'] == 1 and value.inspect_state()['closed'] is True
