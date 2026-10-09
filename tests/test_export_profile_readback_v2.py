"""Full exact export-profile readback after coupled setters; pure adapter fakes."""

from copy import deepcopy
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.exports_v2 import ExportOptions
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.mutations import MutationCoordinator, PreparedMutation
from test_exports_v2 import InlineWorker, native_adapter_module


def preferences_fixture(module, fault=None):
    options = ExportOptions('stl', 'never-written.stl', 'mm')
    desired = module.desired_preferences(options)
    before = {name: (value + 1 if type(value) is int else not value if type(value) is bool
        else value + .5 if type(value) is float else 'Исходная система')
        for name, value in desired.items()}
    state, calls, saves = before.copy(), [], []
    adapter = module.CadExportsAdapter(SimpleNamespace())
    def getter(name):
        calls.append(('get', name))
        return state[name]
    def setter(name, value):
        calls.append(('set', name, value))
        state[name] = value
        # A later native setter may affect an earlier preference while still
        # confirming its own exact value. No actual COM is invoked here.
        if name == 'stl_angle_rad' and value == desired[name]:
            if fault == 'before':
                state['stl_deviation_m'] = before['stl_deviation_m']
            elif fault == 'third':
                state['stl_deviation_m'] = .12345
            elif fault == 'nextafter':
                state['stl_deviation_m'] = math.nextafter(desired['stl_deviation_m'], math.inf)
        assert state[name] == value
    def preflight(model):
        calls.append(('preflight',))
    def snapshot(model):
        calls.append(('snapshot',))
        return {'unchanged': True}
    def save(*args):
        calls.append(('SaveAs3',))
        saves.append((args, deepcopy(state)))
        return True, 0, 0
    def extension(model):
        calls.append(('extension',))
        if fault == 'extension_before':
            state['stl_deviation_m'] = before['stl_deviation_m']
        return SimpleNamespace(SaveAs3=save)
    adapter._get_preference, adapter._set_preference = getter, setter
    adapter._preflight, adapter.snapshot = preflight, snapshot
    adapter._extension = extension
    return adapter, options, desired, before, state, calls, saves


@pytest.mark.parametrize('fault', ['before', 'extension_before'])
def test_last_setter_or_extension_getter_returns_earlier_setting_to_before_refuses_save(native_adapter_module, fault):
    adapter, options, _, before, state, _, saves = preferences_fixture(native_adapter_module, fault)
    with pytest.raises(ExecutionFailure) as error:
        adapter.export_part_to_file(object(), Path('never-written.stl'), options, before)
    assert error.value.code == 'export_preference_write_failed'
    assert saves == [] and state == before


@pytest.mark.parametrize('fault', ['third', 'nextafter'])
def test_unowned_third_value_including_adjacent_float_is_preserved_without_save(native_adapter_module, fault):
    adapter, options, desired, before, state, _, saves = preferences_fixture(native_adapter_module, fault)
    with pytest.raises(ExecutionFailure) as error:
        adapter.export_part_to_file(object(), Path('never-written.stl'), options, before)
    assert error.value.code == 'export_preferences_restore_unconfirmed'
    assert error.value.__cause__.code == 'export_preference_write_failed'
    expected = .12345 if fault == 'third' else math.nextafter(desired['stl_deviation_m'], math.inf)
    assert state['stl_deviation_m'] == expected
    assert {name: value for name, value in state.items() if name != 'stl_deviation_m'} == {
        name: value for name, value in before.items() if name != 'stl_deviation_m'}
    assert saves == []


def test_unchanged_full_profile_is_read_after_final_metadata_then_actual_fake_save(native_adapter_module):
    adapter, options, desired, before, state, calls, saves = preferences_fixture(native_adapter_module)
    result = adapter.export_part_to_file(object(), Path('never-written.stl'), options, before)
    save_index = calls.index(('SaveAs3',))
    profile_reads = [('get', name) for name in desired]
    assert calls[save_index - len(profile_reads):save_index] == profile_reads
    assert calls[save_index - len(profile_reads) - 2:save_index - len(profile_reads)] == [('snapshot',), ('extension',)]
    assert len(saves) == 1 and saves[0][1] == desired
    assert saves[0][0] == ('never-written.stl', 0, 3, None, None, 0, 0)
    assert result['success'] is True and result['errors'] == result['warnings'] == 0
    assert state == before


@pytest.mark.parametrize('fault,expected_status,expected_phase', [
    ('before', 'failed', 'rolled_back'),
    ('third', 'unknown', 'unresolved'),
    (None, 'succeeded', 'committed'),
])
def test_real_journal_protocol_holds_unconfirmed_coupled_preferences(native_adapter_module, tmp_path,
                                                                    fault, expected_status, expected_phase):
    adapter, options, desired, before, state, _, saves = preferences_fixture(native_adapter_module, fault)
    store = JobStore(tmp_path / 'jobs.sqlite')
    coordinator = MutationCoordinator(store, 'connection_profile')
    def execute(operation_id):
        return coordinator.execute(operation_id, document_id='owned_fixture', configuration='Основная',
            expected_revision='exact_profile_revision',
            prepare=lambda: PreparedMutation('exact_profile_revision', {'preferences': before}, effect_scope='application'),
            validate=lambda prepared: True,
            apply=lambda prepared: adapter.export_part_to_file(object(), Path('never-written.stl'), options, before),
            inspect=lambda prepared: {'preferences': deepcopy(state)},
            verify=lambda checkpoint, after, result: after['preferences'] == checkpoint['preferences'] and result['success'] is True,
            # Adapter owns its finally restoration; never overwrite a third value.
            restore=lambda checkpoint, prepared: None,
            verify_restored=lambda checkpoint, after: after['preferences'] == checkpoint['preferences'])
    try:
        context = {'document_id': 'owned_fixture', 'configuration': 'Основная',
                   'expected_revision': 'exact_profile_revision'}
        job = JobRunner(store, InlineWorker()).submit('profile-case', 'internal.export.profile', context, execute,
            context=context,
            mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        assert job['status'] == expected_status and job['mutation']['phase'] == expected_phase
        blockers = store.mutation_blockers('different_connection', 'different_document')
        assert bool(blockers) is (fault == 'third')
        if fault == 'third':
            assert job['error']['code'] == 'mutation_rollback_unconfirmed'
            assert state['stl_deviation_m'] == .12345 and saves == []
        elif fault == 'before':
            assert job['error']['code'] == 'export_preference_write_failed'
            assert state == before and saves == []
        else:
            assert job['result']['verified'] is True and saves[0][1] == desired and state == before
    finally:
        store.close()
