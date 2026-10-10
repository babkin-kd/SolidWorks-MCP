"""Owning-STA single-edge native fillet; exact handle and persistent body proof."""

from dataclasses import dataclass
import math

from . import binding
from .cad_part_cut import NativeCutReceipt
from .documents import rejected
from .jobs import ExecutionFailure


@dataclass
class NativeFilletReceipt(NativeCutReceipt):
    fillet:object=None
    fillet_identity:object=None
    edge:object=None
    edge_pid:bytes=b''
    body_pid:bytes=b''


class CadPartFilletMixin:
    @staticmethod
    def _fillet_scalars(data):
        return dict(type=int(data.Type),radius_m=float(data.DefaultRadius),edge_count=int(data.GetEdgeCount()),
            items_count=int(data.FilletItemsCount),feature_count=int(data.GetFeatureCount()),loop_count=int(data.GetLoopCount()),
            hold_line_count=int(data.GetHoldLineCount()),multiple_radius=bool(data.IsMultipleRadius),
            propagate=bool(data.PropagateToTangentFaces),partial=bool(data.EnablePartialEdgeParameters),
            asymmetric=bool(data.AsymmetricFillet),curvature_continuous=bool(data.CurvatureContinuous),
            conic_type=int(data.ConicTypeForCrossSectionProfile))

    def edge_fillet_parameters(self,model,receipt):
        self._base_target(model,receipt)
        if receipt.restored or receipt.fillet is None:return None
        data=binding.wrap(receipt.fillet.GetDefinition(),self._module.ISimpleFilletFeatureData2)
        if data is None:raise rejected('fillet_definition_unavailable','Native simple fillet definition is unavailable.')
        return self._fillet_scalars(data)

    def new_edge_fillet_receipt(self,model,features,controls,edge):
        base=self.new_corner_cut_receipt(model,features,controls)
        return NativeFilletReceipt(base.model_identity,base.configuration_identity,base.baseline_features,base.controls,
            baseline_body_identity=base.baseline_body_identity,baseline_body_name=base.baseline_body_name,
            edge=edge,edge_pid=self.persistent_id(model,edge))

    def create_edge_fillet(self,model,definition,receipt):
        self._base_target(model,receipt)
        if self.part_creation_controls(model)!=receipt.controls:raise rejected('fillet_controls_changed','Prepared sketch controls changed.')
        bodies=self.bodies(model,'all')
        if len(bodies)!=1 or self.identity(bodies[0])!=receipt.baseline_body_identity:
            raise rejected('fillet_body_changed','Exact prepared single body changed.')
        with self._base_selection(model,receipt):
            entity=binding.wrap(receipt.edge,self._module.IEntity)
            manager=binding.wrap(model.SelectionManager,self._module.ISelectionMgr)
            selection=binding.wrap(manager.CreateSelectData(),self._module.ISelectData);selection.Mark=1
            if not entity.Select4(False,selection):raise rejected('fillet_selection_failed','Explicit native edge could not be selected.')
            factory=binding.wrap(model.FeatureManager,self._module.IFeatureManager)
            receipt.pending_creation=True
            # Uniform radius, simple edge fillet, no tangent propagation. Native
            # 2023 IFeatureManager signature: seven scalars and seven arrays.
            raw=factory.FeatureFillet3(2,definition.radius_mm/1000.,0.,0.,0,0,0,None,None,None,None,None,None,None)
            fillet=self._retain_base_feature(model,receipt,'fillet',raw)
            if fillet.GetTypeName2()!='Fillet':raise rejected('fillet_native_type_mismatch','Exact returned feature is not a native fillet.')
            fillet.Name=definition.feature_name
            if fillet.Name!=definition.feature_name:raise rejected('fillet_name_mismatch','Requested Russian tree name was not retained.')
            if not self.rebuild_dimension_document(model):raise rejected('fillet_rebuild_failed','Native fillet rebuild failed.')
            bodies=self.bodies(model,'all')
            if len(bodies)!=1 or bodies[0].GetType()!=0:raise rejected('fillet_body_scope_mismatch','Exactly one resulting solid is required.')
            receipt.body,receipt.body_identity=bodies[0],self.identity(bodies[0])
            receipt.body_pid=self.persistent_id(model,receipt.body)
            if not receipt.body_pid or self.identity(self.resolve_persistent_id(model,receipt.body_pid,'body'))!=receipt.body_identity:
                raise rejected('fillet_body_reference_unavailable','Resulting body requires a verified persistent reference.')
            if str(receipt.body.Name)!=receipt.baseline_body_name:raise rejected('fillet_body_name_changed','Original body display name changed.')

    def edge_fillet_evidence(self,model,receipt):
        self._base_target(model,receipt)
        if receipt.pending_creation or receipt.selection_uncertain:
            raise ExecutionFailure('fillet_effect_unconfirmed','Creation/access outcome remains unknown.',uncertain=True)
        if receipt.restored:return dict(restored=True,complete=False)
        if receipt.fillet is None:return dict(restored=False,complete=False,controls=self.part_creation_controls(model))
        if not any(self.identity(f)==receipt.fillet_identity for f in self.features(model)):
            raise rejected('fillet_owned_feature_not_current','Exact retained own fillet disappeared.')
        data=binding.wrap(receipt.fillet.GetDefinition(),self._module.ISimpleFilletFeatureData2)
        if data is None:raise rejected('fillet_definition_unavailable','Native simple fillet definition is unavailable.')
        # Access rolls back the fillet to its original selected edge. Only called
        # inside the checkpointed guard, once before final full body snapshots.
        with self._base_selection(model,receipt):
            try:accessed=data.AccessSelections(model,None)
            except BaseException as exc:
                receipt.selection_uncertain=True
                raise ExecutionFailure('fillet_access_unconfirmed','Selection access raised before confirmation.',uncertain=True) from exc
            if accessed is not True:
                receipt.selection_uncertain=True
                raise ExecutionFailure('fillet_access_unconfirmed','Selection access failed.',uncertain=True)
            try:
                edges=tuple(binding.wrap(e,self._module.IEdge) for e in data.Edges or ())
                pid=self.persistent_id(model,edges[0]) if len(edges)==1 and edges[0] is not None else b''
                parameters=dict(self._fillet_scalars(data),edge_matches=bool(pid) and self.same_persistent_id(model,pid,receipt.edge_pid))
            finally:
                try:data.ReleaseSelectionAccess()
                except BaseException:
                    receipt.selection_uncertain=True
                    raise
        self._base_target(model,receipt)
        bodies=self.bodies(model,'all')
        if len(bodies)!=1:raise rejected('fillet_owned_body_not_current','Exact resulting single body changed after selection access.')
        if receipt.body is not None:
            resolved=self.resolve_persistent_id(model,receipt.body_pid,'body');pid=self.persistent_id(model,bodies[0])
            if (not receipt.body_pid or not pid or self.identity(resolved)!=self.identity(bodies[0])
                    or not self.same_persistent_id(model,receipt.body_pid,pid)):
                raise rejected('fillet_owned_body_not_current','Persistent resulting body is not the exact current single body.')
            receipt.body,receipt.body_identity=bodies[0],self.identity(bodies[0])
        values=tuple(bodies[0].GetMassProperties(1.))
        if len(values)<5 or not all(math.isfinite(float(v)) and float(v)>0 for v in values[3:5]):
            raise rejected('fillet_mass_unavailable','Independent native volume/area are unavailable.')
        return dict(restored=False,complete=receipt.body is not None,fillet_native_id=int(receipt.fillet.GetID()),
            parameters=parameters,controls=self.part_creation_controls(model),body_name=str(bodies[0].Name),
            volume_mm3=float(values[3])*1e9,surface_area_mm2=float(values[4])*1e6)

    def restore_edge_fillet(self,model,receipt):
        self._base_target(model,receipt)
        if receipt.pending_creation or receipt.selection_uncertain:
            raise ExecutionFailure('fillet_restore_unsafe','Unknown creation/access prohibits deletion.',uncertain=True)
        if self.part_creation_controls(model)!=receipt.controls:raise rejected('fillet_restore_unsafe','Foreign controls prevent restoration.')
        if receipt.fillet is not None:
            token=receipt.fillet_identity
            if (any(token==old for old,_ in receipt.baseline_features) or not any(self.identity(f)==token for f in self.features(model))
                    or tuple(receipt.fillet.GetChildren() or ())):
                raise rejected('fillet_restore_unsafe','Only an own current fillet without dependent features may be deleted.')
            with self._base_selection(model,receipt):
                if not receipt.fillet.Select2(False,0) or not self._extension(model).DeleteSelection2(0):
                    raise rejected('fillet_restore_unsafe','Scoped own-fillet deletion failed.')
                if not self.rebuild_dimension_document(model):raise rejected('fillet_restore_unsafe','Restoration rebuild failed.')
            if any(self.identity(f)==token for f in self.features(model)):raise rejected('fillet_restore_unsafe','Own fillet survived deletion.')
        bodies=self.bodies(model,'all')
        if len(bodies)!=1 or str(bodies[0].Name)!=receipt.baseline_body_name or self.part_creation_controls(model)!=receipt.controls:
            raise rejected('fillet_restore_unsafe','Original single body and controls were not restored.')
        receipt.restored=True
