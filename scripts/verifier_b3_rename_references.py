"""B3-I04 post-rename reference continuity; native rename/lifecycle stay external."""
from copy import deepcopy
import uuid

from solidworks_mcp.features import russian_name
from verifier_b3_part_geometry import _call, _canonical, _context, _proof
from verifier_b3_component_membership import _ordinal, _pid, _require

SCOPE = 'bounded_b3_i04_rename_reference_evidence_v1'


def anchor(proof, *, context):
    """Raw current original-PID resolution, never a boolean identity certificate."""
    _proof(proof)
    _require(proof['document_id'] == context['document_id'] and proof['configuration'] == context['configuration'],
             'Exact original document/configuration owner required.')
    original, current = _ordinal(proof['original_native_identity']), _ordinal(proof['current_native_identity'])
    _require(original == current, 'Original canonical native incarnation must survive rename.')
    _pid(proof['original_pid_hex']); _pid(proof['current_pid_hex'])
    resolution = proof['original_pid_resolution']
    _require(type(resolution['native_state']) is int and resolution['native_state'] == 0
             and resolution['resolved_native_identity'] == current
             and resolution['returned_pid_hex'] == proof['current_pid_hex'], 'Actual old PID must resolve to the retained current object.')
    _proof(proof['native_receipt'])
    return current


async def rename_references_case(reader, *, part_context, assembly_context, original_refs,
                                  expected_names, capture_full, capture_references):
    """Three passive reads after acknowledged original-owner rename operations.

The caller supplies the original feature/instance/body/face IDs. Native rename
receipts and exact allowed-change scope proof remain explicit external gates.
capture_references(part_context, assembly_context, refs) independently reads
feature/component/body/face summaries and original/current canonical/PID anchors
in the schema checked by anchor(). It proves current native owner membership;
it cannot echo tool results or adopt an object by name. A current PID alias may
differ from the original bytes only with raw old-PID/current-identity proof.
capture_full covers complete current owned parts/assembly/neighbor/session.
"""
    _require(type(part_context) is dict and set(part_context) == {'document_id', 'configuration'}
             and all(type(x) is str and x for x in part_context.values()), 'Explicit original part context required.')
    assembly_context = _context(assembly_context)
    _require(part_context['document_id'] != assembly_context['document_id'], 'Distinct original part and root assembly required.')
    _require(type(original_refs) is dict and set(original_refs) == {'feature_id', 'component_id', 'body_id', 'face_id'}
             and all(type(x) is str and x for x in original_refs.values()), 'Exact original retained object references required.')
    _require(type(expected_names) is dict and set(expected_names) == {'feature', 'component'}, 'Exact acknowledged native rename results required.')
    for name in expected_names.values(): russian_name(name)
    _require(callable(capture_full) and callable(capture_references), 'Independent current native observers required.')
    part_context, refs, names = deepcopy(part_context), deepcopy(original_refs), deepcopy(expected_names)
    before = _proof(await _call(capture_full))
    native = _proof(await _call(capture_references, deepcopy(part_context), deepcopy(assembly_context), deepcopy(refs)))
    _require(set(native) == {'feature', 'component', 'body', 'face'}, 'Complete original reference proof set required.')
    anchor(native['feature'], context=part_context)
    component_identity = anchor(native['component'], context=assembly_context)
    body_identity = anchor(native['body'], context=assembly_context)
    anchor(native['face'], context=assembly_context)
    _require(_ordinal(native['feature']['owner_model_native_identity'])
             == _ordinal(native['component']['referenced_model_native_identity']),
             'Feature must belong to the original retained referenced part model.')
    _require(native['feature']['original_object_id'] == refs['feature_id']
             and native['component']['original_object_id'] == refs['component_id']
             and native['body']['original_object_id'] == refs['body_id']
             and native['face']['original_object_id'] == refs['face_id']
             and native['body']['owner_component_native_identity'] == component_identity
             and native['face']['owner_component_native_identity'] == component_identity
             and native['face']['owner_body_native_identity'] == body_identity,
             'Original opaque IDs and actual current native owner chain required.')
    _require(native['feature']['summary']['name'] == names['feature']
             and native['component']['summary']['component_path'] == names['component'], 'Exact original own Russian rename results differ.')
    rows = []
    async def read(tool, context, **arguments):
        args = dict(request_id='b3-i04-'+uuid.uuid4().hex, **context, **arguments)
        row = await reader.read(tool, args)
        _require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal original reference resolution required.')
        rows.append(dict(tool=tool, arguments=args, journal=deepcopy(row)))
        value = row['result']
        _require(value['document_id'] == context['document_id'] and value['configuration'] == context['configuration'], 'Exact explicit original owner context required.')
        return value
    feature = await read('feature_get', part_context, object_id=refs['feature_id'])
    _require(feature['revision_scope'] == 'part_feature_tree_v1' and feature['feature']['object_id'] == refs['feature_id']
             and _canonical({k: v for k, v in feature['feature'].items() if k != 'object_id'}) == _canonical(native['feature']['summary']),
             'Original feature ref must resolve to the exact current native summary.')
    component = await read('component_get', assembly_context, component_id=refs['component_id'])
    face = await read('component_topology_get', assembly_context, component_id=refs['component_id'], body_id=refs['body_id'], object_id=refs['face_id'])
    for value in (component, face):
        _require(value['observation_revision'] == assembly_context['expected_observation_revision']
                 and value['scope'] == 'resolved_assembly_instance_reads_v1'
                 and value['component']['component_id'] == refs['component_id']
                 and _canonical({k: v for k, v in value['component'].items() if k not in ('component_id', 'parent_component_id')}) == _canonical(native['component']['summary']),
                 'Original instance ref must resolve to the exact current native summary.')
    _require(face['body_id'] == refs['body_id'] and face['object']['object_id'] == refs['face_id']
             and face['object']['component_id'] == refs['component_id'] and face['object']['body_id'] == refs['body_id']
             and _canonical({k: v for k, v in face['object'].items() if k not in ('object_id', 'component_id', 'body_id')}) == _canonical(native['face']['summary']),
             'Original face/body owner and full current native facts differ.')
    closing = _proof(await _call(capture_references, deepcopy(part_context), deepcopy(assembly_context), deepcopy(refs)))
    after = _proof(await _call(capture_full))
    _require(_canonical(native) == _canonical(closing) and _canonical(before) == _canonical(after), 'Complete current original native references/session changed during reads.')
    return dict(scope=SCOPE, rows=rows, native_before=native, native_after=closing, before=before, after=after,
        accepted=False, native_acceptance=False, cleanup_authorized=False,
        open_gates=['acknowledged_native_rename_receipts_and_exact_allowed_change_scope',
                    'actual_original_current_native_producers', 'exact_installed_B3_driver', 'terminal_owned_cleanup'])
