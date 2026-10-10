"""MCP facade for the bounded development-candidate revolve implementation."""

import sqlite3
from typing import Annotated, Literal

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


Length = Annotated[float, Field(strict=True,ge=.001,le=10000000.,allow_inf_nan=False)]
Wait = Annotated[float, Field(strict=True,ge=0,le=120,allow_inf_nan=False)]


def register_part_revolve_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,arguments,timeout_s,*,mutates=False):
        try:
            job = await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],context=job['payload']['context'],
                            data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def part_prepare_base_revolve(request_id:str,document_id:str,configuration:str,plane_object_id:str,
            radius_mm:Length,height_mm:Length,axis:Literal['profile_y']='profile_y',
            sketch_name:str='Эскиз вращения',feature_name:str='Вращение основания',body_name:str='Тело вращения',
            timeout_s:Wait=10.) -> ResponseEnvelope:
        """Read-only preparation for one full-turn cylindrical base in an active empty part.

        Explicit opaque plane reference, one configuration, no existing bodies,
        user sketches or external controls; plane must be at the model origin.
        radius_mm and height_mm define a fully constrained rectangular profile.
        axis=profile_y explicitly binds its OWN x=0 line, never the first axis.
        Returns a revision bound to the complete state, parameters and plane.
        Russian display names required. No document creation, activation or save.
        """
        return await dispatch(request_id,'part.prepare_base_revolve',dict(document_id=document_id,configuration=configuration,
            plane_object_id=plane_object_id,radius_mm=radius_mm,height_mm=height_mm,axis=axis,
            sketch_name=sketch_name,feature_name=feature_name,body_name=body_name),timeout_s)

    @app.tool()
    async def part_create_base_revolve(request_id:str,document_id:str,configuration:str,expected_revision:str,
            plane_object_id:str,radius_mm:Length,height_mm:Length,axis:Literal['profile_y']='profile_y',
            sketch_name:str='Эскиз вращения',feature_name:str='Вращение основания',body_name:str='Тело вращения',
            timeout_s:Wait=10.) -> ResponseEnvelope:
        """Create the prepared full-turn cylinder with its exact owned profile/axis.

        Pass the same parameters and revision from part_prepare_base_revolve.
        Checkpoint precedes CAD/UI writes. Verify full circle/cylinder/plane BREP,
        all native sketch constraints, Радиус/Высота вращения/Угол вращения,
        independent volume/area and original context. Scoped restoration can
        delete only exact retained created features with no foreign dependants.
        This initial scope does not edit existing revolves or create partial turns.
        request_id deduplicates work; timeout limits waiting and does not cancel
        native COM execution. Poll job_get; unknown outcome cannot be replayed.
        """
        return await dispatch(request_id,'part.create_base_revolve',dict(document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,plane_object_id=plane_object_id,radius_mm=radius_mm,height_mm=height_mm,axis=axis,
            sketch_name=sketch_name,feature_name=feature_name,body_name=body_name),timeout_s,mutates=True)
