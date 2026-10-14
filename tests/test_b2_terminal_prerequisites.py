"""Passive gate over artificial domain reports and real SQLite; never native CAD."""
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys

import pytest

# Reuse genuine domain/runner/journal artifacts and both direct/display modes.
# No positive/fault validator or journal reader is replaced.
from test_b2_public_preflight import (
    artifacts, b2_private_dir, case, domain, empty_adapter, execution,
    extrusion_proof, faults, leaf, proof, scripts, sketch_proof, write,
    helper as public_helper,
)

sys.path.insert(0, str(scripts))
try:
    import verifier_b2_terminal_prerequisites as helper
finally:
    sys.path.remove(str(scripts))


def arguments(x):
    args = x.args
    return dict(positive_report=args.positive_report,
                positive_report_sha256=args.positive_report_sha256,
                faults_report=args.faults_report,
                faults_report_sha256=args.faults_report_sha256,
                wheel_path=args.wheel, expected_version=args.expected_version,
                expected_git_sha=args.expected_git_sha)


def artifact_hashes(x):
    paths = [path for report in (x.positive_path, x.fault_path)
             for path in (report, report.with_name('report.json'), report.with_name('jobs.sqlite'))]
    return {str(path): public_helper._sha(path) for path in paths}


@pytest.fixture
def candidate(artifacts, monkeypatch):
    x = artifacts
    calls = []

    def validate(path, *, expected_version, expected_git_sha):
        calls.append('wheel')
        assert Path(path) == x.args.wheel
        assert expected_version == x.args.expected_version
        assert expected_git_sha == x.args.expected_git_sha
        return deepcopy(x.package['wheel'])

    def identity(wheel):
        calls.append('identity')
        assert wheel == x.package['wheel']
        return x.positive_path.parent / 'artificial-console.exe'

    def forbidden(*args, **kwargs):
        pytest.fail('Passive prerequisite audit must never dispatch CAD or a process')

    monkeypatch.setattr(helper, 'validate_wheel', validate)
    monkeypatch.setattr(helper, 'installed_identity', identity)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    monkeypatch.setattr('solidworks_mcp.binding.connect', forbidden)
    monkeypatch.setattr('solidworks_mcp.session.SolidWorksSession.connect', forbidden)
    return x, calls


def test_terminal_actual_reports_readonly_sql_identity_and_no_authority(candidate):
    x, calls = candidate
    before = artifact_hashes(x)
    result = helper.audit_leaf_prerequisites(**arguments(x))
    assert calls == ['wheel', 'identity']
    assert result['scope'] == 'b2_terminal_leaf_prerequisites_audit_v1'
    assert result['prerequisite_reports_verified'] is True
    assert result['positive_preflight']['positive_report_gate_verified'] is True
    assert result['faults_preflight']['fault_report_gate_verified'] is True
    assert result['faults_preflight']['unknown_remains_unresolved'] is True
    assert result['wheel'] == x.package['wheel']
    assert result['installed_console_entrypoint'].endswith('artificial-console.exe')
    assert result['cad_calls'] == result['process_calls'] == []
    for name in ('accepted', 'native_b2_accepted', 'public_mcp_accepted',
                 'permit_native_dispatch', 'cleanup_authorized'):
        assert result[name] is False
    assert result['open_gates'] == [
        'original_process_exit_observation', 'N5_fixture_cases', 'public_MCP', 'whole_B2']
    assert artifact_hashes(x) == before
    rows = public_helper.read_journal(x.fault_path.with_name('jobs.sqlite'))
    unknown = next(row for row in rows
                   if row['operation_id'] == x.row['unknown_job_retained']['operation_id'])
    assert unknown['status'] == 'unknown'
    assert unknown['mutation']['phase'] == 'unresolved'
    assert unknown['mutation']['reconciliation'] is None
    # Returned evidence is detached from the caller's candidate evidence.
    result['wheel']['wheel_sha256'] = '0' * 64
    assert x.package['wheel']['wheel_sha256'] == 'b' * 64
    assert artifact_hashes(x) == before


@pytest.mark.parametrize('which', ['positive', 'faults'])
@pytest.mark.parametrize('fault', [
    'phase', 'cleanup', 'baseline', 'live', 'retained', 'report_sha',
    'foreign_version', 'foreign_wheel', 'manifest', 'malformed_report',
])
def test_invalid_prerequisite_refuses_before_both_candidate_functions(candidate, which, fault):
    x, calls = candidate
    args = arguments(x)
    path = args[which + '_report']
    row = deepcopy(x.positive if which == 'positive' else x.row)
    if fault == 'report_sha':
        args[which + '_report_sha256'] = '0' * 64
    elif fault == 'malformed_report':
        args[which + '_report_sha256'] = write(path, [])
    else:
        if fault == 'phase':
            row['phase'] = 'running'
        elif fault == 'cleanup':
            row['own_cleanup_verified'] = False
        elif fault == 'baseline':
            row['baseline_restored'] = False
        elif fault == 'live':
            row['native_calls_live'] = True
        elif fault == 'retained':
            row['parent_retained_sta_required'] = True
        elif fault == 'foreign_version':
            row['wheel']['package_version'] = '2.0.0.dev96'
        elif fault == 'foreign_wheel':
            row['wheel']['wheel_sha256'] = 'f' * 64
        else:
            row['verifier_hashes'].pop(next(iter(row['verifier_hashes'])))
        args[which + '_report_sha256'] = write(path, row)
    before = artifact_hashes(x)
    with pytest.raises(ValueError):
        helper.audit_leaf_prerequisites(**args)
    assert calls == []
    assert artifact_hashes(x) == before


@pytest.mark.parametrize('fault', ['unsupported_version', 'boolean_version', 'historical_version', 'git'])
def test_requested_candidate_must_match_before_candidate_functions(candidate, fault):
    x, calls = candidate
    args = arguments(x)
    if fault == 'git':
        args['expected_git_sha'] = 'f' * 40
    else:
        args['expected_version'] = {
            'unsupported_version': '2.0.0.dev95', 'boolean_version': True,
            'historical_version': '2.0.0.dev96',
        }[fault]
    before = artifact_hashes(x)
    with pytest.raises(ValueError):
        helper.audit_leaf_prerequisites(**args)
    assert calls == []
    assert artifact_hashes(x) == before


@pytest.mark.parametrize('which', ['positive', 'faults'])
def test_actual_sql_tamper_refuses_before_wheel_and_identity(candidate, which):
    x, calls = candidate
    path = x.positive_path if which == 'positive' else x.fault_path
    operation_id = (x.positive['delete_job']['operation_id'] if which == 'positive'
                    else x.row['leaf_unknown_new_request_blocked']['operation_id'])
    with sqlite3.connect(path.with_name('jobs.sqlite')) as db:
        db.execute("UPDATE jobs SET digest=? WHERE operation_id=?", ('0' * 64, operation_id))
    before = artifact_hashes(x)
    with pytest.raises(ValueError):
        helper.audit_leaf_prerequisites(**arguments(x))
    assert calls == []
    assert artifact_hashes(x) == before


def test_artifact_wheel_mismatch_refuses_before_installed_identity(candidate, monkeypatch):
    x, calls = candidate
    before = artifact_hashes(x)

    def mismatched(path, **kwargs):
        calls.append('wheel')
        return {**x.package['wheel'], 'wheel_sha256': '0' * 64}

    monkeypatch.setattr(helper, 'validate_wheel', mismatched)
    with pytest.raises(ValueError, match='Actual wheel differs'):
        helper.audit_leaf_prerequisites(**arguments(x))
    assert calls == ['wheel']
    assert artifact_hashes(x) == before


@pytest.mark.parametrize('which', ['positive', 'faults'])
def test_report_rewrite_during_installed_identity_cannot_accept(candidate, monkeypatch, which):
    x, calls = candidate
    before = artifact_hashes(x)
    path = x.positive_path if which == 'positive' else x.fault_path

    def rewrite(wheel):
        calls.append('identity')
        # Equal JSON data with changed actual bytes must still fail its exact SHA.
        path.write_text(path.read_text(encoding='utf8') + '\n', encoding='utf8')
        return 'artificial-console.exe'

    monkeypatch.setattr(helper, 'installed_identity', rewrite)
    with pytest.raises(ValueError, match='SHA256 mismatch'):
        helper.audit_leaf_prerequisites(**arguments(x))
    assert calls == ['wheel', 'identity']
    after = artifact_hashes(x)
    assert after.pop(str(path)) != before.pop(str(path))
    assert after == before


@pytest.mark.parametrize('which', ['positive', 'faults'])
@pytest.mark.parametrize('artifact', ['journal', 'parent'])
def test_complete_journal_or_parent_rewrite_during_identity_refuses(candidate, monkeypatch, which, artifact):
    x, calls = candidate
    before = artifact_hashes(x)
    report_path = x.positive_path if which == 'positive' else x.fault_path
    path = report_path.with_name('jobs.sqlite' if artifact == 'journal' else 'report.json')

    def rewrite(wheel):
        calls.append('identity')
        if artifact == 'journal':
            operation_id = (x.positive['delete_job']['operation_id'] if which == 'positive'
                            else x.row['leaf_unknown_new_request_blocked']['operation_id'])
            with sqlite3.connect(path) as db:
                db.execute("UPDATE jobs SET digest=? WHERE operation_id=?", ('0' * 64, operation_id))
        else:
            path.write_text(path.read_text(encoding='utf8') + '\n', encoding='utf8')
        return 'artificial-console.exe'

    monkeypatch.setattr(helper, 'installed_identity', rewrite)
    with pytest.raises(ValueError, match=('journal or parent changed' if artifact == 'journal'
                                          else 'SHA256 mismatch')):
        helper.audit_leaf_prerequisites(**arguments(x))
    assert calls == ['wheel', 'identity']
    after = artifact_hashes(x)
    assert after.pop(str(path)) != before.pop(str(path))
    assert after == before


def test_same_report_and_journal_cannot_supply_both_prerequisites(candidate):
    x, calls = candidate
    args = arguments(x)
    args.update(faults_report=x.positive_path,
                faults_report_sha256=x.args.positive_report_sha256)
    before = artifact_hashes(x)
    with pytest.raises(ValueError, match='Distinct original positive and fault journals'):
        helper.audit_leaf_prerequisites(**args)
    assert calls == []
    assert artifact_hashes(x) == before
