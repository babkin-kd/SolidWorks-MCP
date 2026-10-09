"""Preserved native STL resolution remains exact protected checkpoint state."""
from copy import deepcopy
from dataclasses import replace
import math
from pathlib import Path

import pytest

from solidworks_mcp.jobs import ExecutionFailure, JobRunner
from test_exports_v2 import InlineWorker, native_adapter_module, setup
from test_export_noop_preferences_v2 import fixture


@pytest.mark.parametrize('quality', [1, 2, 3])
@pytest.mark.parametrize('units', ['mm', 'm', 'in'])
def test_native_existing_resolution_is_captured_exactly_but_never_set_or_restored(
        native_adapter_module, quality, units):
    module = native_adapter_module
    _, _, default, _, _, _ = fixture(module, 'stl')
    before = {**default, 'coordinate_system': 'Исходная система', 'stl_units': 0,
        'stl_positive_translation_disabled': False, 'stl_show_info': True,
        'stl_quality': quality, 'stl_deviation_m': math.nextafter(9.15190966989661e-7, math.inf),
        'stl_angle_rad': math.nextafter(.0174532925199433, math.inf)}
    adapter, options, _, checkpoint, application, _ = fixture(module, 'stl', before)
    options = replace(options, units=units)
    captured = adapter.export_preferences(options)
    assert captured == before
    expected = {**before, **module.desired_preferences(options)}
    saved = []
    def save(*args):
        saved.append(deepcopy(application.state))
        assert application.state == expected
        return True, 0, 0
    adapter._extension = lambda model: type('Extension', (), {'SaveAs3': staticmethod(save)})()
    result = adapter.export_part_to_file(object(), Path(options.filename), options, checkpoint)
    assert result['success'] is True and saved == [expected] and application.state == before
    assert all(name not in module.STL_PRESERVED_PREFERENCES for name, value in application.sets)
    assert all(application.state[name].hex() == before[name].hex()
               for name in ('stl_deviation_m', 'stl_angle_rad'))
    profile = adapter.export_profile(options)
    assert profile['resolution_policy'] == 'preserve_existing_native'
    assert profile['effective_resolution_reference'] == 'durable_before_state.preferences'
    assert profile['preserved_application_preferences'] == list(module.STL_PRESERVED_PREFERENCES)
    assert not set(module.STL_PRESERVED_PREFERENCES) & set(profile['desired_application_preferences'])


@pytest.mark.parametrize('name', ['stl_quality', 'stl_deviation_m', 'stl_angle_rad'])
def test_units_setter_coupling_changes_protected_resolution_and_is_not_claimed_as_owned(native_adapter_module, name):
    module = native_adapter_module
    _, _, desired, _, _, _ = fixture(module, 'stl')
    before = {**desired, 'stl_units': 3}
    adapter, options, _, checkpoint, application, saves = fixture(module, 'stl', before)
    third = 2 if name == 'stl_quality' else math.nextafter(before[name], math.inf)
    def coupling(key, value):
        application.state[key] = value
        if key == 'stl_units' and value == 0:
            application.state[name] = third
        return None if module.PREFERENCES[key][0] == 'Toggle' else True
    application.on_set = coupling
    with pytest.raises(ExecutionFailure) as error:
        adapter.export_part_to_file(object(), Path(options.filename), options, checkpoint)
    assert error.value.code == 'export_preferences_restore_unconfirmed'
    assert error.value.__cause__.code == 'export_preference_write_failed'
    assert saves == [] and application.state == {**before, name: third}
    assert application.sets == [('stl_units', 0), ('stl_units', 3)]
    assert 'externally' not in str(error.value)


@pytest.mark.parametrize('name', ['stl_quality', 'stl_deviation_m', 'stl_angle_rad'])
def test_protected_change_during_native_save_is_not_hidden_by_success_or_restore(native_adapter_module, name):
    adapter, options, _, checkpoint, application, _ = fixture(native_adapter_module, 'stl')
    changed = 2 if name == 'stl_quality' else math.nextafter(checkpoint[name], math.inf)
    def save(*args):
        application.state[name] = changed
        return True, 0, 0
    adapter._extension = lambda model: type('Extension', (), {'SaveAs3': staticmethod(save)})()
    with pytest.raises(ExecutionFailure) as error:
        adapter.export_part_to_file(object(), Path(options.filename), options, checkpoint)
    assert error.value.code == 'export_preferences_restore_unconfirmed'
    assert application.state[name] == changed and application.sets == []


@pytest.mark.parametrize('name', ['stl_quality', 'stl_deviation_m', 'stl_angle_rad'])
def test_actual_domain_revision_includes_preserved_resolution_and_rejects_old_prepare_before_writes(
        native_adapter_module, setup, name):
    base, _, catalog, store, document_id, output = setup
    native, _, _, _, application, saves = fixture(native_adapter_module, 'stl')
    # Real profile/preference methods, pure domain source/identity stand-ins.
    # No analytical geometry/native acceptance is claimed by this composition.
    native.documents_adapter = base
    native._sw = application
    native.export_document_is_active = base.export_document_is_active
    native.export_source_snapshot = base.export_source_snapshot
    catalog.adapter = native
    prepared = catalog.prepare(document_id, 'Основная', 'stl', 'Контрольный экспорт.stl', 'mm')
    assert prepared['source']['export_profile']['resolution_policy'] == 'preserve_existing_native'
    before_value = application.state[name]
    application.state[name] = 2 if name == 'stl_quality' else math.nextafter(before_value, math.inf)
    current = catalog.prepare(document_id, 'Основная', 'stl', 'Контрольный экспорт.stl', 'mm')
    assert prepared['revision'] != current['revision']
    arguments = {'document_id': document_id, 'configuration': 'Основная',
        'expected_revision': prepared['revision'], 'format': 'stl', 'filename': 'Контрольный экспорт.stl', 'units': 'mm'}
    context = {key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')}
    job = JobRunner(store, InlineWorker()).submit('preserved-stale', 'internal.export', arguments,
        lambda operation_id: catalog.execute(operation_id, **arguments), context=context,
        mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
    assert job['status'] == 'failed' and job['error']['code'] == 'stale_revision'
    assert store.get(job['operation_id']).get('mutation') is None
    assert application.sets == [] and saves == [] and list(output.iterdir()) == []
