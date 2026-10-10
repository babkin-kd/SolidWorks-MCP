"""Complete bounded linear planar sketch capture, with no COM imports.

Entity ID pairs are local hints, not persistent/client edit targets. Canonical
owner/membership checks and strong captures prevent identical-looking aliases.
The caller brackets two captures with document/configuration/event revision.
Exact doubles stay hexadecimal; no rounding/partial/box fallback is provided.
"""

import json
import math

from .documents import rejected


SCOPE = 'linear_planar_sketch_geometry_v1'


class SketchEntityBinder:
    """Bind alternate relation interfaces to actual native persistent entities.

    Never trusts a local ID pair or identical coordinates as object identity.
    Each reference must resolve and retain the same canonical current entity.
    """
    def __init__(self, *, wrap, reference, resolve, identity):
        self.wrap, self.reference, self.resolve, self.identity = wrap, reference, resolve, identity
        self.bound = {}

    def __call__(self, raw, name):
        # ISketchLine exposes endpoints/infinite state, not ISketchSegment's
        # GetID/GetSketch/Status. Bind the base interface before the typed view.
        if raw is not None and name == 'ISketchLine':
            return self.wrap(self(raw, 'ISketchSegment'), 'ISketchLine')
        obj = self.wrap(raw, name)
        if obj is None or name not in ('ISketchPoint', 'ISketchSegment'):
            return obj
        pid = self.reference(obj)
        if type(pid) is not bytes or not pid:
            raise rejected('sketch_entity_reference_unavailable', 'Every native sketch point/segment requires a persistent reference.')
        current = self.resolve(pid, name)
        if current is None or self.reference(current) != pid or _identifier(current) != _identifier(obj):
            raise rejected('sketch_entity_reference_mismatch', 'Native sketch entity reference did not resolve to the same current entity.')
        category = 'point' if name == 'ISketchPoint' else 'segment'
        key, token = (category, pid), self.identity(current)
        if key in self.bound and self.bound[key] != token:
            raise rejected('sketch_entity_identity_collision', 'The same reference retargeted to another canonical entity during capture.')
        if self.identity(self.wrap(obj.GetSketch(), 'ISketch')) != self.identity(self.wrap(current.GetSketch(), 'ISketch')):
            raise rejected('sketch_entity_reference_mismatch', 'Relation interface and resolved native entity have different sketch owners.')
        if name == 'ISketchPoint':
            actual = (obj.Type, obj.Status, _coordinates((obj.X, obj.Y, obj.Z), 3))
            expected = (current.Type, current.Status, _coordinates((current.X, current.Y, current.Z), 3))
        else:
            actual = (obj.GetType(), obj.Status, obj.ConstructionGeometry)
            expected = (current.GetType(), current.Status, current.ConstructionGeometry)
        if actual != expected:
            raise rejected('sketch_entity_reference_mismatch', 'Alternate interface disagrees with the full resolved native entity.')
        self.bound[key] = token
        return current


def _integer(value, *, low=0, high=100000):
    if type(value) is not int or not low <= value <= high:
        raise rejected('sketch_capture_invalid', 'Native sketch integer is outside the supported bound.')
    return value


def _array(value, maximum):
    if value is None:
        return ()
    if type(value) not in (list, tuple) or len(value) > maximum or any(item is None for item in value):
        raise rejected('sketch_capture_invalid', 'Complete bounded non-null native sketch arrays are required.')
    return tuple(value)


def _boolean(value):
    if type(value) is not bool:
        raise rejected('sketch_capture_invalid', 'A native sketch Boolean is required.')
    return value


def _coordinates(values, length):
    values = _array(values, length)
    if len(values) != length or any(type(value) not in (int, float) for value in values):
        raise rejected('sketch_capture_invalid', 'Complete finite native sketch coordinates are required.')
    numbers = tuple(float(value) for value in values)
    if any(not math.isfinite(value) or abs(value) > 10000. for value in numbers):
        raise rejected('sketch_capture_invalid', 'Native sketch coordinates exceed the finite analytical scope.')
    return [value.hex() for value in numbers]


def _identifier(raw):
    pair = _array(raw.GetID(), 2)
    if len(pair) != 2:
        raise rejected('sketch_capture_invalid', 'Native entity ID must be an ordered pair.')
    return [_integer(value, high=2**31-1) for value in pair]


class LinearSketchReader:
    def __init__(self, sketch, origin, *, wrap, identity):
        self.sketch, self.origin, self.wrap, self.identity = sketch, origin, wrap, identity
        self.sketch_token, self.origin_token = identity(sketch), identity(origin)
        self.points, self.lines, self.members = {}, {}, {}
        self.members['sketch'] = self.sketch_token
        self.members['model_origin'] = self.origin_token
        self.origin_snapshot = {'native_id': _identifier(origin), 'point_type': _integer(origin.Type, high=1000),
            'constraint_status': _integer(origin.Status, high=10), 'coordinates_si': _coordinates((origin.X, origin.Y, origin.Z), 3)}

    def _point(self, raw, *, allow_implicit=False):
        point = self.wrap(raw, 'ISketchPoint')
        token = self.identity(point)
        if token == self.origin_token:
            return 'model_origin'
        owner = self.wrap(point.GetSketch(), 'ISketch')
        if owner is None or self.identity(owner) != self.sketch_token:
            raise rejected('sketch_external_entity_unsupported', 'Only own points and the exact native model origin are supported.')
        identifier = _identifier(point)
        key = 'point:' + ':'.join(map(str, identifier))
        old = self.points.get(key)
        if old is not None:
            if self.members[key] != token:
                raise rejected('sketch_entity_identity_collision', 'Point ID was reused by another canonical native object.')
            return key
        kind = _integer(point.Type, high=1000)
        if kind not in (0, 10) or (allow_implicit and kind != 10):
            raise rejected('sketch_point_type_unsupported', 'Unenumerated relation points must be native origin projections.')
        if len(self.points) >= 2000:
            raise rejected('sketch_budget_exceeded', 'Complete sketch point budget exceeded.')
        self.points[key] = {'key': key, 'native_id': identifier, 'point_type': kind,
            'constraint_status': _integer(point.Status, high=10), 'implicit': allow_implicit,
            'coordinates_si': _coordinates((point.X, point.Y, point.Z), 3)}
        self.members[key] = token
        return key

    def _entity(self, kind, raw):
        if kind == 2:
            return self._point(raw, allow_implicit=True)
        if kind != 3:
            raise rejected('sketch_relation_entity_unsupported', 'Relation includes an unsupported non-point/non-line entity.')
        segment = self.wrap(raw, 'ISketchSegment')
        identifier = _identifier(segment)
        key = 'line:' + ':'.join(map(str, identifier))
        if key not in self.lines or self.members[key] != self.identity(segment):
            raise rejected('sketch_relation_entity_unsupported', 'Relation line is outside the complete canonical segment capture.')
        return key

    def read(self):
        if _boolean(self.sketch.Is3D()):
            raise rejected('sketch_3d_unsupported', 'The initial complete sketch scope is planar.')
        for method in ('GetSketchBlockInstanceCount', 'GetSketchPictureCount', 'GetSketchSlotCount'):
            if _integer(getattr(self.sketch, method)()) != 0:
                raise rejected('sketch_auxiliary_geometry_unsupported', 'Blocks, pictures and slots require their own complete capture.')
        if _array(self.sketch.GetSketchHatches(), 2000) or _array(self.sketch.GetSketchTextSegments(), 2000):
            raise rejected('sketch_auxiliary_geometry_unsupported', 'Hatches/text are outside the complete linear scope.')
        points = _array(self.sketch.GetSketchPoints2(), 2000)
        count = _integer(self.sketch.GetSketchPointsCount2(), high=2000)
        if count != len(points):
            raise rejected('sketch_capture_changed', 'Sketch point count disagrees with the complete enumeration.')
        for raw in points:
            key = self._point(raw)
            if key == 'model_origin' or self.points[key]['point_type'] != 0:
                raise rejected('sketch_point_type_unsupported', 'The enumerated user-point scope supports regular sketch points.')
        if len(self.points) != count:
            raise rejected('sketch_entity_identity_collision', 'Repeated native user point in the complete array.')
        for raw in _array(self.sketch.GetSketchSegments(), 2000):
            segment = self.wrap(raw, 'ISketchSegment')
            if _integer(segment.GetType(), high=1000) != 0:
                raise rejected('sketch_curve_unsupported', 'Complete arc/spline/conic capture is not implemented; no partial linear result.')
            owner = self.wrap(segment.GetSketch(), 'ISketch')
            if owner is None or self.identity(owner) != self.sketch_token:
                raise rejected('sketch_external_entity_unsupported', 'A segment belongs to another sketch.')
            line = self.wrap(segment, 'ISketchLine')
            identifier = _identifier(segment)
            key = 'line:' + ':'.join(map(str, identifier))
            if key in self.lines:
                raise rejected('sketch_entity_identity_collision', 'Repeated/colliding native line in the complete array.')
            start, end = self._point(line.GetStartPoint2()), self._point(line.GetEndPoint2())
            if start == end or 'model_origin' in (start, end):
                raise rejected('sketch_capture_invalid', 'Finite native lines need distinct own endpoints.')
            self.lines[key] = {'key': key, 'native_id': identifier, 'kind': 'line',
                'construction': _boolean(segment.ConstructionGeometry), 'infinite': _boolean(line.Infinite),
                'constraint_status': _integer(segment.Status, high=10), 'start': start, 'end': end}
            self.members[key] = self.identity(segment)
        if len(self.points) != count:
            raise rejected('sketch_capture_invalid', 'A line endpoint was missing from the complete user-point array.')
        manager = self.wrap(self.sketch.RelationManager, 'ISketchRelationManager')
        relation_count = _integer(manager.GetRelationsCount(0), high=5000)
        relations = _array(manager.GetRelations(0), 5000)
        if len(relations) != relation_count:
            raise rejected('sketch_capture_changed', 'Relation count disagrees with the complete all-relations array.')
        rows = []
        relation_tokens = []
        for raw in relations:
            relation = self.wrap(raw, 'ISketchRelation')
            relation_token = self.identity(relation)
            if any(relation_token == token for token in relation_tokens):
                raise rejected('sketch_entity_identity_collision', 'Repeated canonical relation in the complete native array.')
            relation_tokens.append(relation_token)
            kinds = _array(relation.GetEntitiesType(), 32)
            entities = _array(relation.GetEntities(), 32)
            definitions = _array(relation.GetDefinitionEntities2(), 32)
            count = _integer(relation.GetEntitiesCount(), high=32)
            if len(kinds) != count or len(entities) != count or len(definitions) != count:
                raise rejected('sketch_capture_invalid', 'Relation entities/types/definitions are incomplete.')
            keys = [self._entity(_integer(kind, high=1000), raw) for kind, raw in zip(kinds, entities)]
            definitions = [self._entity(kind, raw) for kind, raw in zip(kinds, definitions)]
            row = {'type': _integer(relation.GetRelationType(), high=4096),
                   'suppressed': _boolean(relation.Suppressed), 'entities': keys, 'definitions': definitions,
                   'dimension_full_name': None, 'display_type': None}
            display = self.wrap(relation.GetDisplayDimension(), 'IDisplayDimension')
            if display is not None:
                dimension = self.wrap(display.GetDimension2(0), 'IDimension')
                if dimension is None:
                    raise rejected('sketch_capture_invalid', 'Sketch dimension relation returned no exact dimension.')
                row['dimension_full_name'] = str(dimension.FullName)
                # GetType collapses horizontal/vertical dimensions to generic
                # linear (2). Type2 preserves their actual 11/12 semantics.
                row['display_type'] = _integer(display.Type2, high=1000)
                dimension_key = 'dimension:' + row['dimension_full_name']
                token = self.identity(dimension)
                if dimension_key in self.members and self.members[dimension_key] != token:
                    raise rejected('sketch_entity_identity_collision', 'Relation dimension name aliases another native object.')
                self.members[dimension_key] = token
            rows.append((json.dumps(row, sort_keys=True, separators=(',', ':')), row, relation_token))
        if _integer(manager.GetRelationsCount(0), high=5000) != relation_count:
            raise rejected('sketch_capture_changed', 'Sketch relation count changed while reading.')
        for index, (_, _, token) in enumerate(sorted(rows, key=lambda item: item[0])):
            self.members['relation:' + str(index)] = token
        if _integer(self.sketch.GetSketchPointsCount2(), high=2000) != len(points):
            raise rejected('sketch_capture_changed', 'Sketch user-point count changed while reading.')
        return {'scope': SCOPE, 'is_3d': False, 'constraint_status': _integer(self.sketch.GetConstrainedStatus(), high=10),
                'model_origin_point': self.origin_snapshot,
                'points': [self.points[key] for key in sorted(self.points)],
                'segments': [self.lines[key] for key in sorted(self.lines)],
                'relations': [item[1] for item in sorted(rows, key=lambda item: item[0])]}, tuple(sorted(self.members.items()))
