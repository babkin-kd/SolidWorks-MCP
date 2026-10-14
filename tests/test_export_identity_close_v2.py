"""Export closing canonical equality is native work before the final event poll."""

from dataclasses import asdict
import hashlib

import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.exports_v2 import ExportOptions, SCOPE
from solidworks_mcp.jobs import ExecutionFailure, _json
from test_exports_v2 import setup


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


def canonical_getters(adapter, monkeypatch, *, callback=lambda: None, closing_key='same'):
    original, original_poll = adapter.configuration_identity, adapter.watch.poll
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
    monkeypatch.setattr(adapter.watch, 'poll', poll)
    return calls, getters


@pytest.mark.parametrize('change', ['event_only', 'geometry_with_event'])
def test_closing_canonical_equality_notification_invalidates_export_capture(setup, monkeypatch, change):
    adapter, _, exports, _, document_id, output = setup
    options = ExportOptions('stl', 'Проверка QI.stl', 'mm').checked()
    stamp = adapter.models[0].state['update_stamp']
    def notify():
        if change == 'geometry_with_event':
            adapter.geometry['fingerprint'] = 'changed-during-canonical-comparison'
        adapter.watch.sequence += 1
    calls, getters = canonical_getters(adapter, monkeypatch, callback=notify)
    with pytest.raises(ExecutionFailure) as error:
        exports._state(document_id, 'Основная', options)
    assert error.value.code == 'document_changed_during_read' and not error.value.uncertain
    assert calls[-2:] == ['identity.compare', 'watch.poll']
    assert getters == ['Основная', 'Основная']
    assert adapter.watch.sequence == 1 and adapter.models[0].state['update_stamp'] == stamp
    assert adapter.writes == 0 and list(output.iterdir()) == []


def test_stable_fresh_wrappers_keep_export_formula_and_no_comparison_follows_last_poll(setup, monkeypatch):
    adapter, documents, exports, _, document_id, output = setup
    options = ExportOptions('stl', 'Проверка QI.stl', 'mm').checked()
    calls, _ = canonical_getters(adapter, monkeypatch)
    first = exports._state(document_id, 'Основная', options)
    calls.clear()
    second = exports._state(document_id, 'Основная', options)
    assert calls[-2:] == ['identity.compare', 'watch.poll']
    assert second[1:] == first[1:]
    entry, revision, semantic, preferences = second
    observed = documents.resolve(document_id, 'Основная')[1]
    payload = {'scope': SCOPE, 'connection_epoch': exports.connection_epoch,
               'document_id': document_id, 'configuration': 'Основная',
               'configuration_epoch': entry.features['export_configurations']['Основная'][1],
               'observed': observed, 'semantic': semantic, 'preferences': preferences,
               'options': asdict(options), 'event_sequence': adapter.watch.sequence,
               'solidworks_revision': adapter.revision}
    assert revision == 'export_rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
    assert adapter.watch.sequence == 0 and adapter.writes == 0 and list(output.iterdir()) == []


@pytest.mark.parametrize('closing_key', ['missing', 'changed'])
def test_missing_or_changed_export_identity_is_rejected_even_without_event(setup, monkeypatch, closing_key):
    adapter, _, exports, _, document_id, output = setup
    calls, _ = canonical_getters(adapter, monkeypatch, closing_key=closing_key)
    with pytest.raises(ExecutionFailure) as error:
        exports._state(document_id, 'Основная', ExportOptions('stl', 'Проверка QI.stl', 'mm').checked())
    assert error.value.code == 'document_changed_during_read' and not error.value.uncertain
    assert calls[-1] == 'watch.poll' and adapter.watch.sequence == 0
    assert adapter.writes == 0 and list(output.iterdir()) == []


def test_export_identity_comparison_failure_propagates_before_final_poll(setup, monkeypatch):
    adapter, _, exports, _, document_id, output = setup
    failure = rejected('native_identity_read_failed', 'Canonical export identity comparison failed.')
    def fail():
        raise failure
    calls, _ = canonical_getters(adapter, monkeypatch, callback=fail)
    with pytest.raises(ExecutionFailure) as error:
        exports._state(document_id, 'Основная', ExportOptions('stl', 'Проверка QI.stl', 'mm').checked())
    assert error.value is failure and not error.value.uncertain
    assert calls[-1] == 'identity.compare' and calls.count('watch.poll') == 1
    assert adapter.writes == 0 and list(output.iterdir()) == []
