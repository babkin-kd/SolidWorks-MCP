"""MCP facade for an explicit single-bend folded sheet base."""

import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError

Length=Annotated[float,Field(strict=True,ge=.001,le=10000000.,allow_inf_nan=False)]
KFactor=Annotated[float,Field(strict=True,ge=0.,le=1.,allow_inf_nan=False)]
Wait=Annotated[float,Field(strict=True,ge=0.,le=120.,allow_inf_nan=False)]


def register_sheet_profile_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,arguments,timeout_s,*,mutates=False):
        try:
            job=await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],context=job['payload']['context'],
                data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def sheet_prepare_l_profile(request_id:str,document_id:str,configuration:str,plane_object_id:str,
            leg_x_mm:Length,leg_y_mm:Length,length_mm:Length,thickness_mm:Length,bend_radius_mm:Length,k_factor:KFactor,
            sketch_name:str='Эскиз листового профиля',feature_name:str='Листовой уголок',body_name:str='Тело листового уголка',
            timeout_s:Wait=10.) -> ResponseEnvelope:
        """Prepare one native folded L-sheet with a 90-degree bend in an empty active part.

        Explicit opaque plane at model origin and one configuration. The open
        profile is (0,H)->(0,0)->(W,0); t thickens to its left, positive L along
        the plane normal, inner bend radius r. Both legs extend beyond r+t.
        All dimensions are mm. Explicit user K-factor is REQUIRED; no default.
        Returns revision and full expected folded shape, including bend seams.
        Neutral-axis length is analytical preview, not a native flat pattern.
        No activation, save, flatten, DXF, import or arbitrary profile creation.
        """
        return await dispatch(request_id,'sheet.prepare_l_profile',dict(document_id=document_id,configuration=configuration,
            plane_object_id=plane_object_id,leg_x_mm=leg_x_mm,leg_y_mm=leg_y_mm,length_mm=length_mm,
            thickness_mm=thickness_mm,bend_radius_mm=bend_radius_mm,k_factor=k_factor,
            sketch_name=sketch_name,feature_name=feature_name,body_name=body_name),timeout_s)

    @app.tool()
    async def sheet_create_l_profile(request_id:str,document_id:str,configuration:str,expected_revision:str,plane_object_id:str,
            leg_x_mm:Length,leg_y_mm:Length,length_mm:Length,thickness_mm:Length,bend_radius_mm:Length,k_factor:KFactor,
            sketch_name:str='Эскиз листового профиля',feature_name:str='Листовой уголок',body_name:str='Тело листового уголка',
            timeout_s:Wait=10.) -> ResponseEnvelope:
        """Create the prepared folded L-sheet using the same parameters and revision.

        Durable checkpoint precedes CAD/UI writes. Full native material boundary,
        original controls, five sketch relations/three drivers, native thickness,
        radius/direction/custom K and exact own bundle are verified. New nodes
        and length driver receive Russian names. Scoped restoration may delete
        only the fully proved own bundle; no foreign dependants may be removed.
        This scope creates a folded base, not flange edits or native flattening.
        request_id deduplicates work. timeout_s limits waiting and does not
        cancel COM; poll job_get. Unknown results cannot be repeated automatically.
        """
        return await dispatch(request_id,'sheet.create_l_profile',dict(document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,plane_object_id=plane_object_id,leg_x_mm=leg_x_mm,leg_y_mm=leg_y_mm,
            length_mm=length_mm,thickness_mm=thickness_mm,bend_radius_mm=bend_radius_mm,k_factor=k_factor,
            sketch_name=sketch_name,feature_name=feature_name,body_name=body_name),timeout_s,mutates=True)
