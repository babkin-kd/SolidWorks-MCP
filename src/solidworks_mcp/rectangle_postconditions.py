"""Independent finite postconditions; never convert an incomplete proof to success."""
from copy import deepcopy
import math

from .jobs import _json
from .rectangle_snapshot import EMPTY, SKETCH, validated_rectangle_snapshot
from .sketches import rectangle_profile_parameters
from .rectangle_inventory import feature_relations as _relations, empty_feature_external_inventory


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


def _new_sketch_inventories(a,b,created_id):
    first,last=_relations(a),_relations(b)
    sketch=b['sketch']
    plane=sketch['reference_plane']['native_id']
    origin=sketch['model_origin']['feature_native_id']
    allowed={(plane,created_id),(origin,created_id)}
    extra=last['parent_links']-first['parent_links']
    if not {(plane,created_id)}<=extra<=allowed:return False
    if (last['parent_links']!=first['parent_links']|extra
            or last['child_links']!=first['child_links']|extra
            or any(last[k]!=first[k] for k in ('absorbed_links',
                'parent_links_without_child_confirmation','child_links_without_parent_confirmation'))):return False
    old,new=a['feature_external_reference_inventory'],b['feature_external_reference_inventory']
    empty_feature_external_inventory(a)
    empty_feature_external_inventory(b)
    return [r for r in new['features'] if r['native_id']!=created_id]==old['features']


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
        mutable = {'profile', 'features', 'dependencies', 'dimensions', 'sketch', 'parameters', 'annotations',
                   'origin','feature_external_reference_inventory'}
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
        if not _new_sketch_inventories(a,b,created_native_id):return False
        if a['annotations']!=[] or len(b['annotations'])!=2:return False
        annotations=set()
        for row in b['annotations']:
            if (type(row) is not dict or set(row)!={'role','type','visible','position','display_type','text',
                    'use_document_format','text_format'} or type(row['role']) is not str
                    or row['role'] in annotations or any(type(row[k]) is not int for k in ('type','visible','display_type'))
                    or type(row['text']) is not str or type(row['use_document_format']) is not bool
                    or type(row['position']) is not list or len(row['position'])!=3
                    or any(type(v) is not str for v in row['position'])
                    or type(row['text_format']) is not list or not row['text_format']
                    or any(type(v) not in (str,int,float,bool) for v in row['text_format'])):return False
            if any(not math.isfinite(float.fromhex(v)) for v in row['position']):return False
            annotations.add(row['role'])
        baseline_roles={(r['kind'],r['role']) for r in old['references'] if r['role']!='origin:point'}
        # Existing feature roles can move only with their exact preserved native ID.
        feature_roles={('feature',f'feature:{i}') for i,r in enumerate(b['features']) if r['native_id'] in old_anchors}
        baseline_roles={r for r in baseline_roles if r[0]!='feature'}|feature_roles
        expected_roles=baseline_roles|expected_entities|{('feature',f'feature:{b["features"].index(added[0])}')}
        expected_roles|={('annotation',role) for role in annotations}
        return roles==expected_roles
    except Exception:
        # This is an admission predicate, never a fallback geometry/result path.
        # Exceptions and invalid finite JSON mean unverified, not success.
        return False
