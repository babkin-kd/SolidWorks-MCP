"""Owned installed-server metadata bridge; no CAD, Q, recovery or restart.

Uses the installed server_v2.main entrypoint, SDK ClientSession, and original
Popen custody. SDK stdio_client is deliberately excluded: its shutdown may
terminate/kill after a timeout. Here EOF is explicit and waits never kill.
"""
from contextlib import asynccontextmanager
from copy import deepcopy
from importlib import metadata
import importlib.util
import importlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import sysconfig
import time


class InstalledChildError(RuntimeError):
    def __init__(self, message, *, retained_owner=None):
        super().__init__(message)
        self.retained_owner = retained_owner


def require(condition, message):
    if not condition:
        raise InstalledChildError(message)


def sibling(filename, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    previous = sys.path[:]
    missing = object()
    previous_module = sys.modules.get(name, missing)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        # Dataclasses with postponed annotations resolve cls.__module__ while
        # executing the module. Keep the successful original module registered;
        # a failed import must restore the caller's exact prior binding.
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except BaseException:
        if previous_module is missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous_module
        raise
    finally:
        sys.path[:] = previous
    return module


owned = sibling('verifier_b4_owned_child_process.py', '_b4_installed_owned_primitives')
HELPERS = ('verifier_b4_installed_child.py', 'verifier_b4_owned_child_process.py',
           'verify_installed_metadata.py', 'verify_wheel_artifact.py', 'verifier_lifecycle.py')
PROFILES = frozenset(('metadata', 'finish_seam'))
SEAM_HELPERS = ('verifier_b4_installed_finish.py', 'verifier_b4_finish_barrier.py')


def flags():
    return dict(accepted=False, native_acceptance=False, native_q='not_run',
        native_admission='not_run', process_stop_authorized=False, restart_authorized=False,
        native_b4_accepted=False, server_recovery='not_run', restart='not_run',
        reconciliation='not_run', cad_cleanup_authorized=False,
        cad_tools_called=[], job_tools_called=[])


def helper_names(profile):
    require(type(profile) is str and profile in PROFILES, 'Fixed metadata/finish_seam profile required.')
    return HELPERS + (SEAM_HELPERS if profile == 'finish_seam' else ())


SEAM_CHECKS = frozenset(('original_store_retained', 'runtime_store_is_original_proxy', 'runner_absent',
    'proxy_unarmed', 'barrier_absent', 'arm_not_attempted', 'barrier_persistence_not_invoked',
    'store_closed_normally', 'runtime_closed_normally', 'original_factories_restored', 'seam_uninstalled'))


def validate_seam_receipt(value, *, identity, journal_path):
    require(type(value) is dict and set(value) == {'scope', 'identity', 'journal_path', 'complete_journal'}
            | SEAM_CHECKS | set(flags()), 'Exact finite finish-seam wiring receipt required.')
    require(value['scope'] == 'b4_installed_unarmed_finish_seam_v1'
            and owned._json(value['identity']) == owned._json(identity)
            and value['journal_path'] == str(Path(journal_path).resolve()) and value['complete_journal'] == [],
            'Original finish-seam identity/journal binding differs.')
    require(all(value[key] is True for key in SEAM_CHECKS)
            and all(type(value[key]) is type(expected) and value[key] == expected
                    for key, expected in flags().items()),
            'Finish-seam wiring must stay complete/unarmed with false native authority.')
    return deepcopy(value)


class MetadataFinishOwner:
    """Own finite seam lifecycle. This profile never arms or dispatches jobs."""
    def __init__(self, module, path, identity):
        self.path, self.identity = path, deepcopy(identity)
        self.module = module
        self.original_factories = (module.JobStore, module.Runtime)
        self.persist_attempted = False
        seam_module = sibling('verifier_b4_installed_finish.py', '_b4_installed_metadata_finish_seam')
        self.seam = seam_module.InstalledFinishSeam(module,
            journal_path=path / 'server' / 'jobs.sqlite', persist=self.persist_barrier)
        self.seam.install()

    def persist_barrier(self, value):
        require(not self.persist_attempted, 'Original durable barrier persistence is one-shot; no retry.')
        self.persist_attempted = True
        owned._write(self.path / 'finish-barrier.json', value)

    def complete_normal(self):
        seam = self.seam
        proxy, runtime = seam.proxy, seam.runtime
        seam.assert_wired(runtime)
        require(proxy is not None and runtime is not None and runtime.store is proxy
                and proxy._store is seam._original_owned_store and runtime._runner is None,
                'Original actual seam proxy/runtime/store and absent runner required.')
        require(proxy.state == 'unarmed' and proxy.barrier is None and proxy._arm_attempted is False
                and self.persist_attempted is False and not (self.path / 'finish-barrier.json').exists(),
                'Metadata finish-seam must stay unarmed; no barrier persistence or target dispatch.')
        require(proxy._closed is True and proxy._store._db is None and runtime._closed is True,
                'Original metadata store/runtime must close normally.')
        lifecycle = sibling('verifier_lifecycle.py', '_b4_installed_seam_journal')
        journal = lifecycle.read_journal(seam.path)
        require(journal == [], 'Complete actual finish-seam journal must stay empty.')
        seam.uninstall()
        require(self.module.JobStore is self.original_factories[0]
                and self.module.Runtime is self.original_factories[1] and seam._installed is False,
                'Original server factories must be restored after normal metadata return.')
        receipt = dict(scope='b4_installed_unarmed_finish_seam_v1', identity=deepcopy(self.identity),
            journal_path=str(seam.path), complete_journal=journal, **{key: True for key in SEAM_CHECKS}, **flags())
        validate_seam_receipt(receipt, identity=self.identity, journal_path=seam.path)
        owned._write(self.path / 'finish-seam-wiring.json', receipt)
        return receipt


def private_root():
    return Path(__file__).resolve().parents[1] / 'work'


def windows_dependency_facts(dependency_root, *, windows=None):
    """Explicit pywin32 layout bound to this exact installed purelib.

    Inspect fixed directories/files only; never execute .pth/user-site code or
    search global DLL paths. This is dependency bootstrap, not COM invocation.
    """
    root = Path(dependency_root).resolve()
    require(root.is_dir(), 'Installed dependency root must exist.')
    is_windows = os.name == 'nt' if windows is None else windows
    require(type(is_windows) is bool, 'Explicit dependency platform must be boolean.')
    facts = dict(scope='b4_anchored_windows_dependencies_v1', dependency_root=str(root),
                 windows=is_windows, import_paths=[], dll_directory=None,
                 pywin32_version=None, file_sha256={})
    if not is_windows:
        return facts
    directories = ('win32', 'win32/lib', 'pythonwin', 'pywin32_system32')
    for relative in directories:
        expected = root / relative
        actual = expected.resolve()
        require(actual == expected and actual.is_relative_to(root) and actual.is_dir(),
                'Exact anchored pywin32 directories required; missing/redirected paths rejected.')
    tag = f'{sys.version_info.major}{sys.version_info.minor}'
    files = ('pythoncom.py', 'win32/lib/pywintypes.py', 'win32/_win32sysloader.pyd',
             'win32/win32api.pyd', 'win32/win32job.pyd', f'pywin32_system32/pywintypes{tag}.dll',
             f'pywin32_system32/pythoncom{tag}.dll')
    for relative in files:
        expected = root / relative
        require(expected.resolve() == expected and expected.is_file(),
                'Exact anchored pywin32 bootstrap/DLL files required.')
        facts['file_sha256'][relative] = owned._file_sha(expected)
    facts.update(import_paths=[str(root / name) for name in directories[:3]],
                 dll_directory=str(root / 'pywin32_system32'), pywin32_version=metadata.version('pywin32'))
    return facts


def activate_dependency_bootstrap(candidate):
    """Recheck parent facts and keep owned DLL handles alive through main()."""
    root = Path(candidate['dependency_root']).resolve()
    facts = windows_dependency_facts(root)
    require(facts == candidate['windows_dependencies'], 'Parent/child Windows dependency identity mismatch.')
    # package purelib always precedes these fixed subdirectories. No arbitrary
    # .pth evaluation and no inherited source/user search root is introduced.
    sys.path[0:0] = [str(root), *facts['import_paths']]
    handles = []
    if facts['windows']:
        require(callable(getattr(os, 'add_dll_directory', None)), 'Explicit Windows DLL bootstrap unavailable.')
        handles.append(os.add_dll_directory(facts['dll_directory']))
    return handles


def verify_loaded_windows_dependencies(candidate):
    """No global/other-install pywin32 module may satisfy this import proof."""
    facts = candidate['windows_dependencies']
    if not facts['windows']:
        return
    root = Path(candidate['dependency_root']).resolve()
    tag = f'{sys.version_info.major}{sys.version_info.minor}'
    modules = {'pywintypes': f'pywin32_system32/pywintypes{tag}.dll',
               '_win32sysloader': 'win32/_win32sysloader.pyd',
               'win32api': 'win32/win32api.pyd', 'win32job': 'win32/win32job.pyd'}
    for name, relative in modules.items():
        module = sys.modules.get(name)
        path = root / relative
        require(module is not None and Path(getattr(module, '__file__', '')).resolve() == path
                and owned._file_sha(path) == facts['file_sha256'][relative],
                'Actual loaded Windows dependency must match its anchored original file/hash.')


def run_verified_entrypoint(path, package, expected, identity, *, profile='metadata'):
    """Ready means the real installed server module imported successfully."""
    helper_names(profile)
    module = importlib.import_module('solidworks_mcp.server_v2')
    require(Path(module.__file__).resolve() == package / 'server_v2.py' and callable(module.main),
            'Actual installed server entrypoint required.')
    verify_loaded_windows_dependencies(expected)
    finish_owner = MetadataFinishOwner(module, path, identity) if profile == 'finish_seam' else None
    owned._write(path / 'child-ready.json', dict(scope='b4_installed_child_ready_v1', identity=identity, **flags()))
    sys.argv = [expected['console_entrypoint'], '--state-dir', str(path / 'server')]
    module.main()
    if finish_owner is not None:
        finish_owner.complete_normal()
    owned._write(path / 'child-normal-return.json', dict(identity=identity, normal_server_return=True, **flags()))
    return 0


def validate_candidate(wheel_path, version, git_sha, wheel_sha256):
    require(not os.environ.get('PYTHONPATH'), 'Installed launcher requires PYTHONPATH unset.')
    checker = sibling('verify_installed_metadata.py', '_b4_installed_metadata')
    wheel = checker.validate_wheel(wheel_path, expected_version=version, expected_git_sha=git_sha)
    require(wheel['wheel_sha256'] == wheel_sha256, 'Exact wheel SHA256 mismatch.')
    entry = checker.installed_identity(wheel)
    import solidworks_mcp
    package = Path(solidworks_mcp.__file__).resolve().parent
    dependency = Path(sysconfig.get_path('purelib')).resolve()
    return dict(wheel=wheel, wheel_path=str(Path(wheel_path).resolve()),
        package_root=str(package), dependency_root=str(dependency), windows_dependencies=windows_dependency_facts(dependency),
        console_entrypoint=str(entry.resolve()), sdk_version=metadata.version('mcp'))


def validate_outbound(message):
    """Finite metadata-only request/notification admission, never CAD dispatch."""
    value = message.model_dump(mode='json', by_alias=True, exclude_none=True)
    method = value.get('method')
    require(value.get('jsonrpc') == '2.0', 'Exact JSON-RPC metadata message required.')
    if method == 'initialize':
        require('id' in value, 'Initialize request identity required.')
    elif method == 'notifications/initialized':
        require('id' not in value and value.get('params', {}) == {}, 'Exact initialized notification required.')
    elif method == 'tools/list':
        require('id' in value and value.get('params', {}) == {}, 'Only complete uncursored tool list allowed.')
    elif method == 'tools/call':
        require('id' in value and value.get('params') == {'name': 'system_get_info', 'arguments': {}},
                'Only argument-free system_get_info is admitted; CAD/job tools prohibited.')
    else:
        raise InstalledChildError('Only initialize/tools-list/system_get_info metadata is admitted.')
    return message.model_dump_json(by_alias=True, exclude_none=True).encode('utf8') + b'\n'


async def consume_metadata(client, wheel):
    await client.initialize()
    tools = (await client.list_tools()).tools
    raw = await client.call_tool('system_get_info', {})
    require(raw.isError is False and type(raw.structuredContent) is dict, 'Structured metadata required.')
    response = raw.structuredContent
    require(response['status'] == 'succeeded' and response['error'] is None, 'Metadata call failed.')
    checker = sibling('verify_installed_metadata.py', '_b4_installed_catalog')
    return checker.verify_metadata(tools, response['data'], wheel)


class InstalledMetadataChild:
    """One fresh original server; metadata-only lifecycle, no adoption/restart.

    Startup and terminal observations are bounded. Expiration retains this
    original handle. metadata_probe is shielded: it cannot cancel a child or
    turn an unconfirmed response into success. Normal EOF after SDK closure is
    a metadata-only control path, not a native crash/unknown cleanup permit.
    """

    def __init__(self, state_dir, *, wheel_path, expected_version, expected_git_sha, expected_wheel_sha256,
                 profile='metadata'):
        self._profile = profile
        profile_helpers = helper_names(profile)
        self.path = Path(state_dir).resolve()
        require(self.path.is_relative_to(private_root().resolve()), 'State must stay in private work/.')
        require(not self.path.exists(), 'Fresh own child state required; no adoption.')
        self.candidate = validate_candidate(wheel_path, expected_version, expected_git_sha, expected_wheel_sha256)
        self.path.mkdir(parents=False)
        self.nonce = secrets.token_hex(32)
        self.helpers = {name: owned._file_sha(Path(__file__).with_name(name)) for name in profile_helpers}
        self.spec = dict(scope='b4_installed_metadata_launch_v1', nonce=self.nonce, parent_pid=os.getpid(),
            candidate=self.candidate, helpers=self.helpers, state_dir=str(self.path), profile=self.profile)
        owned._write(self.path / 'launch-spec.json', self.spec)
        self.process = None
        self.start = self.identity = self.ready = self.catalog = self.receipt = None
        self.launch_failed = None
        self.sdk_live = self.probe_attempted = self.eof_sent = False
        self.sdk_closed = False
        # The direct runtime owns the actual server PID, avoiding Windows venv
        # redirectors. -S and explicit installed purelib exclude source/user .pth.
        self.argv = [str(Path(sys._base_executable).resolve()), '-S', str(Path(__file__).resolve()),
                     '--owned-installed-child', str(self.path / 'launch-spec.json')]
        environment = os.environ.copy()
        environment.pop('PYTHONPATH', None)
        environment['PYTHONNOUSERSITE'] = '1'
        try:
            with (self.path / 'child-stderr.log').open('xb') as stream:
                self.process = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=stream, env=environment)
            self.start = owned._process_start(self.process.pid, getattr(self.process, '_handle', None))
            self.identity = self._identity(self.start)
            owned._write(self.path / 'parent-launch.json', dict(identity=self.identity, argv=self.argv,
                environment=dict(PYTHONPATH=None, PYTHONNOUSERSITE='1'), **flags()))
        except BaseException as exc:
            self.launch_failed = repr(exc)
            raise InstalledChildError('Original launch observation failed; retain original owner.',
                                      retained_owner=self if self.process is not None else None) from exc

    def _identity(self, start):
        return dict(pid=self.process.pid, parent_pid=os.getpid(), start=deepcopy(start), nonce=self.nonce,
                    candidate=deepcopy(self.candidate), helpers=deepcopy(self.helpers), profile=self.profile)

    @property
    def profile(self):
        return self._profile

    def await_ready(self, timeout=5):
        require(type(timeout) in (int, float) and 0 <= timeout <= 60, 'Bounded observation required.')
        deadline = time.monotonic() + timeout
        while True:
            if (self.path / 'child-ready.json').exists():
                try:
                    value = owned._read(self.path / 'child-ready.json')
                except json.JSONDecodeError:
                    value = None
                if value is not None:
                    require(self.launch_failed is None and self.identity is not None,
                            'Launch proof incomplete; original owner retained.')
                    require(value['scope'] == 'b4_installed_child_ready_v1'
                            and value['identity'] == self.identity and value['native_q'] == 'not_run',
                            'Original handle/start/wheel/package/nonce binding differs.')
                    self.ready = deepcopy(value)
                    return deepcopy(value)
            code = self.process.poll()
            if code is not None:
                with (self.path / 'child-stderr.log').open('rb') as stream:
                    stream.seek(0, os.SEEK_END)
                    stream.seek(max(0, stream.tell() - 4096))
                    tail = stream.read(4096).decode('utf8', errors='replace')
                raise InstalledChildError(f'Own child terminal before ready; exit_code={code}; stderr_tail={tail!r}',
                                          retained_owner=self)
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(.01, max(0, deadline - time.monotonic())))

    @asynccontextmanager
    async def transport(self):
        import anyio
        from mcp.shared.message import SessionMessage
        from mcp.types import JSONRPCMessage
        require(self.ready is not None and not self.eof_sent, 'Original ready, open metadata channel required.')
        incoming_send, incoming = anyio.create_memory_object_stream(0)
        outgoing, outgoing_receive = anyio.create_memory_object_stream(0)

        async def read_stdout():
            async with incoming_send:
                while True:
                    line = await anyio.to_thread.run_sync(self.process.stdout.readline)
                    if not line:
                        break
                    try:
                        value = SessionMessage(JSONRPCMessage.model_validate_json(line))
                    except Exception as exc:
                        value = exc
                    try:
                        await incoming_send.send(value)
                    except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                        # Continue draining this original pipe until actual EOF.
                        continue

        async def write_stdin():
            async with outgoing_receive:
                async for message in outgoing_receive:
                    payload = validate_outbound(message.message)
                    await anyio.to_thread.run_sync(self.process.stdin.write, payload)
                    await anyio.to_thread.run_sync(self.process.stdin.flush)

        with anyio.CancelScope(shield=True):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(read_stdout)
                tasks.start_soon(write_stdin)
                try:
                    yield incoming, outgoing
                finally:
                    with anyio.CancelScope(shield=True):
                        await outgoing.aclose()
                        # SDK request loop has exited; this finite owner admitted
                        # metadata only. EOF never replaces native Q or crash stop.
                        await anyio.to_thread.run_sync(self._send_eof)
                        await incoming.aclose()
            self.sdk_closed = True

    def _send_eof(self):
        require(not self.eof_sent, 'Normal metadata EOF is one-shot; no retry.')
        self.eof_sent = True
        self.process.stdin.close()

    async def metadata_probe(self):
        import anyio
        from mcp import ClientSession
        require(not self.probe_attempted and self.launch_failed is None, 'One original metadata probe only.')
        self.probe_attempted = self.sdk_live = True
        with anyio.CancelScope(shield=True):
            try:
                async with self.transport() as (read, write):
                    async with ClientSession(read, write) as client:
                        self.catalog = await consume_metadata(client, self.candidate['wheel'])
                return deepcopy(self.catalog)
            except BaseException as exc:
                raise InstalledChildError('Metadata/SDK outcome unconfirmed; retain original owner.',
                                          retained_owner=self) from exc
            finally:
                self.sdk_live = False

    def observe_exit(self, timeout=0):
        require(type(timeout) in (int, float) and 0 <= timeout <= 60, 'Bounded observation required.')
        if self.receipt is not None:
            return deepcopy(self.receipt)
        try:
            code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return dict(phase='owner_retained', process_exit_observed=False, metadata_process_passed=False, **flags())
        receipt = dict(scope='b4_installed_metadata_process_observation_v1', phase='terminal',
            identity=deepcopy(self.identity), exit_code=code, process_exit_observed=True,
            metadata_process_passed=False, finish_seam_wiring_passed=False, profile_passed=False, **flags())
        try:
            returned = owned._read(self.path / 'child-normal-return.json')
            require(code == 0 and self.launch_failed is None and self.ready is not None,
                    'Exact normally returned original child required.')
            require(returned['identity'] == self.identity and returned['normal_server_return'] is True,
                    'Installed server_v2.main normal return proof required.')
            require(self.sdk_closed is True and self.eof_sent is True and self.catalog is not None,
                    'Verified metadata and normal SDK/EOF close required.')
            lifecycle = sibling('verifier_lifecycle.py', '_b4_installed_journal')
            journal = lifecycle.read_journal(self.path / 'server' / 'jobs.sqlite')
            require(journal == [], 'Complete actual journal must stay empty; no metadata dispatch jobs.')
            require(all(owned._file_sha(Path(__file__).with_name(name)) == value
                        for name, value in self.helpers.items()), 'Frozen helper changed.')
            receipt.update(metadata_process_passed=True, complete_journal=journal, catalog=deepcopy(self.catalog))
        except (OSError, ValueError, KeyError, TypeError, InstalledChildError) as exc:
            receipt['reason'] = str(exc)
        if self.profile == 'finish_seam' and receipt['metadata_process_passed']:
            try:
                seam_receipt = validate_seam_receipt(owned._read(self.path / 'finish-seam-wiring.json'),
                    identity=self.identity, journal_path=self.path / 'server' / 'jobs.sqlite')
                require(not (self.path / 'finish-barrier.json').exists(), 'Metadata profile unexpectedly persisted a barrier.')
                receipt.update(finish_seam_wiring_passed=True, finish_seam_wiring=seam_receipt)
            except (OSError, ValueError, KeyError, TypeError, InstalledChildError) as exc:
                receipt['finish_seam_wiring_error'] = str(exc)
        receipt['profile_passed'] = receipt['metadata_process_passed'] and (
            self.profile == 'metadata' or receipt['finish_seam_wiring_passed'])
        owned._write(self.path / 'parent-exit.json', receipt)
        self.receipt = receipt
        return deepcopy(receipt)


def child_main(spec_path):
    spec_path = Path(spec_path).resolve()
    spec = owned._read(spec_path)
    require(type(spec) is dict and set(spec) == {'scope', 'nonce', 'parent_pid', 'candidate', 'helpers', 'state_dir', 'profile'}
        and spec['scope'] == 'b4_installed_metadata_launch_v1' and spec['parent_pid'] == os.getppid()
        and type(spec['nonce']) is str and len(spec['nonce']) == 64, 'Original finite launch spec required.')
    path = Path(spec['state_dir']).resolve()
    require(path == spec_path.parent and path.is_relative_to(private_root().resolve()), 'Own private spec required.')
    require(not os.environ.get('PYTHONPATH') and os.environ.get('PYTHONNOUSERSITE') == '1',
            'Installed child excludes source/user PYTHONPATH.')
    profile = spec['profile']
    require(set(spec['helpers']) == set(helper_names(profile)) and all(owned._file_sha(Path(__file__).with_name(name)) == value
        for name, value in spec['helpers'].items()), 'Exact original helper manifest required.')
    expected = spec['candidate']
    package = Path(expected['package_root']).resolve()
    dependency = Path(expected['dependency_root']).resolve()
    require(package.parent == dependency and package.name == 'solidworks_mcp', 'Exact installed package root required.')
    sys.path.insert(0, str(dependency))
    dll_handles = activate_dependency_bootstrap(expected)
    # Revalidate actual child namespace/distribution/source before invoking the
    # real installed entrypoint. Never source PYTHONPATH or synthetic server.
    import solidworks_mcp
    from solidworks_mcp.build_info import source_digest
    checker = sibling('verify_wheel_artifact.py', '_b4_child_wheel')
    wheel = checker.validate_wheel(expected['wheel_path'], expected_version=expected['wheel']['package_version'],
                                  expected_git_sha=expected['wheel']['git_sha'])
    build = owned._read(package / 'build_info.json')
    require(wheel == expected['wheel'] and Path(solidworks_mcp.__file__).resolve().parent == package
        and metadata.version('solidworks-mcp') == solidworks_mcp.__version__ == wheel['package_version']
        and build['git_sha'] == wheel['git_sha'] and build['source_dirty'] is False
        and source_digest(package) == build['source_digest'] == wheel['source_digest']
        and metadata.version('mcp') == expected['sdk_version'], 'Actual installed child identity mismatch.')
    identity = dict(pid=os.getpid(), parent_pid=os.getppid(), start=owned._process_start(os.getpid()),
                    nonce=spec['nonce'], candidate=expected, helpers=spec['helpers'], profile=profile)
    try:
        return run_verified_entrypoint(path, package, expected, identity, profile=profile)
    finally:
        for handle in dll_handles:
            handle.close()


if __name__ == '__main__':
    require(len(sys.argv) == 3 and sys.argv[1] == '--owned-installed-child', 'Fixed owned installed entrypoint only.')
    raise SystemExit(child_main(sys.argv[2]))
