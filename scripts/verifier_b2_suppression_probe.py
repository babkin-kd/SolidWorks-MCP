"""Passive receipt gate for one owned blind-base feature PID experiment.

This validates detached evidence, never executes CAD, authorizes cleanup, or
accepts B2. Producer contract: retain canonical IUnknown objects for the entire
probe; assign positive capture-local identity ordinals by canonical equality
(never by name/GetID), and record both traversal and normal PID resolution.
Before/restored snapshots use the existing rectangle full oracle unchanged.
The suppressed intermediate has a full feature census and the actual empty
dimension_geometry_snapshot; it is deliberately not mislabeled as a supported
rectangle construction snapshot. Only the base and its absorbed sketch may
change suppression state. Unsupported native behavior must fail this gate.
The entire census is exactly two producer-owned, already-dirty unsaved parts:
target and neighbor. Saved documents/dependencies are outside this probe;
empty files is admissible only with that explicit no-file census. This gate
does not claim preservation of arbitrary disk files outside the probe.
"""
from copy import deepcopy
import json

from solidworks_mcp.jobs import JobError, _json
from solidworks_mcp.rectangle_snapshot import BASE, validated_rectangle_snapshot
from solidworks_mcp.rectangle_extrusion_postconditions import _boundary
from solidworks_mcp.rectangle_inventory import feature_relations, empty_feature_external_inventory


SCOPE = 'owned_blind_base_suppression_pid_probe_v1'
PHASES = ('before', 'suppressed', 'restored')
FEATURE_KEYS = {'native_id', 'name', 'feature_type', 'suppressed',
                'owner_native_id', 'error_code', 'is_warning'}
BASE_KEYS = {'profile', 'features', 'dependencies', 'geometry', 'dimensions',
             'sketch', 'parameters', 'extrusion', 'controls',
             'equation_reference_inventory', 'feature_external_reference_inventory',
             'planes', 'properties', 'units', 'annotations', 'configuration_state',
             'auxiliary_data', 'display_data', 'material', 'body_material', 'body',
             'creation_controls'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return type(value) is str and bool(value.strip()) and '\0' not in value


def _ordinal(value):
    return type(value) is int and value > 0


def _snapshot(value, configuration):
    try:
        result = validated_rectangle_snapshot(value)
    except Exception as exc:
        raise ValueError('Complete supported native rectangle snapshot required.') from exc
    data = result['clone_state']
    _require(result['configuration'] == configuration
             and result['configurations'] == [configuration]
             and result['solid_body_count'] == 1 and result['selection_count'] == 0
             and set(data) == BASE_KEYS and data['profile'] == BASE,
             'Exactly one full unselected blind-base configuration required.')
    _require(_boundary(data['geometry'], data['parameters']),
             'Complete native rectangular planar BREP required, never mass/bounds.')
    _features(data['features'])
    _require(all(row['suppressed'] is False for row in data['features']),
             'Before/restored base feature tree must be unsuppressed.')
    feature_relations(data)
    empty_feature_external_inventory(data)
    _require(all(type(data[key]) is dict and bool(data[key]) for key in (
        'sketch', 'parameters', 'extrusion', 'controls', 'equation_reference_inventory',
        'properties', 'configuration_state', 'auxiliary_data', 'display_data', 'body'))
        and len(data['dimensions']) == 3 and len(data['annotations']) == 3
        and len(data['planes']) == 3 and bool(data['units'])
        and type(data['body_material']) is list and len(data['body_material']) == 2,
        'Full model/data/control inventories must be present.')
    return result


def _features(rows):
    _require(type(rows) is list and 6 <= len(rows) <= 64,
             'Complete bounded feature traversal required.')
    ids = []
    for row in rows:
        _require(type(row) is dict and set(row) == FEATURE_KEYS
                 and type(row['native_id']) is int and _text(row['name'])
                 and _text(row['feature_type']) and type(row['suppressed']) is bool
                 and (row['owner_native_id'] is None or type(row['owner_native_id']) is int)
                 and type(row['error_code']) is int and row['error_code'] == 0
                 and row['is_warning'] is False,
                 'Exact typed native feature summaries required.')
        ids.append(row['native_id'])
    _require(len(set(ids)) == len(ids), 'Duplicate feature incarnation.')
    return ids


def _session(value, target, configuration, owned_document_ids):
    _require(type(value) is dict and set(value) == {
        'semantic', 'neighbor_snapshots', 'application_preferences'},
             'Full session census and neighbor oracles required.')
    semantic = value['semantic']
    _require(type(semantic) is dict and set(semantic) == {
        'documents', 'windows', 'files', 'application', 'active_document_id', 'reference_graph'},
        'Use complete existing native-open session semantics.')
    docs = semantic['documents']
    _require(type(docs) is list and len(docs) == 2
             and all(type(row) is dict and _text(row.get('document_id')) for row in docs),
             'Exactly the owned unsaved target and independent owned neighbor required.')
    ids = [row['document_id'] for row in docs]
    _require(set(ids) == set(owned_document_ids), 'Census contains a foreign or missing owned document.')
    required_doc = {'document_id', 'title', 'path', 'document_type', 'active_configuration',
                    'configurations', 'needs_save', 'update_stamp', 'observation_sequence',
                    'observation_revision', 'view', 'visible', 'dependencies',
                    'dependency_files', 'mode', 'file'}
    _require(all(required_doc <= set(row) and row['document_type'] == 'part'
                 and row['configurations'] == [row['active_configuration']]
                 and type(row['view']) is dict and bool(row['view'])
                 and row['dependencies'] == [] and row['dependency_files'] == []
                 and row['path'] == '' and row['file'] is None and row['needs_save'] is True
                 and _json(row['mode']) == _json({'blocking_state': 0, 'read_only_state': 0,
                    'editing_sketch': False, 'editing_component': False, 'view_only': False})
                 and type(row['visible']) is bool for row in docs),
             'Complete owned dirty unsaved part/view/mode census required; no saved-file scope.')
    app = semantic['application']
    _require(type(app) is dict and set(app) == {
        'user_control', 'visible', 'current_directory', 'search_folders', 'command_in_progress'}
        and type(app['user_control']) is bool and type(app['visible']) is bool
        and type(app['command_in_progress']) is bool and app['command_in_progress'] is False
        and type(app['current_directory']) is str and type(app['search_folders']) is str
        and type(semantic['files']) is list and semantic['files'] == []
        and semantic['reference_graph'] == []
        and type(value['application_preferences']) is dict
        and bool(value['application_preferences']),
        'Complete native application/files/preferences census required.')
    windows = semantic['windows']
    _require(type(windows) is list and bool(windows)
        and all(type(window) is dict and set(window) == {'document_id', 'hwnd', 'title'}
            and window['document_id'] in ids and _ordinal(window['hwnd'])
            and _text(window['title']) for window in windows)
        and len({window['hwnd'] for window in windows}) == len(windows)
        and all(row['visible'] is any(w['document_id'] == row['document_id']
            for w in windows) for row in docs), 'Complete canonical window census required.')
    _require(len(set(ids)) == len(ids) and target in ids
             and semantic['active_document_id'] == target,
             'Exact current target membership required.')
    neighbors = value['neighbor_snapshots']
    _require(type(neighbors) is dict and set(neighbors) == set(ids) - {target},
             'No neighbor may be omitted.')
    for identifier, neighbor in neighbors.items():
        doc = next(row for row in docs if row['document_id'] == identifier)
        _snapshot(neighbor, doc['active_configuration'])
    doc = next(row for row in docs if row['document_id'] == target)
    _require(doc.get('active_configuration') == configuration
             and doc.get('configurations') == [configuration]
             and doc.get('needs_save') is True and doc.get('path') == ''
             and doc.get('file') is None,
             'Probe owns one already-dirty unsaved native target.')
    normalized = deepcopy(value)
    changed = next(row for row in normalized['semantic']['documents']
                   if row['document_id'] == target)
    for key in ('update_stamp', 'observation_sequence'):
        _require(type(changed.get(key)) is int, 'Typed target revision counters required.')
        changed.pop(key)
    _require(_text(changed.get('observation_revision')), 'Target observation revision required.')
    changed.pop('observation_revision')
    return normalized


def validate_probe(receipt):
    """Return receipt-only validation; raise ValueError on incomplete evidence.

    `observations` contains the three ordered phases. Each records document and
    configuration identity ordinals, full `feature_summaries`, parallel ordered
    `feature_identity_tokens`, `session`, normal `resolver`, IsSuppressed2 raw
    singleton, and geometry. Before/restored additionally hold `full_snapshot`.
    Resolver records the original input PID, state 0, nonnull native object,
    regenerated PID, canonical ordinal/GetID, and one exact traversal index.
    `actions` are the four normally-returned setter/rebuild receipts in order.
    Current-configuration setters are bounded by the explicit one-configuration
    capture: SetSuppression2(0/2, 1, None), ForceRebuild3(False).
    Phase captures occur outside setters/rebuilds, after normal release of the
    producer's own action guard (before is captured before acquisition).
    `session.semantic.application.command_in_progress` is the directly observed
    native flag and must be strictly False at every phase, not a normalized or
    inferred release result. `owner.owned_document_ids` contains exactly the two
    unsaved fixtures created by this producer. Full phase census must contain
    those IDs only, empty native paths, no file/dependency facts and empty files;
    saved/user documents require another probe and disk oracle.
    No field grants new native dispatch, cleanup, or process-stop permission.
    """
    try:
        receipt = json.loads(_json(receipt))
        _require(set(receipt) == {'scope', 'phase', 'native_calls_live', 'owner',
                                 'observations', 'actions', 'affected_native_ids'},
                 'Exact finite probe receipt required.')
        _require(receipt['scope'] == SCOPE and receipt['phase'] == 'terminal'
                 and receipt['native_calls_live'] is False,
                 'Only terminal normally returned observations are admissible.')
        owner = receipt['owner']
        _require(type(owner) is dict and set(owner) == {
            'document_id', 'configuration', 'document_identity_token',
            'configuration_identity_token', 'feature_identity_token',
            'feature_native_id', 'feature_pid_hex', 'feature_role', 'window_hwnd',
            'owned_document_ids'},
            'Explicit exact owned native bindings required.')
        target, cfg = owner['document_id'], owner['configuration']
        owned_ids = owner['owned_document_ids']
        _require(type(owned_ids) is list and len(owned_ids) == 2
                 and all(_text(identifier) for identifier in owned_ids)
                 and len(set(owned_ids)) == 2 and target in owned_ids,
                 'Exactly two explicitly producer-owned fixture IDs required.')
        _require(_text(target) and _text(cfg) and _text(owner['feature_role'])
                 and all(_ordinal(owner[k]) for k in ('document_identity_token',
                    'configuration_identity_token', 'feature_identity_token', 'window_hwnd'))
                 and type(owner['feature_native_id']) is int,
                 'Typed current document/configuration/feature/window binding required.')
        pid = owner['feature_pid_hex']
        _require(_text(pid) and bytes.fromhex(pid).hex() == pid and bool(bytes.fromhex(pid)),
                 'Exact original feature PID bytes required.')
        observations = receipt['observations']
        _require(type(observations) is list and len(observations) == 3,
                 'All three ordered native observations required.')
        baseline = None
        sessions = []
        summaries = []
        for phase, obs in zip(PHASES, observations):
            keys = {'phase', 'document_id', 'configuration', 'document_identity_token',
                    'configuration_identity_token', 'feature_summaries',
                    'feature_identity_tokens', 'resolver', 'is_suppressed2',
                    'geometry', 'session'}
            if phase != 'suppressed':
                keys.add('full_snapshot')
            _require(type(obs) is dict and set(obs) == keys and obs['phase'] == phase,
                     'Exact phase receipt shape required.')
            _require(all(type(obs[k]) is type(owner[k]) and obs[k] == owner[k] for k in (
                'document_id', 'configuration', 'document_identity_token',
                'configuration_identity_token')), 'Canonical document/configuration changed.')
            ids = _features(obs['feature_summaries'])
            tokens = obs['feature_identity_tokens']
            _require(type(tokens) is list and len(tokens) == len(ids)
                     and all(_ordinal(token) for token in tokens)
                     and len(set(tokens)) == len(tokens), 'Complete canonical feature census required.')
            position = ids.index(owner['feature_native_id'])
            _require(tokens[position] == owner['feature_identity_token'],
                     'GetID/name may not substitute another canonical feature.')
            expected = phase == 'suppressed'
            _require(obs['is_suppressed2'] == [expected]
                     and type(obs['is_suppressed2']) is list
                     and type(obs['is_suppressed2'][0]) is bool
                     and obs['feature_summaries'][position]['suppressed'] is expected,
                     'Actual IsSuppressed2 singleton and census must agree.')
            resolver = obs['resolver']
            _require(type(resolver) is dict and resolver == {
                'input_pid_hex': pid, 'state': 0, 'object_returned': True,
                'roundtrip_pid_hex': pid, 'canonical_identity_token': owner['feature_identity_token'],
                'native_id': owner['feature_native_id'], 'membership_index': position}
                and type(resolver['state']) is int and type(resolver['object_returned']) is bool
                and type(resolver['canonical_identity_token']) is int
                and type(resolver['native_id']) is int and type(resolver['membership_index']) is int,
                'Normal state-0 exact PID/canonical roundtrip required; no fallback.')
            sessions.append(_session(obs['session'], target, cfg, owned_ids))
            _require(any(window.get('document_id') == target and
                window.get('hwnd') == owner['window_hwnd'] and type(window['hwnd']) is int
                for window in obs['session']['semantic']['windows']), 'Owned exact HWND missing.')
            if phase == 'suppressed':
                _require(obs['geometry'] == {'representation': 'planar_polyhedral_brep_v1', 'bodies': []},
                         'The actual suppressed base must have no remaining bodies.')
                _require(tokens == observations[0]['feature_identity_tokens'],
                         'Feature canonical membership/order changed during suppression.')
            else:
                snapshot = _snapshot(obs['full_snapshot'], cfg)
                _require(snapshot['clone_state']['features'] == obs['feature_summaries']
                         and snapshot['clone_state']['geometry'] == obs['geometry'],
                         'Full independent snapshot must bind actual census and BREP.')
                refs = [row for row in snapshot['references'] if row['kind'] == 'feature'
                        and row['role'] == owner['feature_role']]
                _require(refs == [{'kind': 'feature', 'role': 'feature:' + str(position), 'token': pid}],
                         'Owned feature role must bind exact PID and full snapshot member.')
                if phase == 'before':
                    baseline = snapshot
                else:
                    _require(_json(snapshot) == _json(baseline)
                             and tokens == observations[0]['feature_identity_tokens'],
                             'Unsuppress must restore every full oracle/reference field exactly.')
            summaries.append(obs['feature_summaries'])
        _require(all(_json(session) == _json(sessions[0]) for session in sessions[1:]),
                 'Neighbor, files, windows, UI or session baseline changed.')
        affected = []
        for old, suppressed, restored in zip(*summaries):
            _require(set(old) == set(suppressed) == set(restored)
                     and all(_json(old[k]) == _json(suppressed[k]) for k in FEATURE_KEYS - {'suppressed'})
                     and old == restored, 'Feature tree/identity/definitions changed.')
            if old['suppressed'] != suppressed['suppressed']:
                affected.append(old['native_id'])
        base_row = next(row for row in summaries[0] if row['native_id'] == owner['feature_native_id'])
        _require(base_row['feature_type'] in ('Extrusion', 'Boss') and base_row['suppressed'] is False,
                 'Only the owned native blind-base feature is supported.')
        allowed = {owner['feature_native_id']} | {row['native_id'] for row in summaries[0]
            if row['feature_type'] == 'ProfileFeature' and row['owner_native_id'] == owner['feature_native_id']}
        _require(receipt['affected_native_ids'] == affected
                 and type(receipt['affected_native_ids']) is list
                 and all(type(i) is int for i in receipt['affected_native_ids'])
                 and owner['feature_native_id'] in affected and set(affected) <= allowed,
                 'Exact complete bounded base/absorbed-sketch affected census required.')
        actions = receipt['actions']
        expected_actions = [('suppress', 'SetSuppression2', [0, 1, None]),
                            ('suppress_rebuild', 'ForceRebuild3', [False]),
                            ('unsuppress', 'SetSuppression2', [2, 1, None]),
                            ('unsuppress_rebuild', 'ForceRebuild3', [False])]
        _require(type(actions) is list and len(actions) == 4, 'Four exact returned native actions required.')
        for action, (phase, method, arguments) in zip(actions, expected_actions):
            _require(type(action) is dict and set(action) == {
                'phase', 'method', 'arguments', 'document_id', 'configuration',
                'document_identity_token', 'configuration_identity_token',
                'feature_identity_token', 'native_call_attempted', 'native_call_returned',
                'pending', 'return_value'}, 'Exact native return receipt required.')
            _require(action['phase'] == phase and action['method'] == method
                     and _json(action['arguments']) == _json(arguments)
                     and all(type(action[k]) is type(owner[k]) and action[k] == owner[k] for k in (
                         'document_id', 'configuration', 'document_identity_token',
                         'configuration_identity_token', 'feature_identity_token'))
                     and action['native_call_attempted'] is True
                     and action['native_call_returned'] is True and action['pending'] is False
                     and action['return_value'] is True, 'Normally returned exact setter/rebuild required.')
    except (KeyError, TypeError, IndexError, StopIteration, OverflowError, JobError) as exc:
        raise ValueError('Incomplete owned suppression probe receipt.') from exc
    return {'scope': SCOPE, 'receipt_validated': True, 'accepted': False,
            'native_b2_accepted': False, 'process_stop_authorized': False,
            'cad_cleanup_authorized': False, 'can_dispatch_native': False,
            'affected_native_ids': list(affected)}
