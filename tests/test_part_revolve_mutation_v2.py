"""Artificial revolve effects with the actual SQLite coordinator; not CAD acceptance."""

from copy import deepcopy
import asyncio
import math

import pytest

from solidworks_mcp.jobs import ExecutionFailure, JobRunner
from solidworks_mcp.linear_sketch import LinearSketchReader
from solidworks_mcp.part_revolve import PartRevolveCatalog
from test_cylinder_brep_v2 import cylinder, read
from test_dimension_domain_v2 import dimension
from test_feature_domain_v2 import feature
from test_linear_sketch_v2 import Sketch
from test_part_construction_mutation_v2 import setup as part_setup, Worker


@pytest.fixture
def setup(part_setup):
    adapter,parts,store,ids,_ = part_setup
    catalog = PartRevolveCatalog(parts.dimensions)
    part = adapter.models[0]
    adapter.revolve_writes = adapter.revolve_restores = 0
    adapter.revolve_fault = None
    def receipt(model,features,controls):
        return adapter.new_base_receipt(model,features,controls)
    def create(model,plane,definition,value):
        checkpoint = store._db.execute('SELECT before_state FROM mutations').fetchone()
        assert checkpoint is not None and 'profile_y' in checkpoint[0]
        adapter.revolve_writes += 1
        value.definition = definition
        sketch,operation = feature(10,definition.sketch_name,kind='ProfileFeature'),feature(11,definition.feature_name,kind='Revolution')
        sketch.state['owner_native_id'] = 11
        value.owned = [sketch,operation]
        part.features += value.owned
        value.sketch = Sketch(definition.radius_mm/1000.,definition.height_mm/1000.)
        values = (('Радиус',definition.radius_mm/1000.,sketch,0),
                  ('Высота вращения',definition.height_mm/1000.,sketch,0),
                  ('Угол вращения',2.*math.pi,operation,1))
        part.dimensions = []
        for index,(name,size,owner,kind) in enumerate(values,1):
            row = dimension(index,value=size,kind=kind)
            row.owner = owner
            row.FullName = name+'@'+owner.state['name']
            row.state.update(name=name,full_name=row.FullName,values_si={'Основная':size},owner=deepcopy(owner.state),
                write_blockers=['sketch_geometry_snapshot_not_implemented'] if kind==0 else ['owner_type_not_accepted'])
            part.dimensions.append(row)
            if index <= 2: value.sketch.dimensions[index-1] = row
        value.geometry = read(cylinder(axis=(0.,1.,0.),radial=(0.,0.,1.),radius=definition.radius_mm/1000.,height=definition.height_mm/1000.))
        part.state['bodies'] = [value.geometry]
        part.state['update_stamp'] += 1
        value.complete = True
        if adapter.revolve_fault == 'foreign_feature': part.features.append(feature(90,'Чужой элемент'))
        if adapter.revolve_fault == 'foreign_radius': value.geometry['edges'][0]['circle_parameters'][6] = .012.hex()
        if adapter.revolve_fault == 'foreign_dimension': part.dimensions[0].state['values_si']['Основная'] = .012
        if adapter.revolve_fault == 'unknown': value.pending = True
        if adapter.revolve_fault: raise RuntimeError('Artificial post-creation error')
    def evidence(model,value):
        if value.pending: raise ExecutionFailure('revolve_effect_unconfirmed','Artificial unconfirmed native call',uncertain=True)
        if value.restored: return {'restored':True,'complete':False},()
        snapshot,members = LinearSketchReader(value.sketch,value.sketch.origin,wrap=lambda raw,name:raw,
                                              identity=lambda raw:getattr(raw,'identity',raw)).read()
        frame = [v.hex() for v in adapter.frame]
        snapshot.update(feature_native_id=10,feature_pid_hex=value.owned[0].pid.hex(),model_to_sketch=frame,
            reference_plane={'native_id':1,'pid_hex':part.features[0].pid.hex(),'transform':frame},
            model_origin={'feature_native_id':0,'pid_hex':'00'})
        item = value.definition
        return {'restored':False,'complete':True,'fully_defined':True,'sketch':snapshot,'controls':value.controls,
            'sketch_native_id':10,'revolution_native_id':11,'revolution_type':'Revolution','axis_verified':True,
            'body_name':item.body_name,'volume_mm3':item.volume_mm3,'surface_area_mm2':item.surface_area_mm2},members
    def restore(model,value):
        adapter.revolve_restores += 1
        adapter.restore_base_rectangle(model,value)
    adapter.new_base_revolve_receipt,adapter.create_base_revolve = receipt,create
    adapter.base_revolve_evidence,adapter.restore_base_revolve = evidence,restore
    plane = catalog.features.list(ids[0],'Основная')['items'][0]['object_id']
    args = dict(document_id=ids[0],configuration='Основная',plane_object_id=plane,radius_mm=10.,height_mm=30.)
    revision = catalog.prepare_base_revolve(**args)['revision']
    runner = JobRunner(store,Worker())
    def run(request='revolve',expected_revision=revision):
        payload = dict(args,expected_revision=expected_revision)
        return runner.submit(request,'part.create_base_revolve',payload,lambda op:catalog.create_base_revolve(op,**payload),
            context={key:payload[key] for key in ('document_id','configuration','expected_revision')},
            mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
    return adapter,catalog,store,run


def test_complete_boundary_profile_axis_and_checkpoint_commit_once(setup):
    adapter,_,_,run = setup
    other = deepcopy(adapter.models[1].state)
    result = run()
    assert result['status'] == 'succeeded',result.get('error')
    assert result['mutation']['phase'] == 'committed'
    assert run() == result and adapter.revolve_writes == 1
    assert adapter.revolve_restores == 0 and adapter.models[1].state == other


def test_stale_does_not_create_or_delete_anything(setup):
    adapter,_,_,run = setup
    assert run(expected_revision='rev_stale')['error']['code'] == 'stale_revision'
    assert adapter.revolve_writes == adapter.revolve_restores == 0


def test_runtime_routes_on_owning_worker_and_releases_candidate_handles(setup):
    from solidworks_mcp.runtime_v2 import Runtime
    adapter,catalog,store,_ = setup
    runtime = Runtime(store)
    runtime._catalog,runtime._dimensions = catalog.dimensions.documents,catalog.dimensions
    runtime._connection_epoch = 'revolve-test'
    runtime._runner = JobRunner(store,Worker())
    doc = runtime._catalog.list()['documents'][0]['document_id']
    plane = catalog.features.list(doc,'Основная')['items'][0]['object_id']
    args = dict(document_id=doc,configuration='Основная',plane_object_id=plane,radius_mm=10.,height_mm=30.)
    async def exercise():
        preparation = await runtime.read('revolve-prepare','part.prepare_base_revolve',args)
        assert preparation['status'] == 'succeeded',preparation
        payload = dict(args,expected_revision=preparation['result']['revision'])
        result = await runtime.mutate('revolve-runtime','part.create_base_revolve',payload)
        assert result['status'] == 'succeeded',result
        assert await runtime.mutate('revolve-runtime','part.create_base_revolve',payload) == result
    asyncio.run(exercise())
    assert adapter.revolve_writes == 1
    runtime._release_catalog()
    assert runtime._revolves is runtime._dimensions is None


def test_known_failure_after_exact_creation_restores_empty_part(setup):
    adapter,_,_,run = setup
    adapter.revolve_fault = 'known_exception'
    result = run()
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back',result.get('error')
    assert adapter.revolve_writes == adapter.revolve_restores == 1
    assert adapter.models[0].state['bodies'] == [] and adapter.models[0].dimensions == []


@pytest.mark.parametrize('fault',['unknown','foreign_feature','foreign_radius','foreign_dimension'])
def test_unconfirmed_or_foreign_effect_never_deleted_or_replayed(setup,fault):
    adapter,_,_,run = setup
    adapter.revolve_fault = fault
    result = run()
    assert result['status'] == 'unknown',result.get('error')
    assert adapter.revolve_restores == 0 and adapter.revolve_writes == 1
    assert run() == result
