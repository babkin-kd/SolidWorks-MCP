"""Installed-wheel native mass checks, exclusively on disposable owned fixtures.

Preparation is not evidence. Requires an explicit opt-in and empty/free native
session. Failed/uncertain checks retain fixtures; never repeat COM automatically.
Acceptance is scoped to this internal part-read candidate, never the complete
project stage or a public MCP command.
"""

import argparse
import importlib.metadata
import hashlib
import json
import math
import os
from pathlib import Path
import sysconfig
import uuid

import pythoncom
import win32com.client

import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import (SW_UNITS_LINEAR, SW_TOGGLE_3D_INTERCONNECT,
    SW_UNSUPPRESS_DEPENDENT, SW_DELETE_CHILDREN, SW_DELETE_ABSORBED)
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.geometry import GeometryCatalog
from solidworks_mcp.jobs import ExecutionFailure
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences, activate_owned
from verify_geometry_reads import fixtures
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_wheel_artifact import validate_wheel


class CleanupGate:
    def __init__(self): self.allowed = False
    def can_cleanup(self): return self.allowed


def source_state(sw, module):
    """Independent selection identities, body facts, units and native revisions."""
    result = []
    for raw in sw.GetDocuments() or ():
        model = binding.wrap(raw, module.IModelDoc2)
        extension = binding.wrap(model.Extension, module.IModelDocExtension)
        selection = binding.wrap(model.SelectionManager, module.ISelectionMgr)
        selected = tuple((selection.GetSelectedObject6(i, -1)._oleobj_.QueryInterface(pythoncom.IID_IUnknown),
                          int(selection.GetSelectedObjectMark(i)))
                         for i in range(1, selection.GetSelectedObjectCount2(-1) + 1))
        bodies = tuple(binding.wrap(raw, module.IBody2)
                       for raw in binding.wrap(model, module.IPartDoc).GetBodies2(-1, False) or ())
        facts = tuple((body._oleobj_.QueryInterface(pythoncom.IID_IUnknown), str(body.Name),
                       int(body.GetType()), bool(body.Visible), int(body.GetFaceCount()),
                       int(body.GetEdgeCount())) for body in bodies)
        mass = tuple(tuple(body.GetMassProperties(1.)) for body in bodies if body.GetType() == 0)
        view = binding.wrap(model.ActiveView, module.IModelView)
        if view is None:
            view_state = None
        else:
            orientation = binding.wrap(view.Orientation3, module.IMathTransform)
            translation = binding.wrap(view.Translation3, module.IMathVector)
            view_state = (tuple(orientation.ArrayData), tuple(translation.ArrayData), float(view.Scale2))
        result.append((selected, facts, mass, extension.GetUserPreferenceInteger(SW_UNITS_LINEAR, 0), view_state))
    return native_snapshot(), result


def confirm_source(first, second):
    assert first[0] == second[0], 'Native document/configuration state changed during a read.'
    assert len(first[1]) == len(second[1])
    for before, after in zip(first[1], second[1]):
        assert before[:2] == after[:2] and before[3:] == after[3:], 'Selection, bodies or units changed.'
        assert len(before[2]) == len(after[2])
        for left, right in zip(before[2], after[2]):
            assert len(left) == len(right) == 12
            for i, (a, b) in enumerate(zip(left, right)):
                assert math.isfinite(a) and math.isfinite(b)
                assert math.isclose(a, b, rel_tol=1e-12, abs_tol=0. if i < 6 else 1e-25), 'Independent body fact changed.'


def check_analytical(result, count, x):
    values = result['mass_properties']
    assert result['body_count'] == count
    assert math.isclose(values['volume_mm3'], count * 1000., rel_tol=1e-9, abs_tol=1e-6)
    assert math.isclose(values['surface_area_mm2'], count * 700., rel_tol=1e-9, abs_tol=1e-6)
    for actual, expected in zip(values['center_of_mass_mm'], (x, 5., 2.5)):
        assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)
    assert values['mass_kg'] > 0 and values['density_kg_m3'] > 0
    assert math.isclose(values['mass_kg'], values['volume_mm3'] * 1e-9 * values['density_kg_m3'], rel_tol=1e-6)
    # Density is calculated by SolidWorks; no enterprise-material validation is claimed.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--guarded-public-domain', action='store_true',
                        help='Accept the durable public measurement domain rather than the historical passive backend.')
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.run_solidworks:
        parser.error('Native checks require explicit --run-solidworks; no COM connection attempted.')
    assert not os.environ.get('PYTHONPATH'), 'Source PYTHONPATH is prohibited.'
    package = Path(solidworks_mcp.__file__).resolve().parent
    assert package.is_relative_to(Path(sysconfig.get_path('purelib')).resolve())
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version, expected_git_sha=args.expected_git_sha)
    assert solidworks_mcp.__version__ == importlib.metadata.version('solidworks-mcp') == args.expected_version
    assert source_digest(package) == wheel['source_digest']
    build = json.loads((package / 'build_info.json').read_text())
    assert build['git_sha'] == args.expected_git_sha and build['source_dirty'] is False
    state = args.state_dir.resolve()
    private = (Path(__file__).resolve().parents[1] / 'work').resolve()
    assert state.is_relative_to(private) and state != private
    state.mkdir(parents=True, exist_ok=False)
    report = {'accepted': False, 'core_suite_passed': False, 'scope': 'internal_part_mass_read_native_v1',
              'request_id': uuid.uuid4().hex, 'wheel': wheel,
              'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases': [], 'fixture_cleanup_allowed': False,
              'public_v2_mass_accepted': False, 'material_assignment_verified': False,
              'remaining_native_cases': ['document_mass_overrides', 'document_center_of_mass_override', 'suppressed_or_deleted_body',
                                         'configuration_with_different_geometry']}
    if args.guarded_public_domain:
        report['scope']='internal_guarded_part_mass_native_v1'
    path = state / 'report.json'
    def persist(): path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    sw = None
    owns_guard = False
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        assert not sw.GetDocuments() and not sw.CommandInProgress, 'Requires agreed empty/free baseline; no documents closed.'
        original = native_snapshot()
        preferences = application_preferences(sw)
        interconnect = bool(sw.GetUserPreferenceToggle(SW_TOGGLE_3D_INTERCONNECT))
        report['baseline'] = {'documents': 0, 'command_in_progress': False, 'preferences': preferences,
                              'interconnect': interconnect}
        report['pending_guard_acquisition'] = True
        persist()
        sw.CommandInProgress = True
        assert sw.CommandInProgress, 'Guard acquisition unconfirmed; do not repeat.'
        owns_guard = True
        report['pending_guard_acquisition'] = False
        gate = CleanupGate()
        report['fixture_setup_started'] = True
        persist()
        with fixtures(cleanup_gate=gate.can_cleanup) as (session, owned, _):
            report['fixture_setup_completed'] = True
            report['owned_document_count'] = len(owned)
            report['owned_documents'] = [{'title': model.GetTitle(), 'path': model.GetPathName(),
                                           'type': model.GetType()} for model in owned]
            persist()
            adapter = SolidWorksDocuments()
            documents = DocumentCatalog(adapter)
            geometry = GeometryCatalog(documents)
            if args.guarded_public_domain:
                from concurrent.futures import Future
                from solidworks_mcp.jobs import JobStore,JobRunner
                from solidworks_mcp.mass_measurement import MassMeasurementCatalog
                class InlineSta:
                    def submit(self,function):
                        future=Future()
                        try:future.set_result(function())
                        except BaseException as exc:future.set_exception(exc)
                        return future
                store=JobStore(state/'jobs.sqlite')
                mass=MassMeasurementCatalog(documents,store,uuid.uuid4().hex)
                runner=JobRunner(store,InlineSta())
            module = binding.module()
            first, other = owned
            def context(model):
                item = next(item for item in documents.list()['documents'] if item['title'] == model.GetTitle())
                return dict(document_id=item['document_id'], configuration=item['active_configuration'],
                            expected_observation_revision=item['observation_revision'])
            ctx = context(first)
            solids = geometry.list(**ctx, body_type='solid')['items']
            solids.sort(key=lambda body: body['bounding_box_mm']['min_mm'][0])
            assert len(solids) == 2
            surface = geometry.list(**ctx, body_type='surface')['items']
            assert len(surface) == 1
            def case(label, *, parameters=None, body_id=None, error=None, count=2, x=30.):
                nonlocal owns_guard
                baseline = source_state(sw, module)
                before_preferences = application_preferences(sw)
                arguments = dict(context(first) if parameters is None else parameters)
                if body_id is not None: arguments['body_id'] = body_id
                try:
                    if args.guarded_public_domain:
                        prepared=mass.prepare(**arguments)
                        arguments['expected_revision']=prepared['revision']
                        report['pending_case_guard_release']=label;persist()
                        assert owns_guard and sw.CommandInProgress
                        sw.CommandInProgress=False
                        assert sw.CommandInProgress is False
                        owns_guard=False
                        job=runner.submit(uuid.uuid4().hex,'measurement.mass',arguments,
                            lambda operation_id:mass.measure(operation_id,**arguments),context=arguments,
                            mutates=True,pass_operation_id=True,verify=lambda value:value['verified'] is True)
                        report['last_guarded_job']={'operation_id':job['operation_id'],'status':job['status'],
                            'error':job['error'],'mutation_phase':job['mutation']['phase'] if job['mutation'] else None}
                        persist()
                        assert job['status'] in ('succeeded','failed'), 'Uncertain native job: retain fixtures; never retry.'
                        assert not store.mutation_blockers('fresh_epoch','fresh_document')
                        assert sw.CommandInProgress is False and first.GetBlockingState()==0
                        sw.CommandInProgress=True
                        assert sw.CommandInProgress is True
                        owns_guard=True
                        report['pending_case_guard_release']=None;persist()
                        if job['status']=='failed':
                            assert job['mutation']['phase'] in ('rolled_back','not_started')
                            raise ExecutionFailure(job['error']['code'],job['error']['message'],uncertain=False)
                        result=job['result']
                        assert result['execution_guard']['selection_preserved'] and result['execution_guard']['released']
                    else:result = geometry.measure_mass(**arguments)
                except ExecutionFailure as exc:
                    expected = (error,) if isinstance(error, str) else tuple(error or ())
                    assert exc.code in expected and exc.uncertain is False, (label, exc.code)
                    result = {'expected_error': exc.code}
                else:
                    assert error is None, (label, 'Expected rejection')
                    check_analytical(result, count, x)
                after = source_state(sw, module)
                try:
                    confirm_source(baseline, after)
                except AssertionError:
                    report['read_state_mismatch'] = {'case': label, 'before': repr(baseline),
                                                     'after': repr(after)}
                    persist()
                    raise
                assert application_preferences(sw) == before_preferences, 'Read changed preferences.'
                assert sw.CommandInProgress, 'Owned application guard lost.'
                report['cases'].append({'label': label, 'passed': True, 'result': result})
                persist()
            case('all_solids')
            case('explicit_first', body_id=solids[0]['object_id'], count=1, x=10.)
            case('explicit_second', body_id=solids[1]['object_id'], count=1, x=50.)
            case('foreign_reference', parameters=context(other), body_id=solids[0]['object_id'], error='object_reference_not_found')
            case('inactive_configuration', parameters={**ctx, 'configuration': 'Вариант'}, error='configuration_not_active')
            case('stale_revision', parameters={**ctx, 'expected_observation_revision': 'obsolete'}, error='observation_revision_mismatch')
            case('surface_reference', body_id=surface[0]['object_id'], error='unsupported_body_type')
            bodies = sorted(adapter.bodies(first, 'solid'), key=lambda body: body.GetBodyBox()[0])
            bodies[1].HideBody(True)  # Owned fixture only; native void, verify by readback.
            assert not bodies[1].Visible
            case('hidden_solid_included')
            case('hidden_solid_explicit', body_id=solids[1]['object_id'], count=1, x=50.)
            first.ClearSelection2(True)
            assert bodies[0].Select2(False, None)
            case('ui_selected_other_body', body_id=solids[1]['object_id'], count=1, x=50.)
            extension = binding.wrap(first.Extension, module.IModelDocExtension)
            for unit, label in [(0, 'millimetre_units'), (3, 'inch_units')]:
                assert extension.SetUserPreferenceInteger(SW_UNITS_LINEAR, 0, unit)
                assert extension.GetUserPreferenceInteger(SW_UNITS_LINEAR, 0) == unit
                case(label)
            # Every following write changes only an owned disposable fixture.
            activate_owned(sw, first, first.GetTitle())
            session._model = first
            def current_second_feature():
                return next(feature for feature in session._iter_features()
                            if feature.Name == 'Контрольный блок 2')
            report['pending_fixture_mutation'] = 'variant_suppression'
            persist()
            assert first.ShowConfiguration2('Вариант')
            second_feature = current_second_feature()  # IFeature can retain its old configuration scope.
            assert second_feature.SetSuppression2(0, 1, None)  # swSuppress, swThisConfiguration.
            assert second_feature.IsSuppressed2(1, None) == (True,)
            assert first.ForceRebuild3(False)
            assert len(adapter.bodies(first, 'solid')) == 1
            report['pending_fixture_mutation'] = None
            case('variant_different_geometry', count=1, x=10.)
            case('reference_from_other_configuration', body_id=solids[0]['object_id'], error='object_configuration_mismatch')
            report['pending_fixture_mutation'] = 'main_suppression'
            persist()
            assert first.ShowConfiguration2('Основная')
            second_feature = current_second_feature()
            assert second_feature.IsSuppressed2(1, None) == (False,)
            assert second_feature.SetSuppression2(0, 1, None)
            assert second_feature.IsSuppressed2(1, None) == (True,)
            assert first.ForceRebuild3(False)
            assert len(adapter.bodies(first, 'solid')) == 1
            report['pending_fixture_mutation'] = None
            unavailable = ('object_suppressed', 'object_deleted', 'object_reference_invalid',
                           'object_not_in_active_configuration')
            case('suppressed_body_reference', body_id=solids[1]['object_id'], error=unavailable)
            report['pending_fixture_mutation'] = 'restore_main_suppression'
            persist()
            assert second_feature.SetSuppression2(SW_UNSUPPRESS_DEPENDENT, 1, None)
            assert second_feature.IsSuppressed2(1, None) == (False,)
            assert first.ForceRebuild3(False)
            assert len(adapter.bodies(first, 'solid')) == 2
            report['pending_fixture_mutation'] = None
            case('restored_main_geometry')
            def override_mass(enabled, *, center=False):
                flag = 'OverrideCenterOfMass' if center else 'OverrideMass'
                report['pending_fixture_mutation'] = flag + '_' + str(enabled)
                persist()
                first.ClearSelection2(True)
                calculation = binding.wrap(extension.CreateMassProperty2(), module.IMassProperty2)
                assert calculation is not None
                scoped = adapter.bodies(first, 'solid')
                calculation.SelectedItems = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [body._oleobj_ for body in scoped])
                options = binding.wrap(calculation.GetOverrideOptions(), module.IMassPropertyOverrideOptions)
                assert options is not None
                setattr(options, flag, enabled)
                assert bool(getattr(options, flag)) == enabled
                if enabled and center:
                    assert options.SetOverrideCenterOfMassValue(win32com.client.VARIANT(
                        pythoncom.VT_ARRAY | pythoncom.VT_R8, (.1, .2, .3)), '')
                elif enabled:
                    assert options.SetOverrideMassValue(1.)
                assert calculation.SetOverrideOptions(options, 1, None)
                assert first.ForceRebuild3(False)
                confirmation = binding.wrap(extension.CreateMassProperty2(), module.IMassProperty2)
                actual = binding.wrap(confirmation.GetOverrideOptions(), module.IMassPropertyOverrideOptions)
                assert actual is not None and bool(getattr(actual, flag)) == enabled
                report['pending_fixture_mutation'] = None
                persist()
            override_mass(True)
            case('document_mass_override', error='mass_properties_overridden')
            override_mass(False)
            case('restored_calculated_mass')
            override_mass(True, center=True)
            case('document_center_of_mass_override', error='mass_properties_overridden')
            override_mass(False, center=True)
            case('restored_calculated_center')
            report['pending_fixture_mutation'] = 'delete_second_fixture_feature'
            persist()
            first.ClearSelection2(True)
            assert second_feature.Select2(False, 0)
            assert extension.DeleteSelection2(SW_DELETE_CHILDREN | SW_DELETE_ABSORBED)  # Absorbed and child features of this isolated fixture feature.
            assert first.ForceRebuild3(False)
            assert len(adapter.bodies(first, 'solid')) == 1
            assert all(feature.Name != 'Контрольный блок 2' for feature in session._iter_features())
            report['pending_fixture_mutation'] = None
            case('deleted_body_reference', body_id=solids[1]['object_id'], error=unavailable)
            case('geometry_after_delete', count=1, x=10.)
            assert len(report['cases']) == 22
            if args.guarded_public_domain:
                report['guarded_jobs_terminal']=all(job['status'] in ('succeeded','failed') for job in store.list(limit=100)['items'])
                assert report['guarded_jobs_terminal'] and not store.mutation_blockers('final_epoch','final_document')
                store.close()
            report['remaining_native_cases'] = []
            assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'fixture_non_stl_preferences')
            assert bool(sw.GetUserPreferenceToggle(SW_TOGGLE_3D_INTERCONNECT)) == interconnect
            current = tuple(binding.wrap(raw, module.IModelDoc2) for raw in sw.GetDocuments() or ())
            assert len(current) == len(owned) == 2, 'Unexpected document; fixtures retained.'
            owned_tokens = tuple(model._oleobj_.QueryInterface(pythoncom.IID_IUnknown) for model in owned)
            current_tokens = tuple(model._oleobj_.QueryInterface(pythoncom.IID_IUnknown) for model in current)
            assert all(any(token == owner for owner in owned_tokens) for token in current_tokens)
            titles = tuple(model.GetTitle() for model in current)
            assert len(set(titles)) == 2 and all(not model.GetPathName() for model in current)
            assert sw.CommandInProgress, 'Owned guard lost before cleanup.'
            report['cleanup_ownership_confirmed'] = True
            gate.allowed = True  # Exact owned unsaved fixtures only; no foreign documents.
            report['fixture_cleanup_allowed'] = True
            persist()
        assert native_snapshot() == original and not sw.GetDocuments()
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_non_stl_preferences')
        assert bool(sw.GetUserPreferenceToggle(SW_TOGGLE_3D_INTERCONNECT)) == interconnect
        report['core_suite_passed'] = True
        report['owned_documents_closed'] = True
    except BaseException as exc:
        report['error_type'], report['error'] = type(exc).__name__, str(exc)
        raise
    finally:
        try:
            if owns_guard:
                assert sw.CommandInProgress, 'Owned guard lost; no setter attempted.'
                report['pending_guard_release'] = True
                persist()
                sw.CommandInProgress = False
                assert not sw.CommandInProgress, 'Guard release unconfirmed; do not repeat.'
                report['pending_guard_release'] = False
                report['guard_released'] = True
        except BaseException as exc:
            report['core_suite_passed'] = False
            report['guard_release_error'] = repr(exc)
            raise
        finally:
            report['accepted'] = bool(report['core_suite_passed'] and report.get('guard_released')
                                      and not report['remaining_native_cases'])
            persist()
            pythoncom.CoUninitialize()
    print(json.dumps({'core_suite_passed': report['core_suite_passed'], 'native_cases': len(report['cases']),
                      'internal_native_accepted': report['accepted'], 'public_v2_mass_accepted': False, 'report': str(path)}))


if __name__ == '__main__':
    main()
