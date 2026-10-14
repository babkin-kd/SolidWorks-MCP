"""Finite dimension-only MCP transport admission; never native Q/stop proof.

One exact dimension_set_value, optionally preceded by dimension_get. Observation
requests are fixed in advance. Optional bounded target polling binds the actual
job ID once from the original validated mutation response, never from caller
input. Native admission/callback/guard Q and installed integration stay separate.
"""
from copy import deepcopy
import hashlib
import inspect
import re
from threading import RLock

from mcp.types import JSONRPCMessage, CallToolResult
from pydantic import TypeAdapter
from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.dimension_tools_v2 import register_dimension_tools
from solidworks_mcp.jobs import _json


class AdmissionError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AdmissionError(message)


def _dimension_signatures():
    functions = {}

    class Registry:
        def tool(self):
            def collect(function):
                functions[function.__name__] = inspect.signature(function)
                return function
            return collect

    # Actual current facade signatures only. No function/runtime/CAD callback.
    register_dimension_tools(Registry(), None, None, None)
    return {name: functions[name] for name in ('dimension_get', 'dimension_set_value')}


SIGNATURES = _dimension_signatures()


def typed_arguments(name, arguments):
    require(type(arguments) is dict, 'Exact tool argument object required.')
    if name == 'system_get_info':
        require(arguments == {}, 'Metadata takes no arguments.')
        return {}
    if name == 'job_get':
        require(set(arguments) == {'operation_id'} and type(arguments['operation_id']) is str
                and bool(arguments['operation_id'].strip()), 'Only one known exact job operation_id required.')
        return deepcopy(arguments)
    require(name in SIGNATURES, 'Unknown or unsupported tool; dimension-only finite profile.')
    signature = SIGNATURES[name]
    require(set(arguments) <= set(signature.parameters), 'Extra tool argument keys prohibited.')
    result = {}
    for key, parameter in signature.parameters.items():
        require(key in arguments or parameter.default is not inspect.Parameter.empty, 'Missing required tool argument.')
        value = arguments.get(key, parameter.default)
        result[key] = TypeAdapter(parameter.annotation).validate_python(value, strict=True)
    for key in ('request_id', 'document_id', 'configuration', 'object_id', 'expected_revision'):
        if key in result:
            require(type(result[key]) is str and bool(result[key].strip()), 'Explicit nonempty request/context/object required.')
    _json(result)  # Reject non-finite values before any physical write.
    return result


def plan(value):
    require(type(value) is dict and set(value) == {'name', 'arguments'}, 'Exact owner tool name/arguments plan required.')
    require(type(value['name']) is str, 'Exact tool name required.')
    return dict(name=value['name'], arguments=typed_arguments(value['name'], value['arguments']))


def _sync(function, *arguments):
    value = function(*arguments)
    if inspect.isawaitable(value) or inspect.isgenerator(value) or inspect.isasyncgen(value):
        if inspect.iscoroutine(value) or inspect.isgenerator(value):
            value.close()
        raise AdmissionError('Physical write/flush proof must return synchronously.')
    return value


class DimensionAdmission:
    """Writer owns validation+write+flush under the same admission lock.

    Call write_message(message, pipe.write, pipe.flush) in the writer thread.
    Closing admission waits for that original synchronous write, or revokes a
    later CAD write before it begins. No timeout/cancellation/kill/retry exists.
    observe_response is transport evidence only, not a callback/guard Q producer.
    """

    def __init__(self, *, cad_requests, observation_requests, target_operation, target_payload, target_poll_limit=0):
        require(type(target_poll_limit) is int and 0 <= target_poll_limit <= 64,
                'Target poll limit must be an explicit integer 0..64 (default disabled).')
        require(type(cad_requests) is tuple and 1 <= len(cad_requests) <= 2, 'Finite one/two CAD requests required.')
        require(type(observation_requests) is tuple and len(observation_requests) <= 32, 'Finite observations required.')
        self._cad = tuple(plan(value) for value in cad_requests)
        self._observations = tuple(plan(value) for value in observation_requests)
        require(self._cad[-1]['name'] == 'dimension_set_value'
                and (len(self._cad) == 1 or self._cad[0]['name'] == 'dimension_get'),
                'Only optional dimension_get then one dimension_set_value admitted.')
        require(all(value['name'] in ('system_get_info', 'job_get') for value in self._observations),
                'Observations must be fixed metadata or known job_get only.')
        target = self._cad[-1]['arguments']
        request_ids = [value['arguments']['request_id'] for value in self._cad]
        require(len(set(request_ids)) == len(request_ids), 'CAD request IDs must be distinct; no replay plan.')
        require(all(all(value['arguments'][key] == target[key] for key in ('document_id', 'configuration', 'object_id'))
                    for value in self._cad), 'One exact original dimension/document/configuration required.')
        arguments = {key: value for key, value in target.items() if key not in ('request_id', 'timeout_s')}
        context = {key: arguments[key] for key in ('document_id', 'configuration', 'object_id', 'expected_revision')}
        expected_payload = dict(arguments=arguments, context=context, mutates=True)
        require(target_operation == 'dimension.set_value' and _json(target_payload) == _json(expected_payload),
                'Exact pre-dispatch operation/durable payload binding required.')
        self._target_operation, self._target_payload = target_operation, deepcopy(expected_payload)
        self._lock = RLock()
        self._closed = self._unknown = False
        self._fault = None
        self._attempted = self._emitted = self._cad_emitted = self._observation_emitted = 0
        self._cad_next = self._observation_next = 0
        self._records = []
        self._rpc_ids = set()
        self._write_active = False
        self._target_poll_limit = target_poll_limit
        self._target_poll_emitted = 0
        self._target_binding = None
        self._target_poll_failed = False

    def _bind_target_from_record(self, record):
        if self._target_poll_limit == 0 or record['name'] != 'dimension_set_value' or not record.get('response_validated'):
            return
        if record['write_state'] == 'started':
            return  # Early reply is observed; binding waits for original flush.
        require(not self._unknown and record['write_state'] == 'emitted' and not self._target_poll_failed,
                'Known original mutation write/flush evidence required for target binding.')
        require(self._target_binding is None, 'Original target job binding is one-shot; no replacement.')
        operation_id = record['response_operation_id']
        require(type(operation_id) is str and re.fullmatch(r'job_[0-9a-f]{32}', operation_id) is not None,
                'Actual current JobStore job identity required; no guessed target IDs.')
        self._target_binding = dict(scope='b4_transport_target_job_binding_v1', operation_id=operation_id,
            rpc_id=record['rpc_id'], request_id=record['arguments']['request_id'], operation=self._target_operation,
            payload=deepcopy(self._target_payload), transport_only=True)

    def _validate_target_job(self, response):
        binding = self._target_binding
        require(binding is not None and not self._target_poll_failed and not self._unknown,
                'Original target job binding and known transport required.')
        row = response.data
        keys = {'operation_id', 'request_id', 'operation', 'payload', 'status', 'created_at', 'updated_at', 'result', 'error'}
        require(type(row) is dict and set(row) in (keys, keys | {'mutation'}), 'Exact public JobStore DTO required.')
        require(response.operation_id == row['operation_id'] == binding['operation_id']
                and row['request_id'] == binding['request_id'] and row['operation'] == binding['operation']
                and _json(row['payload']) == _json(binding['payload'])
                and _json(response.context) == _json(binding['payload']['context'])
                and response.status == row['status'], 'Original target job operation/request/payload/context lineage differs.')
        require(all(type(row[key]) in (int, float) and row[key] >= 0 for key in ('created_at', 'updated_at'))
                and (row['result'] is None or type(row['result']) is dict)
                and (row['error'] is None or type(row['error']) is dict), 'Exact finite job timestamps/result/error required.')
        envelope_error = None if response.error is None else response.error.model_dump(mode='json')
        require(_json(envelope_error) == _json(row['error']), 'Target job envelope/error differs from original DTO.')
        if 'mutation' in row:
            mutation = row['mutation']
            mutation_keys = {'operation_id', 'connection_epoch', 'document_id', 'configuration', 'expected_revision',
                             'before_state', 'phase', 'verification', 'reconciliation', 'updated_at'}
            require(type(mutation) is dict and set(mutation) == mutation_keys
                    and mutation['operation_id'] == binding['operation_id']
                    and all(mutation[key] == binding['payload']['context'][key]
                            for key in ('document_id', 'configuration', 'expected_revision'))
                    and type(mutation['connection_epoch']) is str and bool(mutation['connection_epoch'])
                    and type(mutation['before_state']) is dict
                    and mutation['phase'] in ('prepared', 'committed', 'rolled_back', 'not_started', 'unresolved', 'reconciled')
                    and all(mutation[key] is None or type(mutation[key]) is dict for key in ('verification', 'reconciliation'))
                    and type(mutation['updated_at']) in (int, float) and mutation['updated_at'] >= 0,
                    'Target checkpoint DTO scope/shape differs; no mutation/reconciliation authority.')
        _json(row)

    def _reject(self, message):
        self._closed = True
        if self._fault is None:
            self._fault = message
        raise AdmissionError(message)

    def close_admission(self):
        with self._lock:
            self._closed = True  # Irreversible; repeated close is observation-safe.
            return self.receipt()

    def write_message(self, message, write, flush):
        with self._lock:
            self._attempted += 1
            try:
                require(isinstance(message, JSONRPCMessage), 'Real MCP JSONRPCMessage required.')
                raw = message.model_dump(mode='json', by_alias=True, exclude_none=True)
                require(set(raw) == {'jsonrpc', 'id', 'method', 'params'} and raw['jsonrpc'] == '2.0'
                        and raw['method'] == 'tools/call', 'Only exact typed tool requests admitted.')
                rpc_id = raw['id']
                require(type(rpc_id) in (int, str), 'Exact request RPC identity required.')
                rpc_key = (type(rpc_id).__name__, rpc_id)
                require(rpc_key not in self._rpc_ids, 'RPC replay/duplicate prohibited.')
                require(not self._write_active, 'Original physical writer already active; no reentrant sends.')
                params = raw['params']
                value = plan(params)
                kind = 'observation' if value['name'] in ('system_get_info', 'job_get') else 'cad'
                require(not self._unknown, 'Unknown partial write retains transport; no further sends.')
                if kind == 'cad':
                    target_poll = False
                    dynamic_target_poll = False
                    require(not self._closed and self._cad_next < len(self._cad), 'CAD admission permanently closed/exhausted.')
                    require(not any(record['kind'] == 'cad' and record.get('server_status') != 'succeeded'
                                    for record in self._records), 'Prior CAD request not confirmed succeeded; no parallel CAD.')
                    expected = self._cad[self._cad_next]
                else:
                    next_observation = self._observations[self._observation_next] if self._observation_next < len(self._observations) else None
                    target_poll = value['name'] == 'job_get' and self._target_binding is not None \
                        and value['arguments']['operation_id'] == self._target_binding['operation_id']
                    known_match = next_observation is not None and _json(value) == _json(next_observation)
                    dynamic_target_poll = target_poll and not known_match
                    if target_poll:
                        require(not self._target_poll_failed, 'Target polling unavailable after invalid response.')
                        require(not any(record.get('target_poll') and not record['response_observed'] for record in self._records),
                                'Original target poll response still in flight; no overlapping target polls.')
                    if known_match:
                        expected = next_observation
                    elif dynamic_target_poll:
                        require(self._target_poll_emitted < self._target_poll_limit, 'Target finite budget exhausted.')
                        expected = dict(name='job_get', arguments={'operation_id': self._target_binding['operation_id']})
                    else:
                        require(next_observation is not None, 'Observation plan exhausted; target job unbound.')
                        expected = next_observation
                require(_json(value) == _json(expected), 'Owner plan name/typed payload drift.')
                require(all(callable(function) and not inspect.iscoroutinefunction(function)
                            and not inspect.isgeneratorfunction(function) and not inspect.isasyncgenfunction(function)
                            for function in (write, flush)), 'Synchronous physical writer required.')
                payload = message.model_dump_json(by_alias=True, exclude_none=True).encode('utf8') + b'\n'
                require(len(payload) <= 65536, 'Bounded exact MCP request required.')
            except Exception as exc:
                return self._reject(str(exc))
            record = dict(sequence=len(self._records) + 1, rpc_id=rpc_id, kind=kind,
                          name=value['name'], arguments=value['arguments'], write_state='started', response_observed=False,
                          target_poll=target_poll, dynamic_target_poll=dynamic_target_poll)
            self._records.append(record)
            self._rpc_ids.add(rpc_key)
            self._write_active = True
            try:
                written = _sync(write, payload)
                require(type(written) is int and written == len(payload), 'Complete physical byte-write acknowledgement required.')
                require(_sync(flush) is None, 'Normal physical flush acknowledgement required.')
            except BaseException as exc:
                record.update(write_state='unknown', write_error_type=type(exc).__name__)
                self._unknown = self._closed = True
                self._fault = 'Physical write/flush outcome unconfirmed; retain original transport, no retry.'
                raise AdmissionError(self._fault) from exc
            finally:
                self._write_active = False
            record['write_state'] = 'emitted'
            self._emitted += 1
            if kind == 'cad':
                self._cad_emitted += 1
                self._cad_next += 1
            else:
                self._observation_emitted += 1
                if dynamic_target_poll:
                    self._target_poll_emitted += 1
                else:
                    self._observation_next += 1
            try:
                self._bind_target_from_record(record)
            except Exception as exc:
                self._target_poll_failed = True
                return self._reject(str(exc))
            return dict(sequence=record['sequence'], emitted=True, payload_sha256=hashlib.sha256(payload).hexdigest())

    def observe_response(self, message):
        with self._lock:
            try:
                require(isinstance(message, JSONRPCMessage), 'Real MCP response message required.')
                raw = message.model_dump(mode='json', by_alias=True, exclude_none=True)
                require(raw.get('jsonrpc') == '2.0' and 'method' not in raw and 'id' in raw
                        and ('result' in raw or 'error' in raw), 'Exact response identity required.')
                matches = [record for record in self._records if type(record['rpc_id']) is type(raw['id'])
                           and record['rpc_id'] == raw['id']]
                require(len(matches) == 1 and not matches[0]['response_observed'], 'Original unseen response required.')
            except Exception as exc:
                self._target_poll_failed = True
                return self._reject(str(exc))
            record = matches[0]
            record['response_observed'] = True
            record['response_validated'] = False
            try:
                if 'error' in raw:
                    require(not record.get('target_poll'), 'Target poll requires its exact structured JobStore DTO.')
                    record['server_status'] = None
                else:
                    result = CallToolResult.model_validate(raw['result'], strict=True)
                    require(result.isError is False and type(result.structuredContent) is dict,
                            'Normally structured tool response required.')
                    response = ResponseEnvelope.model_validate(result.structuredContent, strict=True)
                    if record['kind'] == 'cad':
                        expected_context = {key: record['arguments'][key] for key in
                            ('document_id', 'configuration', 'object_id', 'expected_revision') if key in record['arguments']}
                        require(type(response.operation_id) is str and bool(response.operation_id)
                                and _json(response.context) == _json(expected_context),
                                'Original CAD response job/context binding required.')
                    record['server_status'] = response.status
                    if response.status == 'succeeded':
                        require(response.error is None, 'Succeeded response cannot hide an error.')
                    if record.get('target_poll'):
                        self._validate_target_job(response)
                    record['response_operation_id'] = response.operation_id
                    record['response_validated'] = True
                    self._bind_target_from_record(record)
            except Exception as exc:
                record['server_status'] = None
                record['response_validated'] = False
                self._target_poll_failed = True
                return self._reject(str(exc))
            # A late reply never manufactures missing write+flush evidence.
            if record['kind'] == 'cad' and record['server_status'] != 'succeeded':
                self._closed = True
            return deepcopy(record)

    def receipt(self):
        with self._lock:
            return dict(scope='b4_dimension_transport_admission_v1', target_operation=self._target_operation,
                target_payload=deepcopy(self._target_payload), admission_closed=self._closed,
                unknown_transport=self._unknown, fault=self._fault, attempted=self._attempted, emitted=self._emitted,
                cad_emitted=self._cad_emitted, observation_emitted=self._observation_emitted,
                in_flight_cad=sum(record['kind'] == 'cad' and not record['response_observed'] for record in self._records),
                in_flight_observations=sum(record['kind'] == 'observation' and not record['response_observed'] for record in self._records),
                records=deepcopy(self._records), accepted=False, native_q='not_run', native_admission='not_run',
                process_stop_authorized=False, restart_authorized=False, cad_cleanup_authorized=False,
                target_job_observation_binding='not_run' if self._target_binding is None else deepcopy(self._target_binding),
                target_poll_limit=self._target_poll_limit, target_poll_emitted=self._target_poll_emitted,
                target_poll_failed=self._target_poll_failed)
