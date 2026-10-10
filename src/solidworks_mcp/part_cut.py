"""Explicit rectangular corner through cut with complete bounded native proof."""

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import math
import re

from .documents import rejected
from .dimensions import DimensionCatalog
from .features import russian_name
from .jobs import _json
from .mutations import PreparedMutation
from .part_creation import _positive_length
from .sketches import rectangle_parameters, rectangle_profile_parameters, persistent_sketch_members


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
    """Explicit candidate with durable execution and scoped owned restoration."""

    def __init__(self, sketches):
        self.sketches, self.dimensions = sketches, sketches.dimensions
        self.adapter = self.dimensions.adapter

    def _capture(self, document_id, configuration, definition):
        captured = self.sketches._capture(document_id, configuration, definition.object_id)
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

    def _prepare(self, document_id, configuration, **parameters):
        definition = CornerCut.validate(**parameters)  # Before any native access.
        first = self._capture(document_id, configuration, definition)
        second = self._capture(document_id, configuration, definition)
        same = (self.dimensions._same_capture(first[0].dimensions, second[0].dimensions)
                and first[0].revision == second[0].revision and first[1:] == second[1:]
                and persistent_sketch_members(first[0].members) == persistent_sketch_members(second[0].members))
        self.dimensions._close_native_proof(second[0].dimensions.state[0], second[0].dimensions.event_sequence)
        if not same:
            raise rejected('cut_target_changed', 'Complete base/plane/control/expected-shape proof changed during preparation.')
        captured, pid, _, controls, base, expected = first
        payload = {'scope': SCOPE, 'document_id': document_id, 'configuration': configuration,
                   'base_revision': captured.revision, 'definition': asdict(definition),
                   'plane_pid_hex': pid.hex(), 'controls': controls, 'base_parameters': base,
                   'expected_geometry': expected}
        public = {'document_id': document_id, 'configuration': configuration, 'revision_scope': SCOPE,
                'revision': 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest(),
                'definition': asdict(definition), 'expected_geometry': expected,
                'native_creation_available': True}
        return public, second

    def prepare_corner_cut(self, document_id, configuration, **parameters):
        return self._prepare(document_id, configuration, **parameters)[0]

    def _inspect(self, document_id, configuration, definition, receipt):
        readings = []
        for _ in range(2):
            captured = self.sketches._capture(document_id, configuration, definition.object_id)
            evidence, members = self.adapter.corner_cut_evidence(captured.dimensions.state[0].model, receipt)
            readings.append((captured, evidence, members))
        first, second = readings
        # Independent mass values may differ by solver ULP; full BREP and sketch
        # semantics, ownership and canonical references remain exact.
        evidence_rows = []
        for _, evidence, _ in readings:
            row = deepcopy(evidence)
            row.pop('volume_mm3', None)
            row.pop('surface_area_mm2', None)
            evidence_rows.append(row)
        same = (self.dimensions._same_capture(first[0].dimensions, second[0].dimensions)
                and first[0].revision == second[0].revision
                and persistent_sketch_members(first[0].members) == persistent_sketch_members(second[0].members)
                and evidence_rows[0] == evidence_rows[1]
                and persistent_sketch_members(first[2]) == persistent_sketch_members(second[2]))
        for key in ('volume_mm3', 'surface_area_mm2'):
            if key in first[1] or key in second[1]:
                same = same and math.isclose(first[1].get(key, -1.), second[1].get(key, -2.), rel_tol=1e-10, abs_tol=1e-8)
        self.dimensions._close_native_proof(second[0].dimensions.state[0], second[0].dimensions.event_sequence)
        if not same:
            raise rejected('cut_changed_during_inspection', 'Complete base/cut/native proof changed across inspection.')
        return {'semantic': second[0].dimensions.state[3], 'base_sketch': second[0].snapshot,
                'revision': second[0].revision, 'created': second[1]}

    @staticmethod
    def _baseline_unchanged(before, after):
        old = before['semantic']
        current = deepcopy(after['semantic'])
        ids = {row['native_id'] for row in old['tree']['features']}
        current['tree']['features'] = [row for row in current['tree']['features'] if row['native_id'] in ids]
        dimension_names = {row['full_name'] for row in old['dimensions']}
        current['dimensions'] = [row for row in current['dimensions'] if row['full_name'] in dimension_names]
        return (DimensionCatalog._comparable(old, ignore_geometry=True) == DimensionCatalog._comparable(current, ignore_geometry=True)
                and before['base_sketch'] == after['base_sketch'])

    @staticmethod
    def _owned_features(before, after, definition):
        evidence = after['created']
        old_ids = {row['native_id'] for row in before['semantic']['tree']['features']}
        added = [row for row in after['semantic']['tree']['features'] if row['native_id'] not in old_ids]
        expected = {evidence.get('sketch_native_id'): (definition.sketch_name, 'ProfileFeature')}
        if evidence.get('cut_native_id') is not None:
            expected[evidence['cut_native_id']] = (definition.feature_name, 'Cut')
        if None in expected:
            return not added
        return (len(added) == len(expected)
                and {row['native_id']: (row['name'], row['feature_type']) for row in added} == expected
                and not any(row['error_code'] or row['suppressed'] for row in added))

    @staticmethod
    def _valid_cut_sketch(before, after, definition, configuration):
        snapshot = after['created'].get('sketch')
        if snapshot is None:
            return False
        if any(snapshot[key] != before['base_sketch'][key]
               for key in ('reference_plane', 'model_to_sketch', 'model_origin', 'model_origin_point')):
            return False
        parameters = rectangle_profile_parameters(snapshot, after['semantic'], configuration)
        if (not math.isclose(parameters['width_m'], definition.width_mm / 1000., rel_tol=0., abs_tol=1e-12)
                or not math.isclose(parameters['height_m'], definition.height_mm / 1000., rel_tol=0., abs_tol=1e-12)):
            return False
        rows = [row for row in after['semantic']['dimensions'] if row['owner']
                and row['owner']['native_id'] == after['created']['sketch_native_id']]
        old_names = {row['full_name'] for row in before['semantic']['dimensions']}
        extra = [row for row in after['semantic']['dimensions'] if row['full_name'] not in old_names]
        return (len(extra) == len(rows) == 2 and {row['name'] for row in rows} == {'Ширина выреза', 'Высота выреза'}
                and all(row['owner']['owner_native_id'] == after['created']['cut_native_id'] for row in rows))

    def create_corner_cut(self, operation_id, document_id, configuration, expected_revision, **parameters):
        definition = CornerCut.validate(**parameters)
        if self.dimensions.mutation_guard is None:
            raise rejected('mutation_guard_unavailable', 'An owning-STA model guard is required for native cuts.')
        target = {}

        def prepare():
            public, captured = self._prepare(document_id, configuration, **asdict(definition))
            base = captured[0]
            entry, identity, _, semantic, _ = base.dimensions.state
            features = self.adapter.features(entry.model)
            if tuple(self.adapter.identity(item) for item in features) != base.dimensions.feature_identities:
                raise rejected('cut_target_changed', 'Feature membership changed after preparation.')
            plane, reference = self.dimensions.features._resolve(entry, configuration, identity, features, definition.plane_object_id)
            if reference.persistent_id != captured[1] or self.adapter.identity(plane) != captured[2]:
                raise rejected('cut_target_changed', 'The explicit native plane changed after preparation.')
            receipt = self.adapter.new_corner_cut_receipt(entry.model, features, captured[3])
            self.dimensions._close_native_proof(entry, base.dimensions.event_sequence)
            target.update(entry=entry, plane=plane, receipt=receipt)
            return PreparedMutation(public['revision'], {'scope': SCOPE, 'definition': asdict(definition),
                'semantic': semantic, 'base_sketch': base.snapshot, 'controls': captured[3],
                'body_name': receipt.baseline_body_name, 'expected_geometry': captured[5]})

        def validate(prepared):
            return self.prepare_corner_cut(document_id, configuration, **asdict(definition))['revision'] == prepared.revision

        def apply(prepared):
            target['entry'].features['mutation_sequence'] = target['entry'].features.get('mutation_sequence', 0) + 1
            self.adapter.create_corner_cut(target['entry'].model, target['plane'], definition, target['receipt'])
            return {'sketch_name': definition.sketch_name, 'feature_name': definition.feature_name}

        def inspect(prepared):
            return self._inspect(document_id, configuration, definition, target['receipt'])

        def verify(before, after, value):
            evidence = after['created']
            return (evidence.get('complete') is True and evidence.get('fully_defined') is True
                    and evidence['controls'] == before['controls'] and evidence['body_name'] == before['body_name']
                    and self._baseline_unchanged(before, after) and self._owned_features(before, after, definition)
                    and self._valid_cut_sketch(before, after, definition, configuration)
                    and corner_body_matches(after['semantic']['geometry'], before['expected_geometry'])
                    and all(math.isclose(evidence[key], before['expected_geometry'][key], rel_tol=1e-10, abs_tol=1e-8)
                            for key in ('volume_mm3', 'surface_area_mm2')))

        def restore(before, prepared):
            current = inspect(prepared)
            if (not self._baseline_unchanged(before, current) or not self._owned_features(before, current, definition)
                    or current['created'].get('controls') != before['controls']):
                raise rejected('cut_restore_unsafe', 'Foreign metadata, constraints or controls prevent scoped restoration.')
            if current['created'].get('complete'):
                if (not self._valid_cut_sketch(before, current, definition, configuration)
                        or not corner_body_matches(current['semantic']['geometry'], before['expected_geometry'])):
                    raise rejected('cut_restore_unsafe', 'Current owned cut sketch/body differs from the requested shape.')
            elif current['semantic']['geometry'] != before['semantic']['geometry']:
                raise rejected('cut_restore_unsafe', 'Unconfirmed foreign body effects prevent restoration.')
            self.adapter.restore_corner_cut(target['entry'].model, target['receipt'])

        return self.dimensions.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
            expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply, inspect=inspect,
            verify=verify, restore=restore,
            verify_restored=lambda before, after: self.dimensions._comparable(before['semantic'])
                == self.dimensions._comparable(after['semantic']) and before['base_sketch'] == after['base_sketch']
                and after['created'].get('restored') is True,
            guard=lambda prepared: self.dimensions.mutation_guard(target['entry'].model))


def corner_body_matches(geometry, expected):
    """Match the complete native L-prism topology, including all face contours."""
    bodies = geometry.get('bodies', [])
    if len(bodies) != 1:
        return False
    body = bodies[0]
    if any(len(body[key]) != expected[count] for key, count in
           (('vertices', 'vertex_count'), ('edges', 'edge_count'), ('faces', 'face_count'))):
        return False
    expected_vertices = [tuple(float.fromhex(v) for v in point) for point in expected['vertices_si']]
    actual_vertices = [tuple(float.fromhex(v) for v in point) for point in body['vertices']]
    mapping = {}
    for index, point in enumerate(actual_vertices):
        matches = [i for i, candidate in enumerate(expected_vertices) if all(abs(a-b) <= 1e-9 for a, b in zip(point, candidate))]
        if len(matches) != 1 or matches[0] in mapping.values():
            return False
        mapping[index] = matches[0]
    edge_pairs = [frozenset((2*i, 2*((i+1)%6))) for i in range(6)]
    edge_pairs += [frozenset((2*i+1, 2*((i+1)%6)+1)) for i in range(6)]
    edge_pairs += [frozenset((2*i, 2*i+1)) for i in range(6)]
    actual_edges = [frozenset((mapping[row['start']], mapping[row['end']])) for row in body['edges']]
    if len(set(actual_edges)) != 18 or set(actual_edges) != set(edge_pairs):
        return False
    expected_faces = [tuple(2*i+z for i in range(6)) for z in (0, 1)]
    expected_faces += [(2*i, 2*((i+1)%6), 2*((i+1)%6)+1, 2*i+1) for i in range(6)]

    def cycle(values):
        rotations = [values[i:]+values[:i] for i in range(len(values))]
        reverse = tuple(reversed(values))
        rotations += [reverse[i:]+reverse[:i] for i in range(len(values))]
        return min(rotations)

    actual_faces = []
    for face in body['faces']:
        if len(face['loops']) != 1 or face['loops'][0]['outer'] is not True:
            return False
        coedges = face['loops'][0]['coedges']
        vertices = tuple(mapping[row['start']] for row in coedges)
        if len(set(vertices)) != len(vertices):
            return False
        actual_faces.append(cycle(vertices))
    return sorted(actual_faces) == sorted(cycle(face) for face in expected_faces)
