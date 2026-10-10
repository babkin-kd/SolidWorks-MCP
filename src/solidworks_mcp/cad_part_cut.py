"""Owning-STA rectangular through cut with exact retained creation handles."""

from dataclasses import dataclass
import math

from . import binding
from .cad_part_creation import NativeBaseReceipt
from .constants import SW_FULLY_CONSTRAINED
from .documents import rejected
from .jobs import ExecutionFailure


@dataclass
class NativeCutReceipt(NativeBaseReceipt):
    cut: object = None
    cut_identity: object = None
    baseline_body_identity: object = None
    baseline_body_name: str = ''


class CadPartCutMixin:
    def new_corner_cut_receipt(self, model, features, controls):
        config = binding.wrap(model.GetActiveConfiguration(), self._module.IConfiguration)
        bodies = self.bodies(model, 'all')
        if len(bodies) != 1 or bodies[0].GetType() != 0:
            raise rejected('cut_body_scope_changed', 'Exactly one current solid base body is required.')
        return NativeCutReceipt(self.identity(model), self.identity(config),
            tuple((self.identity(item), self.feature_summary(item)) for item in features), dict(controls),
            baseline_body_identity=self.identity(bodies[0]), baseline_body_name=str(bodies[0].Name))

    def create_corner_cut(self, model, plane, definition, receipt):
        self._base_target(model, receipt)
        if self.part_creation_controls(model) != receipt.controls:
            raise rejected('cut_controls_changed', 'Native sketch controls changed before construction.')
        bodies = self.bodies(model, 'all')
        if len(bodies) != 1 or self.identity(bodies[0]) != receipt.baseline_body_identity:
            raise rejected('cut_body_scope_changed', 'The exact prepared base body changed before creation.')
        manager = binding.wrap(model.SketchManager, self._module.ISketchManager)
        if manager.ActiveSketch is not None:
            raise rejected('cut_open_sketch', 'An unrelated sketch is active.')
        from .session import SolidWorksSession
        from .sketch_constraints import SketchDefiner
        with self._base_selection(model, receipt):
            if not plane.Select2(False, 0):
                raise rejected('cut_plane_select_failed', 'The explicit current plane could not be selected.')
            receipt.pending_creation = True
            manager.InsertSketch(True)
            sketch = binding.wrap(manager.ActiveSketch, self._module.ISketch)
            if sketch is None:
                raise ExecutionFailure('cut_sketch_unconfirmed', 'No exact active sketch was returned.', uncertain=True)
            receipt.native_sketch, receipt.native_sketch_identity = sketch, self.identity(sketch)
            feature = self._retain_base_feature(model, receipt, 'sketch', self._feature_for_exact_sketch(model, sketch))
            feature.Name = definition.sketch_name
            if feature.Name != definition.sketch_name:
                raise rejected('cut_name_mismatch', 'The requested Russian sketch name was not retained.')
            w, h = definition.width_mm / 1000., definition.height_mm / 1000.
            lines = SolidWorksSession._draw_polyline(manager, ((0., 0.), (w, 0.), (w, h), (0., h)))
            origins = [item for item in self.features(model) if item.GetTypeName2() == 'OriginProfileFeature']
            if len(origins) != 1:
                raise rejected('cut_origin_unavailable', 'The exact unique model origin is unavailable.')
            points = binding.wrap(origins[0].GetSpecificFeature2(), self._module.ISketch).GetSketchPoints2()
            if points is None or len(points) != 1:
                raise rejected('cut_origin_unavailable', 'The exact unique native model-origin point is unavailable.')
            names = {(axis, index): name for axis, name in (('x', 'Ширина выреза'), ('y', 'Высота выреза'))
                     for index in range(8)}
            definer = SketchDefiner(model, self._module, manager, sketch,
                                   binding.wrap(points[0], self._module.ISketchPoint))
            definer.define(lines, names=names, origin_mm=(0., 0.))
            if definer.fully_defined() is not True:
                raise rejected('cut_sketch_underdefined', 'Native constraints did not fully define the rectangle.')
            self._base_target(model, receipt)
            active = binding.wrap(manager.ActiveSketch, self._module.ISketch)
            if active is None or self.identity(active) != receipt.native_sketch_identity:
                raise rejected('cut_sketch_changed', 'An unrelated active sketch replaced the owned sketch.')
            manager.InsertSketch(True)
            if manager.ActiveSketch is not None or not feature.Select2(False, 0):
                raise rejected('cut_profile_select_failed', 'The owned closed sketch could not be selected.')
            factory = binding.wrap(model.FeatureManager, self._module.IFeatureManager)
            receipt.pending_creation = True
            # Through all, along the same positive plane normal as the base.
            raw = factory.FeatureCut4(True, False, True, 1, 0, 0., 0.,
                False, False, False, False, 0., 0., False, False, False, False,
                False, True, True, False, False, False, 0, 0., False, False)
            cut = self._retain_base_feature(model, receipt, 'cut', raw)
            if cut.GetTypeName2() not in ('Cut', 'ICE') or cut.GetTypeName() != 'Cut':
                raise rejected('cut_native_type_mismatch', 'The exact returned feature is not a native extruded cut.')
            cut.Name = definition.feature_name
            if cut.Name != definition.feature_name:
                raise rejected('cut_name_mismatch', 'The requested Russian cut name was not retained.')
            if not self.rebuild_dimension_document(model):
                raise rejected('cut_rebuild_failed', 'Native rebuild did not confirm the through cut.')
            bodies = self.bodies(model, 'all')
            if len(bodies) != 1 or bodies[0].GetType() != 0:
                raise rejected('cut_body_scope_mismatch', 'The cut must leave exactly one solid body.')
            receipt.body, receipt.body_identity = bodies[0], self.identity(bodies[0])
            # Preserve the original body display name; do not rename a replacement.
            if str(bodies[0].Name) != receipt.baseline_body_name:
                raise rejected('cut_body_name_changed', 'The native cut changed the original body display name.')
        if self.part_creation_controls(model) != receipt.controls:
            raise rejected('cut_controls_changed', 'Original sketch controls were not preserved.')

    def corner_cut_evidence(self, model, receipt):
        self._base_target(model, receipt)
        if receipt.pending_creation or receipt.selection_uncertain:
            raise ExecutionFailure('cut_effect_unconfirmed', 'Native creation/selection remains unconfirmed.', uncertain=True)
        if receipt.restored:
            return {'restored': True, 'complete': False}, ()
        features = self.features(model)
        for feature, token in ((receipt.sketch, receipt.sketch_identity), (receipt.cut, receipt.cut_identity)):
            if feature is not None and not any(self.identity(item) == token for item in features):
                raise rejected('cut_owned_feature_not_current', 'An exact retained feature disappeared.')
        if receipt.sketch is None:
            return {'restored': False, 'complete': False}, ()
        snapshot, members = self.sketch_snapshot(model, receipt.sketch)
        complete = receipt.cut is not None and receipt.body is not None
        result = {'restored': False, 'complete': complete,
                  'sketch_native_id': int(receipt.sketch.GetID()),
                  'cut_native_id': int(receipt.cut.GetID()) if receipt.cut is not None else None,
                  'cut_type_name2': str(receipt.cut.GetTypeName2()) if receipt.cut is not None else None,
                  'cut_type_name': str(receipt.cut.GetTypeName()) if receipt.cut is not None else None,
                  'sketch': snapshot, 'controls': self.part_creation_controls(model),
                  'fully_defined': snapshot['constraint_status'] == SW_FULLY_CONSTRAINED}
        if complete:
            bodies = self.bodies(model, 'all')
            if len(bodies) != 1 or self.identity(bodies[0]) != receipt.body_identity:
                raise rejected('cut_owned_body_not_current', 'The exact resulting body is no longer current.')
            values = tuple(receipt.body.GetMassProperties(1.))
            if len(values) < 5 or not all(math.isfinite(float(v)) and float(v) > 0 for v in values[3:5]):
                raise rejected('cut_mass_unavailable', 'Independent native volume and area are unavailable.')
            result.update(body_name=str(receipt.body.Name), volume_mm3=float(values[3]) * 1e9,
                          surface_area_mm2=float(values[4]) * 1e6)
        return result, members

    def restore_corner_cut(self, model, receipt):
        self._base_target(model, receipt)
        if receipt.pending_creation or receipt.selection_uncertain:
            raise ExecutionFailure('cut_restore_unsafe', 'Unknown creation/selection does not authorize deletion.', uncertain=True)
        if self.part_creation_controls(model) != receipt.controls:
            raise rejected('cut_restore_unsafe', 'Foreign control changes prevent scoped restoration.')
        owned = [item for item in (receipt.cut, receipt.sketch) if item is not None]
        tokens = [self.identity(item) for item in owned]
        features = self.features(model)
        for feature in owned:
            token = self.identity(feature)
            if (any(token == baseline for baseline, _ in receipt.baseline_features)
                    or not any(self.identity(item) == token for item in features)):
                raise rejected('cut_restore_unsafe', 'Only exact current non-baseline handles may be deleted.')
            if any(not any(self.identity(raw) == own for own in tokens) for raw in tuple(feature.GetChildren() or ())):
                raise rejected('cut_restore_unsafe', 'Foreign dependent features prevent deletion of the owned cut.')
        manager = binding.wrap(model.SketchManager, self._module.ISketchManager)
        with self._base_selection(model, receipt):
            active = binding.wrap(manager.ActiveSketch, self._module.ISketch)
            if active is not None:
                if self.identity(active) != receipt.native_sketch_identity:
                    raise rejected('cut_restore_unsafe', 'Never close an unrelated sketch.')
                manager.InsertSketch(True)
                if manager.ActiveSketch is not None:
                    raise rejected('cut_restore_unsafe', 'Owned sketch did not close.')
            target = receipt.cut or receipt.sketch
            if target is not None:
                if not target.Select2(False, 0) or not self._extension(model).DeleteSelection2(2 if receipt.cut else 0):
                    raise rejected('cut_restore_unsafe', 'Scoped native deletion failed.')
            if not self.rebuild_dimension_document(model):
                raise rejected('cut_restore_unsafe', 'Restoration rebuild failed.')
        remaining = self.features(model)
        if any(any(self.identity(item) == token for token in tokens) for item in remaining):
            raise rejected('cut_restore_unsafe', 'An owned feature survived deletion.')
        bodies = self.bodies(model, 'all')
        if (len(bodies) != 1 or str(bodies[0].Name) != receipt.baseline_body_name
                or self.part_creation_controls(model) != receipt.controls):
            raise rejected('cut_restore_unsafe', 'Original single body and controls were not restored.')
        receipt.restored = True
