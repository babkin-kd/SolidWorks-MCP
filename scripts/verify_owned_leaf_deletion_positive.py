"""Installed own-leaf positive callback on the original B1 construction owner.

Uses the unchanged B1 CLI/preflight/setup/native census/cleanup. Deletion occurs
once at its first retire boundary, after independent BASE/8000/neighbor proof.
Failure propagates into that driver's retained STA; there is no cleanup, retry,
Undo, or pending guard reset. This is positive-only, never B2/public acceptance.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def detached(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True))


def receipt_facts(receipt):
    """Read held Python receipt data only; never query the deleted feature."""
    flags = ('attempted', 'native_call_returned', 'pending_creation', 'pending_sketch_close',
        'sketch_closed', 'selection_uncertain', 'restore_attempted', 'restored',
        'pending_native_step', 'native_step_journal_failed', 'view_state_uncertain')
    views = receipt.annotation_views
    model_view = receipt.model_view
    return detached(dict(flags={key: getattr(receipt, key) for key in flags},
        controls=receipt.controls, baseline_feature_summaries=[row for _, row in receipt.baseline_features],
        deleted=receipt.deleted, borrowed_sketch_snapshot=receipt.borrowed_sketch_snapshot,
        model_view_baseline=model_view.baseline,
        annotation_views=dict(baseline=[row.data for row in views.baseline],
            owned=[dict(view=row[0].data, bound_feature_retained=row[1] is not None) for row in views.owned],
            **{key: getattr(views, key) for key in ('binding_attempted', 'bound', 'retirement_attempted', 'retired')})))


def normal_flag_boundary(sw, old, new, report, persist, label):
    """One normally returned parent-owned flag handoff, never a recovery reset."""
    raw = sw.CommandInProgress
    require(type(raw) is bool and raw is old, 'Exact parent-owned flag boundary required: ' + label)
    step = dict(label=label, before=raw, requested=new, attempted=True, returned=False,
        pending=True, readback=None)
    report.setdefault('parent_guard_boundaries', []).append(step)
    report.update(native_calls_live=True, phase=label); persist()
    sw.CommandInProgress = new
    step.update(returned=True, pending=False)
    step['readback'] = sw.CommandInProgress; persist()
    require(type(step['readback']) is bool and step['readback'] is new,
            'Parent flag handoff return/readback unconfirmed: ' + label)
    report['native_calls_live'] = False; persist()


class OwnLeafPositiveHook:
    def __init__(self, driver, state, report, persist, *, leaf_factory, runner_factory):
        self.driver, self.state, self.report, self.persist = driver, Path(state), report, persist
        self.leaf_factory, self.runner_factory = leaf_factory, runner_factory
        self.original_factory = driver.RectangleConstructionCatalog
        self.original_retire = driver.retire_owned
        self.domains = []
        self.started = self.completed = self.failed = False
        self.delegations = 0
        self.neighbor_identity = None

    def construction(self, *args, **kwargs):
        require(not self.domains, 'Exactly one original construction catalog is required.')
        result = self.original_factory(*args, **kwargs)
        self.domains.append(result)
        return result

    def _parent(self):
        path = self.state / 'report.json'
        parent = json.loads(path.read_text(encoding='utf8'))
        self.report.update(parent_report_at_callback_sha256=sha256(path),
            parent_report_at_callback=detached(parent), wheel=parent['wheel'],
            package_origin_verified=parent['package_origin_verified'])
        self.persist()
        require(parent['phase'] == 'owned_cleanup' and parent['native_calls_live'] is False
            and parent['independent_native_readback_verified'] is True
            and parent['package_origin_verified'] is True and parent.get('retained_process', False) is False,
            'Parent must finish independent native BASE/volume/neighbor admission first.')
        volume = parent['independent_volume_mm3']
        require(type(volume) in (int, float) and math.isfinite(volume)
            and math.isclose(volume, 8000., rel_tol=1e-8, abs_tol=1e-6), 'Independent exact 8000 mm³ proof required.')
        require(bool(parent['captures']) and all(row['status'] == 'returned' for row in parent['captures']),
            'Every parent native capture must normally return.')
        require([row['label'] for row in parent['cases']] == [
            'B1-N1-separate-sketch-and-replay', 'B1-N1-separate-extrusion-and-replay',
            'B1-N2-N3-exact-native-base-and-neighbor'] and all(row['passed'] is True for row in parent['cases']),
            'Exact completed parent pre-cleanup positive chain required.')
        for key in ('sketch_job', 'extrusion_job'):
            require(self.driver.verified_rectangle_job(parent[key]), 'Original committed creation proof required: ' + key)
        return parent

    def _callback(self, sw, target, owned):
        self.started = True  # Consume before any reads; failure cannot be retried.
        report, persist, driver = self.report, self.persist, self.driver
        started = time.perf_counter()
        report.update(callback_attempted=True, callback_passed=False, phase='leaf_admission'); persist()
        require(len(self.domains) == 1, 'Singular original construction owner required.')
        original = self.domains[0]
        adapter, store = original.adapter, original.store
        require(adapter.identity(adapter._sw) == adapter.identity(sw)
            and len(owned) == 2 and not original.receipts,
            'Same original application/two-fixture construction owner required.')
        parent = self._parent()
        extrusion, sketch = parent['extrusion_job'], parent['sketch_job']
        arguments = extrusion['payload']['arguments']
        document_id, configuration = arguments['document_id'], arguments['configuration']
        object_id = extrusion['result']['value']['feature_object_id']
        sketch_id = sketch['result']['value']['sketch_object_id']
        require(arguments['sketch_object_id'] == sketch_id
            and sketch['payload']['arguments']['document_id'] == document_id, 'Exact original borrowed sketch chain required.')
        for creation in (sketch, extrusion):
            current = store.get(creation['operation_id'])
            require(current == creation and current['status'] == 'succeeded'
                and current['mutation']['phase'] == 'committed', 'Actual original SQLite succeeded/committed row required.')
        binding, feature = original.ownership.resolve(document_id, configuration, object_id,
            connection_epoch=original.connection_epoch)
        target_identity = adapter.identity(target)
        require(binding.kind == 'extrusion' and target_identity == binding.model_identity
            and adapter.identity(binding.model) == binding.model_identity
            and adapter.identity(feature) == binding.feature_identity
            and adapter.identity(adapter.active_document()) == binding.model_identity,
            'Cleanup hook target must be the exact active original owned native part/feature.')
        identities = [adapter.identity(model) for model in owned]
        require(sum(identity == binding.model_identity for identity in identities) == 1
            and len(adapter.documents()) == 2
            and all(adapter.identity(model) in identities for model in adapter.documents()),
            'Two current exact owned fixtures required; no roster/name adoption.')
        neighbor = next(model for model in owned if adapter.identity(model) != binding.model_identity)
        self.neighbor_identity = adapter.identity(neighbor)
        entry, observed = original.documents.resolve(document_id, configuration)
        require(entry.identity == binding.model_identity and observed['document_type'] == 'part'
            and observed['path'] == '' and observed['active_configuration'] == configuration
            and observed['configurations'] == [configuration], 'Exact unsaved one-configuration active part required.')
        base = driver.validated_rectangle_snapshot(parent['independent_base'])
        require(base['clone_state']['profile'] == driver.BASE and base['solid_body_count'] == 1,
            'Full independent parent BASE required before deletion.')
        require(driver.validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == parent['independent_neighbor']
            and neighbor.GetSaveFlag() is True, 'Independent original dirty neighbor proof required before deletion.')
        original_receipt = binding.receipt
        retained_fields = ('extrusion', 'extrusion_identity', 'borrowed_sketch', 'borrowed_sketch_identity',
            'model_identity', 'configuration_identity', 'annotation_views', 'model_view', 'native_step_recorder')
        retained = {key: getattr(original_receipt, key) for key in retained_fields}
        retained_views = [(row, row.view, row.token) for row in original_receipt.annotation_views.baseline]
        retained_owned_views = [(row, row[0], row[0].view, row[0].token, row[1])
            for row in original_receipt.annotation_views.owned]
        facts = receipt_facts(original_receipt)
        report.update(original_creation_receipt_before=facts, original_creation_job=detached(extrusion),
            original_sketch_job=detached(sketch), explicit_target=dict(document_id=document_id,
                configuration=configuration, object_id=object_id, creation_operation_id=binding.creation_operation_id,
                feature_pid_hex=binding.persistent_id.hex(), feature_native_id=binding.native_id))
        persist()
        normal_flag_boundary(sw, True, False, report, persist, 'parent_owned_guard_release')
        leaf = self.leaf_factory(original.documents, store, original.connection_epoch, original.ownership)
        require(leaf.ownership is original.ownership and leaf.store is store and leaf.documents is original.documents,
                'Leaf must use the original live catalog/ownership/SQLite; no reconstruction.')
        runner = self.runner_factory(store, driver.InlineSta())
        context = dict(document_id=document_id, configuration=configuration, object_id=object_id)
        report.update(phase='leaf_prepare', native_calls_live=True); persist()
        prepared_job = runner.submit('own-leaf-positive-prepare', 'feature.prepare_leaf_deletion', context,
            lambda: leaf.prepare(**context), context=context)
        report['prepare_job'] = detached(store.get(prepared_job['operation_id'])); persist()
        require(report['prepare_job'] == prepared_job and prepared_job['status'] == 'succeeded'
            and prepared_job['error'] is None, 'Normally completed actual SQLite leaf preparation required.')
        prepared = prepared_job['result']
        require(prepared['delete_authorized'] is False and prepared['native_execution_available'] is True
            and prepared['baseline']['snapshots'][document_id] == base,
            'Positive-only execution availability and exact parent BASE baseline required.')
        report['native_calls_live'] = False; persist()
        deletion_args = dict(context, expected_revision=prepared['revision'])
        report.update(phase='leaf_delete', native_calls_live=True); persist()
        job = runner.submit('own-leaf-positive-delete', 'feature.delete_leaf', deletion_args,
            lambda operation_id: leaf.delete(operation_id, **deletion_args), context=deletion_args,
            mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        report['delete_job'] = detached(store.get(job['operation_id'])); persist()
        require(report['delete_job'] == job and job['status'] == 'succeeded' and job['error'] is None
            and job['mutation']['phase'] == 'committed'
            and job['mutation']['verification']['outcome'] == 'committed'
            and job['mutation']['verification']['evidence']['after'] == job['result']['after']
            and job['result']['verified'] is True, 'Actual SQLite succeeded committed leaf deletion required.')
        result = job['result']; after = result['after']
        require(after['pending'] is False and after['guard_released'] is True
            and after['receipt']['bridge_returned'] is True and after['receipt']['deletion_bridge_verified'] is True
            and after['sketch_canonical_and_pid_confirmed'] is True and after['target_canonical_absent'] is True
            and result['value']['preserved_sketch_object_id'] == sketch_id
            and not leaf.receipts and not original.receipts
            and store.mutation_blockers(original.connection_epoch, document_id, effect_scope='application') == [],
            'Full native released readback, retained sketch, clear receipts and application hold required.')
        require(type(sw.CommandInProgress) is bool and sw.CommandInProgress is False,
                'Leaf must normally release its own native guard to False.')
        report['native_calls_live'] = False; persist()
        def no_replay(_):
            raise AssertionError('Replay must not dispatch leaf native deletion.')
        replay = runner.submit('own-leaf-positive-delete', 'feature.delete_leaf', deletion_args, no_replay,
            context=deletion_args, mutates=True, pass_operation_id=True, verify=lambda value: value['verified'] is True)
        report['replay_job'] = detached(replay); persist()
        require(replay == job, 'Replay must return the exact original committed SQLite job.')
        require(store.get(extrusion['operation_id']) == extrusion and store.get(sketch['operation_id']) == sketch,
            'Original SQLite construction jobs must remain unchanged after leaf deletion/replay.')
        require(receipt_facts(original_receipt) == facts
            and all(getattr(original_receipt, key) is value for key, value in retained.items())
            and len(original_receipt.annotation_views.baseline) == len(retained_views)
            and all(current is row and current.view is view and current.token is token
                for current, (row, view, token) in zip(original_receipt.annotation_views.baseline, retained_views))
            and len(original_receipt.annotation_views.owned) == len(retained_owned_views)
            and all(current is row and current[0] is native_view and current[0].view is view
                and current[0].token is token and current[1] is feature_handle
                for current, (row, native_view, view, token, feature_handle) in
                    zip(original_receipt.annotation_views.owned, retained_owned_views)),
            'Original creation receipt and retained handles must stay unchanged; deleted feature is never queried.')
        sketch_binding, current_sketch = original.ownership.resolve(document_id, configuration, sketch_id,
            connection_epoch=original.connection_epoch)
        require(adapter.identity(current_sketch) == retained['borrowed_sketch_identity']
            and sketch_binding.feature_identity == retained['borrowed_sketch_identity']
            and (document_id, object_id) not in original.ownership._bindings,
            'Original borrowed sketch canonical binding survives; deleted opaque ID retires.')
        actual = driver.validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(target))
        require(actual == after['state']['snapshots'][document_id]
            and actual['clone_state']['profile'] == driver.SKETCH and actual['solid_body_count'] == 0,
            'Independent actual BASE→SKETCH/full surviving native oracle required.')
        require(driver.validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == parent['independent_neighbor'],
            'Independent original full neighbor oracle must survive deletion.')
        report.update(independent_after=actual, original_creation_receipt_after=receipt_facts(original_receipt),
            original_creation_jobs_unchanged=True, original_retained_receipt_unchanged=True,
            replay_no_second_native_dispatch=True, application_hold_clear=True,
            callback_seconds=time.perf_counter() - started)
        persist()
        normal_flag_boundary(sw, False, True, report, persist, 'parent_owned_guard_reacquire')
        self.completed = True
        report.update(callback_passed=True, phase='delegated_owned_cleanup')
        report.setdefault('cases', []).append(dict(label='own-leaf-original-base-to-sketch-commit-replay', passed=True)); persist()

    def retire(self, sw, module, root, retiring, owned, record):
        try:
            require(not self.failed, 'A failed callback/delegated close cannot dispatch any later cleanup.')
            require(len(retiring) == 1 and retiring[0] is root, 'Only the unchanged parent singular own retire call is supported.')
            if not self.started:
                self._callback(sw, root, owned)
            else:
                require(self.completed and self.delegations == 1 and len(owned) == 1
                    and self.domains[0].adapter.identity(root) == self.neighbor_identity,
                    'Failed/pending/repeated callback cannot dispatch cleanup or another deletion.')
            require(self.completed, 'Successful full leaf callback is required before any cleanup delegation.')
            self.delegations += 1  # Close attempt is one-shot even if delegated helper throws.
            return self.original_retire(sw, module, root, retiring, owned, record)
        except BaseException as error:
            self.failed = True
            self.report.update(phase='failed', error=str(error), traceback=traceback.format_exc(),
                parent_retained_sta_required=True); self.persist()
            raise


def main():
    # Inherit every original CLI option; its installed-wheel/package preflight
    # and fixture setup remain authoritative and precede CoInitialize.
    import verify_rectangle_stages_positive as driver
    from solidworks_mcp.owned_leaf_deletion_catalog import OwnLeafDeletionCatalog
    from solidworks_mcp.jobs import JobRunner
    option = sys.argv.index('--state-dir') if '--state-dir' in sys.argv else None
    require(option is not None and option + 1 < len(sys.argv), 'Inherited CLI requires --state-dir PATH.')
    state = Path(sys.argv[option + 1]).resolve()
    private = Path(__file__).resolve().parents[1] / 'work'
    require(state.is_relative_to(private) and state != private and not state.exists(), 'Use fresh private work/ state.')
    started = time.perf_counter()
    hashes = {name: sha256(Path(__file__).with_name(name)) for name in
        ('verify_owned_leaf_deletion_positive.py', *driver.HELPERS)}
    report = dict(scope='installed_owned_leaf_deletion_positive_only_v1', accepted=False,
        native_b2_accepted=False, public_mcp_accepted=False, positive_case_passed=False,
        phase='preflight', native_calls_live=False, cases=[], verifier_hashes=hashes)
    def persist():
        report['elapsed_seconds'] = time.perf_counter() - started
        if state.exists():
            (state / 'leaf-positive-report.json').write_text(json.dumps(report,
                ensure_ascii=False, allow_nan=False, indent=2), encoding='utf8')
    hook = OwnLeafPositiveHook(driver, state, report, persist,
        leaf_factory=OwnLeafDeletionCatalog, runner_factory=JobRunner)
    driver.RectangleConstructionCatalog, driver.retire_owned = hook.construction, hook.retire
    try:
        driver.main()
        parent = json.loads((state / 'report.json').read_text(encoding='utf8'))
        require(hook.completed and hook.delegations == 2 and parent['phase'] == 'terminal'
            and parent['positive_case_passed'] is True and parent['native_calls_live'] is False
            and parent['baseline_restored'] is True and parent['own_cleanup_verified'] is True
            and parent['owned_documents'] == []
            and parent['original_baseline'] == parent['restored_baseline']
            and parent['original_application'] == parent['restored_application'],
            'Exact parent terminal cleanup and independent original baseline required.')
        report.update(parent_final_report_sha256=sha256(state / 'report.json'), parent_final_report=parent,
            phase='terminal', positive_case_passed=True, native_calls_live=False,
            baseline_restored=True, own_cleanup_verified=True)
        report['cases'].append(dict(label='own-leaf-delegated-cleanup-original-baseline', passed=True)); persist()
    except BaseException as error:
        report.update(phase='failed', error=str(error)); persist(); raise
    finally:
        driver.RectangleConstructionCatalog, driver.retire_owned = hook.original_factory, hook.original_retire
    print(json.dumps(dict(positive_case_passed=True, native_b2_accepted=False,
        public_mcp_accepted=False, elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
