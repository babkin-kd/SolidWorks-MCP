"""Artificial document creation and fault ownership, never native acceptance."""

from concurrent.futures import Future
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp.document_creation import DocumentCreationCatalog, template_signature
from solidworks_mcp.documents import DocumentCatalog, rejected
from solidworks_mcp.jobs import JobRunner, JobStore
from test_document_catalog_v2 import Adapter as BaseAdapter, model


class Adapter(BaseAdapter):
    def __init__(self, template):
        super().__init__()
        self.template, self.active, self.busy = str(template), None, False
        self.count, self.closed_own, self.fault = 0, 0, None
    def default_part_template(self): return self.template
    def active_document(self): return self.active
    def application_visible(self): return True
    def application_busy(self): return self.busy
    def document_editing_sketch(self, model): return False
    def document_view_snapshot(self, model): return {'scale': 1.}
    def new_document_receipt(self, models):
        return SimpleNamespace(old=list(self.models), active=self.active, model=None, restored=False, pending=False)
    @contextmanager
    def document_creation_guard(self, models):
        assert not self.busy
        self.busy = True
        try: yield
        finally: self.busy = False
    def create_empty_part_document(self, receipt, template, name, configuration_name):
        assert self.busy
        self.count += 1
        if self.fault == 'unknown':
            receipt.pending = True
            raise RuntimeError('No exact returned native handle')
        receipt.model = model(path='', title=name, configurations=[configuration_name])
        receipt.model.state['active_configuration'] = configuration_name
        self.models.append(receipt.model)
        self.active = receipt.model
        if self.fault == 'known': raise RuntimeError('Known failure after retaining exact return')
        if self.fault == 'foreign':
            self.models.append(model(title='Чужая новая деталь'))
            raise RuntimeError('Foreign document change')
    def created_document_identity(self, receipt): return receipt.model.identity
    def created_document_evidence(self, receipt):
        if receipt.restored: return {'restored': True, 'complete': False}
        if receipt.pending or receipt.model is None: raise rejected('unknown_creation', 'No exact handle')
        return {'restored': False, 'complete': True, 'title': receipt.model.state['title'],
                'configuration': receipt.model.state['active_configuration'], 'empty_part': True}
    def restore_created_document(self, receipt):
        if receipt.pending or self.models != receipt.old + [receipt.model]:
            raise rejected('unsafe_restore', 'Unknown/foreign changes prohibit closure')
        self.models.remove(receipt.model)
        self.active = receipt.active
        self.closed_own += 1
        receipt.restored = True


class Worker:
    def submit(self, function):
        value = Future()
        try: value.set_result(function())
        except BaseException as exc: value.set_exception(exc)
        return value


@pytest.fixture
def setup(tmp_path):
    template = tmp_path / 'Деталь.prtdot'
    template.write_bytes(b'artificial template')
    adapter = Adapter(template)
    adapter.models = [model(title='Исходная деталь')]
    adapter.active = adapter.models[0]
    documents, store = DocumentCatalog(adapter), JobStore(tmp_path / 'jobs.sqlite')
    catalog = DocumentCreationCatalog(documents, store, 'document-test')
    template_id = catalog.list_templates()['templates'][0]['template_id']
    prepared = catalog.prepare_create_part(template_id, 'Новая пластина')
    runner = JobRunner(store, Worker())
    def run(request='new-part', revision=prepared['revision']):
        args = dict(document_id=catalog.application_id, configuration='', expected_revision=revision,
                    template_id=template_id, name='Новая пластина', configuration_name='Основная')
        return runner.submit(request, 'document.create_part', args, lambda op: catalog.create_part(op, **args),
            context={key: args[key] for key in ('document_id', 'configuration', 'expected_revision')},
            mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
    yield adapter, catalog, template, run
    documents.close()
    store.close()


def test_new_document_returns_explicit_id_and_same_request_not_replayed(setup):
    adapter, catalog, _, run = setup
    before = deepcopy(adapter.models[0].state)
    first, repeat = run(), run()
    assert first['status'] == 'succeeded' and first == repeat
    assert first['result']['after']['created_document_id'].startswith('doc_')
    assert adapter.count == 1 and adapter.closed_own == 0 and adapter.models[0].state == before
    assert catalog.receipts == {}


@pytest.mark.parametrize('fault', ['known', 'unknown', 'foreign'])
def test_native_outcome_controls_scoped_close(setup, fault):
    adapter, catalog, _, run = setup
    adapter.fault = fault
    job = run()
    known = fault == 'known'
    assert job['status'] == ('failed' if known else 'unknown')
    assert job['error']['requires_reconciliation'] is not known
    assert adapter.closed_own == int(known) and adapter.count == 1
    if not known: assert catalog.receipts


def test_stale_revision_and_changed_template_never_create(setup):
    adapter, _, template, run = setup
    assert run(revision='rev_stale')['error']['code'] == 'stale_revision'
    template.write_bytes(b'changed template')
    assert run(request='changed')['error']['code'] == 'template_reference_stale'
    assert adapter.count == 0
    assert setup[1].receipts == {}


def test_busy_existing_command_and_invalid_names_rejected_before_creation(setup):
    adapter, catalog, _, run = setup
    adapter.busy = True
    assert run()['error']['code'] == 'application_busy'
    with pytest.raises(Exception) as error:
        catalog.prepare_create_part('unregistered', 'English')
    assert error.value.code == 'invalid_russian_name' and adapter.count == 0


def test_fingerprint_requires_existing_native_template(tmp_path):
    path = tmp_path / 'wrong.sldprt'
    path.write_bytes(b'fake')
    with pytest.raises(Exception) as error: template_signature(path)
    assert error.value.code == 'invalid_part_template'
