"""Exact-return native open bridge; domain checkpoint/impact checks are required.

This is not a public tool or a complete lifecycle operation. In particular a
normally returned OpenDoc6 and its receipt do not prove successful resolution,
survivor preservation or permission to close newly observed dependencies.
"""

from dataclasses import dataclass, field
from pathlib import Path
import threading

from . import binding
from .application_open_guard import ApplicationOpenGuard
from .cad_selection_scope import preserved_selection
from .constants import SW_OPEN_DOC_SILENT, SW_OPEN_DOC_READ_ONLY, SW_DONT_REBUILD_ACTIVE_DOC
from .documents import rejected
from .jobs import ExecutionFailure
from .native_document_save import EXTENSIONS, MAX_OPEN_DOCUMENTS
from .native_document_open_policy import DOCUMENT_TYPES, validate_native_open_arguments
from .timings_v2 import timed_call


@dataclass
class NativeOpenReceipt:
    baseline_models: tuple
    baseline_identities: tuple
    filename: str
    document_type: str
    configuration: str
    read_only: bool
    thread: int = field(default_factory=threading.get_ident)
    native_call_attempted: bool = False
    pending_open: bool = False
    native_call_returned: bool = False
    raw_model: object = None
    model: object = None
    identity: object = None
    errors: object = None
    warnings: object = None
    acknowledgement_valid: bool = False
    returned_new_identity: bool = False


@dataclass
class NativeActivationReceipt:
    model: object
    identity: object
    thread: int = field(default_factory=threading.get_ident)
    native_call_attempted: bool = False
    pending_activation: bool = False
    native_call_returned: bool = False
    raw_model: object = None
    native_error: object = None


class CadNativeDocumentOpenMixin:
    def new_native_activation_receipt(self, model):
        return NativeActivationReceipt(model, self.identity(model))

    def activate_native_open_document(self, receipt):
        if (type(receipt) is not NativeActivationReceipt or receipt.native_call_attempted
                or threading.get_ident() != receipt.thread):
            raise ExecutionFailure('native_open_activation_receipt_invalid', 'Activation requires one exact unused receipt on its STA.', uncertain=True)
        expected = receipt.identity
        title = receipt.model.GetTitle()
        if type(title) is not str or not title.strip():
            raise rejected('native_open_activation_unconfirmed', 'An exact live native model requires a nonempty title.')
        receipt.native_call_attempted = True
        receipt.pending_activation = True
        result = timed_call('com', self._sw.ActivateDoc3, title, False, SW_DONT_REBUILD_ACTIVE_DOC, 0)
        receipt.native_call_returned = True
        receipt.pending_activation = False
        if isinstance(result, tuple) and len(result) == 2:
            receipt.raw_model, receipt.native_error = result
        if (not isinstance(result, tuple) or len(result) != 2 or type(result[1]) is not int
                or result[1] not in (0, 2)):
            raise rejected('native_open_activation_unconfirmed', 'Registered no-rebuild activation acknowledgement required.')
        returned = binding.wrap(result[0], self._module.IModelDoc2)
        active = self.active_document()
        if returned is None or active is None or self.identity(returned) != expected or self.identity(active) != expected:
            raise rejected('native_open_activation_unconfirmed', 'The explicitly requested live model was not activated.')
        return dict(native_call_returned=True, native_error=result[1])

    def native_open_model_references(self, model):
        """Exact handles reached through the returned root, not roster deltas."""
        kind = model.GetType()
        if type(kind) is not int or kind not in (1, 2, 3):
            raise rejected('native_open_resolution_invalid', 'Only native part/assembly/drawing data can enter the resolved receipt.')
        if kind == 1:
            return []
        references = []
        if kind == 2:
            assembly = binding.wrap(model, self._module.IAssemblyDoc)
            count = assembly.GetComponentCount(False)
            values = assembly.GetComponents(False)
            if values is None:
                values = ()
            if (type(count) is not int or not 0 <= count <= MAX_OPEN_DOCUMENTS
                    or not isinstance(values, (tuple, list)) or len(values) != count):
                raise rejected('native_open_resolution_invalid', 'Complete bounded resolved component enumeration is required.')
            for raw in values:
                component = binding.wrap(raw, self._module.IComponent2)
                state = component.GetSuppression2()
                if (type(state) is not int or state not in (2, 3) or component.IsSpeedPak is not False
                        or component.IsVirtual is not False):
                    raise rejected('native_open_component_mode_unsupported', 'Resolved saved components only; no implicit lightweight/SpeedPak/virtual conversion.')
                target = binding.wrap(component.GetModelDoc2(), self._module.IModelDoc2)
                references.append((target, dict(path=component.GetPathName(), configuration=component.ReferencedConfiguration,
                    name=component.Name2, origin='component', native_suppression_state=state)))
            final_count = assembly.GetComponentCount(False)
            if type(final_count) is not int or final_count != count:
                raise rejected('native_open_resolution_changed', 'Component count changed while resolving native handles.')
        else:
            drawing = binding.wrap(model, self._module.IDrawingDoc)
            groups = drawing.GetViews()
            if groups is None:
                groups = ()
            if not isinstance(groups, (tuple, list)) or len(groups) > MAX_OPEN_DOCUMENTS:
                raise rejected('native_open_resolution_invalid', 'Complete bounded drawing sheet/view enumeration is required.')
            views = []
            for group in groups:
                if not isinstance(group, (tuple, list)) or len(views) + len(group) > MAX_OPEN_DOCUMENTS:
                    raise rejected('native_open_resolution_invalid', 'Complete bounded drawing view groups required.')
                views.extend(group)
            for index, raw in enumerate(views):
                view = binding.wrap(raw, self._module.IView)
                path = view.GetReferencedModelName()
                if type(path) is not str:
                    raise rejected('native_open_resolution_invalid', 'Drawing view reference names must be native strings.')
                if not path:
                    # Sheet view has no referenced model. Empty non-sheet views
                    # can be broken/detached; they are never silently omitted.
                    if type(view.Type) is not int or view.Type != 1:  # swDrawingSheet
                        raise rejected('native_open_drawing_reference_unavailable', 'An unresolved non-sheet drawing view cannot enter the receipt.')
                    continue
                target = binding.wrap(view.ReferencedDocument, self._module.IModelDoc2)
                references.append((target, dict(path=path, configuration=view.ReferencedConfiguration,
                    name=f'view_{index}', origin='drawing_view', native_suppression_state=None)))
        for target, info in references:
            if (target is None or type(info['path']) is not str or not Path(info['path']).is_absolute()
                    or type(info['configuration']) is not str or not info['configuration'].strip()
                    or type(info['name']) is not str or not info['name']):
                raise rejected('native_open_reference_handle_unavailable', 'Each native reference requires an exact live model, saved path, name and configuration.')
        return references

    def native_open_loaded_identity(self, filename):
        # Passive lookup cannot create a receipt or adopt referenced data.
        if type(filename) is not str or not Path(filename).is_absolute() or '\x00' in filename:
            raise rejected('native_document_path_required', 'Loaded-data lookup requires an absolute native path.')
        raw = timed_call('com', self._sw.GetOpenDocumentByName, filename)
        model = binding.wrap(raw, self._module.IModelDoc2)
        return self.identity(model) if model is not None else None

    def native_open_guard(self, baseline_models, baseline_document_ids):
        return ApplicationOpenGuard(self._sw, baseline_models,
            lambda model, state: preserved_selection(self, model, state=state, label='native_document_open'),
            baseline_document_ids)

    def new_native_open_receipt(self, models, filename, document_type, configuration, read_only):
        validate_native_open_arguments(filename, document_type, configuration, read_only)
        if isinstance(models, (str, bytes)):
            raise rejected('native_open_census_invalid', 'An exact baseline model collection is required.')
        # Bounded consumption protects against an incomplete/unbounded iterator.
        from itertools import islice
        try:
            baseline = tuple(islice(iter(models), MAX_OPEN_DOCUMENTS + 1))
        except TypeError as exc:
            raise rejected('native_open_census_invalid', 'An exact baseline model collection is required.') from exc
        if len(baseline) >= MAX_OPEN_DOCUMENTS:
            raise rejected('native_session_budget_exceeded', 'Opening a document must remain within 5000 models.')
        identities = tuple(self.identity(model) for model in baseline)
        if any(token in identities[:index] for index, token in enumerate(identities)):
            raise rejected('native_open_census_invalid', 'Baseline canonical model identities must be unique.')
        return NativeOpenReceipt(baseline, identities, filename, document_type, configuration, read_only)

    def open_native_document(self, receipt):
        if type(receipt) is not NativeOpenReceipt:
            raise rejected('native_open_receipt_invalid', 'An exact native open receipt is required.')
        if threading.get_ident() != receipt.thread:
            raise ExecutionFailure('wrong_apartment', 'Native open receipt belongs to its STA.', uncertain=receipt.native_call_attempted)
        if receipt.native_call_attempted:
            raise ExecutionFailure('native_open_receipt_reused', 'OpenDoc6 is one-shot; never replay a native call through its receipt.', uncertain=True)
        validate_native_open_arguments(receipt.filename, receipt.document_type, receipt.configuration, receipt.read_only)
        options = SW_OPEN_DOC_SILENT | (SW_OPEN_DOC_READ_ONLY if receipt.read_only else 0)
        receipt.native_call_attempted = True
        receipt.pending_open = True
        # Caller persists the pending native step before invoking this bridge.
        # A throwing native call remains pending, without delta-based adoption.
        result = timed_call('com', self._sw.OpenDoc6, receipt.filename,
                            DOCUMENT_TYPES[receipt.document_type], options, receipt.configuration, 0, 0)
        receipt.native_call_returned = True
        receipt.pending_open = False
        if not isinstance(result, tuple) or len(result) != 3:
            raise ExecutionFailure('native_open_acknowledgement_invalid', 'Registered OpenDoc6 must return a model, errors and warnings.', uncertain=True)
        raw, errors, warnings = result
        # Keep the exact returned raw model before wrapping or native getters.
        receipt.raw_model = raw
        receipt.errors, receipt.warnings = errors, warnings
        if raw is not None:
            receipt.model = binding.wrap(raw, self._module.IModelDoc2)
            receipt.identity = self.identity(receipt.model)
            if receipt.identity in receipt.baseline_identities:
                raise ExecutionFailure('native_open_existing_handle', 'Returned preexisting data is borrowed, never owned by this open.', uncertain=True)
            receipt.returned_new_identity = True
        if (type(errors) is not int or not 0 <= errors < 2 ** 31
                or type(warnings) is not int or not 0 <= warnings < 2 ** 31):
            raise ExecutionFailure('native_open_acknowledgement_invalid', 'Native error/warning outputs must be nonnegative 32-bit integers.', uncertain=True)
        receipt.acknowledgement_valid = True
        # A null return/nonzero codes are retained unchanged. Only the domain's
        # complete effect/rollback oracle may classify failure or success.
        return dict(native_call_returned=True, returned_new_identity=receipt.returned_new_identity,
                    errors=errors, warnings=warnings)

    def native_open_file_inventory(self, filename, document_type):
        """Passive native inventory, without Search=True or model adoption."""
        validate_native_open_arguments(filename, document_type,
                                       '' if document_type == 'drawing' else 'inventory', False)
        raw = timed_call('com', self._sw.GetDocumentDependencies2, filename, True, False, False)
        if raw is None:
            raw = ()
        if (not isinstance(raw, (tuple, list)) or len(raw) % 2 or len(raw) > MAX_OPEN_DOCUMENTS * 2
                or any(type(value) is not str for value in raw)):
            raise rejected('native_open_dependencies_unavailable', 'Complete bounded native dependency name/path pairs are required.')
        references = []
        for name, path in zip(raw[::2], raw[1::2]):
            if not name or not path or '\x00' in path or not Path(path).is_absolute():
                raise rejected('native_open_dependencies_unavailable', 'Unresolved or unnamed dependency paths cannot enter an open manifest.')
            kind = next((kind for kind, extension in EXTENSIONS.items() if Path(path).suffix.lower() == extension), None)
            if kind is None:
                raise rejected('native_open_dependency_unsupported', 'Every dependency must be a native CAD file.')
            references.append(dict(name=name, path=path, document_type=kind))
        configurations = []
        if document_type != 'drawing':
            values = timed_call('com', self._sw.GetConfigurationNames, filename)
            if (not isinstance(values, (tuple, list)) or not values or len(values) > MAX_OPEN_DOCUMENTS
                    or any(type(value) is not str or not value.strip() or '\x00' in value for value in values)
                    or len(set(values)) != len(values)):
                raise rejected('native_open_configurations_unavailable', 'Complete unique file configuration names are required.')
            configurations = list(values)
        return dict(dependencies=references, configurations=configurations)
