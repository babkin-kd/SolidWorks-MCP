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
PROFILES = frozenset(('metadata', 'finish_seam', 'dimension_control', 'dimension_commands', 'dimension_commands_live'))
SEAM_HELPERS = ('verifier_b4_installed_finish.py', 'verifier_b4_finish_barrier.py')
CONTROL_HELPERS = SEAM_HELPERS + ('verifier_b4_installed_dimension_control.py',
                                 'verifier_b4_dimension_return.py')
COMMAND_HELPERS = CONTROL_HELPERS + ('verifier_b4_dimension_control_commands.py',)
LIVE_COMMAND_HELPERS = COMMAND_HELPERS + ('verifier_b4_dimension_command_host.py',)


def flags():
    return dict(accepted=False, native_acceptance=False, native_q='not_run',
        native_admission='not_run', process_stop_authorized=False, restart_authorized=False,
        native_b4_accepted=False, server_recovery='not_run', restart='not_run',
        reconciliation='not_run', cad_cleanup_authorized=False,
        cad_tools_called=[], job_tools_called=[])


def helper_names(profile):
    require(type(profile) is str and profile in PROFILES, 'Fixed metadata/finish_seam/dimension_control profile required.')
    return HELPERS + (LIVE_COMMAND_HELPERS if profile == 'dimension_commands_live' else
                      COMMAND_HELPERS if profile == 'dimension_commands' else
                      CONTROL_HELPERS if profile == 'dimension_control' else
                      SEAM_HELPERS if profile == 'finish_seam' else ())


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


CONTROL_AUTHORITY = dict(accepted=False, native_q='not_run', native_admission='not_run',
    independent_postconditions='not_run', process_stop_authorized=False,
    restart_authorized=False, cad_cleanup_authorized=False)
CONTROL_CHECKS = SEAM_CHECKS | {'catalog_absent', 'dimensions_absent', 'controller_closed_normally'}


def control_lineage(identity, path):
    wheel = identity['candidate']['wheel']
    return dict(package_version=wheel['package_version'], git_sha=wheel['git_sha'],
        wheel_sha256=wheel['wheel_sha256'], source_digest=wheel['source_digest'],
        nonce=identity['nonce'], owner_pid=identity['pid'], state_root=str(Path(path).resolve()))


def validate_control_receipt(value, *, identity, path):
    require(type(value) is dict and set(value) == {'scope', 'identity', 'journal_path', 'complete_journal',
            'controller_receipt'} | CONTROL_CHECKS | set(flags()), 'Exact metadata control receipt required.')
    require(value['scope'] == 'b4_installed_unarmed_dimension_control_v1'
            and owned._json(value['identity']) == owned._json(identity)
            and value['journal_path'] == str((Path(path) / 'server' / 'jobs.sqlite').resolve())
            and value['complete_journal'] == [], 'Original control identity/journal binding differs.')
    require(all(value[key] is True for key in CONTROL_CHECKS)
            and all(type(value[key]) is type(expected) and value[key] == expected for key, expected in flags().items()),
            'Metadata control must stay complete/unarmed without native authority.')
    closed = value['controller_receipt']
    require(type(closed) is dict and set(closed) == {'scope', 'lineage', 'target', 'journal',
            'original_factories_restored'} | set(CONTROL_AUTHORITY), 'Exact original control close receipt required.')
    require(closed['scope'] == 'b4_installed_dimension_control_closed_v1'
            and owned._json(closed['lineage']) == owned._json(control_lineage(identity, path))
            and closed['target'] is None and closed['journal'] == []
            and closed['original_factories_restored'] is True
            and all(type(closed[key]) is type(expected) and closed[key] == expected
                    for key, expected in CONTROL_AUTHORITY.items()),
            'Original control normal close/lineage/empty journal proof required.')
    return deepcopy(value)


class MetadataDimensionControlOwner:
    """Actual integrated owner installed before main, never armed in this profile."""
    def __init__(self, module, path, identity, *, inspect_command=False, live_commands=False):
        self.module, self.path, self.identity = module, path, deepcopy(identity)
        self.original_factories = (module.JobStore, module.Runtime)
        control = sibling('verifier_b4_installed_dimension_control.py', '_b4_installed_metadata_dimension_control')
        self.control_module, self.inspect_command = control, inspect_command
        self.owner = control.InstalledDimensionControl(module, state_root=path,
            lineage=control_lineage(identity, path)).install()
        self.host = None
        if live_commands:
            commands = sibling('verifier_b4_dimension_control_commands.py', '_b4_live_metadata_control_commands')
            host = sibling('verifier_b4_dimension_command_host.py', '_b4_live_metadata_command_host')
            receiver = commands.DimensionControlCommands(self.owner, controller_module=self.control_module,
                command_limit=1, allowed_commands=frozenset(('inspect',)))
            self.host = host.DimensionCommandHost(receiver, command_module=commands).start()

    def complete_normal(self):
        if self.host is not None:
            observed = self.host.wait(1)
            if observed['phase'] != 'completed':
                self.host.stop_waiting()
                observed = self.host.wait(1)
            require(observed['phase'] == 'completed' and observed['fault'] is None
                    and observed['action_live'] is False and observed['completed_commands'] == 1
                    and observed['thread_return_observed'] is True
                    and observed['runtime_open_at_last_action'] is True,
                    'Original inspect host must complete while Runtime is open.')
            ack = validate_inspection_ack(owned._read(self.path / 'dimension-command-ack-0001.json'),
                                          identity=self.identity, path=self.path)
            require(owned._json(observed['receiver_state']['last_ack']) == owned._json(ack),
                    'Actual live host acknowledgement differs from durable ack.')
            owned._write(self.path / 'dimension-command-host.json', observed)
        proxy, runtime = self.owner.proxy, self.owner.runtime
        require(proxy is not None and runtime is not None and type(runtime) is self.original_factories[1]
                and type(proxy._store) is self.original_factories[0]
                and proxy._store is proxy._owner._original_owned_store and runtime.store is proxy,
                'Original integrated control store/proxy/runtime identity required.')
        require(runtime._runner is None and runtime._catalog is None and runtime._dimensions is None
                and proxy.state == 'unarmed' and proxy.barrier is None and proxy._arm_attempted is False,
                'Metadata control must not construct CAD, runner, target or barrier.')
        require(proxy._closed is True and proxy._store._db is None and runtime._closed is True,
                'Original integrated runtime/store must close normally.')
        require(not any((self.path / name).exists() for name in ('callback-return.json', 'finish-barrier.json')),
                'Metadata control must not persist native callback/finish receipts.')
        if self.inspect_command:
            commands = sibling('verifier_b4_dimension_control_commands.py', '_b4_installed_metadata_control_commands')
            receiver = commands.DimensionControlCommands(self.owner, controller_module=self.control_module,
                command_limit=1, allowed_commands=frozenset(('inspect',)))
            ack = receiver.handle_command()
            validate_inspection_ack(ack, identity=self.identity, path=self.path)
            require(owned._json(owned._read(self.path / 'dimension-command-ack-0001.json')) == owned._json(ack),
                    'Original durable inspection acknowledgement differs.')
            observed = receiver.inspect_state()
            require(observed['closed'] is True and observed['fault'] is None
                    and observed['attempted'] == observed['action_completed'] == observed['acknowledged'] == 1
                    and observed['next_sequence'] is None and observed['allowed_commands'] == ['inspect'],
                    'Original single inspect-only receiver completion required.')
        closed = self.owner.complete_normal()
        require(self.module.JobStore is self.original_factories[0] and self.module.Runtime is self.original_factories[1]
                and proxy._owner._installed is False,
                'Original integrated control factories must be restored.')
        require(owned._json(owned._read(self.path / 'dimension-control-closed.json')) == owned._json(closed),
                'Actual durable original control close receipt differs.')
        state = self.owner.inspect_state()
        require(state['phase'] == 'closed' and state['fault'] is None and state['target'] is None
                and state['persist_attempted'] == {'callback': False, 'finish': False}
                and state['receipts'] == {'callback': None, 'finish': None}
                and state['return_observation'] is None and state['barrier_state'] is None,
                'Original metadata control must close without any target/native persistence.')
        lifecycle = sibling('verifier_lifecycle.py', '_b4_installed_control_journal')
        journal = lifecycle.read_journal(self.path / 'server' / 'jobs.sqlite')
        receipt = dict(scope='b4_installed_unarmed_dimension_control_v1', identity=deepcopy(self.identity),
            journal_path=str((self.path / 'server' / 'jobs.sqlite').resolve()), complete_journal=journal,
            controller_receipt=closed, **{key: True for key in CONTROL_CHECKS}, **flags())
        validate_control_receipt(receipt, identity=self.identity, path=self.path)
        owned._write(self.path / 'dimension-control-wiring.json', receipt)
        return receipt


def validate_inspection_ack(value, *, identity, path):
    require(type(value) is dict and set(value) == {'scope', 'sequence', 'nonce', 'lineage', 'command',
            'arguments', 'result', 'controller_state'} | set(CONTROL_AUTHORITY),
            'Exact original inspection acknowledgement required.')
    lineage = control_lineage(identity, path)
    require(value['scope'] == 'b4_dimension_control_command_ack_v1' and type(value['sequence']) is int
            and value['sequence'] == 1 and value['nonce'] == identity['nonce']
            and owned._json(value['lineage']) == owned._json(lineage)
            and value['command'] == 'inspect' and value['arguments'] == {},
            'Original inspect-only command/identity binding differs.')
    require(all(type(value[key]) is type(expected) and value[key] == expected
                for key, expected in CONTROL_AUTHORITY.items()), 'Inspection cannot authorize native actions.')
    for state in (value['result'], value['controller_state']):
        require(type(state) is dict and set(state) == {'scope', 'phase', 'fault', 'lineage', 'target',
                'persist_attempted', 'receipts', 'return_observation', 'barrier_state'} | set(CONTROL_AUTHORITY)
                and state['scope'] == 'b4_installed_dimension_control_state_v1'
                and owned._json(state['lineage']) == owned._json(lineage)
                and state['phase'] == 'unarmed' and state['fault'] is None and state['target'] is None
                and owned._json(state['persist_attempted']) == owned._json({'callback': False, 'finish': False})
                and state['receipts'] == {'callback': None, 'finish': None}
                and state['return_observation'] is None and state['barrier_state'] is None
                and all(type(state[key]) is type(expected) and state[key] == expected
                        for key, expected in CONTROL_AUTHORITY.items()),
                'Original cold unarmed control inspection required.')
    return deepcopy(value)


def validate_live_host(value, *, identity, path):
    require(type(value) is dict and set(value) == {'scope', 'phase', 'fault', 'action_live',
            'completed_commands', 'lineage', 'receiver_state', 'runtime_open_at_last_action',
            'thread_return_observed'} | set(CONTROL_AUTHORITY)
            and value['scope'] == 'b4_dimension_command_host_state_v1'
            and value['phase'] == 'completed' and value['fault'] is None
            and value['action_live'] is False and value['runtime_open_at_last_action'] is True
            and value['thread_return_observed'] is True
            and type(value['completed_commands']) is int and value['completed_commands'] == 1
            and owned._json(value['lineage']) == owned._json(control_lineage(identity, path)),
            'Original completed open-Runtime inspect host required.')
    state = value['receiver_state']
    require(type(state) is dict and set(state) == {'scope', 'closed', 'fault', 'lineage', 'command_limit',
            'allowed_commands', 'next_sequence', 'attempted', 'action_completed', 'acknowledged',
            'last_controller_state', 'last_ack'} | set(CONTROL_AUTHORITY)
            and state['scope'] == 'b4_dimension_control_command_receiver_state_v1'
            and state['closed'] is True and state['fault'] is None and state['next_sequence'] is None
            and state['allowed_commands'] == ['inspect']
            and all(type(state[key]) is int and state[key] == 1
                    for key in ('command_limit', 'attempted', 'action_completed', 'acknowledged'))
            and owned._json(state['lineage']) == owned._json(value['lineage']),
            'Original exhausted inspect-only receiver budget required.')
    ack = validate_inspection_ack(state['last_ack'], identity=identity, path=path)
    require(owned._json(ack) == owned._json(owned._read(path / 'dimension-command-ack-0001.json'))
            and owned._json(state['last_controller_state']) == owned._json(ack['controller_state']),
            'Original live host and durable receiver acknowledgement differ.')
    require(all(type(row[key]) is type(expected) and row[key] == expected
                for row in (value, state) for key, expected in CONTROL_AUTHORITY.items()),
            'Live host cannot authorize native/process actions.')
    return deepcopy(value)


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
    finish_owner = (MetadataFinishOwner(module, path, identity) if profile == 'finish_seam' else
                    MetadataDimensionControlOwner(module, path, identity, inspect_command=profile == 'dimension_commands',
                                                  live_commands=profile == 'dimension_commands_live')
                    if profile in ('dimension_control', 'dimension_commands', 'dimension_commands_live') else None)
    owned._write(path / 'child-ready.json', dict(scope='b4_installed_child_ready_v1', identity=identity, **flags()))
    sys.argv = [expected['console_entrypoint'], '--state-dir', str(path / 'server')]
    try:
        module.main()
    except BaseException as primary:
        # Stop only the owned metadata command wait. Never interrupt an entered
        # action or infer normal Runtime/controller completion after an error.
        if finish_owner is not None and getattr(finish_owner, 'host', None) is not None:
            try:
                finish_owner.host.stop_waiting()
                finish_owner.host.wait(1)
            except BaseException as cleanup_error:
                primary.add_note('Owned metadata command wait unconfirmed: ' + str(cleanup_error))
        raise
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
        self._original_process = self._launch_identity = None
        self._launch_spec = deepcopy(self.spec)
        self._inspection_publication_attempted = False
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
            self._original_process = self.process
            self.start = owned._process_start(self.process.pid, getattr(self.process, '_handle', None))
            self.identity = self._identity(self.start)
            self._launch_identity = deepcopy(self.identity)
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

    def publish_live_inspection(self):
        """One atomic request for this original ready/live child; no CAD action."""
        try:
            return self._publish_live_inspection_checked()
        except Exception as error:
            raise InstalledChildError('Original live inspection publication unconfirmed: ' + str(error),
                                      retained_owner=self) from error

    def _publish_live_inspection_checked(self):
        require(not self._inspection_publication_attempted, 'Original inspection publication is one-shot; no retry.')
        self._inspection_publication_attempted = True
        require(self.profile == 'dimension_commands_live' and self.launch_failed is None
                and self.process is self._original_process and self.process.poll() is None
                and self.sdk_live is True and self.sdk_closed is False and not self.eof_sent and self.ready is not None,
                'Original ready/live metadata child and open SDK required.')
        require(owned._json(self.identity) == owned._json(self._launch_identity)
                and owned._json(self._identity(self.start)) == owned._json(self._launch_identity)
                and owned._json(self.ready['identity']) == owned._json(self._launch_identity)
                and owned._json(self.spec) == owned._json(self._launch_spec)
                and owned._json(owned._read(self.path / 'launch-spec.json')) == owned._json(self._launch_spec),
                'Original process/nonce/candidate/launch binding changed.')
        current = owned._process_start(self.process.pid, getattr(self.process, '_handle', None))
        require(owned._json(current) == owned._json(self._launch_identity['start']),
                'Original process start changed; no PID adoption.')
        require(all(owned._file_sha(Path(__file__).with_name(name)) == digest
                    for name, digest in self.helpers.items()), 'Original command helpers changed.')
        host = sibling('verifier_b4_dimension_command_host.py', '_b4_parent_metadata_command_host')
        return host.publish_command(self.path, dict(scope='b4_dimension_control_command_v1', sequence=1,
            nonce=self.identity['nonce'], lineage=control_lineage(self.identity, self.path),
            command='inspect', arguments={}))

    async def metadata_probe(self):
        import anyio
        from mcp import ClientSession
        require(not self.probe_attempted and self.launch_failed is None, 'One original metadata probe only.')
        self.probe_attempted = self.sdk_live = True
        with anyio.CancelScope(shield=True):
            try:
                if self.profile in ('dimension_commands', 'dimension_commands_live'):
                    request = dict(scope='b4_dimension_control_command_v1', sequence=1, nonce=self.identity['nonce'],
                                   lineage=control_lineage(self.identity, self.path), command='inspect', arguments={})
                    if self.profile == 'dimension_commands_live':
                        self.publish_live_inspection()
                    else:
                        owned._write(self.path / 'dimension-command-0001.json', request)
                async with self.transport() as (read, write):
                    async with ClientSession(read, write) as client:
                        self.catalog = await consume_metadata(client, self.candidate['wheel'])
                        if self.profile == 'dimension_commands_live':
                            # Observe only the one published command. Keep SDK
                            # open until its action returned; never send again.
                            deadline = time.monotonic() + 5
                            while True:
                                ack_path = self.path / 'dimension-command-ack-0001.json'
                                if ack_path.exists():
                                    try:
                                        ack = owned._read(ack_path)
                                    except json.JSONDecodeError:
                                        ack = None
                                    if ack is not None:
                                        validate_inspection_ack(ack, identity=self.identity, path=self.path)
                                        break
                                require(self.process.poll() is None and time.monotonic() < deadline,
                                        'Original live inspection not observed; retain owner, no resend.')
                                await anyio.sleep(.01)
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
            metadata_process_passed=False, finish_seam_wiring_passed=False,
            dimension_control_wiring_passed=False, dimension_command_inspection_passed=False,
            dimension_command_host_passed=False,
            profile_passed=False, **flags())
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
        if self.profile in ('dimension_control', 'dimension_commands', 'dimension_commands_live') and receipt['metadata_process_passed']:
            try:
                control_receipt = validate_control_receipt(owned._read(self.path / 'dimension-control-wiring.json'),
                    identity=self.identity, path=self.path)
                require(owned._json(owned._read(self.path / 'dimension-control-closed.json')) ==
                        owned._json(control_receipt['controller_receipt']),
                        'Durable original control close differs from wrapper receipt.')
                require(not any((self.path / name).exists() for name in ('callback-return.json', 'finish-barrier.json')),
                        'Metadata profile unexpectedly persisted native receipts.')
                receipt.update(dimension_control_wiring_passed=True, dimension_control_wiring=control_receipt)
            except (OSError, ValueError, KeyError, TypeError, InstalledChildError) as exc:
                receipt['dimension_control_wiring_error'] = str(exc)
        if self.profile in ('dimension_commands', 'dimension_commands_live') and receipt['dimension_control_wiring_passed']:
            try:
                ack = validate_inspection_ack(owned._read(self.path / 'dimension-command-ack-0001.json'),
                                              identity=self.identity, path=self.path)
                receipt.update(dimension_command_inspection_passed=True, dimension_command_inspection=ack)
            except (OSError, ValueError, KeyError, TypeError, InstalledChildError) as exc:
                receipt['dimension_command_inspection_error'] = str(exc)
        if self.profile == 'dimension_commands_live' and receipt['dimension_command_inspection_passed']:
            try:
                state = validate_live_host(owned._read(self.path / 'dimension-command-host.json'),
                                           identity=self.identity, path=self.path)
                receipt.update(dimension_command_host_passed=True, dimension_command_host=state)
            except (OSError, ValueError, KeyError, TypeError, InstalledChildError) as exc:
                receipt['dimension_command_host_error'] = str(exc)
        receipt['profile_passed'] = receipt['metadata_process_passed'] and (
            self.profile == 'metadata' or self.profile == 'finish_seam' and receipt['finish_seam_wiring_passed']
            or self.profile == 'dimension_control' and receipt['dimension_control_wiring_passed']
            or self.profile == 'dimension_commands' and receipt['dimension_command_inspection_passed']
            or self.profile == 'dimension_commands_live' and receipt['dimension_command_host_passed'])
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
