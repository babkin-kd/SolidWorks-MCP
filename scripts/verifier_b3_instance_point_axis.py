"""Bounded B3-I10 original instance probes; native lifecycle stays external."""
from copy import deepcopy
import math
import uuid

from verifier_b3_part_geometry import _call, _canonical, _context, _proof
from verifier_b3_component_membership import _ordinal, _pid, _require, _transform
from verifier_b3_witnesses import check_witnesses, close_vector, vector

SCOPE = 'bounded_b3_i10_instance_point_axis_evidence_v1'
FRAME = dict(origin_mm=[50., 10., 20.], axes_in_model=[[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]])
POINT_METHOD = 'IFace2.GetClosestPointOn + IModelDocExtension.RayIntersections'
AXIS_METHOD = 'IBody2.GetExtremePoint + temporary ICurve.CreateWireBody edge + IModelDoc2.ClosestDistance'


def _current_scope(value, context, component_id, role):
    value = _proof(value)
    _require(value['context'] == context and value['component_id'] == component_id,
             'Exact original current scope required.')
    for key in ('native_identity', 'model_identity', 'configuration_identity'): _ordinal(value[key])
    _pid(value['persistent_id']); _proof(value['native_receipt'])
    info = value['info']
    _require(info['referenced_document_type'] == 'part' and info['suppression_state'] == 'resolved'
             and type(info['native_suppression_state']) is int and info['native_suppression_state'] in (2, 3)
             and type(info['hidden']) is bool and info['referenced_path']
             and info['referenced_configuration'] == ('Вариант' if role == 'variant' else 'Основная')
             and value['parent_native_identity'] is None and value['parent_component_id'] is None
             and '/' not in info['component_path'], 'Original resolved root part/current referenced configuration required.')
    _transform(info['transform'], value['total_transform'])
    close_vector(info['transform']['origin_mm'], [50., 10., 20.] if role == 'variant' else [150., 0., 0.])
    axes = FRAME['axes_in_model'] if role == 'variant' else [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    for actual, expected in zip(info['transform']['axes_in_assembly'], axes): close_vector(actual, expected)
    if role == 'variant': _require(info['hidden'] is True, 'Original hidden variant remains included.')
    solids, surfaces = value['solid_bodies'], value['surface_bodies']
    _require(type(solids) is list and len(solids) == 1 and type(surfaces) is list
             and len(surfaces) == (1 if role == 'variant' else 0), 'Complete current normal solid/surface census required.')
    seen_ids, seen_faces = set(), set()
    for body in solids+surfaces:
        _require(type(body['body_id']) is str and body['body_id'] and body['body_id'] not in seen_ids
                 and body['component_id'] == component_id and type(body['hidden']) is bool, 'Original exact body owner/visibility required.')
        seen_ids.add(body['body_id']); _ordinal(body['native_identity']); _pid(body['persistent_id']); _proof(body['native_receipt'])
        faces = body['faces']
        expected_count = (6 if role == 'variant' else 3) if body is solids[0] else 1
        _require(type(faces) is list and len(faces) == expected_count, 'Full original current normal face census required.')
        for face in faces:
            _require(type(face['object_id']) is str and face['object_id'] and face['object_id'] not in seen_faces
                     and face['component_id'] == component_id and face['body_id'] == body['body_id'], 'Current original face ID/owner required.')
            seen_faces.add(face['object_id']); _ordinal(face['native_identity']); _pid(face['persistent_id']); _proof(face['native_receipt'])
    return value


def _native_point(value, scope, *, boundary):
    value = _proof(value)
    body = scope['solid_bodies'][0]
    _require(value['component_id'] == scope['component_id'] and value['body_id'] == body['body_id']
             and value['body_native_identity'] == body['native_identity'] and value['body_persistent_id'] == body['persistent_id'],
             'Actual witness must belong to the original solid/PID/canonical.')
    local, root = vector(value['local_point_mm']), vector(value['assembly_point_mm'])
    transform = scope['info']['transform']
    close_vector(root, [transform['origin_mm'][i]+sum(local[j]*transform['axes_in_assembly'][j][i] for j in range(3)) for i in range(3)])
    _proof(value['native_receipt'])
    _require(value['point_location'] in ('boundary', 'inside') and (not boundary or value['point_location'] == 'boundary'),
             'Independent actual solid point-location proof required.')
    if value['point_location'] == 'boundary':
        faces = [face for face in body['faces'] if face['object_id'] == value['face_id']]
        _require(len(faces) == 1 and value['face_native_identity'] == faces[0]['native_identity']
                 and value['face_persistent_id'] == faces[0]['persistent_id'], 'Original trimmed-face membership required.')
    else:
        _require(value['face_id'] is None and value['face_native_identity'] is None and value['face_persistent_id'] is None,
                 'Interior zero witness must not fabricate a nearest boundary face.')
    return root


async def instance_point_axis_case(reader, *, context, instance_ids, capture_full,
                                   capture_scope, capture_witness):
    """Three sends: sqrt425 framed corner, cylinder gap2 and through-solid0.

The owner supplies explicit original variant/cylinder IDs and independent full
current assembly/parts/neighbor/UI observations. capture_scope(context, ID)
returns exact current info/raw16transform/PID/canonical model/config/parent,
solid_bodies/surface_bodies, with full original body/face PID+canonical+opaque-ID
bindings and actual native_receipt data. Missing independent opaque-ID bindings
must reject; identical names/geometry are never a substitute.

capture_witness(context, scope, result, label) returns original body/face/native
local/root point receipts (component_id, body_id, body_native_identity,
body_persistent_id, face_id, face_native_identity, face_persistent_id,
local_point_mm, assembly_point_mm, point_location, native_receipt).
For point it also proves query_point_location='outside' from actual native
classification. Positive probes require trimmed boundary incidence. Axis zero
may return an independently proved inside point with all face fields None;
public zero remains distance-only and never classifies interference.
All producers must raise on incomplete/replaced/foreign/pending observations.
"""
    context = _context(context)
    _require(type(instance_ids) is dict and set(instance_ids) == {'variant', 'cylinder'}
             and all(type(x) is str and x for x in instance_ids.values()) and len(set(instance_ids.values())) == 2,
             'Two distinct exact original held instance IDs required.')
    _require(all(callable(x) for x in (capture_full, capture_scope, capture_witness)), 'Independent original native producers required.')
    ids = deepcopy(instance_ids); before = _proof(await _call(capture_full))
    rows, probes = [], []
    cases = [('point_corner', 'variant', 'point', math.sqrt(425.)),
             ('axis_gap', 'cylinder', 'axis', 2.), ('axis_through', 'cylinder', 'axis', 0.)]
    for label, role, kind, expected in cases:
        scope = _current_scope(await _call(capture_scope, deepcopy(context), ids[role]), context, ids[role], role)
        if label == 'axis_through':
            _require(_canonical(scope) == _canonical(probes[1]['before']), 'Original cylinder scope changed between axes.')
        args = dict(request_id='b3-i10-'+uuid.uuid4().hex, **context, component_id=ids[role])
        if kind == 'point': args.update(point_mm=[30., 20., 20.], frame=deepcopy(FRAME))
        else: args.update(axis_origin_mm=[158. if label == 'axis_gap' else 150., 0., 0.], axis_direction=[0., 1., 0.], frame=None)
        tool = 'measurement_get_component_'+kind+'_distance'
        row = await reader.read(tool, args)
        rows.append(dict(tool=tool, arguments=args, journal=deepcopy(row)))
        _require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal original probe required.')
        result = row['result']
        _require(result['document_id'] == context['document_id'] and result['configuration'] == context['configuration']
                 and result['observation_revision'] == context['expected_observation_revision']
                 and result['scope'] == 'resolved_assembly_instance_reads_v1' and result['transform_target_frame'] == 'assembly_model'
                 and result['includes_hidden_components'] is True and result['implicit_resolution'] is False
                 and type(result['solid_body_count']) is int and result['solid_body_count'] == 1
                 and result['component']['component_id'] == ids[role] and result['component']['parent_component_id'] is None
                 and _canonical({k: v for k, v in result['component'].items() if k not in ('component_id', 'parent_component_id')}) == _canonical(scope['info']),
                 'Current original public component context/census differs.')
        if kind == 'point':
            check_witnesses(result, kind='point', expected_mm=expected, frame=FRAME, point_mm=args['point_mm'], expected_location='outside')
            _require(result['frame'] == FRAME and result['method'] == POINT_METHOD
                     and type(result['face_count']) is int and result['face_count'] == 6
                     and type(result['boundary_tolerance_mm']) in (int, float)
                     and math.isclose(result['boundary_tolerance_mm'], 1e-5, rel_tol=0., abs_tol=1e-15), 'Exact native point contract required.')
            close_vector(result['nearest_mm'], [20., 10., 5.])
            close_vector(result['point_assembly_mm'], [30., 40., 40.])
            close_vector(result['nearest_assembly_mm'], [40., 30., 25.])
            root_point = result['nearest_assembly_mm']
        else:
            check_witnesses(result, kind='axis', expected_mm=expected,
                axis_origin_mm=args['axis_origin_mm'], axis_direction=args['axis_direction'])
            _require(result['method'] == AXIS_METHOD and result['frame'] == dict(origin_mm=[0., 0., 0.],
                axes_in_model=[[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]), 'Exact existing root infinite-axis method/frame required.')
            root_point = result['closest_points_assembly_mm'][0]
        witness = _proof(await _call(capture_witness, deepcopy(context), deepcopy(scope), deepcopy(result), label))
        close_vector(_native_point(witness, scope, boundary=expected > 0.), root_point)
        if kind == 'point':
            _require(witness['query_point_location'] == 'outside' and result['nearest_body_id'] == witness['body_id']
                     and result['nearest_face_id'] == witness['face_id']
                     and result['body_locations'] == [dict(body_id=witness['body_id'], point_location='outside')],
                     'Native location and original nearest body/face binding required.')
        after_probe = _current_scope(await _call(capture_scope, deepcopy(context), ids[role]), context, ids[role], role)
        _require(_canonical(scope) == _canonical(after_probe), 'Complete original native scope changed during probe.')
        probes.append(dict(label=label, expected_mm=expected, before=scope, after=after_probe, witness=witness))
    after = _proof(await _call(capture_full))
    _require(_canonical(before) == _canonical(after), 'Whole current assembly/parts/neighbor/session changed.')
    return dict(scope=SCOPE, instance_ids=ids, rows=rows, probes=probes, before=before, after=after,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_owner_census_opaque_ID_and_native_location_witness_producers',
                            'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])
