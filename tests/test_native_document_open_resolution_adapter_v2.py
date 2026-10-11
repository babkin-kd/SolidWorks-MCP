"""Artificial exact reference/activation acknowledgements; no CAD acceptance."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_native_document_open import CadNativeDocumentOpenMixin
from solidworks_mcp.jobs import ExecutionFailure


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    from solidworks_mcp import cad_native_document_open as native
    monkeypatch.setattr(native.binding, 'wrap', lambda raw, interface: raw)
    adapter = CadNativeDocumentOpenMixin()
    adapter._module = NS(IModelDoc2=object, IAssemblyDoc=object, IComponent2=object, IDrawingDoc=object, IView=object)
    adapter.identity = lambda model: model.token
    target = NS(token='target', GetTitle=lambda: 'Рабочая деталь')
    calls = []
    adapter._sw = NS(ActivateDoc3=lambda *args: calls.append(args) or (target, 0))
    adapter.active_document = lambda: target
    path = str(tmp_path / 'Компонент.SLDPRT')
    component = NS(GetSuppression2=lambda: 2, IsSpeedPak=False, IsVirtual=False,
        GetModelDoc2=lambda: target, GetPathName=lambda: path, ReferencedConfiguration='Основная', Name2='Крепёж-1')
    return adapter, target, component, calls, path


@pytest.mark.parametrize('error', [0, 2])
def test_one_exact_no_rebuild_activation_receipt(bridge, error):
    a, target, _, calls, _ = bridge
    a._sw.ActivateDoc3 = lambda *args: calls.append(args) or (target, error)
    receipt = a.new_native_activation_receipt(target)
    assert a.activate_native_open_document(receipt) == dict(native_call_returned=True, native_error=error)
    assert calls == [('Рабочая деталь', False, 1, 0)]
    assert receipt.raw_model is target and receipt.native_call_returned and not receipt.pending_activation
    with pytest.raises(ExecutionFailure):
        a.activate_native_open_document(receipt)
    assert len(calls) == 1


def test_throwing_activation_retains_pending_without_retry(bridge):
    a, target, _, calls, _ = bridge
    def throwing(*args):
        calls.append(args)
        raise RuntimeError('Native acknowledgement lost')
    a._sw.ActivateDoc3 = throwing
    receipt = a.new_native_activation_receipt(target)
    with pytest.raises(RuntimeError):
        a.activate_native_open_document(receipt)
    assert receipt.pending_activation and not receipt.native_call_returned and receipt.raw_model is None
    with pytest.raises(ExecutionFailure):
        a.activate_native_open_document(receipt)
    assert len(calls) == 1


@pytest.mark.parametrize('result', [None, (None, 0), (NS(token='foreign'), 0), (None, True), (None, 3), (None, 0, 0)])
def test_normally_returned_activation_is_not_success_proof(bridge, result):
    a, target, _, _, _ = bridge
    a._sw.ActivateDoc3 = lambda *args: result
    receipt = a.new_native_activation_receipt(target)
    with pytest.raises(ExecutionFailure):
        a.activate_native_open_document(receipt)
    assert receipt.native_call_returned and not receipt.pending_activation


def test_activation_requires_matching_active_model_and_sta(bridge):
    a, target, _, calls, _ = bridge
    receipt = a.new_native_activation_receipt(target)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ExecutionFailure):
            pool.submit(a.activate_native_open_document, receipt).result()
    assert calls == [] and not receipt.native_call_attempted
    a.active_document = lambda: NS(token='foreign')
    with pytest.raises(ExecutionFailure):
        a.activate_native_open_document(receipt)
    assert receipt.raw_model is target and receipt.native_call_returned


def test_resolved_saved_assembly_references_use_exact_model_handles(bridge):
    a, target, c, _, path = bridge
    model = NS(GetType=lambda: 2, GetComponentCount=lambda top: 1, GetComponents=lambda top: [c])
    assert a.native_open_model_references(model) == [(target, dict(path=path, configuration='Основная',
        name='Крепёж-1', origin='component', native_suppression_state=2))]
    assert a.native_open_model_references(NS(GetType=lambda: 1)) == []


@pytest.mark.parametrize('field,value', [('IsSpeedPak', True), ('IsVirtual', True), ('IsVirtual', 0),
    ('GetSuppression2', lambda: 0), ('GetSuppression2', lambda: 1), ('GetSuppression2', lambda: True),
    ('GetModelDoc2', lambda: None), ('ReferencedConfiguration', ''), ('GetPathName', lambda: 'relative.SLDPRT')])
def test_unproved_component_mode_or_handle_cannot_be_omitted(bridge, field, value):
    a, _, c, _, _ = bridge
    setattr(c, field, value)
    model = NS(GetType=lambda: 2, GetComponentCount=lambda top: 1, GetComponents=lambda top: [c])
    with pytest.raises(ExecutionFailure):
        a.native_open_model_references(model)


@pytest.mark.parametrize('counts,components', [([True], []), ([1], None), ([0], False), ([1, True], 'one')])
def test_incomplete_or_untyped_component_enumeration_rejects(bridge, counts, components):
    a, _, c, _, _ = bridge
    values = iter(counts)
    model = NS(GetType=lambda: 2, GetComponentCount=lambda top: next(values),
        GetComponents=lambda top: [c] if components == 'one' else components)
    with pytest.raises(ExecutionFailure):
        a.native_open_model_references(model)


def test_drawing_sheet_is_skipped_but_referenced_view_retains_exact_model(bridge):
    a, target, _, _, path = bridge
    sheet = NS(GetReferencedModelName=lambda: '', Type=1)
    view = NS(GetReferencedModelName=lambda: path, ReferencedDocument=target, ReferencedConfiguration='Основная')
    model = NS(GetType=lambda: 3, GetViews=lambda: [[sheet, view]])
    assert a.native_open_model_references(model) == [(target, dict(path=path, configuration='Основная',
        name='view_1', origin='drawing_view', native_suppression_state=None))]


@pytest.mark.parametrize('groups', [False, [None], [[NS(GetReferencedModelName=lambda: '', Type=2)]],
    [[NS(GetReferencedModelName=lambda: None)]]])
def test_incomplete_or_broken_drawing_view_is_not_silently_skipped(bridge, groups):
    a, _, _, _, _ = bridge
    with pytest.raises(ExecutionFailure):
        a.native_open_model_references(NS(GetType=lambda: 3, GetViews=lambda: groups))
