"""MCP facade for explicit two-bend U-sheet flat/folded state."""

import sqlite3

from .contracts import ResponseEnvelope
from .jobs import JobError
from .sheet_flat_tools_v2 import FlatState,Wait


def register_sheet_flange_flat_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,arguments,timeout_s,*,mutates=False):
        try:
            job=await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def sheet_prepare_flange_flat_state(request_id:str,document_id:str,configuration:str,base_object_id:str,
            flange_object_id:str,flattened:FlatState,timeout_s:Wait=10.) -> ResponseEnvelope:
        """Prepare native unfold/refold of one explicit existing two-bend U-sheet.

        Requires exact base and flange references, one independent active native
        sheet body/configuration, and the original horizontal fixed leg. Both
        native bend radii and explicit user K factors are read and preserved.
        Complete U/flat BREP, fixed face, profiles, six dimensions and native
        member graph must match. Returns scoped revision and expected geometry.
        Read-only: no activation, suppression, rebuild or save. No export or
        arbitrary imported sheets, corner reliefs or new configurations.
        """
        return await dispatch(request_id,'sheet.prepare_flange_flat_state',dict(document_id=document_id,
            configuration=configuration,base_object_id=base_object_id,flange_object_id=flange_object_id,flattened=flattened),timeout_s)

    @app.tool()
    async def sheet_set_flange_flat_state(request_id:str,document_id:str,configuration:str,base_object_id:str,
            flange_object_id:str,flattened:FlatState,expected_revision:str,timeout_s:Wait=10.) -> ResponseEnvelope:
        """Switch only the prepared U-sheet FlatPattern state and preserve names.

        Durable checkpoint precedes the STA guard and all writes. Fresh paired
        readbacks prove complete material shape, fixed-face/body membership,
        profiles, all original dimensions, both K factors/radii and the limited
        suppression footprint. Only a fully proved transition permits original
        body/cut-list name preservation or restoration of the prior state.
        No deletion or generic Undo. request_id deduplicates the exact job;
        timeout_s limits waiting, never COM execution. Poll job_get; unknown
        outcomes cannot be automatically repeated.
        """
        return await dispatch(request_id,'sheet.set_flange_flat_state',dict(document_id=document_id,
            configuration=configuration,base_object_id=base_object_id,flange_object_id=flange_object_id,
            flattened=flattened,expected_revision=expected_revision),timeout_s,mutates=True)
