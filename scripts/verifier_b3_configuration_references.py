"""B3-I06 passive current-reference probes, never configuration setters."""
from copy import deepcopy
import uuid

from verifier_b3_part_geometry import _call, _canonical, _context, _proof
from verifier_b3_component_membership import _ordinal, _pid, _require, _transform
from verifier_b3_component_retirement import _refs, TOOLS

SCOPE = 'bounded_b3_i06_configuration_reference_evidence_v1'
INSTANCE_CODES = frozenset({'component_reference_context_changed', 'persistent_reference_mismatch'})


def _transition(value, method, native_identity, configuration):
    """Critical raw returned calls; complete ownership/setup gate stays open."""
    _proof(value); events = value['native_steps']
    _require(type(value['transition_id']) is str and value['transition_id'] and type(events) is list
             and 2 <= len(events) <= 32 and len(events) % 2 == 0, 'Bounded acknowledged native transition receipts required.')
    names = set(); returned = {}
    for index in range(0, len(events), 2):
        a, b = events[index:index+2]
        _require(all(type(row) is dict and set(row) == {'sequence', 'name', 'phase', 'evidence'}
                     and type(row['sequence']) is int and row['sequence'] == offset+1
                     and type(row['evidence']) is dict and bool(row['evidence'])
                     for offset, row in ((index, a), (index+1, b)))
                 and type(a['name']) is str and a['name'] and a['name'] not in names
                 and b['name'] == a['name'] and a['phase'] == 'pending' and b['phase'] == 'returned',
                 'Pending/missing/duplicate native transition receipts prohibited.')
        names.add(a['name']); returned[a['name']] = b['evidence']
    receipt = returned.get(method)
    _require(type(receipt) is dict and receipt['readback_configuration'] == configuration,
             'Actual native current configuration readback required.')
    if method == 'IComponent2.ReferencedConfiguration':
        _require(receipt['owner_native_identity'] == native_identity and receipt['requested_configuration'] == configuration,
                 'Exact retained original instance configuration setter acknowledgement required.')
    elif method == 'IModelDoc2.ShowConfiguration2':
        _require(receipt['owner_native_identity'] == native_identity and receipt['return_value'] is True,
                 'Normally returned original part configuration acknowledgement required.')
    else:
        _require(method == 'IModelDoc2.AddConfiguration3' and receipt['returned_native_identity'] == native_identity,
                 'Normally returned original part new configuration incarnation required.')
    if 'IModelDoc2.ForceRebuild3' in returned:
        _require(returned['IModelDoc2.ForceRebuild3']['return_value'] is True, 'Native rebuild must normally acknowledge True.')


def _instance(value, context, old, new):
    value = _proof(value)
    _require(value['context'] == context and value['original_refs'] == old and value['current_refs'] == new
             and type(value['expected_errors']) is dict and set(value['expected_errors']) == set(TOOLS)
             and all(code in INSTANCE_CODES for code in value['expected_errors'].values()), 'Exact current original-ref scope/finite errors required.')
    before, current = value['original'], value['current']; _proof(before['native_receipt']); _proof(current['native_receipt'])
    for row in (before, current):
        for key in ('instance_native_identity', 'model_native_identity', 'configuration_native_identity', 'root_configuration_native_identity'): _ordinal(row[key])
        _pid(row['instance_persistent_id'])
    _require(before['instance_native_identity'] == current['instance_native_identity']
             and before['model_native_identity'] == current['model_native_identity']
             and before['root_configuration_native_identity'] == current['root_configuration_native_identity']
             and before['instance_persistent_id'] == current['instance_persistent_id']
             and before['configuration_native_identity'] != current['configuration_native_identity']
             and before['referenced_configuration'] == 'Вариант' and current['referenced_configuration'] == 'Основная'
             and before['referenced_path'] == current['component']['referenced_path']
             and current['component']['component_id'] == new['component_id']
             and current['component']['referenced_configuration'] == 'Основная'
             and current['component']['referenced_document_type'] == 'part'
             and current['component']['parent_component_id'] is None and current['component']['suppression_state'] == 'resolved',
             'Same exact original native instance/model/PID with changed referenced config required.')
    _transform(current['component']['transform'], current['total_transform'])
    _require(type(before['bodies']) is list and len(before['bodies']) == 2
             and sum(row['body_type'] == 'solid' for row in before['bodies']) == 1
             and sum(row['body_type'] == 'surface' for row in before['bodies']) == 1
             and type(current['bodies']) is list and len(current['bodies']) == 3
             and sum(row['body_type'] == 'solid' for row in current['bodies']) == 2
             and sum(row['body_type'] == 'surface' for row in current['bodies']) == 1
             and len({row['body_id'] for row in current['bodies']}) == 3, 'Exact original2→current3 complete normal body census required.')
    for body in current['bodies']:
        _require(body['component_id'] == new['component_id'] and type(body['body_id']) is str and body['body_id'], 'Exact current instance body owner required.')
    _require(type(current['body_bindings']) is list and len(current['body_bindings']) == 3
             and {body['body_id'] for body in current['body_bindings']} == {body['body_id'] for body in current['bodies']}, 'Independent full current body PID/canonical bindings required.')
    for body in current['body_bindings']:
        _ordinal(body['native_identity']); _pid(body['persistent_id']); _proof(body['native_receipt'])
        _require(body['owner_native_identity'] == current['instance_native_identity'], 'Current original native instance body membership required.')
    face = current['face']; binding = current['face_binding']
    _require(face['object_id'] == new['face_id'] and face['body_id'] == new['body_id'] and face['component_id'] == new['component_id']
             and face['kind'] == 'face' and new['body_id'] in {body['body_id'] for body in current['bodies']}, 'Exact current original face owner required.')
    _ordinal(binding['native_identity']); _pid(binding['persistent_id']); _proof(binding['native_receipt'])
    body = next(body for body in current['body_bindings'] if body['body_id'] == new['body_id'])
    _require(binding['owner_native_identity'] == body['native_identity'], 'Actual current face parent canonical required.')
    _transition(value['transition_receipt'], 'IComponent2.ReferencedConfiguration', before['instance_native_identity'], 'Основная')
    return value


async def component_configuration_phase(reader, *, context, original_refs, current_refs, capture_full, capture_phase):
    """After owner changes original root variant instance to Основная: nine reads.

capture_phase(context,old_refs,new_refs) must independently bind the same held
original instance/model/PID/root config, old Вариант and current Основная config
canonicals, old two-body census, actual current three-body DTOs+PID/canonical
bindings and current representative face/owner, raw16total_transform, exact
finite expected_errors per old-ref tool and acknowledged native transition
receipts. Full native scope and complete transition postconditions stay with
the owner; neither names nor complete=True can replace these observations.
capture_full observes all current owned models/configs/geometry/UI/session.
"""
    context = _context(context); old, new = _refs(original_refs), _refs(current_refs)
    _require(set(old.values()).isdisjoint(new.values()) and callable(capture_full) and callable(capture_phase), 'Fresh current original-owner reference bindings and observers required.')
    before = _proof(await _call(capture_full)); native = _instance(await _call(capture_phase, deepcopy(context), deepcopy(old), deepcopy(new)), context, old, new)
    rows = []
    async def read(tool, error=None, **arguments):
        args = dict(request_id='b3-i06-instance-'+uuid.uuid4().hex, **context, **arguments)
        row = await reader.read(tool, args, expected_error=error); rows.append(dict(tool=tool, arguments=args, journal=deepcopy(row)))
        if error:
            _require(row['status'] == 'failed' and row['result'] is None and row['error']['code'] == error
                     and row['error']['requires_reconciliation'] is False, 'Exact producer-selected old-reference failure required.')
            return None
        _require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal current original-instance read required.')
        value = row['result']
        _require(value['document_id'] == context['document_id'] and value['configuration'] == context['configuration']
                 and value['observation_revision'] == context['expected_observation_revision'] and value['scope'] == 'resolved_assembly_instance_reads_v1'
                 and value['length_unit'] == 'mm' and value['transform_target_frame'] == 'assembly_model' and value['implicit_resolution'] is False,
                 'Exact fresh original assembly configuration context required.')
        return value
    await read('component_get', native['expected_errors']['component_get'], component_id=old['component_id'])
    await read('component_body_get', native['expected_errors']['component_body_get'], component_id=old['component_id'], body_id=old['body_id'])
    await read('component_topology_get', native['expected_errors']['component_topology_get'], component_id=old['component_id'], body_id=old['body_id'], object_id=old['face_id'])
    current = native['current']; component = await read('component_get', component_id=new['component_id'])
    _require(component['component'] == current['component'], 'Current original instance metadata differs.')
    bodies = await read('component_body_list', component_id=new['component_id'])
    _require(bodies['component'] == current['component'] and bodies['body_coordinate_frame'] == 'component_model'
             and bodies['includes_hidden_bodies'] is True and type(bodies['total_count']) is int and bodies['total_count'] == 3
             and _canonical(bodies['items']) == _canonical(current['bodies']), 'Actual full Main body census differs.')
    for body in current['bodies']:
        result = await read('component_body_get', component_id=new['component_id'], body_id=body['body_id'])
        _require(result['component'] == current['component'] and result['items'] == [body]
                 and type(result['total_count']) is int and result['total_count'] == 1 and result['body_coordinate_frame'] == 'component_model', 'Current exact original body roundtrip differs.')
    face = await read('component_topology_get', component_id=new['component_id'], body_id=new['body_id'], object_id=new['face_id'])
    _require(face['component'] == current['component'] and face['object'] == current['face'] and face['body_id'] == new['body_id']
             and face['object_coordinate_frame'] == 'component_model' and face['area_unit'] == 'mm2'
             and face['topology_scope'] == 'resolved_assembly_instance_topology_reads_v1', 'Current exact original face roundtrip differs.')
    after_native = _instance(await _call(capture_phase, deepcopy(context), deepcopy(old), deepcopy(new)), context, old, new)
    after = _proof(await _call(capture_full)); _require(_canonical(native) == _canonical(after_native) and _canonical(before) == _canonical(after), 'Whole current original configuration phase changed.')
    return dict(scope=SCOPE, phase='owner_referenced_configuration_changed', rows=rows, before=before, after=after, native_before=native, native_after=after_native,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_owner_native_setup_ownership_and_full_transition_postconditions', 'independent_current_opaque_ID_PID_canonical_bridge',
                            'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])


async def part_configuration_phase(reader, *, context, original_body_id, inactive_configuration, capture_full, capture_phase):
    """Two finite reads after owner part config change/incarnation replacement.

capture_phase(context,old_body_id,inactive_configuration) binds original/current
same model canonical, old/current configuration canonicals/names, original body
PID/canonical and actual complete current normal-body census (Variant2/Main3),
actual active_configuration, current PID/canonical body bindings, transition
method+raw returned receipts. Inactive geometry must never activate anything.
No native transition/setup helper is called; current context is caller-owned.
"""
    context = _context(context)
    _require(type(original_body_id) is str and original_body_id and type(inactive_configuration) is str
             and inactive_configuration and inactive_configuration != context['configuration']
             and callable(capture_full) and callable(capture_phase), 'Explicit original part/current inactive configuration and observers required.')
    before = _proof(await _call(capture_full))
    def validate(value):
        value = _proof(value); old, new = value['original'], value['current']
        _require(value['context'] == context and value['original_body_id'] == original_body_id
                 and value['inactive_configuration'] == inactive_configuration and value['active_configuration'] == context['configuration']
                 and old['model_native_identity'] == new['model_native_identity']
                 and old['configuration_native_identity'] != new['configuration_native_identity']
                 and old['object_id'] == original_body_id and old['configuration'] in ('Основная', 'Вариант')
                 and old['reference_configuration_native_identity'] == old['configuration_native_identity']
                 and new['configuration'] == context['configuration']
                 and value['expected_errors'] == dict(geometry_get='object_configuration_mismatch', body_list='configuration_not_active'),
                 'Actual current original part/config incarnation and exact finite refusal scope required.')
        for row in (old, new):
            _ordinal(row['model_native_identity']); _ordinal(row['configuration_native_identity']); _proof(row['native_receipt'])
        _pid(old['body_persistent_id']); _ordinal(old['body_native_identity'])
        count = 2 if context['configuration'] == 'Вариант' else 3 if context['configuration'] == 'Основная' else None
        bodies = new['bodies']
        _require(count is not None and type(bodies) is list and len(bodies) == count
                 and len({row['object_id'] for row in bodies}) == count
                 and sum(row['body_type'] == 'solid' for row in bodies) == count-1
                 and sum(row['body_type'] == 'surface' for row in bodies) == 1
                 and type(new['body_bindings']) is list and len(new['body_bindings']) == count
                 and {row['object_id'] for row in new['body_bindings']} == {row['object_id'] for row in bodies}, 'Actual full current part normal-body census/PID bindings required.')
        for body in new['body_bindings']:
            _ordinal(body['native_identity']); _pid(body['persistent_id']); _proof(body['native_receipt'])
            _require(body['model_native_identity'] == new['model_native_identity'], 'Exact original part body ownership required.')
        method = value['transition_method']
        _require(method in ('IModelDoc2.ShowConfiguration2', 'IModelDoc2.AddConfiguration3'), 'Actual finite native part configuration transition required.')
        _transition(value['transition_receipt'], method, new['model_native_identity'] if method.endswith('ShowConfiguration2') else new['configuration_native_identity'], context['configuration'])
        return value
    native = validate(await _call(capture_phase, deepcopy(context), original_body_id, inactive_configuration)); rows = []
    for tool, args, code in (('geometry_get', dict(object_id=original_body_id), 'object_configuration_mismatch'),
                            ('body_list', dict(body_type='all', limit=100, cursor=''), 'configuration_not_active')):
        ctx = context if tool == 'geometry_get' else {**context, 'configuration': inactive_configuration}
        arguments = dict(request_id='b3-i06-part-'+uuid.uuid4().hex, **ctx, **args)
        row = await reader.read(tool, arguments, expected_error=code); rows.append(dict(tool=tool, arguments=arguments, journal=deepcopy(row)))
        _require(row['status'] == 'failed' and row['result'] is None and row['error']['code'] == code and row['error']['requires_reconciliation'] is False,
                 'Exact old part reference/inactive geometry refusal required.')
    after_native = validate(await _call(capture_phase, deepcopy(context), original_body_id, inactive_configuration)); after = _proof(await _call(capture_full))
    _require(_canonical(native) == _canonical(after_native) and _canonical(before) == _canonical(after), 'Current full part/neighbor/session or active config changed.')
    return dict(scope=SCOPE, phase='owner_part_configuration_changed', rows=rows, before=before, after=after, native_before=native, native_after=after_native,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_owner_native_setup_ownership_and_full_transition_postconditions', 'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])
