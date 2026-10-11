"""Read-only native plane input for the internal base-part candidate."""

from dataclasses import dataclass, field
import math

from . import binding
from .constants import SW_FULLY_CONSTRAINED, SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from .documents import rejected
from .jobs import ExecutionFailure
from .timings_v2 import timed_call


@dataclass
class NativeBaseReceipt:
    """Exact handles retained only in the owning STA; never serialized to a job."""
    model_identity: object
    configuration_identity: object
    baseline_features: tuple
    controls: dict
    sketch: object = None
    native_sketch: object = None
    native_sketch_identity: object = None
    extrusion: object = None
    body: object = None
    sketch_identity: object = None
    extrusion_identity: object = None
    body_identity: object = None
    pending_creation: bool = False
    selection_uncertain: bool = False
    restored: bool = False
    deleted: list = field(default_factory=list)


class CadPartCreationMixin:
    def part_creation_controls(self, model):
        manager = binding.wrap(model.SketchManager, self._module.ISketchManager)
        return {'add_to_db': bool(manager.AddToDB), 'auto_solve': bool(manager.AutoSolve),
                'display_when_added': bool(manager.DisplayWhenAdded),
                'dimension_input': bool(self._sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE))}

    def reference_plane_transform(self, feature):
        if str(feature.GetTypeName2()) != 'RefPlane':
            raise rejected('invalid_reference_plane', 'A native RefPlane feature is required.')
        plane = binding.wrap(feature.GetSpecificFeature2(), self._module.IRefPlane)
        if plane is None:
            raise rejected('plane_transform_unavailable', 'The explicit feature has no native reference-plane interface.')
        transform = binding.wrap(plane.Transform, self._module.IMathTransform)
        if transform is None:
            raise rejected('plane_transform_unavailable', 'The explicit reference plane returned no transform.')
        data = transform.ArrayData
        if data is None:
            raise rejected('plane_transform_unavailable', 'The native reference-plane transform is unavailable.')
        return tuple(data)

    def new_base_receipt(self, model, features, controls):
        config = binding.wrap(model.GetActiveConfiguration(), self._module.IConfiguration)
        if self.bodies(model, 'all'):
            raise rejected('part_not_empty', 'The explicit part acquired bodies before construction.')
        return NativeBaseReceipt(self.identity(model), self.identity(config),
            tuple((self.identity(item), self.feature_summary(item)) for item in features), dict(controls))

    def _base_target(self, model, receipt):
        active = binding.wrap(self._sw.ActiveDoc, self._module.IModelDoc2)
        config = binding.wrap(model.GetActiveConfiguration(), self._module.IConfiguration)
        if (self.identity(model) != receipt.model_identity or active is None
                or self.identity(active) != receipt.model_identity
                or self.identity(config) != receipt.configuration_identity):
            raise rejected('construction_target_changed', 'Explicit construction document/configuration changed.')

    def _base_selection(self, model, receipt):
        from .cad_selection_scope import preserved_selection
        return preserved_selection(self, model, state=receipt, label='construction')

    def _retain_base_feature(self, model, receipt, name, raw):
        feature = binding.wrap(raw, self._module.IFeature)
        if feature is None:
            raise ExecutionFailure('construction_returned_no_handle', 'Native creation returned no owned handle.', uncertain=True)
        identity = self.identity(feature)
        if any(identity == token for token, _ in receipt.baseline_features):
            raise ExecutionFailure('construction_returned_existing_feature', 'Creation returned a baseline feature.', uncertain=True)
        # Retain before any naming, persistent-reference or subsequent CAD call.
        setattr(receipt, name, feature)
        setattr(receipt, name + '_identity', identity)
        receipt.pending_creation = False
        persistent = self.persistent_id(model, feature)
        if not persistent or self.identity(self.resolve_persistent_id(model, persistent, 'feature')) != identity:
            raise rejected('created_feature_reference_unavailable', 'The exact created feature has no verified persistent reference.')
        return feature

    def _feature_for_exact_sketch(self, model, sketch):
        """Resolve an exact returned ISketch through documented feature access.

        ISketch has no GetFeature method in SW2023. This is a canonical round-trip
        proof through IFeature.GetSpecificFeature2, never a name/tree-diff guess.
        """
        token = self.identity(sketch)
        matches = []
        for feature in self.features(model):
            if str(feature.GetTypeName2()) not in ('ProfileFeature', '3DProfileFeature'):
                continue
            specific = binding.wrap(feature.GetSpecificFeature2(), self._module.ISketch)
            if specific is not None and self.identity(specific) == token:
                matches.append(feature)
        if len(matches) != 1:
            raise rejected('construction_sketch_feature_unavailable', 'Exact native sketch has no unique matching feature interface.')
        return matches[0]

    def create_base_rectangle(self, model, plane, definition, receipt):
        self._base_target(model, receipt)
        if self.part_creation_controls(model) != receipt.controls:
            raise rejected('construction_controls_changed', 'Sketch controls changed before native construction.')
        manager = binding.wrap(model.SketchManager, self._module.ISketchManager)
        if manager.ActiveSketch is not None:
            raise rejected('part_not_writable', 'An unrelated sketch is active.')
        from .session import SolidWorksSession
        from .sketch_constraints import SketchDefiner
        with self._base_selection(model, receipt):
            if not plane.Select2(False, 0):
                raise rejected('construction_plane_select_failed', 'The exact plane could not be selected.')
            receipt.pending_creation = True
            timed_call('com', manager.InsertSketch, True)  # Native void, not cancellation on timeout.
            sketch = binding.wrap(manager.ActiveSketch, self._module.ISketch)
            if sketch is None:
                raise ExecutionFailure('construction_sketch_unconfirmed', 'Sketch creation returned no active sketch.', uncertain=True)
            receipt.native_sketch, receipt.native_sketch_identity = sketch, self.identity(sketch)
            sketch_feature = self._retain_base_feature(model, receipt, 'sketch', self._feature_for_exact_sketch(model, sketch))
            sketch_feature.Name = definition.sketch_name
            if sketch_feature.Name != definition.sketch_name:
                raise rejected('construction_name_mismatch', 'Created sketch did not retain its requested Russian name.')
            lines = SolidWorksSession._draw_polyline(manager, definition.profile_m)  # Stateless primitive only.
            names = {(axis, i): role for axis, role in (('x', 'Ширина'), ('y', 'Высота')) for i in range(8)}
            origins = [item for item in self.features(model) if item.GetTypeName2() == 'OriginProfileFeature']
            if len(origins) != 1:
                raise rejected('construction_origin_unavailable', 'The explicit model has no unique native origin feature.')
            points = binding.wrap(origins[0].GetSpecificFeature2(), self._module.ISketch).GetSketchPoints2()
            if points is None or len(points) != 1:
                raise rejected('construction_origin_unavailable', 'The explicit model has no unique native origin point.')
            self._base_target(model, receipt)
            definer = SketchDefiner(model, self._module, manager, sketch, binding.wrap(points[0], self._module.ISketchPoint))
            definer.define(lines, names=names, origin_mm=(0., 0.))
            if definer.fully_defined() is not True:
                raise rejected('construction_sketch_underdefined', 'Rectangle was not fully defined by native constraints.')
            self._base_target(model, receipt)
            current = binding.wrap(manager.ActiveSketch, self._module.ISketch)
            if current is None or self.identity(current) != receipt.native_sketch_identity:
                raise rejected('construction_sketch_changed', 'An unrelated sketch replaced the owned open sketch.')
            timed_call('com', manager.InsertSketch, True)
            if manager.ActiveSketch is not None:
                raise rejected('construction_sketch_close_failed', 'The exact owned sketch did not close.')
            if not sketch_feature.Select2(False, 0):
                raise rejected('construction_sketch_select_failed', 'Owned profile selection failed.')
            factory = binding.wrap(model.FeatureManager, self._module.IFeatureManager)
            receipt.pending_creation = True
            raw = timed_call('com', factory.FeatureExtrusion3, True, False, False, 0, 0, definition.depth_m, 0.,
                False, False, False, False, 0., 0., False, False, False, False,
                True, True, True, 0, 0., False)
            extrusion = self._retain_base_feature(model, receipt, 'extrusion', raw)
            extrusion.Name = definition.feature_name
            if extrusion.Name != definition.feature_name:
                raise rejected('construction_name_mismatch', 'Created extrusion did not retain its requested Russian name.')
            dimension = binding.wrap(extrusion.Parameter('D1'), self._module.IDimension)
            if dimension is None:
                raise rejected('construction_depth_dimension_unavailable', 'The exact extrusion has no native depth dimension.')
            dimension.Name = 'Толщина'
            if dimension.Name != 'Толщина':
                raise rejected('construction_name_mismatch', 'Created thickness dimension name was not retained.')
            if not self.rebuild_dimension_document(model):
                raise rejected('construction_rebuild_failed', 'Explicit construction rebuild did not finish.')
            bodies = self.bodies(model, 'all')
            if len(bodies) != 1 or bodies[0].GetType() != 0:
                raise rejected('construction_body_scope_mismatch', 'The new extrusion must create exactly one solid body.')
            receipt.body, receipt.body_identity = bodies[0], self.identity(bodies[0])
            bodies[0].Name = definition.body_name
            if bodies[0].Name != definition.body_name:
                raise rejected('construction_name_mismatch', 'Created body name was not retained.')
        if self.part_creation_controls(model) != receipt.controls:
            raise rejected('construction_controls_changed', 'Sketch controls were not restored after construction.')

    def base_rectangle_evidence(self, model, receipt):
        self._base_target(model, receipt)
        if receipt.restored:
            return {'restored': True, 'complete': False}
        if receipt.pending_creation or receipt.selection_uncertain:
            raise ExecutionFailure('construction_effect_unconfirmed', 'Native creation or selection outcome remains unknown.', uncertain=True)
        if receipt.sketch is None or receipt.extrusion is None or receipt.body is None:
            return {'complete': False, 'restored': False}
        features = self.features(model)
        if not all(any(self.identity(item) == token for item in features)
                   for token in (receipt.sketch_identity, receipt.extrusion_identity)):
            raise rejected('created_feature_not_current', 'An exact owned feature is no longer in the tree.')
        bodies = self.bodies(model, 'all')
        if len(bodies) != 1 or self.identity(bodies[0]) != receipt.body_identity:
            raise rejected('created_body_not_current', 'The exact new solid body no longer occupies the complete body scope.')
        sketch = binding.wrap(receipt.sketch.GetSpecificFeature2(), self._module.ISketch)
        values = tuple(receipt.body.GetMassProperties(1.))
        if len(values) < 5 or not all(math.isfinite(float(value)) and float(value) > 0 for value in values[3:5]):
            raise rejected('created_body_measurement_failed', 'Independent body volume/area is unavailable.')
        return {'complete': True, 'restored': False, 'fully_defined': sketch.GetConstrainedStatus() == SW_FULLY_CONSTRAINED,
                'sketch_native_id': int(receipt.sketch.GetID()), 'extrusion_native_id': int(receipt.extrusion.GetID()),
                'body_name': str(receipt.body.Name), 'volume_mm3': float(values[3]) * 1e9,
                'surface_area_mm2': float(values[4]) * 1e6, 'controls': self.part_creation_controls(model)}

    def restore_base_rectangle(self, model, receipt):
        self._base_target(model, receipt)
        if receipt.pending_creation or receipt.selection_uncertain:
            raise ExecutionFailure('construction_restore_unsafe', 'Unknown creation/selection cannot authorize deletion or replay.', uncertain=True)
        features = self.features(model)
        owned = [item for item in (receipt.extrusion, receipt.sketch) if item is not None]
        owned_tokens = [self.identity(item) for item in owned]
        if any(token == baseline for token in owned_tokens for baseline, _ in receipt.baseline_features):
            raise rejected('construction_restore_unsafe', 'Baseline features cannot be deleted.')
        for item in owned:
            if not any(self.identity(current) == self.identity(item) for current in features):
                raise rejected('construction_restore_unsafe', 'An owned handle disappeared; do not infer a replacement.')
            related = tuple(item.GetChildren() or ())
            if any(not any(self.identity(raw) == token for token in owned_tokens) for raw in related):
                raise rejected('construction_restore_unsafe', 'Unrelated dependent features prevent scoped restoration.')
        manager = binding.wrap(model.SketchManager, self._module.ISketchManager)
        with self._base_selection(model, receipt):
            active = binding.wrap(manager.ActiveSketch, self._module.ISketch)
            if active is not None:
                if receipt.native_sketch is None or self.identity(active) != receipt.native_sketch_identity:
                    raise rejected('construction_restore_unsafe', 'Never close an unrelated active sketch.')
                manager.InsertSketch(True)
                if manager.ActiveSketch is not None:
                    raise rejected('construction_restore_unsafe', 'Owned active sketch restoration failed.')
            target = receipt.extrusion or receipt.sketch
            if target is not None:
                if not target.Select2(False, 0):
                    raise rejected('construction_restore_unsafe', 'Exact owned feature selection failed.')
                # No delete-children flag. Absorbed sketch is exclusively ours.
                if not self._extension(model).DeleteSelection2(2 if receipt.extrusion is not None else 0):
                    raise rejected('construction_restore_unsafe', 'Native deletion of owned features failed.')
            for key, attribute in (('add_to_db', 'AddToDB'), ('auto_solve', 'AutoSolve'), ('display_when_added', 'DisplayWhenAdded')):
                if bool(getattr(manager, attribute)) != receipt.controls[key]:
                    setattr(manager, attribute, receipt.controls[key])
            if not self.rebuild_dimension_document(model):
                raise rejected('construction_restore_unsafe', 'Scoped restoration rebuild failed.')
        remaining = self.features(model)
        if any(any(self.identity(item) == token for token in owned_tokens) for item in remaining):
            raise rejected('construction_restore_unsafe', 'An owned feature remained after scoped deletion.')
        if self.bodies(model, 'all') or self.part_creation_controls(model) != receipt.controls:
            raise rejected('construction_restore_unsafe', 'Empty geometry or original controls were not restored.')
        receipt.restored = True
