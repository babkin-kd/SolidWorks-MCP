"""Explicit owned leaf preview/delete facade; registration is an integration gate."""
import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


Wait=Annotated[float,Field(strict=True,ge=0,le=120,allow_inf_nan=False)]


def register_owned_leaf_deletion_tools(app,runtime,response,failure):
    async def dispatch(operation,request_id,arguments,timeout_s,mutate=False):
        try:
            job=await (runtime.mutate if mutate else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],
                context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as error:
            return failure(error)

    @app.tool()
    async def feature_prepare_leaf_deletion(request_id:str,document_id:str,configuration:str,
            object_id:str,timeout_s:Wait=10.) -> ResponseEnvelope:
        """Preview deletion of an exact original server-owned leaf extrusion.

        Read only. Requires original succeeded B1 creation in the current
        connection epoch, active unsaved one-configuration BASE, complete
        supported neighbors, original PID/canonical ownership and no downstream
        or external dependencies. Current depth/Russian names and full session
        bind the revision. Returns the deleted feature and preserved sketch IDs,
        remaining dimensions and expected absence of bodies. Saved/user features,
        incomplete inventories and changed borrowed sketch are refused.
        Installed native acceptance is reported separately for each wheel.
        """
        return await dispatch('feature.prepare_leaf_deletion',request_id,
            dict(document_id=document_id,configuration=configuration,object_id=object_id),timeout_s)

    @app.tool()
    async def feature_delete_leaf(request_id:str,document_id:str,configuration:str,object_id:str,
            expected_revision:str,timeout_s:Wait=10.) -> ResponseEnvelope:
        """Delete only the previewed retained own leaf; preserve its original sketch.

        Explicit document/configuration/object, expected_revision and request_id
        are required. Full BASE-to-SKETCH postconditions, actual old PID state,
        current sketch canonical/PID, neighbors/UI/files, guarded native ledger
        and cache retirement decide success. Geometry references must be read
        again afterwards. No recursive deletion, absorbed-sketch deletion,
        automatic Undo, recreate or retry of unknown COM/ledger effects.
        Reuse request_id for the same job. timeout_s limits waiting, not COM;
        poll job_get for late results. Installed native acceptance is separate.
        """
        return await dispatch('feature.delete_leaf',request_id,
            dict(document_id=document_id,configuration=configuration,object_id=object_id,
                 expected_revision=expected_revision),timeout_s,True)
