"""Actual retained production producer with artificial records/getters; no CAD."""
from copy import deepcopy
from pathlib import Path
import sys
from threading import Thread
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.rectangle_snapshot import BASE, SKETCH, validated_rectangle_snapshot
from test_cad_owned_suppression_snapshot import case, extrusion_proof, suppress, Identity

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b2_native_observer as helper
finally:
    sys.path.remove(scripts)


def namespace(snapshot, prefix='1', *, reverse=False):
    result = deepcopy(snapshot)
    binding = result['native_observations']['annotation_view_bindings']
    replacements = {old: 'av_' + prefix + f'{index:031x}' for index, old in enumerate(binding['view_ids'])}
    binding['view_ids'] = [replacements[old] for old in binding['view_ids']]
    binding['dimension_views'] = {axis: replacements[old] for axis, old in binding['dimension_views'].items()}
    if reverse:
        binding['view_ids'].reverse()
        result['clone_state']['display_data']['annotation_views'].reverse()
    return result


@pytest.fixture
def setup(case):
    document_id = 'doc_' + 'a' * 32
    case.current = deepcopy(case.baseline)
    case.generic_calls = []
    case.windows = [(case.model, {'hwnd': 100, 'title': 'Контрольная деталь'})]
    case.adapter.native_close_windows = lambda: list(case.windows)
    def generic(model):
        assert model is case.model
        case.generic_calls.append(True)
        return deepcopy(case.current)
    case.adapter.rectangle_construction_snapshot = generic
    def role(kind, feature, letter):
        index = next(index for index, row in enumerate(case.baseline['clone_state']['features'])
                     if row['native_id'] == feature.row['native_id'])
        return dict(document_id=document_id, configuration='Основная', kind=kind,
            object_id='feat_' + letter * 32, creation_operation_id='original-b1-' + kind,
            native_id=feature.row['native_id'], feature_role='feature:' + str(index),
            persistent_id_hex=feature.pid.hex())
    case.ext_role = role('extrusion', case.binding.feature, 'b')
    case.sketch_role = role('sketch', case.binding.receipt.borrowed_sketch, 'c')
    case.arguments = dict(bridge=dict(document_id=document_id, hwnd=100),
        model_identity=case.model.identity, extrusion_role=case.ext_role, sketch_role=case.sketch_role,
        getters=case.getters, query=case.query)
    return case


def construct(setup, **overrides):
    return helper.AttestationOnly(setup.adapter, setup.model, setup.baseline,
                                  **{**setup.arguments, **overrides})


def delete_fixture(setup, extrusion_proof, *, status=1):
    """Change artificial state; the observer never performs this action."""
    old = setup.binding.feature
    setup.features = [feature for feature in setup.features if feature is not old]
    setup.binding.receipt.borrowed_sketch.row['owner_native_id'] = None
    current = deepcopy(extrusion_proof[0]['snapshots']['target'])
    anchors = {row['role']: row['token'] for row in setup.baseline['references'] if row['kind'] == 'dimension'}
    for row in current['references']:
        if row['kind'] == 'dimension': row['token'] = anchors[row['role']]
    setup.current = validated_rectangle_snapshot(current)
    setup.bodies = []
    original_extension = setup.adapter._extension
    def extension(model):
        prior = original_extension(model)
        def lookup(pid):
            if pid == old.pid:
                setup.native_calls.append(('deleted_raw_pid', pid))
                return None, status
            return prior.GetObjectByPersistReference3(pid)
        return NS(GetObjectByPersistReference3=lookup)
    setup.adapter._extension = extension
    original_identity = setup.adapter.identity
    def identity(value):
        if value is old: raise AssertionError('Deleted extrusion canonical/getter must never be consulted.')
        return original_identity(value)
    setup.adapter.identity = identity
    def forbidden(*args): raise AssertionError('Deleted extrusion getter must never be consulted.')
    old.GetID = old.IsSuppressed2 = old.GetDefinition = forbidden
    setup.getters['extrusion'] = forbidden
    return setup.current


def test_actual_retained_producer_survives_suppressed_empty_dimension_enumeration(setup):
    observer = construct(setup)
    assert type(observer._producer) is helper.OwnedSuppressionSnapshot
    assert not hasattr(observer, 'ownership') and not hasattr(observer, 'delete')
    assert not hasattr(observer, 'set_suppressed') and not hasattr(observer, 'cleanup')
    retained = tuple(item.record for item in observer._producer._dimensions)
    suppress(setup)
    setup.records = []
    result = observer.capture(helper.SUPPRESSED)
    assert tuple(item.record for item in observer._producer._dimensions) == retained
    assert setup.enum_calls == 1 and len(setup.generic_calls) == 2
    assert result['snapshot']['solid_body_count'] == 0
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is result['mutation_authorized'] is False
    assert setup.native_calls[-1] == 'watch_closed'


def test_returned_base_uses_actual_generic_snapshot_and_independent_expected_namespace(setup):
    observer = construct(setup)
    result = observer.capture(BASE, expected_snapshot=namespace(setup.current, reverse=True))
    assert result['snapshot'] == validated_rectangle_snapshot(setup.current) and len(setup.generic_calls) == 4
    assert result['extrusion_membership']['original_canonical_confirmed'] is True
    assert result['comparison']['complete_relation_bijection_verified'] is True
    assert not any(row == ('getter', 'extrusion') for row in setup.native_calls)


@pytest.mark.parametrize('status', [1, 4])
def test_deleted_sketch_never_calls_old_extrusion_getter_and_keeps_current_original_sketch(setup, extrusion_proof, status):
    observer = construct(setup)
    current = delete_fixture(setup, extrusion_proof, status=status)
    result = observer.capture(SKETCH, expected_snapshot=namespace(current))
    assert result['sketch_membership']['original_canonical_confirmed'] is True
    assert result['extrusion_membership']['raw_pid_state'] == status
    assert result['extrusion_membership']['raw_object_is_null'] is True
    assert observer.capture(SKETCH)['snapshot'] == current
    calls_before = list(setup.native_calls)
    with pytest.raises(ValueError, match='Deleted'): observer.capture(helper.SUPPRESSED)
    with pytest.raises(ValueError, match='Deleted'): observer.capture(BASE)
    assert setup.native_calls == calls_before


@pytest.mark.parametrize('fault', ['missing_role', 'foreign_document', 'wrong_kind', 'wrong_role',
    'wrong_native_id', 'bool_native_id', 'wrong_pid', 'uppercase_pid', 'name_object_id',
    'missing_hwnd', 'foreign_hwnd_model', 'foreign_model', 'suppressed_before', 'missing_dimension'])
def test_context_requires_original_current_role_pid_canonical_and_unsuppressed_base(setup, fault):
    if fault == 'missing_role': setup.ext_role.pop('creation_operation_id')
    elif fault == 'foreign_document': setup.ext_role['document_id'] = 'foreign'
    elif fault == 'wrong_kind': setup.ext_role['kind'] = 'sketch'
    elif fault == 'wrong_role': setup.ext_role['feature_role'] = 'feature:0'
    elif fault == 'wrong_native_id': setup.ext_role['native_id'] = 0
    elif fault == 'bool_native_id': setup.ext_role['native_id'] = True
    elif fault == 'wrong_pid': setup.ext_role['persistent_id_hex'] = 'abcd'
    elif fault == 'uppercase_pid': setup.ext_role['persistent_id_hex'] = setup.ext_role['persistent_id_hex'].upper()
    elif fault == 'name_object_id': setup.ext_role['object_id'] = 'Основание'
    elif fault == 'missing_hwnd': setup.windows = []
    elif fault == 'foreign_hwnd_model': setup.windows = [(NS(identity=Identity()), {'hwnd': 100})]
    elif fault == 'foreign_model': setup.arguments['model_identity'] = Identity()
    elif fault == 'suppressed_before': suppress(setup)
    elif fault == 'missing_dimension': setup.records.pop()
    with pytest.raises((ValueError, ExecutionFailure)): construct(setup)


@pytest.mark.parametrize('field', ['extrusion', 'sketch', 'properties', 'configuration_state',
    'auxiliary_data', 'display_data', 'annotations', 'material', 'annotation_view_bindings'])
def test_missing_current_native_getter_data_never_fills_from_base(setup, field):
    observer = construct(setup)
    suppress(setup)
    setup.getter_values[field] = None
    with pytest.raises(ExecutionFailure) as error:
        observer.capture(helper.SUPPRESSED)
    assert error.value.code == 'owned_suppression_snapshot_unavailable' and field in str(error.value)


def test_changed_current_dimension_value_is_actually_captured_not_baseline_fill(setup):
    observer = construct(setup)
    suppress(setup)
    depth = next(item.record for item in observer._producer._dimensions if item.role == 'dimension:depth')
    depth.summary['values_si']['Основная'] = .012
    depth.summary['values']['Основная'] = 12.
    result = observer.capture(helper.SUPPRESSED)
    assert result['snapshot']['clone_state']['parameters']['depth_m'] == .012
    assert observer.baseline['clone_state']['parameters']['depth_m'] == .01


@pytest.mark.parametrize('status', [True, None, 0, 2, 6, '1'])
def test_deleted_pid_requires_exact_typed_deleted_state_with_null(setup, extrusion_proof, status):
    observer = construct(setup)
    delete_fixture(setup, extrusion_proof, status=status)
    with pytest.raises(ValueError, match='typed state1/4'): observer.capture(SKETCH)


@pytest.mark.parametrize('fault', ['raw_present', 'foreign_sketch', 'duplicate_sketch', 'pid_still_member'])
def test_deleted_old_pid_and_current_sketch_independent_membership_fail_closed(setup, extrusion_proof, fault):
    observer = construct(setup)
    delete_fixture(setup, extrusion_proof)
    sketch = setup.binding.receipt.borrowed_sketch
    if fault == 'raw_present':
        setup.adapter._extension = lambda model: NS(GetObjectByPersistReference3=lambda pid: (object(), 1))
    elif fault == 'foreign_sketch': sketch.identity = Identity()
    elif fault == 'duplicate_sketch': setup.features.append(sketch)
    else: setup.features.append(NS(identity=Identity(), pid=setup.binding.feature.pid))
    with pytest.raises(ValueError): observer.capture(SKETCH)


@pytest.mark.parametrize('profile', [BASE, SKETCH, helper.SUPPRESSED])
def test_crossprocess_full_view_row_partition_bijection_preserves_every_other_field(setup, extrusion_proof, profile):
    observer = construct(setup)
    if profile == helper.SUPPRESSED:
        suppress(setup)
        observed = observer.capture(profile)['snapshot']
    elif profile == SKETCH:
        observed = delete_fixture(setup, extrusion_proof)
    else:
        observed = setup.current
    original = deepcopy(observed)
    proof = helper.compare_b2_snapshot(observed, namespace(observed, reverse=True))
    assert proof['complete_relation_bijection_verified'] is True
    assert proof['accepted'] is proof['native_acceptance'] is proof['cleanup_authorized'] is proof['mutation_authorized'] is False
    assert observed == original


@pytest.mark.parametrize('fault', ['shown', 'angle', 'rotation', 'row_multiplicity', 'partition_split',
    'partition_merge', 'primary_anchor', 'properties', 'controls', 'missing_current_field'])
def test_hostile_full_suppressed_comparison_cannot_match_by_view_scalar_or_axis_counts(setup, fault):
    observer = construct(setup)
    suppress(setup)
    observed = observer.capture(helper.SUPPRESSED)['snapshot']
    wrong = namespace(observed)
    data = wrong['clone_state']
    binding = wrong['native_observations']['annotation_view_bindings']
    if fault == 'shown': data['display_data']['annotation_views'][1]['shown'] = True
    elif fault == 'angle': data['display_data']['annotation_views'][1]['angle'] = 1..hex()
    elif fault == 'rotation': data['display_data']['annotation_views'][1]['rotation'][0] = 2..hex()
    elif fault == 'row_multiplicity':
        data['display_data']['annotation_views'].append(deepcopy(data['display_data']['annotation_views'][0]))
        binding['view_ids'].append('av_' + 'f' * 32)
    elif fault == 'partition_split': binding['dimension_views']['width'] = binding['dimension_views']['depth']
    elif fault == 'partition_merge': binding['dimension_views']['depth'] = binding['dimension_views']['width']
    elif fault == 'primary_anchor':
        next(row for row in wrong['references'] if row['kind'] == 'dimension')['token'] += ' '
    elif fault == 'properties': data['properties']['hostile'] = True
    elif fault == 'controls': data['controls']['hostile'] = True
    else: data.pop('auxiliary_data')
    with pytest.raises(ValueError): helper.compare_b2_snapshot(observed, wrong)


@pytest.mark.parametrize('fault', ['namespace_replaced', 'anchor_replaced', 'borrowed_partition'])
def test_matching_public_snapshot_cannot_weaken_local_retained_view_ids_or_anchors(setup, fault):
    observed = deepcopy(setup.current)
    if fault == 'namespace_replaced': observed = namespace(observed)
    elif fault == 'anchor_replaced':
        next(row for row in observed['references'] if row['kind'] == 'dimension')['token'] += ' '
    else:
        links = observed['native_observations']['annotation_view_bindings']['dimension_views']
        links['width'] = links['depth']
    # Same expected server fields alone cannot authorize replacement of this
    # independent adapter's already-retained local identities/primary anchors.
    with pytest.raises(ValueError):
        helper.compare_b2_snapshot(observed, namespace(observed, '2'), previous=setup.baseline)


def test_owner_apartment_refusal_precedes_any_native_capture(setup):
    observer = construct(setup)
    failures = []
    calls = len(setup.generic_calls)
    def other_thread():
        try: observer.capture(BASE)
        except ValueError as error: failures.append(str(error))
    thread = Thread(target=other_thread)
    thread.start(); thread.join(5)
    assert not thread.is_alive() and len(failures) == 1 and 'apartment' in failures[0]
    assert len(setup.generic_calls) == calls


@pytest.mark.parametrize('profile', [BASE, SKETCH, helper.SUPPRESSED])
def test_wrong_actual_state_cannot_be_replaced_by_baseline_or_requested_profile(setup, profile):
    observer = construct(setup)
    if profile == BASE: suppress(setup)
    with pytest.raises((ExecutionFailure, ValueError)):
        observer.capture(profile if profile != BASE else BASE)


def test_observer_only_reads_original_handles_without_mutation_or_address_fallback(setup):
    def forbidden(*args, **kwargs):
        raise AssertionError('Observer must not mutate or address by name/GetID fallback.')
    for feature in setup.features:
        feature.GetID = feature.SetSuppression2 = feature.Select2 = forbidden
    for name in ('ClearSelection2', 'EditRebuild3', 'Save3', 'EditUndo2', 'FeatureByName', 'Parameter'):
        setattr(setup.model, name, forbidden)
    for name in ('activate_document', 'close_document', 'rebuild', 'undo', 'set_application_preferences'):
        setattr(setup.adapter, name, forbidden)
    opening = deepcopy(setup.observed)
    observer = construct(setup)
    observer.capture(BASE)
    suppress(setup)  # Explicit artificial fixture action outside the observer.
    observer.capture(helper.SUPPRESSED)
    assert setup.observed == opening
    assert observer._producer.extrusion is setup.binding.feature
    assert observer._producer.sketch is setup.binding.receipt.borrowed_sketch


@pytest.mark.parametrize('fault', ['configuration', 'model', 'window_missing', 'window_ambiguous'])
def test_lost_original_native_context_is_refused_before_generic_capture(setup, fault):
    observer = construct(setup)
    generic_calls = len(setup.generic_calls)
    if fault == 'configuration': setup.configuration_identity = Identity()
    elif fault == 'model': setup.model.identity = Identity()
    elif fault == 'window_missing': setup.windows = []
    else: setup.windows.append(setup.windows[0])
    with pytest.raises(ValueError): observer.capture(BASE)
    assert len(setup.generic_calls) == generic_calls


@pytest.mark.parametrize('malformed', [None, {}, {'scope': helper.SUPPRESSED_SCOPE}, {'scope': 'foreign'}])
def test_authoritative_comparison_raises_valueerror_for_malformed_snapshots(setup, malformed):
    with pytest.raises(ValueError): helper.compare_b2_snapshot(setup.current, malformed)
