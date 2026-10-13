"""Real own Python child/SQLite experiment; Q is synthetic, no SolidWorks."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from solidworks_mcp.jobs import JobStore


spec = importlib.util.spec_from_file_location('_b4_owned_child_tests',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_b4_owned_child_process.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def child_factory(tmp_path):
    children = []

    def create(profile='exit'):
        try:
            child = helper.OwnedSyntheticChild(tmp_path / f'child-{len(children)}', profile=profile)
        except helper.OwnedChildLaunchError as exc:
            children.append(exc.retained_owner)
            raise
        children.append(child)
        return child

    yield create
    for child in children:
        # Never kill/cancel on observation timeout. Every test must return its
        # own child via the fixed protocol or EOF synthetic refusal control.
        if child.process.poll() is None:
            if not child._sent:
                ready = child.await_ready(15)
                assert ready is not None
                child.send_exit_command(ready['command'])
            assert child.observe_exit(15)['process_exit_observed'] is True
        assert child.process.poll() is not None


def finish(child):
    ready = child.await_ready(15)
    assert ready is not None
    child.send_exit_command(ready['command'])
    result = child.observe_exit(15)
    assert result['process_exit_observed'] is True
    return ready, result


def assert_native_false(receipt):
    assert receipt['native_q'] == 'not_run'
    assert receipt['synthetic_cad_free'] is True
    for key in ('accepted', 'native_b4_accepted', 'native_restart_proven',
                'native_dispatch_proven', 'process_stop_authorized', 'cad_cleanup_authorized'):
        assert receipt[key] is False


def test_actual_gate_current_process_exit_is_bound_to_real_os_handle(child_factory):
    child = child_factory()
    ready, result = finish(child)
    assert child.process.pid == ready['identity']['pid']
    assert child.process.returncode == helper.EXIT_CODE == result['exit_code']
    assert result['process_protocol_passed'] is True
    assert result['identity']['start']['ticks'] > 0
    assert len(result['identity']['session_nonce']) == 64
    assert ready['command']['process_identity']['pid'] == child.process.pid
    assert_native_false(result)
    assert not (child.path / 'callback-returned.json').exists()
    assert not (child.path / 'refusal.json').exists()
    intent = helper._read(child.path / 'exit-intent.json')
    assert intent['exit_callback_returned'] is False
    assert intent['process_exit_observed'] is False
    assert intent['process_stop_authorized'] is False
    assert helper._read(child.path / 'parent-exit.json') == result
    # Read-only snapshot before any restart: real process exited with unfinished
    # held finish; no fake terminal row and no SQLite rewrite from observer.
    gate = helper._sibling('verifier_b4_process_exit.py', '_b4_owned_read_tests')
    journal = gate._recovery.read_journal(child.path / 'jobs.sqlite')
    assert journal == helper._read(child.path / 'barrier.json')['journal']
    target = next(row for row in journal if row['request_id'] == 'synthetic_target')
    assert target['status'] == 'running' and target['mutation']['phase'] == 'prepared'


def test_normal_callback_return_and_normal_python_exit_are_not_gate_exit_proof(child_factory):
    child = child_factory('callback_return')
    _, result = finish(child)
    assert result['exit_code'] == 0
    assert result['process_protocol_passed'] is False
    returned = helper._read(child.path / 'callback-returned.json')['receipt']
    assert returned['phase'] == 'test_callback_returned'
    assert returned['exit_callback_returned'] is True
    assert not (child.path / 'exit-callback.json').exists()
    assert_native_false(result)


def test_failed_intent_never_invokes_current_process_exit(child_factory):
    child = child_factory('intent_failure')
    _, result = finish(child)
    assert result['exit_code'] == 66 and not result['process_protocol_passed']
    assert not (child.path / 'exit-intent.json').exists()
    assert not (child.path / 'exit-callback.json').exists()
    refusal = helper._read(child.path / 'refusal.json')
    assert refusal['gate_state'] == 'failed'
    assert 'persistence failure' in refusal['reason']
    assert_native_false(result)
    with pytest.raises(helper.OwnedChildProtocolError, match='one-shot'):
        child.send_exit_command(child._ready['command'])


def test_wait_timeout_retains_live_child_and_does_not_send_or_cancel(child_factory):
    child = child_factory()
    ready = child.await_ready(15)
    result = child.observe_exit(0)
    assert result['phase'] == 'owner_retained'
    assert result['process_exit_observed'] is False
    assert result['exit_code'] is None and not child._sent
    assert child.process.poll() is None
    assert not (child.path / 'exit-intent.json').exists()
    child.send_exit_command(ready['command'])
    assert child.observe_exit(15)['process_protocol_passed'] is True


@pytest.mark.parametrize('field', ['pid', 'incarnation', 'nonce', 'q', 'binding'])
def test_foreign_command_rejected_before_write(child_factory, field):
    child = child_factory()
    ready = child.await_ready(15)
    command = deepcopy(ready['command'])
    if field == 'pid': command['process_identity']['pid'] += 1
    elif field == 'incarnation': command['process_identity']['incarnation'] = 'foreign'
    elif field == 'nonce': command['command_nonce'] = 'foreign'
    elif field == 'q': command['q_sha256'] = 'foreign'
    else: command['binding']['operation_id'] = 'foreign'
    with pytest.raises(helper.OwnedChildProtocolError, match='Foreign'):
        child.send_exit_command(command)
    assert child.process.poll() is None and not child._sent
    assert not (child.path / 'exit-intent.json').exists()
    # Rejected before the child receives any command, not an exit retry.
    child.send_exit_command(ready['command'])
    assert child.observe_exit(15)['process_protocol_passed'] is True


def test_foreign_envelope_is_refused_by_child_before_gate(child_factory):
    child = child_factory()
    ready = child.await_ready(15)
    foreign = deepcopy(child.identity)
    foreign['session_nonce'] = 'foreign'
    child._sent = True
    child.process.stdin.write(json.dumps(dict(scope='b4_owned_synthetic_command_v1',
        identity=foreign, command=ready['command'])) + '\n')
    child.process.stdin.flush()
    child.process.stdin.close()
    result = child.observe_exit(15)
    assert result['exit_code'] == 66 and result['process_protocol_passed'] is False
    assert not (child.path / 'exit-intent.json').exists()
    assert helper._read(child.path / 'refusal.json')['gate_state'] == 'armed'


def test_gate_rejects_foreign_child_command_even_with_valid_envelope(child_factory):
    child = child_factory()
    ready = child.await_ready(15)
    command = deepcopy(ready['command'])
    command['process_identity']['pid'] += 1
    child._sent = True
    child.process.stdin.write(json.dumps(dict(scope='b4_owned_synthetic_command_v1',
        identity=child.identity, command=command)) + '\n')
    child.process.stdin.flush()
    child.process.stdin.close()
    result = child.observe_exit(15)
    assert result['exit_code'] == 66 and not result['process_protocol_passed']
    assert not (child.path / 'exit-intent.json').exists()
    assert helper._read(child.path / 'refusal.json')['gate_state'] == 'failed'


def test_observation_reuses_terminal_receipt_and_does_not_restart(child_factory):
    child = child_factory()
    _, result = finish(child)
    result['identity']['pid'] = -1
    second = child.observe_exit(0)
    assert second['identity']['pid'] == child.process.pid
    assert second == helper._read(child.path / 'parent-exit.json')
    with pytest.raises(helper.OwnedChildProtocolError, match='one-shot'):
        child.send_exit_command(child._ready['command'])


def test_start_identity_change_prevents_command(child_factory):
    child = child_factory()
    ready = child.await_ready(15)
    original = deepcopy(child.start)
    child.start['ticks'] += 1
    with pytest.raises(helper.OwnedChildProtocolError, match='start identity'):
        child.send_exit_command(ready['command'])
    assert not child._sent and child.process.poll() is None
    child.start = original
    child.send_exit_command(ready['command'])
    assert child.observe_exit(15)['process_protocol_passed'] is True


def test_real_sqlite_restart_is_separate_synthetic_experiment(child_factory):
    child = child_factory()
    ready, result = finish(child)
    assert result['process_protocol_passed']
    with_store = JobStore(child.path / 'jobs.sqlite')
    try:
        row = with_store.get(ready['command']['binding']['operation_id'])
        assert row['status'] == 'unknown'
        assert row['error']['code'] == 'runtime_restarted'
        assert row['mutation']['phase'] == 'unresolved'
        assert with_store.mutation_blockers('synthetic_new_epoch', 'synthetic_other')
    finally:
        with_store.close()
    # Actual OS/SQLite behaviour proves only this synthetic process experiment.
    assert_native_false(result)


@pytest.mark.parametrize('profile', ['kill', 'retry', 'native', ['exit'], 73])
def test_no_arbitrary_pid_command_or_profile(tmp_path, profile):
    with pytest.raises(helper.OwnedChildProtocolError, match='Fixed'):
        helper.OwnedSyntheticChild(tmp_path / 'not-created', profile=profile)
    assert not (tmp_path / 'not-created').exists()


def test_existing_directory_not_adopted(tmp_path):
    with pytest.raises(FileExistsError):
        helper.OwnedSyntheticChild(tmp_path)


@pytest.mark.parametrize('timeout', [-1, 61, True, '1'])
def test_invalid_observation_has_no_process_action(child_factory, timeout):
    child = child_factory()
    with pytest.raises(helper.OwnedChildProtocolError, match='Bounded'):
        child.await_ready(timeout)
    with pytest.raises(helper.OwnedChildProtocolError, match='Bounded'):
        child.observe_exit(timeout)
    assert not child._sent


def test_synthetic_q_is_not_external_command_data():
    owner = helper.SyntheticOwnerQ()
    proof = owner.observe_owner_q({'own': 'binding'})
    assert all(obs['receipt'] == {'synthetic_cad_free': True} for obs in proof['evidence'].values())
    owner.admission_closed = False
    with pytest.raises(helper.OwnedChildProtocolError, match='not complete'):
        owner.observe_owner_q({'own': 'binding'})


@pytest.mark.parametrize('change', ['missing_callback', 'foreign_start', 'intent_hash', 'callback_exit_code'])
def test_real_exit_without_complete_bound_receipts_is_not_process_protocol_proof(child_factory, change):
    child = child_factory()
    ready = child.await_ready(15)
    child.send_exit_command(ready['command'])
    assert child.process.wait(15) == helper.EXIT_CODE
    path = child.path / 'exit-callback.json'
    if change == 'missing_callback':
        path.unlink()  # Own synthetic evidence only, after child terminal.
    else:
        callback = helper._read(path)
        if change == 'foreign_start': callback['identity']['start']['ticks'] += 1
        elif change == 'intent_hash': callback['intent_sha256'] = 'foreign'
        else: callback['exit_code'] = 0
        path.write_text(json.dumps(callback), encoding='utf8')
    result = child.observe_exit(0)
    assert result['process_exit_observed'] is True
    assert result['exit_code'] == helper.EXIT_CODE
    assert result['process_protocol_passed'] is False
    assert_native_false(result)


def test_forged_callback_file_cannot_turn_normal_return_into_actual_gate_exit(child_factory):
    child = child_factory('callback_return')
    ready = child.await_ready(15)
    child.send_exit_command(ready['command'])
    assert child.process.wait(15) == 0
    intent = helper._read(child.path / 'exit-intent.json')
    helper._write(child.path / 'exit-callback.json', dict(
        scope='b4_owned_synthetic_exit_callback_v1', identity=child.identity,
        intent_sha256=helper._sha(intent), exit_code=helper.EXIT_CODE))
    result = child.observe_exit(0)
    assert not result['process_protocol_passed']
    assert result['exit_code'] == 0
    assert 'OS exit differs' in result['reason']


@pytest.mark.parametrize('failure', ['start_observation', 'launch_persistence'])
def test_post_popen_failure_retains_exact_original_owner_and_handle(child_factory, monkeypatch, failure):
    original_start, original_write = helper._process_start, helper._write

    def fail_start(pid, handle=None):
        raise OSError('Injected parent start observation failure')

    def fail_write(path, value):
        if Path(path).name == 'parent-launch.json':
            # The original uncertain/partial receipt remains visible; recovery
            # never overwrites or retries this path.
            Path(path).write_text('partial-launch-receipt', encoding='utf8')
            raise OSError('Injected parent launch persistence failure')
        return original_write(path, value)

    monkeypatch.setattr(helper, '_process_start' if failure == 'start_observation' else '_write',
                        fail_start if failure == 'start_observation' else fail_write)
    with pytest.raises(helper.OwnedChildLaunchError) as caught:
        child_factory()
    child = caught.value.retained_owner
    assert child.process.poll() is None
    exact_process = child.process
    assert not child._sent
    assert child.observe_exit(0)['phase'] == 'owner_retained'
    monkeypatch.setattr(helper, '_process_start', original_start)
    monkeypatch.setattr(helper, '_write', original_write)
    identity = child.observe_retained_launch()
    assert child.process is exact_process and identity['pid'] == exact_process.pid
    with pytest.raises(helper.OwnedChildProtocolError, match='one-shot'):
        child.observe_retained_launch()
    ready, result = finish(child)
    assert result['process_protocol_passed'] is True
    assert result['original_launch_failure'] == child._launch_error
    assert ready['identity'] == identity
    assert_native_false(result)
    if failure == 'launch_persistence':
        assert (child.path / 'parent-launch.json').read_text(encoding='utf8') == 'partial-launch-receipt'
