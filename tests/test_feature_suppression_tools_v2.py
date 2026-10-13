"""Isolated candidate MCP schema/dispatch with fake runtime; no CAD acceptance."""
import asyncio
from copy import deepcopy
import sqlite3
from types import SimpleNamespace as NS

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.feature_suppression_tools_v2 import register_feature_suppression_tools
from solidworks_mcp.jobs import JobError


TOOLS = [('feature_prepare_suppression', 'feature.prepare_suppression', False),
         ('feature_set_suppressed', 'feature.set_suppressed', True)]


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.error = None
        self.status = 'succeeded'
        self.context = {'document_id': 'own', 'configuration': 'Основная', 'expected_revision': 'durable-revision'}
        self.data = {'verified': True, 'body_name': 'Тело основания'}
        self.job_error = None

    async def read(self, request_id, operation, arguments, **kwargs):
        return self._dispatch(False, request_id, operation, arguments, kwargs)

    async def mutate(self, request_id, operation, arguments, **kwargs):
        return self._dispatch(True, request_id, operation, arguments, kwargs)

    def _dispatch(self, mutate, request_id, operation, arguments, kwargs):
        self.calls.append((mutate, request_id, operation, deepcopy(arguments), deepcopy(kwargs)))
        if self.error is not None:
            raise self.error
        return dict(status=self.status, operation_id='job_original', payload={'context': deepcopy(self.context)},
                    result=deepcopy(self.data), error=deepcopy(self.job_error))


@pytest.fixture
def candidate():
    app, runtime, failures = FastMCP('suppression-candidate-only'), FakeRuntime(), []
    def response(**kwargs):
        return ResponseEnvelope(**kwargs)
    def failure(error):
        failures.append(error)
        return response(status='failed', operation_id=None, context={}, data=None,
            error={'code': error.code if isinstance(error, JobError) else 'journal_unavailable', 'message': str(error)})
    register_feature_suppression_tools(app, runtime, response, failure)
    return NS(app=app, runtime=runtime, failures=failures)


def arguments(tool, **changes):
    result = dict(request_id='same_request', document_id='own', configuration='Основная',
                  object_id='feat_' + 'a' * 32, suppressed=True)
    if tool == 'feature_set_suppressed': result['expected_revision'] = 'full_revision'
    return {**result, **changes}


def call(candidate, tool, args):
    return asyncio.run(candidate.app.call_tool(tool, args))[1]


def test_explicit_candidate_registration_is_isolated_and_discovers_only_two_tools(candidate):
    untouched = FastMCP('unregistered-candidate')
    assert asyncio.run(untouched.list_tools()) == []
    by_name = {tool.name: tool for tool in asyncio.run(candidate.app.list_tools())}
    assert set(by_name) == {tool for tool, _, _ in TOOLS}
    for name, _, mutates in TOOLS:
        tool = by_name[name]
        schema = tool.inputSchema
        required = {'request_id', 'document_id', 'configuration', 'object_id', 'suppressed'}
        if mutates: required.add('expected_revision')
        assert set(schema['required']) == required
        properties = schema['properties']
        assert properties['suppressed']['type'] == 'boolean' and 'default' not in properties['suppressed']
        assert properties['timeout_s']['type'] == 'number'
        assert properties['timeout_s']['default'] == 10.
        assert properties['timeout_s']['minimum'] == 0 and properties['timeout_s']['maximum'] == 120
        assert ('expected_revision' in properties) is mutates
        assert tool.outputSchema['type'] == 'object'
        assert {'status', 'operation_id', 'data', 'error'} <= set(tool.outputSchema['required'])
        assert 'Installed native acceptance is reported separately' in tool.description
    assert not candidate.runtime.calls


@pytest.mark.parametrize('tool,operation,mutate', TOOLS)
@pytest.mark.parametrize('suppressed', [False, True])
@pytest.mark.parametrize('timeout', [None, 0., 120., 0, 120])
def test_exact_candidate_context_state_revision_and_default_wait_dispatch(candidate, tool, operation, mutate,
                                                                         suppressed, timeout):
    args = arguments(tool, suppressed=suppressed)
    if timeout is not None: args['timeout_s'] = timeout
    result = call(candidate, tool, args)
    domain_arguments = {key: value for key, value in args.items() if key not in ('request_id', 'timeout_s')}
    assert candidate.runtime.calls == [(mutate, 'same_request', operation, domain_arguments,
                                       {'timeout_s': 10. if timeout is None else float(timeout)})]
    assert result['status'] == 'succeeded' and result['operation_id'] == 'job_original'
    assert result['context'] == candidate.runtime.context
    assert result['data'] == candidate.runtime.data
    assert result['error'] is None and not candidate.failures


@pytest.mark.parametrize('tool,operation,mutate', TOOLS)
@pytest.mark.parametrize('invalid', [None, 0, 1, 0., 1., 'true', 'false', 'True', [], {}])
def test_suppressed_requires_strict_bool_before_runtime(candidate, tool, operation, mutate, invalid):
    with pytest.raises(ToolError): call(candidate, tool, arguments(tool, suppressed=invalid))
    assert not candidate.runtime.calls and not candidate.failures


@pytest.mark.parametrize('tool,operation,mutate', TOOLS)
@pytest.mark.parametrize('invalid', [True, False, None, '10', -1., 121., float('nan'), float('inf'), -float('inf')])
def test_timeout_requires_finite_numeric_wait_bounds_before_runtime(candidate, tool, operation, mutate, invalid):
    with pytest.raises(ToolError): call(candidate, tool, arguments(tool, timeout_s=invalid))
    assert not candidate.runtime.calls and not candidate.failures


@pytest.mark.parametrize('tool,operation,mutate', TOOLS)
@pytest.mark.parametrize('missing', ['request_id', 'document_id', 'configuration', 'object_id', 'suppressed'])
def test_explicit_scope_and_request_fields_are_required(candidate, tool, operation, mutate, missing):
    args = arguments(tool); args.pop(missing)
    with pytest.raises(ToolError): call(candidate, tool, args)
    assert not candidate.runtime.calls


@pytest.mark.parametrize('revision', [None, 1, True, [], {}])
def test_write_requires_typed_expected_revision_before_runtime(candidate, revision):
    with pytest.raises(ToolError):
        call(candidate, 'feature_set_suppressed', arguments('feature_set_suppressed', expected_revision=revision))
    assert not candidate.runtime.calls


def test_write_revision_is_required_without_default_or_prepare_substitution(candidate):
    args = arguments('feature_set_suppressed'); args.pop('expected_revision')
    with pytest.raises(ToolError): call(candidate, 'feature_set_suppressed', args)
    assert not candidate.runtime.calls


@pytest.mark.parametrize('tool,operation,mutate', TOOLS)
@pytest.mark.parametrize('status', ['queued', 'running', 'unknown', 'failed', 'cancelled'])
def test_late_unknown_and_failure_rows_are_forwarded_without_cancellation_retry_or_success(candidate, tool,
                                                                                        operation, mutate, status):
    candidate.runtime.status = status
    candidate.runtime.data = None
    candidate.runtime.job_error = {'code': 'native_unconfirmed', 'message': 'Retained hold'} if status == 'unknown' else None
    result = call(candidate, tool, arguments(tool, timeout_s=0.))
    assert result['status'] == status and result['operation_id'] == 'job_original'
    assert result['data'] is None and result['error'] == candidate.runtime.job_error
    assert len(candidate.runtime.calls) == 1 and not candidate.failures


@pytest.mark.parametrize('tool,operation,mutate', TOOLS)
def test_replay_identity_and_changed_payload_are_delegated_to_runtime_once_per_request(candidate, tool, operation, mutate):
    original = arguments(tool, suppressed=True, timeout_s=0.)
    first = call(candidate, tool, original)
    assert call(candidate, tool, original) == first
    assert len(candidate.runtime.calls) == 2
    assert candidate.runtime.calls[0] == candidate.runtime.calls[1]
    candidate.runtime.error = JobError('request_conflict', 'Same request has another suppression state.')
    changed = call(candidate, tool, {**original, 'suppressed': False})
    assert changed['status'] == 'failed' and changed['error']['code'] == 'request_conflict'
    assert len(candidate.runtime.calls) == 3
    assert candidate.runtime.calls[-1][1] == 'same_request'
    assert candidate.runtime.calls[-1][3]['suppressed'] is False


@pytest.mark.parametrize('tool,operation,mutate', TOOLS)
@pytest.mark.parametrize('error', [JobError('unsafe_scope', 'Complete supported scope required.'),
                                 sqlite3.OperationalError('Private journal unavailable')])
def test_expected_runtime_and_storage_errors_use_shared_failure_once(candidate, tool, operation, mutate, error):
    candidate.runtime.error = error
    result = call(candidate, tool, arguments(tool))
    assert result['status'] == 'failed' and result['operation_id'] is None
    assert candidate.failures == [error] and len(candidate.runtime.calls) == 1


@pytest.mark.parametrize('tool,operation,mutate', TOOLS)
def test_unexpected_runtime_exception_is_not_fabricated_as_domain_success(candidate, tool, operation, mutate):
    candidate.runtime.error = RuntimeError('Unclassified internal failure')
    with pytest.raises(ToolError): call(candidate, tool, arguments(tool))
    assert len(candidate.runtime.calls) == 1 and not candidate.failures
