"""Source/pure driver refusal cases with artificial native-shaped adapters.

No installed-wheel acceptance, COM initialization, CAD connection or native run.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from test_b2_probe_observer import observer
from test_b2_suppression_probe import receipt, proof, helper as gate


path = Path(__file__).resolve().parents[1] / 'scripts/verify_b2_suppression_pid.py'
spec = importlib.util.spec_from_file_location('b2_suppression_pid_driver', path)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


@pytest.fixture
def preflight(tmp_path, monkeypatch):
    root = tmp_path
    scripts = root / 'scripts'; scripts.mkdir()
    work = root / 'work'; work.mkdir()
    wheel_path = work / 'accepted.whl'; wheel_path.write_bytes(b'artificial wheel; not an installation')
    monkeypatch.setattr(driver, 'WHEEL_SHA', driver.digest(wheel_path))
    for name in (*driver.HELPERS, 'old_b1_helper.py'):
        (scripts / name).write_text('artificial helper ' + name, encoding='utf8')
    wheel = dict(wheel_sha256=driver.WHEEL_SHA, package_version=driver.VERSION, git_sha=driver.GIT_SHA)
    hashes = {}
    for label in ('positive', 'faults', 'public'):
        folder = work / f'native-rectangle-dev94-{label}-1'; folder.mkdir()
        row = dict(phase='terminal', native_calls_live=False, baseline_restored=True,
            own_cleanup_verified=True, independent_native_readback_verified=True,
            wheel=deepcopy(wheel), verifier_hashes={'old_b1_helper.py': driver.digest(scripts / 'old_b1_helper.py')})
        report = folder / 'report.json'; report.write_text(json.dumps(row), encoding='utf8')
        hashes[label] = driver.digest(report)
    audit = dict(b1_accepted=True, full_baseline_verified=True, wheel=wheel, report_sha256=hashes)
    audit_path = work / 'audit.json'; audit_path.write_text(json.dumps(audit), encoding='utf8')
    monkeypatch.setattr(driver, 'AUDIT_SHA', driver.digest(audit_path))
    calls = []
    def validate(current, **expected):
        calls.append(('validate', current, expected))
        return deepcopy(wheel)
    def installed(current):
        calls.append(('installed', current)); return work / 'artificial-console.exe'
    args = NS(run_solidworks=True, state_dir=work / 'fresh', wheel=wheel_path, b1_audit=audit_path)
    def run(): return driver.passive_preflight(args, root=root, validate=validate, installed=installed)
    return NS(root=root, args=args, calls=calls, run=run, audit=audit, audit_path=audit_path, monkeypatch=monkeypatch)


def test_passive_preflight_hashes_same_accepted_reports_helpers_without_state_write(preflight):
    result = preflight.run()
    assert result['passive_preflight_verified'] is True
    assert result['metadata_mcp_launched'] is False
    assert not preflight.args.state_dir.exists()
    assert set(result['b1_report_sha256']) == {'positive', 'faults', 'public'}
    assert result['verifier_hashes']['old_b1_helper.py'] == driver.digest(preflight.root / 'scripts/old_b1_helper.py')
    assert [call[0] for call in preflight.calls] == ['validate', 'installed']
    assert preflight.calls[0][2] == dict(expected_version=driver.VERSION, expected_git_sha=driver.GIT_SHA)


@pytest.mark.parametrize('fault', ['no_opt_in', 'state_exists', 'outside_work', 'work_root',
    'wheel_hash', 'audit_hash', 'report_hash', 'helper_hash', 'foreign_wheel', 'installed_origin'])
def test_preflight_refuses_before_any_native_entry_or_state_creation(preflight, fault):
    if fault == 'no_opt_in': preflight.args.run_solidworks = False
    elif fault == 'state_exists': preflight.args.state_dir.mkdir()
    elif fault == 'outside_work': preflight.args.state_dir = preflight.root / 'outside'
    elif fault == 'work_root': preflight.args.state_dir = preflight.root / 'work'
    elif fault == 'wheel_hash': preflight.args.wheel.write_bytes(b'changed')
    elif fault == 'audit_hash': preflight.audit_path.write_text('{}', encoding='utf8')
    elif fault == 'report_hash':
        (preflight.root / 'work/native-rectangle-dev94-positive-1/report.json').write_text('{}', encoding='utf8')
    elif fault == 'helper_hash':
        (preflight.root / 'scripts/old_b1_helper.py').write_text('changed', encoding='utf8')
    elif fault == 'foreign_wheel':
        preflight.audit['wheel']['git_sha'] = 'foreign'
        preflight.audit_path.write_text(json.dumps(preflight.audit), encoding='utf8')
        preflight.monkeypatch.setattr(driver, 'AUDIT_SHA', driver.digest(preflight.audit_path))
    else:
        def refused(_): raise ValueError('artificial wrong package origin')
        preflight.run = lambda: driver.passive_preflight(preflight.args, root=preflight.root,
            validate=lambda *a, **k: deepcopy(preflight.audit['wheel']), installed=refused)
    with pytest.raises(ValueError): preflight.run()
    if fault not in ('state_exists', 'work_root'):
        assert not preflight.args.state_dir.exists()
    if fault not in ('foreign_wheel', 'installed_origin'):
        assert not any(call[0] == 'installed' for call in preflight.calls)


@pytest.mark.parametrize('docs,active,command,user', [([object()], None, False, True),
    ([], object(), False, True), ([], None, True, True), ([], None, 0, True),
    ([], None, None, True), ([], None, False, False)])
def test_user_or_busy_session_refused_before_creation(docs, active, command, user):
    sw = NS(GetDocuments=lambda: docs, ActiveDoc=active, CommandInProgress=command, UserControl=user)
    with pytest.raises(ValueError): driver.require_free_session(sw)


@pytest.fixture
def flow(observer):
    state = observer
    state.actions, state.guards, state.persisted = [], [], []
    state.action_fault = None
    class Guard:
        def __init__(self):
            self.evidence = dict(original_command_in_progress=False, acquired=False, released=False,
                selection_preserved=False, model_guards=[dict(original_state=0, locked_state=2, released_state=0)])
        def __enter__(self):
            assert state.sw.CommandInProgress is False
            self.evidence['acquired'] = True; state.sw.CommandInProgress = True
            return self
        def __exit__(self, *exc):
            state.sw.CommandInProgress = False
            self.evidence.update(released=True, selection_preserved=True)
            if state.action_fault == 'guard_release': raise ValueError('artificial unconfirmed release')
    def guard(model):
        assert model is state.model
        result = Guard(); state.guards.append(result); return result
    def suppress(mode, option, names):
        state.actions.append(('SetSuppression2', mode, option, names))
        if state.action_fault == 'setter_throw': raise RuntimeError('artificial unknown setter')
        if state.action_fault == 'setter_false': return False
        state.target.row['suppressed'] = mode == 0
        if state.action_fault == 'suppressed_observation': state.fault = 'body_remaining'
        return True
    def rebuild(flag):
        state.actions.append(('ForceRebuild3', flag))
        if state.action_fault == 'rebuild_false': return False
        if state.action_fault == 'rebuild_throw': raise RuntimeError('artificial unknown rebuild')
        return True
    state.target.SetSuppression2 = suppress
    state.model.ForceRebuild3 = rebuild
    state.adapter.mutation_guard = guard
    state.adapter.active_document = lambda: state.model
    state.report = dict(native_calls_live=False)
    def persist(): state.persisted.append(deepcopy(state.report))
    state.run = lambda: driver.perform_probe(state.instance, state.report, persist, validate=gate.validate_probe)
    return state


def test_normal_artificial_flow_has_four_exact_actions_and_released_three_phases(flow):
    result = flow.run()
    assert flow.actions == [('SetSuppression2', 0, 1, None), ('ForceRebuild3', False),
                            ('SetSuppression2', 2, 1, None), ('ForceRebuild3', False)]
    assert [row['phase'] for row in result['observations']] == ['before', 'suppressed', 'restored']
    assert flow.report['receipt_gate']['receipt_validated'] is True
    assert flow.report['receipt_gate']['native_b2_accepted'] is False
    assert flow.report['native_normal_completion_verified'] is True
    assert len(flow.report['action_guards']) == 4
    assert all(row.evidence['released'] is True for row in flow.guards)
    assert flow.sw.CommandInProgress is False and flow.report['native_calls_live'] is False
    assert any(row['probe_receipt']['actions'][-1]['pending'] is True for row in flow.persisted
               if row['probe_receipt']['actions'])


@pytest.mark.parametrize('fault,count,pending', [('setter_throw', 1, True),
    ('setter_false', 1, False), ('guard_release', 1, False),
    ('rebuild_false', 2, False), ('rebuild_throw', 2, True), ('suppressed_observation', 2, False)])
def test_failed_unknown_and_unconfirmed_steps_never_unsuppress_or_retry(flow, fault, count, pending):
    flow.action_fault = fault
    with pytest.raises((ValueError, RuntimeError)): flow.run()
    assert len(flow.actions) == count
    assert flow.report['probe_receipt']['actions'][-1]['pending'] is pending
    assert 'native_normal_completion_verified' not in flow.report
    assert 'receipt_gate' not in flow.report
    assert not any(call[0] == 'SetSuppression2' and call[1] == 2 for call in flow.actions)


def test_initial_observer_refusal_prevents_all_mutations_and_guards(flow):
    flow.fault = 'foreign_document'
    with pytest.raises(ValueError): flow.run()
    assert flow.actions == [] and flow.guards == []


def test_stale_pid_before_action_refuses_without_fallback(flow):
    original = flow.adapter.resolve_persistent_id
    def resolve(*args):
        if flow.sw.CommandInProgress is True: return None
        return original(*args)
    flow.adapter.resolve_persistent_id = resolve
    with pytest.raises(ValueError): flow.run()
    assert flow.actions == []
    assert len(flow.guards) == 1 and flow.guards[0].evidence['released'] is True
    assert flow.report['probe_receipt']['actions'][0]['native_call_attempted'] is False


def test_gate_failure_does_not_grant_native_completion_or_cleanup(flow, monkeypatch):
    def reject(_): raise ValueError('strict gate rejected artificial restored drift')
    with pytest.raises(ValueError):
        driver.perform_probe(flow.instance, flow.report, lambda: None, validate=reject)
    assert len(flow.actions) == 4
    assert 'native_normal_completion_verified' not in flow.report


def test_name_correction_retains_original_candidate_and_recaptures_real_restored_phase(flow):
    original_observe = flow.instance.observe_phase
    phases = []
    def observe(phase):
        phases.append(phase)
        produced = original_observe(phase)
        if phase == 'restored' and phases.count('restored') == 1:
            produced['observation']['full_snapshot']['clone_state']['body']['name'] = 'Основание'
        return produced
    flow.instance.observe_phase = observe
    corrections = []
    def correct(observer, before, restored, report, persist):
        corrections.append(deepcopy(restored))
        assert restored['full_snapshot']['clone_state']['body']['name'] == 'Основание'
        return True
    driver.perform_probe(flow.instance,flow.report,lambda: None,
        validate=gate.validate_probe,restore_body_name=correct)
    assert phases == ['before','suppressed','restored','restored'] and len(corrections) == 1
    assert flow.report['pre_body_name_restore_observation'] == corrections[0]
    assert flow.report['probe_receipt']['observations'][-1] != corrections[0]
    assert flow.report['receipt_gate']['receipt_validated'] is True


def test_name_correction_refusal_prevents_recapture_and_completion(flow):
    calls = []
    def refuse(*args):
        calls.append(True)
        raise ValueError('Observed delta is outside own body/name scope.')
    with pytest.raises(ValueError):
        driver.perform_probe(flow.instance,flow.report,lambda: None,
            validate=gate.validate_probe,restore_body_name=refuse)
    assert len(calls) == 1 and len(flow.report['probe_receipt']['actions']) == 4
    assert 'pre_body_name_restore_observation' not in flow.report
    assert 'native_normal_completion_verified' not in flow.report
