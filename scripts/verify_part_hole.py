"""Installed internal circular through-hole, stale rejection and exact owned restoration."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sysconfig
import uuid

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.document_creation import DocumentCreationCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.features import FeatureCatalog
from solidworks_mcp.part_creation import PartCreationCatalog
from solidworks_mcp.part_hole import PartHoleCatalog
from solidworks_mcp.part_hole_edit import PartHoleEditCatalog
from solidworks_mcp.sketches import SketchCatalog, same_sketch_geometry
from solidworks_mcp.jobs import JobRunner, JobStore
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences
from verify_mass_properties import source_state
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_wheel_artifact import validate_wheel
from verifier_fixture_cleanup import InlineFixtureCleanupGate, guarded_inline_submit, untouched_busy_guard
from verify_part_construction import Worker


def prewrite_rejection(job, code):
    """Preparation may reject before any checkpoint; both forms are explicit."""
    error = job.get('error') or {}
    mutation = job.get('mutation')
    return (job.get('status') == 'failed' and error.get('code') == code
            and error.get('requires_reconciliation') is False
            and (mutation is None or mutation.get('phase') == 'not_started'))


class Adapter(SolidWorksDocuments):
    inject_cut = False
    inject_edit = False
    inject_pattern = False
    inject_fillet = False
    inject_sheet_parameters=False

    def sheet_modify_parameters(self,*args):
        result=super().sheet_modify_parameters(*args)
        if self.inject_sheet_parameters:
            self.inject_sheet_parameters=False
            raise RuntimeError("Known verifier failure after exact native template update and rebuild.")
        return result

    inject_sheet_state=False
    def sheet_preserve_flat_names(self,*args):
        super().sheet_preserve_flat_names(*args)
        if self.inject_sheet_state:
            self.inject_sheet_state=False
            raise RuntimeError('Known verifier failure after complete native sheet state/name preservation.')

    inject_sheet = False

    def create_sheet_l_profile(self,*args):
        super().create_sheet_l_profile(*args)
        if self.inject_sheet:
            self.inject_sheet=False
            raise RuntimeError('Known verifier failure after complete owned native folded-sheet creation.')

    def create_edge_fillet(self,*args):
        super().create_edge_fillet(*args)
        if self.inject_fillet:
            self.inject_fillet=False
            raise RuntimeError('Known verifier failure after exact own fillet retention and rebuild.')

    def create_linear_hole_pattern(self,*args):
        super().create_linear_hole_pattern(*args)
        if self.inject_pattern:
            self.inject_pattern=False
            raise RuntimeError('Known verifier failure after exact own pattern retention and rebuild.')

    def rebuild_dimension_document(self, *args):
        result = super().rebuild_dimension_document(*args)
        if self.inject_edit:
            self.inject_edit = False
            assert result is True
            raise RuntimeError('Known verifier failure after solving the own circle driver.')
        return result

    def create_through_hole(self, *args):
        super().create_through_hole(*args)
        if self.inject_cut:
            self.inject_cut = False
            raise RuntimeError('Known verifier failure after exact cut/sketch retention and rebuild.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--hole-edit-only', action='store_true', help='Complete editing block; older guard/cut fault cases are not run or counted.')
    parser.add_argument('--pattern-only',action='store_true',help='Complete native linear hole pattern block; hole-edit cases are not counted.')
    parser.add_argument('--fillet-only',action='store_true',help='Complete native selected-edge fillet block; hole/pattern cases are not counted.')
    parser.add_argument('--sheet-parameters-only',action='store_true',help='Existing L-sheet parameter editing block.')
    parser.add_argument('--sheet-flat-only',action='store_true',help='Existing native L-sheet flat/fold state block.')
    parser.add_argument('--sheet-only',action='store_true',help='Empty-part folded sheet block; plate/hole/fillet cases are not run or counted.')
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    if sum((args.pattern_only,args.hole_edit_only,args.fillet_only,args.sheet_only,args.sheet_flat_only,args.sheet_parameters_only))>1:parser.error('Choose one engineering block.')
    if not args.run_solidworks: parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH'), 'Installed package only, without source PYTHONPATH.'
    package = Path(solidworks_mcp.__file__).resolve().parent
    assert package.is_relative_to(Path(sysconfig.get_path('purelib')).resolve())
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version, expected_git_sha=args.expected_git_sha)
    assert solidworks_mcp.__version__ == importlib.metadata.version('solidworks-mcp') == args.expected_version
    assert source_digest(package) == wheel['source_digest']
    state = args.state_dir.resolve()
    private = (Path(__file__).resolve().parents[1] / 'work').resolve()
    assert state.is_relative_to(private) and state != private
    state.mkdir(parents=True, exist_ok=False)
    report = {'accepted': False, 'scope': ('internal_selected_edge_fillet_native_v1' if args.fillet_only else 'internal_linear_through_hole_pattern_native_v1' if args.pattern_only else 'internal_circular_through_hole_edit_native_v1' if args.hole_edit_only else 'internal_circular_through_hole_native_v1'), 'wheel': wheel,
              'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases': [], 'owned_documents': [], 'public_mcp_creation_accepted': False}
    def persist():
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    gate, owned = InlineFixtureCleanupGate(), []
    own_flag = False
    adapter, documents, store, sw = None, None, None, None
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and not sw.CommandInProgress, 'Empty/free baseline required; no user document closed.'
        baseline, preferences = native_snapshot(), application_preferences(sw)
        report['baseline_empty_free'] = True
        adapter = Adapter()
        documents, store = DocumentCatalog(adapter), JobStore(state / 'jobs.sqlite')
        catalog = DocumentCreationCatalog(documents, store, 'new-document-native-verifier')
        dimensions = DimensionCatalog(documents, store, 'new-document-native-verifier', mutation_guard=adapter.mutation_guard)
        parts, runner = PartCreationCatalog(dimensions), JobRunner(store, Worker())
        template = catalog.list_templates()['templates'][0]['template_id']
        suffix = uuid.uuid4().hex[:8]
        def record(label, job, expected='succeeded'):
            report['last_job'] = job
            # Known native receipt remains private even if the journal is unknown.
            report['pending_receipts'] = [{'operation_id': op, 'pending_creation': receipt.pending_creation,
                'pending_close': receipt.pending_close, 'has_exact_identity': receipt.identity is not None}
                for op, receipt in catalog.receipts.items()]
            persist()
            assert gate.can_cleanup(), 'Unknown result prohibits another operation/automatic replay.'
            assert job['status'] == expected, job.get('error')
            assert sw.CommandInProgress is own_flag
            verification = (job.get('mutation') or {}).get('verification') or {}
            evidence = verification.get('evidence', {}).get('execution_guard')
            if label.startswith(('plate_in_server_created','guarded_','hole_known_failure','native_circular','hole_edit_')) and expected=='succeeded':
                assert evidence and evidence['scope']=='application_model_mutation_guard_v1'
            if label=='existing_command_flag_not_borrowed':
                assert untouched_busy_guard(evidence)
                assert verification['outcome']=='not_started' and verification['evidence']['native_mutation_started'] is False
                assert job['status']=='failed' and job['error']['code']=='application_busy'
            elif evidence and evidence.get('scope') == 'application_model_mutation_guard_v1':
                assert evidence['original_command_in_progress'] is False
                assert evidence['acquired'] is True and evidence['released'] is True
                assert evidence['selection_preserved'] is True
                assert evidence['model_guards'] == [{'original_state':0,'locked_state':2,'released_state':0}]
            assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'preferences_' + label)
            report['cases'].append({'label': label, 'passed': True, 'job': job})
            persist()
        def create(name, *, stale=False):
            preparation = catalog.prepare_create_part(template, name)
            arguments = dict(document_id=catalog.application_id, configuration='',
                expected_revision='rev_stale' if stale else preparation['revision'], template_id=template,
                name=name, configuration_name='Основная')
            job = guarded_inline_submit(gate, runner, store, uuid.uuid4().hex, 'document.create_part', arguments,
                lambda op: catalog.create_part(op, **arguments),
                context={key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')},
                mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
            report['last_job'] = job
            persist()
            if job['status'] == 'succeeded' and gate.can_cleanup():
                doc_id = job['result']['after']['created_document_id']
                entry = next(entry for entry in documents._entries if entry.document_id == doc_id)
                owned.append((entry.model, adapter.identity(entry.model)))
                report['owned_documents'] = [{'title': model.GetTitle(), 'path': model.GetPathName(),
                    'type': model.GetType()} for model, _ in owned]
                persist()
            return job
        first = create('Контрольная исходная деталь ' + suffix)
        record('new_part_from_empty_session', first)
        first_id = first['result']['after']['created_document_id']
        first_model = owned[0][0]
        plane = next(item for item in adapter.features(first_model) if item.GetTypeName2() == 'RefPlane')
        assert plane.Select2(False, 7)
        source_before = source_state(sw, module)
        second = create('Контрольная новая пластина ' + suffix)
        record('new_part_preserves_existing_document', second)
        second_id, second_model = second['result']['after']['created_document_id'], owned[1][0]
        snap, facts = source_state(sw, module)
        first_identity = owned[0][1]
        actual = [(row, fact) for row, fact in zip(snap[3], facts) if row[0] == first_identity]
        original = [(row, fact) for row, fact in zip(source_before[0][3], source_before[1]) if row[0] == first_identity]
        assert actual == original, 'Existing exact model metadata/geometry/selection/view changed.'
        assert sw.CommandInProgress is False
        # Production mutation guard must acquire/release its own flag after
        # the durable checkpoint. No harness-wide flag hides this lifecycle.
        report['harness_command_flag_borrowed'] = False
        if args.sheet_parameters_only:
            from verifier_sheet_parameters import exercise_sheet_parameters
            report['scope']='internal_l_sheet_parameters_native_v1'
            report['sheet_parameter_helper_sha256']=hashlib.sha256(Path(__file__).with_name('verifier_sheet_parameters.py').read_bytes()).hexdigest()
            exercise_sheet_parameters(adapter,documents,dimensions,store,runner,gate,second_model,
                dict(document_id=second_id,configuration='Основная'),record,report)
            snap,facts=source_state(sw,module)
            assert [(row,fact) for row,fact in zip(snap[3],facts) if row[0]==first_identity]==original
            report['core_suite_passed']=True
            return
        if args.sheet_flat_only:
            from verifier_sheet_flat_state import exercise_sheet_flat
            report['scope']='internal_l_sheet_flat_state_native_v1'
            report['sheet_state_helper_sha256']=hashlib.sha256(Path(__file__).with_name('verifier_sheet_flat_state.py').read_bytes()).hexdigest()
            exercise_sheet_flat(adapter,documents,dimensions,store,runner,gate,second_model,
                dict(document_id=second_id,configuration='Основная'),record,report)
            snap,facts=source_state(sw,module)
            assert [(row,fact) for row,fact in zip(snap[3],facts) if row[0]==first_identity]==original
            report['core_suite_passed']=True
            return
        if args.sheet_only:
            from verifier_sheet_profile import exercise_sheet
            report['scope']='internal_folded_sheet_l_profile_native_v1'
            report['sheet_helper_sha256']=hashlib.sha256(Path(__file__).with_name('verifier_sheet_profile.py').read_bytes()).hexdigest()
            exercise_sheet(adapter,documents,dimensions,store,runner,gate,second_model,
                dict(document_id=second_id,configuration='Основная'),record,report)
            snap,facts=source_state(sw,module)
            assert [(row,fact) for row,fact in zip(snap[3],facts) if row[0]==first_identity]==original
            report['core_suite_passed']=True
            return
        plane = next(row for row in dimensions.features.list(second_id, 'Основная')['items']
                     if row['feature_type'] == 'RefPlane' and row['object_id'])
        parameters = dict(plane_object_id=plane['object_id'], width_mm=40., height_mm=20., depth_mm=10.)
        prepared = parts.prepare_base_extrusion(second_id, 'Основная', **parameters)
        arguments = dict(document_id=second_id, configuration='Основная', expected_revision=prepared['revision'], **parameters)
        built = guarded_inline_submit(gate, runner, store, uuid.uuid4().hex, 'part.create_base_extrusion', arguments,
            lambda op: parts.create_base_extrusion(op, **arguments),
            context={key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')},
            mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        record('plate_in_server_created_document_40_20_10', built)
        if args.fillet_only:
            from verifier_part_fillet import exercise_fillet
            report['fillet_helper_sha256']=hashlib.sha256(Path(__file__).with_name('verifier_part_fillet.py').read_bytes()).hexdigest()
            sketch_id=next(row['object_id'] for row in dimensions.features.list(second_id,'Основная')['items'] if row['feature_type']=='ProfileFeature')
            exercise_fillet(adapter,documents,dimensions,store,runner,gate,second_model,
                dict(document_id=second_id,configuration='Основная',object_id=sketch_id),record,report)
            snap,facts=source_state(sw,module)
            assert [(row,fact) for row,fact in zip(snap[3],facts) if row[0]==first_identity]==original
            report['core_suite_passed']=True
            return
        if not (args.hole_edit_only or args.pattern_only):
            # The shared guard changed: exercise existing dimension and rename
            # paths on this same fixture, without another physical acceptance set.
            for thickness_mm in (12.,10.):
                page = dimensions.list(second_id,'Основная')
                thickness = next(row for row in page['items'] if row['name']=='Толщина')
                arguments = dict(document_id=second_id,configuration='Основная',object_id=thickness['object_id'],
                    expected_revision=page['revision'],value=thickness_mm,unit='mm')
                edited = guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'dimension.set_value',arguments,
                    lambda op:dimensions.set_value(op,**arguments),
                    context={key:arguments[key] for key in ('document_id','configuration','expected_revision')},
                    mutates=True,pass_operation_id=True,verify=lambda value:value['verified'] is True)
                record('guarded_thickness_'+str(int(thickness_mm)),edited)
                bodies = adapter.bodies(second_model,'all')
                assert len(bodies)==1 and math.isclose(bodies[0].GetMassProperties(1.)[3]*1e9,40.*20.*thickness_mm,rel_tol=1e-10)
            features = FeatureCatalog(documents,store,'new-document-native-verifier',mutation_guard=adapter.mutation_guard)
            tree = features.list(second_id,'Основная')
            extrusion = next(row for row in tree['items'] if row['feature_type']=='Extrusion')
            arguments = dict(document_id=second_id,configuration='Основная',object_id=extrusion['object_id'],
                expected_revision=tree['revision'],name='Основание проверки')
            renamed = guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'feature.rename',arguments,
                lambda op:features.rename(op,**arguments),
                context={key:arguments[key] for key in ('document_id','configuration','expected_revision')},
                mutates=True,pass_operation_id=True,verify=lambda value:value['verified'] is True)
            record('guarded_russian_feature_rename',renamed)
        sketches = SketchCatalog(dimensions)
        sketch_id = next(row['object_id'] for row in dimensions.features.list(second_id, 'Основная')['items'] if row['feature_type']=='ProfileFeature')
        cuts = PartHoleCatalog(sketches)
        parameters = dict(document_id=second_id, configuration='Основная', object_id=sketch_id,
                          plane_object_id=plane['object_id'], centre_x_mm=10., centre_y_mm=10., diameter_mm=6.)
        last_preparation = {}
        def cut(*, stale=False):
            prepared = cuts.prepare_through_hole(**parameters)
            last_preparation.update(prepared)
            args = dict(parameters, expected_revision='rev_stale' if stale else prepared['revision'])
            return guarded_inline_submit(gate, runner, store, uuid.uuid4().hex, 'part.create_through_hole', args,
                lambda op: cuts.create_through_hole(op, **args),
                context={key: args[key] for key in ('document_id', 'configuration', 'expected_revision')},
                mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        if not (args.hole_edit_only or args.pattern_only):
            record('hole_stale_prewrite_rejected', cut(stale=True), 'failed')
            # This is the harness's own temporary flag, never a user's command.
            arguments = dict(parameters,expected_revision=last_preparation['revision'])
            sw.CommandInProgress = True
            own_flag = True
            assert sw.CommandInProgress is True
            try:
                busy = guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'part.create_through_hole',arguments,
                    lambda op:cuts.create_through_hole(op,**arguments),
                    context={key:arguments[key] for key in ('document_id','configuration','expected_revision')},
                    mutates=True,pass_operation_id=True,verify=lambda value:value['verified'] is True)
                report['last_job'] = busy
                persist()
                assert busy['status']=='failed' and busy['error']['code']=='application_busy'
            finally:
                assert sw.CommandInProgress is True
                sw.CommandInProgress = False
                assert sw.CommandInProgress is False
                own_flag = False
            record('existing_command_flag_not_borrowed',busy,'failed')
            adapter.inject_cut = True
            failed = cut()
            record('hole_known_failure_scoped_restoration', failed, 'failed')
            assert failed['mutation']['phase'] == 'rolled_back'
            assert len(adapter.features(second_model)) == len(built['result']['after']['semantic']['tree']['features'])
            assert math.isclose(adapter.rectangle_body_measurements(second_model)['volume_mm3'], 8000., rel_tol=1e-10)
        result = cut()
        record('native_circular_through_hole_d6_x10_y10', result)
        assert result['mutation']['phase'] == 'committed'
        native = binding.wrap(adapter.bodies(second_model, 'all')[0], module.IBody2)
        values = native.GetMassProperties(1.)
        assert math.isclose(float(values[3])*1e9, (8000.-math.pi*3.**2*10.), rel_tol=1e-10)
        assert math.isclose(float(values[4])*1e6, (2800.-2.*math.pi*3.**2+2.*math.pi*3.*10.), rel_tol=1e-10)
        assert (native.GetVertexCount(), native.GetEdgeCount(), native.GetFaceCount()) == (8, 14, 7)
        report['volume_after_cut_mm3'] = float(values[3])*1e9
        report['surface_after_cut_mm2'] = float(values[4])*1e6
        edits = PartHoleEditCatalog(sketches)
        circle_id = next(row['object_id'] for row in dimensions.features.list(second_id,'Основная')['items']
            if row['native_id']==result['result']['after']['created']['sketch_native_id'])
        rows = dimensions.list(second_id,'Основная')['items']
        edit_targets = dict(document_id=second_id,configuration='Основная',base_object_id=sketch_id,object_id=circle_id)
        if args.pattern_only:
            from verifier_part_pattern import exercise_pattern
            report['pattern_helper_sha256']=hashlib.sha256(Path(__file__).with_name('verifier_part_pattern.py').read_bytes()).hexdigest()
            exercise_pattern(adapter,documents,dimensions,store,runner,gate,second_model,edit_targets,
                result['result']['after']['created']['cut_native_id'],record,report)
            snap,facts=source_state(sw,module)
            assert [(row,fact) for row,fact in zip(snap[3],facts) if row[0]==first_identity]==original
            report['core_suite_passed']=True
            return
        ids = {row['name']:row['object_id'] for row in rows if row['owner'] and row['owner']['native_id']==result['result']['after']['created']['sketch_native_id']}
        def edit(name,value,*,revision=None):
            arguments = dict(edit_targets,dimension_id=ids[name],value_mm=value)
            if revision is None:
                revision=edits.prepare_dimension_change(**arguments)['revision']
            arguments['expected_revision']=revision
            return guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'part.set_hole_dimension',arguments,
                lambda op:edits.set_dimension(op,**arguments),
                context={key:arguments[key] for key in ('document_id','configuration','expected_revision')},
                mutates=True,pass_operation_id=True,verify=lambda value:value['verified'] is True)
        outside = edit('Диаметр',20.,revision='rev_explicit')
        record('hole_edit_material_prewrite_rejected',outside,'failed')
        assert prewrite_rejection(outside, 'hole_outside_material')
        stale = edit('Центр X',12.,revision='rev_stale')
        record('hole_edit_stale_prewrite_rejected',stale,'failed')
        assert prewrite_rejection(stale, 'stale_revision')
        adapter.inject_edit=True
        rolled=edit('Диаметр',8.)
        record('hole_edit_known_failure_scoped_restoration',rolled,'failed')
        assert rolled['mutation']['phase']=='rolled_back'
        for name,value,label in (('Центр X',12.,'hole_edit_x12'),('Центр Y',11.,'hole_edit_y11'),('Диаметр',8.,'hole_edit_d8')):
            changed=edit(name,value)
            record(label,changed)
            assert changed['mutation']['phase']=='committed'
        native=binding.wrap(adapter.bodies(second_model,'all')[0],module.IBody2)
        values=native.GetMassProperties(1.)
        assert math.isclose(float(values[3])*1e9,8000.-math.pi*4.**2*10.,rel_tol=1e-10)
        assert math.isclose(float(values[4])*1e6,2800.-2.*math.pi*4.**2+2.*math.pi*4.*10.,rel_tol=1e-10)
        assert (native.GetVertexCount(),native.GetEdgeCount(),native.GetFaceCount())==(8,14,7)
        report['hole_edit_volume_mm3']=float(values[3])*1e9
        report['hole_edit_surface_area_mm2']=float(values[4])*1e6
        report['hole_edit_suite_passed']=True
        snap, facts = source_state(sw, module)
        assert [(row, fact) for row, fact in zip(snap[3], facts) if row[0] == first_identity] == original
        report['core_suite_passed'] = True
    except BaseException as exc:
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        persist()
        raise
    finally:
        try:
            if documents is not None: documents.close()
            if store is not None: store.close()
            if sw is not None and gate.can_cleanup():
                if own_flag:
                    assert sw.CommandInProgress is True
                    sw.CommandInProgress = False
                    assert sw.CommandInProgress is False
                    report["owned_fixture_command_flag_released"] = True
                    own_flag = False
                assert sw.CommandInProgress is False
                report['command_flag_baseline_restored'] = True
                current = [binding.wrap(raw, binding.module().IModelDoc2) for raw in sw.GetDocuments() or ()]
                assert len(current) == len(owned) and all(any(item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == identity
                    for _, identity in owned) for item in current)
                for model, identity in reversed(owned):
                    assert not model.GetPathName() and model.GetType() == 1
                    title = model.GetTitle()
                    assert sum(item.GetTitle() == title for item in current) == 1
                    sw.CloseDoc(title)
                    current = [binding.wrap(raw, binding.module().IModelDoc2) for raw in sw.GetDocuments() or ()]
                    assert not any(item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == identity for item in current)
                assert native_snapshot() == baseline
                assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'preferences_after_cleanup')
                report['fixtures_closed'] = True
                report['accepted'] = report.get('core_suite_passed') is True
        except BaseException as exc:
            report['accepted'] = False
            report['cleanup_failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            persist()
            pythoncom.CoUninitialize()
    print(json.dumps({'accepted': report['accepted'], 'report': str(state / 'report.json')}))


if __name__ == '__main__': main()
