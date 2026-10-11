"""Pure metadata gates; no console process, CAD runtime or journal is created."""
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from mcp.types import Tool
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_function(name):
    tree = ast.parse((ROOT / 'scripts/verify_installed_metadata.py').read_text(encoding='utf8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    catalog = next(node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'TOOLS' for target in node.targets))
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    namespace = {'require': require, 'TOOLS': frozenset(ast.literal_eval(catalog.value.args[0])),
                 'metadata': SimpleNamespace(version=lambda name: '1.30.0'),
                 'hashlib': hashlib, 'json': json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'metadata_gate', 'exec'), namespace)
    return namespace[function.name], namespace


@pytest.fixture
def example():
    verify, namespace = load_function('verify_metadata')
    tools = [Tool(name=name, inputSchema={'type': 'object'}, outputSchema={'type': 'object'})
             for name in sorted(namespace['TOOLS'])]
    wheel = {'package_version': '2.0.0.dev42', 'git_sha': 'a' * 40, 'source_digest': 'd' * 64}
    schemas = json.dumps([tool.model_dump(mode='json', exclude_none=True) for tool in tools],
                        sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    info = {'package_version': wheel['package_version'], 'api_version': 2,
            'build_matches_source': True, 'build': {**wheel, 'source_dirty': False},
            'source_digest': wheel['source_digest'], 'schema_version': '2.0-dev',
            'mutation_revision_scopes': ['part_mass_selection_measurement_v1', 'part_feature_tree_v1', 'part_dimension_values_v1', 'part_solid_brep_export_v1', 'empty_part_base_rectangle_v1', 'new_empty_part_document_v1', 'part_rectangular_sketch_dimension_v1', 'single_base_rectangular_corner_through_cut_v1', 'empty_part_full_turn_cylinder_revolve_v1', 'single_base_circular_through_hole_v1', 'single_base_circular_through_hole_dimension_v1', 'single_base_linear_through_hole_pattern_v1', 'single_base_selected_edge_fillet_v1', 'empty_part_sheet_l_profile_v1', 'single_l_sheet_flat_state_v1', 'single_l_sheet_parameters_v1', 'single_l_sheet_edge_flange_v1', 'single_u_sheet_flat_state_v1', 'native_document_current_file_save_v1', 'native_document_close_clean_v1', 'native_document_open_resolved_v1', 'native_first_save_replace_part_v1'],
            'development_candidate': True, 'implemented_mutations': ['measurement.mass', 'feature.rename', 'dimension.set_value', 'export.execute', 'part.create_base_extrusion', 'document.create_part', 'sketch.set_dimension', 'part.create_corner_cut', 'part.create_base_revolve', 'part.create_through_hole', 'part.set_hole_dimension', 'part.create_linear_hole_pattern', 'part.create_edge_fillet', 'sheet.create_l_profile', 'sheet.set_flat_state', 'sheet.set_parameters', 'sheet.create_edge_flange', 'sheet.set_flange_flat_state', 'document.save_native', 'document.close_native', 'document.open_native', 'document.first_save_native'],
            'capabilities': {'pdm': False, 'simulation': False}, 'export_output_configured': False,
            'mcp_sdk_version': '1.30.0', 'schema_hash': hashlib.sha256(schemas.encode()).hexdigest()}
    return verify, tools, info, wheel


def test_matching_implemented_catalog_is_only_metadata_evidence(example):
    verify, tools, info, wheel = example
    result = verify(tools, info, wheel)
    assert result['public_tool_count'] == 73 and result['output_schemas_verified'] is True
    assert 'native_acceptance' not in result


def test_prior_wheel_without_first_save_is_not_current_metadata_acceptance(example):
    verify, tools, info, wheel = example
    tools = [tool for tool in tools if tool.name not in {
        'document_prepare_first_save_native', 'document_first_save_native'}]
    info = copy.deepcopy(info)
    info['implemented_mutations'].remove('document.first_save_native')
    info['mutation_revision_scopes'].remove('native_first_save_replace_part_v1')
    with pytest.raises(ValueError):
        verify(tools, info, wheel)


@pytest.mark.parametrize('path,value', [
    ('package_version', 'wrong'), ('api_version', 1), ('build_matches_source', False),
    ('build.source_dirty', 0), ('build.git_sha', 'b' * 40), ('build.source_digest', '0' * 64),
    ('source_digest', '0' * 64), ('schema_version', 'legacy'), ('mutation_revision_scopes', ['unbounded']),
    ('development_candidate', False), ('implemented_mutations', ['feature.delete']),
    ('capabilities.pdm', True), ('capabilities.simulation', True), ('export_output_configured', True),
    ('mcp_sdk_version', 'different-environment'), ('schema_hash', '0' * 64),
])
def test_wrong_build_scope_or_unimplemented_module_is_not_metadata_acceptance(example, path, value):
    verify, tools, info, wheel = example
    info = copy.deepcopy(info)
    target = info
    parts = path.split('.')
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    with pytest.raises(ValueError):
        verify(tools, info, wheel)


@pytest.mark.parametrize('change', ['duplicate', 'alias', 'no_output_schema'])
def test_catalog_drift_or_missing_schema_fails(example, change):
    verify, tools, info, wheel = example
    tools = [tool.model_copy(deep=True) for tool in tools]
    if change == 'duplicate':
        tools.append(tools[0])
    elif change == 'alias':
        tools[0].name = 'legacy_alias'
    else:
        tools[0].outputSchema = None
    with pytest.raises(ValueError):
        verify(tools, info, wheel)


def test_source_pythonpath_is_rejected_before_package_import(monkeypatch):
    function, namespace = load_function('installed_identity')
    import os
    namespace['os'] = os
    monkeypatch.setenv('PYTHONPATH', 'some-source-checkout')
    with pytest.raises(ValueError, match='Unset PYTHONPATH'):
        function({})
