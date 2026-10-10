"""Typed MCP facade for the implemented corner-through-cut candidate."""

import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


Length = Annotated[float, Field(strict=True, ge=.001, le=10000000., allow_inf_nan=False)]
Wait = Annotated[float, Field(strict=True, ge=0, le=120)]


def register_part_cut_tools(app, runtime, response, failure):
    async def dispatch(request_id, operation, arguments, timeout_s, *, mutates=False):
        try:
            job = await (runtime.mutate if mutates else runtime.read)(request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def part_prepare_corner_cut(request_id: str, document_id: str, configuration: str,
            object_id: str, plane_object_id: str, width_mm: Length, height_mm: Length,
            sketch_name: str = 'Эскиз выреза', feature_name: str = 'Вырез угла', timeout_s: Wait = 10) -> ResponseEnvelope:
        """Prepare an explicit smaller corner rectangle for a through-all cut.

        Read only. Requires the supported fully defined origin-anchored rectangular
        base and one blind extrusion in an already active writable single-config part.
        object_id identifies the BASE sketch; plane_object_id must resolve to that
        sketch's exact current reference plane. No plane names or implicit activation.
        Cut dimensions are millimetres; each base axis must retain >=0.001 mm material.
        Russian sketch/cut names must be distinct and not conflict with existing names.
        Returns single_base_rectangular_corner_through_cut_v1 revision bound to complete
        constraints, dimensions, BREP, native references, controls and requested shape.
        Waiting timeout does not cancel COM; poll job_get for unfinished work.
        """
        return await dispatch(request_id, 'part.prepare_corner_cut', {
            'document_id': document_id, 'configuration': configuration, 'object_id': object_id,
            'plane_object_id': plane_object_id, 'width_mm': width_mm, 'height_mm': height_mm,
            'sketch_name': sketch_name, 'feature_name': feature_name}, timeout_s)

    @app.tool()
    async def part_create_corner_cut(request_id: str, document_id: str, configuration: str,
            expected_revision: str, object_id: str, plane_object_id: str, width_mm: Length, height_mm: Length,
            sketch_name: str = 'Эскиз выреза', feature_name: str = 'Вырез угла', timeout_s: Wait = 10) -> ResponseEnvelope:
        """Create the prepared origin-corner rectangular through-all cut.

        Use the exact document/configuration/base sketch/plane/parameters/revision from
        part_prepare_corner_cut. Creates one fully constrained Russian sketch and cut.
        Checkpoints before native/UI writes, retains exact returned handles, preserves
        selection/marks and the original body name, rebuilds and checks original base
        constraints/dimensions, complete L-prism BREP and independent volume/area.
        Known failure restores only owned sketch/cut with no foreign dependent features;
        unknown creation or foreign changes hold the application and are never replayed.
        request_id retrieves the same job on repetition. Waiting timeout is not COM
        cancellation. This initial scope excludes arbitrary pockets, holes and face cuts.
        Subsequent base width/height editing is outside the original rectangle-only scope.
        """
        return await dispatch(request_id, 'part.create_corner_cut', {
            'document_id': document_id, 'configuration': configuration, 'expected_revision': expected_revision,
            'object_id': object_id, 'plane_object_id': plane_object_id, 'width_mm': width_mm, 'height_mm': height_mm,
            'sketch_name': sketch_name, 'feature_name': feature_name}, timeout_s, mutates=True)
