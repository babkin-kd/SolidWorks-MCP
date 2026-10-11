"""Distance context, solver evidence and closing geometry/instance boundaries."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
import pytest
from solidworks_mcp.component_distance import ComponentDistanceCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.cad_components import CadComponentsMixin
from test_components_v2 import Adapter, fails


class DistanceAdapter(Adapter):
    def __init__(self):
        super().__init__();self.calls=0;self.during=None
        self.raw=(.03,(.02,0.,0.),(.05,0.,0.))

    def mass_body_signature(self, body):
        return getattr(body, 'moments', [1.]*12)

    def component_distance(self, model, first, second):
        self.calls+=1
        if self.during:self.during()
        return deepcopy(self.raw)


@pytest.fixture
def setup():
    a=DistanceAdapter();d=DocumentCatalog(a);c=ComponentDistanceCatalog(d)
    doc=d.list()['documents'][0]
    ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
    rows=c.list(**ctx)['items']
    args=dict(ctx,component_a_id=rows[0]['component_id'],component_b_id=rows[1]['component_id'])
    return a,d,c,args


def test_distance_native_witnesses_units_hidden_and_same_file_instances(setup):
    a,d,c,args=setup;a.instances[0].bodies.append(a.body(surface=True))
    got=c.measure(**args)
    assert got['distance_mm']==30. and got['closest_points_mm']==[[20.,0.,0.],[50.,0.,0.]]
    assert got['coordinate_frame']=='assembly_model' and got['length_unit']=='mm'
    assert got['measurement_scope']=='resolved_part_component_distance_v1'
    assert got['solid_body_counts']==[1,1] and got['includes_surface_bodies'] is False
    assert got['includes_hidden_bodies'] is True and got['intersection_classification']=='not_provided'
    assert got['component_a']['component_id']==args['component_a_id']
    assert got['component_b']['component_id']==args['component_b_id']
    assert got['component_a']['referenced_path']==got['component_b']['referenced_path']
    assert a.calls==1


@pytest.mark.parametrize('raw',[None,[],(-1.,[0.]*3,[0.]*3),(float('nan'),[0.]*3,[0.]*3),
    (True,[0.]*3,[0.]*3),(0.,None,[0.]*3),(0.,[False,0.,0.],[0.]*3),
    (0.,[0.]*2,[0.]*3),(0.,[float('inf'),0.,0.],[0.]*3),
    (0.,[1e308]*3,[1e308]*3)])
def test_invalid_native_result_has_no_success(setup,raw):
    a,d,c,args=setup;a.raw=raw
    fails('component_distance_unavailable',lambda:c.measure(**args))


def test_solver_points_must_agree_with_distance_and_zero_is_allowed(setup):
    a,d,c,args=setup;a.raw=(.03,[0.]*3,[.02,0.,0.])
    fails('component_distance_inconsistent',lambda:c.measure(**args))
    a.raw=(0.,[.02,0.,0.],[.02,0.,0.]);assert c.measure(**args)['distance_mm']==0.


@pytest.mark.parametrize('change,code',[
    ({'expected_observation_revision':'old'},'observation_revision_mismatch'),
    ({'configuration':'Вариант'},'configuration_not_active'),
    ({'component_b_id':'foreign'},'component_reference_not_found')])
def test_explicit_targets_before_native_solver(setup,change,code):
    a,d,c,args=setup;fails(code,lambda:c.measure(**{**args,**change}));assert a.calls==0


def test_identical_instance_and_surface_only_subassembly_targets_refused(setup):
    a,d,c,args=setup
    fails('same_component_target',lambda:c.measure(**{**args,'component_b_id':args['component_a_id']}))
    a.instances[1].bodies=[a.body(surface=True)]
    fails('component_has_no_solid_bodies',lambda:c.measure(**args))
    a.instances[1].info['referenced_document_type']='assembly'
    fails('unsupported_component_type',lambda:c.measure(**args));assert a.calls==0


@pytest.mark.parametrize('change,code',[
    ('moments','component_geometry_changed_during_measurement'),
    ('body','component_geometry_changed_during_measurement'),
    ('transform','component_changed_during_read'),('stamp','document_changed_during_read')])
def test_changed_native_state_during_solver_rejects(setup,change,code):
    a,d,c,args=setup
    def mutate():
        if change=='moments':a.instances[0].bodies[0].moments=[2.]*12
        elif change=='body':a.instances[0].bodies.append(a.body())
        elif change=='transform':a.instances[1].info['transform']['origin_mm'][0]+=1.
        else:a.models[0].state['update_stamp']+=1
    a.during=mutate;fails(code,lambda:c.measure(**args))


def test_native_adapter_uses_explicit_objects_and_out_tuple():
    a,b=object(),object();calls=[]
    def closest(first,second):calls.append((first,second));return .03,[.02,0.,0.],[.05,0.,0.]
    raw=CadComponentsMixin().component_distance(SimpleNamespace(ClosestDistance=closest),a,b)
    assert calls==[(a,b)] and raw[0]==.03


def test_runtime_distance_routes_shared_instance_ids_and_replay(tmp_path):
    from solidworks_mcp.runtime_v2 import Runtime
    from solidworks_mcp.jobs import JobStore
    from test_runtime_v2 import Worker
    a=DistanceAdapter();store=JobStore(tmp_path/'jobs.sqlite')
    runtime=Runtime(store,worker_factory=Worker,catalog_factory=lambda:DocumentCatalog(a))
    async def exercise():
        doc=(await runtime.read('d','document.list',{}))['result']['documents'][0]
        ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
        rows=(await runtime.read('c','component.list',ctx))['result']['items']
        args={**ctx,'component_a_id':rows[0]['component_id'],'component_b_id':rows[1]['component_id']}
        got=await runtime.read('m','measurement.component_distance',args);assert got['status']=='succeeded'
        assert await runtime.read('m','measurement.component_distance',args)==got and a.calls==1
        assert all(job['payload']['mutates'] is False for job in store.list()['items'])
    try:asyncio.run(exercise())
    finally:assert runtime.shutdown() is True;store.close()
