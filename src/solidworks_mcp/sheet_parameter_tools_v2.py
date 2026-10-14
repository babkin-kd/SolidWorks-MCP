"""Strict MCP facade for explicit existing native L-sheet parameter changes."""

import sqlite3

from .contracts import ResponseEnvelope
from .jobs import JobError
from .sheet_profile_tools_v2 import Length,KFactor,Wait


def register_sheet_parameter_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,arguments,timeout_s,*,mutates=False):
        try:
            job=await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],context=job['payload']['context'],
                data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def sheet_prepare_parameters(request_id:str,document_id:str,configuration:str,base_object_id:str,
            thickness_mm:Length,bend_radius_mm:Length,k_factor:KFactor,timeout_s:Wait=10.) -> ResponseEnvelope:
        """Prepare explicit t/r/K changes for one existing native L-sheet base.

        Preserves profile legs, length, fully defined original sketch, native
        flat/fold state and body/feature names. All three parameters are required;
        no default K-factor. Two closing complete captures bind shape, drivers,
        current body/members/fixed face, exact template/default allowance and
        relief/gauge settings to the revision. Returns current/requested values
        and expected geometry. Read-only: no AccessSelections, rebuild or save.
        One independent body/configuration; no tables/material-driven overrides.
        """
        return await dispatch(request_id,'sheet.prepare_parameters',dict(document_id=document_id,configuration=configuration,
            base_object_id=base_object_id,thickness_mm=thickness_mm,bend_radius_mm=bend_radius_mm,k_factor=k_factor),timeout_s)

    @app.tool()
    async def sheet_set_parameters(request_id:str,document_id:str,configuration:str,base_object_id:str,
            thickness_mm:Length,bend_radius_mm:Length,k_factor:KFactor,expected_revision:str,timeout_s:Wait=10.) -> ResponseEnvelope:
        """Set the prepared thickness/radius/K on the exact native template.

        Checkpoint precedes owning-STA guard and definition access. Full native
        material boundary and independent template/body parameters are verified;
        other options/drivers/state remain unchanged. Only the proved intended
        transition permits preserving original body/cut-list names. Known failure
        restores only a fully proved original or intended parameter state;
        intermediate/foreign state remains unknown, without retry or generic Undo.
        request_id deduplicates the job. timeout_s limits waiting, not COM; poll
        job_get. No file exchange or new feature/configuration/library names.
        """
        return await dispatch(request_id,'sheet.set_parameters',dict(document_id=document_id,configuration=configuration,
            base_object_id=base_object_id,thickness_mm=thickness_mm,bend_radius_mm=bend_radius_mm,k_factor=k_factor,
            expected_revision=expected_revision),timeout_s,mutates=True)
