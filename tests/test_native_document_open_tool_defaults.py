"""Actual facade defaults are explicit durable input, independent of caller."""

import asyncio
from types import SimpleNamespace

import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.native_document_open_tools_v2 import register_native_document_open_tools


@pytest.mark.parametrize('mutate', [False, True])
@pytest.mark.parametrize('read_only', [False, True])
def test_omitted_false_and_explicit_policies_have_exact_durable_facade_payloads(mutate, read_only):
    functions, calls = {}, []
    class App:
        def tool(self):
            def register(function):
                functions[function.__name__] = function
                return function
            return register
    async def dispatch(request_id, operation, arguments, *, timeout_s):
        calls.append((request_id, operation, arguments.copy(), timeout_s))
        return dict(status='queued', operation_id='op_exact', payload={'context': {}}, result=None, error=None)
    def response(**kwargs):
        return ResponseEnvelope(**kwargs)
    register_native_document_open_tools(App(), SimpleNamespace(read=dispatch, mutate=dispatch),
        response, lambda exc: pytest.fail(str(exc)))
    if mutate:
        tool, operation = 'document_open_native', 'document.open_native'
        durable = dict(document_id='app_prepared', configuration='Основная',
                       expected_revision='rev_exact', native_file_id='native_file_exact')
    else:
        tool, operation = 'document_prepare_open_native', 'document.prepare_open_native'
        durable = dict(filename='C:/Работа/Новая деталь.SLDPRT', document_type='part', configuration='Основная')
    kwargs = dict(request_id='same_request', **durable)
    if read_only:
        kwargs['read_only'] = True
    asyncio.run(functions[tool](**kwargs))
    asyncio.run(functions[tool](**kwargs, timeout_s=0., **({} if read_only else {'read_only': False})))
    expected = {**durable, 'read_only': read_only}
    assert calls == [('same_request', operation, expected, 10.), ('same_request', operation, expected, 0.)]
    assert set(expected).isdisjoint({'request_id', 'timeout_s'})
