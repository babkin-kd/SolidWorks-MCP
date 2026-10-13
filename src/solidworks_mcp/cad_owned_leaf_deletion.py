"""Separate one-shot deletion receipt using the proven extrusion inverse.

No public dispatch or generic deletion authority. The domain caller supplies
the complete current leaf proof, checkpoint/guard and independent BASE→SKETCH
postcondition. The original successful creation receipt is never consumed.
Native handles are retained; only receipt/metadata containers are copied.
"""
from dataclasses import fields, is_dataclass

from .documents import rejected


def _receipt_copy(value):
    """Copy server receipt structure without pickling/deepcopying COM handles."""
    if type(value) is dict:
        return {key:_receipt_copy(item) for key,item in value.items()}
    if type(value) is list:
        return [_receipt_copy(item) for item in value]
    if type(value) is tuple:
        return tuple(_receipt_copy(item) for item in value)
    if is_dataclass(value) and not isinstance(value,type):
        return type(value)(**{field.name:_receipt_copy(getattr(value,field.name))
                             for field in fields(value) if field.init})
    return value


class NativeOwnedLeafDeletion:
    def __init__(self, registry, binding, *, recorder, capture_view=None):
        if not callable(recorder):
            raise rejected('leaf_deletion_journal_invalid','A server durable native step recorder is required.')
        self.registry,self.adapter,self.binding=registry,registry.adapter,binding
        self.attempted=False
        self.bridge_returned=False
        self.bridge_exception_returned=False
        self.pending_apply=False
        self._resolve()
        original=binding.receipt
        self.stage=_receipt_copy(original)
        if self.stage is original or not is_dataclass(original):
            raise rejected('leaf_deletion_receipt_invalid','A distinct structured owned creation receipt is required.')
        # The current viewport is preserved. Restoring the creation-time view
        # would overwrite a later user's viewport even if the sketch is unchanged.
        if capture_view is None:
            from .cad_rectangle_model_view import capture_model_view
            capture_view=lambda model:capture_model_view(self.adapter,model)
        self.stage.model_view=capture_view(binding.model)
        if self.stage.model_view is None or self.stage.annotation_views is None:
            raise rejected('leaf_deletion_view_unavailable','Full retained annotation views and current model view are required.')
        self.stage.native_step_recorder=recorder
        self.stage.deleted=[]
        self.stage.restore_attempted=False
        self.stage.restored=False
        self._resolve()

    def _resolve(self):
        held,feature=self.registry.resolve(self.binding.document_id,self.binding.configuration,
            self.binding.object_id,connection_epoch=self.binding.connection_epoch)
        if (held is not self.binding or held.kind!='extrusion'
                or self.adapter.identity(feature)!=held.feature_identity
                or self.adapter.identity(self.adapter.active_document())!=held.model_identity):
            raise rejected('leaf_deletion_target_changed','Only the same original active owned extrusion is supported.')
        states=list(feature.IsSuppressed2(1,None))
        children=feature.GetChildren()
        if (len(states)!=1 or states[0] is not False
                or not (children is None or type(children) in (list,tuple)) or children):
            raise rejected('leaf_deletion_target_unsupported','Unsuppressed own leaf with normally returned empty native children required.')
        sketch=held.receipt.borrowed_sketch
        if (sketch is None or self.adapter.identity(sketch)!=held.receipt.borrowed_sketch_identity
                or sum(self.adapter.identity(item)==held.receipt.borrowed_sketch_identity
                       for item in self.adapter.features(held.model))!=1):
            raise rejected('leaf_deletion_sketch_changed','The original retained borrowed sketch must remain current.')
        return feature

    def evidence(self):
        stage=self.stage
        return dict(attempted=self.attempted,bridge_returned=self.bridge_returned,
            bridge_exception_returned=self.bridge_exception_returned,pending_apply=self.pending_apply,
            deletion_attempted=stage.restore_attempted,deletion_bridge_verified=stage.restored,
            pending_native_step=stage.pending_native_step,journal_failed=stage.native_step_journal_failed,
            selection_uncertain=stage.selection_uncertain,view_state_uncertain=stage.view_state_uncertain)

    def apply(self):
        if self.attempted:
            raise rejected('leaf_deletion_receipt_consumed','A leaf deletion receipt cannot be reused.')
        self._resolve()
        if self.adapter.application_busy() is not True:
            raise rejected('leaf_deletion_guard_missing','The caller must acquire its own checkpointed application guard.')
        self.attempted=True
        self.pending_apply=True
        try:
            # DeleteSelection2(0) preserves the borrowed sketch; the existing
            # bridge records native delete/rebuild/view steps on our OWN clone.
            self.adapter.restore_rectangle_extrusion(self.binding.model,self.stage)
        except Exception:
            # Python control returned with an exception; this does NOT acknowledge
            # any still-pending COM/native ledger step inside the bridge.
            self.bridge_exception_returned=True
            self.pending_apply=False
            raise
        self.pending_apply=False
        self.bridge_returned=True
        return self.evidence()
