"""Application close guard retaining only models that must survive CloseDoc.

The domain owns close-impact validation and the post-close census. This guard
never takes a native handle for a retiring document and never asserts that a
document actually closed. It keeps the existing one-shot CIP and survivor
UI/selection acquisition/release protocol.
"""

from itertools import islice

from .application_guard import ApplicationDocumentGuard


MAX_CLOSE_DOCUMENTS = 5000


def _bounded_documents(values, label):
    if isinstance(values, (str, bytes)):
        raise ValueError(f'{label} must be a collection, not a string.')
    try:
        result = tuple(islice(iter(values), MAX_CLOSE_DOCUMENTS + 1))
    except TypeError as exc:
        raise ValueError(f'{label} must be an iterable collection.') from exc
    if len(result) > MAX_CLOSE_DOCUMENTS:
        raise ValueError('Close guard document budget exceeds 5000.')
    return result


class ApplicationCloseGuard(ApplicationDocumentGuard):
    """Lock survivors only; retiring document IDs are evidence, not handles.

    Zero survivors is valid here. The domain must reject closing the last
    document in a background UserControl=False session before acquiring this
    guard. Native effects and actual retirement are verified by its census.
    """

    scope = 'application_document_close_guard_v1'

    def __init__(self, application, survivor_models, selection_scope, retiring_document_ids):
        survivors = _bounded_documents(survivor_models, 'survivor_models')
        retiring = _bounded_documents(retiring_document_ids, 'retiring_document_ids')
        if (not retiring or any(not isinstance(value, str) or not value.strip() for value in retiring)
                or len(set(retiring)) != len(retiring)):
            raise ValueError('Retiring document IDs must be unique nonempty strings.')
        if len(survivors) + len(retiring) > MAX_CLOSE_DOCUMENTS:
            raise ValueError('Survivors and retiring documents exceed the 5000-document budget.')
        self.retiring_document_ids = retiring
        super().__init__(application, survivors, selection_scope)

    @property
    def evidence(self):
        return {**super().evidence, 'retiring_document_ids': list(self.retiring_document_ids),
                'retiring_targets_locked_during_close': False}
