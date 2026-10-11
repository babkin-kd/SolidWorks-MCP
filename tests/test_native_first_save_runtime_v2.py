"""Real domain/journal/MCP integration using artificial CAD and filesystem effects."""
import asyncio
from copy import deepcopy
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobError, JobStore
from solidworks_mcp import runtime_v2 as module
from solidworks_mcp.server_v2 import create_app
from test_native_first_save import FakeFiles, FirstSaveAdapter
from test_runtime_v2 import Worker


@pytest.fixture
def setup(monkeypatch, tmp_path):
    store = JobStore(tmp_path / 'runtime.sqlite')
    files = FakeFiles()
    state = SimpleNamespace(calls=[], documents=None, adapter=None, request='save')
    constructor = module.NativeFirstSaveCatalog
    monkeypatch.setattr(module, 'NativeFirstSaveCatalog',
                        lambda documents, journal, epoch: constructor(documents, journal, epoch, files=files))

    def catalog_factory():
        state.calls.append(threading.get_ident())
        adapter = FirstSaveAdapter(tmp_path)
        source = adapter.add('Новая контрольная деталь', saved=False)
        neighbor = adapter.add('Соседняя рабочая деталь')
        for current in (source, neighbor):
            current.state['needs_save'] = True
            current.state['configurations'] = ['Основная']
        adapter.active = source
        original = tmp_path / 'Исходная папка'
        original.mkdir()
        adapter.app['current_directory'] = str(original)
        adapter.checkpoint_lookup = lambda: next(row for row in store.list(limit=100)['items']
                                                if row['request_id'] == state.request)
        state.adapter, state.source, state.neighbor = adapter, source, neighbor
        state.documents = DocumentCatalog(adapter)
        return state.documents

    runtime = module.Runtime(store, worker_factory=Worker, catalog_factory=catalog_factory)
    app = create_app(store, runtime)
    state.runtime, state.store, state.files, state.app = runtime, store, files, app
    state.filename = str(tmp_path / 'Сохранённая контрольная деталь.SLDPRT')
    yield state
    assert runtime.shutdown()
    store.close()


async def call(x, tool, **arguments):
    _, result = await x.app.call_tool(tool, arguments)
    return result


async def prepare(x):
    listed = await call(x, 'document_list', request_id='list')
    document_id = next(row['document_id'] for row in listed['data']['documents'] if not row['path'])
    args = dict(document_id=document_id, configuration='Основная', filename=x.filename)
    prepared = await call(x, 'document_prepare_first_save_native', request_id='prepare', **args)
    assert prepared['status'] == 'succeeded', prepared
    return {**args, 'expected_revision': prepared['data']['revision']}


def test_discovery_has_no_cad_side_effect_and_mutation_contract_is_explicit(setup):
    x = setup
    async def exercise():
        tools = {tool.name: tool for tool in await x.app.list_tools()}
        execute = tools['document_first_save_native'].inputSchema
        assert set(execute['required']) == {'request_id', 'document_id', 'configuration', 'filename', 'expected_revision'}
        info = await call(x, 'system_get_info')
        assert 'document.first_save_native' in info['data']['implemented_mutations']
    asyncio.run(exercise())
    assert not x.calls and x.runtime._native_first_saves is None and x.store.list()['items'] == []


def test_public_chain_returns_replacement_identity_and_replay_has_no_second_effect(setup):
    x = setup
    async def exercise():
        args = await prepare(x)
        neighbor = (deepcopy(x.neighbor.state), deepcopy(x.neighbor.view),
                    Path(x.neighbor.state['path']).read_bytes())
        saved = await call(x, 'document_first_save_native', request_id='save', **args)
        assert saved['status'] == 'succeeded', saved
        value = saved['data']['value']
        assert value['document_id'] != args['document_id']
        assert value['retired_document_ids'] == [args['document_id']]
        assert value['source_references_retired'] and value['resolve_saved_references_again']
        assert saved['context']['expected_revision'] == args['expected_revision']
        assert saved['context']['document_id'] == args['document_id']
        assert await call(x, 'document_first_save_native', request_id='save', **args) == saved
        conflict = await call(x, 'document_first_save_native', request_id='save', **{**args, 'filename': x.filename + 'x'})
        assert conflict['status'] == 'failed' and conflict['error']['code'] == 'request_conflict'
        assert x.adapter.copy_calls == x.files.publications == 1
        assert x.adapter.dead_getters == 0
        assert (x.neighbor.state, x.neighbor.view, Path(x.neighbor.state['path']).read_bytes()) == neighbor
        job = x.store.get(saved['operation_id'])
        assert job['mutation']['phase'] == 'committed'
        assert job['mutation']['verification']['native_steps']
        assert x.runtime._native_first_saves.documents is x.runtime._catalog
        assert x.runtime._native_first_saves.connection_epoch == x.runtime._connection_epoch
    asyncio.run(exercise())
    assert len(x.calls) == 1 and x.calls[0] != threading.get_ident()


def test_public_unknown_keeps_journal_and_replay_does_not_repeat_copy(setup):
    x = setup
    async def exercise():
        args = await prepare(x)
        x.adapter.copy_fault = 'throw_after'
        unknown = await call(x, 'document_first_save_native', request_id='save', **args)
        assert unknown['status'] == 'unknown' and unknown['error']['requires_reconciliation']
        assert await call(x, 'document_first_save_native', request_id='save', **args) == unknown
        assert x.adapter.copy_calls == 1 and x.files.publications == 0
        assert x.store.get(unknown['operation_id'])['mutation']['phase'] == 'unresolved'
        x.request = 'held'
        blocked = await call(x, 'document_first_save_native', request_id='held', **args)
        assert blocked['error']['code'] == 'document_mutation_blocked'
        assert x.adapter.copy_calls == 1 and x.files.publications == 0
        assert not x.source.retired
    asyncio.run(exercise())


def test_existing_destination_is_rejected_without_cad_copy(setup):
    x = setup
    async def exercise():
        args = await prepare(x)
        Path(x.filename).write_bytes(b'foreign file')
        failed = await call(x, 'document_first_save_native', request_id='save', **args)
        assert failed['status'] == 'failed', failed
        assert not failed['error']['requires_reconciliation']
        assert Path(x.filename).read_bytes() == b'foreign file'
        assert x.adapter.copy_calls == 0 and x.files.creations == 0
    asyncio.run(exercise())


@pytest.mark.parametrize('tool', ['document_prepare_first_save_native', 'document_first_save_native'])
@pytest.mark.parametrize('invalid', [True, '10', -1., 121., float('inf'), float('nan')])
def test_invalid_timeout_never_starts_worker_or_records_job(setup, tool, invalid):
    x = setup
    args = dict(request_id='invalid', document_id='doc', configuration='Основная', filename=x.filename, timeout_s=invalid)
    if tool == 'document_first_save_native':
        args['expected_revision'] = 'rev'
    with pytest.raises(ToolError):
        asyncio.run(x.app.call_tool(tool, args))
    assert not x.calls and x.store.list()['items'] == []


@pytest.mark.parametrize('route,operation', [('read', 'document.first_save_native'),
                                           ('mutate', 'document.prepare_first_save_native')])
def test_wrong_runtime_route_cannot_start_worker(setup, route, operation):
    x = setup
    with pytest.raises(JobError):
        asyncio.run(getattr(x.runtime, route)('wrong-route', operation, {}))
    assert not x.calls and x.store.list()['items'] == []
