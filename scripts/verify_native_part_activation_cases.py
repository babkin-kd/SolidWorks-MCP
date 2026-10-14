"""One-owner installed ACT-N2/N3/N4 case; not whole activation acceptance.

Own fixture setup uses the established rectangular-base builder. Unknown/live
effects retain this process and every exact receipt; no COM cancellation,
inverse activation, roster-delta cleanup or automatic retry.
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import traceback
import uuid

import pythoncom

from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.native_first_save import validated_part_snapshot
from solidworks_mcp.native_part_activation import NativePartActivationCatalog, SCOPE
from solidworks_mcp.part_creation import BaseRectangle, validated_plane_transform
from solidworks_mcp.session import SolidWorksSession
from probe_native_first_save_domain import package_evidence
from verify_bounds_measurements import InlineSta
from verify_component_reads import native_identity
from verify_export_operations import activate_owned, application_preferences
from verify_native_document_open import retire_owned, snapshot
from verify_native_first_save_rejections import owned_document_rows
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verifier_native_part_activation import verified_committed_part_activation


HELPERS = ('verify_native_part_activation_cases.py', 'verifier_native_part_activation.py', 'probe_native_first_save_domain.py',
           'verify_installed_metadata.py', 'verify_wheel_artifact.py',
           'verify_bounds_measurements.py', 'verify_component_reads.py',
           'verify_export_operations.py', 'verify_native_document_open.py',
           'verify_native_first_save_rejections.py', 'verifier_dimension_diagnostics.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--case', choices=('already_active', 'stale', 'controlled_after_call'), required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    args = parser.parse_args()
    assert args.run_solidworks
    state = args.state_dir.resolve()
    assert state.is_relative_to(Path.cwd() / 'work') and not state.exists()
    state.mkdir()
    args.state_dir = state
    started = time.perf_counter()
    report = dict(scope='installed_native_part_activation_case_only', case=args.case, accepted=False,
                  activation_case_passed=False, actual_com_failure_injected=False, cases=[], captures=[], owned_documents=[],
                  native_calls_live=False, phase='preflight',
                  verifier_hashes={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in HELPERS})

    def persist():
        report['elapsed_seconds'] = time.perf_counter() - started
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')

    def record(models):
        report['owned_documents'] = owned_document_rows(models)
        persist()

    # Wheel/origin/metadata are checked before the first native connection.
    try:
        report.update(package_evidence(args, installed=True))
    except BaseException as error:
        report.update(phase='preflight_failed', error=str(error), traceback=traceback.format_exc())
        persist()
        raise

    class ObservedDocuments(SolidWorksDocuments):
        activations = 0
        fault_enabled = False

        def activate_native_open_document(self, receipt):
            self.activations += 1
            report['native_calls_live'] = True
            persist()
            try:
                returned = super().activate_native_open_document(receipt)
                report['original_activation_receipt'] = dict(native_call_attempted=receipt.native_call_attempted,
                    native_call_returned=receipt.native_call_returned, pending_activation=receipt.pending_activation,
                    native_error=receipt.native_error)
                persist()
                if self.fault_enabled:
                    report['injection_applied'] = True
                    persist()
                    raise RuntimeError('Controlled bridge failure AFTER normal actual native activation')
                return returned
            finally:
                if receipt.native_call_returned is True and receipt.pending_activation is False:
                    report['native_calls_live'] = False
                    persist()

        def first_save_part_snapshot(self, model):
            row = dict(title=model.GetTitle(), started_s=time.perf_counter()-started, status='running')
            report['captures'].append(row)
            persist()
            try:
                result = super().first_save_part_snapshot(model)
                row.update(status='returned', elapsed_s=time.perf_counter()-started-row['started_s'])
                return result
            except BaseException as error:
                row.update(status='failed', error=str(error))
                raise
            finally:
                persist()

    owned = []
    store = domain = adapter = None
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        assert sw.CommandInProgress is False and sw.UserControl is True
        adapter = ObservedDocuments()
        original = snapshot(sw, module)
        original_application = adapter.native_close_application_context()
        preferences = application_preferences(sw)
        report.update(original_baseline=original, original_application=original_application,
                      original_preferences=preferences, phase='owned_fixture_creation')
        dimension_preference = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
        assert type(dimension_preference) is bool
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, False)
        session = SolidWorksSession()
        session._sw, session._mod = sw, module
        for name, sizes in (('Контрольная пластина активации', (40., 20., 12.)),
                            ('Рабочий сосед активации', (5., 6., 7.))):
            report['native_calls_live'] = True
            persist()
            created = session.new_part()
            model = session._model
            owned.append(model)
            assert type(created) is dict and created['ok'] is True and type(created['title']) is str
            report.setdefault('normal_creation_returns', []).append(created)
            report['native_calls_live'] = False
            record(owned)
            assert model.SetTitle2(name) and model.GetTitle() == name
            configuration = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
            configuration.Name = 'Основная'
            assert tuple(model.GetConfigurationNames()) == ('Основная',)
            features = adapter.features(model)
            frame = validated_plane_transform((1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.))
            planes = [f for f in features if f.GetTypeName2() == 'RefPlane'
                      and validated_plane_transform(adapter.reference_plane_transform(f)) == frame]
            assert len(planes) == 1
            definition = BaseRectangle.validate(plane_object_id='feat_'+uuid.uuid4().hex,
                                                width_mm=sizes[0], height_mm=sizes[1], depth_mm=sizes[2])
            receipt = adapter.new_base_receipt(model, features, adapter.part_creation_controls(model))
            report['native_calls_live'] = True
            persist()
            adapter.create_base_rectangle(model, planes[0], definition, receipt)
            report['native_calls_live'] = False
            record(owned)
            for index, feature in enumerate(session._iter_features(), 1):
                if feature.GetTypeName2() in ('RefPlane', 'ProfileFeature'):
                    feature.Name = f'Контрольный элемент {index}'
                    assert feature.Name == f'Контрольный элемент {index}'
            body_values = binding.wrap(model, module.IPartDoc).GetBodies2(-1, False)
            assert len(body_values) == 1
            body = binding.wrap(body_values[0], module.IBody2)
            body.Name = 'Тело основания'
            assert body.Name == 'Тело основания' and model.ForceRebuild3(False)
            model.ClearSelection2(True)
        target, neighbor = owned
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dimension_preference)
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is dimension_preference
        active_before = target if args.case == 'already_active' else neighbor
        activate_owned(sw, active_before, active_before.GetTitle())
        target_identity, neighbor_identity = native_identity(target), native_identity(neighbor)
        before = [validated_part_snapshot(adapter.first_save_part_snapshot(model)) for model in owned]
        report['independent_before'] = deepcopy(before)
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        documents = DocumentCatalog(adapter)
        documents.list()
        target_id = next(entry.document_id for entry in documents._entries if entry.identity == adapter.identity(target))
        store = JobStore(state / 'jobs.sqlite')
        domain = NativePartActivationCatalog(documents, store, 'activation_'+uuid.uuid4().hex)
        runner = JobRunner(store, InlineSta())
        arguments = dict(document_id=target_id, configuration='Основная')
        report['phase'] = 'full_domain_prepare'
        persist()
        prepared = runner.submit('prepare', 'document.prepare_activate_part_native', arguments,
                                 lambda: domain.prepare_activation(**arguments), context=arguments)
        report['preparation'] = prepared
        persist()
        assert prepared['status'] == 'succeeded'
        assert prepared['result']['already_active'] is (args.case == 'already_active')
        if args.case == 'stale':
            # An exact own feature is changed AFTER prepare; preserve the new
            # observed state rather than undoing a concurrent change.
            sw.CommandInProgress = True
            assert sw.CommandInProgress is True
            report['native_calls_live'] = True
            persist()
            bases = [feature for feature in adapter.features(neighbor) if feature.GetTypeName2() in ('Boss', 'Extrusion')]
            assert len(bases) == 1
            bases[0].Name = 'Основание после подготовки'
            assert bases[0].Name == 'Основание после подготовки' and neighbor.ForceRebuild3(False)
            report['native_calls_live'] = False
            before[1] = validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))
            report['independent_before_after_owned_rename'] = before
            sw.CommandInProgress = False
            assert sw.CommandInProgress is False
        adapter.fault_enabled = args.case == 'controlled_after_call'
        arguments['expected_revision'] = prepared['result']['revision']
        report['phase'] = 'full_domain_activate'
        persist()

        def execute():
            return runner.submit('activate', 'document.activate_part_native', arguments,
                lambda operation_id: domain.activate(operation_id, **arguments), context=arguments,
                mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)

        job = execute()
        report['job'] = job
        persist()
        if args.case == 'already_active':
            assert job['status'] == 'succeeded' and job['mutation']['phase'] == 'committed', job['error']
            assert verified_committed_part_activation(job)
            assert job['result']['value']['already_active'] is True
            assert adapter.activations == 0 and not domain.receipts
            assert execute() == job and adapter.activations == 0
            report['cases'].append(dict(label='ACT-N2-already-active-and-replay', passed=True))
        elif args.case == 'stale':
            assert job['status'] == 'failed' and job['error']['code'] == 'stale_revision', job['error']
            assert 'mutation' not in job and adapter.activations == 0
            assert not store.mutation_blockers(domain.connection_epoch, target_id)
            assert execute() == job and adapter.activations == 0
            for request, changed in (('foreign', {'document_id': 'doc_not_owned'}),
                                     ('configuration', {'configuration': 'Несуществующая'})):
                invalid = {**arguments, **changed}
                rejected = runner.submit(request, 'document.activate_part_native', invalid,
                    lambda operation_id: domain.activate(operation_id, **invalid), context=invalid,
                    mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
                assert rejected['status'] == 'failed' and 'mutation' not in rejected
                assert adapter.activations == 0
                report['cases'].append(dict(label='ACT-N3-' + request, passed=True, job=rejected))
            report['cases'].append(dict(label='ACT-N3-stale-before-activation', passed=True))
        else:
            assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved'
            assert job['error']['requires_reconciliation'] is True
            original_receipt = report['original_activation_receipt']
            assert original_receipt['native_call_attempted'] is True
            assert original_receipt['native_call_returned'] is True and original_receipt['pending_activation'] is False
            assert type(original_receipt['native_error']) is int and original_receipt['native_error'] in (0, 2)
            retained = domain.receipts[job['operation_id']]
            assert retained['guard_released'] is True and retained['pending_guard_release'] is False
            assert retained['manager'].evidence['released'] is True
            assert retained['manager'].evidence['selection_preserved'] is True
            report['released_execution_guard'] = retained['manager'].evidence
            assert execute() == job and adapter.activations == 1
            held = runner.submit('held', 'document.activate_part_native', arguments,
                lambda operation_id: domain.activate(operation_id, **arguments), context=arguments,
                mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
            assert held['error']['code'] == 'document_mutation_blocked' and adapter.activations == 1
            report['held_job'] = held
            report['cases'].append(dict(label='ACT-N4-controlled-after-call-unknown-hold-replay', passed=True))
        assert sw.CommandInProgress is False
        expected_active = target_identity if args.case != 'stale' else neighbor_identity
        assert native_identity(binding.wrap(sw.ActiveDoc, module.IModelDoc2)) == expected_active
        persist()
        # Independent native readback after terminal normal receipt/release,
        # under a new explicitly owned observer flag, never while a call is live.
        assert report['native_calls_live'] is False
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        assert [validated_part_snapshot(adapter.first_save_part_snapshot(model)) for model in owned] == before
        assert native_identity(target) == target_identity and native_identity(neighbor) == neighbor_identity
        report['independent_native_readback_verified'] = True
        report['phase'] = 'owned_cleanup'
        persist()
        retire_owned(sw, module, target, [target], owned, record)
        assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == before[1]
        retire_owned(sw, module, neighbor, [neighbor], owned, record)
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        restored = snapshot(sw, module)
        assert restored == original
        assert adapter.native_close_application_context() == original_application
        report['restored_application'] = adapter.native_close_application_context()
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        if args.case == 'controlled_after_call':
            evidence = dict(scope='test_owner_terminal_empty_activation_baseline_v1',
                restored_baseline=restored, restored_application=report['restored_application'],
                original_native_receipt=report['original_activation_receipt'],
                independent_native_readback_verified=True, historical_status_remains_unknown=True)
            reconciled = store.reconcile_mutation(job['operation_id'], resolution='accept_current_state', evidence=evidence)
            assert reconciled['status'] == 'unknown' and reconciled['mutation']['phase'] == 'reconciled'
            assert not store.mutation_blockers(domain.connection_epoch, target_id)
            report['reconciliation'] = reconciled
        report.update(phase='terminal', activation_case_passed=True, baseline_restored=True,
                      own_cleanup_verified=True, restored_baseline=restored, native_calls_live=False)
        report['cases'].append(dict(label='ACT-N5-owned-cleanup', passed=True))
        persist()
        store.close()
    except BaseException as error:
        report.update(phase='failed', error=str(error), traceback=traceback.format_exc())
        persist()
        if owned or report['native_calls_live'] is not False:
            report['retained_process'] = True
            persist()
            while True:
                time.sleep(.5)
        raise
    finally:
        persist()
        pythoncom.CoUninitialize()
    print(json.dumps(dict(scope=report['scope'], case=args.case, activation_case_passed=True,
                         elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
