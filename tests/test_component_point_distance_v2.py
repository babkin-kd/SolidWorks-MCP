"""Point transforms, boundary semantics and complete closing gates."""
import asyncio
import math
import pytest
from solidworks_mcp.component_point_distance import ComponentPointDistanceCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.point_measurement import RAY_DIRECTIONS
from test_component_topology_v2 import TopologyAdapter
from test_components_v2 import fails


class PointAdapter(TopologyAdapter):
    def __init__(self):
        super().__init__();self.point_calls=0;self.ray_calls=0;self.during=None;self.raw=None;self.rays=None
        for c in self.instances:c.info['transform']['axes_in_assembly']=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]

    def mass_body_signature(self,body):return getattr(body,'moments',[1.]*12)

    def face_closest_point(self,face,point):
        self.point_calls+=1
        if self.during:self.during()
        if self.raw is not None:return self.raw
        limits=[.02,.01,.005];closest=[max(0.,min(x,hi)) for x,hi in zip(point,limits)]
        if closest==point:
            _,axis,side=min((abs(x-end),i,end) for i,(x,hi) in enumerate(zip(point,limits)) for end in (0.,hi))
            closest[axis]=side
        return [*closest,0.,0.]

    def body_point_rays(self,model,body,point):
        self.ray_calls+=1;self.last_local=point
        if self.rays is not None:return self.rays
        if not all(0.<x<hi for x,hi in zip(point,(.02,.01,.005))):return 0,None
        values=[]
        for i,d in enumerate(RAY_DIRECTIONS):values.extend([0.,float(i),33.,*(x+.002*a for x,a in zip(point,d)),1.,0.,0.])
        return 3,values


@pytest.fixture
def setup():
    a=PointAdapter();d=DocumentCatalog(a);c=ComponentPointDistanceCatalog(d)
    doc=d.list()['documents'][0];ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
    rows=c.list(**ctx)['items'];args=dict(ctx,component_id=rows[0]['component_id'],point_mm=[30.,20.,20.])
    return a,d,c,args,rows


def test_trimmed_corner_boundary_distance_and_owned_face_reference(setup):
    a,d,c,args,rows=setup;a.instances[0].bodies.append(a.body(surface=True))
    got=c.measure_point(**args)
    assert got['measurement_scope']=='resolved_part_component_point_distance_v1'
    assert math.isclose(got['distance_mm'],math.sqrt(425.),abs_tol=1e-12)
    assert got['nearest_mm']==[20.,10.,5.] and got['point_location']=='outside' and got['inside'] is False
    assert got['solid_body_count']==1 and got['includes_surface_bodies'] is False and got['face_count']==3
    assert got['coordinate_frame']=='assembly_model' and got['point_mm']==args['point_mm']
    target={k:v for k,v in args.items() if k!='point_mm'}
    face=c.get_topology(**target,body_id=got['nearest_body_id'],object_id=got['nearest_face_id'])['object']
    assert face['kind']=='face' and face['component_id']==args['component_id']
    assert a.ray_calls==1


def test_inside_keeps_positive_distance_boundary_has_tristate(setup):
    a,d,c,args,rows=setup
    got=c.measure_point(**{**args,'point_mm':[10.,5.,2.5]})
    assert got['point_location']=='inside' and got['inside'] is True and got['distance_mm']==2.5
    assert got['distance_semantics']=='minimum_to_individual_solid_boundary'
    before=a.ray_calls;got=c.measure_point(**{**args,'point_mm':[20.,5.,2.5]})
    assert got['point_location']=='boundary' and got['inside'] is None and got['distance_mm']==0.
    assert got['boundary_tolerance_mm']==1e-5 and a.ray_calls==before


def test_rotated_hidden_instance_and_explicit_rigid_frame(setup):
    a,d,c,args,rows=setup
    t=a.instances[1].info['transform'];t['origin_mm']=[50.,10.,20.];t['axes_in_assembly']=[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]
    args={**args,'component_id':rows[1]['component_id'],'point_mm':[45.,20.,22.5]}
    got=c.measure_point(**args);assert got['inside'] is True and got['distance_mm']==2.5
    assert a.last_local==pytest.approx([.01,.005,.0025])
    frame=dict(origin_mm=[50.,10.,20.],axes_in_model=[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]])
    got=c.measure_point(**{**args,'point_mm':[10.,5.,2.5]},frame=frame)
    assert got['point_assembly_mm']==[45.,20.,22.5] and got['coordinate_frame']=='explicit_rigid_frame'
    assert math.isclose(math.dist(got['point_mm'],got['nearest_mm']),2.5)


@pytest.mark.parametrize('point',[None,[],[1.,2.],[True,1.,2.],['1',2.,3.],[float('nan'),0.,0.],[float('inf'),0.,0.]])
def test_bad_point_before_native_census(setup,point):
    a,d,c,args,rows=setup;before=a.enumerations
    fails('invalid_measurement_point',lambda:c.measure_point(**{**args,'point_mm':point}))
    assert a.enumerations==before and a.point_calls==a.ray_calls==0


@pytest.mark.parametrize('raw',[[],[0.,0.,0.],(0.,0.,0.,0.,float('nan')),[False,0.,0.,0.,0.]])
def test_bad_closest_xyz_uv_is_not_success(setup,raw):
    a,d,c,args,rows=setup;a.raw=raw
    fails('closest_face_point_unavailable',lambda:c.measure_point(**args))


@pytest.mark.parametrize('change,code',[
    ('faces','component_topology_changed_during_read'),('moments','component_geometry_changed_during_measurement'),
    ('body','component_geometry_changed_during_measurement'),('transform','component_changed_during_read'),
    ('stamp','document_changed_during_read')])
def test_native_change_during_point_read_rejected(setup,change,code):
    a,d,c,args,rows=setup
    def mutate():
        if a.point_calls!=1:return
        if change=='faces':a.instances[0].bodies[0].faces.pop()
        elif change=='moments':a.instances[0].bodies[0].moments=[2.]*12
        elif change=='body':a.instances[0].bodies.append(a.body())
        elif change=='transform':a.instances[0].info['transform']['origin_mm'][0]+=1.
        else:a.models[0].state['update_stamp']+=1
    a.during=mutate;fails(code,lambda:c.measure_point(**args))


def test_surface_only_subassembly_and_preflight_context(setup):
    a,d,c,args,rows=setup
    fails('observation_revision_mismatch',lambda:c.measure_point(**{**args,'expected_observation_revision':'old'}))
    fails('configuration_not_active',lambda:c.measure_point(**{**args,'configuration':'Вариант'}))
    fails('component_reference_not_found',lambda:c.measure_point(**{**args,'component_id':'foreign'}))
    a.instances[0].bodies=[a.body(surface=True)]
    fails('component_has_no_solid_bodies',lambda:c.measure_point(**args))
    a.instances[0].info['referenced_document_type']='assembly'
    fails('unsupported_component_type',lambda:c.measure_point(**args));assert a.point_calls==a.ray_calls==0


def test_ray_ambiguity_and_invalid_frame_rejected(setup):
    a,d,c,args,rows=setup;a.rays=(1,[0.,0.,33.,*(x+.002*v for x,v in zip([.03,.02,.02],RAY_DIRECTIONS[0])),1.,0.,0.])
    fails('point_classification_unavailable',lambda:c.measure_point(**args))
    fails('invalid_measurement_frame',lambda:c.measure_point(**args,frame={'origin_mm':[0.]*3,'axes_in_model':[[2.,0.,0.],[0.,1.,0.],[0.,0.,1.]]}))


def test_runtime_point_measurement_replay_and_shared_topology_ids(tmp_path):
    from solidworks_mcp.runtime_v2 import Runtime
    from solidworks_mcp.jobs import JobStore
    from test_runtime_v2 import Worker
    a=PointAdapter();store=JobStore(tmp_path/'jobs.sqlite');runtime=Runtime(store,worker_factory=Worker,catalog_factory=lambda:DocumentCatalog(a))
    async def exercise():
        doc=(await runtime.read('d','document.list',{}))['result']['documents'][0]
        ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
        cid=(await runtime.read('c','component.list',ctx))['result']['items'][0]['component_id']
        args={**ctx,'component_id':cid,'point_mm':[30.,20.,20.],'frame':None}
        got=await runtime.read('p','measurement.component_point_distance',args);assert got['status']=='succeeded'
        calls=a.point_calls;assert await runtime.read('p','measurement.component_point_distance',args)==got and a.point_calls==calls
        values=got['result'];target={**ctx,'component_id':cid,'body_id':values['nearest_body_id'],'object_id':values['nearest_face_id']}
        ref=await runtime.read('r','component.topology_get',target);assert ref['status']=='succeeded'
        assert all(job['payload']['mutates'] is False for job in store.list()['items'])
    try:asyncio.run(exercise())
    finally:assert runtime.shutdown() is True;store.close()
