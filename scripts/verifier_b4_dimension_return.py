"""Observe the original synchronous dimension callback and guard; never native Q.

Install on an already prepared, exclusively owned Runtime. This observer does
not connect, dispatch, cancel, stop a process or read additional CAD properties.
Its receipt needs separate independent postconditions and admission/Q proof.
"""
from copy import deepcopy
import inspect
from threading import RLock, get_ident

from solidworks_mcp.application_guard import ApplicationModelMutationGuard
from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.jobs import _json
from solidworks_mcp.runtime_v2 import Runtime


class ReturnObservationError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise ReturnObservationError(message)


class DimensionReturnObserver:
    def __init__(self, runtime, *, request_id, payload, persist):
        require(type(runtime) is Runtime and type(runtime._dimensions) is DimensionCatalog,
                'Original prepared Runtime and DimensionCatalog required.')
        original = runtime._execute
        require(getattr(original, '__self__', None) is runtime
                and getattr(original, '__func__', None) is Runtime._execute,
                'Original Runtime callback required; no replaced callback adoption.')
        require(type(request_id) is str and bool(request_id.strip()), 'Explicit new request required.')
        require(type(payload) is dict and set(payload) == {'arguments', 'context', 'mutates'}
                and payload['mutates'] is True and type(payload['arguments']) is dict,
                'Exact original durable payload required.')
        context = {key: payload['arguments'][key] for key in
                   ('document_id', 'configuration', 'object_id', 'expected_revision')}
        require(_json(payload['context']) == _json(context)
                and all(type(value) is str and bool(value.strip()) for value in context.values()),
                'Exact prepared dimension scope required.')
        require(callable(persist) and not inspect.iscoroutinefunction(persist)
                and not inspect.isgeneratorfunction(persist) and not inspect.isasyncgenfunction(persist),
                'Synchronous one-shot receipt persistence required.')
        dimensions = runtime._dimensions
        require(dimensions.documents is runtime._catalog and dimensions.adapter is runtime._catalog.adapter
                and dimensions.coordinator.store is runtime.store
                and dimensions.connection_epoch == runtime._connection_epoch
                and callable(dimensions.mutation_guard), 'Original catalog/store/epoch/guard wiring required.')
        self.runtime, self.dimensions = runtime, dimensions
        self.request_id, self.payload, self.persist = request_id, deepcopy(payload), persist
        self._original_execute, self._original_guard = original, dimensions.mutation_guard
        self._wrapped_execute, self._wrapped_guard = self._execute, self._guard
        self._lock = RLock()
        self._installed = self._install_attempted = self._attempted = self._live = False
        self._persist_attempted = self._persisted = False
        self._returned = False
        self._guards = []
        self._receipt = None
        self._thread = None

    def install(self):
        with self._lock:
            require(not self._install_attempted, 'Observer installation is one-shot.')
            self._install_attempted = True
            require(self.runtime._execute == self._original_execute
                    and self.dimensions.mutation_guard is self._original_guard,
                    'Original callback/guard changed before installation.')
            self.runtime._execute = self._wrapped_execute
            self.dimensions.mutation_guard = self._wrapped_guard
            self._installed = True
            return self

    def _wired(self):
        require(self._installed and self.runtime._execute is self._wrapped_execute
                and self.dimensions.mutation_guard is self._wrapped_guard
                and self.runtime._dimensions is self.dimensions
                and self.runtime._catalog is self.dimensions.documents
                and self.runtime.store is self.dimensions.coordinator.store,
                'Original observer wiring changed; retain owner.')

    def _guard(self, model):
        with self._lock:
            self._wired()
            require(self._live and get_ident() == self._thread and not self._guards,
                    'Exactly one target guard on the original callback thread required.')
            guard = self._original_guard(model)
            require(type(guard) is ApplicationModelMutationGuard and guard.state == 'new'
                    and guard.thread == self._thread and guard.models == (model,),
                    'Original newly created application/model guard required.')
            self._guards.append(guard)
            return guard  # Original context manager executes unchanged.

    def _execute(self, operation, arguments, operation_id=None):
        with self._lock:
            self._wired()
            require(not self._attempted and not self._live, 'One original callback only; no retry/other dispatch.')
            self._attempted = True
            row = self.runtime.store.get(operation_id)
            require(operation == 'dimension.set_value' and _json(arguments) == _json(self.payload['arguments'])
                    and row['operation_id'] == operation_id and row['request_id'] == self.request_id
                    and row['operation'] == operation and _json(row['payload']) == _json(self.payload)
                    and row['status'] == 'running' and row['result'] is None and row['error'] is None,
                    'Original running request/operation/payload required before callback.')
            self._live, self._thread = True, get_ident()
        try:
            result = self._original_execute(operation, arguments, operation_id)
            with self._lock:
                self._returned = True
                self._wired()
                require(type(result) is dict and result.get('verified') is True and len(self._guards) == 1,
                        'Original verified return and exactly one guard required.')
                guard = self._guards[0]
                evidence = deepcopy(guard.evidence)  # Stored observations only; no native reads.
                require(guard.state == 'closed' and guard.owned is False
                        and evidence['original_command_in_progress'] is False
                        and evidence['acquired'] is True and evidence['released'] is True
                        and evidence['selection_preserved'] is True
                        and len(evidence['model_guards']) == 1
                        and evidence['model_guards'][0] ==
                            {'original_state': 0, 'locked_state': 2, 'released_state': 0},
                        'Actual original guard completion/readback evidence required.')
                row = self.runtime.store.get(operation_id)
                mutation = row['mutation']
                require(row['status'] == 'running' and type(mutation) is dict
                        and mutation['phase'] == 'prepared'
                        and mutation['verification']['outcome'] == 'committed'
                        and mutation['connection_epoch'] == self.runtime._connection_epoch,
                        'Original unfinished committed-verification checkpoint required.')
                receipt = dict(scope='b4_original_dimension_callback_return_v1',
                    request_id=self.request_id, operation_id=operation_id, operation=operation,
                    payload=deepcopy(self.payload), connection_epoch=self.runtime._connection_epoch,
                    original_callback_returned=True, callback_thread=self._thread,
                    return_result=deepcopy(result), guard_evidence=evidence, guard_completed=True,
                    journal_row_before_finish=deepcopy(row), accepted=False, native_q='not_run',
                    process_stop_authorized=False, restart_authorized=False, cad_cleanup_authorized=False)
                _json(receipt)
                self._receipt = receipt
                self._persist_attempted = True
                acknowledgement = self.persist(deepcopy(receipt))
                if inspect.iscoroutine(acknowledgement) or inspect.isgenerator(acknowledgement):
                    acknowledgement.close()
                require(not inspect.isawaitable(acknowledgement) and not inspect.isgenerator(acknowledgement)
                        and acknowledgement is None, 'Normal synchronous persistence acknowledgement required.')
                self._persisted = True
            return result
        finally:
            with self._lock:
                self._live = False

    def observation(self):
        with self._lock:
            return dict(attempted=self._attempted, callback_live=self._live,
                original_callback_returned=self._returned, persist_attempted=self._persist_attempted,
                persisted=self._persisted, receipt=deepcopy(self._receipt), native_q='not_run',
                process_stop_authorized=False, restart_authorized=False, cad_cleanup_authorized=False)

    def uninstall(self):
        with self._lock:
            self._wired()
            require(not self._live, 'Never unwire a live original callback.')
            self.runtime._execute = self._original_execute
            self.dimensions.mutation_guard = self._original_guard
            self._installed = False
