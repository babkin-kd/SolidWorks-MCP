"""Lazy CAD connection plus durable read jobs, with apartment-safe shutdown."""

import threading
import json
import uuid

from .documents import DocumentCatalog, rejected
from .geometry import GeometryCatalog
from .components import ComponentCatalog
from .mass_measurement import MassMeasurementCatalog
from .bounds_measurement import BoundsMeasurementCatalog
from .features import FeatureCatalog
from .dimensions import DimensionCatalog
from .part_creation import PartCreationCatalog
from .part_cut import PartCutCatalog
from .part_hole import PartHoleCatalog
from .part_hole_edit import PartHoleEditCatalog
from .part_pattern import PartPatternCatalog
from .part_fillet import PartFilletCatalog
from .part_revolve import PartRevolveCatalog
from .sheet_profile import SheetProfileCatalog
from .sheet_flat_state import SheetFlatStateCatalog
from .sheet_parameters import SheetParameterCatalog
from .sheet_edge_flange import SheetEdgeFlangeCatalog
from .sheet_flange_flat_state import SheetFlangeFlatStateCatalog
from .document_creation import DocumentCreationCatalog
from .sketches import SketchCatalog
from .exports_v2 import ExportCatalog
from .jobs import JobError, JobRunner, _json


MUTATING_OPERATIONS = ('measurement.mass', 'feature.rename', 'dimension.set_value', 'export.execute', 'part.create_base_extrusion', 'document.create_part', 'sketch.set_dimension', 'part.create_corner_cut', 'part.create_base_revolve', 'part.create_through_hole', 'part.set_hole_dimension', 'part.create_linear_hole_pattern', 'part.create_edge_fillet', 'sheet.create_l_profile', 'sheet.set_flat_state', 'sheet.set_parameters', 'sheet.create_edge_flange', 'sheet.set_flange_flat_state')
READ_OPERATIONS = ('component.list', 'component.get', 'component.bodies', 'measurement.bounds', 'measurement.prepare_mass', 'document.list', 'document.get', 'geometry.list', 'geometry.get', 'feature.list', 'feature.get', 'feature.dependencies', 'feature.deletion_structure', 'feature.deletion_context', 'dimension.list', 'dimension.get', 'export.prepare', 'part.prepare_base_extrusion', 'document.list_templates', 'document.prepare_create_part', 'sketch.get', 'sketch.prepare_dimension_change', 'part.prepare_corner_cut', 'part.prepare_base_revolve', 'part.prepare_through_hole', 'part.prepare_hole_dimension_change', 'part.prepare_linear_hole_pattern', 'part.prepare_edge_fillet', 'sheet.prepare_l_profile', 'sheet.prepare_flat_state', 'sheet.prepare_parameters', 'sheet.prepare_edge_flange', 'sheet.prepare_flange_flat_state')

def _worker_factory():
    try:
        from .com_worker import ComWorker
    except ImportError as exc:
        raise JobError('cad_unavailable', 'CAD access requires Windows and pywin32.') from exc
    from .errors import SolidWorksError
    try:
        return ComWorker(pump_messages=True)
    except SolidWorksError as exc:
        raise JobError('cad_unavailable', str(exc)) from exc


def _catalog_factory():
    from .cad_documents import SolidWorksDocuments
    return DocumentCatalog(SolidWorksDocuments())


class Runtime:
    def __init__(self, store, *, worker_factory=_worker_factory, catalog_factory=_catalog_factory,
                 approved_output_root=None, timings=None):
        self.store = store
        self.timings = timings
        self._worker_factory = worker_factory
        self._catalog_factory = catalog_factory
        self._runner = None
        self._catalog = None
        self._geometry = None
        self._measurements = None
        self._bounds = None
        self._components = None
        self._features = None
        self._dimensions = None
        self._parts = None
        self._cuts = None
        self._holes = None
        self._hole_edits = None
        self._patterns = None
        self._fillets = None
        self._revolves = None
        self._sheet_profiles = None
        self._sheet_states = None
        self._sheet_flange_states = None
        self._sheet_parameters = None
        self._sheet_edge_flanges = None
        self._document_creation = None
        self._sketches = None
        self._exports = None
        self._approved_output_root = approved_output_root
        self._connection_epoch = None
        self._lock = threading.RLock()
        self._closed = False

    @property
    def export_output_configured(self):
        """Report operator configuration without filesystem or CAD discovery."""
        return self._approved_output_root is not None

    def _execute(self, operation, arguments, operation_id=None):
        if self._catalog is None:
            try:
                self._catalog = self._catalog_factory()  # Always called on the STA.
            except Exception as exc:
                if operation in ('measurement.mass', 'feature.rename', 'dimension.set_value', 'export.execute', 'part.create_base_extrusion', 'document.create_part', 'sketch.set_dimension', 'part.create_corner_cut', 'part.create_base_revolve', 'part.create_through_hole', 'part.set_hole_dimension', 'part.create_linear_hole_pattern', 'part.create_edge_fillet','sheet.create_l_profile','sheet.set_flat_state','sheet.set_parameters','sheet.create_edge_flange','sheet.set_flange_flat_state'):
                    raise rejected(getattr(exc, 'code', 'cad_connection_failed'), str(exc)) from exc
                raise
            self._connection_epoch = 'connection_' + uuid.uuid4().hex
        try:
            if operation == 'document.list':
                return self._catalog.list()
            if operation == 'document.get':
                return self._catalog.get(**arguments)
            if operation in ('document.list_templates', 'document.prepare_create_part', 'document.create_part'):
                if self._document_creation is None:
                    self._document_creation = DocumentCreationCatalog(self._catalog, self.store, self._connection_epoch)
                if operation == 'document.list_templates':
                    return self._document_creation.list_templates()
                if operation == 'document.prepare_create_part':
                    return self._document_creation.prepare_create_part(**arguments)
                return self._document_creation.create_part(operation_id, **arguments)
            if operation in ('component.list','component.get','component.bodies'):
                if self._components is None:self._components=ComponentCatalog(self._catalog)
                method={'component.list':'list','component.get':'get','component.bodies':'bodies'}[operation]
                return getattr(self._components,method)(**arguments)
            if operation == 'measurement.bounds':
                if self._bounds is None:self._bounds=BoundsMeasurementCatalog(self._catalog)
                return self._bounds.measure(**arguments)
            if operation in ('measurement.prepare_mass','measurement.mass'):
                if self._measurements is None:
                    self._measurements = MassMeasurementCatalog(self._catalog,self.store,self._connection_epoch)
                if operation == 'measurement.prepare_mass':
                    return self._measurements.prepare(**arguments)
                return self._measurements.measure(operation_id,**arguments)
            if operation in ('geometry.list', 'geometry.get') and self._geometry is None:
                self._geometry = GeometryCatalog(self._catalog)
            if operation == 'geometry.list':
                return self._geometry.list(**arguments)
            if operation == 'geometry.get':
                return self._geometry.get(**arguments)
            if operation.startswith('feature.') and self._features is None:
                self._features = FeatureCatalog(self._catalog, self.store, self._connection_epoch,
                    mutation_guard=getattr(self._catalog.adapter, 'mutation_guard', None))
            if operation == 'feature.list':
                return self._features.list(**arguments)
            if operation == 'feature.get':
                return self._features.get(**arguments)
            if operation == 'feature.dependencies':
                return self._features.dependencies(**arguments)
            if operation == 'feature.deletion_context':
                return self._features.deletion_context(**arguments)
            if operation == 'feature.deletion_structure':
                return self._features.deletion_structure(**arguments)
            if operation == 'feature.rename':
                return self._features.rename(operation_id, **arguments)
            if operation.startswith(('dimension.', 'part.', 'sketch.','sheet.')) and self._dimensions is None:
                self._dimensions = DimensionCatalog(self._catalog, self.store, self._connection_epoch,
                    mutation_guard=getattr(self._catalog.adapter, 'mutation_guard', None))
            if operation == 'dimension.list':
                return self._dimensions.list(**arguments)
            if operation == 'dimension.get':
                return self._dimensions.get(**arguments)
            if operation == 'dimension.set_value':
                return self._dimensions.set_value(operation_id, **arguments)
            if operation.startswith('sketch.') and self._sketches is None:
                self._sketches = SketchCatalog(self._dimensions)
            if operation == 'sketch.get':
                return self._sketches.get(**arguments)
            if operation == 'sketch.prepare_dimension_change':
                return self._sketches.prepare_dimension_change(**arguments)
            if operation == 'sketch.set_dimension':
                return self._sketches.set_dimension(operation_id, **arguments)
            if operation in ('sheet.prepare_edge_flange','sheet.create_edge_flange'):
                if self._sheet_edge_flanges is None:self._sheet_edge_flanges=SheetEdgeFlangeCatalog(self._dimensions)
                if operation=='sheet.prepare_edge_flange':return self._sheet_edge_flanges.prepare_edge_flange(**arguments)
                return self._sheet_edge_flanges.create_edge_flange(operation_id,**arguments)
            if operation in ('sheet.prepare_parameters','sheet.set_parameters'):
                if self._sheet_parameters is None:self._sheet_parameters=SheetParameterCatalog(self._dimensions)
                if operation=='sheet.prepare_parameters':return self._sheet_parameters.prepare_parameters(**arguments)
                return self._sheet_parameters.set_parameters(operation_id,**arguments)
            if operation in ('sheet.prepare_flange_flat_state','sheet.set_flange_flat_state'):
                if self._sheet_flange_states is None:self._sheet_flange_states=SheetFlangeFlatStateCatalog(self._dimensions)
                if operation=='sheet.prepare_flange_flat_state':return self._sheet_flange_states.prepare_flat_state(**arguments)
                return self._sheet_flange_states.set_flat_state(operation_id,**arguments)
            if operation in ('sheet.prepare_flat_state','sheet.set_flat_state'):
                if self._sheet_states is None:self._sheet_states=SheetFlatStateCatalog(self._dimensions)
                if operation=='sheet.prepare_flat_state':return self._sheet_states.prepare_flat_state(**arguments)
                return self._sheet_states.set_flat_state(operation_id,**arguments)
            if operation in ('sheet.prepare_l_profile','sheet.create_l_profile'):
                if self._sheet_profiles is None:self._sheet_profiles=SheetProfileCatalog(self._dimensions)
                if operation=='sheet.prepare_l_profile':return self._sheet_profiles.prepare_l_profile(**arguments)
                return self._sheet_profiles.create_l_profile(operation_id,**arguments)
            if operation in ('part.prepare_corner_cut', 'part.create_corner_cut'):
                if self._sketches is None:
                    self._sketches = SketchCatalog(self._dimensions)
                if self._cuts is None:
                    self._cuts = PartCutCatalog(self._sketches)
                if operation == 'part.prepare_corner_cut':
                    return self._cuts.prepare_corner_cut(**arguments)
                return self._cuts.create_corner_cut(operation_id, **arguments)
            if operation in ('part.prepare_through_hole','part.create_through_hole'):
                if self._sketches is None:
                    self._sketches = SketchCatalog(self._dimensions)
                if self._holes is None:
                    self._holes = PartHoleCatalog(self._sketches)
                if operation=='part.prepare_through_hole':
                    return self._holes.prepare_through_hole(**arguments)
                return self._holes.create_through_hole(operation_id,**arguments)
            if operation in ('part.prepare_hole_dimension_change', 'part.set_hole_dimension'):
                if self._sketches is None:
                    self._sketches = SketchCatalog(self._dimensions)
                if self._hole_edits is None:
                    self._hole_edits = PartHoleEditCatalog(self._sketches)
                if operation == 'part.prepare_hole_dimension_change':
                    return self._hole_edits.prepare_dimension_change(**arguments)
                return self._hole_edits.set_dimension(operation_id, **arguments)
            if operation in ('part.prepare_base_revolve', 'part.create_base_revolve'):
                if self._revolves is None:
                    self._revolves = PartRevolveCatalog(self._dimensions)
                if operation == 'part.prepare_base_revolve':
                    return self._revolves.prepare_base_revolve(**arguments)
                return self._revolves.create_base_revolve(operation_id, **arguments)
            if operation in ('part.prepare_linear_hole_pattern','part.create_linear_hole_pattern'):
                if self._sketches is None:
                    self._sketches=SketchCatalog(self._dimensions)
                if self._patterns is None:
                    self._patterns=PartPatternCatalog(self._sketches)
                if operation=='part.prepare_linear_hole_pattern':
                    return self._patterns.prepare_linear_hole_pattern(**arguments)
                return self._patterns.create_linear_hole_pattern(operation_id,**arguments)
            if operation in ('part.prepare_edge_fillet','part.create_edge_fillet'):
                if self._sketches is None:
                    self._sketches=SketchCatalog(self._dimensions)
                if self._fillets is None:
                    self._fillets=PartFilletCatalog(self._sketches)
                if operation=='part.prepare_edge_fillet':
                    return self._fillets.prepare_edge_fillet(**arguments)
                return self._fillets.create_edge_fillet(operation_id,**arguments)
            if operation.startswith('part.') and self._parts is None:
                self._parts = PartCreationCatalog(self._dimensions)
            if operation == 'part.prepare_base_extrusion':
                return self._parts.prepare_base_extrusion(**arguments)
            if operation == 'part.create_base_extrusion':
                return self._parts.create_base_extrusion(operation_id, **arguments)
            if operation.startswith('export.') and self._exports is None:
                from .cad_exports_v2 import CadExportsAdapter
                self._exports = ExportCatalog(self._catalog, self.store, self._connection_epoch,
                    self._approved_output_root, adapter=CadExportsAdapter(self._catalog.adapter),
                    mutation_guard=getattr(self._catalog.adapter, 'mutation_guard', None))
            if operation == 'export.prepare':
                return self._exports.prepare(**arguments)
            if operation == 'export.execute':
                return self._exports.execute(operation_id, **arguments)
            raise rejected('unsupported_operation', 'No domain implementation for this operation.')
        except Exception as exc:
            # Domain rejections retain identities. Unexpected native failures
            # retire the connection; the next request reconnects with fresh IDs.
            if not isinstance(exc, JobError):
                self._release_catalog()
            raise

    async def read(self, request_id, operation, arguments, *, timeout_s=10):
        return await self._dispatch(request_id, operation, arguments, timeout_s=timeout_s, mutates=False)

    async def mutate(self, request_id, operation, arguments, *, timeout_s=10):
        return await self._dispatch(request_id, operation, arguments, timeout_s=timeout_s, mutates=True)

    async def _dispatch(self, request_id, operation, arguments, *, timeout_s, mutates):
        # Validate before recording/dispatch. A bad timeout must not start CAD.
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not 0 <= timeout_s <= 120:
            raise JobError('invalid_timeout', 'timeout_s must be finite and between 0 and 120.')
        allowed = MUTATING_OPERATIONS if mutates else READ_OPERATIONS
        if operation not in allowed:
            raise JobError('unsupported_operation', 'No domain implementation for this operation.')
        if operation.startswith('export.') and self._approved_output_root is None:
            raise JobError('export_output_not_configured', 'A server-owned export output directory is required.')
        arguments = json.loads(_json(arguments))
        with self._lock:
            if self._closed:
                raise JobError('runtime_stopped', 'This runtime no longer accepts new jobs.')
            if self._runner is None:
                worker = self._worker_factory()
                if hasattr(worker, 'add_finalizer'):
                    worker.add_finalizer(self._release_catalog)
                self._runner = JobRunner(self.store, worker, timings=self.timings)
            runner = self._runner
            context = {key: arguments[key] for key in ('document_id', 'configuration',
                       'expected_observation_revision', 'expected_revision', 'body_id', 'object_id', 'dimension_id') if key in arguments}
            job = runner.submit(request_id, operation, arguments,
                (lambda job_id: self._execute(operation, arguments, job_id)) if mutates
                    else (lambda: self._execute(operation, arguments)), context=context,
                mutates=mutates, pass_operation_id=mutates,
                verify=(lambda result: isinstance(result, dict) and result.get('verified') is True) if mutates else None)
        return await runner.wait(job['operation_id'], timeout_s=timeout_s)

    def _release_catalog(self):
        catalog, self._catalog = self._catalog, None
        self._geometry = None
        self._measurements = None
        self._bounds = None
        self._components = None
        self._holes = None
        self._hole_edits = None
        self._patterns = None
        self._fillets = None
        self._features = None
        self._dimensions = None
        self._parts = None
        self._cuts = None
        self._revolves = None
        self._sheet_profiles = None
        self._sheet_states = None
        self._sheet_flange_states = None
        self._sheet_parameters = None
        self._sheet_edge_flanges = None
        self._document_creation = None
        self._sketches = None
        self._exports = None
        self._connection_epoch = None
        if catalog is not None:
            catalog.close()

    def shutdown(self, timeout_s=5):
        with self._lock:
            if not self._closed:
                self._closed = True
                if self._runner is not None:
                    # After pending reads, before CoUninitialize. No COM proxies
                    # are destroyed on the event loop even after a late result.
                    try:
                        self._runner.worker.submit(self._release_catalog)
                    except Exception:
                        if not hasattr(self._runner.worker, 'add_finalizer'):
                            raise
                        # A failed pumping apartment releases the catalog using
                        # its registered STA finalizer before CoUninitialize.
            runner = self._runner
        if runner is None:
            self.store.close()
            return True
        return runner.shutdown(timeout_s=timeout_s)
