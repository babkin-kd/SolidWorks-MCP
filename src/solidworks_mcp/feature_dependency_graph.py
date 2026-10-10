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


class FeatureGraphRead:
    """STA-local, one-use frame shared by a graph and its enclosing context.

    The caller owns exactly two full tree snapshots. Retained canonical
    interfaces protect the census across both complete native relation reads.
    No cache is committed before the caller's additional captures also agree.
    """
    def __init__(self, catalog, document_id, configuration, first):
        self.catalog, self.document_id, self.configuration = catalog, document_id, configuration
        self.first = first
        self.entry, self.identity, self.native, self.semantic, _, self.payload = first
        self._second_started = self._closed = False
        self.last_relations = None
        captured = catalog.adapter.feature_dependencies(self.native)
        self.relations = relation_semantics(captured, self.semantic['features'])
        self.first_work = captured['relations_read']
        previous = self.entry.features.get('dependency_incarnations', {})
        self.census, self.tokens, self.nodes = {}, [], []
        for index, (obj, row) in enumerate(zip(self.native, self.semantic['features'])):
            hint = row['native_id']
            if type(hint) is not int or hint in self.census:
                raise rejected('feature_identity_collision', 'Dependency nodes require unique native ID hints.')
            canonical = catalog.adapter.identity(obj)
            cached = previous.get(hint)
            token = cached[1] if cached is not None and cached[0] == canonical else 'node_' + uuid.uuid4().hex
            self.census[hint] = (canonical, token)
            self.tokens.append(token)
            try:
                ref = catalog._register(self.entry, configuration, self.identity, obj)
                reference_error = None
            except Exception as error:
                if getattr(error, 'code', None) not in ('persistent_reference_unavailable',
                        'persistent_reference_mismatch', 'object_reference_invalid', 'object_deleted', 'object_suppressed'):
                    raise
                ref = None
                reference_error = {'code': error.code, 'message': str(error)}
            self.nodes.append({**row, 'node_index': index, 'object_id': ref.object_id if ref else None,
                               'persistent_reference_supported': ref is not None, 'reference_error': reference_error})

    def capture_second_relations(self):
        if self._second_started or self._closed:
            raise rejected('feature_capture_already_closed', 'A native relation read frame cannot be replayed.')
        self._second_started = True
        captured = self.catalog.adapter.feature_dependencies(self.native)
        # Validation copies typed relation rows before the final full snapshot.
        self.last_relations = relation_semantics(captured, self.semantic['features'])
        self.last_work = captured['relations_read']

    def close(self, last):
        if self._closed or self.last_relations is None:
            raise rejected('feature_capture_already_closed', 'Two relation captures and one closure are required.')
        self._closed = True
        adapter, documents = self.catalog.adapter, self.catalog.documents
        last_entry, last_identity, last_native, last_semantic, last_revision, last_payload = last
        same_native = (len(self.native) == len(last_native)
                       and all(self.census[row['native_id']][0] == adapter.identity(obj)
                               for row, obj in zip(self.semantic['features'], last_native)))
        same_config = self.identity == last_identity
        current, observed = documents.resolve(self.document_id, self.configuration)
        final_identity = adapter.configuration_identity(self.entry.model, self.configuration)
        final_config_equal = final_identity == self.identity
        final_sequence = self.entry.features['watch'].poll()
        if (last_entry is not self.entry or current is not self.entry or self.payload != last_payload
                or self.semantic != last_semantic or self.first[4] != last_revision
                or self.relations != self.last_relations or not same_native or not same_config
                or not final_config_equal or observed != self.payload['observed']
                or final_sequence != self.payload['event_sequence']):
            raise rejected('document_changed_during_read', 'Feature relation graph or context changed during collection.')
        self.entry.features['dependency_incarnations'] = self.census
        revision_payload = {'scope': SCOPE, 'feature_state': self.payload, 'relations': self.relations,
                            'node_incarnations': self.tokens}
        revision = 'rev_' + hashlib.sha256(_json(revision_payload).encode('utf8')).hexdigest()
        return {'document_id': self.document_id, 'configuration': self.configuration,
                'revision_scope': SCOPE, 'revision': revision, 'feature_tree_revision': self.first[4],
                'nodes': self.nodes, 'relations': self.relations,
                'native_relation_work': [self.first_work, self.last_work], 'feature_tree_read_count': 2,
                'all_reported_native_relations_captured': True,
                'deletion_impact_complete': False, 'deletion_authorized': False}


def dependency_graph(catalog, document_id, configuration):
    """Two full tree snapshots and relation captures; no deletion approval."""
    first = catalog._state(document_id, configuration)
    frame = FeatureGraphRead(catalog, document_id, configuration, first)
    frame.capture_second_relations()
    return frame.close(catalog._state(document_id, configuration))
