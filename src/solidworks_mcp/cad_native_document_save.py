"""Registered native Save3 signature; no activation or SaveReferenced."""
from .timings_v2 import timed_call
from .documents import rejected
from . import binding
from .application_guard import ApplicationModelMutationGuard
from .cad_selection_scope import preserved_selection


class CadNativeDocumentSaveMixin:
    def native_save_guard(self, models):
        return ApplicationModelMutationGuard(self._sw, models,
            lambda model, state: preserved_selection(self, model, state=state, label='native_document_save'))

    def native_save_context(self, model):
        blocking, read_only, view_only = model.GetBlockingState(), model.IsOpenedReadOnly(), model.IsOpenedViewOnly()
        if type(blocking) is not int or type(read_only) is not bool or type(view_only) is not bool:
            raise rejected('native_save_context_unavailable', 'Native blocking/read-only/view-only state required.')
        editing_component = (binding.wrap(model, self._module.IAssemblyDoc).GetEditTargetComponent() is not None
                             if model.GetType() == 2 else False)
        return dict(blocking_state=blocking, read_only_state=int(read_only), view_only=view_only,
                    editing_component=editing_component, editing_sketch=model.GetActiveSketch2() is not None)

    def save_native_current_file(self, model):
        result = timed_call('com', model.Save3, 1, 0, 0)
        if not isinstance(result, tuple) or len(result) != 3:
            raise RuntimeError('Save3 did not return its registered Boolean/errors/warnings tuple.')
        return dict(success=result[0], errors=result[1], warnings=result[2])
