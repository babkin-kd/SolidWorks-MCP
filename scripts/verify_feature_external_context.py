"""Installed native equation/reference context on an owned derived part.

Only test-owned source files are saved, inside fresh private work/ state.
The candidate stays internal; this is not full deletion-impact acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pythoncom
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.features import FeatureCatalog
from solidworks_mcp.jobs import JobStore
from diagnose_dimension_preferences import PrivateTrace
from verify_dimension_mcp import _provenance
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences, ui_snapshot, user_file_metadata
from verify_geometry_reads import fixtures
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verifier_fixture_cleanup import InlineFixtureCleanupGate

FIELDS = ('model_path', 'component_path', 'feature_name', 'data_type', 'status',
          'reference_entity', 'feature_component', 'configuration_option', 'configuration_name')


def file_signature(path):
    stat = path.stat()
    return {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def reference_rows(owner, *, feature=False):
    """Independent native OUT decoding; feature configuration outputs are scalar."""
    count = owner.ListExternalFileReferencesCount()
    assert type(count) is int and 0 <= count <= 5000
    columns = owner.ListExternalFileReferences2()
    assert type(columns) in (tuple, list) and len(columns) == 9
    arrays = []
    for index, column in enumerate(columns):
        if feature and index >= 7:
            assert type(column) is (int if index == 7 else str)
            column = [column] * count
        if column is None and count == 0:
            column = []
        assert type(column) in (tuple, list) and len(column) == count
        arrays.append(column)
    closing_count = owner.ListExternalFileReferencesCount()
    assert type(closing_count) is int and closing_count == count
    for index, column in enumerate(arrays):
        expected = int if index in (4, 7) else str
        assert all(type(value) is expected for value in column)
    return [{'row_index': index, **dict(zip(FIELDS, values))}
            for index, values in enumerate(zip(*arrays))]


def verify_reference_context(result, document_rows, feature_rows, source_path, feature_name):
    assert result['native_inventory_capture_closed'] is True
    assert result['row_indices_and_names_are_writable_anchors'] is False
    table = result['native_context']['external_references']
    assert table['count'] == len(table['rows']) == len(document_rows) > 0
    assert table['rows'] == document_rows == feature_rows
    assert all(Path(row['model_path']).resolve() == source_path.resolve() for row in document_rows)
    assert all(row['feature_name'] == feature_name for row in document_rows)
    assert result['deletion_impact_complete'] is result['deletion_authorized'] is False
    assert any(row['code'] == 'unverified_impact_scope'
               and row['scope'] == 'incoming_external_document_references' for row in result['blockers'])


def setup_owned_reference(sw, module, source, target, path, checkpoint):
    assert not source.GetPathName() and not target.GetPathName() and not path.exists()
    assert tuple(source.GetConfigurationNames()) == ('Основная', 'Вариант')
    source_identity = source._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
    target_identity = target._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
    checkpoint({'phase': 'before_owned_source_save', 'path': str(path), 'title': source.GetTitle()})
    status = source.SaveAs3(str(path), 0, 1)  # current format, silent; owned source only
    assert type(status) is int and status == 0
    assert path.is_file() and path.stat().st_size > 0
    assert Path(source.GetPathName()).resolve() == path.resolve()
    assert source._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == source_identity
    checkpoint({'phase': 'owned_source_save_verified', 'file': file_signature(path)})
    active = binding.wrap(sw.ActiveDoc, module.IModelDoc2)
    assert active is not None and active._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == target_identity
    assert target.GetBlockingState() == 0
    checkpoint({'phase': 'before_owned_derived_part_insert', 'target': target.GetTitle(),
                'source_path': str(path), 'source_configuration': 'Основная', 'options': 262145})
    feature = binding.wrap(binding.wrap(target, module.IPartDoc).InsertPart3(str(path), 262145, 'Основная'), module.IFeature)
    assert feature is not None
    checkpoint({'phase': 'owned_derived_part_insert_returned', 'native_id': feature.GetID()})
    name = 'Контрольная ссылка на основу'
    checkpoint({'phase': 'before_owned_derived_feature_rename', 'native_id': feature.GetID(), 'name': name})
    feature.Name = name
    assert feature.Name == name
    checkpoint({'phase': 'owned_derived_feature_rename_verified', 'native_id': feature.GetID()})
    checkpoint({'phase': 'before_owned_target_rebuild', 'target': target.GetTitle()})
    assert target.ForceRebuild3(False)
    assert target._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == target_identity
    checkpoint({'phase': 'owned_target_rebuild_verified'})
    return feature


def check(state, report, gate):
    report.update(_provenance(), accepted=False, public_mcp_dependency_acceptance=False,
                  native_delete_attempted=False, deletion_impact_complete=False,
                  stl_preferences_verified=False, original_document_baseline_restored=False)
    original = native_snapshot()
    sw, module = binding.connect(show=False), binding.module()
    original_ui, original_prefs = ui_snapshot(sw, module), application_preferences(sw)
    original_files = user_file_metadata(original)
    with fixtures(cleanup_gate=gate.can_cleanup) as (_, owned, _):
        documents = store = trace = None
        primary = None
        try:
            source, target = owned
            path = state / 'Основа внешних ссылок.SLDPRT'
            trace = PrivateTrace(state / 'owned-reference-setup.trace.jsonl')
            feature = setup_owned_reference(sw, module, source, target, path, trace)
            source_file = file_signature(path)
            setup, setup_ui = native_snapshot(), ui_snapshot(sw, module)
            adapter = SolidWorksDocuments()
            documents = DocumentCatalog(adapter)
            store = JobStore(state / 'jobs.sqlite')
            catalog = FeatureCatalog(documents, store, 'native_external_context_acceptance')
            doc = next(row for row in documents.list()['documents'] if row['title'] == target.GetTitle())
            context = {'document_id': doc['document_id'], 'configuration': 'Основная'}
            first = catalog.deletion_context(**context)
            document_rows = reference_rows(binding.wrap(target.Extension, module.IModelDocExtension))
            feature_rows = reference_rows(feature, feature=True)
            verify_reference_context(first, document_rows, feature_rows, path, feature.Name)
            second = catalog.deletion_context(**context)
            assert first == second, 'Repeated context changed without a model edit'
            nodes = [row for row in first['dependency_graph']['nodes'] if row['native_id'] == feature.GetID()]
            assert len(nodes) == 1 and nodes[0]['object_id'] and nodes[0]['persistent_reference_supported']
            assert nodes[0]['name'] == feature.Name
            resolved = catalog.get(**context, object_id=nodes[0]['object_id'])['feature']
            assert resolved['native_id'] == feature.GetID() and resolved['name'] == feature.Name
            assert native_snapshot() == setup and ui_snapshot(sw, module) == setup_ui
            assert file_signature(path) == source_file
            assert not store.list()['items']
            report.update(deletion_context=first, independent_document_reference_rows=document_rows,
                          independent_feature_reference_rows=feature_rows,
                          native_nonempty_external_references_verified=True,
                          native_fixture_feature_reference_correspondence_verified=True,
                          native_generic_feature_reference_bindings_implemented=False,
                          native_nonempty_auxiliary_references_verified=False,
                          owned_source_file_unchanged_during_reads=True,
                          repeated_context_exactly_equal=True, fixture_documents_and_ui_unchanged=True)
        except BaseException as error:
            primary = error
            gate.retain()
            raise
        finally:
            errors = []
            for resource in (documents, store, trace):
                if resource is not None:
                    try:
                        resource.close()
                    except BaseException as error:
                        gate.retain()
                        errors.append(error)
            if primary is not None:
                for error in errors:
                    primary.add_note('Reference verifier resource cleanup failed: ' + type(error).__name__)
            elif errors:
                for error in errors[1:]:
                    errors[0].add_note('Reference verifier cleanup also failed: ' + type(error).__name__)
                raise errors[0]
    assert gate.can_cleanup() and native_snapshot() == original
    assert ui_snapshot(sw, module) == original_ui and user_file_metadata(original) == original_files
    assert_non_stl_preferences(lambda: application_preferences(sw), original_prefs, report, 'original_preferences_comparison')
    report.update(accepted=True, original_document_baseline_restored=True,
                  non_stl_preferences_and_ui_restored=True, original_preferences_and_ui_restored=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    private = Path(__file__).resolve().parent.parent / 'work'
    args.state_dir, args.report = args.state_dir.resolve(), args.report.resolve()
    assert all(path.is_relative_to(private) for path in (args.state_dir, args.report))
    assert not args.state_dir.exists() and not args.report.exists()
    args.state_dir.mkdir(parents=True)
    report, gate, initialized = {}, InlineFixtureCleanupGate(), False
    try:
        pythoncom.CoInitialize()
        initialized = True
        check(args.state_dir, report, gate)
    except BaseException as error:
        report.update(accepted=False, error_type=type(error).__name__,
                      fixture_retention_required=not gate.can_cleanup(), automatic_replay_attempted=False)
        try:
            with args.report.open('x', encoding='utf8') as stream:
                json.dump(report, stream, allow_nan=False, indent=2)
        except BaseException as report_error:
            error.add_note('Private reference report write failed: ' + type(report_error).__name__)
        raise
    else:
        with args.report.open('x', encoding='utf8') as stream:
            json.dump(report, stream, allow_nan=False, indent=2)
        print(json.dumps({'accepted': report['accepted'], 'package_version': report['package_version'],
                          'external_reference_count': report['deletion_context']['native_context']['external_references']['count']}))
    finally:
        if initialized:
            primary = sys.exception()
            try:
                pythoncom.CoUninitialize()
            except BaseException as error:
                if primary is None:
                    raise
                primary.add_note('COM cleanup failed: ' + type(error).__name__)


if __name__ == '__main__':
    main()
