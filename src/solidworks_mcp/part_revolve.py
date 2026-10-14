"""Bounded full-turn base revolve candidate with complete analytical proof."""

from copy import deepcopy
from dataclasses import asdict, dataclass
import math
import re

from .cad_cylinder_brep import CYLINDER_BREP_SCOPE
from .dimensions import DimensionCatalog
from .documents import rejected
from .features import russian_name
from .mutations import PreparedMutation
from .part_creation import PartCreationCatalog, _positive_length, validated_plane_transform
from .sketches import persistent_sketch_members, rectangle_profile_parameters


SCOPE = 'empty_part_full_turn_cylinder_revolve_v1'


@dataclass(frozen=True)
class BaseRevolve:
    plane_object_id: str
    radius_mm: float
    height_mm: float
    sketch_name: str
    feature_name: str
    body_name: str
    axis: str

    @classmethod
    def validate(cls, *, plane_object_id, radius_mm, height_mm, axis='profile_y',
                 sketch_name='Эскиз вращения', feature_name='Вращение основания', body_name='Тело вращения'):
        if not isinstance(plane_object_id, str) or not re.fullmatch(r'feat_[0-9a-f]{32}', plane_object_id):
            raise rejected('invalid_plane_reference', 'Use an explicit opaque current plane reference.')
        if axis != 'profile_y':
            raise rejected('unsupported_revolve_axis', 'This scope explicitly revolves the owned x=0 profile edge about its y axis.')
        radius, height = _positive_length(radius_mm, 'radius_mm'), _positive_length(height_mm, 'height_mm')
        if max(radius, height) > 10000000.:
            raise rejected('revolve_parameter_out_of_range', 'Dimensions exceed the complete native coordinate bound.')
        names = tuple(map(russian_name, (sketch_name, feature_name, body_name)))
        if names[0].casefold() == names[1].casefold():
            raise rejected('part_name_collision', 'Sketch and revolve need distinct Russian display names.')
        return cls(plane_object_id, radius, height, *names, axis)

    @property
    def profile_m(self):
        radius, height = self.radius_mm / 1000., self.height_mm / 1000.
        return ((0., 0.), (radius, 0.), (radius, height), (0., height))

    @property
    def volume_mm3(self):
        return math.pi * self.radius_mm**2 * self.height_mm

    @property
    def surface_area_mm2(self):
        return 2.*math.pi*self.radius_mm*(self.radius_mm+self.height_mm)


def cylinder_body_matches(geometry, definition, frame):
    """Match all native analytical surfaces and circles of the complete reader."""
    bodies = geometry.get('bodies', [])
    if len(bodies) != 1:
        return False
    body = bodies[0]
    if (body.get('scope') != CYLINDER_BREP_SCOPE or body.get('vertices') != []
            or len(body.get('edges', [])) != 2 or len(body.get('faces', [])) != 3):
        return False
    frame = validated_plane_transform(frame)
    origin, axis = tuple(frame[9:12]), tuple(frame[3:6])
    height, radius = definition.height_mm/1000., definition.radius_mm/1000.
    ends = [origin, tuple(o+height*a for o,a in zip(origin,axis))]
    close = lambda a,b: all(abs(x-y) <= 1e-12 for x,y in zip(a,b))
    dot = lambda a,b: math.fsum(x*y for x,y in zip(a,b))
    try:
        for edge in body['edges']:
            values = tuple(float.fromhex(v) for v in edge['circle_parameters'])
            if (edge['kind'] != 'circle' or len(values) != 7 or not all(math.isfinite(v) for v in values)
                    or abs(values[6]-radius) > 1e-12 or abs(abs(dot(values[3:6], axis))-1.) > 1e-12):
                return False
            matches = [i for i,point in enumerate(ends) if close(values[:3], point)]
            if len(matches) != 1:
                return False
            ends.pop(matches[0])
        if ends:
            return False
        cylinders = [face for face in body['faces'] if face['surface_type'] == 'cylinder']
        caps = [face for face in body['faces'] if face['surface_type'] == 'plane']
        if len(cylinders) != 1 or len(caps) != 2:
            return False
        side = cylinders[0]
        values = tuple(float.fromhex(v) for v in side['surface_parameters'])
        if (len(values) != 7 or not all(math.isfinite(v) for v in values) or side['normal_opposes_surface']
                or abs(values[6]-radius) > 1e-12 or abs(abs(dot(values[3:6], axis))-1.) > 1e-12):
            return False
        delta = tuple(v-o for v,o in zip(values[:3], origin))
        position = dot(delta, axis)
        if not close(delta, tuple(position*a for a in axis)):
            return False
        ends = [(origin, tuple(-a for a in axis)),
                (tuple(o+height*a for o,a in zip(origin,axis)), axis)]
        for face in caps:
            values = tuple(float.fromhex(v) for v in face['surface_parameters'])
            if len(values) != 6 or not all(math.isfinite(v) for v in values):
                return False
            normal = tuple(-v if face['normal_opposes_surface'] else v for v in values[:3])
            matches = [i for i,(centre,direction) in enumerate(ends)
                       if close(normal,direction) and abs(dot(tuple(c-p for c,p in zip(centre,values[3:])),normal)) <= 1e-12]
            if len(matches) != 1:
                return False
            ends.pop(matches[0])
        return not ends
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


class PartRevolveCatalog(PartCreationCatalog):
    def prepare_base_revolve(self, document_id, configuration, **parameters):
        definition = BaseRevolve.validate(**parameters)
        return self._prepare_base(document_id, configuration, definition, SCOPE)

    def _inspect(self, document_id, configuration, receipt):
        captures = []
        for _ in range(2):
            captured = self.dimensions._capture(document_id, configuration)
            evidence, members = self.adapter.base_revolve_evidence(captured.state[0].model, receipt)
            captures.append((captured, evidence, members))
        first, second = captures
        rows = []
        for _, evidence, _ in captures:
            row = deepcopy(evidence)
            row.pop('volume_mm3', None)
            row.pop('surface_area_mm2', None)
            rows.append(row)
        same = (self.dimensions._same_capture(first[0], second[0]) and rows[0] == rows[1]
                and persistent_sketch_members(first[2]) == persistent_sketch_members(second[2]))
        for key in ('volume_mm3', 'surface_area_mm2'):
            if key in first[1] or key in second[1]:
                same = same and math.isclose(first[1].get(key,-1.), second[1].get(key,-2.), rel_tol=1e-10, abs_tol=1e-8)
        self.dimensions._close_native_proof(second[0].state[0], second[0].event_sequence)
        if not same:
            raise rejected('revolve_changed_during_inspection', 'Complete body, sketch or exact native members changed during inspection.')
        return {'semantic': second[0].state[3], 'revision': second[0].state[4], 'created': second[1]}

    @staticmethod
    def _baseline_unchanged(before, after):
        old = before['semantic']
        current = deepcopy(after['semantic'])
        ids = {row['native_id'] for row in old['tree']['features']}
        current['tree']['features'] = [row for row in current['tree']['features'] if row['native_id'] in ids]
        current['dimensions'] = []  # Empty scope was explicitly proved in preparation.
        return DimensionCatalog._comparable(old,ignore_geometry=True) == DimensionCatalog._comparable(current,ignore_geometry=True)

    @staticmethod
    def _owned_features(before, after, definition):
        evidence = after['created']
        old_ids = {row['native_id'] for row in before['semantic']['tree']['features']}
        added = [row for row in after['semantic']['tree']['features'] if row['native_id'] not in old_ids]
        expected = {}
        if evidence.get('sketch_native_id') is not None:
            expected[evidence['sketch_native_id']] = (definition.sketch_name, 'ProfileFeature')
        if evidence.get('revolution_native_id') is not None:
            if evidence.get('revolution_type') != 'Revolution':
                return False
            expected[evidence['revolution_native_id']] = (definition.feature_name, 'Revolution')
        folders = [row for row in added if row['feature_type'] == 'SolidBodyFolder']
        owned = [row for row in added if row not in folders]
        return (len(folders) <= 1 and len(owned) == len(expected)
                and {row['native_id']:(row['name'],row['feature_type']) for row in owned} == expected
                and not any(row['error_code'] or row['suppressed'] for row in added))

    @staticmethod
    def _valid_profile(before, after, definition, configuration):
        evidence = after['created']
        snapshot = evidence.get('sketch')
        if snapshot is None or snapshot['reference_plane']['pid_hex'] != before['plane_persistent_id_hex']:
            return False
        frame = before['plane_transform']
        if [float.fromhex(v) for v in snapshot['reference_plane']['transform']] != frame:
            return False
        local = validated_plane_transform([float.fromhex(v) for v in snapshot['model_to_sketch']])
        if any(abs(local[i*3+j]-frame[j*3+i]) > 1e-12 for i in range(3) for j in range(3)):
            return False
        profile = rectangle_profile_parameters(snapshot, after['semantic'], configuration)
        if (abs(profile['width_m']-definition.radius_mm/1000.) > 1e-12
                or abs(profile['height_m']-definition.height_mm/1000.) > 1e-12):
            return False
        rows = after['semantic']['dimensions']
        expected = {'Радиус':(evidence['sketch_native_id'], 'mm', definition.radius_mm/1000.),
                    'Высота вращения':(evidence['sketch_native_id'], 'mm', definition.height_mm/1000.),
                    'Угол вращения':(evidence['revolution_native_id'], 'deg', 2.*math.pi)}
        if len(rows) != 3 or {row['name'] for row in rows} != set(expected):
            return False
        for row in rows:
            owner, unit, value = expected[row['name']]
            permitted = ({'sketch_geometry_snapshot_not_implemented'} if unit == 'mm' else {'owner_type_not_accepted'})
            if (row['owner'] is None or row['owner']['native_id'] != owner or row['unit'] != unit
                    or row['driven_state'] != 2 or row['read_only'] or row['reference'] or row['linked'] or row['design_table']
                    or set(row['write_blockers']) - permitted
                    or abs(row['values_si'][configuration]-value) > 1e-12
                    or (unit == 'mm' and row['owner']['owner_native_id'] != evidence['revolution_native_id'])):
                return False
        return evidence.get('axis_verified') is True

    def _verify(self, before, after, definition, configuration):
        evidence = after['created']
        return (evidence.get('complete') is True and evidence.get('fully_defined') is True
                and evidence['controls'] == before['creation_controls'] and evidence['body_name'] == definition.body_name
                and self._baseline_unchanged(before,after) and self._owned_features(before,after,definition)
                and self._valid_profile(before,after,definition,configuration)
                and cylinder_body_matches(after['semantic']['geometry'],definition,before['plane_transform'])
                and math.isclose(evidence['volume_mm3'],definition.volume_mm3,rel_tol=1e-7,abs_tol=1e-8)
                and math.isclose(evidence['surface_area_mm2'],definition.surface_area_mm2,rel_tol=1e-7,abs_tol=1e-8))

    def create_base_revolve(self, operation_id, document_id, configuration, expected_revision, **parameters):
        definition = BaseRevolve.validate(**parameters)
        if self.dimensions.mutation_guard is None:
            raise rejected('mutation_guard_unavailable', 'Revolving requires the owning-STA model guard.')
        target = {}

        def prepare():
            public = self.prepare_base_revolve(document_id, configuration, **asdict(definition))
            capture = self.dimensions._paired_capture(document_id, configuration)
            entry, identity, _, semantic, revision = capture.state
            if revision != public['dimension_revision']:
                raise rejected('revolve_changed_after_preparation', 'The complete empty-part state changed after preparation.')
            features = self.adapter.features(entry.model)
            if tuple(self.adapter.identity(item) for item in features) != capture.feature_identities:
                raise rejected('revolve_changed_after_preparation', 'Exact current feature membership changed.')
            plane, reference = self.features._resolve(entry, configuration, identity, features, definition.plane_object_id)
            if (reference.persistent_id.hex() != public['plane_persistent_id_hex']
                    or list(validated_plane_transform(self.adapter.reference_plane_transform(plane))) != public['plane_transform']):
                raise rejected('revolve_changed_after_preparation', 'The explicit plane reference or frame changed.')
            receipt = self.adapter.new_base_revolve_receipt(entry.model, features, public['creation_controls'])
            self.dimensions._close_native_proof(entry, capture.event_sequence)
            target.update(entry=entry,plane=plane,receipt=receipt)
            return PreparedMutation(public['revision'], {'scope':SCOPE, 'definition':asdict(definition), 'semantic':semantic,
                'plane_persistent_id_hex':public['plane_persistent_id_hex'], 'plane_transform':public['plane_transform'],
                'creation_controls':public['creation_controls']})

        def apply(prepared):
            entry = target['entry']
            entry.features['mutation_sequence'] = entry.features.get('mutation_sequence',0)+1
            self.adapter.create_base_revolve(entry.model,target['plane'],definition,target['receipt'])
            return {'sketch_name':definition.sketch_name,'feature_name':definition.feature_name,'body_name':definition.body_name}

        def restore(before, prepared):
            after = self._inspect(document_id,configuration,target['receipt'])
            if (not self._baseline_unchanged(before,after) or not self._owned_features(before,after,definition)
                    or after['created'].get('controls',before['creation_controls']) != before['creation_controls']
                    or (not after['created'].get('complete') and (after['semantic']['geometry']['bodies'] or after['semantic']['dimensions']))
                    or (after['created'].get('complete') and not self._verify(before,after,definition,configuration))):
                raise rejected('revolve_restore_unsafe', 'Foreign or unproved changes cannot authorize owned-feature deletion.')
            self.adapter.restore_base_revolve(target['entry'].model,target['receipt'])

        return self.dimensions.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=prepare,
            validate=lambda prepared:self.prepare_base_revolve(document_id,configuration,**asdict(definition))['revision'] == prepared.revision,
            apply=apply,inspect=lambda prepared:self._inspect(document_id,configuration,target['receipt']),
            verify=lambda before,after,value:self._verify(before,after,definition,configuration),restore=restore,
            verify_restored=lambda before,after:DimensionCatalog._comparable(before['semantic']) == DimensionCatalog._comparable(after['semantic'])
                and after['created'].get('restored') is True,
            guard=lambda prepared:self.dimensions.mutation_guard(target['entry'].model))
