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

from mcp.server.fastmcp import FastMCP

from . import __version__
from .build_info import source_digest
from .contracts import ResponseEnvelope
from .jobs import JobError, JobStore


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


def create_app(store: JobStore) -> FastMCP:
    app = FastMCP('SolidWorks MCP v2', instructions=(
        'Development API v2. Read solidworks://guide/v2 for the supported contract. '
        'Only advertised tools are available. Jobs survive timeouts; poll their operation_id. '
        'An unknown outcome requires reconciliation before retrying an operation. '
        'Names of new CAD objects must be meaningful Russian names; standard components '
        'must come from approved libraries. CAD tools are not yet available in this candidate.'
    ))

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
                             'cad_documents': False, 'cad_mutations': False,
                             'pdm': False, 'simulation': False},
            'journal_schema_version': 1,
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
    async def job_list(limit: int = 100, before_created_at: float | None = None,
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

    return app


def main():
    parser = argparse.ArgumentParser(prog='solidworks-mcp-v2')
    parser.add_argument('--state-dir', type=Path, required=True,
                        help='Persistent private directory for the job journal; do not use a temporary directory.')
    args = parser.parse_args()
    store = JobStore(args.state_dir / 'jobs.sqlite')
    try:
        create_app(store).run()
    finally:
        store.close()


if __name__ == '__main__':
    main()
