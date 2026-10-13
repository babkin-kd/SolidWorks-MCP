"""Artificial QueryInterface/native feature census; no COM or CAD execution."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b2_plane_birth import OriginalFeature, NativePlaneBridge, bind_returned_plane, E_NOINTERFACE
finally:
    sys.path.remove(scripts)


class QueryFailure(Exception):
    def __init__(self, hresult): self.hresult = hresult


@pytest.fixture
def birth():
    original = [NS(canonical=object(), kind='Boss'), NS(canonical=object(), kind='ProfileFeature')]
    for feature in original:
        feature.GetTypeName2 = lambda feature=feature: feature.kind
        feature.GetID = lambda: (_ for _ in ()).throw(AssertionError('GetID is not birth identity'))
    specific = NS(canonical=object(), interface='IRefPlane')
    feature = NS(canonical=object(), kind='RefPlane', specific=specific, interface='IFeature')
    feature.GetTypeName2 = lambda: feature.kind
    feature.GetSpecificFeature2 = lambda: feature.specific
    feature.GetID = lambda: (_ for _ in ()).throw(AssertionError('No index/GetID adoption'))
    x = NS(original=original, anchors=tuple(OriginalFeature(f, f.canonical) for f in original),
           feature=feature, specific=specific, current=[original[0], feature, original[1]],
           query_calls=[], query_fault=None, interface_override=None)
    def query(raw, interface):
        x.query_calls.append((raw, interface))
        if x.query_fault: return x.query_fault(raw, interface)
        if x.interface_override is not None: return x.interface_override
        if raw.interface != interface: raise QueryFailure(E_NOINTERFACE)
        return raw
    x.query = query
    return x


def run(x, returned=None, **overrides):
    args = dict(returned=x.feature if returned is None else returned, originals=x.anchors,
                current_features=x.current, query=x.query, wrap=lambda raw, interface: raw, identity=lambda raw: raw.canonical)
    args.update(overrides)
    return bind_returned_plane(**args)


@pytest.mark.parametrize('interface', ['feature', 'specific'])
def test_exact_returned_interface_binds_only_sole_new_reference_plane_and_retains_feature(birth, interface):
    x = birth; result = run(x, x.feature if interface == 'feature' else x.specific)
    assert result.feature is x.feature and result.feature_canonical is x.feature.canonical
    assert result.evidence['interface_path'] == ('returned_feature_v1' if interface == 'feature' else 'returned_specific_plane_v1')
    assert result.evidence['accepted'] is result.evidence['native_acceptance'] is result.evidence['cleanup_authorized'] is False
    with pytest.raises(FrozenInstanceError): result.feature = x.original[0]
    # A later normally returned rebuild can yield a different specific wrapper.
    # Birth anchored the feature beforehand; it never reruns/adopts the new one.
    x.feature.specific = NS(canonical=object(), interface='IRefPlane')
    assert result.feature is x.feature and result.feature_canonical is x.feature.canonical


@pytest.mark.parametrize('position', [0, 2])
def test_addition_location_is_not_addressing_and_old_relative_order_must_survive(birth, position):
    x = birth; x.current = list(x.original); x.current.insert(position, x.feature)
    assert run(x).feature is x.feature


@pytest.mark.parametrize('fault', ['old_return', 'foreign_feature', 'foreign_specific', 'queried_different_canonical',
    'specific_none', 'specific_foreign', 'wrong_kind', 'original_replaced', 'original_changed', 'old_order',
    'duplicate_original', 'extra_addition', 'missing_original', 'unknown_feature_query', 'unknown_specific_query',
    'none_feature_query', 'changed_during_query', 'old_order_during_query'])
def test_foreign_unrelated_changed_or_unacknowledged_birth_never_adopted_or_fallback(birth, fault):
    x = birth; returned = x.feature
    if fault == 'old_return':
        returned = x.original[0]; returned.interface = 'IFeature'
    elif fault == 'foreign_feature': returned = NS(canonical=object(), interface='IFeature')
    elif fault == 'foreign_specific': returned = NS(canonical=object(), interface='IRefPlane')
    elif fault == 'queried_different_canonical': x.interface_override = NS(canonical=object(), interface='IFeature')
    elif fault == 'specific_none': returned = x.specific; x.feature.specific = None
    elif fault == 'specific_foreign': returned = x.specific; x.feature.specific = NS(canonical=object(), interface='IRefPlane')
    elif fault == 'wrong_kind': x.feature.kind = 'Boss'
    elif fault == 'original_replaced': x.current[0] = NS(canonical=object())
    elif fault == 'original_changed': x.original[0].canonical = object()
    elif fault == 'old_order': x.current = [x.original[1], x.feature, x.original[0]]
    elif fault == 'duplicate_original': x.current = [x.original[0], x.feature, x.original[0]]
    elif fault == 'extra_addition': x.current.append(NS(canonical=object()))
    elif fault == 'missing_original': x.current.pop()
    elif fault.startswith('unknown_'):
        def query(raw, interface):
            if fault == 'unknown_feature_query' or interface == 'IRefPlane': raise QueryFailure(-2147418111)
            raise QueryFailure(E_NOINTERFACE)
        x.query_fault = query
    elif fault == 'none_feature_query': x.query_fault = lambda *args: None
    else:
        def query(raw, interface):
            if fault == 'changed_during_query': x.original[0].canonical = object()
            else: x.current[:] = [x.original[1], x.feature, x.original[0]]
            return raw
        x.query_fault = query
    with pytest.raises((ValueError, QueryFailure)): run(x, returned)
    if fault in ('old_return', 'foreign_feature', 'queried_different_canonical', 'none_feature_query'):
        assert [interface for _, interface in x.query_calls] == ['IFeature']


def test_unknown_query_hresult_propagates_exactly_without_specific_fallback(birth):
    x = birth; error = QueryFailure(-2147418111)
    def query(raw, interface): raise error
    with pytest.raises(QueryFailure) as caught: run(x, query=query)
    assert caught.value is error


def test_only_exact_enointerface_permits_specific_path_and_queried_raw_canonical_must_match(birth):
    x = birth
    def query(raw, interface):
        if interface == 'IFeature': raise QueryFailure(E_NOINTERFACE)
        return NS(canonical=object())
    with pytest.raises(ValueError, match='raw returned canonical'): run(x, x.specific, query=query)


def test_wrapped_current_feature_canonical_cannot_be_replaced_by_same_name(birth):
    x = birth
    foreign = NS(canonical=object(), Name='Та же плоскость', GetTypeName2=lambda: 'RefPlane')
    with pytest.raises(ValueError): run(x, wrap=lambda raw, interface: foreign if raw is x.feature else raw)


def test_empty_or_incomplete_original_census_never_invokes_query(birth):
    x = birth
    with pytest.raises(ValueError): run(x, originals=())
    assert x.query_calls == []


@pytest.mark.parametrize('comparison', ['raw_only', 'current_only', 'neither', 'null'])
def test_failed_feature_binding_preserves_each_comparison_without_fallback_or_acceptance(birth, comparison):
    x = birth
    returned = NS(canonical=object(), interface='IFeature')
    canonical = {'raw_only': returned.canonical, 'current_only': x.feature.canonical,
                 'neither': object(), 'null': None}[comparison]
    x.interface_override = NS(canonical=canonical) if comparison != 'null' else None
    if comparison == 'null': x.query_fault = lambda *args: None
    diagnostic = {}
    with pytest.raises(ValueError, match='Queried feature'):
        run(x, returned, diagnostic=diagnostic)
    assert diagnostic['phase'] == 'feature_comparison'
    assert diagnostic['raw_equals_current_feature'] is False
    assert diagnostic['raw_equals_queried_feature'] is (comparison == 'raw_only')
    assert diagnostic['queried_feature_equals_current_feature'] is (comparison == 'current_only')
    assert diagnostic['queried_feature_nonnull'] is (comparison != 'null')
    assert diagnostic['accepted'] is diagnostic['native_acceptance'] is diagnostic['cleanup_authorized'] is False
    assert [interface for _, interface in x.query_calls] == ['IFeature']


def test_diagnostic_uses_same_native_reads_as_binding_without_diagnostic(birth):
    x = birth; calls = []
    def identity(raw):
        calls.append(raw)
        return raw.canonical
    run(x, identity=identity)
    original = list(calls); calls.clear()
    diagnostic = {}
    run(x, identity=identity, diagnostic=diagnostic)
    assert len(calls) == len(original) and all(left is right for left, right in zip(calls, original))
    assert diagnostic['phase'] == 'bound' and diagnostic['binding_confirmed'] is True
    assert diagnostic['accepted'] is False


def test_query_error_diagnostic_preserves_hresult_and_original_exception(birth):
    error = QueryFailure(-2147418111); diagnostic = {}
    def query(*args): raise error
    with pytest.raises(QueryFailure) as caught: run(birth, query=query, diagnostic=diagnostic)
    assert caught.value is error and diagnostic['feature_query_hresult'] == error.hresult
    assert diagnostic['feature_query_returned'] is False and diagnostic['accepted'] is False


@pytest.fixture
def bridged_birth(birth):
    x = birth
    x.returned = NS(canonical=object(), interface='IRefPlane', pid=b'actual-plane-pid')
    x.feature.pid = x.specific.pid = x.returned.pid
    x.bridge_calls = []
    def persistent_id(raw):
        x.bridge_calls.append(('pid', raw))
        return raw.pid
    def resolve_feature(pid):
        x.bridge_calls.append(('resolve', pid))
        assert pid == x.feature.pid
        return x.feature
    def is_same(left, right):
        x.bridge_calls.append(('same', left, right))
        assert left is x.returned and right is x.specific
        return 1
    x.bridge = NativePlaneBridge(persistent_id, resolve_feature, is_same)
    return x


def run_bridge(x, **overrides):
    return run(x, x.returned, native_bridge=overrides.pop('native_bridge', x.bridge), **overrides)


def assert_no_feature_query(x):
    assert all(interface == 'IRefPlane' for _, interface in x.query_calls)


def test_explicit_bridge_accepts_distinct_native_wrappers_only_after_both_current_roundtrips(bridged_birth):
    x = bridged_birth; diagnostic = {}
    assert len({id(raw.canonical) for raw in (x.returned, x.feature, x.specific)}) == 3
    result = run_bridge(x, diagnostic=diagnostic)
    assert result.feature is x.feature and result.feature_canonical is x.feature.canonical
    assert result.evidence['interface_path'] == 'returned_native_plane_pid_v1'
    assert result.evidence['native_plane_equality'] == dict(pid_hex=x.returned.pid.hex(),
        native_is_same=1, exact_current_feature_roundtrip=True)
    assert [call[0] for call in x.bridge_calls] == ['pid', 'pid', 'pid', 'same', 'resolve', 'pid'] * 2
    assert [raw for raw, _ in x.query_calls] == [x.returned, x.specific] * 2
    assert_no_feature_query(x)
    assert diagnostic['binding_confirmed'] is True and diagnostic['raw_equals_current_feature'] is False
    assert result.evidence['accepted'] is result.evidence['native_acceptance'] is result.evidence['cleanup_authorized'] is False


@pytest.mark.parametrize('raw_name', ['returned', 'feature', 'specific'])
@pytest.mark.parametrize('bad_pid', [b'', None, bytearray(b'actual-plane-pid'), 'actual-plane-pid', b'foreign'])
def test_bridge_requires_exact_nonempty_bytes_from_every_actual_wrapper(bridged_birth, raw_name, bad_pid):
    x = bridged_birth; getattr(x, raw_name).pid = bad_pid; diagnostic = {}
    with pytest.raises(ValueError, match='same nonempty actual native PID bytes'):
        run_bridge(x, diagnostic=diagnostic)
    assert diagnostic['phase'] == 'native_PID_comparison' and diagnostic['accepted'] is False
    assert [call[0] for call in x.bridge_calls] == ['pid'] * 3
    assert_no_feature_query(x)


@pytest.mark.parametrize('resolved', ['none', 'foreign', 'old', 'wrong_pid', 'empty_pid'])
def test_bridge_pid_resolver_cannot_adopt_unrelated_or_nonroundtripping_feature(bridged_birth, resolved):
    x = bridged_birth
    target = {'none': None, 'foreign': NS(canonical=object(), pid=x.feature.pid), 'old': x.original[0],
        'wrong_pid': NS(canonical=x.feature.canonical, pid=b'wrong'),
        'empty_pid': NS(canonical=x.feature.canonical, pid=b'')}[resolved]
    x.bridge = replace(x.bridge, resolve_feature=lambda pid: target)
    with pytest.raises(ValueError, match='resolve the exact current new feature'): run_bridge(x)
    assert_no_feature_query(x)


@pytest.mark.parametrize('same', [0, 2, True, False, None, 1.0, '1'])
def test_bridge_requires_native_integer_swobjectsame_without_truthiness_or_fallback(bridged_birth, same):
    x = bridged_birth; diagnostic = {}
    x.bridge = replace(x.bridge, is_same=lambda *args: same)
    with pytest.raises(ValueError, match='swObjectSame=1'): run_bridge(x, diagnostic=diagnostic)
    assert diagnostic['native_same_code'] == same and diagnostic['native_same_type'] == type(same).__name__
    assert not any(call[0] == 'resolve' for call in x.bridge_calls)
    assert_no_feature_query(x)


@pytest.mark.parametrize('malformed', ['object', 'duck', 'persistent_id', 'resolve_feature', 'is_same'])
def test_malformed_explicit_bridge_refuses_before_any_query_or_native_callback(bridged_birth, malformed):
    x = bridged_birth
    bridge = object() if malformed == 'object' else (NS(**vars(x.bridge)) if malformed == 'duck'
        else replace(x.bridge, **{malformed: None}))
    with pytest.raises(ValueError, match='Complete native plane bridge'): run_bridge(x, native_bridge=bridge)
    assert x.query_calls == x.bridge_calls == []


@pytest.mark.parametrize('boundary', ['returned', 'specific'])
@pytest.mark.parametrize('result', ['none', 'foreign'])
def test_bridge_plane_queries_must_preserve_each_wrapper_canonical_before_pid_reads(bridged_birth, boundary, result):
    x = bridged_birth
    def query(raw, interface):
        if raw is (x.returned if boundary == 'returned' else x.specific):
            return None if result == 'none' else NS(canonical=object())
        return raw
    x.query_fault = query
    with pytest.raises(ValueError, match='preserve its own canonical identity'): run_bridge(x)
    assert x.bridge_calls == []
    assert_no_feature_query(x)


def test_bridge_missing_current_specific_interface_refuses_before_pid_reads(bridged_birth):
    x = bridged_birth; x.feature.specific = None
    with pytest.raises(ValueError, match='specific interface required'): run_bridge(x)
    assert x.bridge_calls == []
    assert_no_feature_query(x)


@pytest.mark.parametrize('boundary', ['query', 'specific', 'persistent_id', 'is_same', 'resolve_feature'])
def test_bridge_callback_exceptions_propagate_exactly_without_any_other_binding_path(bridged_birth, boundary):
    x = bridged_birth; error = QueryFailure(E_NOINTERFACE)
    def fail(*args): raise error
    if boundary == 'query': x.query_fault = fail
    elif boundary == 'specific': x.feature.GetSpecificFeature2 = fail
    else: x.bridge = replace(x.bridge, **{boundary: fail})
    with pytest.raises(QueryFailure) as caught: run_bridge(x)
    assert caught.value is error
    assert_no_feature_query(x)


@pytest.mark.parametrize('change', ['all_pids', 'same', 'resolved', 'specific_pid', 'raw_canonical',
    'feature_canonical', 'old_canonical', 'old_order', 'extra_addition'])
def test_bridge_rechecks_closing_pid_equality_resolution_and_complete_original_census(bridged_birth, change):
    x = bridged_birth; count = 0; active = x.bridge
    def persistent_id(raw):
        nonlocal count
        count += 1
        value = active.persistent_id(raw)
        if count == 4:
            if change == 'all_pids': x.returned.pid = x.feature.pid = x.specific.pid = b'changed-together'
            elif change == 'specific_pid': x.specific.pid = b'changed-specific'
            elif change == 'raw_canonical': x.returned.canonical = object()
            elif change == 'feature_canonical': x.feature.canonical = object()
            elif change == 'old_canonical': x.original[0].canonical = object()
            elif change == 'old_order': x.current[:] = [x.original[1], x.feature, x.original[0]]
            elif change == 'extra_addition': x.current.append(NS(canonical=object()))
        return value
    x.bridge = NativePlaneBridge(persistent_id,
        lambda pid: None if change == 'resolved' and count >= 4 else active.resolve_feature(pid),
        lambda left, right: 2 if change == 'same' and count >= 4 else active.is_same(left, right))
    with pytest.raises(ValueError): run_bridge(x)
    assert_no_feature_query(x)


@pytest.mark.parametrize('boundary', ['second_same', 'second_resolve', 'final_pid'])
@pytest.mark.parametrize('change', ['old_canonical', 'old_order'])
def test_bridge_final_census_rejects_original_changes_inside_second_native_read_boundary(bridged_birth, boundary, change):
    x = bridged_birth; active = x.bridge; counts = {'pid': 0, 'same': 0, 'resolve': 0}
    def mutate():
        if change == 'old_canonical': x.original[0].canonical = object()
        else: x.current[:] = [x.original[1], x.feature, x.original[0]]
    def persistent_id(raw):
        counts['pid'] += 1
        value = active.persistent_id(raw)
        if boundary == 'final_pid' and counts['pid'] == 8: mutate()
        return value
    def is_same(left, right):
        counts['same'] += 1
        if boundary == 'second_same' and counts['same'] == 2: mutate()
        return active.is_same(left, right)
    def resolve_feature(pid):
        counts['resolve'] += 1
        if boundary == 'second_resolve' and counts['resolve'] == 2: mutate()
        return active.resolve_feature(pid)
    x.bridge = NativePlaneBridge(persistent_id, resolve_feature, is_same); diagnostic = {}
    with pytest.raises(ValueError, match='original retained feature|Original complete feature order'):
        run_bridge(x, diagnostic=diagnostic)
    assert counts == {'pid': 8, 'same': 2, 'resolve': 2}
    assert diagnostic['accepted'] is False and 'binding_confirmed' not in diagnostic
    assert_no_feature_query(x)


@pytest.mark.parametrize('fault', ['missing_original', 'duplicate_original', 'old_order', 'wrong_kind'])
def test_explicit_bridge_does_not_weaken_initial_complete_feature_census(bridged_birth, fault):
    x = bridged_birth
    if fault == 'missing_original': x.current.pop()
    elif fault == 'duplicate_original': x.current[-1] = x.original[0]
    elif fault == 'old_order': x.current[:] = [x.original[1], x.feature, x.original[0]]
    else: x.feature.kind = 'Boss'
    with pytest.raises(ValueError): run_bridge(x)
    assert x.query_calls == x.bridge_calls == []
