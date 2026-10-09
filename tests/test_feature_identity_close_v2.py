"""Canonical equality can perform native QI and dispatch a closing notification."""

import hashlib

import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.jobs import ExecutionFailure, _json
from test_feature_domain_v2 import setup


class CanonicalIdentity:
    __hash__ = None

    def __init__(self, key, generation, closing, calls, callback):
        self.key, self.generation, self.closing = key, generation, closing
        self.calls, self.callback = calls, callback

    def __eq__(self, other):
        self.calls.append('identity.compare')
        if not isinstance(other, CanonicalIdentity):
            return False
        if self.generation == other.generation and self.closing != other.closing:
            self.callback()
        return self.key is other.key


def canonical_getters(adapter, watch, monkeypatch, *, callback=lambda: None, closing_key='same'):
    original, original_poll = adapter.configuration_identity, watch.poll
    calls, getters = [], []
    def configuration(model, name):
        key = original(model, name)
        getters.append(name)
        closing = len(getters) % 2 == 0
        calls.append('configuration')
        if closing and closing_key == 'missing':
            return None
        if closing and closing_key == 'changed':
            key = object()
        return CanonicalIdentity(key, (len(getters) - 1) // 2, closing, calls, callback)
    def poll():
        calls.append('watch.poll')
        return original_poll()
    monkeypatch.setattr(adapter, 'configuration_identity', configuration)
    monkeypatch.setattr(watch, 'poll', poll)
    return calls, getters


@pytest.mark.parametrize('change', ['event_only', 'name_with_event'])
def test_closing_canonical_equality_notification_invalidates_feature_capture(setup, monkeypatch, change):
    adapter, _, catalog, _, ids = setup
    catalog._state(ids[0], 'Основная')
    model = adapter.models[0]
    watch = adapter.watches[id(model.identity)]
    stamp = model.state['update_stamp']
    def notify():
        if change == 'name_with_event':
            model.features[0].state['name'] = 'Позднее изменение при QI'
        watch.sequence += 1
    calls, getters = canonical_getters(adapter, watch, monkeypatch, callback=notify)
    with pytest.raises(ExecutionFailure) as error:
        catalog._state(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read' and not error.value.uncertain
    assert getters == ['Основная', 'Основная']
    assert calls[-2:] == ['identity.compare', 'watch.poll']
    assert watch.sequence == 1 and model.state['update_stamp'] == stamp
    assert adapter.writes == []


def test_stable_fresh_canonical_wrappers_keep_revision_and_compare_before_last_poll(setup, monkeypatch):
    adapter, _, catalog, _, ids = setup
    baseline = catalog._state(ids[0], 'Основная')
    watch = adapter.watches[id(adapter.models[0].identity)]
    calls, _ = canonical_getters(adapter, watch, monkeypatch)
    first = catalog._state(ids[0], 'Основная')
    # The initial switch from plain fake identity creates one new configuration
    # epoch. Further fresh wrappers for that canonical identity must retain it.
    calls.clear()
    second = catalog._state(ids[0], 'Основная')
    assert calls[-2:] == ['identity.compare', 'watch.poll']
    assert second[4] == first[4]
    assert second[3]['features'] == baseline[3]['features']
    assert second[4] == 'rev_' + hashlib.sha256(_json(second[5]).encode('utf8')).hexdigest()
    assert second[5]['event_sequence'] == watch.sequence == 0
    assert adapter.writes == []


@pytest.mark.parametrize('closing_key', ['missing', 'changed'])
def test_missing_or_changed_closing_identity_is_rejected_without_notification(setup, monkeypatch, closing_key):
    adapter, _, catalog, _, ids = setup
    catalog._state(ids[0], 'Основная')
    watch = adapter.watches[id(adapter.models[0].identity)]
    calls, _ = canonical_getters(adapter, watch, monkeypatch, closing_key=closing_key)
    with pytest.raises(ExecutionFailure) as error:
        catalog._state(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read' and not error.value.uncertain
    assert calls[-1] == 'watch.poll' and watch.sequence == 0 and adapter.writes == []


def test_closing_identity_comparison_failure_propagates_without_false_snapshot(setup, monkeypatch):
    adapter, _, catalog, _, ids = setup
    catalog._state(ids[0], 'Основная')
    watch = adapter.watches[id(adapter.models[0].identity)]
    failure = rejected('native_identity_read_failed', 'Canonical native comparison failed.')
    def fail():
        raise failure
    calls, _ = canonical_getters(adapter, watch, monkeypatch, callback=fail)
    with pytest.raises(ExecutionFailure) as error:
        catalog._state(ids[0], 'Основная')
    assert error.value is failure and not error.value.uncertain
    assert calls[-1] == 'identity.compare'
    assert calls.count('watch.poll') == 1 and adapter.writes == []
