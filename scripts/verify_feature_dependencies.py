"""Installed internal native relation/structural acceptance; no feature deletion.

Uses fresh unsaved fixtures, private journals, explicit document/configuration
and persistent targets. This proves only reported feature relations on fixtures,
not complete deletion impact or public MCP availability.
"""

import argparse
import json
from pathlib import Path
import sys
import time

import pythoncom
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.features import FeatureCatalog
from solidworks_mcp.jobs import JobStore
from verify_document_reads import native_snapshot
from verify_dimension_mcp import _provenance
from verify_export_operations import application_preferences, exact_solid, native_extrema_m, ui_snapshot, user_file_metadata
from verify_geometry_reads import fixtures
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verifier_fixture_cleanup import InlineFixtureCleanupGate
from diagnose_dimension_preferences import PrivateTrace


def verify_box_relations(graph, extrusion, sketch, native_parent_ids, native_child_ids):
    """Compare fixture facts against independent native parent/child getters."""
    nodes = graph['nodes']
    owners = [row for row in nodes if row['native_id'] == extrusion]
    sketches = [row for row in nodes if row['native_id'] == sketch]
    assert len(owners) == len(sketches) == 1
    owner, child = owners[0], sketches[0]
    assert owner['feature_type'] == 'Extrusion'
    assert child['feature_type'] == 'ProfileFeature'
    assert owner['object_id'] and child['object_id']
    assert owner['persistent_reference_supported'] and child['persistent_reference_supported']
    assert child['owner_native_id'] == owner['native_id']
    relations = graph['relations']
    indexes = {row['node_index']: row['native_id'] for row in nodes}
    captured_parent_ids = {indexes[left] for left, right in relations['parent_links']
                           if right == owner['node_index']}
    captured_child_ids = {indexes[right] for left, right in relations['child_links']
                          if left == child['node_index']}
    assert captured_parent_ids == native_parent_ids and sketch in captured_parent_ids
    assert captured_child_ids == native_child_ids and extrusion in captured_child_ids
    assert [owner['node_index'], child['node_index']] in relations['absorbed_links']
    assert graph['all_reported_native_relations_captured'] is True
    assert graph['deletion_impact_complete'] is graph['deletion_authorized'] is False
    return owner, child


def verify_options(result, owner, sketch, children, absorbed):
    assert result['options'] == {'include_children': children, 'include_absorbed': absorbed}
    assert result['native_delete_options'] == int(children) + 2 * int(absorbed)
    candidates = result['structural_candidate_nodes']
    ids = {row['object_id'] for row in candidates}
    assert owner['object_id'] in ids
    if absorbed:
        assert sketch['object_id'] in ids
    if not children and not absorbed:
        assert ids == {owner['object_id']}
    assert all(result[key] is False for key in
               ('deletion_impact_complete', 'deletion_authorized', 'native_deletion_result_predicted'))
    assert result['structural_links_complete'] is True
    assert {row.get('scope') for row in result['blockers'] if row['code'] == 'unverified_impact_scope'} >= {
        'other_configurations', 'dimensions_and_equations', 'annotations_and_drawings',
        'external_files_and_in_context_references', 'native_deletion_effects_and_restoration'}


def setup_owned_equations(manager, checkpoint):
    assert manager.GetCount() == 0 and manager.GetDisabledEquationCount() == 0
    expressions = ['"Контрольная активная величина" = 3', '"Контрольная отключённая величина" = 5']
    for index, expression in enumerate(expressions):
        checkpoint({'phase': 'before_equation_add', 'expected_index': index, 'expression': expression})
        actual = manager.Add2(-1, expression, False)
        assert type(actual) is int and actual == index
        assert manager.Equation(index) == expression
        checkpoint({'phase': 'equation_add_verified', 'index': index})
    checkpoint({'phase': 'before_equation_disable', 'index': 1})
    manager.SetDisabled(1, True)
    assert manager.Disabled(1) is True
    assert manager.GetCount() == 2 and manager.GetDisabledEquationCount() == 1
    checkpoint({'phase': 'equation_disable_verified', 'index': 1})


def verify_equation_context(result, manager):
    assert result['native_inventory_capture_closed'] is True
    assert result['row_indices_and_names_are_writable_anchors'] is False
    equations = result['native_context']['equations']
    assert equations['count'] == 2 and equations['disabled_count'] == 1
    rows = [{'row_index': i, 'expression': manager.Equation(i), 'disabled': manager.Disabled(i),
             'global_variable': manager.GlobalVariable(i), 'configuration_option': manager.GetConfigurationOption(i)}
            for i in range(manager.GetCount())]
    assert equations['rows'] == rows
    assert [row['disabled'] for row in rows] == [False, True]
    assert result['native_context']['external_references']['count'] == 0
    assert result['native_context']['auxiliary_references']['count'] == 0
    assert result['deletion_impact_complete'] is result['deletion_authorized'] is False


def check(state, report, gate, *, deletion_context=False):
    report.update(_provenance(), accepted=False, public_mcp_dependency_acceptance=False,
                  native_delete_attempted=False, deletion_impact_complete=False,
                  stl_preferences_verified=False, original_document_baseline_restored=False)
    assert callable(getattr(FeatureCatalog, 'dependencies', None))
    assert callable(getattr(FeatureCatalog, 'deletion_structure', None))
    if deletion_context:
        assert callable(getattr(FeatureCatalog, 'deletion_context', None))
    original = native_snapshot()
    sw, module = binding.connect(show=False), binding.module()
    original_ui, original_prefs = ui_snapshot(sw, module), application_preferences(sw)
    original_files = user_file_metadata(original)
    with fixtures(cleanup_gate=gate.can_cleanup) as (_, owned, _):
        documents = store = trace = None
        primary = None
        try:
            adapter = SolidWorksDocuments()
            documents = DocumentCatalog(adapter)
            store = JobStore(state / 'jobs.sqlite')
            catalog = FeatureCatalog(documents, store, 'native_dependency_acceptance')
            model = owned[1]
            assert not model.GetPathName()
            if deletion_context:
                manager = binding.wrap(model.GetEquationMgr(), module.IEquationMgr)
                trace = PrivateTrace(state / 'owned-equation-setup.trace.jsonl')
                setup_owned_equations(manager, trace)
            doc = next(row for row in documents.list()['documents'] if row['title'] == model.GetTitle())
            context = {'document_id': doc['document_id'], 'configuration': 'Основная'}
            setup, setup_ui = native_snapshot(), ui_snapshot(sw, module)
            body = exact_solid(model, module)
            geometry = {'extrema': native_extrema_m(body), 'volume': float(body.GetMassProperties(1.)[3])}
            graph = catalog.dependencies(**context)
            second = catalog.dependencies(**context)
            assert second == graph, 'Unchanged native graph must keep its revision and persistent IDs.'
            native = adapter.features(model)
            extrusion = next(row for row in native if row.GetTypeName2() == 'Extrusion')
            parent_rows = [binding.wrap(raw, module.IFeature) for raw in (extrusion.GetParents() or ())]
            sketch = next(row for row in parent_rows if row.GetTypeName2() == 'ProfileFeature')
            assert binding.wrap(sketch.GetOwnerFeature(), module.IFeature)._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == extrusion._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
            parent_ids = {int(row.GetID()) for row in parent_rows}
            child_ids = {int(binding.wrap(raw, module.IFeature).GetID()) for raw in (sketch.GetChildren() or ())}
            owner, child = verify_box_relations(graph, int(extrusion.GetID()), int(sketch.GetID()), parent_ids, child_ids)
            assert catalog.get(**context, object_id=owner['object_id'])['feature']['native_id'] == owner['native_id']
            results = []
            for children, absorbed in ((False, False), (True, False), (False, True), (True, True)):
                started = time.monotonic()
                result = catalog.deletion_structure(**context, object_ids=[owner['object_id']],
                    include_children=children, include_absorbed=absorbed)
                verify_options(result, owner, child, children, absorbed)
                assert result['dependency_graph_revision'] == graph['revision']
                results.append({'options': result['options'], 'candidate_count': len(result['structural_candidate_nodes']),
                                'seconds': round(time.monotonic() - started, 3), 'revision': result['revision']})
            assert len({row['revision'] for row in results}) == 4
            if deletion_context:
                inventory = catalog.deletion_context(**context)
                verify_equation_context(inventory, manager)
                assert inventory['dependency_graph'] == graph
                assert catalog.deletion_context(**context) == inventory
                report.update(deletion_context=inventory, enabled_and_disabled_native_equations_verified=True,
                    empty_native_reference_arrays_verified=True, nonempty_native_external_references_verified=False,
                    nonempty_native_auxiliary_references_verified=False)
            assert native_snapshot() == setup and ui_snapshot(sw, module) == setup_ui
            after_body = exact_solid(model, module)
            assert {'extrema': native_extrema_m(after_body), 'volume': float(after_body.GetMassProperties(1.)[3])} == geometry
            report.update(graph=graph, structural_options=results, repeated_graph_exactly_equal=True,
                          independent_fixture_relations_verified=True, native_persistent_target_verified=True,
                          fixture_geometry_and_documents_unchanged=True)
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
                    primary.add_note('Dependency verifier resource cleanup failed: ' + type(error).__name__)
            elif errors:
                for error in errors[1:]:
                    errors[0].add_note('Dependency verifier cleanup also failed: ' + type(error).__name__)
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
    parser.add_argument('--deletion-context', action='store_true')
    args = parser.parse_args()
    private = Path(__file__).resolve().parent.parent / 'work'
    assert all(path.resolve().is_relative_to(private) for path in (args.state_dir, args.report))
    assert not args.state_dir.exists() and not args.report.exists()
    args.state_dir.mkdir(parents=True)
    report, gate, initialized = {}, InlineFixtureCleanupGate(), False
    try:
        pythoncom.CoInitialize()
        initialized = True
        check(args.state_dir, report, gate, deletion_context=args.deletion_context)
    except BaseException as error:
        report.update(accepted=False, error_type=type(error).__name__,
                      fixture_retention_required=not gate.can_cleanup(), automatic_replay_attempted=False)
        try:
            with args.report.open('x', encoding='utf8') as stream:
                json.dump(report, stream, allow_nan=False, indent=2)
        except BaseException as report_error:
            error.add_note('Private dependency report write failed: ' + type(report_error).__name__)
        raise
    else:
        with args.report.open('x', encoding='utf8') as stream:
            json.dump(report, stream, allow_nan=False, indent=2)
        print(json.dumps({'accepted': report['accepted'], 'package_version': report['package_version'],
                          'node_count': len(report['graph']['nodes']), 'native_delete_attempted': False}))
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
