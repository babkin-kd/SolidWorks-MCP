"""Explicit targeting, object lifetime and honest observation revision scope."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure


class Adapter:
    revision = '31.2.1'

    def __init__(self):
        self.models = []
        self.closed = False

    def documents(self):
        # Fresh wrappers every time, same underlying native identity.
        return [SimpleNamespace(identity=m.identity, state=m.state) for m in self.models]

    def identity(self, model):
        return model.identity

    def snapshot(self, model):
        return deepcopy(model.state)

    def close(self):
        self.closed = True


def model(*, path='C:/models/part.sldprt', title='Деталь', configurations=None):
    return SimpleNamespace(identity=object(), state={
        'path': path, 'title': title, 'document_type': 'part', 'needs_save': False,
        'configurations': ['Основная', 'Вариант'] if configurations is None else configurations,
        'active_configuration': 'Основная', 'update_stamp': 3})


def test_same_title_and_path_never_alias_distinct_com_documents():
    adapter = Adapter()
    adapter.models = [model(), model()]
    catalog = DocumentCatalog(adapter)
    first = catalog.list()['documents']
    assert first[0]['document_id'] != first[1]['document_id']
    assert catalog.list()['documents'] == first  # Wrappers did not change identity.
    selected = catalog.get(first[0]['document_id'], 'Вариант')
    assert selected['configuration_is_active'] is False
    assert selected['active_configuration'] == 'Основная'
    assert adapter.models[0].state['active_configuration'] == 'Основная'


def test_reopen_same_path_between_observations_gets_new_id():
    adapter = Adapter()
    adapter.models = [model()]
    catalog = DocumentCatalog(adapter)
    old = catalog.list()['documents'][0]
    adapter.models = [model()]  # No intermediate observation of an empty list.
    new = catalog.list()['documents'][0]
    assert new['document_id'] != old['document_id']
    with pytest.raises(ExecutionFailure) as failure:
        catalog.get(old['document_id'], 'Основная')
    assert failure.value.code == 'document_not_open'
    assert failure.value.uncertain is False


def test_closed_document_and_removed_configuration_rejected():
    adapter = Adapter()
    adapter.models = [model()]
    catalog = DocumentCatalog(adapter)
    document_id = catalog.list()['documents'][0]['document_id']
    adapter.models[0].state['configurations'] = ['Основная']
    with pytest.raises(ExecutionFailure, match='configuration') as failure:
        catalog.get(document_id, 'Вариант')
    assert failure.value.code == 'configuration_not_found'
    adapter.models.clear()
    assert catalog.list()['documents'] == []
    with pytest.raises(ExecutionFailure) as failure:
        catalog.get(document_id, 'Основная')
    assert failure.value.code == 'document_not_open'


@pytest.mark.parametrize('key,value', [('update_stamp', 4), ('title', 'Переименованная деталь'),
    ('path', 'C:/models/new.sldprt'), ('configurations', ['Основная', 'Новое имя']),
    ('active_configuration', 'Вариант'), ('needs_save', True)])
def test_observed_changes_invalidate_token_even_without_new_update_stamp(key, value):
    adapter = Adapter()
    adapter.models = [model()]
    catalog = DocumentCatalog(adapter)
    before = catalog.list()['documents'][0]
    adapter.models[0].state[key] = value
    after = catalog.list()['documents'][0]
    assert after['document_id'] == before['document_id']
    assert after['observation_revision'] != before['observation_revision']
    assert after['observation_sequence'] == before['observation_sequence'] + 1
    assert catalog.list()['documents'][0] == after


def test_observed_change_and_revert_does_not_revive_old_token():
    adapter = Adapter()
    adapter.models = [model()]
    catalog = DocumentCatalog(adapter)
    original = catalog.list()['documents'][0]
    adapter.models[0].state['title'] = 'Промежуточное имя'
    catalog.list()
    adapter.models[0].state['title'] = original['title']
    assert catalog.list()['documents'][0]['observation_revision'] != original['observation_revision']


def test_configurationless_document_requires_explicit_empty_name():
    adapter = Adapter()
    adapter.models = [model(configurations=[])]
    adapter.models[0].state['active_configuration'] = ''
    catalog = DocumentCatalog(adapter)
    document_id = catalog.list()['documents'][0]['document_id']
    assert catalog.get(document_id, '')['configuration_is_active'] is True
    with pytest.raises(ExecutionFailure):
        catalog.get(document_id, 'Основная')


def test_catalog_cannot_be_used_or_released_on_another_thread():
    catalog = DocumentCatalog(Adapter())
    with ThreadPoolExecutor(max_workers=1) as pool:
        for action in (catalog.list, catalog.close):
            with pytest.raises(ExecutionFailure) as failure:
                pool.submit(action).result()
            assert failure.value.code == 'wrong_apartment'


def test_connection_restart_invalidates_document_ids():
    adapter = Adapter()
    adapter.models = [model()]
    old = DocumentCatalog(adapter).list()['documents'][0]['document_id']
    fresh = DocumentCatalog(adapter)
    assert fresh.list()['documents'][0]['document_id'] != old
    with pytest.raises(ExecutionFailure):
        fresh.get(old, 'Основная')


def test_client_mutating_returned_metadata_cannot_corrupt_catalog():
    adapter = Adapter()
    adapter.models = [model()]
    catalog = DocumentCatalog(adapter)
    original = catalog.list()['documents'][0]
    modified = catalog.list()['documents'][0]
    modified['configurations'].append('Внедрённая конфигурация')
    assert catalog.list()['documents'][0] == original
    with pytest.raises(ExecutionFailure):
        catalog.get(original['document_id'], 'Внедрённая конфигурация')
