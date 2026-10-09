"""Pure export capture closing races; no native export/acceptance claim."""

from dataclasses import asdict
import hashlib

import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.exports_v2 import ExportOptions, SCOPE
from solidworks_mcp.jobs import ExecutionFailure, _json
from test_exports_v2 import setup


@pytest.mark.parametrize('getter', ['configuration_identity', 'export_document_is_active'])
def test_late_closing_native_getter_notification_invalidates_export_snapshot(setup, monkeypatch, getter):
    adapter, _, exports, _, document_id, output = setup
    options = ExportOptions('stl', 'Контрольный экспорт.stl', 'mm').checked()
    stamp = adapter.models[0].state['update_stamp']
    original = getattr(adapter, getter)
    calls = []
    def changed(*args):
        result = original(*args)
        calls.append(True)
        if len(calls) == 2:
            adapter.geometry['fingerprint'] = 'late-native-change-without-stamp'
            adapter.watch.sequence += 1
        return result
    monkeypatch.setattr(adapter, getter, changed)
    with pytest.raises(ExecutionFailure) as error:
        exports._state(document_id, 'Основная', options)
    assert error.value.code == 'document_changed_during_read' and error.value.uncertain is False
    assert calls == [True, True] and adapter.models[0].state['update_stamp'] == stamp
    assert adapter.writes == 0 and list(output.iterdir()) == []


@pytest.mark.parametrize('failure_at', ['configuration_identity', 'export_document_is_active', 'watch'])
def test_closing_export_native_errors_propagate_without_write_or_false_snapshot(setup, monkeypatch, failure_at):
    adapter, _, exports, _, document_id, output = setup
    options = ExportOptions('stl', 'Контрольный экспорт.stl', 'mm').checked()
    calls = []
    failure = rejected('native_close_read_failed', 'Closing native export observation failed.')
    for name in ('configuration_identity', 'export_document_is_active'):
        original = getattr(adapter, name)
        count = []
        def getter(*args, _name=name, _original=original, _count=count):
            _count.append(True)
            calls.append(_name)
            if failure_at == _name and len(_count) == 2:
                raise failure
            return _original(*args)
        monkeypatch.setattr(adapter, name, getter)
    original_poll, polls = adapter.watch.poll, []
    def poll():
        polls.append(True)
        calls.append('watch')
        if failure_at == 'watch' and len(polls) == 2:
            raise failure
        return original_poll()
    monkeypatch.setattr(adapter.watch, 'poll', poll)
    with pytest.raises(ExecutionFailure) as error:
        exports._state(document_id, 'Основная', options)
    assert error.value is failure and error.value.uncertain is False
    assert calls[-1] == failure_at
    assert len(polls) == (2 if failure_at == 'watch' else 1)
    if failure_at == 'watch':
        assert calls[-3:] == ['configuration_identity', 'export_document_is_active', 'watch']
    assert adapter.writes == 0 and list(output.iterdir()) == []


def test_stable_export_capture_keeps_revision_formula_and_poll_is_last_native_work(setup, monkeypatch):
    adapter, documents, exports, _, document_id, _ = setup
    options = ExportOptions('stl', 'Контрольный экспорт.stl', 'mm').checked()
    previous = exports._state(document_id, 'Основная', options)
    calls = []
    for name in ('documents', 'identity', 'snapshot', 'configuration_identity',
                 'export_document_is_active', 'export_source_snapshot', 'export_preferences', 'export_profile'):
        original = getattr(adapter, name)
        def observed(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(adapter, name, observed)
    original_poll = adapter.watch.poll
    def poll():
        calls.append('watch.poll')
        return original_poll()
    monkeypatch.setattr(adapter.watch, 'poll', poll)
    entry, revision, semantic, preferences = exports._state(document_id, 'Основная', options)
    assert calls[-3:] == ['configuration_identity', 'export_document_is_active', 'watch.poll']
    assert revision == previous[1] and semantic == previous[2] and preferences == previous[3]
    observed = documents.resolve(document_id, 'Основная')[1]
    payload = {'scope': SCOPE, 'connection_epoch': exports.connection_epoch, 'document_id': document_id,
               'configuration': 'Основная', 'configuration_epoch': entry.features['export_configurations']['Основная'][1],
               'observed': observed, 'semantic': semantic, 'preferences': preferences,
               'options': asdict(options), 'event_sequence': adapter.watch.sequence,
               'solidworks_revision': adapter.revision}
    assert revision == 'export_rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()


@pytest.mark.parametrize('change', ['configuration_identity', 'active_document', 'document_metadata'])
def test_closing_export_identity_active_and_metadata_gates_are_preserved(setup, monkeypatch, change):
    adapter, _, exports, _, document_id, output = setup
    original_preferences = adapter.export_preferences
    def preferences(options):
        result = original_preferences(options)
        if change == 'configuration_identity':
            adapter.config_identity = object()
        elif change == 'active_document':
            adapter.active = False
        else:
            adapter.models[0].state['title'] = 'Другой заголовок'
        return result
    monkeypatch.setattr(adapter, 'export_preferences', preferences)
    with pytest.raises(ExecutionFailure) as error:
        exports._state(document_id, 'Основная', ExportOptions('stl', 'Контрольный экспорт.stl', 'mm').checked())
    assert error.value.code == 'document_changed_during_read' and error.value.uncertain is False
    assert adapter.writes == 0 and list(output.iterdir()) == []
