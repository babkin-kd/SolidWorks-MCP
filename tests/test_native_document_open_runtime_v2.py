"""Lazy open routing/connection lifetime with fake domains; no CAD acceptance."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.jobs import JobError, JobStore
from solidworks_mcp import runtime_v2 as module
from solidworks_mcp.server_v2 import create_app
from test_runtime_v2 import Worker


@pytest.fixture
def setup(monkeypatch, tmp_path):
    calls, catalogs, domains, worker_calls = [], [], [], []
    fault = dict(value=None, connection=None)

    class Catalog:
        def __init__(self):
            self.thread = threading.get_ident()
            self.closed = False
            catalogs.append(self)

        def list(self):
            assert threading.get_ident() == self.thread
            return dict(documents=[])

        def close(self):
            assert threading.get_ident() == self.thread
            self.closed = True
            calls.append(('catalog_closed', self))

    class FakeOpen:
        def __init__(self, documents, store, connection_epoch):
            assert threading.get_ident() == documents.thread
            self.documents, self.store, self.epoch = documents, store, connection_epoch
            domains.append(self)

        def prepare_open(self, filename, document_type, configuration, read_only=False):
            arguments = dict(filename=filename, document_type=document_type,
                             configuration=configuration, read_only=read_only)
            calls.append(('prepare', self, arguments))
            if fault['value'] == 'unexpected_read':
                raise RuntimeError('Read connection ended')
            if fault['value'] == 'domain_rejection':
                raise rejected('native_open_configuration_not_found', 'Artificial expected preparation rejection')
            return dict(application_id='app_fake', native_file_id='native_file_fake', revision='rev_fake',
                        echoed=arguments)

        def open(self, operation_id, document_id, configuration, expected_revision, native_file_id, read_only=False):
            assert threading.get_ident() == self.documents.thread
            arguments = dict(document_id=document_id, configuration=configuration,
                             expected_revision=expected_revision, native_file_id=native_file_id, read_only=read_only)
            calls.append(('open', self, operation_id, arguments))
            if fault['value'] == 'unexpected_mutation':
                raise RuntimeError('Mutation connection ended')
            # This deliberately fake verifier only certifies routing. Domain
            # checkpoint/ownership/native postconditions have separate tests.
            return dict(verified=True, fake_routing_only=True, operation_id=operation_id, echoed=arguments)

    def worker_factory():
        worker_calls.append(threading.get_ident())
        return Worker()

    def catalog_factory():
        if fault['connection'] is not None:
            raise fault['connection']
        return Catalog()

    monkeypatch.setattr(module, 'NativeDocumentOpenCatalog', FakeOpen)
    store = JobStore(tmp_path / 'runtime.sqlite')
    runtime = module.Runtime(store, worker_factory=worker_factory, catalog_factory=catalog_factory)
    prepare_args = dict(filename=str(tmp_path / 'Будущая деталь.SLDPRT'),
                        document_type='part', configuration='Основная')
    open_args = dict(document_id='app_fake', configuration='Основная',
                     expected_revision='rev_fake', native_file_id='native_file_fake')
    yield SimpleNamespace(runtime=runtime, store=store, calls=calls, catalogs=catalogs, domains=domains,
                          worker_calls=worker_calls, fault=fault, prepare_args=prepare_args, open_args=open_args)
    assert runtime.shutdown()


def test_discovery_and_journal_startup_never_create_worker_connection_or_open_domain(setup):
    x = setup

    async def exercise():
        app = create_app(x.store, x.runtime)
        tools = await app.list_tools()
        assert {'document_prepare_open_native', 'document_open_native'} <= {tool.name for tool in tools}
        _, info = await app.call_tool('system_get_info', {})
        assert info['status'] == 'succeeded'
        assert x.store.list()['items'] == []

    asyncio.run(exercise())
    assert x.runtime._native_document_opens is None and x.runtime._connection_epoch is None
    assert x.worker_calls == [] and x.catalogs == [] and x.domains == []


def test_one_catalog_and_epoch_are_shared_by_prepare_mutation_replay_and_document_listing(setup):
    x = setup

    async def exercise():
        assert (await x.runtime.read('docs', 'document.list', {}))['status'] == 'succeeded'
        assert x.runtime._native_document_opens is None
        prepared = await x.runtime.read('prepare', 'document.prepare_open_native', x.prepare_args)
        assert prepared['status'] == 'succeeded'
        domain = x.runtime._native_document_opens
        assert domain.documents is x.runtime._catalog and domain.store is x.store
        assert domain.epoch == x.runtime._connection_epoch and domain.epoch.startswith('connection_')
        assert prepared['payload']['mutates'] is False
        assert prepared['payload']['arguments'] == x.prepare_args
        opened = await x.runtime.mutate('open', 'document.open_native', x.open_args)
        assert opened['status'] == 'succeeded' and opened['result']['fake_routing_only'] is True
        assert opened['payload']['mutates'] is True
        assert opened['payload']['arguments'] == x.open_args
        assert opened['payload']['context'] == {key: x.open_args[key] for key in ('document_id', 'configuration', 'expected_revision')}
        assert opened['result']['operation_id'] == opened['operation_id']
        assert x.calls == [('prepare', domain, {**x.prepare_args, 'read_only': False}),
                           ('open', domain, opened['operation_id'], {**x.open_args, 'read_only': False})]
        assert await x.runtime.mutate('open', 'document.open_native', x.open_args) == opened
        assert x.runtime._native_document_opens is domain and len(x.calls) == 2

    asyncio.run(exercise())
    assert len(x.worker_calls) == len(x.catalogs) == len(x.domains) == 1
    assert x.catalogs[0].thread != threading.get_ident()


@pytest.mark.parametrize('read_only', [False, True])
def test_explicit_read_only_payload_is_forwarded_unchanged_to_both_routes(setup, read_only):
    x = setup

    async def exercise():
        prepare = {**x.prepare_args, 'read_only': read_only}
        execute = {**x.open_args, 'read_only': read_only}
        a = await x.runtime.read('prepare', 'document.prepare_open_native', prepare)
        b = await x.runtime.mutate('open', 'document.open_native', execute)
        assert a['status'] == b['status'] == 'succeeded'
        assert a['payload']['arguments'] == prepare and b['payload']['arguments'] == execute
        assert x.calls[0][2] == prepare and x.calls[1][3] == execute

    asyncio.run(exercise())


def test_unexpected_prepare_failure_retires_cached_domain_and_next_request_uses_fresh_epoch(setup):
    x = setup
    x.fault['value'] = 'unexpected_read'

    async def exercise():
        failed = await x.runtime.read('broken', 'document.prepare_open_native', x.prepare_args)
        assert failed['status'] == 'failed' and failed['error']['requires_reconciliation'] is False
        first = x.domains[0]
        assert first.documents.closed is True
        assert x.runtime._native_document_opens is None and x.runtime._catalog is None and x.runtime._connection_epoch is None
        assert await x.runtime.read('broken', 'document.prepare_open_native', x.prepare_args) == failed
        assert len(x.domains) == 1
        x.fault['value'] = None
        recovered = await x.runtime.read('fresh', 'document.prepare_open_native', x.prepare_args)
        assert recovered['status'] == 'succeeded'
        assert x.domains[1] is x.runtime._native_document_opens and x.domains[1].documents is not first.documents
        assert x.domains[1].epoch != first.epoch and len(x.worker_calls) == 1

    asyncio.run(exercise())


def test_expected_domain_rejection_retains_connection_and_cached_ids(setup):
    x = setup
    x.fault['value'] = 'domain_rejection'

    async def exercise():
        failed = await x.runtime.read('reject', 'document.prepare_open_native', x.prepare_args)
        assert failed['status'] == 'failed' and failed['error']['code'] == 'native_open_configuration_not_found'
        domain = x.runtime._native_document_opens
        epoch = x.runtime._connection_epoch
        assert not domain.documents.closed
        x.fault['value'] = None
        succeeded = await x.runtime.read('retry-fresh-request', 'document.prepare_open_native', x.prepare_args)
        assert succeeded['status'] == 'succeeded'
        assert x.runtime._native_document_opens is domain and x.runtime._connection_epoch == epoch

    asyncio.run(exercise())
    assert len(x.catalogs) == len(x.domains) == 1


def test_unexpected_mutation_failure_is_unknown_retires_domain_and_replay_does_not_reconnect(setup):
    x = setup
    x.fault['value'] = 'unexpected_mutation'

    async def exercise():
        unknown = await x.runtime.mutate('uncertain', 'document.open_native', x.open_args)
        assert unknown['status'] == 'unknown' and unknown['error']['requires_reconciliation'] is True
        assert x.runtime._native_document_opens is None and x.runtime._catalog is None and x.runtime._connection_epoch is None
        assert x.catalogs[0].closed is True
        assert await x.runtime.mutate('uncertain', 'document.open_native', x.open_args) == unknown
        assert len(x.catalogs) == len(x.domains) == 1

    asyncio.run(exercise())


@pytest.mark.parametrize('failure', [JobError('cad_unavailable', 'No connection'), RuntimeError('Factory failure')])
def test_mutation_connection_failure_is_known_prewrite_and_next_new_request_can_connect(setup, failure):
    x = setup
    x.fault['connection'] = failure

    async def exercise():
        failed = await x.runtime.mutate('no-cad', 'document.open_native', x.open_args)
        assert failed['status'] == 'failed' and failed['error']['requires_reconciliation'] is False
        assert failed['error']['code'] == getattr(failure, 'code', 'cad_connection_failed')
        assert x.runtime._native_document_opens is None and x.runtime._connection_epoch is None and not x.domains
        assert x.store.mutation_blockers('connection', 'app_fake') == []
        x.fault['connection'] = None
        succeeded = await x.runtime.mutate('connected', 'document.open_native', x.open_args)
        assert succeeded['status'] == 'succeeded' and len(x.domains) == 1

    asyncio.run(exercise())


def test_shutdown_resets_open_domain_on_owning_worker_and_rejects_new_dispatch(setup):
    x = setup
    assert asyncio.run(x.runtime.read('prepare', 'document.prepare_open_native', x.prepare_args))['status'] == 'succeeded'
    domain = x.runtime._native_document_opens
    assert domain is not None
    assert x.runtime.shutdown()
    assert x.runtime._native_document_opens is None and x.runtime._catalog is None and x.runtime._connection_epoch is None
    assert domain.documents.closed is True
    with pytest.raises(JobError) as error:
        asyncio.run(x.runtime.read('after-close', 'document.prepare_open_native', x.prepare_args))
    assert error.value.code == 'runtime_stopped'


@pytest.mark.parametrize('route,operation,timeout', [
    ('read', 'document.open_native', 10), ('mutate', 'document.prepare_open_native', 10),
    ('read', 'document.prepare_open_native', -1), ('mutate', 'document.open_native', True),
])
def test_wrong_route_or_invalid_timeout_cannot_start_worker_or_record_job(setup, route, operation, timeout):
    x = setup
    with pytest.raises(JobError) as error:
        asyncio.run(getattr(x.runtime, route)('invalid', operation, {}, timeout_s=timeout))
    assert error.value.code in ('unsupported_operation', 'invalid_timeout')
    assert not x.worker_calls and not x.catalogs and not x.domains and x.store.list()['items'] == []
