"""Synthetic candidate acceptance, not installed-wheel or native CAD proof."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp.mass_properties import normalize_mass_properties
from solidworks_mcp.jobs import ExecutionFailure
from test_geometry_v2 import setup_geometry


def si():
    return {'volume_m3': 2e-6, 'surface_area_m2': .01, 'mass_kg': .0157,
            'density_kg_m3': 7850., 'center_of_mass_m': (-.001, .002, 0.)}


def test_si_conversion_and_negative_coordinates():
    assert normalize_mass_properties(si()) == {
        'volume_mm3': 2000., 'surface_area_mm2': 10000., 'mass_kg': .0157,
        'density_kg_m3': 7850., 'center_of_mass_mm': [-1., 2., 0.]}


@pytest.mark.parametrize('field,value', [
    ('volume_m3', 0), ('volume_m3', -1), ('volume_m3', float('nan')),
    ('volume_m3', float('inf')), ('volume_m3', True), ('mass_kg', '1'),
    ('mass_kg', 0), ('density_kg_m3', -1), ('density_kg_m3', float('nan')),
    ('surface_area_m2', 1e308), ('surface_area_m2', float('-inf')),
    ('center_of_mass_m', None), ('center_of_mass_m', [0, 1]),
    ('center_of_mass_m', [0, 1, 2, 3]), ('center_of_mass_m', [0, True, 0]),
    ('center_of_mass_m', [0, float('inf'), 0]), ('center_of_mass_m', [1e308, 0, 0]),
])
def test_invalid_or_overflowing_data_never_reaches_json(field, value):
    values = si()
    values[field] = value
    with pytest.raises(ExecutionFailure) as error:
        normalize_mass_properties(values)
    assert error.value.code == 'mass_properties_invalid'
    assert error.value.uncertain is False


@pytest.mark.parametrize('values', [None, {}, {'volume_m3': 1}])
def test_incomplete_values_fail(values):
    with pytest.raises(ExecutionFailure, match='incomplete or invalid'):
        normalize_mass_properties(values)


def test_mass_density_volume_inconsistency_is_explicit():
    values = si()
    values['mass_kg'] *= 2
    with pytest.raises(ExecutionFailure) as error:
        normalize_mass_properties(values)
    assert error.value.code == 'mass_properties_inconsistent'


def prepare(setup):
    adapter, documents, geometry, context, listed = setup
    calls = []
    def read(model, bodies):
        calls.append((model, bodies))
        return si()
    adapter.mass_properties = read
    return adapter, documents, geometry, context, listed, calls


def test_whole_part_selects_all_solids_and_skips_surface(setup_geometry):
    adapter, _, geometry, context, _, calls = prepare(setup_geometry)
    adapter.body()
    output = geometry.measure_mass(**context)
    assert output['body_count'] == 2 and output['body_id'] is None
    assert output['mass_properties']['volume_mm3'] == 2000
    assert output['density_source'] == 'solidworks_effective'
    assert output['includes_hidden_bodies'] is True
    assert all(body.body_type == 'solid' for body in calls[0][1])
    assert output['observation_revision'] == context['expected_observation_revision']


def test_explicit_body_scope_is_resolved_in_registered_document(setup_geometry):
    _, _, geometry, context, _, calls = prepare(setup_geometry)
    body_id = geometry.list(**context, body_type='solid')['items'][0]['object_id']
    output = geometry.measure_mass(**context, body_id=body_id)
    assert output['body_count'] == 1 and output['body_id'] == body_id
    assert len(calls[0][1]) == 1


def test_surface_body_never_calls_mass_api(setup_geometry):
    _, _, geometry, context, _, calls = prepare(setup_geometry)
    body_id = geometry.list(**context, body_type='surface')['items'][0]['object_id']
    with pytest.raises(ExecutionFailure) as error:
        geometry.measure_mass(**context, body_id=body_id)
    assert error.value.code == 'unsupported_body_type' and not calls


def test_empty_solid_configuration_is_rejected(setup_geometry):
    adapter, _, geometry, context, _, calls = prepare(setup_geometry)
    adapter.objects[adapter.models[0].identity] = []
    with pytest.raises(ExecutionFailure) as error:
        geometry.measure_mass(**context)
    assert error.value.code == 'no_solid_bodies' and not calls


@pytest.mark.parametrize('fault', ['stale', 'inactive', 'rebuild', 'foreign', 'face', 'closed', 'assembly'])
def test_invalid_context_does_not_calculate_mass(setup_geometry, fault):
    adapter, _, geometry, context, listed, calls = prepare(setup_geometry)
    arguments = deepcopy(context)
    if fault == 'stale': arguments['expected_observation_revision'] = 'old'
    if fault == 'inactive': arguments['configuration'] = 'Вариант'
    if fault == 'rebuild': adapter.needs_rebuild = True
    if fault in ('foreign', 'face'):
        body_id = geometry.list(**context, body_type='solid')['items'][0]['object_id']
        arguments['body_id'] = body_id
        if fault == 'foreign':
            arguments.update(document_id=listed[1]['document_id'], expected_observation_revision=listed[1]['observation_revision'])
        else:
            arguments['body_id'] = geometry.list(**context, kind='face', body_id=body_id)['items'][0]['object_id']
    if fault == 'closed': adapter.models.pop(0)
    if fault == 'assembly': adapter.models[0].state['document_type'] = 'assembly'
    with pytest.raises(ExecutionFailure): geometry.measure_mass(**arguments)
    assert not calls


@pytest.mark.parametrize('change', ['stamp', 'configuration_identity', 'rebuild', 'document_identity'])
def test_changed_snapshot_never_returns_measurement(setup_geometry, change):
    adapter, _, geometry, context, _, _ = prepare(setup_geometry)
    def read(model, bodies):
        if change == 'stamp': adapter.models[0].state['update_stamp'] += 1
        if change == 'configuration_identity': adapter.configurations[adapter.models[0].identity, 'Основная'] = object()
        if change == 'rebuild': adapter.needs_rebuild = True
        if change == 'document_identity': adapter.models[0].identity = object()
        return si()
    adapter.mass_properties = read
    with pytest.raises(ExecutionFailure): geometry.measure_mass(**context)
