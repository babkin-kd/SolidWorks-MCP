"""Owner-thread model UI lock with verified acquisition and release.

This blocks native interactive model editing; it is not an atomic CAS or an
exclusion mechanism for other automation clients/add-ins. The caller must use
its durable application-scope checkpoint and revision/postcondition protocol.
No COM dependency is imported here; the model is an apartment-owned adapter.
"""

import threading

from .jobs import ExecutionFailure


class ModelUiGuard:
    """One-shot ``with ModelUiGuard(model)``; all native calls stay on its owner."""

    def __init__(self, model):
        if model is None:
            raise ValueError('An explicit native model is required.')
        self._model = model
        self._thread = threading.get_ident()
        self._state = 'new'
        self._lock_attempted = False
        self._evidence = {'original_state': None, 'locked_state': None, 'released_state': None}

    @property
    def evidence(self):
        """Detached JSON observations; values alone do not override an exit error."""
        return self._evidence.copy()

    def _check_thread(self):
        if threading.get_ident() != self._thread:
            raise ExecutionFailure('wrong_apartment',
                'The model UI guard must be used and released on its owning STA.',
                uncertain=self._lock_attempted and self._state != 'closed')

    def _blocking_state(self):
        state = self._model.GetBlockingState()
        if not isinstance(state, int) or isinstance(state, bool):
            raise RuntimeError('Native blocking state is not an integer.')
        return state

    def _retire(self):
        self._state = 'closed'
        self._model = None  # Release this native reference on the owning thread.

    def _release_owned(self, current):
        if current != 2:
            raise ExecutionFailure('ui_guard_lock_lost',
                f'Owned UI lock was not confirmed (state={current}); no UnLock attempted.',
                uncertain=True)
        release_error = None
        try:
            self._model.UnLock()
        except BaseException as exc:
            release_error = exc
        try:
            after = self._blocking_state()
        except BaseException as exc:
            raise ExecutionFailure('ui_guard_cleanup_unconfirmed',
                f'UI release readback failed: {exc}; UnLock error: {release_error}',
                uncertain=True) from exc
        self._evidence['released_state'] = after
        if release_error is not None or after != 0:
            raise ExecutionFailure('ui_guard_cleanup_unconfirmed',
                f'UI release was not cleanly confirmed (state={after}, UnLock error={release_error}).',
                uncertain=True) from release_error

    def __enter__(self):
        self._check_thread()
        if self._state != 'new':
            raise ExecutionFailure('ui_guard_reentry',
                'A model UI guard is one-shot; nested or repeated acquisition is prohibited.',
                uncertain=False)
        self._state = 'acquiring'
        try:
            before = self._blocking_state()
        except BaseException as exc:
            self._retire()
            raise ExecutionFailure('ui_guard_preflight_failed',
                f'Could not read the model blocking state before Lock: {exc}',
                uncertain=False) from exc
        self._evidence['original_state'] = before
        if before != 0:
            self._retire()
            raise ExecutionFailure('ui_guard_already_blocked',
                f'Model is already blocked (state={before}); existing locks are not borrowed.',
                uncertain=False)
        self._lock_attempted = True  # A throwing native call may still take effect.
        try:
            self._model.Lock()  # Native void return; only state readback proves acquisition.
        except BaseException as original:
            try:
                current = self._blocking_state()
                self._evidence['locked_state'] = current
                if current != 0:
                    self._release_owned(current)
                else:
                    self._evidence['released_state'] = 0
            except BaseException as cleanup:
                raise ExecutionFailure('ui_guard_acquisition_cleanup_unconfirmed',
                    f'Lock failed: {original}; cleanup: {cleanup}', uncertain=True) from original
            finally:
                self._retire()
            raise ExecutionFailure('ui_guard_lock_failed',
                f'Lock failed before entering the operation; UI state 0 was verified: {original}',
                uncertain=False) from original
        try:
            current = self._blocking_state()
        except BaseException as original:
            # Try a second read only to establish ownership for cleanup. Do not
            # blindly UnLock after an ambiguous response from the first read.
            try:
                current = self._blocking_state()
                self._evidence['locked_state'] = current
                self._release_owned(current)
            except BaseException as cleanup:
                raise ExecutionFailure('ui_guard_acquisition_cleanup_unconfirmed',
                    f'Lock readback failed: {original}; cleanup: {cleanup}', uncertain=True) from original
            finally:
                self._retire()
            raise ExecutionFailure('ui_guard_lock_unconfirmed',
                f'Lock readback failed; owned UI lock was released: {original}',
                uncertain=True) from original
        self._evidence['locked_state'] = current
        if current != 2:
            self._retire()
            raise ExecutionFailure('ui_guard_lock_unconfirmed',
                f'Lock did not confirm the required state 2 (state={current}); no operation or UnLock attempted.',
                uncertain=True)
        self._state = 'held'
        return self

    def close(self):
        """Release once on the owner; an uncertain release is never retried here."""
        self._check_thread()
        if self._state == 'closed':
            return
        if self._state == 'new':
            self._retire()
            return
        if self._state != 'held':
            raise ExecutionFailure('ui_guard_lifecycle_error',
                'UI guard acquisition or release is in progress; release is not reentrant.', uncertain=True)
        self._state = 'releasing'
        try:
            try:
                current = self._blocking_state()
            except BaseException as exc:
                raise ExecutionFailure('ui_guard_cleanup_unconfirmed',
                    f'Cannot confirm ownership before UnLock: {exc}', uncertain=True) from exc
            self._release_owned(current)
        finally:
            self._retire()

    def __exit__(self, exception_type, exception, traceback):
        try:
            self.close()
        except ExecutionFailure as release_error:
            if exception is not None:
                raise ExecutionFailure(release_error.code,
                    f'{release_error}; original operation error: {exception}', uncertain=True) from exception
            raise
        return False  # Preserve the original operation exception after a clean release.
