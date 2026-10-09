"""Native part geometry reads; all calls and proxies stay in the owning STA."""

import pythoncom
import win32com.client

from . import binding
from .documents import rejected


class CadGeometryMixin:
    def _extension(self, model):
        return binding.wrap(model.Extension, self._module.IModelDocExtension)

    def pending_rebuild(self, model):
        return int(self._extension(model).NeedsRebuild2) != 0

    def configuration_identity(self, model, configuration):
        raw = model.GetConfigurationByName(configuration)
        if raw is None:
            raise rejected('configuration_not_found', 'Configuration no longer exists.')
        return self.identity(raw)

    @staticmethod
    def _persistent_variant(persistent_id):
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_UI1, tuple(persistent_id))

    def persistent_id(self, model, obj):
        raw = self._extension(model).GetPersistReference3(obj)
        return bytes(raw) if raw is not None else b''

    def same_persistent_id(self, model, left, right):
        # Internal byte representations can change across rebuilds. SolidWorks'
        # equality API returns swObjectSame=1; unsupported=2 is not equality.
        return self._extension(model).IsSamePersistentID(
            self._persistent_variant(left), self._persistent_variant(right)) == 1

    def resolve_persistent_id(self, model, persistent_id, kind):
        raw, status = self._extension(model).GetObjectByPersistReference3(self._persistent_variant(persistent_id))
        if status != 0 or raw is None:
            code = ('object_deleted' if status & 4 else 'object_suppressed' if status & 2 else 'object_reference_invalid')
            raise rejected(code, f'Native persistent reference is unavailable (state bitmask {status}).')
        cls = {'body': self._module.IBody2, 'face': self._module.IFace2, 'edge': self._module.IEdge}[kind]
        return binding.wrap(raw, cls)

    def bodies(self, model, body_type):
        part = binding.wrap(model, self._module.IPartDoc)
        code = {'all': -1, 'solid': 0, 'surface': 1}[body_type]
        return [binding.wrap(body, self._module.IBody2) for body in part.GetBodies2(code, False) or ()]

    def topology(self, body, kind):
        raw = body.GetFaces() if kind == 'face' else body.GetEdges()
        cls = self._module.IFace2 if kind == 'face' else self._module.IEdge
        return [binding.wrap(obj, cls) for obj in raw or ()]

    def owner_body(self, obj, kind):
        return binding.wrap(obj.GetBody(), self._module.IBody2)

    def body_is_current(self, model, body):
        identity = self.identity(body)
        return any(self.identity(candidate) == identity for candidate in self.bodies(model, 'all'))

    def topology_is_current(self, body, obj, kind):
        identity = self.identity(obj)
        return any(self.identity(candidate) == identity for candidate in self.topology(body, kind))

    def geometry_summary(self, obj, kind):
        if kind == 'body':
            body_type = {0: 'solid', 1: 'surface'}.get(obj.GetType())
            if body_type is None:
                raise rejected('unsupported_body_type', 'Only native solid and surface bodies are supported.')
            box = obj.GetBodyBox()
            if box is None or len(box) != 6:
                raise rejected('geometry_read_failed', 'SolidWorks did not provide a body bounding box.')
            return {'body_type': body_type, 'name': str(obj.Name),
                    'face_count': int(obj.GetFaceCount()), 'edge_count': int(obj.GetEdgeCount()),
                    'bounding_box_mm': {'min_mm': [float(v) * 1000 for v in box[:3]],
                                        'max_mm': [float(v) * 1000 for v in box[3:]], 'approximate': True}}
        if kind == 'face':
            surface = binding.wrap(obj.GetSurface(), self._module.ISurface)
            surface_type = 'other'
            if surface is not None:
                for method, label in [('IsPlane', 'plane'), ('IsCylinder', 'cylinder'), ('IsCone', 'cone'),
                                      ('IsSphere', 'sphere'), ('IsTorus', 'torus')]:
                    if getattr(surface, method)():
                        surface_type = label
                        break
            return {'area_mm2': float(obj.GetArea()) * 1000000,
                    'surface_type': surface_type, 'edge_count': len(obj.GetEdges() or ())}
        curve = binding.wrap(obj.GetCurve(), self._module.ICurve)
        parameters = obj.GetCurveParams2()
        if curve is None or parameters is None or len(parameters) < 8:
            raise rejected('unsupported_edge_geometry', 'Edge does not provide a measurable curve.')
        return {'curve_type': {3001: 'line', 3002: 'circle'}.get(curve.Identity(), 'other'),
                'length_mm': float(curve.GetLength3(parameters[6], parameters[7])) * 1000,
                'start_mm': [float(v) * 1000 for v in parameters[:3]],
                'end_mm': [float(v) * 1000 for v in parameters[3:6]]}
