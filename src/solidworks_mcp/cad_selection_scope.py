"""One-shot temporary selection scope, entered only after a durable checkpoint."""

from contextlib import contextmanager
from types import SimpleNamespace

from . import binding
from .jobs import ExecutionFailure


@contextmanager
def preserved_selection(adapter, model, *, state=None, label='dimension'):
    state = state if state is not None else SimpleNamespace(selection_uncertain=False)
    code = label + '_selection_unconfirmed'
    if state.selection_uncertain:
        raise ExecutionFailure(code, 'An earlier selection scope remains unconfirmed.', uncertain=True)
    def manager():
        # ISelectionMgr is transient: acquire it again after selection/native
        # rebuild effects rather than retaining one proxy for the whole job.
        return binding.wrap(model.SelectionManager, adapter._module.ISelectionMgr)
    selection = manager()
    original = adapter._mass_selection_snapshot(selection)  # Read-only canonical objects/marks.
    state.selection_uncertain = True
    try:
        suspended = selection.SuspendSelectionList()
    except BaseException as exc:
        raise ExecutionFailure(code, 'Native selection suspension is unknown; no blind resume.', uncertain=True) from exc
    if type(suspended) is not int or suspended != int(bool(original)):
        raise ExecutionFailure(code, 'Selection suspension acknowledgement is unknown; no blind resume.', uncertain=True)
    primary = None
    try:
        if adapter._mass_selection_snapshot(manager()):
            raise ExecutionFailure(code, 'Private selection list did not start empty.', uncertain=True)
        yield
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            manager().ResumeSelectionList()  # Native void; exactly one attempt.
            if adapter._mass_selection_snapshot(manager()) != original:
                raise RuntimeError('Original canonical objects/marks were not restored.')
        except BaseException as exc:
            failure = ExecutionFailure(code, 'Original selection restoration was not confirmed.', uncertain=True)
            if primary is not None: failure.add_note('Original operation error: ' + repr(primary))
            raise failure from exc
        state.selection_uncertain = False
