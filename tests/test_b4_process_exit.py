"""Real SQLite/Python finish barrier; injected exit only, no CAD/process exit."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
from threading import Thread

import pytest

from solidworks_mcp.jobs import JobStore


def sibling(filename, name):
    spec = importlib.util.spec_from_file_location(name,
        Path(__file__).resolve().parents[1] / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


finish = sibling('verifier_b4_finish_barrier.py', '_b4_exit_finish_tests')
helper = sibling('verifier_b4_process_exit.py', '_b4_exit_tests')
CONTEXT = dict(document_id='own_part', configuration='Основная', expected_revision='before')
PAYLOAD = dict(arguments={'object_id': 'own_dimension', 'value': 12, 'unit': 'mm'},
               context=CONTEXT, mutates=True)


@pytest.fixture
def waiting(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    history, _ = store.create('history', 'dimension.get', {})
    store.start(history['operation_id'])
    store.finish(history['operation_id'], 'succeeded', result={'value': 10})
    job, _ = store.create('target', 'dimension.set_value', PAYLOAD['arguments'], CONTEXT, mutates=True)
    oid = job['operation_id']
    store.start(oid)
    store.prepare_mutation(oid, connection_epoch='epoch_before', **CONTEXT,
        before_state={'parameter': 10, 'neighbor_dirty': True}, effect_scope='application')
    store.record_mutation_step(oid, name='setter', phase='pending', evidence={'value': 12})
    store.record_mutation_step(oid, name='setter', phase='returned', evidence={'status': 0})
    store.verify_mutation(oid, outcome='committed', evidence={'parameter': 12, 'guard_released': True})
    persisted = []
    barrier = finish.FinishBarrierStore(store, request_id='target', operation='dimension.set_value',
                                      payload=PAYLOAD, persist=persisted.append)
    errors = []

    def hold():
        try:
            barrier.finish(oid, 'succeeded', result={'verified': True, 'parameter': 12})
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=hold, daemon=True)
    worker.start()
    assert barrier.wait_reached(5)
    try:
        yield store, barrier, oid, tmp_path, errors
    finally:
        if barrier.state == 'waiting':
            barrier.release()
        worker.join(5)
        assert not worker.is_alive(), 'Only own pure Python barrier must drain.'
        store.close()


def q_observation(binding):
    # Synthetic trusted dependency for pure tests, never a native receipt.
    return dict(scope='b4_owner_callback_guard_q_v1', proof_id='pure-owner-proof',
        binding=deepcopy(binding), **{key: True for key in helper.TRUE_Q},
        **{key: False for key in helper.FALSE_Q},
        evidence=dict(callback_return={'returned': True, 'native_calls_live': False,
            'native_calls_pending': False, 'receipt': {'pure_callback': 'returned'}},
            guard_completion={'completed': True, 'released': True, 'receipt': {'pure_guard': 'released'}},
            admission={'closed': True, 'queued_cad_calls': False, 'unknown_effects': False,
                       'receipt': {'pure_queue': 'closed'}}))


def gate(waiting, **overrides):
    calls, receipts = [], []
    instance = helper.OwnedChildExitGate(waiting[1], **{
        'observe_owner_q': q_observation, 'persist': receipts.append,
        'exit_callback': calls.append, **overrides})
    return instance, calls, receipts


def test_exact_current_process_command_persists_intent_before_one_callback(waiting):
    store, barrier, oid, path, _ = waiting
    writes, calls, observations = [], [], []

    def persist(receipt):
        assert not calls
        (path / 'exit-intent.json').write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf8')
        writes.append(deepcopy(receipt))

    def observe(binding):
        observations.append(deepcopy(binding))
        return q_observation(binding)

    def injected_exit(receipt):
        assert json.loads((path / 'exit-intent.json').read_text(encoding='utf8')) == receipt
        assert store.get(oid)['status'] == 'running' and barrier.state == 'waiting'
        calls.append(deepcopy(receipt))

    instance, _, _ = gate(waiting, observe_owner_q=observe, persist=persist, exit_callback=injected_exit)
    before = helper._recovery.read_journal(store.path)
    command = instance.issue_command()
    assert command['process_identity']['pid'] == os.getpid()
    assert len(command['process_identity']['incarnation']) == len(command['command_nonce']) == 64
    result = instance.execute(command)
    assert len(writes) == len(calls) == 1 and len(observations) == 3
    assert result['phase'] == 'test_callback_returned' and result['exit_callback_returned'] is True
    assert instance.state == 'callback_returned'
    for key in ('accepted', 'native_b4_accepted', 'native_restart_proven', 'native_dispatch_proven',
                'process_stop_authorized', 'cad_cleanup_authorized', 'process_exit_observed'):
        assert result[key] is False
    assert result['exit_command_validated'] is True
    assert helper._recovery.read_journal(store.path) == before
    assert store.mutation_blockers('new_epoch', 'other_part')
    result['command']['binding']['operation_id'] = 'forged'
    assert instance.receipt['command'] == command
    with pytest.raises(helper.ChildExitGateError, match='one-shot'):
        instance.execute(command)
    with pytest.raises(helper.ChildExitGateError, match='exactly one'):
        instance.issue_command()
    assert len(calls) == 1


@pytest.mark.parametrize('field', sorted(helper.TRUE_Q | helper.FALSE_Q))
@pytest.mark.parametrize('value', [None, 'unknown', 1, 0])
def test_q_requires_strict_completed_native_and_guard_flags(waiting, field, value):
    def observe(binding):
        proof = q_observation(binding)
        proof[field] = value
        return proof
    instance, calls, receipts = gate(waiting, observe_owner_q=observe)
    with pytest.raises(helper.ChildExitGateError):
        instance.issue_command()
    assert instance.state == 'failed' and calls == receipts == []


@pytest.mark.parametrize('field', sorted(helper.TRUE_Q | helper.FALSE_Q))
def test_false_completion_or_live_pending_queued_unknown_blocks(waiting, field):
    def observe(binding):
        proof = q_observation(binding)
        proof[field] = field in helper.FALSE_Q
        return proof
    instance, calls, receipts = gate(waiting, observe_owner_q=observe)
    with pytest.raises(helper.ChildExitGateError):
        instance.issue_command()
    assert not calls and not receipts


@pytest.mark.parametrize('corruption', ['missing', 'extra', 'binding', 'evidence', 'empty_callback', 'proof_id', 'scope'])
def test_separate_owner_q_provenance_contract_not_barrier_flag(waiting, corruption):
    def observe(binding):
        proof = q_observation(binding)
        if corruption == 'missing': proof.pop('guard_completed')
        elif corruption == 'extra': proof['timeout_s'] = 10
        elif corruption == 'binding': proof['binding']['operation_id'] = 'another'
        elif corruption == 'evidence': proof['evidence'].pop('admission')
        elif corruption == 'empty_callback': proof['evidence']['callback_return'] = {}
        elif corruption == 'proof_id': proof['proof_id'] = ''
        elif corruption == 'scope': proof['scope'] = 'client_asserted_q'
        return proof
    instance, calls, _ = gate(waiting, observe_owner_q=observe)
    with pytest.raises(helper.ChildExitGateError): instance.issue_command()
    assert not calls


def test_missing_owner_q_is_rejected_even_with_complete_returned_ledger(waiting):
    instance, calls, _ = gate(waiting, observe_owner_q=lambda binding: None)
    assert waiting[1].receipt['native_quiescence_proven'] is False
    with pytest.raises(helper.ChildExitGateError, match='separate owner Q'):
        instance.issue_command()
    assert not calls


@pytest.mark.parametrize('observation,field,value', [
    ('callback_return', 'returned', False), ('callback_return', 'native_calls_live', True),
    ('callback_return', 'native_calls_pending', True), ('guard_completion', 'completed', None),
    ('guard_completion', 'released', False), ('guard_completion', 'released', 'unknown'),
    ('admission', 'closed', False), ('admission', 'queued_cad_calls', True),
    ('admission', 'unknown_effects', True), ('admission', 'receipt', {}),
])
def test_nested_observations_cannot_hide_unresolved_state_behind_q_flags(waiting, observation, field, value):
    def observe(binding):
        proof = q_observation(binding)
        proof['evidence'][observation][field] = value
        return proof
    instance, calls, _ = gate(waiting, observe_owner_q=observe)
    with pytest.raises(helper.ChildExitGateError, match='observation'):
        instance.issue_command()
    assert not calls


@pytest.mark.parametrize('change', ['pid', 'incarnation', 'nonce', 'journal', 'barrier', 'digest',
                                   'operation', 'request', 'q', 'timeout', 'pid_only'])
def test_foreign_or_modified_command_is_latched_without_exit(waiting, change):
    instance, calls, receipts = gate(waiting)
    command = instance.issue_command()
    if change == 'pid': command['process_identity']['pid'] += 1
    elif change == 'incarnation': command['process_identity']['incarnation'] = 'foreign'
    elif change == 'nonce': command['command_nonce'] = 'foreign'
    elif change in ('journal', 'barrier', 'digest', 'operation', 'request'):
        key = {'journal': 'journal_sha256', 'barrier': 'barrier_sha256', 'digest': 'job_digest',
               'operation': 'operation', 'request': 'request_id'}[change]
        command['binding'][key] = 'changed'
    elif change == 'q': command['q_sha256'] = 'foreign'
    elif change == 'timeout': command['timeout_s'] = 10
    elif change == 'pid_only': command = {'pid': os.getpid()}
    with pytest.raises(helper.ChildExitGateError): instance.execute(command)
    assert instance.state == 'failed' and calls == receipts == []
    with pytest.raises(helper.ChildExitGateError, match='one-shot'): instance.execute(command)


def test_another_gate_same_pid_cannot_adopt_command(waiting):
    first, calls_first, _ = gate(waiting)
    second, calls_second, _ = gate(waiting)
    first_command = first.issue_command()
    second.issue_command()
    with pytest.raises(helper.ChildExitGateError): second.execute(first_command)
    assert not calls_first and not calls_second


@pytest.mark.parametrize('change', ['history', 'queued', 'running', 'unknown'])
def test_whole_journal_work_change_prevents_exit(waiting, change):
    store = waiting[0]
    instance, calls, receipts = gate(waiting)
    command = instance.issue_command()
    if change == 'history':
        with store._lock:
            store._db.execute('UPDATE jobs SET result=? WHERE request_id=?', ('{"value":99}', 'history'))
    else:
        job, _ = store.create('unexpected', 'dimension.get', {})
        if change != 'queued':
            store.start(job['operation_id'])
            if change == 'unknown': store.finish(job['operation_id'], 'unknown')
    with pytest.raises(helper.ChildExitGateError, match='journal changed'):
        instance.execute(command)
    assert calls == receipts == []


@pytest.mark.parametrize('state', ['armed', 'capturing', 'released', 'finished', 'failed'])
def test_non_waiting_barrier_prohibits_exit(waiting, state):
    barrier = waiting[1]
    barrier._state = state
    try:
        instance, calls, _ = gate(waiting)
        with pytest.raises(helper.ChildExitGateError, match='waiting'):
            instance.issue_command()
        assert not calls
    finally:
        barrier._state = 'waiting'


def test_pending_ledger_rejected_even_if_synthetic_q_claims_all_returned(waiting):
    store, barrier, oid, _, _ = waiting
    with store._lock:
        row = store.get(oid)['mutation']['verification']
        row['native_steps'].pop()
        store._db.execute('UPDATE mutations SET verification=? WHERE operation_id=?', (json.dumps(row), oid))
    barrier._receipt['journal'] = helper._recovery.read_journal(store.path)
    instance, calls, _ = gate(waiting)
    with pytest.raises(helper.ChildExitGateError, match='Pending native step'):
        instance.issue_command()
    assert not calls


def test_persistence_failure_latches_and_never_executes_or_retries(waiting):
    attempts = []
    def fail(receipt):
        attempts.append(receipt)
        raise OSError('controlled private receipt failure')
    instance, calls, _ = gate(waiting, persist=fail)
    command = instance.issue_command()
    with pytest.raises(OSError): instance.execute(command)
    with pytest.raises(helper.ChildExitGateError): instance.execute(command)
    assert len(attempts) == 1 and not calls and instance.state == 'failed'


def test_q_changed_after_intent_persisted_prevents_callback(waiting):
    closed = True
    def observe(binding):
        proof = q_observation(binding)
        proof['admission_closed'] = closed
        return proof
    intents = []
    def persist(receipt):
        nonlocal closed
        intents.append(receipt)
        closed = False
    instance, calls, _ = gate(waiting, observe_owner_q=observe, persist=persist)
    command = instance.issue_command()
    with pytest.raises(helper.ChildExitGateError): instance.execute(command)
    assert len(intents) == 1 and not calls and instance.state == 'failed'


def test_release_during_intent_persistence_prevents_exit_callback(waiting):
    barrier = waiting[1]
    def persist(receipt):
        barrier.release()
    instance, calls, _ = gate(waiting, persist=persist)
    command = instance.issue_command()
    with pytest.raises(helper.ChildExitGateError, match='waiting'):
        instance.execute(command)
    assert not calls and instance.state == 'failed'


def test_callback_failure_invoked_once_without_success_or_retry(waiting):
    attempts = []
    def fail(receipt):
        attempts.append(receipt)
        raise OSError('injected callback error')
    instance, _, receipts = gate(waiting, exit_callback=fail)
    command = instance.issue_command()
    with pytest.raises(OSError): instance.execute(command)
    with pytest.raises(helper.ChildExitGateError): instance.execute(command)
    assert len(attempts) == len(receipts) == 1
    assert instance.receipt['exit_callback_returned'] is False
    assert instance.receipt['process_exit_observed'] is False


@pytest.mark.parametrize('callback', ['observe', 'persist', 'exit'])
def test_deferred_callback_work_is_not_executed(waiting, callback):
    async_calls = []
    async def deferred(value):
        async_calls.append(value)
    overrides = {dict(observe='observe_owner_q', persist='persist', exit='exit_callback')[callback]:
                 lambda value: deferred(value)}
    instance, calls, _ = gate(waiting, **overrides)
    with pytest.raises(helper.ChildExitGateError, match='Deferred'):
        command = instance.issue_command()
        instance.execute(command)
    assert not async_calls and not calls and instance.state == 'failed'


def test_pid_change_after_command_issuance_blocks_without_external_pid_api(waiting, monkeypatch):
    instance, calls, _ = gate(waiting)
    command = instance.issue_command()
    own_pid = os.getpid()
    monkeypatch.setattr(helper.os, 'getpid', lambda: own_pid + 1)
    with pytest.raises(helper.ChildExitGateError, match='another process'):
        instance.execute(command)
    assert not calls
