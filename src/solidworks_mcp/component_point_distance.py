"""Minimum boundary distance and native point location for one exact instance."""
import math
from .component_distance import ComponentDistanceCatalog
from .component_topology import ComponentTopologyCatalog
from .measurement_frames import measurement_frame, project_point_m
from .point_measurement import point3, component_local_point_m, assembly_point_mm, classify_native_rays, BOUNDARY_TOLERANCE_M
from .documents import rejected


class ComponentPointDistanceCatalog(ComponentDistanceCatalog, ComponentTopologyCatalog):
    POINT_SCOPE = 'resolved_part_component_point_distance_v1'

    def measure_point(self, document_id, configuration, expected_observation_revision, component_id, point_mm, *, frame=None):
        point = point3(point_mm);explicit_frame = frame is not None;axes = measurement_frame(frame)
        root_point = point3([axes.origin_mm[k]+sum(axes.axes_in_model[i][k]*point[i] for i in range(3)) for k in range(3)], 'measurement_numeric_overflow')
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        rows = self._snapshot(entry, configuration, identity)
        component = self._resolve(entry, configuration, identity, component_id, rows)
        bodies, moments, solid_count = self._distance_bodies(entry, component, component_id)
        local = component_local_point_m(component[2]['transform'], root_point)
        faces = [];cost = 0
        for ref, body, summary in bodies:
            if summary['body_type'] != 'solid':continue
            topology = self._topology_rows(entry, body, component_id, ref.object_id, 'face')
            cost += len(topology)
            if not topology or cost > self.MAX_TOPOLOGY:
                raise rejected('topology_budget_exceeded', 'Complete nonempty solid face rosters within 100000 faces required.')
            faces.append((ref, body, topology))
        best = None;locations = []
        for body_ref, body, topology in faces:
            body_best = None
            for ref, face, summary in topology:
                raw = self.adapter.face_closest_point(face, local)
                if (not isinstance(raw, (tuple, list)) or len(raw) != 5
                        or any(type(x) not in (int, float) or not math.isfinite(x) for x in raw)):
                    raise rejected('closest_face_point_unavailable', 'Native trimmed face must return five finite XYZ/UV values.')
                nearest = raw[:3];distance = math.dist(local, nearest)
                if not math.isfinite(distance):raise rejected('measurement_numeric_overflow', 'Native boundary distance overflowed.')
                candidate = (distance, ref, nearest)
                if body_best is None or distance < body_best[0]:body_best = candidate
            if best is None or body_best[0] < best[0]:best = body_best
            location = ('boundary' if body_best[0] <= BOUNDARY_TOLERANCE_M else
                        classify_native_rays(self.adapter.body_point_rays(entry.model, body, local), local))
            locations.append({'body_id': body_ref.object_id, 'point_location': location})
        nearest_root = assembly_point_mm(component[2]['transform'], best[2])
        nearest = project_point_m(axes, [x*.001 for x in nearest_root])
        distance_mm = best[0]*1000.
        if not math.isfinite(distance_mm) or not math.isclose(math.dist(root_point, nearest_root), distance_mm, rel_tol=1e-8, abs_tol=1e-5):
            raise rejected('component_point_distance_inconsistent', 'Transformed closest point disagrees with native local boundary distance.')
        for body_ref, body, topology in faces:
            after = self._topology_rows(entry, body, component_id, body_ref.object_id, 'face')
            if self._topology_signature(topology) != self._topology_signature(after):
                raise rejected('component_topology_changed_during_read', 'Complete native face membership/summary changed during measurement.')
        after = self._distance_bodies(entry, component, component_id)
        if self._body_signature(bodies) != self._body_signature(after[0]) or (moments, solid_count) != after[1:]:
            raise rejected('component_geometry_changed_during_measurement', 'Instance body roster or solid geometric moments changed during measurement.')
        self._finish(entry, observed, configuration, identity, rows)
        location = next((kind for kind in ('inside', 'boundary', 'outside') if any(x['point_location'] == kind for x in locations)), None)
        return {**self._result(entry, observed, configuration), 'measurement_scope': self.POINT_SCOPE,
                'component': self._item(component, component_id), 'point_mm': point, 'point_assembly_mm': root_point,
                'nearest_mm': nearest, 'nearest_assembly_mm': nearest_root, 'distance_mm': distance_mm,
                'coordinate_frame': 'explicit_rigid_frame' if explicit_frame else 'assembly_model', 'frame': axes.model_dump(mode='json'),
                'distance_semantics': 'minimum_to_individual_solid_boundary', 'point_location': location,
                'inside': True if location == 'inside' else False if location == 'outside' else None,
                'boundary_tolerance_mm': BOUNDARY_TOLERANCE_M*1000., 'body_locations': locations,
                'nearest_body_id': best[1].body_id, 'nearest_face_id': best[1].object_id,
                'solid_body_count': solid_count, 'face_count': cost, 'includes_hidden_bodies': True, 'includes_surface_bodies': False,
                'method': 'IFace2.GetClosestPointOn + IModelDocExtension.RayIntersections'}
