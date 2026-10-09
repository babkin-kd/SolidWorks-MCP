"""Opaque, document/configuration-scoped persistent references and bounded pages.

Only reads are supported here. Observation revisions prevent mixed snapshots,
but do not replace the full revision/rollback gates for future mutations.
"""

from dataclasses import dataclass
import uuid

from .documents import rejected


@dataclass
class _Reference:
    object_id: str
    kind: str
    configuration: str
    configuration_identity: object
    persistent_id: bytes
    body_id: str | None


@dataclass
class _Cursor:
    query: tuple
    revision: str
    configuration_identity: object
    offset: int
    objects: tuple


class GeometryCatalog:
    def __init__(self, documents):
        self.documents = documents
        self.adapter = documents.adapter

    def _context(self, document_id, configuration, expected_observation_revision):
        entry, observed = self.documents.resolve(document_id, configuration)
        for old in entry.geometry.get('cursors', {}).values():
            if old.revision != observed['observation_revision']:
                old.objects = ()  # Release stale native enumeration on the STA.
        if observed['document_type'] != 'part':
            raise rejected('unsupported_document_type', 'Geometry reads currently support part documents only.')
        if observed['active_configuration'] != configuration:
            raise rejected('configuration_not_active', 'Geometry requires the explicit active configuration; no automatic switch.')
        if not expected_observation_revision or observed['observation_revision'] != expected_observation_revision:
            raise rejected('observation_revision_mismatch', 'Document observation changed; obtain a fresh snapshot before reading geometry.')
        if self.adapter.pending_rebuild(entry.model):
            raise rejected('document_needs_rebuild', 'Geometry may be stale; rebuild explicitly before reading it.')
        identity = self.adapter.configuration_identity(entry.model, configuration)
        return entry, observed, identity

    def _confirm(self, entry, observed, configuration, identity):
        current, after = self.documents.resolve(entry.document_id, configuration)
        if (current is not entry or after['observation_revision'] != observed['observation_revision']
                or self.adapter.configuration_identity(entry.model, configuration) != identity
                or self.adapter.pending_rebuild(entry.model)):
            raise rejected('document_changed_during_read', 'Document/configuration changed during geometry collection; read again.')

    @staticmethod
    def _references(entry):
        return entry.geometry.setdefault('references', {})

    def _register(self, entry, obj, kind, configuration, identity, body_id=None):
        persistent_id = self.adapter.persistent_id(entry.model, obj)
        if not persistent_id:
            raise rejected('persistent_reference_unavailable', 'SolidWorks did not provide a persistent reference; no index fallback.')
        refs = self._references(entry)
        resolved = self.adapter.resolve_persistent_id(entry.model, persistent_id, kind)
        if self.adapter.identity(resolved) != self.adapter.identity(obj):
            raise rejected('persistent_reference_mismatch', 'Persistent reference resolved to a different native object.')
        # Bytes are only a cache lookup key, never proof of native identity.
        # Different representations may create aliases; existing opaque IDs
        # still resolve through their original persistent references. Avoid an
        # O(n²) scan of all faces/edges and compare cached IDs through the API.
        index = entry.geometry.setdefault('reference_index', {})
        key = (kind, configuration, body_id, persistent_id)
        reference = index.get(key)
        if (reference is not None and reference.configuration_identity == identity
                and self.adapter.same_persistent_id(entry.model, reference.persistent_id, persistent_id)):
            return reference
        if len(refs) >= 100000:
            raise rejected('reference_budget_exceeded', 'Document reference budget exceeded; narrow the geometry request.')
        reference = _Reference('obj_' + uuid.uuid4().hex, kind, configuration, identity, persistent_id, body_id)
        refs[reference.object_id] = reference
        index[key] = reference
        return reference

    def _resolve(self, entry, object_id, configuration, identity, required_kind=None):
        reference = self._references(entry).get(object_id)
        if reference is None:
            raise rejected('object_reference_not_found', 'Unknown object_id for this open document; list geometry again.')
        if reference.configuration != configuration or reference.configuration_identity != identity:
            raise rejected('object_configuration_mismatch', 'Object belongs to a different configuration or its previous incarnation.')
        if required_kind is not None and reference.kind != required_kind:
            raise rejected('object_kind_mismatch', f'This operation requires a {required_kind} reference.')
        obj = self.adapter.resolve_persistent_id(entry.model, reference.persistent_id, reference.kind)
        if reference.kind == 'body' and not self.adapter.body_is_current(entry.model, obj):
            raise rejected('object_not_in_active_configuration', 'Persistent body is not present in the explicit active configuration.')
        if reference.body_id is not None:
            parent, _ = self._resolve(entry, reference.body_id, configuration, identity, 'body')
            if self.adapter.identity(self.adapter.owner_body(obj, reference.kind)) != self.adapter.identity(parent):
                raise rejected('object_body_mismatch', 'Resolved topology no longer belongs to its registered body.')
            if not self.adapter.topology_is_current(parent, obj, reference.kind):
                raise rejected('object_not_in_current_body', 'Persistent topology is not present in its current active body.')
        return obj, reference

    def _summary(self, obj, reference):
        return {**self.adapter.geometry_summary(obj, reference.kind), 'object_id': reference.object_id,
                'kind': reference.kind, 'body_id': reference.body_id}

    def list(self, document_id, configuration, expected_observation_revision, *, kind='body',
             body_id=None, body_type='all', limit=100, cursor=''):
        if kind not in ('body', 'face', 'edge') or body_type not in ('all', 'solid', 'surface'):
            raise rejected('invalid_geometry_query', 'Unsupported geometry kind or body type.')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise rejected('invalid_limit', 'Geometry page limit must be between 1 and 200.')
        if (kind == 'body' and body_id is not None) or (kind != 'body' and not body_id):
            raise rejected('body_reference_required', 'Topology reads require an explicit body_id; body lists do not.')
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        query = (configuration, kind, body_id, body_type)
        cursors = entry.geometry.setdefault('cursors', {})
        body = None
        if kind != 'body':
            body, _ = self._resolve(entry, body_id, configuration, identity, 'body')
        offset = 0
        if cursor:
            prior = cursors.get(cursor)
            if prior is None or prior.query != query:
                raise rejected('invalid_geometry_cursor', 'Cursor belongs to another document/query or previous server session.')
            if prior.revision != observed['observation_revision'] or prior.configuration_identity != identity:
                raise rejected('stale_geometry_cursor', 'Document changed since the previous page; list geometry again.')
            offset = prior.offset
            objects = prior.objects
        elif kind == 'body':
            objects = self.adapter.bodies(entry.model, body_type)
        else:
            objects = self.adapter.topology(body, kind)
        objects = tuple(objects)
        if len(objects) > 100000:
            raise rejected('geometry_budget_exceeded', 'Native collection exceeds 100000 objects; narrow the model scope.')
        if offset > len(objects):
            raise rejected('stale_geometry_cursor', 'Geometry collection changed since the previous page.')
        selected = objects[offset:offset + limit]
        items = []
        for obj in selected:
            if body is not None and self.adapter.identity(self.adapter.owner_body(obj, kind)) != self.adapter.identity(body):
                raise rejected('object_body_mismatch', 'Topology snapshot no longer belongs to the requested body.')
            reference = self._register(entry, obj, kind, configuration, identity, body_id)
            items.append(self._summary(obj, reference))
        self._confirm(entry, observed, configuration, identity)
        next_cursor = None
        if offset + len(selected) < len(objects):
            # Each pagination sequence owns its original native enumeration.
            # Offset is an internal cursor, never an object identifier. Reorder
            # on a later enumeration cannot silently skip or duplicate objects.
            for token, old in list(cursors.items()):
                if old.revision != observed['observation_revision']:
                    del cursors[token]
            if len(cursors) >= 10000:
                raise rejected('cursor_budget_exceeded', 'Document cursor budget exceeded; start a new targeted query.')
            snapshots = {id(old.objects): old.objects for old in cursors.values()}
            snapshots[id(objects)] = objects
            if sum(len(values) for values in snapshots.values()) > 100000:
                raise rejected('geometry_budget_exceeded', 'Pagination snapshot budget exceeded; narrow the query.')
            next_cursor = 'page_' + uuid.uuid4().hex
            cursors[next_cursor] = _Cursor(query, observed['observation_revision'], identity, offset + len(selected), objects)
        return {'document_id': document_id, 'configuration': configuration,
                'observation_revision': observed['observation_revision'], 'items': items,
                'total_count': len(objects), 'next_cursor': next_cursor,
                'coordinate_frame': 'model', 'length_unit': 'mm', 'area_unit': 'mm2'}

    def get(self, document_id, configuration, expected_observation_revision, object_id):
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        obj, reference = self._resolve(entry, object_id, configuration, identity)
        item = self._summary(obj, reference)
        self._confirm(entry, observed, configuration, identity)
        return {'document_id': document_id, 'configuration': configuration,
                'observation_revision': observed['observation_revision'], 'object': item,
                'coordinate_frame': 'model', 'length_unit': 'mm', 'area_unit': 'mm2'}
