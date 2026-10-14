"""One-owner installed ACT-N1/replay probe; not whole activation acceptance.

Own fixture setup uses the established rectangular-base builder. Unknown/live
effects retain this process and every exact receipt; no COM cancellation,
inverse activation, roster-delta cleanup or automatic retry.
"""

import argparse
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


HELPERS = ('verify_native_part_activation_positive.py', 'probe_native_first_save_domain.py',
           'verify_installed_metadata.py', 'verify_wheel_artifact.py',
           'verify_bounds_measurements.py', 'verify_component_reads.py',
           'verify_export_operations.py', 'verify_native_document_open.py',
           'verify_native_first_save_rejections.py', 'verifier_dimension_diagnostics.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
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
    report = dict(scope='installed_native_part_activation_positive_only', accepted=False,
                  activation_positive_passed=False, cases=[], captures=[], owned_documents=[],
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

        def activate_native_open_document(self, receipt):
            self.activations += 1
            report['native_calls_live'] = True
            persist()
            try:
                return super().activate_native_open_document(receipt)
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
        activate_owned(sw, neighbor, neighbor.GetTitle())
        target_identity, neighbor_identity = native_identity(target), native_identity(neighbor)
        before = [validated_part_snapshot(adapter.first_save_part_snapshot(model)) for model in owned]
        report['independent_before'] = before
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
        assert prepared['status'] == 'succeeded' and prepared['result']['already_active'] is False
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
        assert job['status'] == 'succeeded' and job['mutation']['phase'] == 'committed', job['error']
        assert job['mutation']['before_state']['scope'] == SCOPE
        assert adapter.activations == 1 and not domain.receipts
        guard = job['result']['execution_guard']
        assert guard['guard_released'] is True and guard['pending_guard_release'] is False
        assert guard['full_release_check'] == 'effect'
        assert guard['native_guard']['released'] is True and guard['native_guard']['selection_preserved'] is True
        assert job['result']['after']['semantic']['active_document_id'] == target_id
        steps = job['mutation']['verification']['native_steps']
        names = ['part_activation_release_ui', 'part_activation_native',
                 'part_activation_guard_release', 'part_activation_released_check']
        assert [(step['name'], step['phase']) for step in steps] == [(name, phase) for name in names for phase in ('pending','returned')]
        assert [step['sequence'] for step in steps] == list(range(1,9))
        assert steps[-1]['evidence']['verified'] is True
        assert sw.CommandInProgress is False
        assert native_identity(binding.wrap(sw.ActiveDoc, module.IModelDoc2)) == target_identity
        report['cases'].append(dict(label='ACT-N1-positive', passed=True))
        assert execute() == job and adapter.activations == 1
        report['cases'].append(dict(label='ACT-N2-replay-only', passed=True))
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
        report.update(phase='terminal', activation_positive_passed=True, baseline_restored=True,
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
    print(json.dumps(dict(scope=report['scope'], activation_positive_passed=True,
                         elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
