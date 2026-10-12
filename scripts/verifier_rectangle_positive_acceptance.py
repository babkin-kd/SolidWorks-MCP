"""Passive exact-wheel positive gate before the remaining B1 native cases.

Passing this gate proves report coherence only. Native evidence comes from the
trusted installed driver and independent CAD readback, never these checks alone.
"""
import math

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_snapshot import validated_rectangle_snapshot, SKETCH, BASE
from verifier_rectangle_stages import verified_rectangle_job


POSITIVE_LABELS = (
    'B1-N1-separate-sketch-and-replay',
    'B1-N1-separate-extrusion-and-replay',
    'B1-N2-N3-exact-native-base-and-neighbor',
    'B1-owned-cleanup-baseline',
)


def validate_positive_report(prior, wheel, verifier_hashes):
    """Return detached evidence; reject before any native connection."""
    def require(condition, message):
        if not condition: raise ValueError(message)
    try:
        _json(prior); _json(wheel); _json(verifier_hashes)
        require(type(prior) is dict and prior.get('scope') == 'installed_rectangle_stages_positive_only',
            'Exact rectangle positive report required.')
        require(prior.get('accepted') is False and prior.get('positive_case_passed') is True
            and prior.get('phase') == 'terminal' and prior.get('native_calls_live') is False
            and prior.get('retained_process', False) is False,
            'Only terminal passed positive evidence authorizes later B1 cases.')
        require(_json(prior['wheel']) == _json(wheel) and prior['package_origin_verified'] is True,
            'Positive evidence belongs to another installed wheel.')
        require(type(verifier_hashes) is dict and bool(verifier_hashes)
            and prior['verifier_hashes'] == verifier_hashes,
            'Positive evidence belongs to different trusted helpers.')
        for key in ('own_cleanup_verified', 'baseline_restored', 'independent_native_readback_verified'):
            require(prior.get(key) is True, 'Positive proof or owned cleanup is incomplete.')
        require(type(prior['owned_documents']) is list and not prior['owned_documents']
            and _json(prior['restored_baseline']) == _json(prior['original_baseline'])
            and _json(prior['restored_application']) == _json(prior['original_application']),
            'Complete original session baseline must be restored.')
        cases = prior['cases']
        require(type(cases) is list and [row.get('label') for row in cases] == list(POSITIVE_LABELS)
            and all(row.get('passed') is True for row in cases),
            'Exact finite positive case manifest required.')
        captures = prior['captures']
        require(type(captures) is list and bool(captures)
            and all(type(row) is dict and row.get('status') == 'returned' for row in captures),
            'All observed native captures must have returned.')
        for key in ('sketch_job', 'extrusion_job'):
            require(verified_rectangle_job(prior[key]), 'Exact committed stage journal proof required.')
        sketch, extrusion = prior['sketch_job'], prior['extrusion_job']
        require(sketch['operation'] == 'sketch.create_rectangle'
            and extrusion['operation'] == 'part.extrude_rectangle'
            and sketch['payload']['arguments']['document_id'] == extrusion['payload']['arguments']['document_id']
            and extrusion['payload']['arguments']['sketch_object_id'] == sketch['result']['value']['sketch_object_id'],
            'Extrusion must borrow the exact returned sketch of this positive chain.')
        separate = validated_rectangle_snapshot(prior['independent_sketch'])
        base = validated_rectangle_snapshot(prior['independent_base'])
        require(separate['clone_state']['profile'] == SKETCH and separate['solid_body_count'] == 0
            and base['clone_state']['profile'] == BASE and base['solid_body_count'] == 1,
            'Separate native sketch and base snapshots are required.')
        volume = prior['independent_volume_mm3']
        require(type(volume) in (int, float) and math.isfinite(volume)
            and math.isclose(volume, 8000., rel_tol=1e-8, abs_tol=1e-6),
            'Independent 40x20x10 mm geometry required.')
        return dict(accepted=True, scope='rectangle_positive_report_preflight_v1',
            native_b1_accepted=False, wheel=wheel, verified_case_labels=list(POSITIVE_LABELS))
    except (KeyError, TypeError, AssertionError) as error:
        raise ValueError('Incomplete positive rectangle evidence.') from error
