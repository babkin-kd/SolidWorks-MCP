"""One-shot native change of the exact retained owned extrusion.

The domain caller owns the durable checkpoint, released-session observation,
postconditions and any separately justified inverse. A normal native return is
recorded independently of its scalar success. This bridge never retries,
activates, switches configuration, deletes or performs an automatic inverse.
"""
from dataclasses import dataclass, field

from .documents import rejected
from .jobs import ExecutionFailure
from .timings_v2 import timed_call


@dataclass
class OwnedSuppressionReceipt:
    suppressed: bool
    original_suppressed: bool
    attempted: bool = False
    pending_native_step: str = None
    journal_failed: bool = False
    steps: list = field(default_factory=list)

    def evidence(self):
        return dict(suppressed=self.suppressed, original_suppressed=self.original_suppressed,
            attempted=self.attempted, pending_native_step=self.pending_native_step,
            journal_failed=self.journal_failed, steps=[dict(row) for row in self.steps])


class NativeOwnedFeatureSuppression:
    def __init__(self, registry, binding, suppressed, *, recorder):
        if type(suppressed) is not bool or not callable(recorder):
            raise rejected('suppression_input_invalid', 'An explicit boolean and durable native step recorder are required.')
        self.registry, self.adapter, self.binding = registry, registry.adapter, binding
        self.recorder = recorder
        feature = self._resolve()
        original = self._suppressed(feature)
        if original == suppressed:
            raise rejected('suppression_already_requested', 'Prepare an actual state transition; no native no-op is dispatched.')
        self.receipt = OwnedSuppressionReceipt(suppressed, original)

    def _resolve(self):
        binding, feature = self.registry.resolve(self.binding.document_id,
            self.binding.configuration, self.binding.object_id,
            connection_epoch=self.binding.connection_epoch)
        if (binding is not self.binding or binding.kind != 'extrusion'
                or self.adapter.identity(feature) != binding.feature_identity):
            raise rejected('suppression_target_changed', 'Only the same retained owned extrusion is supported.')
        if self.adapter.identity(self.adapter.active_document()) != binding.model_identity:
            raise rejected('suppression_target_inactive', 'Explicitly activate the original target before preparation.')
        return feature

    @staticmethod
    def _suppressed(feature):
        value = list(feature.IsSuppressed2(1, None))
        if len(value) != 1 or type(value[0]) is not bool:
            raise rejected('suppression_state_unconfirmed', 'Exact current-configuration native suppression state is required.')
        return value[0]

    def _step(self, name, call, *args):
        receipt = self.receipt
        if receipt.pending_native_step is not None or receipt.journal_failed:
            raise ExecutionFailure('suppression_native_pending', 'An earlier native/storage boundary is unconfirmed.', uncertain=True)
        row = dict(name=name, native_call_returned=False, result=None)
        receipt.steps.append(row)
        receipt.pending_native_step = name
        receipt.journal_failed = True
        self.recorder(name, 'pending', dict(row))
        receipt.journal_failed = False
        value = timed_call('com', call, *args)
        # Preserve even an unexpected scalar without serializing native objects.
        row.update(native_call_returned=True, result=value if type(value) is bool else None,
                   result_is_boolean=type(value) is bool)
        receipt.journal_failed = True
        self.recorder(name, 'returned', dict(row))
        receipt.journal_failed = False
        receipt.pending_native_step = None
        if type(value) is not bool or value is not True:
            raise ExecutionFailure('suppression_native_rejected',
                'The native call returned without confirming success; inspect its actual effect.', uncertain=False)
        return value

    def apply(self):
        receipt = self.receipt
        if receipt.attempted or receipt.pending_native_step is not None or receipt.journal_failed:
            raise rejected('suppression_receipt_consumed', 'A native suppression receipt cannot be reused.')
        feature = self._resolve()
        if self._suppressed(feature) != receipt.original_suppressed:
            raise rejected('suppression_target_changed', 'The exact retained state changed before dispatch.')
        if self.adapter.application_busy() is not True:
            raise rejected('suppression_guard_missing', 'The caller must acquire its own checkpointed application guard.')
        receipt.attempted = True
        # swSuppressFeature=0, swUnSuppressFeature=2; swThisConfiguration=1.
        self._step('set_suppressed', feature.SetSuppression2,
                   0 if receipt.suppressed else 2, 1, None)
        self._step('rebuild', self.binding.model.ForceRebuild3, False)
        # Independent full-session inspection follows the caller's guard release.
        return self.receipt.evidence()
