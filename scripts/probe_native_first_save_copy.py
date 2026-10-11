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
import traceback
from contextlib import ExitStack

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
    parser.add_argument('--source-oracle-prototype', action='store_true',
        help='Explicit source-only full passive oracle experiment; not installed-wheel acceptance.')
    parser.add_argument('--filesystem-prototype', action='store_true',
        help='Source-only NTFS leases/publication/final writable readback experiment.')
    args = parser.parse_args()
    assert args.run_solidworks
    assert not args.filesystem_prototype or args.source_oracle_prototype
    wheel = validate_wheel(args.wheel.resolve(), expected_version=args.expected_version,
                           expected_git_sha=args.expected_git_sha)
    if args.source_oracle_prototype:
        import solidworks_mcp
        from solidworks_mcp.native_first_save import clone_mapping
        assert Path(solidworks_mcp.__file__).resolve().parent == Path.cwd() / 'src' / 'solidworks_mcp'
        # The integrated source adapter now owns the oracle mixin itself.
        Candidate = SolidWorksDocuments
    else:
        installed_identity(wheel)
        Candidate = SolidWorksDocuments
    state = args.state_dir.absolute()
    assert state.is_relative_to(Path.cwd() / 'work') and not state.exists()
    state.mkdir()
    report = dict(probe_passed=False, native_first_save_accepted=False,
                  scope='modern_unsaved_part_copy_feasibility_only', wheel=wheel,
                  pending_native=False, owned_documents=[],
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if args.source_oracle_prototype:
        report.update(scope='source_passive_first_save_oracle_feasibility_only',
            exact_installed_acceptance=False, source_files={
                str(path.relative_to(Path.cwd())): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted((Path.cwd()/'src'/'solidworks_mcp').glob('*.py'))})
        report['baseline_wheel_reference'] = report.pop('wheel')
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
    filesystem_stack=ExitStack()
    filesystem_lease=filesystem_stage=None
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
            if args.source_oracle_prototype:
                from solidworks_mcp.part_creation import BaseRectangle
                from solidworks_mcp.part_creation import validated_plane_transform
                import uuid
                builder=Candidate()
                features=builder.features(model)
                planes=[feature for feature in features if feature.GetTypeName2()=='RefPlane'
                    and validated_plane_transform(builder.reference_plane_transform(feature))==
                    validated_plane_transform((1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.))]
                assert len(planes)==1
                definition=BaseRectangle.validate(plane_object_id='feat_'+uuid.uuid4().hex,
                    width_mm=sizes[0],height_mm=sizes[1],depth_mm=sizes[2])
                receipt=builder.new_base_receipt(model,features,builder.part_creation_controls(model))
                builder.create_base_rectangle(model,planes[0],definition,receipt)
            else:
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
        adapter = Candidate()
        exports = CadExportsAdapter(adapter)
        source_identity = native_identity(source)
        before = snapshot(sw, module)
        facts = owned_source_snapshot(source, module)
        source_body = binding.wrap(binding.wrap(source, module.IPartDoc).GetBodies2(-1, False)[0], module.IBody2)
        brep = exports._body_fingerprint(source_body)
        assert math.isclose(facts['body_mass_facts'][3] * 1e9, 9600, abs_tol=1e-7)
        stage = state / 'Копия первого сохранения.SLDPRT'
        if args.filesystem_prototype:
            from solidworks_mcp import native_first_save_files as files
            destination=state/'Сохранённая контрольная деталь.SLDPRT'
            token=files.prepare_destination(str(destination))
            report.update(scope='source_copy_ntfs_publication_feasibility_only',destination_token=token)
            persist()
            filesystem_lease=filesystem_stack.enter_context(files.lease_destination(token))
            def stage_checkpoint(checkpoint):
                report['filesystem_stage']=checkpoint;persist()
            filesystem_stage=files.create_owned_stage(filesystem_lease,on_owned_change=stage_checkpoint)
            stage=filesystem_stage.filename
        report.update(source_before=facts, boundary_before=brep,
                      original_directory=original_directory, stage=str(stage))
        if args.source_oracle_prototype:
            report['oracle_phase'] = 'source_before_copy'
            persist()
            source_oracle = adapter.first_save_part_snapshot(source)
            report['source_oracle'] = source_oracle
            neighbor_oracle = adapter.first_save_part_snapshot(neighbor)
            report['neighbor_oracle'] = neighbor_oracle
            assert source_oracle == adapter.first_save_part_snapshot(source)
            assert neighbor_oracle == adapter.first_save_part_snapshot(neighbor)
            assert snapshot(sw,module) == before
            report['complete_passive_source_capture_verified'] = True
            persist()
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
        if args.source_oracle_prototype:
            report['oracle_phase'] = 'source_after_copy'
            persist()
            assert adapter.first_save_part_snapshot(source) == source_oracle
            assert adapter.first_save_part_snapshot(neighbor) == neighbor_oracle
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
        if args.filesystem_prototype:
            report['staged_file']=files.inspect_staged(filesystem_stage)
            filesystem_lease.check();assert filesystem_lease.mode=='strict'
            persist()
        report['pending_native'] = True
        persist()
        raw_model, errors, warnings = sw.OpenDoc6(str(stage), 1,
            3 if args.source_oracle_prototype else 1, 'Основная', 0, 0)
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
        if args.source_oracle_prototype:
            report['oracle_phase'] = 'independent_read_only_clone'
            persist()
            reader_oracle = adapter.first_save_part_snapshot(reader)
            report['reader_oracle'] = reader_oracle
            persist()
            mapping = clone_mapping(source_oracle,reader_oracle)
            assert reader_oracle == adapter.first_save_part_snapshot(reader)
            assert adapter.first_save_part_snapshot(source) == source_oracle
            assert adapter.first_save_part_snapshot(neighbor) == neighbor_oracle
            report.update(reference_mapping=mapping,complete_clone_oracle_verified=True)
            persist()
        assert hashlib.sha256(stage.read_bytes()).hexdigest() == stage_hash
        # Own reader teardown, restore surviving source without rebuild. The
        # accepted public L2/L1 are not claimed by direct probe calls.
        activate_owned(sw, source, source.GetTitle())
        retire_owned(sw, module, reader, [reader], owned, record)
        actual_directory = sw.GetCurrentWorkingDirectory()
        if actual_directory != original_directory:
            assert Path(actual_directory).resolve() == stage.parent
            report['pending_native'] = True
            persist()
            ack = sw.SetCurrentWorkingDirectory(original_directory)
            report.update(pending_native=False, directory_restore_ack=ack)
            persist()
            assert ack is True and sw.GetCurrentWorkingDirectory() == original_directory
        assert snapshot(sw, module) == before
        assert_owned_source_facts_unchanged(facts, owned_source_snapshot(source, module))
        report['reader_roundtrip_verified'] = True
        if args.filesystem_prototype:
            filesystem_lease.check();assert filesystem_lease.mode=='strict'
            report['pending_filesystem_publication']=True;persist()
            publication=files.publish(filesystem_stage,filesystem_lease)
            report['pending_filesystem_publication']=False
            report['publication']=publication;stage_checkpoint(filesystem_stage.checkpoint())
            assert publication['status']=='published' and filesystem_stage.published is True
            assert filesystem_stage.uncertain is False and filesystem_stage.pending_publication is False
            filesystem_lease.check();assert filesystem_lease.mode=='strict'
            report['pending_filesystem_cleanup']=True;persist()
            cleanup=files.cleanup_owned_stage(filesystem_stage,filesystem_lease,verified_terminal=True)
            report['pending_filesystem_cleanup']=False;report['staging_cleanup']=cleanup;persist()
            assert cleanup['destination_removed'] is False
            assert files.observe_owned_stage(filesystem_stage,filesystem_lease)['empty'] is True
            final_file=files.observe_destination(token)
            assert final_file['sha256']==stage_hash
            report['pending_native']=True;persist()
            raw_final,errors,warnings=sw.OpenDoc6(str(destination),1,1,'Основная',0,0)
            report.update(pending_native=False,final_open_returned=True,final_errors=errors,final_warnings=warnings)
            if raw_final is not None:
                final=binding.wrap(raw_final,module.IModelDoc2)
                assert all(native_identity(final)!=native_identity(m) for m in owned)
                owned.append(final);record(owned)
            assert raw_final is not None and errors==warnings==0
            assert Path(final.GetPathName()).resolve()==destination
            assert final.IsOpenedReadOnly() is False and final.GetSaveFlag() is False
            final_oracle=adapter.first_save_part_snapshot(final)
            final_mapping=clone_mapping(source_oracle,final_oracle)
            assert len(final_mapping)==len(mapping)==41
            assert adapter.first_save_part_snapshot(source)==source_oracle
            assert adapter.first_save_part_snapshot(neighbor)==neighbor_oracle
            assert files.observe_destination(token)==final_file
            report.update(final_oracle=final_oracle,final_reference_mapping=final_mapping,
                          final_writable_binding_verified=True)
            persist()
            # Test-owner retirement, not the public replacement domain: retain
            # only returned live handles, never query the retired source.
            retire_owned(sw,module,source,[source],owned,record)
            report['source_retirement_verified']=True;persist()
            retire_owned(sw,module,final,[final],owned,record)
            directory=sw.GetCurrentWorkingDirectory()
            if directory!=original_directory:
                assert Path(directory).resolve()==state
                report['pending_native']=True;persist()
                ack=sw.SetCurrentWorkingDirectory(original_directory)
                report.update(pending_native=False,final_directory_restore_ack=ack);persist()
                assert ack is True and sw.GetCurrentWorkingDirectory()==original_directory
            assert files.observe_destination(token)==final_file
        # Only exact owned terminal fixtures, never user models or CloseAll.
        retire_owned(sw, module, neighbor, [neighbor], owned, record)
        if not args.filesystem_prototype:
            retire_owned(sw, module, source, [source], owned, record)
        assert not owned and not sw.GetDocuments() and sw.ActiveDoc is None
        sw.CommandInProgress = False
        cip_owned = False
        assert sw.CommandInProgress is False
        assert snapshot(sw, module) == baseline
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        report.update(probe_passed=True, own_cleanup_verified=True, baseline_restored=True)
        if args.filesystem_prototype:
            report.update(probe_passed=False,cad_protocol_steps_verified=True)
    except BaseException as error:
        report.update(error_type=type(error).__name__, error=str(error),traceback=traceback.format_exc())
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
        if filesystem_lease is not None and (report['pending_native']
                or report.get('pending_filesystem_publication') or report.get('pending_filesystem_cleanup')
                or filesystem_stage.pending_native_resources is not None):
            filesystem_lease.retain=True
            report['retained_filesystem_process']=True;persist()
            # Preserve the exact live resources. Observation timeouts must
            # never destroy a pending/unknown native publication's handles.
            print('Native/filesystem outcome unconfirmed; retaining this process and evidence.',flush=True)
            while True:time.sleep(.5)
        try:
            filesystem_stack.close()
            if args.filesystem_prototype:
                report['filesystem_lease_released']=True
                if report.get('cad_protocol_steps_verified') is True:
                    report['probe_passed']=True
        except BaseException as error:
            report.update(probe_passed=False,filesystem_release_error=str(error))
            raise
        report['elapsed_seconds'] = time.perf_counter() - start
        persist()
        pythoncom.CoUninitialize()
    print(json.dumps(dict(probe_passed=report['probe_passed'], scope=report['scope'],
                         error=report.get('error'))))
    raise SystemExit(0 if report['probe_passed'] else 1)


if __name__ == '__main__':
    main()
