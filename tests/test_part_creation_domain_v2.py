"""Construction preparation against explicit domain identities; no CAD writes."""

from copy import deepcopy

import pytest

from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobStore
from solidworks_mcp.part_creation import PartCreationCatalog
from test_dimension_domain_v2 import Adapter as DimensionsAdapter, dimension
from test_document_catalog_v2 import model
from test_feature_domain_v2 import feature
from test_part_creation_v2 import IDENTITY


class Adapter(DimensionsAdapter):
    def __init__(self):
        super().__init__()
        self.frame = IDENTITY
        self.plane_hook = None

    def part_creation_controls(self, wrapper):
        return {'add_to_db': False, 'auto_solve': True, 'display_when_added': True, 'dimension_input': False}

    def dimension_geometry_snapshot(self, wrapper):
        return {'representation': 'fake_complete_empty_geometry',
                'bodies': deepcopy(self.original(wrapper).state.get('bodies', []))}

    def reference_plane_transform(self, plane):
        assert plane.state['feature_type'] == 'RefPlane'
        result = self.frame
        if self.plane_hook:
            hook, self.plane_hook = self.plane_hook, None
            hook()
        return result


@pytest.fixture
def setup(tmp_path):
    adapter = Adapter()
    first, other = model(title='Контрольная пластина', configurations=['Основная']), model(title='Другая деталь')
    first.features, other.features = [feature(1, 'Передняя', kind='RefPlane')], [feature(1, 'Передняя', kind='RefPlane')]
    first.dimensions, other.dimensions = [], []
    first.displays, other.displays = [], []
    adapter.models = [first, other]
    adapter.context['configuration_needs_rebuild'] = {'Основная': False}
    store = JobStore(tmp_path / 'parts.sqlite')
    documents = DocumentCatalog(adapter)
    ids = [row['document_id'] for row in documents.list()['documents']]
    dimensions = DimensionCatalog(documents, store, 'connection_1', mutation_guard=adapter.guard)
    planes = [dimensions.features.list(doc, 'Основная')['items'][0]['object_id'] for doc in ids]
    yield adapter, PartCreationCatalog(dimensions), ids, planes
    assert adapter.writes == [] and adapter.dimension_writes == [] and adapter.guard_entries == 0
    documents.close()
    store.close()


def prepare(setup, **changes):
    _, catalog, ids, planes = setup
    return catalog.prepare_base_extrusion(ids[0], 'Основная', **{
        'plane_object_id': planes[0], 'width_mm': 40., 'height_mm': 20., 'depth_mm': 10., **changes})


def test_preparation_binds_full_state_plane_and_parameters_and_does_not_write(setup):
    adapter, _, ids, planes = setup
    before = deepcopy([row.state for row in adapter.models])
    result = prepare(setup)
    assert result['revision_scope'] == 'empty_part_base_rectangle_v1'
    assert result['document_id'] == ids[0] and result['definition']['plane_object_id'] == planes[0]
    assert result['expected_geometry'] == {'volume_mm3': 8000., 'surface_area_mm2': 2800., 'solid_body_count': 1}
    assert result['native_creation_available'] is True
    assert result['revision'] == prepare(setup)['revision']
    assert result['revision'] != prepare(setup, depth_mm=12.)['revision']
    assert [row.state for row in adapter.models] == before


def test_invalid_input_never_reaches_cad(setup, monkeypatch):
    _, catalog, _, _ = setup
    monkeypatch.setattr(catalog.dimensions, '_paired_capture', lambda *args: pytest.fail('Unexpected CAD access'))
    with pytest.raises(ExecutionFailure) as error: prepare(setup, width_mm=True)
    assert error.value.code == 'invalid_part_length'


def test_plane_reference_from_other_document_is_rejected(setup):
    with pytest.raises(ExecutionFailure) as error: prepare(setup, plane_object_id=setup[3][1])
    assert error.value.code == 'object_reference_not_found'


@pytest.mark.parametrize('key,value,code', [
    ('active_document', False, 'document_not_active'), ('read_only', True, 'part_not_writable'),
    ('editing_sketch', True, 'part_not_writable'), ('external_reference_count', 1, 'unsupported_part_controls'),
    ('equation_count', 1, 'unsupported_part_controls'), ('equations_linked', True, 'unsupported_part_controls'),
    ('design_table', True, 'unsupported_part_controls'), ('unsafe_feature_types', ['Macro'], 'unsupported_part_controls'),
    ('configuration_geometry_complete', False, 'unsupported_part_configurations')])
def test_unsupported_control_state_is_rejected_before_creation(setup, key, value, code):
    setup[0].context[key] = value
    with pytest.raises(ExecutionFailure) as error: prepare(setup)
    assert error.value.code == code


@pytest.mark.parametrize('change,code', [
    ('body', 'part_not_empty'), ('dimension', 'part_not_empty'), ('sketch', 'part_not_empty'),
    ('rebuild', 'document_needs_rebuild'), ('feature_error', 'feature_error_before_creation'),
    ('second_configuration', 'unsupported_part_configurations'), ('name_collision', 'feature_name_conflict'),
    ('suppressed_plane', 'invalid_reference_plane'), ('not_plane', 'invalid_reference_plane')])
def test_incompatible_part_state_is_rejected(setup, change, code):
    adapter, _, _, _ = setup
    part = adapter.models[0]
    if change == 'body': part.state['bodies'] = [{'identity': 'owned_body'}]
    if change == 'dimension': part.dimensions = [dimension(1)]
    if change == 'sketch': part.features.append(feature(2, 'Эскиз', kind='ProfileFeature'))
    if change == 'rebuild': part.state['pending'] = True
    if change == 'feature_error': part.features[0].state['error_code'] = 1
    if change == 'second_configuration': part.state['configurations'].append('Вариант')
    if change == 'name_collision': part.features.append(feature(2, 'основание', kind='RefPlane'))
    if change == 'suppressed_plane': part.features[0].state['suppressed'] = True
    if change == 'not_plane': part.features[0].state['feature_type'] = 'RefAxis'
    with pytest.raises(ExecutionFailure) as error: prepare(setup)
    assert error.value.code == code


def test_plane_transform_change_without_event_is_not_accepted(setup):
    adapter = setup[0]
    adapter.plane_hook = lambda: setattr(adapter, 'frame', (0., 1., 0., -1., 0., 0., 0., 0., 1., *IDENTITY[9:]))
    with pytest.raises(ExecutionFailure) as error: prepare(setup)
    assert error.value.code == 'document_changed_during_read'


def test_concurrent_model_edit_during_plane_resolution_is_not_accepted(setup):
    adapter = setup[0]
    adapter.plane_hook = lambda: adapter.models[0].features.append(feature(2, 'Добавленная плоскость', kind='RefPlane'))
    with pytest.raises(ExecutionFailure) as error: prepare(setup)
    assert error.value.code == 'document_changed_during_read'


def test_new_plane_frame_changes_preparation_revision(setup):
    first = prepare(setup)
    setup[0].frame = (0., 1., 0., -1., 0., 0., 0., 0., 1., *IDENTITY[9:])
    assert prepare(setup)['revision'] != first['revision']
