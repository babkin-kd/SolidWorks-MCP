"""Explicit resolved assembly targets, complete solid-leaf minimum and witnesses."""
import sqlite3
from pydantic import StrictFloat
from .contracts import ResponseEnvelope
from .measurement_frames import RigidMeasurementFrame
from .jobs import JobError


def register_component_aggregate_distance_tools(app, runtime, response, failure):
    @app.tool()
    async def measurement_get_component_aggregate_distance(request_id: str, document_id: str, configuration: str,
            expected_observation_revision: str, component_a_id: str, component_b_id: str,
            frame: RigidMeasurementFrame | None = None, timeout_s: StrictFloat = 10.) -> ResponseEnvelope:
        """Minimum between two explicit part/subassembly targets in one root assembly.

        Complete native parent hierarchy selects normal solid part leaves, including
        hidden components/bodies. Surface-only/empty part leaves are counted but
        excluded from the solid minimum. Every solid leaf pair is measured; returns
        nearest original instance IDs and both mm witnesses in root or explicit
        rigid frame. Shared descendant instance witnesses zero with a native solid
        extreme point. Zero does not classify interference. Full closing census,
        body/config/transform/moments checks; no bbox approximation, selection,
        activation, rebuild or partial result. Limits:1000 leaves per target,
        5000 total normal bodies,10000 leaf pairs. Unresolved/SpeedPak/assembly-cut/
        mesh states and named native frames remain outside this read scope.
        """
        try:
            job = await runtime.read(request_id, 'measurement.component_aggregate_distance', dict(document_id=document_id,
                configuration=configuration, expected_observation_revision=expected_observation_revision,
                component_a_id=component_a_id, component_b_id=component_b_id,
                frame=None if frame is None else frame.model_dump(mode='json')), timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'], context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:return failure(exc)
