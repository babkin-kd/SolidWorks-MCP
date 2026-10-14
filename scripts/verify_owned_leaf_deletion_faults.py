"""Finite installed own-leaf failures; unknown SQL history is never reconciled.

Exact current-wheel positive evidence gates the unchanged B1 owner before COM.
Only the controlled Python observation fault after normal native completion may
reach own cleanup, after independent full effects/quiescence proof. Any other
unknown/pending outcome propagates into the parent's retained STA unchanged.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
import uuid

from verify_owned_leaf_deletion_positive import (
    OwnLeafPositiveHook, require, sha256, detached, receipt_facts, normal_flag_boundary)
from verifier_b2_observation_fault import LeafNoEffectFault, LeafObservationFault
from solidworks_mcp.jobs import JobRunner
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from solidworks_mcp.owned_leaf_deletion_postconditions import verified_owned_leaf_deletion
from verifier_b2_public_contract import durable_b2_job, verified_b2_job
from verifier_lifecycle import read_journal
from verifier_rectangle_positive_acceptance import validate_positive_report
from verifier_rectangle_stages import released_rectangle_guard


POSITIVE_HELPERS = ('verify_owned_leaf_deletion_positive.py',
    'verify_rectangle_stages_positive.py', 'verifier_rectangle_stages.py',
    'probe_native_first_save_domain.py', 'verify_installed_metadata.py',
    'verify_wheel_artifact.py', 'verify_bounds_measurements.py',
    'verify_export_operations.py', 'verify_native_document_open.py',
    'verify_native_first_save_rejections.py', 'verifier_dimension_diagnostics.py')


def positive_preflight(path, expected_hash, wheel, scripts):
    path, scripts = Path(path), Path(scripts)
    require(sha256(path) == expected_hash, 'Exact supplied positive report SHA256 required.')
    row = json.loads(path.read_text(encoding='utf8'))
    require(row['scope'] == 'installed_owned_leaf_deletion_positive_only_v1'
        and row['phase'] == 'terminal' and row['positive_case_passed'] is True
        and row['native_calls_live'] is False and row['accepted'] is False
        and row['native_b2_accepted'] is False and row['public_mcp_accepted'] is False
        and row.get('parent_retained_sta_required', False) is False
        and row['baseline_restored'] is True and row['own_cleanup_verified'] is True
        and row['wheel'] == wheel and row['package_origin_verified'] is True,
        'Terminal exact current-wheel own-leaf positive evidence required before COM.')
    require(type(row['verifier_hashes']) is dict and set(row['verifier_hashes']) == set(POSITIVE_HELPERS),
            'Exact complete positive helper manifest required; omissions/additions are inadmissible.')
    for name, expected in row['verifier_hashes'].items():
        require(Path(name).name == name and sha256(scripts / name) == expected,
                'Positive helper changed after acceptance: ' + name)
    parent = row['parent_final_report']
    require(type(parent['verifier_hashes']) is dict
        and set(parent['verifier_hashes']) == set(POSITIVE_HELPERS) - {'verify_owned_leaf_deletion_positive.py'},
        'Exact original parent helper manifest required.')
    require(parent['wheel'] == wheel and parent['phase'] == 'terminal'
        and parent['native_calls_live'] is False and parent['positive_case_passed'] is True
        and parent['baseline_restored'] is True and parent['own_cleanup_verified'] is True
        and parent['owned_documents'] == []
        and parent['original_baseline'] == parent['restored_baseline']
        and parent['original_application'] == parent['restored_application'],
        'Positive independent parent cleanup/baseline proof required.')
    require(sha256(path.with_name('report.json')) == row['parent_final_report_sha256']
        and json.loads(path.with_name('report.json').read_text(encoding='utf8')) == parent,
        'Exact actual positive parent report required.')
    validate_positive_report(parent, wheel,
        {name: row['verifier_hashes'][name] for name in parent['verifier_hashes']})
    rows = {job['operation_id']: job for job in read_journal(path.with_name('jobs.sqlite'))}
    preparation = durable_b2_job(row['prepare_job'], rows[row['prepare_job']['operation_id']])
    deletion = durable_b2_job(row['delete_job'], rows[row['delete_job']['operation_id']])
    durable_b2_job(row['replay_job'], deletion)
    require(verified_b2_job(preparation) and verified_b2_job(deletion, preparation_job=preparation),
            'Actual read-only SQL digest/prepare/full leaf commit invariants required before COM.')
    for key in ('sketch_job', 'extrusion_job'):
        durable_b2_job(parent[key], rows[parent[key]['operation_id']])
    return dict(positive_report_sha256=expected_hash, positive_report_path=str(path.resolve()),
        wheel=wheel, positive_helper_hashes=deepcopy(row['verifier_hashes']), positive_report_gate_verified=True)


def paired_steps(job):
    rows = job['mutation']['verification']['native_steps']
    require(type(rows) is list and 4 <= len(rows) <= 32 and len(rows) % 2 == 0,
            'Complete bounded paired native ledger required.')
    names = set()
    for index in range(0, len(rows), 2):
        a, b = rows[index:index + 2]
        require(type(a) is dict and type(b) is dict
            and set(a) == set(b) == {'sequence', 'name', 'phase', 'evidence'}
            and type(a['sequence']) is int and type(b['sequence']) is int
            and a['sequence'] == index + 1 and b['sequence'] == index + 2
            and a['phase'] == 'pending' and b['phase'] == 'returned'
            and type(a['name']) is str and type(b['name']) is str
            and a['name'].startswith('leaf_') and a['name'] == b['name'] and a['name'] not in names
            and type(a['evidence']) is dict and type(b['evidence']) is dict,
            'Every native step must normally return once in the durable ledger.')
        names.add(a['name'])
    return detached(rows)


def released_native_guard(evidence, ids):
    require(type(evidence) is dict, 'Exact native guard evidence object required.')
    require(type(ids) is list and all(type(value) is str and bool(value) for value in ids)
        and len(ids) == len(set(ids)), 'Exact unique original guard document IDs required.')
    require(detached(evidence.get('activation_ui_release')) == {'attempted': False, 'verified': False}
        and type(evidence['activation_ui_release']['attempted']) is bool
        and type(evidence['activation_ui_release']['verified']) is bool,
        'Typed exact native activation UI receipt required.')
    synthetic = dict(scope='rectangle_construction_guard_v1', native_guards=[evidence],
        guard_released=True, pending_release=False, journal_failed=False,
        reference_binding_unconfirmed=False, full_release_check='effect')
    require(released_rectangle_guard(synthetic, ids),
            'Exact normally released native application/model/selection guard required.')


def prove_quiescent_effect(leaf, binding, job, fault, report, persist):
    require(job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved'
        and job['mutation']['reconciliation'] is None,
        'Controlled fault must retain actual unknown/unresolved history.')
    context = leaf.receipts[job['operation_id']]
    facts = context['action'].evidence()
    require(context['released'] is True and context['release_attempted'] is True
        and context['pending_release'] is False and context['journal_failed'] is False
        and context['guarded_ids'] == ()
        and facts['attempted'] is True and facts['bridge_returned'] is True
        and facts['bridge_exception_returned'] is False and facts['pending_apply'] is False
        and facts['deletion_attempted'] is True and facts['deletion_bridge_verified'] is True
        and facts['pending_native_step'] is None and facts['journal_failed'] is False
        and facts['selection_uncertain'] is False and facts['view_state_uncertain'] is False,
        'Any pending COM, receipt, journal or guard flag prohibits own cleanup.')
    hook = fault.evidence()
    require(hook['normal_bridge_returns'] == hook['bridge_attempts'] == hook['bridge_dispatches'] == hook['injected_faults'] == 1
        and hook['pending_bridge'] is False and hook['pending_snapshot'] is False and hook['armed'] is False
        and hook['bridge_exception_returned'] is False and hook['snapshot_exception_returned'] is False,
        'Exactly one known Python fault after normal native bridge/full snapshot required.')
    before = job['mutation']['before_state']['baseline']
    ids = [row['document_id'] for row in before['semantic']['documents']]
    for guard in context['guards']: released_native_guard(guard.evidence, ids)
    steps = paired_steps(job)
    adapter = leaf.adapter
    require(type(adapter._sw.CommandInProgress) is bool and adapter._sw.CommandInProgress is False,
            'Actual native command must be False before quiescence observations.')
    first_entries, first = leaf._capture_current(binding)
    second_entries, second = leaf._capture_current(binding)
    require(first == second and [entry.identity for entry in first_entries] == [entry.identity for entry in second_entries]
        and any(entry.document_id == binding.document_id and entry.identity == binding.model_identity for entry in second_entries),
        'Two coherent full current native SKETCH/session captures required.')
    definition = BlindRectangleExtrusion.validate(**job['mutation']['before_state']['current_definition'])
    require(verified_owned_leaf_deletion(before, second, document_id=binding.document_id,
        configuration=binding.configuration, object_id=binding.object_id, feature_native_id=binding.native_id,
        feature_pid_hex=binding.persistent_id.hex(), current_definition=definition),
        'Production full BASE→SKETCH/session/neighbor postcondition required for cleanup.')
    require(second['snapshots'][binding.document_id] == hook['actual_after_snapshot'],
        'Controlled-fault full snapshot must equal independent current SKETCH.')
    borrowed = binding.receipt.borrowed_sketch
    members = adapter.features(binding.model)
    identity = adapter.identity(borrowed)
    require(identity == binding.receipt.borrowed_sketch_identity
        and sum(adapter.identity(member) == identity for member in members) == 1
        and not any(adapter.identity(member) == binding.feature_identity for member in members),
        'Original retained sketch survives; deleted canonical feature is absent from current census.')
    old = before['snapshots'][binding.document_id]
    sketch_id = old['clone_state']['sketch']['feature_native_id']
    position = next(i for i, row in enumerate(old['clone_state']['features']) if row['native_id'] == sketch_id)
    pid = bytes.fromhex(next(row['token'] for row in old['references']
        if row['kind'] == 'feature' and row['role'] == 'feature:' + str(position)))
    current = adapter.resolve_persistent_id(binding.model, pid, 'feature')
    require(current is not None and adapter.identity(current) == identity
        and adapter.persistent_id(binding.model, current) == pid, 'Original sketch PID/canonical roundtrip required.')
    raw, status = adapter._extension(binding.model).GetObjectByPersistReference3(adapter._persistent_variant(binding.persistent_id))
    require(type(status) is int and status in (1, 4) and raw is None,
            'Actual old PID invalid/deleted integer state and null object required.')
    report.update(unknown_quiescence=dict(native_action=facts, fault_hook=hook,
        native_guards=[deepcopy(guard.evidence) for guard in context['guards']], native_steps=steps,
        first_full_current=first, second_full_current=second, full_delta_verified=True,
        original_sketch_pid_hex=pid.hex(), old_feature_pid=dict(state=status, object_is_null=True),
        cleanup_scope='only_original_owned_test_documents', reconciliation_authorized=False))
    persist()
    return second


def run_fault_cases(original, leaf, binding, runner, report, persist, *, hooks):
    """Actual domain/runner/SQLite finite cases; no cleanup or reconciliation."""
    adapter, store = original.adapter, original.store
    context = dict(document_id=binding.document_id, configuration=binding.configuration, object_id=binding.object_id)
    creations = deepcopy(report['original_creation_jobs'])
    receipt_before = receipt_facts(binding.receipt)
    physical_bridge = adapter.restore_rectangle_extrusion
    physical_calls = []
    def observed_bridge(*args):
        physical_calls.append(dict(attempted=True, returned=False))
        value = physical_bridge(*args)
        physical_calls[-1]['returned'] = True
        return value
    adapter.restore_rectangle_extrusion = observed_bridge
    prepared = leaf.prepare(**context)
    initial_entries, initial = leaf._capture_current(binding)
    require(initial == prepared['baseline'], 'Actual full initial leaf preparation/session required.')
    report['initial_preparation'] = detached(prepared); persist()
    def submit(label, arguments):
        report.update(phase=label, native_calls_live=True); persist()
        value = runner.submit(label, 'feature.delete_leaf', arguments,
            lambda operation_id: leaf.delete(operation_id, **arguments), context=arguments,
            mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        require(store.get(value['operation_id']) == value, 'Actual SQLite job must match returned result.')
        report[label] = detached(value); persist()
        return value
    def replay(label, arguments, job):
        value = runner.submit(label, 'feature.delete_leaf', arguments,
            lambda _: (_ for _ in ()).throw(AssertionError('Replay cannot dispatch native deletion.')),
            context=arguments, mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        require(value == job, 'Exact same-ID failed/unknown replay required.')
        report[label + '_replay'] = detached(value); persist()
    for label, arguments in (
        ('leaf_stale', dict(context, expected_revision='rev_stale')),
        ('leaf_foreign', dict(context, object_id='feat_' + uuid.uuid4().hex, expected_revision=prepared['revision']))):
        job = submit(label, arguments)
        require(job['status'] == 'failed' and 'mutation' not in job and physical_calls == [],
                'Stale/foreign refusal must have no checkpoint/native bridge.')
        replay(label, arguments, job)
        _, actual = leaf._capture_current(binding)
        require(actual == initial and receipt_facts(binding.receipt) == receipt_before,
                'Full native before/receipt must survive stale/foreign refusal.')
        report['native_calls_live'] = False
        report.setdefault('cases', []).append(dict(label=label, passed=True)); persist()
    no_effect = LeafNoEffectFault(adapter, binding).install(); hooks.append(no_effect)
    arguments = dict(context, expected_revision=leaf.prepare(**context)['revision'])
    job = submit('leaf_no_effect', arguments)
    require(job['status'] == 'failed' and job['mutation']['phase'] == 'rolled_back'
        and job['mutation']['verification']['outcome'] == 'rolled_back', 'Actual durable known no-effect rollback required.')
    after = job['mutation']['verification']['evidence']['after']
    guard = job['mutation']['verification']['evidence']['execution_guard']
    require(after['pending'] is False and after['guard_released'] is True
        and after['state'] == job['mutation']['before_state']['baseline']
        and guard['guard_released'] is True and guard['pending_release'] is False
        and guard['journal_failed'] is False and guard['full_release_check'] == 'no_effect'
        and physical_calls == [] and not leaf.receipts
        and not store.mutation_blockers(original.connection_epoch, binding.document_id, effect_scope='application'),
        'Complete released no-effect state and clear application hold required.')
    for native in guard['native_guards']:
        released_native_guard(native, [row['document_id'] for row in initial['semantic']['documents']])
    paired_steps(job)
    facts = no_effect.evidence()
    require(facts['injected_faults'] == facts['bridge_dispatches'] == facts['bridge_attempts'] == 1
        and facts['normal_bridge_returns'] == 0 and facts['pending_bridge'] is facts['pending_snapshot'] is False,
        'Known Python failure must precede the original native bridge.')
    replay('leaf_no_effect', arguments, job)
    no_effect.detach(); report['no_effect_hook'] = no_effect.evidence()
    require(receipt_facts(binding.receipt) == receipt_before, 'Original successful creation receipt must survive no-effect fault.')
    report.update(native_calls_live=False); report['cases'].append(dict(label='leaf_no_effect', passed=True)); persist()
    observation = LeafObservationFault(adapter, binding).install(); hooks.append(observation)
    arguments = dict(context, expected_revision=leaf.prepare(**context)['revision'])
    job = submit('leaf_observation_unknown', arguments)
    require(job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved'
        and physical_calls == [dict(attempted=True, returned=True)],
        'One normally returned physical bridge must retain unknown SQL history.')
    replay('leaf_observation_unknown', arguments, job)
    blocked = submit('leaf_unknown_new_request_blocked', arguments)
    require(blocked['status'] == 'failed' and blocked['error']['code'] == 'document_mutation_blocked'
        and 'mutation' not in blocked and len(physical_calls) == 1,
        'Application unresolved hold must block another request before native dispatch.')
    current = prove_quiescent_effect(leaf, binding, job, observation, report, persist)
    require(receipt_facts(binding.receipt) == receipt_before
        and all(store.get(row['operation_id']) == row for row in creations),
        'Unknown effects cannot change original successful creation history/receipt.')
    observation.detach()
    adapter.restore_rectangle_extrusion = physical_bridge
    require(store.get(job['operation_id']) == job
        and store.mutation_blockers(original.connection_epoch, binding.document_id, effect_scope='application'),
        'Unknown/unresolved status and hold must remain after observation hooks detach.')
    report.update(native_calls_live=False, physical_bridge_calls=physical_calls,
        original_creation_receipt_after=receipt_facts(binding.receipt), original_creation_jobs_unchanged=True,
        unknown_job_retained=detached(job), unresolved_hold_before_cleanup=store.mutation_blockers(
            original.connection_epoch, binding.document_id, effect_scope='application'))
    report['cases'].append(dict(label='leaf_observation_unknown', passed=True))
    report['cases'].append(dict(label='leaf_unknown_new_request_blocked', passed=True)); persist()
    return current


class OwnLeafFaultHook(OwnLeafPositiveHook):
    def _callback(self, sw, target, owned):
        self.started = True
        report, persist, driver = self.report, self.persist, self.driver
        report.update(callback_attempted=True, callback_passed=False, phase='leaf_admission'); persist()
        require(len(self.domains) == 1, 'Singular original B1 construction catalog required.')
        original = self.domains[0]; adapter, store = original.adapter, original.store
        require(adapter.identity(adapter._sw) == adapter.identity(sw) and len(owned) == 2 and not original.receipts,
            'Exact canonical application/original two own fixtures required.')
        parent = self._parent()
        jobs = [parent['sketch_job'], parent['extrusion_job']]
        args = jobs[1]['payload']['arguments']
        document_id, configuration = args['document_id'], args['configuration']
        object_id = jobs[1]['result']['value']['feature_object_id']
        require(args['sketch_object_id'] == jobs[0]['result']['value']['sketch_object_id']
            and all(store.get(row['operation_id']) == row and row['status'] == 'succeeded'
                and row['mutation']['phase'] == 'committed' for row in jobs),
            'Actual original SQLite succeeded standalone-sketch/extrusion chain required.')
        binding, feature = original.ownership.resolve(document_id, configuration, object_id,
            connection_epoch=original.connection_epoch)
        require(binding.kind == 'extrusion' and adapter.identity(target) == binding.model_identity
            and adapter.identity(binding.model) == binding.model_identity and adapter.identity(feature) == binding.feature_identity
            and adapter.identity(adapter.active_document()) == binding.model_identity,
            'First retirement target must be the exact active original own feature/model.')
        tokens = [adapter.identity(model) for model in owned]
        require(len(adapter.documents()) == 2 and sum(token == binding.model_identity for token in tokens) == 1
            and all(adapter.identity(model) in tokens for model in adapter.documents()), 'Exact owned native census required.')
        neighbor = next(model for model in owned if adapter.identity(model) != binding.model_identity)
        self.neighbor_identity = adapter.identity(neighbor)
        base = driver.validated_rectangle_snapshot(parent['independent_base'])
        require(base['clone_state']['profile'] == driver.BASE and base['solid_body_count'] == 1
            and driver.validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == parent['independent_neighbor']
            and neighbor.GetSaveFlag() is True, 'Independent full original BASE/dirty neighbor proof required.')
        report.update(original_creation_jobs=detached(jobs), original_creation_receipt_before=receipt_facts(binding.receipt))
        persist()
        normal_flag_boundary(sw, True, False, report, persist, 'parent_owned_guard_release')
        self.leaf = self.leaf_factory(original.documents, store, original.connection_epoch, original.ownership)
        self.fault_hooks = []
        self.unknown_state = run_fault_cases(original, self.leaf, binding, self.runner_factory(store, driver.InlineSta()),
            report, persist, hooks=self.fault_hooks)
        normal_flag_boundary(sw, False, True, report, persist, 'parent_owned_guard_reacquire_after_quiescence')
        self.completed = True
        report.update(callback_passed=True, phase='delegated_owned_cleanup'); persist()


def main():
    import argparse
    import verify_rectangle_stages_positive as driver
    from solidworks_mcp.owned_leaf_deletion_catalog import OwnLeafDeletionCatalog
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--positive-report', type=Path, required=True)
    parser.add_argument('--positive-report-sha256', required=True)
    own, inherited = parser.parse_known_args()
    sys.argv = [sys.argv[0], *inherited]
    option = sys.argv.index('--state-dir') if '--state-dir' in sys.argv else None
    require(option is not None and option + 1 < len(sys.argv), 'Inherited CLI requires --state-dir PATH.')
    state = Path(sys.argv[option + 1]).resolve(); scripts = Path(__file__).resolve().parent
    require(state.is_relative_to(scripts.parent / 'work') and not state.exists(), 'Fresh private work/ state required.')
    report = dict(scope='installed_owned_leaf_deletion_faults_only_v1', accepted=False,
        native_b2_accepted=False, public_mcp_accepted=False, fault_cases_passed=False,
        phase='preflight', native_calls_live=False, cases=[], verifier_hashes={
            name: sha256(scripts / name) for name in ('verify_owned_leaf_deletion_faults.py',
                'verify_owned_leaf_deletion_positive.py', 'verifier_b2_observation_fault.py',
                'verifier_b2_public_contract.py', 'verifier_rectangle_positive_acceptance.py',
                'verifier_lifecycle.py', 'verifier_rectangle_public_contract.py',
                'verifier_first_save_public_contract.py', 'verifier_native_open.py',
                'verifier_native_part_activation.py', 'verifier_native_first_save.py',
                'verifier_rectangle_restoration.py', *driver.HELPERS)})
    started = time.perf_counter()
    def persist():
        report['elapsed_seconds'] = time.perf_counter() - started
        if state.exists(): (state / 'leaf-faults-report.json').write_text(json.dumps(report,
            ensure_ascii=False, allow_nan=False, indent=2), encoding='utf8')
    original_preflight = driver.package_evidence
    def gated_preflight(args, *, installed):
        evidence = original_preflight(args, installed=installed)
        report.update(positive_preflight(own.positive_report, own.positive_report_sha256, evidence['wheel'], scripts))
        persist(); return evidence
    hook = OwnLeafFaultHook(driver, state, report, persist,
        leaf_factory=OwnLeafDeletionCatalog, runner_factory=JobRunner)
    driver.package_evidence = gated_preflight
    driver.RectangleConstructionCatalog, driver.retire_owned = hook.construction, hook.retire
    try:
        driver.main()
        parent = json.loads((state / 'report.json').read_text(encoding='utf8'))
        require(hook.completed and hook.delegations == 2 and parent['phase'] == 'terminal'
            and parent['native_calls_live'] is False and parent['baseline_restored'] is True
            and parent['own_cleanup_verified'] is True and parent['owned_documents'] == []
            and parent['original_baseline'] == parent['restored_baseline']
            and parent['original_application'] == parent['restored_application'], 'Actual parent own cleanup/original baseline required.')
        # Original JobStore is closed by the successful parent. Inspect its SQLite
        # with a separate read-only connection; never reconcile or mutate holds.
        import sqlite3
        with sqlite3.connect((state / 'jobs.sqlite').as_uri() + '?mode=ro', uri=True) as database:
            unknown = report['unknown_job_retained']; oid = unknown['operation_id']
            row = database.execute('SELECT status FROM jobs WHERE operation_id=?', (oid,)).fetchone()
            mutation = database.execute('SELECT phase,reconciliation FROM mutations WHERE operation_id=?', (oid,)).fetchone()
            require(row == ('unknown',) and mutation == ('unresolved', None), 'Cleanup must preserve unresolved SQL job/hold.')
        report.update(phase='terminal', fault_cases_passed=True, native_calls_live=False,
            baseline_restored=True, own_cleanup_verified=True, unknown_sql_status_after_cleanup='unknown',
            unknown_sql_phase_after_cleanup='unresolved', reconciled=False,
            parent_final_report_sha256=sha256(state / 'report.json'), parent_final_report=parent)
        persist()
    except BaseException as error:
        report.update(phase='failed', error=str(error)); persist(); raise
    finally:
        driver.package_evidence = original_preflight
        driver.RectangleConstructionCatalog, driver.retire_owned = hook.original_factory, hook.original_retire
    print(json.dumps(dict(fault_cases_passed=True, native_b2_accepted=False, public_mcp_accepted=False)), flush=True)


if __name__ == '__main__': main()
