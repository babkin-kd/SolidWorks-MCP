"""B3-I05 read-only probes after acknowledged original-owner transitions.

No delete/insert/setter/setup callback exists here. Actual native transition,
ownership and complete postcondition proofs remain an explicit open driver gate.
"""
from copy import deepcopy
import uuid

from verifier_b3_part_geometry import _call, _canonical, _context, _proof
from verifier_b3_component_membership import _ordinal, _pid, _require, _transform

SCOPE = 'bounded_b3_i05_component_reference_retirement_evidence_v1'
TOOLS = ('component_get', 'component_body_get', 'component_topology_get')
CODES = frozenset({'object_deleted', 'object_reference_invalid',
                   'component_not_in_active_configuration', 'persistent_reference_mismatch'})


def _refs(value):
    _require(type(value) is dict and set(value) == {'component_id', 'body_id', 'face_id'}
             and all(type(x) is str and x for x in value.values()) and len(set(value.values())) == 3,
             'Exact original owner-held component/body/face IDs required.')
    return deepcopy(value)


def _steps(value, phase, original, current):
    """Critical actual native receipts; not a complete transition certificate."""
    events = value['native_steps']
    _require(type(value['transition_id']) is str and value['transition_id'] and value['phase'] == phase
             and type(events) is list and 4 <= len(events) <= 32 and len(events) % 2 == 0,
             'Normally acknowledged bounded native transition receipts required.')
    labels = set()
    for index in range(0, len(events), 2):
        first, second = events[index:index+2]
        _require(all(type(event) is dict and set(event) == {'sequence', 'name', 'phase', 'evidence'}
                     and type(event['sequence']) is int and event['sequence'] == position+1
                     and type(event['evidence']) is dict and bool(event['evidence'])
                     for position, event in ((index, first), (index+1, second)))
                 and type(first['name']) is str and first['name'] and first['name'] not in labels
                 and second['name'] == first['name'] and first['phase'] == 'pending' and second['phase'] == 'returned',
                 'No missing/pending/duplicate native critical call receipt.')
        labels.add(first['name'])
    returned = {events[i]['name']: events[i]['evidence'] for i in range(1, len(events), 2)}
    _require('IModelDoc2.ForceRebuild3' in returned and returned['IModelDoc2.ForceRebuild3']['return_value'] is True,
             'Actual normally returned rebuild acknowledgement required.')
    if phase == 'deleted':
        receipt = returned.get('IModelDocExtension.DeleteSelection2')
        _require(type(receipt) is dict and receipt['return_value'] is True
                 and receipt['selected_native_identity'] == original['component_native_identity']
                 and receipt['selected_persistent_id'] == original['component_persistent_id'], 'Exact original native deletion acknowledgement required.')
    else:
        receipt = returned.get('IAssemblyDoc.AddComponent5')
        _require(type(receipt) is dict and receipt['returned_native_identity'] == current['component_native_identity']
                 and receipt['returned_persistent_id'] == current['component_persistent_id']
                 and receipt['referenced_path'] == original['referenced_path'], 'Normally returned own new incarnation/native handle required.')


def _phase(value, phase, context, old_refs, new_refs):
    value = _proof(value)
    _require(value['context'] == context and value['phase'] == phase and value['original_refs'] == old_refs
             and value['current_refs'] == new_refs and type(value['expected_errors']) is dict
             and set(value['expected_errors']) == set(TOOLS)
             and all(type(code) is str and code in CODES for code in value['expected_errors'].values()),
             'Exact fresh original-ref scope and independently selected finite errors required.')
    original = value['original']; _proof(original['native_receipt'])
    _require(type(original['referenced_path']) is str and original['referenced_path']
             and type(original['referenced_configuration']) is str and original['referenced_configuration'], 'Original retained file/config anchor required.')
    for kind in ('component', 'body', 'face'):
        _ordinal(original[kind+'_native_identity']); _pid(original[kind+'_persistent_id'])
    _ordinal(value['model_native_identity']); _ordinal(value['configuration_native_identity'])
    census = value['current_instance_census']
    _require(type(census) is list and 4 <= len(census) <= 5
             and all(type(row) is dict for row in census)
             and len({row['native_identity'] for row in census}) == len(census), 'Complete current original root instance census required.')
    for row in census:
        _ordinal(row['native_identity']); _pid(row['persistent_id']); _proof(row['native_receipt'])
    _require(all(row['native_identity'] != original['component_native_identity'] for row in census)
             and len(census) == (4 if phase == 'deleted' else 5), 'Original deleted native instance must be absent from the complete current census.')
    resolution = value['original_pid_resolution']
    _require(type(resolution) is dict and resolution['persistent_id'] == original['component_persistent_id']
             and resolution['native_identity'] != original['component_native_identity'], 'Independent original PID may not retarget its deleted canonical.')
    if resolution['native_identity'] is not None: _ordinal(resolution['native_identity'])
    _proof(resolution['native_receipt'])
    current = value['current']
    if phase == 'deleted': _require(current is None and new_refs is None, 'Deleted phase cannot adopt any replacement.')
    else:
        current = _proof(current); _proof(current['native_receipt'])
        for kind in ('component', 'body', 'face'):
            _ordinal(current[kind+'_native_identity']); _pid(current[kind+'_persistent_id'])
            _require(current[kind+'_native_identity'] != original[kind+'_native_identity'], 'Exact new native incarnation/body/face required.')
        _require(sum(row['native_identity'] == current['component_native_identity'] and row['persistent_id'] == current['component_persistent_id'] for row in census) == 1
                 and current['body_owner_native_identity'] == current['component_native_identity']
                 and current['face_owner_native_identity'] == current['body_native_identity'], 'New own original-file body/face current membership required.')
        component, body, face = current['component'], current['body'], current['face']
        _require(component['component_id'] == new_refs['component_id'] and component['referenced_path'] == original['referenced_path']
                 and component['referenced_configuration'] == original['referenced_configuration'] and component['referenced_document_type'] == 'part'
                 and component['suppression_state'] == 'resolved' and component['parent_component_id'] is None
                 and body['component_id'] == new_refs['component_id'] and body['body_id'] == new_refs['body_id'] and body['body_type'] == 'solid'
                 and face['component_id'] == new_refs['component_id'] and face['body_id'] == new_refs['body_id']
                 and face['object_id'] == new_refs['face_id'] and face['kind'] == 'face', 'Exact new current component/body/face DTO/native binding required.')
        _transform(component['transform'], current['total_transform'])
    _steps(value['transition_receipt'], phase, original, current)
    return value


async def component_retirement_phase(reader, *, phase, context, original_refs,
                                      current_refs=None, capture_full, capture_phase):
    """Read old IDs after delete, then after independent same-file reinsertion.

The caller owns the transition and supplies current context plus original held
refs and, only for reinserted, exact new owned refs. capture_phase(context,phase,
old_refs,new_refs) supplies raw critical pending/returned native receipts,
original PID/canonical/file/config anchors, model/config canonical ordinals,
complete current instance census, actual old PID resolution, independently
selected exact errors per tool and exact new body/face/native memberships.
It must raise on incomplete/unknown/pending/foreign transition observations.
capture_full observes the whole current owned assembly/parts/neighbor/UI scope.
These observers never substitute a complete=True flag, name or source baseline.
No full native transition certificate or public delete operation is claimed.
"""
    _require(phase in ('deleted', 'reinserted'), 'One explicit acknowledged owner transition phase required.')
    context = _context(context); old_refs = _refs(original_refs)
    new_refs = _refs(current_refs) if phase == 'reinserted' else None
    _require(phase != 'deleted' or current_refs is None, 'Deleted phase has no replacement refs.')
    _require(new_refs is None or set(new_refs.values()).isdisjoint(old_refs.values()), 'New incarnation cannot reuse old opaque IDs.')
    _require(callable(capture_full) and callable(capture_phase), 'Independent full/current native transition observers required.')
    before = _proof(await _call(capture_full))
    native = _phase(await _call(capture_phase, deepcopy(context), phase, deepcopy(old_refs), deepcopy(new_refs)), phase, context, old_refs, new_refs)
    rows = []
    async def read(tool, refs, error=None):
        args = dict(request_id='b3-i05-'+uuid.uuid4().hex, **context, component_id=refs['component_id'])
        if tool != 'component_get': args['body_id'] = refs['body_id']
        if tool == 'component_topology_get': args['object_id'] = refs['face_id']
        row = await reader.read(tool, args, expected_error=error)
        rows.append(dict(tool=tool, arguments=args, journal=deepcopy(row)))
        if error:
            _require(row['status'] == 'failed' and row['result'] is None and row['error']['code'] == error
                     and row['error']['requires_reconciliation'] is False, 'Exact producer-selected old reference refusal required.')
            return None
        _require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal new own incarnation read required.')
        result = row['result']
        _require(result['document_id'] == context['document_id'] and result['configuration'] == context['configuration']
                 and result['observation_revision'] == context['expected_observation_revision']
                 and result['scope'] == 'resolved_assembly_instance_reads_v1' and result['length_unit'] == 'mm'
                 and result['transform_target_frame'] == 'assembly_model' and result['implicit_resolution'] is False,
                 'Exact fresh new-incarnation scope required.')
        return result
    for tool in TOOLS: await read(tool, old_refs, native['expected_errors'][tool])
    if new_refs is not None:
        current = native['current']; component = await read('component_get', new_refs)
        body = await read('component_body_get', new_refs); face = await read('component_topology_get', new_refs)
        _require(_canonical(component['component']) == _canonical(current['component'])
                 and _canonical(body['component']) == _canonical(current['component'])
                 and body['items'] == [current['body']] and type(body['total_count']) is int and body['total_count'] == 1
                 and body['body_coordinate_frame'] == 'component_model' and body['includes_hidden_bodies'] is True
                 and _canonical(face['component']) == _canonical(current['component']) and face['object'] == current['face']
                 and face['body_id'] == new_refs['body_id'] and face['object_coordinate_frame'] == 'component_model'
                 and face['area_unit'] == 'mm2' and face['topology_scope'] == 'resolved_assembly_instance_topology_reads_v1',
                 'New same-file opaque IDs must resolve to their exact current own native instance/body/face.')
    after_native = _phase(await _call(capture_phase, deepcopy(context), phase, deepcopy(old_refs), deepcopy(new_refs)), phase, context, old_refs, new_refs)
    after = _proof(await _call(capture_full))
    _require(_canonical(native) == _canonical(after_native) and _canonical(before) == _canonical(after), 'Full current phase/native membership changed during reads.')
    return dict(scope=SCOPE, phase=phase, rows=rows, before=before, after=after, native_before=native, native_after=after_native,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_original_owner_native_transition_ownership_and_full_postconditions',
                            'independent_current_opaque_ID_PID_canonical_bridge', 'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])
