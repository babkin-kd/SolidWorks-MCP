"""Pure fake-owner/SDK admission tests; not actual installed/CAD acceptance."""
from copy import deepcopy
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import anyio
import pytest
from mcp.types import JSONRPCMessage


spec = importlib.util.spec_from_file_location('_b4_installed_child_tests',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_b4_installed_child.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class FakeProcess:
    """Explicit artificial owner; no real OS exit/start/native proof."""
    def __init__(self):
        class CapturedStdin(io.BytesIO):
            def close(self):
                self.written = self.getvalue()
                super().close()
        self.pid = 777
        self.stdin, self.stdout = CapturedStdin(), io.BytesIO()
        self.code = None
        self.waits = []

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.code is None:
            raise subprocess.TimeoutExpired('pure-own-child', timeout)
        return self.code


@pytest.fixture
def harness(tmp_path, monkeypatch):
    candidate = dict(wheel={'wheel_sha256': 'a' * 64, 'package_version': 'pure', 'git_sha': 'b' * 40,
                           'source_digest': 'c' * 64},
        wheel_path='pure-wheel', package_root='pure/site-packages/solidworks_mcp',
        dependency_root='pure/site-packages', console_entrypoint='pure-v2', sdk_version='pure-sdk')
    launches = []
    process = FakeProcess()
    monkeypatch.setattr(helper, 'private_root', lambda: tmp_path)
    monkeypatch.setattr(helper, 'validate_candidate', lambda *args: deepcopy(candidate))
    monkeypatch.setattr(helper.owned, '_process_start', lambda *args: {'kind': 'pure_fake', 'ticks': 123})

    def popen(argv, **kwargs):
        launches.append(dict(argv=argv, kwargs=kwargs))
        return process

    monkeypatch.setattr(helper.subprocess, 'Popen', popen)
    child = helper.InstalledMetadataChild(tmp_path / 'own-child', wheel_path='pure-wheel',
        expected_version='pure', expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64)
    return child, process, launches, candidate


def ready(child):
    helper.owned._write(child.path / 'child-ready.json', dict(
        scope='b4_installed_child_ready_v1', identity=child.identity, **helper.flags()))
    return child.await_ready(0)


def false_native(result):
    assert result['native_q'] == result['server_recovery'] == result['restart'] == result['reconciliation'] == 'not_run'
    assert not result['accepted'] and not result['native_acceptance'] and not result['native_b4_accepted']
    assert result['cad_tools_called'] == result['job_tools_called'] == []


def test_fixed_launch_binds_original_handle_and_excludes_source_environment(harness):
    child, process, launches, candidate = harness
    assert child.process is process and child.identity['pid'] == process.pid
    assert child.identity['candidate'] == candidate
    assert len(child.identity['nonce']) == 64
    launch = launches[0]
    assert launch['argv'][1] == '-S'
    assert launch['argv'][2] == str(Path(helper.__file__).resolve())
    assert launch['argv'][3] == '--owned-installed-child'
    assert 'PYTHONPATH' not in launch['kwargs']['env']
    assert launch['kwargs']['env']['PYTHONNOUSERSITE'] == '1'
    proof = helper.owned._read(child.path / 'parent-launch.json')
    assert proof['identity'] == child.identity
    false_native(proof)


@pytest.mark.parametrize('change', ['pid', 'start', 'nonce', 'package', 'wheel', 'helper'])
def test_ready_rejects_foreign_original_binding(harness, change):
    child = harness[0]
    identity = deepcopy(child.identity)
    if change == 'pid': identity['pid'] += 1
    elif change == 'start': identity['start']['ticks'] += 1
    elif change == 'nonce': identity['nonce'] = 'foreign'
    elif change == 'package': identity['candidate']['package_root'] = 'source/src'
    elif change == 'wheel': identity['candidate']['wheel']['wheel_sha256'] = 'foreign'
    else: identity['helpers']['verifier_b4_installed_child.py'] = 'foreign'
    helper.owned._write(child.path / 'child-ready.json', dict(
        scope='b4_installed_child_ready_v1', identity=identity, **helper.flags()))
    with pytest.raises(helper.InstalledChildError, match='binding differs'):
        child.await_ready(0)
    assert child.ready is None and not child.eof_sent


def test_observation_timeout_keeps_original_fake_owner(harness):
    child, process, _, _ = harness
    assert child.await_ready(0) is None
    result = child.observe_exit(0)
    assert result['phase'] == 'owner_retained' and result['process_exit_observed'] is False
    assert child.process is process and not child.eof_sent
    false_native(result)


@pytest.mark.parametrize('method,params', [('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
    'clientInfo': {'name': 'pure', 'version': '1'}}), ('tools/list', {}),
    ('tools/call', {'name': 'system_get_info', 'arguments': {}})])
def test_admits_only_finite_metadata_requests(method, params):
    message = JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=1, method=method, params=params))
    encoded = helper.validate_outbound(message)
    assert encoded.endswith(b'\n') and method.encode() in encoded


def test_admits_initialized_notification():
    message = JSONRPCMessage.model_validate(dict(jsonrpc='2.0', method='notifications/initialized'))
    assert helper.validate_outbound(message).endswith(b'\n')


@pytest.mark.parametrize('method,params', [('tools/call', {'name': 'document_list', 'arguments': {}}),
    ('tools/call', {'name': 'job_get', 'arguments': {}}),
    ('tools/call', {'name': 'system_get_info', 'arguments': {'request_id': 'foreign'}}),
    ('tools/list', {'cursor': 'other'}), ('resources/read', {'uri': 'solidworks://guide/v2'}),
    ('ping', {}), ('notifications/cancelled', {'requestId': 1, 'reason': 'timeout'})])
def test_no_cad_jobs_discovery_or_cancellation_admission(method, params):
    message = JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=1, method=method, params=params))
    with pytest.raises(helper.InstalledChildError):
        helper.validate_outbound(message)


def test_sdk_metadata_consumer_uses_exact_three_metadata_calls(monkeypatch):
    calls = []

    class Client:
        async def initialize(self): calls.append('initialize')
        async def list_tools(self):
            calls.append('tools/list')
            return SimpleNamespace(tools=['pure-tools'])
        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            return SimpleNamespace(isError=False, structuredContent=dict(status='succeeded', error=None,
                                                                       data={'pure_info': True}))

    def verify(tools, info, wheel):
        assert tools == ['pure-tools'] and info == {'pure_info': True} and wheel == {'pure_wheel': True}
        return {'pure_catalog': True}

    monkeypatch.setattr(helper, 'sibling', lambda *args: SimpleNamespace(verify_metadata=verify))
    result = anyio.run(helper.consume_metadata, Client(), {'pure_wheel': True})
    assert result == {'pure_catalog': True}
    assert calls == ['initialize', 'tools/list', ('system_get_info', {})]


@pytest.mark.parametrize('exit_code,journal,sdk_closed', [(1, [], True), (0, [{'foreign': 'job'}], True),
                                                      (0, [], False), (0, [], True)])
def test_real_receipt_checks_normal_return_sdk_close_and_complete_empty_journal(harness, monkeypatch,
                                                                             exit_code, journal, sdk_closed):
    child, process, _, _ = harness
    ready(child)
    child.catalog, child.sdk_closed, child.eof_sent = {'pure_catalog': True}, sdk_closed, True
    process.code = exit_code
    helper.owned._write(child.path / 'child-normal-return.json', dict(identity=child.identity,
                                                                  normal_server_return=True, **helper.flags()))
    monkeypatch.setattr(helper, 'sibling', lambda *args: SimpleNamespace(read_journal=lambda path: journal))
    result = child.observe_exit(0)
    assert result['process_exit_observed'] is True
    assert result['metadata_process_passed'] == (exit_code == 0 and journal == [] and sdk_closed is True)
    assert result['profile_passed'] == result['metadata_process_passed']
    assert result['finish_seam_wiring_passed'] is False
    false_native(result)
    assert child.observe_exit(0) == result


def test_post_popen_error_retains_exact_handle(harness, tmp_path, monkeypatch):
    _, process, _, _ = harness
    monkeypatch.setattr(helper.owned, '_process_start', lambda *args: (_ for _ in ()).throw(OSError('pure-start-failure')))
    with pytest.raises(helper.InstalledChildError) as caught:
        helper.InstalledMetadataChild(tmp_path / 'failed-owned-child', wheel_path='pure',
            expected_version='pure', expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64)
    assert caught.value.retained_owner.process is process
    assert caught.value.retained_owner.launch_failed is not None
    assert not caught.value.retained_owner.eof_sent


def test_metadata_transport_normal_eof_without_sdk_process_termination(harness):
    child, process, _, _ = harness
    ready(child)

    async def run():
        async with child.transport() as streams:
            assert len(streams) == 2

    anyio.run(run)
    assert child.eof_sent and child.sdk_closed and process.stdin.closed
    assert process.code is None  # EOF itself is never an OS exit receipt.
    assert not process.waits


def test_one_shot_metadata_eof_and_probe(harness):
    child = harness[0]
    child._send_eof()
    with pytest.raises(helper.InstalledChildError, match='one-shot'):
        child._send_eof()
    child.probe_attempted = True
    with pytest.raises(helper.InstalledChildError, match='One original'):
        anyio.run(child.metadata_probe)


@pytest.mark.parametrize('timeout', [-1, 61, True, '1'])
def test_invalid_observations_have_no_process_actions(harness, timeout):
    child = harness[0]
    with pytest.raises(helper.InstalledChildError, match='Bounded'):
        child.await_ready(timeout)
    with pytest.raises(helper.InstalledChildError, match='Bounded'):
        child.observe_exit(timeout)
    assert not child.eof_sent and not harness[1].waits


def test_parent_launch_persistence_failure_retains_handle_and_blocks_probe(harness, tmp_path, monkeypatch):
    _, process, _, _ = harness
    original = helper.owned._write

    def fail_parent_launch(path, value):
        if Path(path).name == 'parent-launch.json':
            raise OSError('pure-parent-launch-failure')
        return original(path, value)

    monkeypatch.setattr(helper.owned, '_write', fail_parent_launch)
    with pytest.raises(helper.InstalledChildError) as caught:
        helper.InstalledMetadataChild(tmp_path / 'failed-persist-child', wheel_path='pure',
            expected_version='pure', expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64)
    child = caught.value.retained_owner
    assert child.process is process and child.identity is not None and child.launch_failed is not None
    with pytest.raises(helper.InstalledChildError, match='One original'):
        anyio.run(child.metadata_probe)
    assert not child.eof_sent


def test_terminal_before_ready_has_bounded_private_stderr(harness):
    child, process, _, _ = harness
    (child.path / 'child-stderr.log').write_bytes(b'prefix' + b'x' * 6000 + b'last-cause')
    process.code = 8
    with pytest.raises(helper.InstalledChildError) as caught:
        child.await_ready(0)
    assert 'exit_code=8' in str(caught.value) and 'last-cause' in str(caught.value)
    assert 'prefix' not in str(caught.value) and len(str(caught.value)) < 4300
    assert caught.value.retained_owner is child and not child.eof_sent


def test_transport_rejected_cad_message_never_reaches_fake_stdin_and_no_force_stop(harness):
    from mcp.shared.message import SessionMessage
    child, process, _, _ = harness
    ready(child)
    message = SessionMessage(JSONRPCMessage.model_validate(dict(jsonrpc='2.0', id=1, method='tools/call',
        params={'name': 'document_list', 'arguments': {}})))

    async def run():
        async with child.transport() as (_, write):
            await write.send(message)
            await anyio.sleep(.01)

    with pytest.raises(BaseExceptionGroup) as caught:
        anyio.run(run)
    assert isinstance(caught.value.exceptions[0], helper.InstalledChildError)
    assert process.stdin.closed and child.eof_sent
    assert process.stdin.written == b''
    assert child.sdk_closed is False and process.code is None and not process.waits


def test_candidate_preflight_rejects_source_pythonpath_before_wheel_check(monkeypatch):
    monkeypatch.setenv('PYTHONPATH', 'foreign/source')
    with pytest.raises(helper.InstalledChildError, match='PYTHONPATH unset'):
        helper.validate_candidate('not-opened-wheel', 'pure', 'a' * 40, 'b' * 64)


def test_candidate_wheel_sha_refusal_precedes_installed_identity(monkeypatch):
    monkeypatch.delenv('PYTHONPATH', raising=False)
    calls = []
    checker = SimpleNamespace(validate_wheel=lambda *args, **kwargs: {'wheel_sha256': 'wrong'},
        installed_identity=lambda wheel: calls.append('must-not-call'))
    monkeypatch.setattr(helper, 'sibling', lambda *args: checker)
    with pytest.raises(helper.InstalledChildError, match='wheel SHA256 mismatch'):
        helper.validate_candidate('pure', 'pure', 'a' * 40, 'b' * 64)
    assert calls == []


@pytest.fixture
def fake_windows_layout(tmp_path, monkeypatch):
    root = tmp_path / 'installed-dependencies'
    for relative in ('win32/lib', 'pythonwin', 'pywin32_system32'):
        (root / relative).mkdir(parents=True)
    tag = f'{sys.version_info.major}{sys.version_info.minor}'
    files = ('pythoncom.py', 'win32/lib/pywintypes.py', 'win32/_win32sysloader.pyd',
             'win32/win32api.pyd', 'win32/win32job.pyd', f'pywin32_system32/pywintypes{tag}.dll',
             f'pywin32_system32/pythoncom{tag}.dll')
    for name in files:
        (root / name).write_bytes(('pure-fake:' + name).encode())
    monkeypatch.setattr(helper.metadata, 'version', lambda name: 'pure-pywin32' if name == 'pywin32' else 'pure-sdk')
    return root, files


def test_windows_dependency_facts_are_finite_anchored_and_hashed(fake_windows_layout):
    root, files = fake_windows_layout
    facts = helper.windows_dependency_facts(root, windows=True)
    assert facts['dependency_root'] == str(root.resolve())
    assert facts['import_paths'] == [str(root / name) for name in ('win32', 'win32/lib', 'pythonwin')]
    assert facts['dll_directory'] == str(root / 'pywin32_system32')
    assert facts['pywin32_version'] == 'pure-pywin32'
    assert set(facts['file_sha256']) == set(files)
    assert all(len(value) == 64 for value in facts['file_sha256'].values())


@pytest.mark.parametrize('relative', ['win32/lib', 'pythonwin', 'pywin32_system32'])
def test_windows_dependency_missing_required_directory_rejected(fake_windows_layout, relative):
    root, _ = fake_windows_layout
    # Own pure layout, no installed files. Rename in-place avoids recursive delete.
    (root / relative).rename(root / ('missing-' + relative.replace('/', '-')))
    with pytest.raises(helper.InstalledChildError, match='directories required'):
        helper.windows_dependency_facts(root, windows=True)


def test_windows_dependency_missing_required_dll_rejected(fake_windows_layout):
    root, files = fake_windows_layout
    (root / files[-1]).unlink()
    with pytest.raises(helper.InstalledChildError, match='bootstrap/DLL files required'):
        helper.windows_dependency_facts(root, windows=True)


def test_windows_dependency_redirected_canonical_directory_rejected(fake_windows_layout, tmp_path, monkeypatch):
    root, _ = fake_windows_layout
    foreign = tmp_path / 'foreign-pythonwin'
    foreign.mkdir()
    original_resolve = Path.resolve

    def redirected_resolve(path, *args, **kwargs):
        # Artificial canonical redirection exercises this exact refusal without
        # requiring Windows symlink privileges or touching installed layout.
        if path == root / 'pythonwin':
            return original_resolve(foreign)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'resolve', redirected_resolve)
    with pytest.raises(helper.InstalledChildError, match='directories required'):
        helper.windows_dependency_facts(root, windows=True)


def test_explicit_windows_bootstrap_retains_dll_handle_without_executing_pth(fake_windows_layout, monkeypatch):
    root, _ = fake_windows_layout
    facts = helper.windows_dependency_facts(root, windows=True)
    (root / 'untrusted.pth').write_text("raise RuntimeError('must not execute')", encoding='utf8')
    monkeypatch.setattr(helper, 'windows_dependency_facts', lambda dependency: deepcopy(facts))
    monkeypatch.setattr(sys, 'path', list(sys.path))
    calls = []
    handle = SimpleNamespace(close=lambda: calls.append('closed'))
    monkeypatch.setattr(os, 'add_dll_directory', lambda directory: calls.append(directory) or handle, raising=False)
    handles = helper.activate_dependency_bootstrap(dict(dependency_root=str(root), windows_dependencies=facts))
    assert handles == [handle]
    assert calls == [str(root / 'pywin32_system32')]
    assert sys.path[:4] == [str(root), *facts['import_paths']]
    assert 'closed' not in calls


@pytest.mark.parametrize('change', ['dll_path', 'import_path', 'version', 'hash'])
def test_parent_child_windows_dependency_mismatch_before_activation(fake_windows_layout, monkeypatch, change):
    root, _ = fake_windows_layout
    actual = helper.windows_dependency_facts(root, windows=True)
    expected = deepcopy(actual)
    if change == 'dll_path': expected['dll_directory'] = 'foreign'
    elif change == 'import_path': expected['import_paths'][0] = 'foreign'
    elif change == 'version': expected['pywin32_version'] = 'foreign'
    else: expected['file_sha256']['pythoncom.py'] = 'foreign'
    monkeypatch.setattr(helper, 'windows_dependency_facts', lambda dependency: deepcopy(actual))
    calls = []
    monkeypatch.setattr(os, 'add_dll_directory', lambda directory: calls.append(directory), raising=False)
    with pytest.raises(helper.InstalledChildError, match='dependency identity mismatch'):
        helper.activate_dependency_bootstrap(dict(dependency_root=str(root), windows_dependencies=expected))
    assert not calls


def test_child_ready_only_after_real_entrypoint_import_and_before_main(tmp_path, monkeypatch):
    package = tmp_path / 'solidworks_mcp'
    package.mkdir()
    state = tmp_path / 'state'
    state.mkdir()
    events = []
    identity = {'pure': 'original-binding'}
    expected = {'console_entrypoint': 'pure-installed-v2', 'windows_dependencies': {'windows': False}}

    def main():
        events.append('main')
        assert (state / 'child-ready.json').is_file()
        assert not (state / 'child-normal-return.json').exists()
        assert sys.argv == ['pure-installed-v2', '--state-dir', str(state / 'server')]

    def import_module(name):
        assert name == 'solidworks_mcp.server_v2'
        assert not (state / 'child-ready.json').exists()
        events.append('import')
        return SimpleNamespace(__file__=str(package / 'server_v2.py'), main=main)

    monkeypatch.setattr(helper.importlib, 'import_module', import_module)
    monkeypatch.setattr(sys, 'argv', list(sys.argv))
    assert helper.run_verified_entrypoint(state, package, expected, identity) == 0
    assert events == ['import', 'main']
    assert helper.owned._read(state / 'child-ready.json')['identity'] == identity
    assert helper.owned._read(state / 'child-normal-return.json')['normal_server_return'] is True


def test_failed_server_import_never_publishes_child_ready(tmp_path, monkeypatch):
    def failed_import(name):
        raise ModuleNotFoundError('pure-pywintypes-missing')

    monkeypatch.setattr(helper.importlib, 'import_module', failed_import)
    with pytest.raises(ModuleNotFoundError, match='pywintypes'):
        helper.run_verified_entrypoint(tmp_path, tmp_path / 'solidworks_mcp', {}, {})
    assert not (tmp_path / 'child-ready.json').exists()
    assert not (tmp_path / 'child-normal-return.json').exists()


def test_foreign_server_module_never_publishes_child_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(helper.importlib, 'import_module', lambda name:
        SimpleNamespace(__file__=str(tmp_path / 'foreign.py'), main=lambda: pytest.fail('foreign main forbidden')))
    with pytest.raises(helper.InstalledChildError, match='installed server entrypoint required'):
        helper.run_verified_entrypoint(tmp_path, tmp_path / 'solidworks_mcp', {}, {})
    assert not (tmp_path / 'child-ready.json').exists()


@pytest.mark.parametrize('foreign', [False, True])
def test_actual_loaded_windows_modules_must_match_bound_install(fake_windows_layout, monkeypatch, foreign):
    root, _ = fake_windows_layout
    facts = helper.windows_dependency_facts(root, windows=True)
    tag = f'{sys.version_info.major}{sys.version_info.minor}'
    bindings = {'pywintypes': root / f'pywin32_system32/pywintypes{tag}.dll',
                '_win32sysloader': root / 'win32/_win32sysloader.pyd',
                'win32api': root / 'win32/win32api.pyd', 'win32job': root / 'win32/win32job.pyd'}
    for name, path in bindings.items():
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(__file__=str(path)))
    candidate = dict(dependency_root=str(root), windows_dependencies=facts)
    if foreign:
        monkeypatch.setitem(sys.modules, 'pywintypes', SimpleNamespace(__file__=str(root.parent / 'foreign.dll')))
        with pytest.raises(helper.InstalledChildError, match='Actual loaded Windows dependency'):
            helper.verify_loaded_windows_dependencies(candidate)
    else:
        helper.verify_loaded_windows_dependencies(candidate)


def test_real_lifecycle_sibling_import_registers_postponed_dataclasses(monkeypatch):
    import dataclasses
    name = '_b4_installed_real_lifecycle_regression'
    # The real module imports its real passive siblings, not mocked schemas.
    # This regression directly reproduces the post-exit audit import route.
    monkeypatch.setitem(sys.modules, name, SimpleNamespace(prior='pure-old-binding'))
    module = helper.sibling('verifier_lifecycle.py', name)
    assert sys.modules[name] is module
    assert dataclasses.is_dataclass(module.ToolSpec)
    assert dataclasses.is_dataclass(module.TrackedRequest)
    spec = module.ToolSpec(operation='pure.metadata', mutates=False)
    assert spec.operation == 'pure.metadata' and spec.mutates is False
    assert callable(module.read_journal)


@pytest.mark.parametrize('prior_present', [False, True])
def test_failed_sibling_import_restores_exact_registry_and_search_path(tmp_path, monkeypatch, prior_present):
    name = '_b4_installed_failed_import_regression'
    old = SimpleNamespace(prior='exact-old-module')
    if prior_present:
        monkeypatch.setitem(sys.modules, name, old)
    else:
        monkeypatch.delitem(sys.modules, name, raising=False)
    source = tmp_path / 'own-failing-helper.py'
    source.write_text('from __future__ import annotations\nfrom dataclasses import dataclass\n'
        '@dataclass\nclass Probe:\n    value: str\n'
        'raise RuntimeError("own-import-error-after-dataclass")\n', encoding='utf8')
    original_factory = helper.importlib.util.spec_from_file_location
    monkeypatch.setattr(helper.importlib.util, 'spec_from_file_location',
        lambda selected_name, path: original_factory(selected_name, source))
    previous_path = sys.path[:]
    with pytest.raises(RuntimeError, match='own-import-error-after-dataclass'):
        helper.sibling('own-failing-helper.py', name)
    assert sys.path == previous_path
    if prior_present:
        assert sys.modules[name] is old
    else:
        assert name not in sys.modules


@pytest.mark.parametrize('profile', ['metadata', 'finish_seam', 'dimension_control', 'dimension_commands', 'dimension_commands_live'])
def test_profile_binds_fixed_helper_manifest_spec_and_original_identity(harness, tmp_path, profile):
    child = helper.InstalledMetadataChild(tmp_path / ('profile-' + profile), wheel_path='pure',
        expected_version='pure', expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64, profile=profile)
    assert child.profile == child.spec['profile'] == child.identity['profile'] == profile
    extras = {'metadata': (), 'finish_seam': helper.SEAM_HELPERS,
              'dimension_control': helper.SEAM_HELPERS + ('verifier_b4_installed_dimension_control.py',
                                                        'verifier_b4_dimension_return.py'),
              'dimension_commands': helper.SEAM_HELPERS + ('verifier_b4_installed_dimension_control.py',
                  'verifier_b4_dimension_return.py', 'verifier_b4_dimension_control_commands.py'),
              'dimension_commands_live': helper.LIVE_COMMAND_HELPERS}
    assert set(child.helpers) == set(helper.HELPERS) | set(extras[profile])
    with pytest.raises(AttributeError):
        child.profile = 'other'


@pytest.mark.parametrize('profile', ['arm', 'cad', 'restart', True, ['finish_seam']])
def test_unsupported_profile_refused_before_preflight_or_launch(tmp_path, monkeypatch, profile):
    monkeypatch.setattr(helper, 'validate_candidate', lambda *args: pytest.fail('No preflight for foreign profile'))
    with pytest.raises(helper.InstalledChildError, match='Fixed metadata/finish_seam'):
        helper.InstalledMetadataChild(tmp_path / 'not-created', wheel_path='pure', expected_version='pure',
            expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64, profile=profile)
    assert not (tmp_path / 'not-created').exists()


def test_finish_profile_installs_actual_store_runtime_seam_before_main_and_restores(tmp_path, monkeypatch):
    from solidworks_mcp.jobs import JobStore
    from solidworks_mcp.runtime_v2 import Runtime
    path, package = tmp_path / 'state', tmp_path / 'solidworks_mcp'
    path.mkdir()
    package.mkdir()
    module = SimpleNamespace(__file__=str(package / 'server_v2.py'), JobStore=JobStore, Runtime=Runtime)
    observations = []

    def main():
        # Actual JobStore/Runtime construction through the real new seam; no
        # worker is ever created, no dispatch/job/native call takes place.
        assert module.JobStore is not JobStore and module.Runtime is not Runtime
        assert (path / 'child-ready.json').exists()
        store = module.JobStore(path / 'server' / 'jobs.sqlite')
        runtime = module.Runtime(store)
        observations.append((store, runtime))
        assert runtime.store is store and runtime._runner is None
        assert store.barrier is None and store.state == 'unarmed'
        assert runtime.shutdown() is True

    module.main = main
    monkeypatch.setattr(helper.importlib, 'import_module', lambda name: module)
    monkeypatch.setattr(sys, 'argv', list(sys.argv))
    identity = {'profile': 'finish_seam', 'pure': 'original-binding'}
    expected = {'console_entrypoint': 'pure-v2', 'windows_dependencies': {'windows': False}}
    assert helper.run_verified_entrypoint(path, package, expected, identity, profile='finish_seam') == 0
    assert len(observations) == 1 and module.JobStore is JobStore and module.Runtime is Runtime
    receipt = helper.owned._read(path / 'finish-seam-wiring.json')
    assert helper.validate_seam_receipt(receipt, identity=identity,
        journal_path=path / 'server' / 'jobs.sqlite') == receipt
    assert receipt['complete_journal'] == []
    assert all(receipt[key] is True for key in helper.SEAM_CHECKS)
    assert not (path / 'finish-barrier.json').exists()
    false_native(receipt)


def test_barrier_persistence_callback_is_one_shot_even_after_failed_write(tmp_path, monkeypatch):
    from solidworks_mcp.jobs import JobStore
    from solidworks_mcp.runtime_v2 import Runtime
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, main=lambda: None)
    owner = helper.MetadataFinishOwner(module, tmp_path, {'profile': 'finish_seam'})
    original_write = helper.owned._write

    def failed_write(path, value):
        raise OSError('pure-durable-write-failure')

    monkeypatch.setattr(helper.owned, '_write', failed_write)
    with pytest.raises(OSError, match='pure-durable-write-failure'):
        owner.persist_barrier({'pure': 'barrier-receipt'})
    monkeypatch.setattr(helper.owned, '_write', original_write)
    with pytest.raises(helper.InstalledChildError, match='one-shot'):
        owner.persist_barrier({'pure': 'barrier-receipt'})
    assert owner.persist_attempted and not (tmp_path / 'finish-barrier.json').exists()
    owner.seam.uninstall()


def valid_seam_receipt(child):
    return dict(scope='b4_installed_unarmed_finish_seam_v1', identity=deepcopy(child.identity),
        journal_path=str((child.path / 'server' / 'jobs.sqlite').resolve()), complete_journal=[],
        **{key: True for key in helper.SEAM_CHECKS}, **helper.flags())


@pytest.mark.parametrize('change', ['missing', 'extra', 'foreign_identity', 'journal', 'bool_as_int',
                                   'native_q', 'native_admission', 'process_stop', 'authority_int', 'armed', 'none'])
def test_frozen_seam_receipt_refuses_incomplete_foreign_or_native_claim(harness, change):
    child = harness[0]
    value = valid_seam_receipt(child)
    if change == 'missing': value.pop('original_store_retained')
    elif change == 'extra': value['target_id'] = 'unsupported'
    elif change == 'foreign_identity': value['identity']['nonce'] = 'foreign'
    elif change == 'journal': value['complete_journal'] = [{'unknown': 'job'}]
    elif change == 'bool_as_int': value['runner_absent'] = 1
    elif change == 'native_q': value['native_q'] = 'proven'
    elif change == 'native_admission': value['native_admission'] = 'proven'
    elif change == 'process_stop': value['process_stop_authorized'] = True
    elif change == 'authority_int': value['accepted'] = 0
    elif change == 'armed': value['proxy_unarmed'] = False
    else: value = None
    with pytest.raises(helper.InstalledChildError):
        helper.validate_seam_receipt(value, identity=child.identity,
                                    journal_path=child.path / 'server' / 'jobs.sqlite')


@pytest.mark.parametrize('seam_valid', [False, True, 'missing', 'unexpected_barrier'])
def test_parent_seam_wiring_is_separate_from_metadata_success(harness, tmp_path, monkeypatch, seam_valid):
    _, process, _, _ = harness
    child = helper.InstalledMetadataChild(tmp_path / 'finish-profile-exit', wheel_path='pure', expected_version='pure',
        expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64, profile='finish_seam')
    ready(child)
    child.catalog, child.sdk_closed, child.eof_sent = {'pure_catalog': True}, True, True
    process.code = 0
    helper.owned._write(child.path / 'child-normal-return.json', dict(identity=child.identity,
                                                                  normal_server_return=True, **helper.flags()))
    value = valid_seam_receipt(child)
    if seam_valid is False: value['runner_absent'] = False
    if seam_valid != 'missing': helper.owned._write(child.path / 'finish-seam-wiring.json', value)
    if seam_valid == 'unexpected_barrier':
        helper.owned._write(child.path / 'finish-barrier.json', {'pure': 'unexpected-barrier'})
    monkeypatch.setattr(helper, 'sibling', lambda *args: SimpleNamespace(read_journal=lambda path: []))
    result = child.observe_exit(0)
    assert result['metadata_process_passed'] is True
    assert result['finish_seam_wiring_passed'] == result['profile_passed'] == (seam_valid is True)
    false_native(result)


def valid_control_receipt(child):
    closed = dict(scope='b4_installed_dimension_control_closed_v1',
        lineage=helper.control_lineage(child.identity, child.path), target=None, journal=[],
        original_factories_restored=True, **helper.CONTROL_AUTHORITY)
    return dict(scope='b4_installed_unarmed_dimension_control_v1', identity=deepcopy(child.identity),
        journal_path=str((child.path / 'server' / 'jobs.sqlite').resolve()), complete_journal=[],
        controller_receipt=closed, **{key: True for key in helper.CONTROL_CHECKS}, **helper.flags())


def valid_inspection_ack(child):
    lineage = helper.control_lineage(child.identity, child.path)
    state = dict(scope='b4_installed_dimension_control_state_v1', phase='unarmed', fault=None,
        lineage=lineage, target=None, persist_attempted={'callback': False, 'finish': False},
        receipts={'callback': None, 'finish': None}, return_observation=None, barrier_state=None,
        **helper.CONTROL_AUTHORITY)
    return dict(scope='b4_dimension_control_command_ack_v1', sequence=1, nonce=child.identity['nonce'],
        lineage=deepcopy(lineage), command='inspect', arguments={}, result=deepcopy(state),
        controller_state=deepcopy(state), **helper.CONTROL_AUTHORITY)


def valid_live_host(child):
    ack = valid_inspection_ack(child)
    state = dict(scope='b4_dimension_control_command_receiver_state_v1', closed=True, fault=None,
        lineage=deepcopy(ack['lineage']), command_limit=1, allowed_commands=['inspect'], next_sequence=None,
        attempted=1, action_completed=1, acknowledged=1, last_controller_state=deepcopy(ack['controller_state']),
        last_ack=ack, **helper.CONTROL_AUTHORITY)
    return dict(scope='b4_dimension_command_host_state_v1', phase='completed', fault=None, action_live=False,
        completed_commands=1, lineage=deepcopy(ack['lineage']), receiver_state=state,
        runtime_open_at_last_action=True, thread_return_observed=True, **helper.CONTROL_AUTHORITY)


@pytest.mark.parametrize('change', ['live', 'closed_runtime', 'thread_live', 'bool_count', 'lineage',
    'extra', 'authority', 'budget', 'allowlist', 'receiver_fault', 'ack', 'ack_count'])
def test_live_host_receipt_refuses_unfinished_foreign_or_authorizing_state(harness, change):
    child = harness[0]
    value = valid_live_host(child)
    helper.owned._write(child.path / 'dimension-command-ack-0001.json', valid_inspection_ack(child))
    if change == 'live': value['action_live'] = True
    elif change == 'closed_runtime': value['runtime_open_at_last_action'] = False
    elif change == 'thread_live': value['thread_return_observed'] = False
    elif change == 'bool_count': value['completed_commands'] = True
    elif change == 'lineage': value['lineage']['nonce'] = 'foreign'
    elif change == 'extra': value['q'] = True
    elif change == 'authority': value['cad_cleanup_authorized'] = True
    elif change == 'budget': value['receiver_state']['command_limit'] = 2
    elif change == 'allowlist': value['receiver_state']['allowed_commands'].append('arm')
    elif change == 'receiver_fault': value['receiver_state']['fault'] = 'unknown'
    elif change == 'ack': value['receiver_state']['last_ack']['nonce'] = 'foreign'
    else: value['receiver_state']['acknowledged'] = True
    with pytest.raises(helper.InstalledChildError):
        helper.validate_live_host(value, identity=child.identity, path=child.path)


@pytest.mark.parametrize('host_valid', [True, False, 'missing'])
def test_parent_live_host_gate_is_separate_from_metadata_control_and_ack(harness, tmp_path, monkeypatch, host_valid):
    _, process, _, _ = harness
    child = helper.InstalledMetadataChild(tmp_path / 'live-host-exit', wheel_path='pure',
        expected_version='pure', expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64,
        profile='dimension_commands_live')
    ready(child)
    child.catalog, child.sdk_closed, child.eof_sent = {'pure_catalog': True}, True, True
    process.code = 0
    helper.owned._write(child.path / 'child-normal-return.json', dict(identity=child.identity,
                                                                  normal_server_return=True, **helper.flags()))
    control = valid_control_receipt(child)
    helper.owned._write(child.path / 'dimension-control-wiring.json', control)
    helper.owned._write(child.path / 'dimension-control-closed.json', control['controller_receipt'])
    helper.owned._write(child.path / 'dimension-command-ack-0001.json', valid_inspection_ack(child))
    value = valid_live_host(child)
    if host_valid is False: value['thread_return_observed'] = False
    if host_valid != 'missing': helper.owned._write(child.path / 'dimension-command-host.json', value)
    monkeypatch.setattr(helper, 'sibling', lambda *args: SimpleNamespace(read_journal=lambda path: []))
    result = child.observe_exit(0)
    assert result['metadata_process_passed'] is result['dimension_control_wiring_passed'] is True
    assert result['dimension_command_inspection_passed'] is True
    assert result['dimension_command_host_passed'] == result['profile_passed'] == (host_valid is True)
    false_native(result)


@pytest.mark.parametrize('observation_fails', [False, True])
def test_live_main_failure_ends_only_owned_wait_and_preserves_original_exception(tmp_path, monkeypatch, observation_fails):
    package = tmp_path / 'site-packages' / 'solidworks_mcp'
    package.mkdir(parents=True)
    path = tmp_path / 'own-live-child'
    path.mkdir()
    events = []
    original = RuntimeError('original server main failure')
    def fail_main():
        events.append('main')
        raise original
    def observe(timeout):
        events.append(('observe_wait', timeout))
        if observation_fails:
            raise RuntimeError('wait observation unavailable')
    host = SimpleNamespace(stop_waiting=lambda: events.append('stop_waiting'), wait=observe)
    module = SimpleNamespace(__file__=str(package / 'server_v2.py'), main=fail_main)
    owner = SimpleNamespace(host=host, complete_normal=lambda: pytest.fail('Failure cannot become normal completion'))
    monkeypatch.setattr(helper.importlib, 'import_module', lambda name: module)
    monkeypatch.setattr(helper, 'MetadataDimensionControlOwner', lambda *args, **kwargs: owner)
    monkeypatch.setattr(sys, 'argv', list(sys.argv))
    expected = dict(console_entrypoint='pure-v2', windows_dependencies={'windows': False})
    with pytest.raises(RuntimeError) as raised:
        helper.run_verified_entrypoint(path, package, expected, {}, profile='dimension_commands_live')
    assert raised.value is original
    assert events == ['main', 'stop_waiting', ('observe_wait', 1)]
    if observation_fails:
        assert 'wait observation unavailable' in original.__notes__[0]
    assert not (path / 'child-normal-return.json').exists()


@pytest.mark.parametrize('change', ['missing', 'extra', 'sequence', 'nonce', 'lineage', 'command',
    'arguments', 'phase', 'target', 'state_extra', 'persistence', 'authority', 'state_authority'])
def test_inspection_ack_refuses_foreign_armed_or_authorizing_receipts(harness, change):
    child = harness[0]
    value = valid_inspection_ack(child)
    if change == 'missing': value.pop('result')
    elif change == 'extra': value['native_verified'] = True
    elif change == 'sequence': value['sequence'] = True
    elif change == 'nonce': value['nonce'] = 'foreign'
    elif change == 'lineage': value['lineage']['owner_pid'] = True
    elif change == 'command': value['command'] = 'arm'
    elif change == 'arguments': value['arguments'] = {'request_id': 'foreign'}
    elif change == 'phase': value['result']['phase'] = 'armed'
    elif change == 'target': value['controller_state']['target'] = {'request_id': 'foreign'}
    elif change == 'state_extra': value['result']['extra'] = True
    elif change == 'persistence': value['result']['persist_attempted']['callback'] = 0
    elif change == 'authority': value['accepted'] = 1
    else: value['controller_state']['cad_cleanup_authorized'] = True
    with pytest.raises(helper.InstalledChildError):
        helper.validate_inspection_ack(value, identity=child.identity, path=child.path)


@pytest.mark.parametrize('ack_valid', [True, False, 'missing'])
def test_parent_command_gate_is_separate_from_metadata_and_control(harness, tmp_path, monkeypatch, ack_valid):
    _, process, _, _ = harness
    child = helper.InstalledMetadataChild(tmp_path / 'commands-profile-exit', wheel_path='pure',
        expected_version='pure', expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64,
        profile='dimension_commands')
    ready(child)
    child.catalog, child.sdk_closed, child.eof_sent = {'pure_catalog': True}, True, True
    process.code = 0
    helper.owned._write(child.path / 'child-normal-return.json', dict(identity=child.identity,
                                                                  normal_server_return=True, **helper.flags()))
    control = valid_control_receipt(child)
    helper.owned._write(child.path / 'dimension-control-wiring.json', control)
    helper.owned._write(child.path / 'dimension-control-closed.json', control['controller_receipt'])
    ack = valid_inspection_ack(child)
    if ack_valid is False: ack['controller_state']['phase'] = 'armed'
    if ack_valid != 'missing': helper.owned._write(child.path / 'dimension-command-ack-0001.json', ack)
    monkeypatch.setattr(helper, 'sibling', lambda *args: SimpleNamespace(read_journal=lambda path: []))
    result = child.observe_exit(0)
    assert result['metadata_process_passed'] is result['dimension_control_wiring_passed'] is True
    assert result['dimension_command_inspection_passed'] == result['profile_passed'] == (ack_valid is True)
    false_native(result)


def test_command_persistence_failure_retains_original_owner_and_clears_sdk_live(harness, tmp_path, monkeypatch):
    child = helper.InstalledMetadataChild(tmp_path / 'commands-write-fault', wheel_path='pure',
        expected_version='pure', expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64,
        profile='dimension_commands')
    def fail_write(*args):
        raise OSError('command storage unavailable')
    monkeypatch.setattr(helper.owned, '_write', fail_write)
    with pytest.raises(helper.InstalledChildError) as raised:
        anyio.run(child.metadata_probe)
    assert raised.value.retained_owner is child
    assert child.probe_attempted and not child.sdk_live and not child.eof_sent


@pytest.mark.parametrize('change', ['missing', 'extra', 'foreign_lineage', 'target', 'journal',
    'bool_as_int', 'native_q', 'postconditions', 'false_close', 'source_digest', 'pid'])
def test_unarmed_control_receipt_rejects_incomplete_foreign_or_native_claim(harness, change):
    child = harness[0]
    value = valid_control_receipt(child)
    closed = value['controller_receipt']
    if change == 'missing': value.pop('controller_closed_normally')
    elif change == 'extra': closed['native_verified'] = True
    elif change == 'foreign_lineage': closed['lineage']['nonce'] = 'foreign'
    elif change == 'target': closed['target'] = {'request_id': 'forbidden'}
    elif change == 'journal': closed['journal'] = [{'status': 'unknown'}]
    elif change == 'bool_as_int': value['catalog_absent'] = 1
    elif change == 'native_q': closed['native_q'] = 'proven'
    elif change == 'postconditions': closed['independent_postconditions'] = 'proven'
    elif change == 'false_close': closed['original_factories_restored'] = False
    elif change == 'source_digest': closed['lineage']['source_digest'] = 'f' * 64
    else: closed['lineage']['owner_pid'] = True
    with pytest.raises(helper.InstalledChildError):
        helper.validate_control_receipt(value, identity=child.identity, path=child.path)


@pytest.mark.parametrize('control_valid', [True, False, 'missing', 'missing_closed', 'changed_closed',
                                         'unexpected_callback', 'unexpected_barrier'])
def test_parent_control_wiring_is_separate_from_metadata_success(harness, tmp_path, monkeypatch, control_valid):
    _, process, _, _ = harness
    child = helper.InstalledMetadataChild(tmp_path / 'control-profile-exit', wheel_path='pure', expected_version='pure',
        expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64, profile='dimension_control')
    ready(child)
    child.catalog, child.sdk_closed, child.eof_sent = {'pure_catalog': True}, True, True
    process.code = 0
    helper.owned._write(child.path / 'child-normal-return.json', dict(identity=child.identity,
                                                                  normal_server_return=True, **helper.flags()))
    value = valid_control_receipt(child)
    if control_valid is False: value['controller_receipt']['original_factories_restored'] = False
    if control_valid != 'missing': helper.owned._write(child.path / 'dimension-control-wiring.json', value)
    if control_valid != 'missing_closed':
        closed = deepcopy(value['controller_receipt'])
        if control_valid == 'changed_closed': closed['lineage']['nonce'] = 'foreign'
        helper.owned._write(child.path / 'dimension-control-closed.json', closed)
    if control_valid in ('unexpected_callback', 'unexpected_barrier'):
        name = 'callback-return.json' if control_valid == 'unexpected_callback' else 'finish-barrier.json'
        helper.owned._write(child.path / name, {'pure': 'unexpected'})
    monkeypatch.setattr(helper, 'sibling', lambda *args: SimpleNamespace(read_journal=lambda path: []))
    result = child.observe_exit(0)
    assert result['metadata_process_passed'] is True
    assert result['dimension_control_wiring_passed'] == result['profile_passed'] == (control_valid is True)
    false_native(result)


def test_control_profile_installs_before_actual_runtime_and_completes_only_after_normal_main(tmp_path, monkeypatch):
    from solidworks_mcp.jobs import JobStore
    from solidworks_mcp.runtime_v2 import Runtime
    path = tmp_path / 'source-control-entrypoint'
    path.mkdir()
    package = tmp_path / 'pure-package'
    module = SimpleNamespace(JobStore=JobStore, Runtime=Runtime, __file__=str(package / 'server_v2.py'))
    original_sibling = helper.sibling
    events = []

    class FakeControl:
        # Real underlying seam/store/Runtime; artificial control lineage owner,
        # no processes or CAD. Actual controller tests remain separate.
        def __init__(self, server, *, state_root, lineage):
            self.lineage = lineage
            self.seam = original_sibling('verifier_b4_installed_finish.py', '_source_control_wrapper_seam').InstalledFinishSeam(
                server, journal_path=state_root / 'server' / 'jobs.sqlite', persist=lambda value: pytest.fail('No arm'))

        def install(self):
            events.append('install')
            self.seam.install()
            return self

        @property
        def runtime(self):
            return self.seam.runtime

        @property
        def proxy(self):
            return self.seam.proxy

        def complete_normal(self):
            events.append('complete_normal')
            assert self.runtime._closed and self.proxy._closed
            self.seam.uninstall()
            closed = dict(scope='b4_installed_dimension_control_closed_v1', lineage=deepcopy(self.lineage),
                target=None, journal=[], original_factories_restored=True, **helper.CONTROL_AUTHORITY)
            helper.owned._write(path / 'dimension-control-closed.json', closed)
            return closed

        def inspect_state(self):
            return dict(phase='closed', fault=None, target=None,
                persist_attempted={'callback': False, 'finish': False},
                receipts={'callback': None, 'finish': None}, return_observation=None, barrier_state=None)

    def main():
        events.append('main')
        assert (path / 'child-ready.json').exists()
        assert module.JobStore is not JobStore and module.Runtime is not Runtime
        store = module.JobStore(path / 'server' / 'jobs.sqlite')
        runtime = module.Runtime(store)
        assert runtime._runner is None and runtime._catalog is None
        assert runtime.shutdown() is True
        events.append('main_return')

    module.main = main
    monkeypatch.setattr(helper.importlib, 'import_module', lambda name: module)
    monkeypatch.setattr(helper, 'sibling', lambda filename, name: SimpleNamespace(InstalledDimensionControl=FakeControl)
        if filename == 'verifier_b4_installed_dimension_control.py' else original_sibling(filename, name))
    monkeypatch.setattr(sys, 'argv', list(sys.argv))
    identity = dict(profile='dimension_control', pid=777, nonce='a' * 64,
        candidate=dict(wheel=dict(package_version='pure', git_sha='b' * 40,
                                 wheel_sha256='c' * 64, source_digest='d' * 64)))
    expected = {'console_entrypoint': 'pure-v2', 'windows_dependencies': {'windows': False}}
    assert helper.run_verified_entrypoint(path, package, expected, identity, profile='dimension_control') == 0
    assert events == ['install', 'main', 'main_return', 'complete_normal']
    receipt = helper.owned._read(path / 'dimension-control-wiring.json')
    assert helper.validate_control_receipt(receipt, identity=identity, path=path) == receipt
    assert module.JobStore is JobStore and module.Runtime is Runtime
    false_native(receipt)
