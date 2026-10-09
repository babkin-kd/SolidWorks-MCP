"""Real FastMCP schemas/calls against an artificial runtime; no CAD/COM."""

import asyncio
from copy import deepcopy
import sqlite3

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.dimension_tools_v2 import register_dimension_tools
from solidworks_mcp.jobs import JobError


FIELDS = {'status', 'operation_id', 'context', 'data', 'diagnostics', 'error'}
CONTEXT = {'document_id': 'doc_explicit', 'configuration': 'Основная'}
ARGUMENTS = {
    'dimension_list': {**CONTEXT, 'request_id': 'read-page', 'limit': 2, 'cursor': 'cursor_explicit', 'timeout_s': 0},
    'dimension_get': {**CONTEXT, 'request_id': 'read-value', 'object_id': 'dim_explicit', 'timeout_s': 2.5},
    'dimension_set_value': {**CONTEXT, 'request_id': 'change-value', 'object_id': 'dim_explicit',
                          'expected_revision': 'rev_explicit', 'value': 9., 'unit': 'mm', 'timeout_s': 0},
}


class Runtime:
    def __init__(self):
        self.calls = []
        self.exception = None
        self.job = {'status': 'succeeded', 'operation_id': 'op_explicit', 'payload': {'context': CONTEXT},
                    'result': {'revision_scope': 'part_dimension_values_v1', 'revision': 'rev_result',
                               'dimension': {'object_id': 'dim_explicit', 'unit': 'mm',
                                   'values': {'Основная': 7.}, 'write_blockers': [],
                                   'reference_anchor': {'strategy': 'display_dimension_v1', 'dimension_index': 0},
                                   'native_incarnation': 'native_dim_explicit'}}, 'error': None}
    async def read(self, request_id, operation, arguments, *, timeout_s):
        return self.execute('read', request_id, operation, arguments, timeout_s)
    async def mutate(self, request_id, operation, arguments, *, timeout_s):
        return self.execute('mutate', request_id, operation, arguments, timeout_s)
    def execute(self, method, request_id, operation, arguments, timeout_s):
        self.calls.append((method, request_id, operation, deepcopy(arguments), timeout_s))
        if self.exception:
            raise self.exception
        return deepcopy(self.job)


@pytest.fixture
def app():
    runtime, responses, failures = Runtime(), [], []
    instance = FastMCP('dimension-candidate-test')
    def response(**kwargs):
        responses.append(deepcopy(kwargs))
        return ResponseEnvelope(diagnostics=[], **kwargs)
    def failure(exc):
        failures.append(exc)
        code = exc.code if isinstance(exc, JobError) else 'journal_unavailable'
        return ResponseEnvelope(status='failed', operation_id=None, context={}, data=None, diagnostics=[],
                                error={'code': code, 'message': str(exc)})
    register_dimension_tools(instance, runtime, response, failure)
    return instance, runtime, responses, failures


def invoke(app, tool, arguments):
    return asyncio.run(app.call_tool(tool, arguments))[1]


@pytest.mark.parametrize('tool,method,operation', [
    ('dimension_list', 'read', 'dimension.list'), ('dimension_get', 'read', 'dimension.get'),
    ('dimension_set_value', 'mutate', 'dimension.set_value')])
def test_exact_explicit_arguments_route_without_wait_parameter_in_idempotent_payload(app, tool, method, operation):
    instance, runtime, responses, failures = app
    arguments = deepcopy(ARGUMENTS[tool])
    result = invoke(instance, tool, arguments)
    expected = {key: value for key, value in arguments.items() if key not in ('request_id', 'timeout_s')}
    assert runtime.calls == [(method, arguments['request_id'], operation, expected, arguments['timeout_s'])]
    assert set(result) == FIELDS and result['status'] == 'succeeded'
    assert result['operation_id'] == runtime.job['operation_id'] and result['context'] == CONTEXT
    assert result['data'] == runtime.job['result'] and result['error'] is None
    assert len(responses) == 1 and failures == []


def test_get_preserves_full_captured_anchor_incarnation_and_revision(app):
    instance, runtime, _, _ = app
    result = invoke(instance, 'dimension_get', ARGUMENTS['dimension_get'])
    assert result['data'] == runtime.job['result']
    assert result['data']['dimension']['reference_anchor'] == {'strategy': 'display_dimension_v1', 'dimension_index': 0}
    assert result['data']['dimension']['native_incarnation'] == 'native_dim_explicit'
    assert result['data']['revision'] == 'rev_result'


@pytest.mark.parametrize('status', ['queued', 'running', 'failed', 'unknown', 'cancelled'])
def test_non_success_status_does_not_trigger_poll_cancel_retry_or_success_claim(app, status):
    instance, runtime, _, _ = app
    runtime.job.update(status=status, result=None)
    if status in ('failed', 'unknown'):
        runtime.job['error'] = {'code': 'state_requires_reconciliation', 'message': 'Проверить состояние', 'hold': True}
    result = invoke(instance, 'dimension_set_value', ARGUMENTS['dimension_set_value'])
    assert result['status'] == status and result['data'] is None
    assert result['error'] == runtime.job['error']
    assert len(runtime.calls) == 1 and result['operation_id'] == 'op_explicit'


@pytest.mark.parametrize('tool', list(ARGUMENTS))
@pytest.mark.parametrize('exception,code', [
    (JobError('invalid_timeout', 'Invalid waiting limit'), 'invalid_timeout'),
    (sqlite3.OperationalError('disk I/O error'), 'journal_unavailable')])
def test_runtime_and_journal_errors_use_injected_uniform_failure_factory(app, tool, exception, code):
    instance, runtime, responses, failures = app
    runtime.exception = exception
    result = invoke(instance, tool, ARGUMENTS[tool])
    assert set(result) == FIELDS and result['status'] == 'failed' and result['error']['code'] == code
    assert result['operation_id'] is None and result['data'] is None
    assert responses == [] and failures == [exception] and len(runtime.calls) == 1


def test_catalog_contains_only_three_typed_tools_and_explicit_required_targets(app):
    instance = app[0]
    tools = {tool.name: tool for tool in asyncio.run(instance.list_tools())}
    assert set(tools) == set(ARGUMENTS)
    required = {'dimension_list': {'request_id', 'document_id', 'configuration'},
                'dimension_get': {'request_id', 'document_id', 'configuration', 'object_id'},
                'dimension_set_value': {'request_id', 'document_id', 'configuration', 'object_id',
                                        'expected_revision', 'value', 'unit'}}
    for name, tool in tools.items():
        assert tool.outputSchema['type'] == 'object' and set(tool.outputSchema['properties']) == FIELDS
        assert set(tool.inputSchema['required']) == required[name]
        assert tool.inputSchema['properties']['timeout_s']['default'] == 10
        assert tool.inputSchema['properties']['timeout_s']['minimum'] == 0
        assert tool.inputSchema['properties']['timeout_s']['maximum'] == 120
        assert 'part_dimension_values_v1' in tool.description
    assert tools['dimension_set_value'].inputSchema['properties']['value']['type'] == 'number'
    assert tools['dimension_list'].inputSchema['properties']['limit']['default'] == 100
    assert tools['dimension_list'].inputSchema['properties']['limit']['minimum'] == 1
    assert tools['dimension_list'].inputSchema['properties']['limit']['maximum'] == 200
    assert tools['dimension_list'].inputSchema['properties']['cursor']['default'] == ''


@pytest.mark.parametrize('tool,omit', [('dimension_list', 'document_id'), ('dimension_get', 'object_id'),
                                      ('dimension_set_value', 'expected_revision'), ('dimension_set_value', 'unit')])
def test_missing_explicit_target_prevents_runtime_dispatch(app, tool, omit):
    instance, runtime, _, _ = app
    args = {key: value for key, value in ARGUMENTS[tool].items() if key != omit}
    with pytest.raises(ToolError):
        invoke(instance, tool, args)
    assert runtime.calls == []


@pytest.mark.parametrize('value', [True, False, '9', None])
def test_dimension_number_schema_rejects_boolean_or_string_coercion_before_dispatch(app, value):
    instance, runtime, _, _ = app
    with pytest.raises(ToolError):
        invoke(instance, 'dimension_set_value', {**ARGUMENTS['dimension_set_value'], 'value': value})
    assert runtime.calls == []


def test_integer_number_and_explicit_unknown_unit_reach_domain_without_unit_conversion(app):
    instance, runtime, _, _ = app
    runtime.job.update(status='failed', result=None, error={'code': 'invalid_dimension_unit', 'message': 'Explicit mm/deg required'})
    result = invoke(instance, 'dimension_set_value', {**ARGUMENTS['dimension_set_value'], 'value': 9, 'unit': 'inch'})
    assert result['status'] == 'failed' and result['error']['code'] == 'invalid_dimension_unit'
    assert runtime.calls[0][3]['value'] == 9. and runtime.calls[0][3]['unit'] == 'inch'


def test_list_defaults_are_forwarded_and_no_legacy_alias_is_registered(app):
    instance, runtime, _, _ = app
    invoke(instance, 'dimension_list', {'request_id': 'fresh', **CONTEXT})
    assert runtime.calls == [('read', 'fresh', 'dimension.list', {**CONTEXT, 'limit': 100, 'cursor': ''}, 10)]
    with pytest.raises(ToolError):
        invoke(instance, 'set_dimension', ARGUMENTS['dimension_set_value'])
    assert len(runtime.calls) == 1


@pytest.mark.parametrize('value', [True, False, '10', float('nan'), float('inf'), float('-inf'), 0, 201, 2.5])
def test_limit_is_strict_bounded_integer_and_never_dispatches_invalid_input(app, value):
    instance, runtime, responses, failures = app
    with pytest.raises(ToolError):
        invoke(instance, 'dimension_list', {**ARGUMENTS['dimension_list'], 'limit': value})
    assert runtime.calls == [] and responses == [] and failures == []


@pytest.mark.parametrize('tool', list(ARGUMENTS))
@pytest.mark.parametrize('value', [True, False, '10', float('nan'), float('inf'), float('-inf'), -.01, 120.01])
def test_timeout_is_strict_finite_and_bounded_before_any_read_or_mutation_dispatch(app, tool, value):
    instance, runtime, responses, failures = app
    with pytest.raises(ToolError):
        invoke(instance, tool, {**ARGUMENTS[tool], 'timeout_s': value})
    assert runtime.calls == [] and responses == [] and failures == []


@pytest.mark.parametrize('tool', list(ARGUMENTS))
@pytest.mark.parametrize('value', [0, 120, .25])
def test_timeout_accepts_integer_json_numbers_and_fractional_wait_with_exact_bounds(app, tool, value):
    instance, runtime, _, _ = app
    invoke(instance, tool, {**ARGUMENTS[tool], 'timeout_s': value})
    assert len(runtime.calls) == 1 and runtime.calls[0][4] == value


@pytest.mark.parametrize('value', [1, 200])
def test_limit_accepts_both_integer_bounds(app, value):
    instance, runtime, _, _ = app
    invoke(instance, 'dimension_list', {**ARGUMENTS['dimension_list'], 'limit': value})
    assert len(runtime.calls) == 1 and runtime.calls[0][3]['limit'] == value
