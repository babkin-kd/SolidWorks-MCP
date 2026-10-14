"""Passive assembly-instance references; proxies and their release stay on STA."""
from dataclasses import dataclass
import uuid
from .geometry import GeometryCatalog
from .documents import rejected


@dataclass
class ComponentReference:
    object_id: str
    configuration: str
    configuration_identity: object
    persistent_id: bytes
    native_identity: object
    referenced_configuration: str
    model_identity: object
    referenced_configuration_identity: object


@dataclass
class BodyReference:
    object_id: str
    component_id: str
    persistent_id: bytes
    native_identity: object


class ComponentCatalog(GeometryCatalog):
    SCOPE = 'resolved_assembly_instance_reads_v1'
    MAX_COMPONENTS = 100000
    MAX_BODIES = 500

    def _context(self, document_id, configuration, expected_observation_revision):
        entry, observed = self.documents.resolve(document_id, configuration)
        if observed['document_type'] != 'assembly':
            raise rejected('unsupported_document_type', 'Component reads require an explicit assembly document.')
        if observed['active_configuration'] != configuration:
            raise rejected('configuration_not_active', 'No implicit assembly configuration switch.')
        if not expected_observation_revision or observed['observation_revision'] != expected_observation_revision:
            raise rejected('observation_revision_mismatch', 'Obtain a fresh document observation before reading components.')
        if self.adapter.pending_rebuild(entry.model):
            raise rejected('document_needs_rebuild', 'Rebuild the assembly explicitly before reading components.')
        return entry, observed, self.adapter.configuration_identity(entry.model, configuration)

    @staticmethod
    def _state(entry):
        return entry.geometry.setdefault('component_catalog', {'refs': {}, 'index': {}, 'bodies': {}, 'body_index': {}, 'cursors': {}})

    def _register(self, entry, obj, configuration, identity, info, anchors):
        pid = self.adapter.persistent_id(entry.model, obj)
        if not pid:
            raise rejected('persistent_reference_unavailable', 'No component persistent reference; no name/index fallback.')
        native = self.adapter.identity(obj)
        resolved = self.adapter.resolve_persistent_id(entry.model, pid, 'component')
        if self.adapter.identity(resolved) != native:
            raise rejected('persistent_reference_mismatch', 'Reference resolved to another native instance.')
        state = self._state(entry)
        key = (configuration, pid, info['referenced_configuration'])
        old = state['index'].get(key)
        if (old is not None and old.configuration_identity == identity and old.native_identity == native
                and old.model_identity == anchors[0] and old.referenced_configuration_identity == anchors[1]
                and self.adapter.same_persistent_id(entry.model, old.persistent_id, pid)):
            return old
        if len(state['refs']) >= self.MAX_COMPONENTS:
            raise rejected('reference_budget_exceeded', 'Component reference budget exceeded.')
        ref = ComponentReference('cmp_' + uuid.uuid4().hex, configuration, identity, pid, native,
                                 info['referenced_configuration'], *anchors)
        state['refs'][ref.object_id] = ref
        state['index'][key] = ref
        return ref

    def _snapshot(self, entry, configuration, identity):
        objects = tuple(self.adapter.components(entry.model))
        if len(objects) > self.MAX_COMPONENTS:
            raise rejected('component_budget_exceeded', 'Native component enumeration exceeds its declared budget.')
        rows = []
        for obj in objects:
            info, anchors = self.adapter.component_info(obj)
            ref = self._register(entry, obj, configuration, identity, info, anchors)
            parent = self.adapter.component_parent(obj)
            rows.append((ref, obj, info, None if parent is None else self.adapter.identity(parent)))
        # Paths check native hierarchy only, never identify a requested object.
        paths = {row[2]['component_path']: row for row in rows}
        if len(paths) != len(rows):
            raise rejected('component_roster_invalid', 'Native instance paths are not unique.')
        for ref, obj, info, parent_identity in rows:
            parent_path = info['component_path'].rsplit('/', 1)[0] if '/' in info['component_path'] else None
            parent = paths.get(parent_path)
            if ((parent is None) != (parent_identity is None)
                    or parent is not None and parent[0].native_identity != parent_identity):
                raise rejected('component_parent_mismatch', 'Native parent disagrees with complete assembly hierarchy.')
            info['parent_component_id'] = None if parent is None else parent[0].object_id
        return tuple(sorted(rows, key=lambda row: row[2]['component_path']))

    @staticmethod
    def _signature(rows):
        return tuple((r[0].native_identity, r[0].model_identity, r[0].referenced_configuration_identity, r[3], r[2]) for r in rows)

    def _finish(self, entry, observed, configuration, identity, rows):
        self._confirm(entry, observed, configuration, identity)
        if self._signature(rows) != self._signature(self._snapshot(entry, configuration, identity)):
            raise rejected('component_changed_during_read', 'Instance hierarchy/configuration/transform changed during read.')
        self._confirm(entry, observed, configuration, identity)

    def _resolve(self, entry, configuration, identity, component_id, rows):
        ref = self._state(entry)['refs'].get(component_id)
        if ref is None:
            raise rejected('component_reference_not_found', 'Unknown component_id in this open assembly.')
        if ref.configuration != configuration or ref.configuration_identity != identity:
            raise rejected('object_configuration_mismatch', 'Component belongs to another assembly configuration/incarnation.')
        obj = self.adapter.resolve_persistent_id(entry.model, ref.persistent_id, 'component')
        if self.adapter.identity(obj) != ref.native_identity:
            raise rejected('persistent_reference_mismatch', 'Reference no longer identifies the original instance.')
        for row in rows:
            current = row[0]
            if current.native_identity != ref.native_identity:
                continue
            if (current.referenced_configuration != ref.referenced_configuration or current.model_identity != ref.model_identity
                    or current.referenced_configuration_identity != ref.referenced_configuration_identity):
                raise rejected('component_reference_context_changed', 'Referenced model/configuration changed; list again.')
            return row
        raise rejected('component_not_in_active_configuration', 'Instance is absent from explicit assembly configuration.')

    @staticmethod
    def _item(row, object_id=None):
        return {'component_id': object_id or row[0].object_id, **row[2]}

    def _result(self, entry, observed, configuration):
        return dict(document_id=entry.document_id, configuration=configuration,
                    observation_revision=observed['observation_revision'], scope=self.SCOPE,
                    length_unit='mm', transform_target_frame='assembly_model',
                    includes_hidden_components=True, implicit_resolution=False)

    def list(self, document_id, configuration, expected_observation_revision, *, limit=100, cursor=''):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise rejected('invalid_limit', 'Page limit must be between 1 and 200.')
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        rows = self._snapshot(entry, configuration, identity)
        state = self._state(entry)
        for token, prior in list(state['cursors'].items()):
            if prior[0] != observed['observation_revision']:
                del state['cursors'][token]  # release strong anchors on STA
        offset = 0
        if cursor:
            prior = state['cursors'].get(cursor)
            if prior is None:
                raise rejected('invalid_component_cursor', 'Unknown/obsolete cursor for this assembly.')
            if (prior[0] != observed['observation_revision'] or prior[1] != identity or prior[2] != self._signature(rows)):
                raise rejected('stale_component_cursor', 'Complete native snapshot changed between pages.')
            offset = prior[3]
        selected = rows[offset:offset + limit]
        self._finish(entry, observed, configuration, identity, rows)
        next_cursor = None
        if offset + len(selected) < len(rows):
            if len(state['cursors']) >= 100:
                raise rejected('cursor_budget_exceeded', 'Too many retained component snapshots.')
            if sum(len(prior[2]) for prior in state['cursors'].values()) + len(rows) > self.MAX_COMPONENTS:
                raise rejected('component_budget_exceeded', 'Retained pagination snapshots exceed the component budget.')
            next_cursor = 'cmp_page_' + uuid.uuid4().hex
            state['cursors'][next_cursor] = (observed['observation_revision'], identity, self._signature(rows), offset + len(selected))
        return {**self._result(entry, observed, configuration), 'items': [self._item(row) for row in selected],
                'total_count': len(rows), 'next_cursor': next_cursor}

    def get(self, document_id, configuration, expected_observation_revision, component_id):
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        rows = self._snapshot(entry, configuration, identity)
        row = self._resolve(entry, configuration, identity, component_id, rows)
        self._finish(entry, observed, configuration, identity, rows)
        return {**self._result(entry, observed, configuration), 'component': self._item(row, component_id)}

    def _body_rows(self, entry, row, component_id):
        if row[2]['referenced_document_type'] != 'part':
            raise rejected('unsupported_component_type', 'Bodies require a resolved part instance, not a subassembly.')
        bodies = tuple(self.adapter.component_bodies(row[1]))
        if len(bodies) > self.MAX_BODIES:
            raise rejected('component_body_budget_exceeded', 'Instance body count exceeds 500.')
        state = self._state(entry)
        items = []
        for body in bodies:
            pid = self.adapter.persistent_id(entry.model, body)
            if not pid:
                raise rejected('persistent_reference_unavailable', 'No instance-context body persistent reference.')
            native = self.adapter.identity(body)
            resolved = self.adapter.resolve_persistent_id(entry.model, pid, 'body')
            if self.adapter.identity(resolved) != native:
                raise rejected('persistent_reference_mismatch', 'Body reference resolved to another instance body.')
            key = (component_id, pid)
            ref = state['body_index'].get(key)
            if ref is None or ref.native_identity != native or not self.adapter.same_persistent_id(entry.model, ref.persistent_id, pid):
                if len(state['bodies']) >= self.MAX_COMPONENTS:
                    raise rejected('reference_budget_exceeded', 'Instance body reference budget exceeded.')
                ref = BodyReference('cmp_body_' + uuid.uuid4().hex, component_id, pid, native)
                state['bodies'][ref.object_id] = ref
                state['body_index'][key] = ref
            items.append((ref, body, self.adapter.geometry_summary(body, 'body')))
        if len({item[0].object_id for item in items}) != len(items):
            raise rejected('component_body_roster_invalid', 'Native body roster has duplicates.')
        return tuple(sorted(items, key=lambda item: item[0].object_id))

    @staticmethod
    def _body_signature(items):
        return tuple((item[0].native_identity, item[2]) for item in items)

    def bodies(self, document_id, configuration, expected_observation_revision, component_id, *, body_type='all', body_id=None):
        if body_type not in ('all', 'solid', 'surface'):
            raise rejected('invalid_body_type', 'Only native solid/surface bodies supported.')
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        rows = self._snapshot(entry, configuration, identity)
        row = self._resolve(entry, configuration, identity, component_id, rows)
        items = self._body_rows(entry, row, component_id)
        selected = [item for item in items if body_type == 'all' or item[2]['body_type'] == body_type]
        if body_id is not None:
            ref = self._state(entry)['bodies'].get(body_id)
            if ref is None:
                raise rejected('component_body_reference_not_found', 'Unknown instance body_id in this assembly.')
            if ref.component_id != component_id:
                raise rejected('object_component_mismatch', 'Body belongs to another explicitly referenced instance.')
            body = self.adapter.resolve_persistent_id(entry.model, ref.persistent_id, 'body')
            if self.adapter.identity(body) != ref.native_identity:
                raise rejected('persistent_reference_mismatch', 'Body reference no longer identifies its original native body.')
            selected = [item for item in selected if item[0].native_identity == ref.native_identity]
            if len(selected) != 1:
                raise rejected('object_not_in_current_component', 'Body is absent from this instance/configuration/type scope.')
        if self._body_signature(items) != self._body_signature(self._body_rows(entry, row, component_id)):
            raise rejected('component_bodies_changed_during_read', 'Instance body membership/summary changed during read.')
        self._finish(entry, observed, configuration, identity, rows)
        return {**self._result(entry, observed, configuration), 'component': self._item(row, component_id),
                'body_coordinate_frame': 'component_model', 'includes_hidden_bodies': True,
                'items': [dict(body_id=item[0].object_id, component_id=component_id, **item[2]) for item in selected],
                'total_count': len(selected), 'body_type': body_type}
