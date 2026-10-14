"""Closed semantic normalization of native owned-base suppression observations.

These pure functions do not resolve objects, authorize a mutation or substitute
for the complete native producer/session/revision gates.
"""
from copy import deepcopy

from .documents import rejected
from .jobs import _json


def normalized_sketch_relations(sketch, qualified_dimensions):
    """Bind native qualified dimension text to previously proven exact roles."""
    if type(sketch) is not dict or type(qualified_dimensions) is not list:
        raise rejected('suppression_intrinsics_incomplete', 'Native sketch and qualified dimension inventory required.')
    names = {}
    roles = set()
    for row in qualified_dimensions:
        if (type(row) is not dict or type(row.get('full_name')) is not str
                or not row['full_name'] or row.get('role') not in
                ('dimension:width','dimension:height','dimension:depth')
                or row['full_name'] in names or row['role'] in roles):
            raise rejected('suppression_intrinsics_incomplete', 'Unique proven dimension namespace/roles required.')
        names[row['full_name']] = row['role']; roles.add(row['role'])
    if roles != {'dimension:width','dimension:height','dimension:depth'}:
        raise rejected('suppression_intrinsics_incomplete', 'All original dimension roles required.')
    result = deepcopy(sketch)
    if type(result.get('relations')) is not list:
        raise rejected('suppression_intrinsics_incomplete', 'Complete native sketch relation inventory required.')
    for relation in result['relations']:
        if type(relation) is not dict:
            raise rejected('suppression_intrinsics_incomplete', 'Typed sketch relation required.')
        if relation.get('dimension_full_name') is not None:
            name = relation['dimension_full_name']
            if type(name) is not str or name not in names or names[name] == 'dimension:depth':
                raise rejected('suppression_intrinsics_incomplete', 'Sketch dimension must bind its original exact width/height role.')
            relation['dimension_full_name'] = {'reference_role':names[name]}
    return result


def normalized_suppressed_configuration(baseline, current, feature_name):
    """Admit only the SW2023 Russian native own suppression parameter row.

    Name qualifies a native configuration property after PID/canonical target
    resolution; it is not a selection/address fallback. Other locales/values
    require their own verified profile rather than a guessed translation.
    """
    if (type(baseline) is not dict or type(current) is not dict
            or type(feature_name) is not str or not feature_name or '@' in feature_name):
        raise rejected('suppression_configuration_unconfirmed', 'Complete original/current configuration and native target name required.')
    expected = deepcopy(baseline)
    parameters = expected.get('parameters')
    key = '$СОСТОЯНИЕ@' + feature_name
    if (type(parameters) is not list
            or any(type(row) is not list or len(row) != 2 or type(row[0]) is not str for row in parameters)
            or len({row[0] for row in parameters}) != len(parameters)
            or any(row[0] == key for row in parameters)):
        raise rejected('suppression_configuration_unconfirmed', 'Complete unsuppressed configuration parameter baseline required.')
    expected['parameters'] = sorted(parameters + [[key,'Пог']])
    if _json(current) != _json(expected):
        raise rejected('suppression_configuration_unconfirmed', 'Only the exact observed owned suppression parameter may change.')
    return deepcopy(baseline)


def normalized_suppressed_intrinsics(baseline_snapshot, current, feature_name):
    """Compare the concrete read-only fields measured in the compatibility probe."""
    keys={'extrusion','sketch','properties','configuration_state','auxiliary_data','display_data','controls'}
    if type(current) is not dict or set(current) != keys:
        raise rejected('suppression_intrinsics_incomplete', 'All declared native intrinsic fields required.')
    baseline = baseline_snapshot['clone_state']
    normalized = deepcopy(current)
    normalized['sketch'] = normalized_sketch_relations(current['sketch'],
        baseline_snapshot['native_observations']['qualified_dimensions'])
    normalized['configuration_state'] = normalized_suppressed_configuration(
        baseline['configuration_state'],current['configuration_state'],feature_name)
    if _json(normalized) != _json({key:baseline[key] for key in keys}):
        raise rejected('suppression_intrinsics_changed', 'Native geometry definition/sketch/property/control fields changed outside owned suppression.')
    return normalized
