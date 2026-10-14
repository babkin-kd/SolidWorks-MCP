"""Bounded one-direction array of disjoint circular through holes; no CAD calls."""

from dataclasses import dataclass
import math
import re

from .documents import rejected
from .features import russian_name
from .part_creation import _positive_length
from .part_hole import ThroughHole, MATERIAL_MARGIN_M


SCOPE = 'single_base_linear_through_hole_pattern_v1'
MAX_INSTANCES = 64


@dataclass(frozen=True)
class LinearHolePattern:
    base_object_id: str
    object_id: str
    seed_object_id: str
    direction_edge_id: str
    count: int
    spacing_mm: float
    feature_name: str

    @classmethod
    def validate(cls, *, base_object_id, object_id, seed_object_id, direction_edge_id,
                 count, spacing_mm, feature_name='Линейный массив отверстий'):
        for value in (base_object_id, object_id, seed_object_id):
            if not isinstance(value, str) or not re.fullmatch(r'feat_[0-9a-f]{32}', value):
                raise rejected('invalid_pattern_reference', 'Explicit opaque base/circle/seed feature references are required.')
        if len({base_object_id, object_id, seed_object_id}) != 3:
            raise rejected('pattern_reference_overlap', 'The base sketch, circle sketch and cut must be distinct.')
        if not isinstance(direction_edge_id, str) or not re.fullmatch(r'obj_[0-9a-f]{32}', direction_edge_id):
            raise rejected('invalid_pattern_reference', 'An explicit current body edge reference is required.')
        if type(count) is not int or not 2 <= count <= MAX_INSTANCES:
            raise rejected('invalid_pattern_count', 'Count includes the seed and must be an integer from 2 to 64.')
        spacing = _positive_length(spacing_mm, 'spacing_mm')
        if spacing > 10000000.:
            raise rejected('pattern_parameter_out_of_range', 'Spacing exceeds the complete native capture bound.')
        return cls(base_object_id, object_id, seed_object_id, direction_edge_id,
                   count, spacing, russian_name(feature_name))

    def expected_geometry(self, base, circle, axis):
        if type(axis) is not int or axis not in (0, 1):
            raise rejected('unsupported_pattern_axis', 'Only positive local X or Y of the explicit base is supported.')
        diameter = circle['diameter_m']
        spacing = self.spacing_mm / 1000.
        if spacing - diameter < MATERIAL_MARGIN_M:
            raise rejected('pattern_holes_overlap', 'Every pair of holes must leave at least one micrometre of material.')
        shapes = []
        for index in range(self.count):
            x = circle['centre_x_m'] + (index * spacing if axis == 0 else 0.)
            y = circle['centre_y_m'] + (index * spacing if axis == 1 else 0.)
            shapes.append(ThroughHole(self.base_object_id, self.base_object_id,
                x * 1000., y * 1000., diameter * 1000., '', '').expected_geometry(base))
        result = dict(shapes[0])
        radius, depth = diameter / 2., base['depth_m']
        result.update(holes_si=[{'circle_centres_si': row['circle_centres_si'],
                                'radius_si': row['radius_si']} for row in shapes],
            edge_count=12 + 2 * self.count, face_count=6 + self.count,
            volume_mm3=(base['width_m'] * base['height_m'] - self.count * math.pi * radius**2) * depth * 1e9,
            surface_area_mm2=(2 * (base['width_m'] * base['height_m'] - self.count * math.pi * radius**2)
                + 2 * (base['width_m'] + base['height_m']) * depth + self.count * 2 * math.pi * radius * depth) * 1e6)
        result.pop('circle_centres_si')
        result.pop('radius_si')
        if not all(math.isfinite(result[key]) and result[key] > 0
                   for key in ('volume_mm3', 'surface_area_mm2')):
            raise rejected('pattern_geometry_unrepresentable', 'Complete pattern measures must be finite and positive.')
        return result
