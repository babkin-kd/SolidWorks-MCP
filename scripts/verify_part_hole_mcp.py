"""Installed public MCP new-part → plate → circular through-hole chain."""

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
from verifier_part_pattern_mcp import TOOL_SPECS as PATTERN_SPECS
from verifier_part_fillet_mcp import TOOL_SPECS as FILLET_SPECS
from verifier_sheet_profile_mcp import TOOL_SPECS as SHEET_SPECS
from verifier_sheet_flat_state_mcp import TOOL_SPECS as SHEET_STATE_SPECS


TOOL_SPECS = {**PART_SPECS, **PATTERN_SPECS, **FILLET_SPECS,**SHEET_SPECS,**SHEET_STATE_SPECS,
    'dimension_list': ToolSpec('dimension.list',False,argument_defaults={'limit':100,'cursor':''}),
    'part_prepare_hole_dimension_change': ToolSpec('part.prepare_hole_dimension_change',False,float_arguments=frozenset({'value_mm'})),
    'part_set_hole_dimension': ToolSpec('part.set_hole_dimension',True,float_arguments=frozenset({'value_mm'}),prewrite_failure_codes=frozenset({'stale_revision'})),
    'part_prepare_through_hole': ToolSpec('part.prepare_through_hole', False,
        float_arguments=frozenset({'centre_x_mm','centre_y_mm','diameter_mm'}),
        argument_defaults={'sketch_name':'Эскиз отверстия','feature_name':'Сквозное отверстие'}),
    'part_create_through_hole': ToolSpec('part.create_through_hole', True,
        float_arguments=frozenset({'centre_x_mm','centre_y_mm','diameter_mm'}),
        argument_defaults={'sketch_name':'Эскиз отверстия','feature_name':'Сквозное отверстие'},
        prewrite_failure_codes=frozenset({'stale_revision'})),
    'sketch_get': ToolSpec('sketch.get', False),
    'sketch_prepare_dimension_change': ToolSpec('sketch.prepare_dimension_change', False, float_arguments=frozenset({'value_mm'})),
    'sketch_set_dimension': ToolSpec('sketch.set_dimension', True, float_arguments=frozenset({'value_mm'}), prewrite_failure_codes=frozenset({'stale_revision'})),
    'document_list_templates': ToolSpec('document.list_templates', False),
    'document_prepare_create_part': ToolSpec('document.prepare_create_part', False,
        argument_defaults={'configuration_name': 'Основная'}),
    'document_create_part': ToolSpec('document.create_part', True,
        argument_map={'application_id': 'document_id'}, argument_defaults={'configuration_name': 'Основная'},
        constant_args={'configuration': ''}, prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise(state, sw, module, owned, report, persist, gate, pattern_only=False,fillet_only=False,sheet_only=False,sheet_flat_only=False):
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
                assert len(tools) == 42 and all(tool.outputSchema for tool in tools)
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
        name = 'Контрольная новая пластина MCP ' + suffix
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
        if sheet_flat_only:
            from verifier_sheet_flat_state_mcp import exercise_sheet_flat
            await exercise_sheet_flat(client,context,second,module,record,report)
            check_first()
            await require_native_cleanup(client,gate)
            report['core_suite_passed']=True
            return
        if sheet_only:
            from verifier_sheet_profile_mcp import exercise_sheet
            await exercise_sheet(client,context,second,module,record,report)
            check_first()
            await require_native_cleanup(client,gate)
            report['core_suite_passed']=True
            return
        tree = succeeded(await call(client, 'feature_list', **context))
        plane = next(row for row in tree['items'] if row['feature_type'] == 'RefPlane' and row['object_id'])
        arguments = dict(context, plane_object_id=plane['object_id'], width_mm=40., height_mm=20., depth_mm=10.)
        prepared = succeeded(await call(client, 'part_prepare_base_extrusion', **arguments))
        built = await call(client, 'part_create_base_extrusion', **arguments, expected_revision=prepared['revision'], timeout_s=0.)
        assert succeeded(built)['verified'] is True
        await record('public_plate_in_server_created_document_40_20_10', built)
        check_first()
        tree = succeeded(await call(client, 'feature_list', **context))
        sketch_id = next(row['object_id'] for row in tree['items'] if row['feature_type']=='ProfileFeature')
        if fillet_only:
            from verifier_part_fillet_mcp import exercise_fillet
            await exercise_fillet(client,context,sketch_id,prepared,second,module,record,report)
            check_first()
            report['core_suite_passed']=True
            return
        arguments = dict(context, object_id=sketch_id, plane_object_id=plane['object_id'],
                         centre_x_mm=10., centre_y_mm=10., diameter_mm=6.)
        prepared = succeeded(await call(client, 'part_prepare_through_hole', **arguments))
        assert prepared['native_creation_available'] is True
        assert math.isclose(prepared['expected_geometry']['volume_mm3'], (8000.-math.pi*3.**2*10.), rel_tol=1e-10)
        prepared_hole_geometry=prepared['expected_geometry']
        request = dict(arguments, request_id='cut-'+uuid.uuid4().hex,
                       expected_revision=prepared['revision'], timeout_s=0.)
        edited = await call(client, 'part_create_through_hole', **request)
        assert succeeded(edited)['verified'] is True
        await record('public_native_circular_through_hole_d6_x10_y10', edited)
        again = await call(client, 'part_create_through_hole', **request)
        assert again['operation_id'] == edited['operation_id'] and again['data'] == edited['data']
        await record('same_request_does_not_create_second_hole', again)
        check_first()
        raw_bodies = binding.wrap(second, module.IPartDoc).GetBodies2(-1, False) or ()
        assert len(raw_bodies) == 1
        native_body = binding.wrap(raw_bodies[0], module.IBody2)
        measures = native_body.GetMassProperties(1.)
        volume, area = float(measures[3])*1e9, float(measures[4])*1e6
        assert math.isclose(volume, (8000.-math.pi*3.**2*10.), rel_tol=1e-10)
        assert math.isclose(area, (2800.-2.*math.pi*3.**2+2.*math.pi*3.*10.), rel_tol=1e-10)
        assert (native_body.GetVertexCount(),native_body.GetEdgeCount(),native_body.GetFaceCount()) == (8,14,7)
        report['surface_after_hole_mm2'] = area
        report['volume_after_cut_mm3'] = volume
        circle_native_id=succeeded(edited)['after']['created']['sketch_native_id']
        tree=succeeded(await call(client,'feature_list',**context))
        circle_id=next(row['object_id'] for row in tree['items'] if row['native_id']==circle_native_id)
        if pattern_only:
            from verifier_part_pattern_mcp import exercise_pattern
            # The base frame is present in the committed complete base sketch.
            frame=prepared_hole_geometry
            await exercise_pattern(client,context,sketch_id,circle_id,succeeded(edited)['after']['created']['cut_native_id'],
                frame,second,module,record,report)
        else:
            rows=succeeded(await call(client,'dimension_list',**context))['items']
            diameter=next(row['object_id'] for row in rows if row['owner'] and row['owner']['native_id']==circle_native_id and row['name']=='Диаметр')
            edit_arguments=dict(context,base_object_id=sketch_id,object_id=circle_id,dimension_id=diameter,value_mm=8.)
            prepared=succeeded(await call(client,'part_prepare_hole_dimension_change',**edit_arguments))
            assert prepared['revision_scope']=='single_base_circular_through_hole_dimension_v1'
            edit_request=dict(edit_arguments,expected_revision=prepared['revision'],request_id='hole-edit-'+uuid.uuid4().hex,timeout_s=0.)
            changed=await call(client,'part_set_hole_dimension',**edit_request)
            assert succeeded(changed)['verified'] is True
            await record('public_hole_edit_d8',changed)
            again=await call(client,'part_set_hole_dimension',**edit_request)
            assert again['operation_id']==changed['operation_id'] and again['data']==changed['data']
            await record('same_request_does_not_edit_hole_twice',again)
            native_body=binding.wrap((binding.wrap(second,module.IPartDoc).GetBodies2(-1,False) or ())[0],module.IBody2)
            measures=native_body.GetMassProperties(1.)
            assert math.isclose(float(measures[3])*1e9,8000.-math.pi*4.**2*10.,rel_tol=1e-10)
            assert math.isclose(float(measures[4])*1e6,2800.-2.*math.pi*4.**2+2.*math.pi*4.*10.,rel_tol=1e-10)
            assert (native_body.GetVertexCount(),native_body.GetEdgeCount(),native_body.GetFaceCount())==(8,14,7)
            report['hole_edit_volume_mm3']=float(measures[3])*1e9
            report['hole_edit_surface_area_mm2']=float(measures[4])*1e6
        check_first()
        await require_native_cleanup(client, gate)
    assert gate.can_cleanup(), 'SDK shutdown must preserve terminal native cleanup proof.'
    report['public_mcp_hole_accepted'] = True
    if not pattern_only:report['public_mcp_hole_edit_accepted'] = True
    report['core_suite_passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--pattern-only',action='store_true')
    parser.add_argument('--fillet-only',action='store_true')
    parser.add_argument('--sheet-flat-only',action='store_true',help='Existing native L-sheet flat/fold state block.')
    parser.add_argument('--sheet-only',action='store_true')
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--internal-report', type=Path, required=True)
    args = parser.parse_args()
    if sum((args.pattern_only,args.fillet_only,args.sheet_only,args.sheet_flat_only))>1:parser.error('Choose one engineering block.')
    if not args.run_solidworks: parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    package = Path(solidworks_mcp.__file__).resolve().parent
    assert package.is_relative_to(Path(sysconfig.get_path('purelib')).resolve())
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version, expected_git_sha=args.expected_git_sha)
    assert solidworks_mcp.__version__ == importlib.metadata.version('solidworks-mcp') == args.expected_version
    assert source_digest(package) == wheel['source_digest']
    internal = json.loads(args.internal_report.read_text(encoding='utf8'))
    assert internal['accepted'] is True and internal['core_suite_passed'] is True
    assert all(internal['wheel'][key] == wheel[key] for key in ('git_sha','source_digest','package_version','wheel_sha256'))
    assert internal['fixtures_closed'] is True and internal['command_flag_baseline_restored'] is True
    assert internal['verifier_sha256'] == hashlib.sha256(Path(__file__).with_name('verify_part_hole.py').read_bytes()).hexdigest()
    if args.sheet_flat_only:
        assert internal['scope']=='internal_l_sheet_flat_state_native_v1' and internal['sheet_state_suite_passed'] is True
        assert internal['sheet_state_helper_sha256']==hashlib.sha256(Path(__file__).with_name('verifier_sheet_flat_state.py').read_bytes()).hexdigest()
        assert {'new_part_from_empty_session','new_part_preserves_existing_document','native_sheet_flat_source_created',
            'sheet_state_stale_prewrite_rejected','sheet_state_known_failure_scoped_restoration','native_sheet_flat_state',
            'native_sheet_folded_state_restored'}<={row['label'] for row in internal['cases'] if row['passed'] is True}
    elif args.sheet_only:
        assert internal['scope']=='internal_folded_sheet_l_profile_native_v1' and internal['sheet_profile_suite_passed'] is True
        assert internal['sheet_helper_sha256']==hashlib.sha256(Path(__file__).with_name('verifier_sheet_profile.py').read_bytes()).hexdigest()
        assert {'new_part_from_empty_session','new_part_preserves_existing_document','sheet_short_leg_prewrite_rejected',
            'sheet_stale_prewrite_rejected','sheet_known_failure_scoped_restoration','native_folded_sheet_l_profile'}<={row['label'] for row in internal['cases'] if row['passed'] is True}
    elif args.fillet_only:
        assert internal['scope']=='internal_selected_edge_fillet_native_v1' and internal['fillet_suite_passed'] is True
        assert internal['fillet_helper_sha256']==hashlib.sha256(Path(__file__).with_name('verifier_part_fillet.py').read_bytes()).hexdigest()
        assert {'new_part_from_empty_session','new_part_preserves_existing_document','plate_in_server_created_document_40_20_10',
            'fillet_material_prewrite_rejected','fillet_stale_prewrite_rejected','fillet_known_failure_scoped_restoration',
            'native_selected_edge_fillet_r2'}<={row['label'] for row in internal['cases'] if row['passed'] is True}
    elif args.pattern_only:
        assert internal['scope']=='internal_linear_through_hole_pattern_native_v1' and internal['pattern_suite_passed'] is True
        assert internal['circle_native_id_metadata_fixed'] is True
        assert internal['pattern_helper_sha256']==hashlib.sha256(Path(__file__).with_name('verifier_part_pattern.py').read_bytes()).hexdigest()
        assert {'pattern_material_prewrite_rejected','pattern_stale_prewrite_rejected',
            'pattern_known_failure_scoped_restoration','native_linear_hole_pattern_x3_step10'} <= {row['label'] for row in internal['cases'] if row['passed'] is True}
    else:
        assert internal['hole_edit_suite_passed'] is True
        assert all(internal['wheel'][key] == wheel[key] for key in ('git_sha', 'source_digest', 'package_version', 'wheel_sha256'))
        assert internal['scope'] == 'internal_circular_through_hole_edit_native_v1'
        assert internal['fixtures_closed'] is True and internal['command_flag_baseline_restored'] is True
        assert internal['verifier_sha256'] == hashlib.sha256(Path(__file__).with_name('verify_part_hole.py').read_bytes()).hexdigest()
        assert {'new_part_from_empty_session','new_part_preserves_existing_document',
                'plate_in_server_created_document_40_20_10','native_circular_through_hole_d6_x10_y10',
                'hole_edit_x12','hole_edit_y11','hole_edit_d8','hole_edit_known_failure_scoped_restoration',
                'hole_edit_stale_prewrite_rejected','hole_edit_material_prewrite_rejected'} <= {
            row['label'] for row in internal['cases'] if row['passed'] is True}
    state = args.state_dir.resolve()
    private = (Path(__file__).resolve().parents[1] / 'work').resolve()
    assert state.is_relative_to(private) and state != private
    state.mkdir(parents=True, exist_ok=False)
    report = {'accepted': False, 'scope': 'public_selected_edge_fillet_native_v1' if args.fillet_only else 'public_linear_through_hole_pattern_native_v1' if args.pattern_only else 'public_circular_through_hole_native_v1', 'wheel': wheel,
        'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'internal_report': str(args.internal_report),
        'cases': [], 'owned_documents': [], 'public_mcp_hole_accepted': False}
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
        if args.sheet_only:report['scope']='public_folded_sheet_l_profile_native_v1'
        if args.sheet_flat_only:report['scope']='public_l_sheet_flat_state_native_v1'
        asyncio.run(exercise(state, sw, module, owned, report, persist, gate,args.pattern_only,args.fillet_only,args.sheet_only,args.sheet_flat_only))
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
