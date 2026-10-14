"""Explicit require-clean native close with declared hidden collateral."""
import sqlite3
from typing import Annotated
from pydantic import Field
from .contracts import ResponseEnvelope
from .jobs import JobError


def register_native_document_close_tools(app, runtime, response, failure):
    async def dispatch(operation, request_id, arguments, timeout_s, mutate=False):
        try:
            job = await (runtime.mutate if mutate else runtime.read)(request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'], context=job['payload']['context'],
                            data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def document_prepare_close_native(request_id: str, document_id: str, configuration: str,
            active_after_document_id: str = '',
            allowed_hidden_document_ids: Annotated[list[str], Field(max_length=5000)] = [],
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10.) -> ResponseEnvelope:
        """Prepare one require-clean CloseDoc for an explicit current configuration.

        Full two-pass models/windows/modes/views/dependencies/application/native
        files census. Exact nonactive hidden collateral IDs must be allowed;
        each retiring document must be clean. Active target needs an explicit
        visible survivor if windows remain; inactive close preserves activation.
        Incoming survivor references and final background window are rejected.
        5000 models/windows,512 MiB/file,2 GiB files. No dirty discard/data-unload
        claim; scope native_document_close_clean_v1 is a lifecycle census.
        """
        return await dispatch('document.prepare_close_native', request_id, dict(document_id=document_id,
            configuration=configuration, active_after_document_id=active_after_document_id,
            allowed_hidden_document_ids=allowed_hidden_document_ids), timeout_s)

    @app.tool()
    async def document_close_native(request_id: str, document_id: str, configuration: str, expected_revision: str,
            active_after_document_id: str = '',
            allowed_hidden_document_ids: Annotated[list[str], Field(max_length=5000)] = [],
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10.) -> ResponseEnvelope:
        """Close the prepared clean document and exact declared hidden collateral once.

        Durable application checkpoint precedes survivor-only UI/selection guard
        and native void CloseDoc. Success requires exact model/window retirement,
        explicit survivor activation and unchanged survivors/settings/all baseline
        native files, including retired files. No save/open/undo/automatic retry
        or UserControl/visibility change. Throwing calls and unproved effects hold
        the application; clean failure requires the original full census.
        request_id replays the same job; timeout limits waiting, not COM.
        """
        return await dispatch('document.close_native', request_id, dict(document_id=document_id,
            configuration=configuration, expected_revision=expected_revision,
            active_after_document_id=active_after_document_id, allowed_hidden_document_ids=allowed_hidden_document_ids),
            timeout_s, True)
