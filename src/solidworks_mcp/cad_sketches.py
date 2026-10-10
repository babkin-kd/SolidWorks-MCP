"""Native sketch reader; every proxy/membership remains on the owning STA."""

import math

from . import binding
from .documents import rejected
from .linear_sketch import LinearSketchReader, SketchEntityBinder, _coordinates


class CadSketchesMixin:
    def rectangle_body_measurements(self, model):
        bodies = self.bodies(model, 'all')
        if len(bodies) != 1 or bodies[0].GetType() != 0:
            raise rejected('sketch_body_measurements_unavailable', 'One exact current solid body is required.')
        values = bodies[0].GetMassProperties(1.)
        if (type(values) not in (list, tuple) or len(values) != 12
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in values)
                or values[3] <= 0 or values[4] <= 0):
            raise rejected('sketch_body_measurements_unavailable', 'Complete finite native body measures are required.')
        return {'volume_mm3': values[3]*1e9, 'surface_area_mm2': values[4]*1e6}

    def sketch_snapshot(self, model, feature):
        if feature.GetTypeName2() != 'ProfileFeature':
            raise rejected('sketch_type_unsupported', 'The initial reader supports explicit planar profile features only.')
        sketch = binding.wrap(feature.GetSpecificFeature2(), self._module.ISketch)
        if sketch is None:
            raise rejected('sketch_unavailable', 'The explicit feature returned no native sketch.')
        raw_plane, kind = sketch.GetReferenceEntity(0)
        if type(kind) is not int or kind != 4 or raw_plane is None:
            raise rejected('sketch_reference_unsupported', 'The initial reader requires an explicit native reference plane.')
        objects = self.features(model)
        # GetReferenceEntity can expose another native interface identity for
        # the same plane. Bind its persistent reference to the exact current
        # IFeature; comparing these different proxy identities is insufficient.
        plane_pid = self.persistent_id(model, raw_plane)
        planes = [item for item in objects if item.GetTypeName2() == 'RefPlane'
                  and plane_pid and self.persistent_id(model, item) == plane_pid]
        origins = [item for item in objects if item.GetTypeName2() == 'OriginProfileFeature']
        if len(planes) != 1 or len(origins) != 1:
            raise rejected('sketch_reference_unsupported', 'The exact reference plane and model origin must be unique current features.')
        origin_sketch = binding.wrap(origins[0].GetSpecificFeature2(), self._module.ISketch)
        points = origin_sketch.GetSketchPoints2() or ()
        if len(points) != 1:
            raise rejected('sketch_origin_unavailable', 'The explicit model has no unique native origin point.')
        plane, origin = planes[0], origins[0]
        references = []
        for item in (feature, plane, origin):
            pid = self.persistent_id(model, item)
            if not pid or self.identity(self.resolve_persistent_id(model, pid, 'feature')) != self.identity(item):
                raise rejected('sketch_reference_unsupported', 'Sketch/plane/origin persistent reference did not round-trip.')
            references.append(pid.hex())
        def resolve(pid, name):
            raw, status = self._extension(model).GetObjectByPersistReference3(self._persistent_variant(pid))
            if type(status) is not int or status != 0 or raw is None:
                raise rejected('sketch_entity_reference_unavailable', 'Current sketch entity reference is unavailable/suppressed/deleted.')
            return binding.wrap(raw, getattr(self._module, name))
        binder = SketchEntityBinder(wrap=lambda raw,name:binding.wrap(raw,getattr(self._module,name)),
            reference=lambda obj:self.persistent_id(model,obj),resolve=resolve,identity=self.identity,coalesce=True)
        reader = LinearSketchReader(sketch, binder(points[0], 'ISketchPoint'), identity=self.identity, wrap=binder)
        snapshot, members = reader.read()
        binder.close()
        transform = binding.wrap(sketch.ModelToSketchTransform, self._module.IMathTransform)
        if transform is None:
            raise rejected('sketch_transform_unavailable', 'Complete native model-to-sketch transform is required.')
        snapshot.update(feature_native_id=int(feature.GetID()), feature_pid_hex=references[0],
            model_to_sketch=_coordinates(transform.ArrayData, 16),
            reference_plane={'native_id': int(plane.GetID()), 'pid_hex': references[1],
                'transform': _coordinates(self.reference_plane_transform(plane), 16)},
            model_origin={'feature_native_id': int(origin.GetID()), 'pid_hex': references[2]})
        snapshot['entity_references'] = sorted(({'kind':kind,'pid_hex':pid.hex()} for kind,pid in binder.bound),
            key=lambda row:(row['kind'],row['pid_hex']))
        return snapshot, members + (('feature', self.identity(feature)), ('plane', self.identity(plane)), ('origin_feature', self.identity(origin)))
