"""Exact no-op preference policy through real adapter methods, with no COM."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.exports_v2 import ExportOptions
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.mutations import MutationCoordinator, PreparedMutation
from test_exports_v2 import InlineWorker, native_adapter_module


class PreferenceApplication:
    """Native getter/setter stand-in; hooks model false results and coupling."""

    def __init__(self, module, state):
        self.state = state
        self.ids = {(kind, code): name for name, (kind, code) in module.PREFERENCES.items()}
        self.gets, self.sets = [], []
        self.on_get = None
        self.on_set = None

    def __getattr__(self, method):
        getters = {'GetUserPreferenceStringValue': 'String',
                   'GetUserPreferenceIntegerValue': 'Integer',
                   'GetUserPreferenceToggle': 'Toggle', 'GetUserPreferenceDoubleValue': 'Double'}
        setters = {'SetUserPreferenceStringValue': 'String',
                   'SetUserPreferenceIntegerValue': 'Integer',
                   'SetUserPreferenceToggle': 'Toggle', 'SetUserPreferenceDoubleValue': 'Double'}
        if method in getters:
            def get(code):
                name = self.ids[getters[method], code]
                self.gets.append(name)
                if self.on_get:
                    self.on_get(name)
                return self.state[name]
            return get
        if method in setters:
            def set_value(code, value):
                name = self.ids[setters[method], code]
                self.sets.append((name, value))
                if self.on_set:
                    return self.on_set(name, value)
                self.state[name] = value
                return None if setters[method] == 'Toggle' else True
            return set_value
        raise AttributeError(method)


def fixture(module, file_format='parasolid', before=None):
    extension = {'stl': 'stl', 'step': 'step', 'parasolid': 'x_t'}[file_format]
    options = ExportOptions(file_format, f'never-written.{extension}', 'mm' if file_format == 'stl' else '')
    desired = module.desired_preferences(options)
    if file_format == 'stl':
        desired.update(stl_quality=3, stl_deviation_m=9.15190966989661e-7, stl_angle_rad=.0174532925199433)
    checkpoint = deepcopy(desired if before is None else before)
    if file_format == 'stl':
        for name in module.STL_PRESERVED_PREFERENCES:
            checkpoint.setdefault(name, desired[name])
            desired[name] = checkpoint[name]
    application = PreferenceApplication(module, deepcopy(checkpoint))
    adapter = module.CadExportsAdapter(SimpleNamespace(_sw=application))
    adapter._preflight = lambda model: None
    adapter.snapshot = lambda model: {'unchanged': True}
    saves = []
    def save(*args):
        saves.append((args, deepcopy(application.state)))
        assert application.state == desired
        return True, 0, 0
    adapter._extension = lambda model: SimpleNamespace(SaveAs3=save)
    return adapter, options, desired, checkpoint, application, saves


@pytest.mark.parametrize('file_format', ['stl', 'step', 'parasolid'])
@pytest.mark.parametrize('unused_setter', ['false', 'raise'])
def test_all_exact_noops_need_no_setter_and_reach_one_save_after_complete_readback(
        native_adapter_module, file_format, unused_setter):
    adapter, options, desired, before, application, saves = fixture(native_adapter_module, file_format)
    def forbidden_setter(name, value):
        if unused_setter == 'raise':
            raise RuntimeError('Native no-op setter would throw.')
        return False  # Some native settings reject an unchanged write.
    application.on_set = forbidden_setter
    reads_at_save = []
    extension = adapter._extension(object())
    native_save = extension.SaveAs3
    def observed_save(*args):
        reads_at_save.extend(application.gets)
        return native_save(*args)
    adapter._extension = lambda model: SimpleNamespace(SaveAs3=observed_save)
    result = adapter.export_part_to_file(object(), Path(options.filename), options, before)
    assert result['success'] is True and result['errors'] == result['warnings'] == 0
    assert application.sets == [] and application.state == before
    assert len(saves) == 1 and saves[0][1] == desired
    assert reads_at_save[-len(desired):] == list(desired)


def test_future_already_desired_setting_changed_by_prior_setter_is_not_overwritten(native_adapter_module):
    before = {'coordinate_system': 'Исходная система', 'parasolid_version': 0}
    adapter, options, _, checkpoint, application, saves = fixture(native_adapter_module, before=before)
    def coupled_setter(name, value):
        application.state[name] = value
        if name == 'coordinate_system' and value == '':
            application.state['parasolid_version'] = 77
        return True
    application.on_set = coupled_setter
    with pytest.raises(ExecutionFailure) as error:
        adapter.export_part_to_file(object(), Path(options.filename), options, checkpoint)
    assert error.value.code == 'stale_export_preferences' and saves == []
    assert application.state == {'coordinate_system': 'Исходная система', 'parasolid_version': 77}
    assert application.sets == [('coordinate_system', ''), ('coordinate_system', 'Исходная система')]


def test_last_guard_getter_changes_earlier_noop_and_complete_profile_refuses_save(native_adapter_module):
    adapter, options, _, before, application, saves = fixture(native_adapter_module, 'stl')
    def coupled_getter(name):
        # Initial full checkpoint read is first; the last per-setting guard is
        # second. Its side effect must not escape the final full-profile gate.
        if name == 'stl_preview' and application.gets.count(name) == 2:
            application.state['coordinate_system'] = 'Чужая система'
    application.on_get = coupled_getter
    with pytest.raises(ExecutionFailure) as error:
        adapter.export_part_to_file(object(), Path(options.filename), options, before)
    assert error.value.code == 'export_preference_write_failed' and saves == []
    assert application.sets == []  # No-op settings are never ours to restore.
    assert application.state['coordinate_system'] == 'Чужая система'


@pytest.mark.parametrize('fault,expected_status,expected_phase', [
    ('false_no_effect', 'failed', 'rolled_back'),
    ('false_after_apply', 'failed', 'rolled_back'),
    ('false_third_value', 'unknown', 'unresolved'),
    ('restore_false', 'unknown', 'unresolved'),
])
def test_changed_setter_must_confirm_and_unrestored_or_third_value_holds_application(
        native_adapter_module, tmp_path, fault, expected_status, expected_phase):
    before = {'coordinate_system': '', 'parasolid_version': 5}
    adapter, options, desired, checkpoint, application, saves = fixture(native_adapter_module, before=before)
    def failing_setter(name, value):
        assert name == 'parasolid_version'
        if value == desired[name]:
            if fault == 'false_third_value':
                application.state[name] = 77
            elif fault != 'false_no_effect':
                application.state[name] = value
            return False
        if fault == 'restore_false':
            return False
        application.state[name] = value
        return True
    application.on_set = failing_setter
    store = JobStore(tmp_path / 'jobs.sqlite')
    coordinator = MutationCoordinator(store, 'no_op_connection')
    def execute(operation_id):
        return coordinator.execute(operation_id, document_id='owned_fixture', configuration='Основная',
            expected_revision='preference_revision',
            prepare=lambda: PreparedMutation('preference_revision', {'preferences': checkpoint},
                                              effect_scope='application'),
            validate=lambda prepared: True,
            apply=lambda prepared: adapter.export_part_to_file(object(), Path(options.filename), options, checkpoint),
            inspect=lambda prepared: {'preferences': deepcopy(application.state)},
            verify=lambda before_state, after, result: after['preferences'] == before_state['preferences']
                and result['success'] is True,
            restore=lambda before_state, prepared: None,
            verify_restored=lambda before_state, after: after['preferences'] == before_state['preferences'])
    try:
        context = {'document_id': 'owned_fixture', 'configuration': 'Основная',
                   'expected_revision': 'preference_revision'}
        job = JobRunner(store, InlineWorker()).submit('preference-failure', 'internal.export', context,
            execute, context=context, mutates=True, pass_operation_id=True,
            verify=lambda result: result['verified'] is True)
        assert job['status'] == expected_status and job['mutation']['phase'] == expected_phase
        assert saves == [] and application.sets[0] == ('parasolid_version', 0)
        assert all(name != 'coordinate_system' for name, value in application.sets)
        assert bool(store.mutation_blockers('other_connection', 'other_document')) is (expected_status == 'unknown')
        if expected_status == 'failed':
            assert job['error']['code'] == 'export_preference_write_failed' and application.state == checkpoint
        else:
            assert job['error']['code'] == 'mutation_rollback_unconfirmed'
            assert application.state['parasolid_version'] == (77 if fault == 'false_third_value' else 0)
    finally:
        store.close()
