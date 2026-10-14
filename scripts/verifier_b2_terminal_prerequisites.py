"""Passive exact-wheel terminal leaf prerequisites; no process/CAD dispatch.

The original native owner must separately observe its process exit. A returned
report gate never permits closing documents, stopping a process or starting CAD.
"""
from copy import deepcopy
from pathlib import Path

from verifier_b2_public_preflight import (
    SUPPORTED_VERSIONS, _report, _same, _require, fault_preflight)
from verify_owned_leaf_deletion_faults import positive_preflight
from verify_wheel_artifact import validate_wheel
from verify_installed_metadata import installed_identity
from verifier_lifecycle import read_journal


def audit_leaf_prerequisites(*, positive_report, positive_report_sha256,
                            faults_report, faults_report_sha256, wheel_path,
                            expected_version, expected_git_sha):
    """Read immutable terminal reports and complete raw journals before identity.

    Existing positive/fault validators check full parent snapshots, helper
    manifests, SQL/digests/replays and the intentionally unresolved old hold.
    No metadata subprocess, reconnect, reconciliation, retry or COM is used.
    """
    _require(type(expected_version) is str and expected_version in SUPPORTED_VERSIONS,
             'Explicit supported B2 candidate version required.')
    positive_path, positive = _report(positive_report, positive_report_sha256)
    faults_path, faults = _report(faults_report, faults_report_sha256)
    for row in (positive, faults):
        _require(row.get('phase') == 'terminal' and row.get('native_calls_live') is False
                 and row.get('own_cleanup_verified') is True and row.get('baseline_restored') is True,
                 'Terminal reports and own cleanup/baseline required before installed identity.')
    _require(positive_path != faults_path and positive_path.parent != faults_path.parent,
             'Distinct original positive and fault journals required.')
    wheel = positive['wheel']
    _require(type(wheel) is dict and wheel['package_version'] == expected_version
             and wheel['git_sha'] == expected_git_sha and _same(faults['wheel'], wheel),
             'Reports must bind the requested exact candidate version/build/wheel.')
    paths = (positive_path, faults_path)
    journals = [read_journal(path.with_name('jobs.sqlite')) for path in paths]
    parents = [_report(path.with_name('report.json'), row['parent_final_report_sha256'])[1]
               for path, row in zip(paths, (positive, faults))]
    scripts = Path(__file__).resolve().parent
    positive_proof = positive_preflight(positive_path, positive_report_sha256, wheel, scripts)
    _require(positive_proof['positive_report_gate_verified'] is True, 'Actual positive gate failed.')
    fault_proof = fault_preflight(faults_path, faults_report_sha256, wheel, scripts, positive_proof)
    _require(fault_proof['fault_report_gate_verified'] is True, 'Actual faults gate failed.')
    artifact = validate_wheel(wheel_path, expected_version=expected_version, expected_git_sha=expected_git_sha)
    _require(_same(artifact, wheel), 'Actual wheel differs from terminal prerequisites.')
    identity = installed_identity(artifact)
    # Re-read and hash after all checks: a concurrently replaced report cannot
    # silently change the gate. Complete validators already inspect the DB.
    _require(_same(_report(positive_path, positive_report_sha256)[1], positive)
             and _same(_report(faults_path, faults_report_sha256)[1], faults),
             'Original terminal reports changed during passive audit.')
    _require(all(_same(read_journal(path.with_name('jobs.sqlite')), journal)
                 and _same(_report(path.with_name('report.json'), row['parent_final_report_sha256'])[1], parent)
                 for path, row, journal, parent in zip(paths, (positive, faults), journals, parents)),
             'Original complete journal or parent changed during passive audit.')
    return dict(scope='b2_terminal_leaf_prerequisites_audit_v1',
                prerequisite_reports_verified=True, wheel=deepcopy(artifact),
                installed_console_entrypoint=str(identity), positive_preflight=positive_proof,
                faults_preflight=fault_proof, cad_calls=[], process_calls=[],
                accepted=False, native_b2_accepted=False, public_mcp_accepted=False,
                permit_native_dispatch=False, cleanup_authorized=False,
                open_gates=['original_process_exit_observation', 'N5_fixture_cases', 'public_MCP', 'whole_B2'])
