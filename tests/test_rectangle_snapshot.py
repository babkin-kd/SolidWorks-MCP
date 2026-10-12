"""Complete empty-target observation with artificial native getters; no CAD."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import binding, cad_rectangle_snapshot as native
from solidworks_mcp.cad_rectangle_snapshot import CadRectangleSnapshotMixin
from solidworks_mcp.rectangle_snapshot import validated_rectangle_snapshot
from solidworks_mcp.jobs import ExecutionFailure, JobError
from test_part_creation_v2 import IDENTITY


class Feature:
    def __init__(self, identifier, kind, specific=None):
        self.identifier, self.kind, self.specific = identifier, kind, specific
    def GetSpecificFeature2(self): return self.specific


class Adapter(CadRectangleSnapshotMixin):
    _module = NS(IPartDoc=object, ISelectionMgr=object, ISketch=object, ISketchPoint=object)
    def __init__(self):
        self.point = NS(GetID=lambda: (0, 0), Type=1, Status=2, X=0., Y=0., Z=0.)
        self.items = [Feature(i, 'RefPlane') for i in range(3)] + [Feature(3,
            'OriginProfileFeature', NS(GetSketchPoints2=lambda: [self.point]))]
        self.objects = {str(i).encode(): obj for i, obj in enumerate([*self.items, self.point])}
        self.metadata = dict(title='Контрольная деталь', path='', document_type='part',
            active_configuration='Основная', configurations=['Основная'], needs_save=True, update_stamp=1)
        self.cfg = object()
        self.context = dict(active_document=True, read_only=False, editing_sketch=False,
            external_reference_count=0, equation_count=0, equations_linked=False,
            design_table=False, unsafe_feature_types=[], configuration_needs_rebuild={'Основная': False})
        self.event = 0
        self.closed = 0
        self.calls = []
        self.hook = None
        self.properties = {'': [{'name': 'Артикул', 'value': 'КП-01'}], 'Основная': []}
        self.model = NS(GetMaterialPropertyName2=lambda cfg: ('', 'Сталь'),
            GetUnits=lambda: [0, 1, 2], SelectionManager=NS(GetSelectedObjectCount2=lambda mark: 0))
        self.body_list = []
    def identity(self, obj): return id(obj)
    def snapshot(self, model): return deepcopy(self.metadata)
    def watch_part(self, model):
        return NS(poll=lambda: self.event, close=lambda: setattr(self, 'closed', self.closed+1))
    def configuration_identity(self, model, name): return self.cfg
    def bodies(self, model, kind): return self.body_list[:]
    def features(self, model): return self.items[:]
    def feature_summary(self, f):
        return dict(native_id=f.identifier, feature_type=f.kind, name='Элемент '+str(f.identifier),
            suppressed=False, error_code=0, owner_native_id=None, is_warning=False)
    def dimension_context(self, model): return deepcopy(self.context)
    def feature_deletion_context(self, model):
        return dict(equations=dict(enumerated_count=0, disabled_count=0, disabled_definitions_captured=True),
            external_references={'count': 0}, auxiliary_references={'count': 0})
    def feature_external_references(self, features):
        return dict(scope='native_feature_external_references_v1',feature_count=len(features),
            total_reference_rows=0,features=[dict(native_id=f.identifier,count=0,rows=[]) for f in features])
    def dimension_geometry_snapshot(self, model):
        return {'representation': 'planar_polyhedral_brep_v1', 'bodies': []}
    def dimensions(self, model, features): return []
    def feature_dependencies(self, features):
        return dict(scope='native_feature_relation_capture_v1',feature_count=len(features),
            parent_links=[],child_links=[],absorbed_links=[],parent_links_without_child_confirmation=[],
            child_links_without_parent_confirmation=[],relations_read=0)
    def reference_plane_transform(self, plane): return IDENTITY
    def persistent_id(self, model, obj):
        return next(token for token, value in self.objects.items() if value is obj)
    def resolve_persistent_id(self, model, token, kind): return self.objects[token]
    def _persistent_variant(self, token): return token
    def _extension(self, model):
        return NS(GetObjectByPersistReference3=lambda token: (self.objects[token], 0))
    def part_creation_controls(self, model):
        return dict(add_to_db=False, auto_solve=True, display_when_added=True, dimension_input=False)


@pytest.fixture
def adapter(monkeypatch):
    a = Adapter()
    monkeypatch.setattr(binding, 'wrap', lambda obj, interface: obj)
    def data(label, value):
        def getter(*args):
            a.calls.append(label)
            if a.hook and label == 'properties': a.hook()
            return deepcopy(value() if callable(value) else value)
        return getter
    monkeypatch.setattr(native, '_properties', data('properties', lambda: a.properties))
    monkeypatch.setattr(native, '_annotations', data('annotations', []))
    monkeypatch.setattr(native, '_configuration', data('configuration', {'name': 'Основная'}))
    monkeypatch.setattr(native, '_empty_auxiliary_data', data('auxiliary', {'comments': []}))
    monkeypatch.setattr(native, '_display_data', data('display', {'lights': []}))
    return a


def test_complete_empty_snapshot_binds_origin_and_retains_every_data_provider(adapter):
    a = adapter
    r = a.rectangle_construction_snapshot(a.model)
    assert r['solid_body_count'] == 0 and r['clone_state']['profile'] == 'empty_native_part_v1'
    assert r['clone_state']['properties'] == a.properties
    assert r['clone_state']['origin']['point_role'] == 'origin:point'
    assert len(r['references']) == 5
    assert a.calls == ['properties', 'annotations', 'configuration', 'auxiliary', 'display']
    assert a.closed == 1
    assert validated_rectangle_snapshot(r) == r


def test_property_change_is_part_of_the_complete_observation_not_only_stamp(adapter):
    a = adapter; before = a.rectangle_construction_snapshot(a.model)
    a.properties[''][0]['value'] = 'КП-02'
    after = a.rectangle_construction_snapshot(a.model)
    assert before != after and a.metadata['update_stamp'] == 1


@pytest.mark.parametrize('change', ['event', 'configuration', 'metadata', 'feature_incarnation'])
def test_changes_during_getters_fail_and_release_the_owned_watch(adapter, change):
    a = adapter
    def hook():
        if change == 'event': a.event += 1
        elif change == 'configuration': a.cfg = object()
        elif change == 'metadata': a.metadata['title'] = 'Изменённая деталь'
        else: a.items[0] = Feature(0, 'RefPlane')
    a.hook = hook
    with pytest.raises(ExecutionFailure): a.rectangle_construction_snapshot(a.model)
    assert a.closed == 1


@pytest.mark.parametrize('change', ['extra_configuration', 'macro', 'open_sketch', 'equation', 'origin_offset'])
def test_unsupported_profile_is_refused_without_native_writes(adapter, change):
    a = adapter
    if change == 'extra_configuration': a.metadata['configurations'].append('Вторая')
    elif change == 'macro': a.items.append(Feature(4, 'MacroFeature'))
    elif change == 'open_sketch': a.context['editing_sketch'] = True
    elif change == 'equation': a.context['equation_count'] = 1
    else: a.point.X = .1
    with pytest.raises(ExecutionFailure): a.rectangle_construction_snapshot(a.model)
    assert a.closed == 1


@pytest.mark.parametrize('change', ['missing_properties', 'missing_controls', 'duplicate_pid',
    'missing_origin', 'malformed_origin_id', 'wrong_origin_feature', 'nonfinite_units'])
def test_detached_partial_or_aliased_evidence_is_not_an_observation(adapter, change):
    r = adapter.rectangle_construction_snapshot(adapter.model)
    d = r['clone_state']
    if change == 'missing_properties': d['properties'] = None
    elif change == 'missing_controls': d['creation_controls'].pop('dimension_input')
    elif change == 'duplicate_pid': r['references'][1]['token'] = r['references'][0]['token']
    elif change == 'missing_origin': d.pop('origin')
    elif change == 'malformed_origin_id': d['origin']['native_id'] = [True, 0]
    elif change == 'wrong_origin_feature': d['origin']['feature_role'] = 'feature:0'
    else: d['units'].append(float('nan'))
    with pytest.raises((ExecutionFailure, ValueError, JobError)): validated_rectangle_snapshot(r)


def test_nonempty_body_is_never_certified_by_an_empty_geometry_snapshot(adapter):
    a = adapter; a.body_list = [object()]
    def existing_body_oracle(model):
        a.calls.append('full_body_oracle')
        raise ExecutionFailure('unsupported_body', 'No complete rectangular body proof.')
    a.first_save_part_snapshot = existing_body_oracle
    with pytest.raises(ExecutionFailure): a.rectangle_construction_snapshot(a.model)
    assert a.calls == ['full_body_oracle'] and a.closed == 1
