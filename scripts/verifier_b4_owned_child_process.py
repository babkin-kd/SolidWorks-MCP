"""Finite synthetic B4-N4-P process experiment, never a CAD/native permit.

Only this file's fixed child entrypoint can be launched. The parent retains its
Popen handle, OS start identity and private nonce. There is no PID adoption,
external command, kill, timeout cancellation, restart or retry. The child uses
real JobStore/FinishBarrierStore and OwnedChildExitGate, but its Q producer is
explicitly synthetic. Native Q and native B4 remain not_run/false.
"""
from copy import deepcopy
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import site
import subprocess
import sys
from threading import Thread
import time


EXIT_CODE = 73
PROFILES = frozenset(('exit', 'callback_return', 'intent_failure'))


class OwnedChildProtocolError(RuntimeError):
    pass


class OwnedChildLaunchError(OwnedChildProtocolError):
    """Original Popen custody survives failed post-launch observation/receipt."""

    def __init__(self, retained_owner, cause):
        super().__init__(f'Own child retained after launch failure: {cause}')
        self.retained_owner = retained_owner


def _require(condition, message):
    if not condition:
        raise OwnedChildProtocolError(message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':'))


def _sha(value):
    return hashlib.sha256(_json(value).encode('utf8')).hexdigest()


def _file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, value):
    """Single original durable receipt; no replacement/retry on partial writes."""
    with Path(path).open('x', encoding='utf8') as stream:
        stream.write(_json(value))
        stream.flush()
        os.fsync(stream.fileno())


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def _process_start(pid, handle=None):
    if os.name == 'nt':
        class FileTime(ctypes.Structure):
            _fields_ = [('low', ctypes.c_uint32), ('high', ctypes.c_uint32)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(FileTime)] * 4
        kernel.GetProcessTimes.restype = ctypes.c_int
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        actual_handle = kernel.GetCurrentProcess() if handle is None else int(handle)
        values = [FileTime() for _ in range(4)]
        _require(kernel.GetProcessTimes(actual_handle, *[ctypes.byref(v) for v in values]),
                 'OS process start observation failed; do not adopt another PID.')
        return {'kind': 'windows_filetime', 'ticks': (values[0].high << 32) | values[0].low}
    # /proc is used only for the retained Popen child or this current process.
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return {'kind': 'linux_proc_start_ticks', 'ticks': int(fields[19])}


def _flags():
    return dict(accepted=False, native_b4_accepted=False, native_q='not_run',
                native_restart_proven=False, native_dispatch_proven=False,
                process_stop_authorized=False, cad_cleanup_authorized=False,
                synthetic_cad_free=True)


class OwnedSyntheticChild:
    """Own handle retained through bounded observations; timeouts leave it live.

    A fresh private directory and finite synthetic profile are the only inputs.
    Receipts are private evidence, not protection against malicious code in the
    same account. Source/helpers must remain frozen for this experiment.
    """

    def __init__(self, state_dir, *, profile='exit'):
        _require(type(profile) is str and profile in PROFILES, 'Fixed synthetic profile required.')
        self.path = Path(state_dir).resolve()
        self.path.mkdir(parents=False, exist_ok=False)
        self.nonce = secrets.token_hex(32)
        self.entrypoint = Path(__file__).resolve()
        self.helper_hashes = {name: _file_sha(self.entrypoint.with_name(name)) for name in
            ('verifier_b4_owned_child_process.py', 'verifier_b4_process_exit.py',
             'verifier_b4_finish_barrier.py', 'verifier_b4_recovery.py', 'verifier_lifecycle.py')}
        # Windows venv python.exe may be a redirector that creates another
        # Python process: its Popen handle would not own the gate's process.
        # This source-only synthetic experiment uses the direct base runtime.
        # Installed-wheel/native ownership needs its own exact launch receipt.
        self.argv = [str(Path(sys._base_executable).resolve()), str(self.entrypoint), '--synthetic-owned-child',
                     str(self.path), self.nonce, str(os.getpid()), profile]
        self.start = self.identity = None
        self._sent = False
        self._ready = self._receipt = None
        self._launch_error = None
        self._launch_recovered = False
        self._recovery_attempted = False
        environment = os.environ.copy()
        # Match this pure test's dependency environment without using a Windows
        # venv redirector. This is explicitly source synthetic, never installed
        # wheel acceptance. No caller-supplied environment/command is accepted.
        environment['PYTHONPATH'] = os.pathsep.join(filter(None,
            [environment.get('PYTHONPATH', ''), *site.getsitepackages()]))
        with (self.path / 'child-stderr.log').open('xb') as error_stream:
            self.process = subprocess.Popen(self.argv, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=error_stream, text=True, encoding='utf8', env=environment)
        try:
            self.start = _process_start(self.process.pid, getattr(self.process, '_handle', None))
            self.identity = self._identity(self.start)
            _write(self.path / 'parent-launch.json', dict(scope='b4_owned_synthetic_launch_v1',
                identity=self.identity, argv=self.argv, **_flags()))
        except BaseException as exc:
            self._launch_error = repr(exc)
            raise OwnedChildLaunchError(self, exc) from exc

    def _identity(self, start):
        return dict(pid=self.process.pid, parent_pid=os.getpid(), start=deepcopy(start),
                    session_nonce=self.nonce, helper_hashes=deepcopy(self.helper_hashes))

    def observe_retained_launch(self):
        """One new proof on the original handle, never retry the failed write.

        Preserve the original launch failure, including any partial receipt.
        A separate recovery receipt binds the still-owned handle/start and
        frozen source before allowing this original synthetic protocol onward.
        Failure retains the same owner and latches; no kill/adoption/relaunch.
        """
        _require(self._launch_error is not None and not self._recovery_attempted,
                 'Retained launch observation is one-shot; no retry.')
        self._recovery_attempted = True
        try:
            _require(self.process.poll() is None, 'Original retained child is already terminal.')
            start = _process_start(self.process.pid, getattr(self.process, '_handle', None))
            _require(self.start is None or self.start == start, 'Original retained start changed.')
            _require(all(_file_sha(self.entrypoint.with_name(name)) == value
                         for name, value in self.helper_hashes.items()), 'Frozen helper changed.')
            identity = self._identity(start)
            _write(self.path / 'parent-launch-recovery.json', dict(
                scope='b4_owned_synthetic_launch_observation_v1', identity=identity,
                original_launch_failure=self._launch_error, **_flags()))
            self.start, self.identity = start, identity
            self._launch_recovered = True
            return deepcopy(identity)
        except BaseException as exc:
            # Retain even if a caller drops its prior exception reference.
            raise OwnedChildLaunchError(self, exc) from exc

    def _check_identity(self, value):
        _require(self.identity is not None, 'Original launch observation is incomplete; retain owner.')
        _require(_json(value) == _json(self.identity), 'Own handle/start/nonce/source identity mismatch.')

    def await_ready(self, timeout=5):
        """Observation only. No command/termination occurs on expiration."""
        _require(type(timeout) in (int, float) and 0 <= timeout <= 60, 'Bounded observation required.')
        deadline = time.monotonic() + timeout
        while True:
            if (self.path / 'ready.json').exists():
                try:
                    ready = _read(self.path / 'ready.json')
                except json.JSONDecodeError:
                    ready = None  # Observe again while original durable write completes.
                if ready is not None:
                    self._check_identity(ready['identity'])
                    _require(ready['scope'] == 'b4_owned_synthetic_ready_v1'
                             and ready['synthetic_cad_free'] is True
                             and ready['native_q'] == 'not_run', 'Synthetic child receipt required.')
                    _require(ready['command']['process_identity']['pid'] == self.process.pid,
                             'Gate does not belong to retained child handle.')
                    self._ready = deepcopy(ready)
                    return deepcopy(ready)
            if self.process.poll() is not None:
                raise OwnedChildProtocolError('Own child exited before a complete ready receipt.')
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(.01, max(0, deadline - time.monotonic())))

    def send_exit_command(self, command):
        _require(not self._sent, 'Own exit command is one-shot; no retry.')
        _require(self._launch_error is None or self._launch_recovered is True,
                 'Retained launch proof required before command.')
        _require(self._ready is not None, 'Original ready receipt required before command.')
        _require(_json(command) == _json(self._ready['command']), 'Foreign or altered gate command prohibited.')
        _require(self.process.poll() is None, 'Original owned child is already terminal.')
        _require(_process_start(self.process.pid, getattr(self.process, '_handle', None)) == self.start,
                 'Own child start identity changed.')
        _require(all(_file_sha(self.entrypoint.with_name(name)) == value
                     for name, value in self.helper_hashes.items()), 'Frozen helper changed.')
        self._sent = True  # A lost pipe acknowledgement is not permission to retry.
        envelope = dict(scope='b4_owned_synthetic_command_v1', identity=deepcopy(self.identity),
                        command=deepcopy(command))
        self.process.stdin.write(_json(envelope) + '\n')
        self.process.stdin.flush()
        self.process.stdin.close()

    def observe_exit(self, timeout=0):
        """Real Popen wait code plus bound durable intent and callback receipt.

        A normal callback return or any other exit code is never gate-exit proof.
        Repeated observation is allowed; no restart, command retry or kill exists.
        """
        _require(type(timeout) in (int, float) and 0 <= timeout <= 60, 'Bounded observation required.')
        if self._receipt is not None:
            return deepcopy(self._receipt)
        try:
            code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return dict(phase='owner_retained', process_exit_observed=False,
                        process_protocol_passed=False, exit_code=None, **_flags())
        receipt = dict(scope='b4_owned_synthetic_exit_observation_v1', phase='terminal',
            identity=deepcopy(self.identity), process_exit_observed=True,
            process_protocol_passed=False, exit_code=code, **_flags())
        if self._launch_error is not None:
            receipt['original_launch_failure'] = self._launch_error
        try:
            ready = _read(self.path / 'ready.json')
            intent = _read(self.path / 'exit-intent.json')
            callback = _read(self.path / 'exit-callback.json')
            self._check_identity(ready['identity'])
            self._check_identity(callback['identity'])
            _require(self._sent and self._ready == ready, 'Original sent command/ready receipt missing.')
            _require(intent['scope'] == 'b4_owned_child_exit_intent_v1'
                     and intent['phase'] == 'exit_intent'
                     and intent['command'] == ready['command']
                     and intent['exit_callback_returned'] is False
                     and intent['process_exit_observed'] is False, 'Original gate exit intent required.')
            _require(callback['scope'] == 'b4_owned_synthetic_exit_callback_v1'
                     and callback['intent_sha256'] == _sha(intent)
                     and callback['exit_code'] == EXIT_CODE, 'Original callback intent binding required.')
            _require(all(_file_sha(self.entrypoint.with_name(name)) == value
                         for name, value in self.helper_hashes.items()), 'Frozen helper changed.')
            _require(code == EXIT_CODE, 'OS exit differs from intended current-process exit.')
            receipt.update(process_protocol_passed=True, intent_sha256=_sha(intent))
        except (OSError, ValueError, KeyError, TypeError, OwnedChildProtocolError) as exc:
            receipt['reason'] = str(exc)
        _write(self.path / 'parent-exit.json', receipt)
        self._receipt = receipt
        return deepcopy(receipt)


def _sibling(filename, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyntheticOwnerQ:
    """CAD-free harness dependency; never supplied by the parent command."""

    def __init__(self):
        self.callback_returned = True
        self.guard_released = True
        self.admission_closed = True

    def observe_owner_q(self, binding):
        _require(self.callback_returned and self.guard_released and self.admission_closed,
                 'Synthetic callback/guard/admission not complete.')
        return dict(scope='b4_owner_callback_guard_q_v1', proof_id='synthetic-cad-free-owner',
            binding=deepcopy(binding), native_callback_returned=True, native_calls_returned=True,
            guard_completed=True, admission_closed=True, native_calls_live=False,
            native_calls_pending=False, queued_cad_calls=False, unknown_effects=False,
            evidence=dict(callback_return=dict(returned=True, native_calls_live=False,
                native_calls_pending=False, receipt={'synthetic_cad_free': True}),
                guard_completion=dict(completed=True, released=True, receipt={'synthetic_cad_free': True}),
                admission=dict(closed=True, queued_cad_calls=False, unknown_effects=False,
                               receipt={'synthetic_cad_free': True})))


def _child(path, nonce, parent_pid, profile):
    """Fixed current-process synthetic entrypoint. Not an installed CAD server."""
    from solidworks_mcp.jobs import JobStore
    finish = _sibling('verifier_b4_finish_barrier.py', '_b4_owned_child_finish')
    gate_module = _sibling('verifier_b4_process_exit.py', '_b4_owned_child_gate')
    path = Path(path).resolve()
    _require(profile in PROFILES and len(nonce) == 64 and parent_pid == os.getppid(),
             'Original parent nonce/profile required.')
    identity = dict(pid=os.getpid(), parent_pid=parent_pid, start=_process_start(os.getpid()),
        session_nonce=nonce, helper_hashes={name: _file_sha(Path(__file__).with_name(name)) for name in
            ('verifier_b4_owned_child_process.py', 'verifier_b4_process_exit.py',
             'verifier_b4_finish_barrier.py', 'verifier_b4_recovery.py', 'verifier_lifecycle.py')})
    context = dict(document_id='synthetic_own_part', configuration='Основная', expected_revision='synthetic_before')
    arguments = {'object_id': 'synthetic_dimension', 'value': 12, 'unit': 'mm'}
    store = JobStore(path / 'jobs.sqlite')
    history, _ = store.create('synthetic_history', 'dimension.get', {})
    store.start(history['operation_id'])
    store.finish(history['operation_id'], 'succeeded', result={'synthetic': True})
    job, _ = store.create('synthetic_target', 'dimension.set_value', arguments, context, mutates=True)
    oid = job['operation_id']
    store.start(oid)
    store.prepare_mutation(oid, connection_epoch='synthetic_epoch', **context,
                          before_state={'synthetic_cad_free': True}, effect_scope='application')
    store.verify_mutation(oid, outcome='committed', evidence={'synthetic_cad_free': True})
    barrier = finish.FinishBarrierStore(store, request_id='synthetic_target', operation='dimension.set_value',
        payload=dict(arguments=arguments, context=context, mutates=True),
        persist=lambda value: _write(path / 'barrier.json', value))
    errors = []

    def hold():
        try:
            barrier.finish(oid, 'succeeded', result={'verified': True, 'synthetic_cad_free': True})
        except BaseException as exc:
            errors.append(str(exc))

    worker = Thread(target=hold, daemon=True)
    worker.start()
    _require(barrier.wait_reached(5), 'Synthetic finish barrier not reached.')
    owner = SyntheticOwnerQ()

    def persist_intent(value):
        if profile == 'intent_failure':
            raise OSError('Injected synthetic intent persistence failure.')
        _write(path / 'exit-intent.json', value)

    def current_process_exit(value):
        if profile == 'callback_return':
            return None
        _write(path / 'exit-callback.json', dict(scope='b4_owned_synthetic_exit_callback_v1',
            identity=identity, intent_sha256=_sha(value), exit_code=EXIT_CODE, **_flags()))
        os._exit(EXIT_CODE)  # Only current fixed own synthetic child, after gate.

    gate = gate_module.OwnedChildExitGate(barrier, observe_owner_q=owner.observe_owner_q,
                                         persist=persist_intent, exit_callback=current_process_exit)
    command = gate.issue_command()
    _write(path / 'ready.json', dict(scope='b4_owned_synthetic_ready_v1', identity=identity,
                                   command=command, **_flags()))
    code = 66
    try:
        line = sys.stdin.readline(65537)
        _require(0 < len(line) <= 65536 and line.endswith('\n'), 'Complete finite owner command required.')
        envelope = json.loads(line)
        _require(type(envelope) is dict and set(envelope) == {'scope', 'identity', 'command'}
                 and envelope['scope'] == 'b4_owned_synthetic_command_v1'
                 and _json(envelope['identity']) == _json(identity), 'Foreign owner envelope prohibited.')
        returned = gate.execute(envelope['command'])
        _write(path / 'callback-returned.json', dict(receipt=returned, **_flags()))
        code = 0
    except BaseException as exc:
        _write(path / 'refusal.json', dict(reason=str(exc), gate_state=gate.state, **_flags()))
    # This control path is synthetic-only: explicit release after refusal or a
    # normally returned test callback. It is not native unknown cleanup.
    if barrier.state == 'waiting':
        barrier.release()
    worker.join(5)
    _require(not worker.is_alive() and not errors, 'Synthetic barrier did not drain normally.')
    store.close()
    return code


if __name__ == '__main__':
    _require(len(sys.argv) == 6 and sys.argv[1] == '--synthetic-owned-child',
             'Only the fixed synthetic owned-child entrypoint exists.')
    raise SystemExit(_child(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]))
