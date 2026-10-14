"""Clean-close domain and durable outcome tests on artificial models/files."""

from concurrent.futures import Future
from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.native_document_close import NativeDocumentCloseCatalog, SCOPE
from test_document_catalog_v2 import Adapter, model


class Worker:
    def submit(self, function):
        future = Future()
        try:
            future.set_result(function())
        except BaseException as error:
            future.set_exception(error)
        return future


class Guard:
    def __init__(self, adapter, models, retiring):
        self.adapter, self.models, self.retiring = adapter, models, retiring
        self.evidence = dict(released=False)

    def __enter__(self):
        a = self.adapter
        assert not a.busy and not any(item.retired for item in self.models)
        assert a.checkpoint_lookup()['mutation']['before_state']['_mutation_effect_scope'] == 'application'
        a.busy = True
        a.guarded = tuple(self.models)
        a.guard_arguments = (self.models, self.retiring)
        for item in self.models:
            item.blocking_state = 2
        if a.guard_hook:
            a.guard_hook()
        return self

    def __exit__(self, *error):
        a = self.adapter
        for item in self.models:
            a.alive(item)  # Retired handles must never reach guard release.
            item.blocking_state = 0
        a.busy = False
        self.evidence['released'] = True

    def release_survivor_ui_for_activation(self):
        assert self.adapter.busy and self.models
        for item in self.models:
            self.adapter.alive(item)
            item.blocking_state=0
        if self.adapter.fault=='activation_release_foreign':self.models[0].state['needs_save']=not self.models[0].state['needs_save']


class CloseAdapter(Adapter):
    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self.active = None
        self.busy = False
        self.windows = []
        self.app = dict(user_control=True, visible=True, current_directory=str(folder), search_folders='')
        self.calls, self.activations, self.dead_getters = 0, [], 0
        self.fault = None
        self.guarded = ()
        self.guard_hook = None
        self.guard_arguments = None
        self.checkpoint_lookup = lambda: pytest.fail('No durable checkpoint before guard')

    def alive(self, current):
        if current.retired:
            self.dead_getters += 1
            raise AssertionError('Getter on a retired model')

    def add(self, title, *, kind='part', visible=True, saved=True):
        extension = dict(part='.SLDPRT', assembly='.SLDASM', drawing='.SLDDRW')[kind]
        path = self.folder / (title + extension)
        if saved:
            path.write_bytes(b'artificial native file ' + title.encode('utf8'))
        item = model(title=title, path=str(path) if saved else '')
        item.state['document_type'] = kind
        if kind == 'drawing':
            item.state.update(configurations=[], active_configuration='')
        item.view = dict(scale=1., selection=[])
        item.dependencies, item.retired, item.blocking_state = [], False, 0
        item.mode = dict(read_only_state=0, editing_sketch=False, editing_component=False, view_only=False)
        self.models.append(item)
        if visible:
            self.windows.append((item, dict(hwnd=100 + len(self.windows), title=title)))
        return item

    def documents(self):
        return list(self.models)

    def identity(self, current):
        self.alive(current)
        return current.identity

    def snapshot(self, current):
        self.alive(current)
        return deepcopy(current.state)

    def active_document(self):
        return self.active

    def application_busy(self):
        return self.busy

    def document_view_snapshot(self, current):
        self.alive(current)
        return deepcopy(current.view)

    def native_close_model_context(self, current):
        self.alive(current)
        return dict(visible=any(item is current for item, _ in self.windows),
                    dependencies=list(current.dependencies), mode={**current.mode, 'blocking_state': current.blocking_state})

    def native_close_windows(self):
        return [(item, dict(details)) for item, details in self.windows]

    def native_close_application_context(self):
        return dict(self.app)

    def native_close_guard(self, survivors, retiring_ids):
        return Guard(self, survivors, retiring_ids)

    def close_native_document(self, current, name):
        self.alive(current)
        assert current.state['title'] == name and current not in self.guarded
        self.calls += 1
        if self.fault == 'throw_before':
            raise RuntimeError('Native return lost before visible effect')
        if self.fault in ('no_effect', 'no_ack'):
            return dict(native_call_returned=self.fault != 'no_ack')
        paths = [item.state['path'] for item in self.models]
        retiring = [item for item in self.models if item is current or
                    (item is not self.active and not any(window is item for window, _ in self.windows))]
        if self.fault == 'partial_hidden':
            retiring = [current]
        self.models = [item for item in self.models if item not in retiring]
        self.windows = [(item, details) for item, details in self.windows if item not in retiring]
        for item in retiring:
            item.retired = True
        if self.active in retiring:
            self.active = self.models[0] if self.models else None
        if self.fault == 'throw_after':
            raise RuntimeError('Native return lost after retirement')
        if self.fault == 'survivor_model':
            self.models[0].state['needs_save'] = True
        if self.fault == 'survivor_view':
            self.models[0].view['selection'] = ['unexpected selection']
        if self.fault == 'window_handle':
            self.windows[0][1]['hwnd'] += 1000
        if self.fault == 'window_title':
            self.windows[0][1]['title'] = 'Чужое окно'
        if self.fault == 'foreign_file':
            Path(self.models[0].state['path']).write_bytes(b'changed surviving file')
        if self.fault == 'retired_file':
            Path(paths[0]).write_bytes(b'changed retired file')
        if self.fault == 'application':
            self.app['search_folders'] = 'changed global setting'
        if self.fault == 'unexpected_model':
            self.add('Неожиданная деталь')
        return dict(native_call_returned=True)

    def activate_native_close_survivor(self, current):
        self.alive(current)
        assert self.busy and all(item.blocking_state==0 for item in self.models)
        self.activations.append(current)
        if self.fault == 'activation_throw':
            raise RuntimeError('Activation return lost')
        if self.fault != 'activation_no_effect':
            self.active = current


@pytest.fixture
def setup(tmp_path):
    adapter = CloseAdapter(tmp_path)
    target = adapter.add('Закрываемая деталь')
    survivor = adapter.add('Соседняя деталь')
    adapter.active = survivor
    docs = DocumentCatalog(adapter)
    store = JobStore(tmp_path / 'jobs.sqlite')
    catalog = NativeDocumentCloseCatalog(docs, store, 'epoch')
    row = docs.list()['documents'][0]
    args = dict(document_id=row['document_id'], configuration=row['active_configuration'])
    prepared = catalog.prepare_close(**args)
    runner = JobRunner(store, Worker())

    def run(request='close', revision=prepared['revision'], **policy):
        data = dict(args, expected_revision=revision, **policy)
        adapter.checkpoint_lookup = lambda: next(item for item in store.list(limit=100)['items'] if item['request_id'] == request)
        return runner.submit(request, 'document.close_native', data, lambda op: catalog.close(op, **data),
                             context=data, mutates=True, pass_operation_id=True,
                             verify=lambda result: result['verified'] is True)

    yield SimpleNamespace(a=adapter, d=docs, s=store, c=catalog, args=args, p=prepared,
                          run=run, target=target, survivor=survivor)
    docs.close()
    store.close()


def assert_prewrite_failure(result, adapter, code=None):
    assert result['status'] == 'failed' and adapter.calls == 0
    assert result['error']['requires_reconciliation'] is False
    if code:
        assert result['error']['code'] == code


def test_clean_inactive_close_preserves_dirty_survivor_files_windows_and_replays(setup):
    x = setup
    x.survivor.state['needs_save'] = True
    p = x.c.prepare_close(**x.args)
    disk = [(item['file']['path'], Path(item['file']['path']).read_bytes()) for item in p['baseline']['files']]
    result = x.run(revision=p['revision'])
    assert result['status'] == 'succeeded' and result['mutation']['phase'] == 'committed'
    assert result['result']['value']['retiring_document_ids'] == [x.args['document_id']]
    assert result['result']['value']['data_unload_claimed'] is False
    assert x.a.models == [x.survivor] and x.a.active is x.survivor
    assert x.a.guard_arguments == ((x.survivor,), (x.args['document_id'],))
    assert x.survivor.state['needs_save'] is True and x.a.activations == []
    assert x.a.dead_getters == 0 and not x.a.busy and x.survivor.blocking_state == 0
    assert all(Path(path).read_bytes() == data for path, data in disk)
    assert x.run(revision=p['revision']) == result and x.a.calls == 1


@pytest.mark.parametrize('kind,configuration', [('assembly', 'Основная'), ('drawing', '')])
def test_exact_native_types_and_configuration(kind, configuration, setup):
    x = setup
    old = Path(x.target.state['path'])
    new = old.with_suffix('.SLDASM' if kind == 'assembly' else '.SLDDRW')
    old.rename(new)
    x.target.state.update(path=str(new), document_type=kind, active_configuration=configuration,
                          configurations=['Основная'] if configuration else [])
    x.args['configuration'] = configuration
    p = x.c.prepare_close(**x.args)
    assert x.run(revision=p['revision'])['status'] == 'succeeded' and x.a.calls == 1


def test_active_target_requires_and_activates_exact_visible_survivor(setup):
    x = setup
    third = x.a.add('Выбранный сосед')
    x.a.active = x.target
    chosen = next(row['document_id'] for row in x.d.list()['documents'] if row['title'] == third.state['title'])
    policy = dict(active_after_document_id=chosen)
    p = x.c.prepare_close(**x.args, **policy)
    result = x.run(revision=p['revision'], **policy)
    assert result['status'] == 'succeeded' and x.a.active is third
    assert x.a.activations == [third] and x.a.dead_getters == 0


@pytest.mark.parametrize('fault', ['activation_throw', 'activation_no_effect'])
def test_unconfirmed_activation_after_irreversible_close_is_unknown(setup, fault):
    x = setup
    third = x.a.add('Выбранный сосед')
    x.a.active = x.target
    chosen = next(row['document_id'] for row in x.d.list()['documents'] if row['title'] == third.state['title'])
    policy = dict(active_after_document_id=chosen)
    p = x.c.prepare_close(**x.args, **policy)
    x.a.fault = fault
    result = x.run(revision=p['revision'], **policy)
    assert result['status'] == 'unknown' and x.a.calls == 1 and x.a.activations == [third]
    assert x.run(revision=p['revision'], **policy) == result and x.a.calls == 1


def test_changed_survivor_during_activation_unlock_is_unknown_without_activation_or_retry(setup):
    x=setup;third=x.a.add('Выбранный сосед');x.a.active=x.target
    chosen=next(row['document_id'] for row in x.d.list()['documents'] if row['title']==third.state['title'])
    policy=dict(active_after_document_id=chosen);p=x.c.prepare_close(**x.args,**policy)
    x.a.fault='activation_release_foreign'
    result=x.run(revision=p['revision'],**policy)
    assert result['status']=='unknown' and x.a.calls==1 and x.a.activations==[]
    assert x.run(revision=p['revision'],**policy)==result and x.a.calls==1


def test_missing_active_successor_is_refused_before_close(setup):
    x = setup
    x.a.active = x.target
    assert_prewrite_failure(x.run(), x.a, 'native_close_active_survivor_required')


def test_inactive_target_cannot_request_other_active_document(setup):
    x = setup
    survivor_id = x.p['impact']['survivor_document_ids'][0]
    assert_prewrite_failure(x.run(active_after_document_id=survivor_id), x.a, 'native_close_active_survivor_invalid')


@pytest.mark.parametrize('user_control', [False, True])
def test_last_document_refuses_background_quit_but_interactive_close_is_verified(setup, user_control):
    x = setup
    x.a.models = [x.target]
    x.a.windows = x.a.windows[:1]
    x.a.active = x.target
    x.a.app['user_control'] = user_control
    if not user_control:
        assert_prewrite_failure(x.run(), x.a, 'native_close_background_quit_risk')
    else:
        p = x.c.prepare_close(**x.args)
        assert x.run(revision=p['revision'])['status'] == 'succeeded'
        assert not x.a.models and not x.a.windows and x.a.active is None
        assert x.a.guard_arguments == ((), (x.args['document_id'],)) and x.a.dead_getters == 0


def test_hidden_collateral_requires_complete_explicit_clean_allowlist(setup):
    x = setup
    hidden = x.a.add('Скрытая контрольная деталь', visible=False)
    hidden_id = next(row['document_id'] for row in x.d.list()['documents'] if row['title'] == hidden.state['title'])
    assert_prewrite_failure(x.run('not-allowed'), x.a, 'native_close_hidden_impact_not_allowed')
    policy = dict(allowed_hidden_document_ids=[hidden_id])
    p = x.c.prepare_close(**x.args, **policy)
    assert set(p['impact']['retiring_document_ids']) == {x.args['document_id'], hidden_id}
    result = x.run('allowed', revision=p['revision'], **policy)
    assert result['status'] == 'succeeded' and hidden.retired and x.a.models == [x.survivor]
    assert x.a.dead_getters == 0


@pytest.mark.parametrize('dirty', ['target', 'hidden'])
def test_dirty_target_or_explicit_hidden_collateral_never_discarded(setup, dirty):
    x = setup
    policy = {}
    if dirty == 'target':
        x.target.state['needs_save'] = True
    else:
        hidden = x.a.add('Скрытая деталь', visible=False)
        hidden.state['needs_save'] = True
        hidden_id = next(row['document_id'] for row in x.d.list()['documents'] if row['title'] == hidden.state['title'])
        policy['allowed_hidden_document_ids'] = [hidden_id]
    assert_prewrite_failure(x.run(**policy), x.a, 'native_close_dirty_document')


@pytest.mark.parametrize('allowed', [['doc_foreign'], ['doc_foreign', 'doc_foreign'], [''], [True], 'doc_foreign'])
def test_allowlist_rejects_extra_ids_duplicates_and_wrong_types(setup, allowed):
    x = setup
    assert_prewrite_failure(x.run(allowed_hidden_document_ids=allowed), x.a)


def test_incoming_survivor_reference_blocks_retained_data_scope(setup):
    x = setup
    x.survivor.dependencies = [x.target.state['path']]
    assert_prewrite_failure(x.run(), x.a, 'native_close_referenced_data_unsupported')


@pytest.mark.parametrize('alias', ['parent_segments', 'hardlink'])
def test_incoming_reference_aliases_cannot_bypass_retained_data_rejection(setup, alias):
    x = setup
    target_path = Path(x.target.state['path'])
    if alias == 'parent_segments':
        folder = target_path.parent / 'Подкаталог'
        folder.mkdir()
        reference = folder / '..' / target_path.name
    else:
        reference = target_path.parent / 'Альтернативное имя.SLDPRT'
        os.link(target_path, reference)
    x.survivor.dependencies = [str(reference)]
    assert_prewrite_failure(x.run(), x.a, 'native_close_referenced_data_unsupported')


def test_loaded_survivor_hardlink_to_target_is_not_claimed_as_unload(setup):
    x = setup
    survivor_path = Path(x.survivor.state['path'])
    survivor_path.unlink()
    os.link(x.target.state['path'], survivor_path)
    assert_prewrite_failure(x.run(), x.a, 'native_close_referenced_data_unsupported')


def test_unavailable_dependency_is_known_prewrite_failure(setup):
    x = setup
    x.survivor.dependencies = [str(x.a.folder / 'Несуществующая деталь.SLDPRT')]
    assert_prewrite_failure(x.run(), x.a, 'native_file_unavailable')


def test_changed_dependency_file_invalidates_complete_checkpoint(setup):
    x = setup
    reference = x.a.folder / 'Внешняя зависимость.SLDPRT'
    reference.write_bytes(b'artificial referenced native file')
    x.survivor.dependencies = [str(reference)]
    p = x.c.prepare_close(**x.args)
    reference.write_bytes(b'externally changed referenced native file')
    assert_prewrite_failure(x.run(revision=p['revision']), x.a, 'stale_revision')


def test_outgoing_dependency_file_remains_in_post_retirement_disk_manifest(setup):
    x = setup
    reference = x.a.folder / 'Внешняя зависимость.SLDPRT'
    reference.write_bytes(b'artificial referenced native file')
    x.target.dependencies = [str(reference)]
    p = x.c.prepare_close(**x.args)
    result = x.run(revision=p['revision'])
    assert result['status'] == 'succeeded'
    assert result['result']['after']['original_files'] == p['baseline']['files']
    assert any(item['file']['path'] == str(reference) for item in result['result']['after']['original_files'])


def test_clean_unsaved_target_can_close_without_discard_or_file_claim(setup):
    x = setup
    x.target.state['path'] = ''
    p = x.c.prepare_close(**x.args)
    target = next(row for row in p['baseline']['documents'] if row['document_id'] == x.args['document_id'])
    assert target['file'] is None and p['dirty_discard_supported'] is False
    assert x.run(revision=p['revision'])['status'] == 'succeeded'


def test_full_native_file_budget_is_not_replaced_with_partial_manifest(setup, monkeypatch):
    from solidworks_mcp import native_document_close as module
    x = setup
    monkeypatch.setattr(module, 'MAX_TOTAL_BYTES', 1)
    assert_prewrite_failure(x.run(), x.a, 'native_session_file_budget_exceeded')


def test_full_document_budget_rejects_before_window_or_file_operations(setup, monkeypatch):
    from solidworks_mcp import native_document_close as module
    x = setup
    monkeypatch.setattr(module, 'MAX_OPEN_DOCUMENTS', 1)
    x.a.native_close_windows = lambda: pytest.fail('No partial census after model budget exceeded')
    assert_prewrite_failure(x.run(), x.a, 'native_session_budget_exceeded')


def test_outgoing_target_reference_does_not_remove_surviving_data(setup):
    x = setup
    x.target.dependencies = [x.survivor.state['path']]
    p = x.c.prepare_close(**x.args)
    assert x.run(revision=p['revision'])['status'] == 'succeeded' and x.a.models == [x.survivor]


@pytest.mark.parametrize('fault', ['throw_before', 'throw_after', 'survivor_model', 'survivor_view', 'window_handle',
                                  'window_title', 'foreign_file', 'retired_file', 'application', 'unexpected_model'])
def test_lost_ack_or_changed_effect_is_unknown_never_reopened_or_retried(setup, fault):
    x = setup
    x.a.fault = fault
    result = x.run()
    assert result['status'] == 'unknown' and result['mutation']['phase'] == 'unresolved'
    assert result['error']['requires_reconciliation'] is True and x.a.calls == 1
    assert x.run() == result and x.a.calls == 1
    blocked = x.run('another-close')
    assert blocked['status'] == 'failed' and blocked['error']['code'] == 'document_mutation_blocked'
    assert x.a.calls == 1 and x.a.dead_getters == 0 and not x.a.busy


@pytest.mark.parametrize('fault', ['no_effect', 'no_ack'])
def test_normal_return_with_verified_unchanged_baseline_is_known_failure(setup, fault):
    x = setup
    x.a.fault = fault
    result = x.run()
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back'
    assert result['error']['requires_reconciliation'] is False and x.a.calls == 1
    assert x.a.models == [x.target, x.survivor] and not x.a.busy and x.a.dead_getters == 0


def test_partial_hidden_retirement_is_unknown(setup):
    x = setup
    hidden = x.a.add('Скрытый сосед', visible=False)
    hidden_id = next(row['document_id'] for row in x.d.list()['documents'] if row['title'] == hidden.state['title'])
    policy = dict(allowed_hidden_document_ids=[hidden_id])
    p = x.c.prepare_close(**x.args, **policy)
    x.a.fault = 'partial_hidden'
    assert x.run(revision=p['revision'], **policy)['status'] == 'unknown' and not hidden.retired


@pytest.mark.parametrize('change', ['file', 'window', 'view', 'application', 'stamp', 'guard_file'])
def test_stale_complete_checkpoint_is_refused_without_native_call(setup, change):
    x = setup
    if change == 'file':
        Path(x.target.state['path']).write_bytes(b'external file change')
    elif change == 'window':
        x.a.windows[1][1]['hwnd'] += 10
    elif change == 'view':
        x.survivor.view['scale'] = 5.
    elif change == 'application':
        x.a.app['current_directory'] += '/new'
    elif change == 'stamp':
        x.survivor.state['update_stamp'] += 1
    else:
        x.a.guard_hook = lambda: Path(x.target.state['path']).write_bytes(b'external change under guard')
    assert_prewrite_failure(x.run(), x.a, 'stale_revision')


@pytest.mark.parametrize('title', ['', '   ', 'сОСЕДНЯЯ ДЕТАЛЬ'])
def test_close_name_must_be_nonempty_and_unique_casefold(setup, title):
    x = setup
    x.target.state['title'] = title
    assert_prewrite_failure(x.run(), x.a, 'native_close_name_ambiguous')


@pytest.mark.parametrize('mode', ['editing_sketch', 'editing_component', 'view_only'])
def test_active_edit_modes_refused_before_guard_or_close(setup, mode):
    x = setup
    x.target.mode[mode] = True
    assert_prewrite_failure(x.run(), x.a, 'native_document_edit_mode')
    assert x.a.guard_arguments is None


def test_busy_and_nonactive_configuration_refused_without_native(setup):
    x = setup
    x.a.busy = True
    assert_prewrite_failure(x.run('busy'), x.a, 'application_busy')
    x.a.busy = False
    x.args['configuration'] = 'Вариант'
    assert_prewrite_failure(x.run('inactive'), x.a, 'configuration_not_active')


def test_prepare_is_read_only_and_revision_scope_is_explicit(setup):
    x = setup
    assert x.p['revision_scope'] == SCOPE and x.p['dirty_discard_supported'] is False
    assert x.a.calls == 0 and x.a.guard_arguments is None and x.s.list()['items'] == []


def test_changed_two_pass_window_census_is_known_rejection(setup):
    x = setup
    original = x.a.native_close_windows
    count = 0

    def changing():
        nonlocal count
        count += 1
        if count == 2:
            x.a.windows[1][1]['title'] = 'Изменённое окно'
        return original()

    x.a.native_close_windows = changing
    assert_prewrite_failure(x.run(), x.a, 'native_session_changed_during_read')


@pytest.mark.parametrize('change', ['duplicate_window', 'bool_hwnd', 'foreign_window', 'visibility_mismatch', 'relative_dependency', 'bool_mode'])
def test_incomplete_or_untyped_native_census_never_closes(setup, change):
    x = setup
    if change == 'duplicate_window':
        x.a.windows[1][1]['hwnd'] = x.a.windows[0][1]['hwnd']
    elif change == 'bool_hwnd':
        x.a.windows[0][1]['hwnd'] = True
    elif change == 'foreign_window':
        foreign = model(); foreign.retired = False
        x.a.windows.append((foreign, dict(hwnd=300, title='Чужое окно')))
    elif change == 'visibility_mismatch':
        original = x.a.native_close_model_context
        x.a.native_close_model_context = lambda current: {**original(current), 'visible': False}
    elif change == 'relative_dependency':
        x.survivor.dependencies = ['relative.SLDPRT']
    else:
        x.survivor.blocking_state = False
    assert_prewrite_failure(x.run(), x.a, 'native_close_census_invalid')
