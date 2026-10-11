"""Native passive resolved-instance reads; no resolution/activation/selection."""
import math
import pythoncom
from win32com.client import VARIANT
from . import binding
from .documents import rejected


def component_transform(values):
    if (values is None or len(values) != 16 or any(type(v) not in (float,int) or not math.isfinite(v) for v in values)):
        raise rejected('component_transform_unavailable', 'Expected a finite 16-value native transform.')
    axes = [list(values[i:i+3]) for i in (0,3,6)]
    if abs(values[12]-1.) > 1e-10 or any(abs(v) > 1e-10 for v in values[13:]):
        raise rejected('unsupported_component_transform', 'Scaled/nonstandard transforms outside this scope.')
    for i in range(3):
        for j in range(3):
            if abs(sum(axes[i][k]*axes[j][k] for k in range(3))-(1. if i == j else 0.)) > 1e-10:
                raise rejected('unsupported_component_transform', 'Component axes must be orthonormal.')
    a,b,c = axes
    det = sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3))
    return dict(origin_mm=[float(x)*1000. for x in values[9:12]], axes_in_assembly=axes,
                parity='right_handed' if det > 0. else 'mirrored', scale=1., includes_presentation_transform=False)


class CadComponentsMixin:
    def component_axis_distance(self, model, component, ends_m, direction):
        # All proxies, including the temporary wire, are created/released on STA.
        modeler = curve = trimmed = wire = edge = None
        try:
            modeler = binding.wrap(self._sw.GetModeler(), self._module.IModeler)
            curve = binding.wrap(modeler.CreateLine(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, ends_m[0]),
                VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, direction)), self._module.ICurve)
            if curve is None or curve.IsLine() is not True:
                raise rejected('temporary_axis_unavailable', 'Modeler did not create a native line.')
            trimmed = binding.wrap(curve.CreateTrimmedCurve2(*ends_m[0], *ends_m[1]), self._module.ICurve)
            if trimmed is None or trimmed.IsLine() is not True:
                raise rejected('temporary_axis_unavailable', 'Native line trimming failed.')
            wire = binding.wrap(trimmed.CreateWireBody(), self._module.IBody2)
            if wire is None or wire.IsTemporaryBody() is not True or wire.GetType() != 2:
                raise rejected('temporary_axis_unavailable', 'Expected a temporary wire body only.')
            edges = tuple(wire.GetEdges() or ())
            if len(edges) != 1:raise rejected('temporary_axis_unavailable', 'Expected one bounded line edge.')
            edge = binding.wrap(edges[0], self._module.IEdge)
            vertices = [binding.wrap(v, self._module.IVertex) for v in (edge.GetStartVertex(), edge.GetEndVertex())]
            from .point_measurement import point3
            actual = [point3(v.GetPoint(), 'temporary_axis_unavailable') if v is not None else None for v in vertices]
            if any(p is None for p in actual) or not any(all(math.dist(a, b) <= 1e-8 for a, b in zip(actual, order)) for order in (ends_m, list(reversed(ends_m)))):
                raise rejected('temporary_axis_unavailable', 'Native temporary edge endpoints disagree with the certified span.')
            return model.ClosestDistance(component, edge)
        finally:
            edge = wire = trimmed = curve = modeler = None

    def face_closest_point(self, face, point_m):
        return face.GetClosestPointOn(*point_m)

    def body_point_rays(self, model, body, point_m):
        from .point_measurement import RAY_DIRECTIONS, MAX_RAY_HITS, BOUNDARY_TOLERANCE_M
        extension = binding.wrap(model.Extension, self._module.IModelDocExtension)
        count = extension.RayIntersections(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [body]),
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(point_m)*3),
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [x for axis in RAY_DIRECTIONS for x in axis]),
            5, 0., BOUNDARY_TOLERANCE_M, True)  # NORMALS=1 | ENTRY_EXIT=4; high precision, no UNBLOCK/UI pumping.
        values = model.GetRayIntersectionsPoints() if type(count) is int and 0 < count <= MAX_RAY_HITS else None
        return count, values

    def component_distance(self, model, first, second):
        # Early-bound out variants return (distance_m, point_a_m, point_b_m).
        # Passing components lets SolidWorks apply their full instance transforms.
        return model.ClosestDistance(first, second)

    def components(self, model):
        asm = binding.wrap(model, self._module.IAssemblyDoc)
        return [binding.wrap(c,self._module.IComponent2) for c in asm.GetComponents(False) or ()]

    def component_parent(self, component):
        raw = component.GetParent()
        if raw is None:return None
        parent = binding.wrap(raw,self._module.IComponent2)
        return None if parent.IsRoot() else parent

    def component_info(self, component):
        state = component.GetSuppression2()
        if type(state) is not int or state not in (2,3):
            raise rejected('component_not_resolved', f'Resolved instances only; native suppression state {state}. No automatic resolution.')
        raw = component.GetModelDoc2()
        if raw is None:raise rejected('component_model_unavailable', 'Referenced model unavailable; no implicit load.')
        model = binding.wrap(raw,self._module.IModelDoc2)
        if self.pending_rebuild(model):
            raise rejected('component_needs_rebuild', 'Referenced model needs an explicit rebuild; no implicit rebuild.')
        kind = {1:'part',2:'assembly'}.get(model.GetType())
        if kind is None or component.IsSpeedPak is not False:
            raise rejected('unsupported_component_type', 'Native parts/assemblies only; SpeedPak outside scope.')
        configuration = str(component.ReferencedConfiguration)
        if not configuration:raise rejected('component_configuration_unavailable','Referenced configuration unavailable.')
        cfg_identity = self.configuration_identity(model,configuration)
        raw_transform = component.GetTotalTransform(False)
        if raw_transform is None:raise rejected('component_transform_unavailable','Native assembly transform unavailable.')
        transform = binding.wrap(raw_transform,self._module.IMathTransform)
        info = dict(component_path=str(component.Name2), referenced_path=str(component.GetPathName()),
                    referenced_configuration=configuration, referenced_document_type=kind,
                    suppression_state='resolved', native_suppression_state=state,
                    hidden=bool(component.IsHidden(False)), transform=component_transform(transform.ArrayData))
        if not info['component_path']:raise rejected('component_path_unavailable','Native instance path unavailable.')
        return info,(self.identity(model),cfg_identity)

    def component_bodies(self, component):
        result = component.GetBodies3(-1)
        if type(result) is not tuple or len(result) != 2:
            raise rejected('component_bodies_unavailable','Native body list/info result unavailable.')
        raw,info = result
        bodies,states = tuple(raw or ()),tuple(info or ())
        if len(bodies) != len(states) or any(type(x) is not int or x != 1 for x in states):
            raise rejected('unsupported_component_bodies','Only normal native bodies; assembly-cut user bodies need separate acceptance.')
        result = [binding.wrap(b,self._module.IBody2) for b in bodies]
        for b in result:self.measurement_body_type(b)
        return result
