"""Scoped feature-tree revisions, persistent feature references and guarded rename.

The revision is complete for this declared operation scope, not an assertion
that every plugin property or external file in arbitrary CAD is unchanged.
Future dimensions/geometry/material operations must extend their own scope.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import re
import uuid

from .documents import rejected
from .jobs import _json
from .mutations import MutationCoordinator, PreparedMutation


SCOPE = 'part_feature_tree_v1'


def russian_name(name):
    if (not isinstance(name, str) or name != name.strip() or not 1 <= len(name) <= 128
            or not re.search('[А-Яа-яЁё]', name) or re.search(r'[\x00-\x1f\x7f\\/:*?"<>|@]', name)):
        raise rejected('invalid_russian_name', 'Use a Russian feature name, 1–128 characters, without reserved/control characters or outer spaces.')
    return name


@dataclass
class FeatureReference:
    object_id: str
    configuration: str
    configuration_identity: object
    persistent_id: bytes


class FeatureCatalog:
    def __init__(self, documents, store, connection_epoch, *, mutation_guard=None):
        self.documents = documents
        self.adapter = documents.adapter
        self.store = store
        self.connection_epoch = connection_epoch
        self.coordinator = MutationCoordinator(store, connection_epoch)
        self.mutation_guard = mutation_guard

    def _state(self, document_id, configuration):
        entry, observed = self.documents.resolve(document_id, configuration)
        if observed['document_type'] != 'part':
            raise rejected('unsupported_document_type', 'Feature-tree revisions currently support parts only.')
        if observed['active_configuration'] != configuration:
            raise rejected('configuration_not_active', 'Explicit active configuration required; no automatic switch.')
        watch = entry.features.get('watch')
        if watch is None:
            watch = self.adapter.watch_part(entry.model)
            entry.features['watch'] = watch
        event_sequence = watch.poll()
        identity = self.adapter.configuration_identity(entry.model, configuration)
        configs = entry.features.setdefault('configurations', {})
        cached = configs.get(configuration)
        if cached is None or cached[0] != identity:
            cached = (identity, 'cfg_' + uuid.uuid4().hex)
            configs[configuration] = cached
        native = self.adapter.features(entry.model)
        features = [self.adapter.feature_summary(feature) for feature in native]
        pending = self.adapter.pending_rebuild(entry.model)
        current, after = self.documents.resolve(document_id, configuration)
        if current is not entry or observed != after:
            raise rejected('document_changed_during_read', 'Document changed during feature-tree collection; read again.')
        # Configuration lookup AND canonical PyIUnknown equality can perform
        # native work. Finish both before the final notification poll.
        closing_identity = self.adapter.configuration_identity(entry.model, configuration)
        same_identity = closing_identity == identity
        closing_sequence = watch.poll()
        if not same_identity or closing_sequence != event_sequence:
            raise rejected('document_changed_during_read', 'Document changed during feature-tree collection; read again.')
        semantic = {'document': {key: observed[key] for key in ('title', 'path', 'document_type',
                    'configurations', 'active_configuration', 'update_stamp')},
                    'configuration_epoch': cached[1], 'needs_rebuild': pending, 'features': features}
        payload = {'scope': SCOPE, 'connection_epoch': self.connection_epoch, 'document_id': document_id,
                   'configuration': configuration, 'observed': observed, 'semantic': semantic,
                   'event_sequence': event_sequence, 'mutation_sequence': entry.features.get('mutation_sequence', 0)}
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()
        return entry, identity, native, semantic, revision, payload

    def _register(self, entry, configuration, identity, native):
        persistent = self.adapter.persistent_id(entry.model, native)
        if not persistent:
            raise rejected('persistent_reference_unavailable', 'Native feature has no persistent reference; no name/index fallback.')
        resolved = self.adapter.resolve_persistent_id(entry.model, persistent, 'feature')
        if self.adapter.identity(resolved) != self.adapter.identity(native):
            source_info = self.adapter.feature_summary(native)
            resolved_info = self.adapter.feature_summary(resolved)
            raise rejected('persistent_reference_mismatch',
                f"Native feature reference differs: source {source_info['feature_type']}/{source_info['native_id']}, "
                f"resolved {resolved_info['feature_type']}/{resolved_info['native_id']}.")
        refs = entry.features.setdefault('references', {})
        index = entry.features.setdefault('reference_index', {})
        key = (configuration, persistent)
        ref = index.get(key)
        if (ref is not None and ref.configuration_identity == identity
                and self.adapter.same_persistent_id(entry.model, ref.persistent_id, persistent)):
            return ref
        if len(refs) >= 10000:
            raise rejected('reference_budget_exceeded', 'Feature-reference budget exhausted for this document.')
        ref = FeatureReference('feat_' + uuid.uuid4().hex, configuration, identity, persistent)
        refs[ref.object_id] = ref
        index[key] = ref
        return ref

    def _resolve(self, entry, configuration, identity, objects, object_id):
        ref = entry.features.setdefault('references', {}).get(object_id)
        if ref is None:
            raise rejected('object_reference_not_found', 'Unknown feature object_id in this document.')
        if ref.configuration != configuration or ref.configuration_identity != identity:
            raise rejected('object_configuration_mismatch', 'Feature belongs to another configuration or its previous incarnation.')
        native = self.adapter.resolve_persistent_id(entry.model, ref.persistent_id, 'feature')
        if not any(self.adapter.identity(item) == self.adapter.identity(native) for item in objects):
            raise rejected('feature_not_current', 'Persistent feature is not in this current feature tree.')
        return native, ref

    def list(self, document_id, configuration, limit=100, cursor=''):
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
            raise rejected('invalid_limit', 'limit must be an integer between 1 and 200.')
        entry, identity, native, semantic, revision, payload = self._state(document_id, configuration)
        cursors = entry.features.setdefault('cursors', {})
        offset = 0
        if cursor:
            value = cursors.get(cursor)
            if value is None or value['revision'] != revision or value['configuration'] != configuration:
                raise rejected('invalid_cursor', 'Feature cursor no longer matches this document/configuration/revision.')
            offset = value['offset']
        items = []
        for obj, item in zip(native[offset:offset + limit], semantic['features'][offset:offset + limit]):
            reference_error = None
            try:
                ref = self._register(entry, configuration, identity, obj)
            except Exception as exc:
                if getattr(exc, 'code', None) not in ('persistent_reference_unavailable',
                    'persistent_reference_mismatch', 'object_reference_invalid', 'object_deleted', 'object_suppressed'):
                    raise
                ref = None  # Show unsupported built-in nodes honestly, without a fake writable ID.
                reference_error = {'code': exc.code, 'message': str(exc)}
            items.append({**item, 'object_id': ref.object_id if ref else None,
                'persistent_reference_supported': ref is not None, 'reference_error': reference_error})
        if self._state(document_id, configuration)[4] != revision:
            raise rejected('document_changed_during_read', 'Feature tree changed while references were collected.')
        for key in list(cursors):
            if cursors[key]['revision'] != revision:
                del cursors[key]
        next_cursor = None
        if offset + limit < len(native):
            if len(cursors) >= 10000:
                raise rejected('cursor_budget_exceeded', 'Feature cursor budget exhausted.')
            next_cursor = 'cursor_' + uuid.uuid4().hex
            cursors[next_cursor] = {'revision': revision, 'configuration': configuration, 'offset': offset + limit}
        return {'document_id': document_id, 'configuration': configuration, 'revision': revision,
                'revision_scope': SCOPE, 'mutation_sequence': payload['mutation_sequence'],
                'event_sequence': payload['event_sequence'], 'needs_rebuild': semantic['needs_rebuild'],
                'items': items, 'total_count': len(native), 'next_cursor': next_cursor}

    def get(self, document_id, configuration, object_id):
        entry, identity, objects, semantic, revision, _ = self._state(document_id, configuration)
        native, _ = self._resolve(entry, configuration, identity, objects, object_id)
        summary = self.adapter.feature_summary(native)
        if self._state(document_id, configuration)[4] != revision:
            raise rejected('document_changed_during_read', 'Feature tree changed during reference resolution.')
        return {'document_id': document_id, 'configuration': configuration, 'revision': revision,
                'revision_scope': SCOPE, 'feature': {**summary, 'object_id': object_id}}

    def dependencies(self, document_id, configuration):
        """Internal relation graph for future deletion preview; no model changes."""
        from .feature_dependency_graph import dependency_graph
        return dependency_graph(self, document_id, configuration)

    def rename(self, operation_id, document_id, configuration, object_id, expected_revision, name):
        name = russian_name(name)
        if self.mutation_guard is None:
            raise rejected('mutation_guard_unavailable', 'Feature rename requires an owning-STA native UI guard.')
        target = {}
        def prepare():
            entry, identity, objects, semantic, revision, _ = self._state(document_id, configuration)
            if semantic['needs_rebuild']:
                raise rejected('document_needs_rebuild', 'Rebuild the explicit document before renaming; no implicit rebuild.')
            native, ref = self._resolve(entry, configuration, identity, objects, object_id)
            summary = self.adapter.feature_summary(native)
            if summary['suppressed']:
                raise rejected('object_suppressed', 'Suppressed features are not writable in this configuration.')
            if any(item['name'].casefold() == name.casefold() and item['native_id'] != summary['native_id']
                   for item in semantic['features']):
                raise rejected('feature_name_conflict', 'Another feature already has this name.')
            target.update(entry=entry, native=native, identity=identity, ref=ref)
            return PreparedMutation(revision, {'scope': SCOPE, 'object_id': object_id,
                'persistent_id_hex': ref.persistent_id.hex(), 'native_id': summary['native_id'],
                'name': summary['name'], 'semantic': semantic})
        def validate(prepared):
            entry, identity, objects, _, revision, _ = self._state(document_id, configuration)
            native, _ = self._resolve(entry, configuration, identity, objects, object_id)
            return (revision == prepared.revision and entry is target['entry']
                    and self.adapter.identity(native) == self.adapter.identity(target['native']))
        def apply(prepared):
            entry = target['entry']
            entry.features['mutation_sequence'] = entry.features.get('mutation_sequence', 0) + 1
            if self.adapter.rename_feature(target['native'], name) != name:
                raise rejected('feature_rename_failed', 'Native feature name did not match the requested Russian name.')
            return {'object_id': object_id, 'name': name}
        def inspect(prepared):
            entry, identity, objects, semantic, revision, _ = self._state(document_id, configuration)
            native, _ = self._resolve(entry, configuration, identity, objects, object_id)
            return {'scope': SCOPE, 'name': self.adapter.feature_summary(native)['name'],
                    'semantic': semantic, 'revision': revision}
        def verify(before, after, value):
            expected = deepcopy(before['semantic'])
            for item in expected['features']:
                if item['native_id'] == before['native_id']:
                    item['name'] = name
            return after['name'] == name and after['semantic'] == expected
        def restore(before, prepared):
            # Never overwrite an unrelated concurrent name. Native references
            # resolve again; a deleted target is not replaced with a namesake.
            entry, identity, objects, _, _, _ = self._state(document_id, configuration)
            native, _ = self._resolve(entry, configuration, identity, objects, object_id)
            current_name = self.adapter.feature_summary(native)['name']
            if current_name not in (before['name'], name):
                raise rejected('concurrent_edit_during_rollback', 'Target now has an unrelated name; reconcile instead of overwriting it.')
            self.adapter.rename_feature(native, before['name'])
        return self.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
            expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply,
            inspect=inspect, verify=verify, restore=restore,
            verify_restored=lambda b, a: a['name'] == b['name'] and a['semantic'] == b['semantic'],
            guard=lambda prepared: self.mutation_guard(target['entry'].model))
