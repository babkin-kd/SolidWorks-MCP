"""Lazy CAD connection plus durable read jobs, with apartment-safe shutdown."""

import threading
import json

from .documents import DocumentCatalog, rejected
from .jobs import JobError, JobRunner, _json


def _worker_factory():
    try:
        from .com_worker import ComWorker
    except ImportError as exc:
        raise JobError('cad_unavailable', 'CAD access requires Windows and pywin32.') from exc
    from .errors import SolidWorksError
    try:
        return ComWorker()
    except SolidWorksError as exc:
        raise JobError('cad_unavailable', str(exc)) from exc


def _catalog_factory():
    from .cad_documents import SolidWorksDocuments
    return DocumentCatalog(SolidWorksDocuments())


class Runtime:
    def __init__(self, store, *, worker_factory=_worker_factory, catalog_factory=_catalog_factory):
        self.store = store
        self._worker_factory = worker_factory
        self._catalog_factory = catalog_factory
        self._runner = None
        self._catalog = None
        self._lock = threading.RLock()
        self._closed = False

    def _execute(self, operation, arguments):
        if self._catalog is None:
            self._catalog = self._catalog_factory()  # Always called on the STA.
        try:
            if operation == 'document.list':
                return self._catalog.list()
            if operation == 'document.get':
                return self._catalog.get(**arguments)
            raise rejected('unsupported_operation', 'No domain implementation for this operation.')
        except Exception as exc:
            # Domain rejections retain identities. Unexpected native failures
            # retire the connection; the next request reconnects with fresh IDs.
            if not isinstance(exc, JobError):
                self._release_catalog()
            raise

    async def read(self, request_id, operation, arguments, *, timeout_s=10):
        # Validate before recording/dispatch. A bad timeout must not start CAD.
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not 0 <= timeout_s <= 120:
            raise JobError('invalid_timeout', 'timeout_s must be finite and between 0 and 120.')
        if operation not in ('document.list', 'document.get'):
            raise JobError('unsupported_operation', 'No domain implementation for this operation.')
        arguments = json.loads(_json(arguments))
        with self._lock:
            if self._closed:
                raise JobError('runtime_stopped', 'This runtime no longer accepts new jobs.')
            if self._runner is None:
                self._runner = JobRunner(self.store, self._worker_factory())
            runner = self._runner
            context = {key: arguments[key] for key in ('document_id', 'configuration') if key in arguments}
            job = runner.submit(request_id, operation, arguments,
                                lambda: self._execute(operation, arguments), context=context)
        return await runner.wait(job['operation_id'], timeout_s=timeout_s)

    def _release_catalog(self):
        if self._catalog is not None:
            self._catalog.close()
            self._catalog = None

    def shutdown(self, timeout_s=5):
        with self._lock:
            if not self._closed:
                self._closed = True
                if self._runner is not None:
                    # After pending reads, before CoUninitialize. No COM proxies
                    # are destroyed on the event loop even after a late result.
                    self._runner.worker.submit(self._release_catalog)
            runner = self._runner
        if runner is None:
            self.store.close()
            return True
        return runner.shutdown(timeout_s=timeout_s)
