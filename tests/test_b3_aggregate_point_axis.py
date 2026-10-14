"""Artificial current geometry/native arrays; real aggregate probes/SQLite."""
import asyncio
from copy import deepcopy
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.component_aggregate_probes import ComponentAggregateProbeCatalog
from solidworks_mcp.point_measurement import classify_native_rays, RAY_DIRECTIONS
from solidworks_mcp.server_v2 import response
from test_b3_aggregate_distance import aggregate_world
from test_b3_component_membership import world

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_aggregate_point_axis as helper
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def probes_world(aggregate_world):
    x = aggregate_world; a = x.a
    catalog = ComponentAggregateProbeCatalog(x.docs); x.probe_catalog = catalog
    x.raw_queries = {}; x.raw_rays = {}; x.raw_axes = {}; x.probe_kind = None
    x.result_corrupt = x.leaf_corrupt = x.point_witness_corrupt = None
    x.zero_boundary = False; x.during_probe = None; x.leaf_calls = 0
    body_rows, face_rows = {}, {}
    for role in ('a_part', 'a_cylinder'):
        native = x.originals[role]
        for body_index, body in enumerate(native.bodies):
            body.faces = []
            labels = [(i, side) for i in range(3) for side in (0, 1)] if body.shape == 'box' else [(0, 0)] if body.shape == 'surface' else [(0, 0), (1, 0), (1, 1)]
            for index, (axis, side) in enumerate(labels):
                pid = f'i12-{role}-{body_index}-face{index}'.encode()
                face = NS(identity=object(), persistent_id=pid, kind='face', body=body, axis=axis, side=side)
                a.registry[pid] = face; body.faces.append(face)
        state = catalog._state(x.entry)
        rows = catalog.bodies(**x.context, component_id=x.aggregate_ids[role])['items']
        body_rows[role] = {state['bodies'][row['body_id']].native_identity: row for row in rows}
        for body in rows:
            faces = catalog.list_topology(**x.context, component_id=x.aggregate_ids[role], body_id=body['body_id'], kind='face')['items']
            native_state = catalog._topology_state(x.entry)
            face_rows[body['body_id']] = {native_state['refs'][face['object_id']].native_identity: face for face in faces}
    def closest(face, point):
        if x.during_probe: x.during_probe('point', face.body)
        body = face.body
        if body.shape == 'box':
            limits = [.020, .010, .005]
            nearest = [max(0., min(p, high)) for p, high in zip(point, limits)]
            nearest[face.axis] = limits[face.axis] if face.side else 0.
        else:
            assert body.shape == 'cylinder'
            radius = math.hypot(point[0], point[2]); radial_scale = .006/max(radius, .006)
            if face.axis == 0:
                nearest = [.006*point[0]/radius if radius else .006, max(0., min(point[1], .030)),
                           .006*point[2]/radius if radius else 0.]
            else: nearest = [point[0]*radial_scale, .030 if face.side else 0., point[2]*radial_scale]
        raw = nearest+[0., 0.]
        x.raw_queries.setdefault(body.persistent_id, {})[face.persistent_id] = deepcopy(raw)
        return raw
    a.face_closest_point = closest
    def rays(model, body, point):
        if body.shape == 'box': raw = (0, None)
        elif math.hypot(point[0], point[2]) >= .006 or not 0. < point[1] < .030: raw = (0, None)
        else:
            values = []
            for index, direction in enumerate(RAY_DIRECTIONS):
                radial = .006/math.hypot(direction[0], direction[2]); cap = (.030-point[1])/direction[1]
                distance = min(radial, cap)
                values += [0., float(index), 33., *(p+distance*d for p, d in zip(point, direction)), 1., 0., 0.]
            raw = (3, values)
        x.raw_rays[body.persistent_id] = deepcopy(raw)
        return raw
    a.body_point_rays = rays
    def extreme(body, direction):
        if body.shape == 'box': return [.020 if direction[0] >= 0 else 0., .010 if direction[1] >= 0 else 0., .005 if direction[2] >= 0 else 0.]
        assert body.shape == 'cylinder'
        length = math.hypot(direction[0], direction[2])
        return [.006*direction[0]/length if length else 0., .030 if direction[1] >= 0 else 0., .006*direction[2]/length if length else 0.]
    a.measurement_extreme_point = extreme
    def axis(model, component, ends, direction):
        body = component.bodies[0]
        if x.during_probe: x.during_probe('axis', body)
        assert direction == [0., 1., 0.]
        root_x = ends[0][0]; base_x = component.info['transform']['origin_mm'][0]*.001
        if body.shape == 'box': nearest_x = min(base_x+.020, max(base_x, root_x))
        else: nearest_x = min(base_x+.006, max(base_x-.006, root_x))
        y = 0. if x.zero_boundary and math.isclose(root_x, .190) and body.shape == 'cylinder' else .005 if body.shape == 'box' else .015
        raw = (abs(root_x-nearest_x), [nearest_x, y, 0.], [root_x, y, 0.])
        x.raw_axes[body.persistent_id] = deepcopy(raw)
        return raw
    a.component_axis_distance = axis
    base_scope = x.scope_capture
    def scope(ctx, left, right):
        value = base_scope(ctx, left, right)
        for role in ('a_part', 'a_cylinder'):
            native = x.originals[role]; component = value['components'][role]
            item = catalog.get(**ctx, component_id=x.aggregate_ids[role])['component']
            for body in native.bodies:
                row = body_rows[role][body.identity]
                held = next(b for b in component['solid_bodies']+component['surface_bodies'] if b['persistent_id'] == body.persistent_id.hex())
                held['faces'] = []
                for face in sorted(a.topology(body, 'face'), key=lambda face: face.persistent_id):
                    frow = face_rows[row['body_id']][face.identity]; proof = x.reference_capture(ctx, item, frow)
                    held['faces'].append(dict(object_id=frow['object_id'], component_id=component['component_id'], body_id=row['body_id'],
                        native_identity=proof['native_identity'], persistent_id=proof['persistent_id'],
                        native_receipt=dict(artificial_face=(face.axis, face.side), parent_pid=body.persistent_id.hex())))
        return value
    x.scope_capture = scope
    original_call = x.client.call_tool
    async def call(tool, args):
        if tool not in ('measurement_get_component_aggregate_point_distance', 'measurement_get_component_aggregate_axis_distance'):
            return await original_call(tool, args)
        x.calls.append((tool, deepcopy(args))); x.raw_queries = {}; x.raw_rays = {}; x.raw_axes = {}
        spec = SPECS[tool]; payload = spec.payload(args)
        method = catalog.measure_aggregate_point if 'point' in tool else catalog.measure_aggregate_axis
        def measure():
            if x.unknown: raise RuntimeError('Artificial unresolved native observation')
            value = method(**payload['arguments'])
            if x.result_corrupt: x.result_corrupt(tool, value)
            return value
        job = x.runner.submit(args['request_id'], spec.operation, payload['arguments'], measure,
            context=payload['context'], mutates=False)
        return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
            context=job['payload']['context'], data=job['result'], error=job['error']).model_dump(mode='json'))
    x.client.call_tool = call
    def leaf(ctx, scope, result, label):
        x.leaf_calls += 1; values = []
        for role in ('a_part', 'a_cylinder'):
            component = scope['components'][role]; body = component['solid_bodies'][0]; raw_body = a.registry[bytes.fromhex(body['persistent_id'])]
            value = dict(component_id=component['component_id'], native_identity=component['native_identity'], persistent_id=component['persistent_id'],
                body_id=body['body_id'], body_native_identity=body['native_identity'], body_persistent_id=body['persistent_id'],
                native_receipt=dict(artificial_original_getters=True, shape=raw_body.shape))
            if label.startswith('point'):
                value['face_readbacks'] = [dict(persistent_id=face['persistent_id'], native_identity=face['native_identity'],
                    closest_xyzuv_m=x.raw_queries[raw_body.persistent_id][bytes.fromhex(face['persistent_id'])]) for face in body['faces']]
                value['ray_observation'] = x.raw_rays[raw_body.persistent_id]
            else:
                value['supports_m'] = [extreme(raw_body, [0., -1., 0.]), extreme(raw_body, [0., 1., 0.])]
                value['native_result'] = x.raw_axes[raw_body.persistent_id]
            values.append(value)
        if x.leaf_corrupt: x.leaf_corrupt(values, label)
        return values
    x.leaf_capture = leaf
    def witness(ctx, scope, result, label):
        component = scope['components']['a_cylinder']; body = component['solid_bodies'][0]
        root = result['nearest_assembly_mm'] if label.startswith('point') else result['closest_points_assembly_mm'][0]
        local = [root[0]-190., root[1], root[2]]; raw_body = a.registry[bytes.fromhex(body['persistent_id'])]
        boundary = math.isclose(math.hypot(local[0], local[2]), 6., abs_tol=1e-9) or local[1] in (0., 30.)
        if boundary:
            if label.startswith('point'): face = next(face for face in body['faces'] if face['object_id'] == result['nearest_face_id'])
            else: face = body['faces'][0] if local[1] not in (0., 30.) else body['faces'][1]
            location = 'boundary'
        else:
            face = None; p = [x*.001 for x in local]; location = classify_native_rays(rays(a.models[0], raw_body, p), p)
        value = dict(component_id=component['component_id'], body_id=body['body_id'], body_native_identity=body['native_identity'],
            body_persistent_id=body['persistent_id'], local_point_mm=local, assembly_point_mm=list(root), point_location=location,
            face_id=None if face is None else face['object_id'], face_native_identity=None if face is None else face['native_identity'],
            face_persistent_id=None if face is None else face['persistent_id'],
            query_point_location=result.get('point_location'), native_receipt=dict(artificial_current_cylinder_point=local, location=location))
        if x.point_witness_corrupt: x.point_witness_corrupt(value, label)
        return value
    x.probe_witness = witness
    x.base_scope = base_scope
    return x


def run(x, **overrides):
    args = dict(context=x.context, instance_ids=x.aggregate_ids, capture_full=x.full, capture_scope=x.scope_capture,
        capture_leaf_probes=x.leaf_capture, capture_witness=x.probe_witness)
    args.update(overrides)
    return asyncio.run(helper.aggregate_point_axis_case(x.reader, **args))


@pytest.mark.parametrize('zero_boundary', [False, True])
def test_four_actual_aggregate_probes_complete_nine_faces_all_leaves_and_framed_witnesses(probes_world, zero_boundary):
    x = probes_world; x.zero_boundary = zero_boundary; result = run(x)
    assert len(result['rows']) == len(x.store.list()['items']) == 4 and x.leaf_calls == 4 and x.full_calls == 2
    assert [row['journal']['result']['distance_mm'] for row in result['rows']] == pytest.approx([3., 6., 2., 0.])
    assert [row['arguments']['frame'] for row in result['rows']] == [helper.FRAME, None, helper.FRAME, None]
    assert [len(probe['leaf_probes']) for probe in result['probes']] == [2]*4
    assert result['probes'][-1]['witness']['point_location'] == ('boundary' if zero_boundary else 'inside')
    assert result['before'] == result['after'] and x.retained == []
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False


@pytest.mark.parametrize('fault', ['counts', 'bool_count', 'leaf_ids', 'face_count', 'nearest', 'surface', 'metric',
    'location', 'body_locations', 'frame', 'translated_frame', 'method', 'nearest_face', 'axis_semantics', 'off_axis'])
def test_coherent_sql_success_cannot_replace_current_complete_census_location_and_original_refs(probes_world, fault):
    x = probes_world
    def corrupt(tool, value):
        point = 'point' in tool
        if fault == 'counts': value['evaluated_leaf_count'] = 1
        elif fault == 'bool_count': value['solid_body_count'] = True
        elif fault == 'leaf_ids': value['leaf_component_ids'][0] = 'foreign'
        elif fault == 'face_count' and point: value['face_count'] = 8
        elif fault == 'nearest': value['nearest_component']['component_id'] = x.ids['cylinder']
        elif fault == 'surface': value['includes_surface_bodies'] = True
        elif fault == 'metric': value['distance_mm'] += 1.
        elif fault == 'location' and point: value['point_location'] = 'boundary'
        elif fault == 'body_locations' and point: value['body_locations'][0]['point_location'] = 'inside'
        elif fault == 'frame': value['frame']['origin_mm'][0] += 1.
        elif fault == 'translated_frame' and point:
            value['point_assembly_mm'][0] += 1.; value['nearest_assembly_mm'][0] += 1.
        elif fault == 'method': value['method'] = 'partial'
        elif fault == 'nearest_face' and point: value['nearest_face_id'] = 'foreign'
        elif fault == 'axis_semantics' and not point: value['axis_semantics'] = 'segment'
        elif fault == 'off_axis' and not point: value['closest_points_assembly_mm'][1][2] += 1.
    x.result_corrupt = corrupt
    with pytest.raises((ValueError, StopIteration, RuntimeError)): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['missing_leaf', 'duplicate_leaf', 'pid', 'body', 'missing_face', 'duplicate_face',
    'foreign_face', 'bad_xyzuv', 'ray_unknown', 'nonwinning_lower', 'axis_support', 'axis_native', 'early_zero'])
def test_actual_all_leaf_face_location_and_exact_axis_readbacks_required_even_for_nonwinner(probes_world, fault):
    x = probes_world
    def corrupt(values, label):
        if fault == 'missing_leaf': values.pop()
        elif fault == 'duplicate_leaf': values[1] = deepcopy(values[0])
        elif fault == 'pid': values[0]['persistent_id'] = '00'
        elif fault == 'body': values[0]['body_native_identity'] += 99
        elif label.startswith('point'):
            if fault == 'missing_face': values[0]['face_readbacks'].pop()
            elif fault == 'duplicate_face': values[0]['face_readbacks'][1] = deepcopy(values[0]['face_readbacks'][0])
            elif fault == 'foreign_face': values[0]['face_readbacks'][0]['persistent_id'] = '00'
            elif fault == 'bad_xyzuv': values[0]['face_readbacks'][0]['closest_xyzuv_m'] = [0., 0., 0.]
            elif fault == 'ray_unknown': values[0]['ray_observation'] = None
            elif fault == 'nonwinning_lower':
                # Metric-consistent nonwinning face tampering must change the minimum.
                local = [.069, .015, 0.]
                values[0]['face_readbacks'][0]['closest_xyzuv_m'] = local+[0., 0.]
        elif fault == 'axis_support': values[0]['supports_m'] = [[0., .020, 0.], [0., .010, 0.]]
        elif fault == 'axis_native': values[0]['native_result'] = [1., [0., 0., 0.], [0., 0., 0.]]
        elif fault == 'early_zero' and label == 'axis_through': values[:] = values[1:]
    x.leaf_corrupt = corrupt
    with pytest.raises((ValueError, RuntimeError)): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['body', 'face', 'point', 'root', 'query_location', 'inside_fake_face'])
def test_original_hidden_cylinder_body_face_and_native_local_root_witness_required(probes_world, fault):
    x = probes_world
    def corrupt(value, label):
        if fault == 'body': value['body_native_identity'] += 99
        elif fault == 'face': value['face_persistent_id'] = '00'
        elif fault == 'point': value['local_point_mm'][0] += 1.
        elif fault == 'root': value['assembly_point_mm'][0] += 1.
        elif fault == 'query_location': value['query_point_location'] = 'boundary'
        elif fault == 'inside_fake_face' and label == 'axis_through': value['face_id'] = 'invented'
    x.point_witness_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['unknown', 'nonwinning_faces', 'nonwinning_moments', 'axis_support'])
def test_actual_catalog_runner_unknown_or_closing_failure_blocks_followups(probes_world, fault):
    x = probes_world
    if fault == 'unknown': x.unknown = True
    else:
        once = []
        def during(kind, body):
            if once or (fault == 'axis_support' and kind != 'axis'): return
            once.append(True)
            if fault == 'nonwinning_faces': x.originals['a_part'].bodies[0].faces.pop()
            elif fault == 'nonwinning_moments': x.originals['a_part'].bodies[0].moments = [2.]*12
            else: x.a.measurement_extreme_point = lambda *args: [0., .040, 0.]
        x.during_probe = during
    with pytest.raises((ValueError, RuntimeError)): run(x)
    assert x.full_calls == 1 and x.retained


def test_full_current_session_change_rejected_after_four_measurements(probes_world):
    x = probes_world; original = x.full
    def full():
        value = original()
        if x.full_calls == 2: value['artificial_native_full_session']['models'][0]['metadata']['active_configuration'] = 'Вариант'
        return value
    with pytest.raises(ValueError): run(x, capture_full=full)
    assert x.leaf_calls == 4


def prepare_artificial_surface_phase(x):
    """Simulate only acknowledged external fixture setup before route starts.

No CAD setters or production mutation APIs are invoked; current fake state and
fresh real catalog refs deliberately differ from initial positive scope.
"""
    a = x.a; old_provider = a.component_info; new_cfg_identity = object()
    def provider(native):
        if native is x.originals['sub_a'] and native.info['referenced_configuration'] == 'Вариант':
            return deepcopy(native.info), (native.model_identity, new_cfg_identity)
        return old_provider(native)
    a.component_info = provider
    x.originals['sub_a'].info['referenced_configuration'] = 'Вариант'
    x.originals['a_part'].info['referenced_configuration'] = 'Основная'
    x.originals['a_part'].bodies = [x.originals['a_part'].bodies[-1]]
    x.originals['a_cylinder'].bodies = []
    a.models[0].state['update_stamp'] += 1
    current = x.docs.get(x.context['document_id'], x.context['configuration'])
    ctx = dict(x.context, expected_observation_revision=current['observation_revision'])
    x.context.update(ctx)  # Trusted owner observers bind the refreshed phase.
    rows = x.probe_catalog.list(**ctx)['items']; state = x.probe_catalog._state(x.entry)
    for role, native in x.originals.items():
        if role in x.aggregate_ids:
            x.aggregate_ids[role] = next(row['component_id'] for row in rows if state['refs'][row['component_id']].native_identity == native.identity)
            x.ids[role] = x.aggregate_ids[role]
    ids = {role: x.aggregate_ids[role] for role in ('sub_a', 'a_part', 'a_cylinder')}
    def scope(context, ids):
        value = x.base_scope(context, x.aggregate_ids['sub_a'], x.aggregate_ids['sub_b'])
        return dict(context=deepcopy(context), components={role: value['components'][role] for role in ids},
                    leaf_component_ids=value['leaf_component_ids'][0])
    return ctx, ids, scope


def test_separate_prepared_surface_phase_uses_refreshed_current_context_and_real_finite_sql_refusal(probes_world):
    x = probes_world; old_ids = deepcopy(x.aggregate_ids); old_context = deepcopy(x.context)
    ctx, ids, scope = prepare_artificial_surface_phase(x)
    assert ids['sub_a'] != old_ids['sub_a'] and ids['a_part'] != old_ids['a_part'] and ctx != old_context
    result = asyncio.run(helper.aggregate_surface_refusal_case(x.reader, context=ctx, instance_ids=ids,
        capture_full=x.full, capture_refusal_scope=scope))
    assert len(result['rows']) == 1 and result['phase'] == 'owner_prepared_surface_only_refusal'
    job = result['rows'][0]['journal']
    assert job['status'] == 'failed' and job['result'] is None and job['error']['code'] == 'component_has_no_solid_bodies'
    assert job['error']['requires_reconciliation'] is False and job['mutation'] is None
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert result['before'] == result['after'] and x.retained == [] and x.raw_queries == {}


@pytest.mark.parametrize('fault', ['initial_ids', 'solid_present', 'wrong_cfg', 'changed', 'unknown'])
def test_refusal_phase_no_stale_scope_partial_success_or_unknown_admission(probes_world, fault):
    x = probes_world; old_ids = {role: x.aggregate_ids[role] for role in ('sub_a', 'a_part', 'a_cylinder')}
    ctx, ids, original = prepare_artificial_surface_phase(x); calls = []
    def scope(context, passed_ids):
        calls.append(True); value = original(context, passed_ids)
        if fault == 'solid_present': value['components']['a_cylinder']['solid_bodies'] = [dict(artificial_incomplete=True)]
        elif fault == 'wrong_cfg': value['components']['a_part']['info']['referenced_configuration'] = 'Вариант'
        elif fault == 'changed' and len(calls) == 2: value['components']['sub_a']['native_receipt']['changed'] = True
        return value
    if fault == 'unknown': x.unknown = True
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(helper.aggregate_surface_refusal_case(x.reader, context=ctx, instance_ids=old_ids if fault == 'initial_ids' else ids,
            capture_full=x.full, capture_refusal_scope=scope))
    assert x.full_calls == 1 or fault == 'changed'
