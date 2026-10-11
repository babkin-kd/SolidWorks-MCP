"""One-owner positive L3 probe; never whole-block native release acceptance.

Defaults to source; verify_native_first_save_positive.py requires an installed
wheel. One process owns COM and all fixtures. A live/unknown job is not cancelled or
repeated. Unknown effects retain this process and its private receipt resources.
"""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import traceback
import uuid

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.native_first_save import NativeFirstSaveCatalog, clone_mapping
from solidworks_mcp.part_creation import BaseRectangle, validated_plane_transform
from solidworks_mcp.session import SolidWorksSession
from verify_bounds_measurements import InlineSta
from verify_component_reads import native_identity
from verify_export_operations import activate_owned, application_preferences
from verify_native_document_open import retire_owned, snapshot
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verifier_native_first_save import verified_committed_first_save
from verify_installed_metadata import installed_identity, check
from verify_wheel_artifact import validate_wheel


def package_evidence(args, *, installed):
    """Reject a wrong origin/wheel/catalog before the first native connection."""
    if installed:
        wheel = validate_wheel(args.wheel, expected_version=args.expected_version,
                               expected_git_sha=args.expected_git_sha)
        entry = installed_identity(wheel)
        metadata_state = args.state_dir / 'metadata-state'
        metadata_state.mkdir()
        catalog = asyncio.run(check(entry, metadata_state, wheel))
        return dict(wheel=wheel, installed_package_origin=str(Path(solidworks_mcp.__file__).resolve().parent),
                    metadata_catalog=catalog, package_origin_verified=True)
    assert Path(solidworks_mcp.__file__).resolve().parent == Path.cwd() / 'src' / 'solidworks_mcp'
    return dict(source_package_origin=str(Path(solidworks_mcp.__file__).resolve().parent),
                package_origin_verified=True)


def main(*, installed=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--state-dir', required=True, type=Path)
    if installed:
        parser.add_argument('--wheel', required=True, type=Path)
        parser.add_argument('--expected-version', required=True)
        parser.add_argument('--expected-git-sha', required=True)
    args = parser.parse_args()
    assert args.run_solidworks
    state = args.state_dir.absolute()
    assert state.is_relative_to(Path.cwd() / 'work') and not state.exists()
    state.mkdir()
    capture_directory = state / 'oracle-captures'
    capture_directory.mkdir()
    start = time.perf_counter()
    report = dict(scope=('installed_first_save_domain_positive_only' if installed
                         else 'source_first_save_domain_positive_only'), probe_passed=False,
                  accepted=False, positive_case_passed=False,
                  native_first_save_accepted=False, exact_installed_acceptance=False,
                  owned_documents=[], native_calls_live=False, captures=[], phase='startup',
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  verifier_hashes={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ('probe_native_first_save_domain.py', 'verify_native_first_save_positive.py',
                                                'verifier_native_first_save.py', 'verify_installed_metadata.py',
                                                'verify_wheel_artifact.py', 'verify_bounds_measurements.py',
                                                'verify_component_reads.py', 'verify_export_operations.py',
                                                'verify_native_document_open.py', 'verifier_dimension_diagnostics.py')},
                  package_files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(Path(solidworks_mcp.__file__).resolve().parent.glob('*.py'))})

    def persist():
        report['elapsed_seconds'] = time.perf_counter() - start
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                     allow_nan=False), encoding='utf-8')

    try:
        args.state_dir = state
        report.update(package_evidence(args, installed=installed))
        persist()
    except BaseException as error:
        report.update(phase='preflight_failed', error=str(error), traceback=traceback.format_exc())
        persist()
        raise

    def record(models):
        report['owned_documents'] = [dict(title=m.GetTitle(), path=m.GetPathName(), type=m.GetType()) for m in models]
        persist()

    class TracedDocuments(SolidWorksDocuments):
        def first_save_part_snapshot(self, model):
            row = dict(number=len(report['captures']) + 1, title=model.GetTitle(),
                       command_in_progress=self._sw.CommandInProgress,
                       started_s=time.perf_counter() - start, status='running')
            report['captures'].append(row)
            persist()
            try:
                value = super().first_save_part_snapshot(model)
                artifact = capture_directory / f"capture-{row['number']:04d}.json"
                artifact.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
                row.update(status='returned', elapsed_s=time.perf_counter() - start - row['started_s'],
                           snapshot_file=str(artifact.relative_to(state)),
                           sha256=hashlib.sha256(json.dumps(value, sort_keys=True,
                                                           ensure_ascii=False).encode()).hexdigest())
                return value
            except BaseException as error:
                row.update(status='failed', error=str(error))
                raise
            finally:
                persist()

    owned = []
    store = domain = adapter = None
    unknown = False
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        assert sw.CommandInProgress is False and sw.UserControl is True
        baseline = snapshot(sw, module)
        report['original_baseline'] = baseline
        preferences = application_preferences(sw)
        report['original_preferences'] = preferences
        original_directory = sw.GetCurrentWorkingDirectory()
        dimension_preference = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
        assert type(dimension_preference) is bool
        report.update(original_directory=original_directory, phase='owned_fixture_creation')
        persist()
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, False)
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is False
        session = SolidWorksSession()
        session._sw, session._mod = sw, module
        adapter = TracedDocuments()
        for name, sizes in (('Деталь первого сохранения', (40., 20., 12.)),
                            ('Сосед первого сохранения', (5., 6., 7.))):
            report['native_calls_live'] = True
            persist()
            session.new_part()
            model = session._model
            report['native_calls_live'] = False
            owned.append(model)
            record(owned)
            assert model.SetTitle2(name)
            configuration = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
            configuration.Name = 'Основная'
            assert tuple(model.GetConfigurationNames()) == ('Основная',)
            features = adapter.features(model)
            identity_frame = validated_plane_transform((1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.))
            planes = [f for f in features if f.GetTypeName2() == 'RefPlane'
                      and validated_plane_transform(adapter.reference_plane_transform(f)) == identity_frame]
            assert len(planes) == 1
            definition = BaseRectangle.validate(plane_object_id='feat_' + uuid.uuid4().hex,
                                                width_mm=sizes[0], height_mm=sizes[1], depth_mm=sizes[2])
            receipt = adapter.new_base_receipt(model, features, adapter.part_creation_controls(model))
            report['native_calls_live'] = True
            persist()
            adapter.create_base_rectangle(model, planes[0], definition, receipt)
            report['native_calls_live'] = False
            for i, feature in enumerate(session._iter_features(), 1):
                if feature.GetTypeName2() in ('RefPlane', 'ProfileFeature'):
                    feature.Name = f'Контрольный элемент {i}'
                    assert feature.Name == f'Контрольный элемент {i}'
            bodies = binding.wrap(model, module.IPartDoc).GetBodies2(-1, False)
            assert len(bodies) == 1
            body = binding.wrap(bodies[0], module.IBody2)
            body.Name = 'Тело основания'
            assert body.Name == 'Тело основания' and model.ForceRebuild3(False)
            model.ClearSelection2(True)
            record(owned)
        source, neighbor = owned
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dimension_preference)
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is dimension_preference
        activate_owned(sw, source, source.GetTitle())
        source_token, neighbor_token = native_identity(source), native_identity(neighbor)
        source_before = adapter.first_save_part_snapshot(source)
        neighbor_before = adapter.first_save_part_snapshot(neighbor)
        report.update(source_before=source_before, neighbor_before=neighbor_before)
        persist()
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        before_session = snapshot(sw, module)
        documents = DocumentCatalog(adapter)
        documents.list()
        source_id = next(entry.document_id for entry in documents._entries if entry.identity == adapter.identity(source))
        store = JobStore(state / 'jobs.sqlite')
        domain = NativeFirstSaveCatalog(documents, store, 'source_probe_' + uuid.uuid4().hex)
        runner = JobRunner(store, InlineSta())
        arguments = dict(document_id=source_id, configuration='Основная',
                         filename=str(state / 'Сохранённая контрольная деталь.SLDPRT'))
        report['phase'] = 'full_domain_prepare'
        persist()
        prepared = runner.submit('prepare', 'document.prepare_first_save_native', arguments,
                                 lambda: domain.prepare_first_save(**arguments), context=arguments)
        report['preparation'] = prepared
        persist()
        assert prepared['status'] == 'succeeded', prepared['error']
        arguments['expected_revision'] = prepared['result']['revision']
        report['phase'] = 'full_domain_execute'
        persist()
        saved = runner.submit('save', 'document.first_save_native', arguments,
                              lambda op: domain.first_save(op, **arguments), context=arguments,
                              mutates=True, pass_operation_id=True,
                              verify=lambda result: result['verified'] is True)
        report['job'] = saved
        unknown = saved['status'] == 'unknown'
        persist()
        assert saved['status'] == 'succeeded', saved['error']
        value = saved['result']['value']
        assert value['retired_document_ids'] == [source_id] and value['document_id'] != source_id
        assert saved['mutation']['phase'] == 'committed' and saved['result']['verified'] is True
        assert value['source_references_retired'] and value['resolve_saved_references_again']
        final = documents.resolve(value['document_id'], 'Основная')[0].model
        owned[:] = [final, neighbor]  # Source retirement was proved by the domain; never query it again.
        record(owned)
        assert verified_committed_first_save(saved)
        report['protocol_verified'] = True
        replay = runner.submit('save', 'document.first_save_native', arguments,
                               lambda _: (_ for _ in ()).throw(AssertionError('Replay must never call CAD')),
                               context=arguments, mutates=True, pass_operation_id=True,
                               verify=lambda result: result['verified'] is True)
        assert replay == saved
        report.update(phase='independent_terminal_readback', replay_verified=True)
        persist()
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        final_snapshot = adapter.first_save_part_snapshot(final)
        report['independent_final_snapshot'] = final_snapshot
        assert clone_mapping(source_before, final_snapshot) == value['reference_mapping']
        assert adapter.first_save_part_snapshot(neighbor) == neighbor_before
        assert neighbor.GetSaveFlag() is True and native_identity(neighbor) == neighbor_token
        assert final.GetPathName() == value['filename'] and final.GetSaveFlag() is False
        assert adapter.native_save_context(final)['read_only_state'] == 0
        report.update(full_domain_committed=True, independent_full_readback_verified=True,
                      reference_mapping_count=len(value['reference_mapping']))
        persist()
        retire_owned(sw, module, final, [final], owned, record)
        assert adapter.first_save_part_snapshot(neighbor) == neighbor_before
        retire_owned(sw, module, neighbor, [neighbor], owned, record)
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        if sw.GetCurrentWorkingDirectory() != original_directory:
            raw = sw.SetCurrentWorkingDirectory(original_directory)
            assert raw is True and sw.GetCurrentWorkingDirectory() == original_directory
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        restored_baseline = snapshot(sw, module)
        assert restored_baseline == baseline
        report['restored_baseline'] = restored_baseline
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        report.update(phase='terminal', probe_passed=True, positive_case_passed=True, baseline_restored=True,
                      own_cleanup_verified=True, native_calls_live=False)
        persist()
    except BaseException as error:
        report.update(error=str(error), traceback=traceback.format_exc(), phase='failed')
        persist()
        # There is no success inferred from test-owner cleanup. Unknown native
        # state retains the actual process/receipt resources for reconciliation.
        if owned or unknown or report['native_calls_live'] or (domain is not None and domain.receipts):
            report['retained_process'] = True
            persist()
            print(json.dumps(dict(scope=report['scope'], retained_process=True, error=str(error))), flush=True)
            while True:
                time.sleep(.5)
        raise
    finally:
        persist()
        pythoncom.CoUninitialize()
    print(json.dumps(dict(scope=report['scope'], probe_passed=report['probe_passed'],
                         elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
