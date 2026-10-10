"""Artificial cut effects and actual SQLite protocol; not CAD acceptance."""

from copy import deepcopy
import asyncio
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.linear_sketch import LinearSketchReader
from solidworks_mcp.part_cut import PartCutCatalog, corner_body_matches
from solidworks_mcp.runtime_v2 import Runtime
from test_dimension_domain_v2 import dimension
from test_feature_domain_v2 import feature
from test_linear_sketch_v2 import Sketch
from test_sketch_dimensions_v2 import setup as sketch_setup
from test_part_cut_preparation_v2 import prepare


def body(expected):
    polygons = [list(range(z, 12, 2)) for z in (0, 1)]
    polygons += [[2*i, 2*((i+1)%6), 2*((i+1)%6)+1, 2*i+1] for i in range(6)]
    edges, lookup, faces = [], {}, []
    for polygon in polygons:
        loop = []
        for a, b in zip(polygon, polygon[1:]+polygon[:1]):
            key = tuple(sorted((a, b)))
            if key not in lookup:
                lookup[key] = len(edges)
                edges.append({'start': a, 'end': b})
            loop.append({'start': a, 'end': b, 'edge': lookup[key]})
        faces.append({'loops': [{'outer': True, 'coedges': loop}]})
    return {'vertices': deepcopy(expected['vertices_si']), 'edges': edges, 'faces': faces}


@pytest.fixture
def setup(sketch_setup):
    adapter, sketches, store, runner, doc, obj, _ = sketch_setup
    part = adapter.models[0]
    snapshot_original = adapter.sketch_snapshot
    adapter.cut_writes, adapter.cut_restores, adapter.cut_fault = 0, 0, None
    adapter.cut_receipts = []

    def receipt(model, features, controls):
        value = SimpleNamespace(baseline_body_name='Тело основания', controls=controls, restored=False,
            baseline=list(features), dimensions=list(part.dimensions), geometry=deepcopy(part.state['bodies']),
            pending=False, complete=False, definition=None, owned=[], sketch=None)
        adapter.cut_receipts.append(value)
        return value

    def create(model, plane, definition, value):
        current = store.get(store.list(limit=1)['items'][0]['operation_id'])
        assert current['mutation']['phase'] == 'prepared'
        adapter.cut_writes += 1
        value.definition = definition
        sketch = feature(20, definition.sketch_name, kind='ProfileFeature')
        cut = feature(21, definition.feature_name, kind='Cut')
        sketch.state['owner_native_id'] = 21
        value.owned = [sketch, cut]
        part.features += value.owned
        value.sketch = Sketch()
        w, h = definition.width_mm/1000., definition.height_mm/1000.
        for point, xyz in zip(value.sketch.points, ((0.,0.,0.),(w,0.,0.),(w,h,0.),(0.,h,0.))):
            point.X, point.Y, point.Z = xyz
        for index, (name, size) in enumerate((('Ширина выреза',w),('Высота выреза',h)), 40):
            row = dimension(index, value=size)
            row.owner = sketch
            row.state.update(name=name, full_name=name+'@'+definition.sketch_name,
                             owner=deepcopy(sketch.state), values_si={'Основная':size},
                             write_blockers=['sketch_geometry_snapshot_not_implemented'])
            row.FullName = row.state['full_name']
            part.dimensions.append(row)
            value.sketch.dimensions[index-40] = row
        value.expected = definition.expected_geometry({'width_m':.04,'height_m':.02,'depth_m':.01,
            'plane_transform':[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]})
        part.state['bodies'] = [body(value.expected)]
        part.state['update_stamp'] += 1
        value.complete = True
        if adapter.cut_fault == 'original_dimension':
            part.dimensions[0].state['values_si']['Основная'] = .041
        if adapter.cut_fault == 'foreign_feature': part.features.append(feature(99,'Чужое изменение'))
        if adapter.cut_fault == 'foreign_vertex': part.state['bodies'][0]['vertices'][0][0] = .003.hex()
        if adapter.cut_fault == 'unknown': value.pending = True
        if adapter.cut_fault: raise RuntimeError('Artificial post-creation failure')

    def snapshot(model, owner):
        if owner.state['native_id'] != 20: return snapshot_original(model, owner)
        value = adapter.cut_receipts[-1]
        result, members = LinearSketchReader(value.sketch, value.sketch.origin,
            wrap=lambda raw,name:raw, identity=lambda raw:getattr(raw,'identity',raw)).read()
        base, _ = snapshot_original(model, part.features[1])
        result.update({key:base[key] for key in ('model_to_sketch','reference_plane','model_origin')})
        result.update(feature_native_id=20, feature_pid_hex=owner.pid.hex())
        return result, members

    def evidence(model, value):
        if value.pending: raise ExecutionFailure('cut_effect_unconfirmed','Artificial unknown effect',uncertain=True)
        if value.restored: return {'restored':True,'complete':False},()
        result, members = snapshot(model, value.owned[0])
        return {'complete':value.complete,'restored':False,'sketch_native_id':20,'cut_native_id':21,
            'sketch':result,'fully_defined':True,'controls':value.controls,'body_name':value.baseline_body_name,
            'volume_mm3':value.expected['volume_mm3'],'surface_area_mm2':value.expected['surface_area_mm2']},members

    def restore(model, value):
        if value.pending: raise ExecutionFailure('cut_restore_unsafe','Unknown effect',uncertain=True)
        adapter.cut_restores += 1
        part.features = value.baseline
        part.dimensions = value.dimensions
        part.state['bodies'] = value.geometry
        part.state['update_stamp'] += 1
        value.restored = True

    adapter.new_corner_cut_receipt, adapter.create_corner_cut = receipt, create
    adapter.corner_cut_evidence, adapter.restore_corner_cut, adapter.sketch_snapshot = evidence, restore, snapshot
    catalog = PartCutCatalog(sketches)
    args = dict(document_id=doc, configuration='Основная', **prepare(sketch_setup)['definition'])
    revision = catalog.prepare_corner_cut(**args)['revision']
    def run(request='cut', expected_revision=revision):
        payload = dict(args,expected_revision=expected_revision)
        return runner.submit(request,'part.create_corner_cut',payload,
            lambda op:catalog.create_corner_cut(op,**payload),mutates=True,pass_operation_id=True,
            context={key:payload[key] for key in ('document_id','configuration','expected_revision')},
            verify=lambda result:result['verified'] is True)
    return adapter, catalog, run, store


def test_complete_cut_committed_and_same_request_does_not_write_again(setup):
    adapter, _, run, _ = setup
    original_other = deepcopy(adapter.models[1].state)
    result = run()
    assert result['status'] == 'succeeded', result.get('error')
    assert result['mutation']['verification']['outcome'] == 'committed'
    assert result['result']['after']['created']['volume_mm3'] == pytest.approx(7500.)
    assert run()['operation_id'] == result['operation_id']
    assert adapter.cut_writes == 1 and adapter.cut_restores == 0
    assert adapter.models[1].state == original_other


def test_stale_revision_fails_without_native_cut_or_restore(setup):
    adapter, _, run, _ = setup
    result = run(expected_revision='rev_stale')
    assert result['status'] == 'failed' and result['error']['code'] == 'stale_revision'
    assert adapter.cut_writes == adapter.cut_restores == 0


def test_runtime_routes_cut_on_existing_owning_worker_and_releases_handles(setup):
    adapter, catalog, _, store = setup
    runtime = Runtime(store)
    runtime._catalog, runtime._dimensions = catalog.dimensions.documents, catalog.dimensions
    runtime._connection_epoch = 'sketch-test'
    from test_part_construction_mutation_v2 import Worker
    from solidworks_mcp.jobs import JobRunner
    runtime._runner = JobRunner(store, Worker())
    doc = runtime._catalog.list()['documents'][0]['document_id']
    features = catalog.dimensions.features.list(doc, 'Основная')['items']
    args = dict(document_id=doc,configuration='Основная',width_mm=10.,height_mm=5.,
        object_id=next(row['object_id'] for row in features if row['feature_type']=='ProfileFeature'),
        plane_object_id=next(row['object_id'] for row in features if row['feature_type']=='RefPlane'))
    async def exercise():
        preparation = await runtime.read('cut-prepare','part.prepare_corner_cut',args)
        assert preparation['status'] == 'succeeded', preparation
        payload = dict(args,expected_revision=preparation['result']['revision'])
        result = await runtime.mutate('cut-runtime','part.create_corner_cut',payload)
        assert result['status'] == 'succeeded', result
        assert await runtime.mutate('cut-runtime','part.create_corner_cut',payload) == result
    asyncio.run(exercise())
    assert adapter.cut_writes == 1
    runtime._release_catalog()
    assert runtime._cuts is runtime._sketches is runtime._dimensions is None


def test_known_failure_restores_only_owned_cut_and_original_geometry(setup):
    adapter, _, run, _ = setup
    original = deepcopy(adapter.models[0].state['bodies'])
    adapter.cut_fault = 'known'
    result = run()
    assert result['status'] == 'failed', result
    assert result['mutation']['verification']['outcome'] == 'rolled_back'
    assert adapter.cut_writes == adapter.cut_restores == 1
    assert adapter.models[0].state['bodies'] == original
    assert len(adapter.models[0].dimensions) == 3


@pytest.mark.parametrize('fault',['unknown','original_dimension','foreign_feature','foreign_vertex'])
def test_unknown_or_foreign_effect_never_deleted_or_replayed(setup, fault):
    adapter, _, run, store = setup
    adapter.cut_fault = fault
    result = run()
    assert result['status'] == 'unknown', result
    assert adapter.cut_restores == 0
    assert run()['operation_id'] == result['operation_id'] and adapter.cut_writes == 1
    assert store.mutation_blockers('sketch-test', result['payload']['context']['document_id'])


@pytest.mark.parametrize('change',['vertex','edge','face_cycle','inner_loop','duplicate_face'])
def test_full_shape_rejects_same_counts_with_wrong_boundary(change):
    from solidworks_mcp.part_cut import CornerCut
    expected = CornerCut.validate(object_id='feat_'+'a'*32,plane_object_id='feat_'+'b'*32,
        width_mm=10.,height_mm=5.).expected_geometry({'width_m':.04,'height_m':.02,'depth_m':.01,
        'plane_transform':[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]})
    original = body(expected)
    assert corner_body_matches({'bodies':[original]}, expected)
    altered = deepcopy(original)
    if change == 'vertex': altered['vertices'][0][0] = .003.hex()
    if change == 'edge': altered['edges'][0]['end'] = 4
    if change == 'face_cycle': altered['faces'][0]['loops'][0]['coedges'][0]['start'] = 4
    if change == 'inner_loop': altered['faces'][0]['loops'][0]['outer'] = False
    if change == 'duplicate_face': altered['faces'][0] = deepcopy(altered['faces'][1])
    assert not corner_body_matches({'bodies':[altered]},expected)
