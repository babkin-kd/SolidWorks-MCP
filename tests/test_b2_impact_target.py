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
