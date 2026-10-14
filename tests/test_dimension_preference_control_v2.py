"""Direct control orchestration and diagnostic I/O without any CAD imports."""

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('direct_dimension_control', ROOT / 'scripts/diagnose_dimension_preferences.py')
control = importlib.util.module_from_spec(spec)
# The helper's only import is pure; no native probe is started by importing it.
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    spec.loader.exec_module(control)
finally:
    sys.path.remove(str(ROOT / 'scripts'))


class Driver:
    def __init__(self, changed_at='rebuild'):
        self.changed_at = changed_at
        self.value = self.body_depth = .007
        self.deviation = .00010488088481701517
        self.quality = 3
        self.calls = []
        self.extra_fault = None
        self.evidence = {'original_state': 0, 'locked_state': 2, 'released_state': None}

    def assert_context(self):
        self.calls.append('context')

    def preferences(self):
        self.calls.append('preferences')
        result = {'stl_deviation': self.deviation, 'stl_quality': self.quality}
        if self.extra_fault:
            result.update(self.extra_fault)
        return result

    def geometry(self):
        self.calls.append('geometry')
        return {'depth_si': self.body_depth, 'complete_boundary': True}

    def depth(self):
        self.calls.append('depth')
        return self.value

    def guard(self):
        return self

    def __enter__(self):
        self.calls.append('lock')
        return self

    def __exit__(self, *arguments):
        self.calls.append('unlock')
        self.evidence['released_state'] = 0

    def change(self, phase):
        if phase == self.changed_at:
            self.deviation = .00011916375287812985 if self.value == .009 else .00010488088481701517

    def set_depth(self, value):
        self.calls.append(('setter', value))
        self.value = value
        self.change('setter')
        return 0

    def rebuild(self):
        self.calls.append('rebuild')
        self.body_depth = self.value
        self.change('rebuild')
        return True

    def assert_geometry_depth(self, value):
        self.calls.append('physical')
        assert self.body_depth == value


@pytest.mark.parametrize('phase', ['setter', 'rebuild', 'never'])
def test_control_locates_first_change_and_restores_exact_initial_scope(phase):
    driver, report, trace = Driver(phase), {}, []
    control.probe(driver, report, lambda value: trace.append(json.loads(json.dumps(value))))
    changed = [row['phase'] for row in report['steps'] if row['changed_fields_from_initial']]
    if phase == 'never':
        assert changed == []
    else:
        assert changed[0] == ('after_setter_0.009' if phase == 'setter' else 'after_rebuild_0.009')
    assert report['initial_preferences'] == report['final_preferences']
    assert report['diagnostic_completed'] and report['final_control_geometry_and_preferences_restored']
    assert report['accepted'] is report['public_mcp_dimension_acceptance'] is report['cause_inferred'] is False
    intentions = []
    for row in trace:
        pending = row.get('pending_native_action')
        if pending and (not intentions or pending != intentions[-1]):
            intentions.append(pending)
    assert intentions == [{'operation': operation, 'value_si': value}
                          for value in (.009, .007) for operation in ('SetSystemValue3', 'ForceRebuild3')]
    assert [call for call in driver.calls if isinstance(call, tuple)] == [('setter', .009), ('setter', .007)]
    # The preference observation immediately follows the target native action,
    # without an intervening context/geometry read that could itself alter it.
    for index, call in enumerate(driver.calls):
        if isinstance(call, tuple) or call == 'rebuild':
            assert driver.calls[index+1] == 'preferences'


@pytest.mark.parametrize('failure', ['checkpoint', 'setter', 'rebuild', 'other_preference', 'context'])
def test_failed_control_has_no_followup_native_read_rebuild_or_reversal(failure):
    driver, report, events = Driver(), {}, []
    error = OSError('Injected probe failure')
    original_setter = driver.set_depth
    def setter(value):
        result = original_setter(value)
        if failure == 'setter':
            raise error
        if failure == 'other_preference':
            driver.quality = False  # Typed equality rejects even an integer-like scalar.
        return result
    driver.set_depth = setter
    original_rebuild = driver.rebuild
    def rebuild():
        if failure == 'rebuild':
            driver.calls.append('rebuild_failed')
            raise error
        return original_rebuild()
    driver.rebuild = rebuild
    original_context = driver.assert_context
    def context():
        original_context()
        if failure == 'context' and driver.value == .009:
            raise error
    driver.assert_context = context
    def checkpoint(value):
        events.append(value.get('pending_native_action'))
        if failure == 'checkpoint' and value.get('pending_native_action'):
            raise error
    with pytest.raises((OSError, AssertionError)):
        control.probe(driver, report, checkpoint)
    assert report['diagnostic_completed'] is False
    writes = [call for call in driver.calls if isinstance(call, tuple)]
    assert writes == ([] if failure == 'checkpoint' else [('setter', .009)])
    if writes:
        assert driver.calls[-1] == 'unlock'
        assert 'physical' not in driver.calls
    assert report['accepted'] is False


def test_rebuild_bool_status_and_final_geometry_or_profile_are_not_weakened():
    driver, report = Driver(), {}
    driver.rebuild = lambda: 1
    with pytest.raises(AssertionError, match='rebuild'):
        control.probe(driver, report, lambda _: None)
    assert driver.value == .009 and not report['diagnostic_completed']
    driver = Driver()
    original_rebuild = driver.rebuild
    def rebuild():
        result = original_rebuild()
        if driver.value == .007:
            driver.deviation += 1e-20
        return result
    driver.rebuild = rebuild
    with pytest.raises(AssertionError, match='profile'):
        control.probe(driver, {}, lambda _: None)


def test_private_trace_is_exclusive_and_flushes_intention_before_call(tmp_path, monkeypatch):
    syncs = []
    monkeypatch.setattr(control.os, 'fsync', lambda descriptor: syncs.append(descriptor))
    path = tmp_path / 'trace.jsonl'
    trace = control.PrivateTrace(path)
    trace({'pending_native_action': {'operation': 'SetSystemValue3', 'value_si': .009}})
    assert json.loads(path.read_text())['pending_native_action']['value_si'] == .009
    assert len(syncs) == 1
    with pytest.raises(FileExistsError):
        control.PrivateTrace(path)
    trace.close()


def test_summary_write_never_overwrites_or_masks_original_error(tmp_path):
    path = tmp_path / 'report.json'
    control.save_summary(path, {'accepted': False}, None)
    original = RuntimeError('Native failure')
    control.save_summary(path, {'accepted': True}, original)
    assert json.loads(path.read_text()) == {'accepted': False}
    assert 'FileExistsError' in original.__notes__[0]
    with pytest.raises(FileExistsError):
        control.save_summary(path, {}, None)


@pytest.mark.parametrize('primary', [True, False])
def test_both_resource_closures_are_attempted_and_first_error_is_preserved(primary):
    events = []
    initial = RuntimeError('Native primary error')
    uninitialize_error, close_error = OSError('Uninitialize failed'), ValueError('Trace close failed')
    def uninitialize():
        events.append('uninitialize')
        raise uninitialize_error
    class Trace:
        def close(self):
            events.append('close')
            raise close_error
    if primary:
        control.close_probe_resources(Trace(), uninitialize, initial)
        assert len(initial.__notes__) == 2
    else:
        with pytest.raises(OSError) as raised:
            control.close_probe_resources(Trace(), uninitialize, None)
        assert raised.value is uninitialize_error and 'ValueError' in uninitialize_error.__notes__[0]
    assert events == ['uninitialize', 'close']


@pytest.mark.parametrize('failure', ['initialize', 'operation', 'summary'])
def test_actual_cli_preserves_primary_and_closes_trace_even_if_uninitialize_fails(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    state = tmp_path / 'project' / 'work' / 'state'
    monkeypatch.setattr(control, '__file__', str(tmp_path / 'project' / 'scripts' / 'diagnose_dimension_preferences.py'))
    parser = SimpleNamespace(add_argument=lambda *args, **kwargs: None,
                             parse_args=lambda: SimpleNamespace(state_dir=state))
    monkeypatch.setattr(control.argparse, 'ArgumentParser', lambda **kwargs: parser)
    events, reports = [], []
    initial = RuntimeError('Injected primary error')
    def initialize():
        events.append('initialize')
        if failure == 'initialize':
            raise initial
    def uninitialize():
        events.append('uninitialize')
        raise OSError('Injected uninitialize error')
    monkeypatch.setitem(sys.modules, 'pythoncom', SimpleNamespace(CoInitialize=initialize, CoUninitialize=uninitialize))
    class Trace:
        def __init__(self, path):
            events.append('trace_open')
        def __call__(self, report):
            reports.append(dict(report))
        def close(self):
            events.append('trace_close')
            raise ValueError('Injected trace close error')
    monkeypatch.setattr(control, 'PrivateTrace', Trace)
    def check(report, trace):
        events.append('check')
        if failure == 'operation':
            raise initial
    monkeypatch.setattr(control, 'check', check)
    if failure == 'summary':
        monkeypatch.setattr(control, 'save_summary', lambda *args: (_ for _ in ()).throw(initial))
    with pytest.raises(RuntimeError) as raised:
        control.main()
    assert raised.value is initial and events[-1] == 'trace_close'
    if failure == 'initialize':
        assert events == ['trace_open', 'initialize', 'trace_close']
        assert len(initial.__notes__) == 1
    else:
        assert events == ['trace_open', 'initialize', 'check', 'uninitialize', 'trace_close']
        assert len(initial.__notes__) == 2
    if failure != 'summary':
        facts = json.loads((state / 'report.json').read_text())
        assert facts['error_type'] == 'RuntimeError' and facts['diagnostic_completed'] is False
        assert facts['accepted'] is facts['public_mcp_dimension_acceptance'] is False
