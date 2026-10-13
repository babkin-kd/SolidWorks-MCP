"""Actual catalogs/JobRunner/SQLite with explicitly artificial native BREP APIs."""
import asyncio
from copy import deepcopy
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.component_point_distance import ComponentPointDistanceCatalog
from solidworks_mcp.component_axis_distance import ComponentAxisDistanceCatalog
from solidworks_mcp.point_measurement import classify_native_rays, RAY_DIRECTIONS
from solidworks_mcp.server_v2 import response
from test_b3_component_membership import world

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_instance_point_axis as helper
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def probes_world(world):
    x = world; a = x.a
    # Correct the unchanged setup's nested Variant profile even though I10
    # targets only the top-level variant and cylinder.
    nested = x.originals['nested']; nested.info['referenced_configuration'] = 'Вариант'
    nested.bodies = [nested.bodies[0], nested.bodies[-1]]
    x.point_catalog = ComponentPointDistanceCatalog(x.docs)
    x.axis_catalog = ComponentAxisDistanceCatalog(x.docs)
    x.probe_calls = []; x.scope_calls = 0; x.witness_calls = 0
    x.result_corrupt = None; x.scope_corrupt = None; x.witness_corrupt = None
    x.during = None; x.unknown = False; x.zero_boundary = False
    variant, cylinder = x.originals['variant'], x.originals['cylinder']
    for role, native in (('variant', variant), ('cylinder', cylinder)):
        for body_index, body in enumerate(native.bodies):
            body.shape = 'surface' if body.body_type == 'surface' else ('box' if role == 'variant' else 'cylinder')
            body.faces = []
            labels = [(axis, side) for axis in range(3) for side in (0, 1)] if body.shape == 'box' else [(0, 0)] if body.shape == 'surface' else [(0, 0), (1, 0), (1, 1)]
            for number, (axis, side) in enumerate(labels):
                pid = f'i10-{role}-{body_index}-face{number}'.encode()
                face = NS(identity=object(), persistent_id=pid, kind='face', body=body, axis=axis, side=side)
                a.registry[pid] = face; body.faces.append(face)
    a.mass_body_signature = lambda body: tuple(getattr(body, 'moments', [1.]*12))
    def closest(face, point):
        x.probe_calls.append('trimmed_face')
        if x.during: x.during('point')
        assert face.body.shape == 'box'
        limits = [.02, .01, .005]
        nearest = [max(0., min(p, high)) for p, high in zip(point, limits)]
        nearest[face.axis] = limits[face.axis] if face.side else 0.
        return nearest+[0., 0.]
    a.face_closest_point = closest
    def rays(model, body, point):
        if body.shape == 'box': return 0, None  # Fixed query lies beyond max on all axes.
        assert body.shape == 'cylinder'
        if math.hypot(point[0], point[2]) >= .006 or not 0. < point[1] < .030: return 0, None
        records = []
        for index, direction in enumerate(RAY_DIRECTIONS):
            radial = .006/math.hypot(direction[0], direction[2])
            cap = (.030-point[1])/direction[1]
            t = min(radial, cap)
            records += [0., float(index), 33., *(p+t*d for p, d in zip(point, direction)), 1., 0., 0.]
        return 3, records
    a.body_point_rays = rays
    def extreme(body, direction):
        assert body.shape == 'cylinder'
        norm = math.hypot(direction[0], direction[2])
        return [.006*direction[0]/norm if norm else 0., .030 if direction[1] >= 0 else 0.,
                .006*direction[2]/norm if norm else 0.]
    a.measurement_extreme_point = extreme
    def axis(model, component, ends, direction):
        x.probe_calls.append('axis_solver')
        assert component is cylinder and direction == [0., 1., 0.]
        assert ends[0][1] < 0. and ends[1][1] > .030
        if x.during: x.during('axis')
        if math.isclose(ends[0][0], .158): return .002, [.156, .015, 0.], [.158, .015, 0.]
        y = 0. if x.zero_boundary else .015
        return 0., [.150, y, 0.], [.150, y, 0.]
    a.component_axis_distance = axis
    # Exact current opaque bindings come from the same retained catalog state;
    # production producers must supply an independent equivalent bridge.
    bodies, faces = {}, {}
    for role in ('variant', 'cylinder'):
        body_rows = x.point_catalog.bodies(**x.context, component_id=x.ids[role])['items']
        state = x.point_catalog._state(x.entry)
        bodies[role] = {state['bodies'][row['body_id']].native_identity: row for row in body_rows}
        for row in body_rows:
            face_rows = x.point_catalog.list_topology(**x.context, component_id=x.ids[role], body_id=row['body_id'], kind='face')['items']
            topology_state = x.point_catalog._topology_state(x.entry)
            faces[row['body_id']] = {topology_state['refs'][item['object_id']].native_identity: item for item in face_rows}
    original_call = x.client.call_tool
    async def call(tool, args):
        if tool not in ('measurement_get_component_point_distance', 'measurement_get_component_axis_distance'):
            return await original_call(tool, args)
        x.calls.append((tool, deepcopy(args)))
        spec = SPECS[tool]; payload = spec.payload(args)
        method = x.point_catalog.measure_point if 'point' in tool else x.axis_catalog.measure_axis
        def measure():
            if x.unknown: raise RuntimeError('Artificial native call acknowledgement unknown')
            value = method(**payload['arguments'])
            if x.result_corrupt: x.result_corrupt(tool, value)
            return value
        job = x.runner.submit(args['request_id'], spec.operation, payload['arguments'], measure,
            context=payload['context'], mutates=False)
        return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
            context=job['payload']['context'], data=job['result'], error=job['error']).model_dump(mode='json'))
    x.client.call_tool = call
    def scope(ctx, component_id):
        x.scope_calls += 1
        role = next(role for role in ('variant', 'cylinder') if x.ids[role] == component_id)
        item = x.point_catalog.get(**ctx, component_id=component_id)['component']
        value = x.instance_capture(ctx, item)
        value['info'] = value.pop('component_info'); value['context'] = deepcopy(ctx)
        value['component_id'] = component_id; value['parent_component_id'] = item['parent_component_id']
        value['solid_bodies'], value['surface_bodies'] = [], []
        for body in a.component_bodies(x.originals[role]):
            row = bodies[role][body.identity]; native = x.reference_capture(ctx, item, row)
            current = dict(component_id=component_id, body_id=row['body_id'], native_identity=native['native_identity'],
                persistent_id=native['persistent_id'], hidden=False, native_receipt=dict(
                    artificial_current_shape=body.shape, body_membership=native['native_receipt']), faces=[])
            for face in sorted(a.topology(body, 'face'), key=lambda face: face.persistent_id):
                f = faces[row['body_id']][face.identity]
                f_native = x.reference_capture(ctx, item, f)
                current['faces'].append(dict(object_id=f['object_id'], component_id=component_id, body_id=row['body_id'],
                    native_identity=f_native['native_identity'], persistent_id=f_native['persistent_id'],
                    native_receipt=dict(artificial_current_face=(face.axis, face.side), membership=f_native['native_receipt'])))
            value['solid_bodies' if body.shape != 'surface' else 'surface_bodies'].append(current)
        if x.scope_corrupt: x.scope_corrupt(value, x.scope_calls)
        return value
    x.scope_capture = scope
    def witness(ctx, scope, result, label):
        x.witness_calls += 1
        body = scope['solid_bodies'][0]
        root = result['nearest_assembly_mm'] if label == 'point_corner' else result['closest_points_assembly_mm'][0]
        transform = scope['info']['transform']
        local = [sum(axis[k]*(root[k]-transform['origin_mm'][k]) for k in range(3)) for axis in transform['axes_in_assembly']]
        raw_body = a.registry[bytes.fromhex(body['persistent_id'])]
        if label == 'point_corner':
            location = 'boundary'
            nearest = next(face for face in body['faces'] if face['object_id'] == result['nearest_face_id'])
            raw_face = a.registry[bytes.fromhex(nearest['persistent_id'])]
            # Independent actual artificial IFace closest-point incidence.
            raw_point = closest(raw_face, [p*.001 for p in local])
            assert math.dist(raw_point[:3], [p*.001 for p in local]) < 1e-12
            query_local = [p*.001 for p in result['point_mm']]
            query_location = classify_native_rays(rays(a.models[0], raw_body, query_local), query_local)
        elif label == 'axis_gap':
            assert math.isclose(math.hypot(local[0], local[2]), 6., abs_tol=1e-9) and 0. <= local[1] <= 30.
            location = 'boundary'; nearest = body['faces'][0]; raw_point = local; query_location = None
        elif local[1] == 0.:
            location = 'boundary'; nearest = body['faces'][1]; raw_point = local; query_location = None
        else:
            local_m = [p*.001 for p in local]
            location = classify_native_rays(rays(a.models[0], raw_body, local_m), local_m)
            nearest = None; raw_point = local; query_location = None
        value = dict(component_id=scope['component_id'], body_id=body['body_id'],
            body_native_identity=body['native_identity'], body_persistent_id=body['persistent_id'],
            face_id=None if nearest is None else nearest['object_id'],
            face_native_identity=None if nearest is None else nearest['native_identity'],
            face_persistent_id=None if nearest is None else nearest['persistent_id'],
            local_point_mm=local, assembly_point_mm=list(root), point_location=location,
            query_point_location=query_location,
            native_receipt=dict(artificial_observed_point=raw_point, location=location,
                body_pid=raw_body.persistent_id.hex(), face_parent_confirmed=nearest is not None))
        if x.witness_corrupt: x.witness_corrupt(value, x.witness_calls)
        return value
    x.witness_capture = witness
    return x


def run(x, **overrides):
    args = dict(context=x.context, instance_ids={role: x.ids[role] for role in ('variant', 'cylinder')},
        capture_full=x.full, capture_scope=x.scope_capture, capture_witness=x.witness_capture)
    args.update(overrides)
    return asyncio.run(helper.instance_point_axis_case(x.reader, **args))


@pytest.mark.parametrize('zero_boundary', [False, True])
def test_actual_catalog_probes_corner_gap_zero_durable_bindings_and_original_witnesses(probes_world, zero_boundary):
    x = probes_world; x.zero_boundary = zero_boundary; result = run(x)
    assert x.scope_calls == 6 and x.witness_calls == 3 and x.full_calls == 2
    assert len(result['rows']) == len(x.store.list()['items']) == 3
    assert [row['journal']['result']['distance_mm'] for row in result['rows']] == pytest.approx([math.sqrt(425.), 2., 0.])
    assert result['probes'][-1]['witness']['point_location'] == ('boundary' if zero_boundary else 'inside')
    assert result['before'] == result['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert all(job['payload']['mutates'] is False and 'mutation' not in job for job in x.store.list()['items'])
    assert x.retained == []


@pytest.mark.parametrize('fault', ['context', 'body_count', 'bool_count', 'faces', 'units', 'location', 'inside',
    'frame', 'component', 'surface', 'method', 'tolerance', 'metric', 'corner', 'translated_root',
    'nearest_body', 'nearest_face', 'body_locations', 'axis_semantics', 'axis_origin', 'axis_direction',
    'off_axis', 'swapped_axis', 'interference'])
def test_coherent_sql_result_cannot_replace_exact_scope_native_location_or_witnesses(probes_world, fault):
    x = probes_world
    def corrupt(tool, value):
        point = 'point' in tool
        if fault == 'context': value['observation_revision'] = 'stale'
        elif fault == 'body_count': value['solid_body_count'] = 2
        elif fault == 'bool_count': value['solid_body_count'] = True
        elif fault == 'faces' and point: value['face_count'] = 5
        elif fault == 'units': value['length_unit'] = 'm'
        elif fault == 'location' and point: value['point_location'] = 'inside'
        elif fault == 'inside' and point: value['inside'] = True
        elif fault == 'frame': value['frame']['origin_mm'][0] += 1.
        elif fault == 'component': value['component']['component_id'] = x.ids['main']
        elif fault == 'surface': value['includes_surface_bodies'] = True
        elif fault == 'method': value['method'] = 'sampled'
        elif fault == 'tolerance' and point: value['boundary_tolerance_mm'] = True
        elif fault == 'metric': value['distance_mm'] += 1.
        elif fault == 'corner' and point: value['nearest_mm'][0] -= 1.
        elif fault == 'translated_root' and point:
            value['point_assembly_mm'][0] += 1.; value['nearest_assembly_mm'][0] += 1.
        elif fault == 'nearest_body' and point: value['nearest_body_id'] = 'foreign'
        elif fault == 'nearest_face' and point: value['nearest_face_id'] = 'foreign'
        elif fault == 'body_locations' and point: value['body_locations'][0]['point_location'] = 'inside'
        elif not point:
            if fault == 'axis_semantics': value['axis_semantics'] = 'segment'
            elif fault == 'axis_origin': value['axis_origin_mm'][0] += 1.
            elif fault == 'axis_direction': value['axis_direction'] = [0., 2., 0.]
            elif fault == 'off_axis': value['closest_points_mm'][1][2] += 1.
            elif fault == 'swapped_axis':
                value['closest_points_mm'].reverse(); value['closest_points_assembly_mm'].reverse()
            elif fault == 'interference': value['intersection_classification'] = 'intersects'
    x.result_corrupt = corrupt
    with pytest.raises((ValueError, StopIteration, RuntimeError)): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['pid', 'cfg', 'short_transform', 'rotation', 'hidden', 'body', 'face',
    'face_pid', 'face_owner', 'duplicate_face', 'scope_changed', 'cylinder_between_axes'])
def test_incomplete_current_native_census_or_canonical_transform_difference_refuses(probes_world, fault):
    x = probes_world
    def corrupt(value, number):
        if fault == 'pid': value['persistent_id'] = 'XX'
        elif fault == 'cfg': value['info']['referenced_configuration'] = 'Другая'
        elif fault == 'short_transform': value['total_transform'].pop()
        elif fault == 'rotation': value['total_transform'][0] += .1
        elif fault == 'hidden': value['info']['hidden'] = False
        elif fault == 'body': value['solid_bodies'] = []
        elif fault == 'face': value['solid_bodies'][0]['faces'].pop()
        elif fault == 'face_pid': value['solid_bodies'][0]['faces'][0]['persistent_id'] = 'AA'
        elif fault == 'face_owner': value['solid_bodies'][0]['faces'][0]['body_id'] = 'foreign'
        elif fault == 'duplicate_face': value['solid_bodies'][0]['faces'][1] = deepcopy(value['solid_bodies'][0]['faces'][0])
        elif fault == 'scope_changed' and number == 2: value['native_receipt']['changed'] = True
        elif fault == 'cylinder_between_axes' and number == 5: value['native_receipt']['changed'] = True
    x.scope_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['body', 'pid', 'face', 'face_pid', 'point', 'root', 'location', 'query_location',
                                  'inside_fabricated_face'])
def test_independent_original_body_face_and_actual_boundary_or_inside_witness_required(probes_world, fault):
    x = probes_world
    def corrupt(value, number):
        if fault == 'body': value['body_native_identity'] += 99
        elif fault == 'pid': value['body_persistent_id'] = '00'
        elif fault == 'face': value['face_native_identity'] = 999
        elif fault == 'face_pid': value['face_persistent_id'] = '00'
        elif fault == 'point': value['local_point_mm'][0] += 1.
        elif fault == 'root': value['assembly_point_mm'][0] += 1.
        elif fault == 'location': value['point_location'] = 'outside'
        elif fault == 'query_location': value['query_point_location'] = 'inside'
        elif fault == 'inside_fabricated_face' and number == 3: value['face_id'] = 'pretend_boundary'
    x.witness_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['unknown', 'point_faces', 'point_moments', 'point_transform', 'axis_support'])
def test_actual_catalog_runner_unknown_or_closing_failure_has_no_followup_or_after_capture(probes_world, fault):
    x = probes_world
    if fault == 'unknown': x.unknown = True
    else:
        once = []
        def during(kind):
            if once: return
            if fault == 'axis_support' and kind != 'axis': return
            once.append(True)
            if fault == 'point_faces': x.originals['variant'].bodies[0].faces.pop()
            elif fault == 'point_moments': x.originals['variant'].bodies[0].moments = [2.]*12
            elif fault == 'point_transform': x.originals['variant'].info['transform']['origin_mm'][0] += 1.
            else: x.a.measurement_extreme_point = lambda *args: [0., .040, 0.]
        x.during = during
    with pytest.raises((ValueError, RuntimeError)): run(x)
    assert x.full_calls == 1 and x.retained


def test_whole_current_session_preservation_difference_refuses_after_all_three(probes_world):
    x = probes_world; original = x.full
    def full():
        value = original()
        if x.full_calls == 2: value['artificial_native_full_session']['models'][0]['metadata']['active_configuration'] = 'Вариант'
        return value
    with pytest.raises(ValueError): run(x, capture_full=full)
    assert x.witness_calls == 3


@pytest.mark.parametrize('fault', ['duplicate', 'missing', 'missing_scope', 'missing_witness', 'full_unknown'])
def test_missing_original_scope_or_native_producers_prevents_dispatch(probes_world, fault):
    x = probes_world; overrides = {}
    if fault == 'duplicate': overrides['instance_ids'] = dict(variant=x.ids['variant'], cylinder=x.ids['variant'])
    elif fault == 'missing': overrides['instance_ids'] = dict(variant=x.ids['variant'])
    elif fault == 'missing_scope': overrides['capture_scope'] = None
    elif fault == 'missing_witness': overrides['capture_witness'] = None
    else: overrides['capture_full'] = lambda: (_ for _ in ()).throw(ValueError('Actual whole session unknown'))
    with pytest.raises(ValueError): run(x, **overrides)
    assert x.calls == []
