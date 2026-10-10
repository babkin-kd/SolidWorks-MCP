"""MCP facade for explicit native L-sheet flat/folded state changes."""

import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


FlatState=Annotated[bool,Field(strict=True)]
Wait=Annotated[float,Field(strict=True,ge=0.,le=120.,allow_inf_nan=False)]


def register_sheet_flat_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,arguments,timeout_s,*,mutates=False):
        try:
            job=await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def sheet_prepare_flat_state(request_id:str,document_id:str,configuration:str,base_object_id:str,flattened:FlatState,
            timeout_s:Wait=10.) -> ResponseEnvelope:
        """Prepare native flat/folded state for one explicit existing L-sheet base.

        Requires an active independent one-configuration L-sheet with its full
        original two-line driving network. Target is the strong base feature;
        its unique flat pattern is bound through exact body/folder membership,
        never its name. K-factor comes from native sheet parameters and is not
        changed. Full BREP and native fixed face determine the target geometry.
        Returns revision/current state and complete expected geometry in mm/m.
        Read-only: no activation, AccessSelections, suppression, rebuild or save.
        No DXF/export, new configurations, arbitrary bends or imported sheets.
        """
        return await dispatch(request_id,'sheet.prepare_flat_state',dict(document_id=document_id,configuration=configuration,
            base_object_id=base_object_id,flattened=flattened),timeout_s)

    @app.tool()
    async def sheet_set_flat_state(request_id:str,document_id:str,configuration:str,base_object_id:str,flattened:FlatState,
            expected_revision:str,timeout_s:Wait=10.) -> ResponseEnvelope:
        """Change only the prepared native L-sheet flat/folded state and preserve names.

        Checkpoint precedes the owning-STA guard and CAD/UI writes. Fresh current
        bodies and exact base/flat/folder/cut-list membership are re-proved after
        rebuilding. Full intended BREP, original drivers/K/parameters/controls,
        limited suppression footprint and body/cut-list names are verified.
        Only the proved transition permits preserving original Russian names
        when SolidWorks auto-renames the cut-list. Known failure may restore
        only the proved original state/names; no deletion or generic Undo.
        request_id deduplicates the job. timeout_s only limits waiting; it does
        not cancel COM. Poll job_get; unknown outcomes cannot be auto-repeated.
        """
        return await dispatch(request_id,'sheet.set_flat_state',dict(document_id=document_id,configuration=configuration,
            base_object_id=base_object_id,flattened=flattened,expected_revision=expected_revision),timeout_s,mutates=True)
