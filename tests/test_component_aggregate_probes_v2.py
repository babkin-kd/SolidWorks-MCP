"""Complete point/axis leaves, independent boundary/location and closing failures."""
import asyncio
from copy import deepcopy
import math
import pytest
from solidworks_mcp.component_aggregate_probes import ComponentAggregateProbeCatalog
from solidworks_mcp.documents import DocumentCatalog
from test_component_aggregate_distance_v2 import AggregateAdapter
from test_component_point_distance_v2 import PointAdapter
from test_component_axis_distance_v2 import AxisAdapter
from test_components_v2 import fails


class ProbeAdapter(AggregateAdapter,PointAdapter,AxisAdapter):
    measurement_extreme_point=AxisAdapter.measurement_extreme_point
    def __init__(self):
        super().__init__();self.axis_calls=[]
    def component_axis_distance(self,model,component,ends,direction):
        self.axis_calls.append(component)
        if self.during:self.during()
        x=component.info['transform']['origin_mm'][0]*.001
        line_x=ends[0][0]; nearest_x=max(x,min(line_x,x+.02))
        point=[nearest_x,.005,.0025];axis=[line_x,.005,.0025]
        return math.dist(point,axis),point,axis


@pytest.fixture
def setup():
    a=ProbeAdapter();d=DocumentCatalog(a);c=ComponentAggregateProbeCatalog(d)
    doc=d.list()['documents'][0];ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
    rows=c.list(**ctx)['items'];ids={r['component_path']:r['component_id'] for r in rows}
    return a,d,c,dict(ctx,component_id=ids[a.a.info['component_path']]),ids


def test_point_complete_hidden_minimum_and_owned_face_component(setup):
    a,d,c,args,ids=setup;value=c.measure_aggregate_point(**args,point_mm=[125.,5.,2.5])
    assert value['distance_mm']==pytest.approx(5.) and value['nearest_assembly_mm']==[120.,5.,2.5]
    assert value['nearest_component']['component_id']==ids[a.hidden.info['component_path']]
    assert value['leaf_component_count']==value['solid_leaf_component_count']==value['evaluated_leaf_count']==2
    assert value['solid_body_count']==2 and value['face_count']==a.point_calls==6
    assert value['point_location']=='outside' and value['inside'] is False and a.ray_calls==2
    face=c.get_topology(**{**args,'component_id':value['nearest_component']['component_id']},
                        body_id=value['nearest_body_id'],object_id=value['nearest_face_id'])['object']
    assert face['component_id']==ids[a.hidden.info['component_path']]


@pytest.mark.parametrize('point,distance,location,inside', [
    ([110.,5.,2.5],2.5,'inside',True),([120.,5.,2.5],0.,'boundary',None)])
def test_point_native_locations_across_all_bodies_positive_inside(setup,point,distance,location,inside):
    a,d,c,args,ids=setup;value=c.measure_aggregate_point(**args,point_mm=point)
    assert value['distance_mm']==pytest.approx(distance) and value['point_location']==location and value['inside'] is inside
    assert len(value['body_locations'])==2 and all('component_id' in row for row in value['body_locations'])
    assert value['distance_semantics']=='minimum_to_individual_solid_boundary'


def test_point_and_axis_explicit_frame_witnesses(setup):
    a,d,c,args,ids=setup;frame={'origin_mm':[50.,10.,20.],'axes_in_model':[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]}
    value=c.measure_aggregate_point(**args,point_mm=[-5.,-75.,-17.5],frame=frame)
    assert value['point_assembly_mm']==[125.,5.,2.5] and value['distance_mm']==pytest.approx(5.)
    assert value['nearest_mm']==pytest.approx([-5.,-70.,-17.5])
    axis=c.measure_aggregate_axis(**args,axis_origin_mm=[-10.,-35.,-17.5],axis_direction=[1.,0.,0.],frame=frame)
    assert axis['distance_mm']==pytest.approx(15.) and axis['axis_origin_assembly_mm']==[85.,0.,2.5]
    assert axis['axis_direction_assembly']==[0.,1.,0.] and axis['coordinate_frame']=='explicit_rigid_frame'
    assert math.dist(*axis['closest_points_mm'])==pytest.approx(15.)


def test_axis_hidden_leaf_minimum_all_leaves_and_no_early_zero(setup):
    a,d,c,args,ids=setup;value=c.measure_aggregate_axis(**args,axis_origin_mm=[85.,0.,2.5],axis_direction=[0.,5.,0.])
    assert value['distance_mm']==pytest.approx(15.) and value['nearest_component']['component_id']==ids[a.hidden.info['component_path']]
    assert value['axis_semantics']=='infinite_line' and value['axis_direction']==[0.,1.,0.]
    assert len(a.axis_calls)==2 and len(a.support_calls)==8
    a.axis_calls.clear();value=c.measure_aggregate_axis(**args,axis_origin_mm=[5.,1e9,2.5],axis_direction=[0.,-1e300,0.])
    assert value['distance_mm']==0. and len(a.axis_calls)==2


@pytest.mark.parametrize('kind',['point','axis'])
def test_nonsolid_leaves_excluded_but_census_closed(setup,kind):
    a,d,c,args,ids=setup;extra=a.add(a.a.info['component_path']+'/Пустая деталь-1',parent=a.a);extra.bodies=[a.body(surface=True)]
    invoke=lambda:c.measure_aggregate_point(**args,point_mm=[125.,5.,2.5]) if kind=='point' else c.measure_aggregate_axis(**args,axis_origin_mm=[85.,0.,2.5],axis_direction=[0.,1.,0.])
    value=invoke();assert value['leaf_component_count']==3 and value['solid_leaf_component_count']==2
    assert value['excluded_nonsolid_leaf_component_count']==1
    def mutate():extra.bodies.append(a.body())
    a.during=mutate;fails('component_geometry_changed_during_measurement',invoke)


@pytest.mark.parametrize('kind',['point','axis'])
@pytest.mark.parametrize('change,code',[('moments','component_geometry_changed_during_measurement'),
    ('transform','component_changed_during_read'),('configuration','component_changed_during_read'),
    ('stamp','document_changed_during_read')])
def test_nonwinning_leaf_and_root_changes_refuse_complete_result(setup,kind,change,code):
    a,d,c,args,ids=setup
    def mutate():
        if change=='moments':a.first.bodies[0].moments=[2.]*12
        elif change=='transform':a.first.info['transform']['origin_mm'][2]+=1.
        elif change=='configuration':a.first.info['referenced_configuration']='Вариант'
        else:a.models[0].state['update_stamp']+=1
    a.during=mutate
    invoke=lambda:c.measure_aggregate_point(**args,point_mm=[125.,5.,2.5]) if kind=='point' else c.measure_aggregate_axis(**args,axis_origin_mm=[85.,0.,2.5],axis_direction=[0.,1.,0.])
    fails(code,invoke)


def test_complete_face_budget_before_any_closest_point(setup):
    a,d,c,args,ids=setup;c.MAX_AGGREGATE_FACES=5
    fails('topology_budget_exceeded',lambda:c.measure_aggregate_point(**args,point_mm=[125.,5.,2.5]))
    assert a.point_calls==a.ray_calls==0


def test_changed_nonwinning_exact_axis_supports_not_masked_by_moments(setup):
    a,d,c,args,ids=setup
    def mutate():a.first.bodies[0].high=[.02,.02,.005]
    a.during=mutate
    fails('component_geometry_changed_during_measurement',lambda:c.measure_aggregate_axis(
        **args,axis_origin_mm=[85.,0.,2.5],axis_direction=[0.,1.,0.]))


@pytest.mark.parametrize('kind',['point','axis'])
@pytest.mark.parametrize('attribute,value',[('MAX_AGGREGATE_LEAVES',1),('MAX_AGGREGATE_BODIES',1)])
def test_aggregate_limits_before_any_native_solver(setup,kind,attribute,value):
    a,d,c,args,ids=setup;setattr(c,attribute,value)
    invoke=lambda:c.measure_aggregate_point(**args,point_mm=[125.,5.,2.5]) if kind=='point' else c.measure_aggregate_axis(
        **args,axis_origin_mm=[85.,0.,2.5],axis_direction=[0.,1.,0.])
    fails('component_aggregate_budget_exceeded',invoke)
    assert a.point_calls==0 and not a.axis_calls and not a.support_calls


def test_all_nonsolid_target_and_zero_direction_before_solver(setup):
    a,d,c,args,ids=setup;a.first.bodies=[];a.hidden.bodies=[a.body(surface=True)]
    fails('component_has_no_solid_bodies',lambda:c.measure_aggregate_point(**args,point_mm=[0.,0.,0.]))
    fails('component_has_no_solid_bodies',lambda:c.measure_aggregate_axis(**args,axis_origin_mm=[0.,0.,0.],axis_direction=[0.,1.,0.]))
    before=a.enumerations;fails('invalid_measurement_axis',lambda:c.measure_aggregate_axis(**args,axis_origin_mm=[0.,0.,0.],axis_direction=[0.,0.,0.]))
    assert a.enumerations==before and not a.axis_calls and a.point_calls==0


@pytest.mark.parametrize('kind',['point','axis'])
def test_runtime_shared_references_readonly_replay_and_conflict(tmp_path,kind):
    from solidworks_mcp.runtime_v2 import Runtime
    from solidworks_mcp.jobs import JobStore,JobError
    from test_runtime_v2 import Worker
    a=ProbeAdapter();store=JobStore(tmp_path/'jobs.sqlite')
    runtime=Runtime(store,worker_factory=Worker,catalog_factory=lambda:DocumentCatalog(a))
    async def exercise():
        doc=(await runtime.read('d','document.list',{}))['result']['documents'][0]
        ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
        rows=(await runtime.read('c','component.list',ctx))['result']['items']
        target=next(row for row in rows if row['component_path']==a.a.info['component_path'])
        args=dict(ctx,component_id=target['component_id'],frame=None)
        args.update(point_mm=[125.,5.,2.5]) if kind=='point' else args.update(axis_origin_mm=[85.,0.,2.5],axis_direction=[0.,1.,0.])
        operation='measurement.component_aggregate_'+kind+'_distance'
        result=await runtime.read('m',operation,args);assert result['status']=='succeeded'
        counts=(a.point_calls,len(a.axis_calls));assert await runtime.read('m',operation,args)==result
        assert counts==(a.point_calls,len(a.axis_calls))
        with pytest.raises(JobError):await runtime.read('m',operation,{**args,'component_id':'foreign'})
        assert all(row['payload']['mutates'] is False for row in store.list()['items'])
    try:asyncio.run(exercise())
    finally:assert runtime.shutdown();assert runtime._component_aggregate_probes is None;store.close()
