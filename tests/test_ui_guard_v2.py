"""One-shot UI guard lifecycle and native side-effect faults using plain fakes."""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.ui_guard import ModelUiGuard


class Model:
    def __init__(self, state=0):
        self.state = state
        self.calls = []
        self.lock_effect = 2
        self.unlock_effect = 0
        self.lock_error = None
        self.unlock_error = None
        self.reads = []

    def GetBlockingState(self):
        self.calls.append(('get', threading.get_ident()))
        if self.reads:
            value = self.reads.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return self.state

    def Lock(self):
        self.calls.append(('lock', threading.get_ident()))
        self.state = self.lock_effect
        if self.lock_error:
            raise self.lock_error

    def UnLock(self):
        self.calls.append(('unlock', threading.get_ident()))
        self.state = self.unlock_effect
        if self.unlock_error:
            raise self.unlock_error


def names(model):
    return [name for name, thread in model.calls]


def test_success_has_only_verified_owner_thread_0_2_0_lifecycle():
    model = Model()
    guard = ModelUiGuard(model)
    with guard as entered:
        assert entered is guard
        assert model.state == 2
    assert model.state == 0
    assert names(model) == ['get', 'lock', 'get', 'get', 'unlock', 'get']
    assert {thread for name, thread in model.calls} == {threading.get_ident()}
    assert guard._model is None
    assert guard.evidence == {'original_state': 0, 'locked_state': 2, 'released_state': 0}
    guard.close()
    assert len(model.calls) == 6


@pytest.mark.parametrize('state', [1, 2, 3, -1, 99])
def test_existing_or_unknown_block_is_never_borrowed_or_unlocked(state):
    model = Model(state)
    guard = ModelUiGuard(model)
    with pytest.raises(ExecutionFailure) as error:
        with guard:
            pytest.fail('Blocked model must not enter the operation.')
    assert error.value.code == 'ui_guard_already_blocked' and error.value.uncertain is False
    assert names(model) == ['get'] and model.state == state
    guard.close()
    assert names(model) == ['get']


@pytest.mark.parametrize('state', [False, True, '0', None, 0.0])
def test_malformed_preflight_state_never_attempts_native_lock(state):
    model = Model(state)
    with pytest.raises(ExecutionFailure) as error:
        ModelUiGuard(model).__enter__()
    assert error.value.code == 'ui_guard_preflight_failed' and error.value.uncertain is False
    assert names(model) == ['get']


def test_acquisition_is_neither_nested_nor_reusable():
    model = Model()
    guard = ModelUiGuard(model)
    with guard:
        before = list(model.calls)
        with pytest.raises(ExecutionFailure) as error:
            guard.__enter__()
        assert error.value.code == 'ui_guard_reentry'
        assert model.calls == before and model.state == 2
    before = list(model.calls)
    with pytest.raises(ExecutionFailure):
        guard.__enter__()
    assert model.calls == before


def test_close_before_enter_is_native_free_and_retires_guard():
    model = Model()
    guard = ModelUiGuard(model)
    guard.close()
    guard.close()
    with pytest.raises(ExecutionFailure):
        guard.__enter__()
    assert model.calls == [] and guard._model is None


def test_wrong_thread_enter_and_close_never_call_native_and_owner_can_cleanup():
    model = Model()
    guard = ModelUiGuard(model)
    with ThreadPoolExecutor(max_workers=1) as pool:
        for function in (guard.__enter__, guard.close):
            with pytest.raises(ExecutionFailure) as error:
                pool.submit(function).result(timeout=2)
            assert error.value.code == 'wrong_apartment' and error.value.uncertain is False
    assert model.calls == []
    guard.__enter__()
    before = list(model.calls)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ExecutionFailure) as error:
            pool.submit(guard.close).result(timeout=2)
        assert error.value.code == 'wrong_apartment' and error.value.uncertain is True
    assert model.calls == before and model.state == 2
    guard.close()
    assert model.state == 0


def test_body_exception_is_preserved_after_verified_release():
    model = Model()
    original = RuntimeError('Operation callback failed.')
    with pytest.raises(RuntimeError) as error:
        with ModelUiGuard(model):
            raise original
    assert error.value is original and model.state == 0


def test_baseexception_body_also_releases_without_swallowing():
    model = Model()
    original = KeyboardInterrupt('Synthetic interrupt.')
    with pytest.raises(KeyboardInterrupt) as error:
        with ModelUiGuard(model):
            raise original
    assert error.value is original and model.state == 0


def test_exception_after_native_lock_effect_releases_owned_lock_before_rejecting():
    model = Model()
    original = RuntimeError('Lock response failed after side effect.')
    model.lock_error = original
    with pytest.raises(ExecutionFailure) as error:
        with ModelUiGuard(model):
            pytest.fail('Failed acquisition must not run the body.')
    assert error.value.code == 'ui_guard_lock_failed' and error.value.uncertain is False
    assert error.value.__cause__ is original
    assert model.state == 0
    assert names(model) == ['get', 'lock', 'get', 'unlock', 'get']


def test_exception_before_lock_effect_proves_zero_without_blind_unlock():
    model = Model()
    model.lock_effect = 0
    model.lock_error = RuntimeError('Failed before lock applied.')
    with pytest.raises(ExecutionFailure) as error:
        ModelUiGuard(model).__enter__()
    assert error.value.uncertain is False and model.state == 0
    assert names(model) == ['get', 'lock', 'get']


@pytest.mark.parametrize('state', [0, 1, 3, -1])
def test_successful_lock_call_without_held_two_rejects_unknown_ownership(state):
    model = Model()
    model.lock_effect = state
    with pytest.raises(ExecutionFailure) as error:
        ModelUiGuard(model).__enter__()
    assert error.value.code == 'ui_guard_lock_unconfirmed' and error.value.uncertain is True
    assert names(model) == ['get', 'lock', 'get'] and model.state == state


@pytest.mark.parametrize('state', [1, 3, -1])
def test_failed_lock_with_unknown_state_does_not_release_possible_foreign_lock(state):
    model = Model()
    model.lock_effect = state
    model.lock_error = RuntimeError('Unknown acquisition outcome.')
    with pytest.raises(ExecutionFailure) as error:
        ModelUiGuard(model).__enter__()
    assert error.value.code == 'ui_guard_acquisition_cleanup_unconfirmed'
    assert error.value.uncertain is True
    assert names(model) == ['get', 'lock', 'get'] and model.state == state


def test_failed_first_lock_readback_attempts_only_confirmed_owned_cleanup():
    model = Model()
    model.reads = [0, RuntimeError('Readback failed.'), 2, 0]
    with pytest.raises(ExecutionFailure) as error:
        ModelUiGuard(model).__enter__()
    assert error.value.code == 'ui_guard_lock_unconfirmed' and error.value.uncertain is True
    assert model.state == 0
    assert names(model) == ['get', 'lock', 'get', 'get', 'unlock', 'get']


def test_unreadable_failed_acquisition_does_not_blindly_unlock():
    model = Model()
    model.lock_error = RuntimeError('Native Lock failed.')
    model.reads = [0, RuntimeError('Cannot inspect lock ownership.')]
    guard = ModelUiGuard(model)
    with pytest.raises(ExecutionFailure) as error:
        guard.__enter__()
    assert error.value.uncertain is True
    assert names(model) == ['get', 'lock', 'get'] and model.state == 2
    guard.close()
    assert names(model) == ['get', 'lock', 'get']  # No automatic retry after uncertainty.


@pytest.mark.parametrize('state', [0, 1, 3, 99])
def test_lost_lock_at_exit_is_unknown_and_never_unlocks_a_foreign_state(state):
    model = Model()
    guard = ModelUiGuard(model)
    with pytest.raises(ExecutionFailure) as error:
        with guard:
            model.state = state
    assert error.value.code == 'ui_guard_lock_lost' and error.value.uncertain is True
    assert 'unlock' not in names(model) and model.state == state
    before = list(model.calls)
    guard.close()
    assert model.calls == before


@pytest.mark.parametrize('state', [0, 2, 3])
def test_unlock_error_is_unknown_even_if_native_effect_already_released(state):
    model = Model()
    model.unlock_effect = state
    model.unlock_error = RuntimeError('UnLock acknowledgement failed.')
    with pytest.raises(ExecutionFailure) as error:
        with ModelUiGuard(model):
            pass
    assert error.value.code == 'ui_guard_cleanup_unconfirmed' and error.value.uncertain is True
    assert names(model).count('unlock') == 1


def test_evidence_is_detached_json_without_model_or_native_calls():
    import json
    model = Model()
    guard = ModelUiGuard(model)
    assert guard.evidence == {'original_state': None, 'locked_state': None, 'released_state': None}
    with guard:
        detached = guard.evidence
        detached['locked_state'] = 'tampered'
        assert guard.evidence['locked_state'] == 2
        before = list(model.calls)
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert json.loads(pool.submit(lambda: json.dumps(guard.evidence)).result(timeout=2)) == {
                'original_state': 0, 'locked_state': 2, 'released_state': None}
        assert model.calls == before
    assert guard.evidence['released_state'] == 0


def test_zero_release_evidence_does_not_hide_unlock_error():
    model = Model()
    model.unlock_error = RuntimeError('Lost release acknowledgement.')
    guard = ModelUiGuard(model)
    with pytest.raises(ExecutionFailure) as error:
        with guard:
            pass
    assert error.value.uncertain is True
    assert guard.evidence == {'original_state': 0, 'locked_state': 2, 'released_state': 0}


def test_operation_and_release_errors_are_both_preserved_as_uncertainty():
    model = Model()
    model.unlock_error = RuntimeError('Cleanup failure.')
    original = ValueError('Operation failure.')
    with pytest.raises(ExecutionFailure) as error:
        with ModelUiGuard(model):
            raise original
    assert error.value.uncertain is True
    assert 'Cleanup failure.' in str(error.value) and 'Operation failure.' in str(error.value)
    assert error.value.__cause__ is original


def test_unreadable_ownership_at_exit_never_attempts_unlock():
    model = Model()
    with pytest.raises(ExecutionFailure) as error:
        with ModelUiGuard(model):
            model.reads = [RuntimeError('Cannot inspect lock ownership.')]
    assert error.value.code == 'ui_guard_cleanup_unconfirmed' and error.value.uncertain is True
    assert 'unlock' not in names(model)


def test_unlock_readback_failure_remains_unknown_after_effect():
    model = Model()
    with pytest.raises(ExecutionFailure) as error:
        with ModelUiGuard(model):
            model.reads = [2, RuntimeError('Readback after UnLock failed.')]
    assert error.value.uncertain is True and model.state == 0
    assert names(model).count('unlock') == 1


def test_reentrant_close_during_unlock_never_attempts_a_second_native_release():
    model = Model()
    guard = ModelUiGuard(model)
    original_unlock = model.UnLock

    def unlock_with_reentry():
        before = list(model.calls)
        with pytest.raises(ExecutionFailure) as error:
            guard.close()
        assert error.value.code == 'ui_guard_lifecycle_error' and error.value.uncertain is True
        assert model.calls == before
        original_unlock()

    model.UnLock = unlock_with_reentry
    with guard:
        pass
    assert model.state == 0 and names(model).count('unlock') == 1


def test_successful_unlock_call_without_zero_readback_stays_unknown():
    model = Model()
    model.unlock_effect = 2
    with pytest.raises(ExecutionFailure) as error:
        with ModelUiGuard(model):
            pass
    assert error.value.code == 'ui_guard_cleanup_unconfirmed' and error.value.uncertain is True
    assert model.state == 2 and names(model).count('unlock') == 1


def test_wrong_thread_exit_leaves_owned_lock_for_correct_owner_without_native_calls():
    model = Model()
    guard = ModelUiGuard(model)
    guard.__enter__()
    before = list(model.calls)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ExecutionFailure) as error:
            pool.submit(guard.__exit__, None, None, None).result(timeout=2)
        assert error.value.code == 'wrong_apartment' and error.value.uncertain is True
    assert model.calls == before and model.state == 2
    assert guard.__exit__(None, None, None) is False
    assert model.state == 0
