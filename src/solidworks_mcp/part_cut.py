"""Internal explicit corner-cut preparation; no native writer/MCP registration."""

from dataclasses import asdict, dataclass
import hashlib
import math
import re

from .documents import rejected
from .features import russian_name
from .jobs import _json
from .part_creation import _positive_length
from .sketches import rectangle_parameters


SCOPE = 'single_base_rectangular_corner_through_cut_v1'


@dataclass(frozen=True)
class CornerCut:
    object_id: str
    plane_object_id: str
    width_mm: float
    height_mm: float
    sketch_name: str
    feature_name: str

    @classmethod
    def validate(cls, *, object_id, plane_object_id, width_mm, height_mm,
                 sketch_name='Эскиз выреза', feature_name='Вырез угла'):
        for value in (object_id, plane_object_id):
            if not isinstance(value, str) or not re.fullmatch(r'feat_[0-9a-f]{32}', value):
                raise rejected('invalid_cut_reference', 'Explicit opaque base sketch and plane feature references are required.')
        sketch_name, feature_name = map(russian_name, (sketch_name, feature_name))
        if sketch_name.casefold() == feature_name.casefold():
            raise rejected('cut_name_collision', 'The new sketch and cut need distinct Russian display names.')
        width, height = (_positive_length(width_mm, 'width_mm'),
                         _positive_length(height_mm, 'height_mm'))
        if max(width, height) > 10000000.:
            raise rejected('cut_parameter_out_of_range', 'Cut dimensions exceed the complete native capture bound.')
        return cls(object_id, plane_object_id, width, height, sketch_name, feature_name)

    def expected_geometry(self, base):
        w, h, d = (base[key] for key in ('width_m', 'height_m', 'depth_m'))
        cw, ch = self.width_mm / 1000., self.height_mm / 1000.
        if w - cw < 1e-6 or h - ch < 1e-6:
            raise rejected('cut_removes_base_extent', 'The cut must leave at least one micrometre of material along both base axes.')
        section = w * h - cw * ch
        volume, area = section * d * 1e9, (2. * section + 2. * (w + h) * d) * 1e6
        if not all(math.isfinite(v) and v > 0 for v in (volume, area)):
            raise rejected('cut_geometry_unrepresentable', 'Complete remaining analytical geometry must be finite and positive.')
        profile = ((0., ch), (cw, ch), (cw, 0.), (w, 0.), (w, h), (0., h))
        frame = base['plane_transform']
        vertices = [[float(x * frame[i] + y * frame[3+i] + z * frame[6+i] + frame[9+i]).hex()
                     for i in range(3)] for x, y in profile for z in (0., d)]
        return {'volume_mm3': volume, 'surface_area_mm2': area, 'solid_body_count': 1,
                'vertex_count': 12, 'edge_count': 18, 'face_count': 8, 'vertices_si': vertices,
                'remaining_profile_si': [[x.hex(), y.hex()] for x, y in profile]}


class PartCutCatalog:
    """Read-only candidate; preparation does not authorize or execute a cut."""

    def __init__(self, sketches):
        self.sketches, self.dimensions = sketches, sketches.dimensions
        self.adapter = self.dimensions.adapter

    def _capture(self, document_id, configuration, definition):
        captured = self.sketches._paired(document_id, configuration, definition.object_id)
        entry, identity, _, semantic, _ = captured.dimensions.state
        parameters = rectangle_parameters(captured.snapshot, semantic, configuration)
        names = {row['name'].casefold() for row in semantic['tree']['features']}
        if definition.sketch_name.casefold() in names or definition.feature_name.casefold() in names:
            raise rejected('cut_name_conflict', 'Requested Russian feature/sketch name already exists in this part.')
        objects = self.adapter.features(entry.model)
        if tuple(self.adapter.identity(item) for item in objects) != captured.dimensions.feature_identities:
            raise rejected('cut_target_changed', 'Current feature membership changed after the complete base capture.')
        plane, ref = self.dimensions.features._resolve(entry, configuration, identity, objects,
                                                     definition.plane_object_id)
        row = self.adapter.feature_summary(plane)
        if (row['feature_type'] != 'RefPlane' or row['suppressed']
                or ref.persistent_id.hex() != captured.snapshot['reference_plane']['pid_hex']):
            raise rejected('cut_plane_mismatch', 'The explicit plane must be the exact current unsuppressed plane of this base sketch.')
        controls = self.adapter.part_creation_controls(entry.model)
        if controls['add_to_db'] or controls['dimension_input']:
            raise rejected('unsupported_cut_ui', 'AddToDB and interactive dimension input must be disabled before preparing creation.')
        expected = definition.expected_geometry(parameters)
        token = self.adapter.identity(plane)
        self.dimensions._close_native_proof(entry, captured.dimensions.event_sequence)
        return captured, ref.persistent_id, token, controls, parameters, expected

    def prepare_corner_cut(self, document_id, configuration, **parameters):
        definition = CornerCut.validate(**parameters)  # Before any native access.
        first = self._capture(document_id, configuration, definition)
        second = self._capture(document_id, configuration, definition)
        same = first[0].revision == second[0].revision and first[1:] == second[1:]
        self.dimensions._close_native_proof(second[0].dimensions.state[0], second[0].dimensions.event_sequence)
        if not same:
            raise rejected('cut_target_changed', 'Complete base/plane/control/expected-shape proof changed during preparation.')
        captured, pid, _, controls, base, expected = first
        payload = {'scope': SCOPE, 'document_id': document_id, 'configuration': configuration,
                   'base_revision': captured.revision, 'definition': asdict(definition),
                   'plane_pid_hex': pid.hex(), 'controls': controls, 'base_parameters': base,
                   'expected_geometry': expected}
        return {'document_id': document_id, 'configuration': configuration, 'revision_scope': SCOPE,
                'revision': 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest(),
                'definition': asdict(definition), 'expected_geometry': expected,
                'native_creation_available': False}
