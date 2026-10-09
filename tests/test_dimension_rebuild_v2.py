"""Native-shaped rebuild result/context regressions; no actual CAD calls."""

from types import SimpleNamespace
import pytest
from solidworks_mcp import cad_dimensions
from solidworks_mcp.jobs import ExecutionFailure


def adapter_for(monkeypatch, model, active, pending):
    monkeypatch.setattr(cad_dimensions.binding, 'wrap', lambda raw, cls: raw)
    class Adapter(cad_dimensions.CadDimensionsMixin):
        _sw = SimpleNamespace(ActiveDoc=active)
        _module = SimpleNamespace(IModelDoc2=object)
        def identity(self, obj): return id(obj)
        def pending_rebuild(self, obj):
            assert obj is model
            return pending
    return Adapter()


@pytest.mark.parametrize('returned,pending,expected', [
    (True, False, True), (True, True, False), (False, False, False),
    (None, False, False), (1, False, False)])
def test_force_rebuild_requires_native_success_and_cleared_pending(monkeypatch, returned, pending, expected):
    calls = []
    model = SimpleNamespace(ForceRebuild3=lambda top_only: calls.append(top_only) or returned)
    # This reproduces the misleading native success observed with EditRebuild3;
    # it cannot establish a successfully recomputed geometry.
    model.EditRebuild3 = lambda: pytest.fail('Do not accept EditRebuild3 success as physical recomputation.')
    adapter = adapter_for(monkeypatch, model, model, pending)
    assert adapter.rebuild_dimension_document(model) is expected
    assert calls == [False]


@pytest.mark.parametrize('active', [None, object()])
def test_inactive_target_is_rejected_before_any_rebuild(monkeypatch, active):
    model = SimpleNamespace(ForceRebuild3=lambda _: pytest.fail('Never rebuild an inactive target.'))
    adapter = adapter_for(monkeypatch, model, active, False)
    with pytest.raises(ExecutionFailure) as error:
        adapter.rebuild_dimension_document(model)
    assert error.value.code == 'document_not_active'


def test_native_failure_propagates_without_an_automatic_second_rebuild(monkeypatch):
    calls = []
    failure = RuntimeError('Native rebuild acknowledgement lost.')
    def force(top_only):
        calls.append(top_only)
        raise failure
    model = SimpleNamespace(ForceRebuild3=force)
    adapter = adapter_for(monkeypatch, model, model, False)
    with pytest.raises(RuntimeError) as error:
        adapter.rebuild_dimension_document(model)
    assert error.value is failure and calls == [False]
