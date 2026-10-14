"""Finite MCP wire bridge to original dimension admission; no SDK/COM owner.

The caller owns the original pipe and process. This bridge neither opens nor
closes them, retries a message, cancels a job, or grants native Q authority.
"""
from copy import deepcopy
import importlib.util
import inspect
from pathlib import Path
from threading import RLock
from types import ModuleType

from mcp.types import JSONRPCMessage, InitializeResult, ListToolsResult

_path = Path(__file__).with_name('verifier_b4_native_admission.py').resolve()
_spec = importlib.util.spec_from_file_location('_b4_protocol_original_admission', _path)
original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(original)


class ProtocolBridgeError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise ProtocolBridgeError(message)


def _sync(function, *args):
    value = function(*args)
    if inspect.isawaitable(value) or inspect.isgenerator(value) or inspect.isasyncgen(value):
        if inspect.iscoroutine(value) or inspect.isgenerator(value):
            value.close()
        raise ProtocolBridgeError('Original physical write/flush must return synchronously.')
    return value


class DimensionProtocolBridge:
    def __init__(self, admission, *, admission_module, metadata_limit=3):
        require(type(admission_module) is ModuleType and Path(admission_module.__file__).resolve() == _path
                and type(admission) is admission_module.DimensionAdmission, 'Exact original admission/module required.')
        klass = type(admission)
        for name, function in vars(original.DimensionAdmission).items():
            if callable(function) and hasattr(function, '__code__'):
                require(getattr(vars(klass).get(name), '__code__', None) == function.__code__,
                        'Original admission implementation changed.')
        require(type(metadata_limit) is int and 2 <= metadata_limit <= 8, 'Finite metadata budget 2..8 required.')
        require(not hasattr(admission, '_dimension_protocol_bridge'), 'One original bridge only; no admission adoption.')
        self.admission, self.module, self.klass = admission, admission_module, klass
        self._codes = {name: function.__code__ for name, function in vars(klass).items()
                       if callable(function) and hasattr(function, '__code__')}
        self._limit, self._lock = metadata_limit, RLock()
        self._configured_limit = metadata_limit
        self._admission_lock = admission._lock
        self._receipt_function = klass.receipt
        self._records, self._fault = {}, None
        self._metadata_emitted = self._tool_emitted = 0
        self._initialized = False
        self._catalog_validated = False
        self._required_tools = frozenset(request['name'] for request in (*admission._cad, *admission._observations))
        if admission._target_poll_limit:
            self._required_tools |= {'job_get'}
        self._initialize_key = self._list_key = None
        self._write_live = False
        with admission._lock:
            require(not hasattr(admission, '_dimension_protocol_bridge'), 'No concurrent bridge adoption.')
            admission._dimension_protocol_bridge = self

    def _identity(self):
        require(self.module.DimensionAdmission is self.klass and Path(self.module.__file__).resolve() == _path
                and type(self.admission) is self.klass and self.admission._dimension_protocol_bridge is self
                and self.admission._lock is self._admission_lock,
                'Original bridge/admission binding changed.')
        require(type(self._limit) is int and self._limit == self._configured_limit, 'Original finite metadata budget changed.')
        for name, code in self._codes.items():
            function, bound = getattr(self.klass, name), getattr(self.admission, name)
            require(getattr(function, '__code__', None) is code and getattr(bound, '__self__', None) is self.admission
                    and getattr(bound, '__func__', None) is function, 'Original admission callback changed.')

    def _fail(self, error):
        if self._fault is None:
            self._fault = type(error).__name__ + ': ' + str(error)
        # Closing the original primitive gate must not invoke a callback whose
        # identity was just rejected. No execution/transport is retried here.
        with self._admission_lock:
            self.admission._closed = True
        raise ProtocolBridgeError(self._fault) from error

    def write_message(self, message, write, flush):
        with self._lock:
            try:
                self._identity()
                require(self._fault is None, 'Failed bridge cannot send again.')
                require(isinstance(message, JSONRPCMessage), 'Actual typed MCP message required.')
                raw = message.model_dump(mode='json', by_alias=True, exclude_none=True)
                require(raw.get('jsonrpc') == '2.0', 'Exact JSON-RPC required.')
                method = raw.get('method')
                if method == 'notifications/initialized':
                    require(set(raw) <= {'jsonrpc', 'method', 'params'} and raw.get('params', {}) == {}
                            and not self._initialized and self._initialize_key in self._records
                            and self._records[self._initialize_key]['response_observed'], 'Original initialization reply required.')
                    key = None
                else:
                    require(set(raw) in ({'jsonrpc', 'id', 'method'}, {'jsonrpc', 'id', 'method', 'params'}),
                            'Exact request envelope required.')
                    require(type(raw.get('id')) in (int, str), 'Exact request identity required.')
                    key = (type(raw['id']).__name__, raw['id'])
                    require(key not in self._records, 'RPC identities never repeat across metadata/CAD.')
                if method == 'tools/call':
                    require(self._initialized and self._catalog_validated,
                            'Original initialization and complete typed catalog required before tool requests.')
                    self._records[key] = dict(kind='tool', method=method, response_observed=False)
                    self._write_live = True
                    try:
                        result = self.admission.write_message(message, write, flush)
                    finally:
                        self._write_live = False
                    self._tool_emitted += 1
                    return deepcopy(result)
                require(method in ('initialize', 'notifications/initialized', 'tools/list')
                        and self._metadata_emitted < self._limit, 'Only finite initialize/list metadata admitted.')
                if method == 'initialize':
                    require(self._initialize_key is None and not self._initialized and type(raw.get('params')) is dict,
                            'Initialize once on this original bridge.')
                    self._initialize_key = key
                elif method == 'tools/list':
                    require(self._initialized and self._list_key is None and raw.get('params', {}) == {},
                            'One complete uncursored tool list required.')
                    self._list_key = key
                if key is not None:
                    self._records[key] = dict(kind='metadata', method=method, response_observed=False)
                payload = message.model_dump_json(by_alias=True, exclude_none=True).encode('utf8') + b'\n'
                self._write_live = True
                try:
                    require(type(count := _sync(write, payload)) is int and count == len(payload), 'Complete original metadata write required.')
                    require(_sync(flush) is None, 'Normal original metadata flush required.')
                finally:
                    self._write_live = False
                self._metadata_emitted += 1
                if method == 'notifications/initialized':
                    self._initialized = True
                return dict(emitted=True, metadata=True)
            except Exception as error:
                self._fail(error)

    def observe_response(self, message):
        with self._lock:
            try:
                self._identity()
                require(isinstance(message, JSONRPCMessage), 'Actual typed MCP response required.')
                raw = message.model_dump(mode='json', by_alias=True, exclude_none=True)
                require(raw.get('jsonrpc') == '2.0' and type(raw.get('id')) in (int, str)
                        and 'method' not in raw and ('result' in raw) != ('error' in raw), 'Exact reply identity required.')
                key = (type(raw['id']).__name__, raw['id'])
                require(key in self._records and not self._records[key]['response_observed'], 'Original unseen reply required.')
                record = self._records[key]
                if record['kind'] == 'tool':
                    result = self.admission.observe_response(message)
                else:
                    require(self._fault is None and type(raw.get('result')) is dict,
                            'Original successful metadata reply required.')
                    if record['method'] == 'initialize':
                        InitializeResult.model_validate(raw['result'], strict=True)
                    else:
                        catalog = ListToolsResult.model_validate(raw['result'], strict=True)
                        names = [tool.name for tool in catalog.tools]
                        require(catalog.nextCursor is None and len(names) == len(set(names))
                                and self._required_tools <= set(names)
                                and all(type(tool.outputSchema) is dict and bool(tool.outputSchema) for tool in catalog.tools),
                                'Complete unique typed catalog must contain every planned tool with output schema.')
                        self._catalog_validated = True
                    result = dict(metadata=True, method=record['method'])
                record['response_observed'] = True
                return deepcopy(result)
            except Exception as error:
                self._fail(error)

    def close_admission(self):
        with self._lock:
            try:
                self._identity()
                with self._admission_lock:
                    self.admission._closed = True
                return self.receipt()
            except Exception as error:
                self._fail(error)

    def receipt(self):
        with self._lock:
            require(self.admission._lock is self._admission_lock
                    and self._receipt_function.__code__ is self._codes['receipt'],
                    'Original passive admission receipt required.')
            return dict(scope='b4_dimension_protocol_bridge_v1', protocol_fault=self._fault,
                initialized=self._initialized, metadata_emitted=self._metadata_emitted,
                catalog_validated=self._catalog_validated,
                tool_emitted=self._tool_emitted, write_live=self._write_live,
                records=[dict(rpc_type=key[0], rpc_id=key[1], **deepcopy(row)) for key, row in self._records.items()],
                admission=self._receipt_function(self.admission), accepted=False,
                native_q='not_run', native_admission='not_run', process_stop_authorized=False,
                restart_authorized=False, cad_cleanup_authorized=False)
