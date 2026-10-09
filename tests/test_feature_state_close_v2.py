"""Pure closing-order regressions; no SolidWorks or COM acceptance claim."""

from copy import deepcopy
import hashlib

import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.features import SCOPE
from solidworks_mcp.jobs import ExecutionFailure, _json
from test_feature_domain_v2 import setup


@pytest.mark.parametrize('change', ['event_only', 'rename_with_event'])
def test_final_configuration_getter_notification_invalidates_feature_capture(setup, monkeypatch, change):
    adapter, _, catalog, _, ids = setup
    catalog._state(ids[0], 'Основная')
    model = adapter.models[0]
    watch = adapter.watches[id(model.identity)]
    stamp = model.state['update_stamp']
    original = adapter.configuration_identity
    calls = []
    def configuration(wrapper, name):
        result = original(wrapper, name)
        calls.append(name)
        if len(calls) == 2:
            if change == 'rename_with_event':
                model.features[0].state['name'] = 'Позднее переименование'
            watch.sequence += 1
        return result
    monkeypatch.setattr(adapter, 'configuration_identity', configuration)

    with pytest.raises(ExecutionFailure) as error:
        catalog._state(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'
    assert error.value.uncertain is False
    assert model.state['update_stamp'] == stamp
    assert calls == ['Основная', 'Основная']
    assert adapter.writes == []


@pytest.mark.parametrize('failure_at', ['configuration', 'watch'])
def test_final_native_getter_or_poll_failure_propagates_known_read_failure(setup, monkeypatch, failure_at):
    adapter, _, catalog, _, ids = setup
    catalog._state(ids[0], 'Основная')
    watch = adapter.watches[id(adapter.models[0].identity)]
    original_configuration = adapter.configuration_identity
    original_poll = watch.poll
    failure = rejected('native_close_read_failed', 'Closing native read is unavailable.')
    configuration_calls, poll_calls = [], []
    def configuration(wrapper, name):
        configuration_calls.append(name)
        if failure_at == 'configuration' and len(configuration_calls) == 2:
            raise failure
        return original_configuration(wrapper, name)
    def poll():
        poll_calls.append(True)
        if failure_at == 'watch' and len(poll_calls) == 2:
            raise failure
        return original_poll()
    monkeypatch.setattr(adapter, 'configuration_identity', configuration)
    monkeypatch.setattr(watch, 'poll', poll)

    with pytest.raises(ExecutionFailure) as error:
        catalog._state(ids[0], 'Основная')
    assert error.value is failure and error.value.uncertain is False
    assert len(configuration_calls) == 2
    assert len(poll_calls) == (1 if failure_at == 'configuration' else 2)
    assert adapter.writes == []


def test_stable_capture_keeps_legacy_revision_formula_and_poll_is_last_native_work(setup, monkeypatch):
    adapter, documents, catalog, _, ids = setup
    previous = catalog._state(ids[0], 'Основная')
    model = adapter.models[0]
    watch = adapter.watches[id(model.identity)]
    calls = []
    for name in ('documents', 'identity', 'snapshot', 'configuration_identity',
                 'features', 'feature_summary', 'pending_rebuild'):
        original = getattr(adapter, name)
        def observed(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(adapter, name, observed)
    original_poll = watch.poll
    def poll():
        calls.append('watch.poll')
        return original_poll()
    monkeypatch.setattr(watch, 'poll', poll)

    entry, identity, native, semantic, revision, payload = catalog._state(ids[0], 'Основная')
    assert calls[-2:] == ['configuration_identity', 'watch.poll']
    assert calls.count('watch.poll') == calls.count('configuration_identity') == 2
    assert revision == previous[4]
    assert identity is adapter.config_identity['Основная']
    assert native == model.features
    # Assert the pre-existing public revision contract, including observation,
    # event and mutation counters; this change must not narrow its coverage.
    observed = documents.resolve(ids[0], 'Основная')[1]
    expected = {'scope': SCOPE, 'connection_epoch': catalog.connection_epoch,
                'document_id': ids[0], 'configuration': 'Основная',
                'observed': observed, 'semantic': semantic,
                'event_sequence': watch.sequence,
                'mutation_sequence': entry.features.get('mutation_sequence', 0)}
    assert payload == expected
    assert revision == 'rev_' + hashlib.sha256(_json(expected).encode('utf8')).hexdigest()
    assert semantic['features'] == [deepcopy(item.state) for item in model.features]


def test_changed_closing_configuration_identity_is_still_rejected(setup, monkeypatch):
    adapter, _, catalog, _, ids = setup
    original = adapter.configuration_identity
    calls = []
    def configuration(wrapper, name):
        result = original(wrapper, name)
        calls.append(name)
        if len(calls) == 2:
            return object()
        return result
    monkeypatch.setattr(adapter, 'configuration_identity', configuration)
    with pytest.raises(ExecutionFailure) as error:
        catalog._state(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'
    assert error.value.uncertain is False


def test_document_metadata_change_retains_early_rejection_before_closing_native_work(setup, monkeypatch):
    adapter, _, catalog, _, ids = setup
    catalog._state(ids[0], 'Основная')
    watch = adapter.watches[id(adapter.models[0].identity)]
    original_pending = adapter.pending_rebuild
    original_configuration = adapter.configuration_identity
    original_poll = watch.poll
    calls = []
    def pending(wrapper):
        result = original_pending(wrapper)
        adapter.models[0].state['title'] = 'Изменённый документ'
        return result
    def configuration(wrapper, name):
        calls.append('configuration')
        return original_configuration(wrapper, name)
    def poll():
        calls.append('poll')
        return original_poll()
    monkeypatch.setattr(adapter, 'pending_rebuild', pending)
    monkeypatch.setattr(adapter, 'configuration_identity', configuration)
    monkeypatch.setattr(watch, 'poll', poll)
    with pytest.raises(ExecutionFailure) as error:
        catalog._state(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'
    assert calls == ['poll', 'configuration']
