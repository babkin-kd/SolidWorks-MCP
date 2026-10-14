"""Complete artificial transition inventories; not installed/native acceptance."""
from copy import deepcopy

import pytest

from solidworks_mcp.owned_suppression_postconditions import (
    verified_owned_suppression, verified_owned_return, owned_body_name_delta)
from test_cad_owned_suppression_snapshot import case, construct, suppress
from test_rectangle_extrusion_postconditions import proof as extrusion_proof


@pytest.fixture
def transition(case):
    case.model.GetUnits = lambda: deepcopy(case.baseline['clone_state']['units'])
    producer = construct(case)
    suppress(case)
    case.getter_values['configuration_state']['parameters'].sort(key=lambda row: row[0])
    depth = next(record for record in case.records
                 if record.summary['full_name'].startswith('Толщина@'))
    depth.summary['owner']['suppressed'] = True
    depth.summary['write_blockers'].append('owner_suppressed_frozen_or_rolled_back')
    snapshot = producer.capture()
    doc = dict(document_id='target', needs_save=True, update_stamp=4,
        observation_sequence=0, observation_revision='original')
    before = dict(semantic=dict(documents=[doc],active_document_id='target'),
        snapshots=dict(target=case.baseline))
    after = deepcopy(before)
    after['snapshots']['target'] = snapshot
    after['semantic']['documents'][0].update(update_stamp=5,observation_sequence=1,observation_revision='suppressed')
    return before, after, case.binding.native_id


def test_complete_own_transition(transition):
    before, after, feature_id = transition
    assert verified_owned_suppression(before, after, 'target', feature_id)
    assert not verified_owned_return(before, after, 'target')


@pytest.mark.parametrize('field', ['parameters','annotations','properties','material','units',
    'dependencies','extrusion','display_data','auxiliary_data','creation_controls',
    'configuration_state','equation_reference_inventory','feature_external_reference_inventory',
    'planes','sketch','dimensions','controls','features','geometry','profile'])
def test_missing_or_changed_complete_field_refused(transition, field):
    before, after, feature_id = transition
    after['snapshots']['target']['clone_state'][field] = None
    assert not verified_owned_suppression(before, after, 'target', feature_id)


@pytest.mark.parametrize('fault', ['reference','counter_type','neighbor','active','body_census',
    'canonical','dimension_null','owner','dimension_anchor','views','extra_state','read_only','rename'])
def test_foreign_session_and_binding_deltas_refused(transition, fault):
    before, after, feature_id = transition
    snapshot = after['snapshots']['target']; native = snapshot['native_observations']
    if fault == 'reference': snapshot['references'].pop()
    elif fault == 'counter_type': after['semantic']['documents'][0]['update_stamp'] = True
    elif fault == 'neighbor': after['snapshots']['neighbor'] = before['snapshots']['target']
    elif fault == 'active': after['semantic']['active_document_id'] = 'neighbor'
    elif fault == 'body_census': native['body_intrinsics']['current_body_count'] = 1
    elif fault == 'canonical': native['current_feature_canonical_census_confirmed'] = False
    elif fault == 'dimension_null': native['retained_dimension_membership'][0]['primary_pid_state'] = 4
    elif fault == 'owner': native['retained_dimension_membership'][0]['original_owner_canonical_confirmed'] = False
    elif fault == 'dimension_anchor': native['retained_dimension_membership'][0]['anchor'] = {}
    elif fault == 'views': native['annotation_view_bindings'] = []
    elif fault == 'extra_state': snapshot['clone_state']['configuration_state']['parameters'].append(['foreign','Пог'])
    elif fault == 'read_only': native['actual_dimension_context']['read_only'] = True
    else: snapshot['clone_state']['features'][-1]['name'] = 'Чужая операция'
    assert not verified_owned_suppression(before, after, 'target', feature_id)


def test_return_and_body_name_only_correction_are_distinct(transition):
    before, _, _ = transition
    returned = deepcopy(before)
    assert verified_owned_return(before, returned, 'target')
    assert owned_body_name_delta(before, returned, 'target') is None
    returned['snapshots']['target']['clone_state']['body']['name'] = 'Основание'
    assert not verified_owned_return(before, returned, 'target')
    assert owned_body_name_delta(before, returned, 'target') == dict(previous_name='Основание',
        original_name=before['snapshots']['target']['clone_state']['body']['name'])
    returned['snapshots']['target']['clone_state']['material'] = ['changed','']
    assert owned_body_name_delta(before, returned, 'target') is None
