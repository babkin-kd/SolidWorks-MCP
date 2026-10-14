"""Artificial acknowledged fixture phases; real topology/catalog/SQL failures."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from test_b3_component_membership import world

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_component_retirement as helper
finally:
    sys.path.remove(scripts)


@pytest.fixture
def phase_world(world):
    x = world; a = x.a; catalog = x.catalog; original = x.originals['cylinder']
    component = catalog.get(**x.context, component_id=x.ids['cylinder'])['component']
    body = catalog.bodies(**x.context, component_id=x.ids['cylinder'])['items'][0]
    face = catalog.list_topology(**x.context, component_id=x.ids['cylinder'], body_id=body['body_id'], kind='face')['items'][0]
    instance_receipt = x.instance_capture(x.context, component)
    body_receipt = x.reference_capture(x.context, component, body)
    face_receipt = x.reference_capture(x.context, component, face)
    original_binding = dict(component_native_identity=instance_receipt['native_identity'], component_persistent_id=instance_receipt['persistent_id'],
        body_native_identity=body_receipt['native_identity'], body_persistent_id=body_receipt['persistent_id'],
        face_native_identity=face_receipt['native_identity'], face_persistent_id=face_receipt['persistent_id'],
        referenced_path=original.info['referenced_path'], referenced_configuration=original.info['referenced_configuration'],
        native_receipt=dict(artificial_original_held_incarnation=instance_receipt, original_body=body_receipt, original_face=face_receipt))
    old_refs = dict(component_id=component['component_id'], body_id=body['body_id'], face_id=face['object_id'])
    x.phase_corrupt = None; x.full_corrupt = False; x.phase_calls = 0
    def prepare(phase, code):
        # Only simulate normally acknowledged external setup in artificial
        # handles. No native setter/delete/insert or production mutation runs.
        assert phase in ('deleted', 'reinserted') and code in helper.CODES
        a.instances.remove(original)
        current_refs, new_native = None, None
        if phase == 'reinserted':
            new_native = NS(identity=object(), persistent_id=b'new-own-cylinder', parent=None,
                model_identity=original.model_identity, cfg=original.cfg, bodies=[a.body()], info=deepcopy(original.info),
                raw_total_transform=list(original.raw_total_transform))
            # Same file, path/name and geometric metadata, but new retained IDs.
            a.registry[new_native.persistent_id] = new_native; a.instances.append(new_native)
            x.originals['new_cylinder'] = new_native
        if code in ('object_deleted', 'object_reference_invalid'): a.states[original.persistent_id] = code
        elif code == 'persistent_reference_mismatch':
            a.registry[original.persistent_id] = new_native if new_native is not None else x.originals['main']
        a.models[0].state['update_stamp'] += 1
        current_doc = x.docs.get(x.context['document_id'], x.context['configuration'])
        x.context['expected_observation_revision'] = current_doc['observation_revision']
        ctx = deepcopy(x.context)
        new_binding = None
        if new_native is not None:
            rows = catalog.list(**ctx)['items']; state = catalog._state(x.entry)
            cid = next(row['component_id'] for row in rows if state['refs'][row['component_id']].native_identity == new_native.identity)
            x.ids['new_cylinder'] = cid
            new_component = catalog.get(**ctx, component_id=cid)['component']
            new_body = catalog.bodies(**ctx, component_id=cid)['items'][0]
            new_face = catalog.list_topology(**ctx, component_id=cid, body_id=new_body['body_id'], kind='face')['items'][0]
            ir = x.instance_capture(ctx, new_component); br = x.reference_capture(ctx, new_component, new_body); fr = x.reference_capture(ctx, new_component, new_face)
            current_refs = dict(component_id=cid, body_id=new_body['body_id'], face_id=new_face['object_id'])
            new_binding = dict(component=new_component, body=new_body, face=new_face,
                component_native_identity=ir['native_identity'], component_persistent_id=ir['persistent_id'],
                body_native_identity=br['native_identity'], body_persistent_id=br['persistent_id'],
                face_native_identity=fr['native_identity'], face_persistent_id=fr['persistent_id'],
                body_owner_native_identity=ir['native_identity'], face_owner_native_identity=br['native_identity'],
                total_transform=ir['total_transform'], native_receipt=dict(artificial_returned_new_handle=ir, body=br, face=fr))
        # Current raw PID observation selects the expected code BEFORE dispatch.
        try:
            resolved = a.resolve_persistent_id(a.models[0], original.persistent_id, 'component')
            if resolved.identity != original.identity:
                selected = 'persistent_reference_mismatch'
                if new_native is resolved: resolution_ordinal = new_binding['component_native_identity']
                else:
                    main = catalog.get(**ctx, component_id=x.ids['main'])['component']
                    resolution_ordinal = x.instance_capture(ctx, main)['native_identity']
            else: selected = 'component_not_in_active_configuration'; resolution_ordinal = None
        except ExecutionFailure as error:
            selected = error.code; resolution_ordinal = None
        assert selected == code
        steps = []
        def pair(name, returned):
            steps.extend([dict(sequence=len(steps)+1, name=name, phase='pending', evidence={'artificial_original_owner_attempt': True}),
                dict(sequence=len(steps)+2, name=name, phase='returned', evidence=returned)])
        if phase == 'deleted':
            pair('IModelDocExtension.DeleteSelection2', dict(return_value=True,
                selected_native_identity=original_binding['component_native_identity'], selected_persistent_id=original_binding['component_persistent_id']))
        else:
            pair('IAssemblyDoc.AddComponent5', dict(returned_native_identity=new_binding['component_native_identity'],
                returned_persistent_id=new_binding['component_persistent_id'], referenced_path=original_binding['referenced_path']))
        pair('IModelDoc2.ForceRebuild3', dict(return_value=True))
        transition = dict(transition_id='artificial-owned-'+phase, phase=phase, native_steps=steps)
        def capture(context, requested_phase, requested_old, requested_current):
            x.phase_calls += 1
            assert context == ctx and requested_phase == phase and requested_old == old_refs and requested_current == current_refs
            rows = catalog.list(**ctx)['items']; census = []
            for item in rows:
                receipt = x.instance_capture(ctx, item)
                census.append(dict(native_identity=receipt['native_identity'], persistent_id=receipt['persistent_id'], native_receipt=receipt))
            # Stable ordinals on held identities, independent of enumeration.
            census.sort(key=lambda item: item['native_identity'])
            value = dict(context=ctx, phase=phase, original_refs=old_refs, current_refs=current_refs,
                expected_errors={tool: selected for tool in helper.TOOLS}, original=original_binding, current=new_binding,
                model_native_identity=100, configuration_native_identity=101,
                current_instance_census=census,
                original_pid_resolution=dict(persistent_id=original_binding['component_persistent_id'], native_identity=resolution_ordinal,
                    native_receipt=dict(artificial_raw_pid_code=selected, original_current_members=[])),
                transition_receipt=transition)
            value = deepcopy(value)
            if x.phase_corrupt: x.phase_corrupt(value, x.phase_calls)
            return value
        return ctx, old_refs, current_refs, capture
    x.prepare_phase = prepare
    return x


def run(x, phase='deleted', code='component_not_in_active_configuration', **overrides):
    ctx, old, new, capture = x.prepare_phase(phase, code)
    args = dict(phase=phase, context=ctx, original_refs=old, current_refs=new, capture_full=x.full, capture_phase=capture)
    args.update(overrides)
    return asyncio.run(helper.component_retirement_phase(x.reader, **args))


@pytest.mark.parametrize('phase', ['deleted', 'reinserted'])
@pytest.mark.parametrize('code', sorted(helper.CODES))
def test_fresh_observed_old_refs_retired_and_same_file_new_incarnation_exact_current_roundtrips(phase_world, phase, code):
    x = phase_world; result = run(x, phase, code)
    assert x.full_calls == x.phase_calls == 2
    assert len(result['rows']) == len(x.store.list()['items']) == (3 if phase == 'deleted' else 6)
    old = result['rows'][:3]
    assert all(row['journal']['status'] == 'failed' and row['journal']['error']['code'] == code
               and row['journal']['error']['requires_reconciliation'] is False and row['journal']['result'] is None for row in old)
    assert all(row['journal']['status'] == 'succeeded' for row in result['rows'][3:])
    assert x.retained == [] and result['before'] == result['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert all(job['payload']['mutates'] is False and 'mutation' not in job for job in x.store.list()['items'])
    if phase == 'reinserted':
        original, new = result['native_before']['original'], result['native_before']['current']
        assert original['referenced_path'] == new['component']['referenced_path']
        assert original['component_native_identity'] != new['component_native_identity']


@pytest.mark.parametrize('fault', ['pending', 'missing_call', 'duplicate_step', 'wrong_original', 'false_delete',
    'false_rebuild', 'code_unknown', 'wrong_phase', 'old_present', 'pid_retarget', 'no_original_pid'])
def test_missing_native_acknowledgement_or_original_absence_proof_prevents_dispatch(phase_world, fault):
    x = phase_world
    def corrupt(value, number):
        steps = value['transition_receipt']['native_steps']
        if fault == 'pending': steps[-1]['phase'] = 'pending'
        elif fault == 'missing_call': del steps[:2]
        elif fault == 'duplicate_step': steps[2]['name'] = steps[3]['name'] = steps[0]['name']
        elif fault == 'wrong_original': steps[1]['evidence']['selected_native_identity'] += 99
        elif fault == 'false_delete': steps[1]['evidence']['return_value'] = False
        elif fault == 'false_rebuild': steps[-1]['evidence']['return_value'] = False
        elif fault == 'code_unknown': value['expected_errors']['component_get'] = 'native_unknown'
        elif fault == 'wrong_phase': value['transition_receipt']['phase'] = 'reinserted'
        elif fault == 'old_present': value['current_instance_census'][0]['native_identity'] = value['original']['component_native_identity']
        elif fault == 'pid_retarget': value['original_pid_resolution']['native_identity'] = value['original']['component_native_identity']
        else: value['original']['component_persistent_id'] = ''
    x.phase_corrupt = corrupt
    with pytest.raises((ValueError, KeyError)): run(x)
    assert x.calls == []


@pytest.mark.parametrize('fault', ['old_id', 'same_native', 'foreign_file', 'foreign_cfg', 'body_owner',
    'face_owner', 'current_pid', 'insert_handle', 'transform', 'new_summary'])
def test_same_name_same_file_does_not_adopt_foreign_or_replaced_new_component_body_face(phase_world, fault):
    x = phase_world
    def corrupt(value, number):
        new = value['current']
        if fault == 'old_id': new['component']['component_id'] = value['original_refs']['component_id']
        elif fault == 'same_native': new['component_native_identity'] = value['original']['component_native_identity']
        elif fault == 'foreign_file': new['component']['referenced_path'] = 'C:/foreign.sldprt'
        elif fault == 'foreign_cfg': new['component']['referenced_configuration'] = 'Другая'
        elif fault == 'body_owner': new['body_owner_native_identity'] += 99
        elif fault == 'face_owner': new['face_owner_native_identity'] += 99
        elif fault == 'current_pid': new['component_persistent_id'] = '00'
        elif fault == 'insert_handle': value['transition_receipt']['native_steps'][1]['evidence']['returned_native_identity'] += 99
        elif fault == 'transform': new['total_transform'][9] += .001
        else: new['body']['name'] = 'Чужая geometry summary'
    x.phase_corrupt = corrupt
    with pytest.raises(ValueError): run(x, 'reinserted')
    assert x.full_calls == 1


def test_expected_exact_code_is_selected_before_request_and_never_adapted_from_sql_error(phase_world):
    x = phase_world
    def corrupt(value, number): value['expected_errors']['component_get'] = 'object_deleted'
    x.phase_corrupt = corrupt
    with pytest.raises(ValueError): run(x, 'deleted', 'component_not_in_active_configuration')
    assert x.phase_calls == 1 and x.full_calls == 1 and x.retained
    assert len([tool for tool, _ in x.calls if tool != 'job_get']) == 1


def test_unknown_actual_runner_failure_has_no_after_capture_or_followup(phase_world):
    x = phase_world
    x.corrupt = lambda *args: (_ for _ in ()).throw(RuntimeError('Unexpected artificial read unknown'))
    # Expected reads fail before result mutation, so inject the actual native
    # component census getter instead, after independent phase proof finishes.
    old_capture = x.prepare_phase
    def prepare(phase, code):
        ctx, old, new, capture = old_capture(phase, code)
        def observed(*args):
            value = capture(*args)
            x.a.components = lambda model: (_ for _ in ()).throw(RuntimeError('Artificial native census pending'))
            return value
        return ctx, old, new, observed
    x.prepare_phase = prepare
    with pytest.raises((ValueError, RuntimeError)): run(x)
    assert x.phase_calls == x.full_calls == 1 and x.retained


def test_current_phase_membership_and_whole_session_must_stay_exact(phase_world):
    x = phase_world
    def corrupt(value, number):
        if number == 2: value['current_instance_census'][0]['native_receipt']['changed'] = True
    x.phase_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.phase_calls == 2 and x.full_calls == 2


@pytest.mark.parametrize('fault', ['phase', 'refs', 'new_for_deleted', 'missing_full', 'missing_phase', 'full_unavailable'])
def test_no_explicit_original_ownership_or_current_native_producers_means_no_read(phase_world, fault):
    x = phase_world; ctx, old, _, capture = x.prepare_phase('deleted', 'component_not_in_active_configuration')
    args = dict(phase='deleted', context=ctx, original_refs=old, capture_full=x.full, capture_phase=capture)
    if fault == 'phase': args['phase'] = 'arbitrary'
    elif fault == 'refs': args['original_refs'] = {}
    elif fault == 'new_for_deleted': args['current_refs'] = old
    elif fault == 'missing_full': args['capture_full'] = None
    elif fault == 'missing_phase': args['capture_phase'] = None
    else: args['capture_full'] = lambda: (_ for _ in ()).throw(ValueError('Unknown current full session'))
    with pytest.raises(ValueError): asyncio.run(helper.component_retirement_phase(x.reader, **args))
    assert x.calls == []
