"""Explicit instance/point read in root assembly or caller-provided rigid axes."""
import sqlite3
from pydantic import StrictFloat
from .contracts import ResponseEnvelope
from .measurement_frames import RigidMeasurementFrame
from .jobs import JobError


def register_component_point_distance_tools(app, runtime, response, failure):
    @app.tool()
    async def measurement_get_component_point_distance(request_id: str, document_id: str, configuration: str,
            expected_observation_revision: str, component_id: str, point_mm: tuple[StrictFloat, StrictFloat, StrictFloat],
            frame: RigidMeasurementFrame | None = None, timeout_s: StrictFloat = 10.) -> ResponseEnvelope:
        """Minimum distance from explicit point to normal solid boundaries of one part instance.

        Explicit root assembly/active config/observation and component ID. Point and
        closest point use mm in assembly model axes or the supplied finite rigid
        frame. Handles nested/rotated instances and hidden solids; surfaces excluded.
        Distance remains positive inside: it measures individual solid boundaries.
        Native entry/exit rays classify inside/outside; boundary within 0.00001 mm
        returns inside=null. Ambiguous rays fail, no face-normal heuristic. Returns
        original nearest face/body references and full closing snapshot checks.
        No selection, activation, rebuild or temporary CAD entities. Named native
        frames/subassembly targets and unsupported component states are refused.
        """
        try:
            job = await runtime.read(request_id, 'measurement.component_point_distance', dict(document_id=document_id,
                configuration=configuration, expected_observation_revision=expected_observation_revision, component_id=component_id,
                point_mm=list(point_mm), frame=None if frame is None else frame.model_dump(mode='json')), timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'], context=job['payload']['context'],
                data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:return failure(exc)
