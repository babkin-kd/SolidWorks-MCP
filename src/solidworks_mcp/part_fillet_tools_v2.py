"""Typed MCP facade for an explicitly selected native cuboid edge fillet."""

import sqlite3

from .contracts import ResponseEnvelope
from .jobs import JobError
from .part_cut_tools_v2 import Length, Wait


def register_part_fillet_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,arguments,timeout_s,mutates=False):
        try:
            job=await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def part_prepare_edge_fillet(request_id:str,document_id:str,configuration:str,object_id:str,edge_id:str,
            radius_mm:Length,feature_name:str='Скругление ребра',timeout_s:Wait=10)->ResponseEnvelope:
        """Read-only preparation of one constant-radius native cuboid edge fillet.

        object_id explicitly identifies the fully defined rectangular base sketch
        from feature_list; edge_id comes from edge_list of its exact current body.
        All twelve complete outer edges are supported. Positive radius is in mm
        and must leave >=0.001 mm beyond half both transverse extents. Requires
        an active writable single-config part with one plain rectangular base.
        Returns revision binding complete source, edge, controls and expected
        rounded geometry. No guessed edge, selection or tangent propagation.
        Timeout does not cancel COM; poll the returned operation_id.
        """
        return await dispatch(request_id,'part.prepare_edge_fillet',dict(document_id=document_id,configuration=configuration,
            object_id=object_id,edge_id=edge_id,radius_mm=radius_mm,feature_name=feature_name),timeout_s)

    @app.tool()
    async def part_create_edge_fillet(request_id:str,document_id:str,configuration:str,expected_revision:str,object_id:str,
            edge_id:str,radius_mm:Length,feature_name:str='Скругление ребра',timeout_s:Wait=10)->ResponseEnvelope:
        """Create the same prepared fillet through durable checkpoint and STA guard.

        New tree name must be Russian. Confirms exact own Fillet, selected edge
        and native radius, unchanged original sketch/drivers, complete finite-arc
        BREP and independent volume/area. Attributable known failure restores
        only the own fillet; foreign/unreadable effects remain unknown and hold
        the application. Repeated request_id returns the same job; never replay
        on waiting timeout. Excludes multiple/variable/face/full-round fillets,
        tangent propagation, partial edges, arbitrary imports and further edits
        of an already rounded body in this initial engineering scope.
        """
        return await dispatch(request_id,'part.create_edge_fillet',dict(document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,object_id=object_id,edge_id=edge_id,radius_mm=radius_mm,feature_name=feature_name),timeout_s,True)
