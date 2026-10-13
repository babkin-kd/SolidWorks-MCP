"""Artificial native records/getters only; no COM connection or acceptance."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_owned_suppression_snapshot import OwnedSuppressionSnapshot, SCOPE, ROLES
from solidworks_mcp.jobs import ExecutionFailure, _json
from test_rectangle_extrusion_postconditions import proof as extrusion_proof


class Identity:
    __hash__ = None


@pytest.fixture(params=['direct', 'display'])
def case(request, extrusion_proof):
    _, after, _ = extrusion_proof
    baseline = deepcopy(after['snapshots']['target'])
    cfg = 'Основная'
    model = NS(identity=Identity(), GetUnits=lambda: [0, 0, 0, 0, False, 0])
    configuration_identity = Identity()
    observed = dict(document_type='part', path='', configurations=[cfg], active_configuration=cfg,
                    title='Контрольная деталь', update_stamp=4)
    features = [NS(identity=Identity(), row=deepcopy(row)) for row in baseline['clone_state']['features']]
    for feature in features:
        feature.IsSuppressed2 = lambda *args, f=feature: [f.row['suppressed']]
    raw_by_pid = {}
    for reference in baseline['references']:
        if reference['kind'] == 'feature':
            feature = features[int(reference['role'].removeprefix('feature:'))]
            feature.pid = bytes.fromhex(reference['token']); raw_by_pid[feature.pid] = feature
    sketch = next(f for f in features if f.row['feature_type'] == 'ProfileFeature')
    extrusion = next(f for f in features if f.row['feature_type'] in ('Boss','Extrusion'))
    body_pid = bytes.fromhex(next(row['token'] for row in baseline['references'] if row['kind'] == 'body'))
    body = NS(identity=Identity(), pid=body_pid)
    raw_by_pid[body_pid] = body
    qualified = baseline['native_observations']['qualified_dimensions']
    records = []
    for qualified_row in qualified:
        role = qualified_row['role']
        owner = extrusion if role == 'dimension:depth' else sketch
        dim = NS(identity=Identity(), owner=owner, GetFeatureOwner=lambda current=owner: current)
        display = NS(identity=Identity(), pid=(role + '-display').encode(), GetType=lambda: 2,
                     GetDimension2=lambda index, current=dim: current)
        record = NS(dimension=dim, owner=owner, owner_tree_identity=owner.identity,
                    displays=[display], display_slots=[(display,0)])
        original_reference = next(row for row in baseline['references'] if row['kind'] == 'dimension' and row['role'] == role)
        import json
        original = json.loads(original_reference['token'])
        dim.pid = bytes.fromhex(original['dimension_pid_hex'])
        if request.param == 'display':
            record.anchor = dict(strategy='display_dimension_v1', display_pid_hex=display.pid.hex(),
                owner_pid_hex=owner.pid.hex(), dimension_index=0, display_type=2)
            raw_by_pid[display.pid] = display
        else:
            record.anchor = original
            raw_by_pid[dim.pid] = dim
        original_reference['token'] = _json(record.anchor)
        source = next(row for row in baseline['clone_state']['dimensions'] if row['full_name'] == {'reference_role':role})
        source.update(parameter_type=0, values={cfg: source['values_si'][cfg] * 1000.},
            display_dimensions=[dict(type=2, linked=False, linked_text='')], tolerance={'type':0,'values_si':[]})
        record.summary = {**deepcopy(source), 'full_name':qualified_row['full_name'], 'owner_update_stamp':4}
        records.append(record)
    state = NS(model=model, configuration_identity=configuration_identity, observed=observed,
        features=features, bodies=[body], records=records, raw_by_pid=raw_by_pid,
        status=0, override_raw=None, override_pid=None, enum_calls=0, native_calls=[], events=0,
        baseline=baseline, annotations_available=True)
    class Adapter:
        def identity(self, value): return value.identity
        def configuration_identity(self, model, configuration): return state.configuration_identity
        def snapshot(self, model): return deepcopy(state.observed)
        def features(self, model): return list(state.features)
        def feature_summary(self, feature): return deepcopy(feature.row)
        def persistent_id(self, model, value): return getattr(value, 'pid', b'')
        def resolve_persistent_id(self, model, pid, kind):
            value = raw_by_pid[pid]
            if getattr(value, 'row', {}).get('suppressed') is True:
                raise ExecutionFailure('object_suppressed', 'Artificial normally returned refusal.')
            return value
        def bodies(self, model, kind): return state.bodies
        def dimensions(self, model, features):
            state.enum_calls += 1
            return list(state.records)
        def dimension_object(self, record): return record.dimension
        def dimension_persistent_id(self, model, record): return deepcopy(record.anchor)
        def dimension_same_persistent_id(self, model, left, right): return left == right
        def dimension_reference_is_current(self, model, record, anchor): return True
        def resolve_dimension_id(self, model, anchor):
            return next(record.dimension for record in records if record.anchor == anchor)
        def dimension_summary(self, record, configurations): return deepcopy(record.summary)
        def dimension_geometry_snapshot(self, model): return {'representation':'planar_polyhedral_brep_v1','bodies':[]}
        def dimension_context(self, model): return deepcopy(state.context)
        def feature_deletion_context(self, model): return deepcopy(baseline['clone_state']['equation_reference_inventory'])
        def feature_external_references(self, features): return deepcopy(baseline['clone_state']['feature_external_reference_inventory'])
        def feature_dependencies(self, features): return deepcopy(baseline['clone_state']['dependencies'])
        def reference_plane_transform(self, feature): return [1. if i in (0,4,8,12) else 0. for i in range(16)]
        def part_creation_controls(self, model): return deepcopy(baseline['clone_state']['creation_controls'])
        def watch_part(self, model): return NS(poll=lambda:state.events, close=lambda:state.native_calls.append('watch_closed'))
        def _persistent_variant(self, pid): return pid
        def _extension(self, model):
            def lookup(pid):
                state.native_calls.append(('raw_pid',pid))
                raw = state.override_raw if pid == state.override_pid else raw_by_pid.get(pid)
                return raw, state.status if pid in {bytes.fromhex(record.anchor.get('dimension_pid_hex',record.anchor.get('display_pid_hex'))) for record in records} else 2
            return NS(GetObjectByPersistReference3=lookup)
    state.adapter = Adapter()
    state.context = {**deepcopy(baseline['clone_state']['controls']), 'active_document':True, 'read_only':False}
    binding = NS(configuration=cfg, kind='extrusion', model=model, model_identity=model.identity,
        configuration_identity=configuration_identity, feature=extrusion, feature_identity=extrusion.identity,
        persistent_id=extrusion.pid, native_id=extrusion.row['native_id'],
        receipt=NS(borrowed_sketch=sketch, borrowed_sketch_identity=sketch.identity))
    state.binding = binding
    def query(raw, interface):
        state.native_calls.append(('query',interface))
        return raw
    state.query = query
    getter_values = {key:deepcopy(baseline['clone_state'][key]) for key in
        ('extrusion','sketch','properties','configuration_state','auxiliary_data','display_data','annotations')}
    getter_values['extrusion']['AutoSelect'] = False
    for relation in getter_values['sketch']['relations']:
        if type(relation['dimension_full_name']) is dict:
            role = relation['dimension_full_name']['reference_role']
            relation['dimension_full_name'] = next(row['full_name'] for row in qualified if row['role'] == role)
    getter_values['material'] = ('','')
    getter_values['selection_count'] = 0
    getter_values['annotation_view_bindings'] = deepcopy(baseline['native_observations']['annotation_view_bindings'])
    getters = {}
    for field in getter_values:
        def getter(*args, field=field):
            state.native_calls.append(('getter',field))
            if field in ('sketch','annotations'):
                destination = args[-1]
                kinds = {'sketch_point','sketch_segment'} if field == 'sketch' else {'annotation'}
                destination.extend(deepcopy(row) for row in baseline['references'] if row['kind'] in kinds)
            return deepcopy(getter_values[field])
        getters[field] = getter
    state.getters, state.getter_values = getters, getter_values
    return state


def construct(case):
    return OwnedSuppressionSnapshot(case.adapter, case.model, case.binding, case.baseline,
                                   getters=case.getters, query=case.query)


def suppress(case):
    case.binding.feature.row['suppressed'] = True
    case.bodies = []
    case.status = 2
    key = '$СОСТОЯНИЕ@' + case.binding.feature.row['name']
    case.getter_values['configuration_state']['parameters'].append([key,'Пог'])


def test_original_three_primary_records_survive_disappearing_enumeration_without_baseline_fill(case):
    producer = construct(case)
    retained = tuple(item.record for item in producer._dimensions)
    suppress(case)
    case.records = []  # Suppression may remove dimensions from traversal.
    result = producer.capture()
    assert case.enum_calls == 1
    assert tuple(item.record for item in producer._dimensions) == retained
    assert result['scope'] == SCOPE and result['solid_body_count'] == 0
    assert {row['full_name']['reference_role'] for row in result['clone_state']['dimensions']} == ROLES
    assert all(row['primary_pid_state'] == 2 for row in result['native_observations']['retained_dimension_membership'])
    assert 'body' not in result['clone_state'] and 'body_material' not in result['clone_state']
    assert result['native_observations']['body_intrinsics']['availability'] == 'unavailable_current_body_absent_v1'
    assert not hasattr(producer,'set_suppressed') and not hasattr(producer,'cleanup')
    assert case.native_calls[-1] == 'watch_closed'


def test_current_depth_values_and_tolerances_are_read_from_original_record_not_baseline(case):
    producer = construct(case); suppress(case)
    record = next(item.record for item in producer._dimensions if item.role == 'dimension:depth')
    record.summary['values_si']['Основная'] = .012
    record.summary['values']['Основная'] = 12.
    record.summary['tolerance'] = {'type':1,'values_si':[-.0001,.0002]}
    result = producer.capture()
    depth = next(row for row in result['clone_state']['dimensions'] if row['full_name'] == {'reference_role':'dimension:depth'})
    assert depth['values_si']['Основная'] == .012 and depth['tolerance']['type'] == 1
    assert result['clone_state']['parameters']['depth_m'] == .012
    assert producer.baseline['clone_state']['parameters']['depth_m'] == .01


@pytest.mark.parametrize('field', ['extrusion','sketch','properties','configuration_state','auxiliary_data',
    'display_data','annotations','material','selection_count','annotation_view_bindings'])
def test_missing_actual_inventory_is_a_specific_gate_without_baseline_substitution(case, field):
    producer = construct(case); suppress(case)
    case.getter_values[field] = None
    with pytest.raises(ExecutionFailure) as error: producer.capture()
    assert error.value.code == 'owned_suppression_snapshot_unavailable' and field in str(error.value)
    assert case.native_calls[-1] == 'watch_closed'


@pytest.mark.parametrize('status', [True, None, 1, 4, 6, '2'])
def test_primary_dimension_membership_requires_exact_returned_raw_state0_or2(case, status):
    producer = construct(case); suppress(case); case.status = status
    with pytest.raises(ExecutionFailure, match='PRIMARY PID'): producer.capture()


@pytest.mark.parametrize('fault', ['null','foreign','owner','retained_record','display_inventory'])
def test_primary_membership_refuses_alias_replacement_and_lost_original_owner(case, fault):
    producer = construct(case); suppress(case)
    item = producer._dimensions[0]
    if fault in ('null','foreign'):
        case.override_pid = bytes.fromhex(item.anchor.get('dimension_pid_hex',item.anchor.get('display_pid_hex')))
        case.override_raw = None if fault == 'null' else NS(identity=Identity(), GetType=lambda:2,
            GetDimension2=lambda index:item.record.dimension)
    elif fault == 'owner': item.record.dimension.owner.identity = Identity()
    elif fault == 'retained_record': item.record.dimension.identity = Identity()
    else: item.record.displays = []
    with pytest.raises(ExecutionFailure): producer.capture()


@pytest.mark.parametrize('fault', ['missing_record','anchor','no_current','foreign_owner','duplicate'])
def test_before_retention_requires_exact_original_three_pid_roles_not_names_or_getid(case, fault):
    if fault == 'missing_record': case.records.pop()
    elif fault == 'anchor': case.records[0].anchor['strategy'] = 'name_lookup'
    elif fault == 'no_current': case.adapter.dimension_reference_is_current = lambda *args:False
    elif fault == 'foreign_owner': case.records[0].owner_tree_identity = Identity()
    else: case.records[1] = case.records[0]
    with pytest.raises(ExecutionFailure): construct(case)


def test_constructor_requires_current_unsuppressed_base_and_current_dimension_values(case):
    case.records[0].summary['values_si']['Основная'] += .001
    with pytest.raises(ExecutionFailure, match='supplied current BASE'): construct(case)
    case.records[0].summary['values_si']['Основная'] -= .001
    case.binding.feature.row['suppressed'] = True
    with pytest.raises(ExecutionFailure, match='before suppression'): construct(case)


@pytest.mark.parametrize('fault', ['model','configuration','feature','sketch','saved','bodies','geometry','features','events'])
def test_reconnect_changed_native_target_and_incomplete_bodyless_boundary_refuse(case, fault):
    producer = construct(case); suppress(case)
    if fault == 'model': case.model.identity = Identity()
    elif fault == 'configuration': case.configuration_identity = Identity()
    elif fault == 'feature': case.binding.feature.identity = Identity()
    elif fault == 'sketch': case.binding.receipt.borrowed_sketch.identity = Identity()
    elif fault == 'saved': case.observed['path'] = 'C:\\part.sldprt'
    elif fault == 'bodies': case.bodies = [object()]
    elif fault == 'geometry': case.adapter.dimension_geometry_snapshot = lambda *args:None
    elif fault == 'features': case.features.pop()
    else:
        prior = case.getters['properties']
        def change(*args):
            result = prior(*args); case.events += 1; return result
        case.getters['properties'] = change
    with pytest.raises(ExecutionFailure): producer.capture()


def test_no_default_dimension_name_parameter_getter_is_ever_used(case):
    case.model.Parameter = lambda name: pytest.fail('Names cannot be primary addressing, including stale D1.')
    producer = construct(case); suppress(case)
    assert producer.capture()['clone_state']['parameters']['depth_m'] == .01


@pytest.mark.parametrize('field,value', [('read_only','unknown'), ('linked',None), ('values_si',{'Основная':float('nan')}),
    ('display_dimensions',None), ('tolerance',{'type':1,'values_si':None})])
def test_unavailable_retained_dimension_metadata_is_not_filled_from_original_base(case, field, value):
    producer = construct(case); suppress(case)
    producer._dimensions[0].record.summary[field] = value
    with pytest.raises(ExecutionFailure): producer.capture()


@pytest.mark.parametrize('fault', ['annotations_empty','annotation_refs','controls_partial','properties_partial',
    'auxiliary_partial','units_null','planes_partial','material_partial','body_array_null'])
def test_partial_arrays_and_dropped_profile_inventory_fields_are_explicit_producer_gates(case, fault):
    producer = construct(case); suppress(case)
    if fault == 'annotations_empty': case.getter_values['annotations'] = []
    elif fault == 'annotation_refs':
        case.getters['annotations'] = lambda *args:deepcopy(case.getter_values['annotations'])
    elif fault == 'controls_partial': case.context.pop(next(iter(case.context)))
    elif fault == 'properties_partial': case.getter_values['properties'].pop('Основная')
    elif fault == 'auxiliary_partial': case.getter_values['auxiliary_data'].pop(next(iter(case.getter_values['auxiliary_data'])))
    elif fault == 'units_null': case.model.GetUnits = lambda:None
    elif fault == 'planes_partial': case.adapter.reference_plane_transform = lambda *args:[0.]*15
    elif fault == 'material_partial': case.getter_values['material'] = ['']
    else: case.bodies = None
    with pytest.raises(ExecutionFailure) as error: producer.capture()
    assert error.value.code == 'owned_suppression_snapshot_unavailable'


def test_current_base_can_already_have_new_depth_before_context_is_retained(case):
    depth = next(record for record in case.records if record.summary['name'] == 'Толщина')
    depth.summary['values_si']['Основная'] = .012
    depth.summary['values']['Основная'] = 12.
    baseline_depth = next(row for row in case.baseline['clone_state']['dimensions']
                          if row['full_name'] == {'reference_role':'dimension:depth'})
    baseline_depth['values_si']['Основная'] = .012
    baseline_depth['values']['Основная'] = 12.
    case.baseline['clone_state']['parameters']['depth_m'] = .012
    producer = construct(case); suppress(case)
    assert producer.capture()['clone_state']['parameters']['depth_m'] == .012


def test_annotation_view_reader_receives_only_reproved_original_records_after_enumeration_is_empty(case):
    producer = construct(case); suppress(case)
    case.records = []
    seen = []
    def getter(adapter, model, display, dimension_roles):
        records = adapter.dimensions(model, adapter.features(model))
        assert tuple(records) == tuple(item.record for item in producer._dimensions)
        assert set(dimension_roles.values()) == {'width','height','depth'}
        assert adapter is not case.adapter
        seen.extend(records)
        return deepcopy(case.getter_values['annotation_view_bindings'])
    case.getters['annotation_view_bindings'] = getter
    assert producer.capture()['solid_body_count'] == 0
    assert len(seen) == 3 and case.enum_calls == 1
