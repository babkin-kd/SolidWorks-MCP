"""Feature operation scopes, persistent identities, concurrent edits and rollback."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import DocumentCatalog, rejected
from solidworks_mcp.features import FeatureCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from test_document_catalog_v2 import Adapter as DocumentsAdapter, model


class Watch:
    def __init__(self):
        self.sequence = 0
        self.closed = False
    def poll(self):
        if self.closed:
            raise rejected('revision_monitor_stopped', 'Closed document monitor.')
        return self.sequence
    def close(self):
        self.closed = True


def feature(native_id, name='Выдавливание', *, kind='Boss', suppressed=False, pid=None):
    return SimpleNamespace(identity=object(), pid=pid or str(native_id).encode(), state={
        'native_id': native_id, 'name': name, 'feature_type': kind, 'suppressed': suppressed,
        'owner_native_id': None, 'error_code': 0, 'is_warning': False})


class Adapter(DocumentsAdapter):
    def mutation_guard(self, model):
        return nullcontext()

    def __init__(self):
        super().__init__()
        self.config_identity = {'Основная': object(), 'Вариант': object()}
        self.watches = {}
        self.writes = []
        self.rename_fault = None
        self.read_hook = None
        self.pid_fault = None
    def original(self, wrapper):
        return next(m for m in self.models if m.identity == wrapper.identity)
    def watch_part(self, wrapper):
        original = self.original(wrapper)
        watch = Watch()
        self.watches[id(original.identity)] = watch
        return watch
    def configuration_identity(self, wrapper, configuration):
        return self.config_identity[configuration]
    def features(self, wrapper):
        return self.original(wrapper).features[:]
    def feature_summary(self, obj):
        if self.read_hook:
            hook, self.read_hook = self.read_hook, None
            hook()
        return deepcopy(obj.state)
    def persistent_id(self, wrapper, obj):
        return obj.pid if self.pid_fault != 'missing' else b''
    def resolve_persistent_id(self, wrapper, persistent, kind):
        assert kind == 'feature'
        for obj in self.original(wrapper).features:
            if obj.pid == persistent:
                return obj
        raise rejected('object_deleted', 'Native persistent feature was deleted.')
    def same_persistent_id(self, wrapper, a, b):
        return a == b
    def pending_rebuild(self, wrapper):
        return self.original(wrapper).state.get('pending', False)
    def rename_feature(self, obj, name):
        self.writes.append((obj.state['native_id'], name))
        if self.rename_fault == 'silent':
            return obj.state['name']
        obj.state['name'] = name
        for original in self.models:
            if obj in original.features:
                self.watches[id(original.identity)].sequence += 1
        if self.rename_fault:
            fault, self.rename_fault = self.rename_fault, None
            if callable(fault):
                fault(obj)
            else:
                raise RuntimeError('Injected COM failure after changing the name.')
        return obj.state['name']


@pytest.fixture
def setup(tmp_path):
    adapter = Adapter()
    first, second = model(title='Первая'), model(title='Вторая')
    first.features = [feature(1), feature(2, 'Эскиз', kind='ProfileFeature')]
    second.features = [feature(1, 'Другое выдавливание')]
    adapter.models = [first, second]
    store = JobStore(tmp_path / 'jobs.sqlite')
    documents = DocumentCatalog(adapter)
    ids = [d['document_id'] for d in documents.list()['documents']]
    catalog = FeatureCatalog(documents, store, 'connection_1', mutation_guard=adapter.mutation_guard)
    yield adapter, documents, catalog, store, ids
    documents.close()
    store.close()


def rename(setup, *, request='rename', document=None, object_id=None, revision=None, name='Кронштейн'):
    adapter, documents, catalog, store, ids = setup
    document = document or ids[0]
    if object_id is None or revision is None:
        listed = catalog.list(document, 'Основная')
        object_id = object_id or listed['items'][0]['object_id']
        revision = revision or listed['revision']
    context = {'document_id': document, 'configuration': 'Основная', 'expected_revision': revision}
    args = {**context, 'object_id': object_id, 'name': name}
    # Inline worker preserves this fixture's STA and still uses the real durable runner.
    class InlineWorker:
        def submit(self, function):
            from concurrent.futures import Future
            future = Future()
            try:
                future.set_result(function())
            except BaseException as exc:
                future.set_exception(exc)
            return future
    runner = JobRunner(store, InlineWorker())
    return runner.submit(request, 'feature.rename', args,
        lambda job_id: catalog.rename(job_id, **args), context=context,
        mutates=True, pass_operation_id=True, verify=lambda r: r['verified'] is True)


def test_rename_changes_only_target_and_persistent_reference_survives_name_change(setup):
    adapter, _, catalog, store, ids = setup
    listed = catalog.list(ids[0], 'Основная')
    target = listed['items'][0]['object_id']
    result = rename(setup, object_id=target, revision=listed['revision'])
    assert result['status'] == 'succeeded' and result['mutation']['phase'] == 'committed'
    assert result['mutation']['before_state']['name'] == 'Выдавливание'
    assert catalog.get(ids[0], 'Основная', target)['feature']['name'] == 'Кронштейн'
    assert adapter.models[0].features[1].state['name'] == 'Эскиз'
    assert adapter.models[1].features[0].state['name'] == 'Другое выдавливание'
    assert catalog.list(ids[0], 'Основная')['revision'] != listed['revision']


def test_same_request_id_renames_once_and_returns_historical_job(setup):
    adapter, _, catalog, _, ids = setup
    listed = catalog.list(ids[0], 'Основная')
    kwargs = {'object_id': listed['items'][0]['object_id'], 'revision': listed['revision']}
    first, retry = rename(setup, **kwargs), rename(setup, **kwargs)
    assert first['operation_id'] == retry['operation_id']
    assert retry['status'] == 'succeeded'
    assert adapter.writes == [(1, 'Кронштейн')]


def test_manual_feature_name_without_stamp_change_rejects_old_revision_before_write(setup):
    adapter, _, catalog, _, ids = setup
    listed = catalog.list(ids[0], 'Основная')
    adapter.models[0].features[0].state['name'] = 'Ручное изменение'
    result = rename(setup, revision=listed['revision'])
    assert result['status'] == 'failed' and result['error']['code'] == 'stale_revision'
    assert adapter.writes == []


def test_notifications_invalidate_rename_then_revert_between_snapshots(setup):
    adapter, _, catalog, _, ids = setup
    listed = catalog.list(ids[0], 'Основная')
    watch = adapter.watches[id(adapter.models[0].identity)]
    watch.sequence += 2
    result = rename(setup, revision=listed['revision'])
    assert result['error']['code'] == 'stale_revision'
    assert adapter.writes == []


@pytest.mark.parametrize('name', ['Box', ' Кронштейн', 'Кронштейн ', 'Кронштейн@1', 'Кронштейн\n', '', 'К'*129])
def test_invalid_names_fail_without_native_write(setup, name):
    result = rename(setup, name=name)
    assert result['status'] == 'failed' and result['error']['code'] == 'invalid_russian_name'
    assert setup[0].writes == []


def test_duplicate_name_foreign_reference_inactive_configuration_and_rebuild_rejected(setup):
    adapter, _, catalog, _, ids = setup
    listed = catalog.list(ids[0], 'Основная')
    target = listed['items'][0]['object_id']
    assert rename(setup, name='эскиз')['error']['code'] == 'feature_name_conflict'
    assert rename(setup, request='foreign', document=ids[1], object_id=target)['error']['code'] == 'object_reference_not_found'
    with pytest.raises(ExecutionFailure) as error:
        catalog.list(ids[0], 'Вариант')
    assert error.value.code == 'configuration_not_active'
    adapter.models[0].state['pending'] = True
    assert rename(setup, request='pending')['error']['code'] == 'document_needs_rebuild'
    assert adapter.writes == []


def test_deleted_reference_never_retargets_a_new_feature_with_same_name(setup):
    adapter, _, catalog, _, ids = setup
    listed = catalog.list(ids[0], 'Основная')
    target = listed['items'][0]['object_id']
    adapter.models[0].features[0] = feature(3)
    result = rename(setup, object_id=target)
    assert result['status'] == 'failed' and result['error']['code'] == 'object_deleted'
    assert adapter.writes == []


def test_recreated_same_name_configuration_rejects_old_reference(setup):
    adapter, _, catalog, _, ids = setup
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    adapter.config_identity['Основная'] = object()
    assert rename(setup, object_id=target)['error']['code'] == 'object_configuration_mismatch'


def test_new_defect_after_rename_triggers_restore_but_unrestored_defect_keeps_hold(setup):
    adapter, _, _, store, ids = setup
    def introduce_error(obj):
        adapter.models[0].features[1].state['error_code'] = 42
    adapter.rename_fault = introduce_error
    result = rename(setup)
    assert result['status'] == 'unknown'
    assert result['mutation']['phase'] == 'unresolved'
    assert adapter.models[0].features[0].state['name'] == 'Выдавливание'
    assert store.mutation_blockers('connection_1', ids[0])
    assert rename(setup, request='after-error')['error']['code'] == 'document_mutation_blocked'


def test_exception_after_actual_write_restores_exact_prior_name(setup):
    adapter, _, _, store, ids = setup
    adapter.rename_fault = 'exception'
    result = rename(setup)
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back'
    assert adapter.models[0].features[0].state['name'] == 'Выдавливание'
    assert store.mutation_blockers('connection_1', ids[0]) == []


def test_rollback_does_not_overwrite_an_unrelated_concurrent_name(setup):
    adapter, _, _, store, ids = setup
    def concurrent(obj):
        obj.state['name'] = 'Имя пользователя'
        raise RuntimeError('Concurrent user edit.')
    adapter.rename_fault = concurrent
    result = rename(setup)
    assert result['status'] == 'unknown'
    assert adapter.models[0].features[0].state['name'] == 'Имя пользователя'
    assert len(adapter.writes) == 1


def test_prior_native_defects_are_preserved_and_not_misreported_as_new(setup):
    adapter, _, _, _, _ = setup
    adapter.models[0].features[1].state.update(error_code=42, is_warning=True)
    assert rename(setup)['status'] == 'succeeded'


def test_missing_native_persistent_id_is_displayed_without_fake_writable_id(setup):
    adapter, _, catalog, _, ids = setup
    adapter.pid_fault = 'missing'
    page = catalog.list(ids[0], 'Основная')
    assert all(item['object_id'] is None and item['persistent_reference_supported'] is False for item in page['items'])


def test_mismatched_native_reference_is_readonly_node_without_poisoning_other_features(setup, monkeypatch):
    adapter, _, catalog, _, ids = setup
    original = adapter.resolve_persistent_id
    first, second = adapter.models[0].features
    monkeypatch.setattr(adapter, 'resolve_persistent_id',
                        lambda m, p, k: second if p == first.pid else original(m, p, k))
    page = catalog.list(ids[0], 'Основная')
    assert page['items'][0]['object_id'] is None
    assert page['items'][0]['reference_error']['code'] == 'persistent_reference_mismatch'
    assert page['items'][1]['object_id'] is not None
    assert adapter.writes == []


def test_paging_and_revision_guard_cover_full_tree_not_only_current_page(setup):
    adapter, _, catalog, _, ids = setup
    first = catalog.list(ids[0], 'Основная', limit=1)
    second = catalog.list(ids[0], 'Основная', limit=1, cursor=first['next_cursor'])
    assert first['total_count'] == second['total_count'] == 2
    assert first['revision'] == second['revision']
    assert first['items'][0]['native_id'] != second['items'][0]['native_id']
    adapter.models[0].features[1].state['name'] = 'Изменение второй страницы'
    with pytest.raises(ExecutionFailure) as error:
        catalog.list(ids[0], 'Основная', limit=1, cursor=first['next_cursor'])
    assert error.value.code == 'invalid_cursor'
    assert rename(setup, revision=first['revision'])['error']['code'] == 'stale_revision'


def test_change_during_read_invalidates_whole_snapshot(setup):
    adapter, _, catalog, _, ids = setup
    catalog.list(ids[0], 'Основная')
    adapter.read_hook = lambda: setattr(adapter.watches[id(adapter.models[0].identity)], 'sequence', 1)
    with pytest.raises(ExecutionFailure) as error:
        catalog.list(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'


def test_document_retirement_releases_event_monitor_on_owner_thread(setup):
    adapter, documents, catalog, _, ids = setup
    catalog.list(ids[0], 'Основная')
    watch = adapter.watches[id(adapter.models[0].identity)]
    adapter.models.pop(0)
    documents.list()
    assert watch.closed is True
