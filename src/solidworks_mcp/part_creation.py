"""Validated engineering input for the first v2 part-construction workflow.

Input validation performs no CAD calls. Internal construction resolves the
explicit plane, checkpoints the full revision and retains exact created objects.
No new MCP command is exposed before installed/native acceptance.
"""

from dataclasses import asdict, dataclass
import hashlib
import math
import re

from .documents import rejected
from .features import russian_name
from .jobs import _json
from .mutations import PreparedMutation


MIN_RECTANGLE_SIZE_MM = 0.001  # First builder scope: edges/depth at least one micrometre.
SCOPE = 'empty_part_base_rectangle_v1'


def _positive_length(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise rejected('invalid_part_length', f'{label} must be a finite number in millimetres.')
    try:
        number = float(value)
    except OverflowError as exc:
        raise rejected('invalid_part_length', f'{label} cannot be represented as a native length.') from exc
    if not math.isfinite(number) or number < MIN_RECTANGLE_SIZE_MM:
        raise rejected('invalid_part_length', f'{label} must be finite and at least {MIN_RECTANGLE_SIZE_MM} mm.')
    return number


@dataclass(frozen=True)
class BaseRectangle:
    """A rectangle at the explicit plane origin, extruded along its positive normal.

    Names are display names only. ``plane_object_id`` must later resolve through
    FeatureCatalog in the requested document/configuration; it is never a plane
    name, native index or instruction to use the first plane.
    """

    plane_object_id: str
    width_mm: float
    height_mm: float
    depth_mm: float
    sketch_name: str
    feature_name: str
    body_name: str

    @classmethod
    def validate(cls, *, plane_object_id, width_mm, height_mm, depth_mm,
                 sketch_name='Эскиз основания', feature_name='Основание', body_name='Тело основания'):
        if not isinstance(plane_object_id, str) or not re.fullmatch(r'feat_[0-9a-f]{32}', plane_object_id):
            raise rejected('invalid_plane_reference', 'Use an opaque feature reference from the explicit document/configuration.')
        sketch_name, feature_name, body_name = map(russian_name, (sketch_name, feature_name, body_name))
        if sketch_name.casefold() == feature_name.casefold():
            raise rejected('part_name_collision', 'The sketch and extrusion require distinct Russian names.')
        width, height, depth = (_positive_length(width_mm, 'width_mm'),
                                _positive_length(height_mm, 'height_mm'),
                                _positive_length(depth_mm, 'depth_mm'))
        try:
            area = 2. * math.fsum((width * height, width * depth, height * depth))
            volume = width * height * depth
        except (OverflowError, ValueError) as exc:
            raise rejected('part_measurement_overflow', 'The analytical rectangle properties cannot be represented.') from exc
        if not math.isfinite(area) or not math.isfinite(volume):
            raise rejected('part_measurement_overflow', 'The analytical rectangle properties cannot be represented.')
        return cls(plane_object_id, width, height, depth, sketch_name, feature_name, body_name)

    @property
    def profile_m(self):
        w, h = self.width_mm / 1000., self.height_mm / 1000.
        return ((0., 0.), (w, 0.), (w, h), (0., h))

    @property
    def depth_m(self):
        return self.depth_mm / 1000.

    @property
    def volume_mm3(self):
        return self.width_mm * self.height_mm * self.depth_mm

    @property
    def surface_area_mm2(self):
        w, h, d = self.width_mm, self.height_mm, self.depth_mm
        return 2. * math.fsum((w * h, w * d, h * d))


def validated_plane_transform(values):
    """Accept a rigid reference plane at the model origin, in native metres.

    SolidWorks MathTransform: rotation 0..8, translation 9..11, scale 12,
    unused 13..15. Offset planes remain outside this initial builder scope.
    """
    if not isinstance(values, (tuple, list)) or len(values) != 16:
        raise rejected('invalid_plane_transform', 'Expected the complete native reference-plane transform.')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
        raise rejected('invalid_plane_transform', 'Plane transform entries must be finite numbers.')
    try:
        data = tuple(float(v) for v in values)
    except OverflowError as exc:
        raise rejected('invalid_plane_transform', 'Plane transform is not representable.') from exc
    if not all(math.isfinite(v) for v in data):
        raise rejected('invalid_plane_transform', 'Plane transform entries must be finite numbers.')
    axes = (data[0:3], data[3:6], data[6:9])
    if any(abs(v) > 1. + 1e-10 for v in data[:9]):
        raise rejected('unsupported_plane_transform', 'Plane axes must have unit length; scaling is unsupported.')
    for i in range(3):
        for j in range(3):
            if not math.isclose(math.fsum(a * b for a, b in zip(axes[i], axes[j])),
                                float(i == j), rel_tol=0., abs_tol=1e-10):
                raise rejected('unsupported_plane_transform', 'A rigid orthonormal plane frame is required.')
    cross = (axes[0][1] * axes[1][2] - axes[0][2] * axes[1][1],
             axes[0][2] * axes[1][0] - axes[0][0] * axes[1][2],
             axes[0][0] * axes[1][1] - axes[0][1] * axes[1][0])
    if (not math.isclose(math.fsum(a * b for a, b in zip(cross, axes[2])), 1., abs_tol=1e-10)
            or not math.isclose(data[12], 1., rel_tol=0., abs_tol=1e-10)):
        raise rejected('unsupported_plane_transform', 'A unit-scale right-handed plane frame is required.')
    if any(abs(v) > 1e-12 for v in data[9:12]):
        raise rejected('unsupported_offset_plane', 'This first construction scope requires a plane at the model origin.')
    return data


class PartCreationCatalog:
    """Internal preparation and guarded execution; no creation tool published yet.

    The returned revision binds the complete dimension/control/geometry capture,
    persistent plane reference, plane transform and validated engineering input.
    A future executor must repeat preparation inside its durable mutation guard;
    this result is neither a native object handle nor authorization to write.
    """

    def __init__(self, dimensions):
        self.dimensions = dimensions
        self.features = dimensions.features
        self.adapter = dimensions.adapter

    @staticmethod
    def _empty_writable_part(semantic):
        tree, context = semantic['tree'], semantic['context']
        if len(tree['document']['configurations']) != 1 or not context['configuration_geometry_complete']:
            raise rejected('unsupported_part_configurations', 'The first construction scope requires one configuration.')
        if (tree['needs_rebuild'] or any(context['configuration_needs_rebuild'].values())):
            raise rejected('document_needs_rebuild', 'Rebuild the explicit part before preparing construction.')
        if not context['active_document']:
            raise rejected('document_not_active', 'The explicit part must already be active; no implicit activation.')
        if context['read_only'] or context['editing_sketch']:
            raise rejected('part_not_writable', 'Read-only documents and open sketches are outside construction scope.')
        if (context['external_reference_count'] or context['equation_count'] or context['equations_linked']
                or context['design_table'] or context['unsafe_feature_types']):
            raise rejected('unsupported_part_controls', 'Externally controlled or derived geometry is outside this scope.')
        if (semantic['dimensions'] or semantic['geometry'].get('bodies') != []
                or any(row['feature_type'] in ('ProfileFeature', '3DProfileFeature') for row in tree['features'])):
            raise rejected('part_not_empty', 'Base construction initially requires no bodies, dimensions or user sketches.')
        if any(row['error_code'] for row in tree['features']):
            raise rejected('feature_error_before_creation', 'Resolve existing feature errors before construction.')

    def prepare_base_extrusion(self, document_id, configuration, **parameters):
        definition = BaseRectangle.validate(**parameters)  # Before any CAD access.
        return self._prepare_base(document_id, configuration, definition, SCOPE)

    def _prepare_base(self, document_id, configuration, definition, scope):
        """Shared read proof for validated empty-part builders; no native write."""
        first = self.dimensions._paired_capture(document_id, configuration)
        entry, identity, _, semantic, dimension_revision = first.state
        self._empty_writable_part(semantic)
        names = {row['name'].casefold() for row in semantic['tree']['features']}
        if definition.sketch_name.casefold() in names or definition.feature_name.casefold() in names:
            raise rejected('feature_name_conflict', 'Requested Russian names already exist in the explicit part.')
        objects = self.adapter.features(entry.model)
        plane, reference = self.features._resolve(entry, configuration, identity, objects, definition.plane_object_id)
        summary = self.adapter.feature_summary(plane)
        if summary['feature_type'] != 'RefPlane' or summary['suppressed']:
            raise rejected('invalid_reference_plane', 'The explicit reference must be an unsuppressed native plane.')
        plane_identity = self.adapter.identity(plane)
        frame = validated_plane_transform(self.adapter.reference_plane_transform(plane))
        controls = self.adapter.part_creation_controls(entry.model)
        if controls['add_to_db'] or controls['dimension_input']:
            raise rejected('unsupported_creation_ui', 'Disable AddToDB and interactive dimension input before construction.')
        second = self.dimensions._paired_capture(document_id, configuration)
        closing_objects = self.adapter.features(second.state[0].model)
        closing_plane, _ = self.features._resolve(second.state[0], configuration, second.state[1],
                                                  closing_objects, definition.plane_object_id)
        closing_frame = validated_plane_transform(self.adapter.reference_plane_transform(closing_plane))
        closing_controls = self.adapter.part_creation_controls(second.state[0].model)
        same_plane = self.adapter.identity(closing_plane) == plane_identity
        self.dimensions._close_capture_pair(first, second)  # Last native comparisons/event poll.
        if not same_plane or frame != closing_frame or controls != closing_controls:
            raise rejected('document_changed_during_read', 'Plane identity or transform changed during preparation.')
        payload = {'revision_scope': scope, 'dimension_revision': dimension_revision,
                   'definition': asdict(definition), 'plane_persistent_id_hex': reference.persistent_id.hex(),
                   'plane_transform': list(frame), 'creation_controls': controls}
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        return {'document_id': document_id, 'configuration': configuration, 'revision': revision,
                **payload, 'expected_geometry': {'volume_mm3': definition.volume_mm3,
                    'surface_area_mm2': definition.surface_area_mm2, 'solid_body_count': 1},
                'native_creation_available': True}

    def create_base_extrusion(self, operation_id, document_id, configuration, expected_revision, **parameters):
        """Internal guarded construction, initially on the validated empty scope.

        Native receipts never leave the owning STA. They contain exact returned
        handles, not candidates inferred from names or differences in the tree.
        The durable coordinator holds the application if restoration is unknown.
        """
        definition = BaseRectangle.validate(**parameters)
        if self.dimensions.mutation_guard is None:
            raise rejected('mutation_guard_unavailable', 'Construction requires the owning-STA native model guard.')
        target = {}

        def prepare():
            public = self.prepare_base_extrusion(document_id, configuration, **asdict(definition))
            capture = self.dimensions._paired_capture(document_id, configuration)
            entry, identity, _, semantic, revision = capture.state
            if revision != public['dimension_revision']:
                raise rejected('document_changed_during_read', 'Construction state changed after preparation.')
            features = self.adapter.features(entry.model)
            plane, _ = self.features._resolve(entry, configuration, identity, features, definition.plane_object_id)
            receipt = self.adapter.new_base_receipt(entry.model, features, public['creation_controls'])
            frame = validated_plane_transform(self.adapter.reference_plane_transform(plane))
            if list(frame) != public['plane_transform']:
                raise rejected('document_changed_during_read', 'Reference plane moved after preparation.')
            self.dimensions._close_native_proof(entry, capture.event_sequence)
            target.update(entry=entry, plane=plane, receipt=receipt, public=public)
            return PreparedMutation(public['revision'], {'scope': SCOPE, 'definition': asdict(definition),
                'semantic': semantic, 'plane_persistent_id_hex': public['plane_persistent_id_hex'],
                'plane_transform': public['plane_transform'], 'creation_controls': public['creation_controls']})

        def validate(prepared):
            current = self.prepare_base_extrusion(document_id, configuration, **asdict(definition))
            return current['revision'] == prepared.revision

        def apply(prepared):
            entry = target['entry']
            entry.features['mutation_sequence'] = entry.features.get('mutation_sequence', 0) + 1
            self.adapter.create_base_rectangle(entry.model, target['plane'], definition, target['receipt'])
            return {'sketch_name': definition.sketch_name, 'feature_name': definition.feature_name,
                    'body_name': definition.body_name}

        def inspect(prepared):
            capture = self.dimensions._paired_capture(document_id, configuration)
            entry, _, _, semantic, revision = capture.state
            evidence = self.adapter.base_rectangle_evidence(entry.model, target['receipt'])
            self.dimensions._close_native_proof(entry, capture.event_sequence)
            return {'semantic': semantic, 'revision': revision, 'created': evidence}

        def verify(before, after, value):
            evidence, semantic = after['created'], after['semantic']
            if not evidence.get('complete') or evidence['controls'] != before['creation_controls']:
                return False
            if not evidence['fully_defined'] or evidence['body_name'] != definition.body_name:
                return False
            if not (math.isclose(evidence['volume_mm3'], definition.volume_mm3, rel_tol=1e-7, abs_tol=1e-8)
                    and math.isclose(evidence['surface_area_mm2'], definition.surface_area_mm2, rel_tol=1e-7, abs_tol=1e-8)):
                return False
            old = before['semantic']
            if (semantic['configuration_epochs'] != old['configuration_epochs']
                    or semantic['context'] != old['context'] or semantic['tree']['needs_rebuild']):
                return False
            document = dict(semantic['tree']['document'])
            baseline_document = dict(old['tree']['document'])
            document.pop('update_stamp', None)
            baseline_document.pop('update_stamp', None)
            if document != baseline_document:
                return False
            baseline_rows = old['tree']['features']
            current_rows = semantic['tree']['features']
            baseline_ids = {row['native_id'] for row in baseline_rows}
            if [row for row in current_rows if row['native_id'] in baseline_ids] != baseline_rows:
                return False
            added = [row for row in current_rows if row['native_id'] not in baseline_ids]
            owned_ids = {evidence['sketch_native_id'], evidence['extrusion_native_id']}
            if any(row['error_code'] or row['suppressed'] for row in added):
                return False
            if any(row['native_id'] not in owned_ids and row['feature_type'] != 'SolidBodyFolder' for row in added):
                return False
            expected_names = {evidence['sketch_native_id']: definition.sketch_name,
                              evidence['extrusion_native_id']: definition.feature_name}
            if {row['native_id']: row['name'] for row in added if row['native_id'] in owned_ids} != expected_names:
                return False
            rows = semantic['dimensions']
            expected_sizes = {'Ширина': definition.width_mm / 1000., 'Высота': definition.height_mm / 1000.,
                              'Толщина': definition.depth_m}
            if len(rows) != 3 or {row['name'] for row in rows} != set(expected_sizes):
                return False
            for row in rows:
                # Sketch driving dimensions are proved during creation; their
                # later editing remains outside the existing dimension scope.
                allowed_blockers = {'sketch_geometry_snapshot_not_implemented'} if row['owner']['native_id'] == evidence['sketch_native_id'] else set()
                if (row['owner']['native_id'] not in owned_ids or row['reference'] or row['read_only']
                        or set(row['write_blockers']) - allowed_blockers or row['driven_state'] != 2 or row['unit'] != 'mm'
                        or not math.isclose(row['values_si'][configuration], expected_sizes[row['name']],
                                            rel_tol=1e-8, abs_tol=1e-10)):
                    return False
            bodies = semantic['geometry']['bodies']
            if len(bodies) != 1:
                return False
            vertices = bodies[0]['vertices']
            if len(vertices) != 8 or len(bodies[0]['edges']) != 12 or len(bodies[0]['faces']) != 6:
                return False
            frame = before['plane_transform']
            expected = [tuple(x * frame[i] + y * frame[3 + i] + z * frame[6 + i] + frame[9 + i]
                              for i in range(3))
                        for x, y in definition.profile_m for z in (0., definition.depth_m)]
            actual = [tuple(float.fromhex(v) for v in point) for point in vertices]
            # Match every exact BREP vertex once, never just a bounding box.
            for point in expected:
                match = next((i for i, candidate in enumerate(actual)
                              if all(math.isclose(a, b, rel_tol=0., abs_tol=1e-9) for a, b in zip(point, candidate))), None)
                if match is None:
                    return False
                actual.pop(match)
            return not actual

        def restore(before, prepared):
            self.adapter.restore_base_rectangle(target['entry'].model, target['receipt'])

        return self.dimensions.coordinator.execute(operation_id, document_id=document_id,
            configuration=configuration, expected_revision=expected_revision, prepare=prepare,
            validate=validate, apply=apply, inspect=inspect, verify=verify, restore=restore,
            verify_restored=lambda before, after: self.dimensions._comparable(before['semantic'])
                == self.dimensions._comparable(after['semantic']) and after['created']['restored'] is True,
            guard=lambda prepared: self.dimensions.mutation_guard(target['entry'].model))
