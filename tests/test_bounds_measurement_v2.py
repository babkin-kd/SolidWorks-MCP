"""Analytical support bounds, adversarial membership and explicit frame units."""
from types import SimpleNamespace as NS
import itertools
import math
import pytest
from solidworks_mcp.bounds_measurement import BoundsMeasurementCatalog
from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.measurement_frames import measurement_frame,project_point_m
from test_geometry_v2 import setup_geometry


def rotated():
    angle=math.pi/6;c,s=math.cos(angle),math.sin(angle)
    return dict(origin_mm=[10.,-20.,3.],axes_in_model=[[c,s,0.],[-s,c,0.],[0.,0.,1.]])


@pytest.fixture
def bounds(setup_geometry):
    adapter,documents,geometry,context,listed=setup_geometry
    adapter.measurement_body_type=lambda body:body.body_type
    events=[]
    for body in adapter.registry.values():
        if body.kind=='body':body.vertices=list(itertools.product([-.002,.006],[0.,.012],[0.,.008]))
    def extreme(body,direction):
        events.append((body,direction))
        return max(body.vertices,key=lambda point:sum(a*b for a,b in zip(point,direction)))
    adapter.measurement_extreme_point=extreme
    return NS(adapter=adapter,documents=documents,geometry=geometry,ctx=context,listed=listed,
        catalog=BoundsMeasurementCatalog(documents),events=events)


def test_all_bodies_model_units_and_two_full_support_passes(bounds):
    result=bounds.catalog.measure(**bounds.ctx)
    assert result['bounding_box_mm']==dict(min_mm=[-2.,0.,0.],max_mm=[6.,12.,8.],size_mm=[8.,12.,8.])
    assert result['body_count']==2 and result['includes_hidden_bodies'] and len(bounds.events)==24
    assert result['coordinate_frame']['kind']=='model' and result['approximate_body_box_used'] is False
    assert result['read_postconditions']==dict(body_membership_confirmed=True,repeated_extrema_confirmed=True)


def test_rotated_shifted_bounds_project_real_support_points_not_box_corners(bounds):
    frame=rotated();body=bounds.adapter.registry[b'body0']
    # An oblique body occupies two opposite corners, not every corner of its AABB.
    body.vertices=[(-.002,0.,0.),(.006,.012,.008)]
    body_id=bounds.geometry.list(**bounds.ctx,body_type='solid')['items'][0]['object_id']
    result=bounds.catalog.measure(**bounds.ctx,body_id=body_id,coordinate_frame=frame)
    projected=[project_point_m(measurement_frame(frame),v) for v in body.vertices]
    assert result['bounding_box_mm']['min_mm']==pytest.approx([min(p[i] for p in projected) for i in range(3)])
    assert result['bounding_box_mm']['max_mm']==pytest.approx([max(p[i] for p in projected) for i in range(3)])
    assert result['body_count']==1 and result['coordinate_frame']['kind']=='explicit_rigid'


def test_selected_planar_surface_zero_extent(bounds):
    surface=bounds.adapter.objects[bounds.adapter.models[0].identity][1]
    surface.vertices=list(itertools.product([.080,.095],[0.,.010],[0.]))
    body_id=bounds.geometry.list(**bounds.ctx,body_type='surface')['items'][0]['object_id']
    result=bounds.catalog.measure(**bounds.ctx,body_id=body_id,body_type='surface')
    assert result['bounding_box_mm']==dict(min_mm=[80.,0.,0.],max_mm=[95.,10.,0.],size_mm=[15.,10.,0.])


@pytest.mark.parametrize('fault',['stale','inactive','foreign','face','empty','filter','rebuild','budget'])
def test_invalid_scope_rejected_before_support_read(bounds,fault):
    ctx=bounds.ctx.copy()
    if fault=='stale':ctx['expected_observation_revision']='old'
    if fault=='inactive':ctx['configuration']='Вариант'
    if fault=='foreign':
        ctx['body_id']=bounds.geometry.list(**ctx,body_type='solid')['items'][0]['object_id']
        ctx.update(document_id=bounds.listed[1]['document_id'],expected_observation_revision=bounds.listed[1]['observation_revision'])
    if fault=='face':
        body=bounds.geometry.list(**ctx,body_type='solid')['items'][0]['object_id']
        ctx['body_id']=bounds.geometry.list(**ctx,body_id=body,kind='face')['items'][0]['object_id']
    if fault=='empty':bounds.adapter.objects[bounds.adapter.models[0].identity]=[]
    if fault=='filter':
        ctx['body_id']=bounds.geometry.list(**ctx,body_type='surface')['items'][0]['object_id'];ctx['body_type']='solid'
    if fault=='rebuild':bounds.adapter.needs_rebuild=True
    if fault=='budget':
        for _ in range(499):bounds.adapter.body(faces=0)
    with pytest.raises(ExecutionFailure):bounds.catalog.measure(**ctx)
    assert not bounds.events


@pytest.mark.parametrize('fault',['geometry','identity','removed','added','configuration','stamp'])
def test_changed_read_never_reports_success(bounds,fault):
    original=bounds.adapter.measurement_extreme_point
    def extreme(body,direction):
        result=original(body,direction)
        if len(bounds.events)==12:
            if fault=='geometry':body.vertices=[(v[0]+.003,v[1],v[2]) for v in body.vertices]
            if fault=='identity':body.identity=object()
            if fault=='removed':bounds.adapter.objects[bounds.adapter.models[0].identity].pop()
            if fault=='added':bounds.adapter.body()
            if fault=='configuration':bounds.adapter.configurations[bounds.adapter.models[0].identity,'Основная']=object()
            if fault=='stamp':bounds.adapter.models[0].state['update_stamp']+=1
        return result
    bounds.adapter.measurement_extreme_point=extreme
    with pytest.raises(ExecutionFailure):bounds.catalog.measure(**bounds.ctx)


@pytest.mark.parametrize('frame',[
    {},dict(origin_mm=[0.,0.],axes_in_model=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]),
    dict(origin_mm=[float('inf'),0.,0.],axes_in_model=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]),
    dict(origin_mm=[True,0.,0.],axes_in_model=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]),
    dict(origin_mm=[0.,0.,0.],axes_in_model=[[2.,0.,0.],[0.,1.,0.],[0.,0.,1.]]),
    dict(origin_mm=[0.,0.,0.],axes_in_model=[[1.,0.,0.],[.1,1.,0.],[0.,0.,1.]]),
    dict(origin_mm=[0.,0.,0.],axes_in_model=[[1.,0.,0.],[0.,1.,0.],[0.,0.,-1.]]),
])
def test_invalid_explicit_frame_rejected_before_any_native_read(bounds,frame):
    reads=bounds.adapter.native_reads
    with pytest.raises(ExecutionFailure) as failure:bounds.catalog.measure(**bounds.ctx,coordinate_frame=frame)
    assert failure.value.code=='invalid_measurement_frame' and not bounds.events and bounds.adapter.native_reads==reads


@pytest.mark.parametrize('point',[None,[0.,0.],[0.,0.,float('nan')],[True,0.,0.],[1e308,0.,0.]])
def test_invalid_native_point_cannot_reach_json(bounds,point):
    bounds.adapter.measurement_extreme_point=lambda *args:point
    with pytest.raises(ExecutionFailure):bounds.catalog.measure(**bounds.ctx)


def test_runtime_read_routing_does_not_use_mass_guard(bounds,tmp_path):
    from solidworks_mcp.jobs import JobStore
    from solidworks_mcp.runtime_v2 import Runtime
    store=JobStore(tmp_path/'jobs.sqlite')
    try:
        runtime=Runtime(store);runtime._catalog=bounds.documents
        result=runtime._execute('measurement.bounds',bounds.ctx)
        assert result['body_count']==2 and runtime._measurements is None
        runtime._release_catalog();assert runtime._bounds is None
    finally:store.close()


def test_huge_origin_cannot_silently_erase_body_size(bounds):
    frame=dict(origin_mm=[1e30,0.,0.],axes_in_model=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    with pytest.raises(ExecutionFailure) as error:bounds.catalog.measure(**bounds.ctx,coordinate_frame=frame)
    assert error.value.code=='measurement_precision_lost'


def test_public_frame_schema_and_read_dispatch(bounds,tmp_path):
    import asyncio
    from solidworks_mcp.server_v2 import create_app
    from solidworks_mcp.jobs import JobStore
    class Runtime:
        def __init__(self):self.calls=[]
        async def read(self,request,operation,args,**kwargs):
            self.calls.append((request,operation,args,kwargs))
            return dict(status='succeeded',operation_id='job',payload={'context':args},result={'unit':'mm'},error=None)
        async def mutate(self,*args,**kwargs):pytest.fail('Bounds are a passive read, never a UI mutation')
    runtime=Runtime();store=JobStore(tmp_path/'jobs.sqlite');app=create_app(store,runtime=runtime)
    async def check():
        _,result=await app.call_tool('measurement_get_bounds',dict(bounds.ctx,request_id='bounds',coordinate_frame=rotated(),timeout_s=0.))
        assert result['status']=='succeeded' and result['data']=={'unit':'mm'}
        request,op,args,kwargs=runtime.calls[0]
        assert request=='bounds' and op=='measurement.bounds' and kwargs=={'timeout_s':0.}
        assert args['coordinate_frame']==rotated() and args['body_id'] is None and args['body_type']=='all'
        before=len(runtime.calls)
        with pytest.raises(Exception):
            await app.call_tool('measurement_get_bounds',dict(bounds.ctx,request_id='invalid',coordinate_frame={'origin_mm':[True,0.,0.],'axes_in_model':[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]}))
        assert len(runtime.calls)==before
    try:asyncio.run(check())
    finally:store.close()
