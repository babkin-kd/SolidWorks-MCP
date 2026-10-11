"""File closure/borrowed data tests with artificial files, not CAD evidence."""

from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.native_document_open_manifest import NativeOpenFileManifest
from solidworks_mcp.native_document_save import native_file_facts


@pytest.fixture
def fixture(tmp_path):
    part = tmp_path/'Деталь.SLDPRT'; part.write_bytes(b'artificial part')
    assembly = tmp_path/'Сборка.SLDASM'; assembly.write_bytes(b'artificial assembly')
    drawing = tmp_path/'Чертёж.SLDDRW'; drawing.write_bytes(b'artificial drawing')
    reference = lambda path, kind: dict(name=path.stem,path=str(path),document_type=kind)
    inventories = {str(part):dict(dependencies=[],configurations=['Основная','Вторая']),
        str(assembly):dict(dependencies=[reference(part,'part')],configurations=['Основная']),
        str(drawing):dict(dependencies=[reference(assembly,'assembly')],configurations=[])}
    calls=[]; loaded={}
    adapter=SimpleNamespace(native_open_loaded_identity=lambda path:loaded.get(path),
        native_open_file_inventory=lambda path,kind:calls.append((path,kind)) or deepcopy(inventories[path]))
    return SimpleNamespace(part=part,assembly=assembly,drawing=drawing,adapter=adapter,
        inventories=inventories,calls=calls,loaded=loaded,entries=[],semantic=dict(documents=[],files=[]))


def capture(fixture, path=None, kind='part', config='Основная'):
    return NativeOpenFileManifest(fixture.adapter).capture(str(path or fixture.part),kind,config,
                                                         fixture.entries,fixture.semantic)


def borrow(fixture,path,kind='part',token='resident',document_id='doc_before'):
    facts=native_file_facts(str(path),kind)
    fixture.entries.append(SimpleNamespace(document_id=document_id,identity=token))
    fixture.semantic['documents'].append(dict(document_id=document_id,file=facts))
    fixture.semantic['files'].append(dict(document_type=kind,file=facts))
    fixture.loaded[str(path)]=token


def test_part_manifest_uses_exact_configuration_and_two_complete_file_observations(fixture):
    value=capture(fixture,config='Вторая')
    assert value['configuration']=='Вторая' and value['source_document_type']=='part'
    assert value['session_unique_bytes']==fixture.part.stat().st_size
    assert value['files']==[dict(document_type='part',file=native_file_facts(str(fixture.part),'part'),
        configurations=['Основная','Вторая'],dependencies=[],borrowed_document_id=None)]
    assert fixture.calls==[(str(fixture.part),'part')]*2


def test_transitive_drawing_closure_binds_borrowed_component_without_owning_it(fixture):
    borrow(fixture,fixture.part)
    value=capture(fixture,fixture.drawing,'drawing','')
    assert len(value['files'])==3
    assert value['session_unique_bytes']==sum(path.stat().st_size for path in (fixture.part,fixture.assembly,fixture.drawing))
    borrowed=[row for row in value['files'] if row['borrowed_document_id']]
    assert len(borrowed)==1 and borrowed[0]['borrowed_document_id']=='doc_before'
    assert fixture.semantic['documents'][0]['file']==native_file_facts(str(fixture.part),'part')
    assert len(fixture.calls)==6  # Every saved file inventory is independently queried twice.


def test_already_loaded_source_is_rejected_before_inventory(fixture):
    borrow(fixture,fixture.part)
    with pytest.raises(ExecutionFailure) as error:capture(fixture)
    assert error.value.code=='native_document_already_loaded' and fixture.calls==[]


def test_hardlink_source_rejected_even_when_native_lookup_does_not_recognize_alias(fixture,tmp_path):
    borrow(fixture,fixture.part)
    alias=tmp_path/'Другой путь.SLDPRT'; os.link(fixture.part,alias)
    assert fixture.adapter.native_open_loaded_identity(str(alias)) is None
    with pytest.raises(ExecutionFailure) as error:capture(fixture,alias)
    assert error.value.code=='native_document_already_loaded' and fixture.calls==[]


def test_unknown_resident_data_is_not_adopted_as_new_or_added_to_baseline(fixture):
    fixture.loaded[str(fixture.part)]='unlisted_loaded_data'
    with pytest.raises(ExecutionFailure) as error:capture(fixture)
    assert error.value.code=='native_open_census_invalid' and fixture.entries==[] and fixture.calls==[]


def test_resident_dependency_identity_must_match_declared_borrowed_model(fixture):
    borrow(fixture,fixture.part); fixture.loaded[str(fixture.part)]='different_native_identity'
    with pytest.raises(ExecutionFailure) as error:capture(fixture,fixture.assembly,'assembly')
    assert error.value.code=='native_open_census_invalid'


def test_multiple_models_for_one_physical_file_fail_closed(fixture):
    borrow(fixture,fixture.part)
    borrow(fixture,fixture.part,token='second_identity',document_id='doc_other')
    with pytest.raises(ExecutionFailure) as error:capture(fixture,fixture.assembly,'assembly')
    assert error.value.code=='native_open_loaded_alias_ambiguous'


def test_config_absence_is_known_prewrite_failure_without_fallback(fixture):
    with pytest.raises(ExecutionFailure) as error:capture(fixture,config='Не существует')
    assert error.value.code=='native_open_configuration_not_found' and not error.value.uncertain


def test_missing_dependency_is_not_dropped_from_manifest(fixture):
    fixture.part.unlink()
    with pytest.raises(ExecutionFailure) as error:capture(fixture,fixture.assembly,'assembly')
    assert error.value.code=='native_file_unavailable'


def test_file_edit_during_inventory_is_detected_in_same_observation(fixture):
    original=fixture.adapter.native_open_file_inventory
    def changed(path,kind):
        value=original(path,kind); fixture.part.write_bytes(b'changed artificial bytes'); return value
    fixture.adapter.native_open_file_inventory=changed
    with pytest.raises(ExecutionFailure) as error:capture(fixture)
    assert error.value.code=='native_file_changed_during_read'


def test_reference_graph_change_between_complete_observations_fails(fixture):
    original=fixture.adapter.native_open_file_inventory; reads=[]
    def changed(path,kind):
        value=original(path,kind); reads.append(path)
        if len(reads)>1: value['configurations']=['Основная']
        return value
    fixture.adapter.native_open_file_inventory=changed
    with pytest.raises(ExecutionFailure) as error:capture(fixture)
    assert error.value.code=='native_open_manifest_changed_during_read'


@pytest.mark.parametrize('fault',['raw','missing','bad_name','relative','null_path','bad_type','bad_kind'])
def test_malformed_dependency_inventory_fails_before_native_open(fixture,fault):
    inventory=fixture.inventories[str(fixture.assembly)]
    if fault=='raw': inventory['dependencies']=[True]
    elif fault=='missing': inventory['dependencies']=[dict(path=str(fixture.part))]
    else:
        row=inventory['dependencies'][0]
        if fault=='bad_name': row['name']=''
        if fault=='relative': row['path']='relative.SLDPRT'
        if fault=='null_path': row['path']+='\x00'
        if fault=='bad_type': row['document_type']=[]
        if fault=='bad_kind': row['document_type']='step'
    with pytest.raises(ExecutionFailure) as error:capture(fixture,fixture.assembly,'assembly')
    assert error.value.code=='native_open_inventory_invalid'


@pytest.mark.parametrize('names',[[],[''],['Основная','Основная'],[True],['Основная\x00']])
def test_invalid_file_configuration_census_rejected(fixture,names):
    fixture.inventories[str(fixture.part)]['configurations']=names
    with pytest.raises(ExecutionFailure) as error:capture(fixture)
    assert error.value.code=='native_open_configurations_unavailable'


def test_dependency_cycles_are_bounded_and_no_new_model_ownership_is_claimed(fixture):
    fixture.inventories[str(fixture.part)]['dependencies']=[dict(name='Сборка',path=str(fixture.assembly),document_type='assembly')]
    value=capture(fixture,fixture.assembly,'assembly')
    assert len(value['files'])==2 and len(fixture.calls)==4
    # File closure only; cyclic/load/configuration resolution remains a domain gate.
    assert not any(key in value for key in ('resolved','loaded','owned','succeeded'))


def test_full_session_byte_budget_includes_preexisting_unrelated_native_file(fixture,monkeypatch):
    borrow(fixture,fixture.part)
    from solidworks_mcp import native_document_open_manifest as native
    monkeypatch.setattr(native,'MAX_TOTAL_BYTES',fixture.part.stat().st_size+fixture.assembly.stat().st_size-1)
    with pytest.raises(ExecutionFailure) as error:capture(fixture,fixture.assembly,'assembly')
    assert error.value.code=='native_session_file_budget_exceeded'


def test_manifest_budget_limits_queued_source_and_dependencies(fixture,monkeypatch):
    from solidworks_mcp import native_document_open_manifest as native
    monkeypatch.setattr(native,'MAX_OPEN_DOCUMENTS',2)
    with pytest.raises(ExecutionFailure) as error:capture(fixture,fixture.drawing,'drawing','')
    assert error.value.code=='native_open_dependency_budget_exceeded'


def test_metadata_ids_cannot_stand_in_for_missing_canonical_baseline_entries(fixture):
    fixture.semantic['documents']=[dict(document_id='doc_missing',file=None)]
    with pytest.raises(ExecutionFailure) as error:capture(fixture)
    assert error.value.code=='native_open_census_invalid'
