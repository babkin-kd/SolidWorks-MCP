"""Full-session preparation and internal independent rectangle-stage execution.

Runtime/facade registration and installed/native acceptance remain separate gates.
"""
import hashlib
import math
from contextlib import ExitStack

from .documents import rejected
from .features import FeatureCatalog
from .jobs import _json
from .native_document_open import NativeDocumentOpenCatalog
from .native_document_save import MAX_OPEN_DOCUMENTS
from .part_creation import validated_plane_transform, _positive_length
from .rectangle_construction import RectangleSketch, BlindRectangleExtrusion
from .rectangle_snapshot import BASE, EMPTY, SKETCH, validated_rectangle_snapshot
from .rectangle_construction_execution import RectangleConstructionExecutionMixin
from .owned_rectangle_feature import OwnedRectangleFeatureRegistry


SKETCH_SCOPE = 'empty_part_rectangle_sketch_v1'
EXTRUSION_SCOPE = 'closed_rectangle_blind_extrusion_v1'


class RectangleConstructionCatalog(RectangleConstructionExecutionMixin):
    def __init__(self, documents, store, connection_epoch):
        self.documents, self.adapter = documents, documents.adapter
        self.store, self.connection_epoch = store, connection_epoch
        self.sessions = NativeDocumentOpenCatalog(documents, store, connection_epoch)
        self.features = FeatureCatalog(documents, store, connection_epoch)
        self.receipts = {}
        self.ownership = OwnedRectangleFeatureRegistry(documents, store, connection_epoch)

    def _capture(self, target_id, guarded_ids=()):
        entries, semantic = self.sessions._capture_session(guarded_ids)
        if not len(entries) < MAX_OPEN_DOCUMENTS:
            raise rejected('rectangle_session_budget', 'Use a bounded complete supported session.')
        snapshots = {}
        for entry in entries:
            row = next(r for r in semantic['documents'] if r['document_id'] == entry.document_id)
            if row['document_type'] != 'part':
                raise rejected('rectangle_baseline_unsupported', 'Every baseline model needs the complete part oracle.')
            first = validated_rectangle_snapshot(self.adapter.rectangle_construction_snapshot(entry.model))
            second = validated_rectangle_snapshot(self.adapter.rectangle_construction_snapshot(entry.model))
            if (first != second or second['configuration'] != row['active_configuration']
                    or second['configurations'] != row['configurations']):
                raise rejected('rectangle_snapshot_changed', 'Complete native target/neighbor observation changed.')
            if entry.document_id != target_id and second['clone_state']['profile'] != BASE:
                raise rejected('rectangle_neighbor_unsupported', 'Neighbors require the fully observed rectangular-base profile.')
            snapshots[entry.document_id] = second
        closing_entries, closing = self.sessions._capture_session(guarded_ids)
        if (closing != semantic or [entry.identity for entry in entries]
                != [entry.identity for entry in closing_entries]):
            raise rejected('rectangle_session_changed', 'Full roster/references/UI/files changed during observation.')
        return closing_entries, semantic, snapshots

    def _state(self, document_id, configuration, profile, guarded_ids=()):
        if (type(document_id) is not str or not document_id.strip()
                or type(configuration) is not str or not configuration.strip()):
            raise rejected('rectangle_context_invalid', 'Use explicit current document and configuration IDs.')
        resolved, _ = self.documents.resolve(document_id, configuration)
        entries, semantic, snapshots = self._capture(document_id, guarded_ids)
        entry = next((e for e in entries if e.document_id == document_id), None)
        if entry is None or entry.identity != resolved.identity:
            raise rejected('document_not_open', 'The exact target incarnation must remain open.')
        row = next(r for r in semantic['documents'] if r['document_id'] == document_id)
        if (semantic['active_document_id'] != document_id or row['active_configuration'] != configuration
                or row['configurations'] != [configuration] or row['path'] != ''
                or row['mode']['read_only_state'] != 0 or not row['visible']
                or row['dependencies'] or semantic['reference_graph']
                or len([w for w in semantic['windows'] if w['document_id'] == document_id]) != 1
                or any(not r['visible'] or r['dependencies'] for r in semantic['documents'])
                or snapshots[document_id]['clone_state']['profile'] != profile):
            raise rejected('rectangle_target_unsupported',
                'Use an active visible unsaved one-configuration target in the exact stage, without references.')
        controls = snapshots[document_id]['clone_state']['creation_controls']
        if controls['add_to_db'] or controls['dimension_input']:
            raise rejected('unsupported_creation_ui', 'Disable AddToDB and interactive dimension input before preparation.')
        return entry, entries, dict(semantic=semantic, snapshots=snapshots)

    def _prepare(self, document_id, configuration, definition, profile, scope, feature_id, feature_kind,
                 guarded_ids=()):
        if not guarded_ids and self.adapter.application_busy():
            raise rejected('application_busy', 'An existing application command cannot be borrowed.')
        entry, entries, state = self._state(document_id, configuration, profile, guarded_ids)
        identity = self.adapter.configuration_identity(entry.model, configuration)
        objects = self.adapter.features(entry.model)
        feature, reference = self.features._resolve(entry, configuration, identity, objects, feature_id)
        summary = self.adapter.feature_summary(feature)
        if summary['feature_type'] != feature_kind or summary['suppressed']:
            raise rejected('rectangle_reference_unsupported', 'The exact current plane/sketch is required.')
        snapshot = state['snapshots'][document_id]['clone_state']
        if feature_kind == 'RefPlane':
            frame = validated_plane_transform(self.adapter.reference_plane_transform(feature))
            name = definition.sketch_name
            if any(r['name'].casefold() == name.casefold() for r in snapshot['features']):
                raise rejected('feature_name_conflict', 'The requested Russian sketch name already exists.')
            expected = dict(solid_body_count=0, sketch_count=1, width_mm=definition.width_mm,
                            height_mm=definition.height_mm)
        else:
            frame = validated_plane_transform([float.fromhex(x) for x in snapshot['sketch']['reference_plane']['transform']])
            if snapshot['sketch']['feature_native_id'] != summary['native_id']:
                raise rejected('rectangle_reference_unsupported', 'The selected feature is not the fully observed rectangle.')
            if any(r['name'].casefold() == definition.feature_name.casefold() for r in snapshot['features']):
                raise rejected('feature_name_conflict', 'The requested Russian extrusion name already exists.')
            parameters = snapshot['parameters']
            w = _positive_length(parameters['width_m'] * 1000., 'width_mm')
            h = _positive_length(parameters['height_m'] * 1000., 'height_mm')
            d = definition.depth_mm
            try:
                volume, area = w * h * d, 2. * math.fsum((w * h, w * d, h * d))
            except (ValueError, OverflowError) as exc:
                raise rejected('part_measurement_overflow', 'The expected solid cannot be represented.') from exc
            if not math.isfinite(volume) or not math.isfinite(area):
                raise rejected('part_measurement_overflow', 'The expected solid cannot be represented.')
            expected = dict(solid_body_count=1, volume_mm3=volume, surface_area_mm2=area)
        token = self.adapter.identity(feature)
        closing, closing_entries, after = self._state(document_id, configuration, profile, guarded_ids)
        closing_cfg = self.adapter.configuration_identity(closing.model, configuration)
        closing_feature, closing_ref = self.features._resolve(closing, configuration, closing_cfg,
            self.adapter.features(closing.model), feature_id)
        if (state != after or [e.identity for e in entries] != [e.identity for e in closing_entries]
                or identity != closing_cfg or self.adapter.identity(closing_feature) != token
                or reference.persistent_id != closing_ref.persistent_id):
            raise rejected('rectangle_snapshot_changed', 'Target/reference/full baseline changed after exact resolution.')
        payload = dict(scope=scope, connection_epoch=self.connection_epoch, document_id=document_id,
            configuration=configuration, definition=vars(definition), baseline=state,
            reference_persistent_id_hex=reference.persistent_id.hex(), plane_transform=list(frame))
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()
        return dict(**payload, revision=revision,
                    revision_scope=scope, expected_geometry=expected,
                    native_execution_available=all(callable(getattr(self.adapter, name, None)) for name in (
                        'native_open_guard', 'new_rectangle_stage_receipt',
                        'create_rectangle_sketch' if profile == EMPTY else 'extrude_rectangle_sketch')))

    def prepare_sketch(self, document_id, configuration, **parameters):
        definition = RectangleSketch.validate(**parameters)
        return self._watched_prepare(document_id, configuration, definition, EMPTY, SKETCH_SCOPE,
                                     definition.plane_object_id, 'RefPlane')

    def prepare_extrusion(self, document_id, configuration, **parameters):
        definition = BlindRectangleExtrusion.validate(**parameters)
        return self._watched_prepare(document_id, configuration, definition, SKETCH, EXTRUSION_SCOPE,
                                     definition.sketch_object_id, 'ProfileFeature')

    def _watched_prepare(self, *args):
        watches = []
        with ExitStack() as cleanup:
            models = self.adapter.documents()
            if len(models) >= MAX_OPEN_DOCUMENTS:
                raise rejected('rectangle_session_budget', 'Use a bounded complete supported session.')
            for model in models:
                if self.adapter.snapshot(model)['document_type'] != 'part':
                    raise rejected('rectangle_baseline_unsupported', 'Every baseline model must be a supported part.')
                watch = self.adapter.watch_part(model)
                cleanup.callback(watch.close)
                watches.append((watch, watch.poll()))
            result = self._prepare(*args)
            if any(watch.poll() != sequence for watch, sequence in watches):
                raise rejected('rectangle_session_changed', 'A baseline model changed during full preparation.')
            return result
