"""Registered clean CloseDoc bridge, without getters on retired targets."""

from pathlib import Path

from . import binding
from .application_close_guard import ApplicationCloseGuard
from .cad_selection_scope import preserved_selection
from .constants import SW_DONT_REBUILD_ACTIVE_DOC
from .documents import rejected
from .timings_v2 import timed_call


MAX_CLOSE_MODELS = 5000
SW_SEARCH_DOCUMENT_FOLDERS = 0  # swSearchFolderTypes_e.swDocumentType


class CadNativeDocumentCloseMixin:
    def native_close_windows(self):
        # Two independently registered enumerations must agree before a close.
        # GetNext is bounded and uses canonical COM identity, never model names.
        listed = self.documents()
        tokens = [self.identity(model) for model in listed]
        if len(tokens) > MAX_CLOSE_MODELS or any(token in tokens[:index] for index, token in enumerate(tokens)):
            raise rejected('native_close_census_invalid', 'Complete unique bounded native model census required.')
        chained = []
        current = binding.wrap(self._sw.GetFirstDocument(), self._module.IModelDoc2)
        while current is not None:
            token = self.identity(current)
            if token in chained or len(chained) >= MAX_CLOSE_MODELS:
                raise rejected('native_close_census_invalid', 'GetNext enumeration is repeated or exceeds the document budget.')
            chained.append(token)
            current = binding.wrap(current.GetNext(), self._module.IModelDoc2)
        if len(chained) != len(tokens) or any(token not in tokens for token in chained):
            raise rejected('native_close_census_invalid', 'GetDocuments and the complete GetNext enumeration disagree.')
        frame = binding.wrap(self._sw.Frame(), self._module.IFrame)
        if frame is None:
            raise rejected('native_close_census_invalid', 'The native application frame is unavailable.')
        count = frame.GetModelWindowCount()
        if type(count) is not int or not 0 <= count <= MAX_CLOSE_MODELS:
            raise rejected('native_close_census_invalid', 'Complete bounded native window count required.')
        raw_windows = frame.ModelWindows
        if raw_windows is None:
            raw_windows = ()
        if not isinstance(raw_windows, (tuple, list)) or len(raw_windows) != count:
            raise rejected('native_close_census_invalid', 'Frame window enumeration/count disagree.')
        result, handles = [], set()
        for raw in raw_windows:
            window = binding.wrap(raw, self._module.IModelWindow)
            model = binding.wrap(window.ModelDoc, self._module.IModelDoc2)
            hwnd, title = window.HWndx64, window.Title
            if (model is None or self.identity(model) not in tokens or type(hwnd) is not int
                    or not 0 < hwnd < 2 ** 63 or hwnd in handles or type(title) is not str):
                raise rejected('native_close_census_invalid', 'Each unique 64-bit window must identify a current native model.')
            handles.add(hwnd)
            result.append((model, dict(hwnd=hwnd, title=title)))
        if frame.GetModelWindowCount() != count:
            raise rejected('native_session_changed_during_read', 'Native window count changed during enumeration.')
        return result

    def native_close_model_context(self, model):
        visible = model.Visible
        if type(visible) is not bool:
            raise rejected('native_close_census_invalid', 'Strict native model visibility required.')
        extension = binding.wrap(model.Extension, self._module.IModelDocExtension)
        # Search=False leaves search settings untouched; complete transitive and
        # broken reference paths are returned rather than silently omitted.
        raw = extension.GetDependencies(True, False, False, True, False)
        if raw is None:
            raw = ()
        if (not isinstance(raw, (tuple, list)) or len(raw) % 2 or len(raw) > MAX_CLOSE_MODELS * 2
                or any(type(item) is not str for item in raw)):
            raise rejected('native_close_dependencies_unavailable', 'Complete native dependency name/path pairs required.')
        paths = list(raw[1::2])
        if any(not path or not Path(path).is_absolute() for path in paths):
            raise rejected('native_close_dependencies_unavailable', 'Broken or unresolved dependency paths prohibit this close scope.')
        return dict(visible=visible, dependencies=paths, mode=self.native_save_context(model))

    def native_close_application_context(self):
        result = dict(user_control=self._sw.UserControl, visible=self._sw.Visible,
                      current_directory=self._sw.GetCurrentWorkingDirectory(),
                      search_folders=self._sw.GetSearchFolders(SW_SEARCH_DOCUMENT_FOLDERS))
        if (type(result['user_control']) is not bool or type(result['visible']) is not bool
                or any(type(result[key]) is not str for key in ('current_directory', 'search_folders'))):
            raise rejected('native_close_census_invalid', 'Strict native application ownership/visibility/search settings required.')
        return result

    def native_close_guard(self, survivor_models, retiring_document_ids):
        return ApplicationCloseGuard(self._sw, survivor_models,
            lambda model, state: preserved_selection(self, model, state=state, label='native_document_close'),
            retiring_document_ids)

    def close_native_document(self, model, native_name):
        if type(native_name) is not str or not native_name.strip():
            raise rejected('native_close_name_ambiguous', 'An explicit prepared nonempty native name is required.')
        # Domain already checked identity, clean state, full impact and revision.
        # Native void is only a returned-call acknowledgement. No target getter
        # here or after CloseDoc; actual retirement is established by the census.
        timed_call('com', self._sw.CloseDoc, native_name)
        return dict(native_call_returned=True)

    def activate_native_close_survivor(self, model):
        expected = self.identity(model)
        title = model.GetTitle()
        if type(title) is not str or not title.strip():
            raise rejected('native_close_activation_unconfirmed', 'The explicit live survivor needs a nonempty native title.')
        raw = timed_call('com', self._sw.ActivateDoc3, title, False, SW_DONT_REBUILD_ACTIVE_DOC, 0)
        if not isinstance(raw, tuple) or len(raw) != 2 or type(raw[1]) is not int or raw[1] not in (0, 2):
            raise rejected('native_close_activation_unconfirmed', 'Registered activation handle/error acknowledgement required.')
        returned = binding.wrap(raw[0], self._module.IModelDoc2)
        active = self.active_document()
        if returned is None or active is None or self.identity(returned) != expected or self.identity(active) != expected:
            raise rejected('native_close_activation_unconfirmed', 'Explicit surviving model activation was not confirmed.')
