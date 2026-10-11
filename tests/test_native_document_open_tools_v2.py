"""Real MCP validation/routing to artificial runtime; no installed/CAD proof."""

import asyncio
from copy import deepcopy
import sqlite3

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.jobs import JobError
from solidworks_mcp.native_document_open_tools_v2 import register_native_document_open_tools


PREPARE = dict(request_id='prepare-file', filename='C:/Работа/Корпус.SLDPRT',
               document_type='part', configuration='Основная')
EXECUTE = dict(request_id='open-file', document_id='app_prepared', configuration='Основная',
               expected_revision='rev_exact', native_file_id='native_file_prepared')
TOOLS = [('document_prepare_open_native', 'read', 'document.prepare_open_native', PREPARE),
         ('document_open_native', 'mutate', 'document.open_native', EXECUTE)]
FIELDS = {'status', 'operation_id', 'context', 'data', 'diagnostics', 'error'}


class Runtime:
    def __init__(self):
        self.calls = []
        self.exception = None
        self.job = dict(status='succeeded', operation_id='op_exact',
            payload={'context': {'document_id': 'app_prepared', 'configuration': 'Основная'}},
            result={'document_id': 'doc_new', 'configuration': 'Основная', 'verified': True}, error=None)

    async def read(self, request_id, operation, arguments, *, timeout_s):
        return self.execute('read', request_id, operation, arguments, timeout_s)

    async def mutate(self, request_id, operation, arguments, *, timeout_s):
        return self.execute('mutate', request_id, operation, arguments, timeout_s)

    def execute(self, method, request_id, operation, arguments, timeout_s):
        self.calls.append((method, request_id, operation, deepcopy(arguments), timeout_s))
        if self.exception is not None:
            raise self.exception
        return deepcopy(self.job)


@pytest.fixture
def setup():
    app, runtime, responses, failures = FastMCP('native-open-test'), Runtime(), [], []
    def response(**kwargs):
        responses.append(deepcopy(kwargs))
        return ResponseEnvelope(diagnostics=[], **kwargs)
    def failure(exc):
        failures.append(exc)
        code = exc.code if isinstance(exc, JobError) else 'journal_unavailable'
        return ResponseEnvelope(status='failed', operation_id=None, context={}, data=None,
            error={'code': code, 'message': str(exc)})
    register_native_document_open_tools(app, runtime, response, failure)
    return app, runtime, responses, failures


def invoke(app, tool, arguments):
    return asyncio.run(app.call_tool(tool, arguments))[1]


@pytest.mark.parametrize('tool,method,operation,arguments', TOOLS)
@pytest.mark.parametrize('read_only', [False, True])
def test_explicit_payload_routes_exact_application_or_file_target_without_wait_fields(
        setup, tool, method, operation, arguments, read_only):
    app, runtime, responses, failures = setup
    arguments = {**arguments, 'read_only': read_only, 'timeout_s': 0.}
    result = invoke(app, tool, arguments)
    durable = {key: value for key, value in arguments.items() if key not in ('request_id', 'timeout_s')}
    assert runtime.calls == [(method, arguments['request_id'], operation, durable, 0.)]
    assert set(result) == FIELDS and result['status'] == 'succeeded'
    assert result['context'] == runtime.job['payload']['context']
    assert result['operation_id'] == 'op_exact' and result['data'] == runtime.job['result']
    assert result['error'] is None and result['diagnostics'] == []
    assert len(responses) == 1 and failures == []
    if method == 'mutate':
        assert durable['document_id'] == 'app_prepared'
        assert result['data']['document_id'] == 'doc_new'


@pytest.mark.parametrize('tool,method,operation,arguments', TOOLS)
@pytest.mark.parametrize('status', ['queued', 'running', 'failed', 'unknown', 'cancelled'])
def test_non_success_envelope_is_preserved_without_retry_cancel_poll_or_success_claim(
        setup, tool, method, operation, arguments, status):
    app, runtime, responses, failures = setup
    runtime.job.update(status=status, result=None)
    if status in ('failed', 'unknown'):
        runtime.job['error'] = {'code': 'native_open_unconfirmed', 'message': 'Native outcome unconfirmed.'}
    result = invoke(app, tool, {**arguments, 'timeout_s': 0.})
    assert result['status'] == status and result['data'] is None
    assert result['operation_id'] == 'op_exact'
    assert result['error'] == runtime.job['error']
    assert len(runtime.calls) == 1 and len(responses) == 1 and failures == []


@pytest.mark.parametrize('tool,method,operation,arguments', TOOLS)
@pytest.mark.parametrize('exception,code', [
    (JobError('request_id_conflict', 'Payload changed.'), 'request_id_conflict'),
    (sqlite3.OperationalError('Storage unavailable.'), 'journal_unavailable')])
def test_expected_job_and_journal_errors_use_shared_failure_envelope(
        setup, tool, method, operation, arguments, exception, code):
    app, runtime, responses, failures = setup
    runtime.exception = exception
    result = invoke(app, tool, arguments)
    assert result['status'] == 'failed' and result['operation_id'] is None
    assert result['context'] == {} and result['data'] is None and result['error']['code'] == code
    assert failures == [exception] and responses == [] and len(runtime.calls) == 1


def test_unexpected_runtime_fault_is_not_fabricated_as_known_domain_failure(setup):
    app, runtime, responses, failures = setup
    runtime.exception = RuntimeError('Unexpected integration defect.')
    with pytest.raises(ToolError, match='Unexpected integration defect'):
        invoke(app, 'document_open_native', EXECUTE)
    assert failures == [] and responses == [] and len(runtime.calls) == 1


def test_both_tools_have_explicit_required_inputs_bool_default_and_bounded_timeout_schema(setup):
    app, _, _, _ = setup
    tools = {tool.name: tool for tool in asyncio.run(app.list_tools())}
    assert set(tools) == {item[0] for item in TOOLS}
    for tool, _, _, arguments in TOOLS:
        schema = tools[tool].inputSchema
        assert set(schema['required']) == set(arguments)
        properties = schema['properties']
        assert properties['read_only']['type'] == 'boolean' and properties['read_only']['default'] is False
        assert properties['timeout_s']['type'] == 'number'
        assert properties['timeout_s']['default'] == 10.
        assert properties['timeout_s']['minimum'] == 0 and properties['timeout_s']['maximum'] == 120
        assert tools[tool].outputSchema['properties']['status']['enum'] == [
            'queued', 'running', 'succeeded', 'failed', 'cancelled', 'unknown']


@pytest.mark.parametrize('tool,method,operation,arguments', TOOLS)
@pytest.mark.parametrize('value', [0, 1, -1, 0., 1., 'true', 'false', '', None, [], {}])
def test_read_only_strict_bool_rejects_coercions_without_runtime_dispatch(
        setup, tool, method, operation, arguments, value):
    app, runtime, responses, failures = setup
    with pytest.raises(ToolError):
        invoke(app, tool, {**arguments, 'read_only': value})
    assert runtime.calls == [] and responses == [] and failures == []


@pytest.mark.parametrize('tool,method,operation,arguments', TOOLS)
@pytest.mark.parametrize('value', [True, False, '10', None, -0.001, 120.001,
                                  float('inf'), float('-inf'), float('nan')])
def test_timeout_strict_finite_and_bounded_without_runtime_dispatch(
        setup, tool, method, operation, arguments, value):
    app, runtime, responses, failures = setup
    with pytest.raises(ToolError):
        invoke(app, tool, {**arguments, 'timeout_s': value})
    assert runtime.calls == [] and responses == [] and failures == []


@pytest.mark.parametrize('tool,method,operation,arguments', TOOLS)
@pytest.mark.parametrize('timeout', [0., 10., 120.])
def test_timeout_boundaries_only_change_wait_argument(setup, tool, method, operation, arguments, timeout):
    app, runtime, _, _ = setup
    invoke(app, tool, {**arguments, 'timeout_s': timeout})
    assert runtime.calls[0][4] == timeout
    assert runtime.calls[0][3] == {key: value for key, value in arguments.items() if key != 'request_id'} | {'read_only': False}


@pytest.mark.parametrize('missing', ['document_id', 'configuration', 'expected_revision', 'native_file_id'])
def test_execute_requires_application_reference_config_revision_and_file_reference(setup, missing):
    app, runtime, _, _ = setup
    arguments = {key: value for key, value in EXECUTE.items() if key != missing}
    with pytest.raises(ToolError):
        invoke(app, 'document_open_native', arguments)
    assert runtime.calls == []


@pytest.mark.parametrize('configuration', ['Основная', ''])
def test_prepare_forwards_exact_file_type_and_config_for_domain_validation(setup, configuration):
    app, runtime, _, _ = setup
    arguments = {**PREPARE, 'filename': 'relative-or-invalid-path',
                 'document_type': 'domain_must_validate', 'configuration': configuration}
    invoke(app, 'document_prepare_open_native', arguments)
    assert runtime.calls[0][3] == dict(filename='relative-or-invalid-path',
        document_type='domain_must_validate', configuration=configuration, read_only=False)
