"""Artificial QueryInterface/native feature census; no COM or CAD execution."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b2_plane_birth import OriginalFeature, bind_returned_plane, E_NOINTERFACE
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
