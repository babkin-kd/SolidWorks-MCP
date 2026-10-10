"""Native isolated-copy feasibility on disposable owned parts only.

No production copy/delete tool is exposed. Source files and private traces stay
under work/. A failed or ambiguous operation retains all owned documents; no
COM call is retried. Execute with the installed wheel and no PYTHONPATH.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

import pythoncom
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from diagnose_dimension_preferences import PrivateTrace
from verify_dimension_mcp import _provenance
from verify_document_reads import native_snapshot
from verify_export_operations import (
    application_preferences, assert_owned_source_facts_unchanged,
    owned_source_snapshot, ui_snapshot, user_file_metadata,
)
from verify_geometry_reads import fixtures
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verifier_fixture_cleanup import InlineFixtureCleanupGate


def file_facts(path):
    info = path.stat()
    assert info.st_size > 0 and path.is_file()
    return {'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
            'identity': [info.st_dev, info.st_ino],
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}



def numeric_global_fixture_signature(expression):
    """Only bounded integer-global fixture grammar; never general equations.

    Keep quoted names exact. Save/load may change whitespace OUTSIDE quotes.
    Raw source/copy strings are retained separately in the private report.
    """
    import re
    if type(expression) is not str or len(expression) > 256:
        raise ValueError('Not a controlled integer-global fixture expression.')
    match = re.fullmatch(r'"([^"\r\n]{1,120})"[ \t]*=[ \t]*([0-9]{1,10})', expression)
    if match is None or '@' in match[1]:
        raise ValueError('Not a controlled integer-global fixture expression.')
    return match[1], int(match[2])


def equation_facts(manager):
    # Exactly two indices were created and observed by THIS fixture setup.
    # These are not generally discoverable/writable equation anchors.
    return {'count': manager.GetCount(), 'disabled_count': manager.GetDisabledEquationCount(),
            'known_fixture_rows': [{'index': index, 'expression': manager.Equation(index),
                                    'disabled': manager.Disabled(index)} for index in (0, 1)]}




def unavailable_copy_reference_observation(is_null, status):
    """Unavailable is not necessarily the native Deleted bit.

    Independent before/after census and absent body prove this fixture's CAD
    effect. This observation reports native Invalid and Deleted separately.
    """
    if is_null is not True or type(status) is not int or status not in (1, 4, 5):
        raise ValueError('Copy reference is not independently observed as invalid/deleted.')
    return {'persistent_reference_status': status,
            'persistent_reference_unavailable_verified': True,
            'native_reference_invalid_bit_verified': bool(status & 1),
            'native_reference_deleted_bit_verified': bool(status & 4)}


def probe_owned_copy_delete(adapter, source, clone, target, persistent_id, trace, report, unchanged):
    """One explicitly resolved extrusion/absorbed sketch, in this OWNED copy."""
    module = binding.module()
    sw = binding.connect(show=False)
    assert adapter.identity(sw.ActiveDoc) == adapter.identity(clone)
    assert adapter.identity(target) == adapter.identity(adapter.resolve_persistent_id(clone, persistent_id, 'feature'))
    assert target.GetTypeName2() == 'Extrusion'
    parents = [binding.wrap(raw, module.IFeature) for raw in (target.GetParents() or ())]
    sketches = [row for row in parents if row.GetTypeName2() == 'ProfileFeature']
    assert len(sketches) == 1 and not (target.GetChildren() or ())
    sketch = sketches[0]
    assert adapter.identity(sketch.GetOwnerFeature()) == adapter.identity(target)
    expected_removed = {int(target.GetID()), int(sketch.GetID())}

    def census():
        result = [{'native_id': int(row.GetID()), 'name': str(row.Name),
                   'type': str(row.GetTypeName2()), 'errors': list(row.GetErrorCode2())}
                  for row in adapter.features(clone)]
        assert len({row['native_id'] for row in result}) == len(result)
        return result

    before = census()
    manager = binding.wrap(clone.SelectionManager, module.ISelectionMgr)
    assert manager.GetSelectedObjectCount2(-1) == 0
    equation_manager = binding.wrap(clone.GetEquationMgr(), module.IEquationMgr)
    equations_before = equation_facts(equation_manager)
    trace({'phase': 'before_select_copy_deletion_target', 'expected_removed_native_ids': sorted(expected_removed)})
    assert target.Select2(False, 0) is True
    assert manager.GetSelectedObjectCount2(-1) == 1
    selected = manager.GetSelectedObject6(1, -1)
    assert selected is not None and adapter.identity(selected) == adapter.identity(target)
    unchanged('after_copy_deletion_selection', clone)
    report['native_delete_attempted'] = True
    trace({'phase': 'before_delete_owned_copy_selection', 'options': 2})  # swDelete_Absorbed
    result = adapter._extension(clone).DeleteSelection2(2)
    trace({'phase': 'copy_delete_returned', 'result': result})
    assert type(result) is bool and result is True
    after = census()
    before_ids, after_ids = {row['native_id'] for row in before}, {row['native_id'] for row in after}
    report['copy_delete_observations'] = {'scope': 'owned_single_extrusion_and_absorbed_sketch_v1',
        'options': 2, 'expected_removed_native_ids': sorted(expected_removed),
        'before': before, 'after': after, 'removed_native_ids': sorted(before_ids - after_ids),
        'added_native_ids': sorted(after_ids - before_ids)}
    assert expected_removed.isdisjoint(after_ids)
    assert {row['native_id'] for row in before if row['type'] in ('Extrusion', 'ProfileFeature') and row['native_id'] not in after_ids} == expected_removed
    assert [row for row in before if row['type'] == 'RefPlane'] == [row for row in after if row['type'] == 'RefPlane']
    assert adapter.bodies(clone, 'all') == []
    assert manager.GetSelectedObjectCount2(-1) == 0
    raw, status = adapter._extension(clone).GetObjectByPersistReference3(adapter._persistent_variant(persistent_id))
    report['copy_delete_observations'].update(persistent_reference_status=status, persistent_reference_null=raw is None)
    report['copy_delete_observations'].update(unavailable_copy_reference_observation(raw is None, status))
    assert equation_facts(equation_manager) == equations_before
    source_target = adapter.resolve_persistent_id(source, persistent_id, 'feature')
    assert int(source_target.GetID()) in expected_removed and source_target.GetTypeName2() == 'Extrusion'
    unchanged('after_copy_delete', clone)
    report['native_copy_delete_effect_verified'] = True
    trace({'phase': 'owned_copy_delete_effect_and_source_preservation_verified'})


def check(state, report, gate, *, probe_delete=False):
    report.update(_provenance(), accepted=False, request_id=uuid.uuid4().hex,
                  public_mcp_copy_acceptance=False, native_delete_attempted=False,
                  deletion_impact_complete=False, deletion_authorized=False,
                  stl_preferences_verified=False, original_document_baseline_restored=False,
                  disabled_equation_generic_discovery_verified=False,
                  native_known_disabled_equation_recovered_on_copy_verified=False,
                  native_copy_delete_effect_verified=False)
    original = native_snapshot()
    report['original_open_document_count'] = len(original[3])
    sw, module = binding.connect(show=False), binding.module()
    original_ui, preferences = ui_snapshot(sw, module), application_preferences(sw)
    original_files = user_file_metadata(original)
    trace = adapter = None
    primary = None
    try:
        trace = PrivateTrace(state / 'isolated-copy.trace.jsonl')
        with fixtures(cleanup_gate=gate.can_cleanup) as (_, owned, _):
            try:
                adapter = SolidWorksDocuments()
                source = owned[1]
                source_identity = adapter.identity(source)
                source_path = state / 'Исходная контрольная деталь.SLDPRT'
                copy_path = state / 'Копия для анализа.SLDPRT'
                assert not source.GetPathName() and not source_path.exists() and not copy_path.exists()
                trace({'phase': 'before_owned_source_save', 'request_id': report['request_id'],
                       'source_title': source.GetTitle(), 'source_path': str(source_path)})
                status = source.SaveAs3(str(source_path), 0, 1)
                trace({'phase': 'owned_source_save_returned', 'status': status})
                assert type(status) is int and status == 0
                assert Path(source.GetPathName()).resolve() == source_path.resolve()
                assert adapter.identity(source) == source_identity
                source_file = file_facts(source_path)
                trace({'phase': 'owned_source_save_verified', 'file': source_file})
                manager = binding.wrap(source.GetEquationMgr(), module.IEquationMgr)
                assert manager.GetCount() == 0 and manager.GetDisabledEquationCount() == 0
                expressions = ['"Величина для копирования" = 3', '"Отключённая величина для копирования" = 5']
                for index, expression in enumerate(expressions):
                    trace({'phase': 'before_owned_equation_add', 'index': index, 'expression': expression})
                    actual = manager.Add2(-1, expression, False)
                    assert type(actual) is int and actual == index and manager.Equation(index) == expression
                    trace({'phase': 'owned_equation_add_verified', 'index': index})
                trace({'phase': 'before_owned_equation_disable', 'index': 1})
                manager.SetDisabled(1, True)
                equations = equation_facts(manager)
                assert equations['count'] == 1 and equations['disabled_count'] == 1
                assert equations['known_fixture_rows'][1]['disabled'] is True
                trace({'phase': 'owned_equation_disable_verified', 'equations': equations})
                feature = next(row for row in adapter.features(source) if row.GetTypeName2() == 'Extrusion')
                feature_meta = (int(feature.GetID()), str(feature.Name), str(feature.GetTypeName2()))
                persistent_id = adapter.persistent_id(source, feature)
                assert persistent_id
                assert adapter.identity(adapter.resolve_persistent_id(source, persistent_id, 'feature')) == adapter.identity(feature)
                baseline, baseline_ui = native_snapshot(), ui_snapshot(sw, module)
                source_facts = owned_source_snapshot(source, module)
                report.update(source_before=source_facts, source_equations_before=equations,
                              source_file_before=source_file, source_feature_reference_bytes=len(persistent_id),
                              source_feature_reference_hex=persistent_id.hex())

                def unchanged(phase, clone=None):
                    current = native_snapshot()
                    current_ui = ui_snapshot(sw, module)
                    if clone is None:
                        assert current == baseline and current_ui == baseline_ui
                    else:
                        identity = adapter.identity(clone)
                        assert current[:2] == baseline[:2]
                        assert [row for row in current[3] if row[0] != identity] == baseline[3]
                        assert [row for row in current_ui if row[0] != identity] == baseline_ui
                        assert sum(row[0] == identity for row in current[3]) == 1
                    after = owned_source_snapshot(source, module)
                    report[phase] = assert_owned_source_facts_unchanged(source_facts, after)
                    assert equation_facts(manager) == equations
                    assert file_facts(source_path) == source_file
                    assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, phase + '_preferences')
                    trace({'phase': phase + '_source_verified', 'source': after})

                trace({'phase': 'before_save_copy', 'options': 3, 'copy_path': str(copy_path)})
                status = source.SaveAs3(str(copy_path), 0, 3)  # Silent | Copy; continue editing source
                trace({'phase': 'save_copy_returned', 'status': status})
                assert type(status) is int and status == 0
                report['copy_file_before'] = copy_file = file_facts(copy_path)
                unchanged('after_copy_save')
                report['native_save_copy_source_unchanged_verified'] = True
                trace({'phase': 'before_open_owned_copy', 'configuration': 'Основная'})
                raw, errors, warnings = sw.OpenDoc6(str(copy_path), 1, 1, 'Основная', 0, 0)
                # Retain the exact returned handle before further getters/mutations.
                if raw is not None:
                    clone = binding.wrap(raw, module.IModelDoc2)
                    owned.append(clone)
                else:
                    clone = None
                trace({'phase': 'open_owned_copy_returned', 'errors': errors, 'warnings': warnings,
                       'model_returned': clone is not None})
                assert clone is not None and type(errors) is int and errors == 0
                assert type(warnings) is int and warnings == 0
                assert adapter.identity(clone) != source_identity
                assert Path(clone.GetPathName()).resolve() == copy_path.resolve() and clone.GetType() == 1
                assert binding.wrap(clone.GetActiveConfiguration(), module.IConfiguration).Name == 'Основная'
                unchanged('after_copy_open', clone)
                copied_feature = adapter.resolve_persistent_id(clone, persistent_id, 'feature')
                copied_meta = (int(copied_feature.GetID()), str(copied_feature.Name), str(copied_feature.GetTypeName2()))
                assert copied_meta == feature_meta and adapter.identity(copied_feature) != adapter.identity(feature)
                report['native_copy_feature_reference_resolution_verified'] = True
                copied_manager = binding.wrap(clone.GetEquationMgr(), module.IEquationMgr)
                copy_equations = equation_facts(copied_manager)
                report['copy_equations_before'] = copy_equations
                assert copy_equations['count'] == 1 and copy_equations['disabled_count'] == 1
                assert [row['disabled'] for row in copy_equations['known_fixture_rows']] == [False, True]
                assert copy_equations['known_fixture_rows'][1]['expression'] == ''
                assert numeric_global_fixture_signature(copy_equations['known_fixture_rows'][0]['expression']) == numeric_global_fixture_signature(expressions[0])
                report['copy_equation_comparison_scope'] = 'owned_two_integer_globals_v1'
                report['copy_active_equation_raw_text_identical'] = copy_equations['known_fixture_rows'][0]['expression'] == expressions[0]
                copy_facts = owned_source_snapshot(clone, module)
                report['copy_geometry_comparison'] = assert_owned_source_facts_unchanged(
                    {key: source_facts[key] for key in ('native_extrema_m', 'body_mass_facts')},
                    {key: copy_facts[key] for key in ('native_extrema_m', 'body_mass_facts')})
                for name in ('AutomaticRebuild', 'AutomaticSolveOrder'):
                    before = getattr(copied_manager, name)
                    assert type(before) is bool
                    if before:
                        trace({'phase': 'before_copy_equation_property', 'name': name, 'value': False})
                        setattr(copied_manager, name, False)
                        assert getattr(copied_manager, name) is False
                        trace({'phase': 'copy_equation_property_verified', 'name': name})
                trace({'phase': 'before_enable_known_copy_equation', 'index': 1})
                copied_manager.SetDisabled(1, False)
                recovered = equation_facts(copied_manager)
                report['copy_equations_after'] = recovered
                if recovered['count'] == 2 and recovered['disabled_count'] == 0:
                    assert [numeric_global_fixture_signature(row['expression']) for row in recovered['known_fixture_rows']] == [numeric_global_fixture_signature(expression) for expression in expressions]
                    assert all(row['disabled'] is False for row in recovered['known_fixture_rows'])
                    report['native_known_disabled_equation_recovered_on_copy_verified'] = True
                    report['disabled_enable_probe_outcome'] = 'known_fixture_definition_recovered'
                else:
                    # A returned setter is not proof of effect. Only exact
                    # observed NO CHANGE is a known negative probe outcome.
                    assert recovered == copy_equations
                    report['disabled_enable_probe_outcome'] = 'no_observed_effect'
                trace({'phase': 'known_copy_equation_enable_observed',
                       'outcome': report['disabled_enable_probe_outcome'], 'equations': recovered})
                unchanged('after_copy_equation_enable', clone)
                enabled_facts = owned_source_snapshot(clone, module)
                report['enabled_copy_geometry_comparison'] = assert_owned_source_facts_unchanged(
                    {key: copy_facts[key] for key in ('native_extrema_m', 'body_mass_facts')},
                    {key: enabled_facts[key] for key in ('native_extrema_m', 'body_mass_facts')})
                assert file_facts(copy_path) == copy_file, 'Copy was unexpectedly saved after enable.'
                if probe_delete:
                    probe_owned_copy_delete(adapter, source, clone, copied_feature,
                                            persistent_id, trace, report, unchanged)
                trace({'phase': 'before_close_owned_copy_without_save', 'title': clone.GetTitle(), 'path': str(copy_path)})
                sw.CloseDoc(clone.GetTitle())
                assert owned[-1] is clone
                owned.pop()
                trace({'phase': 'before_restore_owned_source_activation', 'source_title': source.GetTitle()})
                restored, error = sw.ActivateDoc3(source.GetTitle(), False, 1, 0)
                assert restored is not None and type(error) is int and error == 0
                assert adapter.identity(restored) == source_identity
                unchanged('after_copy_close')
                assert file_facts(copy_path) == copy_file
                trace({'phase': 'owned_copy_closed_source_verified'})
                report.update(native_copy_closed_without_save_verified=True,
                              source_file_and_equations_preserved=True)
            except BaseException:
                gate.retain()
                raise
        assert native_snapshot() == original and ui_snapshot(sw, module) == original_ui
        assert user_file_metadata(original) == original_files
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'original_preferences_comparison')
        report.update(accepted=True, acceptance_scope='owned_single_configuration_copy_feasibility_v1', original_document_baseline_restored=True,
                      non_stl_preferences_and_ui_restored=True, owned_fixture_documents_closed=True)
    except BaseException as error:
        primary = error
        gate.retain()
        raise
    finally:
        cleanup_errors = []
        for resource in (adapter, trace):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as error:
                    gate.retain()
                    cleanup_errors.append(error)
        if primary is not None:
            for error in cleanup_errors:
                primary.add_note('Isolated copy resource cleanup failed: ' + type(error).__name__)
        elif cleanup_errors:
            for error in cleanup_errors[1:]:
                cleanup_errors[0].add_note('Another isolated copy cleanup failed: ' + type(error).__name__)
            raise cleanup_errors[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--probe-delete', action='store_true', help='Delete only the resolved owned-copy extrusion and absorbed sketch.')
    args = parser.parse_args()
    private = Path(__file__).resolve().parent.parent / 'work'
    assert all(path.resolve().is_relative_to(private) for path in (args.state_dir, args.report))
    assert not args.state_dir.exists() and not args.report.exists()
    args.state_dir = args.state_dir.resolve()
    args.report = args.report.resolve()
    args.state_dir.mkdir(parents=True)
    report, gate = {}, InlineFixtureCleanupGate()
    pythoncom.CoInitialize()
    try:
        check(args.state_dir, report, gate, probe_delete=args.probe_delete)
    except BaseException as error:
        report.update(accepted=False, error_type=type(error).__name__, error_message=str(error),
                      fixture_retention_required=not gate.can_cleanup(), automatic_replay_attempted=False)
        try:
            with args.report.open('x', encoding='utf8') as stream:
                json.dump(report, stream, ensure_ascii=True, allow_nan=False, indent=2)
        except BaseException as report_error:
            error.add_note('Private isolated copy report write failed: ' + type(report_error).__name__)
        raise
    else:
        with args.report.open('x', encoding='utf8') as stream:
            json.dump(report, stream, ensure_ascii=True, allow_nan=False, indent=2)
        print(json.dumps({'accepted': report['accepted'], 'package_version': report['package_version'],
                          'native_known_disabled_equation_recovered_on_copy_verified': report['native_known_disabled_equation_recovered_on_copy_verified'],
                          'native_delete_attempted': report['native_delete_attempted'],
                          'native_copy_delete_effect_verified': report['native_copy_delete_effect_verified']}))
    finally:
        primary = sys.exception()
        try:
            pythoncom.CoUninitialize()
        except BaseException as error:
            if primary is None:
                raise
            primary.add_note('Isolated copy COM cleanup failed: ' + type(error).__name__)


if __name__ == '__main__':
    main()