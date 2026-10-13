"""Finite B3-I03 route; live ownership and full native capture stay external.

Five explicit retained IDs are supplied by the original fixture owner. Native
producers must resolve their held canonical/PID anchors independently of the
public summaries; names and enumeration order never adopt an instance.
This is source evidence preparation, not an installed/native acceptance gate.
"""
from copy import deepcopy
import math
import uuid

from verifier_b3_part_geometry import _call, _canonical, _context, _proof

SCOPE = 'bounded_b3_i03_component_membership_evidence_v1'
ROLES = ('main', 'variant', 'nested', 'parent', 'cylinder')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _ordinal(value):
    _require(type(value) is int and value > 0, 'Retained canonical equality ordinal required.')
    return value


def _pid(value):
    _require(type(value) is str and bool(value), 'Current exact native PID required.')
    _require(bytes.fromhex(value).hex() == value, 'Canonical bytes.hex PID required.')
    return value


def _near(value, expected, tolerance=1e-9):
    _require(type(value) in (float, int) and math.isfinite(value)
             and math.isclose(value, expected, rel_tol=0., abs_tol=tolerance),
             'Full independent native transform differs.')


def _transform(value, raw):
    _require(type(raw) is list and len(raw) == 16
             and all(type(x) in (float, int) and math.isfinite(x) for x in raw),
             'Complete GetTotalTransform(False).ArrayData required.')
    _require(type(value) is dict and set(value) == {'origin_mm', 'axes_in_assembly', 'parity',
             'scale', 'includes_presentation_transform'} and value['parity'] == 'right_handed'
             and value['includes_presentation_transform'] is False, 'Existing rigid component transform scope required.')
    axes, origin = value['axes_in_assembly'], value['origin_mm']
    _require(type(axes) is list and len(axes) == 3 and all(type(a) is list and len(a) == 3 for a in axes)
             and type(origin) is list and len(origin) == 3, 'Full axes/origin required.')
    _near(value['scale'], 1.)
    _near(raw[12], 1.)
    for x in raw[13:]: _near(x, 0.)
    for i in range(3):
        _near(origin[i], raw[9+i]*1000., 1e-6)
        for j in range(3):
            _near(axes[i][j], raw[3*i+j])
            _near(sum(raw[3*i+k]*raw[3*j+k] for k in range(3)), float(i == j))
    a, b, c = raw[:3], raw[3:6], raw[6:9]
    _near(sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3)), 1.)


async def component_membership_case(reader, *, context, foreign_root_context, part_context,
                                    instance_ids, part_body_id, capture_full,
                                    capture_instance, capture_reference):
    """One original five-instance profile, three repeated-file part instances.

capture_full() must observe the complete owned assembly, referenced parts and
dirty neighbor/session (including active part configs, selection/view/files/UI),
raising on incomplete scope. No complete=True assertion is a substitute.

capture_instance(context, component) returns independently read component_info
(the actual native info fields, excluding opaque IDs/parent ID), raw 16-value
total_transform, PID and canonical equality ordinals native_identity,
model_identity, configuration_identity, parent_native_identity (None at root),
plus native_receipt. The trusted owner confirms held PID/current membership.

capture_reference(context, component, item) returns actual summary excluding
opaque component/body/object IDs, PID/native_identity and exact
owner_component_native_identity/owner_body_native_identity, plus native_receipt.
Body owner_body_native_identity equals its own identity; topology equals its
current held body's identity. Producers must reject replaced/foreign anchors.
Ordinals represent held IUnknown equality, never names or pointer serialization.
"""
    context, foreign_root_context, part_context = map(_context, (context, foreign_root_context, part_context))
    _require(len({x['document_id'] for x in (context, foreign_root_context, part_context)}) == 3,
             'Distinct explicit root/foreign-root/part contexts required.')
    _require(type(instance_ids) is dict and set(instance_ids) == set(ROLES)
             and all(type(x) is str and x for x in instance_ids.values())
             and len(set(instance_ids.values())) == 5, 'Five exact original owner-held IDs required.')
    _require(type(part_body_id) is str and part_body_id, 'Original independent part body reference required.')
    _require(all(callable(x) for x in (capture_full, capture_instance, capture_reference)),
             'Independent full/current-instance/current-reference producers required.')
    instance_ids = deepcopy(instance_ids)
    before = _proof(await _call(capture_full))
    rows, native_instances, native_refs = [], {}, []

    async def read(tool, *, ctx=None, error=None, **args):
        ctx = context if ctx is None else ctx
        args = dict(request_id='b3-i03-'+uuid.uuid4().hex, **ctx, **args)
        row = await reader.read(tool, args, expected_error=error)
        rows.append(dict(tool=tool, arguments=args, journal=deepcopy(row)))
        if error is not None:
            _require(row['status'] == 'failed' and row['result'] is None
                     and row['error']['code'] == error and row['error']['requires_reconciliation'] is False,
                     'Exact finite membership refusal required.')
            return None
        _require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal component read required.')
        value = row['result']
        _require(value['document_id'] == ctx['document_id'] and value['configuration'] == ctx['configuration']
                 and value['observation_revision'] == ctx['expected_observation_revision']
                 and value['scope'] == 'resolved_assembly_instance_reads_v1' and value['length_unit'] == 'mm'
                 and value['transform_target_frame'] == 'assembly_model'
                 and value['includes_hidden_components'] is True and value['implicit_resolution'] is False,
                 'Exact current component observation/frame/scope required.')
        return value

    census = await read('component_list', limit=100, cursor='')
    components = census['items']
    _require(type(census['total_count']) is int and census['total_count'] == 5
             and census['next_cursor'] is None and type(components) is list and len(components) == 5
             and {row['component_id'] for row in components} == set(instance_ids.values()),
             'Complete exact original instance census required; no roster adoption.')
    by_id = {row['component_id']: row for row in components}
    by_role = {role: by_id[key] for role, key in instance_ids.items()}
    for role, item in by_role.items():
        got = await read('component_get', component_id=item['component_id'])
        _require(_canonical(got['component']) == _canonical(item), 'Original instance list/get differs.')
        receipt = _proof(await _call(capture_instance, deepcopy(context), deepcopy(item)))
        _require(_canonical(receipt['component_info']) == _canonical({key: value for key, value in item.items()
                 if key not in ('component_id', 'parent_component_id')}), 'Actual native instance facts differ.')
        _pid(receipt['persistent_id'])
        for key in ('native_identity', 'model_identity', 'configuration_identity'): _ordinal(receipt[key])
        _proof(receipt['native_receipt'])
        _transform(item['transform'], receipt['total_transform'])
        native_instances[role] = receipt
    _require(len({x['native_identity'] for x in native_instances.values()}) == 5
             and len({x['persistent_id'] for x in native_instances.values()}) == 5, 'Distinct original instances/PIDs required.')
    repeated = [by_role[x] for x in ('main', 'variant', 'nested')]
    _require(len({x['referenced_path'] for x in repeated}) == 1 and repeated[0]['referenced_path']
             and [x['referenced_configuration'] for x in repeated] == ['Основная', 'Вариант', 'Основная']
             and all(x['referenced_document_type'] == 'part' for x in repeated), 'Exact repeated-file/two-config fixture required.')
    _require(len({native_instances[x]['model_identity'] for x in ('main', 'variant', 'nested')}) == 1
             and native_instances['main']['configuration_identity'] == native_instances['nested']['configuration_identity']
             and native_instances['main']['configuration_identity'] != native_instances['variant']['configuration_identity'],
             'Same held native model and distinct exact referenced configs required.')
    parent, nested = by_role['parent'], by_role['nested']
    _require(parent['referenced_document_type'] == 'assembly' and parent['parent_component_id'] is None
             and nested['parent_component_id'] == parent['component_id']
             and nested['component_path'].rsplit('/', 1)[0] == parent['component_path']
             and native_instances['nested']['parent_native_identity'] == native_instances['parent']['native_identity']
             and all(by_role[x]['parent_component_id'] is None and native_instances[x]['parent_native_identity'] is None
                     for x in ('main', 'variant', 'parent', 'cylinder')), 'Exact nested parent canonical/path required.')
    for role, origin in (('main', (0., 0., 0.)), ('variant', (50., 10., 20.)), ('nested', (130., 0., 0.))):
        for actual, expected in zip(by_role[role]['transform']['origin_mm'], origin): _near(actual, expected, 1e-6)

    async def reference(role, item, body_identity=None):
        receipt = _proof(await _call(capture_reference, deepcopy(context), deepcopy(by_role[role]), deepcopy(item)))
        _pid(receipt['persistent_id']); identity = _ordinal(receipt['native_identity'])
        _require(receipt['owner_component_native_identity'] == native_instances[role]['native_identity']
                 and receipt['owner_body_native_identity'] == (identity if body_identity is None else body_identity)
                 and _canonical(receipt['summary']) == _canonical({k: v for k, v in item.items()
                     if k not in ('object_id', 'body_id', 'component_id')}), 'Exact current native owner/summary required.')
        _proof(receipt['native_receipt']); native_refs.append(dict(component_id=by_role[role]['component_id'], item=item, receipt=receipt))
        return identity

    bodies_by_role, targets = {}, {}
    all_ids = set()
    for role, count in (('main', 3), ('variant', 2), ('nested', 3)):
        component = by_role[role]; component_id = component['component_id']
        result = await read('component_body_list', component_id=component_id)
        bodies = result['items']
        _require(result['component'] == component and result['body_coordinate_frame'] == 'component_model'
                 and result['includes_hidden_bodies'] is True and result['body_type'] == 'all'
                 and type(result['total_count']) is int and result['total_count'] == count
                 and type(bodies) is list and len(bodies) == count
                 and sum(x['body_type'] == 'surface' for x in bodies) == 1
                 and sum(x['body_type'] == 'solid' for x in bodies) == count-1,
                 'Complete exact referenced-configuration body roster required.')
        bodies_by_role[role] = bodies
        for body in bodies:
            body_id = body['body_id']
            _require(type(body_id) is str and body_id and body_id not in all_ids
                     and body_id != part_body_id and body['component_id'] == component_id,
                     'Distinct part/instance body IDs and exact owner required.')
            all_ids.add(body_id)
            got = await read('component_body_get', component_id=component_id, body_id=body_id)
            _require(got['component'] == component and got['items'] == [body] and got['total_count'] == 1
                     and got['body_coordinate_frame'] == 'component_model' and got['includes_hidden_bodies'] is True,
                     'Exact original body roundtrip required.')
            identity = await reference(role, body)
            if body['body_type'] != 'solid' or role in targets: continue
            targets[role] = body
            for kind, tool, size in (('face', 'component_face_list', body['face_count']),
                                     ('edge', 'component_edge_list', body['edge_count'])):
                page = await read(tool, component_id=component_id, body_id=body_id, limit=100, cursor='')
                _require(type(size) is int and 0 < size <= 100 and page['kind'] == kind
                         and page['component'] == component and page['body_id'] == body_id
                         and page['topology_scope'] == 'resolved_assembly_instance_topology_reads_v1'
                         and page['object_coordinate_frame'] == 'component_model' and page['area_unit'] == 'mm2'
                         and page['total_count'] == size and type(page['total_count']) is int
                         and page['next_cursor'] is None and len(page['items']) == size,
                         'Complete current local topology census required.')
                for item in page['items']:
                    object_id = item['object_id']
                    _require(type(object_id) is str and object_id and object_id not in all_ids
                             and item['component_id'] == component_id and item['body_id'] == body_id and item['kind'] == kind,
                             'Exact topology owner/kind/reference required.')
                    all_ids.add(object_id); await reference(role, item, identity)
                item = page['items'][0]
                got = await read('component_topology_get', component_id=component_id, body_id=body_id, object_id=item['object_id'])
                _require(got['object'] == item and got['component'] == component and got['body_id'] == body_id
                         and got['object_coordinate_frame'] == 'component_model' and got['area_unit'] == 'mm2'
                         and got['topology_scope'] == page['topology_scope'], 'Exact topology list/get roundtrip required.')
                if role == 'variant' and kind == 'face': foreign_face = item['object_id']
    await read('component_body_get', component_id=instance_ids['main'], body_id=targets['variant']['body_id'], error='object_component_mismatch')
    await read('component_topology_get', component_id=instance_ids['main'], body_id=targets['main']['body_id'], object_id=foreign_face, error='object_component_mismatch')
    await read('component_body_get', component_id=instance_ids['main'], body_id=part_body_id, error='component_body_reference_not_found')
    await read('component_get', ctx=foreign_root_context, component_id=instance_ids['main'], error='component_reference_not_found')
    await read('component_body_get', ctx=part_context, component_id=instance_ids['main'], body_id=targets['main']['body_id'], error='unsupported_document_type')
    after = _proof(await _call(capture_full))
    _require(_canonical(before) == _canonical(after), 'Full original assembly/parts/neighbor/session changed.')
    return dict(scope=SCOPE, rows=rows, instance_ids=instance_ids, native_instances=native_instances,
                native_references=native_refs, before=before, after=after, accepted=False,
                native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_owner_native_producers', 'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])
