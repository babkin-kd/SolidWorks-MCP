"""Passive B2 full-session namespace mapping; no native calls or authority.

NativeSession adds six census fields after DocumentCatalog hashes its seven
native metadata fields. Each catalog's actual positive counter and original
hash are checked independently. Cross-catalog counters have separate histories;
they cannot be equated or replaced by a server baseline. Unknown row schemas
are explicit gates because their original hashed projection is then unknown.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import PureWindowsPath
import re

from solidworks_mcp.owned_rectangle_feature import _canonical
from verifier_b2_native_observer import compare_b2_snapshot


METADATA_FIELDS = frozenset(('title', 'path', 'document_type', 'needs_save', 'configurations',
                             'active_configuration', 'update_stamp'))
OBSERVATION_FIELDS = frozenset(('document_id', 'observation_sequence', 'observation_revision'))
CENSUS_FIELDS = frozenset(('view', 'visible', 'dependencies', 'dependency_files', 'mode', 'file'))
SEMANTIC_FIELDS = frozenset(('documents', 'windows', 'files', 'application', 'active_document_id', 'reference_graph'))
SCOPE = 'b2_canonical_hwnd_session_mapping_v1'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _detach(value):
    try:
        return json.loads(_json(value))
    except (TypeError, ValueError) as error:
        raise ValueError('Complete finite JSON native observation required.') from error


def _id(value):
    return type(value) is str and re.fullmatch(r'doc_[0-9a-f]{32}', value) is not None


def _metadata(row):
    return {key: row[key] for key in METADATA_FIELDS}


def observation_hash(document_id, sequence, metadata):
    """Exact current DocumentCatalog._observe encoding; not a native receipt."""
    return 'obs_' + hashlib.sha256(_json(dict(document_id=document_id, sequence=sequence,
                                             snapshot=metadata)).encode('utf8')).hexdigest()


def _file(facts):
    _require(type(facts) is dict and set(facts) == {'path', 'bytes', 'sha256', 'identity', 'mtime_ns', 'ctime_ns'}
        and type(facts['path']) is str and bool(facts['path']) and type(facts['bytes']) is int and facts['bytes'] > 0
        and type(facts['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', facts['sha256']) is not None
        and type(facts['identity']) is list and len(facts['identity']) == 2
        and all(type(value) is int for value in facts['identity'])
        and type(facts['mtime_ns']) is int and type(facts['ctime_ns']) is int,
        'Complete actual native file fingerprint required; missing fields cannot be baseline-filled.')


def _state(value):
    _require(type(value) is dict and set(value) == {'semantic', 'snapshots'}, 'Complete native semantic+snapshots required.')
    state = _detach(value)
    semantic = state['semantic']
    _require(type(semantic) is dict and set(semantic) == SEMANTIC_FIELDS, 'Exact NativeSession semantic schema required.')
    rows = semantic['documents']
    _require(type(rows) is list and 0 < len(rows) <= 32, 'Complete bounded B2 document census required.')
    ids, hashes = [], []
    for row in rows:
        _require(type(row) is dict and set(row) == METADATA_FIELDS | OBSERVATION_FIELDS | CENSUS_FIELDS,
            'Observation projection gate: unknown/missing metadata or census fields cannot be silently omitted.')
        document_id, sequence = row['document_id'], row['observation_sequence']
        _require(_id(document_id) and type(sequence) is int and sequence > 0,
            'Actual opaque document ID and positive catalog observation counter required.')
        _require(type(row['update_stamp']) is int and type(row['needs_save']) is bool
            and row['document_type'] == 'part' and type(row['title']) is str and bool(row['title'])
            and type(row['path']) is str and type(row['configurations']) is list
            and all(type(cfg) is str and bool(cfg) for cfg in row['configurations'])
            and type(row['active_configuration']) is str and row['active_configuration'] in row['configurations'],
            'Complete actually observed part metadata required.')
        computed = observation_hash(document_id, sequence, _metadata(row))
        _require(type(row['observation_revision']) is str and row['observation_revision'] == computed,
            'Actual observation counter/ID/seven-field metadata hash is inconsistent.')
        _require(type(row['view']) is dict and bool(row['view']) and type(row['visible']) is bool
            and type(row['dependencies']) is list and type(row['dependency_files']) is list
            and type(row['mode']) is dict
            and set(row['mode']) == {'blocking_state', 'read_only_state', 'editing_sketch',
                                     'editing_component', 'view_only', 'drawing_state'}
            and type(row['mode']['blocking_state']) is int and type(row['mode']['read_only_state']) is int
            and all(type(row['mode'][key]) is bool for key in ('editing_sketch', 'editing_component', 'view_only')),
            'Full native view/visibility/dependencies/mode must remain observable.')
        _require(type(row['file']) in (dict, type(None))
            and (bool(row['path']) == (row['file'] is not None)), 'Complete saved/unsaved file observation required.')
        if row['file'] is not None:
            _file(row['file'])
        for facts in row['dependency_files']:
            _file(facts)
        ids.append(document_id)
        hashes.append(dict(document_id=document_id, actual_sequence=sequence,
                           actual_revision=row['observation_revision'], seven_field_hash_verified=True))
    _require(len(set(ids)) == len(ids) and type(state['snapshots']) is dict and set(state['snapshots']) == set(ids),
        'Full distinct document and snapshot rosters must agree exactly.')
    windows = semantic['windows']
    _require(type(windows) is list and all(type(row) is dict and set(row) == {'document_id', 'hwnd', 'title'}
        and row['document_id'] in ids and type(row['hwnd']) is int and 0 < row['hwnd'] < 2**63
        and type(row['title']) is str for row in windows)
        and len({row['hwnd'] for row in windows}) == len(windows), 'Complete unique native HWND census required.')
    for row in rows:
        _require(row['visible'] == any(window['document_id'] == row['document_id'] for window in windows),
                 'Actual document visibility and full window census disagree.')
    _require(semantic['active_document_id'] is None or semantic['active_document_id'] in ids,
        'Active document must belong to the complete current census.')
    app = semantic['application']
    _require(type(app) is dict and set(app) == {'user_control', 'visible', 'current_directory', 'search_folders'}
        and type(app['user_control']) is bool and type(app['visible']) is bool
        and type(app['current_directory']) is str and type(app['search_folders']) is str,
        'Complete declared native application context required.')
    _require(type(semantic['files']) is list and all(type(row) is dict and set(row) == {'document_type', 'file'}
        and type(row['file']) is dict for row in semantic['files']), 'Complete native disk file census required.')
    for row in semantic['files']:
        _file(row['file'])
    kinds = {'.sldprt': 'part', '.sldasm': 'assembly', '.slddrw': 'drawing'}
    required_files = {}
    for row in rows:
        facts = ([row['file']] if row['file'] is not None else []) + row['dependency_files']
        for item in facts:
            kind = kinds.get(PureWindowsPath(item['path']).suffix.lower())
            _require(kind is not None, 'Native disk census contains an unsupported file type.')
            key, descriptor = item['path'].casefold(), dict(document_type=kind, file=item)
            _require(key not in required_files or _json(required_files[key]) == _json(descriptor),
                'Repeated actual disk fingerprint disagrees within the complete session.')
            required_files[key] = descriptor
    declared_files = {row['file']['path'].casefold(): row for row in semantic['files']}
    _require(len(declared_files) == len(semantic['files']) and _json(declared_files) == _json(required_files),
        'Complete disk census must contain exactly all actual document/dependency fingerprints.')
    graph = semantic['reference_graph']
    _require(type(graph) is list and len(graph) <= 5000
        and all(type(row) is dict and {'parent_document_id','document_id','path','configuration','name','origin'} <= set(row)
            and row['parent_document_id'] in ids and row['document_id'] in ids
            and all(type(row[key]) is str and bool(row[key]) for key in ('path','configuration','name','origin'))
            for row in graph), 'Complete reference graph must use current explicit document owners.')
    return state, hashes


def _semantic_projection(semantic):
    projection = deepcopy(semantic)
    for row in projection['documents']:
        # These TWO fields were independently validated above with their actual
        # IDs/counters/metadata. All remaining observed/native fields stay exact.
        row.pop('observation_sequence')
        row.pop('observation_revision')
    projection['documents'].sort(key=lambda row: row['document_id'])
    projection['windows'].sort(key=lambda row: row['hwnd'])
    projection['reference_graph'].sort(key=lambda row: (row['parent_document_id'], row['name'], row['document_id']))
    return projection


def compare_observed_sessions(actual, expected):
    """Compare one logical namespace, retaining both raw observation histories.

Every counter/hash is validated in its own observation. All other semantic
fields (including update_stamp) compare exactly; every full snapshot uses the
existing B2 full-view-row/axis-partition bijection comparator. This is passive
evidence, not a production revision or permission. NativeSession's schema does
not include CommandInProgress/preferences: root MUST observe those separately.
"""
    actual, actual_hashes = _state(actual)
    expected, expected_hashes = _state(expected)
    _require(_json(_semantic_projection(actual['semantic'])) == _json(_semantic_projection(expected['semantic'])),
        'Full native session differs beyond catalog-local counters/revisions.')
    _require(set(actual['snapshots']) == set(expected['snapshots']), 'Full snapshot roster differs.')
    snapshots = {key: compare_b2_snapshot(actual['snapshots'][key], expected['snapshots'][key])
                 for key in sorted(actual['snapshots'])}
    return dict(scope='b2_observed_session_comparison_v1', raw_actual=actual, raw_expected=expected,
        actual_observation_checks=actual_hashes, expected_observation_checks=expected_hashes,
        catalog_histories_equated=False, full_native_semantic_verified=True, snapshot_comparisons=snapshots,
        accepted=False, native_acceptance=False, cleanup_authorized=False, mutation_authorized=False)


@dataclass(frozen=True)
class HeldDocumentBridge:
    """Root-verified original B1 HWND/canonical bridge, never JSON ownership.

canonical_identity is a held native IUnknown compared by equality, not name,
GetID, Python id, pointer text or hash. receipt is the root's independently
checked raw B1/HWND evidence; mapper never reconstructs native authority from it.
B2 currently requires one visible HWND per bridged part. Other profiles gate.
"""
    server_document_id: str
    canonical_identity: object
    hwnd: int
    receipt: dict


def _counter_history(previous, current):
    previous, _ = _state(previous)
    current, _ = _state(current)
    old = {row['document_id']: row for row in previous['semantic']['documents']}
    new = {row['document_id']: row for row in current['semantic']['documents']}
    _require(set(old) == set(new), 'Catalog incarnation/roster changed between bounded B2 observations.')
    for key in old:
        changed = _json(_metadata(old[key])) != _json(_metadata(new[key]))
        _require(new[key]['observation_sequence'] >= old[key]['observation_sequence'] + int(changed),
            'Actual own catalog counter regressed or failed to advance for changed metadata.')
    # Equal endpoints can hide intervening observe/change/revert calls. A larger
    # positive counter is allowed, never asserted to equal another catalog's.


def compare_mapped_session(actual, server, *, native_entries, bridges, previous=None):
    """Map complete independent NativeSession data using held canonical/HWND only.

    native_entries is the full actual _capture_session returned list/tuple of
    DocumentCatalog._Entry objects (document_id, identity, sequence, observed).
    The actual row must match that actual catalog's retained counter/metadata.
    bridges is a full list/tuple of HeldDocumentBridge, separately verified by root
    from the original B1 journal/HWND bridge. No native getter or model call occurs.
    previous, if supplied, is this function's earlier returned full proof.
    server=None explicitly performs mapping-only observation for scalar/rename
    routes whose public results contain no full session. It makes no cross-server
    claim. An absent previous server observation is never invented for history.
    mapped_state keeps ACTUAL counters and native values. Only logical document IDs
    change; its revision is DERIVED from mapped ID+actual counter+actual seven fields,
    never copied from server. Both original namespaces and raw revisions remain.
"""
    actual, _ = _state(actual)
    server = _state(server)[0] if server is not None else None
    # Mapping-only still validates every actually observed snapshot. This is
    # shape/producer evidence only, not an invented matching server result.
    for snapshot in actual['snapshots'].values():
        compare_b2_snapshot(snapshot, snapshot)
    _require(type(native_entries) in (list, tuple) and type(bridges) in (list, tuple)
        and len(native_entries) == len(bridges) == len(actual['semantic']['documents']),
        'Complete separately held canonical/HWND bindings required for every observed document.')
    ids = {row['document_id'] for row in actual['semantic']['documents']}
    _require(all(all(hasattr(entry, name) for name in ('document_id','identity','sequence','observed'))
                 for entry in native_entries), 'Actual retained native catalog observation fields required.')
    _require({entry.document_id for entry in native_entries} == ids
        and len({entry.document_id for entry in native_entries}) == len(native_entries),
        'Native entry and actual observed document rosters differ.')
    native_rows = {row['document_id']: row for row in actual['semantic']['documents']}
    for entry in native_entries:
        row = native_rows[entry.document_id]
        _require(type(entry.sequence) is int and entry.sequence == row['observation_sequence']
            and type(entry.observed) is dict and set(entry.observed) == METADATA_FIELDS
            and _json(entry.observed) == _json(_metadata(row)),
            'Actual producer catalog counter/retained metadata differs from supplied observation.')
    identities = [_canonical(entry.identity) for entry in native_entries]
    _require(all(sum(identity == other for other in identities) == 1 for identity in identities),
        'Actual native canonical document census must be bijective.')
    mapping, receipts = {}, []
    for bridge in bridges:
        _require(type(bridge) is HeldDocumentBridge and _id(bridge.server_document_id)
            and type(bridge.hwnd) is int and 0 < bridge.hwnd < 2**63
            and type(bridge.receipt) is dict and bool(bridge.receipt), 'Exact root-held B1/HWND bridge required.')
        canonical = _canonical(bridge.canonical_identity)
        matches = [entry for entry in native_entries if entry.identity == canonical]
        _require(len(matches) == 1, 'Bridge must bind one original held canonical native entry.')
        entry = matches[0]
        native_windows = [row for row in actual['semantic']['windows'] if row['document_id'] == entry.document_id]
        _require(len(native_windows) == 1 and native_windows[0]['hwnd'] == bridge.hwnd,
            'One-window canonical/HWND gate: hidden/multiple/foreign windows cannot be inferred by names.')
        if server is not None:
            server_windows = [row for row in server['semantic']['windows'] if row['document_id'] == bridge.server_document_id]
            _require(len(server_windows) == 1 and server_windows[0]['hwnd'] == bridge.hwnd,
                'Original canonical/HWND bridge differs from independently observed server window.')
        _require(entry.document_id not in mapping and bridge.server_document_id not in mapping.values(),
            'Held document bridges must define an exact one-to-one namespace mapping.')
        mapping[entry.document_id] = bridge.server_document_id
        receipts.append(dict(native_document_id=entry.document_id, server_document_id=bridge.server_document_id,
            hwnd=bridge.hwnd, held_canonical_equality_verified=True, receipt=_detach(bridge.receipt)))
    _require(set(mapping) == ids and (server is None or set(mapping.values()) == set(server['snapshots'])),
        'No native/server document may be omitted, added or adopted from a roster delta.')
    mapped = deepcopy(actual)
    for row in mapped['semantic']['documents']:
        row['document_id'] = mapping[row['document_id']]
        row['observation_revision'] = observation_hash(row['document_id'], row['observation_sequence'], _metadata(row))
    for row in mapped['semantic']['windows']:
        row['document_id'] = mapping[row['document_id']]
    for row in mapped['semantic']['reference_graph']:
        row['parent_document_id'] = mapping[row['parent_document_id']]
        row['document_id'] = mapping[row['document_id']]
    active = mapped['semantic']['active_document_id']
    mapped['semantic']['active_document_id'] = mapping[active] if active is not None else None
    mapped['snapshots'] = {mapping[key]: value for key, value in mapped['snapshots'].items()}
    mapped['semantic']['documents'].sort(key=lambda row: row['document_id'])
    mapped['semantic']['reference_graph'].sort(key=lambda row: (row['parent_document_id'], row['name'], row['document_id']))
    comparison = compare_observed_sessions(mapped, server) if server is not None else None
    server_history_checked = False
    if previous is not None:
        _require(type(previous) is dict and previous.get('scope') == SCOPE
            and previous.get('document_mapping') == mapping, 'Exact earlier mapper proof and stable canonical namespace required.')
        _counter_history(previous['raw_actual'], actual)
        if previous.get('raw_server') is not None and server is not None:
            _counter_history(previous['raw_server'], server)
            server_history_checked = True
    return dict(scope=SCOPE, raw_actual=actual, raw_server=server, mapped_state=mapped,
        document_mapping=mapping, canonical_hwnd_receipts=receipts, comparison=comparison,
        mapped_revision_is_derived=True, server_revision_copied=False,
        cross_server_comparison_verified=server is not None,
        own_counter_history_checked=previous is not None,
        server_counter_history_checked=server_history_checked,
        accepted=False, native_acceptance=False, cleanup_authorized=False, mutation_authorized=False)
