"""Artificial nine-instance geometry; genuine aggregate catalog/SQLite/reader."""
import asyncio
from copy import deepcopy
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.component_aggregate_distance import ComponentAggregateDistanceCatalog
from solidworks_mcp.server_v2 import response
from test_b3_component_membership import world, transform

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_aggregate_distance as helper
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def aggregate_world(world):
    x = world; a = x.a; original = x.originals
    nested = original['nested']; nested.info['referenced_configuration'] = 'Вариант'
    nested.bodies = [nested.bodies[0], nested.bodies[-1]]
    def add(role, template, origin, parent=None):
        native = NS(identity=object(), persistent_id=role.encode(), parent=parent,
            model_identity=template.model_identity, cfg=template.info['referenced_configuration'], bodies=[])
        native.info = deepcopy(template.info)
        native.info['component_path'] = ('Контрольная повторная подсборка-2' if parent is None else
            parent.info['component_path']+'/Контрольный '+role)
        native.info['transform'] = transform([origin, 0., 0.])
        native.info['hidden'] = role == 'a_cylinder'
        if native.info['referenced_document_type'] == 'part':
            native.bodies = [a.body(surface=i == 1) for i in range(2 if 'part' in role else 1)]
        native.raw_total_transform = [1., 0., 0., 0., 1., 0., 0., 0., 1., origin*.001, 0., 0., 1., 0., 0., 0.]
        a.registry[native.persistent_id] = native; a.instances.append(native)
        x.originals[role] = native
        return native
    sub_a = original['parent']; sub_b = add('sub_b', sub_a, 250.)
    a_cylinder = add('a_cylinder', original['cylinder'], 190., sub_a)
    b_part = add('b_part', nested, 280., sub_b)
    b_cylinder = add('b_cylinder', original['cylinder'], 340., sub_b)
    roles = dict(main=original['main'], sub_a=sub_a, sub_b=sub_b, a_part=nested,
        a_cylinder=a_cylinder, b_part=b_part, b_cylinder=b_cylinder)
    x.originals.update(roles)
    catalog = ComponentAggregateDistanceCatalog(x.docs); x.aggregate_catalog = catalog
    listed = catalog.list(**x.context)['items']; state = catalog._state(x.entry)
    ids = {role: next(row['component_id'] for row in listed
                     if state['refs'][row['component_id']].native_identity == native.identity) for role, native in roles.items()}
    x.ids.update(ids); x.aggregate_ids = ids
    body_items = {}
    for role, native in roles.items():
        if native.info['referenced_document_type'] == 'assembly': continue
        body_items[role] = {state['bodies'][row['body_id']].native_identity: row
            for row in catalog.bodies(**x.context, component_id=ids[role])['items']}
        for index, body in enumerate(native.bodies):
            body.shape = 'surface' if body.body_type == 'surface' else 'cylinder' if 'cylinder' in role else 'box'
            body.hidden = role == 'main' and index == 1
            body.offset_x = 40.*index if role == 'main' and body.shape == 'box' else 80. if body.shape == 'surface' else 0.
    a.mass_body_signature = lambda body: tuple(getattr(body, 'moments', [1.]*12))
    x.solver_receipts = []; x.scope_calls = 0; x.witness_calls = 0; x.pair_calls = 0
    x.result_corrupt = x.scope_corrupt = x.pair_corrupt = x.witness_corrupt = None
    x.unknown = False; x.during = None; x.current_scope = None
    def solve(model, first, second):
        if x.during: x.during(first, second)
        def extent(native):
            limits = []
            for body in native.bodies:
                if body.shape == 'surface': continue
                origin = native.info['transform']['origin_mm'][0]
                low = origin+(-6. if body.shape == 'cylinder' else body.offset_x)
                high = origin+(6. if body.shape == 'cylinder' else body.offset_x+20.)
                limits.append((low, high))
            return min(v[0] for v in limits), max(v[1] for v in limits)
        first_extent, second_extent = extent(first), extent(second)
        assert first_extent[1] < second_extent[0]
        points = [[first_extent[1], 5., 0.], [second_extent[0], 5., 0.]]
        first_role, second_role = [next(role for role, native in roles.items() if native is target) for target in (first, second)]
        current = x.current_scope['components']
        x.solver_receipts.append(dict(component_a_id=ids[first_role], component_b_id=ids[second_role],
            native_a_identity=current[first_role]['native_identity'], native_b_identity=current[second_role]['native_identity'],
            native_a_pid=first.persistent_id.hex(), native_b_pid=second.persistent_id.hex(),
            distance_mm=math.dist(*points), closest_points_assembly_mm=deepcopy(points),
            native_receipt=dict(artificial_current_full_solid_extents=[first_extent, second_extent],
                                original_native_pids=[first.persistent_id.hex(), second.persistent_id.hex()])))
        root_m = [[value*.001 for value in point] for point in points]
        return math.dist(*root_m), *root_m
    a.component_distance = solve
    original_call = x.client.call_tool
    async def call(tool, args):
        if tool != 'measurement_get_component_aggregate_distance': return await original_call(tool, args)
        x.calls.append((tool, deepcopy(args))); x.solver_receipts = []
        spec = SPECS[tool]; payload = spec.payload(args)
        def measure():
            if x.unknown: raise RuntimeError('Artificial native receipt unavailable')
            value = catalog.measure_aggregate(**payload['arguments'])
            if x.result_corrupt: x.result_corrupt(value)
            return value
        job = x.runner.submit(args['request_id'], spec.operation, payload['arguments'], measure,
            context=payload['context'], mutates=False)
        return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
            context=job['payload']['context'], data=job['result'], error=job['error']).model_dump(mode='json'))
    x.client.call_tool = call
    def scope(ctx, left, right):
        x.scope_calls += 1; components = {}
        for role, native in roles.items():
            item = catalog.get(**ctx, component_id=ids[role])['component']
            receipt = x.instance_capture(ctx, item)
            receipt['info'] = receipt.pop('component_info'); receipt['component_id'] = ids[role]
            receipt['parent_component_id'] = item['parent_component_id']
            receipt['solid_bodies'], receipt['surface_bodies'] = [], []
            for body in a.component_bodies(native):
                row = body_items[role][body.identity]; observed = x.reference_capture(ctx, item, row)
                entry = dict(component_id=ids[role], body_id=row['body_id'], native_identity=observed['native_identity'],
                    persistent_id=observed['persistent_id'], hidden=body.hidden,
                    native_receipt=dict(artificial_current_geometry=dict(shape=body.shape, offset_x=body.offset_x),
                                        original_membership=observed['native_receipt']))
                receipt['solid_bodies' if body.body_type == 'solid' else 'surface_bodies'].append(entry)
            components[role] = receipt
        # Derive current descendants from actual retained native parents, not
        # the fixed expected result or IDs. A missing/extra leaf is observable.
        def leaves(target):
            native = next(native for role, native in roles.items() if ids[role] == target)
            children = [child for child in a.instances if child.parent is native]
            members = children if native.info['referenced_document_type'] == 'assembly' else [native]
            return [next(ids[role] for role, candidate in roles.items() if candidate is member) for member in members]
        value = dict(context=deepcopy(ctx), components=components, leaf_component_ids=[leaves(left), leaves(right)])
        # Fixed parent traversal order is semantically normalized by the producer.
        value['leaf_component_ids'] = [[cid for role, cid in ids.items() if cid in group] for group in value['leaf_component_ids']]
        if x.scope_corrupt: x.scope_corrupt(value, x.scope_calls)
        x.current_scope = deepcopy(value)
        return value
    x.scope_capture = scope
    def pairs(ctx, scope, result):
        x.pair_calls += 1
        value = deepcopy(x.solver_receipts)
        if x.pair_corrupt: x.pair_corrupt(value, x.pair_calls)
        return value
    x.pair_capture = pairs
    def witness(component, native, body, local):
        if body.shape == 'cylinder':
            assert math.isclose(math.hypot(local[0], local[2]), 6., abs_tol=1e-9) and 0. <= local[1] <= 30.
        else:
            assert body.offset_x <= local[0] <= body.offset_x+20. and 0. <= local[1] <= 10. and 0. <= local[2] <= 5.
            assert local[0] in (body.offset_x, body.offset_x+20.) or local[2] in (0., 5.)
        observed = next(row for row in component['solid_bodies'] if row['persistent_id'] == body.persistent_id.hex())
        face = body.faces[0]
        assert a.resolve_persistent_id(a.models[0], face.persistent_id, 'face') is face
        assert a.owner_body(face, 'face') is body and face in a.topology(body, 'face')
        t = native.info['transform']; root = [t['origin_mm'][i]+sum(local[j]*t['axes_in_assembly'][j][i] for j in range(3)) for i in range(3)]
        return dict(component_id=component['component_id'], body_id=observed['body_id'],
            body_native_identity=observed['native_identity'], body_persistent_id=observed['persistent_id'],
            face_native_identity=1000+len(face.persistent_id), face_persistent_id=face.persistent_id.hex(),
            local_point_mm=local, assembly_point_mm=root,
            native_receipt=dict(artificial_current_boundary=dict(shape=body.shape, local_point=local),
                                face_parent_pid=body.persistent_id.hex()))
    def witnesses(ctx, scope, result):
        x.witness_calls += 1
        part_case = result['component_a']['component_id'] == ids['main']
        winners = [('main', 1, [60., 5., 0.]), ('a_part', 0, [0., 5., 0.])] if part_case else [
            ('a_cylinder', 0, [6., 5., 0.]), ('b_part', 0, [0., 5., 0.])]
        value = [witness(scope['components'][role], roles[role], roles[role].bodies[index], local) for role, index, local in winners]
        if x.witness_corrupt: x.witness_corrupt(value, x.witness_calls)
        return value
    x.witness_capture = witnesses
    return x


def run(x, **overrides):
    args = dict(context=x.context, instance_ids=x.aggregate_ids, capture_full=x.full,
        capture_scope=x.scope_capture, capture_pairs=x.pair_capture, capture_witnesses=x.witness_capture)
    args.update(overrides)
    return asyncio.run(helper.aggregate_distance_case(x.reader, **args))


def test_two_full_aggregate_reads_all_leaf_pairs_and_both_explicit_frame_witnesses(aggregate_world):
    x = aggregate_world; result = run(x)
    assert x.full_calls == 2 and x.scope_calls == 4 and x.pair_calls == x.witness_calls == 2
    assert len(result['rows']) == len(x.store.list()['items']) == 2
    assert [len(case['native_pairs']) for case in result['cases']] == [2, 4]
    assert [row['journal']['result']['distance_mm'] for row in result['rows']] == pytest.approx([70., 84.])
    framed = result['rows'][1]['journal']['result']
    assert framed['closest_points_mm'] == [[-5., -146., -20.], [-5., -230., -20.]]
    assert result['before'] == result['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert x.retained == []
    assert all(job['payload']['mutates'] is False and 'mutation' not in job for job in x.store.list()['items'])


@pytest.mark.parametrize('fault', ['context', 'leaf_count', 'solid_count', 'bool_count', 'pairs', 'native_pairs',
    'shared', 'leaf_ids', 'nearest', 'target', 'surface', 'method', 'frame', 'translated_frame', 'metric', 'classifier'])
def test_actual_sql_success_does_not_substitute_for_full_scope_metric_and_independent_witnesses(aggregate_world, fault):
    x = aggregate_world
    def corrupt(value):
        if fault == 'context': value['observation_revision'] = 'stale'
        elif fault == 'leaf_count': value['leaf_component_counts'] = [1, 1]
        elif fault == 'solid_count': value['solid_body_counts'] = [1, 1]
        elif fault == 'bool_count': value['solid_leaf_component_counts'][0] = True
        elif fault == 'pairs': value['evaluated_pair_count'] = 1
        elif fault == 'native_pairs': value['native_pair_count'] = 1
        elif fault == 'shared': value['shared_instance_pair_count'] = 1
        elif fault == 'leaf_ids': value['leaf_component_ids'][1][0] = 'foreign'
        elif fault == 'nearest': value['nearest_component_b']['component_id'] = x.ids['cylinder']
        elif fault == 'target': value['component_a']['component_id'] = x.ids['variant']
        elif fault == 'surface': value['includes_surface_bodies'] = True
        elif fault == 'method': value['method'] = 'partial'
        elif fault == 'frame': value['frame']['origin_mm'][0] += 1.
        elif fault == 'translated_frame':
            for point in value['closest_points_assembly_mm']: point[0] += 1.
        elif fault == 'metric': value['distance_mm'] += 1.
        else: value['intersection_classification'] = 'safe'
    x.result_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['missing_leaf', 'native_pid', 'canonical', 'model', 'cfg', 'transform',
    'hidden', 'missing_body', 'missing_surface', 'body_owner', 'scope_changed', 'between_reads'])
def test_current_original_native_hierarchy_body_census_config_transform_or_hidden_leaf_required(aggregate_world, fault):
    x = aggregate_world
    def corrupt(value, number):
        hidden = value['components']['a_cylinder']
        if fault == 'missing_leaf': value['leaf_component_ids'][1].pop()
        elif fault == 'native_pid': hidden['persistent_id'] = 'AA'
        elif fault == 'canonical': hidden['native_identity'] = value['components']['a_part']['native_identity']
        elif fault == 'model': value['components']['b_cylinder']['model_identity'] += 99
        elif fault == 'cfg': value['components']['a_part']['configuration_identity'] += 99
        elif fault == 'transform': hidden['total_transform'][9] += .001
        elif fault == 'hidden': hidden['info']['hidden'] = False
        elif fault == 'missing_body': hidden['solid_bodies'] = []
        elif fault == 'missing_surface': value['components']['b_part']['surface_bodies'] = []
        elif fault == 'body_owner': hidden['solid_bodies'][0]['component_id'] = x.ids['main']
        elif fault == 'scope_changed' and number == 2: hidden['native_receipt']['changed'] = True
        elif fault == 'between_reads' and number == 3: hidden['native_receipt']['changed'] = True
    x.scope_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'foreign', 'pid', 'canonical', 'wrong_metric',
    'winning_points', 'nonwinning_lower', 'nonwinning_nonfinite', 'early_stop'])
def test_actual_all_pair_native_receipts_cannot_be_replaced_by_counts_or_winner_only(aggregate_world, fault):
    x = aggregate_world
    def corrupt(value, number):
        if fault == 'missing': value.pop()
        elif fault == 'duplicate': value[-1] = deepcopy(value[0])
        elif fault == 'foreign': value[-1]['component_b_id'] = 'foreign'
        elif fault == 'pid': value[0]['native_a_pid'] = '00'
        elif fault == 'canonical': value[0]['native_a_identity'] += 99
        elif fault == 'wrong_metric': value[0]['distance_mm'] += 1.
        elif fault == 'winning_points':
            for point in value[0]['closest_points_assembly_mm']: point[0] += 1.
        elif fault == 'nonwinning_lower':
            value[-1]['distance_mm'] = 0.; value[-1]['closest_points_assembly_mm'][1] = list(value[-1]['closest_points_assembly_mm'][0])
        elif fault == 'nonwinning_nonfinite': value[-1]['distance_mm'] = math.nan
        elif fault == 'early_stop': value[:] = [min(value, key=lambda pair: pair['distance_mm'])]
    x.pair_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['body', 'pid', 'foreign_surface', 'local_root', 'face', 'translated'])
def test_original_winning_solid_body_face_and_actual_local_root_boundary_receipts_required(aggregate_world, fault):
    x = aggregate_world
    def corrupt(value, number):
        if fault == 'body': value[0]['body_native_identity'] += 99
        elif fault == 'pid': value[0]['body_persistent_id'] = '00'
        elif fault == 'foreign_surface': value[0]['body_id'] = 'surface'
        elif fault == 'local_root': value[0]['local_point_mm'][0] += 1.
        elif fault == 'face': value[0]['face_native_identity'] = False
        elif fault == 'translated':
            value[0]['local_point_mm'][0] += 1.; value[0]['assembly_point_mm'][0] += 1.
    x.witness_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['unknown', 'nonwinning_moments', 'nonwinning_surface', 'transform'])
def test_real_catalog_or_runner_unconfirmed_nonwinning_state_stops_without_after_read(aggregate_world, fault):
    x = aggregate_world
    if fault == 'unknown': x.unknown = True
    else:
        once = []
        def during(first, second):
            if once: return
            once.append(True)
            if fault == 'nonwinning_moments': x.originals['a_cylinder'].bodies[0].moments = [2.]*12
            elif fault == 'nonwinning_surface': x.originals['a_part'].bodies.pop()
            else: x.originals['a_cylinder'].info['transform']['origin_mm'][0] += 1.
        x.during = during
    with pytest.raises((ValueError, RuntimeError)): run(x)
    assert x.full_calls == 1 and x.retained


def test_full_current_nine_instance_session_change_after_all_pairs_is_rejected(aggregate_world):
    x = aggregate_world; original = x.full
    def full():
        value = original()
        if x.full_calls == 2: value['artificial_native_full_session']['models'][0]['metadata']['active_configuration'] = 'Вариант'
        return value
    with pytest.raises(ValueError): run(x, capture_full=full)
    assert x.witness_calls == 2


@pytest.mark.parametrize('fault', ['duplicate', 'missing', 'missing_scope', 'missing_pairs', 'missing_witness', 'full_unknown'])
def test_original_explicit_ids_full_scope_and_all_native_producers_required_before_dispatch(aggregate_world, fault):
    x = aggregate_world; overrides = {}
    if fault == 'duplicate': overrides['instance_ids'] = dict(x.aggregate_ids, sub_b=x.aggregate_ids['sub_a'])
    elif fault == 'missing': overrides['instance_ids'] = dict(main=x.ids['main'])
    elif fault == 'missing_scope': overrides['capture_scope'] = None
    elif fault == 'missing_pairs': overrides['capture_pairs'] = None
    elif fault == 'missing_witness': overrides['capture_witnesses'] = None
    else: overrides['capture_full'] = lambda: (_ for _ in ()).throw(ValueError('Whole native capture unavailable'))
    with pytest.raises(ValueError): run(x, **overrides)
    assert x.calls == []
