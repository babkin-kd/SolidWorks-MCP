"""One existing through-hole driver, complete shape proof and scoped restoration."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math

from .circular_sketch import circle_profile_parameters
from .combined_guard import CombinedMutationGuard
from .dimensions import close_value
from .documents import rejected
from .jobs import _json
from .mutations import PreparedMutation
from .part_hole import ThroughHole, hole_body_matches
from .sketches import (SketchCatalog, persistent_sketch_members, requested_length,
                      rectangle_extrusion_parameters, same_sketch_geometry)


SCOPE = 'single_base_circular_through_hole_dimension_v1'


def circle_structure(snapshot):
    """Remove only solved circle coordinates/radius; keep every native binding."""
    result = deepcopy(snapshot)
    for point in result['points']:
        point.pop('coordinates_si')
    for circle in result['segments']:
        circle.pop('radius_si')
        circle['circle_parameters_si'] = circle['circle_parameters_si'][3:6]
        for endpoint in circle.get('periodic_endpoints') or ():
            endpoint.pop('coordinates_si')
    return result


class CircularSketchCatalog(SketchCatalog):
    def _read_snapshot(self, model, feature):
        return self.adapter.circular_sketch_snapshot(model, feature)


@dataclass
class HoleCapture:
    circle: object
    base: object
    controls: dict
    parameters: dict
    base_parameters: dict
    expected: dict
    revision: str


class PartHoleEditCatalog:
    def __init__(self, sketches):
        self.sketches, self.dimensions = sketches, sketches.dimensions
        self.adapter = self.dimensions.adapter
        self.circles = CircularSketchCatalog(self.dimensions)

    @staticmethod
    def _expected(parameters, base, base_object_id):
        # IDs/names below are not native lookup keys; this DTO computes shape only.
        definition = ThroughHole(base_object_id, base_object_id,
            parameters['centre_x_m'] * 1000., parameters['centre_y_m'] * 1000.,
            parameters['diameter_m'] * 1000., 'Эскиз отверстия', 'Сквозное отверстие')
        return definition.expected_geometry(base)

    def _capture(self, document_id, configuration, base_object_id, object_id):
        if base_object_id == object_id:
            raise rejected('hole_edit_target_overlap', 'Base and circle must be distinct explicit sketches.')
        circle = self.circles._capture(document_id, configuration, object_id)
        base = self.sketches._capture_from_dimensions(circle.dimensions, document_id, configuration, base_object_id)
        entry, _, records, semantic, _ = circle.dimensions.state
        parameters = circle_profile_parameters(circle.snapshot, semantic, configuration)
        circle_id, base_id = circle.snapshot['feature_native_id'], base.snapshot['feature_native_id']
        own = [row for row in semantic['dimensions'] if row['owner'] and row['owner']['native_id'] == circle_id]
        parents = {row['owner']['owner_native_id'] for row in own}
        cuts = [row for row in semantic['tree']['features'] if row['native_id'] in parents]
        if (len(parents) != 1 or len(cuts) != 1 or cuts[0]['feature_type'] not in ('Cut', 'ICE')
                or len(semantic['dimensions']) != 6):
            raise rejected('unsupported_hole_edit', 'One exact absorbed circle/cut with six independent base/hole drivers is required.')
        filtered = deepcopy(semantic)
        filtered['dimensions'] = [row for row in filtered['dimensions'] if row['owner']['native_id'] != circle_id]
        base_parameters = rectangle_extrusion_parameters(base.snapshot, filtered, configuration)
        base_rows = [row for row in filtered['dimensions'] if row['owner']['native_id'] == base_id]
        base_parent = base_rows[0]['owner']['owner_native_id']
        solids = [row for row in semantic['tree']['features']
                  if row['feature_type'] in ('ProfileFeature', 'Boss', 'Extrusion', 'Cut', 'ICE')]
        if (len(solids) != 4 or {row['native_id'] for row in solids} != {base_id, circle_id, base_parent, cuts[0]['native_id']}
                or any(circle.snapshot[key] != base.snapshot[key]
                       for key in ('reference_plane', 'model_to_sketch', 'model_origin', 'model_origin_point'))):
            raise rejected('unsupported_hole_edit', 'Only one independent base and one own circle on its exact plane are supported.')
        expected = self._expected(parameters, base_parameters, base_object_id)
        if not hole_body_matches(semantic['geometry'], expected):
            raise rejected('hole_edit_shape_mismatch', 'Complete body does not match the explicit base and through-hole constraints.')
        controls = self.adapter.hole_edit_controls(entry.model)
        if controls['sketch_controls']['add_to_db'] or controls['sketch_controls']['dimension_input']:
            raise rejected('unsupported_hole_edit_ui', 'Interactive sketch controls must be disabled.')
        payload = {'scope': SCOPE, 'circle_revision': circle.revision, 'base_revision': base.revision,
                   'controls': controls, 'parameters': parameters, 'base_parameters': base_parameters}
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        self.dimensions._close_native_proof(entry, circle.dimensions.event_sequence)
        return HoleCapture(circle, base, controls, parameters, base_parameters, expected, revision)

    def _paired(self, **arguments):
        first, second = (self._capture(**arguments) for _ in range(2))
        same = (self.dimensions._same_capture(first.circle.dimensions, second.circle.dimensions)
            and first.revision == second.revision
            and first.circle.snapshot == second.circle.snapshot and first.base.snapshot == second.base.snapshot
            and persistent_sketch_members(first.circle.members) == persistent_sketch_members(second.circle.members)
            and persistent_sketch_members(first.base.members) == persistent_sketch_members(second.base.members))
        self.dimensions._close_native_proof(second.circle.dimensions.state[0], second.circle.dimensions.event_sequence)
        if not same:
            raise rejected('hole_edit_changed_during_read', 'Complete base/circle/body/native proof changed across capture.')
        return second

    def _prepare(self, document_id, configuration, base_object_id, object_id, dimension_id, value_mm):
        value = requested_length(value_mm)
        self.dimensions._prevalidate_namespace(document_id, configuration, dimension_id)
        captured = self._paired(document_id=document_id, configuration=configuration,
                                base_object_id=base_object_id, object_id=object_id)
        entry, identity, records, semantic, _ = captured.circle.dimensions.state
        native, ref = self.dimensions._resolve(entry, configuration, identity, records, dimension_id)
        row = self.dimensions._captured_row(records, semantic, native)
        axis = next((axis for axis, name in captured.parameters['axes'].items() if name == row['full_name']), None)
        if axis is None or self.adapter.identity(native.owner) != self.adapter.identity(captured.circle.feature):
            raise rejected('hole_edit_dimension_owner', 'Target must be the exact own X, Y or diameter driver of this circle.')
        wanted = {**captured.parameters, axis + '_m': value}
        wanted['radius_m'] = wanted['diameter_m'] / 2.
        expected = self._expected(wanted, captured.base_parameters, base_object_id)
        payload = {'scope': SCOPE, 'revision': captured.revision, 'dimension_id': dimension_id,
                   'dimension_anchor': ref.persistent_id, 'value_m': value, 'axis': axis}
        public = {'document_id': document_id, 'configuration': configuration, 'base_object_id': base_object_id,
            'object_id': object_id, 'dimension_id': dimension_id, 'axis': axis, 'value_mm': value_mm,
            'revision_scope': SCOPE, 'revision': 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest(),
            'expected_geometry': expected, 'native_change_available': True}
        self.dimensions._close_native_proof(entry, captured.circle.dimensions.event_sequence)
        return public, captured, native, row, wanted, expected

    def prepare_dimension_change(self, **arguments):
        return self._prepare(**arguments)[0]

    def set_dimension(self, operation_id, document_id, configuration, base_object_id, object_id,
                      dimension_id, expected_revision, value_mm):
        requested = requested_length(value_mm)
        if self.dimensions.mutation_guard is None:
            raise rejected('mutation_guard_unavailable', 'An owning-STA mutation guard is required.')
        args = dict(document_id=document_id, configuration=configuration, base_object_id=base_object_id,
                    object_id=object_id, dimension_id=dimension_id, value_mm=value_mm)
        targets = {key: args[key] for key in ('document_id', 'configuration', 'base_object_id', 'object_id')}
        target = {}
        def state(captured):
            return {'semantic': captured.circle.dimensions.state[3], 'circle': captured.circle.snapshot,
                    'base': captured.base.snapshot, 'controls': captured.controls,
                    'parameters': captured.parameters, 'expected': captured.expected}
        def prepare():
            public, captured, native, row, wanted, expected = self._prepare(**args)
            target.update(captured=captured, native=native, wanted=wanted)
            return PreparedMutation(public['revision'], {**state(captured), 'scope': SCOPE,
                'full_name': row['full_name'], 'value_m': row['values_si'][configuration],
                'axis': public['axis'], 'expected_parameters': wanted, 'expected_geometry': expected})
        def validate(prepared):
            public, captured, native, _, _, _ = self._prepare(**args)
            original = target['captured']
            return (public['revision'] == prepared.revision
                and captured.circle.dimensions.state[0] is original.circle.dimensions.state[0]
                and persistent_sketch_members(captured.circle.members) == persistent_sketch_members(original.circle.members)
                and persistent_sketch_members(captured.base.members) == persistent_sketch_members(original.base.members)
                and self.adapter.identity(self.adapter.dimension_object(native)) == self.adapter.identity(self.adapter.dimension_object(target['native'])))
        def apply(prepared):
            entry = target['captured'].circle.dimensions.state[0]
            cache = entry.features['dimensions']
            cache['mutation_sequence'] = cache.get('mutation_sequence', 0) + 1
            status = self.adapter.set_dimension_value(target['native'], requested, configuration)
            if type(status) is not int or status != 0:
                raise rejected('hole_dimension_write_failed', f'Native setter status {status!r} is not 0.')
            if self.adapter.rebuild_dimension_document(entry.model) is not True:
                raise rejected('hole_dimension_rebuild_failed', 'Native rebuild was not confirmed.')
            return {'object_id': object_id, 'dimension_id': dimension_id, 'requested_value_mm': value_mm, 'native_status': status}
        def inspect(prepared):
            captured = self._paired(**targets)
            entry, identity, records, semantic, _ = captured.circle.dimensions.state
            native, _ = self.dimensions._resolve(entry, configuration, identity, records, dimension_id)
            row = self.dimensions._captured_row(records, semantic, native)
            if self.adapter.identity(native.owner) != self.adapter.identity(target['captured'].circle.feature):
                raise rejected('hole_edit_dimension_owner', 'Post-read dimension owner changed.')
            mass = self.adapter.rectangle_body_measurements(entry.model)
            self.dimensions._close_native_proof(entry, captured.circle.dimensions.event_sequence)
            return {**state(captured), 'value_m': row['values_si'][configuration], 'revision': captured.revision,
                    'native_body_measurements': mass}
        def metadata(before, after, *, pending=False):
            old = self.dimensions._comparable(before['semantic'], ignore_geometry=True)
            new = self.dimensions._comparable(after['semantic'], ignore_geometry=True)
            if pending:
                for value in (old, new):
                    value['context'].pop('configuration_needs_rebuild', None)
                    value['tree'].pop('needs_rebuild', None)
            for row in old['dimensions']:
                if row['full_name'] == before['full_name']:
                    row['values_si'][configuration] = after['value_m']
                    row['values'][configuration] = after['value_m'] * 1000.
            return (old == new and before['controls'] == after['controls']
                and same_sketch_geometry(before['base'], after['base'])
                and circle_structure(before['circle']) == circle_structure(after['circle']))
        def shape(after, expected, wanted):
            mass = after['native_body_measurements']
            return (all(close_value(after['parameters'][key], wanted[key])
                        for key in ('centre_x_m', 'centre_y_m', 'diameter_m'))
                and hole_body_matches(after['semantic']['geometry'], expected)
                and all(math.isclose(mass[key], expected[key], rel_tol=1e-10, abs_tol=1e-8)
                        for key in ('volume_mm3', 'surface_area_mm2')))
        def verify(before, after, result):
            return (close_value(after['value_m'], requested) and metadata(before, after)
                    and shape(after, before['expected_geometry'], before['expected_parameters']))
        def restore(before, prepared):
            # Refuse unreadable/unsolved/foreign geometry. Restoration writes are
            # permitted only after a complete capture matches old or wanted shape.
            captured = self._paired(**targets)
            entry, identity, records, semantic, _ = captured.circle.dimensions.state
            native, _ = self.dimensions._resolve(entry, configuration, identity, records, dimension_id)
            row = self.dimensions._captured_row(records, semantic, native)
            current = row['values_si'][configuration]
            after = {**state(captured), 'value_m': current,
                     'native_body_measurements': self.adapter.rectangle_body_measurements(entry.model)}
            if (self.adapter.identity(native.owner) != self.adapter.identity(target['captured'].circle.feature)
                    or not (close_value(current, requested) or close_value(current, before['value_m']))
                    or not metadata(before, after, pending=True)
                    or not (shape(after, before['expected'], before['parameters'])
                            or shape(after, before['expected_geometry'], before['expected_parameters']))):
                raise rejected('hole_edit_concurrent_change', 'Effects are outside the exact old/requested own circle; no restoration write.')
            self.dimensions._close_native_proof(entry, captured.circle.dimensions.event_sequence)
            if not close_value(current, before['value_m']):
                status = self.adapter.set_dimension_value(native, before['value_m'], configuration)
                if type(status) is not int or status != 0:
                    raise rejected('hole_dimension_restore_failed', 'Exact scalar restoration was not acknowledged.')
            if self.adapter.rebuild_dimension_document(entry.model) is not True:
                raise rejected('hole_dimension_restore_failed', 'Restoration rebuild was not confirmed.')
        def verify_restored(before, after):
            return (close_value(after['value_m'], before['value_m']) and metadata(before, after)
                    and shape(after, before['expected'], before['parameters']))
        def guard(prepared):
            model = target['captured'].circle.dimensions.state[0].model
            manager = self.dimensions.mutation_guard(model)
            scope = getattr(self.adapter, 'dimension_selection_scope', None)
            return CombinedMutationGuard(manager, scope(model)) if scope else manager
        return self.dimensions.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
            expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply, inspect=inspect,
            verify=verify, restore=restore, verify_restored=verify_restored, guard=guard)
