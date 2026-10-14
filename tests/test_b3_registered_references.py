"""Actual catalog UUID/PID tables, artificial native adapters; no CAD calls."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.geometry import GeometryCatalog
from solidworks_mcp.component_topology import ComponentTopologyCatalog
from test_geometry_v2 import GeometryAdapter
from test_component_topology_v2 import TopologyAdapter
from test_dimension_domain_v2 import setup as dimension_setup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verifier_b3_registered_references import export_registered_references


def export(entry):
    return export_registered_references(entry, assert_safe=lambda: None)


@pytest.fixture
def part():
    adapter = GeometryAdapter(); adapter.body(faces=3)
    docs = DocumentCatalog(adapter); geometry = GeometryCatalog(docs)
    observed = docs.list()['documents'][0]
    context = dict(document_id=observed['document_id'], configuration='Основная',
                   expected_observation_revision=observed['observation_revision'])
    body = geometry.list(**context)['items'][0]
    faces = geometry.list(**context, body_id=body['object_id'], kind='face')['items']
    edges = geometry.list(**context, body_id=body['object_id'], kind='edge')['items']
    entry = docs.resolve(context['document_id'], 'Основная')[0]
    yield NS(adapter=adapter, docs=docs, entry=entry, body=body, faces=faces, edges=edges)
    docs.close()


def test_actual_geometry_registration_export_is_detached_and_passive(part):
    x = part; before = tuple(x.entry.geometry)
    r = export(x.entry)
    expected = {x.body['object_id'], *(f['object_id'] for f in x.faces), *(e['object_id'] for e in x.edges)}
    assert {row['object_id'] for row in r['rows']} == expected
    for row in r['rows']:
        ref = x.entry.geometry['references'][row['object_id']]
        assert row['persistent_id_hex'] == ref.persistent_id.hex()
        assert row['configuration'] == ref.configuration
        assert row['body_id'] == ref.body_id
    r['rows'][0]['persistent_id_hex'] = 'changed'
    assert tuple(x.entry.geometry) == before
    assert export(x.entry)['rows'][0]['persistent_id_hex'] != 'changed'
    assert r['accepted'] is r['native_acceptance'] is r['cleanup_authorized'] is False
    assert r['current_membership_verified'] is False


def test_actual_component_body_topology_owner_namespace_export():
    adapter = TopologyAdapter(); docs = DocumentCatalog(adapter); catalog = ComponentTopologyCatalog(docs)
    try:
        observed = docs.list()['documents'][0]
        context = dict(document_id=observed['document_id'], configuration='Основная',
                       expected_observation_revision=observed['observation_revision'])
        components = catalog.list(**context)['items']
        component = components[0]
        body = catalog.bodies(**context, component_id=component['component_id'])['items'][0]
        topology = catalog.list_topology(**context, component_id=component['component_id'],
            body_id=body['body_id'], kind='face')['items']
        entry = docs.resolve(context['document_id'], 'Основная')[0]
        r = export(entry)
        by_id = {row['object_id']: row for row in r['rows']}
        assert by_id[body['body_id']]['component_id'] == component['component_id']
        for face in topology:
            row = by_id[face['object_id']]
            assert row['component_id'] == component['component_id'] and row['body_id'] == body['body_id']
            assert row['configuration'] == 'Основная'
        assert {row['object_id'] for row in r['rows'] if row['family'] == 'component'} == {
            c['component_id'] for c in components}
    finally:
        docs.close()


def test_actual_feature_and_dimension_tables_are_exported_with_original_anchors(dimension_setup):
    adapter, dimensions, store, ids = dimension_setup
    dimensions.features.list(ids[0], 'Основная')
    dimensions.list(ids[0], 'Основная')
    entry = dimensions.documents.resolve(ids[0], 'Основная')[0]
    r = export(entry)
    assert {'feature', 'dimension'} <= {row['family'] for row in r['rows']}
    for row in r['rows']:
        if row['family'] == 'dimension':
            ref = entry.features['dimensions']['references'][row['object_id']]
            assert row['reference_anchor'] == ref.persistent_id
            row['reference_anchor']['dimension_pid_hex'] = '00'
            assert ref.persistent_id != row['reference_anchor']


@pytest.mark.parametrize('fault', ['key', 'pid', 'kind', 'body_owner', 'table', 'document', 'budget'])
def test_malformed_actual_registration_state_is_not_exported_as_a_bridge(part, fault):
    x = part; refs = x.entry.geometry['references']; ref = next(iter(refs.values()))
    if fault == 'key': refs['obj_'+'f'*32] = refs.pop(ref.object_id)
    elif fault == 'pid': ref.persistent_id = b''
    elif fault == 'kind': ref.kind = 'mesh'
    elif fault == 'body_owner': ref.body_id = 'invented'
    elif fault == 'table': x.entry.geometry['references'] = []
    elif fault == 'document': x.entry.document_id = 'foreign'
    else: x.entry.geometry['references'] = {str(i): ref for i in range(5001)}
    with pytest.raises(ValueError): export(x.entry)


def test_owner_gate_precedes_any_entry_access():
    class Forbidden:
        def __getattribute__(self, name): raise AssertionError('unadmitted catalog access')
    def reject(): raise ValueError('not owned')
    with pytest.raises(ValueError, match='not owned'):
        export_registered_references(Forbidden(), assert_safe=reject)


def test_empty_tables_not_created_and_two_owner_admissions_required():
    entry = NS(document_id='doc_'+'a'*32, geometry={}, features={})
    admitted = []
    r = export_registered_references(entry, assert_safe=lambda: admitted.append(True))
    assert len(admitted) == 2 and r['rows'] == []
    assert entry.geometry == entry.features == {}
