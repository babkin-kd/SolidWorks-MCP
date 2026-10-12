"""Separate native construction stages; unpublished until full domain/native gates.

The caller supplies a durable checkpoint, explicit resolved targets and complete
before/after proofs. These bridges neither activate nor save a document.
Extrusion borrows the baseline sketch and never owns its deletion.
"""
from copy import deepcopy
from dataclasses import dataclass

from . import binding
from .cad_part_creation import NativeBaseReceipt
from .constants import SW_FULLY_CONSTRAINED
from .documents import rejected
from .jobs import ExecutionFailure
from .timings_v2 import timed_call


@dataclass
class NativeRectangleStageReceipt(NativeBaseReceipt):
    attempted: bool = False
    native_call_returned: bool = False
    pending_sketch_close: bool = False
    sketch_closed: bool = False
    borrowed_sketch: object = None
    borrowed_sketch_identity: object = None
    borrowed_sketch_snapshot: object = None
    raw_extrusion_return: object = None
    restore_attempted: bool = False
    pending_native_step: str = None
    native_step_recorder: object = None
    native_step_journal_failed: bool = False


class CadRectangleConstructionMixin:
    @staticmethod
    def _rectangle_native_step(receipt, label, call, *args, **kwargs):
        if receipt.pending_native_step is not None or receipt.native_step_journal_failed:
            raise ExecutionFailure('construction_native_pending', 'An earlier native step is unconfirmed.', uncertain=True)
        receipt.pending_native_step = label
        recorder = receipt.native_step_recorder
        if recorder is not None:
            receipt.native_step_journal_failed = True
            recorder(label, 'pending', {'native_call_returned': False})
            receipt.native_step_journal_failed = False
        value = timed_call('com', call, *args, **kwargs)
        if recorder is not None:
            receipt.native_step_journal_failed = True
            # No native handle or arbitrary repr enters the durable JSON journal.
            # A normal return is evidence of completion of this call, not success
            # of the operation; the independent admission still decides success.
            recorder(label, 'returned', {'native_call_returned': True})
            receipt.native_step_journal_failed = False
        # Deliberately not finally: an exception cannot acknowledge a native call.
        receipt.pending_native_step = None
        return value

    def new_rectangle_stage_receipt(self, model, features, controls, *, sketch=None, recorder=None):
        if recorder is not None and not callable(recorder):
            raise rejected('construction_journal_invalid', 'Only a server-owned native step recorder is supported.')
        base = self.new_base_receipt(model, features, controls)
        receipt = NativeRectangleStageReceipt(base.model_identity, base.configuration_identity,
            base.baseline_features, dict(base.controls))
        receipt.native_step_recorder = recorder
        if sketch is not None:
            token = self.identity(sketch)
            if not any(token == identity for identity, _ in receipt.baseline_features):
                raise rejected('construction_sketch_not_current', 'Extrusion borrows an exact baseline sketch.')
            if sketch.GetTypeName2() != 'ProfileFeature':
                raise rejected('construction_profile_unsupported', 'Use a current planar sketch.')
            native = binding.wrap(sketch.GetSpecificFeature2(), self._module.ISketch)
            if native is None or native.GetConstrainedStatus() != SW_FULLY_CONSTRAINED:
                raise rejected('construction_profile_unsupported', 'Use a fully defined closed rectangle.')
            receipt.borrowed_sketch = sketch
            receipt.borrowed_sketch_identity = token
            receipt.borrowed_sketch_snapshot = deepcopy(self.sketch_snapshot(model, sketch)[0])
        return receipt

    def _rectangle_stage_ready(self, model, receipt):
        if (receipt.attempted or receipt.restored or receipt.restore_attempted
                or receipt.pending_native_step or receipt.native_step_journal_failed):
            raise rejected('construction_receipt_consumed', 'A native stage receipt cannot be repeated.')
        self._base_target(model, receipt)
        if self.bodies(model, 'all') or self.part_creation_controls(model) != receipt.controls:
            raise rejected('construction_baseline_changed', 'Empty body scope and original controls are required.')
        if receipt.controls['add_to_db'] or receipt.controls['dimension_input']:
            raise rejected('unsupported_creation_ui', 'Disable AddToDB and interactive dimension input.')
        manager = binding.wrap(model.SketchManager, self._module.ISketchManager)
        if manager.ActiveSketch is not None:
            raise rejected('part_not_writable', 'An open sketch cannot be borrowed or implicitly closed.')
        return manager

    def create_rectangle_sketch(self, model, plane, definition, receipt):
        manager = self._rectangle_stage_ready(model, receipt)
        if receipt.borrowed_sketch is not None:
            raise rejected('construction_receipt_scope', 'Sketch creation cannot use an extrusion receipt.')
        if (not any(self.identity(plane) == token for token, _ in receipt.baseline_features)
                or plane.GetTypeName2() != 'RefPlane' or self.feature_summary(plane)['suppressed']):
            raise rejected('invalid_reference_plane', 'The exact baseline unsuppressed plane is required.')
        from .session import SolidWorksSession
        from .sketch_constraints import SketchDefiner
        with self._base_selection(model, receipt):
            if not plane.Select2(False, 0):
                raise rejected('construction_plane_select_failed', 'The exact plane could not be selected.')
            receipt.attempted = True
            receipt.pending_creation = True
            self._base_target(model, receipt)
            self._rectangle_native_step(receipt, 'open_sketch', manager.InsertSketch, True)
            receipt.native_call_returned = True
            sketch = binding.wrap(manager.ActiveSketch, self._module.ISketch)
            if sketch is None:
                raise ExecutionFailure('construction_sketch_unconfirmed', 'No exact returned sketch.', uncertain=True)
            receipt.native_sketch, receipt.native_sketch_identity = sketch, self.identity(sketch)
            feature = self._retain_base_feature(model, receipt, 'sketch', self._feature_for_exact_sketch(model, sketch))
            self._rectangle_native_step(receipt, 'name_sketch', setattr, feature, 'Name', definition.sketch_name)
            if feature.Name != definition.sketch_name:
                raise rejected('construction_name_mismatch', 'The requested Russian sketch name was not retained.')
            lines = self._rectangle_native_step(receipt, 'draw_rectangle',
                SolidWorksSession._draw_polyline, manager, definition.profile_m)
            origins = [f for f in self.features(model) if f.GetTypeName2() == 'OriginProfileFeature']
            if len(origins) != 1:
                raise rejected('construction_origin_unavailable', 'An exact unique model origin is required.')
            points = binding.wrap(origins[0].GetSpecificFeature2(), self._module.ISketch).GetSketchPoints2()
            if points is None or len(points) != 1:
                raise rejected('construction_origin_unavailable', 'An exact unique origin point is required.')
            self._base_target(model, receipt)
            definer = SketchDefiner(model, self._module, manager, sketch,
                binding.wrap(points[0], self._module.ISketchPoint))
            names = {(axis, i): role for axis, role in [('x', 'Ширина'), ('y', 'Высота')] for i in range(8)}
            self._rectangle_native_step(receipt, 'define_rectangle', definer.define,
                lines, names=names, origin_mm=(0., 0.))
            if definer.fully_defined() is not True:
                raise rejected('construction_sketch_underdefined', 'Native rectangle constraints are incomplete.')
            current = binding.wrap(manager.ActiveSketch, self._module.ISketch)
            if current is None or self.identity(current) != receipt.native_sketch_identity:
                raise ExecutionFailure('construction_sketch_changed', 'An unrelated open sketch replaced the target.', uncertain=True)
            receipt.pending_sketch_close = True
            self._rectangle_native_step(receipt, 'close_sketch', manager.InsertSketch, True)
            if manager.ActiveSketch is not None:
                raise ExecutionFailure('construction_sketch_close_unconfirmed', 'The owned sketch close is unconfirmed.', uncertain=True)
            receipt.pending_sketch_close = False
            receipt.sketch_closed = True
            if self._rectangle_native_step(receipt, 'rebuild_sketch', self.rebuild_dimension_document, model) is not True:
                raise rejected('construction_rebuild_failed', 'The closed sketch rebuild did not finish.')
        if self.bodies(model, 'all') or self.part_creation_controls(model) != receipt.controls:
            raise rejected('construction_sketch_postcondition', 'Sketch-only creation must preserve empty geometry and controls.')

    def extrude_rectangle_sketch(self, model, definition, receipt):
        self._rectangle_stage_ready(model, receipt)
        sketch = receipt.borrowed_sketch
        if sketch is None:
            raise rejected('construction_receipt_scope', 'Extrusion requires an exact baseline sketch.')
        if not any(self.identity(f) == receipt.borrowed_sketch_identity for f in self.features(model)):
            raise rejected('construction_sketch_not_current', 'The original sketch incarnation is missing.')
        if self.sketch_snapshot(model, sketch)[0] != receipt.borrowed_sketch_snapshot:
            raise rejected('construction_baseline_changed', 'Sketch data changed after preparation.')
        with self._base_selection(model, receipt):
            if not sketch.Select2(False, 0):
                raise rejected('construction_sketch_select_failed', 'Exact baseline profile selection failed.')
            self._base_target(model, receipt)
            factory = binding.wrap(model.FeatureManager, self._module.IFeatureManager)
            receipt.attempted = True
            receipt.pending_creation = True
            raw = self._rectangle_native_step(receipt, 'extrude', factory.FeatureExtrusion3, True, False, False, 0, 0, definition.depth_m, 0.,
                False, False, False, False, 0., 0., False, False, False, False,
                True, False, False, 0, 0., False)
            receipt.raw_extrusion_return = raw
            receipt.native_call_returned = True
            extrusion = self._retain_base_feature(model, receipt, 'extrusion', raw)
            self._rectangle_native_step(receipt, 'name_extrusion', setattr, extrusion, 'Name', definition.feature_name)
            dimension = binding.wrap(extrusion.Parameter('D1'), self._module.IDimension)
            if dimension is None:
                raise rejected('construction_depth_dimension_unavailable', 'Exact native depth dimension missing.')
            self._rectangle_native_step(receipt, 'name_depth', setattr, dimension, 'Name', 'Толщина')
            if extrusion.Name != definition.feature_name or dimension.Name != 'Толщина':
                raise rejected('construction_name_mismatch', 'Russian feature/dimension names were not retained.')
            if self._rectangle_native_step(receipt, 'rebuild', self.rebuild_dimension_document, model) is not True:
                raise rejected('construction_rebuild_failed', 'Explicit extrusion rebuild did not finish.')
            bodies = self.bodies(model, 'all')
            if len(bodies) != 1 or bodies[0].GetType() != 0:
                raise rejected('construction_body_scope_mismatch', 'Exactly one new solid is required.')
            receipt.body, receipt.body_identity = bodies[0], self.identity(bodies[0])
            self._rectangle_native_step(receipt, 'name_body', setattr, bodies[0], 'Name', definition.body_name)
            if bodies[0].Name != definition.body_name:
                raise rejected('construction_name_mismatch', 'The Russian body name was not retained.')
        if self.part_creation_controls(model) != receipt.controls:
            raise rejected('construction_controls_changed', 'Original creation controls were not restored.')

    def restore_rectangle_sketch(self, model, receipt):
        if (receipt.pending_creation or receipt.pending_sketch_close or receipt.pending_native_step
                or receipt.native_step_journal_failed
                or receipt.selection_uncertain or receipt.restore_attempted or receipt.borrowed_sketch is not None):
            raise ExecutionFailure('construction_restore_unsafe', 'Unknown or borrowed sketch cannot be deleted.', uncertain=True)
        receipt.restore_attempted = True
        # Only this stage's exact newly created sketch is owned by the base restorer.
        self._rectangle_native_step(receipt, 'restore_owned_sketch', self.restore_base_rectangle, model, receipt)

    def restore_rectangle_extrusion(self, model, receipt):
        if (receipt.pending_creation or receipt.pending_sketch_close or receipt.selection_uncertain
                or receipt.pending_native_step or receipt.native_step_journal_failed
                or receipt.restore_attempted or receipt.borrowed_sketch is None):
            raise ExecutionFailure('construction_restore_unsafe', 'Unknown effects cannot authorize deletion/retry.', uncertain=True)
        self._base_target(model, receipt)
        features = self.features(model)
        if not any(self.identity(f) == receipt.borrowed_sketch_identity for f in features):
            raise rejected('construction_restore_unsafe', 'The exact baseline sketch must survive.')
        if receipt.extrusion is None:
            raise rejected('construction_restore_unsafe', 'No exact created extrusion is owned.')
        token = receipt.extrusion_identity
        children = receipt.extrusion.GetChildren()
        if children is not None and type(children) not in (list, tuple):
            raise ExecutionFailure('construction_restore_unsafe', 'A complete native child inventory is required.', uncertain=True)
        if (any(token == old for old, _ in receipt.baseline_features)
                or not any(self.identity(f) == token for f in features)
                or children):
            raise rejected('construction_restore_unsafe', 'Baseline or dependent features cannot be deleted.')
        with self._base_selection(model, receipt):
            if not receipt.extrusion.Select2(False, 0):
                raise rejected('construction_restore_unsafe', 'Exact owned extrusion selection failed.')
            receipt.restore_attempted = True
            # No delete-absorbed-sketch flag: this sketch belongs to the baseline.
            if self._rectangle_native_step(receipt, 'restore_delete_extrusion', self._extension(model).DeleteSelection2, 0) is not True:
                raise ExecutionFailure('construction_restore_unconfirmed', 'Deletion effect is unconfirmed.', uncertain=True)
            if self._rectangle_native_step(receipt, 'restore_rebuild', self.rebuild_dimension_document, model) is not True:
                raise ExecutionFailure('construction_restore_unconfirmed', 'Restoration rebuild is unconfirmed.', uncertain=True)
        remaining = self.features(model)
        if (any(self.identity(f) == token for f in remaining)
                or not any(self.identity(f) == receipt.borrowed_sketch_identity for f in remaining)
                or self.bodies(model, 'all')
                or self.sketch_snapshot(model, receipt.borrowed_sketch)[0] != receipt.borrowed_sketch_snapshot
                or self.part_creation_controls(model) != receipt.controls):
            raise ExecutionFailure('construction_restore_unconfirmed', 'The full baseline sketch was not restored.', uncertain=True)
        receipt.restored = True
