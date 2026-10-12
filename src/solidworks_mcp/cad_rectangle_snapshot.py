"""Passive complete empty-part/closed-rectangle capture; no native writes."""
from copy import deepcopy
from pathlib import Path

from . import binding
from .cad_native_first_save_snapshot import (
    FOLDERS, DISPLAY_FEATURES, _array, _typed, _number, _pid, _properties, _annotations,
    _configuration, _empty_auxiliary_data, _display_data, _sketch,
)
from .documents import rejected
from .rectangle_snapshot import SCOPE, EMPTY, SKETCH, validated_rectangle_snapshot
from .sketches import rectangle_profile_parameters
from .linear_sketch import _identifier, _integer, _coordinates
from .cad_rectangle_annotation_views import rectangle_annotation_view_bindings


class CadRectangleSnapshotMixin:
    def rectangle_construction_snapshot(self, model):
        opening = self.snapshot(model)
        if opening['document_type'] != 'part':
            raise rejected('rectangle_snapshot_unsupported', 'Use an explicit native part.')
        watch = self.watch_part(model)
        try:
            sequence = watch.poll()
            identity = self.identity(model)
            cfg_identity = self.configuration_identity(model, opening['active_configuration'])
            result = self._rectangle_construction_snapshot(model)
            if (self.identity(model) != identity or self.snapshot(model) != opening
                    or self.configuration_identity(model, opening['active_configuration']) != cfg_identity
                    or watch.poll() != sequence):
                raise rejected('rectangle_snapshot_changed', 'The model/configuration/events changed during capture.')
            return validated_rectangle_snapshot(result)
        finally:
            watch.close()

    def _rectangle_construction_snapshot(self, model):
        fail = lambda message: rejected('rectangle_snapshot_unsupported', message)
        before = self.snapshot(model)
        cfg = before['active_configuration']
        if before['configurations'] != [cfg]:
            raise fail('Exactly one native configuration is supported.')
        bodies = self.bodies(model, 'all')
        if bodies:
            # The existing full body oracle is unchanged; retain every field.
            result = deepcopy(self.first_save_part_snapshot(model))
            result['scope'] = SCOPE
            result['clone_state']['creation_controls'] = self.part_creation_controls(model)
            roles={row['full_name']:row['role'].removeprefix('dimension:')
                for row in result['native_observations']['qualified_dimensions']}
            result['native_observations']['annotation_view_bindings']=rectangle_annotation_view_bindings(
                self,model,result['clone_state']['display_data'],roles)
            return result
        features = self.features(model)
        identities = tuple(self.identity(f) for f in features)
        rows = [self.feature_summary(f) for f in features]
        kinds = [r['feature_type'] for r in rows]
        allowed = FOLDERS | DISPLAY_FEATURES | {'RefPlane', 'OriginProfileFeature', 'ProfileFeature'}
        if (not 4 <= len(features) <= 64 or kinds.count('RefPlane') != 3
                or kinds.count('OriginProfileFeature') != 1 or kinds.count('ProfileFeature') not in (0, 1)
                or any(k not in allowed for k in kinds)
                or any(r['suppressed'] or r['error_code'] for r in rows)):
            raise fail('Use three native planes, origin and at most one closed rectangle sketch.')
        context = self.dimension_context(model)
        if (context['editing_sketch'] or context['external_reference_count'] or context['equation_count']
                or context['equations_linked'] or context['design_table'] or context['unsafe_feature_types']
                or any(context['configuration_needs_rebuild'].values())):
            raise fail('Sketch editing, pending rebuild and external/equation controls are unsupported.')
        inventories = self.feature_deletion_context(model)
        equations = inventories['equations']
        if (equations['enumerated_count'] or equations['disabled_count']
                or not equations['disabled_definitions_captured']
                or inventories['external_references']['count'] or inventories['auxiliary_references']['count']):
            raise fail('All enabled/disabled equations and external inventories must be empty.')
        feature_refs = self.feature_external_references(features)
        if feature_refs['total_reference_rows']:
            raise fail('Per-feature external references are unsupported.')
        geometry = self.dimension_geometry_snapshot(model)
        if geometry != {'representation': 'planar_polyhedral_brep_v1', 'bodies': []}:
            raise fail('The full target body census must be empty.')
        native_dims = self.dimensions(model, features)
        dimensions = [self.dimension_summary(d, [cfg]) for d in native_dims]
        has_sketch = 'ProfileFeature' in kinds
        if len(dimensions) != (2 if has_sketch else 0):
            raise fail('Zero dimensions or exactly two proven sketch driving dimensions are required.')
        references = []
        roles = {r['native_id']: f'feature:{i}' for i, r in enumerate(rows)}
        for f, r in zip(features, rows):
            if r['feature_type'] not in FOLDERS | DISPLAY_FEATURES:
                _pid(self, model, f, 'feature', roles[r['native_id']], references)
        sketch = parameters = None
        if has_sketch:
            feature = features[kinds.index('ProfileFeature')]
            raw, _ = self.sketch_snapshot(model, feature)
            parameters = rectangle_profile_parameters(raw,
                dict(dimensions=dimensions, context=context, geometry=geometry), cfg, require_editable=False)
            sketch = _sketch(self, model, feature, roles, references)
            dimension_roles = {name: 'dimension:' + axis for axis, name in parameters['axes'].items()}
            if len(dimension_roles) != 2:
                raise fail('The exact width/height bindings must be distinct.')
            for d, r in zip(native_dims, dimensions):
                anchor = self.dimension_persistent_id(model, d)
                resolved = self.resolve_dimension_id(model, anchor)
                if (self.identity(resolved) != self.identity(self.dimension_object(d))
                        or not self.dimension_reference_is_current(model, d, anchor)
                        or r['full_name'] not in dimension_roles):
                    raise fail('Every driving dimension must round-trip its exact current native owner.')
                references.append(dict(kind='dimension', role=dimension_roles[r['full_name']], token=_json_anchor(anchor)))
        origin_feature = features[kinds.index('OriginProfileFeature')]
        origin_sketch = binding.wrap(origin_feature.GetSpecificFeature2(), self._module.ISketch)
        points = _array(origin_sketch.GetSketchPoints2(), 1)
        if len(points) != 1:
            raise fail('The exact unique native model origin must be observed.')
        point = binding.wrap(points[0], self._module.ISketchPoint)
        point_role = 'sketch:0/model_origin' if has_sketch else 'origin:point'
        proof = [] if has_sketch else references
        _pid(self, model, point, 'sketch_point', point_role, proof, 'ISketchPoint')
        if has_sketch and proof[0] not in references:
            raise fail('The sketch/model origin must share the exact current native anchor.')
        origin = dict(feature_role=roles[rows[kinds.index('OriginProfileFeature')]['native_id']],
            point_role=point_role, native_id=_identifier(point), point_type=_integer(point.Type, high=1000),
            constraint_status=_integer(point.Status, high=10),
            coordinates_si=_coordinates((point.X, point.Y, point.Z), 3))
        material = binding.wrap(model, self._module.IPartDoc).GetMaterialPropertyName2(cfg)
        if type(material) is not tuple or len(material) != 2 or any(type(x) is not str for x in material):
            raise fail('Complete material name/database outputs are required.')
        units = _array(model.GetUnits(), 16)
        if not units or any(type(x) not in (int, float, bool) for x in units):
            raise fail('The complete native units array is required.')
        data = dict(profile=SKETCH if has_sketch else EMPTY, features=rows,
            dependencies=self.feature_dependencies(features), geometry=geometry, dimensions=dimensions,
            sketch=sketch, parameters=parameters,
            controls={k: deepcopy(v) for k, v in context.items() if k not in ('active_document', 'read_only')},
            equation_reference_inventory=inventories, feature_external_reference_inventory=feature_refs,
            planes=[dict(role=roles[r['native_id']], transform=[_number(v) for v in self.reference_plane_transform(f)])
                for f, r in zip(features, rows) if r['feature_type'] == 'RefPlane'],
            properties=_properties(self, model, cfg), units=units,
            annotations=_annotations(self, model, native_dims, references),
            configuration_state=_configuration(self, model, cfg),
            auxiliary_data=_empty_auxiliary_data(self, model, features, rows),
            display_data=_display_data(self, model, features, rows), material=list(material),
            creation_controls=self.part_creation_controls(model), origin=origin)
        selection = binding.wrap(model.SelectionManager, self._module.ISelectionMgr)
        count = _typed(selection.GetSelectedObjectCount2(-1), int)
        if (tuple(self.identity(f) for f in self.features(model)) != identities
                or self.bodies(model, 'all') or self.snapshot(model) != before):
            raise fail('Target features/body census changed during the complete passive read.')
        return dict(scope=SCOPE, configuration=cfg, configurations=[cfg], solid_body_count=0,
            selection_count=count, clone_state=data,
            references=sorted(references, key=lambda r: (r['kind'], r['role'])),
            native_observations=dict(document_dimension_namespace=Path(before['path']).stem if before['path'] else before['title'],
                annotation_view_bindings=rectangle_annotation_view_bindings(self,model,data['display_data'],
                    {name:axis for axis,name in parameters['axes'].items()} if has_sketch else {})))


def _json_anchor(anchor):
    from .jobs import _json
    return _json(anchor)
