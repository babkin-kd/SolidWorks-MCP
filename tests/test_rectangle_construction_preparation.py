"""Full-session preparation with actual domain resolver and artificial CAD."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import binding
from solidworks_mcp.features import FeatureReference
from solidworks_mcp.jobs import ExecutionFailure, JobStore
from solidworks_mcp.rectangle_construction_catalog import RectangleConstructionCatalog
from solidworks_mcp.rectangle_snapshot import SCOPE
from test_rectangle_snapshot import adapter as empty_adapter
from test_native_first_save_full_capture import CaptureAdapter


PLANE_ID = 'feat_' + 'a'*32


@pytest.fixture
def prepared(empty_adapter, monkeypatch, tmp_path):
    adapter = empty_adapter
    monkeypatch.setattr(binding, 'queried', lambda raw, interface: raw)
    base = CaptureAdapter()
    neighbor = deepcopy(base.first_save_part_snapshot(base.model))
    neighbor['scope'] = SCOPE
    neighbor['clone_state']['creation_controls'] = adapter.part_creation_controls(adapter.model)
    cfg = adapter.cfg
    entry = NS(document_id='doc_target', model=adapter.model, identity=id(adapter.model), features={})
    other_model = object()
    other = NS(document_id='doc_neighbor', model=other_model, identity=id(other_model), features={})
    entry.features['references'] = {PLANE_ID: FeatureReference(PLANE_ID, 'Основная', cfg, b'0')}
    original_reader = adapter.rectangle_construction_snapshot
    neighbor_event = [0]
    neighbor_reads = [0]
    def read(model):
        if model is adapter.model: return original_reader(model)
        neighbor_reads[0] += 1
        return deepcopy(neighbor)
    adapter.rectangle_construction_snapshot = read
    adapter.documents = lambda: [adapter.model, other_model]
    original_snapshot = adapter.snapshot
    adapter.snapshot = lambda model: original_snapshot(model) if model is adapter.model else {
        'document_type': 'part', 'title': 'Сосед', 'active_configuration': 'Основная'}
    original_watch = adapter.watch_part
    adapter.watch_part = lambda model: original_watch(model) if model is adapter.model else NS(
        poll=lambda: neighbor_event[0], close=lambda: setattr(adapter, 'closed', adapter.closed+1))
    adapter.application_busy = lambda: False
    adapter.configuration_identity = lambda model, name: cfg
    documents = NS(adapter=adapter, resolve=lambda doc, config: (entry if doc == 'doc_target' else other, {}))
    store = JobStore(tmp_path/'rectangle-prepare.sqlite')
    catalog = RectangleConstructionCatalog(documents, store, 'rectangle_connection')
    rows = [dict(document_id=e.document_id, document_type='part', active_configuration='Основная',
        configurations=['Основная'], path='', visible=True, dependencies=[], mode={'read_only_state': 0})
        for e in [entry, other]]
    semantic = dict(documents=rows, active_document_id=entry.document_id, reference_graph=[],
        windows=[{'document_id': e.document_id} for e in [entry, other]], files={}, app={'visible': True})
    catalog.sessions._capture_session = lambda guarded_ids=(): ([entry, other], deepcopy(semantic))
    yield NS(adapter=adapter, catalog=catalog, semantic=semantic, neighbor=neighbor,
             neighbor_event=neighbor_event, neighbor_reads=neighbor_reads, entry=entry)
    store.close()


def prepare(data, **changes):
    return data.catalog.prepare_sketch('doc_target', 'Основная', **{
        'plane_object_id': PLANE_ID, 'width_mm': 40., 'height_mm': 20., **changes})


def test_complete_prepare_is_readonly_binds_neighbor_and_requested_dimensions(prepared):
    result = prepare(prepared)
    assert result['native_execution_available'] is False
    assert result['revision_scope'] == 'empty_part_rectangle_sketch_v1'
    assert result['expected_geometry'] == dict(solid_body_count=0, sketch_count=1, width_mm=40., height_mm=20.)
    assert set(result['baseline']['snapshots']) == {'doc_target', 'doc_neighbor'}
    assert prepare(prepared)['revision'] == result['revision']
    assert prepare(prepared, width_mm=45.)['revision'] != result['revision']
    assert prepared.neighbor_reads[0] == 12
    assert prepared.adapter.closed > 0


def test_neighbor_data_is_bound_even_when_target_and_session_stamp_are_unchanged(prepared):
    first = prepare(prepared)
    prepared.neighbor['clone_state']['properties'][''][0]['value'] = 'Изменение'
    assert prepare(prepared)['revision'] != first['revision']


def test_foreign_reference_and_wrong_configuration_are_not_name_fallbacks(prepared):
    with pytest.raises(ExecutionFailure) as failure: prepare(prepared, plane_object_id='feat_'+'b'*32)
    assert failure.value.code == 'object_reference_not_found'
    prepared.entry.features['references'][PLANE_ID].configuration = 'Другая'
    with pytest.raises(ExecutionFailure) as failure: prepare(prepared)
    assert failure.value.code == 'object_configuration_mismatch'


@pytest.mark.parametrize('fault', ['inactive', 'readonly', 'saved', 'hidden', 'references', 'window'])
def test_unsupported_target_state_is_refused_before_any_execution(prepared, fault):
    row = prepared.semantic['documents'][0]
    if fault == 'inactive': prepared.semantic['active_document_id'] = 'doc_neighbor'
    elif fault == 'readonly': row['mode']['read_only_state'] = 1
    elif fault == 'saved': row['path'] = 'C:/example.SLDPRT'
    elif fault == 'hidden': row['visible'] = False
    elif fault == 'references': prepared.semantic['reference_graph'] = [{'source': 'doc_target'}]
    else: prepared.semantic['windows'].pop(0)
    with pytest.raises(ExecutionFailure): prepare(prepared)


def test_change_and_undo_in_neighbor_during_target_getter_invalidates_whole_preparation(prepared):
    prepared.adapter.hook = lambda: prepared.neighbor_event.__setitem__(0, prepared.neighbor_event[0]+1)
    with pytest.raises(ExecutionFailure) as failure: prepare(prepared)
    assert failure.value.code == 'rectangle_session_changed'


def test_invalid_input_never_starts_native_observation(prepared):
    prepared.adapter.documents = lambda: pytest.fail('Unexpected CAD access')
    with pytest.raises(ExecutionFailure): prepare(prepared, width_mm=True)


def test_poll_failure_still_releases_the_newly_owned_watch(prepared):
    closed = []
    def fail(): raise RuntimeError('artificial poll failure')
    prepared.adapter.watch_part = lambda model: NS(poll=fail, close=lambda: closed.append(model))
    with pytest.raises(RuntimeError): prepare(prepared)
    assert closed == [prepared.adapter.model]
