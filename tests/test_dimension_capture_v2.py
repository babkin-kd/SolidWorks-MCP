"""Pure capture/registration races and exact geometry read counts; no native CAD."""

from copy import deepcopy
import hashlib

import pytest

from solidworks_mcp.dimensions import SCOPE
from solidworks_mcp.jobs import ExecutionFailure, _json
from test_dimension_domain_v2 import compound_dimension, dimension, set_value, setup
from test_feature_domain_v2 import feature


def geometry_counter(adapter):
    calls = []
    original = adapter.dimension_geometry_snapshot
    def snapshot(model):
        calls.append(model)
        return original(model)
    adapter.dimension_geometry_snapshot = snapshot
    return calls


def test_list_get_and_mutation_state_each_take_two_complete_geometry_snapshots(setup):
    adapter, catalog, _, ids = setup
    calls = geometry_counter(adapter)
    page = catalog.list(ids[0], 'Основная')
    assert len(calls) == 2
    calls.clear()
    result = catalog.get(ids[0], 'Основная', page['items'][0]['object_id'])
    assert len(calls) == 2 and result['revision'] == page['revision']
    calls.clear()
    state = catalog._state(ids[0], 'Основная')
    assert len(calls) == 2 and state[4] == page['revision']
    assert adapter.dimension_writes == []


def test_capture_retains_complete_semantics_and_original_revision_hash_formula(setup):
    adapter, catalog, _, ids = setup
    compound_dimension(setup)
    exact = {'representation': 'fake_complete_brep', 'bodies': [{
        'surface': {'type': 'plane', 'parameters': [0., 0., 0., 0., 0., 1.]},
        'loops': [{'edges': [{'curve': 'line', 'start': [-2., 0., 0.], 'end': [3., 0., 0.]}]}],
        'orientation': True, 'topology': {'face_count': 6, 'edge_count': 12}}]}
    adapter.dimension_geometry_snapshot = lambda model: deepcopy(exact)
    captured = catalog._capture(ids[0], 'Основная')
    entry, identity, native, semantic, revision = captured.state
    assert set(semantic) == {'tree', 'configuration_epochs', 'dimensions', 'context', 'geometry'}
    assert semantic['geometry'] == exact
    assert semantic['context'] == adapter.context
    assert set(semantic['configuration_epochs']) == {'Основная', 'Вариант'}
    for record, row in zip(native, semantic['dimensions']):
        summary = adapter.dimension_summary(record, ['Основная', 'Вариант'])
        assert {key: row[key] for key in summary} == summary
        assert row['reference_anchor'] == adapter.dimension_persistent_id(entry.model, record)
        assert row['native_incarnation'].startswith('native_dim_')
    feature_state = catalog.features._state(ids[0], 'Основная')
    payload = {'scope': SCOPE, 'connection_epoch': catalog.connection_epoch, 'document_id': ids[0],
               'configuration': 'Основная', 'feature_revision': feature_state[4], 'semantic': semantic,
               'mutation_sequence': entry.features['dimensions'].get('mutation_sequence', 0)}
    assert revision == 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
    assert identity == adapter.config_identity['Основная']


def alter(setup, kind):
    adapter = setup[0]
    original = adapter.models[0]
    if kind == 'shape':
        original.state['unrelated_geometry'] = {'changed_exact_edge': [-3., 5., 0.]}
    elif kind == 'name':
        original.dimensions[0].state['full_name'] = 'D1@Изменённое выдавливание'
    elif kind == 'slot':
        record = original.dimensions[0]
        display, _ = record.display_slots[0]
        display.kind = 10
        display.targets[1] = record
        record.display_slots = [(display, 1)]
    elif kind == 'configuration':
        adapter.config_identity['Вариант'] = object()
    elif kind == 'event':
        adapter.watches[id(original.identity)].sequence += 1
    elif kind == 'context':
        adapter.context['equation_count'] = 1
    elif kind == 'tolerance':
        original.dimensions[1].state['tolerance'] = {'type': 2, 'values_si': [-.0001, .0002]}
    elif kind == 'other_configuration_value':
        original.dimensions[1].state['values_si']['Вариант'] += .005
    elif kind == 'member':
        original.dimensions[0].display_slots = []
    elif kind == 'native_dimension':
        previous = original.dimensions[1]
        replacement = dimension(2)
        replacement.pid, replacement.state = previous.pid, deepcopy(previous.state)
        original.dimensions[1] = replacement
    elif kind == 'native_owner':
        record = original.dimensions[0]
        previous = record.owner
        replacement = feature(1)
        replacement.pid, replacement.state = previous.pid, deepcopy(previous.state)
        original.features[0] = replacement
        record.owner = replacement
    elif kind == 'native_display':
        record = original.dimensions[0]
        previous, slot = record.display_slots[0]
        replacement = deepcopy(previous)
        replacement.targets[slot] = record
        record.display_slots = [(replacement, slot)]
        original.displays = [replacement]
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize('operation', ['list', 'get'])
@pytest.mark.parametrize('kind', ['shape', 'name', 'slot', 'configuration', 'event', 'member',
                                 'native_dimension', 'native_owner', 'native_display',
                                 'context', 'tolerance', 'other_configuration_value'])
def test_complete_second_capture_rejects_changes_after_registration_or_resolution(setup, monkeypatch, operation, kind):
    adapter, catalog, _, ids = setup
    compound_dimension(setup)
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    method = '_register' if operation == 'list' else '_resolve'
    original = getattr(catalog, method)
    changed = []
    def reference(*args, **kwargs):
        result = original(*args, **kwargs)
        if not changed:
            changed.append(True)
            alter(setup, kind)
        return result
    monkeypatch.setattr(catalog, method, reference)
    calls = geometry_counter(adapter)
    with pytest.raises(ExecutionFailure) as error:
        if operation == 'list':
            catalog.list(ids[0], 'Основная')
        else:
            catalog.get(ids[0], 'Основная', target)
    assert error.value.code == 'document_changed_during_read'
    assert len(calls) == 2 and changed == [True]
    assert adapter.dimension_writes == []


@pytest.mark.parametrize('operation', ['list', 'get'])
def test_second_full_brep_detects_shape_only_change_around_reference_work(setup, monkeypatch, operation):
    adapter, catalog, _, ids = setup
    exact = {'representation': 'fake_complete_boundary', 'surface_parameters': [0., 0., 0., 1., 0., 0.]}
    calls = []
    def geometry(model):
        calls.append(True)
        return deepcopy(exact)
    adapter.dimension_geometry_snapshot = geometry
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    calls.clear()
    method = '_register' if operation == 'list' else '_resolve'
    original = getattr(catalog, method)
    def reference(*args, **kwargs):
        result = original(*args, **kwargs)
        exact['surface_parameters'][0] = .001
        return result
    monkeypatch.setattr(catalog, method, reference)
    original_stamp = adapter.models[0].state['update_stamp']
    with pytest.raises(ExecutionFailure) as error:
        if operation == 'list':
            catalog.list(ids[0], 'Основная')
        else:
            catalog.get(ids[0], 'Основная', target)
    assert error.value.code == 'document_changed_during_read'
    assert len(calls) == 2 and adapter.models[0].state['update_stamp'] == original_stamp


@pytest.mark.parametrize('operation', ['list', 'get', 'state'])
@pytest.mark.parametrize('kind', ['feature_name', 'feature_error', 'feature_identity', 'configuration', 'event'])
def test_closing_feature_checks_reject_late_changes_at_end_of_brep_read(setup, operation, kind):
    adapter, catalog, _, ids = setup
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    original_geometry = adapter.dimension_geometry_snapshot
    calls = []
    def geometry(model):
        result = original_geometry(model)
        calls.append(True)
        if len(calls) == 1:
            if kind == 'feature_name':
                adapter.models[0].features[0].state['name'] = 'Позднее имя'
            elif kind == 'feature_error':
                adapter.models[0].features[0].state['error_code'] = 9
            elif kind == 'feature_identity':
                old = adapter.models[0].features[0]
                replacement = feature(1)
                replacement.pid, replacement.state = old.pid, deepcopy(old.state)
                adapter.models[0].features[0] = replacement
            else:
                alter(setup, kind)
        return result
    adapter.dimension_geometry_snapshot = geometry
    with pytest.raises(ExecutionFailure) as error:
        if operation == 'list':
            catalog.list(ids[0], 'Основная')
        elif operation == 'get':
            catalog.get(ids[0], 'Основная', target)
        else:
            catalog._state(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'
    assert len(calls) == 1


def test_paired_mutation_state_detects_exact_shape_change_without_stamp_or_mass_hint(setup):
    adapter, catalog, _, ids = setup
    exact = {'representation': 'fake_complete_boundary', 'curve_parameters': [0., 1., 2.]}
    count = []
    stamp = adapter.models[0].state['update_stamp']
    def geometry(model):
        result = deepcopy(exact)
        count.append(True)
        if len(count) == 1:
            exact['curve_parameters'][1] = 1.125
        return result
    adapter.dimension_geometry_snapshot = geometry
    with pytest.raises(ExecutionFailure) as error:
        catalog._state(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'
    assert adapter.models[0].state['update_stamp'] == stamp
    assert len(count) == 2


@pytest.mark.parametrize('kind', ['name', 'event'])
def test_feature_event_close_runs_after_final_named_configuration_identity_reads(setup, kind):
    adapter, catalog, _, ids = setup
    original_configuration = adapter.configuration_identity
    original_geometry = adapter.dimension_geometry_snapshot
    after_geometry = []
    changed = []
    def geometry(model):
        result = original_geometry(model)
        after_geometry.append(True)
        return result
    def configuration(model, name):
        result = original_configuration(model, name)
        if after_geometry and name == 'Вариант' and not changed:
            changed.append(True)
            if kind == 'name':
                adapter.models[0].features[0].state['name'] = 'Позднее имя после конфигурации'
            else:
                alter(setup, 'event')
        return result
    adapter.dimension_geometry_snapshot = geometry
    adapter.configuration_identity = configuration
    with pytest.raises(ExecutionFailure) as error:
        catalog._capture(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'
    assert changed == [True] and len(after_geometry) == 1


@pytest.mark.parametrize('kind', ['event', 'document_metadata', 'inactive_configuration'])
def test_last_closing_feature_identity_native_callback_is_covered_by_final_cheap_guard(setup, kind, monkeypatch):
    adapter, catalog, _, ids = setup
    # Initialise the watch so its poll ordering can be observed independently.
    catalog._capture(ids[0], 'Основная')
    original_feature_state = catalog.features._state
    original_identity = adapter.identity
    original_configuration = adapter.configuration_identity
    original_snapshot = adapter.snapshot
    watch = adapter.watches[id(adapter.models[0].identity)]
    original_poll = watch.poll
    feature_calls, changed, native_calls = [], [], []
    def feature_state(*args):
        result = original_feature_state(*args)
        feature_calls.append(True)
        return result
    def identity(obj):
        result = original_identity(obj)
        native_calls.append('identity')
        if len(feature_calls) == 2 and obj is adapter.models[0].features[0] and not changed:
            changed.append(True)
            if kind == 'event':
                adapter.models[0].features[0].state['name'] = 'Имя после последнего QueryInterface'
                watch.sequence += 1
            elif kind == 'document_metadata':
                adapter.models[0].state['update_stamp'] += 1
            else:
                adapter.config_identity['Вариант'] = object()
        return result
    def configuration(*args):
        native_calls.append('configuration_identity')
        return original_configuration(*args)
    def snapshot(*args):
        native_calls.append('document_metadata')
        return original_snapshot(*args)
    def poll():
        native_calls.append('event_poll')
        return original_poll()
    monkeypatch.setattr(catalog.features, '_state', feature_state)
    monkeypatch.setattr(adapter, 'identity', identity)
    monkeypatch.setattr(adapter, 'configuration_identity', configuration)
    monkeypatch.setattr(adapter, 'snapshot', snapshot)
    monkeypatch.setattr(watch, 'poll', poll)
    with pytest.raises(ExecutionFailure) as error:
        catalog._capture(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'
    assert changed == [True] and native_calls[-1] == 'event_poll'


def install_transient_summary_outside_capture(adapter, catalog, monkeypatch):
    # Simulate 7→9→7 only when somebody performs an extra summary read outside
    # the complete captures. Such a read must never supply response/baseline.
    original_capture = catalog._capture
    original_summary = adapter.dimension_summary
    capture_depth, outside_reads = [], []
    def capture(*args):
        capture_depth.append(True)
        try:
            return original_capture(*args)
        finally:
            capture_depth.pop()
    def summary(record, configurations):
        if capture_depth:
            return original_summary(record, configurations)
        outside_reads.append(record)
        before = record.state['values_si']['Основная']
        try:
            record.state['values_si']['Основная'] = .009
            return original_summary(record, configurations)
        finally:
            record.state['values_si']['Основная'] = before
    monkeypatch.setattr(catalog, '_capture', capture)
    monkeypatch.setattr(adapter, 'dimension_summary', summary)
    return outside_reads


def test_get_response_is_deepcopy_of_revision_row_and_never_transient_extra_summary(setup, monkeypatch):
    adapter, catalog, _, ids = setup
    adapter.models[0].dimensions[0].state['values_si']['Основная'] = .007
    page = catalog.list(ids[0], 'Основная')
    target = page['items'][0]['object_id']
    outside_reads = install_transient_summary_outside_capture(adapter, catalog, monkeypatch)
    result = catalog.get(ids[0], 'Основная', target)
    expected = {key: value for key, value in page['items'][0].items()
                if key not in ('persistent_reference_supported', 'reference_error')}
    assert result['dimension'] == expected and result['revision'] == page['revision']
    assert outside_reads == []
    assert result['dimension']['reference_anchor'] and result['dimension']['native_incarnation']
    result['dimension']['values_si']['Основная'] = .099
    again = catalog.get(ids[0], 'Основная', target)
    assert again['dimension']['values_si']['Основная'] == .007 and again['revision'] == page['revision']


@pytest.mark.parametrize('fault', [None, 'exception'])
def test_mutation_before_inspect_and_restore_share_captured_row_without_extra_summary_aba(setup, monkeypatch, fault):
    adapter, catalog, _, ids = setup
    adapter.models[0].dimensions[0].state['values_si']['Основная'] = .007
    page = catalog.list(ids[0], 'Основная')
    target = page['items'][0]['object_id']
    outside_reads = install_transient_summary_outside_capture(adapter, catalog, monkeypatch)
    adapter.dimension_fault = fault
    result = set_value(setup, object_id=target, revision=page['revision'], value=9.)
    assert outside_reads == []
    before = result['mutation']['before_state']
    assert before['value_si'] == .007
    assert before['semantic']['dimensions'][0]['values_si']['Основная'] == .007
    assert before['semantic']['dimensions'][0]['reference_anchor']
    if fault:
        assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back'
        assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .007
        assert [write[1] for write in adapter.dimension_writes] == [.009, .007]
    else:
        assert result['status'] == 'succeeded' and result['mutation']['phase'] == 'committed'
        assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .009
        assert [write[1] for write in adapter.dimension_writes] == [.009]
