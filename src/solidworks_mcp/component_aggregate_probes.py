"""Complete solid-leaf point-boundary and infinite-axis measurements."""
import math
from .component_aggregate_distance import ComponentAggregateDistanceCatalog
from .component_point_distance import ComponentPointDistanceCatalog
from .component_axis_distance import ComponentAxisDistanceCatalog
from .measurement_frames import measurement_frame, project_point_m
from .point_measurement import point3, BOUNDARY_TOLERANCE_M
from .axis_measurement import unit_direction, anchor_axis
from .documents import rejected


class ComponentAggregateProbeCatalog(ComponentAggregateDistanceCatalog,
                                     ComponentPointDistanceCatalog, ComponentAxisDistanceCatalog):
    AGGREGATE_POINT_SCOPE = 'resolved_component_aggregate_point_distance_v1'
    AGGREGATE_AXIS_SCOPE = 'resolved_component_aggregate_axis_distance_v1'
    MAX_AGGREGATE_FACES = 100000

    def _probe_target(self, document_id, configuration, expected_observation_revision, component_id):
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        rows = self._snapshot(entry, configuration, identity)
        target = self._resolve(entry, configuration, identity, component_id, rows)
        leaves = self._leaves(rows, target)
        snapshots = {}; count = 0
        for row in leaves:
            cid = row[0].object_id; snapshots[cid] = self._aggregate_bodies(entry, row)
            count += len(snapshots[cid][0])
            if count > self.MAX_AGGREGATE_BODIES:
                raise rejected('component_aggregate_budget_exceeded', 'Complete target exceeds 5000 normal bodies; no partial result.')
        solids = tuple(row for row in leaves if snapshots[row[0].object_id][2])
        if not solids:
            raise rejected('component_has_no_solid_bodies', 'Complete target requires a normal solid leaf.')
        return entry, observed, identity, rows, target, leaves, solids, snapshots

    def _close_probe_bodies(self, entry, leaves, snapshots):
        for row in leaves:
            before = snapshots[row[0].object_id]; after = self._aggregate_bodies(entry, row)
            if self._body_signature(before[0]) != self._body_signature(after[0]) or before[1:] != after[1:]:
                raise rejected('component_geometry_changed_during_measurement', 'Selected leaf body roster/summary or solid moments changed.')

    def _probe_counts(self, leaves, solids, snapshots):
        return {'leaf_component_ids': [row[0].object_id for row in leaves],
                'leaf_component_count': len(leaves), 'solid_leaf_component_count': len(solids),
                'excluded_nonsolid_leaf_component_count': len(leaves)-len(solids),
                'evaluated_leaf_count': len(solids),
                'solid_body_count': sum(snapshots[row[0].object_id][2] for row in leaves),
                'includes_hidden_components': True, 'includes_hidden_bodies': True,
                'includes_surface_bodies': False}

    @staticmethod
    def _root_point(axes, point):
        return point3([axes.origin_mm[k]+sum(axes.axes_in_model[i][k]*point[i] for i in range(3))
                       for k in range(3)], 'measurement_numeric_overflow')

    def measure_aggregate_point(self, document_id, configuration, expected_observation_revision,
                                component_id, point_mm, *, frame=None):
        point = point3(point_mm); axes = measurement_frame(frame); root_point = self._root_point(axes, point)
        entry, observed, identity, rows, target, leaves, solids, snapshots = self._probe_target(
            document_id, configuration, expected_observation_revision, component_id)
        face_sets = {}; cost = 0
        for row in solids:
            cid = row[0].object_id
            faces, count = self._point_faces(entry, cid, snapshots[cid][0])
            face_sets[cid] = faces; cost += count
            if cost > self.MAX_AGGREGATE_FACES:
                raise rejected('topology_budget_exceeded', 'Complete aggregate exceeds 100000 solid faces; no partial result.')
        best = None; locations = []
        for row in solids:
            cid = row[0].object_id
            value = self._point_boundary(entry, row, face_sets[cid], root_point)
            locations.extend({'component_id': cid, **item} for item in value['body_locations'])
            if best is None or value['distance_mm'] < best[0]['distance_mm']: best = value, row
        for row in solids: self._close_point_faces(entry, row[0].object_id, face_sets[row[0].object_id])
        self._close_probe_bodies(entry, leaves, snapshots)
        self._finish(entry, observed, configuration, identity, rows)
        location = next(kind for kind in ('inside','boundary','outside') if any(item['point_location']==kind for item in locations))
        value, nearest = best
        return {**self._result(entry, observed, configuration), **self._probe_counts(leaves, solids, snapshots),
                'measurement_scope': self.AGGREGATE_POINT_SCOPE, 'component': self._item(target, component_id),
                'nearest_component': self._item(nearest), 'nearest_body_id': value['nearest_body_id'],
                'nearest_face_id': value['nearest_face_id'], 'distance_mm': value['distance_mm'],
                'point_mm': point, 'point_assembly_mm': root_point,
                'nearest_assembly_mm': value['nearest_assembly_mm'],
                'nearest_mm': project_point_m(axes, [x*.001 for x in value['nearest_assembly_mm']]),
                'coordinate_frame': 'assembly_model' if frame is None else 'explicit_rigid_frame',
                'frame': axes.model_dump(mode='json'), 'distance_semantics': 'minimum_to_individual_solid_boundary',
                'point_location': location, 'inside': True if location=='inside' else False if location=='outside' else None,
                'body_locations': locations, 'face_count': cost, 'boundary_tolerance_mm': BOUNDARY_TOLERANCE_M*1000.,
                'method': 'complete solid leaf faces IFace2.GetClosestPointOn + native body RayIntersections'}

    def measure_aggregate_axis(self, document_id, configuration, expected_observation_revision,
                               component_id, axis_origin_mm, axis_direction, *, frame=None):
        origin = point3(axis_origin_mm, 'invalid_measurement_axis'); direction = unit_direction(axis_direction)
        axes = measurement_frame(frame); root_origin = self._root_point(axes, origin)
        root_direction = unit_direction([sum(axes.axes_in_model[i][k]*direction[i] for i in range(3)) for k in range(3)])
        entry, observed, identity, rows, target, leaves, solids, snapshots = self._probe_target(
            document_id, configuration, expected_observation_revision, component_id)
        spans = {}
        for row in solids:
            cid = row[0].object_id; transform = row[2]['transform']
            anchor = anchor_axis([x*.001 for x in root_origin], root_direction, [x*.001 for x in transform['origin_mm']])
            spans[cid] = anchor, self._supports(snapshots[cid][0], transform, anchor, root_direction)
        best = None
        for row in solids:
            anchor, supports = spans[row[0].object_id]
            distance, points = self._axis_leaf(entry, row, anchor, root_direction, supports)
            if best is None or distance < best[0]: best = distance, points, row
        for row in solids:
            anchor, before = spans[row[0].object_id]
            current = self._supports(snapshots[row[0].object_id][0], row[2]['transform'], anchor, root_direction)
            if len(before)!=len(current) or any(not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-9)
                    for old,new in zip(before,current) for a,b in zip(old,new)):
                raise rejected('component_geometry_changed_during_measurement', 'Selected leaf exact axis supports changed.')
        self._close_probe_bodies(entry, leaves, snapshots)
        self._finish(entry, observed, configuration, identity, rows)
        return {**self._result(entry, observed, configuration), **self._probe_counts(leaves, solids, snapshots),
                'measurement_scope': self.AGGREGATE_AXIS_SCOPE, 'component': self._item(target, component_id),
                'nearest_component': self._item(best[2]), 'distance_mm': best[0],
                'axis_origin_mm': origin, 'axis_direction': direction, 'axis_origin_assembly_mm': root_origin,
                'axis_direction_assembly': root_direction, 'axis_semantics': 'infinite_line',
                'closest_points_assembly_mm': best[1],
                'closest_points_mm': [project_point_m(axes,[x*.001 for x in point]) for point in best[1]],
                'coordinate_frame': 'assembly_model' if frame is None else 'explicit_rigid_frame',
                'frame': axes.model_dump(mode='json'), 'intersection_classification': 'not_provided',
                'method': 'complete solid leaf supports + memory-only certified axis edges + native ClosestDistance'}
