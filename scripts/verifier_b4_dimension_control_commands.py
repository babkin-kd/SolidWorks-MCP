"""Finite synchronous own-root command receiver; no CAD dispatch or Q authority.

The original parent writes dimension-command-NNNN.json once. A missing/invalid
file is an attempt failure, never a polling signal. This receiver neither runs
threads/processes nor prepares/executes a model. A persisted acknowledgement
records only the original controller action/state; no native acceptance follows.
"""
from copy import deepcopy
import importlib.util
import json
import math
import os
from pathlib import Path
from threading import RLock
from types import ModuleType

from solidworks_mcp.jobs import _json


_path = Path(__file__).with_name('verifier_b4_installed_dimension_control.py').resolve()
_spec = importlib.util.spec_from_file_location('_b4_command_original_control', _path)
controlled = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(controlled)


class CommandReceiverError(RuntimeError):
    def __init__(self, message, *, retained_receiver=None):
        super().__init__(message)
        self.retained_receiver = retained_receiver
        self.retained_owner = None if retained_receiver is None else retained_receiver.owner


def require(value, message):
    if not value:
        raise CommandReceiverError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON keys are not an exact command.')
        result[key] = value
    return result


def _read_command(path):
    require(path.resolve() == path, 'Command path must remain inside the original root; no foreign links.')
    with path.open('rb') as stream:
        value = stream.read(32769)
    require(len(value) <= 32768, 'Finite command size is 32768 bytes.')
    return json.loads(value.decode('utf8'), object_pairs_hook=_pairs,
                      parse_constant=lambda token: require(False, 'Finite JSON values required.'))


class DimensionControlCommands:
    def __init__(self, owner, *, command_limit, controller_module,
                 allowed_commands=frozenset({'inspect', 'arm', 'release', 'prepare_normal_shutdown'})):
        # Launcher may retain a separate loading of this same frozen sibling.
        # Match exact exported class identity in that original module AND its
        # original function code, rather than adopting type-name/shape objects.
        require(type(controller_module) is ModuleType and Path(controller_module.__file__).resolve() == _path,
                'Original frozen sibling controller module required.')
        klass = controller_module.InstalledDimensionControl
        require(type(owner) is klass and klass.__bases__ == (object,), 'Exact original controller instance required.')
        for name, reference in vars(controlled.InstalledDimensionControl).items():
            if callable(reference) and hasattr(reference, '__code__'):
                actual = vars(klass).get(name)
                require(callable(actual) and getattr(actual, '__code__', None) == reference.__code__,
                        'Original controller implementation changed; no callback adoption.')
        require(type(command_limit) is int and 1 <= command_limit <= 64, 'Finite original command limit 1..64 required.')
        require(type(allowed_commands) in (set, frozenset) and bool(allowed_commands)
                and allowed_commands <= {'inspect', 'arm', 'release', 'prepare_normal_shutdown'},
                'Fixed nonempty command subset required.')
        require(owner._phase == 'unarmed' and owner._fault is None and owner.seam._installed,
                'Original installed unarmed controller required; no target/control adoption.')
        self.owner, self.controller_module = owner, controller_module
        self.root, self.lineage = owner.root, deepcopy(owner.lineage)
        self.manifest = deepcopy(owner._launch_manifest)
        self._lineage_json, self._manifest_json = _json(self.lineage), _json(self.manifest)
        self._limit = command_limit
        self._allowed_commands = frozenset(allowed_commands)
        self._bound = False
        self._calls = {name: getattr(owner, method) for name, method in
            (('inspect', 'inspect_state'), ('arm', 'arm'), ('release', 'release'),
             ('prepare_normal_shutdown', 'prepare_normal_shutdown'))}
        self._next = 1
        self._closed = False
        self._fault = None
        self._attempted = self._action_completed = self._acknowledged = 0
        self._last_controller_state = None
        self._last_ack = None
        self._lock = RLock()
        self._identity()
        require(not any(self.ack_path(sequence).exists() for sequence in range(1, self.limit+1)),
                'Fresh acknowledgement paths required; no command adoption.')
        with owner._lock:
            require(not hasattr(owner, '_dimension_command_receiver'),
                    'Exactly one original receiver per controller; no retry/adoption.')
            owner._dimension_command_receiver = self
            self._bound = True

    @property
    def limit(self):
        return self._limit

    @property
    def allowed_commands(self):
        return self._allowed_commands

    def command_path(self, sequence):
        require(type(sequence) is int and 1 <= sequence <= self.limit, 'Owned finite sequence required.')
        return self.root / ('dimension-command-' + str(sequence).zfill(4) + '.json')

    def ack_path(self, sequence):
        require(type(sequence) is int and 1 <= sequence <= self.limit, 'Owned finite sequence required.')
        return self.root / ('dimension-command-ack-' + str(sequence).zfill(4) + '.json')

    def _identity(self):
        require(_json(self.lineage) == self._lineage_json and _json(self.manifest) == self._manifest_json,
                'Captured immutable receiver lineage changed.')
        if self._bound:
            require(self.owner._dimension_command_receiver is self, 'Original receiver binding changed; no adoption.')
        require(self.owner.root is self.root and self.root.resolve() == self.root
                and _json(self.owner.lineage) == _json(self.lineage)
                and os.getpid() == self.lineage['owner_pid'], 'Original live owner/root/nonce/version lineage required.')
        require(_json(self.controller_module.owned._read(self.root / 'launch-spec.json')) == _json(self.manifest),
                'Original launch manifest changed; no owner adoption.')
        require(self.owner._fault is None and self.owner.seam._installed,
                'Original controller fault/closed lifecycle forbids further commands.')
        for command, original in self._calls.items():
            method = 'inspect_state' if command == 'inspect' else command
            actual = getattr(self.owner, method)
            require(getattr(actual, '__self__', None) is self.owner
                    and getattr(actual, '__func__', None) is getattr(type(self.owner), method)
                    and actual == original, 'Original controller callback changed; no dispatch adoption.')
        if self.owner.runtime is not None:
            self.owner._lineage(self.owner.runtime, self.lineage)

    def _validate(self, value):
        require(type(value) is dict and set(value) == {'scope', 'sequence', 'nonce', 'lineage', 'command', 'arguments'},
                'Exact fixed command envelope required.')
        require(value['scope'] == 'b4_dimension_control_command_v1' and type(value['sequence']) is int
                and value['sequence'] == self._next and value['nonce'] == self.lineage['nonce']
                and _json(value['lineage']) == _json(self.lineage), 'Original ordered sequence/nonce/lineage required.')
        command, args = value['command'], value['arguments']
        require(type(command) is str and command in ('inspect', 'arm', 'release', 'prepare_normal_shutdown')
                and type(args) is dict, 'Only finite original controller commands are allowed.')
        require(command in self.allowed_commands, 'Command excluded by immutable original allowlist.')
        if command != 'arm':
            require(args == {}, 'This fixed control command takes no arguments.')
            return
        require(set(args) == {'request_id', 'operation', 'payload'} and args['operation'] == 'dimension.set_value'
                and type(args['request_id']) is str and bool(args['request_id'].strip()), 'Exact original dimension arm required.')
        payload = args['payload']
        require(type(payload) is dict and set(payload) == {'arguments', 'context', 'mutates'}
                and payload['mutates'] is True, 'Exact durable dimension payload required.')
        context, arguments = payload['context'], payload['arguments']
        keys = {'document_id', 'configuration', 'object_id', 'expected_revision'}
        require(type(context) is dict and set(context) == keys and type(arguments) is dict
                and set(arguments) == keys | {'value', 'unit'} and
                all(type(context[key]) is str and bool(context[key].strip()) and arguments[key] == context[key]
                    for key in keys), 'Exact dimension document/configuration/object/revision required.')
        require(type(arguments['value']) is float and math.isfinite(arguments['value']) and arguments['value'] > 0
                and arguments['unit'] in ('mm', 'deg') and
                (arguments['unit'] != 'deg' or arguments['value'] < 360), 'Exact supported typed dimension value/unit required.')

    def handle_command(self):
        """One expected file, one synchronous action, one durable ack; no retry."""
        with self._lock:
            try:
                require(not self._closed and self._fault is None, 'Command receiver is permanently closed; no retry.')
                self._attempted += 1
                self._identity()
                command_path, ack_path = self.command_path(self._next), self.ack_path(self._next)
                require(not ack_path.exists() and ack_path.resolve() == ack_path, 'Fresh original acknowledgement path required.')
                value = _read_command(command_path)
                self._validate(value)
                command, args = value['command'], value['arguments']
                if command == 'inspect':
                    result = self._calls[command]()
                elif command == 'arm':
                    result = self._calls[command](runtime=self.owner.runtime, lineage=deepcopy(self.lineage), **args)
                elif command == 'release':
                    result = self._calls[command](runtime=self.owner.runtime, lineage=deepcopy(self.lineage))
                else:
                    result = self._calls[command]()
                self._action_completed += 1
                self._last_controller_state = self.owner.inspect_state()
                self._identity()
                require(_json(_read_command(command_path)) == _json(value),
                        'Original command changed during action; retain completed action without retry.')
                ack = dict(scope='b4_dimension_control_command_ack_v1', sequence=self._next,
                    nonce=self.lineage['nonce'], lineage=deepcopy(self.lineage), command=command,
                    arguments=deepcopy(args), result=deepcopy(result), controller_state=deepcopy(self._last_controller_state),
                    **self.controller_module.authority())
                self.controller_module.owned._write(ack_path, ack)
                self._acknowledged += 1
                self._last_ack = deepcopy(ack)
                self._next += 1
                if self._next > self.limit:
                    self._closed = True
                return ack
            except Exception as exc:
                self._closed = True
                if self._fault is None:
                    self._fault = type(exc).__name__ + ': ' + str(exc)
                raise CommandReceiverError(self._fault, retained_receiver=self) from exc

    def inspect_state(self):
        with self._lock:
            return dict(scope='b4_dimension_control_command_receiver_state_v1', closed=self._closed, fault=self._fault,
                lineage=deepcopy(self.lineage), command_limit=self.limit,
                allowed_commands=sorted(self.allowed_commands),
                next_sequence=None if self._closed else self._next, attempted=self._attempted,
                action_completed=self._action_completed, acknowledged=self._acknowledged,
                last_controller_state=deepcopy(self._last_controller_state), last_ack=deepcopy(self._last_ack),
                **self.controller_module.authority())
