"""Retained registry/current getter integration with artificial handles, no CAD."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from solidworks_mcp.jobs import ExecutionFailure
from test_b2_impact_fixture import fixture, leaf, extrusion_proof, proof, case, domain

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b2_impact_target import B2ImpactTarget
    from verifier_b2_impact_fixture import FixtureGate
    from verifier_b2_body_binding import NativeBodyBridge
finally:
    sys.path.remove(scripts)


@pytest.fixture
def target(fixture):
    x = fixture
    x.c.adapter.sketch_snapshot = lambda model, feature: (deepcopy(x.c.getter_values['sketch']), ())
    x.ancillary_calls = []
    x.topology_calls = []
    def topology(adapter, model, body, boundary, references):
        # Artificial current topology getter; actual installed _topology is the
        # default in native. This boundary fixture has no full native body API.
        x.topology_calls.append((body, boundary))
        references.extend(deepcopy(row) for row in x.c.baseline['references']
                          if row['kind'] in ('face', 'edge'))
    def ancillary(adapter, model, **current):
        x.ancillary_calls.append(current)
        assert model is x.binding.model and current['body'] is x.c.bodies[0]
        assert len(current['dimensions']) == 3
        return dict(scope='artificial_ancillary_for_target_boundary_test', accepted=False)
    x.collector = B2ImpactTarget(x.helper, x.c.baseline, ancillary=ancillary,
                                 extrusion=lambda adapter, feature: deepcopy(x.c.getter_values['extrusion']),
                                 topology=topology)
    return x


@pytest.mark.parametrize('kind', ['child_plane', 'unused_equation'])
def test_capture_uses_current_context_and_does_not_authorize_any_native_result(target, kind):
    x = target
    if kind == 'child_plane': x.helper.add_child_plane(x.c.baseline)
    else: x.helper.add_unused_equation()
    writes = list(x.write_calls)
    result = x.collector.capture()
    assert len(result['planes']) == (4 if kind == 'child_plane' else 3)
    assert result['deletion_context']['native_context']['equations']['enumerated_count'] == (kind == 'unused_equation')
    assert result['geometry'] == x.c.baseline['clone_state']['geometry']
    assert len(x.ancillary_calls) == 1 and x.write_calls == writes
    assert len(x.topology_calls) == 1
    refs = x.ancillary_calls[0]['references']
    assert len([row for row in refs if row['kind'] == 'face']) == 6
    assert len([row for row in refs if row['kind'] == 'edge']) == 12
    assert len([row for row in refs if row['kind'] == 'body']) == 1
    assert len([row for row in refs if row['kind'] == 'feature']) == (7 if kind == 'child_plane' else 6)
    assert all(result[key] is False for key in ('accepted', 'native_b2_accepted',
        'cleanup_authorized', 'full_refusal_context_available'))
    result['features'].clear()
    assert x.c.features
    assert x.c.native_calls[-1] == 'watch_closed'


@pytest.mark.parametrize('fault', ['pending', 'journal', 'extra_feature', 'missing_feature',
    'extra_dimension', 'replaced_dimension', 'different_anchor', 'foreign_body',
    'geometry_changed', 'plane_transform', 'watch_event', 'ancillary_failure', 'topology_missing'])
def test_unsupported_changed_or_pending_target_never_receives_replacement_data(target, fault):
    x = target
    x.helper.add_unused_equation()
    a = x.c.adapter
    if fault == 'pending': x.helper.pending_native_step = 'unreturned'
    elif fault == 'journal': x.helper.journal_failed = True
    elif fault == 'extra_feature': x.c.features.append(NS(identity=object()))
    elif fault == 'missing_feature': x.c.features.pop(0)
    elif fault == 'extra_dimension': x.c.records.append(x.c.records[0])
    elif fault == 'replaced_dimension': x.c.records[0].dimension.identity = object()
    elif fault == 'different_anchor': x.c.records[0].anchor['foreign'] = True
    elif fault == 'foreign_body': x.c.bodies[0].identity = object()
    elif fault == 'geometry_changed': a.dimension_geometry_snapshot = lambda model: {'foreign': True}
    elif fault == 'plane_transform': a.reference_plane_transform = lambda plane: [float('nan')] * 16
    elif fault == 'watch_event':
        def read(*args):
            x.c.events += 1
            return deepcopy(x.c.getter_values['extrusion'])
        x.collector.extrusion = read
    elif fault == 'ancillary_failure':
        def fail(*args, **kwargs): raise ValueError('Actual unknown ancillary inventory')
        x.collector.ancillary = fail
    elif fault == 'topology_missing': x.collector.topology = lambda *args: None
    writes = list(x.write_calls)
    with pytest.raises((FixtureGate, ExecutionFailure, ValueError)):
        x.collector.capture()
    assert x.write_calls == writes
    if fault in ('pending', 'journal'):
        assert x.ancillary_calls == []
    else:
        assert x.c.native_calls[-1] == 'watch_closed'


def test_cannot_reconstruct_original_capture_after_fixture_change(fixture):
    x = fixture
    x.helper.add_unused_equation()
    with pytest.raises(FixtureGate, match='before fixture'):
        B2ImpactTarget(x.helper, x.c.baseline)


def own_plane_dimension(x):
    x.helper.add_child_plane(x.c.baseline)
    plane = x.raw_plane
    dimension = NS(identity=object(), owner=plane)
    record = NS(dimension=dimension, owner=plane, owner_tree_identity=plane.identity,
                anchor={'strategy': 'direct_dimension_v1', 'dimension_pid_hex': b'own-plane-dim'.hex()},
                summary=deepcopy(x.c.records[0].summary))
    record.summary['full_name'] = 'D1@' + plane.Name + '@Контрольная деталь.Part'
    x.c.records.append(record)
    x.collector.ancillary = lambda *args, **current: dict(scope='artificial_ancillary_four_dim_boundary',
        accepted=False, dimensions=len(current['dimensions']), roles=dict(current['dimension_roles']))
    return record


def test_optional_plane_offset_dimension_is_retained_by_exact_native_owner_and_anchor(target):
    x = target
    record = own_plane_dimension(x)
    first = x.collector.capture()
    assert len(first['dimensions']) == 4
    assert first['ancillary']['roles'][record.summary['full_name']] == 'plane_offset'
    assert x.collector.plane_dimension[0] is record
    assert x.collector.capture() == first
    assert first['full_refusal_context_available'] is False


@pytest.mark.parametrize('fault', ['foreign_owner', 'foreign_owner_tree', 'missing_anchor',
    'replaced_after_read', 'removed_after_read', 'changed_anchor_after_read', 'fifth_dimension'])
def test_plane_dimension_cannot_adopt_a_foreign_replaced_or_missing_record(target, fault):
    x = target
    record = own_plane_dimension(x)
    if fault.endswith('after_read'):
        x.collector.capture()
    if fault == 'foreign_owner': record.owner = x.binding.feature
    elif fault == 'foreign_owner_tree': record.owner_tree_identity = object()
    elif fault == 'missing_anchor': record.anchor = None
    elif fault == 'replaced_after_read': record.dimension.identity = object()
    elif fault == 'removed_after_read': x.c.records.remove(record)
    elif fault == 'changed_anchor_after_read': record.anchor['dimension_pid_hex'] = b'changed-plane-dim'.hex()
    else: x.c.records.append(record)
    writes = list(x.write_calls)
    with pytest.raises((FixtureGate, ExecutionFailure, ValueError)):
        x.collector.capture()
    assert x.write_calls == writes


@pytest.mark.parametrize('change_inside_capture',[False,True])
def test_explicit_native_equivalence_uses_current_body_and_rejects_change_during_capture(target,change_inside_capture):
    x=target
    x.helper.add_child_plane(x.c.baseline)
    original=x.collector.body
    current=NS(identity=object(),pid=original.pid)
    x.c.bodies[:]=[current];x.c.raw_by_pid[current.pid]=current
    faces=[NS(identity=object(),GetBody=lambda:x.c.bodies[0]) for _ in range(6)]
    x.binding.feature.GetFaces=lambda:faces
    x.collector.body_bridge=NativeBodyBridge(lambda raw,interface:raw,
        lambda old,new:1 if old is original and new in x.c.bodies else 0)
    ordinary=x.collector.ancillary
    def ancillary(*args,**kwargs):
        result=ordinary(*args,**kwargs)
        if change_inside_capture:
            replacement=NS(identity=object(),pid=original.pid)
            x.c.bodies[:]=[replacement];x.c.raw_by_pid[replacement.pid]=replacement
        return result
    x.collector.ancillary=ancillary
    writes=list(x.write_calls)
    if change_inside_capture:
        with pytest.raises(FixtureGate,match='during ancillary'):
            x.collector.capture()
    else:
        result=x.collector.capture()
        assert result['geometry']==x.c.baseline['clone_state']['geometry']
        assert result['accepted'] is False and result['cleanup_authorized'] is False
        assert x.topology_calls[0][0] is current
    assert x.collector.body is original and x.write_calls==writes


@pytest.mark.parametrize('role', ['width', 'height', 'depth', 'plane_offset'])
@pytest.mark.parametrize('stage,method', [
    ('dimension_reference_is_current', 'dimension_reference_is_current'),
    ('resolve', 'resolve_dimension_id'), ('current_summary', 'dimension_summary')])
def test_dimension_failure_identifies_original_or_own_plane_without_extra_adapter_reads(target, role, stage, method):
    x = target
    plane = own_plane_dimension(x)
    record = plane if role == 'plane_offset' else x.collector.dimensions[x.collector.dimension_roles.index(role)]
    error = ExecutionFailure('persistent_reference_mismatch', 'Artificial normally returned owner mismatch.')
    calls, after_failure = [], []
    failed = False
    adapter = x.c.adapter
    # Observe all adapter calls, not just the failing getter: no retry, replacement
    # summary, PID resolution or independent inspection may follow the exception.
    for name in dir(adapter):
        original = getattr(adapter, name)
        if name.startswith('__') or not callable(original):
            continue
        def observed(*args, _name=name, _original=original, **kwargs):
            nonlocal failed
            if failed:
                after_failure.append(_name)
            calls.append(_name)
            selected = (_name == method and
                (args[1] == record.anchor if method == 'resolve_dimension_id' else
                 args[0 if method == 'dimension_summary' else 1] is record))
            if selected:
                failed = True
                raise error
            return _original(*args, **kwargs)
        setattr(adapter, name, observed)
    with pytest.raises(ExecutionFailure) as caught:
        x.collector.capture()
    assert caught.value is error
    assert after_failure == [] and calls[-1] == method
    context = x.collector.dimension_read_failure
    assert context['dimension_role'] == role and context['stage'] == stage
    assert context['boundary'] == 'current_capture'
    assert context['original_anchor'] == context['current_anchor'] == record.anchor
    assert context['exception_type'] == 'ExecutionFailure'
    assert context['exception_code'] == error.code and context['exception_message'] == str(error)
    assert all(context[key] is False for key in ('accepted', 'native_b2_accepted', 'cleanup_authorized'))
    # Diagnostic anchors are detached Python values, no retained mutable alias.
    record.anchor['test_change'] = True
    assert 'test_change' not in context['original_anchor']
    assert x.c.native_calls[-1] == 'watch_closed'


@pytest.mark.parametrize('role', ['width', 'plane_offset'])
def test_closing_dimension_failure_does_not_claim_an_unread_current_anchor(target, role):
    x = target
    plane = own_plane_dimension(x)
    record = plane if role == 'plane_offset' else x.collector.dimensions[x.collector.dimension_roles.index(role)]
    original = x.c.adapter.dimension_reference_is_current
    count = 0
    error = ValueError('Artificial closing failure')
    def fail_on_closing(model, current, anchor):
        nonlocal count
        if current is record:
            count += 1
            if count == 2:
                raise error
        return original(model, current, anchor)
    x.c.adapter.dimension_reference_is_current = fail_on_closing
    with pytest.raises(ValueError) as caught:
        x.collector.capture()
    assert caught.value is error
    context = x.collector.dimension_read_failure
    assert context['boundary'] == 'closing_capture' and context['dimension_role'] == role
    assert context['original_anchor'] == record.anchor and context['current_anchor'] is None
    assert context['exception_code'] is None


def test_new_plane_anchor_failure_does_not_invent_a_retained_anchor(target):
    x = target
    record = own_plane_dimension(x)
    original = x.c.adapter.dimension_persistent_id
    error = ExecutionFailure('persistent_reference_unavailable', 'Artificial plane anchor failure.')
    def fail(model, current):
        if current is record:
            raise error
        return original(model, current)
    x.c.adapter.dimension_persistent_id = fail
    with pytest.raises(ExecutionFailure) as caught:
        x.collector.capture()
    assert caught.value is error and x.collector.plane_dimension is None
    context = x.collector.dimension_read_failure
    assert context['dimension_role'] == 'plane_offset' and context['stage'] == 'current_anchor'
    assert context['original_anchor'] is None and context['current_anchor'] is None


def test_diagnostic_formatting_failure_preserves_the_exact_original_exception(target):
    class UnformattableError(Exception):
        def __str__(self):
            raise RuntimeError('Diagnostic message unavailable')
    x = target
    x.helper.add_unused_equation()
    error = UnformattableError()
    def fail(*args):
        raise error
    x.c.adapter.dimension_reference_is_current = fail
    with pytest.raises(UnformattableError) as caught:
        x.collector.capture()
    assert caught.value is error and x.collector.dimension_read_failure is None
