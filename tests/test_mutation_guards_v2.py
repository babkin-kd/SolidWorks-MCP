"""Application checkpoints precede native UI writes; release is part of success."""

from concurrent.futures import Future
import sqlite3

import pytest

from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.mutations import MutationCoordinator, PreparedMutation
from solidworks_mcp.ui_guard import ModelUiGuard


class InlineWorker:
    def submit(self, function):
        future = Future()
        try:
            future.set_result(function())
        except BaseException as exc:
            future.set_exception(exc)
        return future


@pytest.fixture
def store(tmp_path):
    value = JobStore(tmp_path / 'jobs.sqlite')
    yield value
    value.close()


def exercise(store, *, request='r', fault=None, document='doc_a'):
    state = {'name': 'До'}
    events = []
    target = {'document_id': document, 'configuration': 'Основная', 'expected_revision': 'rev_1'}
    coordinator = MutationCoordinator(store, 'epoch')

    class Model:
        block = 0

        def GetBlockingState(self):
            return self.block

        def Lock(self):
            events.append('lock')
            job = store.list()['items'][0]
            assert job['status'] == 'running'
            assert job['mutation']['before_state']['_mutation_effect_scope'] == 'application'
            assert store.mutation_blockers('epoch', 'unrelated_document')
            if fault == 'acquire':
                raise RuntimeError('Lock rejected before applying')
            self.block = 2
            if fault == 'acquire_uncertain':
                self.block = 3

        def UnLock(self):
            events.append('unlock')
            assert store.list()['items'][0]['status'] == 'running'
            assert store.mutation_blockers('epoch', 'unrelated_document')
            self.block = 0
            if fault in ('release', 'body_and_release'):
                raise RuntimeError('UnLock acknowledgement lost')

    model = Model()

    def validate(prepared):
        events.append('validate')
        assert model.block == 2
        return fault != 'validation'

    def apply(prepared):
        events.append('apply')
        assert model.block == 2
        state['name'] = 'После'
        if fault in ('body', 'body_and_release'):
            raise RuntimeError('Native call changed the value before raising')
        return state.copy()

    def restore(before, prepared):
        events.append('restore')
        assert model.block == 2
        state.update(before)

    def run(operation_id):
        return coordinator.execute(operation_id, **target,
            prepare=lambda: PreparedMutation('rev_1', state.copy()), validate=validate,
            apply=apply, inspect=lambda _: state.copy(), verify=lambda b, a, v: a == v,
            restore=restore, verify_restored=lambda b, a: b == a,
            guard=lambda _: ModelUiGuard(model))

    result = JobRunner(store, InlineWorker()).submit(request, 'rename', {'name': 'После'}, run,
        context=target, mutates=True, pass_operation_id=True, verify=lambda r: r['verified'] is True)
    return result, state, events, model


def test_checkpoint_precedes_lock_and_release_proof_is_durable(store):
    result, state, events, model = exercise(store)
    evidence = {'original_state': 0, 'locked_state': 2, 'released_state': 0}
    assert result['status'] == 'succeeded'
    assert result['mutation']['phase'] == 'committed'
    assert result['result']['execution_guard'] == evidence
    assert result['mutation']['verification']['evidence']['execution_guard'] == evidence
    assert events == ['lock', 'validate', 'apply', 'unlock']
    assert state['name'] == 'После' and model.block == 0
    assert store.mutation_blockers('epoch', 'doc_b') == []


@pytest.mark.parametrize('fault,expected_events,phase', [
    ('acquire', ['lock'], 'not_started'),
    ('validation', ['lock', 'validate', 'unlock'], 'not_started'),
    ('body', ['lock', 'validate', 'apply', 'restore', 'unlock'], 'rolled_back'),
])
def test_known_failure_releases_ui_before_terminal_failed(store, fault, expected_events, phase):
    result, state, events, model = exercise(store, fault=fault)
    assert result['status'] == 'failed'
    assert result['mutation']['phase'] == phase
    assert state['name'] == 'До' and model.block == 0
    assert events == expected_events
    assert result['mutation']['verification']['evidence']['execution_guard']['released_state'] == 0
    assert store.mutation_blockers('epoch', 'doc_b') == []


@pytest.mark.parametrize('fault', ['acquire_uncertain', 'release'])
def test_uncertain_ui_effect_holds_all_documents_and_is_not_replayed(store, fault):
    result, state, events, model = exercise(store, fault=fault)
    assert result['status'] == 'unknown' and result['mutation']['phase'] == 'unresolved'
    assert state['name'] == ('После' if fault == 'release' else 'До')
    assert 'restore' not in events
    assert store.mutation_blockers('epoch', 'doc_b')
    retry, unchanged, no_events, _ = exercise(store, request='blocked', document='doc_b')
    assert retry['status'] == 'failed' and retry['error']['code'] == 'document_mutation_blocked'
    assert unchanged['name'] == 'До' and no_events == []
    duplicate, _, no_events, _ = exercise(store, fault=fault)
    assert duplicate['operation_id'] == result['operation_id']
    assert duplicate['status'] == 'unknown' and no_events == []


def test_storage_failure_after_release_does_not_write_or_restore_again(store, monkeypatch):
    original = store.verify_mutation

    def verify(operation_id, **kwargs):
        if 'execution_guard' in kwargs['evidence']:
            raise sqlite3.OperationalError('Lost disk after native release')
        return original(operation_id, **kwargs)

    monkeypatch.setattr(store, 'verify_mutation', verify)
    result, state, events, model = exercise(store)
    assert result['status'] == 'unknown'
    assert state['name'] == 'После' and model.block == 0
    assert events == ['lock', 'validate', 'apply', 'unlock']
    assert store.mutation_blockers('epoch', 'doc_b')


def test_unconfirmed_release_after_rollback_preserves_original_error_and_global_hold(store):
    result, state, events, model = exercise(store, fault='body_and_release')
    assert result['status'] == 'unknown' and result['mutation']['phase'] == 'unresolved'
    assert 'Native call changed the value' in result['error']['message']
    assert 'UnLock' in result['error']['message']
    assert state['name'] == 'До' and model.block == 0
    assert events == ['lock', 'validate', 'apply', 'restore', 'unlock']
    assert store.mutation_blockers('epoch', 'doc_b')
