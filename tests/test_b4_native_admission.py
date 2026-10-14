"""Typed MCP messages and artificial pipes only; no processes/COM/native Q."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import Event, Thread

from mcp.types import JSONRPCMessage
import pytest


spec = importlib.util.spec_from_file_location('_b4_native_admission_tests',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_b4_native_admission.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

CONTEXT = dict(document_id='pure-part', configuration='Основная', object_id='pure-dimension', expected_revision='pure-revision')
SET = dict(name='dimension_set_value', arguments=dict(CONTEXT, request_id='pure-set', value=12., unit='mm', timeout_s=0.))
GET = dict(name='dimension_get', arguments={key: value for key, value in dict(CONTEXT, request_id='pure-get').items()
                                          if key != 'expected_revision'})
OBSERVATIONS = (dict(name='system_get_info', arguments={}),
                dict(name='job_get', arguments={'operation_id': 'already-known-pure-job'}))
TARGET = dict(arguments={key: value for key, value in SET['arguments'].items() if key not in ('request_id', 'timeout_s')},
              context=CONTEXT, mutates=True)


def controller(*, with_get=False, cad=None, observations=OBSERVATIONS, target=TARGET):
    return helper.DimensionAdmission(cad_requests=cad if cad is not None else (GET, SET) if with_get else (SET,),
        observation_requests=observations, target_operation='dimension.set_value', target_payload=target)


def request(value, rpc_id=1):
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=rpc_id, method='tools/call', params=deepcopy(value)))


def reply(rpc_id=1, status='succeeded', *, context=None):
    # Original synthetic read/write context, never an actual native receipt.
    context = {key: value for key, value in CONTEXT.items() if key != 'expected_revision'} if context is None else context
    return JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=rpc_id,
        result={'structuredContent': {'status': status, 'operation_id': 'pure-known-return-job',
                                    'context': context, 'data': {}, 'error': None, 'diagnostics': []}, 'content': []}))


def write_to(pipe):
    def write(payload):
        pipe.append(payload)
        return len(payload)
    return write


def false_authority(receipt):
    assert receipt['accepted'] is False
    assert receipt['native_q'] == receipt['native_admission'] == receipt['target_job_observation_binding'] == 'not_run'
    for key in ('process_stop_authorized', 'restart_authorized', 'cad_cleanup_authorized'):
        assert receipt[key] is False


def test_exact_current_dimension_facade_types_and_durable_payload_binding():
    current = controller()
    assert current.receipt()['target_payload'] == TARGET
    assert set(helper.SIGNATURES) == {'dimension_get', 'dimension_set_value'}
    assert helper.typed_arguments('dimension_get', GET['arguments'])['timeout_s'] == 10.
    false_authority(current.receipt())


def test_successful_write_flush_then_actual_response_counts_are_separate():
    current, pipe = controller(), []
    calls = []

    def flush():
        receipt = current.receipt()
        assert receipt['attempted'] == 1 and receipt['emitted'] == 0
        assert receipt['in_flight_cad'] == 1
        calls.append('flush')

    ack = current.write_message(request(SET), write_to(pipe), flush)
    assert ack['emitted'] is True and calls == ['flush']
    assert JSONRPCMessage.model_validate_json(pipe[0]) == request(SET)
    receipt = current.receipt()
    assert receipt['attempted'] == receipt['emitted'] == receipt['cad_emitted'] == 1
    assert receipt['in_flight_cad'] == 1 and receipt['observation_emitted'] == 0
    current.observe_response(reply(context=CONTEXT))
    assert current.receipt()['in_flight_cad'] == 0
    false_authority(current.receipt())


def test_optional_dimension_read_then_exact_target_after_success_no_parallel_cad():
    current, pipe = controller(with_get=True), []
    current.write_message(request(GET), write_to(pipe), lambda: None)
    current.observe_response(reply())
    current.write_message(request(SET, 2), write_to(pipe), lambda: None)
    assert current.receipt()['cad_emitted'] == 2 and len(pipe) == 2


def test_no_second_cad_before_original_response():
    current, pipe = controller(with_get=True), []
    current.write_message(request(GET), write_to(pipe), lambda: None)
    with pytest.raises(helper.AdmissionError, match='no parallel CAD'):
        current.write_message(request(SET, 2), write_to(pipe), lambda: None)
    assert len(pipe) == 1 and current.receipt()['admission_closed'] is True


@pytest.mark.parametrize('status', ['queued', 'running', 'failed', 'unknown', 'cancelled'])
def test_non_succeeded_cad_response_cannot_advance_native_sequence(status):
    current, pipe = controller(with_get=True), []
    current.write_message(request(GET), write_to(pipe), lambda: None)
    current.observe_response(reply(status=status))
    with pytest.raises(helper.AdmissionError, match='closed'):
        current.write_message(request(SET, 2), write_to(pipe), lambda: None)
    assert len(pipe) == 1
    false_authority(current.receipt())


def test_close_is_permanent_but_fixed_observations_remain_allowed():
    current, pipe = controller(), []
    current.close_admission()
    current.close_admission()
    with pytest.raises(helper.AdmissionError, match='closed'):
        current.write_message(request(SET), write_to(pipe), lambda: None)
    current.write_message(request(OBSERVATIONS[0], 2), write_to(pipe), lambda: None)
    current.write_message(request(OBSERVATIONS[1], 3), write_to(pipe), lambda: None)
    receipt = current.receipt()
    assert receipt['attempted'] == 3 and receipt['emitted'] == receipt['observation_emitted'] == 2
    assert receipt['cad_emitted'] == 0 and receipt['in_flight_observations'] == 2
    current.observe_response(reply(2))
    assert current.receipt()['in_flight_observations'] == 1
    false_authority(current.receipt())


def test_replay_after_close_never_sends_second_cad():
    current, pipe = controller(), []
    current.write_message(request(SET), write_to(pipe), lambda: None)
    current.close_admission()
    for rpc_id in (1, 2):
        with pytest.raises(helper.AdmissionError):
            current.write_message(request(SET, rpc_id), write_to(pipe), lambda: None)
    assert len(pipe) == 1 and current.receipt()['emitted'] == 1


@pytest.mark.parametrize('change', ['value', 'revision', 'object', 'request', 'extra', 'unknown', 'cancel', 'reconcile'])
def test_payload_drift_or_unadvertised_control_refused_before_write(change):
    current, pipe = controller(), []
    value = deepcopy(SET)
    if change == 'value': value['arguments']['value'] = 13.
    elif change == 'revision': value['arguments']['expected_revision'] = 'foreign'
    elif change == 'object': value['arguments']['object_id'] = 'foreign'
    elif change == 'request': value['arguments']['request_id'] = 'foreign'
    elif change == 'extra': value['arguments']['other'] = True
    else: value['name'] = {'unknown': 'part_extrude_rectangle', 'cancel': 'job_cancel', 'reconcile': 'job_reconcile'}[change]
    with pytest.raises(helper.AdmissionError):
        current.write_message(request(value), write_to(pipe), lambda: None)
    assert pipe == [] and current.receipt()['attempted'] == 1 and current.receipt()['emitted'] == 0
    assert current.receipt()['admission_closed'] is True


@pytest.mark.parametrize('fault', ['partial', 'write_throw', 'flush_throw', 'flush_ack', 'bool_ack'])
def test_failed_physical_write_or_flush_preserves_unknown_and_never_retries(fault):
    current, pipe = controller(), []

    def write(payload):
        pipe.append(payload)
        if fault == 'write_throw': raise OSError('pure-pipe-failure')
        if fault == 'partial': return len(payload) - 1
        if fault == 'bool_ack': return True
        return len(payload)

    def flush():
        if fault == 'flush_throw': raise OSError('pure-flush-failure')
        if fault == 'flush_ack': return False

    with pytest.raises(helper.AdmissionError, match='unconfirmed'):
        current.write_message(request(SET), write, flush)
    receipt = current.receipt()
    assert receipt['unknown_transport'] and receipt['attempted'] == 1 and receipt['emitted'] == 0
    assert receipt['records'][0]['write_state'] == 'unknown'
    current.observe_response(reply(context=CONTEXT))  # Late response is not missing flush proof.
    assert current.receipt()['unknown_transport'] and current.receipt()['emitted'] == 0
    with pytest.raises(helper.AdmissionError):
        current.write_message(request(OBSERVATIONS[0], 2), write_to(pipe), lambda: None)
    assert len(pipe) == 1
    false_authority(current.receipt())


def test_async_writer_rejected_before_physical_call():
    current, calls = controller(), []
    async def write(payload): calls.append('must-not-run')
    with pytest.raises(helper.AdmissionError, match='Synchronous'):
        current.write_message(request(SET), write, lambda: None)
    assert calls == [] and not current.receipt()['unknown_transport']


def test_close_waits_for_original_write_flush_and_denies_any_later_cad():
    current = controller()
    entered, release, close_started, close_returned = Event(), Event(), Event(), Event()
    errors, pipe = [], []

    def write(payload):
        entered.set()
        assert release.wait(5)
        pipe.append(payload)
        return len(payload)

    def writer():
        try: current.write_message(request(SET), write, lambda: None)
        except BaseException as exc: errors.append(exc)

    def closer():
        close_started.set()
        current.close_admission()
        close_returned.set()

    first, second = Thread(target=writer), Thread(target=closer)
    first.start()
    assert entered.wait(5)
    second.start()
    try:
        assert close_started.wait(5) and not close_returned.wait(.02)
    finally:
        release.set()
        first.join(5)
        second.join(5)
    assert not first.is_alive() and not second.is_alive() and not errors
    assert close_returned.is_set() and current.receipt()['emitted'] == 1
    with pytest.raises(helper.AdmissionError):
        current.write_message(request(SET, 2), write_to(pipe), lambda: None)
    assert len(pipe) == 1


@pytest.mark.parametrize('target_change', ['operation_context', 'arguments', 'mutates'])
def test_exact_target_payload_required_before_dispatch(target_change):
    payload = deepcopy(TARGET)
    if target_change == 'operation_context': payload['context']['object_id'] = 'foreign'
    elif target_change == 'arguments': payload['arguments']['value'] = 13.
    else: payload['mutates'] = False
    with pytest.raises(helper.AdmissionError, match='durable payload'):
        controller(target=payload)


def test_unknown_future_job_id_cannot_replace_predeclared_observation():
    current = controller()
    with pytest.raises(helper.AdmissionError, match='payload drift'):
        current.write_message(request(dict(name='job_get', arguments={'operation_id': 'future-unbound-id'})),
                              lambda payload: len(payload), lambda: None)
    assert current.receipt()['target_job_observation_binding'] == 'not_run'


def test_owner_plan_and_receipts_are_detached():
    target, cad = deepcopy(TARGET), (deepcopy(SET),)
    current = controller(cad=cad, target=target)
    target['arguments']['value'] = 100.
    cad[0]['arguments']['object_id'] = 'foreign'
    snapshot = current.receipt()
    snapshot['target_payload']['arguments']['value'] = 99.
    assert current.receipt()['target_payload'] == TARGET


@pytest.mark.parametrize('change', ['foreign_context', 'missing_structure', 'tool_error', 'hidden_error', 'foreign_id'])
def test_unbound_or_failed_response_cannot_advance_cad_sequence(change):
    current, pipe = controller(with_get=True), []
    current.write_message(request(GET), write_to(pipe), lambda: None)
    value = reply().model_dump(mode='json')
    if change == 'foreign_context': value['result']['structuredContent']['context']['object_id'] = 'foreign'
    elif change == 'missing_structure': value['result'].pop('structuredContent')
    elif change == 'tool_error': value['result']['isError'] = True
    elif change == 'hidden_error': value['result']['structuredContent']['error'] = {'code': 'bad', 'message': 'pure-error'}
    else: value['id'] = 99
    with pytest.raises(helper.AdmissionError):
        current.observe_response(JSONRPCMessage.model_validate(value))
    with pytest.raises(helper.AdmissionError):
        current.write_message(request(SET, 2), write_to(pipe), lambda: None)
    assert len(pipe) == 1 and current.receipt()['admission_closed']


def test_reentrant_physical_writer_cannot_send_second_cad_even_with_early_reply():
    current, pipe = controller(with_get=True), []
    denied = []

    def write(payload):
        current.observe_response(reply())
        try:
            current.write_message(request(SET, 2), write_to(pipe), lambda: None)
        except helper.AdmissionError as exc:
            denied.append(str(exc))
        pipe.append(payload)
        return len(payload)

    current.write_message(request(GET), write, lambda: None)
    assert denied and 'reentrant' in denied[0] and len(pipe) == 1
    assert current.receipt()['emitted'] == 1 and current.receipt()['admission_closed']
