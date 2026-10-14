"""Passive exact feature/reference-plane identity regression; no native CAD proof."""

from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import cad_geometry as native
from solidworks_mcp.cad_geometry import CadGeometryMixin
from solidworks_mcp.jobs import ExecutionFailure


class Feature:
    def __init__(self, pid=b'plane-pid', *, kind='RefPlane', canonical=None, specific=None):
        self.pid, self.kind = pid, kind
        self.canonical = canonical if canonical is not None else object()
        self.specific = specific
        self.specific_reads = 0

    def GetTypeName2(self):
        return self.kind

    def GetSpecificFeature2(self):
        self.specific_reads += 1
        return self.specific

    @property
    def Name(self):
        raise AssertionError('Display name is not identity evidence')

    def GetID(self):
        raise AssertionError('Native feature ID must not substitute for persistent identity')

    def Select2(self, *args):
        raise AssertionError('Read-only resolver must not select/write')


class Extension:
    def __init__(self, raw, status=0):
        self.raw, self.status = raw, status
        self.lookups, self.pid_reads = [], []

    def GetObjectByPersistReference3(self, token):
        self.lookups.append(token)
        return self.raw, self.status

    def GetPersistReference3(self, obj):
        self.pid_reads.append(obj)
        return obj.pid

    def SelectByID2(self, *args):
        raise AssertionError('Resolver must not modify selection')


class Adapter(CadGeometryMixin):
    _module = NS(IFeature=object(), IRefPlane=object(), IBody2=object(), IFace2=object(),
                 IEdge=object(), IComponent2=object())

    def __init__(self, features, raw, status=0):
        self.current = list(features)
        self.extension = Extension(raw, status)
        self.census_reads = 0
        self.same_calls = []
        self.same_result = 'canonical_default'
        self._sw = NS(IsSame=self.native_same)

    def native_same(self, left, right):
        self.same_calls.append((left, right))
        if isinstance(self.same_result, Exception):
            raise self.same_result
        if self.same_result == 'canonical_default':
            return int(left.canonical == right.canonical)
        return self.same_result

    def _extension(self, model):
        return self.extension

    @staticmethod
    def _persistent_variant(token):
        return bytes(token)

    @staticmethod
    def identity(obj):
        return obj.canonical

    def features(self, model):
        self.census_reads += 1
        return list(self.current)


@pytest.fixture(autouse=True)
def fake_typed_wrappers(monkeypatch):
    def wrap(raw, cls):
        # A native specific-plane object cannot be queried as IFeature.
        if raw is not None and cls is Adapter._module.IFeature and not isinstance(raw, Feature):
            raise AssertionError('Specific interface cannot be cast into guessed IFeature')
        return raw
    monkeypatch.setattr(native.binding, 'wrap', wrap)


def test_normal_feature_pid_returns_exact_current_feature_without_specific_lookup():
    feature = Feature(kind='Boss')
    returned_wrapper = Feature(canonical=feature.canonical, pid=feature.pid, kind='Boss')
    adapter = Adapter([Feature(b'unrelated', kind='RefPlane'), feature], returned_wrapper)
    result = adapter.resolve_persistent_id(object(), feature.pid, 'feature')
    assert result is feature
    assert adapter.extension.lookups == [feature.pid] and adapter.census_reads >= 1
    assert feature in adapter.extension.pid_reads and feature.specific_reads == 0 and not adapter.same_calls


def test_reference_plane_specific_interface_requires_exact_pid_and_native_same_ack():
    specific = NS(pid=b'plane-pid', canonical=object())
    feature = Feature(specific=specific)
    returned_wrapper = NS(pid=specific.pid, canonical=object())
    adapter = Adapter([Feature(b'unrelated', kind='Boss'), feature], returned_wrapper)
    adapter.same_result = 1  # Fresh specific wrappers can have different canonical IUnknown.
    result = adapter.resolve_persistent_id(object(), feature.pid, 'feature')
    assert result is feature and result is not specific and result is not returned_wrapper
    assert feature.canonical != specific.canonical and feature.specific_reads >= 1
    assert feature in adapter.extension.pid_reads and specific in adapter.extension.pid_reads
    assert adapter.extension.lookups == [feature.pid]
    assert adapter.same_calls == [(returned_wrapper, specific)]


@pytest.mark.parametrize('ack', [0, 2, True, False, None, '1', RuntimeError('native identity unavailable')])
def test_plane_native_same_must_be_exact_normal_integer_one(ack):
    specific = NS(pid=b'plane-pid', canonical=object())
    feature = Feature(specific=specific)
    raw = NS(pid=specific.pid, canonical=object())
    adapter = Adapter([feature], raw)
    adapter.same_result = ack
    exception = RuntimeError if isinstance(ack, Exception) else ExecutionFailure
    with pytest.raises(exception):
        adapter.resolve_persistent_id(object(), feature.pid, 'feature')
    assert adapter.same_calls == [(raw, specific)]


def test_specific_pid_mismatch_is_rejected_even_if_native_same_would_acknowledge():
    specific = NS(pid=b'foreign-pid', canonical=object())
    feature = Feature(specific=specific)
    raw = NS(pid=feature.pid, canonical=object())
    adapter = Adapter([feature], raw)
    adapter.same_result = 1
    with pytest.raises(ExecutionFailure):
        adapter.resolve_persistent_id(object(), feature.pid, 'feature')
    assert not adapter.same_calls


@pytest.mark.parametrize('fault', [
    'specific_canonical', 'specific_pid', 'feature_pid', 'missing_specific',
    'duplicate_pid', 'gone', 'other_feature_type', 'raw_other_feature',
])
def test_specific_plane_never_uses_foreign_ambiguous_or_unsupported_feature(fault):
    specific = NS(pid=b'plane-pid', canonical=object())
    feature = Feature(specific=specific)
    raw = NS(pid=specific.pid, canonical=specific.canonical)
    census = [feature]
    if fault == 'specific_canonical':
        raw.canonical = object()
    elif fault == 'specific_pid':
        specific.pid = b'foreign-specific-pid'
    elif fault == 'feature_pid':
        feature.pid = b'foreign-feature-pid'
    elif fault == 'missing_specific':
        feature.specific = None
    elif fault == 'duplicate_pid':
        census.append(Feature(specific=NS(pid=b'plane-pid', canonical=object())))
    elif fault == 'gone':
        census = []
    elif fault == 'other_feature_type':
        feature.kind = 'ProfileFeature'
    else:
        raw = Feature(pid=b'plane-pid', canonical=object(), kind='Boss')
    adapter = Adapter(census, raw)
    with pytest.raises(ExecutionFailure):
        adapter.resolve_persistent_id(object(), b'plane-pid', 'feature')
    assert adapter.extension.lookups == [b'plane-pid']


def test_normal_feature_raw_canonical_does_not_bypass_duplicate_pid_census():
    feature = Feature(kind='Boss')
    other = Feature(kind='Boss')
    adapter = Adapter([feature, other], feature)
    with pytest.raises(ExecutionFailure):
        adapter.resolve_persistent_id(object(), feature.pid, 'feature')


@pytest.mark.parametrize('status,raw_present,code', [
    (4, True, 'object_deleted'), (2, True, 'object_suppressed'),
    (1, True, 'object_reference_invalid'), (0, False, 'object_reference_invalid'),
])
def test_native_failed_reference_status_cannot_be_recovered_from_current_plane(status, raw_present, code):
    specific = NS(pid=b'plane-pid', canonical=object())
    feature = Feature(specific=specific)
    adapter = Adapter([feature], specific if raw_present else None, status)
    with pytest.raises(ExecutionFailure) as exc:
        adapter.resolve_persistent_id(object(), feature.pid, 'feature')
    assert exc.value.code == code
    assert adapter.extension.lookups == [feature.pid] and feature.specific_reads == 0
    assert not adapter.extension.pid_reads
