"""Passive exact-wheel coherence gate for positive and N4/N5 B1 reports.

This authorizes only preflight. Reports retain their private CAD evidence; this
module never connects to SolidWorks or grants full native B1 acceptance.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import re
import sys

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_snapshot import validated_rectangle_snapshot, EMPTY, SKETCH


def _sibling(filename, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stages = _sibling('verifier_rectangle_stages.py', '_internal_rectangle_stages')
_restoration = _sibling('verifier_rectangle_restoration.py', '_internal_rectangle_restoration')
_prewrite = _sibling('verifier_rectangle_prewrite.py', '_internal_rectangle_prewrite')
# The frozen positive helper imports its sibling by name. Bind that exact
# passive dependency only while loading it; preserve both sys.path and any
# caller's cached named module, rather than depending on earlier test imports.
_missing = object()
_previous_stages = sys.modules.get('verifier_rectangle_stages', _missing)
try:
    sys.modules['verifier_rectangle_stages'] = _stages
    _positive = _sibling('verifier_rectangle_positive_acceptance.py', '_internal_rectangle_positive')
finally:
    if _previous_stages is _missing:
        sys.modules.pop('verifier_rectangle_stages', None)
    else:
        sys.modules['verifier_rectangle_stages'] = _previous_stages

validate_positive_report = _positive.validate_positive_report
verified_rectangle_job = _stages.verified_rectangle_job
verified_rectangle_restoration = _restoration.verified_rectangle_restoration
verified_rectangle_prewrite = _prewrite.verified_rectangle_prewrite

FAULT_LABELS = (
    'B1-N4-stale-sketch',
    'B1-N4-foreign-plane',
    'B1-N5-owned-sketch-restoration',
    'B1-N4-stale-extrusion',
    'B1-N4-foreign-sketch',
    'B1-N5-owned-extrusion-restoration',
    'B1-N4-N5-owned-cleanup-baseline',
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _profile_arguments(arguments, *, sketch):
    common = {'document_id', 'configuration', 'expected_revision'}
    specific = ({'plane_object_id', 'width_mm', 'height_mm', 'sketch_name'} if sketch
                else {'sketch_object_id', 'depth_mm', 'feature_name', 'body_name'})
    _require(type(arguments) is dict and set(arguments) == common | specific
        and type(arguments['document_id']) is str and bool(arguments['document_id'])
        and arguments['configuration'] == 'Основная'
        and type(arguments['expected_revision']) is str and bool(arguments['expected_revision']),
        'Exact explicit target/configuration/revision and finite profile arguments required.')
    reference = arguments['plane_object_id' if sketch else 'sketch_object_id']
    _require(type(reference) is str and re.fullmatch(r'feat_[0-9a-f]{32}', reference) is not None,
        'An exact opaque plane or sketch reference is required.')
    if sketch:
        _require(all(type(arguments[key]) in (int, float) and arguments[key] == value
                     for key, value in (('width_mm', 40.), ('height_mm', 20.)))
            and arguments['sketch_name'] == 'Эскиз основания', 'Exact 40x20 mm sketch profile required.')
    else:
        _require(type(arguments['depth_mm']) in (int, float) and arguments['depth_mm'] == 10.
            and arguments['feature_name'] == 'Основание' and arguments['body_name'] == 'Тело основания',
            'Exact 10 mm base extrusion profile required.')


def _empty_session_baseline(report):
    baseline, application = report['original_baseline'], report['original_application']
    _require(type(baseline) is list and len(baseline) == 3,
        'Complete independent session, physical and window baseline required.')
    native, physical, windows = baseline
    _require(type(native) is list and len(native) == 4 and type(native[0]) is str and bool(native[0])
        and type(native[1]) is bool and native[2] is None and native[3] == []
        and type(physical) is list and len(physical) == 4 and physical[0] == []
        and physical[1] is None and physical[2] is False and physical[3] is native[1]
        and type(windows) is list and not windows,
        'The trusted internal drivers require an empty quiescent original session.')
    _require(type(application) is dict and set(application) == {'user_control', 'visible',
        'current_directory', 'search_folders'} and application['user_control'] is True
        and application['visible'] is native[1]
        and all(type(application[key]) is str for key in ('current_directory', 'search_folders')),
        'Complete native application ownership, visibility and search baseline required.')


def _same_sketch(before, after):
    """Only the target dimension observation stamps may advance after rollback."""
    first = deepcopy(validated_rectangle_snapshot(before))
    last = deepcopy(validated_rectangle_snapshot(after))
    old, new = first['clone_state']['dimensions'], last['clone_state']['dimensions']
    _require(len(old) == len(new) and all(set(a) == set(b) for a, b in zip(old, new)),
        'Restored sketch dimension inventory differs.')
    for row in [*old, *new]:
        if 'owner_update_stamp' in row:
            _require(type(row['owner_update_stamp']) is int, 'Dimension observation stamp is malformed.')
            row.pop('owner_update_stamp')
    _require(_json(first) == _json(last), 'Independent restored sketch differs from the borrowed baseline.')


def _preparation_revision(report, key, operation, expected):
    job = report[key]
    _require(job['operation'] == operation and job['status'] == 'succeeded'
        and job.get('error') is None and job['payload']['mutates'] is False
        and job.get('mutation') is None
        and job['payload']['arguments'] == {k: v for k, v in expected.items() if k != 'expected_revision'},
        'Exact trusted preparation arguments and terminal read job required.')
    revision = job['result']['revision']
    _require(type(revision) is str and bool(revision) and revision != 'rev_stale',
        'Preparation did not return a current revision.')
    return revision


def _reference_scope(report, setup, target, borrowed):
    refs = report['reference_scope']
    _require(type(refs) is dict and set(refs) == {'target_document_id', 'neighbor_document_id',
        'target_plane_id', 'foreign_plane_id', 'foreign_sketch_id'}
        and refs['target_document_id'] == target
        and type(refs['neighbor_document_id']) is str and bool(refs['neighbor_document_id'])
        and refs['neighbor_document_id'] != target
        and refs['target_plane_id'] == setup['payload']['arguments']['plane_object_id'],
        'Explicit distinct owned target and foreign neighbor reference scope required.')
    for key in ('target_plane_id', 'foreign_plane_id', 'foreign_sketch_id'):
        _require(type(refs[key]) is str and re.fullmatch(r'feat_[0-9a-f]{32}', refs[key]) is not None,
            'Reference scope contains a nonopaque feature ID.')
    _require(len({refs[key] for key in ('target_plane_id', 'foreign_plane_id', 'foreign_sketch_id')}) == 3
        and borrowed not in (refs['foreign_plane_id'], refs['foreign_sketch_id']),
        'Foreign features must be distinct from the borrowed owned references.')
    documents = setup['result']['before']['baseline']['semantic']['documents']
    _require(refs['neighbor_document_id'] in {row['document_id'] for row in documents},
        'Foreign neighbor is absent from the complete owned-session baseline.')
    listing = report['foreign_feature_listing']
    rows = listing['items']
    _require(listing['document_id'] == refs['neighbor_document_id']
        and listing['configuration'] == 'Основная' and listing['next_cursor'] is None
        and type(rows) is list and type(listing['total_count']) is int
        and listing['total_count'] == len(rows) and 1 <= len(rows) <= 100,
        'Complete foreign-neighbor feature listing required.')
    ids = [row['object_id'] for row in rows if row.get('object_id') is not None]
    _require(len(ids) == len(set(ids)), 'Foreign feature listing repeats opaque object IDs.')
    for key, kind in (('foreign_plane_id', 'RefPlane'), ('foreign_sketch_id', 'ProfileFeature')):
        matches = [row for row in rows if row.get('object_id') == refs[key]]
        _require(len(matches) == 1 and matches[0]['feature_type'] == kind
            and matches[0]['persistent_reference_supported'] is True and matches[0]['reference_error'] is None,
            'Foreign plane/sketch must belong to its exact typed neighbor listing.')
    return refs


def _native_case(report, label, expected_arguments, *, sketch, rollback):
    evidence = report['native_case_evidence'][label]
    _require(type(evidence) is dict and set(evidence) == {'before_snapshot', 'after_snapshot',
        'dispatch_counts_before', 'dispatch_counts_after', 'expected_arguments'}
        and evidence['expected_arguments'] == expected_arguments,
        'Complete independently captured case evidence and expected arguments required.')
    for key in ('dispatch_counts_before', 'dispatch_counts_after'):
        counts = evidence[key]
        _require(type(counts) is list and len(counts) == 3
            and all(type(value) is int and value >= 0 for value in counts),
            'Exact native creation/extrusion/Python-failure counters required.')
    before, after = evidence['dispatch_counts_before'], evidence['dispatch_counts_after']
    expected_counts = ([0, 0, 0] if label in FAULT_LABELS[:3] else [2, 0, 1])
    _require(before == expected_counts, 'Case counters do not belong to the finite setup/restoration chain.')
    _require(after == [before[0] + int(rollback and sketch), before[1] + int(rollback and not sketch),
                       before[2] + int(rollback)], 'Native dispatch/failure counts contradict the case outcome.')
    old = validated_rectangle_snapshot(evidence['before_snapshot'])
    new = validated_rectangle_snapshot(evidence['after_snapshot'])
    profile = EMPTY if sketch else SKETCH
    _require(old['clone_state']['profile'] == new['clone_state']['profile'] == profile
        and old['solid_body_count'] == new['solid_body_count'] == 0,
        'Case must preserve its exact empty or borrowed-sketch stage profile.')
    if rollback:
        _same_sketch(old, new)
    else:
        _require(_json(old) == _json(new), 'Prewrite case changed its complete independent native snapshot.')


def validate_internal_reports(reports, wheel, verifier_hashes):
    """Reject partial/foreign reports; return only an anonymous preflight DTO."""
    try:
        _json(reports); _json(wheel); _json(verifier_hashes)
        _require(type(reports) is dict and set(reports) == {'positive', 'faults'}
            and type(verifier_hashes) is dict and set(verifier_hashes) == set(reports),
            'Exact positive/faults report and helper-hash pair required.')
        for hashes in verifier_hashes.values():
            _require(type(hashes) is dict and bool(hashes)
                and all(type(name) is str and bool(name) and type(digest) is str
                        and re.fullmatch(r'[0-9a-f]{64}', digest) is not None for name, digest in hashes.items()),
                'Nonempty exact trusted helper SHA256 maps required.')
        positive = validate_positive_report(reports['positive'], wheel, verifier_hashes['positive'])
        _empty_session_baseline(reports['positive'])
        # The positive gate already validates its exact geometry/chain. Bind the
        # requested finite engineering profile as well as its report manifest.
        for name, sketch in (('sketch_job', True), ('extrusion_job', False)):
            _profile_arguments(reports['positive'][name]['payload']['arguments'], sketch=sketch)
        report = reports['faults']
        _require(type(report) is dict and report['scope'] == 'installed_rectangle_stages_faults_v1'
            and report['accepted'] is True and report['fault_cases_passed'] is True
            and report['native_b1_accepted'] is False and report['phase'] == 'terminal'
            and report['native_calls_live'] is False and report.get('retained_process', False) is False,
            'Only terminal finite fault evidence without live/retained effects is admissible.')
        _require(_json(report['wheel']) == _json(wheel) and report['package_origin_verified'] is True
            and report['verifier_hashes'] == verifier_hashes['faults']
            and _json(report['positive_preflight']) == _json(positive),
            'Fault evidence belongs to another wheel, helper set or positive preflight.')
        _require(all(report[key] is True for key in
                     ('own_cleanup_verified', 'baseline_restored', 'independent_native_readback_verified'))
            and type(report['owned_documents']) is list and not report['owned_documents']
            and _json(report['restored_baseline']) == _json(report['original_baseline'])
            and _json(report['restored_application']) == _json(report['original_application']),
            'Complete original session/application baseline and owned cleanup are required.')
        _empty_session_baseline(report)
        cases = report['cases']
        _require(type(cases) is list and [row.get('label') for row in cases] == list(FAULT_LABELS)
            and all(row.get('passed') is True for row in cases), 'Exact ordered N4/N5 case manifest required.')
        captures = report['captures']
        _require(type(captures) is list and bool(captures)
            and all(type(row) is dict and row.get('status') == 'returned' for row in captures)
            and sum(row.get('controlled_python_failure_after_native_return') is True for row in captures) == 2
            and all('controlled_python_failure_after_native_return' not in row
                    or row['controlled_python_failure_after_native_return'] is True for row in captures),
            'All captures must return, with exactly two controlled Python observation failures.')
        setup = report['setup_sketch_job']
        _require(verified_rectangle_job(setup) and setup['operation'] == 'sketch.create_rectangle',
            'Exact committed borrowed setup sketch proof required.')
        setup_args = setup['payload']['arguments']
        _profile_arguments(setup_args, sketch=True)
        target = setup_args['document_id']
        borrowed = setup['result']['value']['sketch_object_id']
        refs = _reference_scope(report, setup, target, borrowed)
        _require(type(report['native_case_evidence']) is dict
            and set(report['native_case_evidence']) == set(FAULT_LABELS[:-1]),
            'Exact six native before/after case observations required.')
        for index, sketch in ((2, True), (5, False)):
            job, case = report[FAULT_LABELS[index]], cases[index]
            _require(verified_rectangle_restoration(job)
                and job['request_id'] == FAULT_LABELS[index]
                and job['operation'] == ('sketch.create_rectangle' if sketch else 'part.extrude_rectangle')
                and case['controlled_python_fault'] is True and case['real_com_throw'] is False
                and case['full_owned_baseline_restored'] is True,
                'Exact owned restoration and controlled Python fault proof required.')
            args = job['payload']['arguments']
            _profile_arguments(args, sketch=sketch)
            _require(args['document_id'] == target
                and args['plane_object_id' if sketch else 'sketch_object_id']
                    == (setup_args['plane_object_id'] if sketch else borrowed),
                'Restoration must stay on the exact setup target and borrowed reference.')
            _native_case(report, FAULT_LABELS[index], args, sketch=sketch, rollback=True)
            evidence = report['native_case_evidence'][FAULT_LABELS[index]]
            _same_sketch(job['mutation']['before_state']['baseline']['snapshots'][target],
                evidence['before_snapshot'])
            _same_sketch(job['mutation']['verification']['evidence']['after']['state']['snapshots'][target],
                evidence['after_snapshot'])
        sketch_args = report[FAULT_LABELS[2]]['payload']['arguments']
        extrusion_args = report[FAULT_LABELS[5]]['payload']['arguments']
        for first_index, sketch, args, prepare_key, operation in (
            (0, True, sketch_args, 'sketch_prepare', 'sketch.prepare_rectangle'),
            (3, False, extrusion_args, 'extrusion_prepare', 'part.prepare_rectangle_extrusion'),
        ):
            revision = _preparation_revision(report, prepare_key, operation, args)
            reference_key = 'plane_object_id' if sketch else 'sketch_object_id'
            for offset, code in ((0, 'stale_revision'), (1, 'object_reference_not_found')):
                label = FAULT_LABELS[first_index + offset]
                job = report[label]
                actual = job['payload']['arguments']
                _profile_arguments(actual, sketch=sketch)
                expected = {**args, 'expected_revision': 'rev_stale' if offset == 0 else revision}
                if offset:
                    expected[reference_key] = refs['foreign_plane_id' if sketch else 'foreign_sketch_id']
                _require(job['request_id'] == label
                    and job['operation'] == ('sketch.create_rectangle' if sketch else 'part.extrude_rectangle')
                    and verified_rectangle_prewrite(job, expected_code=code, expected_arguments=expected)
                    and type(cases[first_index + offset]['native_creation_dispatches']) is int
                    and cases[first_index + offset]['native_creation_dispatches'] == 0,
                    'Exact prewrite code, arguments and zero-dispatch case required.')
                _native_case(report, label, expected, sketch=sketch, rollback=False)
                baseline = report[FAULT_LABELS[2 if sketch else 5]]['mutation']['before_state']['baseline']
                _same_sketch(baseline['snapshots'][target],
                    report['native_case_evidence'][label]['before_snapshot'])
        empty = validated_rectangle_snapshot(report['independent_empty'])
        final = validated_rectangle_snapshot(report['independent_final_sketch'])
        _require(empty['clone_state']['profile'] == EMPTY and empty['solid_body_count'] == 0
            and final['clone_state']['profile'] == SKETCH and final['solid_body_count'] == 0,
            'Independent empty and final borrowed-sketch observations required.')
        _same_sketch(setup['result']['before']['baseline']['snapshots'][target], empty)
        inverse = report[FAULT_LABELS[5]]['mutation']
        _same_sketch(inverse['before_state']['baseline']['snapshots'][target], final)
        _same_sketch(inverse['verification']['evidence']['after']['state']['snapshots'][target], final)
        return dict(accepted=True, scope='rectangle_internal_reports_preflight_v1', native_b1_accepted=False,
            verified_case_labels=dict(positive=positive['verified_case_labels'], faults=list(FAULT_LABELS)))
    except ValueError:
        raise
    except Exception as error:
        raise ValueError('Incomplete internal rectangle evidence.') from error
