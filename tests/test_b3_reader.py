"""Actual SQLite + job_get route; durable sends are never repeated on failure."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import JobStore
from solidworks_mcp.runtime_v2 import Runtime
from solidworks_mcp.server_v2 import create_app, response

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_reader as helper
finally:
    sys.path.remove(scripts)


class Protocol:
    def __init__(self, store, *, late=False, lost_ack=False, known_failure=False):
        self.store, self.late, self.lost_ack, self.known_failure = store, late, lost_ack, known_failure
        self.calls, self.retained, self.dispatches, self.polls = [], [], [], 0
        self.pending = None
        def forbidden():raise AssertionError('No CAD worker or catalog may start.')
        self.app = create_app(store, Runtime(None, worker_factory=forbidden, catalog_factory=forbidden))

    def finish(self, operation_id):
        if self.known_failure:
            self.store.finish(operation_id, 'failed', error={'code': 'object_body_mismatch',
                'message': 'Foreign native owner.', 'requires_reconciliation': False})
        else:self.store.finish(operation_id, 'succeeded', result={'artificial_domain': True})

    async def call_tool(self, tool, args):
        self.calls.append((tool, deepcopy(args)))
        if tool == 'job_get':
            if self.pending is not None:
                self.polls += 1
                if self.polls == 2:
                    self.finish(self.pending)
                    self.pending = None
            value = await self.app._tool_manager.get_tool('job_get').fn(**args)
        else:
            spec = helper.SPECS[tool]
            payload = spec.payload(args)
            job, created = self.store.create(args['request_id'], spec.operation,
                payload['arguments'], payload['context'], mutates=spec.mutates)
            if created:
                self.dispatches.append(job['operation_id'])
                self.store.start(job['operation_id'])
                if self.late:self.pending = job['operation_id']
                else:self.finish(job['operation_id'])
            if self.lost_ack:raise ConnectionError('lost acknowledgement')
            job = self.store.get(job['operation_id'])
            value = response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=job['result'], error=job['error'])
        return NS(isError=False, structuredContent=value.model_dump(mode='json'))

    async def observe_once(self):
        rows = self.store.list()['items']
        safe = not self.retained and all(row['status'] in ('succeeded', 'failed') for row in rows)
        return NS(child_can_close=safe, fixture_can_cleanup=safe)

    def retain(self, reason):self.retained.append(reason)


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / 'jobs.sqlite'
    store = JobStore(path)
    args = dict(request_id='b3-original', document_id='doc_a', configuration='Основная',
                expected_observation_revision='obs_a', object_id='body_a')
    yield store, path, args
    store.close()


def reader(protocol, path, *, failing_persist=None, unsafe=False):
    snapshots, pauses, safe_calls = [], [], []
    def safe():
        safe_calls.append(True)
        if unsafe:raise RuntimeError('unconfirmed owner baseline')
    def persist(receipts):
        if len(snapshots) + 1 == failing_persist:raise OSError('receipt storage failed')
        snapshots.append(receipts)
    async def pause(interval):pauses.append(interval)
    value = helper.B3Reader(protocol, path, assert_before_dispatch=safe, persist=persist, pause=pause)
    return value, snapshots, pauses, safe_calls


@pytest.mark.parametrize('late', [False, True])
def test_bound_read_has_one_durable_send_and_exact_original_operation(setup, late):
    store, path, args = setup
    client = Protocol(store, late=late)
    value, snapshots, pauses, _ = reader(client, path)
    row = asyncio.run(value.read('geometry_get', args))
    assert row['request_id'] == args['request_id'] and row['status'] == 'succeeded'
    assert len(client.dispatches) == 1
    assert sum(tool == 'geometry_get' for tool, _ in client.calls) == 1
    assert all(arguments == {'operation_id': row['operation_id']} for tool, arguments in client.calls if tool == 'job_get')
    assert snapshots[0][0]['state'] == 'dispatch_prepared'
    assert snapshots[-1][0]['state'] == 'journal_bound'
    assert pauses == ([.25] if late else [])
    assert client.retained == []


def test_read_replay_returns_exact_terminal_receipt_without_second_dispatch(setup):
    store, path, args = setup
    client = Protocol(store)
    value, *_ = reader(client, path)
    async def run():
        first = await value.read('geometry_get', args)
        second = await value.read('geometry_get', args)
        assert first == second
    asyncio.run(run())
    assert len(client.dispatches) == 1 and len(store.list()['items']) == 1


def test_lost_ack_is_retained_without_retry_or_cancellation(setup):
    store, path, args = setup
    client = Protocol(store, lost_ack=True)
    value, snapshots, *_ = reader(client, path)
    with pytest.raises(ConnectionError):asyncio.run(value.read('geometry_get', args))
    assert len(client.calls) == len(client.dispatches) == 1
    assert snapshots[-1][0]['state'] == 'dispatch_prepared'
    assert client.retained
    with pytest.raises(RuntimeError, match='retained'):
        asyncio.run(value.read('geometry_get', {**args, 'request_id': 'new-after-loss'}))
    assert len(client.calls) == 1


@pytest.mark.parametrize('at,sends', [(1, 0), (2, 1), (3, 1)])
def test_receipt_storage_failure_never_repeats_or_starts_another_rpc(setup, at, sends):
    store, path, args = setup
    client = Protocol(store)
    value, *_ = reader(client, path, failing_persist=at)
    with pytest.raises(OSError):asyncio.run(value.read('geometry_get', args))
    assert sum(tool == 'geometry_get' for tool, _ in client.calls) == sends
    assert len(client.dispatches) == sends
    assert bool(client.retained) is bool(sends)


def test_initial_baseline_refusal_and_missing_request_never_start_dispatch(setup):
    store, path, args = setup
    client = Protocol(store)
    value, *_ = reader(client, path, unsafe=True)
    with pytest.raises(RuntimeError):asyncio.run(value.read('geometry_get', args))
    args.pop('request_id')
    with pytest.raises(ValueError):asyncio.run(value.read('geometry_get', args))
    assert client.calls == client.dispatches == []


def test_known_failed_read_is_bound_without_fabricating_success(setup):
    store, path, args = setup
    client = Protocol(store, known_failure=True)
    value, *_ = reader(client, path)
    row = asyncio.run(value.read('geometry_get', args, expected_error='object_body_mismatch'))
    assert row['status'] == 'failed' and row['result'] is None
    assert len(client.dispatches) == 1 and not client.retained


def test_polling_wrong_operation_quarantines_owner(setup):
    store, path, args = setup
    class WrongPoll(Protocol):
        async def call_tool(self, tool, arguments):
            result = await super().call_tool(tool, arguments)
            if tool == 'job_get':result.structuredContent['operation_id'] = 'another_job'
            return result
    client = WrongPoll(store, late=True)
    value, *_ = reader(client, path)
    with pytest.raises(ValueError, match='different'):asyncio.run(value.read('geometry_get', args))
    assert len(client.dispatches) == 1 and client.retained


@pytest.mark.parametrize('field,value', [('data', {'concealed_difference': True}),
    ('context', {'document_id': 'foreign'}), ('status', 'failed'),
    ('error', {'code': 'fabricated', 'message': 'fabricated'})])
def test_original_tool_response_cannot_be_replaced_by_correct_later_job_get(setup, field, value):
    store, path, args = setup
    class WrongTool(Protocol):
        async def call_tool(self, tool, arguments):
            result = await super().call_tool(tool, arguments)
            if tool == 'geometry_get':result.structuredContent[field] = value
            return result
    client = WrongTool(store)
    route, *_ = reader(client, path)
    with pytest.raises(ValueError):asyncio.run(route.read('geometry_get', args))
    assert len(client.dispatches) == 1 and client.retained
    assert route.receipts[-1]['state'] != 'journal_bound'


def test_cancelled_polling_retains_running_job_without_cancel_or_new_send(setup):
    store, path, args = setup
    client = Protocol(store, late=True)
    route, *_ = reader(client, path)
    async def cancelled(interval):raise asyncio.CancelledError()
    route.pause = cancelled
    with pytest.raises(asyncio.CancelledError):asyncio.run(route.read('geometry_get', args))
    assert len(client.dispatches) == 1 and store.get(client.dispatches[0])['status'] == 'running'
    assert all(tool != 'job_cancel' for tool, _ in client.calls)
    with pytest.raises(RuntimeError, match='retained'):asyncio.run(route.read('geometry_get', args))
    assert len(client.dispatches) == 1
