"""Verifier control-plane tests; no CAD connection or operation is performed."""

import importlib
import json
from pathlib import Path
import pytest


@pytest.fixture
def verifier(monkeypatch, tmp_path):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    monkeypatch.delenv('PYTHONPATH', raising=False)
    module = importlib.import_module('verify_mass_properties')
    verifier_path = tmp_path / 'scripts' / 'verify_mass_properties.py'
    verifier_path.parent.mkdir()
    verifier_path.write_bytes((scripts / 'verify_mass_properties.py').read_bytes())
    monkeypatch.setattr(module, '__file__', str(verifier_path))
    monkeypatch.setattr(module.pythoncom, 'CoInitialize', lambda: None)
    monkeypatch.setattr(module.pythoncom, 'CoUninitialize', lambda: None)
    monkeypatch.setattr(module.binding, 'connect', lambda **kw: pytest.fail('No CAD connection allowed'))
    return module


def arguments(module, monkeypatch, tmp_path, *, opt_in=True):
    state = tmp_path / 'work' / 'native-once'
    args = ['verify_mass_properties.py', '--wheel', str(tmp_path / 'candidate.whl'),
            '--expected-version', '2.0.0.dev31', '--expected-git-sha', 'a' * 40,
            '--state-dir', str(state)]
    if opt_in: args.append('--run-solidworks')
    monkeypatch.setattr('sys.argv', args)
    return state


def test_explicit_opt_in_is_checked_before_connection_or_state_creation(verifier, monkeypatch, tmp_path):
    state = arguments(verifier, monkeypatch, tmp_path, opt_in=False)
    with pytest.raises(SystemExit) as error: verifier.main()
    assert error.value.code == 2 and not state.exists()


def test_uninstalled_package_is_rejected_before_wheel_or_connection(verifier, monkeypatch, tmp_path):
    state = arguments(verifier, monkeypatch, tmp_path)
    monkeypatch.setattr(verifier.solidworks_mcp, '__file__', str(tmp_path / 'source' / '__init__.py'))
    monkeypatch.setattr(verifier.sysconfig, 'get_path', lambda kind: str(tmp_path / 'site-packages'))
    monkeypatch.setattr(verifier, 'validate_wheel', lambda *args, **kw: pytest.fail('Source package must be refused first'))
    with pytest.raises(AssertionError): verifier.main()
    assert not state.exists()


@pytest.mark.parametrize('existing_docs,busy', [(True, False), (False, True)])
def test_nonempty_or_busy_baseline_never_sets_flag_or_creates_fixture(verifier, monkeypatch, tmp_path, existing_docs, busy):
    state = arguments(verifier, monkeypatch, tmp_path)
    package = tmp_path / 'site-packages' / 'solidworks_mcp'
    package.mkdir(parents=True)
    (package / 'build_info.json').write_text(json.dumps({'git_sha': 'a' * 40, 'source_dirty': False}))
    monkeypatch.setattr(verifier.solidworks_mcp, '__file__', str(package / '__init__.py'))
    monkeypatch.setattr(verifier.solidworks_mcp, '__version__', '2.0.0.dev31')
    monkeypatch.setattr(verifier.sysconfig, 'get_path', lambda kind: str(package.parent))
    monkeypatch.setattr(verifier.importlib.metadata, 'version', lambda name: '2.0.0.dev31')
    monkeypatch.setattr(verifier, 'source_digest', lambda path: 'digest')
    monkeypatch.setattr(verifier, 'validate_wheel', lambda *args, **kw: {'source_digest': 'digest'})
    monkeypatch.setattr(verifier, 'native_snapshot', lambda: pytest.fail('Unsafe baseline must stop before further native observations'))
    monkeypatch.setattr(verifier, 'fixtures', lambda **kw: pytest.fail('Existing/busy session must not be edited'))
    class FakeSw:
        def GetDocuments(self): return [object()] if existing_docs else []
        @property
        def CommandInProgress(self): return busy
        @CommandInProgress.setter
        def CommandInProgress(self, value): pytest.fail('Foreign session flag must not be changed')
    monkeypatch.setattr(verifier.binding, 'connect', lambda **kw: FakeSw())
    with pytest.raises(AssertionError, match='agreed empty/free baseline'): verifier.main()
    report = json.loads((state / 'report.json').read_text())
    assert report['accepted'] is False and report['core_suite_passed'] is False
    assert report['cases'] == [] and 'guard_released' not in report


def test_source_pythonpath_is_rejected_before_connection(verifier, monkeypatch, tmp_path):
    state = arguments(verifier, monkeypatch, tmp_path)
    monkeypatch.setenv('PYTHONPATH', 'src')
    with pytest.raises(AssertionError, match='PYTHONPATH is prohibited'): verifier.main()
    assert not state.exists()
