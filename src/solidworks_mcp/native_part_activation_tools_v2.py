"""Bounded explicit part activation facade; no implicit change of open policy."""

import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


def register_native_part_activation_tools(app, runtime, response, failure):
    async def dispatch(operation, request_id, arguments, timeout_s, mutate=False):
        try:
            job = await (runtime.mutate if mutate else runtime.read)(
                request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def document_prepare_activate_part_native(request_id: str, document_id: str, configuration: str,
            timeout_s: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=120)] = 10.) -> ResponseEnvelope:
        """Prepare explicit activation of an already-open writable rectangular part.

        One configuration and a self-contained blind rectangular base; every
        neighbor must admit the full passive part oracle. Returns the complete
        application revision. Preparation does not activate/switch configuration.
        Unsupported profiles and incomplete observations are refused.
        """
        return await dispatch('document.prepare_activate_part_native', request_id,
                              dict(document_id=document_id, configuration=configuration), timeout_s)

    @app.tool()
    async def document_activate_part_native(request_id: str, document_id: str, configuration: str,
            expected_revision: str,
            timeout_s: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=120)] = 10.) -> ResponseEnvelope:
        """Activate the explicit prepared part once; preserve all other observed state.

        Complete revision/checkpoint, exact native identity and independent
        post-release readback are required. No open/configuration change or inverse
        retry. An already-active target is a verified no-op. Unknown retains an
        application hold; timeout only limits waiting. Reuse request_id to replay
        the same job and poll job_get for late results. Native acceptance is separate.
        """
        return await dispatch('document.activate_part_native', request_id,
                              dict(document_id=document_id, configuration=configuration,
                                   expected_revision=expected_revision), timeout_s, True)
