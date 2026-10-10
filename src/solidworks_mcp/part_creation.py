"""Validated engineering input for the first v2 part-construction workflow.

This module performs no CAD writes and exposes no MCP command. Native execution
must resolve the explicit plane, checkpoint the full revision and retain exact
created objects before this definition can be used by a builder.
"""

from dataclasses import asdict, dataclass
import hashlib
import math
import re

from .documents import rejected
from .features import russian_name
from .jobs import _json


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
    """Internal read-only preparation; no creation tool is published yet.

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
        second = self.dimensions._paired_capture(document_id, configuration)
        closing_objects = self.adapter.features(second.state[0].model)
        closing_plane, _ = self.features._resolve(second.state[0], configuration, second.state[1],
                                                  closing_objects, definition.plane_object_id)
        closing_frame = validated_plane_transform(self.adapter.reference_plane_transform(closing_plane))
        same_plane = self.adapter.identity(closing_plane) == plane_identity
        self.dimensions._close_capture_pair(first, second)  # Last native comparisons/event poll.
        if not same_plane or frame != closing_frame:
            raise rejected('document_changed_during_read', 'Plane identity or transform changed during preparation.')
        payload = {'revision_scope': SCOPE, 'dimension_revision': dimension_revision,
                   'definition': asdict(definition), 'plane_persistent_id_hex': reference.persistent_id.hex(),
                   'plane_transform': list(frame)}
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        return {'document_id': document_id, 'configuration': configuration, 'revision': revision,
                **payload, 'expected_geometry': {'volume_mm3': definition.volume_mm3,
                    'surface_area_mm2': definition.surface_area_mm2, 'solid_body_count': 1},
                'native_creation_available': False}
