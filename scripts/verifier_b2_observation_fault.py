"""One controlled Python observation failure after a normally completed delete.

No COM connection, fixture creation, cleanup or reconciliation is provided.
The sole native owner installs this on its already proved owned adapter/binding.
The original bridge and full snapshot always run first. A pending/failed bridge
or incomplete snapshot cannot be relabeled as this controlled fault.
"""
from copy import deepcopy
from threading import get_ident

from solidworks_mcp.rectangle_snapshot import SKETCH, validated_rectangle_snapshot


class ControlledLeafObservationFault(RuntimeError):
    pass


class ControlledLeafNoEffectFault(RuntimeError):
    pass


class LeafObservationFault:
    def __init__(self, adapter, binding):
        if binding.kind != 'extrusion' or adapter.identity(binding.model) != binding.model_identity:
            raise ValueError('The original owned extrusion/model binding is required.')
        self.adapter, self.binding = adapter, binding
        self.owner_thread = get_ident()
        self.original_bridge = adapter.restore_rectangle_extrusion
        self.original_snapshot = adapter.rectangle_construction_snapshot
        self.installed = self.detached = self.armed = False
        self.pending_bridge = self.pending_snapshot = False
        self.bridge_attempts = self.normal_bridge_returns = self.injected_faults = 0
        self.bridge_dispatches = 0
        self.bridge_exception_returned = self.snapshot_exception_returned = False
        self.after_snapshot = None

    def _thread(self):
        if get_ident() != self.owner_thread:
            raise ValueError('Only the original native owner can use these hooks.')

    def _target(self, model):
        return self.adapter.identity(model) == self.binding.model_identity

    def install(self):
        self._thread()
        if self.installed or self.detached:
            raise ValueError('Fault-hook installation is one-shot.')
        if not self._target(self.binding.model):
            raise ValueError('The original target incarnation changed.')
        self.adapter.restore_rectangle_extrusion = self.bridge
        self.adapter.rectangle_construction_snapshot = self.snapshot
        self.installed = True
        return self

    def bridge(self, model, receipt):
        self._thread()
        self.bridge_dispatches += 1
        if (not self.installed or self.detached or self.bridge_attempts
                or not self._target(model) or receipt is self.binding.receipt
                or receipt.extrusion is not self.binding.feature
                or receipt.borrowed_sketch is not self.binding.receipt.borrowed_sketch):
            raise ValueError('Only one original own-clone deletion may arm this fault.')
        self.bridge_attempts += 1
        self.pending_bridge = True
        try:
            value = self.original_bridge(model, receipt)
        except BaseException:
            self.bridge_exception_returned = True
            # An exception is not a native completion acknowledgement.
            raise
        self.normal_bridge_returns += 1
        self.pending_bridge = False
        if (receipt.restore_attempted is not True or receipt.restored is not True
                or receipt.pending_native_step is not None
                or receipt.native_step_journal_failed is not False
                or receipt.selection_uncertain is not False
                or receipt.view_state_uncertain is not False):
            raise ValueError('A normal fully acknowledged deletion bridge is required.')
        self.armed = True
        return value

    def snapshot(self, model):
        self._thread()
        if not self.installed or self.detached:
            raise ValueError('The original live observation hook is required.')
        target = self._target(model)
        if not self.armed or not target:
            return self.original_snapshot(model)
        self.pending_snapshot = True
        try:
            actual = self.original_snapshot(model)
        except BaseException:
            self.snapshot_exception_returned = True
            raise
        self.pending_snapshot = False
        actual = validated_rectangle_snapshot(actual)
        if actual['clone_state']['profile'] != SKETCH or actual['solid_body_count'] != 0:
            raise ValueError('Only a complete actual surviving SKETCH can produce this controlled fault.')
        self.after_snapshot = deepcopy(actual)
        self.armed = False
        self.injected_faults += 1
        raise ControlledLeafObservationFault('Controlled Python observation failure after normal native delete/snapshot.')

    def evidence(self):
        return dict(scope='owned_leaf_controlled_python_observation_fault_v1',
            installed=self.installed, detached=self.detached, armed=self.armed,
            pending_bridge=self.pending_bridge, pending_snapshot=self.pending_snapshot,
            bridge_attempts=self.bridge_attempts, normal_bridge_returns=self.normal_bridge_returns,
            bridge_dispatches=self.bridge_dispatches,
            injected_faults=self.injected_faults, bridge_exception_returned=self.bridge_exception_returned,
            snapshot_exception_returned=self.snapshot_exception_returned,
            actual_after_snapshot=deepcopy(self.after_snapshot),
            native_acceptance=False, cleanup_authorized=False, reconciliation_authorized=False)

    def detach(self):
        """Retire only Python hooks; this never closes models or releases holds."""
        self._thread()
        if (not self.installed or self.detached or self.pending_bridge or self.pending_snapshot
                or self.armed or self.injected_faults != 1):
            raise ValueError('Only the normally completed one-shot hook may be detached.')
        if (self.adapter.restore_rectangle_extrusion != self.bridge
                or self.adapter.rectangle_construction_snapshot != self.snapshot):
            raise ValueError('Another owner changed the adapter hooks.')
        self.adapter.restore_rectangle_extrusion = self.original_bridge
        self.adapter.rectangle_construction_snapshot = self.original_snapshot
        self.detached = True


class LeafNoEffectFault(LeafObservationFault):
    """A Python failure before the native deletion bridge, never a fake COM throw.

The actual domain must independently prove the full original state, guard
release and durable known failure. This hook provides no such proof itself.
"""
    def bridge(self, model, receipt):
        self._thread()
        self.bridge_dispatches += 1
        if (not self.installed or self.detached or self.bridge_attempts
                or not self._target(model) or receipt is self.binding.receipt
                or receipt.extrusion is not self.binding.feature
                or receipt.borrowed_sketch is not self.binding.receipt.borrowed_sketch
                or receipt.restore_attempted is not False or receipt.pending_native_step is not None):
            raise ValueError('Only one original untouched own-clone may receive the no-effect fault.')
        self.bridge_attempts += 1
        self.injected_faults += 1
        raise ControlledLeafNoEffectFault('Controlled Python failure before native leaf deletion dispatch.')

    def evidence(self):
        return {**super().evidence(), 'scope':'owned_leaf_controlled_python_no_effect_v1',
            'fault_before_native_bridge':True}
