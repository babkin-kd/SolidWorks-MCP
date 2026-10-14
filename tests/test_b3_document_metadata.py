"""Actual document catalog/runner/SQLite, artificial original native handles."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.server_v2 import response
from test_document_catalog_v2 import Adapter, model
from test_feature_suppression_domain import InlineWorker

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_document_metadata import document_metadata_case
    from verifier_b3_reader import B3Reader
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def world(tmp_path):
    adapter = Adapter()
    adapter.models = [model(title='Контрольная деталь'), model(title='Рабочий сосед')]
    adapter.models[1].state['needs_save'] = True
    docs = DocumentCatalog(adapter)
    initial = docs.list()['documents']
    ids = [x['document_id'] for x in initial]
    original = dict(zip(ids, adapter.models))
    cfg = {key: list(native.state['configurations']) for key, native in original.items()}
    store = JobStore(tmp_path / 'jobs.sqlite')
    runner = JobRunner(store, InlineWorker())
    x = NS(ids=ids, cfg=cfg, adapter=adapter, original=original, store=store,
           calls=[], retained=[], full_calls=0, corrupt=None, native_corrupt=None)
    class Client:
        async def call_tool(self, tool, args):
            x.calls.append((tool, deepcopy(args)))
            if tool == 'job_get':
                job = store.get(args['operation_id'])
                data = job
            else:
                spec = SPECS[tool]
                payload = spec.payload(args)
                method = docs.list if tool == 'document_list' else docs.get
                def execute():
                    value = method(**payload['arguments'])
                    if x.corrupt: x.corrupt(tool, value)
                    return value
                job = runner.submit(args['request_id'], spec.operation, payload['arguments'], execute,
                                    context=payload['context'], mutates=False)
                data = job['result']
            return NS(isError=False, structuredContent=response(status=job['status'],
                operation_id=job['operation_id'], context=job['payload']['context'],
                data=data, error=job['error']).model_dump(mode='json'))
        def retain(self, reason): x.retained.append(reason)
        async def observe_once(self):
            return NS(child_can_close=not x.retained, fixture_can_cleanup=not x.retained)
    client = Client()
    x.reader = B3Reader(client, store.path, assert_before_dispatch=lambda: None, persist=lambda rows: None)
    def full():
        x.full_calls += 1
        return dict(artificial_full_session=[dict(canonical=i+1, metadata=deepcopy(m.state))
            for i, m in enumerate(adapter.models)], selection=[], active=ids[1], command_in_progress=False)
    def native(document_id, configuration):
        held = original[document_id]
        assert held.identity == adapter.models[ids.index(document_id)].identity
        # Independent raw current adapter metadata, not public result copies.
        metadata = deepcopy(held.state)
        metadata.update(configuration=configuration,
            configuration_is_active=configuration == held.state['active_configuration'],
            revision_scope='update_stamp_and_document_metadata')
        value = dict(metadata=metadata, native_identity=ids.index(document_id)+1,
            configuration_identity=10+ids.index(document_id)*2+cfg[document_id].index(configuration),
            native_receipt=dict(artificial_original_handle=True))
        if x.native_corrupt: x.native_corrupt(document_id, configuration, value)
        return value
    x.full, x.native = full, native
    yield x
    store.close()


def run(x, **overrides):
    args = dict(owned_document_ids=x.ids, configurations=x.cfg,
                capture_full=x.full, capture_document=x.native)
    args.update(overrides)
    return asyncio.run(document_metadata_case(x.reader, **args))


def test_two_original_parts_existing_active_and_inactive_configs_actual_journal(world):
    x = world
    result = run(x)
    assert len(result['rows']) == len(x.store.list(limit=100)['items']) == 5
    assert len(result['native_receipts']) == 4 and x.full_calls == 2
    assert result['before'] == result['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert all(m.state['active_configuration'] == 'Основная' for m in x.adapter.models)
    assert all(row['journal']['mutation'] is None for row in result['rows'])


@pytest.mark.parametrize('fault', ['revision', 'scope', 'active', 'native_metadata',
                                 'native_identity', 'configuration_identity', 'incomplete', 'session'])
def test_inconsistent_public_or_independent_native_scope_rejected(world, fault):
    x = world
    if fault in ('revision', 'scope', 'active'):
        def corrupt(tool, value):
            if tool == 'document_get':
                key = dict(revision='observation_revision', scope='revision_scope', active='configuration_is_active')[fault]
                value[key] = 'wrong' if key != 'configuration_is_active' else not value[key]
        x.corrupt = corrupt
    elif fault in ('native_metadata', 'native_identity', 'configuration_identity'):
        def corrupt(doc, cfg, value):
            if fault == 'native_metadata': value['metadata']['update_stamp'] += 1
            elif fault == 'native_identity': value['native_identity'] = 1
            else: value['configuration_identity'] = 1
        x.native_corrupt = corrupt
    elif fault == 'incomplete': x.native = lambda *args: {}
    else:
        original = x.full
        def full():
            value = original()
            if x.full_calls == 2: value['active'] = x.ids[0]
            return value
        x.full = full
    with pytest.raises(ValueError): run(x)


@pytest.mark.parametrize('fault', ['duplicate', 'missing_config', 'too_many_configs', 'missing_observer'])
def test_invalid_original_scope_prevents_any_dispatch(world, fault):
    x = world
    overrides = dict(duplicate=dict(owned_document_ids=[x.ids[0]]*2),
        missing_config=dict(configurations={x.ids[0]: ['Основная']}),
        too_many_configs=dict(configurations={key: ['A', 'B', 'C'] for key in x.ids}),
        missing_observer=dict(capture_document=None))[fault]
    with pytest.raises(ValueError): run(x, **overrides)
    assert x.calls == []
