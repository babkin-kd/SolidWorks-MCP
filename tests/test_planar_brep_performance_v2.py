"""Measured pure equality counts; full linear-reference BREP and reads unchanged.

These fixtures prove algorithmic behavior, not native RPC counts or runtime gains.
The reference key lookup is the complete pre-optimization linear algorithm.
"""

import json
import random
from types import SimpleNamespace

import pytest

import solidworks_mcp.cad_planar_brep as planar
from test_planar_brep_v2 import FaultEntity, make_body


OptimizedReader = planar._Reader


class LinearReferenceReader(OptimizedReader):
    def key(self, obj, interface=None):
        # Original global-only lookup, ignoring the new optional priority hint.
        try:
            identity = self.identity(obj)
            if identity is None:
                planar._fail('planar_brep_incomplete', 'Missing canonical native identity.')
            for index, known in enumerate(self.identities):
                self.identity_comparisons += 1
                if self.identity_comparisons > self.limits.max_identity_comparisons:
                    planar._fail('planar_brep_budget_exceeded', 'Native identity comparison budget exceeded.')
                if identity == known:
                    return index
            self.identities.append(identity)
            return len(self.identities) - 1
        except planar.PlanarBrepError:
            raise
        except Exception as exc:
            raise planar.PlanarBrepError('planar_brep_native_read_failed', 'Native identity failed.') from exc


class CanonicalIdentity:
    __hash__ = None

    def __init__(self, token, meter):
        self.token, self.meter = token, meter

    def __eq__(self, other):
        self.meter.comparisons.append((self.token, other.token))
        if self.meter.on_compare:
            self.meter.on_compare(self.token, other.token)
        return self.token == other.token


class FreshWrapper:
    def __init__(self, entity, meter):
        self.entity, self.meter = entity, meter

    def __getattr__(self, name):
        value = getattr(self.entity, name)
        label = (type(self.entity).__name__, name)
        if callable(value):
            def invoke():
                self.meter.methods.append(label)
                return value()
            return invoke
        self.meter.properties.append(label)
        return value


class Meter:
    def __init__(self):
        self.methods, self.properties, self.wraps, self.identities, self.comparisons = [], [], [], [], []
        self.wrappers = []  # Keep every fresh test wrapper alive, no id reuse.
        self.on_compare = None

    def wrap(self, raw, interface):
        entity = raw.entity if type(raw) is FreshWrapper else raw
        self.wraps.append(interface)
        wrapper = FreshWrapper(entity, self)
        self.wrappers.append(wrapper)
        return wrapper

    def identity(self, obj):
        entity = obj.entity if type(obj) is FreshWrapper else obj
        token = entity.ident
        self.identities.append((type(entity).__name__, token))
        return CanonicalIdentity(token, self)


def measured_snapshot(body, reader, monkeypatch):
    meter = Meter()
    with monkeypatch.context() as patch:
        patch.setattr(planar, '_Reader', reader)
        result = planar.planar_body_snapshot(body, identity=meter.identity, wrap=meter.wrap)
    return result, meter


@pytest.mark.parametrize('shuffled', [False, True])
def test_same_body_exact_complete_json_and_every_explicit_read_identity_wrap_are_preserved(shuffled, monkeypatch):
    body = make_body()
    body.Check3 = FaultEntity(0)
    if shuffled:
        rng = random.Random(48)
        for collection in (body.vertices, body.edges, body.faces):
            rng.shuffle(collection)
        for face in body.faces:
            face.loops[0].shift = 2
            face.loops[0].reverse_array = True
    old, old_meter = measured_snapshot(body, LinearReferenceReader, monkeypatch)
    current, meter = measured_snapshot(body, OptimizedReader, monkeypatch)
    assert current == old and planar.planar_snapshot_digest(current) == planar.planar_snapshot_digest(old)
    assert json.dumps(current, sort_keys=True, separators=(',', ':')) == json.dumps(old, sort_keys=True, separators=(',', ':'))
    assert meter.methods == old_meter.methods and meter.properties == old_meter.properties
    assert meter.identities == old_meter.identities and meter.wraps == old_meter.wraps
    assert len(meter.methods) == 397 and len(meter.properties) == 94
    assert len(meter.identities) == 339 and len(meter.wraps) == 365
    assert len({id(wrapper) for wrapper in meter.wrappers}) == len(meter.wraps)
    assert len(meter.comparisons) < len(old_meter.comparisons)
    if not shuffled:
        assert len(old_meter.comparisons) == 8294
        assert len(meter.comparisons) == 3552  # Actual instrumented fake EQ calls.


def reader_for_tokens(*, limits=None):
    meter = Meter()
    reader = OptimizedReader(meter.identity, None, limits or planar.PlanarBrepLimits())
    return reader, meter


def test_cross_interface_alias_uses_complete_global_fallback_then_retains_global_key():
    reader, meter = reader_for_tokens()
    vertex, edge, alias = [SimpleNamespace(ident=value) for value in ('vertex', 'edge', 'vertex')]
    assert reader.key(vertex, 'IVertex') == 0
    assert reader.key(edge, 'IEdge') == 1
    meter.comparisons.clear()
    assert reader.key(alias, 'IEdge') == 0
    assert meter.comparisons == [('vertex', 'edge'), ('vertex', 'vertex')]
    assert reader.role_keys['IEdge'] == [1, 0] and len(reader.identities) == 2
    assert len(meter.identities) == 3  # Every key call obtains a fresh canonical interface.
    assert reader.identities[0].token == 'vertex' and reader.identities[1].token == 'edge'


def test_candidate_miss_checks_every_remaining_global_key_exactly_once_for_foreign_identity():
    reader, meter = reader_for_tokens()
    assert reader.key(SimpleNamespace(ident='body'), 'IBody2') == 0
    assert reader.key(SimpleNamespace(ident='edge'), 'IEdge') == 1
    meter.comparisons.clear()
    assert reader.key(SimpleNamespace(ident='foreign'), 'IEdge') == 2
    assert meter.comparisons == [('foreign', 'edge'), ('foreign', 'body')]
    assert reader.role_keys['IEdge'] == [1, 2]


def test_same_python_wrapper_with_retargeted_identity_is_not_memoized():
    reader, meter = reader_for_tokens()
    obj = SimpleNamespace(ident='first')
    assert reader.key(obj, 'IVertex') == 0
    obj.ident = 'replacement'
    assert reader.key(obj, 'IVertex') == 1
    assert len(meter.identities) == 2 and meter.comparisons == [('replacement', 'first')]


def test_unhinted_lookup_keeps_global_order_and_canonical_identity_is_not_hashed():
    reader, meter = reader_for_tokens()
    for role, token in [('IEdge', 'first'), ('IBody2', 'second')]:
        reader.key(SimpleNamespace(ident=token), role)
    meter.comparisons.clear()
    assert reader.key(SimpleNamespace(ident='second')) == 1
    assert meter.comparisons == [('second', 'first'), ('second', 'second')]
    assert all(identity.__hash__ is None for identity in reader.identities)


def test_candidate_and_fallback_share_one_strict_identity_comparison_budget():
    reader, meter = reader_for_tokens(limits=planar.PlanarBrepLimits(max_identity_comparisons=2))
    reader.key(SimpleNamespace(ident='body'), 'IBody2')
    reader.key(SimpleNamespace(ident='edge'), 'IEdge')
    with pytest.raises(planar.PlanarBrepError) as error:
        reader.key(SimpleNamespace(ident='foreign'), 'IEdge')
    assert error.value.code == 'planar_brep_budget_exceeded'
    assert len(meter.comparisons) == 2  # Third budget increment fails before native EQ.
    assert reader.identity_comparisons == 3 and len(reader.identities) == 2


@pytest.mark.parametrize('comparison_phase', ['candidate', 'fallback'])
def test_comparison_exception_is_fail_closed_with_original_cause(comparison_phase):
    reader, meter = reader_for_tokens()
    reader.key(SimpleNamespace(ident='body'), 'IBody2')
    reader.key(SimpleNamespace(ident='edge'), 'IEdge')
    original = RuntimeError('Canonical native equality unavailable')
    def reject(left, right):
        if right == ('edge' if comparison_phase == 'candidate' else 'body'):
            raise original
    meter.on_compare = reject
    with pytest.raises(planar.PlanarBrepError) as error:
        reader.key(SimpleNamespace(ident='foreign'), 'IEdge')
    assert error.value.code == 'planar_brep_native_read_failed' and error.value.__cause__ is original
    assert len(reader.identities) == 2


def test_missing_or_throwing_fresh_identity_does_not_fall_back_to_python_identity():
    reader, meter = reader_for_tokens()
    obj = SimpleNamespace(ident='body')
    reader.key(obj, 'IBody2')
    reader.identity = lambda obj: None
    with pytest.raises(planar.PlanarBrepError) as error:
        reader.key(obj, 'IBody2')
    assert error.value.code == 'planar_brep_incomplete'
    original = RuntimeError('Fresh identity unavailable')
    def broken(obj):
        raise original
    reader.identity = broken
    with pytest.raises(planar.PlanarBrepError) as error:
        reader.key(obj, 'IBody2')
    assert error.value.code == 'planar_brep_native_read_failed' and error.value.__cause__ is original
    assert len(reader.identities) == 1 and meter.comparisons == []


@pytest.mark.parametrize('fault', ['foreign_body', 'foreign_vertex', 'foreign_loop', 'alias_duplicate'])
def test_foreign_membership_and_duplicate_alias_rejections_match_linear_reference(fault, monkeypatch):
    body, foreign = make_body(), make_body()
    if fault == 'foreign_body':
        body.edges[0].body = foreign
    elif fault == 'foreign_vertex':
        body.edges[0].GetStartVertex = lambda: foreign.vertices[0]
    elif fault == 'foreign_loop':
        body.faces[0].loops[0].ordered[0].loop = foreign.faces[0].loops[0]
    else:
        body.vertices[1].ident = body.vertices[0].ident
    codes = []
    for reader in (LinearReferenceReader, OptimizedReader):
        with pytest.raises(planar.PlanarBrepError) as error:
            measured_snapshot(body, reader, monkeypatch)
        codes.append(error.value.code)
    expected = 'planar_brep_ambiguous' if fault == 'alias_duplicate' else 'planar_brep_incomplete'
    assert codes == [expected, expected]


def test_new_capture_reacquires_all_identities_and_does_not_reuse_role_hints(monkeypatch):
    body = make_body()
    first, first_meter = measured_snapshot(body, OptimizedReader, monkeypatch)
    second, second_meter = measured_snapshot(body, OptimizedReader, monkeypatch)
    assert first == second and first_meter.identities == second_meter.identities
    assert len(first_meter.identities) == len(second_meter.identities) == 339
    assert first_meter.comparisons == second_meter.comparisons


def test_equality_triggered_late_body_change_still_rejects_in_both_lookup_algorithms(monkeypatch):
    for reader in (LinearReferenceReader, OptimizedReader):
        body, meter = make_body(), Meter()
        changed = []
        def notify(left, right):
            if left == right == body.ident and not changed:
                body.stamp += 1
                changed.append(True)
        meter.on_compare = notify
        with monkeypatch.context() as patch:
            patch.setattr(planar, '_Reader', reader)
            with pytest.raises(planar.PlanarBrepError) as error:
                planar.planar_body_snapshot(body, identity=meter.identity, wrap=meter.wrap)
        assert error.value.code == 'planar_brep_changed_during_read' and changed == [True]
