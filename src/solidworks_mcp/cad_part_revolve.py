"""Exact owning-STA full-turn revolve candidate; retained handles authorize cleanup."""

from dataclasses import dataclass
import math

from . import binding
from .cad_part_creation import NativeBaseReceipt
from .documents import rejected
from .jobs import ExecutionFailure


@dataclass
class NativeRevolveReceipt(NativeBaseReceipt):
    # The inherited extrusion slot is the exact owned base-operation handle,
    # reused by scoped base restoration. It is never inferred from a tree/name.
    axis_segment: object = None
    axis_identity: object = None
    axis_pid: bytes = b''
    axis_height_m: float = 0.


class CadPartRevolveMixin:
    def _bind_revolve_segment(self, model, raw):
        """Prove alternate drawing/selection interfaces through a fresh native reference."""
        from .linear_sketch import SketchEntityBinder
        def resolve(pid,name):
            current,status = self._extension(model).GetObjectByPersistReference3(self._persistent_variant(pid))
            if type(status) is not int or status != 0 or current is None:
                raise rejected('revolve_axis_unavailable','The exact persistent segment is no longer current.')
            return binding.wrap(current,getattr(self._module,name))
        binder = SketchEntityBinder(wrap=lambda value,name:binding.wrap(value,getattr(self._module,name)),
            reference=lambda value:self.persistent_id(model,value),resolve=resolve,identity=self.identity,coalesce=True)
        segment = binder(raw,'ISketchSegment')
        binder.close()
        return segment

    def new_base_revolve_receipt(self, model, features, controls):
        baseline = self.new_base_receipt(model,features,controls)
        return NativeRevolveReceipt(baseline.model_identity,baseline.configuration_identity,
                                   baseline.baseline_features,baseline.controls)

    def _revolve_axis_current(self, model, receipt):
        if receipt.axis_segment is None or not receipt.axis_pid:
            raise rejected('revolve_axis_unavailable', 'No exact owned persistent axis was retained.')
        raw,status = self._extension(model).GetObjectByPersistReference3(self._persistent_variant(receipt.axis_pid))
        segment = binding.wrap(raw,self._module.ISketchSegment)
        if (type(status) is not int or status != 0 or segment is None
                or self.identity(segment) != receipt.axis_identity):
            raise rejected('revolve_axis_changed', 'The exact retained axis reference did not round-trip.')
        sketch = binding.wrap(segment.GetSketch(),self._module.ISketch)
        if sketch is None or self.identity(sketch) != receipt.native_sketch_identity:
            raise rejected('revolve_axis_changed', 'The axis must belong to the exact owned sketch.')
        kind = segment.GetType()
        if type(kind) is not int or kind != 0 or segment.ConstructionGeometry:
            raise rejected('revolve_axis_changed', 'The own y-axis must be a finite nonconstruction profile line.')
        line = binding.wrap(segment,self._module.ISketchLine)
        points = [binding.wrap(raw,self._module.ISketchPoint) for raw in (line.GetStartPoint2(),line.GetEndPoint2())]
        if any(point is None for point in points):
            raise rejected('revolve_axis_changed', 'Both exact axis endpoints must remain available.')
        actual = [(float(point.X),float(point.Y),float(point.Z)) for point in points]
        expected = [(0.,receipt.axis_height_m,0.),(0.,0.,0.)]
        if any(not math.isfinite(value) or abs(value-wanted) > 1e-12
               for point,reference in zip(actual,expected) for value,wanted in zip(point,reference)):
            raise rejected('revolve_axis_changed', 'The retained segment must be the own x=0 rectangle edge, in sketch metres.')
        return segment

    def create_base_revolve(self, model, plane, definition, receipt):
        self._base_target(model,receipt)
        if self.part_creation_controls(model) != receipt.controls or self.bodies(model,'all'):
            raise rejected('revolve_target_changed', 'Empty body scope and prepared native controls are required.')
        manager = binding.wrap(model.SketchManager,self._module.ISketchManager)
        if manager.ActiveSketch is not None:
            raise rejected('revolve_open_sketch', 'Never edit an unrelated active sketch.')
        from .session import SolidWorksSession
        from .sketch_constraints import SketchDefiner
        with self._base_selection(model,receipt):
            if not plane.Select2(False,0):
                raise rejected('revolve_plane_select_failed', 'The exact prepared plane could not be selected.')
            receipt.pending_creation = True
            manager.InsertSketch(True)
            sketch = binding.wrap(manager.ActiveSketch,self._module.ISketch)
            if sketch is None:
                raise ExecutionFailure('revolve_sketch_unconfirmed','Native creation returned no owned active sketch.',uncertain=True)
            receipt.native_sketch,receipt.native_sketch_identity = sketch,self.identity(sketch)
            feature = self._retain_base_feature(model,receipt,'sketch',self._feature_for_exact_sketch(model,sketch))
            feature.Name = definition.sketch_name
            if feature.Name != definition.sketch_name:
                raise rejected('revolve_name_mismatch','Requested Russian sketch name was not retained.')
            lines = SolidWorksSession._draw_polyline(manager,definition.profile_m)
            origins = [item for item in self.features(model) if item.GetTypeName2() == 'OriginProfileFeature']
            if len(origins) != 1:
                raise rejected('revolve_origin_unavailable','The exact unique native model origin is required.')
            points = binding.wrap(origins[0].GetSpecificFeature2(),self._module.ISketch).GetSketchPoints2()
            if points is None or len(points) != 1:
                raise rejected('revolve_origin_unavailable','The unique exact native model-origin point is required.')
            names = {(axis,index):name for axis,name in (('x','Радиус'),('y','Высота вращения')) for index in range(8)}
            definer = SketchDefiner(model,self._module,manager,sketch,binding.wrap(points[0],self._module.ISketchPoint))
            definer.define(lines,names=names,origin_mm=(0.,0.))
            if definer.fully_defined() is not True:
                raise rejected('revolve_underdefined','Native constraints must fully define the complete rectangular profile.')
            # Retain the exact returned x=0 profile edge; no first-axis, name or
            # coordinate selection. Its persistent reference closes ownership.
            receipt.axis_segment = self._bind_revolve_segment(model,lines[3])
            receipt.axis_identity = self.identity(receipt.axis_segment)
            receipt.axis_pid = self.persistent_id(model,receipt.axis_segment)
            receipt.axis_height_m = definition.height_mm/1000.
            self._revolve_axis_current(model,receipt)
            self._base_target(model,receipt)
            active = binding.wrap(manager.ActiveSketch,self._module.ISketch)
            if active is None or self.identity(active) != receipt.native_sketch_identity:
                raise rejected('revolve_sketch_changed','An unrelated sketch replaced the owned active sketch.')
            manager.InsertSketch(True)
            if manager.ActiveSketch is not None or not feature.Select2(False,0):
                raise rejected('revolve_profile_select_failed','The exact owned closed profile could not be selected.')
            selections = binding.wrap(model.SelectionManager,self._module.ISelectionMgr)
            data = binding.wrap(selections.CreateSelectData(),self._module.ISelectData)
            data.Mark = 4
            axis = self._revolve_axis_current(model,receipt)
            if not axis.Select4(True,data):
                raise rejected('revolve_axis_select_failed','Selection of the exact owned axis with mark 4 failed.')
            selected = self._bind_revolve_segment(model,selections.GetSelectedObject6(1,4))
            profile = binding.wrap(selections.GetSelectedObject6(1,0),self._module.IFeature)
            if (selections.GetSelectedObjectCount2(-1) != 2 or selections.GetSelectedObjectCount2(4) != 1
                    or selections.GetSelectedObjectCount2(0) != 1 or selected is None or profile is None
                    or self.identity(selected) != receipt.axis_identity or self.identity(profile) != receipt.sketch_identity):
                raise rejected('revolve_selection_mismatch','Only the exact own profile mark 0 and own axis mark 4 may be selected.')
            self._base_target(model,receipt)
            factory = binding.wrap(model.FeatureManager,self._module.IFeatureManager)
            receipt.pending_creation = True
            raw = factory.FeatureRevolve2(True,True,False,False,False,False,0,0,2.*math.pi,0.,
                                         False,False,0.,0.,0,0.,0.,True,False,False)
            revolution = self._retain_base_feature(model,receipt,'extrusion',raw)
            if revolution.GetTypeName2() != 'Revolution':
                raise rejected('revolve_native_type_mismatch','The exact returned feature must be a solid Revolution.')
            revolution.Name = definition.feature_name
            if revolution.Name != definition.feature_name:
                raise rejected('revolve_name_mismatch','Requested Russian revolve name was not retained.')
            angle = binding.wrap(revolution.Parameter('D1'),self._module.IDimension)
            if angle is None:
                raise rejected('revolve_angle_unavailable','The exact created revolve angle is unavailable.')
            angle.Name = 'Угол вращения'
            if angle.Name != 'Угол вращения':
                raise rejected('revolve_name_mismatch','Requested Russian angle name was not retained.')
            if not self.rebuild_dimension_document(model):
                raise rejected('revolve_rebuild_failed','The explicit native full-turn rebuild was not confirmed.')
            bodies = self.bodies(model,'all')
            if len(bodies) != 1 or bodies[0].GetType() != 0:
                raise rejected('revolve_body_scope_mismatch','The empty-part revolve must create exactly one solid body.')
            receipt.body,receipt.body_identity = bodies[0],self.identity(bodies[0])
            receipt.body.Name = definition.body_name
            if receipt.body.Name != definition.body_name:
                raise rejected('revolve_name_mismatch','Requested Russian body name was not retained.')
        if self.part_creation_controls(model) != receipt.controls:
            raise rejected('revolve_controls_changed','The original native sketch controls were not preserved.')

    def base_revolve_evidence(self, model, receipt):
        evidence = self.base_rectangle_evidence(model,receipt)
        if receipt.restored:
            return evidence,()
        if receipt.sketch is None:
            return {**evidence,'controls':self.part_creation_controls(model)},()
        snapshot,members = self.sketch_snapshot(model,receipt.sketch)
        evidence.update(sketch=snapshot,sketch_native_id=int(receipt.sketch.GetID()),
            revolution_native_id=int(receipt.extrusion.GetID()) if receipt.extrusion is not None else None,
            revolution_type=str(receipt.extrusion.GetTypeName2()) if receipt.extrusion is not None else None,
            controls=self.part_creation_controls(model),axis_verified=False)
        evidence.pop('extrusion_native_id',None)
        if receipt.axis_segment is not None:
            self._revolve_axis_current(model,receipt)
            evidence['axis_verified'] = True
        return evidence,members

    def restore_base_revolve(self, model, receipt):
        # Domain inspection proves baseline and all new state before this call.
        self.restore_base_rectangle(model,receipt)
