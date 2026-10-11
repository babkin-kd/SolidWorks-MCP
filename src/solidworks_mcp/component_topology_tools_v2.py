"""Passive topology reads with exact instance/body targeting."""
import sqlite3
from pydantic import StrictFloat,StrictInt
from .contracts import ResponseEnvelope
from .jobs import JobError


def register_component_topology_tools(app,runtime,response,failure):
    async def dispatch(request_id,operation,args,timeout_s):
        try:
            job=await runtime.read(request_id,operation,args,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],
                context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:return failure(exc)

    @app.tool()
    async def component_face_list(request_id:str,document_id:str,configuration:str,expected_observation_revision:str,
            component_id:str,body_id:str,limit:StrictInt=100,cursor:str='',timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Page persistent faces of one normal native solid/surface instance body.

        Explicit root assembly/active configuration, component_id and body_id.
        Area mm2; root-assembly references checked against exact native owner body.
        Rechecks whole instance/body/topology snapshots including between pages.
        No selection, activation, resolve or rebuild; never searches by names/indices.
        Observations are not mutation revisions. Inherits resolved-instance scope.
        """
        return await dispatch(request_id,'component.topology_list',dict(document_id=document_id,configuration=configuration,
            expected_observation_revision=expected_observation_revision,component_id=component_id,body_id=body_id,kind='face',limit=limit,cursor=cursor),timeout_s)

    @app.tool()
    async def component_edge_list(request_id:str,document_id:str,configuration:str,expected_observation_revision:str,
            component_id:str,body_id:str,limit:StrictInt=100,cursor:str='',timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Page persistent edges of one exact normal native instance body.

        Length/endpoints are component-local mm; apply returned component transform
        to reach assembly axes. Start/end may coincide for closed curves. Rechecks
        native owner and complete snapshots. No approximate box-distance inference.
        Resolved instance/normal body scope; no temporary sketches or UI effects.
        """
        return await dispatch(request_id,'component.topology_list',dict(document_id=document_id,configuration=configuration,
            expected_observation_revision=expected_observation_revision,component_id=component_id,body_id=body_id,kind='edge',limit=limit,cursor=cursor),timeout_s)

    @app.tool()
    async def component_topology_get(request_id:str,document_id:str,configuration:str,expected_observation_revision:str,
            component_id:str,body_id:str,object_id:str,timeout_s:StrictFloat=10.) -> ResponseEnvelope:
        """Resolve original instance face/edge within exact body/configuration.

        Foreign/deleted/replaced/nonmember references fail without reassignment.
        Body IDs use component_body_get; this tool accepts only face/edge IDs.
        Returns native area/length/local endpoints and the current instance transform.
        """
        return await dispatch(request_id,'component.topology_get',dict(document_id=document_id,configuration=configuration,
            expected_observation_revision=expected_observation_revision,component_id=component_id,body_id=body_id,object_id=object_id),timeout_s)
