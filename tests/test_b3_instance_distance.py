"""Artificial original BREP/witness handles; actual distance catalog/SQL/reader."""
import asyncio
from copy import deepcopy
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.component_distance import ComponentDistanceCatalog
from solidworks_mcp.server_v2 import response
from test_b3_component_membership import world

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_instance_distance as helper
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def distance_world(world):
    x = world; a = x.a
    # The unchanged native fixture inserts the nested child in Вариант.
    nested = x.originals['nested']; nested.info['referenced_configuration'] = 'Вариант'
    nested.bodies = [nested.bodies[0], nested.bodies[-1]]
    catalog = ComponentDistanceCatalog(x.docs)
    x.distance_catalog = catalog; x.solvers = 0; x.scope_calls = 0; x.witness_calls = 0
    x.scope_corrupt = None; x.witness_corrupt = None; x.during = None
    x.distance_corrupt = None
    body_rows = {}
    for role in ('main', 'variant', 'nested'):
        values = catalog.bodies(**x.context, component_id=x.ids[role])['items']
        state = catalog._state(x.entry)
        body_rows[role] = {ref.native_identity: row for row in values for ref in [state['bodies'][row['body_id']]]}
        for index, body in enumerate(x.originals[role].bodies):
            offset = 80. if body.body_type == 'surface' else 40.*index
            body.native_bounds = ([offset, 0., 0.], [offset+(15. if body.body_type == 'surface' else 20.), 10.,
                                  0. if body.body_type == 'surface' else 5.])
            body.hidden = role == 'main' and index == 1
    a.mass_body_signature = lambda body: tuple([1.]*12)
    def solve(model, first, second):
        x.solvers += 1
        assert first is x.originals['main'] and second in (x.originals['variant'], x.originals['nested'])
        if x.during: x.during()
        if second is x.originals['variant']: return .015, [.045, .01, .005], [.045, .01, .020]
        return .070, [.060, .005, .005], [.130, .005, .005]
    a.component_distance = solve
    original_call = x.client.call_tool
    async def call(tool, args):
        if tool != 'measurement_get_component_distance': return await original_call(tool, args)
        x.calls.append((tool, deepcopy(args)))
        spec = SPECS[tool]; payload = spec.payload(args)
        def measure():
            if x.unknown: raise RuntimeError('Artificial unknown native return')
            value = catalog.measure(**payload['arguments'])
            if x.distance_corrupt: x.distance_corrupt(value)
            return value
        job = x.runner.submit(args['request_id'], spec.operation, payload['arguments'], measure,
                              context=payload['context'], mutates=False)
        return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
            context=job['payload']['context'], data=job['result'], error=job['error']).model_dump(mode='json'))
    x.client.call_tool = call
    def scope(ctx, left, right):
        x.scope_calls += 1
        assert ctx == x.context and left == x.ids['main']
        roles = ['main', next(role for role in ('variant', 'nested') if x.ids[role] == right)]
        components = []
        for role in roles:
            item = catalog.get(**ctx, component_id=x.ids[role])['component']
            receipt = x.instance_capture(ctx, item)
            info = receipt.pop('component_info')
            receipt['info'] = info; receipt['component_id'] = x.ids[role]
            receipt['parent_component_id'] = item['parent_component_id']
            receipt['solid_bodies'], receipt['surface_bodies'] = [], []
            for body in a.component_bodies(x.originals[role]):
                row = body_rows[role][body.identity]
                native = x.reference_capture(ctx, item, row)
                body_receipt = dict(body_id=row['body_id'], component_id=x.ids[role],
                    native_identity=native['native_identity'], persistent_id=native['persistent_id'], hidden=body.hidden,
                    native_receipt=dict(artificial_native_bounds=deepcopy(body.native_bounds),
                                        native_membership=native['native_receipt']))
                receipt['solid_bodies' if body.body_type == 'solid' else 'surface_bodies'].append(body_receipt)
            components.append(receipt)
        value = dict(context=deepcopy(ctx), component_ids=[left, right], components=components)
        if x.scope_corrupt: x.scope_corrupt(value, x.scope_calls)
        return value
    x.scope_capture = scope
    def point(component, body, local):
        low, high = body.native_bounds
        assert all(lo-1e-9 <= p <= hi+1e-9 for p, lo, hi in zip(local, low, high))
        assert any(math.isclose(p, edge, abs_tol=1e-9) for p, lo, hi in zip(local, low, high) for edge in (lo, hi))
        matched = next(row for row in component['solid_bodies']+component['surface_bodies']
                       if row['persistent_id'] == body.persistent_id.hex())
        face = body.faces[0]
        # Real catalog PID/owner-current checks on the artificial face handles.
        assert a.resolve_persistent_id(a.models[0], face.persistent_id, 'face') is face
        assert a.owner_body(face, 'face') is body and face in a.topology(body, 'face')
        transform = component['info']['transform']
        root = [transform['origin_mm'][i]+sum(local[j]*transform['axes_in_assembly'][j][i] for j in range(3)) for i in range(3)]
        return dict(component_id=component['component_id'], body_id=matched['body_id'],
            body_native_identity=matched['native_identity'], body_persistent_id=matched['persistent_id'],
            face_native_identity=1000+len(face.persistent_id), face_persistent_id=face.persistent_id.hex(),
            local_point_mm=list(local), assembly_point_mm=root,
            native_receipt=dict(artificial_current_trimmed_boundary=dict(bounds=[low, high], point=list(local)),
                                face_parent_pid=body.persistent_id.hex()))
    def witnesses(ctx, pair, result):
        x.witness_calls += 1
        assert ctx == x.context
        first, second = pair['components']; main = x.originals['main']
        nested_case = second['component_id'] == x.ids['nested']
        other = x.originals['nested' if nested_case else 'variant']
        points = ([60., 5., 5.], [0., 5., 5.]) if nested_case else ([45., 10., 5.], [0., 5., 0.])
        value = dict(witnesses=[point(first, main.bodies[1], points[0]), point(second, other.bodies[0], points[1])])
        if nested_case:
            # Surface x95 to nested original solid x130 is35mm, less than70.
            value['closer_surface'] = dict(distance_mm=35., witnesses=[
                point(first, main.bodies[-1], [95., 5., 0.]), point(second, other.bodies[0], [0., 5., 0.])])
        if x.witness_corrupt: x.witness_corrupt(value, x.witness_calls)
        return value
    x.witness_capture = witnesses
    return x


def run(x, **overrides):
    args = dict(context=x.context, instance_ids={role: x.ids[role] for role in ('main', 'variant', 'nested')},
        capture_full=x.full, capture_pair_scope=x.scope_capture, capture_witnesses=x.witness_capture)
    args.update(overrides)
    return asyncio.run(helper.instance_distance_case(x.reader, **args))


def test_two_actual_durable_distance_reads_original_census_and_boundary_receipts(distance_world):
    x = distance_world; result = run(x)
    assert x.solvers == 2 and x.scope_calls == 4 and x.witness_calls == x.full_calls == 2
    assert len(result['rows']) == len(x.store.list()['items']) == 2
    assert [row['journal']['result']['distance_mm'] for row in result['rows']] == [15., 70.]
    assert result['pairs'][1]['witness']['closer_surface']['distance_mm'] == 35.
    assert result['before'] == result['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert x.retained == []
    assert [tool for tool, _ in x.calls if tool != 'job_get'] == ['measurement_get_component_distance']*2
    assert all(job['payload']['mutates'] is False and 'mutation' not in job for job in x.store.list()['items'])


@pytest.mark.parametrize('fault', ['context', 'counts', 'bool_count', 'surface_included', 'hidden_excluded',
    'metric', 'points', 'translated_witness', 'frame', 'method', 'component', 'parent', 'units', 'classifier'])
def test_coherent_sql_success_cannot_replace_native_metric_scope_or_original_witness_proof(distance_world, fault):
    x = distance_world
    def corrupt(value):
        if fault == 'context': value['observation_revision'] = 'stale'
        elif fault == 'counts': value['solid_body_counts'] = [1, 1]
        elif fault == 'bool_count': value['solid_body_counts'] = [2, True]
        elif fault == 'surface_included': value['includes_surface_bodies'] = True
        elif fault == 'hidden_excluded': value['includes_hidden_bodies'] = False
        elif fault == 'metric': value['distance_mm'] = 35.
        elif fault == 'points': value['closest_points_mm'][1][0] += 1.
        elif fault == 'translated_witness':
            for point in value['closest_points_mm']: point[0] += 1.
        elif fault == 'frame': value['coordinate_frame'] = 'component_model'
        elif fault == 'method': value['method'] = 'sampled'
        elif fault == 'component': value['component_b']['component_id'] = x.ids['cylinder']
        elif fault == 'parent': value['component_a']['parent_component_id'] = x.ids['parent']
        elif fault == 'units': value['length_unit'] = 'm'
        elif fault == 'classifier': value['intersection_classification'] = 'safe_clearance'
    x.distance_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.solvers == 1 and x.full_calls == 1


@pytest.mark.parametrize('fault', ['pid', 'model', 'cfg', 'transform', 'short_transform', 'rotation', 'hidden',
    'missing_solid', 'missing_surface', 'duplicate_body', 'foreign_body', 'pair_changed', 'main_between_pairs'])
def test_actual_current_pair_scope_mismatch_incomplete_roster_or_changed_state_refuses(distance_world, fault):
    x = distance_world
    def corrupt(value, number):
        first, second = value['components']
        if fault == 'pid': second['persistent_id'] = first['persistent_id']
        elif fault == 'model': second['model_identity'] += 999
        elif fault == 'cfg': second['configuration_identity'] = first['configuration_identity']
        elif fault == 'transform': second['total_transform'][9] += .001
        elif fault == 'short_transform': second['total_transform'].pop()
        elif fault == 'rotation':
            second['info']['transform']['axes_in_assembly'] = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
            second['total_transform'][:9] = [1., 0., 0., 0., 1., 0., 0., 0., 1.]
        elif fault == 'hidden': first['solid_bodies'][1]['hidden'] = False
        elif fault == 'missing_solid': first['solid_bodies'].pop()
        elif fault == 'missing_surface': second['surface_bodies'] = []
        elif fault == 'duplicate_body': first['solid_bodies'][1] = deepcopy(first['solid_bodies'][0])
        elif fault == 'foreign_body': second['solid_bodies'][0]['component_id'] = x.ids['main']
        elif fault == 'pair_changed' and number == 2: second['native_receipt']['changed'] = True
        elif fault == 'main_between_pairs' and number == 3: first['native_receipt']['changed'] = True
    x.scope_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.solvers <= 1 and x.full_calls == 1


@pytest.mark.parametrize('fault', ['body', 'face_pid', 'face_identity', 'wrong_frame', 'different_native_point',
                                  'surface_as_solid', 'missing_closer', 'closer_metric', 'closer_solid'])
def test_original_body_face_boundary_or_excluded_closer_surface_proof_required(distance_world, fault):
    x = distance_world
    def corrupt(value, number):
        point = value['witnesses'][0]
        if fault == 'body': point['body_native_identity'] += 99
        elif fault == 'face_pid': point['face_persistent_id'] = 'unknown'
        elif fault == 'face_identity': point['face_native_identity'] = False
        elif fault == 'wrong_frame': point['assembly_point_mm'][0] += 1.
        elif fault == 'different_native_point':
            point['local_point_mm'][0] += 1.; point['assembly_point_mm'][0] += 1.
        elif fault == 'surface_as_solid': point['body_id'] = 'surface-not-solid'
        elif number == 2:
            if fault == 'missing_closer': value.pop('closer_surface')
            elif fault == 'closer_metric': value['closer_surface']['distance_mm'] = 70.
            elif fault == 'closer_solid': value['closer_surface']['witnesses'][0] = deepcopy(value['witnesses'][0])
    x.witness_corrupt = corrupt
    with pytest.raises((ValueError, KeyError)): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['unknown', 'changed_moments', 'changed_transform', 'removed_body'])
def test_real_runner_or_catalog_unconfirmed_native_outcome_stops_without_second_read(distance_world, fault):
    x = distance_world
    if fault == 'unknown': x.unknown = True
    elif fault == 'changed_moments':
        def change(): x.a.mass_body_signature = lambda body: tuple([2.]*12)
        x.during = change
    elif fault == 'changed_transform': x.during = lambda: x.originals['variant'].info['transform']['origin_mm'].__setitem__(0, 60.)
    else: x.during = lambda: x.originals['main'].bodies.pop()
    with pytest.raises((ValueError, RuntimeError)): run(x)
    assert x.full_calls == 1 and x.retained
    assert len([tool for tool, _ in x.calls if tool != 'job_get']) == 1


def test_full_current_session_change_rejects_after_both_durable_reads(distance_world):
    x = distance_world; original = x.full
    def full():
        value = original()
        if x.full_calls == 2: value['artificial_native_full_session']['models'][0]['metadata']['active_configuration'] = 'Вариант'
        return value
    with pytest.raises(ValueError): run(x, capture_full=full)
    assert x.solvers == 2 and x.full_calls == 2


@pytest.mark.parametrize('fault', ['duplicate', 'missing', 'missing_census', 'missing_witness', 'full_unknown'])
def test_no_original_ids_or_independent_producers_prevents_any_dispatch(distance_world, fault):
    x = distance_world; overrides = {}
    if fault == 'duplicate': overrides['instance_ids'] = dict(main=x.ids['main'], variant=x.ids['main'], nested=x.ids['nested'])
    elif fault == 'missing': overrides['instance_ids'] = dict(main=x.ids['main'])
    elif fault == 'missing_census': overrides['capture_pair_scope'] = None
    elif fault == 'missing_witness': overrides['capture_witnesses'] = None
    else: overrides['capture_full'] = lambda: (_ for _ in ()).throw(ValueError('Actual session unavailable'))
    with pytest.raises(ValueError): run(x, **overrides)
    assert x.calls == [] and x.solvers == 0
