"""Explicit full linear sketch reads and scoped rectangle dimension changes."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math

from .combined_guard import CombinedMutationGuard
from .dimensions import DimensionCatalog, close_value
from .documents import rejected
from .jobs import _json
from .mutations import PreparedMutation
from .part_creation import _positive_length, validated_plane_transform


READ_SCOPE = 'part_linear_sketch_read_v1'
CHANGE_SCOPE = 'part_rectangular_sketch_dimension_v1'


def requested_length(value_mm):
    value = _positive_length(value_mm, 'value_mm') / 1000.
    if value > 10000.:
        raise rejected('sketch_parameter_out_of_range', 'Requested length exceeds the complete native capture bound of 10000 metres.')
    return value


def sketch_structure(snapshot):
    result = deepcopy(snapshot)
    for point in result['points']:
        point.pop('coordinates_si')
    return result


def same_sketch_geometry(first, second):
    if sketch_structure(first) != sketch_structure(second):
        return False
    current = {point['key']:point['coordinates_si'] for point in second['points']}
    return all(all(abs(float.fromhex(a)-float.fromhex(b)) <= 1e-12 for a,b in zip(point['coordinates_si'],current[point['key']]))
               for point in first['points'])


def persistent_sketch_members(members):
    # ISketchRelation has no persistent reference and GetRelations returns fresh
    # relation wrappers every time. Retain them in the capture, but compare
    # their complete semantics and resolved entity memberships, not addresses.
    return tuple((key,value) for key,value in members if not key.startswith('relation:'))


def rectangle_parameters(snapshot, semantic, configuration):
    """Classify native structure/axis relations, never dimension display names."""
    fail = lambda message: rejected('unsupported_rectangular_sketch', message)
    if snapshot['constraint_status'] != 3 or snapshot['is_3d']:
        raise fail('Dimension changes require a fully defined planar rectangle.')
    origin = snapshot['model_origin_point']
    if origin['point_type'] != 1 or origin['constraint_status'] != 2 or any(abs(float.fromhex(v)) > 1e-12 for v in origin['coordinates_si']):
        raise fail('The exact fully constrained model origin point must be captured at the model origin.')
    points = {point['key']: point for point in snapshot['points']}
    regular = {key: point for key, point in points.items() if not point['implicit']}
    implicit = {key: point for key, point in points.items() if point['implicit']}
    if len(regular) != 4 or len(implicit) != 1 or any(point['constraint_status'] != 2 for point in points.values()):
        raise fail('The rectangle needs four fully defined user corners and one origin projection.')
    coordinates = {key: tuple(float.fromhex(value) for value in point['coordinates_si']) for key, point in points.items()}
    projected = next(iter(implicit))
    if implicit[projected]['point_type'] != 10 or any(abs(v) > 1e-12 for v in coordinates[projected]):
        raise fail('The exact native projected model origin is required.')
    width = max(coordinates[key][0] for key in regular)
    height = max(coordinates[key][1] for key in regular)
    if width < 1e-6 or height < 1e-6:
        raise fail('The initial rectangle branch has positive widths/heights at least one micrometre.')
    corners = ((0., 0., 0.), (width, 0., 0.), (width, height, 0.), (0., height, 0.))
    corner_by_key = {}
    for key in regular:
        matches = [index for index, corner in enumerate(corners) if all(abs(a-b) <= 1e-12 for a, b in zip(coordinates[key], corner))]
        if len(matches) != 1:
            raise fail('All four exact supported rectangular corners must be present.')
        corner_by_key[key] = matches[0]
    if set(corner_by_key.values()) != {0, 1, 2, 3}:
        raise fail('Rectangle corner identities are not unique.')
    lines = {line['key']: line for line in snapshot['segments']}
    expected_edges = {frozenset((i, (i+1)%4)) for i in range(4)}
    edges, horizontal, vertical = set(), set(), set()
    for key, line in lines.items():
        if line['construction'] or line['infinite'] or line['constraint_status'] != 2:
            raise fail('Only finite fully defined nonconstruction rectangle edges can be changed.')
        a, b = line['start'], line['end']
        if a not in regular or b not in regular:
            raise fail('Every edge endpoint must be an enumerated rectangle corner.')
        edges.add(frozenset((corner_by_key[a], corner_by_key[b])))
        (horizontal if abs(coordinates[a][1] - coordinates[b][1]) <= 1e-12 else vertical).add(key)
    if len(lines) != 4 or edges != expected_edges:
        raise fail('Four native lines must form exactly one rectangular perimeter.')
    dimension_rows = [row for row in semantic['dimensions'] if row['owner'] and row['owner']['native_id'] == snapshot['feature_native_id']]
    if len(dimension_rows) != 2:
        raise fail('Two independent driving sketch dimensions are required.')
    rows = {row['full_name']: row for row in dimension_rows}
    axes, horizontal_relations, vertical_relations, coincident = {}, set(), set(), 0
    for relation in snapshot['relations']:
        if relation['suppressed']:
            raise fail('Suppressed sketch relations are outside this constraint contract.')
        kind, entities, definitions = relation['type'], relation['entities'], relation['definitions']
        if kind in (4, 5):
            allowed = horizontal if kind == 4 else vertical
            if len(entities) != 1 or entities != definitions or entities[0] not in allowed or relation['dimension_full_name'] is not None:
                raise fail('Horizontal/vertical constraints must bind the correct native perimeter lines.')
            (horizontal_relations if kind == 4 else vertical_relations).add(entities[0])
        elif kind == 9:
            origin_key = next(key for key, corner in corner_by_key.items() if corner == 0)
            if (set(entities) != {projected, origin_key} or set(definitions) != {'model_origin', origin_key}
                    or len(entities) != 2 or len(definitions) != 2 or relation['dimension_full_name'] is not None):
                raise fail('Coincidence must bind the corner/projection to the exact model origin definition.')
            coincident += 1
        elif kind == 1:
            axis = {11: 'width', 12: 'height'}.get(relation['display_type'])
            name = relation['dimension_full_name']
            own = [key for key in definitions if key in regular]
            if (axis is None or axis in axes or name not in rows or len(entities) != 2 or len(definitions) != 2
                    or len(own) != 1 or set(entities) != {projected, own[0]} or set(definitions) != {'model_origin', own[0]}):
                raise fail('Dimension orientation and actual own-point/model-origin definitions must be explicit.')
            index, size = (0, width) if axis == 'width' else (1, height)
            if not close_value(rows[name]['values_si'][configuration], size) or abs(coordinates[own[0]][index] - size) > 1e-12:
                raise fail('Driving dimension disagrees with the native sketch extent.')
            axes[axis] = name
        else:
            raise fail('This initial rectangle contract supports only its seven defining relations.')
    if len(snapshot['relations']) != 7 or horizontal_relations != horizontal or vertical_relations != vertical or coincident != 1 or set(axes) != {'width', 'height'}:
        raise fail('The complete rectangle constraint network is not the supported independent seven-relation network.')
    for row in dimension_rows:
        checked = deepcopy(row)
        checked['write_blockers'] = [item for item in checked['write_blockers'] if item != 'sketch_geometry_snapshot_not_implemented']
        DimensionCatalog._writable(semantic, checked, 'mm')
    other = [row for row in semantic['dimensions'] if row not in dimension_rows]
    parent = dimension_rows[0]['owner']['owner_native_id']
    if (len(other) != 1 or parent is None or other[0]['owner'] is None or other[0]['owner']['native_id'] != parent
            or other[0]['owner']['feature_type'] not in ('Boss', 'Extrusion') or other[0]['unit'] != 'mm'):
        raise fail('Initial scope supports one independent blind rectangular base extrusion.')
    DimensionCatalog._writable(semantic, other[0], 'mm')
    depth = other[0]['values_si'][configuration]
    if depth < 1e-6:
        raise fail('The base extrusion thickness is outside the supported positive branch.')
    frame = validated_plane_transform([float.fromhex(value) for value in snapshot['reference_plane']['transform']])
    local = validated_plane_transform([float.fromhex(value) for value in snapshot['model_to_sketch']])
    if any(abs(local[i*3+j]-frame[j*3+i]) > 1e-12 for i in range(3) for j in range(3)):
        raise fail('Model-to-sketch and exact plane transforms do not form the same rigid frame.')
    result = {'width_m': width, 'height_m': height, 'depth_m': depth, 'axes': axes, 'plane_transform': list(frame)}
    if not rectangular_body_matches(semantic['geometry'], result):
        raise fail('Complete body boundary does not match this single positive blind base.')
    return result


def rectangular_body_matches(geometry, parameters):
    bodies = geometry.get('bodies', [])
    if len(bodies) != 1:
        return False
    body = bodies[0]
    if len(body['vertices']) != 8 or len(body['edges']) != 12 or len(body['faces']) != 6:
        return False
    w, h, d, frame = (parameters[key] for key in ('width_m', 'height_m', 'depth_m', 'plane_transform'))
    expected = [tuple(x*frame[i] + y*frame[3+i] + z*frame[6+i] + frame[9+i] for i in range(3))
                for x in (0., w) for y in (0., h) for z in (0., d)]
    actual = [tuple(float.fromhex(value) for value in point) for point in body['vertices']]
    for point in expected:
        index = next((index for index, candidate in enumerate(actual) if all(abs(a-b) <= 1e-9 for a, b in zip(point, candidate))), None)
        if index is None:
            return False
        actual.pop(index)
    return not actual


@dataclass
class SketchCapture:
    dimensions: object
    feature: object
    snapshot: dict
    members: tuple
    revision: str


class SketchCatalog:
    def __init__(self, dimensions):
        self.dimensions, self.adapter, self.documents = dimensions, dimensions.adapter, dimensions.documents

    def _capture(self, document_id, configuration, object_id):
        captured = self.dimensions._capture(document_id, configuration)
        entry, identity, records, semantic, dimension_revision = captured.state
        objects = self.adapter.features(entry.model)
        if tuple(self.adapter.identity(item) for item in objects) != captured.feature_identities:
            raise rejected('document_changed_during_read', 'Sketch feature identities changed after the complete dimension capture.')
        feature, ref = self.dimensions.features._resolve(entry, configuration, identity, objects, object_id)
        snapshot, members = self.adapter.sketch_snapshot(entry.model, feature)
        for relation in snapshot['relations']:
            if relation['dimension_full_name'] is not None:
                matches = [record for record, row in zip(records, semantic['dimensions']) if row['full_name'] == relation['dimension_full_name']]
                token = dict(members).get('dimension:' + relation['dimension_full_name'])
                if (len(matches) != 1 or token != self.adapter.identity(self.adapter.dimension_object(matches[0]))
                        or self.adapter.identity(matches[0].owner) != self.adapter.identity(feature)):
                    raise rejected('sketch_dimension_identity_mismatch', 'Relation dimension is not the exact captured own driving dimension.')
        payload = {'scope': READ_SCOPE, 'document_id': document_id, 'configuration': configuration,
            'object_id': object_id, 'feature_pid_hex': ref.persistent_id.hex(), 'dimension_revision': dimension_revision, 'sketch': snapshot}
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        self.dimensions._close_native_proof(entry, captured.event_sequence)
        return SketchCapture(captured, feature, snapshot, members, revision)

    def _paired(self, document_id, configuration, object_id):
        first, second = (self._capture(document_id, configuration, object_id) for _ in range(2))
        same = (self.dimensions._same_capture(first.dimensions, second.dimensions) and first.revision == second.revision
                and first.snapshot == second.snapshot
                and persistent_sketch_members(first.members) == persistent_sketch_members(second.members))
        self.dimensions._close_native_proof(second.dimensions.state[0], second.dimensions.event_sequence)
        if not same:
            raise rejected('sketch_changed_during_read', 'Sketch/control/native identity changed during paired capture.')
        return first

    def get(self, document_id, configuration, object_id):
        captured = self._paired(document_id, configuration, object_id)
        return {'document_id': document_id, 'configuration': configuration, 'object_id': object_id,
                'revision_scope': READ_SCOPE, 'revision': captured.revision, 'sketch': captured.snapshot}

    def _prepare(self, document_id, configuration, object_id, dimension_id, value_mm):
        value = requested_length(value_mm)
        self.dimensions._prevalidate_namespace(document_id, configuration, dimension_id)
        captured = self._paired(document_id, configuration, object_id)
        entry, identity, records, semantic, _ = captured.dimensions.state
        native, ref = self.dimensions._resolve(entry, configuration, identity, records, dimension_id)
        if getattr(native, 'owner', None) is None or self.adapter.identity(native.owner) != self.adapter.identity(captured.feature):
            raise rejected('sketch_dimension_owner_mismatch', 'Explicit dimension does not belong to the exact requested sketch.')
        row = self.dimensions._captured_row(records, semantic, native)
        parameters = rectangle_parameters(captured.snapshot, semantic, configuration)
        axis = next((axis for axis, name in parameters['axes'].items() if name == row['full_name']), None)
        if axis is None:
            raise rejected('sketch_dimension_axis_unsupported', 'The target must be the actual horizontal or vertical driving dimension.')
        expected = {**parameters, axis + '_m': value}
        volume = expected['width_m'] * expected['height_m'] * expected['depth_m']
        area = 2.*math.fsum((expected['width_m']*expected['height_m'], expected['width_m']*expected['depth_m'], expected['height_m']*expected['depth_m']))
        if not math.isfinite(volume) or not math.isfinite(area):
            raise rejected('sketch_parameter_overflow', 'Requested analytical rectangle properties are not representable.')
        payload = {'scope': CHANGE_SCOPE, 'sketch_revision': captured.revision, 'dimension_id': dimension_id,
                   'dimension_anchor': ref.persistent_id, 'value_m': value, 'axis': axis}
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        self.dimensions._close_native_proof(entry, captured.dimensions.event_sequence)
        public = {'document_id': document_id, 'configuration': configuration, 'object_id': object_id, 'dimension_id': dimension_id,
            'revision_scope': CHANGE_SCOPE, 'revision': revision, 'value_mm': value_mm, 'axis': axis,
            'expected_volume_mm3': volume*1e9, 'expected_surface_area_mm2': area*1e6, 'native_change_available': True}
        return public, captured, native, row, expected

    def prepare_dimension_change(self, document_id, configuration, object_id, dimension_id, value_mm):
        return self._prepare(document_id, configuration, object_id, dimension_id, value_mm)[0]

    def set_dimension(self, operation_id, document_id, configuration, object_id, dimension_id, expected_revision, value_mm):
        requested = requested_length(value_mm)
        if self.dimensions.mutation_guard is None:
            raise rejected('mutation_guard_unavailable', 'An owning-STA mutation guard is required before sketch changes.')
        target = {}
        def prepare():
            public, captured, native, row, expected = self._prepare(document_id, configuration, object_id, dimension_id, value_mm)
            target.update(captured=captured, native=native, expected=expected, row=row)
            return PreparedMutation(public['revision'], {'scope': CHANGE_SCOPE, 'object_id': object_id,
                'dimension_id': dimension_id, 'full_name': row['full_name'], 'axis': public['axis'],
                'value_m': row['values_si'][configuration], 'semantic': captured.dimensions.state[3],
                'sketch': captured.snapshot, 'expected_parameters': expected,
                'expected_volume_mm3': public['expected_volume_mm3'], 'expected_surface_area_mm2': public['expected_surface_area_mm2']})
        def validate(prepared):
            public, captured, native, _, _ = self._prepare(document_id, configuration, object_id, dimension_id, value_mm)
            original = target['captured']
            same = (public['revision'] == prepared.revision and captured.dimensions.state[0] is original.dimensions.state[0]
                and self.adapter.identity(captured.feature) == self.adapter.identity(original.feature)
                and self.adapter.identity(self.adapter.dimension_object(native)) == self.adapter.identity(self.adapter.dimension_object(target['native'])))
            self.dimensions._close_native_proof(captured.dimensions.state[0], captured.dimensions.event_sequence)
            return same
        def apply(prepared):
            entry = target['captured'].dimensions.state[0]
            cache = entry.features['dimensions']
            cache['mutation_sequence'] = cache.get('mutation_sequence', 0) + 1
            status = self.adapter.set_dimension_value(target['native'], requested, configuration)
            if type(status) is not int or status != 0:
                raise rejected('sketch_dimension_write_failed', f'Native dimension setter returned {status!r}; only status 0 is accepted.')
            if self.adapter.rebuild_dimension_document(entry.model) is not True:
                raise rejected('sketch_dimension_rebuild_failed', 'Native rebuild and its cleared pending flag were not confirmed.')
            return {'object_id': object_id, 'dimension_id': dimension_id, 'requested_value_mm': value_mm, 'native_status': status}
        def inspect(prepared):
            captured = self._paired(document_id, configuration, object_id)
            entry, identity, records, semantic, _ = captured.dimensions.state
            native, _ = self.dimensions._resolve(entry, configuration, identity, records, dimension_id)
            row = self.dimensions._captured_row(records, semantic, native)
            if self.adapter.identity(native.owner) != self.adapter.identity(captured.feature):
                raise rejected('sketch_dimension_owner_mismatch', 'Post-read dimension owner changed.')
            measurements = self.adapter.rectangle_body_measurements(entry.model)
            self.dimensions._close_native_proof(entry, captured.dimensions.event_sequence)
            return {'semantic': semantic, 'sketch': captured.snapshot, 'value_m': row['values_si'][configuration],
                    'revision': captured.revision, 'native_body_measurements': measurements}
        def metadata(before, after):
            expected = self.dimensions._comparable(before['semantic'], ignore_geometry=True)
            actual = self.dimensions._comparable(after['semantic'], ignore_geometry=True)
            for row in expected['dimensions']:
                if row['full_name'] == before['full_name']:
                    row['values_si'][configuration] = after['value_m']
                    row['values'][configuration] = after['value_m'] * 1000.
            return expected == actual
        def verify(before, after, result):
            parameters = rectangle_parameters(after['sketch'], after['semantic'], configuration)
            expected = before['expected_parameters']
            mass = after['native_body_measurements']
            return (close_value(after['value_m'], requested) and metadata(before, after)
                and sketch_structure(before['sketch']) == sketch_structure(after['sketch'])
                and all(close_value(parameters[key], expected[key]) for key in ('width_m', 'height_m', 'depth_m'))
                and rectangular_body_matches(after['semantic']['geometry'], expected)
                and math.isclose(mass['volume_mm3'], before['expected_volume_mm3'], rel_tol=1e-7, abs_tol=1e-8)
                and math.isclose(mass['surface_area_mm2'], before['expected_surface_area_mm2'], rel_tol=1e-7, abs_tol=1e-8))
        def restore(before, prepared):
            captured = self._paired(document_id, configuration, object_id)
            entry, identity, records, semantic, _ = captured.dimensions.state
            native, _ = self.dimensions._resolve(entry, configuration, identity, records, dimension_id)
            row = self.dimensions._captured_row(records, semantic, native)
            current = row['values_si'][configuration]
            if not (close_value(current, requested) or close_value(current, before['value_m'])):
                raise rejected('sketch_concurrent_change', 'Target value has an unrelated change; it must not be overwritten.')
            current_semantic, old_semantic = deepcopy(semantic), deepcopy(before['semantic'])
            for value in (current_semantic, old_semantic):
                value['context'].pop('configuration_needs_rebuild', None)
                value['tree'].pop('needs_rebuild', None)
            current_semantic = self.dimensions._comparable(current_semantic, ignore_geometry=True)
            old_semantic = self.dimensions._comparable(old_semantic, ignore_geometry=True)
            for item in current_semantic['dimensions']:
                if item['full_name'] == before['full_name']:
                    item['values_si'][configuration] = before['value_m']
                    item['values'][configuration] = before['value_m'] * 1000.
            if (current_semantic != old_semantic or sketch_structure(captured.snapshot) != sketch_structure(before['sketch'])
                    or self.adapter.identity(native.owner) != self.adapter.identity(captured.feature)):
                raise rejected('sketch_concurrent_change', 'Sketch constraints, other dimensions or controls changed; no restoration write.')
            # A setter may fail before solving or after solving. Only the exact
            # original shape or the explicitly requested single-axis shape is
            # attributable to our write; never overwrite another geometric edit.
            expected_sketch = deepcopy(before['sketch'])
            coordinate = 0 if before['axis'] == 'width' else 1
            original_size = before['value_m']
            for point in expected_sketch['points']:
                values = [float.fromhex(v) for v in point['coordinates_si']]
                if not point['implicit'] and close_value(values[coordinate], original_size):
                    values[coordinate] = requested
                point['coordinates_si'] = [v.hex() for v in values]
            current_points = {point['key']: point['coordinates_si'] for point in captured.snapshot['points']}
            requested_points = {point['key']: point['coordinates_si'] for point in expected_sketch['points']}
            requested_coordinates_match = all(all(abs(float.fromhex(a)-float.fromhex(b)) <= 1e-12
                for a, b in zip(current_points[key], values)) for key, values in requested_points.items())
            if captured.snapshot != before['sketch'] and not requested_coordinates_match:
                raise rejected('sketch_concurrent_geometry', 'Point geometry is neither the exact old nor requested rectangle; no restoration write.')
            if (semantic['geometry'] != before['semantic']['geometry']
                    and not rectangular_body_matches(semantic['geometry'], before['expected_parameters'])):
                raise rejected('sketch_concurrent_geometry', 'Body geometry is outside the old/requested shape; no restoration write.')
            self.dimensions._close_native_proof(entry, captured.dimensions.event_sequence)
            if not close_value(current, before['value_m']):
                status = self.adapter.set_dimension_value(native, before['value_m'], configuration)
                if type(status) is not int or status != 0:
                    raise rejected('sketch_dimension_restore_failed', 'Restoring the exact target value was not acknowledged.')
            if self.adapter.rebuild_dimension_document(entry.model) is not True:
                raise rejected('sketch_dimension_restore_failed', 'Restoration rebuild was not confirmed.')
        def verify_restored(before, after):
            # A native solver can return the original rectangle with a few ULP
            # differences in corner/face doubles. Keep all structural/control
            # data exact and prove the complete bounded shape and native measures.
            old = self.dimensions._comparable(before['semantic'], ignore_geometry=True)
            current = self.dimensions._comparable(after['semantic'], ignore_geometry=True)
            for row in current['dimensions']:
                if row['full_name'] == before['full_name'] and close_value(row['values_si'][configuration], before['value_m']):
                    row['values_si'][configuration] = before['value_m']
                    row['values'][configuration] = before['value_m']*1000.
            original = rectangle_parameters(before['sketch'], before['semantic'], configuration)
            restored = rectangle_parameters(after['sketch'], after['semantic'], configuration)
            mass = after['native_body_measurements']
            w,h,d = (original[key] for key in ('width_m','height_m','depth_m'))
            return (close_value(after['value_m'], before['value_m']) and old == current
                and same_sketch_geometry(before['sketch'], after['sketch'])
                and all(close_value(original[key],restored[key]) for key in ('width_m','height_m','depth_m'))
                and rectangular_body_matches(after['semantic']['geometry'], original)
                and math.isclose(mass['volume_mm3'],w*h*d*1e9,rel_tol=1e-10,abs_tol=1e-8)
                and math.isclose(mass['surface_area_mm2'],2*(w*h+w*d+h*d)*1e6,rel_tol=1e-10,abs_tol=1e-8))
        def guard(prepared):
            model = target['captured'].dimensions.state[0].model
            manager = self.dimensions.mutation_guard(model)
            scope = getattr(self.adapter, 'dimension_selection_scope', None)
            return CombinedMutationGuard(manager, scope(model)) if scope is not None else manager
        return self.dimensions.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
            expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply, inspect=inspect,
            verify=verify, restore=restore, verify_restored=verify_restored, guard=guard)
