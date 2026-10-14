"""Artificial retained config handles; real catalogs/JobRunner/SQLite gates."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.geometry import GeometryCatalog
from solidworks_mcp.server_v2 import response
from test_b3_component_membership import world

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_configuration_references as helper
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


def steps(method, evidence):
    return dict(transition_id='artificial-original-owner-transition', native_steps=[
        dict(sequence=1, name=method, phase='pending', evidence={'artificial_owner_native_attempt': True}),
        dict(sequence=2, name=method, phase='returned', evidence=evidence),
        dict(sequence=3, name='IModelDoc2.ForceRebuild3', phase='pending', evidence={'artificial_owner_rebuild': True}),
        dict(sequence=4, name='IModelDoc2.ForceRebuild3', phase='returned', evidence={'return_value': True})])


@pytest.fixture
def configuration_world(world):
    x = world; a = x.a; catalog = x.catalog; target = x.originals['variant']
    original_component = catalog.get(**x.context, component_id=x.ids['variant'])['component']
    original_bodies = catalog.bodies(**x.context, component_id=x.ids['variant'])['items']
    body = next(row for row in original_bodies if row['body_type'] == 'solid')
    old_face = catalog.list_topology(**x.context, component_id=x.ids['variant'], body_id=body['body_id'], kind='face')['items'][0]
    old_receipt = x.instance_capture(x.context, original_component)
    old_refs = dict(component_id=x.ids['variant'], body_id=body['body_id'], face_id=old_face['object_id'])
    old_binding = dict(instance_native_identity=old_receipt['native_identity'], instance_persistent_id=old_receipt['persistent_id'],
        model_native_identity=old_receipt['model_identity'], configuration_native_identity=old_receipt['configuration_identity'],
        root_configuration_native_identity=100, referenced_configuration='Вариант', referenced_path=target.info['referenced_path'],
        bodies=deepcopy(original_bodies), native_receipt=old_receipt)
    # Simulate only the normally acknowledged original owner's prior setup;
    # no native setter, fixture action or production mutation API is called.
    target.info['referenced_configuration'] = 'Основная'
    target.bodies.insert(1, a.body())  # Current fake Main census preserves old BREP identities.
    a.models[0].state['update_stamp'] += 1
    doc = x.docs.get(x.context['document_id'], x.context['configuration'])
    x.context['expected_observation_revision'] = doc['observation_revision']
    rows = catalog.list(**x.context)['items']; state = catalog._state(x.entry)
    cid = next(row['component_id'] for row in rows if state['refs'][row['component_id']].native_identity == target.identity)
    x.ids['current_variant'] = cid; x.originals['current_variant'] = target
    component = catalog.get(**x.context, component_id=cid)['component']
    bodies = catalog.bodies(**x.context, component_id=cid)['items']
    selected_body = next(row for row in bodies if state['bodies'][row['body_id']].native_identity == target.bodies[0].identity)
    face = catalog.list_topology(**x.context, component_id=cid, body_id=selected_body['body_id'], kind='face')['items'][0]
    current_receipt = x.instance_capture(x.context, component)
    bindings = []
    for row in bodies:
        current = x.reference_capture(x.context, component, row)
        bindings.append(dict(body_id=row['body_id'], native_identity=current['native_identity'], persistent_id=current['persistent_id'],
            owner_native_identity=current['owner_component_native_identity'], native_receipt=current))
    f = x.reference_capture(x.context, component, face)
    current = dict(instance_native_identity=current_receipt['native_identity'], instance_persistent_id=current_receipt['persistent_id'],
        model_native_identity=current_receipt['model_identity'], configuration_native_identity=current_receipt['configuration_identity'],
        root_configuration_native_identity=100, referenced_configuration='Основная', component=component, bodies=bodies,
        body_bindings=bindings, face=face, face_binding=dict(native_identity=f['native_identity'], persistent_id=f['persistent_id'],
            owner_native_identity=f['owner_body_native_identity'], native_receipt=f),
        total_transform=current_receipt['total_transform'], native_receipt=current_receipt)
    new_refs = dict(component_id=cid, body_id=selected_body['body_id'], face_id=face['object_id'])
    transition = steps('IComponent2.ReferencedConfiguration', dict(owner_native_identity=old_binding['instance_native_identity'],
        requested_configuration='Основная', readback_configuration='Основная'))
    x.phase_calls = 0; x.phase_corrupt = None
    def capture(ctx, old, new):
        x.phase_calls += 1
        assert ctx == x.context and old == old_refs and new == new_refs
        # Actual retained ref/current native configuration explains the precise
        # refusal before the public request; no SQL-result-selected error.
        old_ref = state['refs'][old['component_id']]
        now = a.component_info(target)
        assert old_ref.native_identity == target.identity and old_ref.referenced_configuration != now[0]['referenced_configuration']
        value = dict(context=deepcopy(ctx), original_refs=old, current_refs=new, original=old_binding, current=current,
            expected_errors={tool: 'component_reference_context_changed' for tool in helper.TOOLS}, transition_receipt=transition)
        value = deepcopy(value)
        if x.phase_corrupt: x.phase_corrupt(value, x.phase_calls)
        return value
    x.instance_capture_phase = capture; x.old_refs = old_refs; x.new_refs = new_refs
    return x


def run_instance(x, **overrides):
    args = dict(context=x.context, original_refs=x.old_refs, current_refs=x.new_refs,
        capture_full=x.full, capture_phase=x.instance_capture_phase)
    args.update(overrides)
    return asyncio.run(helper.component_configuration_phase(x.reader, **args))


def test_changed_referenced_configuration_retires_old_ids_and_current_exact_three_body_roster(configuration_world):
    x = configuration_world; result = run_instance(x)
    assert len(result['rows']) == len(x.store.list()['items']) == 9 and x.full_calls == x.phase_calls == 2
    assert all(row['journal']['status'] == 'failed' and row['journal']['error']['code'] == 'component_reference_context_changed' for row in result['rows'][:3])
    assert all(row['journal']['status'] == 'succeeded' for row in result['rows'][3:])
    assert x.old_refs['component_id'] != x.new_refs['component_id']
    old = result['native_before']['original']; new = result['native_before']['current']
    assert old['instance_native_identity'] == new['instance_native_identity'] and old['configuration_native_identity'] != new['configuration_native_identity']
    assert result['before'] == result['after'] and x.retained == []
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False


@pytest.mark.parametrize('fault', ['pending', 'false_rebuild', 'readback', 'foreign_instance', 'foreign_model', 'same_cfg',
    'root_cfg', 'file', 'old_count', 'current_count', 'missing_binding', 'body_owner', 'face_owner', 'native_pid', 'transform'])
def test_original_current_canonical_pid_configuration_full_roster_and_native_receipts_required_before_dispatch(configuration_world, fault):
    x = configuration_world
    def corrupt(value, number):
        new = value['current']
        if fault == 'pending': value['transition_receipt']['native_steps'][1]['phase'] = 'pending'
        elif fault == 'false_rebuild': value['transition_receipt']['native_steps'][-1]['evidence']['return_value'] = False
        elif fault == 'readback': value['transition_receipt']['native_steps'][1]['evidence']['readback_configuration'] = 'Вариант'
        elif fault == 'foreign_instance': new['instance_native_identity'] += 99
        elif fault == 'foreign_model': new['model_native_identity'] += 99
        elif fault == 'same_cfg': new['configuration_native_identity'] = value['original']['configuration_native_identity']
        elif fault == 'root_cfg': new['root_configuration_native_identity'] += 99
        elif fault == 'file': new['component']['referenced_path'] = 'C:/foreign.sldprt'
        elif fault == 'old_count': value['original']['bodies'].pop()
        elif fault == 'current_count': new['bodies'].pop()
        elif fault == 'missing_binding': new['body_bindings'].pop()
        elif fault == 'body_owner': new['body_bindings'][0]['owner_native_identity'] += 99
        elif fault == 'face_owner': new['face_binding']['owner_native_identity'] += 99
        elif fault == 'native_pid': new['instance_persistent_id'] = '00'
        else: new['total_transform'][9] += .001
    x.phase_corrupt = corrupt
    with pytest.raises(ValueError): run_instance(x)
    assert x.calls == []


@pytest.mark.parametrize('fault', ['error_after_result', 'current_summary', 'unknown'])
def test_exact_error_or_current_public_roundtrip_failure_stops_without_after_capture(configuration_world, fault):
    x = configuration_world
    if fault == 'error_after_result':
        x.phase_corrupt = lambda value, number: value['expected_errors'].__setitem__('component_get', 'persistent_reference_mismatch')
    elif fault == 'current_summary':
        x.corrupt = lambda tool, args, value: value['component'].__setitem__('hidden', False) if tool == 'component_get' else None
    else:
        original = x.instance_capture_phase
        def capture(*args):
            value = original(*args); x.a.components = lambda model: (_ for _ in ()).throw(RuntimeError('Artificial unknown current read'))
            return value
        x.instance_capture_phase = capture
    with pytest.raises((ValueError, RuntimeError)): run_instance(x)
    assert x.full_calls == x.phase_calls == 1


@pytest.fixture(params=['active_change', 'incarnation'])
def part_world(world, request):
    x = world; a = x.a; model = a.models[2]; geometry = GeometryCatalog(x.docs)
    a.body(document_index=2); a.body(document_index=2, surface=True)
    original_ctx = deepcopy(x.part_context)
    original_rows = geometry.list(**original_ctx)['items']; old_id = x.part_body
    entry, _ = x.docs.resolve(original_ctx['document_id'], original_ctx['configuration'])
    old_ref = geometry._references(entry)[old_id]; old_cfg = a.configuration_identity(model, original_ctx['configuration'])
    old_native = a.resolve_persistent_id(model, old_ref.persistent_id, 'body')
    ordinals = []
    def ordinal(value):
        for index, old in enumerate(ordinals):
            if old == value: return index+1
        ordinals.append(value); return len(ordinals)
    old = dict(object_id=old_id, configuration=old_ref.configuration, model_native_identity=ordinal(model.identity),
        configuration_native_identity=ordinal(old_cfg), reference_configuration_native_identity=ordinal(old_ref.configuration_identity),
        body_native_identity=ordinal(old_native.identity), body_persistent_id=old_ref.persistent_id.hex(),
        native_receipt=dict(artificial_original_current_reference=old_id, config=old_ref.configuration))
    # Prior acknowledged original owner setup is simulated in fake state only.
    if request.param == 'active_change':
        model.state['active_configuration'] = 'Вариант'
        current = a.objects[model.identity]; a.objects[model.identity] = [current[0], current[-1]]
        method = 'IModelDoc2.ShowConfiguration2'
    else:
        a.configurations[model.identity, 'Основная'] = object()
        method = 'IModelDoc2.AddConfiguration3'
    model.state['update_stamp'] += 1
    metadata = x.docs.get(original_ctx['document_id'], model.state['active_configuration'])
    ctx = dict(document_id=metadata['document_id'], configuration=metadata['active_configuration'], expected_observation_revision=metadata['observation_revision'])
    inactive = 'Основная' if ctx['configuration'] == 'Вариант' else 'Вариант'
    current_rows = geometry.list(**ctx)['items']; cfg = a.configuration_identity(model, ctx['configuration'])
    new = dict(configuration=ctx['configuration'], model_native_identity=ordinal(model.identity), configuration_native_identity=ordinal(cfg),
        bodies=current_rows, body_bindings=[dict(object_id=row['object_id'], native_identity=ordinal(a.resolve_persistent_id(model, geometry._references(entry)[row['object_id']].persistent_id, 'body').identity),
            persistent_id=geometry._references(entry)[row['object_id']].persistent_id.hex(), model_native_identity=ordinal(model.identity),
            native_receipt={'artificial_actual_part_membership': True}) for row in current_rows],
        native_receipt=dict(artificial_current_config=ctx['configuration'],
            native_body_pids=[body.persistent_id.hex() for body in a.bodies(model, 'all')]))
    evidence = dict(readback_configuration=ctx['configuration'])
    if method.endswith('ShowConfiguration2'): evidence.update(owner_native_identity=new['model_native_identity'], return_value=True)
    else: evidence['returned_native_identity'] = new['configuration_native_identity']
    transition = steps(method, evidence); x.part_phase_calls = 0; x.part_corrupt = None
    original_call = x.client.call_tool
    async def call(tool, args):
        if tool not in ('body_list', 'geometry_get'): return await original_call(tool, args)
        x.calls.append((tool, deepcopy(args))); spec = SPECS[tool]; payload = spec.payload(args)
        method = geometry.list if tool == 'body_list' else geometry.get
        job = x.runner.submit(args['request_id'], spec.operation, payload['arguments'], lambda: method(**payload['arguments']),
            context=payload['context'], mutates=False)
        return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
            context=job['payload']['context'], data=job['result'], error=job['error']).model_dump(mode='json'))
    x.client.call_tool = call
    def capture(context, original_body, inactive_configuration):
        x.part_phase_calls += 1
        assert context == ctx and original_body == old_id and inactive_configuration == inactive
        # The actual retained GeometryCatalog ref still records the previous
        # config identity, while native current config identity differs.
        assert old_ref.configuration_identity != a.configuration_identity(model, ctx['configuration'])
        value = dict(context=ctx, original_body_id=old_id, inactive_configuration=inactive,
            active_configuration=a.snapshot(model)['active_configuration'], original=old, current=new,
            expected_errors=dict(geometry_get='object_configuration_mismatch', body_list='configuration_not_active'),
            transition_method=method, transition_receipt=transition)
        value = deepcopy(value)
        if x.part_corrupt: x.part_corrupt(value, x.part_phase_calls)
        return value
    original_full = x.full
    def full():
        value = original_full()
        value['artificial_current_part_brep'] = [dict(pid=body.persistent_id.hex(), native_identity=ordinal(body.identity),
            summary=a.geometry_summary(body, 'body'), face_pids=[face.persistent_id.hex() for face in body.faces]) for body in a.bodies(model, 'all')]
        return value
    x.part_args = dict(context=ctx, original_body_id=old_id, inactive_configuration=inactive, capture_full=full, capture_phase=capture)
    x.part_model = model
    return x


def test_old_part_reference_incarnation_and_inactive_geometry_exact_finite_fail_without_switch(part_world):
    x = part_world; initial = deepcopy(x.part_model.state)
    inactive = x.docs.get(x.part_args['context']['document_id'], x.part_args['inactive_configuration'])
    assert inactive['configuration_is_active'] is False
    assert inactive['active_configuration'] == x.part_args['context']['configuration']
    result = asyncio.run(helper.part_configuration_phase(x.reader, **x.part_args))
    assert len(result['rows']) == len(x.store.list()['items']) == 2 and x.full_calls == x.part_phase_calls == 2
    assert [row['journal']['error']['code'] for row in result['rows']] == ['object_configuration_mismatch', 'configuration_not_active']
    assert all(row['journal']['status'] == 'failed' and row['journal']['result'] is None for row in result['rows'])
    assert x.part_model.state == initial and result['before'] == result['after'] and x.retained == []
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False


@pytest.mark.parametrize('fault', ['old_ref_cfg', 'old_ref_id', 'foreign_model', 'same_cfg', 'active', 'body_count', 'body_owner',
    'native_pending', 'readback', 'changed', 'wrong_error'])
def test_part_original_ref_current_native_incarnation_full_census_and_no_activation_proof_required(part_world, fault):
    x = part_world
    def corrupt(value, number):
        old, new = value['original'], value['current']
        if fault == 'old_ref_cfg': old['reference_configuration_native_identity'] += 99
        elif fault == 'old_ref_id': old['object_id'] = 'foreign'
        elif fault == 'foreign_model': new['model_native_identity'] += 99
        elif fault == 'same_cfg': new['configuration_native_identity'] = old['configuration_native_identity']
        elif fault == 'active': value['active_configuration'] = value['inactive_configuration']
        elif fault == 'body_count': new['bodies'].pop()
        elif fault == 'body_owner': new['body_bindings'][0]['model_native_identity'] += 99
        elif fault == 'native_pending': value['transition_receipt']['native_steps'][1]['phase'] = 'pending'
        elif fault == 'readback': value['transition_receipt']['native_steps'][1]['evidence']['readback_configuration'] = 'foreign'
        elif fault == 'changed' and number == 2: new['native_receipt']['changed'] = True
        elif fault == 'wrong_error': value['expected_errors']['geometry_get'] = 'object_reference_not_found'
    x.part_corrupt = corrupt
    with pytest.raises(ValueError): asyncio.run(helper.part_configuration_phase(x.reader, **x.part_args))
    assert x.calls == [] or fault == 'changed'


def test_whole_current_original_instance_session_preservation_difference_rejects(configuration_world):
    x = configuration_world; original = x.full
    def full():
        value = original()
        if x.full_calls == 2: value['artificial_native_full_session']['models'][0]['metadata']['active_configuration'] = 'Вариант'
        return value
    with pytest.raises(ValueError): run_instance(x, capture_full=full)
    assert x.full_calls == 2


@pytest.mark.parametrize('fault', ['same_refs', 'missing_full', 'missing_phase', 'full_unknown'])
def test_missing_explicit_current_original_owner_scope_prevents_any_dispatch(configuration_world, fault):
    x = configuration_world; overrides = {}
    if fault == 'same_refs': overrides['current_refs'] = x.old_refs
    elif fault == 'missing_full': overrides['capture_full'] = None
    elif fault == 'missing_phase': overrides['capture_phase'] = None
    else: overrides['capture_full'] = lambda: (_ for _ in ()).throw(ValueError('Whole current native scope unavailable'))
    with pytest.raises(ValueError): run_instance(x, **overrides)
    assert x.calls == []
