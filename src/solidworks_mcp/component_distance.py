"""Native minimum distance between two explicitly referenced part instances."""
import math
from .components import ComponentCatalog
from .documents import rejected


class ComponentDistanceCatalog(ComponentCatalog):
    DISTANCE_SCOPE = 'resolved_part_component_distance_v1'

    def _distance_bodies(self, entry, row, component_id):
        items = self._body_rows(entry, row, component_id)
        solids = tuple(item for item in items if item[2]['body_type'] == 'solid')
        if not solids:
            raise rejected('component_has_no_solid_bodies', 'Distance requires at least one normal native solid in each part instance.')
        moments = tuple((item[0].native_identity, self.adapter.mass_body_signature(item[1])) for item in solids)
        return items, moments, len(solids)

    @staticmethod
    def _native_result(raw):
        scalar = lambda x: type(x) in (int, float) and math.isfinite(x)
        if not isinstance(raw, (tuple, list)) or len(raw) != 3:
            raise rejected('component_distance_unavailable', 'Native distance must include both closest points.')
        distance, first, second = raw
        if not scalar(distance) or distance < 0:
            raise rejected('component_distance_unavailable', 'Native solver returned no finite nonnegative distance.')
        if any(not isinstance(point, (tuple, list)) or len(point) != 3 or not all(scalar(x) for x in point) for point in (first, second)):
            raise rejected('component_distance_unavailable', 'Closest points must be finite assembly-model coordinates.')
        if not math.isclose(math.dist(first, second), distance, rel_tol=1e-8, abs_tol=1e-8):
            raise rejected('component_distance_inconsistent', 'Native distance disagrees with its closest points.')
        mm = float(distance)*1000.
        points = [[float(x)*1000. for x in point] for point in (first, second)]
        if not math.isfinite(mm) or not all(math.isfinite(x) for point in points for x in point):
            raise rejected('component_distance_unavailable', 'Native coordinates overflow the mm contract.')
        return mm, points

    def measure(self, document_id, configuration, expected_observation_revision, component_a_id, component_b_id):
        if component_a_id == component_b_id:
            raise rejected('same_component_target', 'Specify two distinct part instances; identical file paths are permitted.')
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        rows = self._snapshot(entry, configuration, identity)
        targets = [self._resolve(entry, configuration, identity, cid, rows) for cid in (component_a_id, component_b_id)]
        if targets[0][0].native_identity == targets[1][0].native_identity:
            raise rejected('same_component_target', 'Two reference aliases must not target the same native instance.')
        snapshots = [self._distance_bodies(entry, row, cid) for row, cid in zip(targets, (component_a_id, component_b_id))]
        distance, points = self._native_result(self.adapter.component_distance(entry.model, targets[0][1], targets[1][1]))
        for row, cid, before in zip(targets, (component_a_id, component_b_id), snapshots):
            after = self._distance_bodies(entry, row, cid)
            if self._body_signature(before[0]) != self._body_signature(after[0]) or before[1:] != after[1:]:
                raise rejected('component_geometry_changed_during_measurement', 'Instance body roster, local summaries or solid geometric moments changed during measurement.')
        self._finish(entry, observed, configuration, identity, rows)
        return {**self._result(entry, observed, configuration), 'measurement_scope': self.DISTANCE_SCOPE,
                'component_a': self._item(targets[0], component_a_id), 'component_b': self._item(targets[1], component_b_id),
                'distance_mm': distance, 'closest_points_mm': points, 'coordinate_frame': 'assembly_model',
                'solid_body_counts': [snapshot[2] for snapshot in snapshots], 'includes_hidden_bodies': True,
                'includes_surface_bodies': False, 'method': 'IModelDoc2.ClosestDistance',
                'intersection_classification': 'not_provided'}
