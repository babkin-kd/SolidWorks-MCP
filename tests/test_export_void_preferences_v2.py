"""Typed VOID Toggle versus BOOL setter contracts, using pure native stand-ins."""

from copy import deepcopy
from pathlib import Path

import pytest

from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.mutations import MutationCoordinator, PreparedMutation
from test_exports_v2 import InlineWorker, native_adapter_module
from test_export_noop_preferences_v2 import fixture


@pytest.mark.parametrize('name,before_value', [
    ('coordinate_system', 'Исходная система'), ('stl_units', 3),
    ('stl_deviation_m', .25), ('stl_binary', False),
])
def test_real_setter_confirms_documented_return_and_exact_readback(native_adapter_module, name, before_value):
    adapter, _, desired, _, application, _ = fixture(native_adapter_module, 'stl')
    application.state[name] = before_value
    adapter._set_preference(name, desired[name])
    assert application.state[name] == desired[name]
    assert application.sets == [(name, desired[name])] and application.gets == [name]


@pytest.mark.parametrize('unexpected', [True, False, 0, 1, ''])
def test_void_toggle_rejects_every_unexpected_non_none_result_even_if_applied(native_adapter_module, unexpected):
    adapter, _, desired, _, application, _ = fixture(native_adapter_module, 'stl')
    def applied_wrong_return(name, value):
        application.state[name] = value
        return unexpected
    application.on_set = applied_wrong_return
    with pytest.raises(ExecutionFailure) as error:
        adapter._set_preference('stl_binary', desired['stl_binary'])
    assert error.value.code == 'export_preference_write_failed'
    assert application.state['stl_binary'] == desired['stl_binary']


@pytest.mark.parametrize('name', ['coordinate_system', 'stl_units', 'stl_deviation_m'])
@pytest.mark.parametrize('unexpected', [False, None, 0, 1])
def test_bool_return_setters_do_not_accept_false_none_or_integer_even_if_applied(
        native_adapter_module, name, unexpected):
    adapter, _, desired, _, application, _ = fixture(native_adapter_module, 'stl')
    def applied_wrong_return(key, value):
        application.state[key] = value
        return unexpected
    application.on_set = applied_wrong_return
    with pytest.raises(ExecutionFailure) as error:
        adapter._set_preference(name, desired[name])
    assert error.value.code == 'export_preference_write_failed'
    assert application.state[name] == desired[name]


def test_void_toggle_applies_and_restores_with_other_typed_preferences_and_one_save(native_adapter_module):
    _, _, desired, _, _, _ = fixture(native_adapter_module, 'stl')
    before = {name: (not value if type(value) is bool else value + 1 if type(value) is int
        else value + .5 if type(value) is float else 'Исходная система') for name, value in desired.items()}
    adapter, options, desired, checkpoint, application, saves = fixture(native_adapter_module, 'stl', before)
    result = adapter.export_part_to_file(object(), Path(options.filename), options, checkpoint)
    assert result['success'] is True and result['errors'] == result['warnings'] == 0
    assert len(saves) == 1 and saves[0][1] == desired and application.state == checkpoint
    for name in desired:
        assert (name, desired[name]) in application.sets and (name, checkpoint[name]) in application.sets


@pytest.mark.parametrize('name', ['coordinate_system', 'stl_units', 'stl_deviation_m', 'stl_binary'])
def test_valid_typed_return_without_exact_readback_fails_before_save(native_adapter_module, name):
    _, _, desired, _, _, _ = fixture(native_adapter_module, 'stl')
    changed = {'coordinate_system': 'Исходная система', 'stl_units': 3,
               'stl_deviation_m': .25, 'stl_binary': False}[name]
    adapter, options, _, before, application, saves = fixture(native_adapter_module, 'stl',
        {**desired, name: changed})
    application.on_set = lambda key, value: None if native_adapter_module.PREFERENCES[key][0] == 'Toggle' else True
    with pytest.raises(ExecutionFailure) as error:
        adapter.export_part_to_file(object(), Path(options.filename), options, before)
    assert error.value.code == 'export_preference_write_failed' and saves == []
    assert application.state == before


def test_void_exception_after_apply_is_preserved_after_confirmed_restore(native_adapter_module):
    _, _, desired, _, _, _ = fixture(native_adapter_module, 'stl')
    adapter, options, _, before, application, saves = fixture(native_adapter_module, 'stl',
        {**desired, 'stl_binary': False})
    original = RuntimeError('Injected native VOID exception after partial apply.')
    def partial_then_raise(name, value):
        application.state[name] = value
        if value is True:
            raise original
        return None
    application.on_set = partial_then_raise
    with pytest.raises(RuntimeError) as error:
        adapter.export_part_to_file(object(), Path(options.filename), options, before)
    assert error.value is original and application.state == before and saves == []
    assert application.sets == [('stl_binary', True), ('stl_binary', False)]


@pytest.mark.parametrize('restore_fails', [False, True])
def test_void_partial_exception_uses_real_checkpoint_and_retains_global_hold_if_restore_unconfirmed(
        native_adapter_module, tmp_path, restore_fails):
    _, _, desired, _, _, _ = fixture(native_adapter_module, 'stl')
    adapter, options, _, before, application, saves = fixture(native_adapter_module, 'stl',
        {**desired, 'stl_binary': False})
    original = RuntimeError('Injected native exception after Toggle write.')
    def partial_then_raise(name, value):
        assert name == 'stl_binary'
        if value is True:
            application.state[name] = value
            raise original
        if restore_fails:
            raise RuntimeError('Injected failed VOID restore with desired setting retained.')
        application.state[name] = value
        return None
    application.on_set = partial_then_raise
    store = JobStore(tmp_path / 'jobs.sqlite')
    coordinator = MutationCoordinator(store, 'void_connection')
    def execute(operation_id):
        return coordinator.execute(operation_id, document_id='owned_fixture', configuration='Основная',
            expected_revision='void_revision',
            prepare=lambda: PreparedMutation('void_revision', {'preferences': before}, effect_scope='application'),
            validate=lambda prepared: True,
            apply=lambda prepared: adapter.export_part_to_file(object(), Path(options.filename), options, before),
            inspect=lambda prepared: {'preferences': deepcopy(application.state)},
            verify=lambda checkpoint, after, result: after['preferences'] == checkpoint['preferences']
                and result['success'] is True,
            restore=lambda checkpoint, prepared: None,
            verify_restored=lambda checkpoint, after: after['preferences'] == checkpoint['preferences'])
    try:
        context = {'document_id': 'owned_fixture', 'configuration': 'Основная', 'expected_revision': 'void_revision'}
        job = JobRunner(store, InlineWorker()).submit('void-failure', 'internal.export', context, execute,
            context=context, mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
        assert saves == [] and application.sets == [('stl_binary', True), ('stl_binary', False)]
        assert job['status'] == ('unknown' if restore_fails else 'failed')
        assert job['mutation']['phase'] == ('unresolved' if restore_fails else 'rolled_back')
        assert bool(store.mutation_blockers('other_connection', 'other_document')) is restore_fails
        assert application.state == ({**before, 'stl_binary': True} if restore_fails else before)
        if restore_fails:
            assert job['error']['code'] == 'mutation_rollback_unconfirmed'
    finally:
        store.close()
