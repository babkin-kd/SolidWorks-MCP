"""Test-only arm-once finish seam installed before server Runtime creation.

No synthetic IDs/results/journal rows are produced. The owner supplies the
exact prepared request before dispatch. Waiting is a Python finish barrier,
never native Q, admission, process-stop, restart or cleanup authority.
"""
from copy import deepcopy
import importlib.util
import inspect
from pathlib import Path
from threading import RLock

from solidworks_mcp.jobs import JobStore, _json
from solidworks_mcp.runtime_v2 import Runtime, MUTATING_OPERATIONS


_name = '_b4_installed_finish_original_barrier'
_spec = importlib.util.spec_from_file_location(_name, Path(__file__).with_name('verifier_b4_finish_barrier.py'))
_barrier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_barrier)


class InstalledFinishError(RuntimeError):
    def __init__(self, message, *, retained_owner=None):
        super().__init__(message)
        self.retained_owner = retained_owner


def require(condition, message):
    if not condition:
        raise InstalledFinishError(message)


def authority():
    return dict(accepted=False, native_q='not_run', native_admission='not_run',
                process_stop_authorized=False, native_b4_accepted=False,
                restart_authorized=False, cad_cleanup_authorized=False)


class ArmableFinishStore:
    """Same exact owned store; atomically arm before its target create.

    create/arm share this lock. A pre-existing request in any status cannot be
    adopted. Nonmatching operations remain ordinary real JobStore operations.
    The original store's finish is captured by the existing FinishBarrierStore.
    """

    def __init__(self, store, *, owner):
        require(type(store) is JobStore, 'Exact original JobStore required.')
        require(type(owner) is InstalledFinishSeam and owner._installed
                and owner._original_owned_store is store,
                'Original installed factory owner must retain this exact store.')
        self._store, self._owner = store, owner
        self._lock = RLock()
        self._barrier = None
        self._arm_attempted = False
        self._target = None
        self._finish_live = 0
        self._closed = False

    def __getattr__(self, name):
        return getattr(self._store, name)

    @property
    def barrier(self):
        with self._lock:
            return self._barrier

    @property
    def state(self):
        with self._lock:
            if self._barrier is not None:
                return self._barrier.state
            return 'arm_failed' if self._arm_attempted else 'unarmed'

    def arm(self, *, runtime, request_id, operation, payload):
        with self._lock:
            require(not self._arm_attempted and not self._closed, 'Arm is one-shot; no retry or closed store.')
            self._arm_attempted = True
            self._owner.assert_wired(runtime)
            require(type(request_id) is str and bool(request_id), 'Explicit new request_id required.')
            require(operation in MUTATING_OPERATIONS, 'One implemented mutating operation required.')
            require(type(payload) is dict and set(payload) == {'arguments', 'context', 'mutates'}
                    and type(payload['arguments']) is dict and type(payload['context']) is dict
                    and payload['mutates'] is True, 'Exact mutating durable payload required.')
            detached = deepcopy(payload)
            for key in ('document_id', 'configuration', 'expected_revision'):
                require(type(detached['context'].get(key)) is str and bool(detached['context'][key]),
                        'Explicit prepared document/configuration/revision required.')
                require(key not in detached['arguments'] or detached['arguments'][key] == detached['context'][key],
                        'Prepared argument/context scope differs.')
            for key in ('object_id', 'dimension_id', 'body_id', 'sketch_id'):
                require(key not in detached['arguments'] or key not in detached['context']
                        or detached['arguments'][key] == detached['context'][key],
                        'Prepared argument/context object identity differs.')
            require(any(type(detached['arguments'].get(key, detached['context'].get(key))) is str
                        and bool(detached['arguments'].get(key, detached['context'].get(key)))
                        for key in ('object_id', 'dimension_id', 'body_id', 'sketch_id')),
                    'Explicit originally prepared object identity required; no generated target IDs.')
            # This passive complete snapshot also detects raw store bypass. No
            # queued/running/terminal request can become this new arm target.
            rows = _barrier._read_journal(self._store.path)
            require(not any(row['request_id'] == request_id for row in rows),
                    'Target request already exists; cannot arm after dispatch or adopt queued work.')
            barrier = _barrier.FinishBarrierStore(self._store, request_id=request_id,
                operation=operation, payload=detached, persist=self._owner.persist)
            self._target = dict(request_id=request_id, operation=operation, payload=detached)
            self._barrier = barrier
            return dict(scope='b4_installed_finish_arm_v1', request_id=request_id,
                        operation=operation, payload=deepcopy(detached), **authority())

    def create(self, request_id, operation, arguments, context=None, *, mutates=False):
        with self._lock:
            require(not (self._arm_attempted and self._barrier is None and mutates),
                    'Failed arm retains mutation admission closed; no new dispatch.')
            if self._target is not None and request_id == self._target['request_id']:
                self._owner.assert_wired(self._owner.runtime)
                actual = dict(arguments=arguments, context=context or {}, mutates=mutates)
                require(operation == self._target['operation'] and _json(actual) == _json(self._target['payload']),
                        'Armed request operation/payload changed; no dispatch permitted.')
            return self._store.create(request_id, operation, arguments, context, mutates=mutates)

    def finish(self, operation_id, status, *, result=None, error=None):
        with self._lock:
            barrier = self._barrier
            if barrier is None:
                return self._store.finish(operation_id, status, result=result, error=error)
            self._owner.assert_wired(self._owner.runtime)
            self._finish_live += 1
        try:
            return barrier.finish(operation_id, status, result=result, error=error)
        finally:
            with self._lock:
                self._finish_live -= 1

    def release(self, *, runtime):
        with self._lock:
            self._owner.assert_wired(runtime)
            require(self._barrier is not None, 'Original armed barrier required.')
            self._barrier.release()  # Explicit control only; no auto release.

    def wait_reached(self, timeout=0):
        require(type(timeout) in (int, float) and 0 <= timeout <= 60, 'Bounded observation required.')
        with self._lock:
            barrier = self._barrier
        return False if barrier is None else barrier.wait_reached(timeout)

    def close(self):
        with self._lock:
            require(self._finish_live == 0 and (self._barrier is None or self._barrier.state not in
                    ('capturing', 'waiting', 'released', 'finishing')), 'Cannot close store while original finish is live/held.')
            self._store.close()
            self._closed = True


class InstalledFinishSeam:
    """Finite server module factory injection, exactly one store and Runtime.

    install before main(); main's existing JobStore/Runtime construction receives
    this proxy. Keep the owner instance. Later arm with exact prepared durable
    payload and retained runtime, then dispatch that new request normally.
    uninstall never releases a held worker and refuses while finish is live.
    """

    def __init__(self, server_module, *, journal_path, persist):
        require(server_module.JobStore is JobStore and server_module.Runtime is Runtime
                and callable(server_module.main), 'Original server JobStore/Runtime/main factories required.')
        require(callable(persist) and not inspect.iscoroutinefunction(persist)
                and not inspect.isgeneratorfunction(persist) and not inspect.isasyncgenfunction(persist),
                'Synchronous durable owner persist required.')
        self.module, self.path, self.persist = server_module, Path(journal_path).resolve(), persist
        self._original_store, self._original_runtime = server_module.JobStore, server_module.Runtime
        self._store_factory, self._runtime_factory = self._make_store, self._make_runtime
        self.proxy = self.runtime = None
        self._original_owned_store = None
        self._installed = self._install_attempted = False
        self._lock = RLock()

    def install(self):
        with self._lock:
            require(not self._install_attempted, 'Factory installation is one-shot.')
            self._install_attempted = True
            require(self.module.JobStore is self._original_store and self.module.Runtime is self._original_runtime,
                    'Foreign/replaced server factories refused.')
            self.module.JobStore, self.module.Runtime = self._store_factory, self._runtime_factory
            self._installed = True
            return self

    def _make_store(self, path):
        with self._lock:
            require(self._installed and self.proxy is None and Path(path).resolve() == self.path,
                    'Exactly one original configured store path required; no adoption.')
            store = self._original_store(path)
            self._original_owned_store = store
            self.proxy = ArmableFinishStore(store, owner=self)
            return self.proxy

    def _make_runtime(self, store, *args, **kwargs):
        with self._lock:
            require(self._installed and self.proxy is not None and store is self.proxy and self.runtime is None,
                    'Original proxy must precede exactly one Runtime construction.')
            self.runtime = self._original_runtime(store, *args, **kwargs)
            return self.runtime

    def assert_wired(self, runtime):
        require(self._installed and self.module.JobStore is self._store_factory
                and self.module.Runtime is self._runtime_factory and self.proxy is not None
                and self.proxy._store is self._original_owned_store
                and runtime is self.runtime and runtime is not None and runtime.store is self.proxy,
                'Exact original store/runtime factory wiring required.')
        runner = runtime._runner
        require(runner is None or runner.store is self.proxy, 'Foreign/unproxied JobRunner refused.')

    def uninstall(self):
        with self._lock:
            require(self._installed and self.module.JobStore is self._store_factory
                    and self.module.Runtime is self._runtime_factory, 'Original installed factories required.')
            if self.proxy is not None:
                with self.proxy._lock:
                    require(self.proxy._finish_live == 0 and (self.proxy.barrier is None or
                        self.proxy.barrier.state not in ('capturing', 'waiting', 'released', 'finishing')),
                        'Cannot unwire live/held original finish; retain owner.')
            self.module.JobStore, self.module.Runtime = self._original_store, self._original_runtime
            self._installed = False
