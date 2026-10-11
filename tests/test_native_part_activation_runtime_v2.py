"""Runtime/real MCP facade and journal on artificial CAD; not native acceptance."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from solidworks_mcp.jobs import JobError
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.runtime_v2 import Runtime
from solidworks_mcp.server_v2 import create_app
from test_native_part_activation import setup, capture
from test_runtime_v2 import Worker


@pytest.fixture
def public(setup):
    x = setup
    state = SimpleNamespace(calls=[], request='activate')

    def factory():
        state.calls.append(threading.get_ident())
        return DocumentCatalog(x.adapter)

    runtime = Runtime(x.store, worker_factory=Worker, catalog_factory=factory)
    x.adapter.checkpoint_lookup = lambda: next(row for row in x.store.list()['items'] if row['request_id'] == state.request)
    state.runtime, state.app, state.x = runtime, create_app(x.store, runtime), x
    yield state
    assert runtime.shutdown()


async def call(p, name, **arguments):
    if name == 'document_activate_part_native':
        p.request = arguments['request_id']
    _, result = await p.app.call_tool(name, arguments)
    return result


async def prepare(p):
    listed = await call(p, 'document_list', request_id='list')
    p.document_id = next(row['document_id'] for row in listed['data']['documents']
                         if row['path'] == p.x.target.state['path'])
    args = dict(document_id=p.document_id, configuration='Основная')
    result = await call(p, 'document_prepare_activate_part_native', request_id='prepare', **args)
    assert result['status'] == 'succeeded', result
    return {**args, 'expected_revision': result['data']['revision']}


def test_discovery_and_contract_are_explicit_and_do_not_start_cad(public):
    p = public

    async def exercise():
        tools = {item.name: item for item in await p.app.list_tools()}
        schema = tools['document_activate_part_native'].inputSchema
        assert set(schema['required']) == {'request_id', 'document_id', 'configuration', 'expected_revision'}
        assert tools['document_activate_part_native'].outputSchema['type'] == 'object'
        assert schema['properties']['timeout_s']['default'] == 10.
        result = await call(p, 'system_get_info')
        assert 'document.activate_part_native' in result['data']['implemented_mutations']
        assert 'native_rectangular_part_activation_v1' in result['data']['mutation_revision_scopes']

    asyncio.run(exercise())
    assert not p.calls and p.runtime._native_part_activations is None and not p.x.store.list()['items']


def test_public_prepare_activate_replay_and_conflict_use_owning_runtime_domain(public):
    p = public

    async def exercise():
        args = await prepare(p)
        result = await call(p, 'document_activate_part_native', request_id='activate', **args)
        assert result['status'] == 'succeeded', result
        assert result['context']['document_id'] == p.document_id
        assert result['data']['value']['active_after_document_id'] == p.document_id
        assert await call(p, 'document_activate_part_native', request_id='activate', **args) == result
        conflict = await call(p, 'document_activate_part_native', request_id='activate',
                              **{**args, 'expected_revision': 'rev_other'})
        assert conflict['status'] == 'failed' and conflict['error']['code'] == 'request_conflict'
        assert p.x.adapter.activations == [p.x.target]
        assert p.x.store.get(result['operation_id'])['mutation']['phase'] == 'committed'
        assert p.runtime._native_part_activations.connection_epoch == p.runtime._connection_epoch
        assert p.runtime._native_part_activations.documents is p.runtime._catalog

    asyncio.run(exercise())
    assert len(p.calls) == 1 and p.calls[0] != threading.get_ident()


def test_public_unknown_replay_and_new_request_remain_held(public):
    p = public

    async def exercise():
        args = await prepare(p)
        p.x.adapter.open_fault = 'activation_throw'
        result = await call(p, 'document_activate_part_native', request_id='activate', **args)
        assert result['status'] == 'unknown' and result['error']['requires_reconciliation'] is True
        assert await call(p, 'document_activate_part_native', request_id='activate', **args) == result
        held = await call(p, 'document_activate_part_native', request_id='held', **args)
        assert held['error']['code'] == 'document_mutation_blocked'
        assert p.x.adapter.activations == [p.x.target]
        assert result['operation_id'] in p.runtime._native_part_activations.receipts

    asyncio.run(exercise())


@pytest.mark.parametrize('tool', ['document_prepare_activate_part_native', 'document_activate_part_native'])
@pytest.mark.parametrize('invalid', [True, '10', -1., 121., float('inf'), float('nan')])
def test_invalid_timeout_never_starts_runtime_or_records_job(public, tool, invalid):
    p = public
    args = dict(request_id='invalid', document_id='doc', configuration='Основная', timeout_s=invalid)
    if tool == 'document_activate_part_native':
        args['expected_revision'] = 'rev'
    with pytest.raises(ToolError):
        asyncio.run(p.app.call_tool(tool, args))
    assert not p.calls and p.x.store.list()['items'] == []


@pytest.mark.parametrize('route,operation', [('read', 'document.activate_part_native'),
                                           ('mutate', 'document.prepare_activate_part_native')])
def test_wrong_runtime_route_never_starts_worker(public, route, operation):
    with pytest.raises(JobError):
        asyncio.run(getattr(public.runtime, route)('wrong', operation, {}))
    assert not public.calls and not public.x.store.list()['items']
