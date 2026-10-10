"""One-shot application command flag, never borrowed from another owner."""

import threading
from contextlib import ExitStack
from types import SimpleNamespace

from .jobs import ExecutionFailure
from .ui_guard import ModelUiGuard


class ApplicationDocumentGuard:
    def __init__(self, application, models, selection_scope):
        self.application = application
        self.models = tuple(models)
        self.selection_scope = selection_scope
        self.thread = threading.get_ident()
        self.state = 'new'
        self.owned = False
        self.stack = ExitStack()
        self.model_guards = []
        self.selection_states = []
        self.flag = {'original_command_in_progress': None, 'acquired': False, 'released': False}

    @property
    def evidence(self):
        return {'scope': 'application_document_create_guard_v1', **self.flag,
                'model_guards': [item.evidence for item in self.model_guards],
                'selection_preserved': self.state == 'closed' and
                    len(self.selection_states) == len(self.models) and
                    all(not state.selection_uncertain for state in self.selection_states)}

    def _thread(self):
        if threading.get_ident() != self.thread:
            raise ExecutionFailure('wrong_apartment', 'Application guard belongs to its STA.', uncertain=self.owned)

    def _read(self):
        value = self.application.CommandInProgress
        if type(value) is not bool:
            raise RuntimeError('CommandInProgress did not return a native Boolean.')
        return value

    def _release_flag(self):
        if not self.owned:
            return
        self.owned = False  # Never retry a throwing setter/release.
        try:
            if self._read() is not True:
                raise RuntimeError('Acknowledged application flag was lost.')
            self.application.CommandInProgress = False
            if self._read() is not False:
                raise RuntimeError('Application flag release did not read back False.')
        except BaseException as exc:
            raise ExecutionFailure('application_guard_release_unconfirmed', str(exc), uncertain=True) from exc
        self.flag['released'] = True

    def __enter__(self):
        self._thread()
        if self.state != 'new':
            raise ExecutionFailure('application_guard_reentry', 'Application guard is one-shot.', uncertain=False)
        self.state = 'acquiring'
        try:
            before = self._read()
        except BaseException as exc:
            self.state = 'closed'
            raise ExecutionFailure('application_guard_preflight_failed', str(exc), uncertain=False) from exc
        self.flag['original_command_in_progress'] = before
        if before:
            self.state = 'closed'
            raise ExecutionFailure('application_busy', 'An existing command flag is never borrowed.', uncertain=False)
        try:
            self.application.CommandInProgress = True
            if self._read() is not True:
                raise RuntimeError('Application flag acquisition was not acknowledged.')
        except BaseException as exc:
            # A failed setter can have taken effect. Read once to establish
            # ownership for release; never reissue acquisition or blindly reset.
            try:
                if self._read() is True:
                    self.owned = True
                    self._release_flag()
            except BaseException as cleanup:
                self.state = 'closed'
                raise ExecutionFailure('application_guard_acquisition_unconfirmed',
                    f'{exc}; cleanup: {cleanup}', uncertain=True) from exc
            self.state = 'closed'
            raise ExecutionFailure('application_guard_acquisition_unconfirmed', str(exc), uncertain=True) from exc
        self.owned = True
        self.flag['acquired'] = True
        self.stack.callback(self._release_flag)
        try:
            for model in self.models:
                guard = ModelUiGuard(model)
                self.model_guards.append(guard)
                self.stack.enter_context(guard)
                selection = SimpleNamespace(selection_uncertain=False)
                self.selection_states.append(selection)
                self.stack.enter_context(self.selection_scope(model, selection))
        except BaseException:
            try:
                self.stack.close()
            finally:
                self.state = 'closed'
            raise
        self.state = 'held'
        return self

    def __exit__(self, *exception):
        self._thread()
        try:
            return self.stack.__exit__(*exception)
        finally:
            self.state = 'closed'
