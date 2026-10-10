"""Read-only exact FlatPattern fixed face for the working sheet-state domain."""

import math

from . import binding
from .documents import rejected


class CadSheetFlatReadMixin:
    def sheet_flat_fixed_face(self,model,flat,body):
        """No AccessSelections/rollback, suppression, rebuild or UI setters.

        Called within the domain's full paired capture. A name or a normal alone
        never establishes the target: body membership, current topology and the
        native face persistent-reference round trip are all required.
        """
        body_type=body.GetType()
        if (flat.GetTypeName2()!='FlatPattern' or type(body_type) is not int or body_type!=0 or body.IsSheetMetal() is not True
                or not self.body_is_current(model,body)):
            raise rejected('sheet_flat_target_unsupported','One current native sheet-metal body and exact FlatPattern are required.')
        members=[binding.wrap(raw,self._module.IFeature) for raw in body.GetFeatures() or ()]
        if sum(self.identity(item)==self.identity(flat) for item in members)!=1:
            raise rejected('sheet_flat_membership_changed','The explicit flat feature must belong uniquely to the current sheet body.')
        data=binding.wrap(flat.GetDefinition(),self._module.IFlatPatternFeatureData)
        if data is None:raise rejected('sheet_flat_definition_unavailable','The native flat definition is required.')
        face=binding.wrap(data.FixedFace2,self._module.IFace2)
        if face is None:raise rejected('sheet_fixed_face_unavailable','The native fixed face cannot be inferred from a body box.')
        pid=self.persistent_id(model,face)
        if not pid:raise rejected('sheet_fixed_face_unavailable','The native fixed face requires a strong persistent reference.')
        resolved=self.resolve_persistent_id(model,pid,'face')
        owner=binding.wrap(face.GetBody(),self._module.IBody2)
        if (self.identity(resolved)!=self.identity(face) or self.identity(owner)!=self.identity(body)
                or not self.topology_is_current(body,face,'face')
                or not self.same_persistent_id(model,pid,self.persistent_id(model,resolved))):
            raise rejected('sheet_fixed_face_changed','The exact current fixed face and persistent reference disagree.')
        surface=binding.wrap(face.GetSurface(),self._module.ISurface)
        if surface is None or surface.IsPlane() is not True:
            raise rejected('sheet_fixed_face_unsupported','The initial L-profile scope requires one complete native planar fixed face.')
        edges=[binding.wrap(raw,self._module.IEdge) for raw in face.GetEdges() or ()]
        if len(edges)!=4 or any(self.identity(edge)==self.identity(old) for i,edge in enumerate(edges) for old in edges[:i]):
            raise rejected('sheet_fixed_face_unsupported','Exactly four distinct fixed-face boundary edges are required.')
        vertices=[]
        for edge in edges:
            for raw in (edge.GetStartVertex(),edge.GetEndVertex()):
                vertex=binding.wrap(raw,self._module.IVertex)
                if vertex is None:raise rejected('sheet_fixed_face_unsupported','The fixed face must have finite straight boundary endpoints.')
                point=tuple(vertex.GetPoint())
                if len(point)!=3 or any(type(v) not in (float,int) or not math.isfinite(v) for v in point):
                    raise rejected('sheet_fixed_face_unsupported','Every exact fixed-face corner must be finite.')
                token=self.identity(vertex);prior=[p for identity,p in vertices if token==identity]
                if prior:
                    if prior!=[point]:raise rejected('sheet_fixed_face_changed','A retained fixed-face corner changed during collection.')
                else:
                    if any(point==p for _,p in vertices):raise rejected('sheet_fixed_face_unsupported','Distinct native corners cannot collapse.')
                    vertices.append((token,point))
        if len(vertices)!=4:raise rejected('sheet_fixed_face_unsupported','Four exact fixed-face corners are required.')
        parameters=surface.PlaneParams;parameters=parameters() if callable(parameters) else parameters
        parameters=list(parameters);sense=face.FaceInSurfaceSense()
        options={name:getattr(data,name) for name in ('MergeFace','SimplifyBends','ShowSlitInCornerRelief')}
        if (len(parameters)!=6 or any(type(v) not in (float,int) or not math.isfinite(v) for v in parameters)
                or type(sense) is not bool or any(type(v) is not bool for v in options.values())):
            raise rejected('sheet_flat_definition_unsupported','Complete finite native plane and unambiguous flat options are required.')
        return dict(face=dict(pid_hex=pid.hex(),vertices=[list(p) for p in sorted(p for _,p in vertices)],
            is_plane=True,plane_parameters=parameters,normal_opposes_surface=sense,owner_body_is_current=True),options=options)
