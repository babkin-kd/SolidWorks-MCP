"""Installed-wheel native export acceptance, exclusively on owned fixtures.

This file is a verifier, not acceptance evidence until root executes it. Use a
fresh private journal/output directory under work/, with no source PYTHONPATH.
Only the exact two disposable unsaved documents from fixtures() are edited or
activated. Uncertain outputs/foreign files are retained for reconciliation.
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import uuid

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pythoncom

import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures


# Independent reads against the registered swconst31 API; do not reuse the
# domain's preference helper or format validators as their own evidence.
PREFS = {
    'coordinate_system': ('String', 134), 'stl_units': ('Integer', 211),
    'stl_binary': ('Toggle', 69), 'stl_dont_translate_to_positive': ('Toggle', 71),
    'stl_show_info': ('Toggle', 70), 'stl_preview': ('Toggle', 191),
    'stl_quality': ('Integer', 78), 'stl_deviation': ('Double', 2),
    'stl_angle': ('Double', 3), 'step_ap': ('Integer', 75),
    'step_geometry': ('Integer', 142), 'step_curves': ('Toggle', 497),
    'step_appearances': ('Toggle', 787), 'step_face_edge_props': ('Toggle', 397),
    'step_configuration_data': ('Toggle', 403), 'step_split_periodic': ('Toggle', 396),
    'step_atomic_save': ('Toggle', 786), 'parasolid_version': ('Integer', 89),
    'dimension_input': ('Toggle', SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE),
}


def application_preferences(sw):
    methods = {'String': 'GetUserPreferenceStringValue', 'Integer': 'GetUserPreferenceIntegerValue',
               'Toggle': 'GetUserPreferenceToggle', 'Double': 'GetUserPreferenceDoubleValue'}
    return {name: getattr(sw, methods[kind])(code) for name, (kind, code) in PREFS.items()}


def fixture_preferences_baseline(setup_preferences, export_preferences):
    """Allow only the observed fixture-geometry deviation recalculation.

    This exemption applies solely to replacement of our own fixture geometry.
    Callers retain exact comparisons of ALL preferences after every export.
    """
    assert set(setup_preferences) == set(export_preferences), 'Fixture preference keys changed.'
    changed = {key: {'before': setup_preferences[key], 'after': export_preferences[key]}
               for key in setup_preferences if setup_preferences[key] != export_preferences[key]}
    assert set(changed) <= {'stl_deviation'}, ('Fixture setup changed other preferences.', changed)
    return {'fixture_setup_stl_deviation': {'before': setup_preferences['stl_deviation'],
                                          'after': export_preferences['stl_deviation']},
            'export_preferences_baseline_captured_after_fixture_setup': True,
            'fixture_setup_other_preferences_exactly_unchanged': True}


def ui_snapshot(sw, module):
    result = []
    for raw in sw.GetDocuments() or ():
        model = binding.wrap(raw, module.IModelDoc2)
        manager = binding.wrap(model.SelectionManager, module.ISelectionMgr)
        result.append((model._oleobj_.QueryInterface(pythoncom.IID_IUnknown),
                       int(model.GetBlockingState()), int(manager.GetSelectedObjectCount2(-1))))
    return result


def user_file_metadata(native_state):
    # Read file metadata only; no original CAD file is opened for writing. This
    # detects ordinary saves/replacements without hashing large production data.
    result = {}
    for _, _, path, *_ in native_state[3]:
        if path:
            try:
                info = Path(path).stat()
                result[str(path)] = info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
            except FileNotFoundError:
                result[str(path)] = None
    return result


def exact_solid(model, module):
    bodies = [binding.wrap(raw, module.IBody2)
              for raw in binding.wrap(model, module.IPartDoc).GetBodies2(-1, False) or ()]
    assert len(bodies) == 1 and int(bodies[0].GetType()) == 0
    assert not bodies[0].IsMeshBody() and bool(bodies[0].Visible)
    return bodies[0]


def native_extrema_m(body):
    low, high = [], []
    for axis in range(3):
        values = []
        for sign in (-1, 1):
            direction = [0., 0., 0.]
            direction[axis] = float(sign)
            result = body.GetExtremePoint(*direction)
            assert isinstance(result, tuple) and len(result) == 4 and result[0] is True, result
            assert all(math.isfinite(float(value)) for value in result[1:])
            values.append(float(result[axis + 1]))
        low.append(values[0])
        high.append(values[1])
    return {'min': low, 'max': high}


def owned_source_snapshot(model, module):
    body = exact_solid(model, module)
    manager = binding.wrap(model.SelectionManager, module.ISelectionMgr)
    active = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
    feature = binding.wrap(model.FirstFeature(), module.IFeature)
    features = []
    while feature is not None:
        features.append((int(feature.GetID()), str(feature.Name), str(feature.GetTypeName2()),
                         tuple(feature.GetErrorCode2())))
        feature = binding.wrap(feature.GetNextFeature(), module.IFeature)
    return {'title': str(model.GetTitle()), 'path': str(model.GetPathName()),
            'stamp': int(model.GetUpdateStamp()), 'save_flag': bool(model.GetSaveFlag()),
            'configurations': tuple(model.GetConfigurationNames() or ()), 'active_configuration': str(active.Name),
            'blocking_state': int(model.GetBlockingState()), 'selection_count': int(manager.GetSelectedObjectCount2(-1)),
            'native_extrema_m': native_extrema_m(body), 'body_mass_facts': tuple(body.GetMassProperties(1)),
            'features': tuple(features)}


def independent_file_facts(path):
    before = path.stat()
    assert path.is_file() and not path.is_symlink() and before.st_size > 0
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return {'bytes': before.st_size, 'sha256': digest.hexdigest(),
            'identity': (before.st_dev, before.st_ino)}


def independent_binary_stl(path):
    facts = independent_file_facts(path)
    low, high = [math.inf] * 3, [-math.inf] * 3
    with path.open('rb') as stream:
        header = stream.read(84)
        assert len(header) == 84
        triangles = struct.unpack('<I', header[80:84])[0]
        assert triangles > 0 and facts['bytes'] == 84 + triangles * 50
        for _ in range(triangles):
            record = stream.read(50)
            assert len(record) == 50
            values = struct.unpack('<12fH', record)
            assert all(math.isfinite(value) for value in values[:12])
            for vertex in (3, 6, 9):
                for axis in range(3):
                    low[axis] = min(low[axis], values[vertex + axis])
                    high[axis] = max(high[axis], values[vertex + axis])
        assert stream.read(1) == b''
    return {**facts, 'triangles': triangles, 'min': low, 'max': high}


def assert_stl_frame_and_units(parsed, native_m, units):
    scale = {'mm': 1000., 'm': 1., 'in': 1. / .0254}[units]
    # Native test source has planar rectangular faces: triangulation must retain
    # its exact extrema. This is stronger than a domain-reported approximate box.
    for key in ('min', 'max'):
        expected = [value * scale for value in native_m[key]]
        for got, wanted in zip(parsed[key], expected):
            assert math.isclose(got, wanted, rel_tol=2e-6, abs_tol=1e-7 * scale), (units, key, got, wanted)
    assert min(parsed['min']) < 0, 'Output moved the negative-space source into positive coordinates.'


async def settle(client, tool, arguments):
    response = (await client.call_tool(tool, arguments)).structuredContent
    assert isinstance(response, dict) and set(response) == {
        'status', 'operation_id', 'context', 'data', 'error', 'diagnostics'}, response
    while response['status'] in ('queued', 'running'):
        await asyncio.sleep(.25)
        job = (await client.call_tool('job_get', {'operation_id': response['operation_id']})).structuredContent
        response = {**job, 'data': job['data'] if tool == 'job_get' else job['data']['result']}
    return response


def succeeded(response):
    assert response['status'] == 'succeeded', response
    return response['data']


def failed(response, *codes):
    assert response['status'] == 'failed', response
    assert response['error']['code'] in codes, response


async def check(state, output):
    assert 'site-packages' in solidworks_mcp.__file__, 'Use an installed wheel without source PYTHONPATH.'
    assert not os.environ.get('PYTHONPATH'), 'Unset source PYTHONPATH before native acceptance.'
    state = state.resolve()
    output = output.absolute()
    assert state != output and state not in output.parents and output not in state.parents
    assert not state.exists() or not list(state.iterdir()), 'Use a fresh private job journal.'
    if output.exists():
        assert output.is_dir() and not list(output.iterdir()), 'Use a fresh empty private export directory.'
    else:
        output.mkdir()
    assert not output.is_symlink()
    output = output.resolve()
    original = native_snapshot()
    original_sw = binding.connect(show=False)
    original_module = binding.module()
    original_preferences = application_preferences(original_sw)
    original_ui = ui_snapshot(original_sw, original_module)
    original_file_metadata = user_file_metadata(original)
    report = {}
    owned_files = {}  # Only verifier-created, independently confirmed exact paths.
    try:
        with fixtures() as (session, owned, _):
            sw, module = session._sw, session._mod
            setup_preferences = application_preferences(sw)
            assert session._model._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == (
                owned[1]._oleobj_.QueryInterface(pythoncom.IID_IUnknown))
            assert sw.ActiveDoc._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == (
                owned[1]._oleobj_.QueryInterface(pythoncom.IID_IUnknown))
            # Replace only an exact feature of our second unsaved fixture. This
            # leaves one solid and tests 'don't translate to positive' directly.
            session.delete_feature('Контрольный чужой блок', with_children=True)
            session.add_extruded_profile([[-25, -30], [-20, -30], [-20, -24], [-25, -24]],
                                        7, name='Отрицательный контрольный блок', merge=False)
            for feature in session._iter_features():
                if feature.GetTypeName2() in ('ProfileFeature', '3DProfileFeature'):
                    feature.Name = 'Отрицательный контрольный эскиз'
                    assert feature.Name == 'Отрицательный контрольный эскиз'
            body = exact_solid(owned[1], module)
            body.Name = 'Отрицательное контрольное тело'
            assert body.Name == 'Отрицательное контрольное тело'
            assert owned[1].ForceRebuild3(False)
            owned[1].ClearSelection2(True)
            before_preferences = application_preferences(sw)
            report.update(fixture_preferences_baseline(setup_preferences, before_preferences))
            source = owned_source_snapshot(owned[1], module)
            assert source['selection_count'] == 0 and source['blocking_state'] == 0
            assert source['active_configuration'] == 'Основная'
            assert min(source['native_extrema_m']['min']) < 0
            setup = native_snapshot()
            setup_ui = ui_snapshot(sw, module)
            titles = [str(model.GetTitle()) for model in owned]
            params = StdioServerParameters(command=str(Path(sys.executable).with_name('solidworks-mcp-v2.exe')),
                args=['--state-dir', str(state), '--output-dir', str(output)])
            async def call(client, tool, **arguments):
                if tool not in ('system_get_info', 'job_get'):
                    arguments.setdefault('request_id', uuid.uuid4().hex)
                return await settle(client, tool, arguments)
            def unchanged():
                assert native_snapshot() == setup, 'Export changed native document/active/configuration metadata.'
                assert ui_snapshot(sw, module) == setup_ui, 'Export changed native UI blocking/selection state.'
                assert owned_source_snapshot(owned[1], module) == source, 'Export changed independent source body facts.'
                assert application_preferences(sw) == before_preferences, 'Export preferences were not restored.'
            with anyio.fail_after(900):
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        info = succeeded(await call(client, 'system_get_info'))
                        assert info['build_matches_source'] is True
                        tools = (await client.list_tools()).tools
                        names = {tool.name for tool in tools}
                        assert {'export_prepare', 'export_part', 'document_list', 'job_get'} <= names
                        assert all(tool.outputSchema for tool in tools)
                        documents = succeeded(await call(client, 'document_list'))['documents']
                        mixed, target = [next(document for document in documents if document['title'] == title)
                                         for title in titles]
                        context = {'document_id': target['document_id'], 'configuration': 'Основная'}
                        token = uuid.uuid4().hex[:12]
                        missing = await call(client, 'export_prepare', document_id='doc_missing', configuration='Основная',
                            file_format='stl', filename=f'Неизвестный документ {token}.stl', units='mm')
                        failed(missing, 'document_not_open')
                        wrong = await call(client, 'export_prepare', document_id=mixed['document_id'], configuration='Основная',
                            file_format='stl', filename=f'Неактивная часть {token}.stl', units='mm')
                        failed(wrong, 'document_not_active')
                        inactive = await call(client, 'export_prepare', document_id=mixed['document_id'], configuration='Вариант',
                            file_format='stl', filename=f'Неактивная конфигурация {token}.stl', units='mm')
                        failed(inactive, 'configuration_not_active')
                        # Make the mixed fixture active only to test its unsupported
                        # surface. Activation is verifier-owned and immediately restored.
                        activated, _ = sw.ActivateDoc3(titles[0], False, 1, 0)
                        assert activated is not None
                        owned[0].ClearSelection2(True)
                        unsupported = await call(client, 'export_prepare', document_id=mixed['document_id'], configuration='Основная',
                            file_format='stl', filename=f'Смешанные тела {token}.stl', units='mm')
                        failed(unsupported, 'unsupported_export_body')
                        activated, _ = sw.ActivateDoc3(titles[1], False, 1, 0)
                        assert activated is not None
                        unchanged()
                        assert not list(output.iterdir())

                        # Prepare does not authorize silently changed sources. An
                        # outside-MCP name edit to the exact owned feature invalidates it.
                        stale_filename = f'Устаревший экспорт {token}.stl'
                        prepared = succeeded(await call(client, 'export_prepare', **context,
                            file_format='stl', filename=stale_filename, units='mm'))
                        assert prepared['revision_scope'] == 'part_solid_brep_export_v1'
                        session._model = owned[1]
                        native_feature = next(feature for feature in session._iter_features()
                                              if feature.Name == 'Отрицательный контрольный блок')
                        native_feature.Name = 'Отрицательный блок после проверки'
                        assert native_feature.Name == 'Отрицательный блок после проверки'
                        stale = await call(client, 'export_part', **context, expected_revision=prepared['revision'],
                            file_format='stl', filename=stale_filename, units='mm')
                        failed(stale, 'stale_revision')
                        assert not (output / stale_filename).exists()
                        source = owned_source_snapshot(owned[1], module)
                        setup = native_snapshot()
                        setup_ui = ui_snapshot(sw, module)
                        unchanged()

                        # An exact verifier-created sentinel stands in for an
                        # existing user file. Its content must never be overwritten.
                        sentinel = output / f'Существующий файл {token}.stl'
                        sentinel.write_bytes(b'verifier-sentinel-must-survive')
                        owned_files[sentinel] = independent_file_facts(sentinel)
                        exists = await call(client, 'export_prepare', **context,
                            file_format='stl', filename=sentinel.name, units='mm')
                        failed(exists, 'export_file_exists')
                        assert sentinel.read_bytes() == b'verifier-sentinel-must-survive'
                        unchanged()

                        formats = [('stl', 'mm', '.stl'), ('stl', 'm', '.stl'), ('stl', 'in', '.stl'),
                                   ('step', '', '.step'), ('parasolid', '', '.x_t')]
                        results = []
                        for index, (format, units, extension) in enumerate(formats):
                            filename = f'Контрольный экспорт {token} {index}{extension}'
                            prepared = succeeded(await call(client, 'export_prepare', **context,
                                file_format=format, filename=filename, units=units))
                            assert prepared['revision_scope'] == 'part_solid_brep_export_v1'
                            unchanged()
                            arguments = {**context, 'file_format': format, 'filename': filename, 'units': units,
                                'expected_revision': prepared['revision'], 'request_id': f'export-{token}-{index}', 'timeout_s': 0}
                            pending = (await client.call_tool('export_part', arguments)).structuredContent
                            retry = (await client.call_tool('export_part', arguments)).structuredContent
                            assert pending['operation_id'] == retry['operation_id']
                            complete = succeeded(await call(client, 'job_get', operation_id=pending['operation_id']))
                            assert complete['mutation']['phase'] == 'committed', complete
                            assert complete['mutation']['before_state']['_mutation_effect_scope'] == 'application'
                            result = complete['result']
                            assert result['verified'] is True
                            manifest = result['value']
                            assert manifest['source_revision'] == prepared['revision']
                            assert manifest['revision_scope'] == prepared['revision_scope']
                            assert manifest['operation_id'] == pending['operation_id']
                            assert manifest['document_id'] == context['document_id']
                            assert manifest['configuration'] == 'Основная' and manifest['format'] == format
                            assert manifest['source_unchanged'] is True and manifest['preferences_restored'] is True
                            assert manifest['native_errors'] == 0 and manifest['native_warnings'] == 0
                            assert manifest['coordinate_frame'] == 'part_model'
                            assert manifest['geometry_roundtrip_verified'] is False
                            path = output / filename
                            assert Path(manifest['path']).resolve() == path.resolve()
                            facts = independent_file_facts(path)
                            owned_files[path] = facts
                            assert facts['bytes'] == manifest['bytes'] and facts['sha256'] == manifest['sha256']
                            format_facts = {}
                            if format == 'stl':
                                parsed = independent_binary_stl(path)
                                assert_stl_frame_and_units(parsed, source['native_extrema_m'], units)
                                assert manifest['units'] == units and manifest['units_embedded'] is False
                                format_facts = {'triangles': parsed['triangles'], 'bbox': {'min': parsed['min'], 'max': parsed['max']},
                                                'native_bbox_and_units_confirmed': True}
                            elif format == 'step':
                                content = path.read_text(encoding='ascii', errors='replace')
                                assert 'ISO-10303-21;' in content[:256] and 'END-ISO-10303-21;' in content[-4096:]
                                declarations = re.findall(r'SI_UNIT\(\s*(\$|\.MILLI\.)\s*,\s*\.METRE\.\s*\)', content)
                                assert declarations and len(set(declarations)) == 1
                                declared_units = 'mm' if declarations[0] == '.MILLI.' else 'm'
                                assert manifest['units'] == declared_units and manifest['units_embedded'] is True
                                format_facts = {'file_length_units': declared_units, 'exchange_header_confirmed': True}
                            else:
                                header = path.read_bytes()[:4096]
                                assert header.startswith(b'**') and b'PARASOLID' in header.upper()
                                assert manifest['units'] is None and manifest['units_embedded'] is None
                                format_facts = {'text_transmit_header_confirmed': True, 'file_units_independently_verified': False}
                            unchanged()
                            historical = succeeded(await call(client, 'job_get', operation_id=pending['operation_id']))
                            assert historical['result'] == result and historical['mutation']['phase'] == 'committed'
                            assert set(output.iterdir()) == set(owned_files), 'Unexpected output/sidecar was produced.'
                            results.append({'format': format, 'requested_units': units, 'bytes': facts['bytes'],
                                'sha256': facts['sha256'], 'timeout_zero_initial_status': pending['status'],
                                'same_request_id_same_job': True, 'durable_application_checkpoint': True, **format_facts})
                        report = {**report, 'package_version': info['package_version'], 'git_sha': info['build']['git_sha'],
                            'source_dirty': info['build']['source_dirty'], 'build_matches_source': True,
                            'solidworks_revision': original[0], 'tool_count': len(tools), 'owned_fixture_documents': 2,
                            'native_mcp_exports': results, 'independent_source_geometry_and_native_state_unchanged': True,
                            'preferences_and_ui_blocking_restored': True, 'stale_revision_rejected': True,
                            'foreign_inactive_and_mixed_source_rejected': True, 'existing_output_unchanged': True,
                            'revision_scope': 'part_solid_brep_export_v1', 'geometry_roundtrip_verified': False,
                            'fault_injection_rollback_and_crash_acceptance': False}
            unchanged()
        assert native_snapshot() == original
        assert application_preferences(original_sw) == original_preferences
        assert ui_snapshot(original_sw, original_module) == original_ui
        assert user_file_metadata(original) == original_file_metadata
        report['original_user_document_baseline_restored'] = True
        report['original_cad_file_metadata_unchanged'] = True
        report['original_cad_file_byte_hashes_checked'] = False
    finally:
        # Only files that the verifier created and independently identified are
        # removed. Never glob-delete, recurse-delete, or clean an uncertain output.
        for path, recorded in owned_files.items():
            if not path.exists():
                continue
            current = independent_file_facts(path)
            assert current == recorded, 'Owned output changed; retain it for reconciliation instead of deleting.'
            path.unlink()
    assert not list(output.iterdir()), 'Unconfirmed outputs retained in private output directory.'
    report['confirmed_owned_output_files_removed'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    pythoncom.CoInitialize()
    try:
        print(json.dumps(asyncio.run(check(args.state_dir, args.output_dir)), ensure_ascii=True, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
