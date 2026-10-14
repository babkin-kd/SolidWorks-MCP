"""Pure verifier lifetime/acknowledgement tests, without SDK processes or CAD."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import uuid

import anyio
import pytest


HELPER = Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_lifecycle.py'
spec = importlib.util.spec_from_file_location('_verifier_lifecycle_test', HELPER)
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)

ARGS = {'request_id': 'owned-request', 'document_id': 'doc', 'configuration': 'Основная',
        'object_id': 'dim', 'expected_revision': 'rev', 'value': 9, 'unit': 'mm', 'timeout_s': 0}
GUARD = {'original_state': 0, 'locked_state': 2, 'released_state': 0}


def test_application_document_guard_requires_its_own_typed_release_evidence():
    guard = {'scope': 'application_document_create_guard_v1', 'original_command_in_progress': False,
        'acquired': True, 'released': True, 'selection_preserved': True, 'model_guards': [deepcopy(GUARD)]}
    assert helper.released_execution_guard(guard)
    for key, value in [('original_command_in_progress', 0), ('acquired', 1), ('released', False),
                       ('selection_preserved', False), ('model_guards', [{'released_state': 0}])]:
        changed = deepcopy(guard)
        changed[key] = value
        assert not helper.released_execution_guard(changed)
SPECS = {
    'document_list': helper.ToolSpec('document.list', False),
    'dimension_set_value': helper.ToolSpec('dimension.set_value', True,
        float_arguments=frozenset({'value'}), prewrite_failure_codes=frozenset({'stale_revision'}),
        preenqueue_error_codes=frozenset({'invalid_timeout'})),
}


def raw(value):
    return SimpleNamespace(structuredContent=value, isError=False)


def job(arguments=ARGS, *, mutates=True, status='running', phase=None):
    domain = {k: v for k, v in arguments.items() if k not in ('request_id', 'timeout_s')}
    if mutates and type(domain.get('value')) in (int, float):
        domain['value'] = float(domain['value'])
    context = {k: domain[k] for k in ('document_id', 'configuration', 'object_id', 'expected_revision') if k in domain}
    return {'operation_id': 'operation', 'request_id': arguments['request_id'],
            'operation': 'dimension.set_value' if mutates else 'document.list',
            'payload': {'arguments': domain, 'context': context, 'mutates': mutates},
            'status': status, 'result': {'verified': True} if mutates else {'documents': []},
            'error': None, 'created_at': 1., 'mutation': None if phase is None else {
                'phase': phase, 'before_state': {'_mutation_effect_scope': 'application'},
                'verification': {'outcome': phase, 'evidence': {'execution_guard': dict(GUARD)}}}}


class FakeClient:
    def __init__(self):
        self.rows, self.calls, self.events = [], [], []
        self.mode = 'ack'
        self.owner = None
        self.pages = []

    async def call_tool(self, name, arguments=None, **kwargs):
        arguments = deepcopy(arguments or {})
        self.calls.append((name, arguments))
        if name == 'job_list':
            page = self.pages.pop(0) if self.pages else {'items': deepcopy(self.rows), 'next_cursor': None}
            return raw({'status': 'succeeded', 'data': page})
        assert name in SPECS
        request = self.owner.requests[arguments['request_id']]
        assert request.attempt_arguments[-1] == arguments
        assert not request.not_dispatched, 'A new send must be uncertain before awaiting its acknowledgement.'
        self.events.append('registered-before-send')
        if self.mode == 'preenqueue':
            return raw({'status': 'failed', 'operation_id': None, 'error': {'code': 'invalid_timeout'}})
        if self.mode == 'cancel-before-row':
            await anyio.sleep_forever()
        if self.mode == 'error-before-row':
            raise OSError('Later acknowledgement lost before durable row is visible')
        self.rows = [job(arguments, mutates=name == 'dimension_set_value')]
        if self.mode == 'lost-ack':
            raise OSError('First acknowledgement lost')
        if self.mode == 'cancel-after-row':
            await anyio.sleep_forever()
        return raw({'status': 'running', 'operation_id': 'operation', 'context': request.payload['context'], 'data': None})

    async def initialize(self):
        return 'initialized'

    async def list_tools(self):
        return 'tool-schema'


def owner_for(client, *, reader=None, on_hold=None, **kwargs):
    owner = helper.VerifierSupervisor(client, tool_specs=SPECS,
        journal_reader=reader or (lambda: deepcopy(client.rows)), poll_interval=.001,
        on_hold=on_hold, **kwargs)
    client.owner = owner
    return owner


def terminal(client, *, status='succeeded', phase='committed'):
    row = client.rows[0]
    row['status'] = status
    if row['payload']['mutates']:
        row['mutation'] = job(status=status, phase=phase)['mutation']


def test_new_dispatch_revokes_previous_cleanup_and_history_before_transport():
    async def scenario():
        class Client(FakeClient):
            async def call_tool(self, name, arguments=None, **kwargs):
                if name not in helper.DIRECT_QUERIES:
                    assert not self.owner.cleanup_gate.can_cleanup()
                    assert not self.owner.cleanup_gate.decision.child_can_close
                    assert self.owner._approved_snapshot is None
                    with pytest.raises(RuntimeError):
                        self.owner.history_seed()
                return await super().call_tool(name, arguments, **kwargs)
        client = Client()
        owner = owner_for(client)
        async with owner.inside_live_session():
            await owner.call_tool('dimension_set_value', ARGS)
            terminal(client)
            assert (await owner.observe_once()).fixture_can_cleanup
            earlier = deepcopy(client.rows)
            later_args = {**ARGS, 'request_id': 'later-owned-request'}
            client.mode = 'cancel-before-row'
            with anyio.move_on_after(.01):
                await owner.call_tool('dimension_set_value', later_args)
            assert client.rows == earlier  # Existing durable history remains intact.
            assert not (await owner.observe_once()).child_can_close
            assert not owner.cleanup_gate.can_cleanup()
            later = job(later_args, status='succeeded', phase='committed')
            later['operation_id'] = 'later-operation'
            client.rows.append(later)
            assert (await owner.observe_once()).fixture_can_cleanup
        assert owner.history_seed()
    anyio.run(scenario)


@pytest.mark.parametrize('reason', ['terminal unknown retains fixtures', 'transport lost'])
def test_tainted_owner_denies_further_mutation_before_send_but_allows_read_observation(reason):
    async def scenario():
        client = FakeClient()
        owner = owner_for(client)
        async with owner.inside_live_session():
            owner.retain(reason)
            with pytest.raises(RuntimeError, match='Unconfirmed effects'):
                await owner.call_tool('dimension_set_value', ARGS)
            assert not client.calls
            await owner.call_tool('document_list', {'request_id': 'read'})
            terminal(client)
        assert owner.cleanup_gate.decision.child_can_close
        assert not owner.cleanup_gate.can_cleanup()
    anyio.run(scenario)


@pytest.mark.parametrize('mutates,status,phase', [
    (False, 'succeeded', None), (False, 'failed', None),
    (True, 'succeeded', 'committed'), (True, 'failed', 'rolled_back'),
    (True, 'failed', 'not_started'),
])
def test_normal_terminal_jobs_allow_cleanup_and_preserve_raw_sdk_result(mutates, status, phase):
    async def scenario():
        client = FakeClient()
        owner = owner_for(client, on_hold=lambda decision: terminal(client, status=status, phase=phase))
        async with owner.inside_live_session():
            result = await owner.call_tool('dimension_set_value' if mutates else 'document_list',
                                           ARGS if mutates else {'request_id': 'read'})
            assert result.structuredContent['operation_id'] == 'operation'
            assert await owner.initialize() == 'initialized'
            assert await owner.list_tools() == 'tool-schema'
        assert owner.cleanup_gate.can_cleanup()
        assert owner.cleanup_gate.decision.child_can_close
        assert [name for name, _ in client.calls] == ['dimension_set_value' if mutates else 'document_list']
    anyio.run(scenario)


def test_assertion_after_dispatch_drains_before_sdk_and_fixture_cleanup_preserving_original_error():
    async def scenario():
        client, trace = FakeClient(), []
        original = AssertionError('Duplicate acknowledgement assertion')
        def on_hold(decision):
            trace.append('drain-running')
            assert not owner.cleanup_gate.can_cleanup()
            terminal(client)
        @asynccontextmanager
        async def session_factory():
            trace.append('sdk-open')
            try:
                yield client
            finally:
                assert client.rows[0]['status'] == 'succeeded'
                trace.append('sdk-exit')
        with pytest.raises(AssertionError) as raised:
            async with helper.open_supervised_session(session_factory, tool_specs=SPECS,
                    journal_reader=lambda: deepcopy(client.rows), on_hold=on_hold, poll_interval=.001) as owner:
                client.owner = owner
                await owner.call_tool('dimension_set_value', ARGS)
                raise original
        assert raised.value is original
        assert trace == ['sdk-open', 'drain-running', 'sdk-exit']
        if owner.cleanup_gate.can_cleanup():
            trace.append('fixture-cleanup')
        assert trace[-1] == 'fixture-cleanup'
    anyio.run(scenario)


def test_body_deadline_does_not_cancel_sdk_pump_and_running_job_drains_first():
    async def scenario():
        client, trace = FakeClient(), []
        client.mode = 'cancel-after-row'
        ticks = []
        async def pump():
            while True:
                ticks.append(1)
                await anyio.sleep(.001)
        @asynccontextmanager
        async def sdk():
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(pump)
                try:
                    yield client
                finally:
                    assert client.rows[0]['status'] == 'succeeded'
                    trace.append('sdk-exit')
                    tasks.cancel_scope.cancel()
        holds = 0
        async def observe_hold(decision):
            nonlocal holds
            holds += 1
            previous = len(ticks)
            await anyio.sleep(.005)
            assert len(ticks) > previous, 'SDK sibling task was cancelled with the test body.'
            assert 'sdk-exit' not in trace
            if holds == 2:
                terminal(client)
        async def body(owner):
            await owner.call_tool('dimension_set_value', ARGS)
        with pytest.raises(TimeoutError):
            async with helper.open_supervised_session(sdk, tool_specs=SPECS,
                    journal_reader=lambda: deepcopy(client.rows), on_hold=observe_hold, poll_interval=.001) as owner:
                client.owner = owner
                await owner.run_body(body, timeout_s=.005)
        assert holds == 2 and trace == ['sdk-exit']
        assert owner.cleanup_gate.can_cleanup()
    anyio.run(scenario)


def test_lost_ack_is_recovered_from_exact_durable_row_without_repeating_mutation():
    async def scenario():
        client = FakeClient()
        client.mode = 'lost-ack'
        owner = owner_for(client, on_hold=lambda decision: terminal(client))
        with pytest.raises(OSError, match='acknowledgement lost'):
            async with owner.inside_live_session():
                await owner.call_tool('dimension_set_value', ARGS)
        assert owner.requests[ARGS['request_id']].operation_id == 'operation'
        assert owner.cleanup_gate.decision.child_can_close
        assert not owner.cleanup_gate.can_cleanup(), 'Transport uncertainty must retain fixtures.'
        assert [name for name, _ in client.calls] == ['dimension_set_value']
    anyio.run(scenario)


@pytest.mark.parametrize('explicit_callback', [False, True])
def test_later_pre_enqueue_rejection_cannot_erase_earlier_cancelled_lost_ack(explicit_callback):
    async def scenario():
        client = FakeClient()
        client.mode = 'cancel-before-row'
        owner = owner_for(client, preenqueue_rejection=(lambda *args: True) if explicit_callback else None)
        owner._fresh = owner._entered = True
        with anyio.move_on_after(.002):
            await owner.call_tool('dimension_set_value', ARGS)
        client.mode = 'preenqueue'
        await owner.call_tool('dimension_set_value', {**ARGS, 'timeout_s': -1})
        request = owner.requests[ARGS['request_id']]
        assert request.send_attempts == 2 and request.rejected_attempts == 1
        assert request.attempt_arguments == [ARGS, {**ARGS, 'timeout_s': -1}]
        assert not request.not_dispatched
        decision = await owner.observe_once()
        assert not decision.child_can_close and not decision.fixture_can_cleanup
        # The delayed first dispatch may still appear; never repeat it to find out.
        client.rows = [job(status='succeeded', phase='committed')]
        assert (await owner.observe_once()).child_can_close
        assert len(client.calls) == 2
    anyio.run(scenario)


def test_explicit_pre_enqueue_rejection_is_safe_but_generic_missing_ack_is_not():
    async def scenario():
        client = FakeClient()
        client.mode = 'preenqueue'
        owner = owner_for(client)
        async with owner.inside_live_session():
            await owner.call_tool('dimension_set_value', {**ARGS, 'timeout_s': -1})
        assert owner.cleanup_gate.can_cleanup()
        other = owner_for(FakeClient())
        other._fresh = True
        assert not (await other.observe_once()).child_can_close  # Empty tracker proves nothing.
    anyio.run(scenario)


@pytest.mark.parametrize('later_outcome', ['cancel-before-row', 'error-before-row'])
def test_earlier_pre_enqueue_rejection_never_certifies_a_later_unacknowledged_attempt(later_outcome):
    async def scenario():
        client = FakeClient()
        owner = owner_for(client)
        owner._fresh = owner._entered = True
        client.mode = 'preenqueue'
        await owner.call_tool('dimension_set_value', {**ARGS, 'timeout_s': -1})
        request = owner.requests[ARGS['request_id']]
        assert request.not_dispatched and request.rejected_attempts == 1
        client.mode = later_outcome
        if later_outcome == 'cancel-before-row':
            with anyio.move_on_after(.002):
                await owner.call_tool('dimension_set_value', ARGS)
        else:
            with pytest.raises(OSError, match='Later acknowledgement lost'):
                await owner.call_tool('dimension_set_value', ARGS)
        assert request.send_attempts == 2 and request.rejected_attempts == 1
        assert not request.not_dispatched and request.operation_id is None
        decision = await owner.observe_once()
        assert not decision.child_can_close and not decision.fixture_can_cleanup
        assert len(client.calls) == 2 and client.rows == []
    anyio.run(scenario)


def test_job_list_recovery_reads_all_pages_but_never_releases_without_coherent_journal():
    async def scenario():
        client = FakeClient()
        async def unavailable():
            raise OSError('Journal temporarily unavailable')
        owner = owner_for(client, reader=unavailable)
        owner._entered = owner._fresh = True
        client.mode = 'cancel-before-row'
        with anyio.move_on_after(.002):
            await owner.call_tool('dimension_set_value', ARGS)
        client.pages = [
            {'items': [], 'next_cursor': {'created_at': 2., 'operation_id': 'previous'}},
            {'items': [job(status='succeeded', phase='committed')], 'next_cursor': None},
        ]
        decision = await owner.observe_once()
        assert owner.requests[ARGS['request_id']].operation_id == 'operation'
        assert not decision.child_can_close and not owner.cleanup_gate.can_cleanup()
        assert client.calls[-1] == ('job_list', {'limit': 1000, 'before_created_at': 2., 'before_operation_id': 'previous'})
        assert sum(name == 'dimension_set_value' for name, _ in client.calls) == 1
    anyio.run(scenario)


@pytest.mark.parametrize('fault', ['unknown', 'unreleased', 'bool-guard', 'reconciliation', 'invalid-reconciliation', 'untracked-mutation'])
def test_terminal_uncertainty_retains_fixtures_but_quiescent_child_can_exit(fault):
    async def scenario():
        client = FakeClient()
        owner = owner_for(client)
        owner._entered = owner._fresh = True
        await owner.call_tool('dimension_set_value', ARGS)
        terminal(client)
        row = client.rows[0]
        if fault == 'unknown':
            row['status'] = 'unknown'
            row['mutation']['phase'] = 'unresolved'
        elif fault == 'unreleased':
            row['mutation']['verification']['evidence']['execution_guard']['released_state'] = 2
        elif fault == 'bool-guard':
            row['mutation']['verification']['evidence']['execution_guard']['original_state'] = False
        elif fault in ('reconciliation', 'invalid-reconciliation'):
            row['error'] = {'requires_reconciliation': True if fault == 'reconciliation' else 0}
        else:
            foreign = deepcopy(row)
            foreign['operation_id'], foreign['request_id'] = 'foreign-op', 'foreign-request'
            client.rows.append(foreign)
        decision = await owner.observe_once()
        assert decision.child_can_close and not owner.cleanup_gate.can_cleanup()
    anyio.run(scenario)


@pytest.mark.parametrize('fault', ['payload', 'context', 'bool-value', 'wrong-operation', 'failed-prepared', 'unverified-success', 'pending-untracked-read'])
def test_invalid_or_pending_journal_never_releases_child(fault):
    async def scenario():
        client = FakeClient()
        owner = owner_for(client)
        owner._entered = owner._fresh = True
        await owner.call_tool('dimension_set_value', ARGS)
        terminal(client)
        row = client.rows[0]
        if fault == 'payload': row['payload']['arguments']['unit'] = 'deg'
        elif fault == 'context': row['payload']['context']['document_id'] = 'foreign'
        elif fault == 'bool-value': row['payload']['arguments']['value'] = True
        elif fault == 'wrong-operation': row['operation'] = 'export.execute'
        elif fault == 'failed-prepared':
            row['status'] = 'failed'
            row['mutation']['phase'] = 'prepared'
        elif fault == 'unverified-success': row['result']['verified'] = False
        else:
            pending = job({'request_id': 'untracked-read'}, mutates=False)
            pending['operation_id'] = 'other-operation'
            client.rows.append(pending)
        decision = await owner.observe_once()
        assert not decision.child_can_close and not decision.fixture_can_cleanup
    anyio.run(scenario)


@pytest.mark.parametrize('error_type', [RuntimeError, asyncio.CancelledError])
def test_hold_callback_error_does_not_close_resources_or_replace_original_body_error(error_type):
    async def scenario():
        client = FakeClient()
        original = AssertionError('original-body-error')
        holds = 0
        def hold(decision):
            nonlocal holds
            holds += 1
            if holds == 1:
                raise error_type('observer failed')
            terminal(client)
        owner = owner_for(client, on_hold=hold)
        with pytest.raises(AssertionError) as raised:
            async with owner.inside_live_session():
                await owner.call_tool('dimension_set_value', ARGS)
                raise original
        assert raised.value is original and holds == 2
        assert any(isinstance(entry, tuple) and entry[0] == 'hold observer failed' for entry in owner.progress)
    anyio.run(scenario)


def test_explicit_normalization_defaults_mapping_and_constants_preserve_exact_send_args():
    spec = helper.ToolSpec('export.execute', True, argument_map={'file_format': 'format'},
        argument_defaults={'units': ''}, float_arguments=frozenset({'value'}))
    arguments = {'request_id': 'r', 'file_format': 'step', 'filename': 'Деталь.step', 'timeout_s': 0, 'value': 9}
    saved = deepcopy(arguments)
    payload = spec.payload(arguments)
    assert payload['arguments'] == {'format': 'step', 'filename': 'Деталь.step', 'units': '', 'value': 9.}
    assert type(payload['arguments']['value']) is float and arguments == saved
    with pytest.raises(ValueError, match='aliases collide'):
        spec.payload({**arguments, 'format': 'parasolid'})
    constant = helper.ToolSpec('geometry.list', False, constant_args={'kind': 'body'})
    with pytest.raises(ValueError, match='server-owned constants'):
        constant.payload({'kind': 'face'})


def test_cancelled_journal_observer_cannot_bypass_drain_or_replace_body_error():
    async def scenario():
        client, reads = FakeClient(), 0
        original = AssertionError('original-after-dispatch')
        async def reader():
            nonlocal reads
            reads += 1
            if reads == 2:
                raise asyncio.CancelledError('Observer cancellation')
            return deepcopy(client.rows)
        owner = owner_for(client, reader=reader, on_hold=lambda decision: terminal(client))
        with pytest.raises(AssertionError) as raised:
            async with owner.inside_live_session():
                await owner.call_tool('dimension_set_value', ARGS)
                raise original
        assert raised.value is original
        assert client.rows[0]['status'] == 'succeeded'
        assert owner.cleanup_gate.decision.child_can_close and not owner.cleanup_gate.can_cleanup()
        assert reads >= 3
    anyio.run(scenario)


def test_body_and_sdk_shutdown_errors_both_survive_as_original_exception_objects():
    async def scenario():
        client = FakeClient()
        body_error, sdk_error = ValueError('body'), RuntimeError('SDK shutdown')
        @asynccontextmanager
        async def sdk():
            yield client
            raise sdk_error
        with pytest.raises(BaseExceptionGroup) as raised:
            async with helper.open_supervised_session(sdk, tool_specs=SPECS,
                    journal_reader=lambda: deepcopy(client.rows), on_hold=lambda decision: terminal(client),
                    poll_interval=.001) as owner:
                client.owner = owner
                await owner.call_tool('dimension_set_value', ARGS)
                raise body_error
        assert raised.value.exceptions == (body_error, sdk_error)
        assert not owner.cleanup_gate.can_cleanup()
        assert 'SDK shutdown unconfirmed' in owner.cleanup_gate.decision.reasons
        with pytest.raises(RuntimeError, match='completed safe'):
            owner.history_seed()
    anyio.run(scenario)


def test_sdk_teardown_failure_after_success_retains_still_alive_resources():
    async def scenario():
        client = FakeClient()
        alive = True
        failure = RuntimeError('SDK teardown failed before transport exit')
        @asynccontextmanager
        async def sdk():
            yield client
            assert alive
            raise failure
        with pytest.raises(RuntimeError) as raised:
            async with helper.open_supervised_session(sdk, tool_specs=SPECS,
                    journal_reader=lambda: deepcopy(client.rows), on_hold=lambda decision: terminal(client),
                    poll_interval=.001) as owner:
                client.owner = owner
                await owner.call_tool('dimension_set_value', ARGS)
        assert raised.value is failure and alive
        assert owner.cleanup_gate.decision.child_can_close
        assert not owner.cleanup_gate.can_cleanup()
        with pytest.raises(RuntimeError, match='completed safe'):
            owner.history_seed()
    anyio.run(scenario)


async def completed_owner():
    client = FakeClient()
    owner = owner_for(client, on_hold=lambda decision: terminal(client))
    async with owner.inside_live_session():
        await owner.call_tool('dimension_set_value', ARGS)
    return owner, deepcopy(client.rows)


def test_verified_history_allows_readonly_restart_and_blocks_new_mutation_before_send():
    async def scenario():
        previous, rows = await completed_owner()
        seed = previous.history_seed()
        class RestartClient(FakeClient):
            async def call_tool(self, name, arguments=None, **kwargs):
                assert name == 'document_list'
                self.calls.append((name, deepcopy(arguments)))
                self.rows.append(job(arguments, mutates=False, status='succeeded'))
                self.rows[-1]['operation_id'] = 'new-read'
                return raw({'status': 'succeeded', 'operation_id': 'new-read'})
        client = RestartClient()
        client.rows = rows
        owner = owner_for(client, trusted_history=seed, readonly_restart=True)
        async with owner.inside_live_session():
            with pytest.raises(RuntimeError, match='cannot dispatch mutations'):
                await owner.call_tool('dimension_set_value', {**ARGS, 'request_id': 'forbidden'})
            assert client.calls == []
            await owner.call_tool('document_list', {'request_id': 'restart-read'})
        assert owner.cleanup_gate.can_cleanup()
        assert len(client.calls) == 1
    anyio.run(scenario)


@pytest.mark.parametrize('change', ['missing', 'modified', 'pending', 'extra'])
def test_history_requires_exact_unchanged_initial_snapshot(change):
    async def scenario():
        previous, rows = await completed_owner()
        seed = previous.history_seed()
        if change == 'missing': rows = []
        elif change == 'modified': rows[0]['mutation']['verification']['evidence']['execution_guard']['released_state'] = 2
        elif change == 'pending': rows[0]['status'] = 'running'
        else: rows.append(job({'request_id': 'unexpected'}, mutates=False))
        client = FakeClient()
        client.rows = rows
        owner = owner_for(client, trusted_history=seed, readonly_restart=True)
        # Evaluate the real startup match without entering an indefinite hold.
        owner._fresh = helper._json(rows) == seed._snapshot
        assert not owner._fresh
        decision = await owner.observe_once()
        assert not decision.child_can_close and not owner.cleanup_gate.can_cleanup()
    anyio.run(scenario)


def test_history_cannot_be_imported_as_json_or_issued_without_safe_drain():
    owner = owner_for(FakeClient())
    with pytest.raises(RuntimeError, match='completed safe'):
        owner.history_seed()
    with pytest.raises(ValueError, match='verified supervisor'):
        helper.VerifiedHistory('[]', object())
    with pytest.raises(ValueError, match='explicitly read-only'):
        owner_for(FakeClient(), trusted_history={'approved': True}, readonly_restart=True)


def test_unknown_owner_cannot_issue_a_fixture_safe_history_seed():
    async def scenario():
        client = FakeClient()
        owner = owner_for(client, on_hold=lambda decision: terminal(client, status='unknown', phase='unresolved'))
        async with owner.inside_live_session():
            await owner.call_tool('dimension_set_value', ARGS)
        assert owner.cleanup_gate.decision.child_can_close and not owner.cleanup_gate.can_cleanup()
        with pytest.raises(RuntimeError, match='completed safe'):
            owner.history_seed()
    anyio.run(scenario)


def test_history_retains_precheckpoint_failure_proof_without_reinterpreting_error_code():
    async def scenario():
        client = FakeClient()
        previous = owner_for(client)
        async with previous.inside_live_session():
            await previous.call_tool('dimension_set_value', ARGS)
            client.rows[0].update(status='failed', error={'code': 'stale_revision'}, mutation=None)
        assert previous.cleanup_gate.can_cleanup()
        seed = previous.history_seed()
        class ReadOnlyRestart(FakeClient):
            async def call_tool(self, name, arguments=None, **kwargs):
                assert name == 'document_list'
                self.calls.append((name, deepcopy(arguments)))
                read = job(arguments, mutates=False, status='succeeded')
                read['operation_id'] = 'restart-read-op'
                self.rows.append(read)
                return raw({'status': 'succeeded', 'operation_id': read['operation_id']})
        reopened = ReadOnlyRestart()
        reopened.rows = deepcopy(client.rows)
        # No mutation spec/code whitelist in the new read-only owner: its
        # permission comes solely from the exact previous safe history seed.
        owner = helper.VerifierSupervisor(reopened, tool_specs={'document_list': SPECS['document_list']},
            journal_reader=lambda: deepcopy(reopened.rows), trusted_history=seed,
            readonly_restart=True, poll_interval=.001)
        async with owner.inside_live_session():
            await owner.call_tool('document_list', {'request_id': 'new-read'})
        assert owner.cleanup_gate.can_cleanup()
        assert reopened.calls == [('document_list', {'request_id': 'new-read'})]
    anyio.run(scenario)


@pytest.mark.parametrize('fresh_checkout', [False, True])
def test_read_only_sqlite_snapshot_sees_wal_and_never_recovers_or_rewrites_jobs(tmp_path, fresh_checkout):
    # Existing private parent avoids creating a pytest temp directory with an
    # incompatible Windows ACL. These unique files belong only to this test.
    base = tmp_path / 'checkout' / 'work' if fresh_checkout else HELPER.parent.parent / 'work'
    if fresh_checkout:
        assert not base.exists()
    # work/ is ignored by Git and is absent on a fresh CI checkout.
    base.mkdir(parents=True, exist_ok=True)
    path = base / ('lifecycle-readonly-test-' + uuid.uuid4().hex + '.sqlite')
    writer = sqlite3.connect(path)
    try:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.executescript('''PRAGMA user_version=3;
            CREATE TABLE jobs(operation_id TEXT, request_id TEXT, operation TEXT, payload TEXT,
                              status TEXT, result TEXT, error TEXT, created_at REAL);
            CREATE TABLE mutations(operation_id TEXT, before_state TEXT, verification TEXT, reconciliation TEXT, phase TEXT);''')
        record = job()
        writer.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',
            (record['operation_id'], record['request_id'], record['operation'], json.dumps(record['payload']),
             'running', None, None, 1.))
        writer.commit()
        result = helper.read_journal(path)
        assert result[0]['status'] == 'running' and result[0]['mutation'] is None
        assert writer.execute('SELECT status FROM jobs').fetchone()[0] == 'running'
        assert writer.execute('SELECT COUNT(*) FROM mutations').fetchone()[0] == 0
        assert path.exists()
        missing = base / ('missing-' + path.name)
        with pytest.raises(sqlite3.OperationalError):
            helper.read_journal(missing)
        assert not missing.exists(), 'mode=ro must never create a journal.'
    finally:
        writer.close()
        for owned in (path, path.with_name(path.name + '-wal'), path.with_name(path.name + '-shm')):
            assert owned.resolve().parent == base.resolve()
            owned.unlink(missing_ok=True)
