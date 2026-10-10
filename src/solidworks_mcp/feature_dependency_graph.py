"""Complete bounded native feature relation captures; not a deletion approval."""

import hashlib
import uuid

from .documents import rejected
from .jobs import _json


SCOPE = 'part_feature_dependency_graph_v1'
CAPTURE_SCOPE = 'native_feature_relation_capture_v1'
LINK_FIELDS = ('parent_links', 'child_links', 'absorbed_links',
               'parent_links_without_child_confirmation', 'child_links_without_parent_confirmation')


def relation_semantics(capture, feature_rows):
    count = len(feature_rows)
    if (type(capture) is not dict or set(capture) != {'scope', 'feature_count', 'relations_read', *LINK_FIELDS}
            or capture['scope'] != CAPTURE_SCOPE or type(capture['feature_count']) is not int
            or capture['feature_count'] != count or not 0 <= count <= 5000
            or type(capture['relations_read']) is not int or not 0 <= capture['relations_read'] <= 100000):
        raise rejected('feature_dependency_capture_invalid', 'Expected a complete bounded relation capture.')
    links, work = {}, 0
    for field in LINK_FIELDS:
        rows = capture[field]
        if type(rows) is not list or len(rows) > 100000:
            raise rejected('feature_dependency_capture_invalid', 'Invalid relation array.')
        edges = []
        for edge in rows:
            if (type(edge) is not list or len(edge) != 2
                    or any(type(index) is not int or not 0 <= index < count for index in edge)):
                raise rejected('feature_dependency_capture_invalid', 'Relation endpoints must belong to captured nodes.')
            edges.append(tuple(edge))
        if edges != sorted(set(edges)):
            raise rejected('feature_dependency_capture_invalid', 'Relation arrays must be unique and ordered.')
        links[field] = set(edges)
        work += len(edges) if field in LINK_FIELDS[:3] else 0
    if work > capture['relations_read']:
        raise rejected('feature_dependency_capture_invalid', 'Relation work evidence cannot be smaller than captured links.')
    parents, children = links['parent_links'], links['child_links']
    if (links['parent_links_without_child_confirmation'] != parents - children
            or links['child_links_without_parent_confirmation'] != children - parents):
        raise rejected('feature_dependency_capture_invalid', 'Parent/child disagreement evidence is inconsistent.')
    owners = {}
    for owner, owned in links['absorbed_links']:
        if owned in owners:
            raise rejected('feature_dependency_capture_invalid', 'An absorbed feature cannot have two reported owners.')
        owners[owned] = feature_rows[owner]['native_id']
    for index, row in enumerate(feature_rows):
        if row['owner_native_id'] != owners.get(index):
            raise rejected('document_changed_during_read', 'Relation ownership differs from captured feature metadata.')
    return {'scope': CAPTURE_SCOPE, 'feature_count': count,
            **{field: [list(edge) for edge in sorted(links[field])] for field in LINK_FIELDS}}


def dependency_graph(catalog, document_id, configuration):
    """Read two full captures, then close all native identity/context checks.

    Indices describe only graph topology. object_id remains the only persistent
    feature target; unsupported native references remain null. This operation
    does not predict equations, annotations, external files or deletion effects.
    """
    adapter, documents = catalog.adapter, catalog.documents
    first = catalog._state(document_id, configuration)
    entry, identity, native, semantic, _, payload = first
    first_capture = adapter.feature_dependencies(native)
    relations = relation_semantics(first_capture, semantic['features'])
    previous = entry.features.get('dependency_incarnations', {})
    census, tokens, nodes = {}, [], []
    for index, (obj, row) in enumerate(zip(native, semantic['features'])):
        hint = row['native_id']
        if type(hint) is not int or hint in census:
            raise rejected('feature_identity_collision', 'Dependency nodes require unique native ID hints.')
        canonical = adapter.identity(obj)
        cached = previous.get(hint)
        token = cached[1] if cached is not None and cached[0] == canonical else 'node_' + uuid.uuid4().hex
        census[hint] = (canonical, token)
        tokens.append(token)
        try:
            ref = catalog._register(entry, configuration, identity, obj)
            reference_error = None
        except Exception as error:
            if getattr(error, 'code', None) not in ('persistent_reference_unavailable',
                    'persistent_reference_mismatch', 'object_reference_invalid', 'object_deleted', 'object_suppressed'):
                raise
            ref = None
            reference_error = {'code': error.code, 'message': str(error)}
        nodes.append({**row, 'node_index': index, 'object_id': ref.object_id if ref else None,
                      'persistent_reference_supported': ref is not None, 'reference_error': reference_error})

    closing = catalog._state(document_id, configuration)
    last_entry, last_identity, last_native, last_semantic, _, last_payload = closing
    last_capture = adapter.feature_dependencies(last_native)
    last_relations = relation_semantics(last_capture, last_semantic['features'])
    # Canonical equality can itself perform native work; it precedes the final
    # document/configuration read and notification poll, never follows them.
    same_native = (len(native) == len(last_native)
                   and all(census[row['native_id']][0] == adapter.identity(obj)
                           for row, obj in zip(semantic['features'], last_native)))
    same_config = identity == last_identity
    current, observed = documents.resolve(document_id, configuration)
    final_identity = adapter.configuration_identity(entry.model, configuration)
    final_config_equal = final_identity == identity
    final_sequence = entry.features['watch'].poll()
    if (last_entry is not entry or current is not entry or payload != last_payload
            or semantic != last_semantic or relations != last_relations or not same_native
            or not same_config or not final_config_equal or observed != payload['observed']
            or final_sequence != payload['event_sequence']):
        raise rejected('document_changed_during_read', 'Feature relation graph changed during collection; no partial graph returned.')
    # Only a successfully closed capture updates this bounded STA cache. Strong
    # canonical interfaces detect reuse of an integer hint across future reads.
    entry.features['dependency_incarnations'] = census
    revision_payload = {'scope': SCOPE, 'feature_state': payload, 'relations': relations,
                        'node_incarnations': tokens}
    revision = 'rev_' + hashlib.sha256(_json(revision_payload).encode('utf8')).hexdigest()
    return {'document_id': document_id, 'configuration': configuration,
            'revision_scope': SCOPE, 'revision': revision, 'feature_tree_revision': first[4],
            'nodes': nodes, 'relations': relations,
            'native_relation_work': [first_capture['relations_read'], last_capture['relations_read']],
            'all_reported_native_relations_captured': True,
            'deletion_impact_complete': False, 'deletion_authorized': False}
