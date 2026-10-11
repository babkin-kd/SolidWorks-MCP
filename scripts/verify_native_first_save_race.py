"""Installed L3-I3: actual Copy/readback followed by a no-replace collision.

Only the controlled producer is injected. CAD, filesystem leases and NT
publication use the installed package. Unknown retains the actual process;
no test-owner cleanup is allowed until the outcome is confirmed terminal.
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
from solidworks_mcp.native_first_save import NativeFirstSaveCatalog, validated_part_snapshot
from solidworks_mcp.part_creation import BaseRectangle, validated_plane_transform
from solidworks_mcp.session import SolidWorksSession
from probe_native_first_save_domain import package_evidence
from verify_bounds_measurements import InlineSta
from verify_export_operations import activate_owned, application_preferences
from verify_native_document_open import retire_owned, snapshot
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verifier_first_save_faults import file_witness, DestinationRace
from verifier_first_save_race import verified_race_rollback
from solidworks_mcp import native_first_save_files as actual_files


LABELS = ['destination_race_after_native_readback_no_overwrite',
          'owned_fixture_cleanup_baseline_restored']


def owned_document_rows(models):
    """Canonical IUnknown stays in process; only native scalar facts enter JSON."""
    rows = []
    for model in models:
        row = dict(title=model.GetTitle(), path=model.GetPathName(), type=model.GetType())
        if (type(row['title']) is not str or type(row['path']) is not str
                or type(row['type']) is not int or row['type'] not in (1, 2, 3)):
            raise ValueError('Owned document report needs detached native scalar facts.')
        rows.append(row)
    return rows


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
    report = dict(scope='installed_first_save_destination_race_only', accepted=False,
                  cases=[], captures=[], owned_documents=[], native_calls_live=False,
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  verifier_hashes={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ('verify_native_first_save_race.py', 'verifier_first_save_race.py',
                                                'verifier_native_first_save.py', 'verifier_first_save_faults.py',
                                                'probe_native_first_save_domain.py', 'verify_installed_metadata.py',
                                                'verify_wheel_artifact.py', 'verify_bounds_measurements.py',
                                                'verify_export_operations.py', 'verify_native_document_open.py',
                                                'verifier_dimension_diagnostics.py')},
                  phase='preflight')

    def persist():
        report['elapsed_seconds'] = time.perf_counter() - started
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False,
                                                      allow_nan=False, indent=2), encoding='utf-8')

    def record(models):
        report['owned_documents'] = owned_document_rows(models)
        persist()

    try:
        report.update(package_evidence(args, installed=True))
        persist()
    except BaseException as error:
        report.update(phase='preflight_failed', error=str(error))
        persist()
        raise

    class ObservedDocuments(SolidWorksDocuments):
        copy_calls = 0
        open_calls = 0
        close_calls = 0

        def open_native_document(self, receipt):
            self.open_calls += 1
            return super().open_native_document(receipt)

        def close_native_first_save_document(self, receipt):
            self.close_calls += 1
            return super().close_native_first_save_document(receipt)

        def save_native_first_save_copy(self, receipt):
            self.copy_calls += 1
            return super().save_native_first_save_copy(receipt)

        def first_save_part_snapshot(self, model):
            row = dict(title=model.GetTitle(), started_s=time.perf_counter()-started, status='running')
            report['captures'].append(row)
            persist()
            try:
                value = super().first_save_part_snapshot(model)
                row.update(status='returned', elapsed_s=time.perf_counter()-started-row['started_s'])
                return value
            except BaseException as error:
                row.update(status='failed', error=str(error))
                raise
            finally:
                persist()

    owned = []
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        assert sw.CommandInProgress is False and sw.UserControl is True
        baseline = snapshot(sw, module)
        preferences = application_preferences(sw)
        report.update(original_baseline=baseline, original_preferences=preferences,
                      phase='owned_fixture_creation')
        dimension_preference = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
        assert type(dimension_preference) is bool
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, False)
        session = SolidWorksSession()
        session._sw, session._mod = sw, module
        adapter = ObservedDocuments()
        for name, sizes in (('Деталь проверки отказов', (40., 20., 12.)),
                            ('Сосед проверки отказов', (5., 6., 7.))):
            report['native_calls_live'] = True
            persist()
            created = session.new_part()
            model = session._model
            owned.append(model)
            assert type(created) is dict and created['ok'] is True and type(created['title']) is str
            report.setdefault('normal_creation_returns', []).append(created)
            report['native_calls_live'] = False
            persist()
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
            adapter.create_base_rectangle(model, planes[0], definition, receipt)
            for index, feature in enumerate(session._iter_features(), 1):
                if feature.GetTypeName2() in ('RefPlane', 'ProfileFeature'):
                    feature.Name = f'Контрольный элемент {index}'
                    assert feature.Name == f'Контрольный элемент {index}'
            bodies = binding.wrap(model, module.IPartDoc).GetBodies2(-1, False)
            assert len(bodies) == 1
            body = binding.wrap(bodies[0], module.IBody2)
            body.Name = 'Тело основания'
            assert body.Name == 'Тело основания'
            assert model.ForceRebuild3(False)
            model.ClearSelection2(True)
            report['native_calls_live'] = False
            record(owned)
        source, neighbor = owned
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dimension_preference)
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is dimension_preference
        activate_owned(sw, source, source.GetTitle())
        neighbor_before = validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))
        source_before = validated_part_snapshot(adapter.first_save_part_snapshot(source))
        report.update(source_before=source_before, neighbor_before=neighbor_before)
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        documents = DocumentCatalog(adapter)
        documents.list()
        source_id = next(e.document_id for e in documents._entries if e.identity == adapter.identity(source))
        store = JobStore(state / 'jobs.sqlite')
        raced_files = DestinationRace(actual_files, state)
        catalog = NativeFirstSaveCatalog(documents, store, 'race_'+uuid.uuid4().hex, files=raced_files)
        runner = JobRunner(store, InlineSta())
        arguments = dict(document_id=source_id, configuration='Основная',
                         filename=str(state / 'Сохранённая контрольная деталь.SLDPRT'))
        report['phase'] = 'prepare'
        persist()
        prepared = runner.submit('prepare', 'document.prepare_first_save_native', arguments,
                                lambda: catalog.prepare_first_save(**arguments), context=arguments)
        report['preparation'] = prepared
        persist()
        assert prepared['status'] == 'succeeded', prepared['error']
        arguments['expected_revision'] = prepared['result']['revision']

        def execute(request):
            report['native_calls_live'] = True
            persist()
            job = runner.submit(request, 'document.first_save_native', arguments,
                lambda operation: catalog.first_save(operation, **arguments), context=arguments,
                mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
            report['native_calls_live'] = None if job['status'] == 'unknown' else False
            report.setdefault('jobs', []).append(job)
            persist()
            return job

        def check_parts(expected_source):
            before = snapshot(sw, module)
            assert sw.CommandInProgress is False
            sw.CommandInProgress = True
            assert sw.CommandInProgress is True
            assert validated_part_snapshot(adapter.first_save_part_snapshot(source)) == expected_source
            assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == neighbor_before
            sw.CommandInProgress = False
            assert sw.CommandInProgress is False and snapshot(sw, module) == before
            assert neighbor.GetSaveFlag() is True and source.GetSaveFlag() is True

        target = Path(arguments['filename'])
        report['phase'] = LABELS[0]
        job = execute('race')
        assert job['status'] == 'failed' and job['error']['code'] == 'first_save_publication_failed'
        assert job['error']['requires_reconciliation'] is False
        assert job['mutation']['phase'] == 'rolled_back'
        assert adapter.copy_calls == adapter.open_calls == adapter.close_calls == 1
        assert raced_files.publication_calls == 1 and raced_files.preserved_foreign_file()
        assert not catalog.receipts
        after = job['mutation']['verification']['evidence']['after']
        assert after['stage']['empty'] is True and after['stage']['file'] is None
        assert after['pending'] is after['pending_release'] is after['journal_failed'] is False
        assert after['semantic'] == job['mutation']['before_state']['semantic']
        assert after['snapshots'] == job['mutation']['before_state']['snapshots']
        assert after['destination_file']['sha256'] == raced_files.foreign_witness['sha256']
        assert after['cleanup']['destination_removed'] is False and after['cleanup']['file_removed'] is True
        assert verified_race_rollback(job, raced_files.foreign_witness)
        check_parts(source_before)
        replay = execute('race')
        assert replay == job
        assert adapter.copy_calls == adapter.open_calls == adapter.close_calls == raced_files.publication_calls == 1
        assert raced_files.preserved_foreign_file()
        report['cases'].append(dict(label=LABELS[0], passed=True, job=job,
            foreign_file=raced_files.foreign_witness, replay_verified=True,
            copy_calls=adapter.copy_calls, open_calls=adapter.open_calls, close_calls=adapter.close_calls,
            publication_calls=raced_files.publication_calls, independent_source_preserved=True,
            independent_neighbor_preserved=True, foreign_file_retained=True))
        persist()

        report['phase'] = 'owned_cleanup'
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        retire_owned(sw, module, source, [source], owned, record)
        assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == neighbor_before
        retire_owned(sw, module, neighbor, [neighbor], owned, record)
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        restored = snapshot(sw, module)
        assert restored == baseline
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        report['cases'].append(dict(label=LABELS[1], passed=True))
        assert [row['label'] for row in report['cases']] == LABELS
        report.update(phase='terminal', race_case_passed=True, baseline_restored=True,
                      own_cleanup_verified=True, restored_baseline=restored, native_calls_live=False)
        persist()
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
    print(json.dumps(dict(scope=report['scope'], race_case_passed=True,
                         elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
