"""MCP facade for the native-accepted, bounded base-part workflow."""

import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


def register_part_tools(app, runtime, response, failure):
    async def dispatch(request_id, operation, arguments, timeout_s, *, mutates=False):
        try:
            job = await (runtime.mutate if mutates else runtime.read)(request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def part_prepare_base_extrusion(request_id: str, document_id: str, configuration: str,
            plane_object_id: str, width_mm: Annotated[float, Field(strict=True, ge=.001, allow_inf_nan=False)],
            height_mm: Annotated[float, Field(strict=True, ge=.001, allow_inf_nan=False)],
            depth_mm: Annotated[float, Field(strict=True, ge=.001, allow_inf_nan=False)],
            sketch_name: str = 'Эскиз основания', feature_name: str = 'Основание', body_name: str = 'Тело основания',
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10) -> ResponseEnvelope:
        """Prepare a parametrical rectangular base on an explicit opaque plane ID.

        Read only: no document creation, activation, sketch edit, rebuild or save.
        Requires an already active empty part with one configuration, no bodies,
        user sketches, equations/external controls or pending rebuild. The plane
        must be a current unsuppressed RefPlane at the model origin, identified by
        feature_list, never its name/index. Positive dimensions are explicitly mm.
        All created display names require Russian text; collisions are rejected.
        Interactive dimension input and AddToDB must be disabled beforehand.
        Returns empty_part_base_rectangle_v1 revision bound to these parameters,
        complete supported state and the plane transform, plus expected volume/area.
        Pass exactly these parameters/revision to part_create_base_extrusion.
        Waiting timeout does not cancel COM; poll job_get for queued/running work.
        """
        return await dispatch(request_id, 'part.prepare_base_extrusion', {
            'document_id': document_id, 'configuration': configuration, 'plane_object_id': plane_object_id,
            'width_mm': width_mm, 'height_mm': height_mm, 'depth_mm': depth_mm,
            'sketch_name': sketch_name, 'feature_name': feature_name, 'body_name': body_name}, timeout_s)

    @app.tool()
    async def part_create_base_extrusion(request_id: str, document_id: str, configuration: str,
            expected_revision: str, plane_object_id: str,
            width_mm: Annotated[float, Field(strict=True, ge=.001, allow_inf_nan=False)],
            height_mm: Annotated[float, Field(strict=True, ge=.001, allow_inf_nan=False)],
            depth_mm: Annotated[float, Field(strict=True, ge=.001, allow_inf_nan=False)],
            sketch_name: str = 'Эскиз основания', feature_name: str = 'Основание', body_name: str = 'Тело основания',
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10) -> ResponseEnvelope:
        """Create a fully defined rectangular sketch and one blind base extrusion.

        Use the same explicit document/configuration/plane/parameters and revision
        returned by part_prepare_base_extrusion. Construction supports that bounded
        empty-part scope only; this tool does not create/open a document or save it.
        Creates Russian names and driving Ширина/Высота/Толщина dimensions.
        Checkpoints before native/UI changes, preserves selected objects/marks,
        verifies three dimensions, complete planar BREP, volume/area and diagnostics.
        Scoped restoration deletes only exact retained created features, without
        deleting original or unrelated dependent features. Unknown creation/selection
        holds the application and is never automatically replayed. A repeated
        request_id retrieves the same job. timeout_s limits waiting, not COM execution;
        poll job_get. Obtain the thickness object_id/revision from dimension_list
        before dimension_set_value; sketch dimension editing remains unsupported.
        """
        return await dispatch(request_id, 'part.create_base_extrusion', {
            'document_id': document_id, 'configuration': configuration, 'expected_revision': expected_revision,
            'plane_object_id': plane_object_id, 'width_mm': width_mm, 'height_mm': height_mm, 'depth_mm': depth_mm,
            'sketch_name': sketch_name, 'feature_name': feature_name, 'body_name': body_name}, timeout_s, mutates=True)
