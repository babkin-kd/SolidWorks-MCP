"""Strict detached probe receipts over the real artificial full CAD oracle.

No SolidWorks, installed-wheel acceptance, restart, cleanup, or CAD dispatch.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from test_rectangle_extrusion_postconditions import proof


path = Path(__file__).resolve().parents[1] / 'scripts/verifier_b2_suppression_probe.py'
spec = importlib.util.spec_from_file_location('b2_suppression_probe', path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def receipt(proof):
    _, after, _ = proof
    full = deepcopy(after['snapshots']['target'])
    rows = full['clone_state']['features']
    # CaptureAdapter's historical summaries predate the production warning bit.
    # The new producer uses feature_summary, which explicitly supplies it.
    for row in rows:
        row['is_warning'] = False
    position = next(i for i, row in enumerate(rows) if row['native_id'] == 5)
    role = 'feature:' + str(position)
    pid = next(row['token'] for row in full['references']
               if row['kind'] == 'feature' and row['role'] == role)
    owner = dict(document_id='target', configuration='Основная',
                 document_identity_token=101, configuration_identity_token=102,
                 feature_identity_token=1000 + position, feature_native_id=5,
                 feature_pid_hex=pid, feature_role=role, window_hwnd=100,
                 owned_document_ids=['target', 'neighbor'])
    semantic = deepcopy(after['semantic'])
    semantic['files'] = []
    semantic['application'] = dict(user_control=True, visible=True,
                                   current_directory='C:/контроль', search_folders='',
                                   command_in_progress=False)
    for i, doc in enumerate(semantic['documents']):
        doc.update(document_type='part', visible=True, dependencies=[], dependency_files=[],
                   path='', file=None, mode=dict(blocking_state=0, read_only_state=0,
                      editing_sketch=False, editing_component=False, view_only=False,
                      drawing_state=None))
    semantic['windows'] = [dict(document_id=doc['document_id'], hwnd=100+i, title=doc['title'])
                           for i, doc in enumerate(semantic['documents'])]
    session = dict(semantic=semantic, neighbor_snapshots={'neighbor': deepcopy(full)},
                   application_preferences={'raw_native_preference': True})
    observations = []
    for phase in helper.PHASES:
        observation = dict(phase=phase, **{key: owner[key] for key in (
            'document_id', 'configuration', 'document_identity_token',
            'configuration_identity_token')}, feature_summaries=deepcopy(rows),
            feature_identity_tokens=list(range(1000, 1000 + len(rows))),
            resolver=dict(input_pid_hex=pid, state=0, object_returned=True,
                roundtrip_pid_hex=pid, canonical_identity_token=1000+position,
                native_id=5, membership_index=position),
            is_suppressed2=[phase == 'suppressed'],
            geometry=deepcopy(full['clone_state']['geometry']), session=deepcopy(session))
        if phase == 'suppressed':
            observation['feature_summaries'][position]['suppressed'] = True
            observation['geometry']['bodies'] = []
            observation['session']['semantic']['documents'][0].update(
                update_stamp=20, observation_sequence=6, observation_revision='suppressed')
        else:
            observation['full_snapshot'] = deepcopy(full)
        if phase == 'restored':
            observation['session']['semantic']['documents'][0].update(
                update_stamp=21, observation_sequence=7, observation_revision='restored')
        observations.append(observation)
    actions = []
    for phase, method, arguments in (
        ('suppress', 'SetSuppression2', [0, 1, None]),
        ('suppress_rebuild', 'ForceRebuild3', [False]),
        ('unsuppress', 'SetSuppression2', [2, 1, None]),
        ('unsuppress_rebuild', 'ForceRebuild3', [False])):
        actions.append(dict(phase=phase, method=method, arguments=arguments,
            **{key: owner[key] for key in ('document_id', 'configuration',
                'document_identity_token', 'configuration_identity_token', 'feature_identity_token')},
            native_call_attempted=True, native_call_returned=True, pending=False, return_value=True))
    return dict(scope=helper.SCOPE, phase='terminal', native_calls_live=False,
                owner=owner, observations=observations, actions=actions, affected_native_ids=[5])


def test_full_restoration_normal_pid_probe_validates_only_detached_receipts(receipt):
    original = deepcopy(receipt)
    result = helper.validate_probe(receipt)
    assert result['receipt_validated'] is True
    assert result['affected_native_ids'] == [5]
    assert all(result[key] is False for key in ('accepted', 'native_b2_accepted',
        'can_dispatch_native', 'cad_cleanup_authorized', 'process_stop_authorized'))
    assert receipt == original


def test_observed_absorbed_sketch_suppression_can_be_in_complete_affected_set(receipt):
    rows = receipt['observations'][1]['feature_summaries']
    sketch = next(row for row in rows if row['feature_type'] == 'ProfileFeature')
    assert sketch['owner_native_id'] == 5
    sketch['suppressed'] = True
    receipt['affected_native_ids'] = [row['native_id'] for row in rows if row['suppressed']]
    assert helper.validate_probe(receipt)['receipt_validated']


@pytest.mark.parametrize('fault', [
    'running', 'pending_native', 'extra_top', 'missing_phase', 'phase_order',
    'configuration', 'document_identity', 'configuration_identity', 'pid_state4',
    'pid_state_bool', 'pid_null', 'pid_roundtrip', 'pid_input', 'pid_missing',
    'canonical_alias', 'getid_alias', 'name_fallback', 'membership',
    'census_duplicate', 'census_missing', 'census_identity', 'census_rename',
    'census_suppression_disagreement', 'suppression_unobserved', 'suppression_bool_int',
    'intermediate_body', 'intermediate_metric', 'restored_geometry', 'restored_properties',
    'restored_reference', 'restored_control', 'full_geometry_mass_fallback',
    'full_geometry_coedge', 'full_snapshot_missing', 'full_snapshot_extra',
    'full_summaries_differ', 'affected_omitted', 'foreign_affected', 'affected_duplicate',
    'neighbor_changed', 'neighbor_missing', 'neighbor_metric_fallback', 'windows_changed',
    'window_missing', 'files_changed', 'application_changed', 'preferences_changed',
    'target_view_changed', 'target_path_changed', 'target_configuration_added',
    'session_partial', 'session_empty_application', 'session_empty_view',
    'action_pending', 'action_unknown', 'action_bool_int', 'action_order',
    'action_rebuild_wrong', 'action_all_configurations', 'action_wrong_target',
    'action_wrong_identity', 'owner_window_bool', 'owner_pid_invalid', 'nonfinite',
    'empty_dependencies', 'empty_external_inventory', 'empty_controls',
    'missing_annotations', 'full_suppressed_tree', 'mode_scalar_alias',
    'command_missing', 'command_true', 'command_numeric_zero', 'command_numeric_one',
    'saved_neighbor_omitted_files', 'saved_neighbor_with_files', 'unsaved_extra_file',
    'neighbor_dependencies', 'owned_ids_missing', 'foreign_owned_ids',
])
def test_partial_identity_alias_geometry_and_session_drift_fail_closed(receipt, fault):
    obs = receipt['observations'][1]
    restored = receipt['observations'][2]
    resolver = obs['resolver']
    pos = resolver['membership_index']
    if fault == 'running': receipt['phase'] = 'running'
    elif fault == 'pending_native': receipt['native_calls_live'] = True
    elif fault == 'extra_top': receipt['accepted'] = True
    elif fault == 'missing_phase': receipt['observations'].pop()
    elif fault == 'phase_order': receipt['observations'].reverse()
    elif fault == 'configuration': obs['configuration'] = 'Другая'
    elif fault == 'document_identity': obs['document_identity_token'] += 1
    elif fault == 'configuration_identity': obs['configuration_identity_token'] += 1
    elif fault == 'pid_state4': resolver['state'] = 4
    elif fault == 'pid_state_bool': resolver['state'] = False
    elif fault == 'pid_null': resolver['object_returned'] = False
    elif fault == 'pid_roundtrip': resolver['roundtrip_pid_hex'] = 'ffff'
    elif fault == 'pid_input': resolver['input_pid_hex'] = 'ffff'
    elif fault == 'pid_missing': receipt['owner'].pop('feature_pid_hex')
    elif fault == 'canonical_alias': resolver['canonical_identity_token'] += 1
    elif fault == 'getid_alias': resolver['native_id'] += 1
    elif fault == 'name_fallback': resolver['strategy'] = 'feature_name'
    elif fault == 'membership': resolver['membership_index'] -= 1
    elif fault == 'census_duplicate': obs['feature_summaries'][0]['native_id'] = 5
    elif fault == 'census_missing': obs['feature_summaries'].pop()
    elif fault == 'census_identity': obs['feature_identity_tokens'][pos] = 9999
    elif fault == 'census_rename': obs['feature_summaries'][pos]['name'] = 'Другое'
    elif fault == 'census_suppression_disagreement': obs['feature_summaries'][pos]['suppressed'] = False
    elif fault == 'suppression_unobserved': obs['is_suppressed2'] = []
    elif fault == 'suppression_bool_int': obs['is_suppressed2'] = [1]
    elif fault == 'intermediate_body': obs['geometry'] = deepcopy(restored['geometry'])
    elif fault == 'intermediate_metric': obs['geometry'] = {'volume_mm3': 0.0}
    elif fault == 'restored_geometry': restored['full_snapshot']['clone_state']['geometry']['bodies'][0]['vertices'][0][0] = 1.0.hex()
    elif fault == 'restored_properties': restored['full_snapshot']['clone_state']['properties'][''][0]['value'] = 'Другая'
    elif fault == 'restored_reference': restored['full_snapshot']['references'][0]['token'] = 'ffff'
    elif fault == 'restored_control': restored['full_snapshot']['clone_state']['creation_controls']['auto_solve'] = False
    elif fault == 'full_geometry_mass_fallback':
        for before in (receipt['observations'][0], restored):
            before['full_snapshot']['clone_state']['geometry'] = {'mass': 1.0}
    elif fault == 'full_geometry_coedge': receipt['observations'][0]['full_snapshot']['clone_state']['geometry']['bodies'][0]['edges'][0]['coedges'] = []
    elif fault == 'full_snapshot_missing': restored['full_snapshot']['clone_state'].pop('annotations')
    elif fault == 'full_snapshot_extra': restored['full_snapshot']['clone_state']['unknown'] = []
    elif fault == 'full_summaries_differ': restored['full_snapshot']['clone_state']['features'][0]['name'] = 'Другое'
    elif fault == 'affected_omitted': receipt['affected_native_ids'] = []
    elif fault == 'foreign_affected':
        obs['feature_summaries'][0]['suppressed'] = True
        receipt['affected_native_ids'] = [0, 5]
    elif fault == 'affected_duplicate': receipt['affected_native_ids'] = [5, 5]
    elif fault == 'neighbor_changed': obs['session']['neighbor_snapshots']['neighbor']['clone_state']['body']['visible'] = False
    elif fault == 'neighbor_missing': obs['session']['neighbor_snapshots'] = {}
    elif fault == 'neighbor_metric_fallback': obs['session']['neighbor_snapshots']['neighbor'] = {'volume_mm3': 8000.0}
    elif fault == 'windows_changed': obs['session']['semantic']['windows'][1]['title'] = 'Другое'
    elif fault == 'window_missing': obs['session']['semantic']['windows'].pop(0)
    elif fault == 'files_changed': obs['session']['semantic']['files'] = [{'hash': 'other'}]
    elif fault == 'application_changed': obs['session']['semantic']['application']['current_directory'] = 'C:/другое'
    elif fault == 'preferences_changed': obs['session']['application_preferences']['raw_native_preference'] = False
    elif fault == 'target_view_changed': obs['session']['semantic']['documents'][0]['view'] = {'matrix': 'other'}
    elif fault == 'target_path_changed': obs['session']['semantic']['documents'][0]['path'] = 'C:/target.sldprt'
    elif fault == 'target_configuration_added': obs['session']['semantic']['documents'][0]['configurations'].append('Вторая')
    elif fault == 'session_partial': obs['session']['semantic'].pop('reference_graph')
    elif fault == 'session_empty_application':
        for row in receipt['observations']: row['session']['semantic']['application'] = {}
    elif fault == 'session_empty_view':
        for row in receipt['observations']: row['session']['semantic']['documents'][0]['view'] = {}
    elif fault == 'action_pending': receipt['actions'][0]['pending'] = True
    elif fault == 'action_unknown': receipt['actions'][0]['native_call_returned'] = False
    elif fault == 'action_bool_int': receipt['actions'][0]['return_value'] = 1
    elif fault == 'action_order': receipt['actions'].reverse()
    elif fault == 'action_rebuild_wrong': receipt['actions'][1]['arguments'] = [True]
    elif fault == 'action_all_configurations': receipt['actions'][0]['arguments'] = [0, 2, None]
    elif fault == 'action_wrong_target': receipt['actions'][0]['document_id'] = 'neighbor'
    elif fault == 'action_wrong_identity': receipt['actions'][0]['feature_identity_token'] += 1
    elif fault == 'owner_window_bool': receipt['owner']['window_hwnd'] = True
    elif fault == 'owner_pid_invalid': receipt['owner']['feature_pid_hex'] = 'xx'
    elif fault == 'empty_dependencies': receipt['observations'][0]['full_snapshot']['clone_state']['dependencies'] = {}
    elif fault == 'empty_external_inventory': receipt['observations'][0]['full_snapshot']['clone_state']['feature_external_reference_inventory'] = {}
    elif fault == 'empty_controls': receipt['observations'][0]['full_snapshot']['clone_state']['controls'] = {}
    elif fault == 'missing_annotations': receipt['observations'][0]['full_snapshot']['clone_state']['annotations'] = []
    elif fault == 'full_suppressed_tree':
        for row in (receipt['observations'][0], restored):
            row['feature_summaries'][0]['suppressed'] = True
            row['full_snapshot']['clone_state']['features'][0]['suppressed'] = True
    elif fault == 'mode_scalar_alias':
        for row in receipt['observations']:
            row['session']['semantic']['documents'][0]['mode']['editing_sketch'] = 0
    elif fault == 'command_missing':
        for row in receipt['observations']:
            row['session']['semantic']['application'].pop('command_in_progress')
    elif fault in ('command_true', 'command_numeric_zero', 'command_numeric_one'):
        value = {'command_true': True, 'command_numeric_zero': 0, 'command_numeric_one': 1}[fault]
        for row in receipt['observations']:
            row['session']['semantic']['application']['command_in_progress'] = value
    elif fault in ('saved_neighbor_omitted_files', 'saved_neighbor_with_files'):
        for row in receipt['observations']:
            doc = row['session']['semantic']['documents'][1]
            doc.update(path='C:/neighbor.sldprt', file={'path': 'C:/neighbor.sldprt', 'hash': 'unchanged'})
            if fault == 'saved_neighbor_with_files':
                row['session']['semantic']['files'] = [deepcopy(doc['file'])]
    elif fault == 'unsaved_extra_file':
        for row in receipt['observations']:
            row['session']['semantic']['files'] = [{'path': 'C:/unexpected.sldprt'}]
    elif fault == 'neighbor_dependencies':
        for row in receipt['observations']:
            row['session']['semantic']['documents'][1]['dependencies'] = ['C:/other.sldprt']
    elif fault == 'owned_ids_missing': receipt['owner'].pop('owned_document_ids')
    elif fault == 'foreign_owned_ids': receipt['owner']['owned_document_ids'] = ['target', 'foreign']
    else: obs['session']['application_preferences']['raw_native_preference'] = float('nan')
    with pytest.raises(ValueError):
        helper.validate_probe(receipt)


@pytest.mark.parametrize('fault', ['missing', 'empty', 'drawing', 'extra'])
def test_actual_part_mode_requires_explicit_null_drawing_state(receipt, fault):
    """NativeDocumentCloseCatalog includes drawing_state even for a part."""
    for phase in receipt['observations']:
        mode = phase['session']['semantic']['documents'][0]['mode']
        if fault == 'missing':
            mode.pop('drawing_state')
        elif fault == 'empty':
            mode['drawing_state'] = {}
        elif fault == 'drawing':
            mode['drawing_state'] = {'sheet': 'Лист1'}
        else:
            mode['unexpected'] = None
    with pytest.raises(ValueError, match='Complete owned dirty'):
        helper.validate_probe(receipt)


@pytest.mark.parametrize('phase', ['before', 'suppressed', 'restored'])
def test_raw_state2_is_confined_to_actual_suppressed_owner(receipt, phase):
    obs = next(row for row in receipt['observations'] if row['phase'] == phase)
    obs['resolver']['state'] = 2
    if phase == 'suppressed':
        assert helper.validate_probe(receipt)['receipt_validated'] is True
    else:
        with pytest.raises(ValueError): helper.validate_probe(receipt)
