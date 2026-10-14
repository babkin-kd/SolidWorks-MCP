"""Test-only own-child exit command gate; no process termination implementation.

The native owner must supply a synchronous trusted Q observer and exit callback.
The observer is a harness dependency, never evidence supplied by an MCP client.
This gate binds its live observations to the real FinishBarrierStore receipt,
but cannot establish that an observer tells the truth about COM. Pure acceptance
does not authorize native process stop, restart, dispatch or fixture cleanup.
There is deliberately no os._exit, kill, terminate, timeout or retry path.
"""
from copy import deepcopy
import hashlib
import importlib.util
import inspect
import os
from pathlib import Path
import secrets
from threading import Lock

from solidworks_mcp.jobs import _json


_spec = importlib.util.spec_from_file_location('_b4_exit_recovery',
    Path(__file__).with_name('verifier_b4_recovery.py'))
_recovery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recovery)

TRUE_Q = frozenset(('native_callback_returned', 'native_calls_returned',
                    'guard_completed', 'admission_closed'))
FALSE_Q = frozenset(('native_calls_live', 'native_calls_pending',
                     'queued_cad_calls', 'unknown_effects'))
Q_KEYS = frozenset(('scope', 'proof_id', 'binding', 'evidence')) | TRUE_Q | FALSE_Q
COMMAND_KEYS = frozenset(('scope', 'process_identity', 'command_nonce',
                          'binding', 'q_sha256'))
RECEIPT_KEYS = frozenset(('scope', 'journal', 'operation_id', 'return_result',
    'python_finish_intercepted', 'terminal_finish_called', 'native_b4_accepted',
    'process_stop_authorized', 'native_quiescence_proven', 'cad_cleanup_authorized'))


class ChildExitGateError(RuntimeError):
    """No exit callback is authorized; retain the held journal and fixtures."""


def _require(condition, message):
    if not condition:
        raise ChildExitGateError(message)


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _sync(function, *arguments):
    value = function(*arguments)
    if inspect.isawaitable(value) or inspect.isgenerator(value) or inspect.isasyncgen(value):
        if inspect.iscoroutine(value) or inspect.isgenerator(value):
            value.close()
        raise ChildExitGateError('Deferred callbacks cannot authorize an exit.')
    return value


def validate_owner_q(proof, binding):
    """Validate the finite owner observer contract, not truth of native evidence.

    This schema belongs to this helper. It is NOT a FinishBarrierStore field.
    A trusted native harness must observe complete callback/guard completion,
    close admission, and keep it closed through the injected exit callback.
    """
    _require(type(proof) is dict and set(proof) == Q_KEYS,
             'Complete separate owner Q proof required.')
    _require(proof['scope'] == 'b4_owner_callback_guard_q_v1'
             and type(proof['proof_id']) is str and bool(proof['proof_id']),
             'Exact owner Q scope and proof identity required.')
    _require(_json(proof['binding']) == _json(binding), 'Owner Q binding changed.')
    _require(all(proof[key] is True for key in TRUE_Q)
             and all(proof[key] is False for key in FALSE_Q),
             'Callback/guard/admission completion and no live/pending/queued/unknown effects required.')
    evidence = proof['evidence']
    _require(type(evidence) is dict and set(evidence) ==
             {'callback_return', 'guard_completion', 'admission'}, 'Complete owner Q evidence required.')
    _require(all(type(value) is dict and bool(value) for value in evidence.values()),
             'Nonempty actual callback, guard and admission observations required.')
    schemas = {
        'callback_return': ({'returned', 'native_calls_live', 'native_calls_pending', 'receipt'},
                            {'returned'}, {'native_calls_live', 'native_calls_pending'}),
        'guard_completion': ({'completed', 'released', 'receipt'}, {'completed', 'released'}, set()),
        'admission': ({'closed', 'queued_cad_calls', 'unknown_effects', 'receipt'},
                      {'closed'}, {'queued_cad_calls', 'unknown_effects'}),
    }
    for name, (keys, true_keys, false_keys) in schemas.items():
        observation = evidence[name]
        _require(set(observation) == keys
                 and all(observation[key] is True for key in true_keys)
                 and all(observation[key] is False for key in false_keys)
                 and type(observation['receipt']) is dict and bool(observation['receipt']),
                 'Actual callback/guard/admission observation is incomplete or unresolved.')
    _json(proof)  # Finite JSON only; no process/CAD handles or non-finite values.


def validate_exit_command(command, *, expected_command, binding, owner_q_proof):
    """Pure exact command validation; never executes a process operation."""
    _require(type(command) is dict and set(command) == COMMAND_KEYS,
             'Exact one-shot command schema required; timeout/PID-only commands are unsupported.')
    _require(command['scope'] == 'b4_owned_child_exit_command_v1'
             and _json(command) == _json(expected_command),
             'Own process identity, nonce, barrier/journal or owner Q binding changed.')
    _require(_json(command['binding']) == _json(binding), 'Live barrier/journal binding changed.')
    validate_owner_q(owner_q_proof, binding)
    _require(command['q_sha256'] == _digest(owner_q_proof), 'Live owner Q proof changed.')
    return dict(accepted=False, exit_command_validated=True, native_b4_accepted=False,
                native_restart_proven=False, native_dispatch_proven=False,
                process_stop_authorized=False, cad_cleanup_authorized=False)


class OwnedChildExitGate:
    """Bind one exact waiting finish to a current-process injected exit callback.

    No external PID/identity is accepted by the constructor. PID plus a fresh
    unpredictable incarnation token identify this gate in its own child; a new
    instance cannot reuse a command even when Windows reuses a PID. Command
    nonce is a private capability, keep commands/receipts outside public Git.

    ``observe_owner_q(binding)`` is called at issuance AND immediately before
    exit intent persistence, and must return the same detached owner proof.
    ``persist`` must durably complete synchronously. ``exit_callback(receipt)``
    is invoked once, only after that intent is persisted. A normal callback
    return is recorded as a test callback return, never as process exit proof.
    The native harness must own exclusive admission and barrier release during
    this sequence; flags in a client-provided dict are not that harness.
    """

    def __init__(self, barrier, *, observe_owner_q, persist, exit_callback):
        for function in (observe_owner_q, persist, exit_callback):
            _require(callable(function) and not inspect.iscoroutinefunction(function)
                     and not inspect.isgeneratorfunction(function)
                     and not inspect.isasyncgenfunction(function), 'Synchronous owner callbacks required.')
        self._barrier = barrier
        self._observe_owner_q = observe_owner_q
        self._persist = persist
        self._exit = exit_callback
        self._identity = dict(pid=os.getpid(), incarnation=secrets.token_hex(32))
        self._nonce = secrets.token_hex(32)
        self._lock = Lock()
        self._state = 'new'
        self._command = None
        self._receipt = None

    @property
    def state(self):
        with self._lock:
            return self._state

    @property
    def receipt(self):
        with self._lock:
            return deepcopy(self._receipt)

    def _binding(self):
        _require(os.getpid() == self._identity['pid'], 'Gate moved to another process.')
        barrier = self._barrier
        _require(barrier.state == 'waiting' and barrier.wait_reached(0) is True,
                 'Persisted waiting FinishBarrierStore required.')
        receipt = barrier.receipt
        _require(type(receipt) is dict and set(receipt) == RECEIPT_KEYS
                 and receipt['scope'] == 'b4_python_finish_barrier_v1'
                 and receipt['python_finish_intercepted'] is True,
                 'Real complete Python finish barrier receipt required.')
        _require(all(receipt[key] is False for key in ('terminal_finish_called',
            'native_b4_accepted', 'process_stop_authorized', 'native_quiescence_proven',
            'cad_cleanup_authorized')), 'Barrier native/permission flags must remain false.')
        rows = _recovery.read_journal(barrier.path)
        _require(_json(rows) == _json(receipt['journal']), 'Complete held journal changed.')
        indexed = _recovery._rows(rows)
        _require(all(row['status'] not in ('queued', 'unknown') for row in rows),
                 'Queued or unknown journal work prohibits exit.')
        oid = receipt['operation_id']
        _require(oid in indexed and all(row['status'] != 'running' or row['operation_id'] == oid
                                       for row in rows), 'Another running job prohibits exit.')
        _require(all(row['operation_id'] == oid or row['mutation'] is None
                     or row['mutation']['phase'] not in ('prepared', 'unresolved')
                     for row in rows), 'Another unresolved mutation prohibits exit.')
        row = indexed[oid]
        mutation = row['mutation']
        _require(row['status'] == 'running' and row['result'] is None and row['error'] is None
                 and type(mutation) is dict and mutation['phase'] == 'prepared'
                 and mutation['reconciliation'] is None, 'Exact running/prepared target required.')
        verification = mutation['verification'] or {}
        _require(verification.get('outcome') == 'committed'
                 and type(verification.get('evidence')) is dict and bool(verification['evidence'])
                 and type(receipt['return_result']) is dict
                 and receipt['return_result'].get('verified') is True, 'Committed callback verification required.')
        steps = verification.get('native_steps', [])
        _require(type(steps) is list and len(steps) % 2 == 0, 'Pending native step prohibits exit.')
        names = set()
        for index in range(0, len(steps), 2):
            pending, returned = steps[index:index + 2]
            _require(type(pending) is dict and type(returned) is dict
                     and set(pending) == set(returned) == {'sequence', 'name', 'phase', 'evidence'}
                     and type(pending['sequence']) is int and pending['sequence'] == index + 1
                     and type(returned['sequence']) is int and returned['sequence'] == index + 2
                     and pending['phase'] == 'pending' and returned['phase'] == 'returned'
                     and type(pending['name']) is str and bool(pending['name'])
                     and pending['name'] == returned['name'] and pending['name'] not in names
                     and all(type(step['evidence']) is dict and bool(step['evidence'])
                             for step in (pending, returned)), 'Native ledger is incomplete or changed.')
            names.add(pending['name'])
        # This is a binding only. Empty/returned ledger does NOT prove COM Q.
        binding = dict(process_identity=deepcopy(self._identity), operation_id=oid,
            request_id=row['request_id'], operation=row['operation'], job_digest=row['digest'],
            journal_sha256=_digest(rows), barrier_sha256=_digest(receipt))
        _require(barrier.state == 'waiting', 'Barrier was released during observation.')
        return binding

    def issue_command(self):
        with self._lock:
            _require(self._state == 'new', 'One gate issues exactly one command.')
            self._state = 'issuing'
        try:
            binding = self._binding()
            proof = deepcopy(_sync(self._observe_owner_q, deepcopy(binding)))
            validate_owner_q(proof, binding)
            _require(_json(self._binding()) == _json(binding), 'Binding changed during owner Q observation.')
            command = dict(scope='b4_owned_child_exit_command_v1',
                process_identity=deepcopy(self._identity), command_nonce=self._nonce,
                binding=binding, q_sha256=_digest(proof))
            with self._lock:
                self._command = deepcopy(command)
                self._state = 'armed'
            return deepcopy(command)
        except BaseException:
            with self._lock:
                self._state = 'failed'
            raise

    def execute(self, command):
        with self._lock:
            _require(self._state == 'armed', 'Exit command is one-shot; no retry.')
            self._state = 'validating'
            expected = deepcopy(self._command)
        try:
            binding = self._binding()
            proof = deepcopy(_sync(self._observe_owner_q, deepcopy(binding)))
            validation = validate_exit_command(command, expected_command=expected,
                binding=binding, owner_q_proof=proof)
            _require(_json(self._binding()) == _json(binding), 'Binding changed during owner Q observation.')
            receipt = dict(scope='b4_owned_child_exit_intent_v1', phase='exit_intent',
                command=deepcopy(expected), owner_q_proof=proof, **validation,
                exit_callback_returned=False, process_exit_observed=False)
            _sync(self._persist, deepcopy(receipt))
            # Persistence may take time: re-observe Q and binding before callback.
            final_binding = self._binding()
            final_proof = deepcopy(_sync(self._observe_owner_q, deepcopy(final_binding)))
            validate_exit_command(command, expected_command=expected,
                binding=final_binding, owner_q_proof=final_proof)
            _require(_json(self._binding()) == _json(binding), 'Binding changed after exit intent persistence.')
            with self._lock:
                self._receipt = deepcopy(receipt)
                self._state = 'callback_invoked'
            _sync(self._exit, deepcopy(receipt))
            receipt.update(phase='test_callback_returned', exit_callback_returned=True)
            with self._lock:
                self._receipt = deepcopy(receipt)
                self._state = 'callback_returned'
            return deepcopy(receipt)
        except BaseException:
            with self._lock:
                self._state = 'failed'
            raise
