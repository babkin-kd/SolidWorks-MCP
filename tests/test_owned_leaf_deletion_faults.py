"""Source/pure fault driver: real domain/SQLite and artificial native records."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from test_owned_leaf_deletion_execution import execution
from test_owned_leaf_deletion_catalog import leaf, extrusion_proof, proof, case, domain
from test_owned_leaf_deletion_positive import artificial


scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
try:
    spec = importlib.util.spec_from_file_location('owned_leaf_fault_driver', scripts / 'verify_owned_leaf_deletion_faults.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
finally: sys.path.remove(str(scripts))


@pytest.fixture
def faults(execution):
    x = execution
    class Application:
        identity = object()
        @property
        def CommandInProgress(self): return x.busy
        @CommandInProgress.setter
        def CommandInProgress(self, value): x.busy = value
    x.c.adapter._sw = Application()
    class Guard:
        def __init__(self):
            self.evidence = dict(original_command_in_progress=False, acquired=False, released=False,
                scope='application_document_open_guard_v1',
                selection_preserved=False, baseline_document_ids=['target', 'neighbor'],
                activation_ui_release=dict(attempted=False, verified=False),
                model_guards=[dict(original_state=0, locked_state=2, released_state=0) for _ in x.entries])
        def __enter__(self):
            assert x.busy is False
            x.busy = True; x.guard_count += 1
            self.evidence['acquired'] = True
        def __exit__(self, *args):
            x.busy = False; x.releases += 1
            self.evidence.update(released=True, selection_preserved=True)
    x.c.adapter.native_open_guard = lambda *args: Guard()
    x.original = NS(adapter=x.c.adapter, store=x.store, connection_epoch='epoch')
    x.report = dict(native_calls_live=False, original_creation_jobs=[x.store.get(x.binding.creation_operation_id)], cases=[])
    x.persisted, x.hooks = [], []
    def persist(): x.persisted.append(deepcopy(x.report))
    x.persist = persist
    x.run = lambda: helper.run_fault_cases(x.original, x.leaf, x.binding, x.runner, x.report, persist, hooks=x.hooks)
    return x


def test_real_artificial_finite_failures_keep_unknown_hold_after_full_effect_proof(faults):
    x = faults
    original = x.store.get(x.binding.creation_operation_id)
    actual = x.run()
    assert x.report['leaf_stale']['status'] == x.report['leaf_foreign']['status'] == 'failed'
    assert 'mutation' not in x.report['leaf_stale'] and 'mutation' not in x.report['leaf_foreign']
    assert x.report['leaf_no_effect']['mutation']['phase'] == 'rolled_back'
    assert x.report['leaf_observation_unknown']['status'] == 'unknown'
    assert x.report['leaf_observation_unknown']['mutation']['phase'] == 'unresolved'
    assert x.report['leaf_observation_unknown'] == x.report['leaf_observation_unknown_replay']
    assert x.report['leaf_unknown_new_request_blocked']['error']['code'] == 'document_mutation_blocked'
    assert x.native_calls == ['delete', 'rebuild'] and x.bridge_calls == ['restore_rectangle_extrusion']
    assert x.after_forbidden_calls == []
    assert x.store.get(original['operation_id']) == original
    assert x.store.mutation_blockers('epoch', 'neighbor', effect_scope='application')
    assert x.report['unknown_quiescence']['full_delta_verified'] is True
    assert actual == x.report['unknown_quiescence']['first_full_current'] == x.report['unknown_quiescence']['second_full_current']
    assert x.hooks[0].detached and x.hooks[1].detached
    assert x.report['native_calls_live'] is False and x.report['physical_bridge_calls'] == [dict(attempted=True, returned=True)]
    assert [row['label'] for row in x.report['cases']] == ['leaf_stale', 'leaf_foreign', 'leaf_no_effect',
        'leaf_observation_unknown', 'leaf_unknown_new_request_blocked']


@pytest.mark.parametrize('fault', ['delete_pending', 'rebuild_pending', 'bad_after_data'])
def test_native_pending_or_partial_effect_is_never_quiescent_cleanup_proof(faults, fault):
    x = faults; x.fault = fault
    with pytest.raises((ValueError, RuntimeError)): x.run()
    assert 'unknown_quiescence' not in x.report
    assert len(x.bridge_calls) == 1
    assert not x.hooks[-1].detached
    assert x.store.mutation_blockers('epoch', 'neighbor', effect_scope='application')
    assert x.after_forbidden_calls == []


@pytest.mark.parametrize('fault', ['pending_release', 'journal_failed', 'pending_native', 'raw_pid', 'canonical_census', 'unpaired_ledger'])
def test_quiescence_refuses_guard_ledger_pid_or_membership_ambiguity(faults, fault, monkeypatch):
    x = faults; x.run()
    job = deepcopy(x.report['unknown_job_retained'])
    held = x.leaf.receipts[job['operation_id']]
    observation = x.hooks[-1]
    if fault == 'pending_release': held['pending_release'] = True
    elif fault == 'journal_failed': held['journal_failed'] = True
    elif fault == 'pending_native': held['action'].stage.pending_native_step = 'unconfirmed'
    elif fault == 'raw_pid':
        original = x.c.adapter._extension
        monkeypatch.setattr(x.c.adapter, '_extension', lambda model: NS(GetObjectByPersistReference3=lambda pid: (None, False)))
    elif fault == 'canonical_census':
        original = x.c.adapter.features
        monkeypatch.setattr(x.c.adapter, 'features', lambda model: [f for f in original(model) if f is not x.binding.receipt.borrowed_sketch])
    else: job['mutation']['verification']['native_steps'].pop()
    with pytest.raises((ValueError, RuntimeError)):
        helper.prove_quiescent_effect(x.leaf, x.binding, job, observation, {}, lambda: None)
    assert x.store.get(job['operation_id'])['status'] == 'unknown'
    assert x.store.mutation_blockers('epoch', 'neighbor', effect_scope='application')
    assert x.bridge_calls == ['restore_rectangle_extrusion'] and x.after_forbidden_calls == []


def fault_hook(artificial, monkeypatch, *, reject=False):
    a = artificial
    hook = helper.OwnLeafFaultHook(a.hook.driver, a.hook.state, a.report, lambda: None,
        leaf_factory=a.hook.leaf_factory, runner_factory=a.hook.runner_factory)
    hook.construction(None, None, 'epoch')
    calls = []
    def run(*args, **kwargs):
        calls.append('finite-fault-callback')
        if reject: raise ValueError('Artificial pending proof; retain STA.')
        return {'artificial_full_current': True}
    monkeypatch.setattr(helper, 'run_fault_cases', run)
    return hook, calls


def test_fault_retire_hook_same_application_canonical_proxies_then_two_own_delegations(artificial, monkeypatch):
    a = artificial
    a.original.adapter._sw = NS(token=a.sw.token)
    hook, calls = fault_hook(a, monkeypatch)
    hook.retire(a.sw, None, a.target, [a.target], a.owned, lambda _: None)
    hook.retire(a.sw, None, a.neighbor, [a.neighbor], a.owned, lambda _: None)
    assert calls == ['finite-fault-callback'] and a.flag_sets == [False, True]
    assert hook.completed and a.delegations == [a.target, a.neighbor]
    with pytest.raises(ValueError): hook.retire(a.sw, None, a.neighbor, [a.neighbor], a.owned, lambda _: None)


@pytest.mark.parametrize('fault', ['pending', 'foreign_application', 'foreign_target', 'incomplete_parent'])
def test_fault_callback_pending_foreign_or_premature_never_cleans_resets_or_repeats(artificial, monkeypatch, fault):
    a = artificial
    root = a.target
    if fault == 'foreign_application': a.original.adapter._sw = NS(token=object())
    elif fault == 'foreign_target': root = NS(token=object())
    elif fault == 'incomplete_parent':
        a.parent['independent_native_readback_verified'] = False; a.write_parent()
    hook, calls = fault_hook(a, monkeypatch, reject=fault == 'pending')
    with pytest.raises(ValueError): hook.retire(a.sw, None, root, [root], a.owned, lambda _: None)
    with pytest.raises(ValueError): hook.retire(a.sw, None, a.target, [a.target], a.owned, lambda _: None)
    assert a.delegations == [] and a.deletes == 0 and hook.completed is False
    assert a.flag_sets == ([False] if fault == 'pending' else [])
    assert calls == (['finite-fault-callback'] if fault == 'pending' else [])


@pytest.fixture
def positive_receipt(tmp_path, monkeypatch):
    scripts = tmp_path / 'scripts'; scripts.mkdir()
    for name in helper.POSITIVE_HELPERS:
        (scripts / name).write_text('artificial helper ' + name, encoding='utf8')
    hashes = {name: helper.sha256(scripts / name) for name in helper.POSITIVE_HELPERS}
    wheel = dict(wheel_sha256='artificial-exact-current-wheel')
    parent = dict(wheel=wheel, phase='terminal', native_calls_live=False, positive_case_passed=True,
        baseline_restored=True, own_cleanup_verified=True, owned_documents=[],
        original_baseline=['artificial'], restored_baseline=['artificial'],
        original_application={'artificial': True}, restored_application={'artificial': True})
    jobs = []
    for index, operation in enumerate(('feature.prepare_leaf_deletion', 'feature.delete_leaf',
            'sketch.create_rectangle', 'part.extrude_rectangle')):
        row = dict(operation_id=str(index), request_id='artificial-' + str(index),
            digest='artificial-digest', status='succeeded', operation=operation,
            payload=dict(mutates=index != 0), mutation=None, result={'artificial': True}, error=None)
        jobs.append(row)
    prepare, deletion, sketch, extrusion = [{key: value for key, value in row.items() if key != 'digest'} for row in jobs]
    parent.update(verifier_hashes={name: value for name, value in hashes.items()
        if name != 'verify_owned_leaf_deletion_positive.py'}, sketch_job=sketch, extrusion_job=extrusion)
    parent_path = tmp_path / 'report.json'; parent_path.write_text(json.dumps(parent), encoding='utf8')
    receipt = dict(scope='installed_owned_leaf_deletion_positive_only_v1', phase='terminal',
        positive_case_passed=True, native_calls_live=False, accepted=False, native_b2_accepted=False,
        public_mcp_accepted=False, baseline_restored=True, own_cleanup_verified=True,
        package_origin_verified=True, wheel=wheel, verifier_hashes=hashes,
        prepare_job=prepare, delete_job=deletion, replay_job=deepcopy(deletion),
        parent_final_report=parent, parent_final_report_sha256=helper.sha256(parent_path))
    monkeypatch.setattr(helper, 'validate_positive_report', lambda row, expected, hashes: None)
    monkeypatch.setattr(helper, 'read_journal', lambda path: deepcopy(jobs))
    def bind(dto, raw):
        assert dto == {key: value for key, value in raw.items() if key != 'digest'}
        return deepcopy(raw)
    monkeypatch.setattr(helper, 'durable_b2_job', bind)
    monkeypatch.setattr(helper, 'verified_b2_job', lambda row, **kwargs: row['status'] == 'succeeded')
    path = tmp_path / 'leaf-positive-report.json'
    def save(): path.write_text(json.dumps(receipt), encoding='utf8')
    save()
    return NS(path=path, receipt=receipt, wheel=wheel, scripts=scripts, save=save, parent=parent, parent_path=parent_path)


def test_passive_gate_requires_exact_current_wheel_parent_report_and_helpers(positive_receipt):
    x = positive_receipt
    result = helper.positive_preflight(x.path, helper.sha256(x.path), x.wheel, x.scripts)
    assert result['positive_report_gate_verified'] is True


def test_passive_gate_cannot_ignore_strict_actual_sql_commit_contract(positive_receipt, monkeypatch):
    x = positive_receipt
    monkeypatch.setattr(helper, 'verified_b2_job', lambda *args, **kwargs: False)
    with pytest.raises(ValueError): helper.positive_preflight(x.path, helper.sha256(x.path), x.wheel, x.scripts)


@pytest.mark.parametrize('fault', ['wrong_wheel', 'wrong_hash', 'running', 'helper_changed', 'parent_changed',
    'unrestored', 'omitted_manifest', 'extra_manifest', 'omitted_parent_manifest'])
def test_positive_preflight_rejects_without_native_entry(positive_receipt, fault):
    x = positive_receipt; wheel = x.wheel; expected = helper.sha256(x.path)
    if fault == 'wrong_wheel': wheel = {'wheel_sha256': 'other-wheel'}
    elif fault == 'wrong_hash': expected = '0' * 64
    elif fault == 'running': x.receipt['phase'] = 'running'; x.save(); expected = helper.sha256(x.path)
    elif fault == 'helper_changed': (x.scripts / helper.POSITIVE_HELPERS[0]).write_text('changed', encoding='utf8')
    elif fault == 'parent_changed': x.parent_path.write_text('{}', encoding='utf8')
    elif fault == 'unrestored': x.receipt['baseline_restored'] = False; x.save(); expected = helper.sha256(x.path)
    elif fault == 'omitted_manifest':
        x.receipt['verifier_hashes'].pop(helper.POSITIVE_HELPERS[0]); x.save(); expected = helper.sha256(x.path)
    elif fault == 'extra_manifest':
        x.receipt['verifier_hashes']['unexpected.py'] = '0' * 64; x.save(); expected = helper.sha256(x.path)
    else:
        x.parent['verifier_hashes'].pop(helper.POSITIVE_HELPERS[1])
        x.parent_path.write_text(json.dumps(x.parent), encoding='utf8')
        x.receipt['parent_final_report_sha256'] = helper.sha256(x.parent_path)
        x.save(); expected = helper.sha256(x.path)
    with pytest.raises(ValueError): helper.positive_preflight(x.path, expected, wheel, x.scripts)


def artificial_steps(count=4):
    return [dict(sequence=index + 1, name='leaf_step_' + str(index // 2),
        phase='pending' if index % 2 == 0 else 'returned', evidence={}) for index in range(count)]


@pytest.mark.parametrize('fault', ['bool_sequence', 'extra_key', 'missing_key', 'name_type',
    'foreign_prefix', 'evidence_type', 'oversized', 'odd', 'too_short', 'duplicate'])
def test_paired_ledger_rejects_hostile_types_shapes_scope_or_budget(fault):
    rows = artificial_steps()
    if fault == 'bool_sequence': rows[0]['sequence'] = True
    elif fault == 'extra_key': rows[0]['extra'] = None
    elif fault == 'missing_key': rows[0].pop('evidence')
    elif fault == 'name_type': rows[0]['name'] = 1
    elif fault == 'foreign_prefix': rows[0]['name'] = rows[1]['name'] = 'foreign_step'
    elif fault == 'evidence_type': rows[0]['evidence'] = []
    elif fault == 'oversized': rows = artificial_steps(34)
    elif fault == 'odd': rows = artificial_steps(33)
    elif fault == 'too_short': rows = artificial_steps(2)
    else: rows[2]['name'] = rows[3]['name'] = rows[0]['name']
    with pytest.raises(ValueError): helper.paired_steps({'mutation': {'verification': {'native_steps': rows}}})


def test_paired_ledger_accepts_the_finite_native_budget_boundary():
    for count in (4, 32):
        rows = artificial_steps(count)
        assert helper.paired_steps({'mutation': {'verification': {'native_steps': rows}}}) == rows


@pytest.mark.parametrize('fault', ['scope', 'duplicate_ids', 'extra_native_key', 'bool_model_state',
    'activation_number', 'selection_number', 'extra_activation_key', 'foreign_ids'])
def test_native_guard_rejects_hostile_scope_keys_ids_and_boolean_coercion(fault):
    guard = dict(scope='application_document_open_guard_v1', original_command_in_progress=False,
        acquired=True, released=True, selection_preserved=True, baseline_document_ids=['target', 'neighbor'],
        activation_ui_release=dict(attempted=False, verified=False),
        model_guards=[dict(original_state=0, locked_state=2, released_state=0) for _ in range(2)])
    if fault == 'scope': guard['scope'] = 'foreign_guard'
    elif fault == 'duplicate_ids': guard['baseline_document_ids'] = ['target', 'neighbor', 'target']
    elif fault == 'extra_native_key': guard['unknown'] = None
    elif fault == 'bool_model_state': guard['model_guards'][0]['original_state'] = False
    elif fault == 'activation_number': guard['activation_ui_release']['attempted'] = 0
    elif fault == 'selection_number': guard['selection_preserved'] = 1
    elif fault == 'extra_activation_key': guard['activation_ui_release']['unknown'] = False
    else: guard['baseline_document_ids'] = ['target', 'foreign']
    with pytest.raises(ValueError): helper.released_native_guard(guard, ['target', 'neighbor'])
