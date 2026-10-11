"""Explicit native open facade; domain owns resolution and postconditions."""

import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


def register_native_document_open_tools(app, runtime, response, failure):
    async def dispatch(operation, request_id, arguments, timeout_s, mutate=False):
        try:
            job = await (runtime.mutate if mutate else runtime.read)(
                request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def document_prepare_open_native(request_id: str, filename: str, document_type: str,
            configuration: str, read_only: Annotated[bool, Field(strict=True)] = False,
            timeout_s: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=120)] = 10.) -> ResponseEnvelope:
        """Prepare explicit native file open with a complete application revision.

        The domain validates absolute native path/type/configuration, read-only
        policy and exact source/dependency file manifest against the full live
        baseline. No implicit last-used configuration or already-loaded adoption.
        Return server-owned application_id and native_file_id for execute; the
        model to open has no invented document_id. Preparation is not CAD open
        acceptance. read_only=False is always part of the durable arguments.
        """
        return await dispatch('document.prepare_open_native', request_id, dict(filename=filename,
            document_type=document_type, configuration=configuration, read_only=read_only), timeout_s)

    @app.tool()
    async def document_open_native(request_id: str, document_id: str, configuration: str,
            expected_revision: str, native_file_id: str,
            read_only: Annotated[bool, Field(strict=True)] = False,
            timeout_s: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=120)] = 10.) -> ResponseEnvelope:
        """Open the prepared native file once for its exact application target.

        document_id must be the server-owned application_id from prepare, with
        explicit configuration/native_file_id/expected_revision and matching
        read-only policy. Durable application checkpoint precedes guard/native
        execution. Success requires zero native errors/warnings, exact returned
        and dependency handles, native configuration/modes and full baseline
        postconditions. Throwing calls and unproved effects retain an application
        hold; no automatic retry/adoption/COM cancellation. request_id replays
        the same job; timeout limits waiting only. Poll job_get for late results.
        """
        return await dispatch('document.open_native', request_id, dict(document_id=document_id,
            configuration=configuration, expected_revision=expected_revision,
            native_file_id=native_file_id, read_only=read_only), timeout_s, True)
