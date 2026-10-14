"""Disk-checkpoint races and failed writes through the real durable coordinator.

All native data and notifications are synthetic. This does not constitute CAD
or installed-wheel acceptance; the fixtures deliberately never create COM.
"""

import pytest

from solidworks_mcp.jobs import JobStore
from test_feature_domain_v2 import setup, rename


@pytest.mark.parametrize('edit', ['rename', 'rename_and_revert', 'configuration_identity', 'save_flag'])
def test_user_edit_after_checkpoint_blocks_apply_and_does_not_undo_user_work(setup, monkeypatch, edit):
    adapter, _, catalog, store, ids = setup
    page = catalog.list(ids[0], 'Основная')
    original = store.prepare_mutation

    def checkpoint_then_edit(*args, **kwargs):
        original(*args, **kwargs)
        if edit == 'rename':
            adapter.models[0].features[0].state['name'] = 'Имя пользователя'
        elif edit == 'rename_and_revert':
            # Native notifications retain a change even when semantic values
            # happen to return to their checkpoint state.
            adapter.watches[id(adapter.models[0].identity)].sequence += 2
        elif edit == 'configuration_identity':
            adapter.config_identity['Основная'] = object()
        else:
            adapter.models[0].state['needs_save'] = True

    monkeypatch.setattr(store, 'prepare_mutation', checkpoint_then_edit)
    result = rename(setup, object_id=page['items'][0]['object_id'], revision=page['revision'])
    assert result['status'] == 'failed'
    assert result['mutation']['phase'] == 'not_started'
    assert result['mutation']['verification']['evidence']['native_mutation_started'] is False
    assert adapter.writes == []
    if edit == 'rename':
        assert adapter.models[0].features[0].state['name'] == 'Имя пользователя'
    assert store.mutation_blockers('connection_1', ids[0]) == []


def test_queued_checkpoint_recheck_on_other_document_does_not_change_target_revision(setup, monkeypatch):
    adapter, _, catalog, store, ids = setup
    page = catalog.list(ids[0], 'Основная')
    original = store.prepare_mutation

    def checkpoint_then_edit_other(*args, **kwargs):
        original(*args, **kwargs)
        adapter.models[1].features[0].state['name'] = 'Ручное имя другой детали'

    monkeypatch.setattr(store, 'prepare_mutation', checkpoint_then_edit_other)
    result = rename(setup, object_id=page['items'][0]['object_id'], revision=page['revision'])
    assert result['status'] == 'succeeded'
    assert adapter.models[1].features[0].state['name'] == 'Ручное имя другой детали'
    assert adapter.writes == [(1, 'Кронштейн')]


def test_deleted_target_during_failed_write_is_not_replaced_or_renamed_by_rollback(setup):
    adapter, _, _, store, ids = setup

    def delete_target(obj):
        adapter.models[0].features.remove(obj)
        raise RuntimeError('Target deleted after attempted native write.')

    adapter.rename_fault = delete_target
    result = rename(setup)
    assert result['status'] == 'unknown'
    assert result['mutation']['phase'] == 'unresolved'
    assert adapter.writes == [(1, 'Кронштейн')]
    assert [f.state['name'] for f in adapter.models[0].features] == ['Эскиз']
    assert store.mutation_blockers('connection_1', ids[0])


def test_restart_keeps_unknown_hold_global_even_if_current_feature_snapshot_is_readable(setup):
    adapter, _, catalog, store, ids = setup

    def external_edit(obj):
        obj.state['name'] = 'Другое ручное имя'
        raise RuntimeError('Rollback must not overwrite the external edit.')

    adapter.rename_fault = external_edit
    result = rename(setup)
    assert result['status'] == 'unknown'
    path = store.path
    store.close()
    reopened = JobStore(path)
    try:
        assert catalog.list(ids[0], 'Основная')['items'][0]['name'] == 'Другое ручное имя'
        assert reopened.get(result['operation_id'])['status'] == 'unknown'
        assert reopened.mutation_blockers('new_connection', 'new_opaque_document_id')
        # Reopening a store never verifies live CAD state by itself.
        assert reopened.get(result['operation_id'])['mutation']['reconciliation'] is None
    finally:
        reopened.close()
