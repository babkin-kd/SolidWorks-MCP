"""Complete native-parent leaf sets, all pair minimum, shared witnesses and races."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace as NS
import math
import pytest
from solidworks_mcp.component_aggregate_distance import ComponentAggregateDistanceCatalog
from solidworks_mcp.documents import DocumentCatalog
from test_components_v2 import Adapter, fails


class AggregateAdapter(Adapter):
    def __init__(self):
        super().__init__();self.calls=[];self.supports=0;self.during=None;self.raw=None
        first,second=self.instances;self.instances=[]
        a=self.add('Подсборка А-1',assembly=True);b=self.add('Подсборка Б-1',assembly=True)
        self.a=a;self.b=b
        for c,parent,x in ((first,a,0.),(second,b,135.)):
            c.parent=parent;c.info['component_path']=parent.info['component_path']+'/'+c.info['component_path']
            c.info['transform']={'origin_mm':[x,0.,0.],'axes_in_assembly':[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]}
            self.instances.append(c)
        self.first=first;self.second=second
        self.hidden=self.add(a.info['component_path']+'/Скрытая деталь-1',parent=a,x=100.)
        self.hidden.info['hidden']=True
        self.far=self.add(b.info['component_path']+'/Дальняя деталь-1',parent=b,x=300.)

    def add(self,name,*,parent=None,x=0.,assembly=False):
        c=NS(identity=object(),persistent_id=('new'+str(len(self.registry))).encode(),parent=parent,bodies=[] if assembly else [self.body()],cfg='Основная')
        c.info=dict(component_path=name,referenced_path='C:/same.sldasm' if assembly else 'C:/one.sldprt',referenced_configuration='Основная',
            referenced_document_type='assembly' if assembly else 'part',suppression_state='resolved',native_suppression_state=2,hidden=False,
            transform={'origin_mm':[x,0.,0.],'axes_in_assembly':[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]})
        self.registry[c.persistent_id]=c;self.instances.append(c);return c

    def mass_body_signature(self,body):return getattr(body,'moments',[1.]*12)

    def measurement_extreme_point(self,body,direction):self.supports+=1;return [.02,0.,0.]

    def component_distance(self,model,a,b):
        self.calls.append((a,b))
        if self.during:self.during()
        if self.raw is not None:return deepcopy(self.raw)
        first=[];second=[]
        for x,y,span in zip(a.info['transform']['origin_mm'],b.info['transform']['origin_mm'],(20.,10.,5.)):
            if x+span<y:p,q=x+span,y
            elif y+span<x:p,q=x,y+span
            else:p=q=max(x,y)
            first.append(p*.001);second.append(q*.001)
        return math.dist(first,second),first,second


@pytest.fixture
def setup():
    a=AggregateAdapter();d=DocumentCatalog(a);c=ComponentAggregateDistanceCatalog(d);doc=d.list()['documents'][0]
    ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
    rows=c.list(**ctx)['items'];ids={r['component_path']:r['component_id'] for r in rows}
    args=dict(ctx,component_a_id=ids[a.a.info['component_path']],component_b_id=ids[a.b.info['component_path']])
    return a,d,c,args,ids


def test_all_four_pairs_minimum_is_hidden_leaf_and_original_instance_ids(setup):
    a,d,c,args,ids=setup;got=c.measure_aggregate(**args)
    assert got['distance_mm']==pytest.approx(15.) and got['closest_points_assembly_mm']==[[120.,0.,0.],[135.,0.,0.]]
    assert got['leaf_component_counts']==got['solid_leaf_component_counts']==got['solid_body_counts']==[2,2]
    assert got['evaluated_pair_count']==got['native_pair_count']==len(a.calls)==4
    assert got['shared_instance_pair_count']==0 and got['excluded_nonsolid_leaf_component_counts']==[0,0]
    assert got['nearest_component_a']['component_id']==ids[a.hidden.info['component_path']]
    assert got['nearest_component_b']['component_id']==ids[a.second.info['component_path']]
    assert all(x.info['referenced_document_type']=='part' and y.info['referenced_document_type']=='part' for x,y in a.calls)
    assert got['includes_hidden_components'] is True and got['includes_surface_bodies'] is False
    assert got['measurement_scope']=='resolved_component_aggregate_distance_v1'
    assert got['intersection_classification']=='not_provided'


def test_shared_descendant_exact_zero_without_native_self_solver(setup):
    a,d,c,args,ids=setup;got=c.measure_aggregate(**{**args,'component_b_id':ids[a.first.info['component_path']]})
    assert got['distance_mm']==0. and got['closest_points_mm']==[[20.,0.,0.],[20.,0.,0.]]
    assert got['native_pair_count']==len(a.calls)==1 and got['shared_instance_pair_count']==a.supports==1
    assert got['nearest_component_a']['component_id']==got['nearest_component_b']['component_id']
    assert all(x is not y for x,y in a.calls)


def test_part_targets_and_explicit_frame_are_supported_without_parent_bodies(setup):
    a,d,c,args,ids=setup;frame={'origin_mm':[50.,10.,20.],'axes_in_model':[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]}
    got=c.measure_aggregate(**{**args,'component_a_id':ids[a.first.info['component_path']],'component_b_id':ids[a.second.info['component_path']]},frame=frame)
    assert got['distance_mm']==115. and got['leaf_component_counts']==[1,1]
    assert got['coordinate_frame']=='explicit_rigid_frame' and got['closest_points_mm']==[[-10.,30.,-20.],[-10.,-85.,-20.]]


def test_nonsolid_empty_leaves_counted_excluded_and_body_readback_checked(setup):
    a,d,c,args,ids=setup;a.first.bodies=[a.body(surface=True)];a.far.bodies=[]
    got=c.measure_aggregate(**args)
    assert got['distance_mm']==pytest.approx(15.) and got['leaf_component_counts']==[2,2]
    assert got['solid_leaf_component_counts']==[1,1] and got['excluded_nonsolid_leaf_component_counts']==[1,1]
    assert len(a.calls)==1
    def mutate():a.far.bodies=[a.body()]
    a.during=mutate;fails('component_geometry_changed_during_measurement',lambda:c.measure_aggregate(**args))


def test_empty_subassembly_and_all_surface_group_refused(setup):
    a,d,c,args,ids=setup;a.first.bodies=[];a.hidden.bodies=[a.body(surface=True)]
    fails('component_has_no_solid_bodies',lambda:c.measure_aggregate(**args));assert not a.calls
    a.instances=[x for x in a.instances if x.parent is not a.a]
    fails('component_has_no_solid_bodies',lambda:c.measure_aggregate(**args));assert not a.calls


def test_multi_level_membership_uses_native_parent_and_preserves_leaf_scope(setup):
    a,d,c,args,ids=setup;nested=a.add(a.a.info['component_path']+'/Вложенная подсборка-1',parent=a.a,assembly=True)
    a.hidden.parent=nested;a.hidden.info['component_path']=nested.info['component_path']+'/Скрытая деталь-1'
    got=c.measure_aggregate(**args)
    assert got['distance_mm']==pytest.approx(15.) and got['leaf_component_counts']==[2,2] and len(a.calls)==4


@pytest.mark.parametrize('attr,value,code',[('MAX_AGGREGATE_LEAVES',1,'component_aggregate_budget_exceeded'),
    ('MAX_AGGREGATE_BODIES',3,'component_aggregate_budget_exceeded'),('MAX_DISTANCE_PAIRS',3,'component_distance_budget_exceeded')])
def test_declared_budgets_fail_before_solver_without_partial_result(setup,attr,value,code):
    a,d,c,args,ids=setup;setattr(c,attr,value);fails(code,lambda:c.measure_aggregate(**args));assert not a.calls


@pytest.mark.parametrize('change,code',[
    ('moments','component_geometry_changed_during_measurement'),('body','component_geometry_changed_during_measurement'),
    ('surface','component_geometry_changed_during_measurement'),('transform','component_changed_during_read'),
    ('parent','component_changed_during_read'),('cfg','component_changed_during_read'),('stamp','document_changed_during_read')])
def test_changes_in_any_leaf_or_hierarchy_reject_even_nonwinning_pair(setup,change,code):
    a,d,c,args,ids=setup
    def mutate():
        if len(a.calls)!=1:return
        if change=='moments':a.far.bodies[0].moments=[2.]*12
        elif change=='body':a.far.bodies.append(a.body())
        elif change=='surface':a.far.bodies.append(a.body(surface=True))
        elif change=='transform':a.far.info['transform']['origin_mm'][0]+=1.
        elif change=='parent':a.far.parent=a.a;a.far.info['component_path']=a.a.info['component_path']+'/Перемещённая деталь-1'
        elif change=='cfg':a.far.info['referenced_configuration']='Вариант'
        else:a.models[0].state['update_stamp']+=1
    a.during=mutate;fails(code,lambda:c.measure_aggregate(**args))


@pytest.mark.parametrize('change,code',[
    ({'expected_observation_revision':'old'},'observation_revision_mismatch'),({'configuration':'Вариант'},'configuration_not_active'),
    ({'component_b_id':'foreign'},'component_reference_not_found')])
def test_preflight_context_before_solver(setup,change,code):
    a,d,c,args,ids=setup;fails(code,lambda:c.measure_aggregate(**{**args,**change}));assert not a.calls


def test_invalid_frame_same_target_unresolved_and_native_failure_not_partial(setup):
    a,d,c,args,ids=setup
    fails('invalid_measurement_frame',lambda:c.measure_aggregate(**args,frame={'origin_mm':[0.]*3,'axes_in_model':[[2.,0.,0.],[0.,1.,0.],[0.,0.,1.]]}))
    fails('same_component_target',lambda:c.measure_aggregate(**{**args,'component_b_id':args['component_a_id']}))
    a.hidden.info['native_suppression_state']=1;fails('component_not_resolved',lambda:c.measure_aggregate(**args));assert not a.calls
    a.hidden.info['native_suppression_state']=2;a.raw=(-1.,[0.]*3,[0.]*3)
    fails('component_distance_unavailable',lambda:c.measure_aggregate(**args));assert len(a.calls)==1


def test_duplicate_and_part_with_descendants_hierarchy_refused(setup):
    a,d,c,args,ids=setup;entry,obs,ident=c._context(args['document_id'],args['configuration'],args['expected_observation_revision'])
    rows=c._snapshot(entry,args['configuration'],ident);target=next(r for r in rows if r[1] is a.a)
    fails('component_roster_invalid',lambda:c._leaves(rows+rows[:1],target))
    part=next(r for r in rows if r[1] is a.first);part[2]['referenced_document_type']='part'
    target[2]['parent_component_id']=part[0].object_id
    fails('component_hierarchy_invalid',lambda:c._leaves(rows,part))


def test_runtime_shared_ids_replay_conflict_and_read_only_journal(tmp_path):
    from solidworks_mcp.runtime_v2 import Runtime
    from solidworks_mcp.jobs import JobStore,JobError
    from test_runtime_v2 import Worker
    a=AggregateAdapter();store=JobStore(tmp_path/'jobs.sqlite');r=Runtime(store,worker_factory=Worker,catalog_factory=lambda:DocumentCatalog(a))
    async def exercise():
        doc=(await r.read('d','document.list',{}))['result']['documents'][0]
        ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
        rows=(await r.read('c','component.list',ctx))['result']['items'];ids={x['component_path']:x['component_id'] for x in rows}
        args={**ctx,'component_a_id':ids[a.a.info['component_path']],'component_b_id':ids[a.b.info['component_path']],'frame':None}
        got=await r.read('m','measurement.component_aggregate_distance',args);assert got['status']=='succeeded'
        assert await r.read('m','measurement.component_aggregate_distance',args)==got and len(a.calls)==4
        with pytest.raises(JobError):await r.read('m','measurement.component_aggregate_distance',{**args,'component_a_id':args['component_b_id']})
        assert all(x['payload']['mutates'] is False for x in store.list()['items'])
    try:asyncio.run(exercise())
    finally:assert r.shutdown() is True;store.close()


def test_relist_both_targets_after_configuration_recreates_related_native_instance(setup):
    a,d,c,args,ids=setup;a.a.info['referenced_configuration']='Вариант';a.b.identity=object()
    ctx={key:args[key] for key in ('document_id','configuration','expected_observation_revision')}
    fresh={row['component_path']:row['component_id'] for row in c.list(**ctx)['items']}
    updated={**args,'component_a_id':fresh[a.a.info['component_path']]}
    fails('persistent_reference_mismatch',lambda:c.measure_aggregate(**updated));assert not a.calls
    got=c.measure_aggregate(**{**updated,'component_b_id':fresh[a.b.info['component_path']]})
    assert got['distance_mm']==pytest.approx(15.) and len(a.calls)==4
