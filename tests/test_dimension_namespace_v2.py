"""Early namespace denial never replaces native revision/identity verification."""

from copy import deepcopy

import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.jobs import ExecutionFailure
from test_dimension_domain_v2 import compound_dimension, dimension, set_value, setup
from test_feature_domain_v2 import feature


@pytest.mark.parametrize('operation', ['get', 'set'])
@pytest.mark.parametrize('case,code', [('foreign', 'object_reference_not_found'),
                                    ('unknown', 'object_reference_not_found'),
                                    ('configuration', 'object_configuration_mismatch'),
                                    ('missing_document', 'document_not_open'),
                                    ('missing_configuration', 'configuration_not_found')])
def test_namespace_rejection_precedes_expensive_geometry_and_native_resolution(setup, monkeypatch, operation, case, code):
    adapter, catalog, _, ids = setup
    page = catalog.list(ids[0], 'Основная')
    target = page['items'][0]['object_id']
    document, configuration = ids[0], 'Основная'
    if case == 'foreign':
        document = ids[1]
    elif case == 'unknown':
        target = 'dim_unknown'
    elif case == 'configuration':
        configuration = 'Вариант'
    elif case == 'missing_document':
        document = 'doc_unknown'
    else:
        configuration = 'Несуществующая'
    calls = []
    def forbidden_geometry(*args):
        calls.append('geometry')
        raise rejected('planar_brep_unsupported', 'Mixed native bodies must not mask a namespace rejection.')
    def forbidden_resolution(*args):
        calls.append('resolution')
        pytest.fail('Namespace denial must precede all native dimension resolution.')
    monkeypatch.setattr(adapter, 'dimension_geometry_snapshot', forbidden_geometry)
    monkeypatch.setattr(adapter, 'resolve_dimension_id', forbidden_resolution)
    if operation == 'get':
        with pytest.raises(ExecutionFailure) as error:
            catalog.get(document, configuration, target)
        assert error.value.code == code and error.value.uncertain is False
    else:
        job = set_value(setup, document=document, configuration=configuration,
                        object_id=target, revision=page['revision'])
        assert job['status'] == 'failed' and job['error']['code'] == code
        assert job['error']['requires_reconciliation'] is False
        assert 'mutation' not in job
    assert calls == [] and adapter.dimension_writes == []


@pytest.mark.parametrize('operation', ['get', 'set'])
def test_valid_namespace_still_runs_complete_captures_and_native_resolution(setup, monkeypatch, operation):
    adapter, catalog, _, ids = setup
    page = catalog.list(ids[0], 'Основная')
    target = page['items'][0]['object_id']
    geometry, resolution = [], []
    original_geometry = adapter.dimension_geometry_snapshot
    original_resolution = adapter.resolve_dimension_id
    def read_geometry(*args):
        geometry.append(True)
        return original_geometry(*args)
    def resolve(*args):
        resolution.append(True)
        return original_resolution(*args)
    monkeypatch.setattr(adapter, 'dimension_geometry_snapshot', read_geometry)
    monkeypatch.setattr(adapter, 'resolve_dimension_id', resolve)
    if operation == 'get':
        result = catalog.get(ids[0], 'Основная', target)
        assert result['revision'] == page['revision'] and len(geometry) == 2
        assert adapter.dimension_writes == []
    else:
        result = set_value(setup, object_id=target, revision=page['revision'], value=9.)
        assert result['status'] == 'succeeded' and result['mutation']['phase'] == 'committed'
        assert len(geometry) == 6 and len(adapter.dimension_writes) == 1
    assert resolution


@pytest.mark.parametrize('operation', ['get', 'set'])
@pytest.mark.parametrize('replacement', ['configuration', 'dimension', 'owner'])
def test_valid_namespace_never_bypasses_configuration_or_native_replacement_checks(setup, operation, replacement):
    adapter, catalog, _, ids = setup
    record, _ = compound_dimension(setup)
    page = catalog.list(ids[0], 'Основная')
    target = page['items'][0]['object_id']
    if replacement == 'configuration':
        adapter.config_identity['Основная'] = object()
        expected = 'object_configuration_mismatch'
    elif replacement == 'dimension':
        original = adapter.models[0].dimensions[1]
        replaced = dimension(2)
        replaced.pid, replaced.state = original.pid, deepcopy(original.state)
        adapter.models[0].dimensions[1] = replaced
        target = page['items'][1]['object_id']
        expected = 'persistent_reference_mismatch'
    else:
        original = record.owner
        replaced = feature(1)
        replaced.pid, replaced.state = original.pid, deepcopy(original.state)
        adapter.models[0].features[0] = replaced
        expected = 'persistent_reference_mismatch'
    if operation == 'get':
        with pytest.raises(ExecutionFailure) as error:
            catalog.get(ids[0], 'Основная', target)
        assert error.value.code == expected and error.value.uncertain is False
    else:
        result = set_value(setup, object_id=target, revision=page['revision'])
        assert result['status'] == 'failed' and result['error']['code'] == expected
        assert 'mutation' not in result
    assert adapter.dimension_writes == []


def test_valid_namespace_stale_revision_still_rejects_without_write(setup):
    adapter, catalog, _, ids = setup
    page = catalog.list(ids[0], 'Основная')
    adapter.models[0].dimensions[1].state['values_si']['Основная'] += .001
    result = set_value(setup, object_id=page['items'][0]['object_id'], revision=page['revision'])
    assert result['status'] == 'failed' and result['error']['code'] == 'stale_revision'
    assert 'mutation' not in result and adapter.dimension_writes == []
