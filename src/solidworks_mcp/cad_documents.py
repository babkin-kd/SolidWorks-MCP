"""Read-only SolidWorks adapter. Construct, call and release only on the STA."""

import pythoncom

from . import binding
from .cad_geometry import CadGeometryMixin
from .cad_mass_properties import CadMassPropertiesMixin
from .cad_features import CadFeaturesMixin
from .cad_dimensions import CadDimensionsMixin
from .cad_deletion_context import CadDeletionContextMixin
from .cad_part_creation import CadPartCreationMixin
from .cad_part_cut import CadPartCutMixin
from .cad_part_hole import CadPartHoleMixin
from .cad_part_pattern import CadPartPatternMixin
from .cad_part_fillet import CadPartFilletMixin
from .cad_part_revolve import CadPartRevolveMixin
from .cad_document_creation import CadDocumentCreationMixin
from .cad_sketches import CadSketchesMixin
from .documents import rejected
from .errors import SolidWorksError
from .application_guard import ApplicationModelMutationGuard
from .cad_selection_scope import preserved_selection


class SolidWorksDocuments(CadMassPropertiesMixin, CadGeometryMixin, CadFeaturesMixin, CadDimensionsMixin, CadDeletionContextMixin, CadPartCreationMixin, CadPartCutMixin, CadPartHoleMixin, CadPartPatternMixin, CadPartFilletMixin, CadPartRevolveMixin, CadDocumentCreationMixin, CadSketchesMixin):
    def mutation_guard(self, model):
        return ApplicationModelMutationGuard(self._sw, [model],
            lambda current, state: preserved_selection(self, current, state=state, label='model_mutation'))

    def __init__(self):
        try:
            self._sw = binding.connect(show=False)
        except SolidWorksError as exc:
            raise rejected('cad_unavailable', str(exc)) from exc
        self._module = binding.module()
        self.revision = str(self._sw.RevisionNumber())

    def documents(self):
        return [binding.wrap(raw, self._module.IModelDoc2)
                for raw in self._sw.GetDocuments() or ()]

    def identity(self, model):
        # PyIUnknown compares canonical IUnknown addresses according to COM's
        # identity rules. Retaining the object also prevents pointer reuse while
        # the catalog is live. PyIUnknown is deliberately unhashable.
        return model._oleobj_.QueryInterface(pythoncom.IID_IUnknown)

    def snapshot(self, model):
        before = int(model.GetUpdateStamp())
        configurations = list(model.GetConfigurationNames() or ())
        raw = model.GetActiveConfiguration()
        active = binding.wrap(raw, self._module.IConfiguration).Name if raw is not None else ''
        result = {'title': str(model.GetTitle()), 'path': str(model.GetPathName()),
                  'document_type': {1: 'part', 2: 'assembly', 3: 'drawing'}.get(model.GetType(), 'unknown'),
                  'needs_save': bool(model.GetSaveFlag()), 'configurations': configurations,
                  'active_configuration': str(active), 'update_stamp': before}
        if int(model.GetUpdateStamp()) != before:
            raise rejected('document_changed_during_read', 'Document changed during metadata collection; read again.')
        return result

    def close(self):
        # Release the application proxy in its apartment. Never close user CAD
        # documents, change visibility, save, or quit SolidWorks on shutdown.
        self._sw = None
        self._module = None
