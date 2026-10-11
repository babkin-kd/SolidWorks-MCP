"""Passive assembly distance tool; no implicit selection, activation or rebuild."""
import sqlite3
from pydantic import StrictFloat
from .contracts import ResponseEnvelope
from .jobs import JobError


def register_component_distance_tools(app, runtime, response, failure):
    @app.tool()
    async def measurement_get_component_distance(request_id: str, document_id: str, configuration: str,
            expected_observation_revision: str, component_a_id: str, component_b_id: str,
            timeout_s: StrictFloat = 10.) -> ResponseEnvelope:
        """Native minimum distance between two distinct resolved part instances.

        Explicit root assembly, active configuration, observation and component IDs.
        Includes hidden normal native solids; excludes surface bodies. Both closest
        points and distance use mm in root assembly model axes, including nested
        and rotated instances. No UI selection/activation, rebuild or temporary CAD
        entities. Subassemblies as targets, unresolved/cut/mesh bodies are refused.
        Does not classify interference or volume containment. Observations are not
        mutation revisions. Zero is the native minimum, not an interference test.
        """
        try:
            job = await runtime.read(request_id, 'measurement.component_distance', dict(document_id=document_id,
                configuration=configuration, expected_observation_revision=expected_observation_revision,
                component_a_id=component_a_id, component_b_id=component_b_id), timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'], context=job['payload']['context'],
                data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)
