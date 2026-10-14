"""Inputs for separate rectangular sketch/extrusion candidates, no CAD calls."""
from dataclasses import dataclass
import math
import re

from .documents import rejected
from .features import russian_name
from .part_creation import _positive_length


def _reference(value, label):
    if type(value) is not str or re.fullmatch(r'feat_[0-9a-f]{32}', value) is None:
        raise rejected('invalid_' + label + '_reference', 'Use an explicit opaque feature ID.')
    return value


@dataclass(frozen=True)
class RectangleSketch:
    plane_object_id: str
    width_mm: float
    height_mm: float
    sketch_name: str

    @classmethod
    def validate(cls, *, plane_object_id, width_mm, height_mm, sketch_name='Эскиз основания'):
        plane = _reference(plane_object_id, 'plane')
        width, height = _positive_length(width_mm, 'width_mm'), _positive_length(height_mm, 'height_mm')
        if not math.isfinite(width * height):
            raise rejected('part_measurement_overflow', 'Rectangle area cannot be represented.')
        return cls(plane, width, height, russian_name(sketch_name))

    @property
    def profile_m(self):
        w, h = self.width_mm / 1000., self.height_mm / 1000.
        return ((0., 0.), (w, 0.), (w, h), (0., h))


@dataclass(frozen=True)
class BlindRectangleExtrusion:
    sketch_object_id: str
    depth_mm: float
    feature_name: str
    body_name: str

    @classmethod
    def validate(cls, *, sketch_object_id, depth_mm, feature_name='Основание', body_name='Тело основания'):
        return cls(_reference(sketch_object_id, 'sketch'), _positive_length(depth_mm, 'depth_mm'),
                   russian_name(feature_name), russian_name(body_name))

    @property
    def depth_m(self):
        return self.depth_mm / 1000.
