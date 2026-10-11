"""Installed console/MCP metadata smoke only. Never calls CAD or job tools."""
import argparse
import asyncio
from importlib import metadata
import hashlib
import json
import os
from pathlib import Path
import sys
import sysconfig

from verify_wheel_artifact import require, validate_wheel

TOOLS = frozenset({'system_get_info', 'job_get', 'job_list', 'job_cancel',
    'document_list', 'document_get', 'body_list', 'face_list', 'edge_list', 'geometry_get',
    'feature_list', 'feature_get', 'feature_rename', 'dimension_list', 'dimension_get',
    'dimension_set_value', 'export_prepare', 'export_part', 'part_prepare_base_extrusion', 'part_create_base_extrusion',
    'document_list_templates', 'document_prepare_create_part', 'document_create_part', 'sketch_get', 'sketch_prepare_dimension_change', 'sketch_set_dimension', 'part_prepare_corner_cut', 'part_create_corner_cut', 'part_prepare_base_revolve', 'part_create_base_revolve', 'part_prepare_through_hole', 'part_create_through_hole', 'part_prepare_hole_dimension_change', 'part_set_hole_dimension', 'part_prepare_linear_hole_pattern', 'part_create_linear_hole_pattern', 'part_prepare_edge_fillet', 'part_create_edge_fillet', 'sheet_prepare_l_profile', 'sheet_create_l_profile', 'sheet_prepare_flat_state', 'sheet_set_flat_state', 'sheet_prepare_parameters', 'sheet_set_parameters'})


def installed_identity(wheel):
    require(not os.environ.get('PYTHONPATH'), 'Unset PYTHONPATH before installed-wheel verification.')
    import solidworks_mcp
    from solidworks_mcp.build_info import source_digest
    package = Path(solidworks_mcp.__file__).resolve().parent
    purelib = Path(sysconfig.get_path('purelib')).resolve()
    require(package.is_relative_to(purelib), 'Package is outside this interpreter site-packages.')
    require(metadata.version('solidworks-mcp') == solidworks_mcp.__version__ == wheel['package_version'],
            'Installed version mismatch.')
    build = json.loads((package / 'build_info.json').read_text(encoding='utf8'))
    require(build['git_sha'] == wheel['git_sha'] and build['source_dirty'] is False,
            'Installed build SHA/cleanliness mismatch.')
    require(build['package_version'] == wheel['package_version'] and build['api_version'] == 2,
            'Installed build API/version mismatch.')
    actual = source_digest(package)
    require(actual == build['source_digest'] == wheel['source_digest'], 'Installed source digest mismatch.')
    entry = Path(sys.executable).with_name('solidworks-mcp-v2.exe' if sys.platform == 'win32' else 'solidworks-mcp-v2')
    require(entry.is_file(), 'Installed v2 console entry point is missing.')
    return entry


def verify_metadata(tools, info, wheel):
    names = [tool.name for tool in tools]
    require(len(names) == len(set(names)) and set(names) == TOOLS, 'Unexpected public tool catalog.')
    require(all(tool.outputSchema for tool in tools), 'Public tool lacks outputSchema.')
    require(info['package_version'] == wheel['package_version'] and info['api_version'] == 2,
            'MCP API/version mismatch.')
    require(info['build_matches_source'] is True and info['build']['source_dirty'] is False,
            'MCP build mismatch or dirty build.')
    require(info['build']['git_sha'] == wheel['git_sha'], 'MCP build SHA mismatch.')
    require(info['source_digest'] == info['build']['source_digest'] == wheel['source_digest'],
            'MCP source digest mismatch.')
    require(info['schema_version'] == '2.0-dev', 'Unexpected API schema version.')
    require(info['mutation_revision_scopes'] == ['part_feature_tree_v1', 'part_dimension_values_v1',
                                                 'part_solid_brep_export_v1', 'empty_part_base_rectangle_v1', 'new_empty_part_document_v1', 'part_rectangular_sketch_dimension_v1', 'single_base_rectangular_corner_through_cut_v1', 'empty_part_full_turn_cylinder_revolve_v1', 'single_base_circular_through_hole_v1', 'single_base_circular_through_hole_dimension_v1', 'single_base_linear_through_hole_pattern_v1', 'single_base_selected_edge_fillet_v1', 'empty_part_sheet_l_profile_v1', 'single_l_sheet_flat_state_v1', 'single_l_sheet_parameters_v1'],
            'Unexpected mutation revision scopes.')
    require(info['development_candidate'] is True, 'Expected a development candidate.')
    require(info['implemented_mutations'] == ['feature.rename', 'dimension.set_value', 'export.execute', 'part.create_base_extrusion', 'document.create_part', 'sketch.set_dimension', 'part.create_corner_cut', 'part.create_base_revolve', 'part.create_through_hole', 'part.set_hole_dimension', 'part.create_linear_hole_pattern', 'part.create_edge_fillet', 'sheet.create_l_profile', 'sheet.set_flat_state', 'sheet.set_parameters'],
            'Unexpected implemented mutation catalog.')
    require(info['capabilities']['pdm'] is False and info['capabilities']['simulation'] is False,
            'Unimplemented modules must not be advertised.')
    require(info['export_output_configured'] is False, 'Metadata smoke unexpectedly configured exports.')
    require(info['mcp_sdk_version'] == metadata.version('mcp'), 'Console uses a different MCP SDK environment.')
    schemas = json.dumps([tool.model_dump(mode='json', exclude_none=True) for tool in tools],
                         sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    actual_hash = hashlib.sha256(schemas.encode('utf8')).hexdigest()
    require(info['schema_hash'] == actual_hash, 'MCP schema hash does not match tools/list.')
    return {'public_tool_count': len(names), 'tool_names': sorted(names),
            'schema_hash': actual_hash, 'output_schemas_verified': True,
            'mcp_sdk_version': info['mcp_sdk_version'], 'build_matches_installed_wheel': True}


async def check(entry, state, wheel):
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=str(entry), args=['--state-dir', str(state)],
                                   env={**os.environ, 'PYTHONPATH': '', 'PYTHONNOUSERSITE': '1'})
    with anyio.fail_after(45):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                raw = await client.call_tool('system_get_info', {})
                require(raw.isError is False and type(raw.structuredContent) is dict,
                        'Missing structured metadata response.')
                response = raw.structuredContent
                require(response['status'] == 'succeeded' and response['error'] is None,
                        'Metadata tool failed.')
                return verify_metadata(tools, response['data'], wheel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    private = Path(__file__).resolve().parents[1] / 'work'
    args.state_dir, args.report = args.state_dir.resolve(), args.report.resolve()
    require(all(path.is_relative_to(private) for path in (args.state_dir, args.report)),
            'Smoke state/report must stay in private work/.')
    require(not args.state_dir.exists() and not args.report.exists(), 'Use fresh smoke state/report paths.')
    report = {'accepted': False, 'scope': 'installed_wheel_console_metadata_v1',
              'native_acceptance': False, 'cad_tools_called': [], 'job_tools_called': [],
              'public_registry_publication_verified': False}
    try:
        wheel = validate_wheel(args.wheel, expected_version=args.expected_version,
                               expected_git_sha=args.expected_git_sha)
        report['wheel'] = wheel
        entry = installed_identity(wheel)
        args.state_dir.mkdir(parents=True)
        report['runtime'] = {'python_version': '.'.join(map(str, sys.version_info[:3])),
                             'platform': sys.platform,
                             'installed_dependencies': dict(sorted((distribution.metadata['Name'], distribution.version)
                                 for distribution in metadata.distributions()))}
        report['metadata_catalog'] = asyncio.run(check(entry, args.state_dir, wheel))
        report['accepted'] = True
    except BaseException as error:
        report['error_type'] = type(error).__name__
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open('x', encoding='utf8') as stream:
                json.dump(report, stream, allow_nan=False, indent=2)
        except BaseException as report_error:
            error.add_note('Metadata smoke report write failed: ' + type(report_error).__name__)
        raise
    else:
        with args.report.open('x', encoding='utf8') as stream:
            json.dump(report, stream, allow_nan=False, indent=2)
        print(json.dumps({'accepted': True, 'package_version': wheel['package_version'],
                          'public_tool_count': report['metadata_catalog']['public_tool_count'],
                          'native_acceptance': False, 'cad_tools_called': []}))


if __name__ == '__main__':
    main()
