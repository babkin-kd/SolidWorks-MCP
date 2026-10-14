"""Public-candidate transport/routing tests, independent of native acceptance."""

import asyncio
from copy import deepcopy
import sqlite3

from mcp.server.fastmcp import FastMCP
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.export_tools_v2 import register_export_tools
from solidworks_mcp.jobs import JobError


FIELDS = {'status', 'operation_id', 'context', 'data', 'diagnostics', 'error'}
BASE = {'request_id': 'export-request', 'document_id': 'doc_owned', 'configuration': 'Основная',
        'file_format': 'stl', 'filename': 'Контрольная деталь.stl', 'units': 'mm'}


def response(**kwargs):
    return ResponseEnvelope(status=kwargs.get('status', 'succeeded'),
        operation_id=kwargs.get('operation_id'), context=kwargs.get('context', {}),
        data=kwargs.get('data'), diagnostics=kwargs.get('diagnostics', []), error=kwargs.get('error'))


def failure(exc):
    if isinstance(exc, sqlite3.Error):
        exc = JobError('journal_unavailable', 'Job storage is unavailable; verify before continuing.')
    return response(status='failed', error={'code': exc.code, 'message': str(exc)})


class FakeRuntime:
    def __init__(self, *, status='succeeded', result=None, error=None, raises=None):
        self.calls = []
        self.status, self.result, self.error, self.raises = status, result, error, raises
    async def read(self, request, operation, arguments, *, timeout_s):
        return await self._call('read', request, operation, arguments, timeout_s)
    async def mutate(self, request, operation, arguments, *, timeout_s):
        return await self._call('mutate', request, operation, arguments, timeout_s)
    async def _call(self, kind, request, operation, arguments, timeout_s):
        self.calls.append((kind, request, operation, deepcopy(arguments), timeout_s))
        if self.raises:
            raise self.raises
        context = {key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')
                   if key in arguments}
        return {'status': self.status, 'operation_id': 'op_durable',
                'payload': {'context': context}, 'result': deepcopy(self.result), 'error': deepcopy(self.error)}


def app_for(runtime, **kwargs):
    app = FastMCP('Isolated export registration candidate')
    assert register_export_tools(app, runtime, kwargs.get('response', response), kwargs.get('failure', failure)) is app
    return app


def call(app, name, arguments):
    async def run():
        _, structured = await app.call_tool(name, arguments)
        return structured
    return asyncio.run(run())


def test_registration_is_opt_in_exact_schema_no_client_output_directory():
    runtime = FakeRuntime()
    app = FastMCP('Before optional registration')
    assert asyncio.run(app.list_tools()) == []
    register_export_tools(app, runtime, response, failure)
    tools = {tool.name: tool for tool in asyncio.run(app.list_tools())}
    assert set(tools) == {'export_prepare', 'export_part'}
    for name, tool in tools.items():
        required = {'request_id', 'document_id', 'configuration', 'file_format', 'filename'}
        if name == 'export_part': required.add('expected_revision')
        assert set(tool.inputSchema['required']) == required
        props = tool.inputSchema['properties']
        assert set(props) == required | {'units', 'timeout_s'}
        assert props['file_format']['enum'] == ['stl', 'step', 'parasolid']
        assert props['units']['enum'] == ['', 'mm', 'm', 'in'] and props['units']['default'] == ''
        assert props['timeout_s']['default'] == 10
        assert props['timeout_s']['minimum'] == 0 and props['timeout_s']['maximum'] == 120
        assert set(tool.outputSchema['properties']) == FIELDS
        assert 'planar polyhedral' in tool.description or 'analytical scope' in tool.description
    assert runtime.calls == []


@pytest.mark.parametrize('units', ['mm', 'm', 'in'])
def test_stl_prepare_explicit_unit_and_file_format_route_to_read(units):
    result = {'revision': 'export_rev_native', 'revision_scope': 'declared_export_scope',
              'options': {'format': 'stl', 'filename': BASE['filename'], 'units': units}}
    runtime = FakeRuntime(result=result)
    arguments = {**BASE, 'units': units}
    reply = call(app_for(runtime), 'export_prepare', arguments)
    assert set(reply) == FIELDS and reply['status'] == 'succeeded'
    assert reply['data'] == result
    assert reply['context'] == {'document_id': 'doc_owned', 'configuration': 'Основная'}
    assert runtime.calls == [('read', BASE['request_id'], 'export.prepare', {
        'document_id': 'doc_owned', 'configuration': 'Основная', 'format': 'stl',
        'filename': BASE['filename'], 'units': units}, 10)]


@pytest.mark.parametrize('file_format,units,embedded,evidence,extension', [
    ('stl', 'mm', False, 'Explicit STL mm; no embedded units.', '.stl'),
    ('stl', 'm', False, 'Explicit STL m; no embedded units.', '.stl'),
    ('stl', 'in', False, 'Explicit STL in; no embedded units.', '.stl'),
    ('step', 'mm', True, 'SI_UNIT(.MILLI.,.METRE.) length declaration.', '.step'),
    ('step', 'm', True, 'SI_UNIT($,.METRE.) length declaration.', '.step'),
    ('parasolid', None, None, 'PARASOLID text header; units not independently verified.', '.x_t'),
])
def test_manifest_unit_evidence_and_nullable_parasolid_facts_preserved(file_format, units, embedded, evidence, extension):
    manifest = {'format': file_format, 'units': units, 'units_embedded': embedded,
                'unit_evidence': evidence, 'native_warnings': 0, 'native_errors': 0,
                'geometry_roundtrip_verified': False, 'coordinate_frame': 'part_model'}
    result = {'verified': True, 'value': manifest, 'before': {'scope': 'declared'}, 'after': {'source_unchanged': True}}
    runtime = FakeRuntime(result=result)
    arguments = {**BASE, 'expected_revision': 'export_rev_exact', 'file_format': file_format,
                 'filename': 'Проверка' + extension, 'units': units if file_format == 'stl' else ''}
    reply = call(app_for(runtime), 'export_part', arguments)
    assert reply['data'] == result
    assert reply['data']['value']['units'] == units
    assert reply['data']['value']['units_embedded'] is embedded
    kind, request, operation, forwarded, timeout = runtime.calls[0]
    assert kind == 'mutate' and operation == 'export.execute' and request == BASE['request_id']
    assert forwarded['format'] == file_format and 'file_format' not in forwarded
    assert forwarded['expected_revision'] == 'export_rev_exact'
    assert forwarded['units'] == arguments['units'] and timeout == 10
    assert set(forwarded) == {'document_id', 'configuration', 'expected_revision', 'format', 'filename', 'units'}


@pytest.mark.parametrize('status', ['queued', 'running', 'cancelled', 'unknown'])
def test_pending_timeout_or_uncertainty_preserves_job_without_poll_retry_or_success(status):
    error = {'code': 'mutation_unconfirmed', 'message': 'Inspect state.', 'requires_reconciliation': True} if status == 'unknown' else None
    runtime = FakeRuntime(status=status, error=error)
    reply = call(app_for(runtime), 'export_part', {**BASE, 'expected_revision': 'export_rev_exact', 'timeout_s': 0})
    assert set(reply) == FIELDS and reply['status'] == status
    assert reply['operation_id'] == 'op_durable' and reply['data'] is None
    assert reply['error'] == error
    assert reply['context']['expected_revision'] == 'export_rev_exact'
    assert len(runtime.calls) == 1 and runtime.calls[0][4] == 0


def test_known_no_overwrite_failure_is_returned_once_without_override_option():
    error = {'code': 'export_file_exists', 'message': 'Destination exists; overwrite unsupported.'}
    runtime = FakeRuntime(status='failed', error=error)
    reply = call(app_for(runtime), 'export_part', {**BASE, 'expected_revision': 'export_rev_exact'})
    assert reply['status'] == 'failed' and reply['error'] == error
    assert len(runtime.calls) == 1
    assert 'overwrite' not in runtime.calls[0][3] and 'output_dir' not in runtime.calls[0][3]


@pytest.mark.parametrize('code', ['export_output_not_configured', 'stale_revision',
                                 'explicit_stl_units_required', 'unsupported_export_units',
                                 'native_export_warning', 'document_mutation_blocked'])
def test_domain_and_runtime_errors_keep_typed_envelope(code):
    runtime = FakeRuntime(raises=JobError(code, 'Explicit domain rejection.'))
    reply = call(app_for(runtime), 'export_prepare', BASE)
    assert set(reply) == FIELDS and reply['status'] == 'failed'
    assert reply['error']['code'] == code and reply['operation_id'] is None
    assert len(runtime.calls) == 1


def test_sqlite_error_uses_injected_application_failure_factory():
    runtime = FakeRuntime(raises=sqlite3.OperationalError('disk I/O'))
    errors = []
    def observed_failure(exc):
        errors.append(exc)
        return failure(exc)
    reply = call(app_for(runtime, failure=observed_failure), 'export_part', {**BASE, 'expected_revision': 'export_rev_exact'})
    assert reply['status'] == 'failed' and reply['error']['code'] == 'journal_unavailable'
    assert len(errors) == 1 and isinstance(errors[0], sqlite3.Error)


@pytest.mark.parametrize('changes', [{'file_format': 'iges'}, {'units': 'cm'},
                                    {'timeout_s': -1}, {'timeout_s': 121},
                                    {'timeout_s': True}, {'timeout_s': '10'}])
def test_invalid_schema_input_cannot_dispatch_runtime(changes):
    runtime = FakeRuntime()
    with pytest.raises(Exception):
        call(app_for(runtime), 'export_prepare', {**BASE, **changes})
    assert runtime.calls == []


def test_missing_expected_revision_does_not_dispatch_mutation():
    runtime = FakeRuntime()
    with pytest.raises(Exception): call(app_for(runtime), 'export_part', BASE)
    assert runtime.calls == []


def test_unexpected_exception_not_fabricated_as_verified_failure_or_success():
    runtime = FakeRuntime(raises=RuntimeError('Unexpected runtime defect'))
    with pytest.raises(Exception, match='Unexpected runtime defect'):
        call(app_for(runtime), 'export_part', {**BASE, 'expected_revision': 'export_rev_exact'})
    assert len(runtime.calls) == 1
