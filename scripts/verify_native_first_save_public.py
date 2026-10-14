"""Public L3-P1 native file roundtrip/edit/Save3; requires same-wheel internal gates.

Own fixture setup uses the established rectangular-base builder. Unknown/live
effects retain this process and every exact receipt; no COM cancellation,
inverse activation, roster-delta cleanup or automatic retry.
"""

import argparse
import ast
import asyncio
from contextlib import asynccontextmanager
import os
import math
import sys
import hashlib
import json
from pathlib import Path
import time
import traceback
import uuid

import pythoncom
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from verify_dimension_mcp import SessionCleanupGate, call, require_native_cleanup, succeeded
from verifier_lifecycle import ToolSpec, open_supervised_session
from verifier_native_part_activation import verified_committed_part_activation
from verifier_native_part_activation_acceptance import validate_internal_activation
from verifier_first_save_internal_acceptance import validate_internal_cases
from verifier_first_save_public_contract import SPECS, fixture_depth_dimension
from verifier_native_first_save import verified_committed_first_save
from verify_installed_metadata import TOOLS
from solidworks_mcp.native_document_save import native_file_facts

from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.native_first_save import validated_part_snapshot, clone_mapping
from solidworks_mcp.native_part_activation import NativePartActivationCatalog, SCOPE
from solidworks_mcp.part_creation import BaseRectangle, validated_plane_transform
from solidworks_mcp.session import SolidWorksSession
from probe_native_first_save_domain import package_evidence
from verify_bounds_measurements import InlineSta
from verify_component_reads import native_identity
from verify_export_operations import activate_owned, application_preferences
from verify_native_document_open import retire_owned, snapshot
from verify_native_first_save_rejections import owned_document_rows
from verifier_dimension_diagnostics import assert_non_stl_preferences


HELPERS = ('verify_native_first_save_public.py', 'verifier_first_save_internal_acceptance.py',
           'verifier_first_save_public_contract.py', 'verifier_native_first_save.py', 'verifier_native_part_activation.py',
           'verifier_native_part_activation_acceptance.py', 'verifier_lifecycle.py', 'verifier_native_open.py',
           'verify_dimension_mcp.py', 'verify_native_part_activation_positive.py', 'verify_native_part_activation_cases.py', 'probe_native_first_save_domain.py',
           'verify_installed_metadata.py', 'verify_wheel_artifact.py',
           'verify_bounds_measurements.py', 'verify_component_reads.py',
           'verify_export_operations.py', 'verify_native_document_open.py',
           'verify_native_first_save_rejections.py', 'verifier_dimension_diagnostics.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    for case in ('positive', 'already_active', 'stale', 'controlled_after_call'):
        parser.add_argument('--internal-' + case.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--first-save-internal-manifest', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    args = parser.parse_args()
    assert args.run_solidworks
    state = args.state_dir.resolve()
    assert state.is_relative_to(Path.cwd() / 'work') and not state.exists()
    state.mkdir()
    args.state_dir = state
    started = time.perf_counter()
    report = dict(scope='installed_first_save_public_chain', accepted=False,
                  public_first_save_passed=False, cases=[], captures=[], owned_documents=[],
                  native_calls_live=False, phase='preflight',
                  verifier_hashes={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in HELPERS})

    def persist():
        report['elapsed_seconds'] = time.perf_counter() - started
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')

    def record(models):
        report['owned_documents'] = owned_document_rows(models)
        persist()

    # Wheel/origin/metadata are checked before the first native connection.
    try:
        report.update(package_evidence(args, installed=True))
        reports, trusted = {}, {}
        for case in ('positive', 'already_active', 'stale', 'controlled_after_call'):
            path = getattr(args, 'internal_' + case).resolve()
            assert path.is_relative_to(Path.cwd() / 'work')
            reports[case] = json.loads(path.read_text(encoding='utf-8'))
            driver = ('verify_native_part_activation_positive.py' if case == 'positive'
                      else 'verify_native_part_activation_cases.py')
            tree = ast.parse(Path(__file__).with_name(driver).read_text(encoding='utf-8'))
            names = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'HELPERS' for target in node.targets)))
            trusted[case] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                             for name in names}
        report['internal_preflight'] = validate_internal_activation(reports, report['wheel'], trusted)
        manifest_path = args.first_save_internal_manifest.resolve()
        assert manifest_path.is_relative_to(Path.cwd() / 'work')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        reports, trusted = {}, {}
        drivers = {'positive': 'probe_native_first_save_domain.py',
                   'rejections': 'verify_native_first_save_rejections.py',
                   'race': 'verify_native_first_save_race.py',
                   **{mode+'_after_copy': 'verify_native_first_save_fault.py'
                      for mode in ('false','warning','throw','incomplete')}}
        assert type(manifest) is dict and set(manifest) == set(drivers)
        for case, driver in drivers.items():
            path = Path(manifest[case]).resolve()
            assert path.is_relative_to(Path.cwd() / 'work')
            reports[case] = json.loads(path.read_text(encoding='utf-8'))
            tree = ast.parse(Path(__file__).with_name(driver).read_text(encoding='utf-8'))
            inventories = [kw.value for node in ast.walk(tree) if isinstance(node,ast.Call)
                           for kw in node.keywords if kw.arg == 'verifier_hashes']
            assert len(inventories) == 1 and isinstance(inventories[0],ast.DictComp)
            names = ast.literal_eval(inventories[0].generators[0].iter)
            trusted[case] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                             for name in names}
        validate_internal_cases(reports, report['wheel'], trusted, expected_public_tool_count=len(TOOLS))
        report['first_save_internal_preflight'] = dict(passed=True, report_count=7,
                                                     public_tool_count=len(TOOLS))
    except BaseException as error:
        report.update(phase='preflight_failed', error=str(error), traceback=traceback.format_exc())
        persist()
        raise

    class ObservedDocuments(SolidWorksDocuments):
        activations = 0

        def activate_native_open_document(self, receipt):
            self.activations += 1
            report['native_calls_live'] = True
            persist()
            try:
                return super().activate_native_open_document(receipt)
            finally:
                if receipt.native_call_returned is True and receipt.pending_activation is False:
                    report['native_calls_live'] = False
                    persist()

        def first_save_part_snapshot(self, model):
            row = dict(title=model.GetTitle(), started_s=time.perf_counter()-started, status='running')
            report['captures'].append(row)
            persist()
            try:
                result = super().first_save_part_snapshot(model)
                row.update(status='returned', elapsed_s=time.perf_counter()-started-row['started_s'])
                return result
            except BaseException as error:
                row.update(status='failed', error=str(error))
                raise
            finally:
                persist()

    owned = []
    store = domain = adapter = None
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        assert sw.CommandInProgress is False and sw.UserControl is True
        adapter = ObservedDocuments()
        original = snapshot(sw, module)
        original_application = adapter.native_close_application_context()
        preferences = application_preferences(sw)
        report.update(original_baseline=original, original_application=original_application,
                      original_preferences=preferences, phase='owned_fixture_creation')
        dimension_preference = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
        assert type(dimension_preference) is bool
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, False)
        session = SolidWorksSession()
        session._sw, session._mod = sw, module
        for name, sizes in (('Контрольная пластина активации', (40., 20., 12.)),
                            ('Рабочий сосед активации', (5., 6., 7.))):
            report['native_calls_live'] = True
            persist()
            created = session.new_part()
            model = session._model
            owned.append(model)
            assert type(created) is dict and created['ok'] is True and type(created['title']) is str
            report.setdefault('normal_creation_returns', []).append(created)
            report['native_calls_live'] = False
            record(owned)
            assert model.SetTitle2(name) and model.GetTitle() == name
            configuration = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
            configuration.Name = 'Основная'
            assert tuple(model.GetConfigurationNames()) == ('Основная',)
            features = adapter.features(model)
            frame = validated_plane_transform((1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.))
            planes = [f for f in features if f.GetTypeName2() == 'RefPlane'
                      and validated_plane_transform(adapter.reference_plane_transform(f)) == frame]
            assert len(planes) == 1
            definition = BaseRectangle.validate(plane_object_id='feat_'+uuid.uuid4().hex,
                                                width_mm=sizes[0], height_mm=sizes[1], depth_mm=sizes[2])
            receipt = adapter.new_base_receipt(model, features, adapter.part_creation_controls(model))
            report['native_calls_live'] = True
            persist()
            adapter.create_base_rectangle(model, planes[0], definition, receipt)
            report['native_calls_live'] = False
            record(owned)
            for index, feature in enumerate(session._iter_features(), 1):
                if feature.GetTypeName2() in ('RefPlane', 'ProfileFeature'):
                    feature.Name = f'Контрольный элемент {index}'
                    assert feature.Name == f'Контрольный элемент {index}'
            body_values = binding.wrap(model, module.IPartDoc).GetBodies2(-1, False)
            assert len(body_values) == 1
            body = binding.wrap(body_values[0], module.IBody2)
            body.Name = 'Тело основания'
            assert body.Name == 'Тело основания' and model.ForceRebuild3(False)
            model.ClearSelection2(True)
        target, neighbor = owned
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dimension_preference)
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is dimension_preference
        activate_owned(sw, neighbor, neighbor.GetTitle())
        target_identity, neighbor_identity = native_identity(target), native_identity(neighbor)
        before = [validated_part_snapshot(adapter.first_save_part_snapshot(model)) for model in owned]
        report['independent_before'] = before
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        gate = SessionCleanupGate()
        target_title = target.GetTitle()
        specs = SPECS
        filename = str(state / 'Сохранённая контрольная пластина.SLDPRT')
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'solidworks_mcp.server_v2', '--state-dir', str(state / 'server')],
            env={**os.environ, 'PYTHONPATH': '', 'PYTHONNOUSERSITE': '1'})

        @asynccontextmanager
        async def factory():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as raw:
                    await raw.initialize()
                    yield raw

        async def exercise():
            async with open_supervised_session(factory, tool_specs=specs,
                    journal_path=state / 'server/jobs.sqlite',
                    on_hold=lambda decision: report.update(lifecycle_hold=True)) as client:
                gate.add(client)
                async def invoke(tool, **arguments):
                    report['native_calls_live'] = True
                    persist()
                    result = await call(client, tool, **arguments, timeout_s=0.)
                    await require_native_cleanup(client, gate)
                    report['native_calls_live'] = False
                    persist()
                    return result

                listed = succeeded(await invoke('document_list', request_id='list'))
                matching = [row for row in listed['documents'] if row['title'] == target_title]
                assert len(matching) == 1 and matching[0]['path'] == ''
                source_id = matching[0]['document_id']
                neighbor_rows = [row for row in listed['documents'] if row['document_id'] != source_id]
                assert len(neighbor_rows) == 1
                neighbor_id = neighbor_rows[0]['document_id']
                # Establish the source through public explicit ACT before
                # first save; all edits after open use the same ACT contract.
                p = succeeded(await invoke('document_prepare_activate_part_native', request_id='initial-act-prepare',
                                           document_id=source_id, configuration='Основная'))
                succeeded(await invoke('document_activate_part_native', request_id='initial-act',
                    document_id=source_id, configuration='Основная', expected_revision=p['revision']))
                args = dict(document_id=source_id, configuration='Основная', filename=filename)
                report['phase'] = 'public_first_save'
                p = succeeded(await invoke('document_prepare_first_save_native', request_id='first-prepare', **args))
                args['expected_revision'] = p['revision']
                saved = await invoke('document_first_save_native', request_id='first-save', **args)
                assert saved['status'] == 'succeeded'
                job = (await client.call_tool('job_get', {'operation_id': saved['operation_id']})).structuredContent['data']
                assert verified_committed_first_save(job)
                report['first_save_job'] = job
                value = saved['data']['value']
                assert value['retired_document_ids'] == [source_id]
                final_id = value['document_id']
                assert final_id != source_id and value['source_references_retired'] is True
                assert await invoke('document_first_save_native', request_id='first-save', **args) == saved

                def bind_saved(retiring):
                    # Only the declared exact filename after a verified terminal
                    # native receipt can provide an owned replacement handle.
                    model = binding.wrap(sw.GetOpenDocumentByName(filename), module.IModelDoc2)
                    assert model is not None and model.GetType() == 1
                    assert Path(model.GetPathName()).resolve() == Path(filename)
                    if retiring is not None:
                        live = [native_identity(binding.wrap(raw,module.IModelDoc2)) for raw in sw.GetDocuments() or ()]
                        assert not any(token == target_identity for token in live)
                        owned[:] = [item for item in owned if item is not retiring]
                    owned.insert(0,model)
                    record(owned)
                    return model

                final = bind_saved(target)
                sw.CommandInProgress = True
                assert sw.CommandInProgress is True
                clone_mapping(before[0], validated_part_snapshot(adapter.first_save_part_snapshot(final)))
                assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == before[1]
                sw.CommandInProgress = False
                assert sw.CommandInProgress is False
                assert native_file_facts(filename,'part') == value['file']
                report['cases'].append(dict(label='public-first-save-replacement-and-replay',passed=True))

                async def close_current(document_id, model, tag):
                    close_args = dict(document_id=document_id,configuration='Основная',
                                      active_after_document_id=neighbor_id,allowed_hidden_document_ids=[])
                    p = succeeded(await invoke('document_prepare_close_native',request_id=tag+'-prepare',**close_args))
                    succeeded(await invoke('document_close_native',request_id=tag,
                        expected_revision=p['revision'],**close_args))
                    owned[:] = [item for item in owned if item is not model]
                    record(owned)

                async def open_current(read_only,tag):
                    p = succeeded(await invoke('document_prepare_open_native',request_id=tag+'-prepare',
                        filename=filename,document_type='part',configuration='Основная',read_only=read_only))
                    result = succeeded(await invoke('document_open_native',request_id=tag,
                        document_id=p['application_id'],configuration='Основная',expected_revision=p['revision'],
                        native_file_id=p['native_file_id'],read_only=read_only))
                    return result['value']['source_document_id'], bind_saved(None)

                await close_current(final_id,final,'first-close')
                final_id, final = await open_current(False,'writable-open')
                report['phase'] = 'public_open_activate_edit'
                p = succeeded(await invoke('document_prepare_activate_part_native',request_id='act-prepare',
                    document_id=final_id,configuration='Основная'))
                succeeded(await invoke('document_activate_part_native',request_id='act',document_id=final_id,
                    configuration='Основная',expected_revision=p['revision']))
                rows = succeeded(await invoke('dimension_list',request_id='depth-list',
                    document_id=final_id,configuration='Основная'))
                depth = fixture_depth_dimension(rows,'Основная',12.)
                read = succeeded(await invoke('dimension_get',request_id='depth-read',
                    document_id=final_id,configuration='Основная',object_id=depth['object_id']))
                succeeded(await invoke('dimension_set_value',request_id='depth-edit',document_id=final_id,
                    configuration='Основная',object_id=depth['object_id'],expected_revision=read['revision'],value=14.,unit='mm'))
                p = succeeded(await invoke('document_prepare_save_native',request_id='save-prepare',
                    document_id=final_id,configuration='Основная'))
                succeeded(await invoke('document_save_native',request_id='save',document_id=final_id,
                    configuration='Основная',expected_revision=p['revision']))
                sw.CommandInProgress = True
                assert sw.CommandInProgress is True
                after_edit = validated_part_snapshot(adapter.first_save_part_snapshot(final))
                assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == before[1]
                bodies = binding.wrap(final,module.IPartDoc).GetBodies2(-1,False)
                assert len(bodies) == 1
                volume = binding.wrap(bodies[0],module.IBody2).GetMassProperties(1.)[3] * 1e9
                assert math.isclose(volume,11200.,rel_tol=1e-9,abs_tol=1e-5)
                sw.CommandInProgress = False
                assert sw.CommandInProgress is False
                report['cases'].append(dict(label='public-reopen-activate-edit-save3',passed=True,volume_mm3=volume))
                report['phase'] = 'independent_disk_readback'
                await close_current(final_id,final,'edited-close')
                final_id, final = await open_current(True,'readonly-disk-open')
                sw.CommandInProgress = True
                assert sw.CommandInProgress is True
                clone_mapping(after_edit,validated_part_snapshot(adapter.first_save_part_snapshot(final)))
                assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == before[1]
                sw.CommandInProgress = False
                assert sw.CommandInProgress is False
                p = succeeded(await invoke('document_prepare_close_native',request_id='readonly-close-prepare',
                    document_id=final_id,configuration='Основная',active_after_document_id='',allowed_hidden_document_ids=[]))
                succeeded(await invoke('document_close_native',request_id='readonly-close',document_id=final_id,
                    configuration='Основная',expected_revision=p['revision'],active_after_document_id='',allowed_hidden_document_ids=[]))
                owned[:] = [item for item in owned if item is not final]
                record(owned)
                report['independent_native_readback_verified'] = True
                report['cases'].append(dict(label='public-independent-saved-file-readback',passed=True))
                await require_native_cleanup(client,gate)
                persist()
            assert gate.can_cleanup()
        asyncio.run(exercise())
        assert gate.can_cleanup() and report['native_calls_live'] is False
        assert report['independent_native_readback_verified'] is True
        assert owned == [neighbor] and report['native_calls_live'] is False
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        report['phase'] = 'owned_cleanup'
        assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == before[1]
        retire_owned(sw,module,neighbor,[neighbor],owned,record)
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        restored = snapshot(sw, module)
        assert restored == original
        assert adapter.native_close_application_context() == original_application
        report['restored_application'] = adapter.native_close_application_context()
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        report.update(phase='terminal', public_first_save_passed=True, accepted=True, baseline_restored=True,
                      own_cleanup_verified=True, restored_baseline=restored, native_calls_live=False)
        report['cases'].append(dict(label='public-owned-cleanup-baseline', passed=True))
        persist()
        report['supervised_cleanup_verified'] = gate.can_cleanup()
    except BaseException as error:
        report.update(phase='failed', error=str(error), traceback=traceback.format_exc())
        persist()
        if owned or report['native_calls_live'] is not False:
            report['retained_process'] = True
            persist()
            while True:
                time.sleep(.5)
        raise
    finally:
        persist()
        pythoncom.CoUninitialize()
    print(json.dumps(dict(scope=report['scope'], public_first_save_passed=True,
                         elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
