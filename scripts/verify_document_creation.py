"""Installed internal new-document + plate chain, exclusively on owned parts."""

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
from solidworks_mcp.part_creation import PartCreationCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences
from verify_mass_properties import source_state
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_wheel_artifact import validate_wheel
from verifier_fixture_cleanup import InlineFixtureCleanupGate, guarded_inline_submit
from verify_part_construction import Worker


class Adapter(SolidWorksDocuments):
    inject_after_creation = False

    def create_empty_part_document(self, *args):
        super().create_empty_part_document(*args)
        if self.inject_after_creation:
            self.inject_after_creation = False
            raise RuntimeError('Known verifier failure after retaining exact native new document.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
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
    report = {'accepted': False, 'scope': 'internal_new_part_and_plate_native_v1', 'wheel': wheel,
              'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases': [], 'owned_documents': [], 'public_mcp_creation_accepted': False}
    def persist():
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    gate, owned = InlineFixtureCleanupGate(), []
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
            assert sw.CommandInProgress is False
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
        record('stale_creation_prewrite_rejected', create('Проверка устаревшей ревизии ' + suffix, stale=True), 'failed')
        first = create('Контрольная исходная деталь ' + suffix)
        record('new_part_from_empty_session', first)
        first_id = first['result']['after']['created_document_id']
        first_model = owned[0][0]
        plane = next(item for item in adapter.features(first_model) if item.GetTypeName2() == 'RefPlane')
        assert plane.Select2(False, 7)
        source_before = source_state(sw, module)
        adapter.inject_after_creation = True
        failed = create('Контрольная отменяемая деталь ' + suffix)
        record('known_new_document_failure_scoped_close', failed, 'failed')
        assert failed['mutation']['phase'] == 'rolled_back'
        assert source_state(sw, module) == source_before, 'Existing document/view/selection changed after scoped closure.'
        second = create('Контрольная новая пластина ' + suffix)
        record('new_part_preserves_existing_document', second)
        second_id, second_model = second['result']['after']['created_document_id'], owned[1][0]
        snap, facts = source_state(sw, module)
        first_identity = owned[0][1]
        actual = [(row, fact) for row, fact in zip(snap[3], facts) if row[0] == first_identity]
        original = [(row, fact) for row, fact in zip(source_before[0][3], source_before[1]) if row[0] == first_identity]
        assert actual == original, 'Existing exact model metadata/geometry/selection/view changed.'
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
        listed = dimensions.list(second_id, 'Основная')
        thickness = next(row for row in listed['items'] if row['name'] == 'Толщина')
        arguments = dict(document_id=second_id, configuration='Основная', expected_revision=listed['revision'],
            object_id=thickness['object_id'], value=12., unit='mm')
        edited = guarded_inline_submit(gate, runner, store, uuid.uuid4().hex, 'dimension.set_value', arguments,
            lambda op: dimensions.set_value(op, **arguments),
            context={key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')},
            mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        record('thickness_edit_12', edited)
        bodies = adapter.bodies(second_model, 'all')
        volume = float(bodies[0].GetMassProperties(1.)[3]) * 1e9
        assert len(bodies) == 1 and math.isclose(volume, 9600., rel_tol=1e-7)
        report['volume_after_edit_mm3'] = volume
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
                assert sw.CommandInProgress is False
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
