"""Infinite-axis semantics, exact supports, instance races and read-only replay."""
import asyncio
from copy import deepcopy
import math
import pytest
from solidworks_mcp.axis_measurement import unit_direction, anchor_axis, bracket_axis, check_axis_witnesses
from solidworks_mcp.component_axis_distance import ComponentAxisDistanceCatalog
from solidworks_mcp.documents import DocumentCatalog
from test_components_v2 import Adapter, fails


class AxisAdapter(Adapter):
    def __init__(self):
        super().__init__();self.calls=0;self.support_calls=[];self.during=None
        self.raw=(.005,[.02,.005,.0025],[.025,.005,.0025])
        for c in self.instances:
            c.info['transform']['axes_in_assembly']=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]

    def mass_body_signature(self, body):return getattr(body,'moments',[1.]*12)

    def measurement_extreme_point(self, body, direction):
        self.support_calls.append((body,direction))
        if getattr(body,'bad_support',False):return [float('nan'),0.,0.]
        high=getattr(body,'high',[.02,.01,.005]);low=getattr(body,'low',[0.]*3)
        return [hi if d>=0 else lo for hi,lo,d in zip(high,low,direction)]

    def component_axis_distance(self, model, component, ends, direction):
        self.calls+=1;self.last=(component,ends,direction)
        if self.during:self.during()
        return deepcopy(self.raw)


@pytest.fixture
def setup():
    a=AxisAdapter();d=DocumentCatalog(a);c=ComponentAxisDistanceCatalog(d);doc=d.list()['documents'][0]
    ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
    rows=c.list(**ctx)['items']
    return a,d,c,dict(ctx,component_id=rows[0]['component_id'],axis_origin_mm=[25.,0.,2.5],axis_direction=[0.,5.,0.])


def test_certified_span_all_hidden_solids_excludes_surface_and_closes_supports(setup):
    a,d,c,args=setup;solid=a.instances[0].bodies[0];hidden=a.body();hidden.high=[.02,.04,.005]
    surface=a.body(surface=True);a.instances[0].bodies += [hidden,surface]
    got=c.measure_axis(**args)
    assert got['distance_mm']==5. and got['closest_points_mm']==[[20.,5.,2.5],[25.,5.,2.5]]
    assert got['axis_direction']==[0.,1.,0.] and got['axis_semantics']=='infinite_line'
    assert got['solid_body_count']==2 and got['includes_surface_bodies'] is False
    assert got['includes_hidden_bodies'] is True and got['intersection_classification']=='not_provided'
    assert got['coordinate_frame']=='assembly_model' and got['measurement_scope']=='resolved_part_component_axis_distance_v1'
    assert len(a.support_calls)==8 and all(b is not surface for b,_ in a.support_calls)
    assert a.last[1][0][1]<0. and a.last[1][1][1]>.04 and a.calls==1


def test_origin_along_infinite_line_and_reversed_scaled_direction_do_not_limit_span(setup):
    a,d,c,args=setup
    got=c.measure_axis(**{**args,'axis_origin_mm':[25.,1e9,2.5],'axis_direction':[0.,-1e300,0.]})
    assert got['distance_mm']==5. and got['axis_direction']==[0.,-1.,0.]
    assert max(abs(x) for p in a.last[1] for x in p)<.1


def test_rigid_frame_rotated_instance_and_witness_projection(setup):
    a,d,c,args=setup;transform=a.instances[0].info['transform']
    transform.update(origin_mm=[50.,10.,20.],axes_in_assembly=[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]])
    frame={'origin_mm':[50.,10.,20.],'axes_in_model':transform['axes_in_assembly']}
    a.raw=(.005,[.045,.03,.0225],[.045,.035,.0225])
    got=c.measure_axis(**args,frame=frame)
    assert got['coordinate_frame']=='explicit_rigid_frame'
    assert got['axis_direction_assembly']==[-1.,0.,0.]
    assert got['closest_points_assembly_mm']==[[45.,30.,22.5],[45.,35.,22.5]]
    assert all(math.dist(x,y)<1e-9 for x,y in zip(got['closest_points_mm'],[[20.,5.,2.5],[25.,5.,2.5]]))
    assert a.support_calls[0][1]==[0.,-1.,0.]


@pytest.mark.parametrize('direction',[None,[],[0.]*3,[True,0.,0.],[float('nan'),0.,0.],[float('inf'),0.,0.],['1',0.,0.]])
def test_invalid_axis_before_native_census(setup,direction):
    a,d,c,args=setup;before=a.enumerations
    fails('invalid_measurement_axis',lambda:c.measure_axis(**{**args,'axis_direction':direction}));assert a.enumerations==before and a.calls==0


@pytest.mark.parametrize('raw,code',[
    ((-1.,[0.]*3,[0.]*3),'component_distance_unavailable'),
    ((.003,[.02,.005,.0025],[.025,.005,.0025]),'component_distance_inconsistent'),
    ((.005,[.02,.005,.0035],[.025,.005,.0035]),'component_axis_distance_inconsistent'),
    ((.005,[.02,.025,.0025],[.025,.025,.0025]),'component_axis_distance_inconsistent'),
    ((.005,[.025,0.,.0025],[.025,.005,.0025]),'component_axis_distance_inconsistent')])
def test_invalid_distance_off_axis_outside_support_or_nonorthogonal_witness_refused(setup,raw,code):
    a,d,c,args=setup;a.raw=raw;fails(code,lambda:c.measure_axis(**args))


@pytest.mark.parametrize('change,code',[
    ('support','component_geometry_changed_during_measurement'),('moments','component_geometry_changed_during_measurement'),
    ('body','component_geometry_changed_during_measurement'),('transform','component_changed_during_read'),('stamp','document_changed_during_read')])
def test_native_state_change_during_solver_refused(setup,change,code):
    a,d,c,args=setup
    def mutate():
        if change=='support':a.instances[0].bodies[0].high=[.02,.011,.005]
        elif change=='moments':a.instances[0].bodies[0].moments=[2.]*12
        elif change=='body':a.instances[0].bodies.append(a.body())
        elif change=='transform':a.instances[0].info['transform']['origin_mm'][0]+=1.
        else:a.models[0].state['update_stamp']+=1
    a.during=mutate;fails(code,lambda:c.measure_axis(**args))


def test_zero_supported_but_no_interference_classification(setup):
    a,d,c,args=setup;a.raw=(0.,[.01,.005,.0025],[.01,.005,.0025])
    assert c.measure_axis(**{**args,'axis_origin_mm':[10.,0.,2.5]})['distance_mm']==0.


def test_explicit_context_subassembly_surface_only_and_bad_support(setup):
    a,d,c,args=setup
    for change,code in [({'expected_observation_revision':'old'},'observation_revision_mismatch'),({'configuration':'Вариант'},'configuration_not_active'),({'component_id':'foreign'},'component_reference_not_found')]:
        fails(code,lambda:c.measure_axis(**{**args,**change}))
    a.instances[0].bodies[0].bad_support=True;fails('native_axis_support_unavailable',lambda:c.measure_axis(**args))
    a.instances[0].bodies=[a.body(surface=True)];fails('component_has_no_solid_bodies',lambda:c.measure_axis(**args))
    a.instances[0].info['referenced_document_type']='assembly';fails('unsupported_component_type',lambda:c.measure_axis(**args));assert a.calls==0


def test_unit_norm_no_overflow_underflow_and_far_anchor_math():
    assert unit_direction([1e308]*3)==pytest.approx([1/math.sqrt(3)]*3)
    assert unit_direction([1e-320,0.,0.])==[1.,0.,0.]
    anchor=anchor_axis([.025,1000.,.0025],[0.,1.,0.],[0.]*3)
    ends,r=bracket_axis(anchor,[0.,1.,0.],[(0.,.01)])
    assert ends[0][1]<0. and ends[1][1]>.01 and r==[0.,.01]
    check_axis_witnesses([[.02,.005,.0025],[.025,.005,.0025]],anchor,[0.,1.,0.],r)


def test_mirrored_instance_support_direction_and_world_points(setup):
    a,d,c,args=setup;a.instances[0].info['transform']['axes_in_assembly'][0]=[-1.,0.,0.]
    a.raw=(.01,[-.01,.01,.0025],[-.01,.02,.0025])
    got=c.measure_axis(**{**args,'axis_origin_mm':[0.,20.,2.5],'axis_direction':[1.,0.,0.]})
    assert got['distance_mm']==10. and a.support_calls[0][1]==[1.,0.,0.]
    assert a.last[1][0][0]<-.02 and a.last[1][1][0]>0.


def test_bad_frame_and_overflow_before_solver(setup):
    a,d,c,args=setup
    fails('invalid_measurement_frame',lambda:c.measure_axis(**args,frame={'origin_mm':[0.]*3,'axes_in_model':[[2.,0.,0.],[0.,1.,0.],[0.,0.,1.]]}))
    fails('measurement_numeric_overflow',lambda:c.measure_axis(**{**args,'axis_origin_mm':[1e308,0.,0.]},frame={'origin_mm':[1e308,0.,0.],'axes_in_model':[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]}))
    assert a.calls==0


def test_runtime_shared_instance_ids_replay_and_conflict(tmp_path):
    from solidworks_mcp.runtime_v2 import Runtime
    from solidworks_mcp.jobs import JobStore,JobError
    from test_runtime_v2 import Worker
    a=AxisAdapter();store=JobStore(tmp_path/'jobs.sqlite');runtime=Runtime(store,worker_factory=Worker,catalog_factory=lambda:DocumentCatalog(a))
    async def exercise():
        doc=(await runtime.read('d','document.list',{}))['result']['documents'][0]
        ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
        cid=(await runtime.read('c','component.list',ctx))['result']['items'][0]['component_id']
        args={**ctx,'component_id':cid,'axis_origin_mm':[25.,0.,2.5],'axis_direction':[0.,1.,0.],'frame':None}
        got=await runtime.read('a','measurement.component_axis_distance',args);assert got['status']=='succeeded'
        assert await runtime.read('a','measurement.component_axis_distance',args)==got and a.calls==1
        with pytest.raises(JobError):await runtime.read('a','measurement.component_axis_distance',{**args,'axis_direction':[0.,2.,0.]})
        assert all(job['payload']['mutates'] is False for job in store.list()['items'])
    try:asyncio.run(exercise())
    finally:assert runtime.shutdown() is True;store.close()
