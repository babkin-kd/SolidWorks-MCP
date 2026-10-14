"""Installed public MCP new-part → full-turn radius10 height30 revolve chain."""

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import sysconfig
import uuid

import pythoncom
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences
from verify_mass_properties import source_state
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_wheel_artifact import validate_wheel
from verifier_lifecycle import ToolSpec, open_supervised_session
from verify_dimension_mcp import SessionCleanupGate, require_native_cleanup, call, succeeded
from verify_part_mcp import TOOL_SPECS as PART_SPECS


TOOL_SPECS = {**PART_SPECS,
    'part_prepare_base_revolve': ToolSpec('part.prepare_base_revolve', False,
        float_arguments=frozenset({'radius_mm','height_mm'}),
        argument_defaults={'axis':'profile_y','sketch_name':'Эскиз вращения','feature_name':'Вращение основания','body_name':'Тело вращения'}),
    'part_create_base_revolve': ToolSpec('part.create_base_revolve', True,
        float_arguments=frozenset({'radius_mm','height_mm'}),
        argument_defaults={'axis':'profile_y','sketch_name':'Эскиз вращения','feature_name':'Вращение основания','body_name':'Тело вращения'}),
    'document_list_templates': ToolSpec('document.list_templates', False),
    'document_prepare_create_part': ToolSpec('document.prepare_create_part', False,
        argument_defaults={'configuration_name':'Основная'}),
    'document_create_part': ToolSpec('document.create_part', True,
        argument_map={'application_id':'document_id'},argument_defaults={'configuration_name':'Основная'},
        constant_args={'configuration':''},prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise(state, sw, module, owned, report, persist, gate):
    params = StdioServerParameters(command=str(Path(sys.executable).with_name('solidworks-mcp-v2.exe')),
                                   args=['--state-dir', str(state / 'mcp')])
    @asynccontextmanager
    async def session():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as raw:
                await raw.initialize()
                info = (await raw.call_tool('system_get_info')).structuredContent['data']
                assert info['build_matches_source'] is True and info['package_version'] == report['wheel']['package_version']
                assert info['build']['git_sha'] == report['wheel']['git_sha'] and info['source_digest'] == report['wheel']['source_digest']
                tools = (await raw.list_tools()).tools
                assert len(tools) == 30 and all(tool.outputSchema for tool in tools)
                assert set(TOOL_SPECS) <= {tool.name for tool in tools}
                report['tool_count'] = len(tools)
                yield raw
    suffix = uuid.uuid4().hex[:8]
    async with open_supervised_session(session, tool_specs=TOOL_SPECS, journal_path=state / 'mcp' / 'jobs.sqlite') as client:
        gate.add(client)
        async def record(label, response):
            report['last_response'] = response
            persist()
            await require_native_cleanup(client, gate)
            assert sw.CommandInProgress is False
            assert_non_stl_preferences(lambda: application_preferences(sw), report['preferences'], report, 'preferences_' + label)
            report['cases'].append({'label': label, 'passed': True, 'response': response})
            persist()
        templates = succeeded(await call(client, 'document_list_templates'))
        template_id = templates['templates'][0]['template_id']
        name = 'Контрольная исходная деталь MCP ' + suffix
        prepared = succeeded(await call(client, 'document_prepare_create_part', template_id=template_id, name=name))
        assert prepared['native_creation_available'] is True and prepared['revision_scope'] == 'new_empty_part_document_v1'
        create_args = dict(application_id=prepared['application_id'], expected_revision=prepared['revision'], template_id=template_id, name=name)
        stale = await call(client, 'document_create_part', **{**create_args, 'expected_revision': 'rev_stale'})
        assert stale['status'] == 'failed' and stale['error']['code'] == 'stale_revision'
        await record('public_new_document_stale_prewrite_rejected', stale)
        async def create(arguments, label):
            response = await call(client, 'document_create_part', **arguments, timeout_s=0.)
            report['last_response'] = response
            persist()
            proof = succeeded(response)
            assert proof['verified'] is True and proof['execution_guard']['scope'] == 'application_document_create_guard_v1'
            await require_native_cleanup(client, gate)
            created_id = proof['after']['created_document_id']
            row = next(row for row in proof['after']['semantic']['documents'] if row['document_id'] == created_id)
            # A title/delta alone never grants ownership. First require the same-
            # wheel durable committed exact-NewDocument proof and released guard.
            # Only then independently locate its unique matching native document
            # in the initially empty/entirely caller-owned isolated session.
            models = [binding.wrap(raw, module.IModelDoc2) for raw in sw.GetDocuments() or ()]
            assert len(models) == len(owned) + 1
            matches = [model for model in models if model.GetTitle() == row['title'] and not model.GetPathName()]
            assert len(matches) == 1
            model = matches[0]
            token = model._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
            assert not any(token == old for _, old in owned)
            assert all(any(item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == old for item in models) for _, old in owned)
            assert model.GetType() == 1 and list(model.GetConfigurationNames() or ()) == row['configurations']
            assert model.GetUpdateStamp() == row['update_stamp'] and bool(model.GetSaveFlag()) == row['needs_save']
            owned.append((model, token))
            report['owned_documents'] = [{'title': item.GetTitle(), 'path': item.GetPathName(), 'type': item.GetType(),
                'ownership_basis': 'durable_verified_exact_NewDocument_return'} for item, _ in owned]
            persist()
            await record(label, response)
            return created_id, model, response
        create_args['request_id'] = 'new-part-' + uuid.uuid4().hex
        first_id, first, first_response = await create(create_args, 'public_new_part_from_empty_session')
        repeat = await call(client, 'document_create_part', **create_args)
        assert repeat['operation_id'] == first_response['operation_id'] and succeeded(repeat) == succeeded(first_response)
        await record('same_request_does_not_create_second_document', repeat)
        assert len(sw.GetDocuments() or ()) == 1
        first_identity = owned[0][1]
        from solidworks_mcp.cad_documents import SolidWorksDocuments
        adapter = SolidWorksDocuments()
        try:
            plane = next(item for item in adapter.features(first) if item.GetTypeName2() == 'RefPlane')
            assert plane.Select2(False, 7)
        finally:
            adapter.close()
        original = source_state(sw, module)
        name = 'Контрольная деталь вращения MCP ' + suffix
        prepared = succeeded(await call(client, 'document_prepare_create_part', template_id=template_id, name=name))
        second_id, second, _ = await create(dict(application_id=prepared['application_id'], expected_revision=prepared['revision'],
            template_id=template_id, name=name), 'public_new_part_preserves_existing_document')
        def check_first():
            current, facts = source_state(sw, module)
            before = [(row, fact) for row, fact in zip(original[0][3], original[1]) if row[0] == first_identity]
            after = [(row, fact) for row, fact in zip(current[3], facts) if row[0] == first_identity]
            assert before == after, 'Existing metadata/selection/geometry/view changed.'
        check_first()
        context = dict(document_id=second_id, configuration='Основная')
        tree = succeeded(await call(client, 'feature_list', **context))
        plane = next(row for row in tree['items'] if row['feature_type'] == 'RefPlane' and row['object_id'])
        arguments = dict(context, plane_object_id=plane['object_id'], radius_mm=10., height_mm=30., axis='profile_y')
        preparation = await call(client, 'part_prepare_base_revolve', **arguments)
        prepared = succeeded(preparation)
        assert prepared['native_creation_available'] is True
        assert prepared['revision_scope'] == 'empty_part_full_turn_cylinder_revolve_v1'
        assert math.isclose(prepared['expected_geometry']['volume_mm3'], 3000.*math.pi, rel_tol=1e-10)
        await record('public_prepare_full_turn_revolve_radius10_height30', preparation)
        request = dict(arguments, request_id='revolve-'+uuid.uuid4().hex,
                       expected_revision=prepared['revision'], timeout_s=0.)
        edited = await call(client, 'part_create_base_revolve', **request)
        assert succeeded(edited)['verified'] is True
        await record('public_native_full_turn_revolve_radius10_height30', edited)
        again = await call(client, 'part_create_base_revolve', **request)
        assert again['operation_id'] == edited['operation_id'] and again['data'] == edited['data']
        await record('same_request_does_not_create_second_revolve', again)
        check_first()
        raw_bodies = binding.wrap(second, module.IPartDoc).GetBodies2(-1, False) or ()
        assert len(raw_bodies) == 1
        native = binding.wrap(raw_bodies[0], module.IBody2)
        mass = native.GetMassProperties(1.)
        volume, area = float(mass[3])*1e9, float(mass[4])*1e6
        assert math.isclose(volume, 3000.*math.pi, rel_tol=1e-7)
        assert math.isclose(area, 800.*math.pi, rel_tol=1e-7)
        assert (native.GetVertexCount(),native.GetEdgeCount(),native.GetFaceCount()) == (0,2,3)
        report['volume_after_revolve_mm3'], report['surface_after_revolve_mm2'] = volume, area
        await require_native_cleanup(client, gate)
    assert gate.can_cleanup(), 'SDK shutdown must preserve terminal native cleanup proof.'
    report['public_mcp_revolve_accepted'] = True
    report['core_suite_passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--internal-report', type=Path, required=True)
    args = parser.parse_args()
    if not args.run_solidworks: parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    package = Path(solidworks_mcp.__file__).resolve().parent
    assert package.is_relative_to(Path(sysconfig.get_path('purelib')).resolve())
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version, expected_git_sha=args.expected_git_sha)
    assert solidworks_mcp.__version__ == importlib.metadata.version('solidworks-mcp') == args.expected_version
    assert source_digest(package) == wheel['source_digest']
    internal = json.loads(args.internal_report.read_text(encoding='utf8'))
    assert internal['accepted'] is True and internal['core_suite_passed'] is True
    assert all(internal['wheel'][key] == wheel[key] for key in ('git_sha', 'source_digest', 'package_version', 'wheel_sha256'))
    assert internal['scope'] == 'internal_full_turn_base_revolve_native_v1'
    assert internal['fixtures_closed'] is True and internal['owned_fixture_command_flag_released'] is True
    assert internal['verifier_sha256'] == hashlib.sha256(Path(__file__).with_name('verify_part_revolve.py').read_bytes()).hexdigest()
    assert {'revolve_stale_prewrite_rejected','revolve_known_failure_scoped_restoration','native_full_turn_revolve_radius10_height30'} <= {
        row['label'] for row in internal['cases'] if row['passed'] is True}
    state = args.state_dir.resolve()
    private = (Path(__file__).resolve().parents[1] / 'work').resolve()
    assert state.is_relative_to(private) and state != private
    state.mkdir(parents=True, exist_ok=False)
    report = {'accepted': False, 'scope': 'public_full_turn_base_revolve_native_v1', 'wheel': wheel,
        'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'internal_report': str(args.internal_report),
        'cases': [], 'owned_documents': [], 'public_mcp_revolve_accepted': False}
    def persist():
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    sw, owned, gate = None, [], SessionCleanupGate()
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and sw.CommandInProgress is False, 'Empty/free native baseline required.'
        baseline = native_snapshot()
        report['preferences'] = application_preferences(sw)
        asyncio.run(exercise(state, sw, module, owned, report, persist, gate))
    except BaseException as exc:
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        try:
            if sw is not None and gate.can_cleanup():
                assert sw.CommandInProgress is False
                models = [binding.wrap(raw, binding.module().IModelDoc2) for raw in sw.GetDocuments() or ()]
                assert len(models) == len(owned) and all(any(item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == token
                    for _, token in owned) for item in models)
                for model, token in reversed(owned):
                    title = model.GetTitle()
                    assert model.GetType() == 1 and not model.GetPathName() and sum(item.GetTitle() == title for item in models) == 1
                    sw.CloseDoc(title)
                    models = [binding.wrap(raw, binding.module().IModelDoc2) for raw in sw.GetDocuments() or ()]
                    assert not any(item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == token for item in models)
                assert native_snapshot() == baseline
                assert_non_stl_preferences(lambda: application_preferences(sw), report['preferences'], report, 'preferences_after_cleanup')
                report['fixtures_closed'] = True
                report['accepted'] = report.get('core_suite_passed') is True
        except BaseException as exc:
            report['cleanup_failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            report['accepted'] = False
            raise
        finally:
            persist()
            pythoncom.CoUninitialize()
    print(json.dumps({'accepted': report['accepted'], 'report': str(state / 'report.json')}))


if __name__ == '__main__': main()
