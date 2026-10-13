"""Private same-STA reference-registration export for the B3 driver.

Records actual catalog UUID/PID associations, including historical references.
No native calls, registration, resolution, model adoption or public tools.
These rows supply the namespace side of the bridge, never native identity proof.
"""
from copy import deepcopy
import json
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def export_registered_references(entry, *, assert_safe):
    """Export existing tables only; assert_safe admits the original catalog/STA.

The driver must separately associate document_id with its retained native
model/window, and resolve every used PID against original canonical anchors.
An exported retired/inactive reference is not thereby current or usable.
No setdefault/_register/adapter resolver is called by this exporter.
"""
    require(callable(assert_safe), 'Original driver admission required.')
    assert_safe()
    require(type(entry.document_id) is str and re.fullmatch(r'doc_[0-9a-f]{32}', entry.document_id),
            'Actual private document catalog UUID required.')
    require(type(entry.geometry) is dict and type(entry.features) is dict, 'Actual catalog state tables required.')
    rows = []

    def table(state, name):
        result = state.get(name, {})
        require(type(result) is dict, 'Actual registration table must be a mapping.')
        return result

    def add(refs, family, prefix, *, anchors=False, owner=None):
        require(len(refs) <= 5000, 'Finite private export budget exceeded; no partial bridge.')
        for key, ref in refs.items():
            require(type(key) is str and key == ref.object_id
                    and re.fullmatch(prefix+r'_[0-9a-f]{32}', key), 'Actual registry key/UUID differs.')
            row = dict(family=family, object_id=key)
            if hasattr(ref, 'configuration'):
                require(type(ref.configuration) is str and ref.configuration, 'Original registered configuration required.')
                row['configuration'] = ref.configuration
            if anchors:
                require(type(ref.persistent_id) is dict and ref.persistent_id, 'Actual dimension compound anchor required.')
                row['reference_anchor'] = deepcopy(ref.persistent_id)
                anchor = row['reference_anchor']
                strategy = anchor.get('strategy')
                fields = {'strategy', 'dimension_pid_hex'} if strategy == 'direct_dimension_v1' else {
                    'strategy', 'display_pid_hex', 'owner_pid_hex', 'dimension_index', 'display_type'}
                require(strategy in ('direct_dimension_v1', 'display_dimension_v1') and set(anchor) == fields,
                        'Actual finite direct/display dimension anchor schema required.')
                for name in fields - {'strategy', 'dimension_index', 'display_type'}:
                    value = anchor[name]
                    require(type(value) is str and value and len(value) % 2 == 0
                            and re.fullmatch('[0-9a-f]+', value), 'Actual canonical PID hex required.')
                if strategy == 'display_dimension_v1':
                    require(type(anchor['dimension_index']) is int and anchor['dimension_index'] in (0, 1)
                            and type(anchor['display_type']) is int,
                            'Actual typed native dimension slot/type required.')
            else:
                require(type(ref.persistent_id) is bytes and ref.persistent_id, 'Actual registered native PID bytes required.')
                row['persistent_id_hex'] = ref.persistent_id.hex()
            if family in ('part_geometry', 'component_topology'):
                require(ref.kind in ('body', 'face', 'edge'), 'Registered native geometry kind required.')
                row['kind'] = ref.kind
                row['body_id'] = ref.body_id
                require((ref.kind == 'body' and ref.body_id is None) or
                        (ref.kind != 'body' and type(ref.body_id) is str and ref.body_id),
                        'Actual registered geometry body ownership required.')
            if family in ('component_body', 'component_topology'):
                require(type(ref.component_id) is str and ref.component_id in owner,
                        'Registered body/topology must retain its actual component namespace owner.')
                row['component_id'] = ref.component_id
                row['configuration'] = owner[ref.component_id].configuration
            if family == 'component_topology':
                require(ref.kind in ('face', 'edge') and type(ref.body_id) is str and ref.body_id in bodies
                        and bodies[ref.body_id].component_id == ref.component_id,
                        'Topology owner must match its actual registered instance body.')
            if family == 'component':
                require(type(ref.referenced_configuration) is str and ref.referenced_configuration,
                        'Registered referenced configuration required.')
                row['referenced_configuration'] = ref.referenced_configuration
            rows.append(row)

    add(table(entry.geometry, 'references'), 'part_geometry', 'obj')
    add(table(entry.features, 'references'), 'feature', 'feat')
    add(table(table(entry.features, 'dimensions'), 'references'), 'dimension', 'dim', anchors=True)
    component_state = table(entry.geometry, 'component_catalog')
    components, bodies = table(component_state, 'refs'), table(component_state, 'bodies')
    add(components, 'component', 'cmp')
    add(bodies, 'component_body', 'cmp_body', owner=components)
    add(table(table(entry.geometry, 'component_topology'), 'refs'), 'component_topology', 'cmp_obj', owner=components)
    require(len(rows) <= 5000 and len({r['object_id'] for r in rows}) == len(rows),
            'Whole registration export budget/UUID uniqueness required.')
    rows.sort(key=lambda row: (row['family'], row['object_id']))
    # This serialization deliberately cannot include native handles/IUnknowns.
    detached = json.loads(json.dumps(rows, ensure_ascii=False, allow_nan=False, sort_keys=True))
    assert_safe()
    return dict(scope='private_b3_actual_registered_reference_export_v1', document_id=entry.document_id,
                rows=detached, accepted=False, native_acceptance=False, cleanup_authorized=False,
                current_membership_verified=False,
                open_gates=['original_document_ID_native_model_window_bridge',
                            'current_PID_original_canonical_owner_membership',
                            'whole_session_event_envelope', 'installed_native_driver'])
