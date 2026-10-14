"""Typed MCP facade for an explicit native one-direction through-hole pattern."""

import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError
from .part_cut_tools_v2 import Length, Wait


Count = Annotated[int, Field(strict=True, ge=2, le=64)]


def register_part_pattern_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,arguments,timeout_s,mutates=False):
        try:
            job=await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],
                context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def part_prepare_linear_hole_pattern(request_id:str,document_id:str,configuration:str,
            base_object_id:str,object_id:str,seed_object_id:str,direction_edge_id:str,
            count:Count,spacing_mm:Length,feature_name:str='Линейный массив отверстий',timeout_s:Wait=10)->ResponseEnvelope:
        """Prepare a native one-direction array of an existing circular through hole.

        Explicit base_object_id is the base sketch; object_id the circle sketch;
        seed_object_id its exact owning cut, all from feature_list. direction_edge_id
        comes from edge_list of the current supported body and must be a complete
        outer edge along local base X or Y. Direction is positive local X/Y, derived
        from actual endpoints; no guessed axis or selection. Count 2..64 includes
        the seed; positive spacing is millimetres. Each hole and gap must retain
        >=0.001 mm material. Requires one rectangular base/one existing fully
        defined through hole in an active writable single-config part. Read only;
        binds full source/edge/body/control/input proof to the returned revision.
        Waiting timeout does not cancel COM; poll the returned operation_id.
        """
        return await dispatch(request_id,'part.prepare_linear_hole_pattern',dict(
            document_id=document_id,configuration=configuration,base_object_id=base_object_id,
            object_id=object_id,seed_object_id=seed_object_id,direction_edge_id=direction_edge_id,
            count=count,spacing_mm=spacing_mm,feature_name=feature_name),timeout_s)

    @app.tool()
    async def part_create_linear_hole_pattern(request_id:str,document_id:str,configuration:str,expected_revision:str,
            base_object_id:str,object_id:str,seed_object_id:str,direction_edge_id:str,
            count:Count,spacing_mm:Length,feature_name:str='Линейный массив отверстий',timeout_s:Wait=10)->ResponseEnvelope:
        """Create the prepared native LPattern with the same explicit input/revision.

        Checkpoint precedes CAD/UI writes. Proves exact retained own pattern,
        native seed/axis/count/spacing, unchanged original sketches/drivers,
        complete multi-hole BREP and independent volume/area after rebuild.
        New tree name must be Russian. Known attributable failure deletes only
        the own pattern, retaining seed/sketches. Unreadable/foreign effects hold
        the application and are never replayed; repeated request_id returns the
        same job. Timeout is not cancellation. Excludes two-direction/circular/
        body/face patterns, skipped instances, variable spacing, arbitrary imports
        and further hole/base editing after adding a pattern.
        """
        return await dispatch(request_id,'part.create_linear_hole_pattern',dict(
            document_id=document_id,configuration=configuration,expected_revision=expected_revision,
            base_object_id=base_object_id,object_id=object_id,seed_object_id=seed_object_id,
            direction_edge_id=direction_edge_id,count=count,spacing_mm=spacing_mm,
            feature_name=feature_name),timeout_s,True)
