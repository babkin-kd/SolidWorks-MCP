"""Manufactured report preflight; detailed receipts have separate predicate tests."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import re

import pytest


FAULTS = ('false_after_copy', 'warning_after_copy', 'throw_after_copy', 'incomplete_after_copy')
tree = ast.parse((Path(__file__).resolve().parents[1] / 'scripts/verifier_first_save_internal_acceptance.py').read_text(encoding='utf-8'))
# Detailed native receipt predicates are stubs here: these tests isolate report
# completeness, current helper hashes, wheel binding and truthful terminal flags.
namespace = dict(deepcopy=deepcopy, re=re, COPY_FAULTS=FAULTS,
                 _json=lambda value: json.dumps(value, allow_nan=False),
                 verified_committed_first_save=lambda value: value == {'synthetic': 'positive'},
                 verified_race_rollback=lambda job, foreign: job == {'synthetic': 'race'} and foreign == {})
body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
exec(compile(ast.Module(body=body, type_ignores=[]), 'internal_preflight', 'exec'), namespace)
verify = namespace['validate_internal_cases']


@pytest.fixture
def complete():
    wheel = dict(package_version='2.0.0.dev88', git_sha='a'*40, source_digest='b'*64, wheel_sha256='c'*64)
    scopes = namespace['BASE_SCOPES']
    hashes = {key: {'trusted.py': 'd'*64} for key in (*scopes, *FAULTS)}
    def report(key, scope, flag):
        return dict(scope=scope, phase='terminal', accepted=False, **{flag: True}, wheel=deepcopy(wheel),
                    verifier_hashes=deepcopy(hashes[key]), owned_documents=[], native_calls_live=False,
                    baseline_restored=True, own_cleanup_verified=True, package_origin_verified=True,
                    metadata_catalog=dict(public_tool_count=73, output_schemas_verified=True))
    reports = {key: report(key, *value) for key, value in scopes.items()}
    reports['positive']['job'] = {'synthetic': 'positive'}
    reports['rejections']['cases'] = [dict(label=label, passed=True) for label in namespace['REJECTION_LABELS']]
    for case, code in zip(reports['rejections']['cases'], ('first_save_destination_exists', 'stale_revision')):
        case.update(copy_calls=0, job=dict(status='failed', error={'code': code}))
    reports['race']['cases'] = [dict(label=label, passed=True) for label in namespace['RACE_LABELS']]
    reports['race']['cases'][0].update(job={'synthetic': 'race'}, foreign_file={}, replay_verified=True,
        copy_calls=1, open_calls=1, close_calls=1, publication_calls=1)
    for fault in FAULTS:
        r = report(fault, 'installed_first_save_controlled_fault_only', 'fault_case_passed')
        r.update(fault=fault, actual_com_failure_injected=False, injection_applied=True,
                 original_native_copy_receipt=dict(success=True, native_call_returned=True, pending_copy=False, errors=0, warnings=0),
                 reconciliation=dict(status='unknown', mutation={'phase': 'reconciled'}),
                 recovery_reference_mapping=[{'synthetic': True} for _ in range(41)])
        r['cases'] = [dict(label=label, passed=True) for label in namespace['FAULT_LABELS']]
        r['cases'][0].update(job=dict(status='unknown', mutation={'phase': 'unresolved'}), replay_verified=True,
                             hold_blocked_job=dict(error={'code': 'document_mutation_blocked'}))
        r['cases'][1].update(independent_native_clone_verified=True, stage_file_retained=True)
        reports[fault] = r
    return reports, wheel, hashes


def test_complete_same_wheel_internal_set_is_detached_without_claiming_cad_acceptance(complete):
    reports, wheel, hashes = complete
    detached = verify(reports, wheel, hashes)
    assert detached == reports and detached is not reports
    assert all(report['accepted'] is False for report in detached.values())


@pytest.mark.parametrize('fault', ['missing_mode', 'wrong_wheel', 'wrong_hash', 'partial_hashes', 'source_scope',
                                 'pending', 'owned', 'skipped', 'unknown_as_success', 'no_reconciliation',
                                 'fake_native_warning', 'boolean_copy_count', 'boolean_retained', 'missing_mapping'])
def test_missing_foreign_or_unconfirmed_internal_reports_block_public_dispatch(complete, fault):
    reports, wheel, hashes = complete
    r = reports['warning_after_copy']
    if fault == 'missing_mode':del reports['throw_after_copy']
    elif fault == 'wrong_wheel':r['wheel']['git_sha'] = 'e'*40
    elif fault == 'wrong_hash':r['verifier_hashes']['trusted.py'] = 'f'*64
    elif fault == 'partial_hashes':r['verifier_hashes'] = {}
    elif fault == 'source_scope':reports['positive']['scope'] = 'source_first_save_domain_positive_only'
    elif fault == 'pending':r['recovery_open_pending'] = True
    elif fault == 'owned':r['owned_documents'] = [{'title': 'retained'}]
    elif fault == 'skipped':r['cases'][1]['passed'] = False
    elif fault == 'unknown_as_success':r['reconciliation']['status'] = 'succeeded'
    elif fault == 'no_reconciliation':r['reconciliation']['mutation']['phase'] = 'unresolved'
    elif fault == 'fake_native_warning':r['original_native_copy_receipt']['warnings'] = False
    elif fault == 'boolean_copy_count':reports['rejections']['cases'][0]['copy_calls'] = False
    elif fault == 'boolean_retained':r['retained_process'] = 0
    elif fault == 'missing_mapping':r['recovery_reference_mapping'] = []
    with pytest.raises(ValueError):
        verify(reports, wheel, hashes)


def test_new_trusted_catalog_count_does_not_reuse_prior_metadata_shape(complete):
    reports, wheel, hashes = complete
    for report in reports.values():
        report['metadata_catalog']['public_tool_count'] = 75
    with pytest.raises(ValueError):
        verify(reports, wheel, hashes)
    assert verify(reports, wheel, hashes, expected_public_tool_count=75) == reports


@pytest.mark.parametrize('count', [True, 75., '75', 0, 513, None])
def test_invalid_trusted_catalog_count_is_refused(complete, count):
    with pytest.raises(ValueError):
        verify(*complete, expected_public_tool_count=count)
