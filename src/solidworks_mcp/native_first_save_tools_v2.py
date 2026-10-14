"""Bounded first native part save with explicit replacement identity."""
import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


def register_native_first_save_tools(app, runtime, response, failure):
    async def dispatch(operation, request_id, arguments, timeout_s, mutate=False):
        try:
            job = await (runtime.mutate if mutate else runtime.read)(
                request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def document_prepare_first_save_native(
        request_id: str, document_id: str, configuration: str, filename: str,
        timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10.,
    ) -> ResponseEnvelope:
        """Prepare first save of an exact active unsaved rectangular-base part.

        One visible writable configuration/window, independent blind base,
        no external references and empty source selection. All open neighbors
        must admit the complete passive part oracle. An unsupported baseline
        refuses before writing. filename is a new absolute local NTFS .SLDPRT
        path with a Russian stem, never an existing file or overwrite request.
        Revision binds the complete supported session/part/file observation.
        The replacement policy explicitly retires source IDs on success.
        This is a development candidate; installed native acceptance is separate.
        """
        return await dispatch('document.prepare_first_save_native', request_id,
                              dict(document_id=document_id, configuration=configuration,
                                   filename=filename), timeout_s)

    @app.tool()
    async def document_first_save_native(
        request_id: str, document_id: str, configuration: str, filename: str,
        expected_revision: str,
        timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10.,
    ) -> ResponseEnvelope:
        """Save the prepared unsaved part to a new native path once.

        Owned staging Copy/readback, no-replace NTFS publication, writable final
        open and full clone proof precede exact source retirement. Use the
        returned new document_id; source object IDs retire. Native reference
        mapping is evidence, not permission to reuse old public object IDs:
        resolve_saved_references_again requires fresh explicit resolution.
        Existing/raced destinations are never overwritten. Unknown/pending
        effects retain artifacts and application holds; do not repeat the CAD
        call with a new request_id. Replay returns the same durable job.
        timeout_s limits waiting only; poll job_get for the late result.
        """
        return await dispatch('document.first_save_native', request_id,
                              dict(document_id=document_id, configuration=configuration,
                                   filename=filename, expected_revision=expected_revision),
                              timeout_s, True)
