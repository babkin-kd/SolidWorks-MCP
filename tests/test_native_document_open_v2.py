"""Native-open domain tests with artificial files/handles, never CAD evidence."""

from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobError, JobRunner, JobStore
from solidworks_mcp.native_document_open import NativeDocumentOpenCatalog, SCOPE, _directory_key
from test_native_document_close_v2 import CloseAdapter, Guard, Worker


class OpenGuard(Guard):
    def release_baseline_ui_for_activation(self):
        a = self.adapter
        assert a.busy and not a.baseline_ui_released
        a.baseline_ui_released = True
        a.release_calls += 1
        if a.open_fault == 'release_throw':
            raise RuntimeError('UI release acknowledgement lost')
        for item in self.models:
            a.alive(item)
            item.blocking_state = 0
        if a.open_fault == 'release_foreign':
            self.models[0].view['scale'] = 9.


class OpenAdapter(CloseAdapter):
    def __init__(self, folder):
        super().__init__(folder)
        self.inventories, self.kinds = {}, {}
        self.open_calls, self.release_calls = 0, 0
        self.open_fault, self.cleanup_fault = None, None
        self.baseline_ui_released = False
        self.reference_calls = []
        self.resident_override = {}
        self.open_directory = False
        self.directory_fault = None
        self.directory_calls = 0
        self.directory_receipts = []

    @staticmethod
    def key(path):
        return str(Path(path).resolve(strict=True))

    def add(self, title, *, kind='part', visible=True, saved=True):
        current = super().add(title, kind=kind, visible=visible, saved=saved)
        current.references = []
        if saved:
            self.inventories[self.key(current.state['path'])] = dict(dependencies=[], configurations=list(current.state['configurations']))
            self.kinds[self.key(current.state['path'])] = kind
        return current

    def file(self, title, *, kind='part', dependencies=()):
        extension = dict(part='.SLDPRT', assembly='.SLDASM', drawing='.SLDDRW')[kind]
        path = self.folder / (title + extension)
        path.write_bytes(b'artificial saved native data ' + title.encode('utf8'))
        self.kinds[str(path)] = kind
        self.inventories[str(path)] = dict(configurations=[] if kind == 'drawing' else ['Основная', 'Вариант'],
            dependencies=[dict(name=Path(child).stem, path=str(child), document_type=self.kinds[self.key(child)]) for child in dependencies])
        return path

    def native_open_loaded_identity(self, filename):
        if filename in self.resident_override:
            return self.resident_override[filename]
        current = next((item for item in self.models if item.state['path'] and self.key(item.state['path']) == filename), None)
        return current.identity if current is not None else None

    def native_open_file_inventory(self, filename, kind):
        return deepcopy(self.inventories[filename])

    def native_open_guard(self, models, document_ids):
        self.baseline_ui_released = False
        return OpenGuard(self, models, document_ids)

    def new_native_open_receipt(self, models, filename, document_type, configuration, read_only):
        return SimpleNamespace(baseline_models=models, baseline_identities=tuple(item.identity for item in models),
            filename=filename, document_type=document_type, configuration=configuration, read_only=read_only,
            native_call_attempted=False, pending_open=False, native_call_returned=False,
            raw_model=None, model=None, identity=None, errors=None, warnings=None,
            acknowledgement_valid=False, returned_new_identity=False)

    def _load(self, path, *, configuration=None, read_only=False, visible=False):
        canonical = self.key(path)
        existing = next((item for item in self.models if item.state['path'] and self.key(item.state['path']) == canonical), None)
        if existing is not None:
            return existing
        kind = self.kinds[canonical]
        inventory = self.inventories[canonical]
        cfg = configuration if configuration is not None else (inventory['configurations'][0] if inventory['configurations'] else '')
        current = self.add(Path(canonical).stem, kind=kind, visible=visible, saved=False)
        current.state.update(path=canonical, configurations=list(inventory['configurations']), active_configuration=cfg)
        current.mode['read_only_state'] = int(read_only)
        current.dependencies = [row['path'] for row in inventory['dependencies']]
        for index, dependency in enumerate(inventory['dependencies']):
            child = self._load(dependency['path'])
            current.references.append((child, dict(path=dependency['path'], configuration='Основная',
                name=f'Компонент {index + 1}', origin='drawing_view' if kind == 'drawing' else 'component',
                native_suppression_state=None if kind == 'drawing' else 2)))
        return current

    def native_open_model_references(self, model):
        self.alive(model)
        self.reference_calls.append(model)
        return [(target, dict(info)) for target, info in model.references]

    def open_native_document(self, receipt):
        assert not receipt.native_call_attempted and self.busy
        assert self.checkpoint_lookup()['mutation']['verification']['native_steps'][-1]['name'] == 'open_native'
        assert self.checkpoint_lookup()['mutation']['verification']['native_steps'][-1]['phase'] == 'pending'
        self.open_calls += 1
        receipt.native_call_attempted = receipt.pending_open = True
        if self.open_fault == 'throw_before':
            raise RuntimeError('OpenDoc6 return lost before model delta')
        if self.open_directory:
            self.app['current_directory'] = str(Path(receipt.filename).parent)
        if self.open_fault == 'foreign_directory':
            self.app['current_directory'] = str(self.folder / 'Чужая папка')
        if self.open_fault in ('null', 'null_error'):
            receipt.native_call_returned, receipt.pending_open, receipt.acknowledgement_valid = True, False, True
            receipt.errors, receipt.warnings = (1 if self.open_fault == 'null_error' else 0), 0
            return
        if self.open_fault == 'borrowed_return':
            receipt.model = receipt.raw_model = receipt.baseline_models[0]
            receipt.identity = receipt.model.identity
            receipt.native_call_returned, receipt.pending_open = True, False
            raise ExecutionFailure('native_open_existing_handle', 'Borrowed native return is never an owned model.', uncertain=True)
        current = self._load(receipt.filename, configuration=receipt.configuration,
                             read_only=receipt.read_only, visible=True)
        self.active = current
        if self.open_fault == 'throw_after':
            # A native throw does not supply a raw returned model receipt.
            raise RuntimeError('OpenDoc6 return lost after an observed model delta')
        receipt.model = receipt.raw_model = current
        receipt.identity = current.identity
        receipt.returned_new_identity, receipt.acknowledgement_valid = True, True
        receipt.native_call_returned, receipt.pending_open = True, False
        receipt.errors, receipt.warnings = 0, (2 if self.open_fault in ('warning', 'warning_dirty_new') else 0)
        if self.open_fault == 'error':
            receipt.errors = 1
        if self.open_fault == 'source_config_fallback':
            current.state['active_configuration'] = 'Основная'
        if self.open_fault == 'read_only_fallback':
            current.mode['read_only_state'] = 0
        if self.open_fault == 'foreign_model':
            self.add('Неожиданная модель')
        if self.open_fault == 'neighbor_model':
            receipt.baseline_models[0].state['needs_save'] = False
        if self.open_fault == 'neighbor_view':
            receipt.baseline_models[0].view['selection'] = ['Чужое выделение']
        if self.open_fault == 'neighbor_file':
            Path(receipt.baseline_models[0].state['path']).write_bytes(b'externally changed neighbor bytes')
        if self.open_fault == 'source_file':
            Path(receipt.filename).write_bytes(b'externally changed source bytes')
        if self.open_fault == 'application':
            self.app['search_folders'] = 'unexpected search setting'
        if self.open_fault == 'reference_config_fallback':
            current.references[0][1]['configuration'] = 'Несуществующая конфигурация'
        if self.open_fault == 'missing_reference_receipt':
            current.references = []
        if self.open_fault == 'warning_dirty_new':
            current.state['needs_save'] = True
        if self.open_fault == 'baseline_reference':
            parent = next(item for item in receipt.baseline_models if item.references)
            parent.references[0][1]['configuration'] = 'Основная'

    def new_native_directory_restore_receipt(self, original_directory, expected_current_directory):
        if self.directory_fault == 'constructor':
            raise ExecutionFailure('native_open_directory_target_invalid', 'Original directory no longer exists.', uncertain=False)
        receipt = SimpleNamespace(original_directory=original_directory,
            expected_current_directory=expected_current_directory, native_call_attempted=False,
            pending_directory=False, native_call_returned=False, acknowledgement_valid=False,
            setter_succeeded=False, raw_return=None)
        self.directory_receipts.append(receipt)
        return receipt

    def restore_native_open_directory(self, receipt):
        assert self.busy and not receipt.native_call_attempted
        ledger = self.checkpoint_lookup()['mutation']['verification']['native_steps']
        assert ledger[-1] == dict(sequence=len(ledger), name='restore_directory_native', phase='pending',
            evidence=dict(original_directory=receipt.original_directory,
                          expected_current_directory=receipt.expected_current_directory))
        if self.directory_fault == 'precall_changed':
            self.app['current_directory'] = str(self.folder / 'Чужая папка')
        if self.app['current_directory'] != receipt.expected_current_directory:
            raise ExecutionFailure('native_open_directory_changed', 'CWD changed before setter.', uncertain=False)
        assert Path(receipt.original_directory).is_absolute() and Path(receipt.original_directory).is_dir()
        self.directory_calls += 1
        receipt.native_call_attempted = receipt.pending_directory = True
        if self.directory_fault == 'throw_before':
            raise RuntimeError('Setter return lost before effect')
        if self.directory_fault not in ('false', 'invalid_ack', 'no_effect'):
            self.app['current_directory'] = receipt.original_directory
        if self.directory_fault == 'throw_after':
            raise RuntimeError('Setter return lost after effect')
        receipt.native_call_returned, receipt.pending_directory = True, False
        receipt.raw_return = None if self.directory_fault == 'invalid_ack' else self.directory_fault != 'false'
        receipt.acknowledgement_valid = type(receipt.raw_return) is bool
        receipt.setter_succeeded = receipt.raw_return is True
        if self.directory_fault == 'foreign_application':
            self.app['search_folders'] = 'foreign change after setter'
        if not receipt.acknowledgement_valid or not receipt.setter_succeeded:
            raise ExecutionFailure('native_open_directory_unacknowledged', 'Setter ACK is not true.', uncertain=True)

    def new_native_activation_receipt(self, current):
        self.alive(current)
        return SimpleNamespace(model=current, identity=current.identity, native_call_attempted=False,
                              pending_activation=False, native_call_returned=False, raw_model=None, native_error=None)

    def activate_native_open_document(self, receipt):
        assert self.busy and all(item.blocking_state == 0 for item in self.guarded)
        assert not receipt.native_call_attempted
        assert self.checkpoint_lookup()['mutation']['verification']['native_steps'][-1]['phase'] == 'pending'
        self.activations.append(receipt.model)
        receipt.native_call_attempted = receipt.pending_activation = True
        if self.open_fault == 'activation_throw':
            raise RuntimeError('Activation return lost')
        receipt.native_call_returned, receipt.pending_activation = True, False
        receipt.raw_model, receipt.native_error = receipt.model, 0
        if self.open_fault == 'activation_no_effect':
            raise ExecutionFailure('native_open_activation_unconfirmed', 'Activation left the wrong current model.', uncertain=False)
        self.active = receipt.model

    def close_native_document(self, current, name):
        original = self.fault
        self.fault = self.cleanup_fault
        try:
            return super().close_native_document(current, name)
        finally:
            self.fault = original


@pytest.fixture
def setup(tmp_path):
    adapter = OpenAdapter(tmp_path)
    neighbor = adapter.add('Рабочая соседняя деталь')
    neighbor.state['needs_save'] = True
    neighbor.view['selection'] = ['Исходное выделение']
    adapter.active = neighbor
    source = adapter.file('Открываемая деталь')
    docs = DocumentCatalog(adapter)
    store = JobStore(tmp_path / 'jobs.sqlite')
    catalog = NativeDocumentOpenCatalog(docs, store, 'epoch')
    runner = JobRunner(store, Worker())
    prepared = catalog.prepare_open(str(source), 'part', 'Основная')

    def run(request='open', preparation=None, **changes):
        p = preparation or prepared
        data = dict(document_id=p['application_id'], native_file_id=p['native_file_id'],
                    configuration=p['configuration'], expected_revision=p['revision'], read_only=p['read_only'])
        data.update(changes)
        adapter.checkpoint_lookup = lambda: next(row for row in store.list(limit=100)['items'] if row['request_id'] == request)
        return runner.submit(request, 'document.open_native', data, lambda operation_id: catalog.open(operation_id, **data),
                             context=data, mutates=True, pass_operation_id=True,
                             verify=lambda result: result['verified'] is True)

    yield SimpleNamespace(a=adapter, neighbor=neighbor, source=source, d=docs, s=store, c=catalog, p=prepared, run=run)
    docs.close()
    store.close()


def steps(result):
    return [(row['name'], row['phase']) for row in result['mutation']['verification']['native_steps']]


def test_exact_part_preserves_dirty_neighbor_and_all_files_and_replays(setup):
    x = setup
    original_state, original_view = deepcopy(x.neighbor.state), deepcopy(x.neighbor.view)
    disk = {str(path): path.read_bytes() for path in (x.source, Path(x.neighbor.state['path']))}
    result = x.run()
    assert result['status'] == 'succeeded' and result['mutation']['phase'] == 'committed', result
    value = result['result']['value']
    assert value['source_document_id'] in value['new_document_ids'] and len(value['new_document_ids']) == 1
    assert value['borrowed_document_ids'] == [] and value['references'] == []
    assert x.neighbor.state == original_state and x.neighbor.view == original_view
    assert x.a.active is x.neighbor and x.a.activations == [x.neighbor]
    assert x.a.open_calls == 1 and x.a.calls == 0 and x.a.release_calls == 1 and not x.a.busy
    assert all(Path(path).read_bytes() == data for path, data in disk.items())
    assert x.run() == result and x.a.open_calls == 1
    assert steps(result) == [('open_native', 'pending'), ('open_native', 'returned'),
                             ('release_baseline_ui', 'pending'), ('release_baseline_ui', 'returned'),
                             ('activate_native', 'pending'), ('activate_native', 'returned')]


@pytest.mark.parametrize('kind,configuration', [('part', 'Вариант'), ('assembly', 'Вариант'), ('drawing', '')])
@pytest.mark.parametrize('read_only', [False, True])
def test_exact_document_type_configuration_and_read_only_are_not_implicit(setup, kind, configuration, read_only):
    x = setup
    source = x.a.file('Точный файл', kind=kind)
    p = x.c.prepare_open(str(source), kind, configuration, read_only)
    result = x.run(preparation=p)
    assert result['status'] == 'succeeded', result
    source_id = result['result']['value']['source_document_id']
    actual = next(row for row in result['result']['after']['semantic']['documents'] if row['document_id'] == source_id)
    assert actual['active_configuration'] == configuration and actual['document_type'] == kind
    assert bool(actual['mode']['read_only_state']) is read_only


def test_empty_baseline_leaves_exact_new_document_active(setup):
    x = setup
    x.a.models, x.a.windows, x.a.active = [], [], None
    p = x.c.prepare_open(str(x.source), 'part', 'Основная')
    result = x.run(preparation=p)
    assert result['status'] == 'succeeded', result
    assert result['result']['value']['active_after_document_id'] == result['result']['value']['source_document_id']
    assert x.a.release_calls == 0 and x.a.activations == []
    assert steps(result) == [('open_native', 'pending'), ('open_native', 'returned')]


@pytest.mark.parametrize('source_kind', ['assembly', 'drawing'])
@pytest.mark.parametrize('borrowed', [False, True])
def test_full_reference_graph_uses_exact_reached_handles_and_borrowed_membership(setup, source_kind, borrowed):
    x = setup
    child = Path(x.neighbor.state['path']) if borrowed else x.a.file('Загружаемая дочерняя деталь')
    root = x.a.file('Открываемый документ с зависимостью', kind=source_kind, dependencies=[child])
    configuration = '' if source_kind == 'drawing' else 'Основная'
    p = x.c.prepare_open(str(root), source_kind, configuration)
    result = x.run(preparation=p)
    assert result['status'] == 'succeeded', result
    value = result['result']['value']
    assert len(value['new_document_ids']) == (1 if borrowed else 2)
    assert len(value['borrowed_document_ids']) == int(borrowed)
    reference = value['references'][0]
    assert reference['parent_document_id'] == value['source_document_id'] and reference['path'] == str(child)
    assert reference['origin'] == ('component' if source_kind == 'assembly' else 'drawing_view')
    if borrowed:
        assert reference['document_id'] == value['borrowed_document_ids'][0]
        assert x.neighbor.state['needs_save'] is True and reference['document_id'] not in value['new_document_ids']
    else:
        assert reference['document_id'] in value['new_document_ids']


def test_transitive_drawing_assembly_part_resolution_is_complete(setup):
    x = setup
    child = x.a.file('Дочерняя деталь')
    assembly = x.a.file('Подсборка', kind='assembly', dependencies=[child])
    drawing = x.a.file('Чертёж сборки', kind='drawing', dependencies=[assembly])
    p = x.c.prepare_open(str(drawing), 'drawing', '')
    result = x.run(preparation=p)
    assert result['status'] == 'succeeded', result
    value = result['result']['value']
    assert len(value['new_document_ids']) == 3 and len(value['references']) == 2
    assert {edge['document_id'] for edge in value['references']} == set(value['new_document_ids']) - {value['source_document_id']}


@pytest.mark.parametrize('fault', ['null', 'null_error'])
def test_normal_null_return_with_exact_no_effect_is_known_failure(setup, fault):
    x = setup
    x.a.open_fault = fault
    result = x.run()
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back', result
    assert result['error']['requires_reconciliation'] is False
    assert x.a.open_calls == 1 and x.a.calls == 0 and x.a.models == [x.neighbor]
    assert not x.c.receipts and steps(result) == [('open_native', 'pending'), ('open_native', 'returned')]


@pytest.mark.parametrize('fault', ['warning', 'error', 'source_config_fallback', 'read_only_fallback'])
def test_normally_returned_clean_owned_source_is_safely_rolled_back(setup, fault):
    x = setup
    p = x.c.prepare_open(str(x.source), 'part', 'Вариант', True)
    x.a.open_fault = fault
    result = x.run(preparation=p)
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back', result
    assert result['error']['requires_reconciliation'] is False
    assert x.a.open_calls == 1 and x.a.calls == 1 and x.a.models == [x.neighbor]
    assert x.a.active is x.neighbor and x.neighbor.state['needs_save'] is True and x.a.dead_getters == 0
    assert not x.c.receipts


@pytest.mark.parametrize('fault', ['throw_before', 'throw_after', 'foreign_model', 'neighbor_model', 'neighbor_view',
                                  'neighbor_file', 'source_file', 'application', 'release_throw', 'release_foreign',
                                  'activation_throw', 'warning_dirty_new'])
def test_pending_or_unproved_foreign_delta_is_unknown_without_adoption_or_cleanup(setup, fault):
    x = setup
    x.a.open_fault = fault
    result = x.run()
    assert result['status'] == 'unknown' and result['error']['requires_reconciliation'] is True, result
    assert result['mutation']['phase'] == 'unresolved' and x.a.open_calls == 1 and x.a.calls == 0
    assert result['operation_id'] in x.c.receipts
    assert x.run() == result and x.a.open_calls == 1
    blocked = x.run('different-request')
    assert blocked['status'] == 'failed' and blocked['error']['code'] == 'document_mutation_blocked'
    assert x.a.open_calls == 1 and x.a.calls == 0 and not x.a.busy
    if fault.startswith('throw_'):
        assert steps(result) == [('open_native', 'pending')]
        assert x.c.receipts[result['operation_id']].raw_model is None


@pytest.mark.parametrize('fault', ['reference_config_fallback', 'missing_reference_receipt'])
def test_invalid_or_missing_reference_receipts_never_become_success_or_owned_delta_cleanup(setup, fault):
    x = setup
    child = x.a.file('Собственная зависимость')
    assembly = x.a.file('Сборка с зависимостью', kind='assembly', dependencies=[child])
    p = x.c.prepare_open(str(assembly), 'assembly', 'Основная')
    x.a.open_fault = fault
    result = x.run(preparation=p)
    assert result['status'] == 'unknown' and x.a.calls == 0, result
    assert result['operation_id'] in x.c.receipts


@pytest.mark.parametrize('change', ['source', 'neighbor_file', 'neighbor_view', 'active', 'application', 'guard_source'])
def test_changed_complete_revision_never_calls_native_open(setup, change):
    x = setup
    if change == 'source':
        x.source.write_bytes(b'changed bound source')
    elif change == 'neighbor_file':
        Path(x.neighbor.state['path']).write_bytes(b'changed baseline file')
    elif change == 'neighbor_view':
        x.neighbor.view['scale'] = 3.
    elif change == 'active':
        x.a.active = None
    elif change == 'application':
        x.a.app['current_directory'] += '/changed'
    else:
        x.a.guard_hook = lambda: x.source.write_bytes(b'changed bound file under acquired guard')
    result = x.run()
    assert result['status'] == 'failed' and not result['error']['requires_reconciliation'], result
    assert result['error']['code'] in ('stale_revision', 'native_file_reference_stale')
    assert x.a.open_calls == 0 and not x.c.receipts


@pytest.mark.parametrize('alias', ['same', 'parent_segments', 'hardlink'])
def test_already_loaded_source_cannot_become_new_through_filename_alias(setup, alias):
    x = setup
    path = Path(x.neighbor.state['path'])
    if alias == 'parent_segments':
        directory = path.parent / 'Подкаталог'
        directory.mkdir()
        path = directory / '..' / path.name
    elif alias == 'hardlink':
        other = path.parent / 'Alias.SLDPRT'
        os.link(path, other)
        path = other
    with pytest.raises(ExecutionFailure) as error:
        x.c.prepare_open(str(path), 'part', 'Основная')
    assert error.value.code == 'native_document_already_loaded' and x.a.open_calls == 0


def test_missing_configuration_is_refused_before_native_fallback(setup):
    x = setup
    with pytest.raises(ExecutionFailure) as error:
        x.c.prepare_open(str(x.source), 'part', 'Не существует')
    assert error.value.code == 'native_open_configuration_not_found' and x.a.open_calls == 0


def test_resident_handle_outside_complete_census_is_never_adopted(setup):
    x = setup
    x.a.resident_override[str(x.source)] = object()
    with pytest.raises(ExecutionFailure) as error:
        x.c.prepare_open(str(x.source), 'part', 'Основная')
    assert error.value.code == 'native_open_census_invalid' and x.a.models == [x.neighbor]


def test_prepare_has_no_native_mutation_or_job_and_file_reference_is_stable(setup):
    x = setup
    second = x.c.prepare_open(str(x.source), 'part', 'Основная')
    assert second['native_file_id'] == x.p['native_file_id'] and second['revision'] == x.p['revision']
    assert second['application_id'].startswith('app_') and second['revision_scope'] == SCOPE
    assert x.a.open_calls == 0 and x.a.calls == 0 and x.a.guard_arguments is None and x.s.list()['items'] == []


@pytest.mark.parametrize('changes,code', [
    ({'document_id': 'app_foreign'}, 'application_reference_mismatch'),
    ({'native_file_id': 'native_file_foreign'}, 'native_file_reference_not_found'),
    ({'read_only': 1}, 'native_open_policy_invalid'),
    ({'expected_revision': 'rev_stale'}, 'stale_revision'),
])
def test_explicit_application_file_policy_and_revision_are_required_before_write(setup, changes, code):
    x = setup
    result = x.run(**changes)
    assert result['status'] == 'failed' and result['error']['code'] == code, result
    assert x.a.open_calls == 0


def test_request_id_payload_conflict_never_repeats_open(setup):
    x = setup
    assert x.run()['status'] == 'succeeded'
    with pytest.raises(JobError) as error:
        x.run(read_only=True)
    assert error.value.code == 'request_conflict' and x.a.open_calls == 1


def baseline_assembly(x):
    """Existing references can change without a model update stamp or disk edit."""
    current = x.a.add('Существующая сборка', kind='assembly')
    current.dependencies = [x.neighbor.state['path']]
    current.references = [(x.neighbor, dict(path=x.neighbor.state['path'], configuration='Вариант',
        name='Рабочий компонент', origin='component', native_suppression_state=2))]
    x.a.inventories[current.state['path']]['dependencies'] = [dict(name='Рабочий компонент',
        path=x.neighbor.state['path'], document_type='part')]
    return current


def test_baseline_reference_change_invalidates_revision_without_metadata_stamp_change(setup):
    x = setup
    parent = baseline_assembly(x)
    p = x.c.prepare_open(str(x.source), 'part', 'Основная')
    stamp = parent.state['update_stamp']
    parent.references[0][1]['configuration'] = 'Основная'
    result = x.run(preparation=p)
    assert parent.state['update_stamp'] == stamp
    assert result['status'] == 'failed' and result['error']['code'] == 'stale_revision', result
    assert x.a.open_calls == 0


def test_unexpected_baseline_reference_change_after_open_is_unknown_without_cleanup(setup):
    x = setup
    baseline_assembly(x)
    p = x.c.prepare_open(str(x.source), 'part', 'Основная')
    x.a.open_fault = 'baseline_reference'
    result = x.run(preparation=p)
    assert result['status'] == 'unknown' and x.a.calls == 0, result
    assert x.neighbor.state['needs_save'] is True
    assert result['operation_id'] in x.c.receipts


def test_returned_borrowed_handle_never_becomes_owned_or_closed(setup):
    x = setup
    x.a.open_fault = 'borrowed_return'
    result = x.run()
    assert result['status'] != 'succeeded' and x.a.open_calls == 1 and x.a.calls == 0
    assert x.a.models == [x.neighbor] and x.neighbor.state['needs_save'] is True
    assert all(not receipt.returned_new_identity for receipt in x.c.receipts.values())


@pytest.mark.parametrize('step_number', [1, 2, 3, 4, 5, 6])
def test_native_step_storage_failure_holds_effect_without_automatic_cleanup(setup, monkeypatch, step_number):
    x = setup
    original = x.s.record_mutation_step
    calls = 0

    def failure(operation_id, **kwargs):
        nonlocal calls
        calls += 1
        if calls == step_number:
            raise OSError('Native step persistence lost')
        return original(operation_id, **kwargs)

    monkeypatch.setattr(x.s, 'record_mutation_step', failure)
    result = x.run()
    assert calls >= step_number and result['status'] == 'unknown', result
    assert result['error']['requires_reconciliation'] is True and x.a.calls == 0
    assert x.a.open_calls == (0 if step_number == 1 else 1)
    assert x.run() == result and x.a.calls == 0


def test_failed_open_with_foreign_hidden_close_collateral_is_not_cleaned(setup):
    x = setup
    foreign = x.a.add('Исходная скрытая модель', visible=False)
    p = x.c.prepare_open(str(x.source), 'part', 'Основная')
    x.a.open_fault = 'warning'
    result = x.run(preparation=p)
    assert result['status'] == 'unknown' and x.a.calls == 0, result
    assert foreign in x.a.models and foreign.retired is False


def test_failed_open_with_final_background_quit_risk_does_not_close_owned_model(setup):
    x = setup
    x.a.models, x.a.windows, x.a.active = [], [], None
    x.a.app['user_control'] = False
    p = x.c.prepare_open(str(x.source), 'part', 'Основная')
    x.a.open_fault = 'warning'
    result = x.run(preparation=p)
    assert result['status'] == 'unknown' and x.a.calls == 0 and len(x.a.models) == 1, result


@pytest.mark.parametrize('cleanup_fault', ['throw_before', 'throw_after', 'no_effect'])
def test_failed_cleanup_is_unknown_without_second_close_attempt(setup, cleanup_fault):
    x = setup
    x.a.open_fault, x.a.cleanup_fault = 'warning', cleanup_fault
    result = x.run()
    assert result['status'] == 'unknown' and x.a.open_calls == 1 and x.a.calls == 1, result
    assert result['operation_id'] in x.c.receipts
    assert x.run() == result and x.a.calls == 1


@pytest.mark.parametrize('source_kind', ['assembly', 'drawing'])
@pytest.mark.parametrize('borrowed_child', [False, True])
def test_clean_reference_rollback_retires_only_full_exact_owned_new_graph(setup, source_kind, borrowed_child):
    x = setup
    child = Path(x.neighbor.state['path']) if borrowed_child else x.a.file('Контрольная зависимость')
    source = x.a.file('Контрольный документ с зависимостью', kind=source_kind, dependencies=[child])
    p = x.c.prepare_open(str(source), source_kind, '' if source_kind == 'drawing' else 'Основная')
    original_state, original_view = deepcopy(x.neighbor.state), deepcopy(x.neighbor.view)
    x.a.open_fault = 'warning'
    result = x.run(preparation=p)
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back', result
    assert x.a.open_calls == 1 and x.a.calls == 1 and x.a.models == [x.neighbor]
    assert x.neighbor.state == original_state and x.neighbor.view == original_view and x.a.active is x.neighbor
    assert x.a.dead_getters == 0 and not x.c.receipts
    assert ('rollback_close_native', 'pending') in steps(result) and ('rollback_close_native', 'returned') in steps(result)
    evidence = next(row['evidence'] for row in result['mutation']['verification']['native_steps']
                    if row['name'] == 'rollback_close_native' and row['phase'] == 'pending')
    assert len(evidence['impact']['retiring_document_ids']) == (1 if borrowed_child else 2)


def test_pending_application_hold_cannot_be_bypassed_with_new_connection_epoch(setup):
    x = setup
    x.a.open_fault = 'throw_before'
    original = x.run()
    assert original['status'] == 'unknown'
    fresh = NativeDocumentOpenCatalog(x.d, x.s, 'new-epoch')
    p = fresh.prepare_open(str(x.source), 'part', 'Основная')
    data = dict(document_id=p['application_id'], native_file_id=p['native_file_id'],
                configuration=p['configuration'], expected_revision=p['revision'])
    assert p['application_id'] != x.p['application_id']
    result = JobRunner(x.s, Worker()).submit('after-reconnect', 'document.open_native', data,
        lambda operation_id: fresh.open(operation_id, **data), context=data, mutates=True,
        pass_operation_id=True, verify=lambda value: value['verified'] is True)
    assert result['status'] == 'failed' and result['error']['code'] == 'document_mutation_blocked'
    assert x.a.open_calls == 1 and not fresh.receipts
    assert x.s.get(original['operation_id'])['status'] == 'unknown'


def directory_preparation(x, *, source=None, kind='part', configuration='Основная', read_only=False):
    original = x.a.folder / 'Исходная рабочая папка'
    original.mkdir(exist_ok=True)
    x.a.app['current_directory'] = str(original)
    x.a.open_directory = True
    return x.c.prepare_open(str(source or x.source), kind, configuration, read_only)


@pytest.mark.parametrize('empty', [False, True])
def test_receipt_bound_directory_change_is_restored_once_last_and_replayed(setup, empty):
    x = setup
    if empty:
        x.a.models, x.a.windows, x.a.active = [], [], None
    p = directory_preparation(x)
    result = x.run(preparation=p)
    assert result['status'] == 'succeeded', result
    assert result['result']['after']['semantic']['application'] == p['baseline']['application']
    assert x.a.directory_calls == 1 and x.a.calls == 0
    assert steps(result)[-2:] == [('restore_directory_native', 'pending'), ('restore_directory_native', 'returned')]
    evidence = result['mutation']['verification']['native_steps'][-2]['evidence']
    assert evidence == dict(original_directory=p['baseline']['application']['current_directory'],
                            expected_current_directory=str(x.source.parent))
    assert result['mutation']['verification']['native_steps'][-1]['evidence'] == dict(
        native_call_attempted=True, pending_directory=False, native_call_returned=True,
        acknowledgement_valid=True, setter_succeeded=True)
    assert x.run(preparation=p) == result and x.a.directory_calls == 1 and x.a.open_calls == 1
    assert x.neighbor.state['needs_save'] is True and not x.a.busy


@pytest.mark.parametrize('fault', ['null', 'null_error'])
def test_normal_null_directory_only_effect_is_restored_without_close(setup, fault):
    x = setup
    p = directory_preparation(x)
    x.a.open_fault = fault
    result = x.run(preparation=p)
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back', result
    assert result['error']['requires_reconciliation'] is False
    assert x.a.directory_calls == 1 and x.a.calls == 0 and x.a.models == [x.neighbor]
    assert x.a.app == p['baseline']['application'] and not x.c.receipts


@pytest.mark.parametrize('fault', ['warning', 'error', 'source_config_fallback', 'read_only_fallback'])
def test_clean_open_failure_closes_owned_root_then_restores_directory_once(setup, fault):
    x = setup
    p = directory_preparation(x, configuration='Вариант', read_only=True)
    x.a.open_fault = fault
    result = x.run(preparation=p)
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back', result
    assert x.a.calls == 1 and x.a.directory_calls == 1 and x.a.models == [x.neighbor]
    assert x.a.app == p['baseline']['application'] and x.a.active is x.neighbor
    assert steps(result)[-2:] == [('restore_directory_native', 'pending'), ('restore_directory_native', 'returned')]
    assert steps(result).index(('rollback_close_native', 'returned')) < len(steps(result)) - 2
    assert x.a.dead_getters == 0 and not x.c.receipts


def test_directory_restore_follows_exact_original_active_rollback_activation(setup):
    x = setup
    active = x.a.add('Исходная активная модель CWD')
    x.a.active = active
    p = directory_preparation(x)
    x.a.open_fault = 'warning'
    result = x.run(preparation=p)
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back', result
    assert x.a.active is active and x.a.activations == [active]
    assert x.a.calls == 1 and x.a.directory_calls == 1
    assert steps(result)[-4:] == [('rollback_activate_native', 'pending'), ('rollback_activate_native', 'returned'),
                                 ('restore_directory_native', 'pending'), ('restore_directory_native', 'returned')]
    assert x.a.app == p['baseline']['application']


@pytest.mark.parametrize('kind', ['assembly', 'drawing'])
@pytest.mark.parametrize('borrowed', [False, True])
@pytest.mark.parametrize('fault', [None, 'warning'])
def test_directory_restore_requires_complete_new_and_borrowed_reference_closure(setup, kind, borrowed, fault):
    x = setup
    child = Path(x.neighbor.state['path']) if borrowed else x.a.file('Дочерняя модель CWD')
    source = x.a.file('Документ CWD', kind=kind, dependencies=[child])
    p = directory_preparation(x, source=source, kind=kind, configuration='' if kind == 'drawing' else 'Основная')
    x.a.open_fault = fault
    result = x.run(preparation=p)
    assert result['status'] == ('failed' if fault else 'succeeded'), result
    assert result['mutation']['phase'] == ('rolled_back' if fault else 'committed')
    assert x.a.directory_calls == 1 and x.a.calls == int(fault is not None)
    assert x.a.app == p['baseline']['application'] and x.neighbor.state['needs_save'] is True


@pytest.mark.parametrize('fault', ['foreign_directory', 'application', 'foreign_model', 'neighbor_model',
    'neighbor_view', 'neighbor_file', 'source_file', 'throw_before', 'throw_after', 'release_foreign', 'activation_throw'])
def test_foreign_or_pending_effect_with_directory_change_has_no_setter_or_close(setup, fault):
    x = setup
    p = directory_preparation(x)
    x.a.open_fault = fault
    result = x.run(preparation=p)
    assert result['status'] == 'unknown' and result['error']['requires_reconciliation'] is True, result
    assert x.a.directory_calls == 0 and x.a.calls == 0
    assert result['operation_id'] in x.c.receipts


@pytest.mark.parametrize('fault', ['missing_reference_receipt', 'reference_config_fallback'])
def test_incomplete_source_closure_with_directory_change_does_not_restore_or_close(setup, fault):
    x = setup
    child = x.a.file('Зависимость CWD')
    source = x.a.file('Сборка CWD', kind='assembly', dependencies=[child])
    p = directory_preparation(x, source=source, kind='assembly')
    x.a.open_fault = fault
    result = x.run(preparation=p)
    assert result['status'] == 'unknown' and x.a.directory_calls == 0 and x.a.calls == 0, result


@pytest.mark.parametrize('fault', ['throw_before', 'throw_after', 'false', 'invalid_ack', 'no_effect',
                                  'foreign_application', 'precall_changed', 'constructor'])
def test_failed_directory_restore_is_held_without_retry_or_cleanup(setup, fault):
    x = setup
    p = directory_preparation(x)
    x.a.directory_fault = fault
    result = x.run(preparation=p)
    assert result['status'] == 'unknown' and result['mutation']['phase'] == 'unresolved', result
    assert result['error']['requires_reconciliation'] is True and x.a.calls == 0
    assert x.a.directory_calls == (0 if fault in ('precall_changed', 'constructor') else 1)
    assert len(x.a.directory_receipts) == int(fault != 'constructor') and len(x.a.models) == 2
    assert x.run(preparation=p) == result and len(x.a.directory_receipts) == int(fault != 'constructor')
    blocked = x.run('new-after-directory-failure', preparation=p)
    assert blocked['error']['code'] == 'document_mutation_blocked'
    assert result['operation_id'] in x.c.receipts and x.a.calls == 0 and not x.a.busy
    if fault == 'constructor':
        assert not any(name == 'restore_directory_native' for name, _ in steps(result))
    elif fault.startswith('throw_'):
        assert steps(result)[-1] == ('restore_directory_native', 'pending')
    else:
        assert steps(result)[-1] == ('restore_directory_native', 'returned')


@pytest.mark.parametrize('phase', ['pending', 'returned'])
def test_directory_step_journal_failure_prohibits_native_retry_and_cleanup(setup, monkeypatch, phase):
    x = setup
    p = directory_preparation(x)
    original = x.s.record_mutation_step
    def fail(operation_id, **kwargs):
        if kwargs['name'] == 'restore_directory_native' and kwargs['phase'] == phase:
            raise OSError('Directory ledger persistence lost')
        return original(operation_id, **kwargs)
    monkeypatch.setattr(x.s, 'record_mutation_step', fail)
    result = x.run(preparation=p)
    assert result['status'] == 'unknown' and x.a.calls == 0, result
    assert x.a.directory_calls == int(phase == 'returned')
    assert x.run(preparation=p) == result and len(x.a.directory_receipts) == 1


@pytest.mark.parametrize('value', [None, True, 1, '', ' ', 'relative/path', 'C:relative', '\\relative',
                                  '/contains\0nul', '/' + 'x' * 32767],
                         ids=['none', 'bool', 'integer', 'empty', 'whitespace', 'relative', 'drive_relative',
                              'root_relative', 'nul', 'too_long'])
def test_directory_normalization_rejects_unbounded_or_nonabsolute_strings(value):
    assert _directory_key(value) is None


@pytest.mark.parametrize('value,expected', [
    ('C:\\Work\\.\\Sub\\..', ('windows', 'c:\\work')),
    ('\\\\Server\\Share\\Models\\..', ('windows', '\\\\server\\share\\')),
    ('/work/./models/..', ('posix', '/work')),
])
def test_directory_normalization_is_flavor_bound_without_filesystem_alias_resolution(value, expected):
    assert _directory_key(value) == expected


def test_final_baseline_predicate_never_accepts_owned_directory_delta(setup):
    x = setup
    p = directory_preparation(x)
    after = deepcopy(p['baseline'])
    after['application']['current_directory'] = str(x.source.parent)
    receipt = SimpleNamespace(native_call_attempted=True, native_call_returned=True,
                              pending_open=False, acknowledgement_valid=True)
    assert not x.c._same_baseline(p['baseline'], after)
    assert x.c._same_intermediate_baseline(p['baseline'], after, str(x.source), receipt)
    receipt.acknowledgement_valid = False
    assert not x.c._same_intermediate_baseline(p['baseline'], after, str(x.source), receipt)
