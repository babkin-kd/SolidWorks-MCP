"""Whole passive first-save oracle on complete artificial native inventories.

Only binding.wrap is replaced at the fake/native boundary. The real oracle,
rectangle classifier, linear-sketch reader and PID/topology checks execute.
These cases do not constitute installed-wheel, Win32 or SolidWorks acceptance.
"""

from copy import deepcopy
from itertools import combinations, product
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import cad_native_first_save_snapshot as oracle
from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.linear_sketch import LinearSketchReader
from test_linear_sketch_v2 import Sketch
from test_part_creation_v2 import IDENTITY


def hex_vector(values):
    return [float(value).hex() for value in values]


class FakeAnnotationView:
    Always2D, FlatPatternView, UnassignedView = False, False, False
    AngleMadeWithViewHorizontal = 0.

    def __init__(self, adapter, name):
        self.adapter, self.Name = adapter, name

    @property
    def AnnotationCount(self): return self.adapter.read('view_annotation_count:' + self.Name, 0)
    @property
    def Annotations(self): return self.adapter.read('view_annotations:' + self.Name, [])
    def IsShown(self): return self.adapter.read('view_shown:' + self.Name, False)
    def GetViewRotation(self): return self.adapter.read('view_rotation:' + self.Name, list(IDENTITY[:9]))


class FakeExtension(NS):
    @property
    def AnnotationViewCount(self): return self.adapter.read('view_count', len(self.adapter.annotation_views))
    @property
    def AnnotationViews(self): return self.adapter.read('views', self.adapter.annotation_views[:])


class FakeWatch:
    def __init__(self, adapter):
        self.adapter, self.closed = adapter, False
        self.polls = 0

    def poll(self):
        assert not self.closed
        self.polls += 1
        self.adapter.calls.append('watch_poll')
        if self.adapter.fault == 'monitor_stopped':
            raise ExecutionFailure('revision_monitor_stopped', 'Artificial monitor unavailable.', uncertain=False)
        return self.adapter.event_sequence

    def close(self):
        assert not self.closed, 'Each capture must release its owned monitor exactly once'
        self.closed = True
        self.adapter.calls.append('watch_close')


class CaptureAdapter(oracle.CadNativeFirstSaveSnapshotMixin):
    """One native-shaped fake part, complete supported data and no write API."""

    def __init__(self):
        self.calls = []
        self.fault = None
        self.counters = {}
        self.event_sequence = 0
        self.watches = []
        self.model_identity_override = None
        names = ('IPartDoc', 'IVertex', 'IEdge', 'IExtrudeFeatureData2',
                 'ICustomPropertyManager', 'ISketchPoint', 'ISketchSegment',
                 'IAnnotation', 'ITextFormat', 'IConfiguration',
                 'ICommentFolder', 'ISelectionSetFolder', 'ISelectionMgr', 'IAnnotationView', 'IFeature')
        self._module = NS(**{name: object() for name in names})
        self.objects = {}
        self.configuration = self.make_configuration()
        self.state = dict(document_type='part', active_configuration='Основная',
                          configurations=['Основная'], needs_save=True,
                          read_only=False, update_stamp=17)
        self.context = dict(active_document=True, read_only=False,
            editing_sketch=False, external_reference_count=0, equation_count=0,
            equations_linked=False, design_table=False, unsafe_feature_types=[],
            configuration_needs_rebuild={'Основная': False})
        self.inventory = dict(equations=dict(enumerated_count=0, disabled_count=0,
            disabled_definitions_captured=True), external_references=dict(count=0),
            auxiliary_references=dict(count=0))
        self.comment_count, self.comments = -1, None
        self.global_annotations = None  # Feature-owned dimensions are separate.
        self.attachments = (None, None)  # Independent native names/linked outputs.
        self.feature_rows = []
        for index, (name, kind) in enumerate((
                ('Спереди', 'RefPlane'), ('Сверху', 'RefPlane'), ('Справа', 'RefPlane'),
                ('Начало координат', 'OriginProfileFeature'), ('Эскиз основания', 'ProfileFeature'),
                ('Основание', 'Boss'), ('Комментарии', 'CommentsFolder'),
                ('Наборы выбора', 'SelectionSetFolder'), ('Аннотации', 'DetailCabinet'),
                ('Виды аннотаций', 'NotesAreaFtrFolder'), ('Не назначено', 'NotesAreaFtrFolder'),
                ('Свет и камеры', 'EnvFolder'), ('Окружающий свет', 'AmbientLight'),
                ('Направленный свет 1', 'DirectionLight'), ('Направленный свет 2', 'DirectionLight'),
                ('Направленный свет 3', 'DirectionLight'))):
            obj = self.register(NS(), f'feature:{index}')
            obj.row = dict(native_id=index, name=name, feature_type=kind,
                           suppressed=False, error_code=0,
                           owner_native_id=5 if kind == 'ProfileFeature' else None)
            if kind == 'NotesAreaFtrFolder': obj.row['owner_native_id'] = 8
            elif kind in ('AmbientLight', 'DirectionLight'): obj.row['owner_native_id'] = 11
            obj.GetDefinition = lambda: self.extrude_definition()
            obj.GetSpecificFeature2 = (lambda feature=obj: NS(
                GetCommentCount=lambda: self.read('comment_count', self.comment_count),
                GetComments=lambda: self.read('comments', self.comments),
                GetFeature=lambda: self.read('comment_owner', feature))) if kind == 'CommentsFolder' else (
                lambda: NS(GetSelectionSets=lambda: self.read('selection_sets', [])))
            self.feature_rows.append(obj)
        self.body = self.register(NS(Name='Тело основания', Visible=True,
            GetType=lambda: 0, IsMeshBody=lambda: False,
            GetMaterialPropertyName=lambda cfg: ('', '')), 'body:0')
        self.vertices, self.edges, self.faces, self.geometry = self.make_geometry()
        self.sketch = Sketch()
        for index, item in enumerate((*self.sketch.points, self.sketch.projected,
                                      self.sketch.origin, *self.sketch.lines)):
            self.register(item, f'sketch:{index}')
        self.dimension_rows = []
        self.annotations = []
        for index, (name, value, owner) in enumerate((
                ('D1@Основание', .04, self.feature_rows[4]),
                ('D2@Основание', .02, self.feature_rows[4]),
                ('D1@Выдавливание', .01, self.feature_rows[5]))):
            annotation = self.register(NS(
                GetName=lambda i=index: f'Размер {i + 1}', GetType=lambda: 4,
                Visible=1, GetPosition=lambda i=index: [float(i), 0., 0.]), f'annotation:{index}')
            self.annotations.append(annotation)
            display = NS(GetAnnotation=lambda a=annotation: a,
                GetTextFormat=lambda: NS(GetAllValues=lambda: ['Arial', .0035, False]),
                Type2=(11, 12, 0)[index], GetText=lambda part: '',
                GetUseDocTextFormat=lambda: True)
            row = self.register(NS(displays=[display]), f'dimension:{index}')
            row.summary = dict(full_name=name, owner=deepcopy(owner.row), unit='mm',
                values_si={'Основная': value}, driven_state=2, reference=False,
                linked=False, design_table=False, read_only=False,
                write_blockers=[], owner_update_stamp=17)
            self.dimension_rows.append(row)
        self.annotation_views = [FakeAnnotationView(self, 'Виды аннотаций'), FakeAnnotationView(self, 'Не назначено')]
        self.light_rows = [dict(native_name='Ambient' if index == 0 else f'Directional-{index}',
            user_name=self.feature_rows[12 + index].row['name'], values=tuple(float(i) / 20 for i in range(19)),
            locked=True) for index in range(4)]
        self.extension = FakeExtension(adapter=self, CustomPropertyManager=self.property_manager,
            GetObjectByPersistReference3=self.resolve_raw,
            GetAnnotationCount=lambda: self.read('annotation_count', len(self.global_annotations or [])),
            GetAnnotations=lambda: self.read('annotations', self.global_annotations),
            GetAttachmentCount=lambda: self.read('attachment_count', 0),
            GetAttachments=lambda: self.read('attachments', self.attachments))
        self.model = NS(GetConfigurationByName=lambda name: self.configuration if name == 'Основная' else None,
            GetMaterialPropertyName2=lambda cfg: ('', ''),
            GetUnits=lambda: self.read('units', [0, 0, 0, 0, False]),
            GetLightSourceCount=lambda: self.read('light_count', len(self.light_rows)),
            GetLightSourceName=lambda index: self.read(f'light_native_name:{index}', self.light_rows[index]['native_name']),
            LightSourceUserName=lambda index: self.read(f'light_user_name:{index}', self.light_rows[index]['user_name']),
            LightSourcePropertyValues=lambda index: self.read(f'light_values:{index}', self.light_rows[index]['values']),
            IsLightLockedToModel=lambda index: self.read(f'light_locked:{index}', self.light_rows[index]['locked']),
            SelectionManager=NS(GetSelectedObjectCount2=lambda mark: 0))

    def read(self, name, value):
        self.calls.append(name)
        self.counters[name] = self.counters.get(name, 0) + 1
        if self.fault == 'annotations_changed' and name == 'annotations' and self.counters[name] == 2:
            return [*(value or [])[:-1], NS()]
        if self.fault == 'properties_changed' and name == 'property_names:' and self.counters[name] == 2:
            return ['Подменённое свойство']
        if self.fault == 'configuration_changed' and name == 'parameter_count' and self.counters[name] == 2:
            return 2
        if self.fault == 'units_missing' and name == 'units': return []
        if self.fault == 'annotations_missing' and name == 'annotation_count': return 3
        if self.fault == 'annotations_missing' and name == 'annotations': return self.annotations[:2]
        if self.fault == 'attachments' and name == 'attachment_count': return 1
        if self.fault == 'comments' and name == 'comment_count': return 1
        if self.fault == 'comments_changed' and name == 'comment_count' and self.counters[name] == 2: return 0
        if self.fault == 'comment_owner' and name == 'comment_owner': return self.feature_rows[0]
        if self.fault == 'lights_missing' and name == 'light_count': return value - 1
        if self.fault == 'lights_changed' and name == 'light_count' and self.counters[name] == 2: return value - 1
        if self.fault == 'light_values_missing' and name == 'light_values:0': return value[:-1]
        if self.fault == 'light_values_nonfinite' and name == 'light_values:0': return (float('nan'), *value[1:])
        if self.fault == 'light_name_mismatch' and name == 'light_user_name:0': return 'Чужой свет'
        if self.fault == 'light_duplicate_name' and name == 'light_user_name:1': return self.light_rows[0]['user_name']
        if self.fault == 'views_missing' and name == 'views': return value[:-1]
        if self.fault == 'views_changed' and name == 'views' and self.counters[name] == 2:
            return [value[0], FakeAnnotationView(self, value[1].Name)]
        if self.fault == 'view_count_changed' and name == 'view_count' and self.counters[name] == 2: return value - 1
        if self.fault == 'view_nonempty' and name.startswith('view_annotation_count:'): return 1
        if self.fault == 'view_unknown_annotation' and name.startswith('view_annotations:'): return [self.annotations[0]]
        if self.fault == 'view_rotation_missing' and name.startswith('view_rotation:'): return value[:-1]
        if name == 'view_count' and self.counters[name] == 2:
            if self.fault == 'event_change': self.event_sequence += 1
            elif self.fault == 'event_aba':
                # Both edits restore their semantic field but leave two events.
                self.state['update_stamp'] += 1
                self.event_sequence += 1
                self.state['update_stamp'] -= 1
                self.event_sequence += 1
            elif self.fault == 'replaced_configuration':
                self.configuration = deepcopy(self.configuration)
            elif self.fault == 'replaced_model':
                self.model_identity_override = object()
        return value

    def register(self, obj, token):
        obj.pid = token.encode()
        self.objects[obj.pid] = obj
        return obj

    def identity(self, obj):
        return id(self.model_identity_override) if obj is getattr(self, 'model', None) and self.model_identity_override is not None else id(obj)
    def configuration_identity(self, model, name):
        self.calls.append('configuration_identity')
        assert name == 'Основная'
        return self.identity(model.GetConfigurationByName(name))
    def watch_part(self, model):
        assert model is self.model
        self.calls.append('watch_attach')
        if self.fault == 'monitor_unavailable':
            raise ExecutionFailure('revision_monitor_unavailable', 'Artificial attach unavailable.', uncertain=False)
        watch = FakeWatch(self)
        self.watches.append(watch)
        return watch
    def persistent_id(self, model, obj):
        self.calls.append('persistent_id')
        if self.fault == 'missing_pid' and obj is self.feature_rows[0]: return b''
        return obj.pid
    def resolve_persistent_id(self, model, token, kind):
        self.calls.append('resolve_pid')
        if self.fault == 'wrong_pid' and token == self.feature_rows[0].pid: return self.feature_rows[1]
        return self.objects[token]
    def _persistent_variant(self, token): return token
    def resolve_raw(self, token):
        self.calls.append('resolve_raw_pid')
        if self.fault == 'sketch_pid' and token.startswith(b'sketch:'): return None, 1
        return self.objects[token], 0
    def _extension(self, model): return self.extension

    def snapshot(self, model):
        result = self.read('snapshot', deepcopy(self.state))
        if self.fault == 'snapshot_changed' and self.counters['snapshot'] == 2:
            result['update_stamp'] += 1
        return result
    def features(self, model):
        values = self.read('features', self.feature_rows[:])
        return values[:-1] if self.fault == 'features_changed' and self.counters['features'] == 2 else values
    def bodies(self, model, kind):
        values = self.read('bodies', [self.body])
        return [] if self.fault == 'bodies_changed' and self.counters['bodies'] == 2 else values
    def feature_summary(self, obj): return deepcopy(obj.row)
    def dimension_context(self, model): return deepcopy(self.context)
    def feature_deletion_context(self, model): return deepcopy(self.inventory)
    def feature_external_references(self, features): return dict(total_reference_rows=0, rows=[])
    def feature_dependencies(self, features):
        return [{'parent': 0, 'child': 4}, {'parent': 4, 'child': 5}]
    def dimension_geometry_snapshot(self, model): return deepcopy(self.geometry)
    def dimensions(self, model, features): return self.dimension_rows[:]
    def dimension_summary(self, item, configurations): return deepcopy(item.summary)
    def dimension_persistent_id(self, model, item): return dict(strategy='direct_dimension_v1', dimension_pid_hex=item.pid.hex())
    def resolve_dimension_id(self, model, anchor):
        if self.fault == 'dimension_pid': return self.dimension_rows[-1]
        return self.objects[bytes.fromhex(anchor['dimension_pid_hex'])]
    def dimension_object(self, item): return item
    def dimension_reference_is_current(self, model, item, anchor): return True
    def reference_plane_transform(self, feature): return IDENTITY[:]
    def topology(self, body, kind):
        objects = self.edges if kind == 'edge' else self.faces
        return objects[:-1] if self.fault == 'topology_missing' and kind == 'face' else objects[:]
    def owner_body(self, obj, kind): return self.body

    def sketch_snapshot(self, model, feature):
        snapshot, members = LinearSketchReader(self.sketch, self.sketch.origin,
            wrap=lambda raw, name: raw, identity=self.identity).read()
        member_objects = {self.identity(obj): obj for obj in (
            *self.sketch.points, self.sketch.projected, self.sketch.origin, *self.sketch.lines)}
        snapshot.update(feature_native_id=4, feature_pid_hex=feature.pid.hex(),
            reference_plane=dict(native_id=0, pid_hex=self.feature_rows[0].pid.hex(), transform=hex_vector(IDENTITY)),
            model_origin=dict(feature_native_id=3, pid_hex=self.feature_rows[3].pid.hex()),
            model_to_sketch=hex_vector(IDENTITY), entity_references=[
                dict(kind='segment' if role.startswith('line:') else 'point', pid_hex=member_objects[token].pid.hex())
                for role, token in members if token in member_objects])
        return snapshot, members

    def property_manager(self, configuration):
        name = 'Описание' if not configuration else 'Обозначение'
        manager = NS(Count=1,
            GetNames=lambda: self.read('property_names:' + configuration, [name]),
            GetType2=lambda field: 30,
            Get6=lambda field, cached: self.cached_property(field, cached))
        return manager
    def cached_property(self, name, cached):
        assert cached is True, 'Passive capture must never evaluate uncached properties'
        self.calls.append('cached_property')
        return 0, 'Контрольная деталь', 'Контрольная деталь', True, False

    def make_configuration(self):
        values = dict(Name='Основная', Description='Основная конфигурация', Comment='', AlternateName='',
            BOMPartNoSource=0, Type=0, Lock=False, UseAlternateNameInBOM=False,
            UseDescriptionInBOM=False, SuppressNewFeatures=False, HideNewComponentModels=False,
            SuppressNewComponentModels=False, RepresentationShared=False,
            GetParameterCount=lambda: self.read('parameter_count', 1),
            GetParameters=lambda: (['Параметр'], ['Значение']),
            GetDisplayStates=lambda: ['Состояние отображения 1'],
            GetDisplayStatesCount=lambda: 1, GetChildrenCount=lambda: 0)
        return NS(**values)

    def extrude_definition(self):
        values = {name: False for name in ('BothDirections', 'ReverseDirection', 'FeatureScope',
            'AutoSelect', 'FromOffsetReverse', 'FlipSideToCut', 'NormalCut', 'LinkToThickness', 'CapEnds')}
        values.update(Merge=True, FromType=0, ThinWallType=0, FromOffsetDistance=0., CapThickness=0.,
            IsThinFeature=lambda: False, GetContoursCount=lambda: 0,
            GetEndCondition=lambda forward: 0, GetDepth=lambda forward: .01 if forward else 0.,
            GetDraftAngle=lambda forward: 0., GetDraftWhileExtruding=lambda forward: False,
            GetDraftOutward=lambda forward: False, GetReverseOffset=lambda forward: False,
            GetTranslateSurface=lambda forward: False, GetWallThickness=lambda forward: 0.)
        return NS(**values)

    def make_geometry(self):
        xyz = list(product((0., .04), (0., .02), (0., .01)))
        vertices = [NS(GetPoint=lambda value=value: list(value)) for value in xyz]
        pairs = [(a, b) for a, b in combinations(range(8), 2)
                 if sum(x != y for x, y in zip(xyz[a], xyz[b])) == 1]
        edges = [self.register(NS(GetStartVertex=lambda a=a: vertices[a],
                    GetEndVertex=lambda b=b: vertices[b]), f'edge:{index}')
                 for index, (a, b) in enumerate(pairs)]
        faces, boundary_faces = [], []
        for axis in range(3):
            for coordinate in (0., (.04, .02, .01)[axis]):
                indices = [i for i, point in enumerate(xyz) if point[axis] == coordinate]
                # Binary-order plane vertices 0,1,3,2 form an oriented perimeter.
                ring = [indices[i] for i in (0, 1, 3, 2)]
                edge_ids = [index for index, pair in enumerate(pairs) if set(pair) <= set(ring)]
                faces.append(self.register(NS(GetEdges=lambda ids=edge_ids: [edges[i] for i in ids]), f'face:{len(faces)}'))
                boundary_faces.append(dict(loops=[dict(coedges=[
                    dict(start=a, end=b) for a, b in zip(ring, ring[1:] + ring[:1])])]))
        geometry = dict(representation='planar_polyhedral_brep_v1', bodies=[dict(
            vertices=[hex_vector(point) for point in xyz],
            edges=[dict(start=a, end=b) for a, b in pairs], faces=boundary_faces)])
        return vertices, edges, faces, geometry


@pytest.fixture
def capture(monkeypatch):
    # Native boundary only: never replace the real oracle's component helpers.
    monkeypatch.setattr(oracle.binding, 'wrap', lambda raw, interface: raw)
    monkeypatch.setattr(oracle.binding, 'queried', lambda raw, interface: raw)
    return CaptureAdapter()


def test_full_supported_capture_covers_geometry_data_controls_and_exact_references(capture):
    result = capture.first_save_part_snapshot(capture.model)
    assert result['scope'] == oracle.SCOPE and result['configuration'] == 'Основная'
    assert result['solid_body_count'] == 1 and result['selection_count'] == 0
    clone = result['clone_state']
    assert clone['parameters']['width_m'] == .04 and clone['parameters']['height_m'] == .02
    assert clone['parameters']['depth_m'] == .01
    assert len(clone['features']) == 16 and len(clone['planes']) == 3
    assert len(clone['dimensions']) == 3 and len(clone['annotations']) == 3
    assert all('owner_update_stamp' not in item for item in clone['dimensions'])
    assert len(clone['sketch']['relations']) == 7
    assert clone['properties'][''][0]['name'] == 'Описание'
    assert clone['properties']['Основная'][0]['name'] == 'Обозначение'
    assert clone['configuration_state']['parameters'] == [('Параметр', 'Значение')]
    assert clone['auxiliary_data'] == dict(attachments=0, comments=0, named_selection_sets=0)
    assert clone['body'] == dict(name='Тело основания', visible=True)
    display = clone['display_data']
    assert len(display['lights']) == 4 and len(display['annotation_views']) == 2
    assert [item['user_name'] for item in display['lights']] == [item['user_name'] for item in capture.light_rows]
    assert all(item['values'] == hex_vector(capture.light_rows[index]['values'])
               and item['locked_to_model'] is True for index, item in enumerate(display['lights']))
    assert all(item['rotation'] == hex_vector(IDENTITY[:9]) and item['annotation_count'] == 0
               for item in display['annotation_views'])
    references = result['references']
    assert len(references) == 41  # 6 features + body + 12 edges + 6 faces + 10 sketch entities + 3 dimensions + 3 annotations
    assert {kind: sum(row['kind'] == kind for row in references) for kind in (
        'feature', 'body', 'edge', 'face', 'sketch_point', 'sketch_segment', 'dimension', 'annotation')} == {
        'feature': 6, 'body': 1, 'edge': 12, 'face': 6, 'sketch_point': 6, 'sketch_segment': 4, 'dimension': 3, 'annotation': 3}
    assert len({(row['kind'], row['role']) for row in references}) == len(references)


def test_whole_double_capture_is_detached_stable_and_does_not_change_native_state(capture):
    before = deepcopy((capture.state, capture.context, capture.inventory, capture.geometry))
    first = capture.first_save_part_snapshot(capture.model)
    second = capture.first_save_part_snapshot(capture.model)
    assert first == second
    assert (capture.state, capture.context, capture.inventory, capture.geometry) == before
    first['clone_state']['features'][0]['name'] = 'Локальное изменение результата'
    assert second['clone_state']['features'][0]['name'] == 'Спереди'
    assert capture.feature_rows[0].row['name'] == 'Спереди'


def test_readonly_inactive_reader_uses_cached_passive_capture_without_write_authority(capture):
    capture.context.update(active_document=False, read_only=True)
    capture.state['read_only'] = True
    for item in capture.dimension_rows:
        item.summary['read_only'] = True
        item.summary['write_blockers'] = ['read_only']
    before = deepcopy((capture.state, capture.context, [item.summary for item in capture.dimension_rows]))
    result = capture.first_save_part_snapshot(capture.model)
    assert result['clone_state']['parameters']['width_m'] == .04
    assert 'active_document' not in result['clone_state']['controls']
    assert 'read_only' not in result['clone_state']['controls']
    assert (capture.state, capture.context, [item.summary for item in capture.dimension_rows]) == before
    # The fake exposes only read APIs: a hidden activation/rebuild/selection/
    # write invocation would raise AttributeError instead of silently succeeding.
    assert capture.calls.count('cached_property') == 2


@pytest.mark.parametrize('fault', ['missing_pid', 'wrong_pid', 'sketch_pid', 'dimension_pid',
    'topology_missing', 'annotations_missing', 'units_missing', 'attachments', 'comments',
    'annotations_changed', 'properties_changed', 'configuration_changed',
    'features_changed', 'bodies_changed', 'snapshot_changed'])
def test_whole_capture_rejects_missing_or_changed_inventory_and_noncurrent_pid(capture, fault):
    capture.fault = fault
    before = deepcopy(capture.state)
    with pytest.raises(ExecutionFailure):
        capture.first_save_part_snapshot(capture.model)
    assert capture.state == before


@pytest.mark.parametrize('unsupported', ['equations', 'external', 'suppressed_feature', 'extra_body', 'configuration'])
def test_full_capture_rejects_unsupported_source_before_returning_partial_oracle(capture, unsupported):
    if unsupported == 'equations': capture.inventory['equations']['disabled_count'] = 1
    elif unsupported == 'external': capture.context['external_reference_count'] = 1
    elif unsupported == 'suppressed_feature': capture.feature_rows[5].row['suppressed'] = True
    elif unsupported == 'extra_body': capture.bodies = lambda model, kind: [capture.body, capture.body]
    else: capture.state['configurations'].append('Вторая конфигурация')
    with pytest.raises(ExecutionFailure): capture.first_save_part_snapshot(capture.model)


@pytest.mark.parametrize('fault', [
    'lights_missing', 'lights_changed', 'light_values_missing', 'light_values_nonfinite',
    'light_name_mismatch', 'light_duplicate_name', 'views_missing', 'views_changed',
    'view_count_changed', 'view_nonempty', 'view_unknown_annotation', 'view_rotation_missing',
])
def test_whole_capture_rejects_incomplete_changed_lights_and_annotation_views(capture, fault):
    capture.fault = fault
    before = deepcopy(capture.state)
    with pytest.raises(ExecutionFailure) as error:
        capture.first_save_part_snapshot(capture.model)
    assert error.value.code == 'first_save_snapshot_unsupported'
    assert capture.state == before


@pytest.mark.parametrize('change', ['light_values', 'annotation_view_angle'])
def test_whole_capture_exposes_display_state_changes_for_domain_double_read(capture, change):
    before = capture.first_save_part_snapshot(capture.model)
    if change == 'light_values':
        capture.light_rows[0]['values'] = (0.9, *capture.light_rows[0]['values'][1:])
    else:
        capture.annotation_views[0].AngleMadeWithViewHorizontal = 0.125
    after = capture.first_save_part_snapshot(capture.model)
    assert before['clone_state']['display_data'] != after['clone_state']['display_data']
    # It is the domain's paired capture that rejects a changed complete state;
    # a single passive read must report actual values instead of inventing zeros.
    assert before['references'] == after['references']


@pytest.mark.parametrize('count', [0, 1, 2, 3])
def test_complete_global_annotation_subset_preserves_all_feature_owned_displays(capture, count):
    capture.global_annotations = capture.annotations[:count] if count else None
    result = capture.first_save_part_snapshot(capture.model)
    assert len(result['clone_state']['annotations']) == 3
    assert sum(row['kind'] == 'annotation' for row in result['references']) == 3
    assert all(row['token'] in {item.pid.hex() for item in capture.annotations}
               for row in result['references'] if row['kind'] == 'annotation')


@pytest.mark.parametrize('fault', ['unknown_global', 'duplicate_global', 'changed_global_count'])
def test_global_annotation_census_still_rejects_unknown_duplicate_or_changing_rows(capture, fault):
    if fault == 'unknown_global': capture.global_annotations = [NS()]
    elif fault == 'duplicate_global': capture.global_annotations = [capture.annotations[0]] * 2
    else:
        capture.extension.GetAnnotationCount = lambda: capture.read('count_drift', 0) + (capture.counters['count_drift'] > 1)
    with pytest.raises(ExecutionFailure): capture.first_save_part_snapshot(capture.model)


@pytest.mark.parametrize('count', [0, -1])
@pytest.mark.parametrize('empty', [None, []])
def test_empty_comments_sentinel_requires_complete_empty_array_and_exact_folder_owner(capture, count, empty):
    capture.comment_count, capture.comments = count, empty
    result = capture.first_save_part_snapshot(capture.model)
    assert result['clone_state']['auxiliary_data']['comments'] == 0
    assert capture.calls.count('comment_count') == 2 and capture.calls.count('comments') == 2
    assert capture.calls.count('comment_owner') == 1


@pytest.mark.parametrize('fault', ['unsupported_minus_two', 'nonempty_minus_one', 'comments_changed', 'comment_owner'])
def test_comments_sentinel_never_hides_unobserved_or_changed_data(capture, fault):
    if fault == 'unsupported_minus_two': capture.comment_count = -2
    elif fault == 'nonempty_minus_one': capture.comments = [NS()]
    else: capture.fault = fault
    with pytest.raises(ExecutionFailure): capture.first_save_part_snapshot(capture.model)


@pytest.mark.parametrize('outputs', [(None, None), ([], [])])
def test_both_independent_attachment_arrays_must_be_proven_empty(capture, outputs):
    capture.attachments = outputs
    assert capture.first_save_part_snapshot(capture.model)['clone_state']['auxiliary_data']['attachments'] == 0


@pytest.mark.parametrize('outputs', [(None,), None, [], (['foreign'], None), (None, [True])])
def test_missing_attachment_output_or_nonempty_either_column_rejected(capture, outputs):
    capture.attachments = outputs
    with pytest.raises(ExecutionFailure): capture.first_save_part_snapshot(capture.model)


def test_each_whole_capture_owns_and_closes_its_independent_event_watch(capture):
    first = capture.first_save_part_snapshot(capture.model)
    second = capture.first_save_part_snapshot(capture.model)
    assert first == second and len(capture.watches) == 2
    assert all(watch.closed and watch.polls == 2 for watch in capture.watches)
    events = [call for call in capture.calls if call.startswith('watch_')]
    assert events == ['watch_attach', 'watch_poll', 'watch_poll', 'watch_close'] * 2


@pytest.mark.parametrize('fault,events', [('event_change', 1), ('event_aba', 2)])
def test_event_envelope_rejects_intervening_change_even_with_same_complete_semantic_state(capture, fault, events):
    capture.fault = fault
    original = deepcopy(capture.state)
    with pytest.raises(ExecutionFailure): capture.first_save_part_snapshot(capture.model)
    assert capture.state == original and capture.event_sequence == events
    assert len(capture.watches) == 1 and capture.watches[0].closed
    assert capture.watches[0].polls == 2
    assert capture.calls[-1] == 'watch_close'


def test_equal_named_configuration_replacement_cannot_pass_canonical_capture_envelope(capture):
    capture.fault = 'replaced_configuration'
    original = capture.configuration
    with pytest.raises(ExecutionFailure): capture.first_save_part_snapshot(capture.model)
    assert capture.configuration is not original
    assert capture.configuration.Name == original.Name == 'Основная'
    assert capture.event_sequence == 0
    assert len(capture.watches) == 1 and capture.watches[0].closed


def test_replaced_canonical_model_identity_rejected_despite_equal_snapshot(capture):
    original = deepcopy(capture.state)
    capture.fault = 'replaced_model'
    with pytest.raises(ExecutionFailure): capture.first_save_part_snapshot(capture.model)
    assert capture.state == original and capture.model_identity_override is not None
    assert capture.event_sequence == 0 and capture.watches[0].closed


@pytest.mark.parametrize('fault', ['monitor_stopped', 'units_missing', 'wrong_pid'])
def test_owned_watch_always_closed_after_monitor_or_inner_capture_rejection(capture, fault):
    capture.fault = fault
    with pytest.raises(ExecutionFailure): capture.first_save_part_snapshot(capture.model)
    assert len(capture.watches) == 1 and capture.watches[0].closed
    assert capture.calls[-1] == 'watch_close'
    assert capture.state['needs_save'] is True


def test_unavailable_event_monitor_rejects_before_any_full_capture_or_write(capture):
    capture.fault = 'monitor_unavailable'
    with pytest.raises(ExecutionFailure) as error:
        capture.first_save_part_snapshot(capture.model)
    assert error.value.code == 'revision_monitor_unavailable'
    assert capture.watches == [] and 'features' not in capture.calls and 'cached_property' not in capture.calls
    assert capture.state['needs_save'] is True
