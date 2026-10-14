"""One-shot Python finish barrier for the future B4-N4 process test.

Wrap the owned JobStore before constructing JobRunner. Reaching this barrier
means Python called finish after its callback returned; it proves neither COM
quiescence nor permission to stop a process or close CAD. The native owner must
prove those separately. No native imports, process operations or automatic
timeout/retry are provided here. This is a test harness, not production API.
"""
from copy import deepcopy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from threading import Event, Lock

from solidworks_mcp.jobs import _json


class FinishBarrierError(RuntimeError):
    """The finite barrier cannot proceed; retain the journal and its holds."""


def _require(condition, message):
    if not condition:
        raise FinishBarrierError(message)


def _detach(value):
    return json.loads(_json(value))


# Reuse the shared passive schema/budget/orphan checks. Register temporarily
# for its dataclasses, restoring the prior binding even when loading fails.
_name = '_b4_finish_passive_lifecycle'
_spec = importlib.util.spec_from_file_location(_name, Path(__file__).with_name('verifier_lifecycle.py'))
_module = importlib.util.module_from_spec(_spec)
_prior = sys.modules.get(_name)
sys.modules[_name] = _module
try:
    _spec.loader.exec_module(_module)
finally:
    if _prior is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _prior
_read_journal = _module.read_journal


class FinishBarrierStore:
    """Proxy the store, delaying exactly one matching successful finish.

    ``payload`` is the whole durable object: arguments/context/mutates. The
    constructor snapshots it. ``persist(receipt)`` must synchronously persist
    the complete receipt and return normally before ``wait_reached`` can succeed.
    It is invoked once only. Its failure is latched and never retried. Other
    jobs and all ordinary store methods delegate unchanged. A matching request
    with changed operation/payload is rejected rather than adopted.

    ``release()`` explicitly allows one original finish; it does not authorize
    process termination. ``wait_reached(timeout)`` bounds observation only. The
    worker's actual wait has no timeout or automatic success/cancellation path.
    Do not close the underlying store while its worker is waiting.
    """

    def __init__(self, store, *, request_id, operation, payload, persist):
        _require(type(request_id) is str and bool(request_id), 'Explicit request_id required.')
        _require(type(operation) is str and bool(operation), 'Explicit operation required.')
        _require(type(payload) is dict and set(payload) == {'arguments', 'context', 'mutates'}
                 and type(payload['arguments']) is dict and type(payload['context']) is dict
                 and payload['mutates'] is True, 'Explicit mutating durable payload required.')
        context = payload['context']
        _require(all(type(context.get(key)) is str and bool(context[key]) for key in
                     ('document_id', 'configuration', 'expected_revision')),
                 'Explicit document, configuration and revision required.')
        _require(callable(persist) and not inspect.iscoroutinefunction(persist)
                 and not inspect.isasyncgenfunction(persist) and not inspect.isgeneratorfunction(persist),
                 'A synchronous persist callback is required.')
        self._store = store
        self._original_finish = store.finish
        self._request_id = request_id
        self._operation = operation
        self._payload = _detach(payload)
        self._persist = persist
        self._lock = Lock()
        self._reached = Event()
        self._release = Event()
        self._state = 'armed'
        self._operation_id = None
        self._receipt = None

    def __getattr__(self, name):
        return getattr(self._store, name)

    @property
    def state(self):
        with self._lock:
            return self._state

    @property
    def receipt(self):
        with self._lock:
            return deepcopy(self._receipt)

    def wait_reached(self, timeout=None):
        return self._reached.wait(timeout)

    def release(self):
        with self._lock:
            _require(self._state == 'waiting', 'Release requires the single persisted waiting barrier.')
            self._state = 'released'
            self._release.set()

    def _validate(self, row, result, error):
        _require(row['request_id'] == self._request_id and row['operation'] == self._operation
                 and _json(row['payload']) == _json(self._payload), 'Exact request scope changed.')
        expected_digest = hashlib.sha256((self._operation + '\n' + _json(self._payload)).encode('utf-8')).hexdigest()
        _require(row['digest'] == expected_digest, 'Durable digest does not match the explicit request.')
        mutation = row['mutation']
        _require(row['status'] == 'running' and row['result'] is None and row['error'] is None
                 and type(mutation) is dict and mutation['phase'] == 'prepared',
                 'Expected running/prepared mutation required.')
        context = self._payload['context']
        _require(mutation['operation_id'] == row['operation_id']
                 and all(mutation[key] == context[key] for key in
                         ('document_id', 'configuration', 'expected_revision'))
                 and type(mutation['connection_epoch']) is str and bool(mutation['connection_epoch'])
                 and type(mutation['before_state']) is dict
                 and mutation['reconciliation'] is None, 'Checkpoint scope changed or incomplete.')
        verification = mutation['verification']
        _require(type(verification) is dict and verification.get('outcome') == 'committed'
                 and type(verification.get('evidence')) is dict and bool(verification['evidence']),
                 'A committed postcondition verification is required.')
        _require(type(result) is dict and result.get('verified') is True and error is None,
                 'A verified Python return result without an error is required.')

    def finish(self, operation_id, status, *, result=None, error=None):
        job = self._store.get(operation_id)
        if job['request_id'] != self._request_id:
            return self._original_finish(operation_id, status, result=result, error=error)
        with self._lock:
            _require(self._state == 'armed', 'The exact request barrier cannot be activated twice.')
            _require(job['operation'] == self._operation and _json(job['payload']) == _json(self._payload),
                     'Matching request_id cannot substitute another operation or payload.')
            if status != 'succeeded':
                return self._original_finish(operation_id, status, result=result, error=error)
            self._state = 'capturing'
            self._operation_id = operation_id
        try:
            detached_result = _detach(result)
            rows = _read_journal(self._store.path)
            matches = [row for row in rows if row['operation_id'] == operation_id]
            _require(len(matches) == 1, 'One exact coherent raw job is required.')
            row = matches[0]
            self._validate(row, detached_result, error)
            published = deepcopy(row)
            published.pop('digest')
            _require(_json(published) == _json(job), 'Store DTO and coherent raw checkpoint disagree.')
            receipt = dict(scope='b4_python_finish_barrier_v1', journal=rows,
                           operation_id=operation_id, return_result=detached_result,
                           python_finish_intercepted=True, terminal_finish_called=False,
                           native_b4_accepted=False, process_stop_authorized=False,
                           native_quiescence_proven=False, cad_cleanup_authorized=False)
            # Callback receives a detached copy; it cannot mutate the saved
            # result, checkpoint or subsequent original finish arguments.
            acknowledgement = self._persist(deepcopy(receipt))
            if (inspect.isawaitable(acknowledgement) or inspect.isgenerator(acknowledgement)
                    or inspect.isasyncgen(acknowledgement)):
                # Do not schedule, execute or cancel a deferred persistence
                # operation. Close only an unstarted native Python coroutine/
                # generator to avoid a resource warning, retaining the hold.
                if inspect.iscoroutine(acknowledgement) or inspect.isgenerator(acknowledgement):
                    acknowledgement.close()
                raise FinishBarrierError('Persistence must complete synchronously, not return deferred work.')
            with self._lock:
                self._receipt = receipt
                self._state = 'waiting'
                self._reached.set()
            self._release.wait()  # Deliberately no timeout, cancellation or retry.
            current = _read_journal(self._store.path)
            _require(_json(current) == _json(rows),
                     'Held checkpoint or complete journal changed before explicit finish release.')
            with self._lock:
                self._state = 'finishing'
            completed = self._original_finish(operation_id, status, result=detached_result, error=None)
            with self._lock:
                self._state = 'finished'
            return completed
        except BaseException:
            with self._lock:
                self._state = 'failed'
            raise
