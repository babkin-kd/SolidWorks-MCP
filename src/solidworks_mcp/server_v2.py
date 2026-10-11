"""Application API v2. Durable job inspection never enters the CAD STA queue.

This development entry point exposes only implemented capabilities. CAD domain
tools are added as their explicit document/object contracts are implemented.
"""

import argparse
import hashlib
from importlib import metadata, resources
import json
from pathlib import Path
import sqlite3
import sys
import sysconfig
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import StrictFloat, StrictInt

from . import __version__
from .build_info import source_digest
from .contracts import ResponseEnvelope
from .dimension_tools_v2 import register_dimension_tools
from .measurement_tools_v2 import register_measurement_tools
from .component_tools_v2 import register_component_tools
from .component_topology_tools_v2 import register_component_topology_tools
from .component_distance_tools_v2 import register_component_distance_tools
from .component_point_distance_tools_v2 import register_component_point_distance_tools
from .component_axis_distance_tools_v2 import register_component_axis_distance_tools
from .part_tools_v2 import register_part_tools
from .part_cut_tools_v2 import register_part_cut_tools
from .part_hole_tools_v2 import register_part_hole_tools
from .part_pattern_tools_v2 import register_part_pattern_tools
from .part_fillet_tools_v2 import register_part_fillet_tools
from .part_revolve_tools_v2 import register_part_revolve_tools
from .sheet_profile_tools_v2 import register_sheet_profile_tools
from .sheet_flat_tools_v2 import register_sheet_flat_tools
from .sheet_flange_flat_tools_v2 import register_sheet_flange_flat_tools
from .sheet_parameter_tools_v2 import register_sheet_parameter_tools
from .sheet_edge_flange_tools_v2 import register_sheet_edge_flange_tools
from .document_creation_tools_v2 import register_document_creation_tools
from .sketch_tools_v2 import register_sketch_tools
from .export_tools_v2 import register_export_tools
from .jobs import JOURNAL_SCHEMA_VERSION, JobError, JobStore
from .runtime_v2 import Runtime, READ_OPERATIONS, MUTATING_OPERATIONS
from .timings_v2 import TimingConfig, TimingRecorder
from .timing_tools_v2 import TimingToolRegistrar, register_timing_tools


API_VERSION = 2
SCHEMA_VERSION = '2.0-dev'


def response(*, status='succeeded', operation_id=None, context=None,
             data=None, diagnostics=None, error=None):
    return ResponseEnvelope(status=status, operation_id=operation_id, context=context or {},
                            data=data, diagnostics=diagnostics or [], error=error)


def failure(exc):
    if isinstance(exc, sqlite3.Error):
        exc = JobError('journal_unavailable', 'Job storage is unavailable; verify it before continuing.')
    return response(status='failed', error={'code': exc.code, 'message': str(exc)})


def create_app(store: JobStore, runtime: Runtime | None = None, *, timings=None) -> FastMCP:
    runtime = runtime if runtime is not None else Runtime(store)
    app = FastMCP('SolidWorks MCP v2', instructions=(
        'Development API v2. Read solidworks://guide/v2 for the supported contract. '
        'Only advertised tools are available. Jobs survive timeouts; poll their operation_id. '
        'An unknown outcome requires reconciliation before retrying an operation. '
        'Names of new CAD objects must be meaningful Russian names; standard components '
        'must come from approved libraries. Document/part geometry reads and guarded part feature '
        'renaming, scoped dimension changes and part exports are available. Exports require '
        'a server-configured output directory and supported planar polyhedral geometry. '
        'Each operation requires its own declared revision scope; '
        'observation revisions are not mutation guards.'
    ))
    native_app = app
    app = TimingToolRegistrar(app, timings)

    @app.resource('solidworks://guide/v2')
    def guide() -> str:
        return resources.files('solidworks_mcp').joinpath('guide_v2.md').read_text(encoding='utf-8')

    @app.tool()
    async def system_get_info() -> ResponseEnvelope:
        """Read API/package/schema versions and implemented capabilities; no CAD changes."""
        tools = [tool.model_dump(mode='json', exclude_none=True) for tool in await app.list_tools()]
        schemas = json.dumps(tools, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        build_path = resources.files('solidworks_mcp').joinpath('build_info.json')
        build = json.loads(build_path.read_text(encoding='utf-8')) if build_path.is_file() else None
        actual_digest = source_digest(Path(__file__).parent)
        verified = (build.get('package_version') == __version__ and build.get('source_digest') == actual_digest
                    and build.get('api_version') == API_VERSION) if build else None
        return response(data={
            'api_version': API_VERSION, 'schema_version': SCHEMA_VERSION,
            'package_version': __version__, 'mcp_sdk_version': metadata.version('mcp'),
            'schema_hash': hashlib.sha256(schemas.encode('utf-8')).hexdigest(),
            'build': build, 'source_digest': actual_digest, 'build_matches_source': verified,
            'platform': sys.platform, 'development_candidate': True,
            'capabilities': {'job_journal': True, 'job_query': True, 'queued_job_cancellation': True,
                             'timing_diagnostics': True,
                             'cad_documents': True, 'cad_mutations': True,
                             'resolved_part_component_axis_distance': True, 'resolved_part_component_point_distance': True, 'resolved_part_component_distance': True, 'resolved_assembly_instance_reads': True, 'resolved_assembly_instance_topology_reads': True, 'part_geometry_reads': True, 'part_bounds_measurements': True, 'part_mass_measurements': True, 'persistent_geometry_references': True,
                             'part_feature_reads': True, 'part_feature_rename': True,
                             'part_dimension_reads': True, 'part_dimension_set_value': True,
                             'new_part_documents': True, 'part_base_extrusion': True,
                             'part_linear_sketch_reads': True, 'rectangular_sketch_dimensions': True,
                             'part_corner_through_cut': True,
                             'part_full_turn_base_revolve': True,
                             'part_circular_through_hole': True,
                             'part_circular_through_hole_dimension': True,
                             'part_linear_through_hole_pattern': True,
                             'part_selected_edge_fillet': True,
                             'sheet_l_profile': True,
                             'sheet_flat_state': True,
                             'sheet_parameters': True,
                             'sheet_edge_flange': True,
                             'sheet_flange_flat_state': True,
                             'part_exports': True,
                             'pdm': False, 'simulation': False},
            'export_output_configured': runtime.export_output_configured,
            'timing_collection_enabled': bool(timings is not None and timings.config.enabled),
            'implemented_mutations': ['measurement.mass', 'feature.rename', 'dimension.set_value', 'export.execute', 'part.create_base_extrusion', 'document.create_part', 'sketch.set_dimension', 'part.create_corner_cut', 'part.create_base_revolve', 'part.create_through_hole', 'part.set_hole_dimension', 'part.create_linear_hole_pattern', 'part.create_edge_fillet', 'sheet.create_l_profile', 'sheet.set_flat_state', 'sheet.set_parameters', 'sheet.create_edge_flange', 'sheet.set_flange_flat_state'],
            'mutation_revision_scopes': ['part_mass_selection_measurement_v1', 'part_feature_tree_v1', 'part_dimension_values_v1',
                                         'part_solid_brep_export_v1', 'empty_part_base_rectangle_v1', 'new_empty_part_document_v1', 'part_rectangular_sketch_dimension_v1', 'single_base_rectangular_corner_through_cut_v1', 'empty_part_full_turn_cylinder_revolve_v1', 'single_base_circular_through_hole_v1', 'single_base_circular_through_hole_dimension_v1', 'single_base_linear_through_hole_pattern_v1', 'single_base_selected_edge_fillet_v1', 'empty_part_sheet_l_profile_v1', 'single_l_sheet_flat_state_v1', 'single_l_sheet_parameters_v1', 'single_l_sheet_edge_flange_v1', 'single_u_sheet_flat_state_v1'],
            'journal_schema_version': JOURNAL_SCHEMA_VERSION,
        })

    @app.tool()
    async def job_get(operation_id: str) -> ResponseEnvelope:
        """Read a durable job by operation_id, including a late result or unknown outcome."""
        try:
            job = store.get(operation_id)
            return response(status=job['status'], operation_id=operation_id,
                            context=job['payload']['context'], data=job, error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def job_list(limit: StrictInt = 100, before_created_at: StrictFloat | None = None,
                       before_operation_id: str = '') -> ResponseEnvelope:
        """Page through durable jobs, newest first; pass both cursor fields for the next page."""
        try:
            return response(data=store.list(limit=limit, before_created_at=before_created_at,
                                             before_operation_id=before_operation_id))
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def job_cancel(operation_id: str) -> ResponseEnvelope:
        """Cancel only a queued job. A running COM operation cannot be force-cancelled."""
        try:
            return response(data=store.cancel(operation_id))
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    async def read_document(request_id, operation, arguments, timeout_s):
        try:
            job = await runtime.read(request_id, operation, arguments, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                            context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def document_list(request_id: str, timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """List open documents with opaque IDs/configurations and observation revisions.

        Read-only: does not activate, save, resolve components, or change visibility.
        Use a new request_id for a fresh snapshot; retries retrieve the same job.
        A timeout returns its running/queued status; poll job_get for completion.
        """
        return await read_document(request_id, 'document.list', {}, timeout_s)

    @app.tool()
    async def document_get(request_id: str, document_id: str, configuration: str,
                           timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """Read metadata for an explicit open document and existing configuration.

        Never switches the active document/configuration. Use configuration=""
        only when document_list reports no configurations. Observation revisions
        cover stamps and document metadata, not all CAD properties or geometry.
        """
        return await read_document(request_id, 'document.get',
                                   {'document_id': document_id, 'configuration': configuration}, timeout_s)

    @app.tool()
    async def body_list(request_id: str, document_id: str, configuration: str,
                        expected_observation_revision: str, body_type: Literal['all', 'solid', 'surface'] = 'all',
                        limit: StrictInt = 100, cursor: str = '', timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """Page native solid/surface bodies of an explicit part's active configuration.

        Pass the current observation_revision from document_get/list. No automatic
        activation or rebuild. IDs are opaque persistent references, never indices.
        Bounding boxes are approximate and remain in the model coordinate frame.
        """
        return await read_document(request_id, 'geometry.list', {
            'document_id': document_id, 'configuration': configuration,
            'expected_observation_revision': expected_observation_revision, 'kind': 'body',
            'body_type': body_type, 'limit': limit, 'cursor': cursor}, timeout_s)

    @app.tool()
    async def face_list(request_id: str, document_id: str, configuration: str,
                        expected_observation_revision: str, body_id: str, limit: StrictInt = 100,
                        cursor: str = '', timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """Page faces of an explicit solid/surface body; areas are mm², IDs are opaque."""
        return await read_document(request_id, 'geometry.list', {
            'document_id': document_id, 'configuration': configuration,
            'expected_observation_revision': expected_observation_revision, 'kind': 'face',
            'body_id': body_id, 'limit': limit, 'cursor': cursor}, timeout_s)

    @app.tool()
    async def edge_list(request_id: str, document_id: str, configuration: str,
                        expected_observation_revision: str, body_id: str, limit: StrictInt = 100,
                        cursor: str = '', timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """Page edges of an explicit solid/surface body; lengths/endpoints are mm."""
        return await read_document(request_id, 'geometry.list', {
            'document_id': document_id, 'configuration': configuration,
            'expected_observation_revision': expected_observation_revision, 'kind': 'edge',
            'body_id': body_id, 'limit': limit, 'cursor': cursor}, timeout_s)

    @app.tool()
    async def geometry_get(request_id: str, document_id: str, configuration: str,
                           expected_observation_revision: str, object_id: str,
                           timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """Resolve an opaque body/face/edge reference in its original document/configuration.

        Revalidates the native persistent reference and parent body. Deleted,
        suppressed, foreign or obsolete references fail without a fallback.
        """
        return await read_document(request_id, 'geometry.get', {
            'document_id': document_id, 'configuration': configuration,
            'expected_observation_revision': expected_observation_revision, 'object_id': object_id}, timeout_s)

    @app.tool()
    async def feature_list(request_id: str, document_id: str, configuration: str,
                           limit: StrictInt = 100, cursor: str = '', timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """Read a part's complete scoped feature-tree revision and a page of native features.

        Explicit active configuration; no activation/rebuild. Includes absorbed
        subfeatures. Opaque IDs use native persistent references, never names/indices.
        Unsupported built-in nodes have object_id=null. The revision scope is
        part_feature_tree_v1 for feature.rename, not arbitrary CAD/plugin state.
        """
        return await read_document(request_id, 'feature.list', {'document_id': document_id,
            'configuration': configuration, 'limit': limit, 'cursor': cursor}, timeout_s)

    @app.tool()
    async def feature_get(request_id: str, document_id: str, configuration: str,
                          object_id: str, timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """Resolve a persistent feature ID in its original part/configuration and read its revision."""
        return await read_document(request_id, 'feature.get', {'document_id': document_id,
            'configuration': configuration, 'object_id': object_id}, timeout_s)

    @app.tool()
    async def feature_rename(request_id: str, document_id: str, configuration: str, object_id: str,
                             expected_revision: str, name: str, timeout_s: StrictFloat = 10) -> ResponseEnvelope:
        """Rename one explicitly referenced part feature to a Russian name with durable verification.

        Obtain expected_revision from feature_list/get (part_feature_tree_v1).
        Rechecks document/configuration/reference/revision on the STA immediately
        before writing. Rejects suppressed targets, duplicate names and pending
        rebuilds. Checkpoints before-state, verifies only the requested name changes
        and no new feature defects appear; scoped restoration on failure. No save,
        activation or implicit rebuild. An uncertain restoration holds the document.
        """
        try:
            job = await runtime.mutate(request_id, 'feature.rename', {'document_id': document_id,
                'configuration': configuration, 'object_id': object_id, 'expected_revision': expected_revision,
                'name': name}, timeout_s=timeout_s)
            return response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=job['result'], error=job['error'])
        except (JobError, sqlite3.Error) as exc:
            return failure(exc)

    register_dimension_tools(app, runtime, response, failure)
    register_measurement_tools(app, runtime, response, failure)
    register_component_tools(app, runtime, response, failure)
    register_component_topology_tools(app, runtime, response, failure)
    register_component_distance_tools(app, runtime, response, failure)
    register_component_point_distance_tools(app, runtime, response, failure)
    register_component_axis_distance_tools(app, runtime, response, failure)
    register_part_tools(app, runtime, response, failure)
    register_part_cut_tools(app, runtime, response, failure)
    register_part_hole_tools(app, runtime, response, failure)
    register_part_pattern_tools(app, runtime, response, failure)
    register_part_fillet_tools(app, runtime, response, failure)
    register_part_revolve_tools(app, runtime, response, failure)
    register_sheet_profile_tools(app, runtime, response, failure)
    register_sheet_flat_tools(app, runtime, response, failure)
    register_sheet_flange_flat_tools(app, runtime, response, failure)
    register_sheet_parameter_tools(app, runtime, response, failure)
    register_sheet_edge_flange_tools(app, runtime, response, failure)
    register_document_creation_tools(app, runtime, response, failure)
    register_sketch_tools(app, runtime, response, failure)
    register_export_tools(app, runtime, response, failure)
    # Explicit output model keeps the same envelope schema as all public tools.
    register_timing_tools(app, timings, response)
    return native_app


def main():
    parser = argparse.ArgumentParser(prog='solidworks-mcp-v2')
    parser.add_argument('--state-dir', type=Path, required=True,
                        help='Persistent private directory for the job journal; do not use a temporary directory.')
    parser.add_argument('--output-dir', type=Path,
                        help='Existing operator-approved export directory; clients cannot choose an output path.')
    parser.add_argument('--enable-timings', action='store_true', help='Enable optional private bounded timing collection.')
    parser.add_argument('--timings-max-records', type=int, default=1000)
    parser.add_argument('--timings-retention-days', type=int, default=7)
    parser.add_argument('--timings-max-mib', type=int, default=16)
    args = parser.parse_args()
    config = TimingConfig(enabled=args.enable_timings, max_records=args.timings_max_records,
        retention_days=args.timings_retention_days,max_database_bytes=args.timings_max_mib*1024*1024)
    timings = None
    if config.enabled:
        build_path = resources.files('solidworks_mcp').joinpath('build_info.json')
        if not build_path.is_file():
            parser.error('Timing collection requires a verified installed build.')
        build = json.loads(build_path.read_text(encoding='utf8'))
        if (build['package_version'] != __version__ or build['source_digest'] != source_digest(Path(__file__).parent)
                or build['source_dirty'] is not False or metadata.version('solidworks-mcp') != __version__
                or not Path(__file__).parent.resolve().is_relative_to(Path(sysconfig.get_path('purelib')).resolve())):
            parser.error('Timing collection requires a verified installed build.')
        timings = TimingRecorder(args.state_dir/'timings.sqlite',config=config,
            build={key:build[key] for key in ('package_version','git_sha','source_digest')},
            operations=READ_OPERATIONS+MUTATING_OPERATIONS)
    store = JobStore(args.state_dir / 'jobs.sqlite')
    runtime = Runtime(store, approved_output_root=args.output_dir, timings=timings)
    try:
        create_app(store, runtime, timings=timings).run()
    finally:
        stopped = runtime.shutdown()
        # Keep the optional store alive if a late COM result can still finish.
        if timings is not None and stopped:
            timings.close()


if __name__ == '__main__':
    main()
