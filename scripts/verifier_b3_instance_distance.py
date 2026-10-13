"""B3-I09: two original part-instance distances, no CAD/fixture lifecycle.

Native current census and trimmed-boundary witness producers remain with the
one original owner. Equal metric points alone never certify a native minimum.
"""
from copy import deepcopy
import math
import uuid

from verifier_b3_part_geometry import _call, _canonical, _context, _proof
from verifier_b3_component_membership import _ordinal, _pid, _require, _transform
from verifier_b3_witnesses import check_witnesses, close_vector, vector

SCOPE = 'bounded_b3_i09_instance_distance_evidence_v1'


def _scope(value, context, ids, second):
    value = _proof(value)
    _require(value['context'] == context and value['component_ids'] == [ids['main'], ids[second]]
             and type(value['components']) is list and len(value['components']) == 2,
             'Exact independent current pair scope required.')
    for index, (row, role, solids) in enumerate(zip(value['components'], ('main', second), (2, 1))):
        _require(row['component_id'] == ids[role], 'Original held component ID required.')
        for key in ('native_identity', 'model_identity', 'configuration_identity'): _ordinal(row[key])
        _pid(row['persistent_id']); _proof(row['native_receipt'])
        info = row['info']
        _require(info['referenced_document_type'] == 'part' and info['suppression_state'] == 'resolved'
                 and type(info['native_suppression_state']) is int and info['native_suppression_state'] in (2, 3)
                 and type(info['hidden']) is bool and info['referenced_configuration'] == ('Основная' if index == 0 else 'Вариант'),
                 'Original resolved part/two referenced configurations required.')
        _transform(info['transform'], row['total_transform'])
        expected = {'main': [0., 0., 0.], 'variant': [50., 10., 20.], 'nested': [130., 0., 0.]}[role]
        close_vector(info['transform']['origin_mm'], expected)
        axes = ([[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]] if role == 'variant'
                else [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        for actual, expected_axis in zip(info['transform']['axes_in_assembly'], axes): close_vector(actual, expected_axis)
        if role == 'nested':
            _ordinal(row['parent_native_identity'])
            _require('/' in info['component_path'] and type(row['parent_component_id']) is str and row['parent_component_id'],
                     'Exact current nested path/held parent receipt required.')
        else:
            _require(row['parent_native_identity'] is None and row['parent_component_id'] is None
                     and '/' not in info['component_path'], 'Original root instance required.')
        solid, surface = row['solid_bodies'], row['surface_bodies']
        _require(type(solid) is list and len(solid) == solids and type(surface) is list and len(surface) == 1,
                 'Full current normal solid/surface census required; no partial solver scope.')
        seen = set()
        for body in solid + surface:
            _require(type(body['body_id']) is str and body['body_id'] and body['body_id'] not in seen
                     and body['component_id'] == ids[role] and type(body['hidden']) is bool,
                     'Exact current body owner/visibility required.')
            seen.add(body['body_id']); _pid(body['persistent_id']); _ordinal(body['native_identity'])
            _proof(body['native_receipt'])
    first, other = value['components']
    _require(first['native_identity'] != other['native_identity'] and first['persistent_id'] != other['persistent_id']
             and first['model_identity'] == other['model_identity']
             and first['configuration_identity'] != other['configuration_identity']
             and first['info']['referenced_path'] == other['info']['referenced_path'] and first['info']['referenced_path'],
             'Distinct original same-file instances and exact configuration anchors required.')
    _require(any(row['hidden'] for row in first['solid_bodies']), 'Original hidden main solid must remain in the complete census.')
    _require(set(body['body_id'] for body in first['solid_bodies']+first['surface_bodies']).isdisjoint(
        body['body_id'] for body in other['solid_bodies']+other['surface_bodies']), 'Instance body IDs must remain distinct.')
    return value


def _point_on_original(value, component, *, solid):
    value = _proof(value)
    rows = component['solid_bodies'] if solid else component['surface_bodies']
    bodies = [body for body in rows if body['body_id'] == value['body_id']]
    _require(len(bodies) == 1 and value['component_id'] == component['component_id']
             and value['body_native_identity'] == bodies[0]['native_identity']
             and value['body_persistent_id'] == bodies[0]['persistent_id'], 'Witness must belong to the original current body/PID.')
    _ordinal(value['face_native_identity']); _pid(value['face_persistent_id']); _proof(value['native_receipt'])
    local, root = vector(value['local_point_mm']), vector(value['assembly_point_mm'])
    transform = component['info']['transform']
    close_vector(root, [transform['origin_mm'][i] + sum(local[j]*transform['axes_in_assembly'][j][i]
        for j in range(3)) for i in range(3)])
    return root


async def instance_distance_case(reader, *, context, instance_ids, capture_full,
                                 capture_pair_scope, capture_witnesses):
    """Exactly main→variant15 and main→nested70 mm in the existing profile.

instance_ids is the explicit original owner's main/variant/nested ID mapping.
capture_full observes the complete current assembly/referenced parts/neighbor
and session/UI/configs, raising on incomplete scope; no boolean completeness
certificate is accepted as a replacement for these observations.

capture_pair_scope(context, component_a_id, component_b_id) returns context,
component_ids and two current components with info (native component metadata),
raw 16-value total_transform, retained canonical equality ordinals/PID/parent,
parent_component_id bound by the owner to that original parent canonical,
and full solid_bodies/surface_bodies. Each body has exact component/body ID,
native_identity, persistent_id, hidden, native_receipt. The live owner proves
normal bodies and current held PID/canonical membership independently.

capture_witnesses(context, pair_scope, public_result) proves two original solid
trimmed-boundary witnesses. Its witnesses contain component/body IDs, exact
body PID/canonical, face PID/canonical, actual local_point_mm and
assembly_point_mm, and raw native_receipt. This cannot merely echo public
points. For nested it also returns closer_surface: distance_mm and witnesses
(first an original main surface, second an original nested solid). The actual
native receipts must independently prove these boundary points and their
closer separation; surfaces remain excluded from the solid minimum.
"""
    context = _context(context)
    _require(type(instance_ids) is dict and set(instance_ids) == {'main', 'variant', 'nested'}
             and all(type(x) is str and x for x in instance_ids.values()) and len(set(instance_ids.values())) == 3,
             'Three distinct original held IDs required; no name/roster adoption.')
    _require(all(callable(x) for x in (capture_full, capture_pair_scope, capture_witnesses)),
             'Independent full/current census/original native witness producers required.')
    ids = deepcopy(instance_ids)
    before = _proof(await _call(capture_full))
    rows, pairs = [], []
    for role, expected in (('variant', 15.), ('nested', 70.)):
        scope = _scope(await _call(capture_pair_scope, deepcopy(context), ids['main'], ids[role]), context, ids, role)
        if pairs:
            _require(_canonical(scope['components'][0]) == _canonical(pairs[0]['before']['components'][0]),
                     'Original main census/metadata changed between pair reads.')
        args = dict(request_id='b3-i09-'+uuid.uuid4().hex, **context,
                    component_a_id=ids['main'], component_b_id=ids[role])
        row = await reader.read('measurement_get_component_distance', args)
        rows.append(dict(tool='measurement_get_component_distance', arguments=args, journal=deepcopy(row)))
        _require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal pair read required.')
        result = row['result']
        _require(result['document_id'] == context['document_id'] and result['configuration'] == context['configuration']
                 and result['observation_revision'] == context['expected_observation_revision']
                 and result['scope'] == 'resolved_assembly_instance_reads_v1'
                 and result['transform_target_frame'] == 'assembly_model'
                 and result['includes_hidden_components'] is True and result['implicit_resolution'] is False
                 and result['method'] == 'IModelDoc2.ClosestDistance'
                 and type(result['solid_body_counts']) is list and result['solid_body_counts'] == [2, 1]
                 and all(type(x) is int for x in result['solid_body_counts']), 'Exact current public pair context/census/method required.')
        check_witnesses(result, kind='pair', expected_mm=expected)
        for key, component in zip(('component_a', 'component_b'), scope['components']):
            public = result[key]
            _require(public['component_id'] == component['component_id']
                     and public['parent_component_id'] == component['parent_component_id']
                     and _canonical({k: v for k, v in public.items() if k not in ('component_id', 'parent_component_id')}) ==
                         _canonical(component['info']), 'Public targets differ from original independent native scope.')
        witness = _proof(await _call(capture_witnesses, deepcopy(context), deepcopy(scope), deepcopy(result)))
        _require(type(witness['witnesses']) is list and len(witness['witnesses']) == 2, 'Two original boundary witness receipts required.')
        for native, component, point in zip(witness['witnesses'], scope['components'], result['closest_points_mm']):
            close_vector(_point_on_original(native, component, solid=True), point)
        if role == 'nested':
            closer = _proof(witness['closer_surface'])
            distance = closer['distance_mm']
            _require(type(distance) in (int, float) and math.isfinite(distance) and 0 <= distance < expected
                     and type(closer['witnesses']) is list and len(closer['witnesses']) == 2,
                     'Actual independently proven closer surface must remain excluded.')
            points = [_point_on_original(point, component, solid=index == 1)
                      for index, (point, component) in enumerate(zip(closer['witnesses'], scope['components']))]
            _require(math.isclose(math.dist(*points), distance, rel_tol=0., abs_tol=1e-6), 'Closer surface native metric differs.')
        after_pair = _scope(await _call(capture_pair_scope, deepcopy(context), ids['main'], ids[role]), context, ids, role)
        _require(_canonical(scope) == _canonical(after_pair), 'Full original pair scope changed during read/witness proof.')
        pairs.append(dict(expected_mm=expected, before=scope, after=after_pair, witness=witness))
    after = _proof(await _call(capture_full))
    _require(_canonical(before) == _canonical(after), 'Full owned assembly/parts/neighbor/session changed.')
    return dict(scope=SCOPE, instance_ids=ids, rows=rows, pairs=pairs, before=before, after=after,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_owner_native_census_and_trimmed_boundary_producers',
                            'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])
