"""Public export facades backed by the accepted internal export path.

No registration at import time, CAD calls, client-owned output directory or
filesystem access here. Runtime owns job idempotency, server output root and
all native/revision/publication verification. This module never retries a job.
"""

import sqlite3
from typing import Annotated, Literal

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


def register_export_tools(app, runtime, response, failure):
    """Register two implemented-domain facades on the caller's existing app.

    Runtime must be configured with approved_output_root from server/operator
    configuration; neither tool accepts a directory or overwriting option.
    response/failure are the same envelope factories used by the calling app.
    Registration alone is not native acceptance or a capability announcement.
    """

    async def dispatch(request_id, operation, arguments, timeout_s, *, mutates):
        try:
            method = runtime.mutate if mutates else runtime.read
            job = await method(request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def export_prepare(
        request_id: str,
        document_id: str,
        configuration: str,
        file_format: Literal['stl', 'step', 'parasolid'],
        filename: str,
        units: Literal['', 'mm', 'm', 'in'] = '',
        timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10,
    ) -> ResponseEnvelope:
        """Prepare a scoped revision for exporting an explicitly active solid part.

        Native geometry is limited to supported planar polyhedral BREP; curved,
        mesh or ambiguous bodies fail explicitly. No activation/rebuild/source
        save. Pass one plain filename under the server-configured output root:
        .stl/.step/.x_t must match stl/step/parasolid. Existing files are rejected.
        STL requires explicit mm/m/in because the file has no unit metadata.
        STEP/Parasolid require units=""; STEP units come from its declaration,
        with consistent SI length contexts in a complete file up to 4 MiB.
        Parasolid units remain unknown without independent roundtrip evidence.
        Use the returned revision with export_part and exactly the same options.
        This is a read job: no preferences or output file are changed. A fresh
        snapshot needs a new request_id; repeated requests retrieve the same job.
        Timeout returns queued/running status; inspect job_get by operation_id.
        """
        return await dispatch(request_id, 'export.prepare', {
            'document_id': document_id, 'configuration': configuration,
            'format': file_format, 'filename': filename, 'units': units,
        }, timeout_s, mutates=False)

    @app.tool()
    async def export_part(
        request_id: str,
        document_id: str,
        configuration: str,
        expected_revision: str,
        file_format: Literal['stl', 'step', 'parasolid'],
        filename: str,
        units: Literal['', 'mm', 'm', 'in'] = '',
        timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10,
    ) -> ResponseEnvelope:
        """Export a prepared active solid part with durable scoped verification.

        expected_revision comes from export_prepare for the same document,
        active configuration, format, filename and units; observation/feature
        revisions do not authorize export. Runtime checkpoints before native
        preference changes, restores preferences and verifies supported source
        geometry/state before publishing one file without overwrite. Errors or
        warnings require inspection; publication is not a CAD/filesystem
        transaction. Source preservation covers the declared analytical scope.
        The verified result contains a manifest with file hash, frame and unit
        evidence; geometry roundtrip is not implied. staging_cleanup explicitly
        reports a removed or independently verified retained empty directory.
        Output location comes only
        from server configuration. No automatic activation/rebuild/source save.
        A timeout does not cancel COM: poll job_get using the returned operation_id.
        Reuse request_id to retrieve the same job; unknown outcomes require
        reconciliation, never an automatic retry under a new request_id.
        """
        return await dispatch(request_id, 'export.execute', {
            'document_id': document_id, 'configuration': configuration,
            'expected_revision': expected_revision, 'format': file_format,
            'filename': filename, 'units': units,
        }, timeout_s, mutates=True)

    return app
