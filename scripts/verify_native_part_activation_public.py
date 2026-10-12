"""Public installed ACT chain; dispatch requires the four finite internal reports.

Own fixture setup uses the established rectangular-base builder. Unknown/live
effects retain this process and every exact receipt; no COM cancellation,
inverse activation, roster-delta cleanup or automatic retry.
"""

import argparse
import ast
import asyncio
from contextlib import asynccontextmanager
import os
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

from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.native_first_save import validated_part_snapshot
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


HELPERS = ('verify_native_part_activation_public.py', 'verifier_native_part_activation.py',
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
    report = dict(scope='installed_native_part_activation_public', accepted=False,
                  public_activation_passed=False, cases=[], captures=[], owned_documents=[],
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
        specs = {
            'document_list': ToolSpec('document.list', False),
            'document_prepare_activate_part_native': ToolSpec('document.prepare_activate_part_native', False),
            'document_activate_part_native': ToolSpec('document.activate_part_native', True),
        }
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
                target_id = matching[0]['document_id']
                args = dict(document_id=target_id, configuration='Основная')
                report['phase'] = 'public_prepare'
                prepared = succeeded(await invoke('document_prepare_activate_part_native', request_id='prepare', **args))
                assert prepared['already_active'] is False
                args['expected_revision'] = prepared['revision']
                report['phase'] = 'public_activate'
                changed = await invoke('document_activate_part_native', request_id='activate', **args)
                assert changed['status'] == 'succeeded'
                first_job = (await client.call_tool('job_get', {'operation_id': changed['operation_id']})).structuredContent['data']
                assert verified_committed_part_activation(first_job)
                report['job'] = first_job
                assert await invoke('document_activate_part_native', request_id='activate', **args) == changed
                report['cases'].append(dict(label='public-explicit-activation-and-replay', passed=True))
                no_op_args = dict(document_id=target_id, configuration='Основная')
                prepared = succeeded(await invoke('document_prepare_activate_part_native', request_id='noop-prepare', **no_op_args))
                assert prepared['already_active'] is True
                no_op_args['expected_revision'] = prepared['revision']
                report['phase'] = 'public_noop'
                no_op = await invoke('document_activate_part_native', request_id='noop', **no_op_args)
                assert no_op['status'] == 'succeeded'
                noop_job = (await client.call_tool('job_get', {'operation_id': no_op['operation_id']})).structuredContent['data']
                assert verified_committed_part_activation(noop_job)
                report['noop_job'] = noop_job
                report['cases'].append(dict(label='public-already-active-noop', passed=True))
                await require_native_cleanup(client, gate)
                assert sw.CommandInProgress is False
                assert native_identity(binding.wrap(sw.ActiveDoc, module.IModelDoc2)) == target_identity
                persist()
            assert gate.can_cleanup()
        asyncio.run(exercise())
        assert gate.can_cleanup() and report['native_calls_live'] is False
        # Independent native readback after terminal normal receipt/release,
        # under a new explicitly owned observer flag, never while a call is live.
        assert report['native_calls_live'] is False
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        assert [validated_part_snapshot(adapter.first_save_part_snapshot(model)) for model in owned] == before
        assert native_identity(target) == target_identity and native_identity(neighbor) == neighbor_identity
        report['independent_native_readback_verified'] = True
        report['phase'] = 'owned_cleanup'
        persist()
        retire_owned(sw, module, target, [target], owned, record)
        assert validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == before[1]
        retire_owned(sw, module, neighbor, [neighbor], owned, record)
        assert not sw.GetDocuments() and sw.ActiveDoc is None
        sw.CommandInProgress = False
        assert sw.CommandInProgress is False
        restored = snapshot(sw, module)
        assert restored == original
        assert adapter.native_close_application_context() == original_application
        report['restored_application'] = adapter.native_close_application_context()
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        report.update(phase='terminal', public_activation_passed=True, accepted=True, baseline_restored=True,
                      own_cleanup_verified=True, restored_baseline=restored, native_calls_live=False)
        report['cases'].append(dict(label='ACT-N5-owned-cleanup', passed=True))
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
    print(json.dumps(dict(scope=report['scope'], public_activation_passed=True,
                         elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
