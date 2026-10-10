"""Existing-hole edits over artificial native geometry and real durable jobs."""

from copy import deepcopy
from dataclasses import replace
import asyncio

import pytest

from solidworks_mcp.circular_sketch import CircularSketchReader
from solidworks_mcp.jobs import JobRunner
from solidworks_mcp.part_hole_edit import PartHoleEditCatalog
from solidworks_mcp.runtime_v2 import Runtime
from test_dimension_domain_v2 import Adapter as DimensionAdapter
from test_feature_domain_v2 import feature
from test_part_hole_mutation_v2 import setup as hole_setup, cut_setup, sketch_setup, native_shape
from test_part_construction_mutation_v2 import Worker


@pytest.fixture
def setup(hole_setup):
    adapter, holes, run, store, args = hole_setup
    assert run()['status'] == 'succeeded'
    receipt = adapter.cut_receipts[-1]
    part = adapter.models[0]
    circle = receipt.sketch
    catalog = PartHoleEditCatalog(holes.sketches)
    doc, cfg = args['document_id'], args['configuration']
    adapter.edit_fault = None
    def snapshot(model, owner):
        assert owner.state['native_id'] == 20
        result, members = CircularSketchReader(circle, circle.origin,
            wrap=lambda raw, name: raw, identity=lambda raw: getattr(raw, 'identity', id(raw))).read()
        base, _ = holes.sketches._read_snapshot(model, part.features[1])
        result.update({key: base[key] for key in ('model_to_sketch', 'reference_plane', 'model_origin')})
        result.update(feature_native_id=20, feature_pid_hex=owner.pid.hex())
        return result, members
    adapter.circular_sketch_snapshot = snapshot
    adapter.hole_edit_controls = lambda model: {'body_name': receipt.baseline_body_name,
        'sketch_controls': adapter.part_creation_controls(model)}
    def rebuild(model):
        result = DimensionAdapter.rebuild_dimension_document(adapter, model)
        x, y, d = [row.state['values_si'][cfg] for row in part.dimensions[3:]]
        circle.points[0].X, circle.points[0].Y, circle.lines[0].radius = x, y, d / 2.
        definition = replace(receipt.definition, centre_x_mm=x*1000., centre_y_mm=y*1000., diameter_mm=d*1000.)
        part.state['bodies'] = [native_shape(definition)]
        fault, adapter.edit_fault = adapter.edit_fault, None
        if fault == 'foreign_dimension': part.dimensions[0].state['values_si'][cfg] = .041
        if fault == 'foreign_feature': part.features.append(feature(99, 'Чужое изменение'))
        if fault == 'foreign_vertex': part.state['bodies'][0]['vertices'][0][0] = (.003).hex()
        if fault: raise RuntimeError('Artificial error after solving own circle.')
        return result
    adapter.rebuild_dimension_document = rebuild
    def measurements(model):
        x, y, d = [row.state['values_si'][cfg] for row in part.dimensions[3:]]
        wanted = replace(receipt.definition, centre_x_mm=x*1000., centre_y_mm=y*1000., diameter_mm=d*1000.)
        return {key: wanted.expected_geometry({'width_m':.04,'height_m':.02,'depth_m':.01,
            'plane_transform':[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]})[key]
            for key in ('volume_mm3', 'surface_area_mm2')}
    adapter.rectangle_body_measurements = measurements
    items = holes.dimensions.features.list(doc, cfg)['items']
    circle_id = next(row['object_id'] for row in items if row['native_id'] == 20)
    dims = holes.dimensions.list(doc, cfg)['items']
    identifiers = {row['name']: row['object_id'] for row in dims}
    targets = dict(document_id=doc, configuration=cfg, base_object_id=args['object_id'], object_id=circle_id)
    runner = JobRunner(store, Worker())
    def edit(name='Центр X', value=12., request='edit', revision=None):
        arguments = {**targets, 'dimension_id': identifiers[name], 'value_mm': value}
        arguments['expected_revision'] = revision or catalog.prepare_dimension_change(**arguments)['revision']
        return runner.submit(request, 'part.set_hole_dimension', arguments,
            lambda op: catalog.set_dimension(op, **arguments), mutates=True, pass_operation_id=True,
            context={key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')},
            verify=lambda result: result['verified'] is True)
    return adapter, catalog, store, targets, identifiers, edit


@pytest.mark.parametrize('name,value,axis', [('Центр X',12.,'centre_x'),('Центр Y',11.,'centre_y'),('Диаметр',8.,'diameter')])
def test_each_independent_driver_commits_and_preserves_other_document(setup,name,value,axis):
    adapter, _, _, _, _, edit = setup
    other = deepcopy(adapter.models[1].state)
    job = edit(name, value)
    assert job['status'] == 'succeeded', job.get('error')
    assert job['mutation']['verification']['outcome'] == 'committed'
    assert job['result']['after']['parameters'][axis + '_m'] == pytest.approx(value/1000.)
    assert len(adapter.dimension_writes) == 1 and adapter.models[1].state == other


def test_same_request_and_input_returns_exact_job_without_second_write(setup):
    adapter, catalog, _, targets, ids, edit = setup
    revision = catalog.prepare_dimension_change(**targets, dimension_id=ids['Диаметр'], value_mm=8.)['revision']
    first = edit('Диаметр', 8., revision=revision)
    second = edit('Диаметр', 8., revision=revision)
    assert first == second and len(adapter.dimension_writes) == 1


def test_stale_revision_is_prewrite(setup):
    adapter, _, _, _, _, edit = setup
    job = edit(revision='rev_stale')
    assert job['status'] == 'failed' and job['error']['code'] == 'stale_revision'
    assert adapter.dimension_writes == []


@pytest.mark.parametrize('name,value', [('Центр X',2.),('Центр Y',19.),('Диаметр',20.)])
def test_material_violation_rejected_before_write(setup,name,value):
    adapter, _, _, _, _, edit = setup
    # Reject through the durable operation as well as the preparation.
    job = edit(name, value, revision='rev_explicit')
    assert job['status'] == 'failed' and job['error']['code'] == 'hole_outside_material'
    assert adapter.dimension_writes == []


@pytest.mark.parametrize('name', ['Центр X', 'Центр Y', 'Диаметр'])
def test_known_post_rebuild_failure_restores_only_own_driver(setup,name):
    adapter, _, _, _, _, edit = setup
    old = deepcopy(adapter.models[0].state['bodies'])
    adapter.edit_fault = 'known'
    job = edit(name, 8. if name == 'Диаметр' else 12.)
    assert job['status'] == 'failed' and job['mutation']['verification']['outcome'] == 'rolled_back',job.get('error')
    assert len(adapter.dimension_writes) == 2 and adapter.models[0].state['bodies'] == old


@pytest.mark.parametrize('fault', ['foreign_dimension', 'foreign_feature', 'foreign_vertex'])
def test_foreign_effect_holds_application_without_restoration_or_replay(setup,fault):
    adapter, catalog, store, targets, ids, edit = setup
    revision = catalog.prepare_dimension_change(**targets, dimension_id=ids['Центр X'], value_mm=12.)['revision']
    adapter.edit_fault = fault
    job = edit(revision=revision)
    assert job['status'] == 'unknown', job.get('error')
    assert len(adapter.dimension_writes) == 1
    assert edit(revision=revision) == job and len(adapter.dimension_writes) == 1
    assert store.mutation_blockers('sketch-test', targets['document_id'])


def test_wrong_base_dimension_never_written(setup):
    adapter, _, _, _, _, edit = setup
    job = edit('Ширина', 45., revision='rev_explicit')
    assert job['status'] == 'failed' and job['error']['code'] == 'hole_edit_dimension_owner'
    assert adapter.dimension_writes == []


def test_runtime_routes_both_operations_on_existing_worker_and_releases_catalog(setup):
    adapter, catalog, store, targets, ids, _ = setup
    runtime = Runtime(store)
    runtime._catalog, runtime._dimensions = catalog.dimensions.documents, catalog.dimensions
    runtime._connection_epoch, runtime._runner = 'sketch-test', JobRunner(store, Worker())
    async def exercise():
        args = {**targets, 'dimension_id': ids['Центр Y'], 'value_mm': 11.}
        prep = await runtime.read('prepare-edit', 'part.prepare_hole_dimension_change', args)
        assert prep['status'] == 'succeeded', prep.get('error')
        result = await runtime.mutate('runtime-edit', 'part.set_hole_dimension', {**args,'expected_revision':prep['result']['revision']})
        assert result['status'] == 'succeeded', result.get('error')
    asyncio.run(exercise())
    assert len(adapter.dimension_writes) == 1
    runtime._release_catalog()
    assert runtime._hole_edits is runtime._holes is runtime._sketches is None


def test_preparation_binds_target_value_and_complete_geometry_without_writes(setup):
    adapter, catalog, _, targets, ids, _ = setup
    args = dict(targets, dimension_id=ids['Диаметр'], value_mm=8.)
    old = deepcopy(adapter.models[0].state)
    first = catalog.prepare_dimension_change(**args)
    assert first['revision_scope'] == 'single_base_circular_through_hole_dimension_v1'
    assert first['axis'] == 'diameter'
    assert catalog.prepare_dimension_change(**args)['revision'] == first['revision']
    assert catalog.prepare_dimension_change(**{**args,'value_mm':7.})['revision'] != first['revision']
    assert adapter.dimension_writes == [] and adapter.models[0].state == old


def test_target_change_inside_guard_is_stale_before_setter(setup):
    adapter, _, _, _, _, edit = setup
    adapter.guard_hook = lambda: adapter.models[0].state.update(update_stamp=999)
    job = edit()
    assert job['status'] == 'failed' and job['mutation']['phase'] == 'not_started'
    assert adapter.dimension_writes == []


def test_unsolved_setter_error_is_held_without_speculative_restore(setup):
    adapter, _, _, _, _, edit = setup
    adapter.dimension_fault = 'exception'
    job = edit()
    assert job['status'] == 'unknown'
    assert len(adapter.dimension_writes) == 1
