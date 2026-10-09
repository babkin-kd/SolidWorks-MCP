"""Canonical equality may dispatch native notifications; pure Python simulation."""

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from test_dimension_domain_v2 import set_value, setup


class EqualityEffects:
    def __init__(self, adapter):
        self.adapter = adapter
        self.armed = None
        self.events = []
        self.comparisons = []
    def compare(self, tag):
        self.comparisons.append(tag)
        if tag == self.armed:
            self.armed = None
            self.events.append(tag)
            model = self.adapter.models[0]
            self.adapter.watches[id(model.identity)].sequence += 1


class NativeIdentity:
    __hash__ = None
    def __init__(self, key, tag, effects):
        self.key, self.tag, self.effects = key, tag, effects
    def __eq__(self, other):
        self.effects.compare(self.tag)
        return isinstance(other, NativeIdentity) and self.key == other.key


def native_equality(setup, monkeypatch):
    adapter, catalog, _, _ = setup
    effects = EqualityEffects(adapter)
    original_identity = adapter.identity
    original_configuration = adapter.configuration_identity
    def identity(obj):
        state = getattr(obj, 'state', {})
        tag = 'dimension' if 'parameter_type' in state else 'feature' if 'feature_type' in state else 'document'
        return NativeIdentity(original_identity(obj), tag, effects)
    def configuration(model, name):
        return NativeIdentity(original_configuration(model, name), 'configuration:' + name, effects)
    monkeypatch.setattr(adapter, 'identity', identity)
    monkeypatch.setattr(adapter, 'configuration_identity', configuration)
    # Existing explicit document IDs were created by the setup fixture before
    # installing COM-shaped identity wrappers. Preserve their canonical keys.
    for entry in catalog.documents._entries:
        entry.identity = NativeIdentity(entry.identity, 'document', effects)
    return effects


@pytest.mark.parametrize('tag', ['feature', 'configuration:Основная', 'configuration:Вариант'])
def test_capture_closes_after_all_native_equality_including_last_config_tuple(setup, monkeypatch, tag):
    adapter, catalog, _, ids = setup
    effects = native_equality(setup, monkeypatch)
    original_feature_state = catalog.features._state
    original_configuration = adapter.configuration_identity
    feature_calls = []
    def feature_state(*args):
        result = original_feature_state(*args)
        feature_calls.append(True)
        return result
    def configuration(model, name):
        result = original_configuration(model, name)
        if len(feature_calls) == 2 and name == 'Вариант':
            # Arm only after closing metadata and the final getter. The event
            # originates in subsequent equality, not in the getter itself.
            effects.armed = tag
        return result
    monkeypatch.setattr(catalog.features, '_state', feature_state)
    monkeypatch.setattr(adapter, 'configuration_identity', configuration)
    with pytest.raises(ExecutionFailure) as error:
        catalog._capture(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'
    assert effects.events == [tag]


@pytest.mark.parametrize('operation', ['state', 'list', 'get'])
@pytest.mark.parametrize('tag', ['feature', 'dimension', 'configuration:Основная'])
def test_pair_equality_has_its_own_close_after_second_capture(setup, monkeypatch, operation, tag):
    _, catalog, _, ids = setup
    effects = native_equality(setup, monkeypatch)
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    original_same = catalog._same_capture
    def same(first, second):
        effects.armed = tag
        return original_same(first, second)
    monkeypatch.setattr(catalog, '_same_capture', same)
    with pytest.raises(ExecutionFailure) as error:
        if operation == 'state':
            catalog._state(ids[0], 'Основная')
        elif operation == 'list':
            catalog.list(ids[0], 'Основная')
        else:
            catalog.get(ids[0], 'Основная', target)
    assert error.value.code == 'document_changed_during_read'
    assert effects.events == [tag]


def test_stable_native_equalities_preserve_scope_revision_full_rows_and_two_geometry_reads(setup, monkeypatch):
    adapter, catalog, _, ids = setup
    effects = native_equality(setup, monkeypatch)
    original_geometry = adapter.dimension_geometry_snapshot
    calls = []
    def geometry(model):
        calls.append(True)
        return original_geometry(model)
    monkeypatch.setattr(adapter, 'dimension_geometry_snapshot', geometry)
    page = catalog.list(ids[0], 'Основная')
    assert len(calls) == 2
    calls.clear()
    read = catalog.get(ids[0], 'Основная', page['items'][0]['object_id'])
    assert read['revision'] == page['revision'] and len(calls) == 2
    assert read['dimension']['reference_anchor'] and read['dimension']['native_incarnation']
    captured = catalog._paired_capture(ids[0], 'Основная')
    assert captured.event_sequence == 0
    assert len(captured.state) == 5
    assert set(captured.state[3]) == {'tree', 'configuration_epochs', 'dimensions', 'context', 'geometry'}
    assert effects.comparisons and effects.events == []


class CallbackCoordinator:
    """Run a selected domain callback without pretending a native job ran."""
    def __init__(self, adapter, effects, phase):
        self.adapter, self.effects, self.phase = adapter, effects, phase
        self.checkpoint = None
    def execute(self, operation_id, **callbacks):
        prepare = callbacks['prepare']
        if self.phase == 'prepare':
            return prepare()
        prepared = prepare()
        self.checkpoint = prepared.before
        if self.phase == 'validate':
            return callbacks['validate'](prepared)
        if self.phase == 'inspect':
            return callbacks['inspect'](prepared)
        assert self.phase == 'restore'
        self.adapter.models[0].dimensions[0].state['values_si']['Основная'] = .009
        return callbacks['restore'](prepared.before, prepared)


@pytest.mark.parametrize('phase', ['prepare', 'validate', 'inspect', 'restore'])
def test_mutation_resolution_equality_is_closed_before_baseline_return_or_restore_write(setup, monkeypatch, phase):
    adapter, catalog, _, ids = setup
    effects = native_equality(setup, monkeypatch)
    page = catalog.list(ids[0], 'Основная')
    target = page['items'][0]['object_id']
    coordinator = CallbackCoordinator(adapter, effects, phase)
    monkeypatch.setattr(catalog, 'coordinator', coordinator)
    original_resolve = catalog._resolve
    resolves = []
    def resolve(*args):
        resolves.append(True)
        if len(resolves) == (1 if phase == 'prepare' else 2):
            effects.armed = 'dimension'
        return original_resolve(*args)
    monkeypatch.setattr(catalog, '_resolve', resolve)
    with pytest.raises(ExecutionFailure) as error:
        catalog.set_value('artificial-callback', ids[0], 'Основная', target, page['revision'], 9., 'mm')
    assert error.value.code == 'document_changed_during_read'
    assert effects.events == ['dimension'] and adapter.dimension_writes == []
    if phase == 'restore':
        assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .009


def test_validate_last_target_identity_comparison_is_closed_before_allowing_setter(setup, monkeypatch):
    adapter, catalog, _, ids = setup
    effects = native_equality(setup, monkeypatch)
    page = catalog.list(ids[0], 'Основная')
    coordinator = CallbackCoordinator(adapter, effects, 'validate')
    monkeypatch.setattr(catalog, 'coordinator', coordinator)
    original_resolve = catalog._resolve
    resolves = []
    def resolve(*args):
        result = original_resolve(*args)
        resolves.append(True)
        if len(resolves) == 2:
            effects.armed = 'dimension'
        return result
    monkeypatch.setattr(catalog, '_resolve', resolve)
    with pytest.raises(ExecutionFailure) as error:
        catalog.set_value('artificial-validate', ids[0], 'Основная', page['items'][0]['object_id'], page['revision'], 9., 'mm')
    assert error.value.code == 'document_changed_during_read' and effects.events == ['dimension']
    assert adapter.dimension_writes == []


def test_actual_artificial_coordinator_does_not_checkpoint_late_prepare_identity_event(setup, monkeypatch):
    adapter, catalog, store, ids = setup
    effects = native_equality(setup, monkeypatch)
    page = catalog.list(ids[0], 'Основная')
    original_resolve = catalog._resolve
    def resolve(*args):
        effects.armed = 'dimension'
        return original_resolve(*args)
    monkeypatch.setattr(catalog, '_resolve', resolve)
    job = set_value(setup, object_id=page['items'][0]['object_id'], revision=page['revision'], value=9.)
    assert job['status'] == 'failed' and job['error']['code'] == 'document_changed_during_read'
    assert job.get('mutation') is None and adapter.dimension_writes == []
    assert store.mutation_blockers('connection_1', ids[0]) == []


@pytest.mark.parametrize('phase,resolve_number,outcome', [
    ('validate', 2, 'not_started'), ('inspect', 3, 'rolled_back'), ('restore', 3, 'unresolved')])
def test_actual_artificial_protocol_preserves_not_started_rollback_and_unknown_holds(setup, monkeypatch,
                                                                                 phase, resolve_number, outcome):
    adapter, catalog, store, ids = setup
    effects = native_equality(setup, monkeypatch)
    page = catalog.list(ids[0], 'Основная')
    original_resolve = catalog._resolve
    resolves = []
    def resolve(*args):
        resolves.append(True)
        if len(resolves) == resolve_number:
            effects.armed = 'dimension'
        return original_resolve(*args)
    monkeypatch.setattr(catalog, '_resolve', resolve)
    if phase == 'restore':
        adapter.dimension_fault = 'exception'
    job = set_value(setup, object_id=page['items'][0]['object_id'], revision=page['revision'], value=9.)
    assert effects.events == ['dimension'] and job['mutation']['phase'] == outcome
    if phase == 'validate':
        assert job['status'] == 'failed' and adapter.dimension_writes == []
    elif phase == 'inspect':
        assert job['status'] == 'failed'
        assert [write[1] for write in adapter.dimension_writes] == [.009, .01]
        assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .01
    else:
        assert job['status'] == 'unknown'
        assert [write[1] for write in adapter.dimension_writes] == [.009]
        assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .009
        assert store.mutation_blockers('connection_1', ids[0])


def test_stable_identity_equalities_allow_verified_real_artificial_mutation_protocol(setup, monkeypatch):
    adapter, catalog, _, ids = setup
    effects = native_equality(setup, monkeypatch)
    page = catalog.list(ids[0], 'Основная')
    job = set_value(setup, object_id=page['items'][0]['object_id'], revision=page['revision'], value=9.)
    assert job['status'] == 'succeeded' and job['mutation']['phase'] == 'committed'
    assert job['result']['verified'] is True and effects.events == []
    assert [write[1] for write in adapter.dimension_writes] == [.009]
