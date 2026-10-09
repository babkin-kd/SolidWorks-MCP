"""Unconnected dimension MCP candidate; register only after native acceptance.

Registration performs no CAD work. The owning runtime supplies explicit targets,
complete scoped captures, durable jobs and verified mutation/guard semantics.
"""

import sqlite3
from typing import Annotated

from pydantic import Field, StrictFloat

from .contracts import ResponseEnvelope
from .jobs import JobError


def register_dimension_tools(app, runtime, response, failure):
    """Add exactly three tools using the server's shared envelope factories.

    Root calls this from create_app only after installed-wheel native gates pass,
    and separately updates system_get_info, guide and capability declarations.
    This module does not publish itself, instantiate a runtime or enter COM.
    """
    async def dispatch(request_id, operation, arguments, timeout_s, *, mutates=False):
        try:
            execute = runtime.mutate if mutates else runtime.read
            job = await execute(request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def dimension_list(request_id: str, document_id: str, configuration: str,
                             limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 100,
                             cursor: str = '',
                             timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10) -> ResponseEnvelope:
        """Page captured dimensions of an explicit part and active configuration.

        part_dimension_values_v1 covers the complete supported dimension/control/
        configuration/analytical-boundary scope, not arbitrary CAD/add-in state.
        Values are mm/deg with explicit units; all named configuration values are
        captured. Rows include blockers, reference_anchor and native_incarnation.
        Sketch dimensions are read-only; unsupported persistent references have
        object_id=null. Opaque IDs never resolve by name or traversal index.
        No activation, rebuild or save. A cursor belongs to the current revision;
        limit is 1–200. Use a new request_id for a fresh read. timeout_s only limits
        waiting: queued/running work continues; poll job_get(operation_id).
        """
        return await dispatch(request_id, 'dimension.list', {
            'document_id': document_id, 'configuration': configuration,
            'limit': limit, 'cursor': cursor}, timeout_s)

    @app.tool()
    async def dimension_get(request_id: str, document_id: str, configuration: str,
                            object_id: str,
                            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10) -> ResponseEnvelope:
        """Read one opaque dimension ID in its original explicit part/configuration.

        Revalidates native identity and current owner/display-slot membership,
        without a name/ordinal fallback. Returns the full captured row, including
        reference_anchor, native_incarnation, mm/deg values and write blockers,
        with its part_dimension_values_v1 revision. Sketch dimensions are read-only.
        No activation, rebuild or save. Timeout does not cancel COM; poll job_get
        for queued/running work. An unknown outcome requires reconciliation.
        """
        return await dispatch(request_id, 'dimension.get', {
            'document_id': document_id, 'configuration': configuration,
            'object_id': object_id}, timeout_s)

    @app.tool()
    async def dimension_set_value(request_id: str, document_id: str, configuration: str,
                                  object_id: str, expected_revision: str, value: StrictFloat,
                                  unit: str,
                                  timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10) -> ResponseEnvelope:
        """Change one accepted independent feature dimension with durable verification.

        Obtain expected_revision from dimension_list/get (part_dimension_values_v1);
        feature-tree/observation revisions are insufficient. Explicit active document,
        active single-configuration part and persistent object ID are required.
        value is a finite positive number; unit must be mm or deg matching the
        parameter type, with 0 < deg < 360. No guessed units/sign/angle wrapping.
        Sketch dimensions are read-only. Rejects driven/linked/reference/design-table
        dimensions and unsupported equation/dependency/external/editing contexts.
        Checkpoints the captured baseline, rechecks before writing, rebuilds this
        target and verifies readback, scoped inputs and feature diagnostics. No save
        or activation; restoration is claimed only when independently confirmed.
        request_id repeats retrieve the same job, never a second write. timeout_s
        limits waiting, not COM execution: poll job_get. Unknown requires state
        reconciliation; do not retry automatically with a new request_id.
        """
        return await dispatch(request_id, 'dimension.set_value', {
            'document_id': document_id, 'configuration': configuration, 'object_id': object_id,
            'expected_revision': expected_revision, 'value': value, 'unit': unit}, timeout_s, mutates=True)
