"""B3-I01 sketch_get on the original same-wheel B1 rectangle; no lifecycle."""
from copy import deepcopy
import math
import uuid

from solidworks_mcp.sketches import rectangle_profile_parameters
from verifier_b3_part_geometry import _call, _canonical, _proof

SCOPE = 'bounded_b3_i01_rectangle_sketch_evidence_v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


async def rectangle_sketch_case(reader, *, context, sketch_object_id, width_mm,
                                height_mm, capture_full, capture_sketch):
    """One original B1 sketch read, retaining independent current native proofs.

capture_sketch(context, sketch_object_id) reads the original held sketch's
full snapshot and whole dimension_semantic independently, plus current exact
feature PID/canonical equality ordinal and native_receipt. It must reject
foreign/replaced anchors and prove current sketch/plane/origin/member bindings.
The exact snapshot namespaces must be bound to original native entities; an
echo of tool fields is not a native producer. capture_full covers the original
B1 part, dirty neighbor, whole session and exact single configuration.
"""
    require(type(context) is dict and set(context) == {'document_id', 'configuration'}
            and all(type(x) is str and x for x in context.values()), 'Explicit original B1 part/configuration required.')
    require(type(sketch_object_id) is str and sketch_object_id, 'Original committed B1 sketch reference required.')
    require(all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in (width_mm, height_mm)),
            'Original explicit finite positive rectangle sizes required.')
    require(callable(capture_full) and callable(capture_sketch), 'Independent current native observers required.')
    context = deepcopy(context)
    before = _proof(await _call(capture_full))
    native = _proof(await _call(capture_sketch, deepcopy(context), sketch_object_id))
    require(type(native['feature_native_identity']) is int and native['feature_native_identity'] > 0,
            'Retained canonical sketch incarnation required.')
    pid = native['feature_pid_hex']
    require(type(pid) is str and pid and bytes.fromhex(pid).hex() == pid, 'Actual current original sketch PID required.')
    _proof(native['native_receipt'])
    require(native['dimension_semantic']['tree']['document']['configurations'] == [context['configuration']],
            'Original single-configuration B1 profile required.')
    args = dict(request_id='b3-i01-sketch-'+uuid.uuid4().hex, **context, object_id=sketch_object_id)
    row = await reader.read('sketch_get', args)
    require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal current sketch read required.')
    value = row['result']
    require(value['document_id'] == context['document_id'] and value['configuration'] == context['configuration']
            and value['object_id'] == sketch_object_id and value['revision_scope'] == 'part_linear_sketch_read_v1'
            and type(value['revision']) is str and value['revision'].startswith('rev_'), 'Exact sketch read context/scope required.')
    require(value['sketch']['feature_pid_hex'] == pid
            and _canonical(value['sketch']) == _canonical(native['sketch_snapshot']),
            'Independent full current original sketch snapshot differs.')
    profile = rectangle_profile_parameters(value['sketch'], native['dimension_semantic'],
                                            context['configuration'], require_editable=False)
    require(math.isclose(profile['width_m']*1000., width_mm, rel_tol=0., abs_tol=1e-6)
            and math.isclose(profile['height_m']*1000., height_mm, rel_tol=0., abs_tol=1e-6),
            'Complete native rectangle constraints/sizes differ from original B1 dimensions.')
    closing = _proof(await _call(capture_sketch, deepcopy(context), sketch_object_id))
    require(_canonical(native) == _canonical(closing), 'Original sketch/member/configuration anchors changed.')
    after = _proof(await _call(capture_full))
    require(_canonical(before) == _canonical(after), 'Full original B1 part/neighbor/session changed.')
    return dict(scope=SCOPE, rows=[dict(tool='sketch_get', arguments=args, journal=deepcopy(row))],
        native_before=native, native_after=closing, before=before, after=after,
        accepted=False, native_acceptance=False, cleanup_authorized=False,
        open_gates=['actual_original_B1_native_producers', 'exact_installed_B3_driver', 'terminal_owned_cleanup'])
