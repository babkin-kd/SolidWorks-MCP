"""Bounded dimension-value scope and durable, explicitly targeted mutations.

This is an internal candidate domain. Native acceptance and an owning-STA
mutation guard are required before publishing tools. Its revision extends the
feature scope with all enumerated dimension values, control flags, all named
configuration incarnations and complete supported analytical boundaries. It is not a
universal revision of arbitrary add-in data or a full document rollback.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
import uuid

from .documents import rejected
from .features import FeatureCatalog
from .jobs import _json
from .mutations import MutationCoordinator, PreparedMutation


SCOPE = 'part_dimension_values_v1'
SI_ABSOLUTE_TOLERANCE = 1e-10
SI_RELATIVE_TOLERANCE = 1e-9


def close_value(left, right):
    # Preserve sign: abs(value), angle wrapping and document-unit guesses can
    # silently accept a different constraint/branch.
    return math.isclose(left, right, rel_tol=SI_RELATIVE_TOLERANCE,
                        abs_tol=SI_ABSOLUTE_TOLERANCE)


def system_value(value, unit):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise rejected('invalid_dimension_value', 'A finite numeric dimension value is required.')
    if unit not in ('mm', 'deg'):
        raise rejected('invalid_dimension_unit', 'Explicit mm or deg is required; no document-unit inference.')
    if value <= 0 or (unit == 'deg' and value >= 360):
        raise rejected('unsupported_signed_dimension', 'This operation supports positive sizes and angles strictly between 0 and 360 degrees.')
    converted = float(value) / 1000 if unit == 'mm' else math.radians(value)
    if not math.isfinite(converted) or converted <= 0:
        raise rejected('invalid_dimension_value', 'The value cannot be represented in system units.')
    return converted


@dataclass
class DimensionReference:
    object_id: str
    configuration: str
    configuration_identity: object
    persistent_id: dict
    native_identity: object


@dataclass
class _DimensionCapture:
    # Keep strong canonical native identities in the owning STA, outside the
    # JSON revision payload. Equality alone is required; no IUnknown hashing.
    state: tuple
    feature_identities: tuple
    dimension_memberships: tuple


class DimensionCatalog:
    def __init__(self, documents, store, connection_epoch, *, mutation_guard=None):
        self.documents = documents
        self.adapter = documents.adapter
        self.connection_epoch = connection_epoch
        self.features = FeatureCatalog(documents, store, connection_epoch)
        self.coordinator = MutationCoordinator(store, connection_epoch)
        self.mutation_guard = mutation_guard

    def _collect(self, entry, features, configurations):
        if not configurations or len(configurations) > 128:
            raise rejected('dimension_configuration_budget_exceeded', 'A bounded dimension snapshot requires 1–128 named configurations.')
        native = self.adapter.dimensions(entry.model, features)
        rows = [self.adapter.dimension_summary(item, configurations) for item in native]
        if len(rows) > 5000:
            raise rejected('dimension_budget_exceeded', 'Dimension snapshot budget is 5000; partial revisions are refused.')
        if len(rows) * len(configurations) > 100000:
            raise rejected('dimension_budget_exceeded', 'Dimension/configuration value budget is 100000; partial revisions are refused.')
        names = [row['full_name'] for row in rows]
        if len(set(names)) != len(names):
            raise rejected('dimension_identity_collision', 'Different native dimensions have the same full name.')
        identities = entry.features.setdefault('dimensions', {}).setdefault('native_identities', [])
        for item, row in zip(native, rows):
            dimension = self.adapter.dimension_object(item)
            try:
                anchor = self.adapter.dimension_persistent_id(entry.model, item)
            except Exception as exc:
                if getattr(exc, 'code', None) not in ('persistent_reference_unavailable', 'persistent_reference_mismatch',
                        'object_reference_invalid', 'object_deleted', 'object_suppressed'):
                    raise
                anchor = None  # Read-only row; registration will expose the reason.
            row['reference_anchor'] = anchor
            # Even an unsupported/read-only native dimension must invalidate
            # the full revision when replaced by an identical-looking object.
            identity = self.adapter.identity(dimension)
            prior = next((old for old in identities if old[0] == identity), None)
            if prior is None:
                if len(identities) >= 10000:
                    raise rejected('reference_budget_exceeded', 'Native dimension incarnation budget exhausted.')
                prior = (identity, 'native_dim_' + uuid.uuid4().hex)
                identities.append(prior)
            row['native_incarnation'] = prior[1]
        # finite JSON is a protocol requirement, including adapter-provided values.
        _json(rows)
        return native, rows

    def _capture(self, document_id, configuration):
        """One complete capture, bracketed by feature/event/config checks.

        This is not a reusable cached geometry result. Two full captures must
        agree before any public read or mutation state can be accepted.
        """
        entry, identity, features, tree, feature_revision, feature_payload = self.features._state(document_id, configuration)
        feature_identities = tuple(self.adapter.identity(feature) for feature in features)
        configurations = tree['document']['configurations']
        cache = entry.features.setdefault('dimensions', {})
        config_cache = cache.setdefault('configurations', {})
        epochs, configuration_identities = {}, {}
        for name in configurations:
            current = self.adapter.configuration_identity(entry.model, name)
            configuration_identities[name] = current
            old = config_cache.get(name)
            if old is None or old[0] != current:
                old = (current, 'cfg_' + uuid.uuid4().hex)
                config_cache[name] = old
            epochs[name] = old[1]
        native, rows = self._collect(entry, features, configurations)
        dimension_memberships = tuple((
            self.adapter.identity(self.adapter.dimension_object(record)),
            self.adapter.identity(record.owner) if getattr(record, 'owner', None) is not None else None,
            tuple((self.adapter.identity(display), slot) for display, slot in getattr(record, 'display_slots', ())))
            for record in native)
        context = self.adapter.dimension_context(entry.model)
        geometry = self.adapter.dimension_geometry_snapshot(entry.model)
        if any(self.adapter.configuration_identity(entry.model, name) != original
               for name, original in configuration_identities.items()):
            raise rejected('document_changed_during_read', 'Configuration incarnation changed during dimension capture.')
        # Keep the complete feature/event close after all named-configuration
        # identity reads: those native calls may pump notifications themselves.
        second = self.features._state(document_id, configuration)
        closing_feature_identities = tuple(self.adapter.identity(feature) for feature in second[2])
        # QueryInterface for the strong identities above is itself native work.
        # Bracket it with a cheap final observation/configuration check, then
        # poll events LAST. No native work follows that poll in this capture.
        closing_entry, closing_observed = self.documents.resolve(document_id, configuration)
        closing_configurations = tuple(self.adapter.configuration_identity(entry.model, name)
                                       for name in configuration_identities)
        final_event_sequence = entry.features['watch'].poll()
        if (second[0] is not entry or second[1] != identity or second[4] != feature_revision
                or closing_feature_identities != feature_identities
                or closing_entry is not entry or closing_observed != second[5]['observed']
                or closing_configurations != tuple(configuration_identities.values())
                or final_event_sequence != second[5]['event_sequence']):
            raise rejected('document_changed_during_read', 'Feature/event/configuration state changed during dimension capture.')
        semantic = {'tree': tree, 'configuration_epochs': epochs, 'dimensions': rows,
                    'context': context, 'geometry': geometry}
        payload = {'scope': SCOPE, 'connection_epoch': self.connection_epoch,
                   'document_id': document_id, 'configuration': configuration,
                   'feature_revision': feature_revision, 'semantic': semantic,
                   'mutation_sequence': cache.get('mutation_sequence', 0)}
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()
        return _DimensionCapture((entry, identity, native, semantic, revision),
                                 feature_identities, dimension_memberships)

    @staticmethod
    def _same_capture(first, second):
        return (first.state[0] is second.state[0] and first.state[1] == second.state[1]
                and first.state[3:] == second.state[3:]
                and first.feature_identities == second.feature_identities
                and first.dimension_memberships == second.dimension_memberships)

    def _state(self, document_id, configuration):
        # Mutations continue to require a complete paired consistency check at
        # every prepare/validate/inspect stage, including both full BREP reads.
        first = self._capture(document_id, configuration)
        second = self._capture(document_id, configuration)
        if not self._same_capture(first, second):
            raise rejected('document_changed_during_read', 'Dimension/control/geometry state changed during collection.')
        return first.state

    def _register(self, entry, configuration, identity, native):
        dimension = self.adapter.dimension_object(native)
        persistent = self.adapter.dimension_persistent_id(entry.model, native)
        if not persistent:
            raise rejected('persistent_reference_unavailable', 'Native dimension has no persistent reference.')
        resolved = self.adapter.resolve_dimension_id(entry.model, persistent)
        if (self.adapter.identity(resolved) != self.adapter.identity(dimension)
                or not self.adapter.dimension_reference_is_current(entry.model, native, persistent)):
            raise rejected('persistent_reference_mismatch', 'Persistent dimension reference resolves to another native object.')
        cache = entry.features.setdefault('dimensions', {})
        refs = cache.setdefault('references', {})
        index = cache.setdefault('reference_index', {})
        native_identity = self.adapter.identity(dimension)
        key = (configuration, _json(persistent))
        ref = index.get(key)
        if ref is None:
            # Native byte representations may change across rebuilds. Equality
            # is the native PID comparison, never JSON/hex/name equality alone.
            ref = next((old for old in refs.values() if old.configuration == configuration
                        and old.configuration_identity == identity and old.native_identity == native_identity
                        and self.adapter.dimension_same_persistent_id(entry.model, persistent, old.persistent_id)), None)
        if (ref is not None and ref.configuration_identity == identity and ref.native_identity == native_identity
                and self.adapter.dimension_same_persistent_id(entry.model, persistent, ref.persistent_id)):
            index[key] = ref
            return ref
        if len(refs) >= 10000:
            raise rejected('reference_budget_exceeded', 'Dimension reference budget exhausted.')
        ref = DimensionReference('dim_' + uuid.uuid4().hex, configuration, identity, deepcopy(persistent), native_identity)
        refs[ref.object_id] = ref
        index[key] = ref
        return ref

    def _resolve(self, entry, configuration, identity, objects, object_id):
        ref = entry.features.setdefault('dimensions', {}).setdefault('references', {}).get(object_id)
        if ref is None:
            raise rejected('object_reference_not_found', 'Unknown dimension object_id in this document.')
        if ref.configuration != configuration or ref.configuration_identity != identity:
            raise rejected('object_configuration_mismatch', 'Dimension belongs to another configuration/incarnation.')
        resolved = self.adapter.resolve_dimension_id(entry.model, ref.persistent_id)
        if self.adapter.identity(resolved) != ref.native_identity:
            raise rejected('persistent_reference_mismatch', 'Dimension anchor was retargeted to another native dimension; re-list it.')
        current = next((obj for obj in objects if self.adapter.identity(self.adapter.dimension_object(obj)) == self.adapter.identity(resolved)), None)
        if current is None or not self.adapter.dimension_reference_is_current(entry.model, current, ref.persistent_id):
            raise rejected('dimension_not_current', 'Persistent dimension is not in the current bounded dimension enumeration.')
        return current, ref

    def _prevalidate_namespace(self, document_id, configuration, object_id):
        """Deny foreign/unknown references before expensive complete captures.

        This proves no writability or current native membership. All subsequent
        capture, incarnation, persistent-reference and owner checks still run.
        """
        entry, _ = self.documents.resolve(document_id, configuration)
        references = entry.features.get('dimensions', {}).get('references', {})
        ref = references.get(object_id)
        if ref is None:
            raise rejected('object_reference_not_found', 'Unknown dimension object_id in this document.')
        if ref.configuration != configuration:
            raise rejected('object_configuration_mismatch', 'Dimension belongs to another configuration.')

    @staticmethod
    def _captured_row(objects, semantic, native):
        # _resolve has already proven the canonical native identity and current
        # membership. Bind the exact record it returned to its captured row in
        # local Python; no name, client ordinal or additional COM read is used.
        index = next((index for index, record in enumerate(objects) if record is native), None)
        if index is None:
            raise rejected('dimension_not_current', 'Resolved dimension has no row in this complete capture.')
        return deepcopy(semantic['dimensions'][index])

    def list(self, document_id, configuration, limit=100, cursor=''):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise rejected('invalid_limit', 'limit must be an integer between 1 and 200.')
        captured = self._capture(document_id, configuration)
        entry, identity, objects, semantic, revision = captured.state
        cache = entry.features['dimensions']
        cursors = cache.setdefault('cursors', {})
        offset = 0
        if cursor:
            prior = cursors.get(cursor)
            if prior is None or prior['configuration'] != configuration or prior['revision'] != revision:
                raise rejected('invalid_cursor', 'Dimension cursor no longer matches document/configuration/revision.')
            offset = prior['offset']
        items = []
        for obj, row in zip(objects[offset:offset + limit], semantic['dimensions'][offset:offset + limit]):
            ref, error = None, None
            try:
                ref = self._register(entry, configuration, identity, obj)
            except Exception as exc:
                if getattr(exc, 'code', None) not in ('persistent_reference_unavailable', 'persistent_reference_mismatch',
                        'object_reference_invalid', 'object_deleted', 'object_suppressed'):
                    raise
                error = {'code': exc.code, 'message': str(exc)}
            items.append({**row, 'object_id': ref.object_id if ref else None,
                          'persistent_reference_supported': ref is not None, 'reference_error': error})
        if not self._same_capture(captured, self._capture(document_id, configuration)):
            raise rejected('document_changed_during_read', 'Dimension state changed while references were registered.')
        for key in list(cursors):
            if cursors[key]['revision'] != revision:
                del cursors[key]
        next_cursor = None
        if offset + limit < len(objects):
            if len(cursors) >= 10000:
                raise rejected('cursor_budget_exceeded', 'Dimension cursor budget exhausted.')
            next_cursor = 'cursor_' + uuid.uuid4().hex
            cursors[next_cursor] = {'configuration': configuration, 'revision': revision, 'offset': offset + limit}
        return {'document_id': document_id, 'configuration': configuration, 'revision': revision,
                'revision_scope': SCOPE, 'items': items, 'total_count': len(objects), 'next_cursor': next_cursor}

    def get(self, document_id, configuration, object_id):
        self._prevalidate_namespace(document_id, configuration, object_id)
        captured = self._capture(document_id, configuration)
        entry, identity, objects, semantic, revision = captured.state
        native, _ = self._resolve(entry, configuration, identity, objects, object_id)
        summary = self._captured_row(objects, semantic, native)
        if not self._same_capture(captured, self._capture(document_id, configuration)):
            raise rejected('document_changed_during_read', 'Dimension changed while its reference was resolved.')
        return {'document_id': document_id, 'configuration': configuration, 'revision': revision,
                'revision_scope': SCOPE, 'dimension': {**summary, 'object_id': object_id}}

    @staticmethod
    def _writable(semantic, row, unit):
        if semantic['tree']['needs_rebuild']:
            raise rejected('document_needs_rebuild', 'Rebuild the explicit document before submitting a dimension edit.')
        context = semantic['context']
        if context['configuration_geometry_complete'] is not True:
            raise rejected('configuration_geometry_scope_unavailable', 'This adapter cannot verify every affected configuration geometry/rebuild state.')
        if context['active_document'] is not True:
            raise rejected('document_not_active', 'Dimension rebuild requires this explicitly targeted document to be active; no implicit activation.')
        if (context['read_only'] or context['editing_sketch'] or context['external_reference_count']
                or context['design_table'] or context['equation_count'] or context['equations_linked']
                or context['unsafe_feature_types']):
            raise rejected('unsupported_dimension_context', 'Read-only/editing/external/equation/design-table/macro-feature context is unsupported.')
        if row['unit'] != unit:
            raise rejected('dimension_unit_mismatch', 'Requested unit does not match the native dimension parameter type.')
        if row['write_blockers']:
            raise rejected('dimension_not_writable', 'Native dimension is not writable in this scope: ' + ', '.join(row['write_blockers']))
        if any(v <= 0 or (unit == 'deg' and v >= 2 * math.pi) for v in row['values_si'].values()):
            raise rejected('unsupported_signed_dimension', 'Existing zero/signed/wrapped target values require a dedicated constraint contract.')
        # Independent inputs only. Dependent/reference values may change after
        # rebuild and require a separately specified dependency contract.
        if any(r['driven_state'] != 2 or r['reference'] or r['linked'] or r['design_table'] for r in semantic['dimensions']):
            raise rejected('unsupported_dimension_dependencies', 'Parts with driven/reference/linked dimensions need an explicit dependency contract.')
        if any(f['error_code'] for f in semantic['tree']['features']):
            raise rejected('document_has_feature_errors', 'Repair existing feature errors/warnings before dimension changes.')

    @staticmethod
    def _comparable(semantic, *, ignore_geometry=False):
        result = deepcopy(semantic)
        # Stamps and save flags are expected to advance after our own native
        # write/rebuild. They still participate in the pre-write revision.
        result['tree']['document'].pop('update_stamp', None)
        for row in result['dimensions']:
            row.pop('owner_update_stamp', None)
        if ignore_geometry:
            result.pop('geometry', None)
        return result

    def set_value(self, operation_id, document_id, configuration, object_id, expected_revision, value, unit):
        requested = system_value(value, unit)
        if self.mutation_guard is None:
            raise rejected('mutation_guard_unavailable', 'An owning-STA model mutation guard must be installed before dimension writes.')
        target = {}
        def prepare():
            self._prevalidate_namespace(document_id, configuration, object_id)
            entry, identity, objects, semantic, revision = self._state(document_id, configuration)
            native, ref = self._resolve(entry, configuration, identity, objects, object_id)
            row = self._captured_row(objects, semantic, native)
            self._writable(semantic, row, unit)
            target.update(entry=entry, identity=identity, native=native)
            return PreparedMutation(revision, {'scope': SCOPE, 'object_id': object_id,
                'reference_anchor': ref.persistent_id, 'full_name': row['full_name'],
                'value_si': row['values_si'][configuration], 'semantic': semantic})
        def validate(prepared):
            entry, identity, objects, semantic, revision = self._state(document_id, configuration)
            native, _ = self._resolve(entry, configuration, identity, objects, object_id)
            row = self._captured_row(objects, semantic, native)
            self._writable(semantic, row, unit)
            return (entry is target['entry'] and revision == prepared.revision
                    and self.adapter.identity(self.adapter.dimension_object(native)) == self.adapter.identity(self.adapter.dimension_object(target['native'])))
        def apply(prepared):
            entry = target['entry']
            cache = entry.features['dimensions']
            cache['mutation_sequence'] = cache.get('mutation_sequence', 0) + 1
            status = self.adapter.set_dimension_value(target['native'], requested, configuration)
            if type(status) is not int or status != 0:
                raise rejected('dimension_write_failed', f'SetSystemValue3 returned {status!r}; only native status 0 is success.')
            if self.adapter.rebuild_dimension_document(entry.model) is not True:
                raise rejected('dimension_rebuild_failed', 'ForceRebuild3 did not confirm rebuilding with no pending rebuild.')
            return {'object_id': object_id, 'requested_value': value, 'unit': unit, 'value_si': requested, 'native_status': status}
        def inspect(prepared):
            entry, identity, objects, semantic, revision = self._state(document_id, configuration)
            native, _ = self._resolve(entry, configuration, identity, objects, object_id)
            row = self._captured_row(objects, semantic, native)
            return {'scope': SCOPE, 'value_si': row['values_si'][configuration], 'semantic': semantic, 'revision': revision}
        def verify(before, after, result):
            expected = self._comparable(before['semantic'], ignore_geometry=True)
            actual = self._comparable(after['semantic'], ignore_geometry=True)
            for row in expected['dimensions']:
                if row['full_name'] == before['full_name']:
                    row['values_si'][configuration] = after['value_si']
                    row['values'][configuration] = (after['value_si'] * 1000 if unit == 'mm'
                                                     else math.degrees(after['value_si']))
            return (close_value(after['value_si'], requested) and expected == actual
                    and not after['semantic']['tree']['needs_rebuild'])
        def restore(before, prepared):
            entry, identity, objects, semantic, _ = self._state(document_id, configuration)
            native, _ = self._resolve(entry, configuration, identity, objects, object_id)
            row = self._captured_row(objects, semantic, native)
            current = row['values_si'][configuration]
            if not (close_value(current, requested) or close_value(current, before['value_si'])):
                raise rejected('concurrent_edit_during_rollback', 'Target dimension has an unrelated value; reconciliation is required.')
            current_context = deepcopy(semantic['context'])
            before_context = deepcopy(before['semantic']['context'])
            # Our own SetSystemValue3 may mark this configuration for rebuild.
            # Restoration must rebuild and verify it, rather than treating that
            # expected dirty flag as an unrelated control/active-context edit.
            current_context.pop('configuration_needs_rebuild', None)
            before_context.pop('configuration_needs_rebuild', None)
            if row['write_blockers'] or current_context != before_context:
                raise rejected('concurrent_edit_during_rollback', 'Dimension control/active context changed; do not overwrite it.')
            if not close_value(current, before['value_si']):
                status = self.adapter.set_dimension_value(native, before['value_si'], configuration)
                if type(status) is not int or status != 0:
                    raise rejected('dimension_restore_failed', 'Native dimension restoration was not accepted.')
            if self.adapter.rebuild_dimension_document(entry.model) is not True:
                raise rejected('dimension_restore_rebuild_failed', 'Restoration rebuild was not confirmed.')
        def verify_restored(before, after):
            expected, actual = self._comparable(before['semantic']), self._comparable(after['semantic'])
            for row in actual['dimensions']:
                if row['full_name'] == before['full_name'] and close_value(row['values_si'][configuration], before['value_si']):
                    row['values_si'][configuration] = before['value_si']
                    row['values'][configuration] = (before['value_si'] * 1000 if unit == 'mm'
                                                     else math.degrees(before['value_si']))
            return close_value(after['value_si'], before['value_si']) and expected == actual
        return self.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
            expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply,
            inspect=inspect, verify=verify, restore=restore, verify_restored=verify_restored,
            guard=lambda prepared: self.mutation_guard(target['entry'].model))
