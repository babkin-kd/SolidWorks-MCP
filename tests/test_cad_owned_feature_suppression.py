"""Native bridge boundaries on artificial handles; no CAD acceptance."""
from types import SimpleNamespace

import pytest

from solidworks_mcp.cad_owned_feature_suppression import NativeOwnedFeatureSuppression
from solidworks_mcp.jobs import JobError, ExecutionFailure


def fixture(suppressed=False):
    calls, events = [], []
    feature = SimpleNamespace()
    feature.IsSuppressed2 = lambda *args: [suppressed]
    feature.SetSuppression2 = lambda *args: calls.append(('setter', args)) or True
    model = SimpleNamespace(ForceRebuild3=lambda *args: calls.append(('rebuild', args)) or True)
    binding = SimpleNamespace(document_id='doc', configuration='Основная', object_id='obj',
        connection_epoch='epoch', kind='extrusion', feature_identity=feature, model_identity=model, model=model)
    adapter = SimpleNamespace(identity=lambda obj: obj, active_document=lambda: model, application_busy=lambda: True)
    registry = SimpleNamespace(adapter=adapter, resolve=lambda *args, **kwargs: (binding, feature))
    action = NativeOwnedFeatureSuppression(registry, binding, not suppressed,
        recorder=lambda *args: events.append(args))
    return action, feature, calls, events


@pytest.mark.parametrize('original,expected', [(False, 0), (True, 2)])
def test_exact_config_and_paired_receipts(original, expected):
    action, feature, calls, events = fixture(original)
    evidence = action.apply()
    assert calls == [('setter', (expected, 1, None)), ('rebuild', (False,))]
    assert [(row[0], row[1]) for row in events] == [
        ('set_suppressed', 'pending'), ('set_suppressed', 'returned'), ('rebuild', 'pending'), ('rebuild', 'returned')]
    assert evidence['pending_native_step'] is None and evidence['journal_failed'] is False
    with pytest.raises(JobError): action.apply()
    assert len(calls) == 2


@pytest.mark.parametrize('step', ['setter', 'rebuild'])
@pytest.mark.parametrize('value', [False, None, 1, 'true'])
def test_normal_failure_is_recorded_but_not_retried(step, value):
    action, feature, calls, events = fixture()
    if step == 'setter': feature.SetSuppression2 = lambda *args: calls.append(('setter', args)) or value
    else: action.binding.model.ForceRebuild3 = lambda *args: calls.append(('rebuild', args)) or value
    with pytest.raises(ExecutionFailure, match='inspect its actual effect') as error: action.apply()
    assert error.value.uncertain is False
    assert action.receipt.pending_native_step is None
    assert events[-1][1] == 'returned'
    assert len(calls) == (1 if step == 'setter' else 2)
    with pytest.raises(JobError): action.apply()


@pytest.mark.parametrize('boundary', ['pending', 'returned', 'com'])
def test_unknown_boundary_stays_pending(boundary):
    action, feature, calls, events = fixture()
    def fail(*args): raise RuntimeError('injected')
    if boundary == 'com': feature.SetSuppression2 = fail
    else:
        def record(name, phase, evidence):
            events.append((name, phase, evidence))
            if phase == boundary: fail()
        action.recorder = record
    with pytest.raises(RuntimeError): action.apply()
    assert action.receipt.pending_native_step == 'set_suppressed'
    assert action.receipt.journal_failed is (boundary != 'com')
    with pytest.raises(JobError): action.apply()
    assert not any(row[0] == 'rebuild' for row in calls)


@pytest.mark.parametrize('change', ['identity', 'active', 'state', 'guard', 'kind', 'binding'])
def test_exact_prewrite_recheck(change):
    action, feature, calls, events = fixture()
    if change == 'identity': action.adapter.identity = lambda obj: object()
    if change == 'active': action.adapter.active_document = lambda: object()
    if change == 'state': feature.IsSuppressed2 = lambda *args: [True]
    if change == 'guard': action.adapter.application_busy = lambda: False
    if change == 'kind': action.binding.kind = 'sketch'
    if change == 'binding': action.registry.resolve = lambda *args, **kwargs: (object(), feature)
    with pytest.raises((JobError, AttributeError)): action.apply()
    assert calls == events == [] and action.receipt.attempted is False


@pytest.mark.parametrize('state', [[], [False, False], [0], [None]])
def test_incomplete_native_state_rejected(state):
    action, feature, calls, events = fixture()
    feature.IsSuppressed2 = lambda *args: state
    with pytest.raises(JobError): action.apply()
    assert calls == events == []


def test_noop_never_constructs_a_write():
    action, feature, calls, events = fixture()
    with pytest.raises(JobError, match='actual state transition'):
        NativeOwnedFeatureSuppression(action.registry, action.binding, False, recorder=action.recorder)
    assert calls == events == []
