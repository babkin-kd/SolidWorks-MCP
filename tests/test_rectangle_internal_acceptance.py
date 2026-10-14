"""Combined report preflight on actual coordinator jobs and artificial CAD.

The report envelope/listing is artificial. Stage predicates, revisions, geometry,
restoration and durable failures are real pure-domain evidence, never success stubs.
"""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from test_rectangle_native_verifier import configured as configure_fixture
from test_rectangle_construction_execution import execution as execution_fixture, run
from test_rectangle_postconditions import proof as sketch_proof, empty_adapter
from test_rectangle_extrusion_postconditions import proof as extrusion_proof


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('_rectangle_internal_acceptance_test',
    SCRIPTS / 'verifier_rectangle_internal_acceptance.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def evidence(sketch_proof, extrusion_proof, monkeypatch, tmp_path):
    generators, contexts, captures, native_cases = [], {}, [], {}

    def context(kind):
        folder = tmp_path / kind
        folder.mkdir()
        generator = execution_fixture.__wrapped__(NS(param=kind), sketch_proof, extrusion_proof, folder)
        generators.append(generator)
        value = configure_fixture.__wrapped__(next(generator), monkeypatch)
        contexts[kind] = value
        value.adapter.injected_failures = 0
        capture = value.catalog._capture

        def observe(*args, **kwargs):
            try:
                return capture(*args, **kwargs)
            except RuntimeError:
                value.adapter.injected_failures += 1
                captures.append(dict(status='returned', controlled_python_failure_after_native_return=True))
                raise
        monkeypatch.setattr(value.catalog, '_capture', observe)
        return value

    def counts():
        return [contexts['sketch'].adapter.dispatches,
            contexts['extrusion'].adapter.dispatches if 'extrusion' in contexts else 0,
            sum(x.adapter.injected_failures for x in contexts.values())]

    def arguments(value):
        return dict(document_id='target', configuration='Основная',
            expected_revision=value.catalog.prepare_sketch()['revision'], **vars(value.definition))

    def submit(value, label, args):
        method = value.catalog.create_sketch if value.kind == 'sketch' else value.catalog.create_extrusion
        def execute(operation_id):
            value.adapter.operation_id = operation_id
            return method(operation_id, **args)
        ack = value.runner.submit(label, 'rectangle.' + value.kind, args, execute,
            context=args, mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        return value.store.get(ack['operation_id'])

    def case(value, label, args, *, restore=False):
        before = deepcopy(value.adapter.state['snapshots']['target'])
        old_counts = counts()
        if restore:
            value.adapter.fault = 'inspect_once'
        job = submit(value, label, args)
        native_cases[label] = dict(before_snapshot=before,
            after_snapshot=deepcopy(value.adapter.state['snapshots']['target']),
            dispatch_counts_before=old_counts, dispatch_counts_after=counts(), expected_arguments=deepcopy(args))
        if restore:
            assert helper.verified_rectangle_restoration(job), job.get('error')
        else:
            assert helper.verified_rectangle_prewrite(job, expected_code=(
                'stale_revision' if 'stale' in label else 'object_reference_not_found'), expected_arguments=args)
        return job

    def prepare(value, label, operation):
        args = {key: val for key, val in arguments(value).items() if key != 'expected_revision'}
        return value.runner.submit(label, operation, args, lambda: value.catalog.prepare_sketch(), context=args)

    try:
        sketch = context('sketch')
        args_sketch = arguments(sketch)
        jobs = {}
        sketch_prepare = prepare(sketch, 'sketch_prepare', 'sketch.prepare_rectangle')
        jobs[helper.FAULT_LABELS[0]] = case(sketch, helper.FAULT_LABELS[0],
            {**args_sketch, 'expected_revision': 'rev_stale'})
        jobs[helper.FAULT_LABELS[1]] = case(sketch, helper.FAULT_LABELS[1],
            {**args_sketch, 'plane_object_id': 'feat_' + 'f' * 32})
        jobs[helper.FAULT_LABELS[2]] = case(sketch, helper.FAULT_LABELS[2], args_sketch, restore=True)
        setup = run(sketch, 'setup_sketch_job')
        assert helper.verified_rectangle_job(setup)
        extrusion = context('extrusion')
        borrowed = setup['result']['value']['sketch_object_id']
        extrusion.definition = replace(extrusion.definition, sketch_object_id=borrowed)
        resolve = extrusion.catalog.features._resolve

        def resolve_borrowed(*args):
            # Give the exact returned sketch ID the artificial baseline's real
            # persistent reference. All created-feature registration stays real.
            if args[-1] == borrowed:
                args = (*args[:-1], 'feat_' + 'a' * 32)
            return resolve(*args)
        monkeypatch.setattr(extrusion.catalog.features, '_resolve', resolve_borrowed)
        args_extrusion = arguments(extrusion)
        extrusion_prepare = prepare(extrusion, 'extrusion_prepare', 'part.prepare_rectangle_extrusion')
        jobs[helper.FAULT_LABELS[3]] = case(extrusion, helper.FAULT_LABELS[3],
            {**args_extrusion, 'expected_revision': 'rev_stale'})
        jobs[helper.FAULT_LABELS[4]] = case(extrusion, helper.FAULT_LABELS[4],
            {**args_extrusion, 'sketch_object_id': 'feat_' + 'e' * 32})
        jobs[helper.FAULT_LABELS[5]] = case(extrusion, helper.FAULT_LABELS[5], args_extrusion, restore=True)
        positive_extrusion = run(extrusion, 'extrusion_job')
        assert helper.verified_rectangle_job(positive_extrusion)
        wheel = dict(package_version='2.0.0.dev92', git_sha='a' * 40,
            source_digest='b' * 64, wheel_sha256='d' * 64)
        hashes = dict(positive={'trusted-positive.py': 'c' * 64}, faults={'trusted-faults.py': 'e' * 64})
        original = [['34.0', False, None, []], [[], None, False, False], []]
        application = dict(user_control=True, visible=False, current_directory='original', search_folders='')
        common = dict(phase='terminal', native_calls_live=False, package_origin_verified=True,
            wheel=deepcopy(wheel), own_cleanup_verified=True, baseline_restored=True,
            independent_native_readback_verified=True, owned_documents=[], original_baseline=original,
            restored_baseline=deepcopy(original), original_application=application,
            restored_application=deepcopy(application))
        positive = dict(**deepcopy(common), scope='installed_rectangle_stages_positive_only',
            accepted=False, positive_case_passed=True, verifier_hashes=hashes['positive'].copy(),
            cases=[dict(label=label, passed=True) for label in helper._positive.POSITIVE_LABELS],
            captures=[dict(status='returned')], sketch_job=deepcopy(setup), extrusion_job=positive_extrusion,
            independent_sketch=deepcopy(setup['result']['after']['state']['snapshots']['target']),
            independent_base=deepcopy(positive_extrusion['result']['after']['state']['snapshots']['target']),
            independent_volume_mm3=8000.)
        cases = []
        for index, label in enumerate(helper.FAULT_LABELS):
            row = dict(label=label, passed=True)
            if index in (0, 1, 3, 4):
                row['native_creation_dispatches'] = 0
            elif index in (2, 5):
                row.update(controlled_python_fault=True, real_com_throw=False, full_owned_baseline_restored=True)
            cases.append(row)
        listing = dict(document_id='neighbor', configuration='Основная', next_cursor=None, total_count=2,
            items=[dict(object_id='feat_' + 'f' * 32, feature_type='RefPlane', persistent_reference_supported=True,
                        reference_error=None),
                   dict(object_id='feat_' + 'e' * 32, feature_type='ProfileFeature', persistent_reference_supported=True,
                        reference_error=None)])
        faults = dict(**deepcopy(common), scope='installed_rectangle_stages_faults_v1', accepted=True,
            fault_cases_passed=True, native_b1_accepted=False, verifier_hashes=hashes['faults'].copy(),
            positive_preflight=helper.validate_positive_report(positive, wheel, hashes['positive']),
            cases=cases, captures=captures, setup_sketch_job=setup, sketch_prepare=sketch_prepare,
            extrusion_prepare=extrusion_prepare, native_case_evidence=native_cases,
            reference_scope=dict(target_document_id='target', neighbor_document_id='neighbor',
                target_plane_id=args_sketch['plane_object_id'], foreign_plane_id='feat_' + 'f' * 32,
                foreign_sketch_id='feat_' + 'e' * 32), foreign_feature_listing=listing,
            independent_empty=deepcopy(sketch.before['snapshots']['target']),
            independent_final_sketch=deepcopy(jobs[helper.FAULT_LABELS[5]]['mutation']['verification']
                ['evidence']['after']['state']['snapshots']['target']), **jobs)
        yield dict(positive=positive, faults=faults), wheel, hashes
    finally:
        for generator in reversed(generators):
            generator.close()


def test_full_artificial_internal_chain_authorizes_preflight_only(evidence):
    result = helper.validate_internal_reports(*evidence)
    assert result['accepted'] is True and result['native_b1_accepted'] is False
    assert result['verified_case_labels']['faults'] == list(helper.FAULT_LABELS)
    assert 'target' not in str(result) and 'original' not in str(result)


@pytest.mark.parametrize('fault', [
    'missing_case', 'case_order', 'extra_case', 'wrong_wheel', 'old_positive_wheel', 'wrong_hash',
    'missing_report', 'extra_report', 'live', 'retained', 'not_terminal', 'capture_pending',
    'false_fault_flag', 'native_acceptance', 'owned', 'baseline', 'application', 'positive_binding',
    'partial_baseline', 'partial_application', 'original_busy',
    'unsafe_ledger', 'unknown_restore', 'pending_restore', 'wrong_target', 'wrong_borrowed',
    'setup_ledger', 'wrong_profile', 'real_com_throw', 'python_fault', 'missing_native_case',
    'n4_snapshot', 'n4_counts', 'n5_snapshot', 'n5_stamp', 'n5_counts', 'expected_arguments',
    'foreign_document', 'foreign_membership', 'foreign_kind', 'foreign_owned', 'partial_listing',
    'prewrite_code', 'prewrite_checkpoint', 'prewrite_revision', 'prewrite_dispatch', 'positive_profile',
])
def test_partial_foreign_or_unsafe_evidence_never_authorizes_preflight(evidence, fault):
    reports, wheel, hashes = evidence
    positive, report = reports['positive'], reports['faults']
    inverse = report[helper.FAULT_LABELS[5]]
    native = report['native_case_evidence']
    if fault == 'missing_case': report['cases'].pop()
    elif fault == 'case_order': report['cases'][0], report['cases'][1] = report['cases'][1], report['cases'][0]
    elif fault == 'extra_case': report['cases'].append(dict(label='unexpected', passed=True))
    elif fault == 'wrong_wheel': report['wheel']['wheel_sha256'] = '0' * 64
    elif fault == 'old_positive_wheel': positive['wheel']['package_version'] = '2.0.0.dev91'
    elif fault == 'wrong_hash': hashes['faults']['trusted-faults.py'] = '0' * 64
    elif fault == 'missing_report': reports.pop('positive')
    elif fault == 'extra_report': reports['old'] = {}
    elif fault == 'live': report['native_calls_live'] = True
    elif fault == 'retained': report['retained_process'] = True
    elif fault == 'not_terminal': report['phase'] = 'owned_cleanup'
    elif fault == 'capture_pending': report['captures'][0]['status'] = 'running'
    elif fault == 'false_fault_flag': report['fault_cases_passed'] = False
    elif fault == 'native_acceptance': report['native_b1_accepted'] = True
    elif fault == 'owned': report['owned_documents'] = [{'document_id': 'target'}]
    elif fault == 'baseline': report['restored_baseline'][0][2] = 'foreign'
    elif fault == 'application': report['restored_application']['user_control'] = False
    elif fault == 'partial_baseline': report['original_baseline'] = report['restored_baseline'] = []
    elif fault == 'partial_application': report['original_application'] = report['restored_application'] = {}
    elif fault == 'original_busy': report['original_baseline'][1][2] = report['restored_baseline'][1][2] = True
    elif fault == 'positive_binding': report['positive_preflight']['wheel']['wheel_sha256'] = '0' * 64
    elif fault == 'unsafe_ledger': inverse['mutation']['verification']['native_steps'].pop()
    elif fault == 'unknown_restore': inverse['status'] = 'unknown'
    elif fault == 'pending_restore': inverse['mutation']['verification']['evidence']['after']['receipt']['pending_native_step'] = 'delete'
    elif fault == 'wrong_target': inverse['mutation']['document_id'] = 'foreign'
    elif fault == 'wrong_borrowed': inverse['payload']['arguments']['sketch_object_id'] = 'feat_' + 'e' * 32
    elif fault == 'setup_ledger': report['setup_sketch_job']['mutation']['verification']['native_steps'].pop()
    elif fault == 'wrong_profile': inverse['payload']['arguments']['depth_mm'] = 11.
    elif fault == 'real_com_throw': report['cases'][2]['real_com_throw'] = True
    elif fault == 'python_fault': report['cases'][5]['controlled_python_fault'] = False
    elif fault == 'missing_native_case': native.pop(helper.FAULT_LABELS[0])
    elif fault == 'n4_snapshot': native[helper.FAULT_LABELS[0]]['after_snapshot']['clone_state']['material'][0] = 'changed'
    elif fault == 'n4_counts': native[helper.FAULT_LABELS[1]]['dispatch_counts_after'][0] = 1
    elif fault == 'n5_snapshot': native[helper.FAULT_LABELS[5]]['after_snapshot']['clone_state']['material'][0] = 'changed'
    elif fault == 'n5_stamp': native[helper.FAULT_LABELS[5]]['after_snapshot']['clone_state']['dimensions'][0]['owner_update_stamp'] = True
    elif fault == 'n5_counts': native[helper.FAULT_LABELS[5]]['dispatch_counts_after'][2] = 1
    elif fault == 'expected_arguments': native[helper.FAULT_LABELS[0]]['expected_arguments']['width_mm'] = 41.
    elif fault == 'foreign_document': report['foreign_feature_listing']['document_id'] = 'target'
    elif fault == 'foreign_membership': report['foreign_feature_listing']['items'][0]['object_id'] = 'feat_' + '1' * 32
    elif fault == 'foreign_kind': report['foreign_feature_listing']['items'][1]['feature_type'] = 'RefPlane'
    elif fault == 'foreign_owned': report['reference_scope']['foreign_plane_id'] = report['reference_scope']['target_plane_id']
    elif fault == 'partial_listing': report['foreign_feature_listing']['next_cursor'] = 'cursor_partial'
    elif fault == 'prewrite_code': report[helper.FAULT_LABELS[1]]['error']['code'] = 'stale_revision'
    elif fault == 'prewrite_checkpoint': report[helper.FAULT_LABELS[0]]['mutation'] = deepcopy(inverse['mutation'])
    elif fault == 'prewrite_revision': report[helper.FAULT_LABELS[0]]['payload']['arguments']['expected_revision'] = 'rev_other'
    elif fault == 'prewrite_dispatch': report['cases'][1]['native_creation_dispatches'] = True
    else: positive['sketch_job']['payload']['arguments']['width_mm'] = 41.
    with pytest.raises(ValueError):
        helper.validate_internal_reports(reports, wheel, hashes)


def test_n5_observation_stamp_can_advance_without_changing_borrowed_model(evidence):
    reports, wheel, hashes = evidence
    after = reports['faults']['native_case_evidence'][helper.FAULT_LABELS[5]]['after_snapshot']
    after['clone_state']['dimensions'][0]['owner_update_stamp'] += 1
    assert helper.validate_internal_reports(reports, wheel, hashes)['accepted'] is True


@pytest.mark.parametrize('mode', ['path', 'standalone'])
def test_passive_loader_preserves_path_and_cached_named_sibling(mode):
    code = '''
import importlib.util, pathlib, runpy, sys, types
path = pathlib.Path(sys.argv[1])
before = list(sys.path)
cached = types.ModuleType('verifier_rectangle_stages')
sys.modules['verifier_rectangle_stages'] = cached
if sys.argv[2] == 'path':
    spec = importlib.util.spec_from_file_location('_isolated_internal', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
else:
    runpy.run_path(str(path), run_name='__main__')
assert sys.path == before
assert str(path.parent) not in sys.path
assert sys.modules['verifier_rectangle_stages'] is cached
'''
    result = subprocess.run([sys.executable, '-c', code,
        str(SCRIPTS / 'verifier_rectangle_internal_acceptance.py'), mode],
        cwd=SCRIPTS.parent, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
