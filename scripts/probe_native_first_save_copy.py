"""L3 feasibility only: modern SaveAs3 Copy of an exact owned unsaved part.

No first-save tool is registered or accepted by this probe. Native calls are
one-shot; an unverified outcome retains owned fixtures and private evidence.
Run using the exact installed wheel, with PYTHONPATH unset and an empty session.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

import pythoncom
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.cad_exports_v2 import CadExportsAdapter
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from solidworks_mcp.session import SolidWorksSession
from verify_component_reads import native_identity
from verify_export_operations import (
    activate_owned, application_preferences, assert_owned_source_facts_unchanged,
    owned_source_snapshot,
)
from verify_installed_metadata import installed_identity
from verify_native_document_open import retire_owned, snapshot
from verify_wheel_artifact import validate_wheel
from verifier_dimension_diagnostics import assert_non_stl_preferences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', required=True, type=Path)
    args = parser.parse_args()
    assert args.run_solidworks
    wheel = validate_wheel(args.wheel.resolve(), expected_version=args.expected_version,
                           expected_git_sha=args.expected_git_sha)
    installed_identity(wheel)
    state = args.state_dir.absolute()
    assert state.is_relative_to(Path.cwd() / 'work') and not state.exists()
    state.mkdir()
    report = dict(probe_passed=False, native_first_save_accepted=False,
                  scope='modern_unsaved_part_copy_feasibility_only', wheel=wheel,
                  pending_native=False, owned_documents=[])
    owned = []
    start = time.perf_counter()
    def persist():
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False,
            indent=2, allow_nan=False), encoding='utf-8')
    def record(models):
        report['owned_documents'] = [dict(title=m.GetTitle(), path=m.GetPathName(),
            type=m.GetType()) for m in models]
        persist()
    pythoncom.CoInitialize()
    sw = None
    cip_owned = False
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        assert sw.CommandInProgress is False and sw.UserControl is True
        baseline = snapshot(sw, module)
        preferences = application_preferences(sw)
        original_directory = sw.GetCurrentWorkingDirectory()
        dimension_preference = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
        assert type(dimension_preference) is bool
        sw.CommandInProgress = True
        cip_owned = True
        assert sw.CommandInProgress is True
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, False)
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is False
        session = SolidWorksSession()
        session._sw, session._mod = sw, module
        for name, sizes in (('Деталь первого сохранения', (40, 20, 12)),
                            ('Сосед первого сохранения', (5, 6, 7))):
            session.new_part()
            model = session._model
            owned.append(model)
            record(owned)
            assert model.SetTitle2(name)
            configuration = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
            configuration.Name = 'Основная'
            assert tuple(model.GetConfigurationNames()) == ('Основная',)
            session.add_box(*sizes, name='Основание')
            for i, feature in enumerate(session._iter_features(), 1):
                if feature.GetTypeName2() in ('RefPlane', 'ProfileFeature', '3DProfileFeature'):
                    feature.Name = f'Контрольный элемент {i}'
                    assert feature.Name == f'Контрольный элемент {i}'
            bodies = binding.wrap(model, module.IPartDoc).GetBodies2(-1, False)
            assert len(bodies) == 1
            body = binding.wrap(bodies[0], module.IBody2)
            body.Name = 'Тело основания'
            assert body.Name == 'Тело основания'
            assert model.ForceRebuild3(False)
            model.ClearSelection2(True)
            record(owned)
        source, neighbor = owned
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dimension_preference)
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is dimension_preference
        activate_owned(sw, source, source.GetTitle())
        assert source.GetPathName() == neighbor.GetPathName() == ''
        assert source.GetSaveFlag() is True and neighbor.GetSaveFlag() is True
        adapter = SolidWorksDocuments()
        exports = CadExportsAdapter(adapter)
        source_identity = native_identity(source)
        before = snapshot(sw, module)
        facts = owned_source_snapshot(source, module)
        source_body = binding.wrap(binding.wrap(source, module.IPartDoc).GetBodies2(-1, False)[0], module.IBody2)
        brep = exports._body_fingerprint(source_body)
        assert math.isclose(facts['body_mass_facts'][3] * 1e9, 9600, abs_tol=1e-7)
        stage = state / 'Копия первого сохранения.SLDPRT'
        report.update(source_before=facts, boundary_before=brep,
                      original_directory=original_directory, stage=str(stage))
        assert not stage.exists()
        extension = binding.wrap(source.Extension, module.IModelDocExtension)
        report['pending_native'] = True
        persist()
        raw = extension.SaveAs3(str(stage), 0, 3, None, None, 0, 0)
        report.update(pending_native=False, native_copy_returned=True, native_ack=raw)
        persist()
        assert type(raw) is tuple and len(raw) == 3
        assert type(raw[0]) is bool and type(raw[1]) is int and type(raw[2]) is int
        assert raw == (True, 0, 0)
        assert native_identity(source) == source_identity
        after_facts = owned_source_snapshot(source, module)
        report['source_after'] = after_facts
        report['directory_after_copy'] = sw.GetCurrentWorkingDirectory()
        persist()
        assert_owned_source_facts_unchanged(facts, after_facts)
        assert exports._body_fingerprint(source_body) == brep
        assert snapshot(sw, module) == before
        assert sw.GetCurrentWorkingDirectory() == original_directory
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'after_copy_preferences')
        file_bytes = stage.read_bytes()
        assert file_bytes and len(file_bytes) <= 512 * 1024 * 1024
        stage_hash = hashlib.sha256(file_bytes).hexdigest()
        report.update(source_copy_preserved=True, stage_sha256=stage_hash)
        report['pending_native'] = True
        persist()
        raw_model, errors, warnings = sw.OpenDoc6(str(stage), 1, 1, 'Основная', 0, 0)
        # Only the exact normal native return can acquire ownership.
        report.update(pending_native=False, native_reader_returned=True,
                      reader_errors=errors, reader_warnings=warnings)
        if raw_model is not None:
            reader = binding.wrap(raw_model, module.IModelDoc2)
            assert all(native_identity(reader) != native_identity(m) for m in owned)
            owned.append(reader)
            record(owned)
        assert raw_model is not None and errors == warnings == 0
        assert Path(reader.GetPathName()).resolve() == stage
        reader_facts = owned_source_snapshot(reader, module)
        reader_body = binding.wrap(binding.wrap(reader, module.IPartDoc).GetBodies2(-1, False)[0], module.IBody2)
        report['reader_facts'] = reader_facts
        assert exports._body_fingerprint(reader_body) == brep
        ignored = {'title', 'path', 'stamp', 'save_flag', 'blocking_state'}
        assert {k: v for k, v in reader_facts.items() if k not in ignored | {'body_mass_facts'}} == {
            k: v for k, v in facts.items() if k not in ignored | {'body_mass_facts'}}
        assert math.isclose(reader_facts['body_mass_facts'][3] * 1e9, 9600, abs_tol=1e-7)
        assert reader.GetSaveFlag() is False
        assert hashlib.sha256(stage.read_bytes()).hexdigest() == stage_hash
        # Own reader teardown, restore surviving source without rebuild. The
        # accepted public L2/L1 are not claimed by direct probe calls.
        activate_owned(sw, source, source.GetTitle())
        retire_owned(sw, module, reader, [reader], owned, record)
        actual_directory = sw.GetCurrentWorkingDirectory()
        if actual_directory != original_directory:
            assert Path(actual_directory).resolve() == state
            report['pending_native'] = True
            persist()
            ack = sw.SetCurrentWorkingDirectory(original_directory)
            report.update(pending_native=False, directory_restore_ack=ack)
            persist()
            assert ack is True and sw.GetCurrentWorkingDirectory() == original_directory
        assert snapshot(sw, module) == before
        assert_owned_source_facts_unchanged(facts, owned_source_snapshot(source, module))
        report['reader_roundtrip_verified'] = True
        # Only exact owned terminal fixtures, never user models or CloseAll.
        retire_owned(sw, module, neighbor, [neighbor], owned, record)
        retire_owned(sw, module, source, [source], owned, record)
        assert not owned and not sw.GetDocuments() and sw.ActiveDoc is None
        sw.CommandInProgress = False
        cip_owned = False
        assert sw.CommandInProgress is False
        assert snapshot(sw, module) == baseline
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        report.update(probe_passed=True, own_cleanup_verified=True, baseline_restored=True)
    except BaseException as error:
        report.update(error_type=type(error).__name__, error=str(error))
        # Unknown/failed stages retain all documents. A terminal call permits
        # releasing only the command flag this probe acquired, never retrying.
        if sw is not None and cip_owned and report['pending_native'] is False:
            try:
                assert sw.CommandInProgress is True
                sw.CommandInProgress = False
                assert sw.CommandInProgress is False
                report['owned_command_flag_released'] = True
            except BaseException:
                report['owned_command_flag_released'] = False
    finally:
        report['elapsed_seconds'] = time.perf_counter() - start
        persist()
        pythoncom.CoUninitialize()
    print(json.dumps(dict(probe_passed=report['probe_passed'], scope=report['scope'],
                         error=report.get('error'))))
    raise SystemExit(0 if report['probe_passed'] else 1)


if __name__ == '__main__':
    main()
