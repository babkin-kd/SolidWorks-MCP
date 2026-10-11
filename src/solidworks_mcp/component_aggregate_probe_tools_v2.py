"""Explicit complete aggregate point/axis read facade."""
import sqlite3
from pydantic import StrictFloat
from .contracts import ResponseEnvelope
from .measurement_frames import RigidMeasurementFrame
from .jobs import JobError


def register_component_aggregate_probe_tools(app, runtime, response, failure):
    async def dispatch(operation, request_id, document_id, configuration, expected_observation_revision,
                       component_id, frame, timeout_s, **arguments):
        try:
            job = await runtime.read(request_id, operation, dict(document_id=document_id,
                configuration=configuration, expected_observation_revision=expected_observation_revision,
                component_id=component_id, frame=None if frame is None else frame.model_dump(mode='json'),
                **arguments), timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],context=job['payload']['context'],
                            data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def measurement_get_component_aggregate_point_distance(request_id: str, document_id: str, configuration: str,
            expected_observation_revision: str, component_id: str,
            point_mm: tuple[StrictFloat,StrictFloat,StrictFloat], frame: RigidMeasurementFrame|None=None,
            timeout_s: StrictFloat=10.) -> ResponseEnvelope:
        """Complete minimum to individual solid boundaries of a part/subassembly target.

        Includes every normal solid leaf/body/trimmed face, including hidden items;
        empty/surface-only leaves count but do not enter minimum. Point and nearest
        boundary witness use mm in root or explicit rigid frame. Positive distance
        inside; point_location=inside when any solid contains the point, then boundary,
        otherwise outside. This is not the exterior boundary of a Boolean union.
        Native ray ambiguity rejects the complete read. Original nearest component/
        body/face IDs and all body locations returned. Full hierarchy/config/transform/
        bodies/moments/face closing checks. No UI changes, activation/rebuild or sampling.
        Limits:1000 leaves,5000 normal bodies,100000 solid faces; no partial result.
        """
        return await dispatch('measurement.component_aggregate_point_distance',request_id,document_id,
            configuration,expected_observation_revision,component_id,frame,timeout_s,point_mm=list(point_mm))

    @app.tool()
    async def measurement_get_component_aggregate_axis_distance(request_id: str, document_id: str, configuration: str,
            expected_observation_revision: str, component_id: str,
            axis_origin_mm: tuple[StrictFloat,StrictFloat,StrictFloat], axis_direction: tuple[StrictFloat,StrictFloat,StrictFloat],
            frame: RigidMeasurementFrame|None=None, timeout_s: StrictFloat=10.) -> ResponseEnvelope:
        """Complete solid-leaf minimum to an infinite axis for part/subassembly target.

        Exact supports certify a memory-only finite wire for each native part solver;
        all solid leaves are measured, even after zero. Axis origin in mm, finite
        nonzero direction normalized, root or explicit rigid frame. Both witnesses
        and nearest original component returned. Hidden solids included; nonsolid
        leaves counted/excluded. Full closing supports/body/moments/root context.
        Limits1000 leaves/5000 normal bodies, no sampling/bbox/partial minimum.
        No CAD-tree insertion/display/selection/activation/rebuild; no collision
        classification. Unsupported native states and named frames remain outside scope.
        """
        return await dispatch('measurement.component_aggregate_axis_distance',request_id,document_id,
            configuration,expected_observation_revision,component_id,frame,timeout_s,
            axis_origin_mm=list(axis_origin_mm),axis_direction=list(axis_direction))
