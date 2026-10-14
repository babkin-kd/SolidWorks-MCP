"""Actual SketchCatalog/SQLite reads using the artificial B1-like rectangle."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.server_v2 import response
from test_sketch_dimensions_v2 import setup as sketch_setup

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_rectangle_sketch import rectangle_sketch_case
    from verifier_b3_reader import B3Reader
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def world(sketch_setup):
    a, catalog, store, runner, doc, obj, _ = sketch_setup
    part = a.models[0]
    original_feature = next(f for f in part.features if f.state['feature_type'] == 'ProfileFeature')
    x = NS(a=a, catalog=catalog, store=store, doc=doc, obj=obj, calls=[], retained=[],
           corrupt=None, native_corrupt=None, full_calls=0)
    class Client:
        async def call_tool(self, tool, args):
            x.calls.append((tool, deepcopy(args)))
            if tool == 'job_get':
                job = store.get(args['operation_id']); data = job
            else:
                payload = SPECS[tool].payload(args)
                def execute():
                    value = catalog.get(**payload['arguments'])
                    if x.corrupt: x.corrupt(value)
                    return value
                job = runner.submit(args['request_id'], SPECS[tool].operation, payload['arguments'], execute,
                                    context=payload['context'], mutates=False)
                data = job['result']
            return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=data, error=job['error']).model_dump(mode='json'))
        def retain(self, reason): x.retained.append(reason)
        async def observe_once(self): return NS(child_can_close=not x.retained, fixture_can_cleanup=not x.retained)
    x.reader = B3Reader(Client(), store.path, assert_before_dispatch=lambda: None, persist=lambda rows: None)
    def native(context, object_id):
        assert context == dict(document_id=doc, configuration='Основная') and object_id == obj
        assert original_feature in part.features
        # Raw artificial native getter and full dimension collector, not SketchCatalog.get DTO.
        snapshot, members = a.sketch_snapshot(part, original_feature)
        dimensions = catalog.dimensions._capture(doc, 'Основная').state[3]
        value = dict(sketch_snapshot=snapshot, dimension_semantic=deepcopy(dimensions),
            feature_pid_hex=original_feature.pid.hex(), feature_native_identity=1,
            native_receipt=dict(artificial_current_members=[key for key, identity in members]))
        if x.native_corrupt: x.native_corrupt(value)
        return value
    def full():
        x.full_calls += 1
        return dict(artificial_full_parts=[deepcopy(m.state) for m in a.models],
            ui=dict(active='original', selection=[], command_in_progress=False))
    x.native, x.full = native, full
    return x


def run(x, **overrides):
    args = dict(context=dict(document_id=x.doc, configuration='Основная'), sketch_object_id=x.obj,
                width_mm=40., height_mm=20., capture_full=x.full, capture_sketch=x.native)
    args.update(overrides)
    return asyncio.run(rectangle_sketch_case(x.reader, **args))


def test_original_full_constrained_rectangle_read_with_actual_durable_job(world):
    x = world; before_count = len(x.store.list(limit=100)['items'])
    value = run(x)
    assert len(value['rows']) == 1 and len(x.store.list(limit=100)['items']) == before_count+1
    assert value['rows'][0]['journal']['mutation'] is None
    assert value['before'] == value['after'] and x.full_calls == 2
    assert value['accepted'] is value['native_acceptance'] is value['cleanup_authorized'] is False


@pytest.mark.parametrize('fault', ['scope', 'object', 'pid', 'points', 'native', 'incomplete', 'multi_cfg', 'size', 'session'])
def test_current_native_sketch_or_full_scope_difference_rejects(world, fault):
    x = world
    def corrupt(value):
        if fault == 'scope': value['revision_scope'] = 'other'
        elif fault == 'object': value['object_id'] = 'other'
        elif fault == 'pid': value['sketch']['feature_pid_hex'] = '00'
        elif fault == 'points': value['sketch']['points'] = []
    x.corrupt = corrupt
    if fault == 'native': x.native_corrupt = lambda value: value.update(feature_native_identity=True)
    elif fault == 'incomplete': x.native = lambda *args: {}
    elif fault == 'multi_cfg':
        x.native_corrupt = lambda value: value['dimension_semantic']['tree']['document'].update(configurations=['Основная', 'Вариант'])
    elif fault == 'size':
        with pytest.raises(ValueError): run(x, width_mm=41.)
        return
    elif fault == 'session':
        original = x.full
        def full():
            value = original()
            if x.full_calls == 2: value['ui']['selection'] = ['other']
            return value
        x.full = full
    with pytest.raises(ValueError): run(x)


def test_missing_original_reference_prevents_dispatch(world):
    x = world
    with pytest.raises(ValueError): run(x, sketch_object_id='')
    assert x.calls == []
