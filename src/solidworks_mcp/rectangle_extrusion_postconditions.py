"""Independent finite sketch-to-base admission; detached evidence only, no CAD."""
from copy import deepcopy
from itertools import combinations, product
import math

from .cad_planar_brep import _line_consistent, _plane_consistent, _points_consistent
from .jobs import _json
from .rectangle_construction import BlindRectangleExtrusion
from .rectangle_postconditions import same_unmodified_session
from .rectangle_snapshot import BASE, SKETCH, validated_rectangle_snapshot
from .sketches import rectangle_parameters, rectangle_profile_parameters
from .rectangle_annotation_views import verified_new_dimension_view


def _refs(snapshot):
    return {(r['kind'], r['role']): r['token'] for r in snapshot['references']}


def _features(data):
    rows = data['features']
    if type(rows) is not list or not 5 <= len(rows) <= 64:
        raise ValueError('Incomplete feature tree')
    ids = [r['native_id'] for r in rows]
    if (any(type(i) is not int for i in ids) or len(set(ids)) != len(ids)
            or any(r['suppressed'] is not False or type(r['error_code']) is not int
                   or r['error_code'] != 0 for r in rows)):
        raise ValueError('Invalid feature incarnations')
    return {r['native_id']: (i, r) for i, r in enumerate(rows)}


def _restore_qualifications(snapshot):
    """Undo only the documented role normalization, retaining every other field."""
    data = deepcopy(snapshot['clone_state'])
    evidence = snapshot['native_observations']['qualified_dimensions']
    names = {r['role']: r['full_name'] for r in evidence}
    if set(names) != {'dimension:width', 'dimension:height', 'dimension:depth'}:
        raise ValueError('Incomplete qualified dimensions')

    def restore(value):
        if type(value) is not dict or set(value) != {'reference_role'}:
            raise ValueError('Expected an exact bound dimension role')
        return names[value['reference_role']]

    for row in data['dimensions']:
        if 'owner_update_stamp' in row:
            raise ValueError('Base clone must use its documented stamp exclusion')
        row['full_name'] = restore(row['full_name'])
    for row in data['sketch']['relations']:
        if row['dimension_full_name'] is not None:
            row['dimension_full_name'] = restore(row['dimension_full_name'])
    data['parameters']['axes'] = {axis: restore(value) for axis, value in data['parameters']['axes'].items()}
    return data


def _dependency_delta(old, new, old_features, new_features, sketch_id, created_id, plane_id, origin_id):
    keys = {'scope', 'feature_count', 'parent_links', 'child_links', 'absorbed_links',
            'parent_links_without_child_confirmation', 'child_links_without_parent_confirmation', 'relations_read'}

    def read(value, features):
        if (type(value) is not dict or set(value) != keys
                or value['scope'] != 'native_feature_relation_capture_v1'
                or value['feature_count'] != len(features) or type(value['feature_count']) is not int):
            raise ValueError('Incomplete native dependency inventory')
        ids = {index: native for native, (index, _) in features.items()}
        result = {}
        for key in keys - {'scope', 'feature_count', 'relations_read'}:
            rows = value[key]
            if type(rows) is not list:
                raise ValueError('Incomplete links')
            edges = []
            for row in rows:
                if type(row) is not list or len(row) != 2 or any(type(i) is not int for i in row):
                    raise ValueError('Invalid dependency membership')
                edges.append(tuple(ids[i] for i in row))
            if len(set(edges)) != len(edges):
                raise ValueError('Duplicate links')
            result[key] = set(edges)
        if (result['parent_links_without_child_confirmation'] != result['parent_links'] - result['child_links']
                or result['child_links_without_parent_confirmation'] != result['child_links'] - result['parent_links']
                or type(value['relations_read']) is not int
                or value['relations_read'] != sum(len(result[k]) for k in ('parent_links', 'child_links', 'absorbed_links'))):
            raise ValueError('Unconfirmed dependency census')
        return result

    first, last = read(old, old_features), read(new, new_features)
    expected = (sketch_id, created_id)
    # SW2023 also reports the borrowed sketch's exact supporting plane/origin
    # as direct parents of the first extrusion. These are independently bound
    # above, and may project only an already confirmed baseline sketch link.
    allowed = {expected} | {(parent, created_id) for parent in (plane_id, origin_id)
        if (parent, sketch_id) in first['parent_links'] & first['child_links']}
    extra = last['parent_links'] - first['parent_links']
    if not {expected} <= extra <= allowed:
        return False
    for key in ('parent_links', 'child_links'):
        if last[key] != first[key] | extra:
            return False
    if last['absorbed_links'] != first['absorbed_links'] | {(created_id, sketch_id)}:
        return False
    return all(last[k] == first[k] for k in ('parent_links_without_child_confirmation',
                                           'child_links_without_parent_confirmation'))


def _external_delta(old, new, old_features, new_features, created_id):
    keys = {'scope', 'feature_count', 'total_reference_rows', 'features'}
    for value, features in ((old, old_features), (new, new_features)):
        if (type(value) is not dict or set(value) != keys
                or value['scope'] != 'native_feature_external_references_v1'
                or type(value['feature_count']) is not int or value['feature_count'] != len(features)
                or type(value['total_reference_rows']) is not int or value['total_reference_rows'] != 0
                or type(value['features']) is not list or len(value['features']) != len(features)
                or any(r != {'native_id': i, 'count': 0, 'rows': []}
                       for r, i in zip(value['features'], features))):
            return False
    return ([r for r in new['features'] if r['native_id'] != created_id] == old['features'])


def _controls(extrusion, depth):
    # ThinWallType describes a thin extrusion only. SW2023 returns -1 for the
    # first non-thin solid; the artificial/older capture uses 0. Admit precisely
    # those inactive encodings while retaining IsThinFeature=False, both zero
    # wall thicknesses, no cap/link, and the complete independent solid BREP.
    inactive_thin_type = extrusion.get('ThinWallType')
    if type(inactive_thin_type) is not int or inactive_thin_type not in (-1, 0):
        return False
    expected = {k: False for k in ('BothDirections', 'ReverseDirection', 'FeatureScope',
        'FromOffsetReverse', 'FlipSideToCut', 'NormalCut', 'LinkToThickness', 'CapEnds', 'thin_feature')}
    expected.update(Merge=True, AutoSelect={'availability': 'unavailable_feature_scope_disabled_v1'},
        FromType=0, ThinWallType=inactive_thin_type, FromOffsetDistance=0.0.hex(), CapThickness=0.0.hex(), contour_count=0)
    expected['directions'] = [dict(forward=forward, end_condition=0, depth=float(value).hex(),
        draft_angle=0.0.hex(), draft_enabled=False, draft_outward=False, reverse_offset=False,
        translate_surface=False, wall_thickness=0.0.hex()) for forward, value in ((True, depth), (False, 0.))]
    return _json(extrusion) == _json(expected)


def _numbers(values, size):
    if type(values) is not list or len(values) != size or any(type(v) is not str for v in values):
        raise ValueError('Incomplete exact native numbers')
    result = tuple(float.fromhex(v) for v in values)
    if any(not math.isfinite(v) or abs(v) > 10000. for v in result):
        raise ValueError('Invalid native numbers')
    return result


def _tolerance(value):
    return (type(value) is dict and set(value) == {'is_tolerant', 'gap_m'}
        and value['is_tolerant'] is False and type(value['gap_m']) is str
        and math.isfinite(float.fromhex(value['gap_m'])) and 0. <= float.fromhex(value['gap_m']) <= 5e-9)


def _boundary(geometry, parameters):
    """Check complete box incidence, native line/plane/trim data and outward shell."""
    if type(geometry) is not dict or set(geometry) != {'representation', 'bodies'} or geometry['representation'] != 'planar_polyhedral_brep_v1':
        return False
    bodies = geometry['bodies']
    if type(bodies) is not list or len(bodies) != 1:
        return False
    body = bodies[0]
    if (set(body) != {'scope', 'coordinate_frame', 'length_unit', 'number_encoding', 'vertices',
                     'vertex_tolerances', 'edges', 'faces'}
            or body['scope'] != 'planar_polyhedral_brep_v1' or body['coordinate_frame'] != 'part_model'
            or body['length_unit'] != 'm' or body['number_encoding'] != 'ieee754_binary64_hex_exact'
            or len(body['vertices']) != 8 or len(body['vertex_tolerances']) != 8
            or len(body['edges']) != 12 or len(body['faces']) != 6
            or not all(_tolerance(v) for v in body['vertex_tolerances'])):
        return False
    points = [_numbers(v, 3) for v in body['vertices']]
    w, h, d = (parameters[k] for k in ('width_m', 'height_m', 'depth_m'))
    frame = parameters['plane_transform']
    corners = list(product((0., w), (0., h), (0., d)))
    expected = [tuple(x*frame[i] + y*frame[3+i] + z*frame[6+i] + frame[9+i] for i in range(3)) for x, y, z in corners]
    corner_ids = []
    for point in points:
        matches = [i for i, p in enumerate(expected) if _points_consistent(point, p, 1e-12)]
        if len(matches) != 1: return False
        corner_ids.append(matches[0])
    if len(set(corner_ids)) != 8: return False
    pairs = {frozenset((i, j)) for i, j in combinations(range(8), 2)
             if sum(a != b for a, b in zip(corners[corner_ids[i]], corners[corner_ids[j]])) == 1}
    seen, uses = set(), {}
    for index, edge in enumerate(body['edges']):
        if set(edge) != {'start', 'end', 'line_parameters', 'trimmed_curve', 'native_tolerance', 'coedges'}:
            return False
        start, end = edge['start'], edge['end']
        if any(type(i) is not int or not 0 <= i < 8 for i in (start, end)): return False
        pair = frozenset((start, end))
        if pair not in pairs or pair in seen or not _tolerance(edge['native_tolerance']): return False
        seen.add(pair)
        line = _numbers(edge['line_parameters'], 6)
        if not any(line[3:]) or any(not _line_consistent(points[i], line, 1e-12) for i in (start, end)): return False
        trim = edge['trimmed_curve']
        if (set(trim) != {'curve_type', 'same_direction_as_edge', 'start_point', 'end_point', 'u_min', 'u_max'}
                or type(trim['curve_type']) is not int or trim['curve_type'] != 3001
                or type(trim['same_direction_as_edge']) is not bool
                or _numbers([trim['u_min'], trim['u_max']], 2)[0] >= _numbers([trim['u_min'], trim['u_max']], 2)[1]):
            return False
        a, b = (start, end) if trim['same_direction_as_edge'] else (end, start)
        if not _points_consistent(_numbers(trim['start_point'], 3), points[a], 1e-12) or not _points_consistent(_numbers(trim['end_point'], 3), points[b], 1e-12): return False
        uses[index] = []
    face_sets = {frozenset(i for i in range(8) if corners[corner_ids[i]][axis] == value)
                 for axis, size in enumerate((w, h, d)) for value in (0., size)}
    seen_faces, coedges = set(), {}
    for f, face in enumerate(body['faces']):
        if (set(face) != {'plane_parameters', 'normal_opposes_surface', 'loops'}
                or type(face['normal_opposes_surface']) is not bool or len(face['loops']) != 1): return False
        plane = _numbers(face['plane_parameters'], 6)
        if not any(plane[:3]): return False
        loop = face['loops'][0]
        if set(loop) != {'outer', 'coedges'} or loop['outer'] is not True or len(loop['coedges']) != 4: return False
        ring = loop['coedges']
        for c, row in enumerate(ring):
            if set(row) != {'edge', 'same_direction_as_edge', 'start', 'end', 'partner'}: return False
            if any(type(row[k]) is not int for k in ('edge', 'start', 'end')) or row['edge'] not in uses or type(row['same_direction_as_edge']) is not bool: return False
            edge = body['edges'][row['edge']]
            a, b = (edge['start'], edge['end']) if row['same_direction_as_edge'] else (edge['end'], edge['start'])
            if (row['start'], row['end']) != (a, b) or b != ring[(c+1)%4]['start']: return False
            pos = (f, 0, c)
            coedges[pos] = row
            uses[row['edge']].append(pos)
        vertices = frozenset(row['start'] for row in ring)
        if vertices not in face_sets or vertices in seen_faces or any(not _plane_consistent(points[i], plane, 1e-12) for i in vertices): return False
        seen_faces.add(vertices)
        a, b, c = (points[row['start']] for row in ring[:3])
        u, v = tuple(y-x for x,y in zip(a,b)), tuple(y-x for x,y in zip(a,c))
        cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        normal = tuple(-x if face['normal_opposes_surface'] else x for x in plane[:3])
        center = tuple(sum(p[i] for p in points)/8. for i in range(3))
        if sum(x*y for x,y in zip(cross,normal)) <= 0. or sum(normal[i]*(a[i]-center[i]) for i in range(3)) <= 0.: return False
    for index, positions in uses.items():
        if len(positions) != 2 or positions[0][0] == positions[1][0] or body['edges'][index]['coedges'] != [list(p) for p in sorted(positions)]: return False
        a, b = (coedges[p] for p in positions)
        if a['partner'] != list(positions[1]) or b['partner'] != list(positions[0]) or a['same_direction_as_edge'] == b['same_direction_as_edge']: return False
    return seen == pairs and seen_faces == face_sets


def verified_rectangle_extrusion(before, after, target_id, definition, created_native_id):
    """Admit only an exact blind base retaining the full borrowed rectangle."""
    try:
        if (type(definition) is not BlindRectangleExtrusion or type(created_native_id) is not int
                or BlindRectangleExtrusion.validate(**vars(definition)) != definition
                or not same_unmodified_session(before, after, target_id)):
            return False
        old = validated_rectangle_snapshot(before['snapshots'][target_id])
        new = validated_rectangle_snapshot(after['snapshots'][target_id])
        a, b = old['clone_state'], _restore_qualifications(new)
        if not verified_new_dimension_view(a['display_data'],b['display_data'],
                old['native_observations']['annotation_view_bindings'],new['native_observations']['annotation_view_bindings'],
                created_axes={'depth'}):return False
        if (a['profile'] != SKETCH or b['profile'] != BASE or old['solid_body_count'] != 0
                or new['solid_body_count'] != 1 or any(old[k] != new[k] for k in ('configuration', 'configurations', 'selection_count'))
                or old['native_observations']['document_dimension_namespace'] != new['native_observations']['document_dimension_namespace']
                or set(b) != (set(a) - {'origin'}) | {'extrusion', 'body', 'body_material'}): return False
        first, last = _features(a), _features(b)
        sketches = [i for i, (_, r) in first.items() if r['feature_type'] == 'ProfileFeature']
        if len(sketches) != 1 or set(last) - set(first) != {created_native_id} or not set(first) < set(last): return False
        sketch_id = sketches[0]
        added = last[created_native_id][1]
        if added['feature_type'] not in ('Boss', 'Extrusion') or added['name'] != definition.feature_name or added['owner_native_id'] is not None: return False
        if [r['native_id'] for r in b['features'] if r['native_id'] in first] != list(first): return False
        for native_id, (_, row) in first.items():
            expected = deepcopy(row)
            if native_id == sketch_id:
                if expected['owner_native_id'] is not None: return False
                expected['owner_native_id'] = created_native_id
            if last[native_id][1] != expected: return False
        roles = {f'feature:{index}': f'feature:{first[native_id][0]}'
                 for native_id, (index, _) in last.items() if native_id in first}
        for key in ('feature_pid_hex',):
            b['sketch'][key]['reference_role'] = roles[b['sketch'][key]['reference_role']]
        for key in ('reference_plane', 'model_origin'):
            b['sketch'][key]['pid_hex']['reference_role'] = roles[b['sketch'][key]['pid_hex']['reference_role']]
        if b['sketch'] != a['sketch'] or a['sketch']['feature_native_id'] != sketch_id: return False
        origin = a['origin']
        origin_ids = [native_id for native_id, (index, _) in first.items()
                      if f'feature:{index}' == origin['feature_role']]
        if (len(origin_ids) != 1
                or b['sketch']['model_origin_point'] != {k:v for k,v in origin.items() if k not in ('feature_role', 'point_role')}
                or b['sketch']['model_origin']['feature_native_id'] != origin_ids[0]): return False
        refs_a, refs_b = _refs(old), _refs(new)
        old_new_roles = set()
        for (kind, role), token in refs_a.items():
            if kind == 'feature':
                matches = [native_id for native_id, (index, _) in first.items() if f'feature:{index}' == role]
                if len(matches) != 1: return False
                new_role = f'feature:{last[matches[0]][0]}'
            else:
                new_role = role
            key = (kind, new_role)
            if refs_b.get(key) != token: return False
            old_new_roles.add(key)
        for role, native_id in (
                (a['sketch']['feature_pid_hex']['reference_role'], sketch_id),
                (a['sketch']['reference_plane']['pid_hex']['reference_role'], a['sketch']['reference_plane']['native_id']),
                (a['sketch']['model_origin']['pid_hex']['reference_role'], origin_ids[0])):
            if role != f'feature:{first[native_id][0]}' or ('feature',role) not in refs_a: return False
        entities = {('sketch_point', 'sketch:0/'+p['key']) for p in a['sketch']['points']}
        entities |= {('sketch_segment', 'sketch:0/'+s['key']) for s in a['sketch']['segments']}
        entities |= {('sketch_point', 'sketch:0/model_origin'), ('dimension', 'dimension:width'), ('dimension', 'dimension:height')}
        expected_old = entities | {('feature', f'feature:{index}') for index, row in first.values()
                                   if row['feature_type'] in ('RefPlane','OriginProfileFeature','ProfileFeature')}
        expected_old |= {('annotation', row['role']) for row in a['annotations']}
        if refs_a.keys() != expected_old: return False
        dims = [r for r in b['dimensions'] if r['owner']['native_id'] == sketch_id]
        normalized = deepcopy(a['dimensions'])
        for row in normalized:
            if type(row.pop('owner_update_stamp')) is not int or row['owner']['owner_native_id'] is not None: return False
            row['owner']['owner_native_id'] = created_native_id
        if dims != normalized: return False
        depth = [r for r in b['dimensions'] if r not in dims]
        if len(depth) != 1 or depth[0]['name'] != 'Толщина' or depth[0]['owner']['native_id'] != created_native_id or depth[0]['owner']['name'] != definition.feature_name: return False
        for row in b['dimensions']:
            owner = last[row['owner']['native_id']][1]
            if any(row['owner'].get(k) != value for k,value in owner.items()): return False
        old_params = rectangle_profile_parameters(a['sketch'], dict(dimensions=a['dimensions'], context=a['controls'], geometry=a['geometry']), old['configuration'], require_editable=False)
        params = rectangle_parameters(b['sketch'], dict(dimensions=b['dimensions'], context=b['controls'], geometry=b['geometry']), new['configuration'], require_editable=False)
        if (_json(old_params) != _json(a['parameters']) or _json(params) != _json(b['parameters'])
                or any(params[k] != old_params[k] for k in ('width_m', 'height_m', 'axes')) or params['depth_m'] != definition.depth_m
                or not _boundary(b['geometry'], params) or not _controls(b['extrusion'], definition.depth_m)
                or b['body'] != {'name': definition.body_name, 'visible': True}
                or type(b['body_material']) is not list or len(b['body_material']) != 2 or any(type(v) is not str for v in b['body_material'])): return False
        if not _dependency_delta(a['dependencies'], b['dependencies'], first, last, sketch_id, created_native_id,
                a['sketch']['reference_plane']['native_id'], origin_ids[0]): return False
        if not _external_delta(a['feature_external_reference_inventory'], b['feature_external_reference_inventory'], first, last, created_native_id): return False
        for plane in b['planes']:
            plane['role'] = roles[plane['role']]
        if b['planes'] != a['planes']: return False
        old_annotations = {r['role']:r for r in a['annotations']}
        new_annotations = {r['role']:r for r in b['annotations']}
        if (len(new_annotations) != len(b['annotations']) or len(old_annotations) != len(a['annotations'])
                or len(new_annotations) != len(old_annotations)+1
                or any(new_annotations.get(k) != v for k,v in old_annotations.items())): return False
        if [r for r in b['annotations'] if r['role'] in old_annotations] != a['annotations']: return False
        for annotation in b['annotations']:
            if (set(annotation) != {'role','type','visible','position','display_type','text','use_document_format','text_format'}
                    or any(type(annotation[k]) is not int for k in ('type','visible','display_type'))
                    or type(annotation['text']) is not str or type(annotation['use_document_format']) is not bool
                    or type(annotation['text_format']) is not list or not annotation['text_format']
                    or any(type(v) not in (str,int,float,bool) for v in annotation['text_format'])
                    or ('annotation', annotation['role']) not in refs_b): return False
            _numbers(annotation['position'],3)
        expected_new = {('feature', f'feature:{last[created_native_id][0]}'), ('body', 'body:0'), ('dimension', 'dimension:depth')}
        body = b['geometry']['bodies'][0]
        expected_new |= {('edge', 'body:0/' + _json(sorted([body['vertices'][r['start']],body['vertices'][r['end']]]))) for r in body['edges']}
        expected_new |= {('face', 'body:0/' + _json(sorted({tuple(body['vertices'][c['start']]) for loop in r['loops'] for c in loop['coedges']}))) for r in body['faces']}
        expected_new |= {('annotation', role) for role in new_annotations.keys() - old_annotations.keys()}
        if refs_b.keys() != old_new_roles | expected_new: return False
        changed = {'profile','features','dependencies','geometry','dimensions','sketch','parameters','origin',
                   'feature_external_reference_inventory','planes','annotations','display_data'}
        return all(_json(a[k]) == _json(b[k]) for k in a if k not in changed)
    except Exception:
        return False
