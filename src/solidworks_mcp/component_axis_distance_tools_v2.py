"""Explicit passive part-instance distance to an infinite line."""
import sqlite3
from pydantic import StrictFloat
from .contracts import ResponseEnvelope
from .measurement_frames import RigidMeasurementFrame
from .jobs import JobError


def register_component_axis_distance_tools(app, runtime, response, failure):
    @app.tool()
    async def measurement_get_component_axis_distance(request_id: str, document_id: str, configuration: str,
            expected_observation_revision: str, component_id: str,
            axis_origin_mm: tuple[StrictFloat, StrictFloat, StrictFloat], axis_direction: tuple[StrictFloat, StrictFloat, StrictFloat],
            frame: RigidMeasurementFrame | None = None, timeout_s: StrictFloat = 10.) -> ResponseEnvelope:
        """Native minimum from one resolved part instance to an infinite axis.

        Axis origin in mm, nonzero finite direction normalized; both interpreted
        in root assembly axes or explicit rigid frame. Includes normal hidden
        solids, excludes surfaces. Exact directional supports certify the finite
        temporary wire edge covers the infinite-line minimum. Wire exists only
        in memory: no sketch/feature insertion, selection, display, activation,
        rebuild or deletion. Returns both witnesses in input and assembly axes.
        Closing body/support/config/instance checks; zero does not classify
        interference. Named native frames/subassembly targets are outside scope.
        """
        try:
            job = await runtime.read(request_id, 'measurement.component_axis_distance', dict(document_id=document_id,
                configuration=configuration, expected_observation_revision=expected_observation_revision, component_id=component_id,
                axis_origin_mm=list(axis_origin_mm), axis_direction=list(axis_direction), frame=None if frame is None else frame.model_dump(mode='json')), timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'], context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:return failure(exc)
