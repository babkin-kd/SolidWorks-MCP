"""Actual geometry/mass catalogs and SQLite replay; artificial native adapters."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.server_v2 import response
from test_geometry_v2 import setup_geometry
from test_mass_measurement_v2 import mass

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_replay import replay_case
    from verifier_b3_reader import B3Reader
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def world(mass):
    m = mass
    x = NS(m=m, calls=[], dispatches=0, retained=[], replay_hook=None, full_calls=0)
    class Client:
        async def call_tool(self, tool, args):
            x.calls.append((tool, deepcopy(args)))
            if tool == 'job_get':
                job = m.store.get(args['operation_id']); data = job
            else:
                payload = SPECS[tool].payload(args)
                existing = next((row for row in m.store.list(limit=100)['items']
                                 if row['request_id'] == args['request_id']), None)
                def execute(operation_id):
                    x.dispatches += 1
                    if tool == 'geometry_get': return m.geometry.get(**payload['arguments'])
                    return m.catalog.measure(operation_id, **payload['arguments'])
                job = m.runner.submit(args['request_id'], SPECS[tool].operation, payload['arguments'], execute,
                    context=payload['context'], mutates=SPECS[tool].mutates, pass_operation_id=True,
                    verify=(lambda value: value['verified'] is True) if SPECS[tool].mutates else None)
                if existing is not None and x.replay_hook: x.replay_hook()
                data = job['result']
            return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=data, error=job['error']).model_dump(mode='json'))
        def retain(self, reason): x.retained.append(reason)
        async def observe_once(self):
            return NS(child_can_close=not x.retained, fixture_can_cleanup=not x.retained)
    x.reader = B3Reader(Client(), m.store.path, assert_before_dispatch=lambda: None, persist=lambda rows: None)
    body_id = m.geometry.list(**m.context, body_type='solid')['items'][0]['object_id']
    passive_args = dict(request_id='original-geometry', **m.context, object_id=body_id)
    passive = asyncio.run(x.reader.read('geometry_get', passive_args))
    prepared = m.catalog.prepare(**m.context)
    mass_args = dict(request_id='original-mass', **m.context, body_id=None, expected_revision=prepared['revision'])
    measured = asyncio.run(x.reader.read('measurement_get_mass', mass_args))
    x.passive = dict(tool='geometry_get', arguments=passive_args, journal=passive)
    x.mass = dict(tool='measurement_get_mass', arguments=mass_args, journal=measured)
    def full():
        x.full_calls += 1
        a = m.adapter
        return dict(artificial_parts=[dict(metadata=deepcopy(model.state),
            bodies=[dict(pid=b.persistent_id.hex(), kind=b.body_type,
                faces=[f.persistent_id.hex() for f in b.faces], edges=[e.persistent_id.hex() for e in b.edges])
                for b in a.objects[model.identity]]) for model in a.models],
            selection=[(pid.hex(), mark) for pid, mark in a.selection], guard_history=deepcopy(m.events))
    def activity():
        return dict(connection_epoch='epoch', domain_dispatch_count=x.dispatches,
            mass_calculation_count=sum(isinstance(event, tuple) and event[0] == 'calculate' for event in m.events))
    x.full, x.activity = full, activity
    return x


def run(x, **overrides):
    args = dict(passive_receipt=x.passive, mass_receipt=x.mass, capture_full=x.full, capture_activity=x.activity)
    args.update(overrides)
    return asyncio.run(replay_case(x.reader, **args))


def test_exact_passive_and_guarded_mass_replay_no_second_actual_domain_calculation(world):
    x = world; events = deepcopy(x.m.events)
    result = run(x)
    assert x.dispatches == 2 and x.m.events == events and x.full_calls == 2
    assert result['before_journal'] == result['after_journal'] and len(result['rows']) == 2
    assert result['rows'][0]['journal'] == x.passive['journal']
    assert result['rows'][1]['journal'] == x.mass['journal']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False


@pytest.mark.parametrize('fault', ['wrong_request', 'changed_row', 'other_part', 'wrong_tool', 'wrong_epoch',
                                 'missing_activity', 'second_dispatch', 'second_calculation', 'session', 'journal'])
def test_replay_scope_counters_whole_journal_and_preservation_cannot_be_fabricated(world, fault):
    x = world
    if fault == 'wrong_request': x.passive['arguments']['request_id'] = 'new_request'
    elif fault == 'changed_row': x.passive['journal']['result']['object']['body_type'] = 'surface'
    elif fault == 'other_part': x.passive['arguments']['document_id'] = 'other'
    elif fault == 'wrong_tool': x.passive['tool'] = 'feature_get'
    elif fault == 'wrong_epoch':
        original = x.activity
        x.activity = lambda: dict(original(), connection_epoch='other')
    elif fault == 'missing_activity': x.activity = lambda: {}
    elif fault == 'second_dispatch': x.replay_hook = lambda: setattr(x, 'dispatches', x.dispatches+1)
    elif fault == 'second_calculation': x.replay_hook = lambda: x.m.events.append(('calculate', 1))
    elif fault == 'session':
        original = x.full
        def full():
            value = original()
            if x.full_calls == 2: value['selection'] = [('other', 0)]
            return value
        x.full = full
    else:
        def extra(): x.m.store.create('unrelated', 'unrelated', {}, {}, mutates=False)
        x.replay_hook = extra
    with pytest.raises(ValueError): run(x)
