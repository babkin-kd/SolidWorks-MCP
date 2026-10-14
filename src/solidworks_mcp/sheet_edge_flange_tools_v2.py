"""Explicit MCP preparation and creation of one bounded native edge flange."""

import sqlite3

from .contracts import ResponseEnvelope
from .jobs import JobError
from .sheet_profile_tools_v2 import Length,KFactor,Wait


def register_sheet_edge_flange_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,arguments,timeout_s,*,mutates=False):
        try:
            job=await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],context=job['payload']['context'],
                data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def sheet_prepare_edge_flange(request_id:str,document_id:str,configuration:str,base_object_id:str,
            edge_id:str,flange_length_mm:Length,bend_radius_mm:Length,k_factor:KFactor,
            sketch_name:str='Эскиз отбортовки',feature_name:str='Отбортовка',timeout_s:Wait=10.) -> ResponseEnvelope:
        """Prepare one inward 90-degree flange on an explicit folded L-sheet edge.

        The exact existing base and full inner longitudinal free edge are required.
        This bounded scope uses the original horizontal fixed leg, one independent
        body/configuration and explicit second-bend radius/K. Length is measured
        to the outer virtual sharp. Returns the complete revision and expected
        U boundary; preserves original sheet parameters, drivers and nodes.
        Read-only. New sketch/flange/bend nodes use Russian names. This operation
        does not cover arbitrary sheets, corner treatments or flattening the U.
        """
        return await dispatch(request_id,'sheet.prepare_edge_flange',dict(document_id=document_id,
            configuration=configuration,base_object_id=base_object_id,edge_id=edge_id,
            flange_length_mm=flange_length_mm,bend_radius_mm=bend_radius_mm,k_factor=k_factor,
            sketch_name=sketch_name,feature_name=feature_name),timeout_s)

    @app.tool()
    async def sheet_create_edge_flange(request_id:str,document_id:str,configuration:str,base_object_id:str,
            edge_id:str,flange_length_mm:Length,bend_radius_mm:Length,k_factor:KFactor,expected_revision:str,
            sketch_name:str='Эскиз отбортовки',feature_name:str='Отбортовка',timeout_s:Wait=10.) -> ResponseEnvelope:
        """Create the exact prepared edge flange with complete native readback.

        Durable checkpoint precedes the STA guard and CAD writes. Full material
        boundary, own constrained profile, both bend parameters and all original
        nodes/drivers/controls are verified. Scoped restoration deletes only a
        completely proved own flange or fully defined unconsumed input sketch.
        Intermediate or foreign effects remain unknown without Undo or retry.
        request_id deduplicates the job. timeout_s limits waiting, not COM;
        poll job_get until terminal. The original base/edge reference is explicit.
        """
        return await dispatch(request_id,'sheet.create_edge_flange',dict(document_id=document_id,
            configuration=configuration,base_object_id=base_object_id,edge_id=edge_id,
            flange_length_mm=flange_length_mm,bend_radius_mm=bend_radius_mm,k_factor=k_factor,
            sketch_name=sketch_name,feature_name=feature_name,expected_revision=expected_revision),timeout_s,mutates=True)
