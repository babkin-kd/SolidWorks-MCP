"""Explicit passive assembly instance/body catalog, without legacy aliases."""
import sqlite3
from typing import Literal
from pydantic import StrictFloat,StrictInt
from .contracts import ResponseEnvelope
from .jobs import JobError


def register_component_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,args,timeout_s):
        try:
            job = await runtime.read(request_id,operation,args,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],
                            context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def component_list(request_id:str,document_id:str,configuration:str,expected_observation_revision:str,
            limit:StrictInt=100,cursor:str='',timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Page persistent instances of explicit assembly/active configuration.

        Fully resolved native parts/subassemblies, including hidden instances.
        Rechecks full hierarchy/configuration/transform. No resolution, activation,
        selection or rebuild. Suppressed/lightweight/SpeedPak reject this scope.
        Paths are labels; opaque component_id targets the original native instance.
        p_assembly_mm=origin_mm+sum(axes_in_assembly[i]*p_component_mm[i]);
        excludes presentation/exploded display transform. Revisions are observations.
        """
        return await dispatch(request_id,'component.list',dict(document_id=document_id,configuration=configuration,
            expected_observation_revision=expected_observation_revision,limit=limit,cursor=cursor),timeout_s)

    @app.tool()
    async def component_get(request_id:str,document_id:str,configuration:str,expected_observation_revision:str,
            component_id:str,timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Resolve original native instance, never a name or reused file path.

        Deleted/foreign/inactive/replaced model/configuration references fail.
        Renaming may change displayed path without selecting another instance.
        """
        return await dispatch(request_id,'component.get',dict(document_id=document_id,configuration=configuration,
            expected_observation_revision=expected_observation_revision,component_id=component_id),timeout_s)

    @app.tool()
    async def component_body_list(request_id:str,document_id:str,configuration:str,expected_observation_revision:str,
            component_id:str,body_type:Literal['all','solid','surface']='all',timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Read <=500 normal native solid/surface bodies of a resolved part instance.

        Persistent body IDs belong to the exact component_id and root assembly.
        Approximate bounding boxes use component-local mm; apply returned transform.
        Includes hidden bodies. Assembly-cut/mesh/subassembly-wide bodies unavailable.
        """
        return await dispatch(request_id,'component.bodies',dict(document_id=document_id,configuration=configuration,
            expected_observation_revision=expected_observation_revision,component_id=component_id,body_type=body_type),timeout_s)

    @app.tool()
    async def component_body_get(request_id:str,document_id:str,configuration:str,expected_observation_revision:str,
            component_id:str,body_id:str,timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Resolve original body within its exact instance/configuration/membership.

        Body of another instance of the same part is rejected. Returns one-item
        local-coordinate list, no selection/model effects or index fallback.
        """
        return await dispatch(request_id,'component.bodies',dict(document_id=document_id,configuration=configuration,
            expected_observation_revision=expected_observation_revision,component_id=component_id,body_id=body_id),timeout_s)
