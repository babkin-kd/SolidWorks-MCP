"""Finite dimension-only MCP transport admission; never native Q/stop proof.

One exact dimension_set_value, optionally preceded by dimension_get. Observation
requests (system_get_info/job_get) are fixed in advance. A future actual target
operation_id is NOT fabricated or bound here: polling it needs a separate
one-shot binding from a verified structured response in installed integration.
"""
from copy import deepcopy
import hashlib
import inspect
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

    def __init__(self, *, cad_requests, observation_requests, target_operation, target_payload):
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
                    require(not self._closed and self._cad_next < len(self._cad), 'CAD admission permanently closed/exhausted.')
                    require(not any(record['kind'] == 'cad' and record.get('server_status') != 'succeeded'
                                    for record in self._records), 'Prior CAD request not confirmed succeeded; no parallel CAD.')
                    expected = self._cad[self._cad_next]
                else:
                    require(self._observation_next < len(self._observations), 'Observation plan exhausted.')
                    expected = self._observations[self._observation_next]
                require(_json(value) == _json(expected), 'Owner plan name/typed payload drift.')
                require(all(callable(function) and not inspect.iscoroutinefunction(function)
                            and not inspect.isgeneratorfunction(function) and not inspect.isasyncgenfunction(function)
                            for function in (write, flush)), 'Synchronous physical writer required.')
                payload = message.model_dump_json(by_alias=True, exclude_none=True).encode('utf8') + b'\n'
                require(len(payload) <= 65536, 'Bounded exact MCP request required.')
            except Exception as exc:
                return self._reject(str(exc))
            record = dict(sequence=len(self._records) + 1, rpc_id=rpc_id, kind=kind,
                          name=value['name'], arguments=value['arguments'], write_state='started', response_observed=False)
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
                self._observation_next += 1
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
                return self._reject(str(exc))
            record = matches[0]
            record['response_observed'] = True
            record['response_validated'] = False
            try:
                if 'error' in raw:
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
                    record['response_validated'] = True
                    if response.status == 'succeeded':
                        require(response.error is None, 'Succeeded response cannot hide an error.')
            except Exception as exc:
                record['server_status'] = None
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
                target_job_observation_binding='not_run')
