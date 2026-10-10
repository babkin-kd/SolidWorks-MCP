"""Lazy CAD connection plus durable read jobs, with apartment-safe shutdown."""

import threading
import json
import uuid

from .documents import DocumentCatalog, rejected
from .geometry import GeometryCatalog
from .features import FeatureCatalog
from .dimensions import DimensionCatalog
from .part_creation import PartCreationCatalog
from .part_cut import PartCutCatalog
from .document_creation import DocumentCreationCatalog
from .sketches import SketchCatalog
from .exports_v2 import ExportCatalog
from .jobs import JobError, JobRunner, _json


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
                 approved_output_root=None):
        self.store = store
        self._worker_factory = worker_factory
        self._catalog_factory = catalog_factory
        self._runner = None
        self._catalog = None
        self._geometry = None
        self._features = None
        self._dimensions = None
        self._parts = None
        self._cuts = None
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
                if operation in ('feature.rename', 'dimension.set_value', 'export.execute', 'part.create_base_extrusion', 'document.create_part', 'sketch.set_dimension', 'part.create_corner_cut'):
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
            if operation.startswith(('dimension.', 'part.', 'sketch.')) and self._dimensions is None:
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
            if operation in ('part.prepare_corner_cut', 'part.create_corner_cut'):
                if self._sketches is None:
                    self._sketches = SketchCatalog(self._dimensions)
                if self._cuts is None:
                    self._cuts = PartCutCatalog(self._sketches)
                if operation == 'part.prepare_corner_cut':
                    return self._cuts.prepare_corner_cut(**arguments)
                return self._cuts.create_corner_cut(operation_id, **arguments)
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
        allowed = ('feature.rename', 'dimension.set_value', 'export.execute', 'part.create_base_extrusion', 'document.create_part', 'sketch.set_dimension', 'part.create_corner_cut') if mutates else (
            'document.list', 'document.get', 'geometry.list', 'geometry.get', 'feature.list', 'feature.get', 'feature.dependencies',
            'feature.deletion_structure', 'feature.deletion_context',
            'dimension.list', 'dimension.get', 'export.prepare', 'part.prepare_base_extrusion',
            'document.list_templates', 'document.prepare_create_part', 'sketch.get', 'sketch.prepare_dimension_change', 'part.prepare_corner_cut')
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
                self._runner = JobRunner(self.store, worker)
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
        self._features = None
        self._dimensions = None
        self._parts = None
        self._cuts = None
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
