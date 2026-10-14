"""Actual admission/JobStore with typed MCP and artificial byte pipes only."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from threading import Event, RLock, Thread
from types import ModuleType, SimpleNamespace

from mcp.types import JSONRPCMessage, LATEST_PROTOCOL_VERSION
import pytest

from test_b4_native_admission import (
    SET, TARGET, controller, envelope, helper as admission_module,
    poll, real_job, request, write_to,
)
from test_b4_dimension_return import prepared
from test_dimension_domain_v2 import setup
from test_b4_dimension_control_commands import (
    arm_args, command, control_owner, receiver, helper as command_receiver_module)
from test_b4_dimension_command_host import helper as host_module, observed as observe_host
from test_b4_installed_dimension_control import helper as controller_module


spec = importlib.util.spec_from_file_location(
    '_b4_protocol_bridge_tests', Path(__file__).resolve().parents[1] /
    'scripts' / 'verifier_b4_dimension_protocol_bridge.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def initialize(rpc_id='initialize'):
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=rpc_id, method='initialize',
        params=dict(protocolVersion=LATEST_PROTOCOL_VERSION, capabilities={},
                    clientInfo=dict(name='pure-original-bridge', version='1'))))


def initialization_reply(rpc_id='initialize'):
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=rpc_id, result=dict(
        protocolVersion=LATEST_PROTOCOL_VERSION, capabilities={'tools': {}},
        serverInfo=dict(name='pure-protocol-fixture', version='1'))))


def initialized():
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', method='notifications/initialized'))


def tool_list(rpc_id='catalog', params=None):
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=rpc_id, method='tools/list',
                                            params={} if params is None else params))


def catalog_reply(rpc_id='catalog'):
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=rpc_id, result={'tools': [dict(
        name=name, inputSchema={'type': 'object'}, outputSchema={'type': 'object'})
        for name in ('dimension_set_value', 'dimension_get', 'system_get_info', 'job_get')]}))


def bridge(current=None, *, metadata_limit=3):
    return helper.DimensionProtocolBridge(
        controller() if current is None else current,
        admission_module=admission_module, metadata_limit=metadata_limit)


def ready(current=None, *, initialize_id='initialize', list_id='catalog'):
    value, pipe = bridge(current), []
    value.write_message(initialize(initialize_id), write_to(pipe), lambda: None)
    value.observe_response(initialization_reply(initialize_id))
    value.write_message(initialized(), write_to(pipe), lambda: None)
    value.write_message(tool_list(list_id), write_to(pipe), lambda: None)
    value.observe_response(catalog_reply(list_id))
    return value, pipe


def no_authority(value):
    assert value['accepted'] is False
    assert value['native_q'] == value['native_admission'] == 'not_run'
    for name in ('process_stop_authorized', 'restart_authorized', 'cad_cleanup_authorized'):
        assert value[name] is False
    json.dumps(value, ensure_ascii=False, allow_nan=False)


def assert_transport_only(value):
    receipt = value.receipt()
    no_authority(receipt)
    no_authority(receipt['admission'])
    assert receipt['write_live'] is False
    return receipt


def test_original_initialize_reply_notification_uncursored_list_and_exact_admitted_call(real_job):
    store, oid = real_job
    current = controller(observations=(), target_poll_limit=2)
    value, pipe = ready(current)
    assert type(value.admission) is admission_module.DimensionAdmission
    assert value.module is admission_module
    receipt = assert_transport_only(value)
    assert receipt['initialized'] is True and receipt['metadata_emitted'] == 3
    assert receipt['catalog_validated'] is True
    assert receipt['tool_emitted'] == receipt['admission']['attempted'] == 0
    assert [JSONRPCMessage.model_validate_json(raw).root.method for raw in pipe] == [
        'initialize', 'notifications/initialized', 'tools/list']
    assert all(raw.endswith(b'\n') for raw in pipe)
    sent = value.write_message(request(SET, 'target'), write_to(pipe), lambda: None)
    assert sent['emitted'] is True
    assert JSONRPCMessage.model_validate_json(pipe[-1]) == request(SET, 'target')
    observed = value.observe_response(envelope(store.get(oid), 'target', mutation_reply=True))
    assert observed['response_observed'] is observed['response_validated'] is True
    receipt = assert_transport_only(value)
    binding = receipt['admission']['target_job_observation_binding']
    assert binding == dict(scope='b4_transport_target_job_binding_v1', operation_id=oid,
        rpc_id='target', request_id=SET['arguments']['request_id'], operation='dimension.set_value',
        payload=TARGET, transport_only=True)
    assert receipt['tool_emitted'] == receipt['admission']['cad_emitted'] == 1
    assert receipt['admission']['admission_closed'] is True  # Actual queued JobStore response.
    assert store.get(oid)['status'] == 'queued'
    assert receipt['records'] == [
        dict(rpc_type='str', rpc_id='initialize', kind='metadata', method='initialize', response_observed=True),
        dict(rpc_type='str', rpc_id='catalog', kind='metadata', method='tools/list', response_observed=True),
        dict(rpc_type='str', rpc_id='target', kind='tool', method='tools/call', response_observed=True)]
    receipt['records'][0]['response_observed'] = False
    receipt['admission']['target_payload']['arguments']['value'] = 99.
    assert value.receipt()['records'][0]['response_observed'] is True
    assert value.receipt()['admission']['target_payload'] == TARGET


def bound(real_job, *, limit=2):
    store, oid = real_job
    value, pipe = ready(controller(observations=(), target_poll_limit=limit))
    value.write_message(request(SET, 'target'), write_to(pipe), lambda: None)
    value.observe_response(envelope(store.get(oid), 'target', mutation_reply=True))
    return value, pipe


def test_actual_bound_job_polls_after_close_are_serial_finite_and_transport_only(real_job):
    store, oid = real_job
    value, pipe = bound(real_job)
    first_close = value.close_admission()
    assert first_close['admission']['admission_closed'] is True
    value.write_message(poll(oid, 'poll-1'), write_to(pipe), lambda: None)
    assert value.observe_response(envelope(store.get(oid), 'poll-1'))['server_status'] == 'queued'
    store.start(oid)
    value.write_message(poll(oid, 'poll-2'), write_to(pipe), lambda: None)
    assert value.observe_response(envelope(store.get(oid), 'poll-2'))['server_status'] == 'running'
    receipt = assert_transport_only(value)
    assert receipt['admission']['target_poll_emitted'] == 2
    assert receipt['admission']['in_flight_observations'] == 0
    assert len(pipe) == 6  # Three metadata, original mutation, two bounded polls.
    with pytest.raises(helper.ProtocolBridgeError, match='budget exhausted'):
        value.write_message(poll(oid, 'poll-3'), write_to(pipe), lambda: None)
    assert len(pipe) == 6
    failed = assert_transport_only(value)
    assert failed['protocol_fault'] and failed['admission']['target_poll_emitted'] == 2
    assert failed['admission']['target_job_observation_binding'] == receipt['admission']['target_job_observation_binding']


@pytest.mark.parametrize('kind', ['overlap', 'foreign_target', 'disabled'])
def test_bridge_keeps_actual_admission_target_poll_restrictions(real_job, kind):
    store, oid = real_job
    value, pipe = bound(real_job, limit=0 if kind == 'disabled' else 2)
    if kind == 'overlap':
        value.write_message(poll(oid, 'first-poll'), write_to(pipe), lambda: None)
        attempted = poll(oid, 'second-poll')
    elif kind == 'foreign_target':
        attempted = poll('job_' + 'f' * 32, 'foreign-poll')
    else:
        attempted = poll(oid, 'disabled-poll')
    before = list(pipe)
    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(attempted, write_to(pipe), lambda: None)
    assert pipe == before
    receipt = assert_transport_only(value)
    assert receipt['protocol_fault'] and receipt['admission']['admission_closed']
    if kind == 'disabled':
        assert receipt['admission']['target_job_observation_binding'] == 'not_run'


@pytest.mark.parametrize('change', ['request', 'payload', 'context', 'oid', 'status', 'extra_dto'])
def test_real_job_poll_dto_drift_is_rejected_by_original_admission(real_job, change):
    store, oid = real_job
    value, pipe = bound(real_job)
    value.write_message(poll(oid, 'poll'), write_to(pipe), lambda: None)
    raw = envelope(store.get(oid), 'poll').model_dump(mode='json')
    outer, row = raw['result']['structuredContent'], raw['result']['structuredContent']['data']
    if change == 'request':
        row['request_id'] = 'foreign'
    elif change == 'payload':
        row['payload']['arguments']['value'] = 13.
    elif change == 'context':
        outer['context']['configuration'] = 'foreign'
    elif change == 'oid':
        row['operation_id'] = 'job_' + 'e' * 32
    elif change == 'status':
        outer['status'] = 'succeeded'
    else:
        row['digest'] = 'non-public'
    with pytest.raises(helper.ProtocolBridgeError):
        value.observe_response(JSONRPCMessage.model_validate(raw))
    receipt = assert_transport_only(value)
    assert receipt['admission']['target_poll_failed'] and receipt['protocol_fault']
    assert store.get(oid)['status'] == 'queued'
    before = list(pipe)
    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(poll(oid, 'next'), write_to(pipe), lambda: None)
    assert pipe == before


@pytest.mark.parametrize('collision', ['initialize', 'catalog'])
def test_metadata_and_cad_rpc_identity_collisions_refuse_without_wire_write(collision):
    value, pipe = ready()
    before = list(pipe)
    with pytest.raises(helper.ProtocolBridgeError, match='identities never repeat'):
        value.write_message(request(SET, collision), write_to(pipe), lambda: None)
    assert pipe == before
    receipt = assert_transport_only(value)
    assert receipt['admission']['attempted'] == 0
    assert receipt['admission']['admission_closed'] is True


def test_int_and_string_rpc_identity_are_distinct_across_metadata_and_cad(real_job):
    store, oid = real_job
    value, pipe = ready(controller(target_poll_limit=1), initialize_id=7)
    value.write_message(request(SET, '7'), write_to(pipe), lambda: None)
    value.observe_response(envelope(store.get(oid), '7', mutation_reply=True))
    receipt = assert_transport_only(value)
    assert (receipt['records'][0]['rpc_type'], receipt['records'][0]['rpc_id']) == ('int', 7)
    assert (receipt['records'][-1]['rpc_type'], receipt['records'][-1]['rpc_id']) == ('str', '7')
    assert receipt['admission']['target_job_observation_binding']['rpc_id'] == '7'


@pytest.mark.parametrize('reply_kind', ['duplicate_initialize', 'duplicate_catalog', 'foreign'])
def test_metadata_duplicate_or_foreign_reply_permanently_faults_bridge(reply_kind):
    value, pipe = ready()
    message = (initialization_reply() if reply_kind == 'duplicate_initialize' else
               catalog_reply() if reply_kind == 'duplicate_catalog' else initialization_reply('foreign'))
    with pytest.raises(helper.ProtocolBridgeError, match='unseen reply'):
        value.observe_response(message)
    before = list(pipe)
    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(request(SET, 'target'), write_to(pipe), lambda: None)
    assert pipe == before
    assert assert_transport_only(value)['admission']['attempted'] == 0


def test_duplicate_tool_reply_cannot_replace_bound_actual_job(real_job):
    store, oid = real_job
    value, pipe = bound(real_job)
    original_binding = deepcopy(value.receipt()['admission']['target_job_observation_binding'])
    raw = envelope(store.get(oid), 'target', mutation_reply=True).model_dump(mode='json')
    raw['result']['structuredContent']['operation_id'] = 'job_' + 'f' * 32
    with pytest.raises(helper.ProtocolBridgeError, match='unseen reply'):
        value.observe_response(JSONRPCMessage.model_validate(raw))
    assert value.receipt()['admission']['target_job_observation_binding'] == original_binding
    assert len(pipe) == 4
    assert_transport_only(value)


@pytest.mark.parametrize('attempt', ['cad', 'list', 'notification'])
def test_uninitialized_requests_are_rejected_before_physical_writer(attempt):
    value, pipe = bridge(), []
    message = request(SET) if attempt == 'cad' else tool_list() if attempt == 'list' else initialized()
    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(message, write_to(pipe), lambda: None)
    assert pipe == []
    assert assert_transport_only(value)['admission']['attempted'] == 0


def test_initialization_notification_requires_original_observed_reply():
    value, pipe = bridge(), []
    value.write_message(initialize(), write_to(pipe), lambda: None)
    with pytest.raises(helper.ProtocolBridgeError, match='initialization reply required'):
        value.write_message(initialized(), write_to(pipe), lambda: None)
    assert len(pipe) == 1
    receipt = assert_transport_only(value)
    assert receipt['initialized'] is False and receipt['records'][0]['response_observed'] is False


@pytest.mark.parametrize('field', ['protocolVersion', 'capabilities', 'serverInfo'])
def test_malformed_initialize_result_is_rejected_by_actual_mcp_schema(field):
    value, pipe = bridge(), []
    value.write_message(initialize(), write_to(pipe), lambda: None)
    raw = initialization_reply().model_dump(mode='json')
    raw['result'].pop(field)
    with pytest.raises(helper.ProtocolBridgeError):
        value.observe_response(JSONRPCMessage.model_validate(raw))
    receipt = assert_transport_only(value)
    assert receipt['initialized'] is False and receipt['catalog_validated'] is False
    assert receipt['records'][0]['response_observed'] is False
    assert len(pipe) == 1


@pytest.mark.parametrize('change', ['missing_tool', 'missing_poll_tool', 'duplicate_name',
                                   'no_output_schema', 'empty_output_schema', 'cursor', 'malformed_tools'])
def test_missing_malformed_or_cursored_catalog_cannot_admit_cad(change):
    value, pipe = bridge(controller(observations=(), target_poll_limit=1)), []
    value.write_message(initialize(), write_to(pipe), lambda: None)
    value.observe_response(initialization_reply())
    value.write_message(initialized(), write_to(pipe), lambda: None)
    value.write_message(tool_list(), write_to(pipe), lambda: None)
    raw = catalog_reply().model_dump(mode='json')
    tools = raw['result']['tools']
    if change == 'missing_tool':
        raw['result']['tools'] = [tool for tool in tools if tool['name'] != 'dimension_set_value']
    elif change == 'missing_poll_tool':
        raw['result']['tools'] = [tool for tool in tools if tool['name'] != 'job_get']
    elif change == 'duplicate_name':
        tools.append(deepcopy(tools[0]))
    elif change == 'no_output_schema':
        tools[0].pop('outputSchema')
    elif change == 'empty_output_schema':
        tools[0]['outputSchema'] = {}
    elif change == 'cursor':
        raw['result']['nextCursor'] = 'more-tools'
    else:
        raw['result']['tools'] = {'foreign': True}
    with pytest.raises(helper.ProtocolBridgeError):
        value.observe_response(JSONRPCMessage.model_validate(raw))
    receipt = assert_transport_only(value)
    assert receipt['catalog_validated'] is False and receipt['tool_emitted'] == 0
    assert receipt['admission']['attempted'] == 0
    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(request(SET, 'target'), write_to(pipe), lambda: None)
    assert len(pipe) == 3


@pytest.mark.parametrize('list_sent', [False, True])
def test_initialized_without_original_validated_catalog_cannot_write_tools(list_sent):
    value, pipe = bridge(), []
    value.write_message(initialize(), write_to(pipe), lambda: None)
    value.observe_response(initialization_reply())
    value.write_message(initialized(), write_to(pipe), lambda: None)
    if list_sent:
        value.write_message(tool_list(), write_to(pipe), lambda: None)
    before = list(pipe)
    with pytest.raises(helper.ProtocolBridgeError, match='complete typed catalog'):
        value.write_message(request(SET, 'target'), write_to(pipe), lambda: None)
    assert pipe == before
    assert assert_transport_only(value)['admission']['attempted'] == 0


@pytest.mark.parametrize('change', ['cursor', 'extra_params', 'second_list', 'second_initialize', 'second_notification'])
def test_only_one_uncursored_metadata_exchange_is_admitted(change):
    value, pipe = ready()
    message = (tool_list('next', {'cursor': 'foreign'}) if change == 'cursor' else
               tool_list('next', {'extra': True}) if change == 'extra_params' else
               tool_list('next') if change == 'second_list' else
               initialize('next') if change == 'second_initialize' else initialized())
    before = list(pipe)
    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(message, write_to(pipe), lambda: None)
    assert pipe == before
    assert_transport_only(value)


@pytest.mark.parametrize('layer', ['metadata', 'cad'])
@pytest.mark.parametrize('failure', ['partial', 'write_throw', 'bool_ack', 'flush_throw', 'flush_ack'])
def test_unknown_write_flush_cannot_resend_late_reply_or_close_into_success(real_job, layer, failure):
    store, oid = real_job
    value, pipe = (bridge(controller(target_poll_limit=1)), []) if layer == 'metadata' else ready(
        controller(target_poll_limit=1))
    message = initialize() if layer == 'metadata' else request(SET, 'target')
    before = len(pipe)

    def write(payload):
        pipe.append(payload[:-1] if failure == 'partial' else payload)
        if failure == 'write_throw':
            raise OSError('Own artificial byte write failed')
        return True if failure == 'bool_ack' else len(payload) - 1 if failure == 'partial' else len(payload)

    def flush():
        if failure == 'flush_throw':
            raise OSError('Own artificial flush unknown')
        return False if failure == 'flush_ack' else None

    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(message, write, flush)
    receipt = assert_transport_only(value)
    assert receipt['protocol_fault'] and receipt['tool_emitted'] == 0
    assert len(pipe) == before + 1
    assert receipt['admission']['emitted'] == 0
    if layer == 'cad':
        assert receipt['admission']['unknown_transport'] is True
        assert receipt['admission']['records'][0]['write_state'] == 'unknown'
    else:
        assert receipt['metadata_emitted'] == 0
        assert receipt['admission']['attempted'] == 0
    late = initialization_reply() if layer == 'metadata' else envelope(store.get(oid), 'target', mutation_reply=True)
    with pytest.raises(helper.ProtocolBridgeError):
        value.observe_response(late)
    for rpc_id in ('target', 'new-target'):
        with pytest.raises(helper.ProtocolBridgeError):
            value.write_message(request(SET, rpc_id), write_to(pipe), lambda: None)
    assert len(pipe) == before + 1
    closed = value.close_admission()
    assert closed['protocol_fault'] == receipt['protocol_fault']
    assert closed['admission']['emitted'] == 0
    assert closed['admission']['target_job_observation_binding'] == 'not_run'
    no_authority(closed)


def test_close_waits_for_original_pending_tool_write_without_adopting_or_interrupting(real_job):
    value, pipe = ready(controller(target_poll_limit=1))
    entered, release, close_started, close_returned = Event(), Event(), Event(), Event()
    errors, closed = [], []

    def write(payload):
        entered.set()
        assert release.wait(5)
        pipe.append(payload)
        return len(payload)

    def writer():
        try:
            value.write_message(request(SET, 'target'), write, lambda: None)
        except BaseException as error:
            errors.append(error)

    def closer():
        close_started.set()
        try:
            closed.append(value.close_admission())
        except BaseException as error:
            errors.append(error)
        finally:
            close_returned.set()

    sending, closing = Thread(target=writer), Thread(target=closer)
    sending.start()
    assert entered.wait(5)
    closing.start()
    try:
        assert close_started.wait(5) and not close_returned.wait(.02)
        assert value._write_live is True
    finally:
        release.set()
        sending.join(5)
        closing.join(5)
    assert not sending.is_alive() and not closing.is_alive() and errors == []
    assert len(closed) == 1 and close_returned.is_set()
    receipt = assert_transport_only(value)
    assert receipt['admission']['admission_closed'] is True
    assert receipt['tool_emitted'] == receipt['admission']['emitted'] == 1
    assert receipt['admission']['records'][0]['write_state'] == 'emitted'
    assert receipt['admission']['records'][0]['response_observed'] is False
    assert receipt['admission']['target_job_observation_binding'] == 'not_run'
    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(request(SET, 'next'), write_to(pipe), lambda: None)
    assert len(pipe) == 4


@pytest.mark.parametrize('change', ['module_path', 'module_class', 'class_method', 'instance_callback',
                                   'bridge_binding', 'admission_lock', 'metadata_budget'])
def test_original_module_callback_or_primitive_binding_drift_faults_before_write(monkeypatch, change):
    value, pipe = ready()
    current = value.admission
    if change == 'module_path':
        monkeypatch.setattr(admission_module, '__file__', str(Path(__file__).with_name('foreign.py')))
    elif change == 'module_class':
        monkeypatch.setattr(admission_module, 'DimensionAdmission', type('ForeignAdmission', (), {}))
    elif change == 'class_method':
        monkeypatch.setattr(type(current), 'write_message', lambda *args: pytest.fail('Changed class entered write'))
    elif change == 'instance_callback':
        current.write_message = lambda *args: pytest.fail('Changed instance entered write')
    elif change == 'bridge_binding':
        current._dimension_protocol_bridge = object()
    elif change == 'metadata_budget':
        value._limit = 8
    else:
        current._lock = RLock()
    before = list(pipe)
    with pytest.raises(helper.ProtocolBridgeError):
        value.write_message(request(SET, 'target'), write_to(pipe), lambda: None)
    assert pipe == before and current._closed is True
    assert current._attempted == current._emitted == 0
    assert value._fault


@pytest.mark.parametrize('limit', [True, 1, 9, 3., '3', None])
def test_metadata_budget_is_original_finite_integer(limit):
    current = controller()
    with pytest.raises(helper.ProtocolBridgeError, match='budget 2..8'):
        bridge(current, metadata_limit=limit)
    assert not hasattr(current, '_dimension_protocol_bridge')


def test_two_message_budget_does_not_dispatch_a_third_metadata_message():
    value, pipe = bridge(metadata_limit=2), []
    value.write_message(initialize(), write_to(pipe), lambda: None)
    value.observe_response(initialization_reply())
    value.write_message(initialized(), write_to(pipe), lambda: None)
    with pytest.raises(helper.ProtocolBridgeError, match='finite initialize/list'):
        value.write_message(tool_list(), write_to(pipe), lambda: None)
    assert len(pipe) == 2
    assert assert_transport_only(value)['metadata_emitted'] == 2


def test_second_bridge_cannot_adopt_original_admission_or_reset_budget():
    current = controller()
    first = bridge(current)
    with pytest.raises(helper.ProtocolBridgeError, match='One original bridge'):
        bridge(current)
    assert current._dimension_protocol_bridge is first
    assert current.receipt()['attempted'] == 0


@pytest.mark.parametrize('change', ['module_shape', 'module_path', 'admission_shape', 'implementation'])
def test_constructor_requires_exact_original_module_and_admission(monkeypatch, change):
    current, module = controller(), admission_module
    if change == 'module_shape':
        module = SimpleNamespace(__file__=admission_module.__file__, DimensionAdmission=type(current))
    elif change == 'module_path':
        module = ModuleType('foreign_admission')
        module.__file__ = str(Path(__file__).with_name('foreign.py'))
        module.DimensionAdmission = type(current)
    elif change == 'admission_shape':
        current = SimpleNamespace(_lock=RLock())
    else:
        monkeypatch.setattr(type(current), 'write_message', lambda *args: pytest.fail('Changed callback executed'))
    with pytest.raises(helper.ProtocolBridgeError, match='original admission|implementation'):
        helper.DimensionProtocolBridge(current, admission_module=module)
    assert not hasattr(current, '_dimension_protocol_bridge')


def test_actual_client_session_memory_sdk_envelopes_original_bridge_runtime_and_bounded_poll(prepared):
    """Actual SDK wire shapes/FastMCP/domain/SQLite, source-only artificial CAD."""
    from datetime import timedelta

    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams
    from mcp.shared.message import SessionMessage
    from solidworks_mcp.server_v2 import create_app

    runtime, store = prepared.runtime, prepared.store
    target = dict(name='dimension_set_value', arguments=dict(
        prepared.payload['arguments'], request_id='sdk-original-dimension', timeout_s=0.))
    current = admission_module.DimensionAdmission(
        cad_requests=(target,), observation_requests=(), target_operation='dimension.set_value',
        target_payload=prepared.payload, target_poll_limit=2)
    value = bridge(current)
    app = create_app(store, runtime)
    wire, original_sdk_messages, response_messages, flushes = [], [], [], []
    original = (runtime, runtime._catalog, runtime._dimensions, prepared.adapter, prepared.catalog)

    class BridgeIncoming:
        def __init__(self, stream):
            self.stream = stream

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.stream.aclose()

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return await self.receive()
            except anyio.EndOfStream:
                raise StopAsyncIteration

        async def receive(self):
            incoming = await self.stream.receive()
            assert isinstance(incoming, SessionMessage)
            original_sdk_messages.append(incoming.message.model_dump(mode='json', by_alias=True))
            emitted = []

            def physical_write(payload):
                assert type(payload) is bytes
                emitted.append(payload)
                wire.append(payload)
                return len(payload)

            def physical_flush():
                flushes.append(len(wire))

            value.write_message(incoming.message, physical_write, physical_flush)
            assert len(emitted) == 1
            # Deliver the actual admitted bytes, not a replacement manual RPC.
            return SessionMessage(message=JSONRPCMessage.model_validate_json(emitted[0]),
                                  metadata=incoming.metadata)

    class BridgeOutgoing:
        def __init__(self, stream):
            self.stream = stream

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.stream.aclose()

        async def send(self, outgoing):
            assert isinstance(outgoing, SessionMessage)
            response_messages.append(outgoing.message)
            value.observe_response(outgoing.message)
            await self.stream.send(outgoing)

    async def scenario():
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            client_read, client_write = client_streams
            server_read, server_write = server_streams
            server = app._mcp_server
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(lambda: server.run(
                    BridgeIncoming(server_read), BridgeOutgoing(server_write),
                    server.create_initialization_options(), raise_exceptions=True))
                try:
                    async with ClientSession(client_read, client_write,
                                             read_timeout_seconds=timedelta(seconds=5)) as sdk:
                        initialized_result = await sdk.initialize()
                        assert initialized_result.protocolVersion == LATEST_PROTOCOL_VERSION
                        catalog = await sdk.list_tools()
                        assert catalog.nextCursor is None
                        assert {'dimension_set_value', 'job_get'} <= {tool.name for tool in catalog.tools}
                        assert value.receipt()['catalog_validated'] is True
                        changed = await sdk.call_tool('dimension_set_value', target['arguments'])
                        assert changed.isError is False
                        assert changed.structuredContent['status'] == 'succeeded'
                        oid = changed.structuredContent['operation_id']
                        assert oid.startswith('job_')
                        binding = value.receipt()['admission']['target_job_observation_binding']
                        assert binding['operation_id'] == oid and binding['payload'] == prepared.payload
                        assert binding['request_id'] == 'sdk-original-dimension' and binding['transport_only'] is True
                        polled = await sdk.call_tool('job_get', {'operation_id': oid})
                        assert polled.isError is False
                        dto = polled.structuredContent['data']
                        assert polled.structuredContent['status'] == dto['status'] == 'succeeded'
                        assert dto == store.get(oid)
                        assert dto['operation'] == 'dimension.set_value'
                        assert dto['mutation']['phase'] == 'committed'
                        assert dto['result']['verified'] is True
                        assert len(store.list()['items']) == 1
                        return oid
                finally:
                    # Only the source in-memory SDK listener tasks finish here;
                    # no process, CAD job or native owner exists in this fixture.
                    tasks.cancel_scope.cancel()

    oid = anyio.run(scenario)
    assert original == (runtime, runtime._catalog, runtime._dimensions, prepared.adapter, prepared.catalog)
    assert store.get(oid)['status'] == 'succeeded'
    assert len(prepared.adapter.dimension_writes) == len(prepared.guards) == 1
    assert prepared.application.CommandInProgress is False
    assert runtime._closed is False
    receipt = assert_transport_only(value)
    assert receipt['protocol_fault'] is None and receipt['initialized'] is True
    assert receipt['catalog_validated'] is True and receipt['metadata_emitted'] == 3
    assert receipt['tool_emitted'] == receipt['admission']['emitted'] == 2
    assert receipt['admission']['cad_emitted'] == 1
    assert receipt['admission']['target_poll_emitted'] == 1
    assert receipt['admission']['in_flight_cad'] == receipt['admission']['in_flight_observations'] == 0
    assert len(wire) == len(flushes) == 5 and len(response_messages) == 4
    assert [raw['method'] for raw in original_sdk_messages] == [
        'initialize', 'notifications/initialized', 'tools/list', 'tools/call', 'tools/call']
    for method in ('notifications/initialized', 'tools/list'):
        original_message = next(raw for raw in original_sdk_messages if raw['method'] == method)
        assert original_message.get('params') is None
        wire_message = next(json.loads(raw) for raw in wire if json.loads(raw)['method'] == method)
        assert 'params' not in wire_message
    assert json.loads(wire[-2])['params']['arguments']['timeout_s'] == 0.
    closed = value.close_admission()
    assert closed['admission']['admission_closed'] is True
    assert closed['admission']['target_job_observation_binding']['operation_id'] == oid
    no_authority(closed)


def test_actual_sdk_queued_reply_original_held_finish_two_polls_atomic_release_and_normal_close(control_owner):
    """Source SDK N3 late-result flow; original PythonWorker/fake CAD, never native Q."""
    from datetime import timedelta

    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams
    from mcp.shared.message import SessionMessage
    from solidworks_mcp.server_v2 import create_app

    owner = control_owner
    runtime, proxy, control = owner.runtime, owner.proxy, owner.control
    commands = receiver(owner, 3)
    host = host_module.DimensionCommandHost(
        commands, command_module=command_receiver_module, poll_interval_s=.001)
    arm_arguments = arm_args(owner)
    target = dict(name='dimension_set_value', arguments=dict(
        owner.payload['arguments'], request_id=arm_arguments['request_id'], timeout_s=0.))
    current = admission_module.DimensionAdmission(
        cad_requests=(target,), observation_requests=(), target_operation='dimension.set_value',
        target_payload=owner.payload, target_poll_limit=2)
    value = bridge(current)
    app = create_app(proxy, runtime)
    original = (runtime._runner, runtime._catalog, runtime._dimensions, proxy._store,
                control.seam, owner.prepared.adapter)
    original_factories = control.seam._original_store, control.seam._original_runtime
    original_rows = controller_module.finished._barrier._read_journal(proxy.path)
    wire, flushes, replies = [], [], []

    class Endpoint:
        def __init__(self, stream):
            self.stream = stream

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.stream.aclose()

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                incoming = await self.stream.receive()
            except anyio.EndOfStream:
                raise StopAsyncIteration
            assert isinstance(incoming, SessionMessage)
            sent = []

            def write(payload):
                assert type(payload) is bytes
                wire.append(payload)
                sent.append(payload)
                return len(payload)

            def flush():
                flushes.append(len(wire))

            value.write_message(incoming.message, write, flush)
            assert len(sent) == 1
            return SessionMessage(message=JSONRPCMessage.model_validate_json(sent[0]),
                                  metadata=incoming.metadata)

        async def send(self, outgoing):
            assert isinstance(outgoing, SessionMessage)
            value.observe_response(outgoing.message)
            replies.append(outgoing.message)
            await self.stream.send(outgoing)

    async def scenario():
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            server = app._mcp_server
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(lambda: server.run(
                    Endpoint(server_streams[0]), Endpoint(server_streams[1]),
                    server.create_initialization_options(), raise_exceptions=True))
                try:
                    async with ClientSession(*client_streams,
                                             read_timeout_seconds=timedelta(seconds=5)) as sdk:
                        await sdk.initialize()
                        catalog = await sdk.list_tools()
                        assert catalog.nextCursor is None and value.receipt()['catalog_validated'] is True
                        changed = await sdk.call_tool('dimension_set_value', target['arguments'])
                        assert changed.isError is False
                        first = changed.structuredContent
                        assert first['status'] in ('queued', 'running')
                        oid = first['operation_id']
                        binding = value.receipt()['admission']['target_job_observation_binding']
                        assert binding['operation_id'] == oid and binding['transport_only'] is True
                        assert binding['payload'] == owner.payload
                        assert proxy.wait_reached(5), control.inspect_state()
                        held = control.inspect_state()
                        callback = controller_module.owned._read(owner.root / 'callback-return.json')
                        finish = controller_module.owned._read(owner.root / 'finish-barrier.json')
                        assert held['barrier_state'] == 'waiting'
                        assert held['return_observation']['callback_live'] is False
                        assert held['return_observation']['persisted'] is True
                        assert callback['journal'] == finish['journal']
                        assert callback['original_receipt']['operation_id'] == finish['original_receipt']['operation_id'] == oid
                        assert callback['original_receipt']['return_result'] == finish['original_receipt']['return_result']
                        assert callback['lineage'] == finish['lineage'] == owner.lineage
                        assert callback['target'] == finish['target'] == control.target
                        assert len(owner.prepared.adapter.dimension_writes) == 1
                        assert owner.prepared.application.CommandInProgress is False
                        for receipt in (held, callback, finish):
                            no_authority(receipt)

                        first_poll = await sdk.call_tool('job_get', {'operation_id': oid})
                        running = first_poll.structuredContent['data']
                        assert first_poll.isError is False
                        assert first_poll.structuredContent['status'] == running['status'] == 'running'
                        assert running['operation_id'] == oid and running == proxy.get(oid)
                        assert running['mutation']['phase'] == 'prepared'
                        assert controller_module.finished._barrier._read_journal(proxy.path) == callback['journal']
                        assert callback['journal'][:-1] == original_rows
                        assert value.receipt()['admission']['target_poll_emitted'] == 1

                        host_module.publish_command(owner.root, command(commands, 2, 'release'))
                        released = observe_host(host, lambda state: state['completed_commands'] == 2 or state['phase'] == 'fault')
                        assert released['phase'] == 'waiting' and released['fault'] is None
                        final = await runtime._runner.wait(oid, 5)
                        assert final['status'] == 'succeeded' and final['mutation']['phase'] == 'committed'
                        assert final['result']['verified'] is True
                        second_poll = await sdk.call_tool('job_get', {'operation_id': oid})
                        terminal = second_poll.structuredContent['data']
                        assert second_poll.isError is False
                        assert second_poll.structuredContent['status'] == terminal['status'] == 'succeeded'
                        assert terminal == final == proxy.get(oid)
                        assert terminal['mutation']['phase'] == 'committed'
                        terminal_rows = controller_module.finished._barrier._read_journal(proxy.path)
                        assert terminal_rows[:-1] == original_rows and len(terminal_rows) == 3
                        assert value.receipt()['admission']['target_poll_emitted'] == 2
                        assert proxy.barrier.state == 'finished'
                        # One source Runtime replay only; no second SDK CAD request
                        # is admitted and no setter/callback/SQL row repeats.
                        replay = await runtime.mutate(arm_arguments['request_id'], 'dimension.set_value',
                                                       owner.payload['arguments'], timeout_s=5)
                        assert replay == final
                        assert controller_module.finished._barrier._read_journal(proxy.path) == terminal_rows
                        assert len(owner.prepared.adapter.dimension_writes) == 1
                        assert original == (runtime._runner, runtime._catalog, runtime._dimensions,
                                            proxy._store, control.seam, owner.prepared.adapter)
                        assert controller_module.owned._read(owner.root / 'callback-return.json') == callback
                        assert controller_module.owned._read(owner.root / 'finish-barrier.json') == finish

                        host_module.publish_command(owner.root, command(commands, 3, 'prepare_normal_shutdown'))
                        completed = host.wait(5)
                        assert completed['phase'] == 'completed' and completed['fault'] is None
                        assert completed['thread_return_observed'] is True
                        assert completed['runtime_open_at_last_action'] is True
                        assert completed['completed_commands'] == 3 and not host._thread.is_alive()
                        assert control.inspect_state()['phase'] == 'ready_for_normal_shutdown'
                        assert runtime._closed is False
                        no_authority(completed)
                        return oid, terminal_rows, callback, finish
                finally:
                    tasks.cancel_scope.cancel()  # Source in-memory listener only.

    try:
        host_module.publish_command(owner.root, command(commands, 1, 'arm', arm_arguments))
        host.start()
        armed = observe_host(host, lambda state: state['completed_commands'] == 1 or state['phase'] == 'fault')
        assert armed['phase'] == 'waiting' and armed['fault'] is None
        assert control.inspect_state()['phase'] == 'armed'
        assert controller_module.finished._barrier._read_journal(proxy.path) == original_rows
        assert owner.prepared.adapter.dimension_writes == []
        oid, terminal_rows, callback, finish = anyio.run(scenario)
        receipt = assert_transport_only(value)
        assert receipt['admission']['cad_emitted'] == 1
        assert receipt['admission']['target_poll_emitted'] == 2
        assert receipt['metadata_emitted'] == receipt['tool_emitted'] == 3
        assert receipt['admission']['in_flight_cad'] == receipt['admission']['in_flight_observations'] == 0
        assert len(wire) == len(flushes) == 6 and len(replies) == 5
        assert len(owner.prepared.adapter.dimension_writes) == 1
        for sequence, expected in enumerate(('arm', 'release', 'prepare_normal_shutdown'), 1):
            ack = controller_module.owned._read(commands.ack_path(sequence))
            assert ack['command'] == expected and ack['lineage'] == owner.lineage
            no_authority(ack)
        assert runtime.shutdown() is True
        closed = control.complete_normal()
        assert closed['journal'] == terminal_rows and closed['original_factories_restored'] is True
        assert control.runtime is runtime and control.proxy is proxy
        assert proxy._store._db is None and runtime._closed is True
        assert owner.module.JobStore is original_factories[0] and owner.module.Runtime is original_factories[1]
        assert controller_module.owned._read(owner.root / 'callback-return.json') == callback
        assert controller_module.owned._read(owner.root / 'finish-barrier.json') == finish
        assert controller_module.owned._read(owner.root / 'dimension-control-closed.json') == closed
        assert len(owner.prepared.adapter.dimension_writes) == 1
        no_authority(closed)
        no_authority(value.close_admission())
    finally:
        host.stop_waiting()
        if host._started:
            host._thread.join(5)
            assert not host._thread.is_alive(), host.inspect_state()
