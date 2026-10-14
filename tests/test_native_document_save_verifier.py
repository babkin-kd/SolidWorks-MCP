"""Native Save3 preflight gates, with no COM import or CAD connection."""

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
WHEEL = dict(package_version='2.0.0.dev82', git_sha='a' * 40,
             source_digest='b' * 64, wheel_sha256='c' * 64)


class NativeBoundaryReached(Exception):
    """Stop before COM initialization; an accepted preflight is not CAD evidence."""


def extract_function(path, name, namespace):
    tree = ast.parse(path.read_text(encoding='utf8'))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


@pytest.fixture
def preflight(monkeypatch, tmp_path):
    """Execute the real main gate, stopping at its first native boundary."""
    source = SCRIPTS / 'verify_native_document_save.py'
    script = tmp_path / 'scripts' / source.name
    script.parent.mkdir()
    script.write_bytes(source.read_bytes())
    fixture = script.with_name('verify_geometry_reads.py')
    fixture.write_bytes((SCRIPTS / fixture.name).read_bytes())
    lifecycle = script.with_name('verifier_lifecycle.py')
    lifecycle.write_bytes((SCRIPTS / lifecycle.name).read_bytes())
    events = []

    def validate(path, **expected):
        events.append(('wheel', path, expected))
        return dict(WHEEL)

    def installed(wheel):
        events.append(('installed', copy.deepcopy(wheel)))
        return tmp_path / 'site-packages' / 'solidworks-mcp-v2.exe'

    def native_boundary():
        events.append(('native_boundary',))
        raise NativeBoundaryReached

    tree = ast.parse(source.read_text(encoding='utf8'))
    counts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('INTERNAL_CASES', 'PUBLIC_CASES'):
                    counts[target.id] = ast.literal_eval(node.value)
    namespace = dict(argparse=argparse, Path=Path, os=os, json=json, hashlib=hashlib,
                     time=time, __file__=str(script), validate_wheel=validate,
                     installed_identity=installed,
                     pythoncom=SimpleNamespace(CoInitialize=native_boundary), **counts)
    # Only main is executed; top-level imports and all CAD bodies are excluded.
    main = extract_function(source, 'main', namespace)
    monkeypatch.delenv('PYTHONPATH', raising=False)
    return SimpleNamespace(main=main, namespace=namespace, events=events,
                           script=script, root=tmp_path, private=tmp_path / 'work')


def arguments(preflight, monkeypatch, *, opt_in=True, public=False, prior=None, state=None):
    state = state if state is not None else preflight.private / 'native-once'
    argv = ['verify_native_document_save.py', '--wheel', str(preflight.root / 'candidate.whl'),
            '--expected-version', WHEEL['package_version'], '--expected-git-sha', WHEEL['git_sha'],
            '--state-dir', str(state)]
    if opt_in:
        argv.append('--run-solidworks')
    if public:
        argv.append('--public')
    if prior is not None:
        argv.extend(['--internal-report', str(prior)])
    monkeypatch.setattr(sys, 'argv', argv)
    return state


def prior_report(preflight, **changes):
    prior = dict(accepted=True, scope='internal_native_current_file_save_v1',
                 cases=[dict(passed=True) for _ in range(preflight.namespace['INTERNAL_CASES'])],
                 verifier_sha256=hashlib.sha256(preflight.script.read_bytes()).hexdigest(),
                 fixture_sha256=hashlib.sha256(preflight.script.with_name('verify_geometry_reads.py').read_bytes()).hexdigest(),
                 lifecycle_sha256=hashlib.sha256(preflight.script.with_name('verifier_lifecycle.py').read_bytes()).hexdigest(),
                 wheel=dict(WHEEL))
    prior.update(changes)
    path = preflight.root / 'prior.json'
    path.write_text(json.dumps(prior), encoding='utf8')
    return path


def test_opt_in_precedes_wheel_installation_state_and_native(preflight, monkeypatch):
    state = arguments(preflight, monkeypatch, opt_in=False)
    with pytest.raises(SystemExit) as error:
        preflight.main()
    assert error.value.code == 2
    assert preflight.events == [] and not state.exists()


@pytest.mark.parametrize('pythonpath', ['src', 'source-checkout;other', ' '])
def test_nonempty_pythonpath_stops_before_wheel_or_native(preflight, monkeypatch, pythonpath):
    state = arguments(preflight, monkeypatch)
    monkeypatch.setenv('PYTHONPATH', pythonpath)
    with pytest.raises(AssertionError):
        preflight.main()
    assert preflight.events == [] and not state.exists()


@pytest.mark.parametrize('gate', ['validate_wheel', 'installed_identity'])
def test_wheel_and_installed_identity_rejections_precede_state_and_native(preflight, monkeypatch, gate):
    state = arguments(preflight, monkeypatch)

    def refuse(*args, **kwargs):
        raise ValueError('Rejected candidate')

    preflight.namespace[gate] = refuse
    with pytest.raises(ValueError, match='Rejected candidate'):
        preflight.main()
    assert not state.exists()
    assert not any(event[0] == 'native_boundary' for event in preflight.events)
    assert [event[0] for event in preflight.events] == ([] if gate == 'validate_wheel' else ['wheel'])


def test_valid_internal_gate_checks_exact_wheel_before_creating_fresh_private_state(preflight, monkeypatch):
    state = arguments(preflight, monkeypatch)
    with pytest.raises(NativeBoundaryReached):
        preflight.main()
    assert preflight.events == [
        ('wheel', preflight.root / 'candidate.whl',
         dict(expected_version=WHEEL['package_version'], expected_git_sha=WHEEL['git_sha'])),
        ('installed', WHEEL), ('native_boundary',)]
    assert state.is_dir() and list(state.iterdir()) == []


def test_public_requires_internal_receipt_before_native(preflight, monkeypatch):
    state = arguments(preflight, monkeypatch, public=True)
    with pytest.raises(AssertionError):
        preflight.main()
    assert not state.exists()
    assert [event[0] for event in preflight.events] == ['wheel', 'installed']


@pytest.mark.parametrize('change', [
    {'accepted': False}, {'scope': 'public_native_current_file_save_v1'},
    {'cases': [dict(passed=True)] * 9}, {'cases': [dict(passed=True)] * 11},
    {'verifier_sha256': '0' * 64}, {'fixture_sha256': '0' * 64}, {'lifecycle_sha256': '0' * 64},
    *[{'wheel': {**WHEEL, key: 'different'}} for key in WHEEL],
])
def test_public_refuses_incomplete_or_other_candidate_receipt(preflight, monkeypatch, change):
    prior = prior_report(preflight, **change)
    state = arguments(preflight, monkeypatch, public=True, prior=prior)
    original = prior.read_bytes()
    with pytest.raises(AssertionError):
        preflight.main()
    assert not state.exists() and prior.read_bytes() == original
    assert [event[0] for event in preflight.events] == ['wheel', 'installed']


def test_matching_public_receipt_reaches_only_native_boundary(preflight, monkeypatch):
    prior = prior_report(preflight)
    state = arguments(preflight, monkeypatch, public=True, prior=prior)
    with pytest.raises(NativeBoundaryReached):
        preflight.main()
    assert state.is_dir() and list(state.iterdir()) == []
    assert [event[0] for event in preflight.events] == ['wheel', 'installed', 'native_boundary']


@pytest.mark.parametrize('kind', ['private_root', 'outside', 'existing', 'escaped'])
def test_state_must_be_new_child_of_private_work(preflight, monkeypatch, kind):
    paths = dict(private_root=preflight.private, outside=preflight.root / 'outputs' / 'native',
                 existing=preflight.private / 'already-used',
                 escaped=preflight.private / '..' / 'escaped')
    state = paths[kind]
    marker = None
    if kind == 'existing':
        state.mkdir(parents=True)
        marker = state / 'report.json'
        marker.write_text('retain prior result', encoding='utf8')
    arguments(preflight, monkeypatch, state=state)
    with pytest.raises(AssertionError):
        preflight.main()
    assert [event[0] for event in preflight.events] == ['wheel', 'installed']
    if marker:
        assert marker.read_text(encoding='utf8') == 'retain prior result'
    else:
        assert not state.resolve().exists()


@pytest.fixture
def installed_gate(monkeypatch, tmp_path):
    """Real installed_identity against synthetic bytes, never an installed CAD test."""
    package_path = tmp_path / 'site-packages' / 'solidworks_mcp'
    package_path.mkdir(parents=True)
    package = ModuleType('solidworks_mcp')
    package.__file__ = str(package_path / '__init__.py')
    package.__version__ = WHEEL['package_version']
    build_info = ModuleType('solidworks_mcp.build_info')
    build_info.source_digest = lambda path: WHEEL['source_digest']
    monkeypatch.setitem(sys.modules, 'solidworks_mcp', package)
    monkeypatch.setitem(sys.modules, 'solidworks_mcp.build_info', build_info)
    monkeypatch.delenv('PYTHONPATH', raising=False)
    build = {**WHEEL, 'source_dirty': False, 'api_version': 2}
    (package_path / 'build_info.json').write_text(json.dumps(build), encoding='utf8')
    interpreter = tmp_path / 'bin' / 'python.exe'
    interpreter.parent.mkdir()
    entry = interpreter.with_name('solidworks-mcp-v2.exe')
    entry.write_bytes(b'synthetic entry; never executed')

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    namespace = dict(require=require, os=os, Path=Path, json=json,
                     sys=SimpleNamespace(executable=str(interpreter), platform='win32'),
                     sysconfig=SimpleNamespace(get_path=lambda kind: str(package_path.parent)),
                     metadata=SimpleNamespace(version=lambda name: WHEEL['package_version']))
    check = extract_function(SCRIPTS / 'verify_installed_metadata.py', 'installed_identity', namespace)
    return SimpleNamespace(check=check, package=package, path=package_path,
                           namespace=namespace, build=build, entry=entry)


def test_installed_identity_accepts_only_matching_synthetic_candidate(installed_gate):
    assert installed_gate.check(dict(WHEEL)) == installed_gate.entry


def test_installed_identity_rejects_checkout_location(installed_gate, tmp_path):
    installed_gate.package.__file__ = str(tmp_path / 'src' / 'solidworks_mcp' / '__init__.py')
    with pytest.raises(ValueError, match='outside this interpreter site-packages'):
        installed_gate.check(dict(WHEEL))


@pytest.mark.parametrize('field,value,message', [
    ('git_sha', 'different', 'SHA/cleanliness'), ('source_dirty', True, 'SHA/cleanliness'),
    ('source_dirty', 0, 'SHA/cleanliness'), ('package_version', 'different', 'API/version'),
    ('api_version', 1, 'API/version'), ('source_digest', 'different', 'source digest'),
])
def test_installed_identity_refuses_build_mismatch(installed_gate, field, value, message):
    build = {**installed_gate.build, field: value}
    (installed_gate.path / 'build_info.json').write_text(json.dumps(build), encoding='utf8')
    with pytest.raises(ValueError, match=message):
        installed_gate.check(dict(WHEEL))


def test_installed_identity_requires_actual_console_entry_file(installed_gate):
    installed_gate.entry.unlink()
    with pytest.raises(ValueError, match='entry point is missing'):
        installed_gate.check(dict(WHEEL))
