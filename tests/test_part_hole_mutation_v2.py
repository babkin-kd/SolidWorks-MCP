"""Artificial hole geometry with the real SQLite protocol; not CAD acceptance."""

from copy import deepcopy
import math

import pytest

from solidworks_mcp.jobs import ExecutionFailure,JobRunner
from solidworks_mcp.part_hole import PartHoleCatalog
from test_part_cut_mutation_v2 import setup as cut_setup
from test_sketch_dimensions_v2 import setup as sketch_setup
from test_part_construction_mutation_v2 import Worker
from test_feature_domain_v2 import feature
from test_dimension_domain_v2 import dimension
from test_circular_sketch_v2 import CircleSketch,capture
from test_planar_brep_v2 import make_body,Face,Coedge
from test_cylinder_brep_v2 import Edge,Surface,PeriodicLoop
from test_hole_brep_v2 import read


def native_shape(definition):
    body=make_body(points=[(x,y,z) for z in (0.,.01) for y,x in ((0.,0.),(0.,.04),(.02,.04),(.02,0.))])
    for edge in body.edges:edge.curve.IsCircle=lambda:False
    for face in body.faces:face.surface.IsCylinder=lambda:False
    x,y,r=definition.centre_x_mm/1000.,definition.centre_y_mm/1000.,definition.diameter_mm/2000.
    wall=Face(body,())
    wall.surface=Surface('cylinder',(x,y,-.005,0.,0.,1.,r))
    wall.sense=True
    body.faces.append(wall)
    for z,cap in zip((0.,.01),body.faces[:2]):
        normal=(0.,0.,-1.) if z==0. else (0.,0.,1.)
        edge=Edge(body,(x,y,z,*normal,r),(x+r,y,z))
        body.edges.append(edge)
        inner,outer=PeriodicLoop(cap,False),PeriodicLoop(wall,True)
        cap.loops.append(inner);wall.loops.append(outer)
        inner.ordered=[Coedge(edge,inner,False)]
        outer.ordered=[Coedge(edge,outer,True)]
    return read(body)


@pytest.fixture
def setup(cut_setup):
    adapter,cut,_,store=cut_setup
    sketches=cut.sketches
    part=adapter.models[0]
    documents=cut.dimensions.documents
    doc=documents.list()['documents'][0]['document_id']
    items=cut.dimensions.features.list(doc,'Основная')['items']
    parameters={'object_id':next(row['object_id'] for row in items if row['feature_type']=='ProfileFeature'),
        'plane_object_id':next(row['object_id'] for row in items if row['feature_type']=='RefPlane'),
        'centre_x_mm':10.,'centre_y_mm':10.,'diameter_mm':6.}
    original_snapshot=adapter.sketch_snapshot
    adapter.new_through_hole_receipt=adapter.new_corner_cut_receipt
    adapter.restore_through_hole=adapter.restore_corner_cut

    def create(model,plane,definition,value):
        latest=store.get(store.list(limit=1)['items'][0]['operation_id'])
        assert latest['mutation']['phase']=='prepared'
        adapter.cut_writes+=1
        value.definition=definition
        profile=feature(20,definition.sketch_name,kind='ProfileFeature')
        profile.state['owner_native_id']=21
        value.owned=[profile,feature(21,definition.feature_name,kind=adapter.cut_native_type2)]
        part.features+=value.owned
        value.sketch=CircleSketch()
        centre=value.sketch.points[0]
        centre.X,centre.Y=definition.centre_x_mm/1000.,definition.centre_y_mm/1000.
        value.sketch.lines[0].radius=definition.diameter_mm/2000.
        old_origin=value.sketch.origin
        value.sketch.origin=adapter.sketch.origin
        for relation in value.sketch.relations:
            relation.definitions=[value.sketch.origin if item is old_origin else item for item in relation.definitions]
        for index,(name,size) in enumerate((('Центр X',centre.X),('Центр Y',centre.Y),('Диаметр',2.*value.sketch.lines[0].radius))):
            row=dimension(40+index,value=size)
            row.owner=profile
            row.state.update(name=name,full_name=name+'@'+definition.sketch_name,
                owner=deepcopy(profile.state),values_si={'Основная':size},write_blockers=['sketch_geometry_snapshot_not_implemented'])
            row.FullName=row.state['full_name']
            part.dimensions.append(row)
            value.sketch.dimensions[index]=row
        value.expected=definition.expected_geometry({'width_m':.04,'height_m':.02,'depth_m':.01,
            'plane_transform':[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]})
        part.state['bodies']=[native_shape(definition)]
        part.state['update_stamp']+=1
        value.complete=True
        if adapter.cut_fault=='original_dimension':part.dimensions[0].state['values_si']['Основная']=.041
        if adapter.cut_fault=='foreign_feature':part.features.append(feature(99,'Чужое изменение'))
        if adapter.cut_fault=='foreign_vertex':part.state['bodies'][0]['vertices'][0][0]=(.003).hex()
        if adapter.cut_fault=='diameter':part.dimensions[-1].state['values_si']['Основная']=.007
        if adapter.cut_fault=='unknown':value.pending=True
        if adapter.cut_fault:raise RuntimeError('Artificial post-hole failure')

    def evidence(model,value):
        if value.pending:raise ExecutionFailure('cut_effect_unconfirmed','Artificial unknown effect',uncertain=True)
        if value.restored:return {'restored':True,'complete':False},()
        snapshot,members=capture(value.sketch)
        base,_=original_snapshot(model,part.features[1])
        snapshot.update({key:base[key] for key in ('model_to_sketch','reference_plane','model_origin')})
        snapshot.update(feature_native_id=20,feature_pid_hex=value.owned[0].pid.hex())
        return {'complete':True,'restored':False,'sketch_native_id':20,'cut_native_id':21,
            'cut_type_name2':adapter.cut_native_type2,'cut_type_name':adapter.cut_native_type,
            'sketch':snapshot,'fully_defined':True,'controls':value.controls,'body_name':value.baseline_body_name,
            'volume_mm3':value.expected['volume_mm3'],'surface_area_mm2':value.expected['surface_area_mm2']},members

    adapter.create_through_hole,adapter.through_hole_evidence=create,evidence
    catalog=PartHoleCatalog(sketches)
    arguments={'document_id':doc,'configuration':'Основная',**parameters}
    revision=catalog.prepare_through_hole(**arguments)['revision']
    runner=JobRunner(store,Worker())
    def run(request='hole',expected_revision=revision):
        payload={**arguments,'expected_revision':expected_revision}
        return runner.submit(request,'part.create_through_hole',payload,
            lambda op:catalog.create_through_hole(op,**payload),mutates=True,pass_operation_id=True,
            context={key:payload[key] for key in ('document_id','configuration','expected_revision')},
            verify=lambda result:result['verified'] is True)
    return adapter,catalog,run,store,arguments


def test_hole_commits_full_shape_and_same_request_does_not_cut_again(setup):
    adapter,_,run,_,_=setup
    other=deepcopy(adapter.models[1].state)
    result=run()
    assert result['status']=='succeeded',result
    assert result['mutation']['verification']['outcome']=='committed'
    assert result['result']['after']['created']['volume_mm3']==pytest.approx(8000.-math.pi*3.**2*10.)
    assert adapter.cut_writes==1 and adapter.cut_restores==0
    assert run()['operation_id']==result['operation_id'] and adapter.cut_writes==1
    assert adapter.models[1].state==other


def test_hole_stale_revision_fails_before_write_or_restore(setup):
    adapter,_,run,_,_=setup
    result=run(expected_revision='rev_stale')
    assert result['status']=='failed' and result['error']['code']=='stale_revision'
    assert adapter.cut_writes==adapter.cut_restores==0


def test_known_post_creation_failure_restores_only_own_hole(setup):
    adapter,_,run,_,_=setup
    geometry=deepcopy(adapter.models[0].state['bodies'])
    adapter.cut_fault='known'
    result=run()
    assert result['status']=='failed' and result['mutation']['verification']['outcome']=='rolled_back',result
    assert adapter.cut_writes==adapter.cut_restores==1
    assert adapter.models[0].state['bodies']==geometry and len(adapter.models[0].dimensions)==3


@pytest.mark.parametrize('fault',['unknown','original_dimension','foreign_feature','foreign_vertex','diameter'])
def test_unknown_or_foreign_effect_is_not_deleted_or_replayed(setup,fault):
    adapter,_,run,store,_=setup
    adapter.cut_fault=fault
    result=run()
    assert result['status']=='unknown',result
    assert adapter.cut_restores==0 and adapter.cut_writes==1
    assert run()['operation_id']==result['operation_id'] and adapter.cut_writes==1
    assert store.mutation_blockers('sketch-test',result['payload']['context']['document_id'])


def test_hole_preparation_binds_geometry_input_and_distinct_scope_without_write(setup):
    adapter,catalog,_,_,arguments=setup
    original=deepcopy(adapter.models[0].state)
    first=catalog.prepare_through_hole(**arguments)
    assert first['revision_scope']=='single_base_circular_through_hole_v1'
    assert catalog.prepare_through_hole(**arguments)['revision']==first['revision']
    assert catalog.prepare_through_hole(**{**arguments,'centre_x_mm':11.})['revision']!=first['revision']
    assert original==adapter.models[0].state and adapter.cut_writes==0


def test_runtime_routes_hole_on_existing_worker_and_releases_handles(setup):
    import asyncio
    from solidworks_mcp.runtime_v2 import Runtime
    adapter,catalog,_,store,arguments=setup
    runtime=Runtime(store)
    runtime._catalog,runtime._dimensions=catalog.dimensions.documents,catalog.dimensions
    runtime._connection_epoch='sketch-test'
    runtime._runner=JobRunner(store,Worker())
    async def exercise():
        prepared=await runtime.read('hole-prepare','part.prepare_through_hole',arguments)
        assert prepared['status']=='succeeded',prepared
        payload={**arguments,'expected_revision':prepared['result']['revision']}
        result=await runtime.mutate('hole-runtime','part.create_through_hole',payload)
        assert result['status']=='succeeded',result
        assert await runtime.mutate('hole-runtime','part.create_through_hole',payload)==result
    asyncio.run(exercise())
    assert adapter.cut_writes==1
    runtime._release_catalog()
    assert runtime._holes is runtime._sketches is runtime._dimensions is None
