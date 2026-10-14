"""Finite original receiver host; no COM, SDK, process stop or Q authority.

Only atomically published command files enter the existing synchronous receiver.
Stopping the wait never interrupts an action which has already entered it.
"""
from copy import deepcopy
import importlib.util
import json
import math
import os
from pathlib import Path
from threading import Event, Lock, Thread
from types import ModuleType

_path = Path(__file__).with_name('verifier_b4_dimension_control_commands.py').resolve()
_spec = importlib.util.spec_from_file_location('_b4_host_original_commands', _path)
commands = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(commands)


class CommandHostError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise CommandHostError(message)


def publish_command(root, value):
    """Publish one fresh complete request by rename; never overwrite or retry.

    The caller still owns admission and original child identity. This publisher
    confers no action authority; the receiver validates the complete request.
    Failed publication retains its private partial file for diagnosis.
    """
    root = Path(root)
    require(root.is_absolute() and root.is_dir() and root.resolve() == root, 'Original absolute owned root required.')
    require(type(value) is dict and set(value) == {'scope', 'sequence', 'nonce', 'lineage', 'command', 'arguments'}
            and value['scope'] == 'b4_dimension_control_command_v1'
            and type(value['sequence']) is int and 1 <= value['sequence'] <= 64
            and type(value['lineage']) is dict and value['lineage'].get('state_root') == str(root)
            and type(value['nonce']) is str and len(value['nonce']) == 64
            and value['lineage'].get('nonce') == value['nonce']
            and value['command'] in ('inspect', 'arm', 'release', 'prepare_normal_shutdown')
            and type(value['arguments']) is dict, 'Exact finite command publication required.')
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf8')
    require(len(raw) <= 32768, 'Finite command size is 32768 bytes.')
    name = 'dimension-command-' + str(value['sequence']).zfill(4) + '.json'
    path, partial = root / name, root / (name + '.publishing')
    require(not path.exists() and not partial.exists() and path.resolve() == path and partial.resolve() == partial,
            'Fresh original command paths required; no overwrite/adoption.')
    with partial.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    # NTFS rename publishes complete bytes. Existing final paths must fail, not
    # replace an earlier command, including a race after the preflight above.
    if os.name == 'nt':
        os.rename(partial, path)
    else:
        os.link(partial, path)
        partial.unlink()
    return path


class DimensionCommandHost:
    def __init__(self, receiver, *, command_module, poll_interval_s=.02):
        require(type(command_module) is ModuleType and Path(command_module.__file__).resolve() == _path,
                'Original command receiver module required.')
        klass = command_module.DimensionControlCommands
        require(type(receiver) is klass, 'Exact original command receiver required.')
        for name, reference in vars(commands.DimensionControlCommands).items():
            if callable(reference) and hasattr(reference, '__code__'):
                actual = vars(klass).get(name)
                require(getattr(actual, '__code__', None) == reference.__code__, 'Receiver implementation changed.')
        require(type(poll_interval_s) in (int, float) and math.isfinite(poll_interval_s)
                and .001 <= poll_interval_s <= .1, 'Finite wait interval required.')
        require(not hasattr(receiver, '_dimension_command_host'), 'One original host only; no restart/adoption.')
        receiver._identity()
        self.receiver, self.command_module = receiver, command_module
        self._klass, self._limit, self._allowed = klass, receiver.limit, receiver.allowed_commands
        self._codes = {name: method.__code__ for name, method in vars(klass).items()
                       if callable(method) and hasattr(method, '__code__')}
        self._interval, self._lock = float(poll_interval_s), Lock()
        self._stop, self._done = Event(), Event()
        self._started = False
        self._state = dict(scope='b4_dimension_command_host_state_v1', phase='new', fault=None,
            action_live=False, completed_commands=0, lineage=deepcopy(receiver.lineage),
            receiver_state=None, runtime_open_at_last_action=None, **receiver.controller_module.authority())
        self._thread = Thread(target=self._run, name='b4-owned-dimension-commands', daemon=False)
        with receiver._lock:
            require(not hasattr(receiver, '_dimension_command_host'), 'One original host only; no concurrent adoption.')
            receiver._dimension_command_host = self

    def _identity(self):
        require(self.command_module.DimensionControlCommands is self._klass
                and Path(self.command_module.__file__).resolve() == _path
                and type(self.receiver) is self._klass and self.receiver._dimension_command_host is self
                and type(self.receiver.limit) is int and self.receiver.limit == self._limit
                and self.receiver.allowed_commands == self._allowed,
                'Original host module/budget/allowlist binding changed.')
        for name, code in self._codes.items():
            current = getattr(self._klass, name)
            method = getattr(self.receiver, name)
            require(getattr(current, '__code__', None) is code
                    and getattr(method, '__self__', None) is self.receiver
                    and getattr(method, '__func__', None) is current,
                    'Original host receiver methods changed; no callback adoption.')
        self.receiver._identity()

    def start(self):
        with self._lock:
            require(not self._started, 'Original command host starts once; no retry.')
            self._started = True
            self._state['phase'] = 'waiting'
        try:
            self._thread.start()
        except BaseException as exc:
            self._update(phase='fault', fault=type(exc).__name__ + ': ' + str(exc))
            self._done.set()
            raise
        return self

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def _run(self):
        try:
            while not self._stop.is_set():
                self._identity()
                state = self.receiver.inspect_state()
                self._update(receiver_state=state)
                if state['closed']:
                    require(state['fault'] is None and state['acknowledged'] == self._limit,
                            'Original finite commands did not all acknowledge.')
                    self._update(phase='completed')
                    return
                # Factories create this original Runtime inside server.main.
                # Read only Python references; never prepare a CAD catalog here.
                path = self.receiver.command_path(state['next_sequence'])
                if self.receiver.owner.runtime is None or not path.exists():
                    self._stop.wait(self._interval)
                    continue
                self._update(phase='executing', action_live=True,
                             runtime_open_at_last_action=self.receiver.owner.runtime._closed is False)
                try:
                    self.receiver.handle_command()
                finally:
                    self._update(action_live=False)
                self._update(phase='waiting', completed_commands=state['acknowledged'] + 1)
            self._update(phase='stopped_incomplete')
        except BaseException as exc:
            self._update(phase='fault', fault=type(exc).__name__ + ': ' + str(exc))
        finally:
            self._done.set()

    def inspect_state(self):
        # Never acquire the receiver/action lock from an observation caller.
        with self._lock:
            value = deepcopy(self._state)
        value['thread_return_observed'] = self._started and self._done.is_set() and not self._thread.is_alive()
        return value

    def wait(self, timeout_s=0):
        require(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 <= timeout_s <= 60,
                'Bounded observation wait required.')
        if self._thread.ident is not None:
            self._thread.join(timeout_s)
        return self.inspect_state()

    def stop_waiting(self):
        """End missing-file wait only; an entered action must return normally."""
        self._stop.set()
        return self.inspect_state()
