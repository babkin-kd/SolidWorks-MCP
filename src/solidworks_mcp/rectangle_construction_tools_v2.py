"""Explicit standalone rectangle stages, with separate prepare/write contracts."""
import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


Length = Annotated[float, Field(strict=True, ge=.001, allow_inf_nan=False)]
Wait = Annotated[float, Field(strict=True, ge=0, le=120, allow_inf_nan=False)]


def register_rectangle_construction_tools(app, runtime, response, failure):
    async def dispatch(operation, request_id, arguments, timeout_s, *, mutate=False):
        try:
            job = await (runtime.mutate if mutate else runtime.read)(
                request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def sketch_prepare_rectangle(request_id: str, document_id: str, configuration: str,
            plane_object_id: str, width_mm: Length, height_mm: Length,
            sketch_name: str = 'Эскиз основания', timeout_s: Wait = 10.) -> ResponseEnvelope:
        """Prepare a separate fully defined rectangle on an explicit current plane ID.

        Active writable unsaved one-configuration empty part, origin plane and
        fully observed self-contained rectangular neighbors only. No model/UI
        writes, activation or save. Russian sketch/dimension names; mm units.
        Complete revision binds parameters, exact references and supported session.
        Unsupported/incomplete baselines are refused. Native acceptance is separate.
        """
        return await dispatch('sketch.prepare_rectangle', request_id,
            dict(document_id=document_id, configuration=configuration, plane_object_id=plane_object_id,
                 width_mm=width_mm, height_mm=height_mm, sketch_name=sketch_name), timeout_s)

    @app.tool()
    async def sketch_create_rectangle(request_id: str, document_id: str, configuration: str,
            expected_revision: str, plane_object_id: str, width_mm: Length, height_mm: Length,
            sketch_name: str = 'Эскиз основания', timeout_s: Wait = 10.) -> ResponseEnvelope:
        """Create only the prepared closed rectangle, returning its exact opaque sketch ID.

        Use unchanged prepare parameters/revision. No body is created. Durable
        application checkpoint, one-shot native journal and full post-release
        geometry/reference/session proof are required. Known own restoration is
        scoped; uncertain outcomes hold writes without retry. Reuse request_id
        for replay; timeout limits waiting, never cancels COM. Poll job_get.
        """
        return await dispatch('sketch.create_rectangle', request_id,
            dict(document_id=document_id, configuration=configuration, expected_revision=expected_revision,
                 plane_object_id=plane_object_id, width_mm=width_mm, height_mm=height_mm,
                 sketch_name=sketch_name), timeout_s, mutate=True)

    @app.tool()
    async def part_prepare_rectangle_extrusion(request_id: str, document_id: str, configuration: str,
            sketch_object_id: str, depth_mm: Length, feature_name: str = 'Основание',
            body_name: str = 'Тело основания', timeout_s: Wait = 10.) -> ResponseEnvelope:
        """Prepare blind base extrusion from the exact existing closed rectangle ID.

        Fresh full revision after sketch creation; active writable unsaved
        one-configuration part with no bodies and one supported rectangle.
        Existing sketch belongs to this operation's baseline. Explicit mm depth,
        Russian feature/body/Толщина names; no implicit profile selection or writes.
        Arbitrary profiles, thin/drafted extrusion and external refs are unsupported.
        """
        return await dispatch('part.prepare_rectangle_extrusion', request_id,
            dict(document_id=document_id, configuration=configuration, sketch_object_id=sketch_object_id,
                 depth_mm=depth_mm, feature_name=feature_name, body_name=body_name), timeout_s)

    @app.tool()
    async def part_extrude_rectangle(request_id: str, document_id: str, configuration: str,
            expected_revision: str, sketch_object_id: str, depth_mm: Length,
            feature_name: str = 'Основание', body_name: str = 'Тело основания',
            timeout_s: Wait = 10.) -> ResponseEnvelope:
        """Extrude the prepared baseline rectangle once and return the exact feature ID.

        Full BREP, dimensions, retained sketch anchors and neighbors are independently
        verified after guard release. Restoration removes only the owned extrusion;
        its borrowed baseline sketch is preserved. Unknown/pending/storage failures
        prohibit inverse/retry and retain an application hold. No activation/save.
        Reuse request_id and poll job_get for late results. Native acceptance is separate.
        """
        return await dispatch('part.extrude_rectangle', request_id,
            dict(document_id=document_id, configuration=configuration, expected_revision=expected_revision,
                 sketch_object_id=sketch_object_id, depth_mm=depth_mm, feature_name=feature_name,
                 body_name=body_name), timeout_s, mutate=True)
