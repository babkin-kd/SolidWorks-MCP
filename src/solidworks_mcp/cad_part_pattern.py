"""Owning-STA native LPattern with explicit seed/edge and retained own handle."""

from dataclasses import dataclass
import math

from . import binding
from .cad_part_cut import NativeCutReceipt
from .documents import rejected
from .jobs import ExecutionFailure


@dataclass
class NativePatternReceipt(NativeCutReceipt):
    pattern: object = None
    pattern_identity: object = None
    seed: object = None
    seed_identity: object = None
    direction: object = None
    direction_pid: bytes = b''
    reverse: bool = False
    body_pid: bytes = b''


class CadPartPatternMixin:
    @staticmethod
    def _linear_pattern_scalars(data):
        return dict(count=int(data.D1TotalInstances), spacing_m=float(data.D1Spacing),
            reverse=bool(data.D1ReverseDirection), end_condition=int(data.D1EndCondition),
            geometry_pattern=bool(data.GeometryPattern), vary_sketch=bool(data.VarySketch),
            body_pattern=bool(data.BodyPattern), direction_2=bool(data.IsDirection2Specified()),
            skipped_count=int(data.GetSkippedItemCount()), seed_count=int(data.GetPatternFeatureCount()))

    def linear_hole_pattern_parameters(self, model, receipt):
        self._base_target(model,receipt)
        if receipt.restored or receipt.pattern is None:
            return None
        data=binding.wrap(receipt.pattern.GetDefinition(),self._module.ILinearPatternFeatureData)
        if data is None:
            raise rejected('pattern_definition_unavailable','Native pattern definition is unavailable.')
        return self._linear_pattern_scalars(data)

    def pattern_edge_points(self, edge):
        curve = binding.wrap(edge.GetCurve(), self._module.ICurve)
        if curve is None or curve.IsLine() is not True:
            raise rejected('unsupported_pattern_axis', 'Direction requires an exact finite straight body edge.')
        points = []
        for raw in (edge.GetStartVertex(), edge.GetEndVertex()):
            vertex = binding.wrap(raw, self._module.IVertex)
            data = vertex.GetPoint() if vertex is not None else None
            if data is None or len(data) != 3 or not all(math.isfinite(float(value)) for value in data):
                raise rejected('unsupported_pattern_axis', 'Finite native edge endpoints are required.')
            points.append(tuple(float(value) for value in data))
        if points[0] == points[1]:
            raise rejected('unsupported_pattern_axis', 'A nonzero direction edge is required.')
        return tuple(points)

    def new_linear_hole_pattern_receipt(self, model, features, controls, seed, direction, reverse):
        base = self.new_corner_cut_receipt(model, features, controls)
        return NativePatternReceipt(base.model_identity, base.configuration_identity,
            base.baseline_features, base.controls, baseline_body_identity=base.baseline_body_identity,
            baseline_body_name=base.baseline_body_name, seed=seed, seed_identity=self.identity(seed),
            direction=direction, direction_pid=self.persistent_id(model, direction), reverse=reverse)

    def create_linear_hole_pattern(self, model, definition, receipt):
        self._base_target(model, receipt)
        if self.part_creation_controls(model) != receipt.controls:
            raise rejected('pattern_controls_changed', 'Prepared sketch controls changed.')
        bodies = self.bodies(model, 'all')
        if len(bodies) != 1 or self.identity(bodies[0]) != receipt.baseline_body_identity:
            raise rejected('pattern_body_changed', 'The exact prepared single body changed.')
        with self._base_selection(model, receipt):
            entity = binding.wrap(receipt.direction, self._module.IEntity)
            manager = binding.wrap(model.SelectionManager, self._module.ISelectionMgr)
            data = binding.wrap(manager.CreateSelectData(), self._module.ISelectData)
            data.Mark = 1
            if not entity.Select4(False, data) or not receipt.seed.Select2(True, 4):
                raise rejected('pattern_selection_failed', 'The explicit direction edge/seed could not be selected.')
            factory = binding.wrap(model.FeatureManager, self._module.IFeatureManager)
            receipt.pending_creation = True
            raw = factory.FeatureLinearPattern4(definition.count, definition.spacing_mm/1000.,
                1, 0., receipt.reverse, False, '', '', False, False,
                False, False, True, True, False, False, False, False, 0., 0.)
            pattern = self._retain_base_feature(model, receipt, 'pattern', raw)
            if pattern.GetTypeName2() != 'LPattern':
                raise rejected('pattern_native_type_mismatch', 'The exact returned feature is not a native linear pattern.')
            pattern.Name = definition.feature_name
            if pattern.Name != definition.feature_name:
                raise rejected('pattern_name_mismatch', 'The requested Russian name was not retained.')
            if not self.rebuild_dimension_document(model):
                raise rejected('pattern_rebuild_failed', 'Rebuild did not confirm the native pattern.')
            bodies = self.bodies(model, 'all')
            if len(bodies) != 1 or bodies[0].GetType() != 0:
                raise rejected('pattern_body_scope_mismatch', 'Exactly one resulting solid body is required.')
            receipt.body, receipt.body_identity = bodies[0], self.identity(bodies[0])
            receipt.body_pid = self.persistent_id(model, receipt.body)
            if not receipt.body_pid or self.identity(self.resolve_persistent_id(model,receipt.body_pid,'body'))!=receipt.body_identity:
                raise rejected('pattern_body_reference_unavailable','Exact created body has no verified persistent reference.')
            if str(receipt.body.Name) != receipt.baseline_body_name:
                raise rejected('pattern_body_name_changed', 'The original body display name changed.')

    def linear_hole_pattern_evidence(self, model, receipt):
        self._base_target(model, receipt)
        if receipt.pending_creation or receipt.selection_uncertain:
            raise ExecutionFailure('pattern_effect_unconfirmed', 'Creation/selection outcome remains unknown.', uncertain=True)
        if receipt.restored:
            return {'restored': True, 'complete': False}
        if receipt.pattern is None:
            return {'restored': False, 'complete': False, 'controls': self.part_creation_controls(model)}
        if not any(self.identity(item) == receipt.pattern_identity for item in self.features(model)):
            raise rejected('pattern_owned_feature_not_current', 'The exact retained pattern disappeared.')
        data = binding.wrap(receipt.pattern.GetDefinition(), self._module.ILinearPatternFeatureData)
        if data is None:
            raise rejected('pattern_definition_unavailable', 'Native pattern definition is unavailable.')
        # AccessSelections can roll back the feature. This method is called only
        # inside an already checkpointed mutation guard, never during prepare.
        with self._base_selection(model, receipt):
            try:
                accessed = data.AccessSelections(model, None)
            except BaseException as exc:
                receipt.selection_uncertain = True
                raise ExecutionFailure('pattern_access_unconfirmed','Pattern selection access raised before confirmation.',uncertain=True) from exc
            if accessed is not True:
                receipt.selection_uncertain = True
                raise ExecutionFailure('pattern_access_unconfirmed', 'Pattern selection access failed.', uncertain=True)
            try:
                axis = binding.wrap(data.D1Axis, self._module.IEdge)
                seeds = tuple(binding.wrap(raw, self._module.IFeature) for raw in data.PatternFeatureArray or ())
                axis_pid = self.persistent_id(model, axis) if axis is not None else b''
                result = dict(self._linear_pattern_scalars(data),
                    seed_matches=len(seeds)==1 and self.identity(seeds[0])==receipt.seed_identity,
                    axis_matches=bool(axis_pid) and self.same_persistent_id(model, axis_pid, receipt.direction_pid))
            finally:
                try:
                    data.ReleaseSelectionAccess()
                except BaseException:
                    receipt.selection_uncertain = True
                    raise
        self._base_target(model, receipt)
        bodies = self.bodies(model, 'all')
        if len(bodies)!=1:
            raise rejected('pattern_owned_body_not_current', 'Exact resulting single body changed after selection access.')
        if receipt.body is not None:
            # AccessSelections can replace the IBody2 wrapper when ending its
            # documented rollback. Prove the same persistent body against the
            # current native collection; name/index/mass are not identity.
            resolved=self.resolve_persistent_id(model,receipt.body_pid,'body')
            pid=self.persistent_id(model,bodies[0])
            if (not receipt.body_pid or not pid or self.identity(resolved)!=self.identity(bodies[0])
                    or not self.same_persistent_id(model,receipt.body_pid,pid)):
                raise rejected('pattern_owned_body_not_current','Persistent resulting body is not the exact current single body.')
            receipt.body,receipt.body_identity=bodies[0],self.identity(bodies[0])
        values = tuple(bodies[0].GetMassProperties(1.))
        if len(values)<5 or not all(math.isfinite(float(v)) and float(v)>0 for v in values[3:5]):
            raise rejected('pattern_mass_unavailable', 'Independent native volume/area are unavailable.')
        return {'restored':False, 'complete':receipt.body is not None,
            'pattern_native_id':int(receipt.pattern.GetID()), 'parameters':result,
            'controls':self.part_creation_controls(model), 'body_name':str(bodies[0].Name),
            'volume_mm3':float(values[3])*1e9, 'surface_area_mm2':float(values[4])*1e6}

    def restore_linear_hole_pattern(self, model, receipt):
        self._base_target(model, receipt)
        if receipt.pending_creation or receipt.selection_uncertain:
            raise ExecutionFailure('pattern_restore_unsafe', 'Unknown creation/access prohibits deletion.', uncertain=True)
        if self.part_creation_controls(model)!=receipt.controls:
            raise rejected('pattern_restore_unsafe', 'Foreign controls prevent restoration.')
        if receipt.pattern is not None:
            token = receipt.pattern_identity
            if (any(token==old for old,_ in receipt.baseline_features)
                    or not any(self.identity(item)==token for item in self.features(model))
                    or tuple(receipt.pattern.GetChildren() or ())):
                raise rejected('pattern_restore_unsafe', 'Only an own current pattern with no dependent features may be deleted.')
            with self._base_selection(model, receipt):
                # Flag zero deliberately preserves the baseline seed and sketches.
                if not receipt.pattern.Select2(False,0) or not self._extension(model).DeleteSelection2(0):
                    raise rejected('pattern_restore_unsafe', 'Scoped pattern deletion failed.')
                if not self.rebuild_dimension_document(model):
                    raise rejected('pattern_restore_unsafe', 'Restoration rebuild failed.')
            if any(self.identity(item)==token for item in self.features(model)):
                raise rejected('pattern_restore_unsafe', 'Own pattern survived deletion.')
        bodies = self.bodies(model,'all')
        if (len(bodies)!=1 or str(bodies[0].Name)!=receipt.baseline_body_name
                or self.part_creation_controls(model)!=receipt.controls):
            raise rejected('pattern_restore_unsafe', 'Original single body and controls were not restored.')
        receipt.restored = True
