"""Reference lifetime, foreign targeting, stale snapshots and stable pagination."""

from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import DocumentCatalog, rejected
from solidworks_mcp.geometry import GeometryCatalog
from solidworks_mcp.jobs import ExecutionFailure
from test_document_catalog_v2 import Adapter, model


class GeometryAdapter(Adapter):
    def __init__(self):
        super().__init__()
        self.models = [model(title='Первая'), model(title='Вторая')]
        self.configurations = {(doc.identity, name): object() for doc in self.models
                               for name in doc.state['configurations']}
        self.objects = {doc.identity: [] for doc in self.models}
        self.registry = {}
        self.states = {}
        self.needs_rebuild = False
        self.native_reads = 0
        self.comparisons = 0
        self.change_during_read = None

    def pending_rebuild(self, doc):
        return self.needs_rebuild

    def configuration_identity(self, doc, configuration):
        return self.configurations[doc.identity, configuration]

    def body(self, document_index=0, *, surface=False, faces=3):
        key = len(self.registry)
        body = SimpleNamespace(identity=object(), persistent_id=f'body{key}'.encode(), kind='body',
                               body_type='surface' if surface else 'solid', faces=[], edges=[], body=None)
        self.registry[body.persistent_id] = body
        self.objects[self.models[document_index].identity].append(body)
        for kind, count in [('face', faces), ('edge', 4)]:
            items = body.faces if kind == 'face' else body.edges
            for i in range(count):
                obj = SimpleNamespace(identity=object(), persistent_id=f'{kind}{key}:{i}'.encode(), kind=kind, body=body)
                self.registry[obj.persistent_id] = obj
                items.append(obj)
        return body

    def persistent_id(self, model, obj):
        return obj.persistent_id

    def same_persistent_id(self, model, left, right):
        self.comparisons += 1
        return self.registry[left].identity == self.registry[right].identity

    def resolve_persistent_id(self, model, reference, kind):
        state = self.states.get(reference)
        if state:
            raise rejected(state, 'Native object is unavailable.')
        return self.registry[reference]

    def bodies(self, model, body_type):
        self.native_reads += 1
        if self.change_during_read:
            self.change_during_read()
        return [body for body in self.objects[model.identity] if body_type == 'all' or body.body_type == body_type]

    def topology(self, body, kind):
        self.native_reads += 1
        return list(body.faces if kind == 'face' else body.edges)

    def owner_body(self, obj, kind):
        return obj.body

    def body_is_current(self, model, body):
        return any(candidate.identity == body.identity for candidate in self.objects[model.identity])

    def topology_is_current(self, body, obj, kind):
        return any(candidate.identity == obj.identity for candidate in self.topology(body, kind))

    def geometry_summary(self, obj, kind):
        return {'body_type': obj.body_type} if kind == 'body' else {'area_mm2': 25} if kind == 'face' else {'length_mm': 5}


@pytest.fixture
def setup_geometry():
    adapter = GeometryAdapter()
    adapter.body()
    adapter.body(surface=True)
    adapter.body(document_index=1)
    documents = DocumentCatalog(adapter)
    geometry = GeometryCatalog(documents)
    listed = documents.list()['documents']
    context = {'document_id': listed[0]['document_id'], 'configuration': 'Основная',
               'expected_observation_revision': listed[0]['observation_revision']}
    return adapter, documents, geometry, context, listed


def test_solid_surface_and_selected_body_topology_without_index_ids(setup_geometry):
    adapter, documents, geometry, context, _ = setup_geometry
    bodies = geometry.list(**context)
    assert [obj['body_type'] for obj in bodies['items']] == ['solid', 'surface']
    for body in bodies['items']:
        faces = geometry.list(**context, kind='face', body_id=body['object_id'])
        assert len(faces['items']) == 3
        assert all(obj['body_id'] == body['object_id'] and 'index' not in obj for obj in faces['items'])
        face = faces['items'][0]
        assert geometry.get(**context, object_id=face['object_id'])['object'] == face
    assert geometry.list(**context)['items'] == bodies['items']
    assert len(geometry.list(**context, body_type='surface')['items']) == 1
    assert adapter.comparisons > 0


def test_foreign_document_and_kind_never_fall_back_to_first_body(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    body = geometry.list(**context)['items'][0]['object_id']
    foreign = {**context, 'document_id': listed[1]['document_id'],
               'expected_observation_revision': listed[1]['observation_revision']}
    with pytest.raises(ExecutionFailure) as failure:
        geometry.get(**foreign, object_id=body)
    assert failure.value.code == 'object_reference_not_found'
    face = geometry.list(**context, kind='face', body_id=body)['items'][0]['object_id']
    with pytest.raises(ExecutionFailure) as failure:
        geometry.list(**context, kind='edge', body_id=face)
    assert failure.value.code == 'object_kind_mismatch'


@pytest.mark.parametrize('state', ['object_deleted', 'object_suppressed', 'object_reference_invalid'])
def test_native_stale_reference_state_is_not_success(setup_geometry, state):
    adapter, documents, geometry, context, listed = setup_geometry
    body = geometry.list(**context)['items'][0]['object_id']
    adapter.states[next(iter(adapter.registry))] = state
    with pytest.raises(ExecutionFailure) as failure:
        geometry.get(**context, object_id=body)
    assert failure.value.code == state
    assert failure.value.uncertain is False  # Read-only rejection.


def test_old_token_inactive_configuration_and_rebuild_rejected_before_geometry_read(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    for changed, code in [({**context, 'expected_observation_revision': 'wrong'}, 'observation_revision_mismatch'),
                          ({**context, 'configuration': 'Вариант'}, 'configuration_not_active')]:
        with pytest.raises(ExecutionFailure) as failure:
            geometry.list(**changed)
        assert failure.value.code == code
    adapter.needs_rebuild = True
    with pytest.raises(ExecutionFailure) as failure:
        geometry.list(**context)
    assert failure.value.code == 'document_needs_rebuild'
    assert adapter.native_reads == 0


def test_reference_survives_native_representation_change_and_model_update(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    body_id = geometry.list(**context)['items'][0]['object_id']
    body = adapter.objects[adapter.models[0].identity][0]
    body.persistent_id = b'new_native_representation'
    adapter.registry[body.persistent_id] = body  # Old persistent reference still resolves to this object.
    adapter.models[0].state['update_stamp'] += 1
    context['expected_observation_revision'] = documents.get(context['document_id'], 'Основная')['observation_revision']
    assert geometry.get(**context, object_id=body_id)['object']['object_id'] == body_id


def test_same_named_recreated_configuration_does_not_retarget_old_reference(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    body = geometry.list(**context)['items'][0]['object_id']
    adapter.configurations[adapter.models[0].identity, 'Основная'] = object()
    with pytest.raises(ExecutionFailure) as failure:
        geometry.get(**context, object_id=body)
    assert failure.value.code == 'object_configuration_mismatch'


def test_parent_body_mismatch_is_rejected(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    bodies = geometry.list(**context)['items']
    face = geometry.list(**context, kind='face', body_id=bodies[0]['object_id'])['items'][0]
    adapter.objects[adapter.models[0].identity][0].faces[0].body = adapter.objects[adapter.models[0].identity][1]
    with pytest.raises(ExecutionFailure) as failure:
        geometry.get(**context, object_id=face['object_id'])
    assert failure.value.code == 'object_body_mismatch'


def test_pagination_uses_original_enumeration_without_duplicate_or_missing_faces(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    body_id = geometry.list(**context)['items'][0]['object_id']
    first = geometry.list(**context, kind='face', body_id=body_id, limit=1)
    adapter.objects[adapter.models[0].identity][0].faces.reverse()  # Enumeration order can vary without a model update.
    second = geometry.list(**context, kind='face', body_id=body_id, limit=1, cursor=first['next_cursor'])
    third = geometry.list(**context, kind='face', body_id=body_id, limit=1, cursor=second['next_cursor'])
    assert len({p['items'][0]['object_id'] for p in (first, second, third)}) == 3
    assert third['next_cursor'] is None and third['total_count'] == 3


def test_cursor_cannot_cross_query_revision_or_configuration(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    bodies = geometry.list(**context)['items']
    first = geometry.list(**context, kind='face', body_id=bodies[0]['object_id'], limit=1)
    with pytest.raises(ExecutionFailure) as failure:
        geometry.list(**context, kind='edge', body_id=bodies[0]['object_id'], cursor=first['next_cursor'])
    assert failure.value.code == 'invalid_geometry_cursor'
    adapter.models[0].state['update_stamp'] += 1
    context['expected_observation_revision'] = documents.get(context['document_id'], 'Основная')['observation_revision']
    with pytest.raises(ExecutionFailure) as failure:
        geometry.list(**context, kind='face', body_id=bodies[0]['object_id'], cursor=first['next_cursor'])
    assert failure.value.code == 'stale_geometry_cursor'


def test_document_changed_during_read_is_not_success(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    adapter.change_during_read = lambda: adapter.models[0].state.update(update_stamp=4)
    with pytest.raises(ExecutionFailure) as failure:
        geometry.list(**context)
    assert failure.value.code == 'document_changed_during_read'


def test_unsupported_native_reference_does_not_get_index_fallback(setup_geometry, monkeypatch):
    adapter, documents, geometry, context, listed = setup_geometry
    monkeypatch.setattr(adapter, 'persistent_id', lambda *args: b'')
    with pytest.raises(ExecutionFailure) as failure:
        geometry.list(**context)
    assert failure.value.code == 'persistent_reference_unavailable'


def test_registered_reference_must_resolve_to_the_same_native_object(setup_geometry, monkeypatch):
    adapter, documents, geometry, context, listed = setup_geometry
    monkeypatch.setattr(adapter, 'resolve_persistent_id', lambda *args: adapter.objects[adapter.models[1].identity][0])
    with pytest.raises(ExecutionFailure) as failure:
        geometry.list(**context)
    assert failure.value.code == 'persistent_reference_mismatch'


@pytest.mark.parametrize('limit', [0, 201, True])
def test_bounded_page_limit_checked_before_native_reads(setup_geometry, limit):
    adapter, documents, geometry, context, listed = setup_geometry
    with pytest.raises(ExecutionFailure) as failure:
        geometry.list(**context, limit=limit)
    assert failure.value.code == 'invalid_limit'
    assert adapter.native_reads == 0


def test_stale_cursor_releases_native_snapshot_when_revision_changes(setup_geometry):
    adapter, documents, geometry, context, _ = setup_geometry
    body_id = geometry.list(**context)['items'][0]['object_id']
    page = geometry.list(**context, kind='face', body_id=body_id, limit=1)
    entry = documents.resolve(context['document_id'], 'Основная')[0]
    cursor = entry.geometry['cursors'][page['next_cursor']]
    assert len(cursor.objects) == 3
    adapter.models[0].state['update_stamp'] += 1
    with pytest.raises(ExecutionFailure):
        geometry.list(**context, kind='face', body_id=body_id, cursor=page['next_cursor'])
    assert cursor.objects == ()


@pytest.mark.parametrize('native_status,expected', [(0, False), (1, True), (2, False)])
def test_native_persistent_equality_unsupported_is_not_same(native_status, expected):
    from solidworks_mcp.cad_geometry import CadGeometryMixin
    class NativeAdapter(CadGeometryMixin):
        def _extension(self, model):
            return SimpleNamespace(IsSamePersistentID=lambda a, b: native_status)
    assert NativeAdapter().same_persistent_id(None, b'a', b'b') is expected


def test_native_success_for_body_absent_in_active_configuration_is_rejected(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    surface_id = geometry.list(**context)['items'][1]['object_id']
    face_id = geometry.list(**context, kind='face', body_id=surface_id)['items'][0]['object_id']
    adapter.objects[adapter.models[0].identity].pop()  # API still returns old body/face with status=OK.
    for object_id in (surface_id, face_id):
        with pytest.raises(ExecutionFailure) as failure:
            geometry.get(**context, object_id=object_id)
        assert failure.value.code == 'object_not_in_active_configuration'


def test_native_success_for_detached_face_is_rejected(setup_geometry):
    adapter, documents, geometry, context, listed = setup_geometry
    body_id = geometry.list(**context)['items'][0]['object_id']
    face_id = geometry.list(**context, kind='face', body_id=body_id)['items'][0]['object_id']
    adapter.objects[adapter.models[0].identity][0].faces.pop(0)  # Old face still reports same owner body.
    with pytest.raises(ExecutionFailure) as failure:
        geometry.get(**context, object_id=face_id)
    assert failure.value.code == 'object_not_in_current_body'
