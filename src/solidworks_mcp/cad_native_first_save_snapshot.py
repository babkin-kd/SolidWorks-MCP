"""Passive full oracle for the first-save rectangular-base profile.

No activation, rebuild, selection, cached-property evaluation or file write.
The domain brackets two captures with the complete session census. Unsupported
geometry, feature/control/data inventories fail closed before Copy.
"""
from copy import deepcopy
import math

from . import binding
from .documents import rejected
from .jobs import _json
from .sketches import rectangle_parameters


SCOPE = 'native_first_save_part_snapshot_v1'
FOLDERS = frozenset(('CommentsFolder', 'FavoriteFolder', 'HistoryFolder',
    'SelectionSetFolder', 'SensorFolder', 'DocsFolder', 'DetailCabinet',
    'SurfaceBodyFolder', 'SolidBodyFolder', 'EnvFolder', 'InkMarkupFolder',
    'EqnFolder', 'MaterialFolder'))


def _fail(message):
    raise rejected('first_save_snapshot_unsupported', message)


def _array(value, maximum=128):
    if value is None:
        return []
    if type(value) not in (tuple, list) or len(value) > maximum:
        _fail('A complete bounded native array is required.')
    return list(value)


def _number(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        _fail('An exact finite native number is required.')
    return float(value).hex()


def _typed(value, kind):
    if type(value) is not kind or (kind is str and ('\0' in value or len(value) > 16384)):
        _fail('A bounded exact native scalar is required.')
    return value


def _pid(adapter, model, obj, kind, role, references, interface=None):
    token = adapter.persistent_id(model, obj)
    if type(token) is not bytes or not token:
        _fail('Every declared current reference needs a native persistent ID.')
    if interface is None:
        current = adapter.resolve_persistent_id(model, token, kind)
    else:
        raw, status = adapter._extension(model).GetObjectByPersistReference3(adapter._persistent_variant(token))
        if type(status) is not int or status != 0 or raw is None:
            _fail('Declared reference did not resolve with status zero.')
        current = binding.wrap(raw, getattr(adapter._module, interface))
    if (adapter.identity(current) != adapter.identity(obj)
            or adapter.persistent_id(model, current) != token):
        _fail('Declared persistent reference must round-trip its exact native object.')
    row = dict(kind=kind, role=role, token=token.hex())
    if any(old['token'] == row['token'] or (old['kind'], old['role']) == (kind, role) for old in references):
        _fail('Complete reference roles and native tokens must be unique.')
    references.append(row)
    return row


def _properties(adapter, model, configuration):
    result = {}
    for name in ('', configuration):
        manager = binding.wrap(adapter._extension(model).CustomPropertyManager(name), adapter._module.ICustomPropertyManager)
        count = _typed(manager.Count, int)
        names = _array(manager.GetNames())
        if not 0 <= count <= 128 or len(names) != count or len(set(names)) != count:
            _fail('Custom-property names/count must form a complete unique inventory.')
        rows = []
        for field in names:
            _typed(field, str)
            raw = manager.Get6(field, True)  # Use cached data: never activate/evaluate another configuration.
            if type(raw) is not tuple or len(raw) != 5:
                _fail('Complete cached custom-property outputs are required.')
            code, value, resolved, was_resolved, linked = raw
            _typed(code, int); _typed(value, str); _typed(resolved, str)
            _typed(was_resolved, bool); _typed(linked, bool)
            if linked or value != resolved:
                _fail('Linked/evaluated properties require a separate first-save data profile.')
            rows.append(dict(name=field, type=_typed(manager.GetType2(field), int),
                value=value, resolved=resolved, was_resolved=was_resolved, linked=linked, cached_result=code))
        if manager.Count != count or _array(manager.GetNames()) != names:
            _fail('Property inventory changed during the passive read.')
        result[name] = sorted(rows, key=lambda row: row['name'])
    return result


def _extrusion(adapter, feature):
    data = binding.wrap(feature.GetDefinition(), adapter._module.IExtrudeFeatureData2)
    if data is None:
        _fail('A complete native extrusion definition is required.')
    booleans = ('BothDirections', 'ReverseDirection', 'Merge', 'FeatureScope', 'AutoSelect',
                'FromOffsetReverse', 'FlipSideToCut', 'NormalCut', 'LinkToThickness', 'CapEnds')
    integers = ('FromType', 'ThinWallType')
    numbers = ('FromOffsetDistance', 'CapThickness')
    result = {name: _typed(getattr(data, name), bool) for name in booleans}
    result.update({name: _typed(getattr(data, name), int) for name in integers})
    result.update({name: _number(getattr(data, name)) for name in numbers})
    result['thin_feature'] = _typed(data.IsThinFeature(), bool)
    result['contour_count'] = _typed(data.GetContoursCount(), int)
    result['directions'] = []
    for forward in (True, False):
        result['directions'].append(dict(forward=forward,
            end_condition=_typed(data.GetEndCondition(forward), int),
            depth=_number(data.GetDepth(forward)), draft_angle=_number(data.GetDraftAngle(forward)),
            draft_enabled=_typed(data.GetDraftWhileExtruding(forward), bool),
            draft_outward=_typed(data.GetDraftOutward(forward), bool),
            reverse_offset=_typed(data.GetReverseOffset(forward), bool),
            translate_surface=_typed(data.GetTranslateSurface(forward), bool),
            wall_thickness=_number(data.GetWallThickness(forward))))
    if (result['BothDirections'] or result['ReverseDirection'] or result['thin_feature']
            or result['FromType'] != 0 or result['contour_count'] != 0
            or result['directions'][0]['end_condition'] != 0
            or any(row['draft_enabled'] for row in result['directions'])):
        _fail('First save currently supports one positive, unthinned, undrafted blind base.')
    return result


def _point(vertex):
    values = _array(vertex.GetPoint(), 3)
    if len(values) != 3:
        _fail('Exact topology vertex coordinates are required.')
    return [_number(value) for value in values]


def _annotations(adapter, model, dimensions, references):
    """Complete annotation census; only exact own dimension displays allowed."""
    extension=adapter._extension(model)
    count=_typed(extension.GetAnnotationCount(),int)
    native=_array(extension.GetAnnotations(),128)
    if not 0 <= count <= 128 or len(native)!=count:
        _fail('Complete native annotation count and array must agree.')
    candidates=[]
    rows=[]
    for item in dimensions:
        for display in item.displays:
            annotation=binding.wrap(display.GetAnnotation(),adapter._module.IAnnotation)
            if annotation is None:_fail('Every display dimension needs its exact annotation.')
            identity=adapter.identity(annotation)
            if any(identity==old for old in candidates):continue
            candidates.append(identity)
            matches=[raw for raw in native if adapter.identity(raw)==identity]
            if len(matches)!=1:
                _fail('Display annotation must be a unique member of the complete document census.')
            position=_array(annotation.GetPosition(),3)
            if len(position)!=3:_fail('Full dimension annotation position is required.')
            text_format=binding.wrap(display.GetTextFormat(),adapter._module.ITextFormat)
            if text_format is None:_fail('Full dimension text format is required.')
            values=_array(text_format.GetAllValues(),128)
            if not values or any(type(value) not in (str,int,float,bool) for value in values):
                _fail('Complete typed native text-format values are required.')
            role='annotation:'+_typed(annotation.GetName(),str)
            _pid(adapter,model,annotation,'annotation',role,references,'IAnnotation')
            rows.append(dict(role=role,type=_typed(annotation.GetType(),int),
                visible=_typed(annotation.Visible,int),position=[_number(value) for value in position],
                display_type=_typed(display.Type2,int),text=_typed(display.GetText(0),str),
                use_document_format=_typed(display.GetUseDocTextFormat(),bool),text_format=values))
    if len(candidates)!=count or extension.GetAnnotationCount()!=count:
        _fail('Unknown notes/annotations or a changing inventory require a separate data profile.')
    closing=_array(extension.GetAnnotations(),128)
    if len(closing)!=count or any(sum(adapter.identity(raw)==token for raw in closing)!=1 for token in candidates):
        _fail('Annotation membership changed during the passive read.')
    return sorted(rows,key=lambda row:row['role'])


def _configuration(adapter, model, name):
    config=binding.wrap(model.GetConfigurationByName(name),adapter._module.IConfiguration)
    if config is None:_fail('The exact named native configuration is required.')
    token=adapter.identity(config)
    fields={'Name':str,'Description':str,'Comment':str,'AlternateName':str,
        'BOMPartNoSource':int,'Type':int,'Lock':bool,'UseAlternateNameInBOM':bool,
        'UseDescriptionInBOM':bool,'SuppressNewFeatures':bool,'HideNewComponentModels':bool,
        'SuppressNewComponentModels':bool,'RepresentationShared':bool}
    values={key:_typed(getattr(config,key),kind) for key,kind in fields.items()}
    count=_typed(config.GetParameterCount(),int)
    raw=config.GetParameters()
    if type(raw) is not tuple or len(raw)!=2 or not 0 <= count <= 128:
        _fail('Complete bounded configuration parameter outputs are required.')
    names,parameters=(_array(column,128) for column in raw)
    if (len(names)!=count or len(parameters)!=count or len(set(names))!=count
            or any(type(key) is not str for key in names)
            or any(type(value) not in (str,int,float,bool) for value in parameters)):
        _fail('Configuration parameter names and values must be complete and unique.')
    values['parameters']=sorted(zip(names,parameters))
    displays=_array(config.GetDisplayStates(),16)
    if (not displays or len(displays)!=_typed(config.GetDisplayStatesCount(),int)
            or any(type(value) is not str for value in displays) or len(set(displays))!=len(displays)
            or config.GetChildrenCount()!=0 or config.GetParameterCount()!=count
            or adapter.identity(model.GetConfigurationByName(name))!=token):
        _fail('Complete native configuration/display-state membership must remain unchanged.')
    values['display_states']=displays
    return values


def _empty_auxiliary_data(adapter, model, features, summaries):
    extension=adapter._extension(model)
    if _typed(extension.GetAttachmentCount(),int)!=0 or _array(extension.GetAttachments()):
        _fail('Embedded attachments require a separate complete data profile.')
    for feature,row in zip(features,summaries):
        if row['feature_type']=='CommentsFolder':
            folder=binding.wrap(feature.GetSpecificFeature2(),adapter._module.ICommentFolder)
            if folder is None or _typed(folder.GetCommentCount(),int)!=0 or _array(folder.GetComments()):
                _fail('Comments must be independently proven empty in the initial data profile.')
        elif row['feature_type']=='SelectionSetFolder':
            folder=binding.wrap(feature.GetSpecificFeature2(),adapter._module.ISelectionSetFolder)
            if folder is None or _array(folder.GetSelectionSets()):
                _fail('Named selection sets require a separate complete data profile.')
    return dict(attachments=0,comments=0,named_selection_sets=0)


def _topology(adapter, model, body, boundary, references):
    """Bind unique analytical roles, never enumeration order, names or PID bytes."""
    expected_edges = {_json(sorted([boundary['vertices'][row['start']], boundary['vertices'][row['end']]]))
                      for row in boundary['edges']}
    expected_faces = {_json(sorted({tuple(boundary['vertices'][coedge['start']])
                       for loop in row['loops'] for coedge in loop['coedges']})) for row in boundary['faces']}
    for kind, expected in (('edge', expected_edges), ('face', expected_faces)):
        objects = adapter.topology(body, kind)
        if len(objects) != len(expected):
            _fail('Native topology census must agree with the complete analytical boundary.')
        seen = set()
        for obj in objects:
            if adapter.identity(adapter.owner_body(obj, kind)) != adapter.identity(body):
                _fail('A declared topology object belongs to another body.')
            if kind == 'edge':
                vertices = [binding.wrap(obj.GetStartVertex(), adapter._module.IVertex),
                            binding.wrap(obj.GetEndVertex(), adapter._module.IVertex)]
                key = _json(sorted(_point(vertex) for vertex in vertices))
            else:
                vertices = set()
                for raw_edge in _array(obj.GetEdges(), 12):
                    edge = binding.wrap(raw_edge, adapter._module.IEdge)
                    for getter in ('GetStartVertex', 'GetEndVertex'):
                        vertex = binding.wrap(getattr(edge, getter)(), adapter._module.IVertex)
                        vertices.add(tuple(_point(vertex)))
                key = _json(sorted(vertices))
            if key not in expected or key in seen:
                _fail('Topology must have unique complete analytical incidence roles.')
            seen.add(key)
            _pid(adapter, model, obj, kind, 'body:0/' + key, references)
        if seen != expected:
            _fail('Topology roles do not cover the entire supported boundary.')


def _sketch(adapter, model, feature, feature_roles, references):
    snapshot, members = adapter.sketch_snapshot(model, feature)
    result = deepcopy(snapshot)
    bindings = [('feature_pid_hex', result['feature_native_id']),
                ('reference_plane', result['reference_plane']['native_id']),
                ('model_origin', result['model_origin']['feature_native_id'])]
    for key, native_id in bindings:
        role = feature_roles[native_id]
        token = result[key] if key == 'feature_pid_hex' else result[key]['pid_hex']
        if not any(row['kind'] == 'feature' and row['role'] == role and row['token'] == token for row in references):
            _fail('Sketch plane/origin/owner must bind the exact declared feature inventory.')
        if key == 'feature_pid_hex':
            result[key] = {'reference_role': role}
        else:
            result[key]['pid_hex'] = {'reference_role': role}
    entities = result.pop('entity_references')
    for row in entities:
        interface = 'ISketchPoint' if row['kind'] == 'point' else 'ISketchSegment' if row['kind'] == 'segment' else None
        if interface is None:
            _fail('Only complete own linear sketch points/segments can be bound.')
        raw, status = adapter._extension(model).GetObjectByPersistReference3(adapter._persistent_variant(bytes.fromhex(row['pid_hex'])))
        if type(status) is not int or status != 0 or raw is None:
            _fail('Sketch entity persistent reference did not resolve.')
        current = binding.wrap(raw, getattr(adapter._module, interface))
        roles = [key for key, token in members if adapter.identity(current) == token
                 and (key == 'model_origin' or key.startswith('point:') or key.startswith('line:'))]
        if len(roles) != 1:
            _fail('Sketch entity must map bijectively to an exact captured structural role.')
        _pid(adapter, model, current, 'sketch_' + row['kind'], 'sketch:0/' + roles[0], references, interface)
    return result


class CadNativeFirstSaveSnapshotMixin:
    def first_save_part_snapshot(self, model):
        before = self.snapshot(model)
        configuration = before['active_configuration']
        if before['document_type'] != 'part' or before['configurations'] != [configuration]:
            _fail('The complete first-save oracle supports one native part configuration.')
        features = self.features(model)
        feature_identities=tuple(self.identity(feature) for feature in features)
        summaries = [self.feature_summary(feature) for feature in features]
        kinds = [row['feature_type'] for row in summaries]
        if (len(features) > 64 or kinds.count('RefPlane') != 3 or kinds.count('OriginProfileFeature') != 1
                or kinds.count('ProfileFeature') != 1 or sum(kinds.count(k) for k in ('Extrusion', 'Boss')) != 1
                or any(k not in FOLDERS | {'RefPlane', 'OriginProfileFeature', 'ProfileFeature', 'Extrusion', 'Boss'} for k in kinds)
                or any(row['suppressed'] or row['error_code'] for row in summaries)):
            _fail('The initial complete profile is three native planes, origin, rectangular sketch and blind base.')
        bodies = self.bodies(model, 'all')
        body_identities=tuple(self.identity(body) for body in bodies)
        if len(bodies) != 1 or bodies[0].GetType() != 0 or bodies[0].IsMeshBody() is not False:
            _fail('One exact native solid body is required.')
        context = self.dimension_context(model)
        if (context['editing_sketch'] or context['external_reference_count'] or context['equation_count']
                or context['equations_linked'] or context['design_table'] or context['unsafe_feature_types']
                or any(context['configuration_needs_rebuild'].values())):
            _fail('Editing/rebuild/equation/external/design-table controls are unsupported.')
        inventories = self.feature_deletion_context(model)
        equations = inventories['equations']
        if (equations['enumerated_count'] or equations['disabled_count']
                or not equations['disabled_definitions_captured']
                or inventories['external_references']['count'] or inventories['auxiliary_references']['count']):
            _fail('All enabled/disabled equations and external reference inventories must be empty.')
        feature_refs = self.feature_external_references(features)
        if feature_refs['total_reference_rows']:
            _fail('Per-feature external references are not supported by this first-save profile.')
        geometry = self.dimension_geometry_snapshot(model)
        if geometry['representation'] != 'planar_polyhedral_brep_v1':
            _fail('The rectangular-base profile requires a complete planar analytical boundary.')
        native_dimensions = self.dimensions(model, features)
        dimensions = [self.dimension_summary(item, [configuration]) for item in native_dimensions]
        sketch_feature = features[kinds.index('ProfileFeature')]
        original_sketch, _ = self.sketch_snapshot(model, sketch_feature)
        parameters = rectangle_parameters(original_sketch, dict(dimensions=dimensions, context=context, geometry=geometry),
                                          configuration, require_editable=False)
        references = []
        roles = {row['native_id']: 'feature:' + str(index) for index, row in enumerate(summaries)}
        for feature, row in zip(features, summaries):
            if row['feature_type'] not in FOLDERS:
                _pid(self, model, feature, 'feature', roles[row['native_id']], references)
        body = bodies[0]
        _pid(self, model, body, 'body', 'body:0', references)
        _topology(self, model, body, geometry['bodies'][0], references)
        sketch = _sketch(self, model, sketch_feature, roles, references)
        for item, row in zip(native_dimensions, dimensions):
            anchor = self.dimension_persistent_id(model, item)
            resolved = self.resolve_dimension_id(model, anchor)
            if (self.identity(resolved) != self.identity(self.dimension_object(item))
                    or not self.dimension_reference_is_current(model, item, anchor)):
                _fail('Every dimension anchor must round-trip the exact current dimension and owner.')
            references.append(dict(kind='dimension', role='dimension:' + row['full_name'], token=_json(anchor)))
        # Incarnation counters are retained by the session oracle, not treated
        # as persisted CAD parameters. No opaque IDs are generically stripped.
        clone_dimensions = [{key: deepcopy(value) for key, value in row.items() if key != 'owner_update_stamp'} for row in dimensions]
        part = binding.wrap(model, self._module.IPartDoc)
        material = part.GetMaterialPropertyName2(configuration)
        body_material = body.GetMaterialPropertyName(configuration)
        if any(type(value) is not tuple or len(value) != 2 or any(type(v) is not str for v in value)
               for value in (material, body_material)):
            _fail('Complete native model/body material name and database outputs are required.')
        units = _array(model.GetUnits(), 16)
        if not units or any(type(value) not in (int, float, bool) for value in units):
            _fail('The complete native units array is required.')
        clone = dict(profile='single_rectangular_blind_base_v1', features=summaries,
            dependencies=self.feature_dependencies(features), geometry=geometry,
            dimensions=clone_dimensions, sketch=sketch, parameters=parameters,
            extrusion=_extrusion(self, features[next(i for i,k in enumerate(kinds) if k in ('Extrusion','Boss'))]),
            controls={key: deepcopy(value) for key,value in context.items() if key not in ('active_document','read_only')},
            equation_reference_inventory=inventories, feature_external_reference_inventory=feature_refs,
            planes=[dict(role=roles[row['native_id']], transform=[_number(value) for value in self.reference_plane_transform(feature)])
                    for feature,row in zip(features,summaries) if row['feature_type']=='RefPlane'],
            properties=_properties(self, model, configuration), units=units,
            annotations=_annotations(self,model,native_dimensions,references),
            configuration_state=_configuration(self,model,configuration),
            auxiliary_data=_empty_auxiliary_data(self,model,features,summaries),
            material=list(material), body_material=list(body_material),
            body=dict(name=_typed(body.Name,str), visible=_typed(body.Visible,bool)))
        selection = binding.wrap(model.SelectionManager, self._module.ISelectionMgr)
        count = _typed(selection.GetSelectedObjectCount2(-1), int)
        closing_features=tuple(self.identity(feature) for feature in self.features(model))
        closing_bodies=tuple(self.identity(body) for body in self.bodies(model,'all'))
        if (not 0 <= count <= 256 or closing_features!=feature_identities
                or closing_bodies!=body_identities or self.snapshot(model) != before):
            _fail('Native source changed during the complete passive capture.')
        result = dict(scope=SCOPE, configuration=configuration, configurations=[configuration],
            solid_body_count=1, selection_count=count, clone_state=clone,
            references=sorted(references,key=lambda row:(row['kind'],row['role'])))
        _json(result)
        return result
