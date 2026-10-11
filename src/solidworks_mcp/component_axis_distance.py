"""Native instance-to-infinite-axis distance using a certified temporary edge."""
import math
from .component_distance import ComponentDistanceCatalog
from .measurement_frames import measurement_frame, project_point_m
from .point_measurement import point3, assembly_point_mm
from .axis_measurement import unit_direction, dot, anchor_axis, bracket_axis, check_axis_witnesses
from .documents import rejected


class ComponentAxisDistanceCatalog(ComponentDistanceCatalog):
    AXIS_SCOPE = 'resolved_part_component_axis_distance_v1'

    def _supports(self, bodies, transform, anchor, direction):
        local_direction = [dot(axis, direction) for axis in transform['axes_in_assembly']]
        result = []
        for ref, body, summary in bodies:
            if summary['body_type'] != 'solid':continue
            values = []
            for sign in (-1., 1.):
                local = point3(self.adapter.measurement_extreme_point(body, [sign*x for x in local_direction]), 'native_axis_support_unavailable')
                root = [x*.001 for x in assembly_point_mm(transform, local)]
                values.append(dot([x-a for x, a in zip(root, anchor)], direction))
            result.append(tuple(values))
        return tuple(result)

    def measure_axis(self, document_id, configuration, expected_observation_revision, component_id,
                     axis_origin_mm, axis_direction, *, frame=None):
        origin = point3(axis_origin_mm, 'invalid_measurement_axis');direction = unit_direction(axis_direction)
        explicit_frame = frame is not None;axes = measurement_frame(frame)
        root_origin = point3([axes.origin_mm[k]+sum(axes.axes_in_model[i][k]*origin[i] for i in range(3)) for k in range(3)], 'measurement_numeric_overflow')
        root_direction = unit_direction([sum(axes.axes_in_model[i][k]*direction[i] for i in range(3)) for k in range(3)])
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        rows = self._snapshot(entry, configuration, identity)
        component = self._resolve(entry, configuration, identity, component_id, rows)
        bodies, moments, solid_count = self._distance_bodies(entry, component, component_id)
        transform = component[2]['transform']
        anchor = anchor_axis([x*.001 for x in root_origin], root_direction, [x*.001 for x in transform['origin_mm']])
        supports = self._supports(bodies, transform, anchor, root_direction)
        ends, projection_range = bracket_axis(anchor, root_direction, supports)
        distance, root_points = self._native_result(self.adapter.component_axis_distance(entry.model, component[1], ends, root_direction))
        points_m = [[x*.001 for x in point] for point in root_points]
        check_axis_witnesses(points_m, anchor, root_direction, projection_range)
        after = self._distance_bodies(entry, component, component_id)
        if (self._body_signature(bodies) != self._body_signature(after[0]) or (moments, solid_count) != after[1:]
                or any(not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-9)
                       for before, current in zip(supports, self._supports(after[0], transform, anchor, root_direction))
                       for a, b in zip(before, current))):
            raise rejected('component_geometry_changed_during_measurement', 'Instance bodies, moments or exact directional supports changed.')
        self._finish(entry, observed, configuration, identity, rows)
        return {**self._result(entry, observed, configuration), 'measurement_scope': self.AXIS_SCOPE,
                'component': self._item(component, component_id), 'axis_origin_mm': origin, 'axis_direction': direction,
                'axis_origin_assembly_mm': root_origin, 'axis_direction_assembly': root_direction,
                'axis_semantics': 'infinite_line', 'distance_mm': distance,
                'closest_points_mm': [project_point_m(axes, point) for point in points_m],
                'closest_points_assembly_mm': root_points,
                'coordinate_frame': 'explicit_rigid_frame' if explicit_frame else 'assembly_model', 'frame': axes.model_dump(mode='json'),
                'solid_body_count': solid_count, 'includes_hidden_bodies': True, 'includes_surface_bodies': False,
                'intersection_classification': 'not_provided',
                'method': 'IBody2.GetExtremePoint + temporary ICurve.CreateWireBody edge + IModelDoc2.ClosestDistance'}
