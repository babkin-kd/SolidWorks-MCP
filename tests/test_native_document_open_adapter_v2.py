"""Artificial OpenDoc6 acknowledgement/ownership cases; no native acceptance."""

from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

from solidworks_mcp.cad_native_document_open import CadNativeDocumentOpenMixin
from solidworks_mcp.jobs import ExecutionFailure


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    from solidworks_mcp import cad_native_document_open as native
    monkeypatch.setattr(native.binding, 'wrap', lambda raw, cls: raw)
    adapter = CadNativeDocumentOpenMixin()
    adapter._module = SimpleNamespace(IModelDoc2=object)
    adapter.identity = lambda model: model.token
    baseline, loaded = SimpleNamespace(token='before'), SimpleNamespace(token='loaded')
    calls = []
    adapter._sw = SimpleNamespace(OpenDoc6=lambda *args: calls.append(args) or (loaded, 0, 0),
        GetDocumentDependencies2=lambda *args: None, GetConfigurationNames=lambda path: ['Основная'])
    return adapter, baseline, loaded, calls, str(tmp_path / 'Контрольная деталь.SLDPRT')


@pytest.mark.parametrize('kind,extension,configuration,type_id', [
    ('part','.SLDPRT','Основная',1),('assembly','.SLDASM','Сборочная',2),('drawing','.SLDDRW','',3)])
@pytest.mark.parametrize('read_only,options', [(False,1),(True,3)])
def test_exact_return_and_native_options(bridge, kind, extension, configuration, type_id, read_only, options):
    adapter, before, model, calls, filename = bridge
    filename = filename[:-7] + extension
    receipt = adapter.new_native_open_receipt([before], filename, kind, configuration, read_only)
    result = adapter.open_native_document(receipt)
    assert calls == [(filename, type_id, options, configuration, 0, 0)]
    assert receipt.model is model and receipt.raw_model is model
    assert receipt.identity == 'loaded' and receipt.returned_new_identity
    assert receipt.native_call_attempted and receipt.native_call_returned and not receipt.pending_open
    assert receipt.acknowledgement_valid and result == dict(native_call_returned=True,returned_new_identity=True,errors=0,warnings=0)


def test_throwing_open_is_pending_without_adoption_or_retry(bridge):
    adapter, before, _, calls, filename = bridge
    def throws(*args):
        calls.append(args)
        raise RuntimeError('Open acknowledgement lost after possible effect')
    adapter._sw.OpenDoc6 = throws
    receipt = adapter.new_native_open_receipt([before], filename, 'part', 'Основная', False)
    with pytest.raises(RuntimeError): adapter.open_native_document(receipt)
    assert receipt.pending_open and not receipt.native_call_returned and receipt.model is None
    with pytest.raises(ExecutionFailure) as error: adapter.open_native_document(receipt)
    assert error.value.uncertain and error.value.code == 'native_open_receipt_reused' and len(calls) == 1


def test_returned_existing_handle_never_owned(bridge):
    adapter, before, _, calls, filename = bridge
    # Another proxy for the same canonical identity, not Python object identity.
    borrowed = SimpleNamespace(token=before.token)
    adapter._sw.OpenDoc6 = lambda *args: calls.append(args) or (borrowed,0,0)
    receipt = adapter.new_native_open_receipt([before],filename,'part','Основная',False)
    with pytest.raises(ExecutionFailure) as error: adapter.open_native_document(receipt)
    assert error.value.code == 'native_open_existing_handle' and error.value.uncertain
    assert receipt.model is borrowed and not receipt.returned_new_identity
    assert receipt.native_call_returned and not receipt.pending_open and len(calls) == 1


@pytest.mark.parametrize('raw', [None, True, (), (None,0), (None,0,0,0)])
def test_invalid_registered_tuple_does_not_prove_no_effect(bridge, raw):
    adapter, before, _, calls, filename = bridge
    adapter._sw.OpenDoc6 = lambda *args: calls.append(args) or raw
    receipt = adapter.new_native_open_receipt([before],filename,'part','Основная',False)
    with pytest.raises(ExecutionFailure) as error: adapter.open_native_document(receipt)
    assert error.value.uncertain and error.value.code == 'native_open_acknowledgement_invalid'
    assert receipt.native_call_returned and not receipt.acknowledgement_valid and len(calls) == 1


@pytest.mark.parametrize('errors,warnings', [(True,0),(0,False),(-1,0),(0,2**31),(None,0),(0,'0')])
def test_bad_outputs_preserve_returned_handle_but_do_not_validate_acknowledgement(bridge, errors, warnings):
    adapter, before, model, _, filename = bridge
    adapter._sw.OpenDoc6 = lambda *args: (model,errors,warnings)
    receipt = adapter.new_native_open_receipt([before],filename,'part','Основная',False)
    with pytest.raises(ExecutionFailure) as error: adapter.open_native_document(receipt)
    assert error.value.uncertain and receipt.raw_model is model and receipt.model is model
    assert receipt.identity == 'loaded' and not receipt.acknowledgement_valid


@pytest.mark.parametrize('model_present,errors,warnings', [(False,1,0),(True,0,4),(True,2,3),(False,0,0)])
def test_no_handle_and_nonzero_codes_are_evidence_for_domain_not_success(bridge, model_present, errors, warnings):
    adapter, before, model, _, filename = bridge
    adapter._sw.OpenDoc6 = lambda *args: (model if model_present else None, errors, warnings)
    receipt = adapter.new_native_open_receipt([before],filename,'part','Основная',False)
    assert adapter.open_native_document(receipt) == dict(native_call_returned=True,
        returned_new_identity=model_present,errors=errors,warnings=warnings)
    assert receipt.acknowledgement_valid


def test_returned_raw_is_retained_if_identity_getter_throws(bridge):
    adapter, before, model, _, filename = bridge
    receipt = adapter.new_native_open_receipt([before],filename,'part','Основная',False)
    adapter.identity = lambda model: (_ for _ in ()).throw(RuntimeError('canonical identity unavailable'))
    with pytest.raises(RuntimeError): adapter.open_native_document(receipt)
    assert receipt.raw_model is model and receipt.model is model and receipt.native_call_returned
    assert not receipt.returned_new_identity and not receipt.acknowledgement_valid


@pytest.mark.parametrize('change', ['relative','type','extension','empty_config','drawing_config','bool_readonly','null_path','null_config'])
def test_bad_arguments_reject_before_native_call(bridge, change):
    adapter, before, _, calls, filename = bridge
    kind, configuration, read_only = 'part','Основная',False
    if change == 'relative': filename = 'Деталь.SLDPRT'
    if change == 'type': kind = True
    if change == 'extension': filename += '.step'
    if change == 'empty_config': configuration = ' '
    if change == 'drawing_config': kind,filename = 'drawing',filename[:-7]+'.SLDDRW'
    if change == 'bool_readonly': read_only = 1
    if change == 'null_path': filename += '\x00'
    if change == 'null_config': configuration += '\x00'
    with pytest.raises(ExecutionFailure) as error:
        adapter.new_native_open_receipt([before],filename,kind,configuration,read_only)
    assert error.value.uncertain is False and calls == []


def test_duplicate_baseline_proxy_and_exhausted_model_budget(bridge):
    adapter, before, _, calls, filename = bridge
    with pytest.raises(ExecutionFailure) as error:
        adapter.new_native_open_receipt([before,SimpleNamespace(token='before')],filename,'part','Основная',False)
    assert error.value.code == 'native_open_census_invalid'
    with pytest.raises(ExecutionFailure) as error:
        adapter.new_native_open_receipt((SimpleNamespace(token=i) for i in range(5001)),filename,'part','Основная',False)
    assert error.value.code == 'native_session_budget_exceeded' and calls == []


def test_wrong_thread_cannot_start_open_or_mark_receipt_attempted(bridge):
    adapter, before, _, calls, filename = bridge
    receipt = adapter.new_native_open_receipt([before],filename,'part','Основная',False)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ExecutionFailure) as error: pool.submit(adapter.open_native_document,receipt).result()
    assert error.value.code == 'wrong_apartment' and not error.value.uncertain
    assert not receipt.native_call_attempted and not receipt.pending_open and calls == []


def test_passive_loaded_lookup_returns_canonical_borrowed_identity_without_opening(bridge):
    adapter, before, _, calls, filename = bridge; reads=[]
    adapter._sw.GetOpenDocumentByName = lambda path: reads.append(path) or SimpleNamespace(token=before.token)
    assert adapter.native_open_loaded_identity(filename) == before.token
    adapter._sw.GetOpenDocumentByName = lambda path: None
    assert adapter.native_open_loaded_identity(filename) is None
    assert reads == [filename] and calls == []


@pytest.mark.parametrize('models',[None,42,'bad'])
def test_invalid_baseline_collection_is_known_prewrite_failure(bridge,models):
    adapter, _, _, calls, filename = bridge
    with pytest.raises(ExecutionFailure) as error:
        adapter.new_native_open_receipt(models,filename,'part','Основная',False)
    assert error.value.code=='native_open_census_invalid' and not error.value.uncertain and calls==[]


def test_inventory_uses_transitive_search_false_no_model_open_and_drawing_no_configuration_getter(bridge, tmp_path):
    adapter, _, _, calls, filename = bridge
    dependency = str(tmp_path/'Компонент.SLDPRT'); reads=[]
    adapter._sw.GetDocumentDependencies2 = lambda *args: reads.append(args) or ['Компонент',dependency]
    assert adapter.native_open_file_inventory(filename,'part') == dict(
        dependencies=[dict(name='Компонент',path=dependency,document_type='part')],configurations=['Основная'])
    adapter._sw.GetConfigurationNames = lambda path: (_ for _ in ()).throw(AssertionError('Drawing configuration getter'))
    drawing = filename[:-7]+'.SLDDRW'
    assert adapter.native_open_file_inventory(drawing,'drawing')['configurations'] == []
    assert reads == [(filename,True,False,False),(drawing,True,False,False)] and calls == []


@pytest.mark.parametrize('raw',[True,['name'],['name','relative.SLDPRT'],['','/tmp/model.SLDPRT'],['name',42],['name','/tmp/model.step']])
def test_invalid_dependency_inventory_fails_closed(bridge,raw):
    adapter, _, _, calls, filename = bridge
    adapter._sw.GetDocumentDependencies2 = lambda *args: raw
    with pytest.raises(ExecutionFailure): adapter.native_open_file_inventory(filename,'part')
    assert calls == []


@pytest.mark.parametrize('raw',[None,True,[],['Основная','Основная'],[''],[42],['Основная\x00']])
def test_missing_or_invalid_configuration_inventory_fails_closed(bridge,raw):
    adapter, _, _, calls, filename = bridge
    adapter._sw.GetConfigurationNames = lambda *args: raw
    with pytest.raises(ExecutionFailure) as error: adapter.native_open_file_inventory(filename,'part')
    assert error.value.code == 'native_open_configurations_unavailable' and calls == []
