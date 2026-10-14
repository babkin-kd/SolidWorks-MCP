"""Revision notifications and bounded traversal, without a native COM apartment."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import weakref

import pytest

from solidworks_mcp.cad_features import CadFeaturesMixin, PartRevisionWatch
from solidworks_mcp.jobs import ExecutionFailure


@pytest.fixture
def monitor(monkeypatch):
    calls = []
    pump = {'quit': False}

    class Sink:
        _dispid_to_func_ = {i: name for i, name in enumerate(
            sorted(PartRevisionWatch.EVENTS | {'OnNewSelectionNotify'}))}

        def __init__(self, model):
            calls.append(('attach', model))

        def close(self):
            calls.append(('close',))

    monkeypatch.setattr('solidworks_mcp.cad_features.pythoncom.PumpWaitingMessages',
                        lambda: int(pump['quit']))
    value = PartRevisionWatch('synthetic model', SimpleNamespace(DPartDocEvents=Sink))
    yield value, calls, pump
    value.close()


@pytest.mark.parametrize('name', sorted(PartRevisionWatch.EVENTS))
def test_notification_returns_nonveto_and_increments_without_retaining_arguments(monitor, name):
    watch, calls, _ = monitor

    class Argument:
        pass

    argument = Argument()
    reference = weakref.ref(argument)
    assert getattr(watch._sink, name)(argument) == 0
    assert watch.sequence == 1
    assert calls == [('attach', 'synthetic model')]
    del argument
    assert reference() is None
    if name in {'OnDestroyNotify', 'OnDestroyNotify2'}:
        with pytest.raises(ExecutionFailure) as error:
            watch.poll()
        assert error.value.code == 'revision_monitor_stopped'
    else:
        assert watch.poll() == 1


def test_selection_events_do_not_get_a_model_revision_handler(monitor):
    watch, _, _ = monitor
    assert 'OnNewSelectionNotify' not in watch.events
    assert not hasattr(watch._sink, 'OnNewSelectionNotify')


def test_wrong_apartment_cannot_pump_or_detach_sink(monitor, monkeypatch):
    watch, calls, _ = monitor
    monkeypatch.setattr('solidworks_mcp.cad_features.pythoncom.PumpWaitingMessages',
                        lambda: pytest.fail('Wrong apartment must not pump.'))
    with ThreadPoolExecutor(max_workers=1) as pool:
        for operation in (watch.poll, watch.close):
            with pytest.raises(ExecutionFailure) as error:
                pool.submit(operation).result(timeout=2)
            assert error.value.code == 'wrong_apartment'
    assert watch._sink is not None
    assert calls == [('attach', 'synthetic model')]


def test_wm_quit_invalidates_even_an_attached_live_monitor(monitor):
    watch, _, pump = monitor
    pump['quit'] = True
    with pytest.raises(ExecutionFailure) as error:
        watch.poll()
    assert error.value.code == 'revision_monitor_stopped'
    assert watch.alive is False
    pump['quit'] = False
    with pytest.raises(ExecutionFailure):
        watch.poll()


def test_close_is_idempotent_and_native_disconnect_still_retires_monitor(monitor, monkeypatch):
    import pythoncom
    watch, calls, _ = monitor

    def disconnected():
        calls.append(('disconnect',))
        raise pythoncom.com_error(-2147417848, 'Synthetic disconnect', None, None)

    monkeypatch.setattr(watch._sink, 'close', disconnected)
    watch.close()
    watch.close()
    assert watch._sink is None and watch.alive is False
    assert calls.count(('disconnect',)) == 1
    with pytest.raises(ExecutionFailure):
        watch.poll()


def test_missing_required_native_notifications_fails_before_attach():
    class IncompleteSink:
        _dispid_to_func_ = {1: 'OnRenameItemNotify', 2: 'OnDimensionChangeNotify'}

        def __init__(self, model):
            pytest.fail('Do not attach an incomplete monitor.')

    with pytest.raises(ExecutionFailure) as error:
        PartRevisionWatch(None, SimpleNamespace(DPartDocEvents=IncompleteSink))
    assert error.value.code == 'revision_monitor_unavailable'


class NativeFeature:
    """Synthetic wrapper; equality identifies its canonical native object."""
    def __init__(self, native_id, *, identity=None, next_feature=None, subfeature=None):
        self.native_id = native_id
        self.identity = object() if identity is None else identity
        self.next_feature = next_feature
        self.subfeature = subfeature

    def GetID(self):
        return self.native_id

    def GetNextFeature(self):
        return self.next_feature

    def GetNextSubFeature(self):
        return self.next_feature

    def GetFirstSubFeature(self):
        return self.subfeature


def traversal(monkeypatch):
    class Adapter(CadFeaturesMixin):
        _module = SimpleNamespace(IFeature=object)

        def identity(self, feature):
            return feature.identity

    monkeypatch.setattr('solidworks_mcp.cad_features.binding.wrap', lambda raw, cls: raw)
    return Adapter()


def test_repeated_same_native_feature_and_cycles_terminate_without_duplication(monkeypatch):
    adapter = traversal(monkeypatch)
    first = NativeFeature(1)
    duplicate_wrapper = NativeFeature(1, identity=first.identity)
    first.next_feature = duplicate_wrapper
    duplicate_wrapper.next_feature = first
    assert adapter.features(SimpleNamespace(FirstFeature=lambda: first)) == [first]


def test_same_native_id_with_different_identity_never_issues_partial_tree(monkeypatch):
    adapter = traversal(monkeypatch)
    second = NativeFeature(1)
    first = NativeFeature(1, next_feature=second)
    with pytest.raises(ExecutionFailure) as error:
        adapter.features(SimpleNamespace(FirstFeature=lambda: first))
    assert error.value.code == 'feature_identity_collision'


def test_revision_budget_rejects_a_partial_5000_feature_tree(monkeypatch):
    adapter = traversal(monkeypatch)
    first = None
    for native_id in range(5001, 0, -1):
        first = NativeFeature(native_id, next_feature=first)
    with pytest.raises(ExecutionFailure) as error:
        adapter.features(SimpleNamespace(FirstFeature=lambda: first))
    assert error.value.code == 'feature_budget_exceeded'


def exception_leaves(error):
    """Accept either the original error or an aggregate that preserves it."""
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in exception_leaves(child)]
    return [error]


@pytest.mark.parametrize('adapter_failure', [False, True])
def test_catalog_cleanup_attempts_every_monitor_and_adapter_then_releases_caches(adapter_failure):
    from solidworks_mcp.documents import DocumentCatalog
    from test_document_catalog_v2 import Adapter, model

    events = []
    monitor_error = RuntimeError('First synthetic monitor cleanup failed.')
    adapter_error = RuntimeError('Synthetic adapter cleanup failed.')

    class Watch:
        def __init__(self, name, error=None):
            self.name, self.error = name, error

        def close(self):
            events.append(self.name)
            if self.error:
                raise self.error

    class CleanupAdapter(Adapter):
        def close(self):
            events.append('adapter')
            self.closed = True
            if adapter_failure:
                raise adapter_error

    adapter = CleanupAdapter()
    adapter.models = [model(title='Первая'), model(title='Вторая')]
    catalog = DocumentCatalog(adapter)
    catalog.list()
    entries = list(catalog._entries)
    for index, entry in enumerate(entries):
        # These caches stand for native references/cursor snapshots. Keeping
        # external entry references also catches traceback-retained caches.
        entry.geometry['objects'] = [object()]
        entry.features.update(watch=Watch(f'watch_{index}', monitor_error if index == 0 else None),
                              references={'feature': object()})

    with pytest.raises(Exception) as error:
        catalog.close()
    leaves = exception_leaves(error.value)
    assert monitor_error in leaves, 'The first cleanup failure must not be swallowed.'
    if adapter_failure:
        assert adapter_error in leaves, 'All cleanup failures must remain available for diagnostics.'
    assert events == ['watch_0', 'watch_1', 'adapter']
    assert adapter.closed is True
    assert catalog._entries == []
    assert all(entry.geometry == {} and entry.features == {} for entry in entries)


def test_runtime_retirement_resets_every_catalog_cache_even_when_close_raises():
    from solidworks_mcp.runtime_v2 import Runtime

    failure = RuntimeError('Synthetic catalog retirement failure.')

    class Catalog:
        def close(self):
            raise failure

    runtime = Runtime(None)
    runtime._catalog = Catalog()
    runtime._geometry = object()
    runtime._features = object()
    runtime._connection_epoch = 'old_connection'
    with pytest.raises(Exception) as error:
        runtime._release_catalog()
    assert failure in exception_leaves(error.value)
    assert runtime._catalog is None
    assert runtime._geometry is None
    assert runtime._features is None
    assert runtime._connection_epoch is None
