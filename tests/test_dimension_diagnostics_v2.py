"""Exact passive evidence and failure reports; no native calls or acceptance."""

import importlib.util
import ast
import asyncio
import json
import math
from pathlib import Path

import pytest
from types import SimpleNamespace

MODULE = Path(__file__).resolve().parents[1] / 'scripts/verifier_dimension_diagnostics.py'
spec = importlib.util.spec_from_file_location('dimension_diagnostics_test', MODULE)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


@pytest.mark.parametrize('after', [
    {'deviation': math.nextafter(.00010488088481701516, math.inf), 'quality': 0},
    {'deviation': .00010488088481701516, 'quality': False},
    {'deviation': .00010488088481701516},
    {'deviation': .00010488088481701516, 'quality': 0, 'extra': 1},
])
def test_mismatch_retains_raw_values_with_one_reader_and_no_tolerance(after):
    before = {'deviation': .00010488088481701516, 'quality': 0}
    calls, report = [], {}
    def read():
        calls.append('read')
        return after
    with pytest.raises(AssertionError):
        diagnostics.assert_preference_snapshot(read, before, report, 'comparison')
    facts = report['comparison']
    assert calls == ['read'] and facts['before'] == before and facts['after'] == after
    assert facts['changed_fields'] and facts['snapshot_read'] and not facts['exactly_equal']
    assert facts['cause_inferred'] is False
    json.dumps(report, allow_nan=False)


def test_equal_and_reader_failure_never_trigger_another_read():
    report, calls = {}, []
    before = {'deviation': .00010488088481701516, 'quality': 0}
    def read():
        calls.append('read')
        return dict(before)
    diagnostics.assert_preference_snapshot(read, before, report, 'comparison')
    assert calls == ['read'] and report['comparison']['exactly_equal'] is True
    error = OSError('Reader failed')
    def fail():
        calls.append('fail')
        raise error
    with pytest.raises(OSError) as raised:
        diagnostics.assert_preference_snapshot(fail, before, report, 'comparison')
    assert raised.value is error and calls == ['read', 'fail']
    assert report['comparison']['after'] is None and not report['comparison']['snapshot_read']


def test_failure_report_exclusive_write_preserves_existing_artifact_and_primary_error(tmp_path):
    path = tmp_path / 'failure.json'
    original = AssertionError('Native evidence mismatch')
    report = {'original_document_baseline_restored': False, 'fixture_retention_required': True}
    diagnostics.write_failure_report(path, report, original)
    facts = json.loads(path.read_text())
    assert facts['accepted'] is False and facts['public_mcp_dimension_acceptance'] is False
    assert facts['fixture_retention_required'] is True and not facts['automatic_replay_attempted']
    before = path.read_bytes()
    diagnostics.write_failure_report(path, {'different': True}, original)
    assert path.read_bytes() == before
    assert any('FileExistsError' in note for note in original.__notes__)


def test_invalid_native_scalar_not_stringified_or_compared():
    class Native:
        def __str__(self):
            pytest.fail('Must not format a native object.')
        def __eq__(self, other):
            pytest.fail('Must not compare an unsupported native object.')
    report = {}
    with pytest.raises(ValueError):
        diagnostics.assert_preference_snapshot(lambda: {'deviation': Native()}, {'deviation': 1.}, report, 'comparison')
    assert report['comparison']['diagnostic_error_type'] == 'invalid_scalar_snapshot'
    assert report['comparison']['after'] is None
    json.dumps(report)


def test_actual_cli_failure_preserves_context_in_requested_report_and_original_error(tmp_path):
    script = MODULE.with_name('verify_dimension_mcp.py')
    tree = ast.parse(script.read_text(encoding='utf8'))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    private_root = tmp_path / 'project' / 'work'
    private_root.mkdir(parents=True)
    internal = private_root / 'internal.json'
    internal.write_text('{}')
    args = SimpleNamespace(state_dir=private_root / 'state', internal_report=internal,
                           report=private_root / 'failure.json')
    events = []
    original = AssertionError('Independent preference comparison failed')
    async def fail(state, internal_report, *, failure_report):
        events.append('check')
        assert state == args.state_dir.resolve() and internal_report == internal.resolve()
        failure_report.update(fixture_retention_required=True, owned_fixture_retained_count=2,
                              original_document_baseline_restored=False)
        raise original
    parser = SimpleNamespace(add_argument=lambda *args, **kwargs: None, parse_args=lambda: args)
    namespace = {'argparse': SimpleNamespace(ArgumentParser=lambda **kwargs: parser), 'Path': Path,
                 '__file__': str(tmp_path / 'project/scripts/verify_dimension_mcp.py'),
                 'pythoncom': SimpleNamespace(CoInitialize=lambda: events.append('initialize'),
                                               CoUninitialize=lambda: events.append('uninitialize')),
                 'asyncio': asyncio, 'check': fail, 'json': json,
                 'write_failure_report': diagnostics.write_failure_report}
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(script), 'exec'), namespace)
    with pytest.raises(AssertionError) as raised:
        namespace['main']()
    assert raised.value is original and events == ['initialize', 'check', 'uninitialize']
    facts = json.loads(args.report.read_text())
    assert facts['owned_fixture_retained_count'] == 2 and facts['fixture_retention_required'] is True
    assert facts['accepted'] is False and facts['original_document_baseline_restored'] is False
