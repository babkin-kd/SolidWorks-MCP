"""Independent finite postconditions; never convert an incomplete proof to success."""
from copy import deepcopy

from .jobs import _json
from .rectangle_snapshot import EMPTY, SKETCH, validated_rectangle_snapshot
from .sketches import rectangle_profile_parameters


VOLATILE_TARGET = frozenset(('needs_save', 'update_stamp', 'observation_revision', 'observation_sequence'))


def same_unmodified_session(before, after, target_id):
    if (type(before) is not dict or type(after) is not dict or set(before) != set(after)
            or set(before) != {'semantic', 'snapshots'}):
        return False
    first, last = before['semantic'], after['semantic']
    if type(first) is not dict or type(last) is not dict or set(first) != set(last):
        return False
    if any(_json(first[k]) != _json(last[k]) for k in first if k != 'documents'):
        return False
    a, b = first['documents'], last['documents']
    if type(a) is not list or type(b) is not list or len(a) != len(b):
        return False
    if [r['document_id'] for r in a] != [r['document_id'] for r in b]:
        return False
    if sum(r['document_id'] == target_id for r in a) != 1:
        return False
    for old, new in zip(a, b):
        if old['document_id'] != target_id:
            if _json(old) != _json(new): return False
            continue
        if set(old) != set(new) or not VOLATILE_TARGET <= set(new): return False
        if (new['needs_save'] is not True or type(new['update_stamp']) is not int
                or type(new['observation_sequence']) is not int
                or type(new['observation_revision']) is not str or not new['observation_revision']):
            return False
        if any(_json(old[k]) != _json(new[k]) for k in old if k not in VOLATILE_TARGET):
            return False
    if set(before['snapshots']) != set(after['snapshots']): return False
    return all(_json(snapshot) == _json(after['snapshots'][key])
        for key, snapshot in before['snapshots'].items() if key != target_id)


def _feature_anchors(snapshot):
    rows = snapshot['clone_state']['features']
    result = {}
    for ref in snapshot['references']:
        if ref['kind'] != 'feature': continue
        index = int(ref['role'].removeprefix('feature:'))
        result[rows[index]['native_id']] = ref['token']
    return result


def verified_rectangle_sketch(before, after, target_id, definition, created_native_id):
    """Only one new closed rectangle; all baseline data/anchors/neighbors survive."""
    try:
        if not same_unmodified_session(before, after, target_id): return False
        old = validated_rectangle_snapshot(before['snapshots'][target_id])
        new = validated_rectangle_snapshot(after['snapshots'][target_id])
        a, b = old['clone_state'], new['clone_state']
        if (a['profile'] != EMPTY or b['profile'] != SKETCH
                or new['configuration'] != old['configuration']
                or new['configurations'] != old['configurations']
                or new['selection_count'] != old['selection_count']
                or new['native_observations'] != old['native_observations']
                or type(created_native_id) is not int):
            return False
        old_ids = {r['native_id'] for r in a['features']}
        if created_native_id in old_ids: return False
        baseline = [r for r in b['features'] if r['native_id'] in old_ids]
        added = [r for r in b['features'] if r['native_id'] not in old_ids]
        if (baseline != a['features'] or len(added) != 1
                or added[0]['native_id'] != created_native_id
                or added[0]['feature_type'] != 'ProfileFeature'
                or added[0]['name'] != definition.sketch_name
                or added[0].get('owner_native_id') is not None):
            return False
        old_anchors, new_anchors = _feature_anchors(old), _feature_anchors(new)
        if any(new_anchors.get(key) != token for key, token in old_anchors.items()): return False
        mutable = {'profile', 'features', 'dependencies', 'dimensions', 'sketch', 'parameters', 'annotations', 'origin'}
        for key in a:
            if key not in mutable and _json(a[key]) != _json(b[key]): return False
        origin = deepcopy(b['origin'])
        origin['point_role'] = a['origin']['point_role']
        if origin != a['origin']: return False
        old_point = next(r['token'] for r in old['references'] if r['role'] == 'origin:point')
        new_point = next(r['token'] for r in new['references'] if r['role'] == 'sketch:0/model_origin')
        if old_point != new_point: return False
        params = b['parameters']
        classified = rectangle_profile_parameters(b['sketch'], dict(dimensions=b['dimensions'],
            context=b['controls'], geometry=b['geometry']), new['configuration'], require_editable=False)
        if _json(classified) != _json(params): return False
        if (params['width_m'] != definition.width_mm / 1000.
                or params['height_m'] != definition.height_mm / 1000.
                or b['sketch']['feature_native_id'] != created_native_id):
            return False
        dimensions = b['dimensions']
        if ({d['name'] for d in dimensions} != {'Ширина', 'Высота'}
                or any(d['owner']['native_id'] != created_native_id for d in dimensions)
                or set(params['axes']) != {'width', 'height'}
                or len(set(params['axes'].values())) != 2):
            return False
        roles = {(r['kind'], r['role']) for r in new['references']}
        expected_entities = {('sketch_point', 'sketch:0/' + p['key']) for p in b['sketch']['points']}
        expected_entities.update(('sketch_segment', 'sketch:0/' + s['key']) for s in b['sketch']['segments'])
        expected_entities.update({('dimension', 'dimension:width'), ('dimension', 'dimension:height'),
                                  ('sketch_point', 'sketch:0/model_origin')})
        if not expected_entities <= roles: return False
        return True
    except Exception:
        # This is an admission predicate, never a fallback geometry/result path.
        # Exceptions and invalid finite JSON mean unverified, not success.
        return False
