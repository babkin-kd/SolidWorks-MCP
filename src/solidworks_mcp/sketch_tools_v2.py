"""Explicit MCP facade for complete linear sketches and bounded rectangle edits."""

import sqlite3
from typing import Annotated
from pydantic import Field
from .contracts import ResponseEnvelope
from .jobs import JobError


def register_sketch_tools(app, runtime, response, failure):
    async def dispatch(request_id, operation, arguments, timeout_s, *, mutates=False):
        try:
            job = await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],
                context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def sketch_get(request_id: str, document_id: str, configuration: str, object_id: str,
            timeout_s: Annotated[float,Field(strict=True,ge=0,le=120)]=10) -> ResponseEnvelope:
        """Read the complete supported planar linear sketch by explicit feature ID.

        Returns part_linear_sketch_read_v1 revision, exact SI hex coordinates,
        points/lines, constrained status, all internal/defining relation entities,
        native dimension orientation, model origin and transforms/references.
        Rejects curves, 3D, blocks/text/pictures/slots/hatches and unsupported
        external entities; no partial capture. Local entity ID pairs are read-only
        hints, never edit targets. No activation, sketch editing or solving.
        """
        return await dispatch(request_id,'sketch.get',dict(document_id=document_id,
            configuration=configuration,object_id=object_id),timeout_s)

    @app.tool()
    async def sketch_prepare_dimension_change(request_id: str, document_id: str, configuration: str,
            object_id: str, dimension_id: str,
            value_mm: Annotated[float,Field(strict=True,ge=.001,le=10000000.,allow_inf_nan=False)],
            timeout_s: Annotated[float,Field(strict=True,ge=0,le=120)]=10) -> ResponseEnvelope:
        """Prepare width/height change of one fully defined rectangular base sketch.

        Read only. Explicit active single-configuration part, feature object_id
        from feature_list and own driving dimension_id from dimension_list.
        Supports four finite perimeter lines, seven independent defining relations,
        exact model-origin corner, two native horizontal/vertical dimensions and
        one positive blind extrusion. Returns part_rectangular_sketch_dimension_v1
        revision bound to this exact value_mm, target and complete supported state.
        General sketch dimensions remain outside dimension_set_value's scope.
        """
        return await dispatch(request_id,'sketch.prepare_dimension_change',dict(document_id=document_id,
            configuration=configuration,object_id=object_id,dimension_id=dimension_id,value_mm=value_mm),timeout_s)

    @app.tool()
    async def sketch_set_dimension(request_id: str, document_id: str, configuration: str,
            object_id: str, dimension_id: str, expected_revision: str,
            value_mm: Annotated[float,Field(strict=True,ge=.001,le=10000000.,allow_inf_nan=False)],
            timeout_s: Annotated[float,Field(strict=True,ge=0,le=120)]=10) -> ResponseEnvelope:
        """Change the prepared rectangle width/height with durable native proof.

        Pass exactly the target/value/revision from sketch_prepare_dimension_change.
        Preserves all other dimensions/constraints/metadata, selection and UI lock;
        verifies rebuild, complete bounded BREP and independent native volume/area.
        Known failure restores only the target parameter if ownership and remaining
        state are unchanged, proving the full original shape within declared solver
        tolerances. No Undo, save, activation or constraint deletion. A repeated
        request_id retrieves the same job; timeout does not cancel COM. Poll job_get.
        Unknown blocks mutations and must not be automatically repeated.
        """
        return await dispatch(request_id,'sketch.set_dimension',dict(document_id=document_id,
            configuration=configuration,object_id=object_id,dimension_id=dimension_id,
            expected_revision=expected_revision,value_mm=value_mm),timeout_s,mutates=True)
