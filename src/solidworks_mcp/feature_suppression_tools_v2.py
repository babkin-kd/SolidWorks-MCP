"""Public facade for the bounded retained own-feature suppression domain.

Source implementation/registration and installed native acceptance are separate
gates. Unsupported native data profiles are refused rather than filled in.
"""
import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


SuppressionState = Annotated[bool, Field(strict=True)]
Wait = Annotated[float, Field(strict=True, ge=0, le=120, allow_inf_nan=False)]


def register_feature_suppression_tools(app, runtime, response, failure):
    async def dispatch(operation, request_id, arguments, timeout_s, *, mutate=False):
        try:
            job = await (runtime.mutate if mutate else runtime.read)(
                request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def feature_prepare_suppression(request_id: str, document_id: str, configuration: str,
            object_id: str, suppressed: SuppressionState, timeout_s: Wait = 10.) -> ResponseEnvelope:
        """Prepare suppression of an exact server-owned blind rectangular extrusion.

        Only the original retained ownership in the current connection epoch,
        an unsaved one-configuration part and complete supported session are
        admitted. A suppressed target requires its own original PID and retained
        canonical feature through the exact native state2 bridge; no name/GetID
        fallback. Returns the full revision, current state and expected effect.
        Preparation performs no suppression, rebuild, activation or save.
        Foreign/unsafe targets and incomplete observations are refused.
        Installed native acceptance is reported separately for each wheel.
        """
        return await dispatch('feature.prepare_suppression', request_id,
            dict(document_id=document_id, configuration=configuration,
                 object_id=object_id, suppressed=suppressed), timeout_s)

    @app.tool()
    async def feature_set_suppressed(request_id: str, document_id: str, configuration: str,
            object_id: str, suppressed: SuppressionState, expected_revision: str,
            timeout_s: Wait = 10.) -> ResponseEnvelope:
        """Set only the prepared retained extrusion's native suppression state.

        The explicit object/configuration and fresh full revision bind the entire
        supported session, checkpoint and postconditions. Preserve the retained
        original sketch, dimensions, references, neighbors, UI/files and original
        body name when the body returns. Foreign/unsafe/incomplete scope is refused;
        no name/GetID fallback, deletion or implicit activation/configuration switch.
        A known scoped restoration requires independent proof; unknown retains its
        hold without automatic inverse or retry. Reuse request_id for the same job;
        timeout_s limits waiting and never cancels COM. Poll job_get for late results.
        Installed native acceptance is reported separately for each wheel.
        """
        return await dispatch('feature.set_suppressed', request_id,
            dict(document_id=document_id, configuration=configuration, object_id=object_id,
                 suppressed=suppressed, expected_revision=expected_revision), timeout_s, mutate=True)
