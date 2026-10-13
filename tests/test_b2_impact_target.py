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
    def ancillary(adapter, model, **current):
        x.ancillary_calls.append(current)
        assert model is x.binding.model and current['body'] is x.c.bodies[0]
        assert len(current['dimensions']) == 3
        return dict(scope='artificial_ancillary_for_target_boundary_test', accepted=False)
    x.collector = B2ImpactTarget(x.helper, x.c.baseline, ancillary=ancillary,
                                 extrusion=lambda adapter, feature: deepcopy(x.c.getter_values['extrusion']))
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
    assert all(result[key] is False for key in ('accepted', 'native_b2_accepted',
        'cleanup_authorized', 'full_refusal_context_available'))
    result['features'].clear()
    assert x.c.features
    assert x.c.native_calls[-1] == 'watch_closed'


@pytest.mark.parametrize('fault', ['pending', 'journal', 'extra_feature', 'missing_feature',
    'extra_dimension', 'replaced_dimension', 'different_anchor', 'foreign_body',
    'geometry_changed', 'plane_transform', 'watch_event', 'ancillary_failure'])
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
