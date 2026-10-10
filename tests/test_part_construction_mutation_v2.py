"""Durable construction on artificial native effects; never CAD acceptance."""

from concurrent.futures import Future
from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.documents import DocumentCatalog, rejected
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.part_creation import PartCreationCatalog
from test_document_catalog_v2 import model
from test_dimension_domain_v2 import dimension
from test_feature_domain_v2 import feature
from test_part_creation_domain_v2 import Adapter as PreparationAdapter


class Adapter(PreparationAdapter):
    def __init__(self):
        super().__init__()
        self.creation_count = 0
        self.restore_count = 0
        self.creation_fault = None
        self.before_creation = None

    def new_base_receipt(self, wrapper, features, controls):
        return SimpleNamespace(baseline=list(features), controls=dict(controls), owned=[], complete=False,
                               restored=False, pending=False, definition=None)

    def create_base_rectangle(self, wrapper, plane, definition, receipt):
        if self.before_creation: self.before_creation()
        self.creation_count += 1
        if self.creation_fault == 'silent': return
        part = self.original(wrapper)
        sketch = feature(10, definition.sketch_name, kind='ProfileFeature')
        boss = feature(11, definition.feature_name, kind='Boss')
        sketch.state['owner_native_id'] = 11
        receipt.owned = [sketch, boss]
        part.features.extend(receipt.owned)
        receipt.definition = definition
        part.dimensions = []
        for i, (name, value, owner) in enumerate((('Ширина', definition.width_mm / 1000., sketch),
                ('Высота', definition.height_mm / 1000., sketch), ('Толщина', definition.depth_m, boss)), 1):
            row = dimension(i, value=value)
            row.state.update(name=name, full_name=name + '@' + owner.state['name'], values_si={'Основная': value},
                             owner=deepcopy(owner.state))
            part.dimensions.append(row)
        part.state['update_stamp'] += 1
        part.state['bodies'] = [{'vertices': [[float(v).hex() for v in (x, y, z)]
                                 for x, y in definition.profile_m for z in (0., definition.depth_m)],
                                 'edges': [None] * 12, 'faces': [None] * 6}]
        receipt.complete = True
        if self.creation_fault == 'exception': raise RuntimeError('Known creation failed after owned handles were retained.')
        if self.creation_fault == 'unknown':
            receipt.pending = True
            raise RuntimeError('Unknown native creation outcome.')
        if self.creation_fault == 'foreign':
            part.features.append(feature(20, 'Чужое изменение'))
            raise RuntimeError('Concurrent feature discovered.')
        if self.creation_fault == 'wrong_vertex': part.state['bodies'][0]['vertices'][0][0] = (.005).hex()
        if self.creation_fault == 'wrong_dimension': part.dimensions[0].state['values_si']['Основная'] = .03
        if self.creation_fault == 'wrong_name': sketch.state['name'] = 'Подменённый эскиз'

    def base_rectangle_evidence(self, wrapper, receipt):
        if receipt.restored: return {'restored': True, 'complete': False}
        if not receipt.complete: return {'restored': False, 'complete': False}
        item = receipt.definition
        return {'restored': False, 'complete': True, 'fully_defined': True,
                'sketch_native_id': 10, 'extrusion_native_id': 11, 'body_name': item.body_name,
                'volume_mm3': item.volume_mm3, 'surface_area_mm2': item.surface_area_mm2,
                'controls': dict(receipt.controls)}

    def restore_base_rectangle(self, wrapper, receipt):
        self.restore_count += 1
        part = self.original(wrapper)
        if receipt.pending or any(row not in receipt.baseline + receipt.owned for row in part.features):
            raise rejected('construction_restore_unsafe', 'Unknown/foreign effects cannot authorize deletion.')
        part.features = list(receipt.baseline)
        part.dimensions = []
        part.state['bodies'] = []
        part.state['update_stamp'] += 1
        receipt.restored = True


class Worker:
    def submit(self, function):
        future = Future()
        try: future.set_result(function())
        except BaseException as exc: future.set_exception(exc)
        return future


@pytest.fixture
def setup(tmp_path):
    adapter = Adapter()
    first, other = model(title='Контрольная пластина', configurations=['Основная']), model(title='Чужая деталь')
    for part in (first, other):
        part.features, part.dimensions, part.displays = [feature(1, 'Передняя', kind='RefPlane')], [], []
    adapter.models = [first, other]
    adapter.context['configuration_needs_rebuild'] = {'Основная': False}
    store = JobStore(tmp_path / 'construction.sqlite')
    documents = DocumentCatalog(adapter)
    ids = [row['document_id'] for row in documents.list()['documents']]
    dimensions = DimensionCatalog(documents, store, 'construction-test', mutation_guard=adapter.guard)
    catalog = PartCreationCatalog(dimensions)
    plane = dimensions.features.list(ids[0], 'Основная')['items'][0]['object_id']
    parameters = dict(plane_object_id=plane, width_mm=40., height_mm=20., depth_mm=10.)
    prepared = catalog.prepare_base_extrusion(ids[0], 'Основная', **parameters)
    runner = JobRunner(store, Worker())
    def run(request='create-plate', revision=prepared['revision']):
        args = dict(document_id=ids[0], configuration='Основная', expected_revision=revision, **parameters)
        return runner.submit(request, 'part.create_base_extrusion', args,
            lambda op: catalog.create_base_extrusion(op, **args),
            context={key: args[key] for key in ('document_id', 'configuration', 'expected_revision')},
            mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
    yield adapter, catalog, store, ids, run
    documents.close()
    store.close()


def test_creation_runs_after_durable_checkpoint_and_preserves_other_part(setup):
    adapter, _, store, _, run = setup
    other = deepcopy(adapter.models[1].state)
    def checkpoint():
        row = store._db.execute('SELECT before_state FROM mutations').fetchone()
        assert row is not None and 'Эскиз основания' in row[0]
    adapter.before_creation = checkpoint
    job = run()
    assert job['status'] == 'succeeded' and job['mutation']['phase'] == 'committed'
    assert job['result']['verified'] is True
    assert job['mutation']['before_state']['_mutation_effect_scope'] == 'application'
    assert adapter.creation_count == 1 and adapter.restore_count == 0
    assert adapter.models[1].state == other


def test_same_request_id_is_not_replayed_after_creation(setup):
    first = setup[4]()
    second = setup[4]()
    assert first == second and setup[0].creation_count == 1


def test_stale_revision_never_starts_native_creation_or_rollback(setup):
    job = setup[4](revision='rev_stale')
    assert job['status'] == 'failed' and job['error']['code'] == 'stale_revision'
    assert setup[0].creation_count == setup[0].restore_count == 0


@pytest.mark.parametrize('fault', ['silent', 'exception', 'wrong_vertex', 'wrong_dimension', 'wrong_name'])
def test_known_failure_restores_only_created_features_and_geometry(setup, fault):
    adapter, _, _, _, run = setup
    adapter.creation_fault = fault
    job = run()
    assert job['status'] == 'failed' and job['mutation']['phase'] == 'rolled_back'
    assert job['error']['requires_reconciliation'] is False
    assert [row.state['native_id'] for row in adapter.models[0].features] == [1]
    assert adapter.models[0].state['bodies'] == []
    assert adapter.creation_count == adapter.restore_count == 1


@pytest.mark.parametrize('fault', ['unknown', 'foreign'])
def test_unknown_or_foreign_effects_hold_application_without_another_dispatch(setup, fault):
    adapter, _, store, ids, run = setup
    adapter.creation_fault = fault
    job = run()
    assert job['status'] == 'unknown' and job['error']['requires_reconciliation'] is True
    assert store.mutation_blockers('construction-test', ids[1])
    assert len(adapter.models[0].features) >= 3
    assert run('new-request')['status'] == 'failed'
    assert adapter.creation_count == 1


def test_concurrent_edit_after_checkpoint_is_not_rolled_back(setup):
    adapter = setup[0]
    adapter.guard_hook = lambda: adapter.models[0].features.append(feature(20, 'Чужая плоскость', kind='RefPlane'))
    job = setup[4]()
    assert job['status'] == 'failed' and job['mutation']['phase'] == 'not_started'
    assert adapter.creation_count == adapter.restore_count == 0
    assert adapter.models[0].features[-1].state['name'] == 'Чужая плоскость'
