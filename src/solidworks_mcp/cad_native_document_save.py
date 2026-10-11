"""Registered native Save3 signature; no activation or SaveReferenced."""
from pathlib import Path
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
        document_type = model.GetType()
        editing_component = False
        if document_type == 2:
            raw = binding.wrap(model, self._module.IAssemblyDoc).GetEditTargetComponent()
            if raw is not None:
                root = binding.wrap(raw, self._module.IComponent2).IsRoot()
                if type(root) is not bool:
                    raise rejected('native_save_context_unavailable', 'Native edit target root state required.')
                editing_component = not root
        active_sketch = model.GetActiveSketch2()
        editing_sketch = active_sketch is not None
        drawing_state = None
        if document_type == 3:
            drawing = binding.wrap(model, self._module.IDrawingDoc)
            edit_sheet = drawing.GetEditSheet()
            if type(edit_sheet) is not bool:
                raise rejected('native_save_context_unavailable', 'Native drawing sheet edit state required.')
            # GetFirstView is the sheet itself; its sketch is active even in
            # normal drawing mode. Compare COM identities, never sketch names.
            sheet_view = binding.wrap(drawing.GetFirstView(), self._module.IView)
            sheet_sketch = sheet_view.GetSketch() if sheet_view is not None else None
            editing_sketch = (not edit_sheet or sheet_sketch is None or active_sketch is None
                              or self.identity(active_sketch) != self.identity(sheet_sketch))
            sheet = binding.wrap(drawing.GetCurrentSheet(), self._module.ISheet)
            names = list(drawing.GetSheetNames() or ())
            current = sheet.GetName() if sheet is not None else None
            if not names or any(type(name) is not str or not name for name in names) or current not in names:
                raise rejected('native_save_context_unavailable', 'Complete drawing sheet names/current sheet required.')
            drawing_state = dict(sheet_names=names, current_sheet=current,
                                 saved_display_title=Path(model.GetPathName()).stem + ' - ' + current)
        return dict(blocking_state=blocking, read_only_state=int(read_only), view_only=view_only,
                    editing_component=editing_component, editing_sketch=editing_sketch, drawing_state=drawing_state)

    def save_native_current_file(self, model):
        result = timed_call('com', model.Save3, 1, 0, 0)
        if not isinstance(result, tuple) or len(result) != 3:
            raise RuntimeError('Save3 did not return its registered Boolean/errors/warnings tuple.')
        return dict(success=result[0], errors=result[1], warnings=result[2])
