"""Scheduling failures cannot become B3 native acceptance or further dispatch."""
import asyncio
from copy import deepcopy
import importlib.util
import math
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('b3_manifest',
    Path(__file__).resolve().parents[1] / 'scripts/verifier_b3_manifest.py')
module = importlib.util.module_from_spec(spec)
# dataclasses resolves module annotations via sys.modules.
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def setup_run(*, fail_case=None, safe_failure_at=None, persist_failure_at=None):
    dispatched, snapshots, safety = [], [], []
    def handler(case):
        dispatched.append(case.identifier)
        if case.identifier == fail_case:
            raise RuntimeError('native outcome unknown')
        return {'raw_observation': {'owner': case.identifier, 'scalar': 1.}}
    def safe():
        safety.append(len(dispatched))
        if len(safety) == safe_failure_at:
            raise RuntimeError('unresolved native hold')
    def persist(report):
        if len(snapshots) + 1 == persist_failure_at:
            raise OSError('durable store unavailable')
        snapshots.append(deepcopy(report))
    handlers = {case.identifier: handler for case in module.MANIFEST}
    return handlers, safe, persist, dispatched, snapshots, safety


def execute(value, **kwargs):
    handlers, safe, persist, *_ = value
    return asyncio.run(module.run_manifest(handlers=handlers,
        assert_dispatch_safe=safe, persist=persist,
        identity={'wheel_sha256': 'validated_by_driver'}, **kwargs))


def test_complete_recording_is_explicitly_not_native_acceptance():
    run = setup_run()
    report = execute(run)
    assert run[3] == [case.identifier for case in module.execution_order()]
    assert len(run[5]) == 26
    assert report['schedule_completed'] is True
    assert report['accepted'] is report['native_acceptance'] is False
    assert report['phase'] == 'awaiting_independent_acceptance'
    assert len(report['rows']) == 13


@pytest.mark.parametrize('change', ['missing', 'extra', 'not_callable'])
def test_partial_manifest_rejected_before_any_gate_or_dispatch(change):
    run = setup_run()
    if change == 'missing':run[0].pop('B3-I01')
    elif change == 'extra':run[0]['B3-I99'] = lambda _: {}
    else:run[0]['B3-I01'] = None
    with pytest.raises(ValueError):execute(run)
    assert run[3] == run[4] == run[5] == []


def test_handler_failure_preserves_running_case_and_never_starts_next():
    run = setup_run(fail_case='B3-I02')
    with pytest.raises(RuntimeError, match='unknown'):execute(run)
    assert run[3] == ['B3-I01', 'B3-I02']
    assert run[4][-1]['rows'][-1] == {'identifier': 'B3-I02', 'state': 'running', 'evidence': None}
    assert run[4][-1]['schedule_completed'] is False


@pytest.mark.parametrize('at,expected', [(1, []), (2, ['B3-I01']), (3, ['B3-I01'])])
def test_supervisor_refusal_before_or_after_native_return_stops_schedule(at, expected):
    run = setup_run(safe_failure_at=at)
    with pytest.raises(RuntimeError, match='hold'):execute(run)
    assert run[3] == expected
    assert run[4][-1]['accepted'] is False


@pytest.mark.parametrize('at,expected', [(1, []), (2, []), (3, ['B3-I01'])])
def test_durability_failure_never_replays_effect_or_dispatches_next(at, expected):
    run = setup_run(persist_failure_at=at)
    with pytest.raises(OSError):execute(run)
    assert run[3] == expected


@pytest.mark.parametrize('value', [None, {}, {'native_scalar': math.nan}])
def test_missing_or_nonfinite_evidence_retains_running_row(value):
    run = setup_run()
    run[0]['B3-I01'] = lambda _: value
    with pytest.raises(ValueError):execute(run)
    assert run[4][-1]['rows'][-1]['state'] == 'running'
    assert len(run[4][-1]['rows']) == 1


def test_cancellation_retains_evidence_and_cannot_advance():
    run = setup_run()
    async def cancelled(case):
        raise asyncio.CancelledError()
    run[0]['B3-I01'] = cancelled
    with pytest.raises(asyncio.CancelledError):execute(run)
    assert run[4][-1]['rows'][-1]['state'] == 'running'
    assert run[4][-1]['phase'] == 'B3-I01'


def test_async_callbacks_and_saved_reports_are_isolated():
    observations = {}
    saves = []
    async def handler(case):
        observations[case.identifier] = {'owner': case.identifier}
        return observations[case.identifier]
    async def safe():pass
    async def persist(report):
        saves.append(report)
        report['phase'] = 'caller_modified_copy'
    result = asyncio.run(module.run_manifest(
        handlers={case.identifier: handler for case in module.MANIFEST},
        assert_dispatch_safe=safe, persist=persist, identity={'wheel': 'candidate'}))
    observations['B3-I01']['owner'] = 'changed_later'
    assert result['phase'] == 'awaiting_independent_acceptance'
    assert result['rows'][0]['evidence']['owner'] == 'B3-I01'


def test_condition_coverage_requires_all_five_conditions_and_final_cleanup():
    assert {case.condition for case in module.MANIFEST} == {'N1', 'N2', 'N3', 'N4', 'N5'}
    assert module.execution_order()[-1].identifier == 'B3-I13'
    assert 'measurement_get_mass' in module.required_tools()
    assert 'full_baseline_restored' in module.execution_order()[-1].checks


def test_manifest_and_real_public_contract_have_identical_tool_coverage():
    scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
    sys.path.insert(0, scripts)
    try:
        from verifier_b3_public_contract import SPECS
    finally:
        sys.path.remove(scripts)
    assert module.required_tools() == frozenset(SPECS)
    assert len(module.required_tools()) == 27
