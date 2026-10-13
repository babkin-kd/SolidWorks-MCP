"""Real DocumentCatalog/NativeSession reads; artificial files/snapshots, no CAD."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.native_document_open import NativeDocumentOpenCatalog
from test_native_document_open_v2 import OpenAdapter
from test_rectangle_extrusion_postconditions import proof as extrusion_proof

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b2_session_mapping as helper
finally:
    sys.path.remove(scripts)


def other_view_namespace(snapshot):
    snapshot = deepcopy(snapshot)
    binding = snapshot['native_observations']['annotation_view_bindings']
    replacements = {value: 'av_' + f'{index + 1:032x}' for index, value in enumerate(binding['view_ids'])}
    binding['view_ids'] = [replacements[value] for value in binding['view_ids']]
    binding['dimension_views'] = {axis: replacements[value] for axis, value in binding['dimension_views'].items()}
    return snapshot


@pytest.fixture
def integrated(tmp_path, extrusion_proof):
    adapter = OpenAdapter(tmp_path)
    target = adapter.add('Одинаковая деталь', saved=False)
    neighbor = adapter.add('Сохранённый сосед', saved=True)
    neighbor.state['title'] = target.state['title']
    for model in (target, neighbor):
        model.state['configurations'] = ['Основная']
        model.state['needs_save'] = True
        model.mode['drawing_state'] = None
    # Deliberately identical titles/windows: names can never select a mapping.
    for model, window in adapter.windows: window['title'] = 'Одинаковое окно'
    adapter.active = target
    server_documents = DocumentCatalog(adapter)
    server_documents.list()
    target.state['update_stamp'] += 1
    server_documents.list()
    target.state['update_stamp'] -= 1
    server_documents.list()
    native_documents = DocumentCatalog(adapter)
    native_session = NativeDocumentOpenCatalog(native_documents, None, 'artificial-independent')
    server_session = NativeDocumentOpenCatalog(server_documents, None, 'artificial-server')
    base = extrusion_proof[1]['snapshots']['target']

    def capture():
        native_entries, native_semantic = native_session._capture_session()
        server_entries, server_semantic = server_session._capture_session()
        native = dict(semantic=native_semantic,
                      snapshots={entry.document_id: deepcopy(base) for entry in native_entries})
        server = dict(semantic=server_semantic,
                      snapshots={entry.document_id: other_view_namespace(base) for entry in server_entries})
        return native_entries, native, server_entries, server

    native_entries, actual, server_entries, server = capture()
    bridges = [helper.HeldDocumentBridge(entry.document_id, entry.identity,
        next(window['hwnd'] for model, window in adapter.windows if model.identity == entry.identity),
        dict(artificial_original_b1_bridge=True, original_document_id=entry.document_id))
        for entry in server_entries]
    return NS(adapter=adapter, target=target, neighbor=neighbor, native_entries=native_entries,
        actual=actual, server=server, bridges=bridges, capture=capture,
        native_documents=native_documents, server_documents=server_documents)


def compare(x, *, server=True, previous=None):
    return helper.compare_mapped_session(x.actual, x.server if server else None,
        native_entries=x.native_entries, bridges=x.bridges, previous=previous)


def rehash(row):
    row['observation_revision'] = helper.observation_hash(row['document_id'], row['observation_sequence'],
        {key: row[key] for key in helper.METADATA_FIELDS})


def test_actual_native_session_catalog_hashes_map_by_held_canonical_hwnd_preserving_native_counters(integrated):
    x = integrated
    actual, server = deepcopy(x.actual), deepcopy(x.server)
    proof = compare(x)
    assert proof['raw_actual'] == helper._detach(actual) and proof['raw_server'] == helper._detach(server)
    assert x.actual == actual and x.server == server
    assert proof['cross_server_comparison_verified'] is True
    assert proof['accepted'] is proof['native_acceptance'] is proof['cleanup_authorized'] is proof['mutation_authorized'] is False
    mapping = proof['document_mapping']
    assert set(mapping) == set(x.actual['snapshots']) and set(mapping.values()) == set(x.server['snapshots'])
    original = {row['document_id']: row for row in actual['semantic']['documents']}
    mapped = {row['document_id']: row for row in proof['mapped_state']['semantic']['documents']}
    for local, logical in mapping.items():
        assert mapped[logical]['observation_sequence'] == original[local]['observation_sequence']
        assert mapped[logical]['observation_revision'] != original[local]['observation_revision']
        expected = next(row for row in server['semantic']['documents'] if row['document_id'] == logical)
        if expected['observation_sequence'] != mapped[logical]['observation_sequence']:
            assert mapped[logical]['observation_revision'] != expected['observation_revision']
    assert any(row['observation_sequence'] == 3 for row in server['semantic']['documents'])
    assert all(row['observation_sequence'] == 1 for row in actual['semantic']['documents'])
    assert proof['comparison']['full_native_semantic_verified'] is True
    assert proof['mapped_revision_is_derived'] is True and proof['server_revision_copied'] is False


def test_one_logical_namespace_compares_actual_histories_without_copying_server_counters(integrated):
    proof = compare(integrated)
    mapped = proof['mapped_state']
    result = helper.compare_observed_sessions(mapped, integrated.server)
    assert result['raw_actual'] == mapped and result['raw_expected'] == helper._detach(integrated.server)
    assert result['catalog_histories_equated'] is False
    assert len(result['actual_observation_checks']) == len(result['snapshot_comparisons']) == 2


@pytest.mark.parametrize('field,value', [('observation_sequence', True), ('observation_sequence', 0),
    ('observation_sequence', -1), ('observation_sequence', '1'), ('observation_revision', 'obs_wrong'),
    ('update_stamp', 500), ('needs_save', False), ('document_id', 'doc_' + 'f' * 32)])
def test_actual_catalog_counter_hash_tampering_refuses_mapping(integrated, field, value):
    x = integrated
    x.actual['semantic']['documents'][0][field] = value
    with pytest.raises(ValueError): compare(x)


@pytest.mark.parametrize('field,value', [('update_stamp', 500), ('title', 'Чужое имя'),
    ('path', 'C:/foreign.sldprt'), ('needs_save', False), ('active_configuration', 'Чужая'),
    ('view', {'hostile': True}), ('visible', False), ('dependencies', ['C:/other.sldprt']),
    ('dependency_files', [{'hostile': True}]), ('mode', {'blocking_state': 2}), ('file', None)])
def test_rehashed_native_and_all_extended_fields_still_compare_exactly(integrated, field, value):
    x = integrated
    row = next(row for row in x.actual['semantic']['documents'] if row['file'] is not None)
    row[field] = value
    if field in helper.METADATA_FIELDS: rehash(row)
    with pytest.raises(ValueError): compare(x)


@pytest.mark.parametrize('fault', ['window_title', 'window_handle', 'app', 'file_bytes', 'file_identity',
    'active', 'snapshot', 'missing_snapshot', 'extra_snapshot', 'partial_metadata', 'unknown_metadata',
    'partial_semantic', 'missing_entry', 'extra_entry'])
def test_complete_native_windows_files_application_snapshots_and_census_are_never_dropped(integrated, fault):
    x = integrated
    semantic = x.actual['semantic']
    if fault == 'window_title': semantic['windows'][0]['title'] = 'Чужое окно'
    elif fault == 'window_handle': semantic['windows'][0]['hwnd'] += 1000
    elif fault == 'app': semantic['application']['search_folders'] = 'changed'
    elif fault == 'file_bytes': semantic['files'][0]['file']['bytes'] += 1
    elif fault == 'file_identity': semantic['files'][0]['file']['identity'][1] += 1
    elif fault == 'active': semantic['active_document_id'] = None
    elif fault == 'snapshot': next(iter(x.actual['snapshots'].values()))['clone_state']['body']['name'] = 'Чужое тело'
    elif fault == 'missing_snapshot': x.actual['snapshots'].pop(next(iter(x.actual['snapshots'])))
    elif fault == 'extra_snapshot': x.actual['snapshots']['doc_' + 'e' * 32] = deepcopy(next(iter(x.actual['snapshots'].values())))
    elif fault == 'partial_metadata': semantic['documents'][0].pop('update_stamp')
    elif fault == 'unknown_metadata': semantic['documents'][0]['future_snapshot_field'] = 1
    elif fault == 'partial_semantic': semantic.pop('reference_graph')
    elif fault == 'missing_entry': x.native_entries = x.native_entries[:-1]
    elif fault == 'extra_entry': x.native_entries = [*x.native_entries, x.native_entries[0]]
    with pytest.raises(ValueError): compare(x)


@pytest.mark.parametrize('fault', ['missing', 'foreign_canonical', 'scalar_identity', 'wrong_hwnd',
    'duplicate_logical_id', 'duplicate_canonical', 'empty_receipt', 'hidden', 'two_windows'])
def test_only_separately_held_canonical_hwnd_receipts_can_map_documents(integrated, fault):
    x = integrated
    if fault == 'missing': x.bridges.pop()
    elif fault == 'foreign_canonical': x.bridges[0] = replace(x.bridges[0], canonical_identity=object())
    elif fault == 'scalar_identity': x.bridges[0] = replace(x.bridges[0], canonical_identity='Одинаковая деталь')
    elif fault == 'wrong_hwnd': x.bridges[0] = replace(x.bridges[0], hwnd=999)
    elif fault == 'duplicate_logical_id': x.bridges[1] = replace(x.bridges[1], server_document_id=x.bridges[0].server_document_id)
    elif fault == 'duplicate_canonical': x.bridges[1] = replace(x.bridges[1], canonical_identity=x.bridges[0].canonical_identity)
    elif fault == 'empty_receipt': x.bridges[0] = replace(x.bridges[0], receipt={})
    elif fault == 'hidden':
        window = x.actual['semantic']['windows'].pop()
        next(row for row in x.actual['semantic']['documents'] if row['document_id'] == window['document_id'])['visible'] = False
    else:
        window = deepcopy(x.actual['semantic']['windows'][0])
        window['hwnd'] += 1000
        x.actual['semantic']['windows'].append(window)
    with pytest.raises((ValueError, ExecutionFailure)): compare(x)


def test_complete_reference_graph_translates_only_declared_document_owner_fields(integrated):
    x = integrated
    # Actual production NativeSession builds this edge from live returned model
    # handles; graph fields here remain artificial because B2 CAD is not run.
    native_target = next(entry.document_id for entry in x.native_entries if entry.identity == x.target.identity)
    native_neighbor = next(entry.document_id for entry in x.native_entries if entry.identity == x.neighbor.identity)
    logical_target = next(bridge.server_document_id for bridge in x.bridges if bridge.canonical_identity == x.target.identity)
    logical_neighbor = next(bridge.server_document_id for bridge in x.bridges if bridge.canonical_identity == x.neighbor.identity)
    data = dict(path=x.neighbor.state['path'], configuration='Основная', name=native_target,
                origin='component', native_suppression_state=2)
    x.actual['semantic']['reference_graph'] = [dict(parent_document_id=native_target, document_id=native_neighbor, **data)]
    x.server['semantic']['reference_graph'] = [dict(parent_document_id=logical_target, document_id=logical_neighbor, **data)]
    proof = compare(x)
    edge = proof['mapped_state']['semantic']['reference_graph'][0]
    assert edge['parent_document_id'] == logical_target and edge['document_id'] == logical_neighbor
    assert edge['name'] == native_target  # No arbitrary recursive string replacement.
    x.actual['semantic']['reference_graph'][0]['native_suppression_state'] = 0
    with pytest.raises(ValueError): compare(x)


def test_mapping_only_scalar_rename_mode_uses_actual_values_and_never_invents_server_observation(integrated):
    x = integrated
    previous = compare(x)
    x.target.state['update_stamp'] += 1
    x.native_entries, x.actual, _, x.server = x.capture()
    proof = compare(x, server=False, previous=previous)
    assert proof['raw_server'] is proof['comparison'] is None
    assert proof['cross_server_comparison_verified'] is False
    assert proof['own_counter_history_checked'] is True and proof['server_counter_history_checked'] is False
    assert any(row['update_stamp'] == x.target.state['update_stamp'] for row in proof['mapped_state']['semantic']['documents'])
    again = compare(x, previous=proof)
    assert again['cross_server_comparison_verified'] is True and again['server_counter_history_checked'] is False


def test_own_counter_history_checks_actual_metadata_changes_without_equating_catalog_counts(integrated):
    x = integrated
    previous = compare(x)
    x.target.state['update_stamp'] += 1
    x.native_entries, x.actual, _, x.server = x.capture()
    proof = compare(x, previous=previous)
    assert proof['own_counter_history_checked'] is proof['server_counter_history_checked'] is True
    row = next(row for row in x.actual['semantic']['documents'] if row['update_stamp'] == x.target.state['update_stamp'])
    row['observation_sequence'] -= 1
    rehash(row)  # A mathematically valid token cannot conceal its own history.
    with pytest.raises(ValueError, match='counter'): compare(x, previous=previous)


def test_equal_metadata_after_real_intermediate_observations_can_have_larger_actual_counter(integrated):
    x = integrated
    previous = compare(x)
    x.target.state['update_stamp'] += 1
    x.native_documents.list()
    x.target.state['update_stamp'] -= 1
    x.native_entries, x.actual, _, x.server = x.capture()
    proof = compare(x, previous=previous)
    assert proof['own_counter_history_checked'] is True
    assert proof['raw_actual']['semantic']['documents'] != previous['raw_actual']['semantic']['documents']


@pytest.mark.parametrize('fault', ['source_hash', 'logical_hash', 'mapping'])
def test_previous_proof_cannot_replace_actual_source_hashes_or_original_mapping(integrated, fault):
    x = integrated
    previous = compare(x)
    if fault == 'source_hash': previous['raw_actual']['semantic']['documents'][0]['observation_revision'] = 'wrong'
    elif fault == 'logical_hash': previous['raw_server']['semantic']['documents'][0]['observation_revision'] = 'wrong'
    else: previous['document_mapping'][next(iter(previous['document_mapping']))] = 'doc_' + 'f' * 32
    with pytest.raises(ValueError): compare(x, previous=previous)


@pytest.mark.parametrize('fault', ['counter_rehashed', 'metadata_rehashed', 'no_retained_projection', 'entry_counter_bool'])
def test_mapping_only_rejects_forged_self_consistent_observation_against_actual_catalog_entry(integrated, fault):
    x = integrated
    row = x.actual['semantic']['documents'][0]
    entry = next(entry for entry in x.native_entries if entry.document_id == row['document_id'])
    if fault == 'counter_rehashed':
        row['observation_sequence'] += 100
        rehash(row)
    elif fault == 'metadata_rehashed':
        row['update_stamp'] += 100
        rehash(row)
    elif fault == 'no_retained_projection': entry.observed = None
    else: entry.sequence = True
    with pytest.raises(ValueError, match='producer catalog'): compare(x, server=False)


@pytest.mark.parametrize('fault', ['missing_file', 'duplicate_file', 'partial_file', 'missing_view', 'missing_snapshot'])
def test_mapping_only_never_fills_unavailable_full_native_fields_from_previous_server_state(integrated, fault):
    x = integrated
    previous = compare(x)
    if fault == 'missing_file': x.actual['semantic']['files'].clear()
    elif fault == 'duplicate_file': x.actual['semantic']['files'].append(deepcopy(x.actual['semantic']['files'][0]))
    elif fault == 'partial_file': x.actual['semantic']['files'][0]['file'].pop('sha256')
    elif fault == 'missing_view': x.actual['semantic']['documents'][0].pop('view')
    else: x.actual['snapshots'].pop(next(iter(x.actual['snapshots'])))
    with pytest.raises(ValueError): compare(x, server=False, previous=previous)
