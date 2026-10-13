"""Bounded B3-I12 probes and a separate prepared surface-only refusal phase."""
from copy import deepcopy
import math
import uuid

from solidworks_mcp.component_distance import ComponentDistanceCatalog
from solidworks_mcp.point_measurement import assembly_point_mm, component_local_point_m, classify_native_rays
from solidworks_mcp.axis_measurement import anchor_axis, dot, check_axis_witnesses
from verifier_b3_part_geometry import _call, _canonical, _context, _proof
from verifier_b3_component_membership import _ordinal, _pid, _require, _transform
from verifier_b3_aggregate_distance import _scope, _component
from verifier_b3_instance_point_axis import FRAME, _native_point
from verifier_b3_witnesses import check_witnesses, close_vector, model_point, model_direction, vector

SCOPE = 'bounded_b3_i12_aggregate_point_axis_evidence_v1'
POINT_METHOD = 'complete solid leaf faces IFace2.GetClosestPointOn + native body RayIntersections'
AXIS_METHOD = 'complete solid leaf supports + memory-only certified axis edges + native ClosestDistance'
ROOT_FRAME = dict(origin_mm=[0., 0., 0.], axes_in_model=[[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])


def _faces(scope):
    for role, count in (('a_part', 6), ('a_cylinder', 3)):
        component = scope['components'][role]
        for body in component['solid_bodies']+component['surface_bodies']:
            faces = body['faces']; expected = count if body in component['solid_bodies'] else 1
            _require(type(faces) is list and len(faces) == expected
                     and len({face['object_id'] for face in faces}) == expected, 'Complete original current leaf face census required.')
            for face in faces:
                _require(type(face['object_id']) is str and face['object_id'] and face['component_id'] == component['component_id']
                         and face['body_id'] == body['body_id'], 'Original native face opaque-ID owner binding required.')
                _ordinal(face['native_identity']); _pid(face['persistent_id']); _proof(face['native_receipt'])


def _leaf_receipts(receipts, scope, result, *, kind, args, expected_location):
    _require(type(receipts) is list and len(receipts) == 2, 'Both actual original leaf computations required, including nonwinner/zero.')
    components = scope['components']; seen = set(); minimum = math.inf; locations = []
    root_query = model_point(args['point_mm'] if kind == 'point' else args['axis_origin_mm'], args['frame'])
    root_direction = model_direction(args['axis_direction'], args['frame']) if kind == 'axis' else None
    for receipt in receipts:
        receipt = _proof(receipt)
        role = next((role for role in ('a_part', 'a_cylinder') if components[role]['component_id'] == receipt['component_id']), None)
        _require(role is not None and role not in seen, 'No missing/duplicate/foreign leaf receipt.')
        seen.add(role); component = components[role]; body = component['solid_bodies'][0]
        _require(receipt['native_identity'] == component['native_identity'] and receipt['persistent_id'] == component['persistent_id']
                 and receipt['body_id'] == body['body_id'] and receipt['body_native_identity'] == body['native_identity']
                 and receipt['body_persistent_id'] == body['persistent_id'], 'Original current leaf/body solver PID/canonical inputs required.')
        _proof(receipt['native_receipt']); transform = component['info']['transform']
        if kind == 'point':
            queries = receipt['face_readbacks']; faces = body['faces']
            _require(type(queries) is list and len(queries) == len(faces), 'Every original solid trimmed face must be measured.')
            local = component_local_point_m(transform, root_query); face_seen = set(); best = None
            for query in queries:
                matches = [face for face in faces if face['persistent_id'] == query['persistent_id']
                           and face['native_identity'] == query['native_identity']]
                _require(len(matches) == 1 and query['persistent_id'] not in face_seen, 'Exact nonduplicate original face readback required.')
                face_seen.add(query['persistent_id']); raw = query['closest_xyzuv_m']
                _require(type(raw) is list and len(raw) == 5 and all(type(x) in (float, int) and math.isfinite(x) for x in raw),
                         'Actual complete finite IFace2 XYZ/UV readback required.')
                candidate = math.dist(local, raw[:3])*1000.
                if best is None or candidate < best[0]: best = candidate, assembly_point_mm(transform, raw[:3])
            distance, nearest = best
            location = 'boundary' if distance <= 1e-5 else classify_native_rays(receipt['ray_observation'], local)
            locations.append(dict(component_id=component['component_id'], body_id=body['body_id'], point_location=location))
            if role == 'a_cylinder': close_vector(nearest, result['nearest_assembly_mm'])
        else:
            supports = receipt['supports_m']
            _require(type(supports) is list and len(supports) == 2, 'Actual GetExtremePoint(-direction/+direction) supports required.')
            root_supports = [[x*.001 for x in assembly_point_mm(transform, vector(point))] for point in supports]
            anchor = anchor_axis([x*.001 for x in root_query], root_direction, [x*.001 for x in transform['origin_mm']])
            interval = [dot([x-a for x, a in zip(point, anchor)], root_direction) for point in root_supports]
            _require(interval[0] <= interval[1], 'Original exact directional support interval required.')
            distance, points = ComponentDistanceCatalog._native_result(receipt['native_result'])
            check_axis_witnesses([[x*.001 for x in point] for point in points], anchor, root_direction, interval)
            if role == 'a_cylinder':
                for actual, public in zip(points, result['closest_points_assembly_mm']): close_vector(actual, public)
        minimum = min(minimum, distance)
    _require(seen == {'a_part', 'a_cylinder'} and math.isclose(minimum, result['distance_mm'], rel_tol=0., abs_tol=1e-6),
             'True complete leaf minimum required; no early zero/partial public counts substitute.')
    if kind == 'point':
        observed = next(loc for loc in ('inside', 'boundary', 'outside') if any(row['point_location'] == loc for row in locations))
        _require(observed == expected_location and _canonical(sorted(result['body_locations'], key=lambda row: row['component_id'])) ==
                 _canonical(sorted(locations, key=lambda row: row['component_id'])), 'Actual native locations of both original bodies required.')


async def aggregate_point_axis_case(reader, *, context, instance_ids, capture_full,
                                    capture_scope, capture_leaf_probes, capture_witness):
    """Four sends, unchanged initial sub_aОсновная/childВариант profile.

Uses the I11 complete original scope contract (seven held IDs; both subassembly
groups) plus full body faces for a_part/a_cylinder. capture_scope(context,
sub_a_id,sub_b_id) observes actual full current hierarchy/normal bodies; it must
raise on incomplete scope. capture_leaf_probes(context,scope,result,label)
returns both actual native leaf computations: leaf/body PID+canonical anchors,
native_receipt; point face_readbacks with each face PID/canonical and actual
closest_xyzuv_m, ray_observation; axis supports_m[-/+direction] and native_result
(distance_m, root_points_m). Producers must not copy public minimum/counts.
capture_witness follows I10 original solid/face/local-root/native-location
contract for the winning hidden cylinder. Whole nine-instance current session
and referenced-part/config/UI preservation come from capture_full.
No setup, unknown recovery, COM connection or cleanup happens here.
"""
    context = _context(context)
    _require(type(instance_ids) is dict and set(instance_ids) == {'main', 'sub_a', 'sub_b', 'a_part', 'a_cylinder', 'b_part', 'b_cylinder'}
             and len(set(instance_ids.values())) == 7 and all(type(x) is str and x for x in instance_ids.values()), 'Seven original held aggregate IDs required.')
    _require(all(callable(x) for x in (capture_full, capture_scope, capture_leaf_probes, capture_witness)), 'Independent complete native producers required.')
    ids = deepcopy(instance_ids); before = _proof(await _call(capture_full)); rows, probes = [], []
    groups = (('a_part', 'a_cylinder'), ('b_part', 'b_cylinder'))
    cases = [('point_outside', 'point', 3., 'outside', [5., -149., -20.], None, FRAME),
             ('point_inside', 'point', 6., 'inside', [190., 15., 0.], None, None),
             ('axis_gap', 'axis', 2., None, [-10., -148., -20.], [1., 0., 0.], FRAME),
             ('axis_through', 'axis', 0., None, [190., 0., 0.], [0., 1., 0.], None)]
    for label, kind, expected, location, point, direction, frame in cases:
        scope = _scope(await _call(capture_scope, deepcopy(context), ids['sub_a'], ids['sub_b']), context, ids, groups); _faces(scope)
        if probes: _require(_canonical(scope) == _canonical(probes[0]['before']), 'Original full scope changed between probes.')
        args = dict(request_id='b3-i12-'+uuid.uuid4().hex, **context, component_id=ids['sub_a'], frame=deepcopy(frame))
        if kind == 'point': args['point_mm'] = point
        else: args.update(axis_origin_mm=point, axis_direction=direction)
        tool = 'measurement_get_component_aggregate_'+kind+'_distance'; row = await reader.read(tool, args)
        rows.append(dict(tool=tool, arguments=args, journal=deepcopy(row)))
        _require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal complete aggregate probe required.')
        result = row['result']; native = scope['components']
        _require(result['document_id'] == context['document_id'] and result['configuration'] == context['configuration']
                 and result['observation_revision'] == context['expected_observation_revision']
                 and result['scope'] == 'resolved_assembly_instance_reads_v1' and result['transform_target_frame'] == 'assembly_model'
                 and result['includes_hidden_components'] is True and result['implicit_resolution'] is False,
                 'Exact current original aggregate public scope required.')
        for key, count in (('leaf_component_count', 2), ('solid_leaf_component_count', 2), ('evaluated_leaf_count', 2),
                           ('excluded_nonsolid_leaf_component_count', 0), ('solid_body_count', 2)):
            _require(type(result[key]) is int and result[key] == count, 'Complete two-leaf normal-solid census required.')
        _require(type(result['leaf_component_ids']) is list and len(result['leaf_component_ids']) == 2
                 and set(result['leaf_component_ids']) == {ids['a_part'], ids['a_cylinder']} and result['frame'] == (ROOT_FRAME if frame is None else frame),
                 'Original leaf IDs and declared frame required.')
        _component(result['component'], native['sub_a']); _component(result['nearest_component'], native['a_cylinder'])
        if kind == 'point':
            check_witnesses(result, kind='point', aggregate=True, expected_mm=expected, frame=frame, point_mm=point, expected_location=location)
            _require(result['method'] == POINT_METHOD and type(result['face_count']) is int and result['face_count'] == 9
                     and type(result['boundary_tolerance_mm']) in (float, int)
                     and math.isclose(result['boundary_tolerance_mm'], 1e-5, rel_tol=0., abs_tol=1e-15), 'Exact complete native point/face contract required.')
            root_point = result['nearest_assembly_mm']
        else:
            check_witnesses(result, kind='axis', aggregate=True, expected_mm=expected, frame=frame, axis_origin_mm=point, axis_direction=direction)
            _require(result['method'] == AXIS_METHOD, 'Exact existing complete infinite-axis method required.')
            root_point = result['closest_points_assembly_mm'][0]
        leaf_probes = await _call(capture_leaf_probes, deepcopy(context), deepcopy(scope), deepcopy(result), label)
        _leaf_receipts(leaf_probes, scope, result, kind=kind, args=args, expected_location=location)
        witness = _proof(await _call(capture_witness, deepcopy(context), deepcopy(scope), deepcopy(result), label))
        close_vector(_native_point(witness, native['a_cylinder'], boundary=expected > 0), root_point)
        if kind == 'point':
            _require(witness['query_point_location'] == location and witness['body_id'] == result['nearest_body_id']
                     and witness['face_id'] == result['nearest_face_id'], 'Original actual nearest body/face/location binding required.')
        after_probe = _scope(await _call(capture_scope, deepcopy(context), ids['sub_a'], ids['sub_b']), context, ids, groups); _faces(after_probe)
        _require(_canonical(scope) == _canonical(after_probe), 'Complete current native scope changed during probe.')
        probes.append(dict(label=label, before=scope, after=after_probe, leaf_probes=deepcopy(leaf_probes), witness=witness))
    after = _proof(await _call(capture_full)); _require(_canonical(before) == _canonical(after), 'Whole current session changed.')
    return dict(scope=SCOPE, phase='initial_owned_aggregate_probes', rows=rows, probes=probes, before=before, after=after,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_owner_census_opaque_ID_native_queries_and_location_producers', 'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])


async def aggregate_surface_refusal_case(reader, *, context, instance_ids, capture_full, capture_refusal_scope):
    """Separate owner-prepared nonsolid phase, exactly one finite point refusal.

The unchanged legacy fixture first sets sub_aВариант/childОсновная then suppresses
owned solids. This helper performs neither step. Caller must provide refreshed
current retained target/part/cylinder IDs/context AFTER acknowledged owner setup.
capture_refusal_scope returns actual context/components by these three roles,
current canonical/PID/normal info+raw16transform/parent bindings, complete leaf
IDs and solid_bodies/surface_bodies; target empty, part one surface, cylinder
empty. Initial-scope IDs/names or a setup-complete boolean cannot adopt them.
Native setup/ownership/postconditions and final cleanup remain explicit gates.
"""
    context = _context(context)
    _require(type(instance_ids) is dict and set(instance_ids) == {'sub_a', 'a_part', 'a_cylinder'}
             and all(type(x) is str and x for x in instance_ids.values()) and len(set(instance_ids.values())) == 3
             and callable(capture_full) and callable(capture_refusal_scope), 'Refreshed explicit original owner nonsolid scope required.')
    ids = deepcopy(instance_ids); before = _proof(await _call(capture_full))
    def validate(value):
        value = _proof(value)
        _require(value['context'] == context and set(value['components']) == set(ids)
                 and value['leaf_component_ids'] == [ids['a_part'], ids['a_cylinder']], 'Actual full refreshed nonsolid leaf census required.')
        components = value['components']
        for role, cfg, origin in (('sub_a', 'Вариант', 100.), ('a_part', 'Основная', 130.), ('a_cylinder', 'Основная', 190.)):
            row = components[role]; info = row['info']
            _require(row['component_id'] == ids[role] and info['referenced_configuration'] == cfg
                     and info['referenced_document_type'] == ('assembly' if role == 'sub_a' else 'part')
                     and info['suppression_state'] == 'resolved' and type(info['native_suppression_state']) is int
                     and info['native_suppression_state'] in (2, 3) and row['solid_bodies'] == []
                     and type(row['surface_bodies']) is list and len(row['surface_bodies']) == (1 if role == 'a_part' else 0),
                     'Actual current prepared surface/empty normal-body profile required.')
            _pid(row['persistent_id']); _ordinal(row['native_identity']); _ordinal(row['model_identity']); _ordinal(row['configuration_identity']); _proof(row['native_receipt'])
            _transform(info['transform'], row['total_transform']); close_vector(info['transform']['origin_mm'], [origin, 0., 0.])
            if role == 'sub_a': _require(row['parent_component_id'] is None and row['parent_native_identity'] is None, 'Current root aggregate required.')
            else: _require(row['parent_component_id'] == ids['sub_a'] and row['parent_native_identity'] == components['sub_a']['native_identity']
                           and info['component_path'].rsplit('/', 1)[0] == components['sub_a']['info']['component_path'], 'Current original native parent/leaf required.')
            for body in row['surface_bodies']:
                _require(body['component_id'] == ids[role] and type(body['body_id']) is str and body['body_id'], 'Actual current surface reference required.')
                _pid(body['persistent_id']); _ordinal(body['native_identity']); _proof(body['native_receipt'])
        return value
    scope = validate(await _call(capture_refusal_scope, deepcopy(context), deepcopy(ids)))
    args = dict(request_id='b3-i12-surface-refusal-'+uuid.uuid4().hex, **context, component_id=ids['sub_a'], point_mm=[199., 15., 0.], frame=None)
    tool = 'measurement_get_component_aggregate_point_distance'
    row = await reader.read(tool, args, expected_error='component_has_no_solid_bodies')
    _require(row['status'] == 'failed' and row['result'] is None and row['error']['code'] == 'component_has_no_solid_bodies'
             and row['error']['requires_reconciliation'] is False, 'Exact finite nonsolid aggregate refusal required.')
    after_scope = validate(await _call(capture_refusal_scope, deepcopy(context), deepcopy(ids)))
    after = _proof(await _call(capture_full))
    _require(_canonical(scope) == _canonical(after_scope) and _canonical(before) == _canonical(after), 'Complete prepared nonsolid session changed.')
    return dict(scope=SCOPE, phase='owner_prepared_surface_only_refusal', rows=[dict(tool=tool, arguments=args, journal=row)],
                before=before, after=after, native_before=scope, native_after=after_scope,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['acknowledged_native_setup_and_current_ownership_transition_postconditions',
                            'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])
