"""Explicit durable save to the current bound native file."""
import sqlite3
from typing import Annotated
from pydantic import Field
from .contracts import ResponseEnvelope
from .jobs import JobError


def register_native_document_save_tools(app, runtime, response, failure):
    async def dispatch(operation, request_id, arguments, timeout_s, mutate=False):
        try:
            job = await (runtime.mutate if mutate else runtime.read)(request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'], context=job['payload']['context'],
                            data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def document_prepare_save_native(request_id: str, document_id: str, configuration: str,
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10.) -> ResponseEnvelope:
        """Prepare native part/assembly/drawing Save3 to its existing bound file.

        Explicit active configuration; no activation/first save/rename/copy/checkout
        or saving referenced documents. Revision binds complete open metadata,
        configs/update stamps/read-only/edit state/views and hashed native files.
        5000 documents,512 MiB/file,2 GiB files; no partial checkpoint. Scope
        native_document_current_file_save_v1 is a lifecycle/file observation
        revision, not a full BREP/arbitrary add-in revision.
        """
        return await dispatch('document.prepare_save_native', request_id,
                              dict(document_id=document_id, configuration=configuration), timeout_s)

    @app.tool()
    async def document_save_native(request_id: str, document_id: str, configuration: str, expected_revision: str,
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10.) -> ResponseEnvelope:
        """Save the exact prepared native document once to its current bound file.

        Durable application checkpoint then guard and one Save3 Silent call.
        True/zero native errors/warnings, unchanged path/config/view, cleared
        needs_save and hashed output required. Other open documents/files unchanged.
        Failed writes with changed effects and COM errors retain an application
        hold; no automatic rewrite/deletion/save-flag reset/retry. Guard is not a
        filesystem CAS against outsiders. First save/open/close are separate.
        request_id returns same job; timeout limits waiting, not COM. Poll job_get.
        """
        return await dispatch('document.save_native', request_id, dict(document_id=document_id,
            configuration=configuration, expected_revision=expected_revision), timeout_s, True)
