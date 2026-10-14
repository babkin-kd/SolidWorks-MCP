"""Preserve baseline models while opening data; phase UI release for activation.

This guard holds only preexisting model handles. New handles/dependencies are
owned and verified by the domain, not by this guard. Native UI release alone
does not prove successful open or survivor preservation.
"""

from itertools import islice

from .application_guard import ApplicationDocumentGuard
from .jobs import ExecutionFailure


MAX_OPEN_MODELS = 5000


class ApplicationOpenGuard(ApplicationDocumentGuard):
    scope = 'application_document_open_guard_v1'

    def __init__(self, application, baseline_models, selection_scope, baseline_document_ids):
        if isinstance(baseline_models, (str, bytes)) or isinstance(baseline_document_ids, (str, bytes)):
            raise ValueError('Baseline models and document IDs must be exact collections.')
        models = tuple(islice(iter(baseline_models), MAX_OPEN_MODELS))
        ids = tuple(islice(iter(baseline_document_ids), MAX_OPEN_MODELS))
        if len(models) >= MAX_OPEN_MODELS or len(ids) >= MAX_OPEN_MODELS:
            raise ValueError('Opening data must leave capacity within the 5000-model budget.')
        if (len(models) != len(ids) or any(type(value) is not str or not value.strip() for value in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError('Each preexisting model requires one unique explicit document ID.')
        self.baseline_document_ids = ids
        self.activation_ui_release = dict(attempted=False, verified=False)
        super().__init__(application, models, selection_scope)

    def release_baseline_ui_for_activation(self):
        """One native unlock phase, retaining CIP and selection scopes.

        The domain must prove the complete effect/survivor census before and
        after this phase and confirm explicit activation independently.
        """
        self._thread()
        if self.state != 'held' or self.activation_ui_release['attempted'] or not self.model_guards:
            raise ExecutionFailure('native_open_activation_guard_invalid', 'Activation release requires held baseline models and is one-shot.', uncertain=self.owned)
        self.activation_ui_release['attempted'] = True
        if not self.owned or self._read() is not True:
            raise ExecutionFailure('native_open_application_flag_lost', 'Owned application flag must remain held during UI release.', uncertain=True)
        for guard in reversed(self.model_guards):
            guard.close()
        self.activation_ui_release['verified'] = True

    @property
    def evidence(self):
        return {**super().evidence, 'baseline_document_ids': list(self.baseline_document_ids),
                'activation_ui_release': dict(self.activation_ui_release)}
