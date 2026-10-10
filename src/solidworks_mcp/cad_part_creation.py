"""Read-only native plane input for the internal base-part candidate."""

from . import binding
from .documents import rejected


class CadPartCreationMixin:
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
