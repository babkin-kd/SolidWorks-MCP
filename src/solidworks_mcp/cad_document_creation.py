"""Exact returned-document ownership and bounded, unsaved part creation."""

from dataclasses import dataclass
import math

from . import binding
from .application_guard import ApplicationDocumentGuard
from .cad_selection_scope import preserved_selection
from .constants import SW_PREF_DEFAULT_TEMPLATE_PART, SW_DONT_REBUILD_ACTIVE_DOC
from .documents import rejected
from .jobs import ExecutionFailure


@dataclass
class NativeDocumentReceipt:
    baseline_models: tuple
    baseline_identities: tuple
    baseline_snapshots: tuple
    original_active: object
    original_active_identity: object
    model: object = None
    identity: object = None
    pending_creation: bool = False
    pending_close: bool = False
    restored: bool = False


class CadDocumentCreationMixin:
    def default_part_template(self):
        return str(self._sw.GetUserPreferenceStringValue(SW_PREF_DEFAULT_TEMPLATE_PART) or '')

    def active_document(self):
        return binding.wrap(self._sw.ActiveDoc, self._module.IModelDoc2)

    def application_visible(self):
        return bool(self._sw.Visible)

    def application_busy(self):
        return bool(self._sw.CommandInProgress)

    def document_editing_sketch(self, model):
        return model.GetActiveSketch2() is not None

    def document_view_snapshot(self, model):
        view = binding.wrap(model.ActiveView, self._module.IModelView)
        if view is None:
            return None
        orientation = binding.wrap(view.Orientation3, self._module.IMathTransform)
        translation = binding.wrap(view.Translation3, self._module.IMathVector)
        rotation, position, scale = list(orientation.ArrayData), list(translation.ArrayData), float(view.Scale2)
        if (len(rotation) != 16 or len(position) != 3 or scale <= 0 or
                not all(math.isfinite(value) for value in rotation + position + [scale])):
            raise rejected('document_view_unavailable', 'Complete finite native view state is required.')
        return {'orientation': rotation, 'translation': position, 'scale': scale}

    def document_creation_guard(self, models):
        return ApplicationDocumentGuard(self._sw, models,
            lambda model, state: preserved_selection(self, model, state=state, label='document_creation'))

    def new_document_receipt(self, models):
        active = self.active_document()
        return NativeDocumentReceipt(tuple(models), tuple(self.identity(model) for model in models),
            tuple(self.snapshot(model) for model in models), active,
            self.identity(active) if active is not None else None)

    def _owned_document(self, receipt):
        if receipt.pending_creation or receipt.pending_close or receipt.model is None or receipt.identity is None:
            raise ExecutionFailure('document_ownership_unconfirmed', 'No complete exact returned-document ownership.', uncertain=True)
        if self.identity(receipt.model) != receipt.identity or receipt.identity in receipt.baseline_identities:
            raise ExecutionFailure('document_ownership_unconfirmed', 'Returned document is not an owned new identity.', uncertain=True)
        current = self.documents()
        if sum(self.identity(model) == receipt.identity for model in current) != 1:
            raise rejected('created_document_not_current', 'Exact created document is not currently open.')
        return receipt.model

    def _empty_part_evidence(self, model):
        if int(model.GetType()) != 1 or model.GetPathName():
            return False
        configurations = list(model.GetConfigurationNames() or ())
        if len(configurations) != 1:
            return False
        context = self.dimension_context(model)
        features = self.features(model)
        return (not self.bodies(model, 'all') and not self.dimensions(model, features)
                and not any(str(item.GetTypeName2()) in ('ProfileFeature', '3DProfileFeature') for item in features)
                and not any(self.feature_summary(item)['error_code'] for item in features)
                and context['active_document'] and not context['read_only'] and not context['editing_sketch']
                and not context['external_reference_count'] and not context['equation_count']
                and not context['equations_linked'] and not context['design_table'] and not context['unsafe_feature_types']
                and not any(context['configuration_needs_rebuild'].values()))

    def create_empty_part_document(self, receipt, template, name, configuration_name):
        receipt.pending_creation = True  # A throwing NewDocument is never replayed/adopted by a delta.
        raw = self._sw.NewDocument(template, 0, 0, 0)
        if raw is None:
            raise ExecutionFailure('document_creation_no_handle', 'NewDocument returned no exact owned handle.', uncertain=True)
        model = binding.wrap(raw, self._module.IModelDoc2)
        receipt.model = model  # Retain the exact return before other native getters.
        token = self.identity(model)
        if token in receipt.baseline_identities:
            raise ExecutionFailure('document_creation_existing_handle', 'NewDocument returned a baseline document.', uncertain=True)
        receipt.identity = token
        receipt.pending_creation = False
        if not self._empty_part_evidence(model):
            raise rejected('unsupported_part_template', 'The configured template must produce one empty writable part configuration.')
        if model.SetTitle2(name) is not True or str(model.GetTitle()) != name:
            raise rejected('created_document_name_unconfirmed', 'Russian document title was not confirmed.')
        config = binding.wrap(model.GetActiveConfiguration(), self._module.IConfiguration)
        config.Name = configuration_name
        if str(config.Name) != configuration_name or list(model.GetConfigurationNames() or ()) != [configuration_name]:
            raise rejected('created_configuration_name_unconfirmed', 'Russian configuration name was not confirmed.')

    def created_document_identity(self, receipt):
        self._owned_document(receipt)
        return receipt.identity

    def created_document_evidence(self, receipt):
        if receipt.restored:
            return {'restored': True, 'complete': False}
        model = self._owned_document(receipt)
        active = self.active_document()
        config = binding.wrap(model.GetActiveConfiguration(), self._module.IConfiguration)
        return {'restored': False, 'complete': True, 'title': str(model.GetTitle()),
                'configuration': str(config.Name), 'empty_part': self._empty_part_evidence(model),
                'active': active is not None and self.identity(active) == receipt.identity,
                'unsaved': str(model.GetPathName()) == ''}

    def restore_created_document(self, receipt):
        model = self._owned_document(receipt)
        current = self.documents()
        tokens = [self.identity(item) for item in current]
        expected = list(receipt.baseline_identities) + [receipt.identity]
        if len(tokens) != len(expected) or any(token not in expected for token in tokens):
            raise ExecutionFailure('document_restore_foreign_effects', 'Foreign document changes prohibit scoped closure.', uncertain=True)
        if any(self.snapshot(item) != before for item, before in zip(receipt.baseline_models, receipt.baseline_snapshots)):
            raise ExecutionFailure('document_restore_foreign_effects', 'Existing document metadata changed; no closure attempted.', uncertain=True)
        active = self.active_document()
        title = str(model.GetTitle())
        if (active is None or self.identity(active) != receipt.identity or model.GetPathName()
                or int(model.GetType()) != 1 or sum(str(item.GetTitle()) == title for item in current) != 1):
            raise ExecutionFailure('document_restore_unsafe', 'Exact unsaved active owned part closure was not proved.', uncertain=True)
        receipt.pending_close = True
        self._sw.CloseDoc(title)  # Native void, once; never save, close baseline, or retry.
        if any(self.identity(item) == receipt.identity for item in self.documents()):
            raise ExecutionFailure('document_close_unconfirmed', 'Owned document absence was not confirmed.', uncertain=True)
        receipt.pending_close = False
        active = self.active_document()
        token = self.identity(active) if active is not None else None
        if token != receipt.original_active_identity:
            if receipt.original_active is None or token not in receipt.baseline_identities:
                raise ExecutionFailure('document_activation_restore_unsafe', 'Original activation cannot be restored safely.', uncertain=True)
            raw = self._sw.ActivateDoc3(receipt.original_active.GetTitle(), False, SW_DONT_REBUILD_ACTIVE_DOC, 0)
            restored = binding.wrap(raw[0] if isinstance(raw, tuple) else raw, self._module.IModelDoc2)
            if restored is None or self.identity(restored) != receipt.original_active_identity:
                raise ExecutionFailure('document_activation_restore_unconfirmed', 'Original active document was not restored.', uncertain=True)
        receipt.restored = True
