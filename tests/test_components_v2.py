"""Instance identity, hierarchy, configuration/transform races and body ownership."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from solidworks_mcp.documents import DocumentCatalog,rejected
from solidworks_mcp.components import ComponentCatalog
from solidworks_mcp.jobs import ExecutionFailure
from test_geometry_v2 import GeometryAdapter


class Adapter(GeometryAdapter):
    def __init__(self):
        super().__init__()
        self.models[0].state['document_type']='assembly'
        self.instances=[]
        self.changed=None
        self.enumerations=0
        self.part=object()
        self.cfgs={'Основная':object(),'Вариант':object()}
        for index,cfg in enumerate(('Основная','Вариант')):
            body=self.body()
            c=SimpleNamespace(identity=object(),persistent_id=f'component{index}'.encode(),parent=None,bodies=[body],cfg=cfg)
            c.info=dict(component_path=f'Контрольная деталь-{index+1}',referenced_path='C:/one.sldprt',
                referenced_configuration=cfg,referenced_document_type='part',suppression_state='resolved',
                native_suppression_state=2,hidden=index==1,transform={'origin_mm':[index*50.,0.,0.]})
            self.registry[c.persistent_id]=c
            self.instances.append(c)

    def components(self,model):
        self.enumerations+=1
        if self.changed:self.changed()
        return list(reversed(self.instances)) if self.enumerations%2 else list(self.instances)

    def component_info(self,c):
        if c.info['native_suppression_state'] not in (2,3):raise rejected('component_not_resolved','Artificial state')
        return deepcopy(c.info),(self.part,self.cfgs[c.info['referenced_configuration']])

    def component_parent(self,c):return c.parent
    def component_bodies(self,c):return list(c.bodies)


@pytest.fixture
def setup():
    adapter=Adapter();docs=DocumentCatalog(adapter);catalog=ComponentCatalog(docs)
    item=docs.list()['documents'][0]
    ctx=dict(document_id=item['document_id'],configuration='Основная',expected_observation_revision=item['observation_revision'])
    return adapter,docs,catalog,ctx


def fails(code,fn):
    with pytest.raises(ExecutionFailure) as caught:fn()
    assert caught.value.code==code and caught.value.uncertain is False


def test_reused_file_has_distinct_instance_body_ids_and_stable_unordered_pages(setup):
    a,d,c,ctx=setup
    first=c.list(**ctx,limit=1);second=c.list(**ctx,limit=1,cursor=first['next_cursor'])
    rows=first['items']+second['items'];assert len(rows)==2 and second['next_cursor'] is None
    assert rows[0]['component_id']!=rows[1]['component_id']
    assert rows[0]['referenced_path']==rows[1]['referenced_path']
    assert c.list(**ctx)['items']==rows
    bodies=[]
    for row in rows:
        assert c.get(**ctx,component_id=row['component_id'])['component']==row
        values=c.bodies(**ctx,component_id=row['component_id']);bodies.append(values['items'][0])
        assert values['body_coordinate_frame']=='component_model'
        assert c.bodies(**ctx,component_id=row['component_id'],body_id=bodies[-1]['body_id'])['items']==values['items']
    assert bodies[0]['body_id']!=bodies[1]['body_id']
    fails('object_component_mismatch',lambda:c.bodies(**ctx,component_id=rows[0]['component_id'],body_id=bodies[1]['body_id']))


def test_nested_path_parent_native_identity_is_checked(setup):
    a,d,c,ctx=setup;a.instances[0].info['referenced_document_type']='assembly'
    a.instances[1].parent=a.instances[0];a.instances[1].info['component_path']='Контрольная деталь-1/Вложенная деталь-1'
    rows=c.list(**ctx)['items'];assert rows[1]['parent_component_id']==rows[0]['component_id']
    fails('unsupported_component_type',lambda:c.bodies(**ctx,component_id=rows[0]['component_id']))
    a.instances[1].parent=None
    fails('component_parent_mismatch',lambda:c.list(**ctx))


@pytest.mark.parametrize('change,code',[
    ({'expected_observation_revision':'old'},'observation_revision_mismatch'),
    ({'configuration':'Вариант'},'configuration_not_active')])
def test_preflight_refuses_wrong_context_before_enumeration(setup,change,code):
    a,d,c,ctx=setup;fails(code,lambda:c.list(**{**ctx,**change}));assert a.enumerations==0


def test_part_document_and_pending_rebuild_rejected(setup):
    a,d,c,ctx=setup;a.needs_rebuild=True;fails('document_needs_rebuild',lambda:c.list(**ctx));a.needs_rebuild=False
    a.models[0].state['document_type']='part';item=d.list()['documents'][0];ctx['expected_observation_revision']=item['observation_revision']
    fails('unsupported_document_type',lambda:c.list(**ctx))


@pytest.mark.parametrize('state',[0,1,4,5])
def test_no_implicit_resolution(setup,state):
    a,d,c,ctx=setup;a.instances[1].info['native_suppression_state']=state
    fails('component_not_resolved',lambda:c.list(**ctx));assert a.instances[1].info['native_suppression_state']==state


def test_foreign_document_cannot_resolve_component(setup):
    a,d,c,ctx=setup;row=c.list(**ctx)['items'][0]
    a.models[1].state['document_type']='assembly';item=d.list()['documents'][1]
    ctx.update(document_id=item['document_id'],expected_observation_revision=item['observation_revision'])
    fails('component_reference_not_found',lambda:c.get(**ctx,component_id=row['component_id']))


def test_old_reference_survives_rename_but_not_configuration_replacement(setup):
    a,d,c,ctx=setup;row=c.list(**ctx)['items'][0];native=a.instances[0]
    native.info['component_path']='Переименованная деталь-1'
    assert c.get(**ctx,component_id=row['component_id'])['component']['component_path']=='Переименованная деталь-1'
    native.info['referenced_configuration']='Вариант'
    fails('component_reference_context_changed',lambda:c.get(**ctx,component_id=row['component_id']))
    new=next(x for x in c.list(**ctx)['items'] if x['component_path']=='Переименованная деталь-1')
    assert new['component_id']!=row['component_id']


def test_configuration_incarnation_and_recreated_instance_do_not_alias(setup):
    a,d,c,ctx=setup;row=c.list(**ctx)['items'][0]
    a.cfgs['Основная']=object()
    fails('component_reference_context_changed',lambda:c.get(**ctx,component_id=row['component_id']))
    a.instances[0].identity=object()
    fails('persistent_reference_mismatch',lambda:c.get(**ctx,component_id=row['component_id']))


def test_deleted_instance_and_removed_body_are_not_fallbacks(setup):
    a,d,c,ctx=setup;row=c.list(**ctx)['items'][0];body=c.bodies(**ctx,component_id=row['component_id'])['items'][0]
    native=a.instances[0];native.bodies=[]
    fails('object_not_in_current_component',lambda:c.bodies(**ctx,component_id=row['component_id'],body_id=body['body_id']))
    a.instances.pop(0)
    fails('component_not_in_active_configuration',lambda:c.get(**ctx,component_id=row['component_id']))


def test_native_pid_roundtrip_mismatch_is_rejected(setup):
    a,d,c,ctx=setup;a.instances[1].persistent_id=a.instances[0].persistent_id
    fails('persistent_reference_mismatch',lambda:c.list(**ctx))


def test_transform_change_without_observation_stamp_is_detected(setup):
    a,d,c,ctx=setup
    def changed():
        if a.enumerations==2:a.instances[1].info['transform']['origin_mm'][0]=60.
    a.changed=changed
    fails('component_changed_during_read',lambda:c.list(**ctx))


def test_cursor_rejects_manual_change_without_stamp(setup):
    a,d,c,ctx=setup;page=c.list(**ctx,limit=1)
    a.instances[0].info['hidden']=True
    fails('stale_component_cursor',lambda:c.list(**ctx,cursor=page['next_cursor']))


def test_body_census_closing_change_detected(setup):
    a,d,c,ctx=setup;row=c.list(**ctx)['items'][0];original=a.component_bodies;count=0
    def bodies(obj):
        nonlocal count
        count+=1
        return original(obj) if count==1 else []
    a.component_bodies=bodies
    fails('component_bodies_changed_during_read',lambda:c.bodies(**ctx,component_id=row['component_id']))


@pytest.mark.parametrize('limit',[True,0,201,1.,'2'])
def test_page_validation(setup,limit):
    a,d,c,ctx=setup;fails('invalid_limit',lambda:c.list(**ctx,limit=limit));assert a.enumerations==0


def test_unknown_and_wrong_body_type(setup):
    a,d,c,ctx=setup;row=c.list(**ctx)['items'][0]
    fails('component_reference_not_found',lambda:c.get(**ctx,component_id='foreign'))
    fails('invalid_body_type',lambda:c.bodies(**ctx,component_id=row['component_id'],body_type='mesh'))
    fails('component_body_reference_not_found',lambda:c.bodies(**ctx,component_id=row['component_id'],body_id='foreign'))


def test_all_empty_surface_budget_and_close_releases_anchors(setup):
    a,d,c,ctx=setup;a.instances[0].bodies[0].body_type='surface';row=c.list(**ctx)['items'][0]
    assert c.bodies(**ctx,component_id=row['component_id'],body_type='surface')['total_count']==1
    assert c.bodies(**ctx,component_id=row['component_id'],body_type='solid')['total_count']==0
    c.MAX_BODIES=0;fails('component_body_budget_exceeded',lambda:c.bodies(**ctx,component_id=row['component_id']))
    entry,_=d.resolve(ctx['document_id'],'Основная');d.close();assert entry.geometry=={} and a.closed


def test_runtime_routes_all_component_reads_through_one_worker_and_durable_replay(tmp_path):
    import asyncio
    from solidworks_mcp.runtime_v2 import Runtime
    from solidworks_mcp.jobs import JobStore
    from test_runtime_v2 import Worker
    a=Adapter();store=JobStore(tmp_path/'jobs.sqlite')
    runtime=Runtime(store,worker_factory=Worker,catalog_factory=lambda:DocumentCatalog(a))
    async def exercise():
        doc=(await runtime.read('doc','document.list',{}))['result']['documents'][0]
        ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
        listed=await runtime.read('list','component.list',ctx);cid=listed['result']['items'][0]['component_id']
        got=await runtime.read('get','component.get',{**ctx,'component_id':cid});assert got['status']=='succeeded'
        args={**ctx,'component_id':cid}
        bodies=await runtime.read('bodies','component.bodies',args);assert bodies['status']=='succeeded'
        assert await runtime.read('bodies','component.bodies',args)==bodies
        assert bodies['payload']['mutates'] is False
        assert len(store.list()['items'])==4
    try:asyncio.run(exercise())
    finally:assert runtime.shutdown() is True;store.close()
