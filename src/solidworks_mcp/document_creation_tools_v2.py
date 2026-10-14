"""Explicit configured-template facade for bounded new unsaved parts."""

import sqlite3
from typing import Annotated

from pydantic import Field

from .contracts import ResponseEnvelope
from .jobs import JobError


def register_document_creation_tools(app, runtime, response, failure):
    async def dispatch(request_id, operation, arguments, timeout_s, *, mutates=False):
        try:
            job = await (runtime.mutate if mutates else runtime.read)(request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def document_list_templates(request_id: str,
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10) -> ResponseEnvelope:
        """Read the configured existing .prtdot and return an opaque template_id.

        No CAD mutation/file writing or fallback NewPart. Only the SolidWorks
        configured default part template is currently supported; arbitrary client
        paths and assembly/drawing templates are unavailable. The returned
        application_id belongs to this connection. Template SHA256/identity binds
        the actual file; a changed template requires new preparation.
        """
        return await dispatch(request_id, 'document.list_templates', {}, timeout_s)

    @app.tool()
    async def document_prepare_create_part(request_id: str, template_id: str, name: str,
            configuration_name: str = 'Основная',
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10) -> ResponseEnvelope:
        """Prepare a new empty part, without creating/activating/saving anything.

        Use template_id from document_list_templates and Russian display names.
        Initial scope supports an empty session or existing parts without active
        sketch editing; assemblies/drawings and a preexisting command flag are
        rejected. The revision binds this connection/application, template file,
        input, existing document metadata/configurations/stamps/save flags/views
        and active document/visibility. It is not a full add-in state revision.
        Pass these exact inputs/application_id/revision to document_create_part.
        """
        return await dispatch(request_id, 'document.prepare_create_part', {'template_id': template_id,
            'name': name, 'configuration_name': configuration_name}, timeout_s)

    @app.tool()
    async def document_create_part(request_id: str, application_id: str, expected_revision: str,
            template_id: str, name: str, configuration_name: str = 'Основная',
            timeout_s: Annotated[float, Field(strict=True, ge=0, le=120)] = 10) -> ResponseEnvelope:
        """Create one new unsaved empty part from the prepared configured template.

        Explicit application target is required because no target document exists
        yet. Durable context maps application_id to document_id with configuration
        ""; the result after.created_document_id is the new real doc_* reference.
        Creates and activates the part, assigning Russian title/configuration.
        Template must produce an empty writable single-configuration part.
        Checkpoints before native/UI effects, owns and releases its command flag,
        locks existing parts and preserves their original selections/marks.
        Verifies existing metadata/views and exact returned new-document ownership.
        Scoped restoration closes only that exact owned new unsaved document and
        restores prior activation. Unknown native effects hold the application:
        never replay NewDocument or close guessed/foreign documents. No disk save.
        Repeat request_id retrieves the same job. timeout_s limits waiting only;
        poll job_get. Use feature_list and part_prepare_base_extrusion to continue.
        """
        return await dispatch(request_id, 'document.create_part', {'document_id': application_id,
            'configuration': '', 'expected_revision': expected_revision, 'template_id': template_id,
            'name': name, 'configuration_name': configuration_name}, timeout_s, mutates=True)
