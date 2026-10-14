"""Real feature/dimension catalogs and durable B3 reader; artificial native data."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import JobRunner
from solidworks_mcp.server_v2 import response
from test_dimension_domain_v2 import setup as dimension_setup, dimension
from test_feature_domain_v2 import feature
from test_feature_suppression_domain import InlineWorker

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_part_objects import part_objects_case
    from verifier_b3_reader import B3Reader
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def world(dimension_setup):
    a, catalog, store, ids = dimension_setup
    target = a.models[0]
    builtin = feature(2, 'Встроенный элемент', kind='RefPlane'); builtin.pid = b''
    target.features.append(builtin)
    target.dimensions[1] = dimension(2, kind=1, value=.75)
    unavailable = dimension(3); unavailable.pid = b''
    target.dimensions.append(unavailable)
    runner = JobRunner(store, InlineWorker())
    x = NS(a=a, catalog=catalog, store=store, ids=ids, context=dict(document_id=ids[0], configuration='Основная'),
           corrupt=None, native_corrupt=None, calls=[], retained=[], full_calls=0)
    class Client:
        async def call_tool(self, tool, args):
            x.calls.append((tool, deepcopy(args)))
            if tool == 'job_get':
                job = store.get(args['operation_id']); data = job
            else:
                spec = SPECS[tool]; payload = spec.payload(args)
                domain = catalog.features if tool.startswith('feature') else catalog
                method = domain.list if tool.endswith('list') else domain.get
                def execute():
                    value = method(**payload['arguments'])
                    if x.corrupt: x.corrupt(tool, value)
                    return value
                job = runner.submit(args['request_id'], spec.operation, payload['arguments'], execute,
                                    context=payload['context'], mutates=False)
                data = job['result']
            return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=data, error=job['error']).model_dump(mode='json'))
        def retain(self, reason): x.retained.append(reason)
        async def observe_once(self): return NS(child_can_close=not x.retained, fixture_can_cleanup=not x.retained)
    x.reader = B3Reader(Client(), store.path, assert_before_dispatch=lambda: None, persist=lambda rows: None)
    identities = []
    def ordinal(obj):
        if obj.identity not in identities: identities.append(obj.identity)
        return identities.index(obj.identity)+1
    def inventory(context, family):
        assert context == x.context
        native = target.features if family == 'feature' else target.dimensions
        rows = []
        for obj in native:
            summary = deepcopy(obj.state) if family == 'feature' else a.dimension_summary(obj, target.state['configurations'])
            if family == 'dimension': summary['reference_anchor'] = a.dimension_persistent_id(target, obj)
            rows.append(dict(summary=summary, native_identity=ordinal(obj), reference_supported=bool(obj.pid),
                native_receipt=dict(artificial_retained_pid=obj.pid.hex(), original_model=True)))
        value = dict(rows=rows)
        if x.native_corrupt: x.native_corrupt(family, value)
        return value
    def full():
        x.full_calls += 1
        return dict(artificial_full_parts=[dict(metadata=deepcopy(m.state),
            features=[deepcopy(f.state) for f in m.features], dimensions=[deepcopy(d.state) for d in m.dimensions])
            for m in a.models], ui=dict(active=ids[1], selected=[], command_in_progress=False))
    x.inventory, x.full = inventory, full
    return x


def run(x, **overrides):
    args = dict(context=x.context, capture_inventory=x.inventory, capture_full=x.full)
    args.update(overrides)
    return asyncio.run(part_objects_case(x.reader, **args))


def test_supported_refs_roundtrip_unsupported_rows_null_units_and_actual_journal(world):
    x = world; result = run(x)
    assert len(result['rows']) == len(x.store.list(limit=100)['items']) == 5
    assert len(result['inventories']) == 2 and x.full_calls == 2
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert result['before'] == result['after']
    assert x.a.dimension_writes == x.a.writes == []
    dimensions = next(row['journal']['result']['items'] for row in result['rows'] if row['tool'] == 'dimension_list')
    assert dimensions[1]['unit'] == 'deg' and dimensions[2]['object_id'] is None
    assert all(row['journal']['mutation'] is None for row in result['rows'])


@pytest.mark.parametrize('fault', ['scope', 'count', 'partial', 'owner', 'revision', 'roundtrip',
                                 'unsupported_id', 'unsupported_error', 'units', 'nonfinite', 'native', 'changed'])
def test_incomplete_or_inconsistent_native_public_proofs_are_not_accepted(world, fault):
    x = world
    def corrupt(tool, value):
        if fault == 'scope': value['revision_scope'] = 'other'
        elif fault == 'count' and tool.endswith('list'): value['total_count'] = True
        elif fault == 'partial' and tool.endswith('list'): value['next_cursor'] = 'next'
        elif fault == 'owner': value['document_id'] = x.ids[1]
        elif fault == 'revision' and tool.endswith('get'): value['revision'] = 'rev_other'
        elif fault == 'roundtrip' and tool.endswith('get'): value[tool.split('_')[0]]['name'] = 'Другое'
        elif fault == 'unsupported_id' and tool == 'feature_list': value['items'][1]['object_id'] = 'fake'
        elif fault == 'unsupported_error' and tool == 'feature_list': value['items'][1]['reference_error']['code'] = 'unexpected'
        elif fault == 'units' and tool == 'dimension_list': value['items'][0]['values']['Основная'] = .01
        elif fault == 'nonfinite' and tool == 'dimension_list': value['items'][0]['values_si']['Основная'] = float('nan')
    x.corrupt = corrupt
    if fault == 'native': x.native_corrupt = lambda family, value: value['rows'][0]['summary'].update(name='Подмена')
    if fault == 'changed':
        original = x.full
        def full():
            value = original()
            if x.full_calls == 2: value['ui']['selected'] = ['other']
            return value
        x.full = full
    with pytest.raises(ValueError): run(x)


def test_missing_full_current_inventory_prevents_dispatch(world):
    x = world
    with pytest.raises(ValueError): run(x, capture_inventory=lambda *args: {})
    assert x.calls == []
