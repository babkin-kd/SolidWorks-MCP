"""Exact B3 public payload contracts; registration/normalization only, no CAD.

Mass calculation is a guarded mutation despite leaving model geometry intact.
Tuple/frame normalization mirrors public Pydantic inputs and the runtime's JSON
payload. These contracts do not claim that native B3 acceptance has passed.
"""
from dataclasses import dataclass

from pydantic import StrictFloat, TypeAdapter

from solidworks_mcp.measurement_frames import RigidMeasurementFrame
from verifier_lifecycle import ToolSpec


_VECTOR = TypeAdapter(tuple[StrictFloat, StrictFloat, StrictFloat])


@dataclass(frozen=True)
class B3ToolSpec(ToolSpec):
    vector_arguments: frozenset = frozenset()
    frame_arguments: frozenset = frozenset()

    def payload(self, arguments):
        normalized = {**self.argument_defaults, **arguments}
        for key in self.vector_arguments:
            if key in normalized:
                normalized[key] = list(_VECTOR.validate_python(normalized[key]))
        for key in self.frame_arguments:
            if key in normalized and normalized[key] is not None:
                normalized[key] = RigidMeasurementFrame.model_validate(normalized[key]).model_dump(mode='json')
        return super().payload(normalized)


SPECS = {
    'document_list': ToolSpec('document.list', False),
    'document_get': ToolSpec('document.get', False),
    'feature_list': ToolSpec('feature.list', False, argument_defaults={'limit': 100, 'cursor': ''}),
    'feature_get': ToolSpec('feature.get', False),
    'dimension_list': ToolSpec('dimension.list', False, argument_defaults={'limit': 100, 'cursor': ''}),
    'dimension_get': ToolSpec('dimension.get', False),
    'sketch_get': ToolSpec('sketch.get', False),
    'body_list': ToolSpec('geometry.list', False, argument_defaults={'body_type': 'all', 'limit': 100, 'cursor': ''},
                          constant_args={'kind': 'body'}),
    'face_list': ToolSpec('geometry.list', False, argument_defaults={'limit': 100, 'cursor': ''},
                          constant_args={'kind': 'face'}),
    'edge_list': ToolSpec('geometry.list', False, argument_defaults={'limit': 100, 'cursor': ''},
                          constant_args={'kind': 'edge'}),
    'geometry_get': ToolSpec('geometry.get', False),
    'component_list': ToolSpec('component.list', False, argument_defaults={'limit': 100, 'cursor': ''}),
    'component_get': ToolSpec('component.get', False),
    'component_body_list': ToolSpec('component.bodies', False, argument_defaults={'body_type': 'all'}),
    'component_body_get': ToolSpec('component.bodies', False),
    'component_face_list': ToolSpec('component.topology_list', False, argument_defaults={'limit': 100, 'cursor': ''},
                                    constant_args={'kind': 'face'}),
    'component_edge_list': ToolSpec('component.topology_list', False, argument_defaults={'limit': 100, 'cursor': ''},
                                    constant_args={'kind': 'edge'}),
    'component_topology_get': ToolSpec('component.topology_get', False),
    'measurement_prepare_mass': ToolSpec('measurement.prepare_mass', False, argument_defaults={'body_id': None}),
    'measurement_get_mass': ToolSpec('measurement.mass', True, argument_defaults={'body_id': None}),
    'measurement_get_bounds': B3ToolSpec('measurement.bounds', False,
        argument_defaults={'body_id': None, 'body_type': 'all', 'coordinate_frame': None},
        frame_arguments=frozenset({'coordinate_frame'})),
    'measurement_get_component_distance': ToolSpec('measurement.component_distance', False),
    'measurement_get_component_point_distance': B3ToolSpec('measurement.component_point_distance', False,
        argument_defaults={'frame': None}, vector_arguments=frozenset({'point_mm'}), frame_arguments=frozenset({'frame'})),
    'measurement_get_component_axis_distance': B3ToolSpec('measurement.component_axis_distance', False,
        argument_defaults={'frame': None}, vector_arguments=frozenset({'axis_origin_mm', 'axis_direction'}),
        frame_arguments=frozenset({'frame'})),
    'measurement_get_component_aggregate_distance': B3ToolSpec('measurement.component_aggregate_distance', False,
        argument_defaults={'frame': None}, frame_arguments=frozenset({'frame'})),
    'measurement_get_component_aggregate_point_distance': B3ToolSpec('measurement.component_aggregate_point_distance', False,
        argument_defaults={'frame': None}, vector_arguments=frozenset({'point_mm'}), frame_arguments=frozenset({'frame'})),
    'measurement_get_component_aggregate_axis_distance': B3ToolSpec('measurement.component_aggregate_axis_distance', False,
        argument_defaults={'frame': None}, vector_arguments=frozenset({'axis_origin_mm', 'axis_direction'}),
        frame_arguments=frozenset({'frame'})),
}
