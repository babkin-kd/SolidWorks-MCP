"""B3 candidate preflight rejects wrong-wheel and incomplete catalog evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest


scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
try:
    import verify_b3_preflight as helper
finally:
    sys.path.remove(str(scripts))


@pytest.fixture
def reports():
    wheel = dict(wheel_sha256='a' * 64, package_version='fixture', git_sha='b' * 40)
    names = sorted(helper.SPECS)
    report = dict(accepted=True, scope='installed_wheel_console_metadata_v1',
        native_acceptance=False, cad_tools_called=[], job_tools_called=[], wheel=deepcopy(wheel),
        metadata_catalog=dict(tool_names=names, public_tool_count=len(names),
            schema_hash='c' * 64, output_schemas_verified=True, build_matches_installed_wheel=True))
    return report, wheel


def test_coherent_preflight_never_claims_native_or_allows_occupied_session(reports):
    result = helper.validate_metadata(*reports)
    assert result['accepted'] is True
    assert result['native_acceptance'] is result['cad_calls_started'] is result['can_start_native'] is False
    assert len(result['manifest']) == 13 and len(result['required_tools']) == 27


@pytest.mark.parametrize('key,value', [('accepted', False), ('scope', 'fake'),
    ('native_acceptance', True), ('cad_tools_called', ['document_list']), ('job_tools_called', ['job_get'])])
def test_nonmetadata_evidence_rejected(reports, key, value):
    report, wheel = reports
    report[key] = value
    with pytest.raises(ValueError):helper.validate_metadata(report, wheel)


@pytest.mark.parametrize('key', ['wheel_sha256', 'git_sha', 'package_version'])
def test_old_wheel_report_is_not_reusable(reports, key):
    report, wheel = reports
    report['wheel'][key] = 'another_candidate'
    with pytest.raises(ValueError):helper.validate_metadata(report, wheel)


@pytest.mark.parametrize('fault', ['missing_tool', 'duplicate', 'false_count', 'bool_count',
    'no_schema', 'schema_unverified', 'wrong_installed', 'malformed_hash'])
def test_incomplete_or_unverified_catalog_rejected(reports, fault):
    report, wheel = reports
    catalog = report['metadata_catalog']
    if fault == 'missing_tool':
        catalog['tool_names'].remove('measurement_get_mass')
        catalog['public_tool_count'] -= 1
    elif fault == 'duplicate':catalog['tool_names'].append(catalog['tool_names'][0])
    elif fault == 'false_count':catalog['public_tool_count'] += 1
    elif fault == 'bool_count':catalog['public_tool_count'] = True
    elif fault == 'no_schema':catalog.pop('schema_hash')
    elif fault == 'schema_unverified':catalog['output_schemas_verified'] = False
    elif fault == 'wrong_installed':catalog['build_matches_installed_wheel'] = False
    else:catalog['schema_hash'] = 'unverified'
    with pytest.raises(ValueError):helper.validate_metadata(report, wheel)


def test_additional_implemented_tools_do_not_require_b3_scope_expansion(reports):
    report, wheel = reports
    report['metadata_catalog']['tool_names'].append('part_create_corner_cut')
    report['metadata_catalog']['public_tool_count'] += 1
    assert 'part_create_corner_cut' not in helper.validate_metadata(report, wheel)['required_tools']
