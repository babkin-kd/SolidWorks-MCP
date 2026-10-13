"""Finite B3-I11 aggregate route; all native producers/lifecycle stay external."""
from copy import deepcopy
import math
import uuid

from verifier_b3_part_geometry import _call, _canonical, _context, _proof
from verifier_b3_component_membership import _ordinal, _pid, _require, _transform
from verifier_b3_instance_distance import _point_on_original
from verifier_b3_instance_point_axis import FRAME
from verifier_b3_witnesses import check_witnesses, close_vector, vector

SCOPE = 'bounded_b3_i11_aggregate_distance_evidence_v1'
ROLES = ('main', 'sub_a', 'sub_b', 'a_part', 'a_cylinder', 'b_part', 'b_cylinder')
METHOD = 'complete leaf-pair IModelDoc2.ClosestDistance; IBody2.GetExtremePoint for shared instance'


def _scope(value, context, ids, groups):
    value = _proof(value)
    _require(value['context'] == context and type(value['components']) is dict
             and set(value['components']) == set(ROLES)
             and value['leaf_component_ids'] == [[ids[role] for role in group] for group in groups],
             'Actual complete original native leaf census required; no declared roster replacement.')
    components = value['components']; all_body_ids = set()
    origins = dict(main=0., sub_a=100., sub_b=250., a_part=130., a_cylinder=190., b_part=280., b_cylinder=340.)
    for role in ROLES:
        row = components[role]; assembly = role.startswith('sub_')
        _require(row['component_id'] == ids[role], 'Original explicit target/leaf ID required.')
        _pid(row['persistent_id']); _proof(row['native_receipt'])
        for key in ('native_identity', 'model_identity', 'configuration_identity'): _ordinal(row[key])
        info = row['info']
        _require(info['referenced_document_type'] == ('assembly' if assembly else 'part')
                 and info['referenced_configuration'] == ('Вариант' if role.endswith('_part') else 'Основная')
                 and info['suppression_state'] == 'resolved' and type(info['native_suppression_state']) is int
                 and info['native_suppression_state'] in (2, 3) and type(info['hidden']) is bool,
                 'Existing resolved native aggregate fixture/configuration required.')
        _transform(info['transform'], row['total_transform'])
        close_vector(info['transform']['origin_mm'], [origins[role], 0., 0.])
        for axis, expected in zip(info['transform']['axes_in_assembly'], [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]): close_vector(axis, expected)
        if role.startswith(('a_', 'b_')):
            parent_role = 'sub_'+role[0]; parent = components[parent_role]
            _require(row['parent_component_id'] == ids[parent_role]
                     and row['parent_native_identity'] == parent['native_identity']
                     and info['component_path'].rsplit('/', 1)[0] == parent['info']['component_path'],
                     'Original nested native parent/path/total transform required.')
        else:
            _require(row['parent_component_id'] is None and row['parent_native_identity'] is None
                     and '/' not in info['component_path'], 'Original root target required.')
        solids, surfaces = row['solid_bodies'], row['surface_bodies']
        _require(type(solids) is list and len(solids) == (0 if assembly else 2 if role == 'main' else 1)
                 and type(surfaces) is list and len(surfaces) == (1 if role == 'main' or role.endswith('_part') else 0),
                 'Full normal solid/surface census including nonwinning leaves required.')
        for body in solids+surfaces:
            _require(type(body['body_id']) is str and body['body_id'] and body['body_id'] not in all_body_ids
                     and body['component_id'] == ids[role] and type(body['hidden']) is bool, 'Exact original instance-body owner required.')
            all_body_ids.add(body['body_id']); _pid(body['persistent_id']); _ordinal(body['native_identity']); _proof(body['native_receipt'])
    _require(len({row['native_identity'] for row in components.values()}) == 7
             and len({row['persistent_id'] for row in components.values()}) == 7,
             'Distinct original aggregate/leaf canonical identities and PIDs required.')
    for roles in (('sub_a', 'sub_b'), ('a_part', 'b_part'), ('a_cylinder', 'b_cylinder')):
        a, b = (components[role] for role in roles)
        _require(a['model_identity'] == b['model_identity'] and a['configuration_identity'] == b['configuration_identity']
                 and a['info']['referenced_path'] == b['info']['referenced_path'] and a['info']['referenced_path'],
                 'Repeated same-file/config exact native anchors required.')
    _require(components['main']['model_identity'] == components['a_part']['model_identity']
             and components['main']['configuration_identity'] != components['a_part']['configuration_identity']
             and components['main']['info']['referenced_path'] == components['a_part']['info']['referenced_path']
             and components['a_cylinder']['info']['hidden'] is True,
             'Original main/two-config part and hidden cylinder must remain in full scope.')
    return value


def _component(public, native):
    _require(public['component_id'] == native['component_id'] and public['parent_component_id'] == native['parent_component_id']
             and _canonical({k: v for k, v in public.items() if k not in ('component_id', 'parent_component_id')}) == _canonical(native['info']),
             'Public target/nearest leaf differs from exact independent original native instance.')


async def aggregate_distance_case(reader, *, context, instance_ids, capture_full,
                                  capture_scope, capture_pairs, capture_witnesses):
    """Two reads: main→sub_a70 root; sub_a→sub_b84 in the existing frame.

capture_full observes the entire original nine-instance session/parts/neighbor,
with actual current geometry/config/selection/view/file/application data.
capture_scope(context, target_a_id, target_b_id) independently returns context,
complete actual leaf_component_ids and components by the seven original roles:
component_id/info/raw16total_transform/retained native/model/config ordinals,
PID/parent native+opaque anchors, full solid_bodies/surface_bodies. Body receipts
have body_id/component_id/native_identity/persistent_id/hidden/native_receipt.
The owner confirms actual full traversal/current normal body membership and
raises on any missing/extra/unsupported/nonwinning leaf; no complete=True flag
can stand in for it. No names or partial solver roster may adopt a leaf.

capture_pairs(context, scope, result) supplies all actual independent leaf-pair
native receipts, including nonwinning pairs: component_a_id/component_b_id,
native_a_identity/native_b_identity/native_a_pid/native_b_pid, distance_mm,
closest_points_assembly_mm/native_receipt. It must never echo the result/counts.
capture_witnesses(context, scope, result) supplies two actual original winning
solid-body/trimmed-face local/root receipts using the I09 witness contract.
Independent opaque-ID→retained PID/canonical bindings remain a required driver
gate. This helper never performs native queries or authorizes cleanup.
"""
    context = _context(context)
    _require(type(instance_ids) is dict and set(instance_ids) == set(ROLES)
             and all(type(x) is str and x for x in instance_ids.values()) and len(set(instance_ids.values())) == 7,
             'Seven exact original owner-held aggregate/leaf IDs required.')
    _require(all(callable(x) for x in (capture_full, capture_scope, capture_pairs, capture_witnesses)),
             'Independent full/current leaf-census/all-pair/boundary producers required.')
    ids = deepcopy(instance_ids); before = _proof(await _call(capture_full)); rows, cases = [], []
    for label, targets, groups, winner, expected, frame in (
        ('part_to_subassembly', ('main', 'sub_a'), (('main',), ('a_part', 'a_cylinder')), ('main', 'a_part'), 70., None),
        ('repeated_subassemblies', ('sub_a', 'sub_b'), (('a_part', 'a_cylinder'), ('b_part', 'b_cylinder')), ('a_cylinder', 'b_part'), 84., FRAME)):
        a_id, b_id = (ids[role] for role in targets)
        scope = _scope(await _call(capture_scope, deepcopy(context), a_id, b_id), context, ids, groups)
        if cases:
            _require(_canonical(scope['components']) == _canonical(cases[0]['before']['components']), 'Original complete aggregate scope changed between reads.')
        args = dict(request_id='b3-i11-'+uuid.uuid4().hex, **context, component_a_id=a_id, component_b_id=b_id, frame=deepcopy(frame))
        row = await reader.read('measurement_get_component_aggregate_distance', args)
        rows.append(dict(tool='measurement_get_component_aggregate_distance', arguments=args, journal=deepcopy(row)))
        _require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal full aggregate read required.')
        result = row['result']; native = scope['components']; count = len(groups[0])*len(groups[1])
        _require(result['document_id'] == context['document_id'] and result['configuration'] == context['configuration']
                 and result['observation_revision'] == context['expected_observation_revision']
                 and result['scope'] == 'resolved_assembly_instance_reads_v1' and result['transform_target_frame'] == 'assembly_model'
                 and result['includes_hidden_components'] is True and result['implicit_resolution'] is False and result['method'] == METHOD,
                 'Exact original current aggregate public context/method required.')
        for key, expected_counts in (('leaf_component_counts', [len(group) for group in groups]),
            ('solid_leaf_component_counts', [len(group) for group in groups]), ('solid_body_counts', [2, 2]),
            ('excluded_nonsolid_leaf_component_counts', [0, 0])):
            _require(type(result[key]) is list and result[key] == expected_counts and all(type(x) is int for x in result[key]),
                     'Actual complete aggregate census differs; no partial scope.')
        for key, expected_count in (('evaluated_pair_count', count), ('native_pair_count', count), ('shared_instance_pair_count', 0)):
            _require(type(result[key]) is int and result[key] == expected_count, 'All original native leaf pairs must be evaluated.')
        _require(type(result['leaf_component_ids']) is list and len(result['leaf_component_ids']) == 2
                 and all(type(actual) is list and len(actual) == len(expected_ids) and set(actual) == set(expected_ids)
                         for actual, expected_ids in zip(result['leaf_component_ids'], scope['leaf_component_ids'])), 'Full exact original leaf IDs required.')
        check_witnesses(result, kind='pair', aggregate=True, expected_mm=expected, frame=frame)
        root_frame = dict(origin_mm=[0., 0., 0.], axes_in_model=[[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        _require(result['frame'] == (root_frame if frame is None else frame), 'Exact declared aggregate frame required.')
        for key, role in zip(('component_a', 'component_b'), targets): _component(result[key], native[role])
        for key, role in zip(('nearest_component_a', 'nearest_component_b'), winner): _component(result[key], native[role])
        pairs = await _call(capture_pairs, deepcopy(context), deepcopy(scope), deepcopy(result))
        expected_pairs = {(ids[a], ids[b]) for a in groups[0] for b in groups[1]}
        _require(type(pairs) is list and len(pairs) == count, 'Actual all-pair raw receipts required.')
        seen, minimum = set(), math.inf
        for pair in pairs:
            pair = _proof(pair); key = (pair['component_a_id'], pair['component_b_id'])
            _require(key in expected_pairs and key not in seen, 'Missing/duplicate/foreign native leaf pair prohibited.')
            seen.add(key)
            a, b = (next(item for item in native.values() if item['component_id'] == cid) for cid in key)
            _require(pair['native_a_identity'] == a['native_identity'] and pair['native_b_identity'] == b['native_identity']
                     and pair['native_a_pid'] == a['persistent_id'] and pair['native_b_pid'] == b['persistent_id'], 'Original leaf PID/canonical solver inputs required.')
            distance = pair['distance_mm']; points = pair['closest_points_assembly_mm']
            _require(type(distance) in (int, float) and math.isfinite(distance) and distance >= 0
                     and type(points) is list and len(points) == 2
                     and math.isclose(math.dist(vector(points[0]), vector(points[1])), distance, rel_tol=0., abs_tol=1e-6), 'Actual native pair metric/witnesses required.')
            _proof(pair['native_receipt']); minimum = min(minimum, distance)
            if key == (ids[winner[0]], ids[winner[1]]):
                _require(math.isclose(distance, expected, rel_tol=0., abs_tol=1e-6), 'Original winning native pair differs.')
                for point, public in zip(points, result['closest_points_assembly_mm']): close_vector(point, public)
        _require(seen == expected_pairs and math.isclose(minimum, expected, rel_tol=0., abs_tol=1e-6),
                 'True all-pair minimum required; no early stop or result-count substitute.')
        witnesses = await _call(capture_witnesses, deepcopy(context), deepcopy(scope), deepcopy(result))
        _require(type(witnesses) is list and len(witnesses) == 2, 'Two original solid-body boundary witnesses required.')
        for witness, role, point in zip(witnesses, winner, result['closest_points_assembly_mm']):
            close_vector(_point_on_original(witness, native[role], solid=True), point)
        after_scope = _scope(await _call(capture_scope, deepcopy(context), a_id, b_id), context, ids, groups)
        _require(_canonical(scope) == _canonical(after_scope), 'Complete current aggregate/normal-body/native leaf scope changed.')
        cases.append(dict(label=label, expected_mm=expected, before=scope, after=after_scope,
                          native_pairs=deepcopy(pairs), witnesses=deepcopy(witnesses)))
    after = _proof(await _call(capture_full)); _require(_canonical(before) == _canonical(after), 'Full current owned session changed.')
    return dict(scope=SCOPE, rows=rows, cases=cases, before=before, after=after, instance_ids=ids,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_owner_full_census_all_pair_and_opaque_ID_boundary_producers',
                            'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])
