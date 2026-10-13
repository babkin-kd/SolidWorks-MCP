"""Finite complete transition proofs for the retained own blind-base profile.

These predicates consume server observations, not client certificates. Native
canonical membership remains the producer's responsibility. No predicate can
authorize dispatch or reconstruction of ownership from serialized evidence.
"""
from copy import deepcopy

from .jobs import _json
from .rectangle_snapshot import BASE, validated_rectangle_snapshot
from .rectangle_postconditions import same_unmodified_session
from .cad_owned_suppression_snapshot import PROFILE, SCOPE, ROLES
from .suppressed_rectangle_intrinsics import normalized_suppressed_intrinsics


INTRINSICS = frozenset(('extrusion','sketch','properties','configuration_state',
                       'auxiliary_data','display_data','controls'))
BODY_REFS = frozenset(('body','face','edge','vertex'))


def _same(a, b):
    return _json(a) == _json(b)


def verified_owned_suppression(before, after, target_id, feature_native_id):
    """All original data preserved except the exact measured suppression effect."""
    try:
        if type(feature_native_id) is not int or not same_unmodified_session(before, after, target_id):
            return False
        original = validated_rectangle_snapshot(before['snapshots'][target_id])
        current = after['snapshots'][target_id]
        if (original['clone_state']['profile'] != BASE or original['selection_count'] != 0
                or set(current) != set(original) or current['scope'] != SCOPE
                or current['configurations'] != original['configurations']
                or current['configuration'] != original['configuration']
                or type(current['solid_body_count']) is not int or current['solid_body_count'] != 0
                or type(current['selection_count']) is not int or current['selection_count'] != 0):
            return False
        first, last = original['clone_state'], current['clone_state']
        if (type(last) is not dict or set(last) != set(first) - {'body','body_material'}
                or last['profile'] != PROFILE
                or last['geometry'] != {'representation':'planar_polyhedral_brep_v1','bodies':[]}):
            return False
        features = deepcopy(first['features'])
        matches = [row for row in features if row['native_id'] == feature_native_id]
        if len(matches) != 1 or matches[0]['suppressed'] is not False:
            return False
        feature_name = matches[0]['name']
        matches[0]['suppressed'] = True
        if not _same(features, last['features']):
            return False
        normalized = normalized_suppressed_intrinsics(original,
            {key:last[key] for key in INTRINSICS}, feature_name)
        dimensions = deepcopy(first['dimensions'])
        depth = [row for row in dimensions if row['full_name'] == {'reference_role':'dimension:depth'}]
        if (len(depth) != 1 or depth[0]['owner']['native_id'] != feature_native_id
                or depth[0]['owner']['suppressed'] is not False
                or 'owner_suppressed_frozen_or_rolled_back' in depth[0]['write_blockers']):
            return False
        depth[0]['owner']['suppressed'] = True
        depth[0]['write_blockers'].append('owner_suppressed_frozen_or_rolled_back')
        ordered = lambda rows: sorted(rows, key=lambda row: _json(row['full_name']))
        if not _same(ordered(dimensions), ordered(last['dimensions'])):
            return False
        ignored = INTRINSICS | {'profile','geometry','features','dimensions','body','body_material'}
        if any(not _same(first[key], last[key]) for key in first if key not in ignored):
            return False
        expected_refs = [row for row in original['references'] if row['kind'] not in BODY_REFS]
        if not _same(expected_refs, current['references']):
            return False
        native = current['native_observations']
        if (native['current_body_census_empty'] is not True
                or native['current_feature_canonical_census_confirmed'] is not True
                or native['body_intrinsics'] != dict(availability='unavailable_current_body_absent_v1',
                    source='actual_complete_body_census',current_body_count=0)
                or not _same(native['qualified_dimensions'], original['native_observations']['qualified_dimensions'])
                or native['document_dimension_namespace'] != original['native_observations']['document_dimension_namespace']
                or not _same(native['annotation_view_bindings'],original['native_observations']['annotation_view_bindings'])):
            return False
        members = native['retained_dimension_membership']
        anchors = {row['role']:row['token'] for row in expected_refs if row['kind'] == 'dimension'}
        if (type(members) is not list or len(members) != 3 or {row['role'] for row in members} != ROLES
                or any(set(row) != {'role','primary_pid_state','anchor',
                    'original_dimension_canonical_confirmed','original_owner_canonical_confirmed'}
                    or type(row['primary_pid_state']) is not int or row['primary_pid_state'] not in (0,2)
                    or row['original_dimension_canonical_confirmed'] is not True
                    or row['original_owner_canonical_confirmed'] is not True
                    or _json(row['anchor']) != anchors[row['role']] for row in members)):
            return False
        context = native['actual_dimension_context']
        if (set(context) != set(first['controls']) | {'active_document','read_only'}
                or context['active_document'] is not True or context['read_only'] is not False
                or not _same({key:context[key] for key in first['controls']},normalized['controls'])):
            return False
        stamps = native['dimension_owner_update_stamps']
        return set(stamps) == ROLES and all(type(value) is int for value in stamps.values())
    except (KeyError, TypeError, ValueError, AttributeError, RuntimeError):
        return False


def verified_owned_return(before, after, target_id):
    """Exact original full BASE and neighbors, after the body name is restored."""
    try:
        return (same_unmodified_session(before, after, target_id)
            and _same(validated_rectangle_snapshot(before['snapshots'][target_id]),
                      validated_rectangle_snapshot(after['snapshots'][target_id])))
    except (KeyError, TypeError, ValueError, AttributeError, RuntimeError):
        return False


def owned_body_name_delta(before, after, target_id):
    """Only a full name-only difference may admit an independently guarded repair."""
    try:
        original = before['snapshots'][target_id]['clone_state']['body']['name']
        current = after['snapshots'][target_id]['clone_state']['body']['name']
        if type(original) is not str or not original or type(current) is not str or current == original:
            return None
        patched = deepcopy(after)
        patched['snapshots'][target_id]['clone_state']['body']['name'] = original
        return dict(previous_name=current, original_name=original) if verified_owned_return(before,patched,target_id) else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
