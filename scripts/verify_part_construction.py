"""Installed internal plate construction and thickness edit on owned parts.

This proves only the bounded engineering chain exercised by the report, not
public MCP availability or completion of a project stage. No user file is saved.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sysconfig
import uuid
from concurrent.futures import Future
import math

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import SW_PREF_DEFAULT_TEMPLATE_PART
from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.part_creation import PartCreationCatalog
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences, activate_owned
from verify_mass_properties import source_state, confirm_source
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_wheel_artifact import validate_wheel
from verifier_fixture_cleanup import InlineFixtureCleanupGate, guarded_inline_submit


class Worker:
    def submit(self, function):
        future = Future()
        try: future.set_result(function())
        except BaseException as exc: future.set_exception(exc)
        return future


class Adapter(SolidWorksDocuments):
    def __init__(self):
        super().__init__()
        self.inject_after_creation = False

    def create_base_rectangle(self, *args):
        super().create_base_rectangle(*args)
        if self.inject_after_creation:
            self.inject_after_creation = False
            raise RuntimeError('Verifier injection after exact native construction; not a COM fault.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.run_solidworks:
        parser.error('Native checks require explicit --run-solidworks; no connection attempted.')
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
    report = {'accepted': False, 'scope': 'internal_parametric_plate_construction_native_v1',
              'wheel': wheel, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases': [], 'owned_documents': [], 'part_creation_accepted': False,
              'public_mcp_creation_accepted': False}
    def persist():
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    owned, adapter, documents, store = [], None, None, None
    gate = InlineFixtureCleanupGate()
    sw, owns_guard, creation_pending = None, False, False
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and not sw.CommandInProgress, 'Requires empty/free baseline; no documents closed.'
        baseline = native_snapshot()
        preferences = application_preferences(sw)
        report['baseline'] = {'empty_session': True, 'command_in_progress': False, 'preferences': preferences}
        template = sw.GetUserPreferenceStringValue(SW_PREF_DEFAULT_TEMPLATE_PART)
        assert template and Path(template).is_file(), 'A configured existing part template is required; no fallback creation.'
        report['pending_guard_acquisition'] = True
        persist()
        sw.CommandInProgress = True
        assert sw.CommandInProgress, 'Guard acquisition unconfirmed; no repeat.'
        owns_guard = True
        report['pending_guard_acquisition'] = False
        for index in range(2):
            report['pending_document_creation'] = True
            creation_pending = True
            persist()
            raw = sw.NewDocument(template, 0, 0, 0)  # Exactly once; never replay an unknown outcome.
            assert raw is not None, 'Native document creation returned no owned handle.'
            model = binding.wrap(raw, module.IModelDoc2)
            identity = model._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
            owned.append((model, identity))
            creation_pending = False
            report['pending_document_creation'] = False
            assert model.SetTitle2(f'Контрольная пластина {index + 1} ' + uuid.uuid4().hex[:8])
            config = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
            config.Name = 'Основная'
            assert config.Name == 'Основная'
            report['owned_documents'] = [{'title': item.GetTitle(), 'path': item.GetPathName(),
                                         'type': item.GetType()} for item, _ in owned]
            persist()
        first, other = (row[0] for row in owned)
        activate_owned(sw, first, first.GetTitle())
        adapter = Adapter()
        documents = DocumentCatalog(adapter)
        store = JobStore(state / 'jobs.sqlite')
        dimensions = DimensionCatalog(documents, store, 'part-preparation-verifier', mutation_guard=adapter.mutation_guard)
        catalog = PartCreationCatalog(dimensions)
        ids = [next(row['document_id'] for row in documents.list()['documents']
                    if row['title'] == model.GetTitle()) for model, _ in owned]
        planes = [row for row in dimensions.features.list(ids[0], 'Основная')['items']
                  if row['feature_type'] == 'RefPlane' and row['object_id']]
        assert len(planes) == 3, 'This first fixture requires three referenceable principal planes.'
        runner = JobRunner(store, Worker())
        other_identity = other._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
        def other_state():
            snapshot, facts = source_state(sw, module)
            matches = [(row, fact) for row, fact in zip(snapshot[3], facts) if row[0] == other_identity]
            assert len(matches) == 1
            return matches[0]
        other_baseline = other_state()
        def check_other():
            assert other_state() == other_baseline
        def record(label, job):
            report['last_job'] = job
            persist()  # Retain journal outcome before any independent CAD check.
            assert gate.can_cleanup(), 'Unknown outcome prohibits further CAD checks or automatic replay.'
            check_other()
            assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'preferences_' + label)
            report['cases'].append({'label': label, 'passed': True, 'job': job})
            persist()
        parameters = dict(plane_object_id=planes[0]['object_id'], width_mm=40., height_mm=20., depth_mm=10.)
        # Fixture-only selection establishes a nonempty, marked original list.
        entry, identity, objects, *_ = dimensions.features._state(ids[0], 'Основная')
        selected_plane, _ = dimensions.features._resolve(entry, 'Основная', identity, objects, planes[1]['object_id'])
        assert selected_plane.Select2(False, 7)
        selection = binding.wrap(first.SelectionManager, module.ISelectionMgr)
        original_selection = adapter._mass_selection_snapshot(selection)
        assert len(original_selection) == 1 and original_selection[0][1] == 7
        def check_selection(label):
            current = adapter._mass_selection_snapshot(binding.wrap(first.SelectionManager, module.ISelectionMgr))
            report['selection_' + label] = {'count': len(current), 'marks': [mark for _, mark in current],
                                            'exactly_restored': current == original_selection}
            persist()
            assert current == original_selection, 'Original selection identities/marks changed.'
        def create(request):
            prepared = catalog.prepare_base_extrusion(ids[0], 'Основная', **parameters)
            arguments = dict(document_id=ids[0], configuration='Основная', expected_revision=prepared['revision'], **parameters)
            return guarded_inline_submit(gate, runner, store, request, 'part.create_base_extrusion', arguments,
                lambda op: catalog.create_base_extrusion(op, **arguments),
                context={key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')},
                mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        adapter.inject_after_creation = True
        rollback = create('plate-known-rollback-' + uuid.uuid4().hex)
        report['last_job'] = rollback
        persist()
        assert rollback['status'] == 'failed' and rollback['mutation']['phase'] == 'rolled_back', rollback.get('error')
        record('known_creation_failure_scoped_rollback', rollback)
        check_selection('after_rollback')
        result = create('plate-create-' + uuid.uuid4().hex)
        report['last_job'] = result
        persist()
        assert result['status'] == 'succeeded' and result['mutation']['phase'] == 'committed', result.get('error')
        record('parametric_plate_40_20_10', result)
        check_selection('after_creation')
        page = dimensions.list(ids[0], 'Основная')
        thickness = next(row for row in page['items'] if row['name'] == 'Толщина')
        assert thickness['object_id'] and thickness['write_blockers'] == []
        arguments = dict(document_id=ids[0], configuration='Основная', object_id=thickness['object_id'],
                         expected_revision=page['revision'], value=12., unit='mm')
        edited = guarded_inline_submit(gate, runner, store, 'plate-thickness-' + uuid.uuid4().hex,
            'dimension.set_value', arguments, lambda op: dimensions.set_value(op, **arguments),
            context={key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')},
            mutates=True, pass_operation_id=True, verify=lambda value: value['verified'] is True)
        report['last_job'] = edited
        persist()
        assert edited['status'] == 'succeeded' and edited['mutation']['phase'] == 'committed', edited.get('error')
        record('thickness_edit_12', edited)
        check_selection('after_thickness_edit')
        bodies = adapter.bodies(first, 'all')
        assert len(bodies) == 1 and math.isclose(float(bodies[0].GetMassProperties(1.)[3]) * 1e9, 9600., rel_tol=1e-7)
        report['plate_volume_after_edit_mm3'] = float(bodies[0].GetMassProperties(1.)[3]) * 1e9
        report['part_creation_accepted'] = True
        report['core_suite_passed'] = True
    except BaseException as exc:
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        persist()
        raise
    finally:
        try:
            if documents is not None: documents.close()
            if store is not None: store.close()
            if sw is not None and owns_guard and not creation_pending and gate.can_cleanup():
                # Standing authorization: terminal read calls, exact own handles,
                # and an initially empty session. Never close a new/foreign model.
                current = [binding.wrap(raw, binding.module().IModelDoc2) for raw in sw.GetDocuments() or ()]
                tokens = [item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) for item in current]
                assert len(current) == len(owned) and all(any(token == identity for _, identity in owned) for token in tokens)
                for model, identity in reversed(owned):
                    assert model._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == identity
                    assert not model.GetPathName() and model.GetType() == 1
                    title = model.GetTitle()
                    assert sum(item.GetTitle() == title for item in current) == 1
                    sw.CloseDoc(title)
                    current = [binding.wrap(raw, binding.module().IModelDoc2) for raw in sw.GetDocuments() or ()]
                    assert not any(item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == identity for item in current)
                assert native_snapshot() == baseline
                assert_non_stl_preferences(lambda: application_preferences(sw), preferences,
                                           report, 'preferences_after_cleanup')
                report['fixtures_closed'] = True
        except BaseException as exc:
            report['cleanup_failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            report['accepted'] = False
            persist()
            raise
        finally:
            try:
                if sw is not None and owns_guard and not creation_pending:
                    # This process has completed its own native calls. Release
                    # only its acknowledged flag even if another check failed.
                    sw.CommandInProgress = False
                    assert not sw.CommandInProgress
                    owns_guard = False
                    report['guard_released'] = True
                report['accepted'] = (report.get('core_suite_passed') is True
                    and report.get('fixtures_closed') is True and report.get('guard_released') is True
                    and 'cleanup_failure' not in report)
                persist()
            finally:
                pythoncom.CoUninitialize()
    print(json.dumps({'accepted': report['accepted'], 'cases': len(report['cases']), 'report': str(state / 'report.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
