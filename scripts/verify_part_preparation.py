"""Installed internal preparation on owned empty parts; no extrusion is created.

This proves native plane reads and rejection of incompatible input only. It is
not acceptance of part creation, public MCP availability, or a project stage.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sysconfig
import uuid

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import SW_PREF_DEFAULT_TEMPLATE_PART
from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobStore
from solidworks_mcp.part_creation import PartCreationCatalog
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences, activate_owned
from verify_mass_properties import source_state, confirm_source
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_wheel_artifact import validate_wheel


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
    report = {'accepted': False, 'scope': 'internal_empty_part_preparation_native_v1',
              'wheel': wheel, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases': [], 'owned_documents': [], 'part_creation_accepted': False,
              'public_mcp_creation_accepted': False}
    def persist():
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    owned, adapter, documents, store = [], None, None, None
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
        adapter = SolidWorksDocuments()
        documents = DocumentCatalog(adapter)
        store = JobStore(state / 'jobs.sqlite')
        dimensions = DimensionCatalog(documents, store, 'part-preparation-verifier', mutation_guard=adapter.mutation_guard)
        catalog = PartCreationCatalog(dimensions)
        ids = [next(row['document_id'] for row in documents.list()['documents']
                    if row['title'] == model.GetTitle()) for model, _ in owned]
        planes = [row for row in dimensions.features.list(ids[0], 'Основная')['items']
                  if row['feature_type'] == 'RefPlane' and row['object_id']]
        assert len(planes) == 3, 'This first fixture requires three referenceable principal planes.'
        other_plane = next(row['object_id'] for row in dimensions.features.list(ids[1], 'Основная')['items']
                           if row['feature_type'] == 'RefPlane' and row['object_id'])
        def case(label, parameters, error=None):
            before = source_state(sw, module)
            before_preferences = application_preferences(sw)
            try:
                result = catalog.prepare_base_extrusion(ids[0], 'Основная', **parameters)
            except ExecutionFailure as exc:
                assert error == exc.code and exc.uncertain is False, (label, exc.code)
                result = {'expected_error': exc.code}
            else:
                assert error is None and result['native_creation_available'] is False
                assert result['expected_geometry']['volume_mm3'] == parameters['width_mm'] * parameters['height_mm'] * parameters['depth_mm']
            confirm_source(before, source_state(sw, module))
            assert_non_stl_preferences(before_preferences, application_preferences(sw))
            report['cases'].append({'label': label, 'passed': True, 'result': result})
            persist()
        parameters = dict(plane_object_id=planes[0]['object_id'], width_mm=40., height_mm=20., depth_mm=10.)
        for index, plane in enumerate(planes):
            case(f'principal_plane_{index + 1}', {**parameters, 'plane_object_id': plane['object_id']})
        case('planned_thickness_12', {**parameters, 'depth_mm': 12.})
        case('foreign_plane', {**parameters, 'plane_object_id': other_plane}, 'object_reference_not_found')
        case('invalid_length', {**parameters, 'width_mm': True}, 'invalid_part_length')
        case('english_feature_name', {**parameters, 'feature_name': 'Base'}, 'invalid_russian_name')
        case('plane_name_instead_of_reference', {**parameters, 'plane_object_id': planes[0]['name']}, 'invalid_plane_reference')
        report['core_suite_passed'] = True
    except BaseException as exc:
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        persist()
        raise
    finally:
        try:
            if documents is not None: documents.close()
            if store is not None: store.close()
            if sw is not None and owns_guard and not creation_pending:
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
                assert_non_stl_preferences(preferences, application_preferences(sw))
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
