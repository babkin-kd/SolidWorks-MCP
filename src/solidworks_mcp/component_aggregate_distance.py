"""Exact minimum over the normal solid part leaves of two explicit targets."""
from .component_distance import ComponentDistanceCatalog
from .measurement_frames import measurement_frame, project_point_m
from .point_measurement import point3, assembly_point_mm
from .documents import rejected


class ComponentAggregateDistanceCatalog(ComponentDistanceCatalog):
    AGGREGATE_SCOPE = 'resolved_component_aggregate_distance_v1'
    MAX_AGGREGATE_LEAVES = 1000
    MAX_AGGREGATE_BODIES = 5000
    MAX_DISTANCE_PAIRS = 10000

    def _leaves(self, rows, target):
        indexed = {row[0].object_id: row for row in rows}
        if len(indexed) != len(rows):raise rejected('component_roster_invalid', 'Duplicate instance references in complete hierarchy.')
        children = {}
        for row in rows:children.setdefault(row[2]['parent_component_id'], []).append(row)
        stack = [target];seen = set();leaves = []
        while stack:
            row = stack.pop();cid = row[0].object_id
            if cid in seen:raise rejected('component_hierarchy_invalid', 'Duplicate or cyclic descendant membership.')
            seen.add(cid);nested = children.get(cid, ())
            if row[2]['referenced_document_type'] == 'part':
                if nested:raise rejected('component_hierarchy_invalid', 'A part must not have component descendants.')
                leaves.append(row)
                if len(leaves) > self.MAX_AGGREGATE_LEAVES:
                    raise rejected('component_aggregate_budget_exceeded', 'Complete target exceeds 1000 part leaves; no partial result.')
            elif row[2]['referenced_document_type'] == 'assembly':stack.extend(nested)
            else:raise rejected('unsupported_component_type', 'Only resolved native part/assembly descendants supported.')
        return tuple(sorted(leaves, key=lambda row: row[2]['component_path']))

    def _aggregate_bodies(self, entry, row):
        items = self._body_rows(entry, row, row[0].object_id)
        solids = tuple(item for item in items if item[2]['body_type'] == 'solid')
        moments = tuple((item[0].native_identity, self.adapter.mass_body_signature(item[1])) for item in solids)
        return items, moments, len(solids)

    def measure_aggregate(self, document_id, configuration, expected_observation_revision,
                          component_a_id, component_b_id, *, frame=None):
        axes = measurement_frame(frame)
        if component_a_id == component_b_id:raise rejected('same_component_target', 'Specify two distinct explicit targets.')
        entry, observed, identity = self._context(document_id, configuration, expected_observation_revision)
        rows = self._snapshot(entry, configuration, identity)
        targets = [self._resolve(entry, configuration, identity, cid, rows) for cid in (component_a_id, component_b_id)]
        if targets[0][0].native_identity == targets[1][0].native_identity:
            raise rejected('same_component_target', 'Two aliases must not target the same native instance.')
        groups = [self._leaves(rows, target) for target in targets]
        unique = {row[0].object_id: row for group in groups for row in group}
        snapshots = {};body_count = 0
        for cid, row in unique.items():
            snapshots[cid] = self._aggregate_bodies(entry, row);body_count += len(snapshots[cid][0])
            if body_count > self.MAX_AGGREGATE_BODIES:
                raise rejected('component_aggregate_budget_exceeded', 'Complete targets exceed 5000 normal bodies; no partial result.')
        solid_groups = [tuple(row for row in group if snapshots[row[0].object_id][2]) for group in groups]
        if not all(solid_groups):raise rejected('component_has_no_solid_bodies', 'Each complete aggregate requires a normal solid leaf; empty/surface-only leaves are excluded.')
        pair_count = len(solid_groups[0])*len(solid_groups[1])
        if pair_count > self.MAX_DISTANCE_PAIRS:
            raise rejected('component_distance_budget_exceeded', 'Complete minimum exceeds 10000 leaf pairs; no partial result.')
        best = None;native_count = shared_count = 0
        for a in solid_groups[0]:
            for b in solid_groups[1]:
                if a[0].native_identity == b[0].native_identity:
                    # An aggregate and its descendant can contain the SAME instance.
                    # A confirmed solid support point witnesses the exact zero minimum.
                    body = next(item[1] for item in snapshots[a[0].object_id][0] if item[2]['body_type'] == 'solid')
                    local = point3(self.adapter.measurement_extreme_point(body, [1.,0.,0.]), 'native_extreme_point_unavailable')
                    root = assembly_point_mm(a[2]['transform'], local)
                    value = (0., [root, list(root)]);shared_count += 1
                else:
                    value = self._native_result(self.adapter.component_distance(entry.model, a[1], b[1]));native_count += 1
                if best is None or value[0] < best[0]:best = (*value, a, b)
        for cid, row in unique.items():
            before = snapshots[cid];after = self._aggregate_bodies(entry, row)
            if self._body_signature(before[0]) != self._body_signature(after[0]) or before[1:] != after[1:]:
                raise rejected('component_geometry_changed_during_measurement', 'A selected leaf body roster/summary or solid moments changed.')
        self._finish(entry, observed, configuration, identity, rows)
        return {**self._result(entry, observed, configuration), 'measurement_scope': self.AGGREGATE_SCOPE,
                'component_a': self._item(targets[0], component_a_id), 'component_b': self._item(targets[1], component_b_id),
                'nearest_component_a': self._item(best[2]), 'nearest_component_b': self._item(best[3]),
                'distance_mm': best[0], 'closest_points_assembly_mm': best[1],
                'closest_points_mm': [project_point_m(axes, [x*.001 for x in point]) for point in best[1]],
                'coordinate_frame': 'assembly_model' if frame is None else 'explicit_rigid_frame', 'frame': axes.model_dump(mode='json'),
                'leaf_component_ids': [[row[0].object_id for row in group] for group in groups],
                'leaf_component_counts': [len(group) for group in groups],
                'solid_leaf_component_counts': [len(group) for group in solid_groups],
                'excluded_nonsolid_leaf_component_counts': [len(group)-len(solid) for group, solid in zip(groups, solid_groups)],
                'solid_body_counts': [sum(snapshots[row[0].object_id][2] for row in group) for group in groups],
                'evaluated_pair_count': pair_count, 'native_pair_count': native_count, 'shared_instance_pair_count': shared_count,
                'includes_hidden_components': True, 'includes_hidden_bodies': True, 'includes_surface_bodies': False,
                'intersection_classification': 'not_provided',
                'method': 'complete leaf-pair IModelDoc2.ClosestDistance; IBody2.GetExtremePoint for shared instance'}
