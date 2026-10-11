"""Explicit measurements; guarded temporary UI effects do not edit geometry."""
import sqlite3
from pydantic import StrictFloat
from .contracts import ResponseEnvelope
from .jobs import JobError


def register_measurement_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,args,timeout_s,guarded=False):
        try:
            execute=runtime.mutate if guarded else runtime.read
            job=await execute(request_id,operation,args,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],
                context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def measurement_prepare_mass(request_id:str,document_id:str,configuration:str,
            expected_observation_revision:str,body_id:str|None=None,timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Prepare explicit part/active-configuration solid mass scope without changing UI.

        All solids including hidden bodies, or one persistent body_id. Returns
        a measurement revision for body membership, geometry moments and original
        selected-object references. It is not a revision for editing geometry.
        Assemblies/custom coordinate frames remain unavailable in this scope.
        """
        return await dispatch(request_id,'measurement.prepare_mass',dict(document_id=document_id,
            configuration=configuration,expected_observation_revision=expected_observation_revision,body_id=body_id),timeout_s)

    @app.tool()
    async def measurement_get_mass(request_id:str,document_id:str,configuration:str,
            expected_observation_revision:str,expected_revision:str,body_id:str|None=None,
            timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Calculate volume mm3, area mm2, mass kg and model-frame center mm.

        Geometry is not edited. Temporary selection/lock/command-flag effects
        have a durable application checkpoint; exact original selection is
        restored once. Document/scoped mass or center overrides are rejected.
        Unknown restoration retains an application hold across restart: never
        repeat the calculation. A timeout does not cancel COM; poll job_get.
        request_id replay returns the same calculation, not a new measurement.
        """
        return await dispatch(request_id,'measurement.mass',dict(document_id=document_id,
            configuration=configuration,expected_observation_revision=expected_observation_revision,
            expected_revision=expected_revision,body_id=body_id),timeout_s,True)
