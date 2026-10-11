"""Exact instance/body ownership, lifetime, cursors and closing topology races."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
import pytest
from solidworks_mcp.component_topology import ComponentTopologyCatalog
from solidworks_mcp.components import ComponentCatalog
from solidworks_mcp.documents import DocumentCatalog
from test_components_v2 import Adapter,fails


class TopologyAdapter(Adapter):
    def __init__(self):
        super().__init__();self.topology_reads=0;self.on_topology=None

    def geometry_summary(self,obj,kind):
        if kind=='edge':return dict(length_mm=5.,start_mm=[0.,0.,0.],end_mm=[5.,0.,0.],curve_type='line')
        if kind=='face':return dict(area_mm2=25.,surface_type='plane',edge_count=4)
        return super().geometry_summary(obj,kind)

    def topology(self,body,kind):
        self.topology_reads+=1
        if self.on_topology:self.on_topology()
        return list(reversed(body.faces if kind=='face' else body.edges)) if self.topology_reads%2 else list(body.faces if kind=='face' else body.edges)


@pytest.fixture
def setup():
    a=TopologyAdapter();d=DocumentCatalog(a);base=ComponentCatalog(d);c=ComponentTopologyCatalog(d)
    doc=d.list()['documents'][0];ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
    rows=base.list(**ctx)['items'];bodies=[base.bodies(**ctx,component_id=row['component_id'])['items'][0] for row in rows]
    target={**ctx,'component_id':rows[0]['component_id'],'body_id':bodies[0]['body_id']}
    return a,d,base,c,target,ctx,rows,bodies


@pytest.mark.parametrize('kind,count',[('face',3),('edge',4)])
def test_exact_instance_body_topology_paging_and_roundtrip(setup,kind,count):
    a,d,b,c,target,ctx,rows,bodies=setup
    first=c.list_topology(**target,kind=kind,limit=1);values=first['items'];cursor=first['next_cursor']
    while cursor:
        page=c.list_topology(**target,kind=kind,limit=1,cursor=cursor);values+=page['items'];cursor=page['next_cursor']
    assert len(values)==count and len({x['object_id'] for x in values})==count
    assert first['object_coordinate_frame']=='component_model' and first['area_unit']=='mm2'
    for item in values:
        assert item['component_id']==target['component_id'] and item['body_id']==target['body_id'] and item['kind']==kind
        assert c.get_topology(**target,object_id=item['object_id'])['object']==item
    assert c.list_topology(**target,kind=kind)['items']==values


@pytest.mark.parametrize('kind',['face','edge'])
def test_same_file_foreign_instance_has_distinct_topology_ids(setup,kind):
    a,d,b,c,target,ctx,rows,bodies=setup
    own=c.list_topology(**target,kind=kind)['items'];other={**ctx,'component_id':rows[1]['component_id'],'body_id':bodies[1]['body_id']}
    foreign=c.list_topology(**other,kind=kind)['items']
    assert {x['object_id'] for x in own}.isdisjoint(x['object_id'] for x in foreign)
    fails('object_component_mismatch',lambda:c.get_topology(**other,object_id=own[0]['object_id']))
    fails('object_component_mismatch',lambda:c.list_topology(**{**target,'body_id':bodies[1]['body_id']},kind=kind))


def test_same_instance_wrong_body_is_not_name_fallback(setup):
    a,d,b,c,target,ctx,rows,bodies=setup;extra=a.body();a.instances[0].bodies.append(extra)
    another=b.bodies(**ctx,component_id=rows[0]['component_id'])['items'];extra_id=next(x['body_id'] for x in another if x['body_id']!=target['body_id'])
    face=c.list_topology(**target,kind='face')['items'][0]
    fails('object_body_mismatch',lambda:c.get_topology(**{**target,'body_id':extra_id},object_id=face['object_id']))


@pytest.mark.parametrize('kind',['face','edge'])
def test_owner_body_mismatch_even_inside_returned_topology_rejected(setup,kind):
    a,d,b,c,target,*_=setup;obj=(a.instances[0].bodies[0].faces if kind=='face' else a.instances[0].bodies[0].edges)[0]
    obj.body=a.instances[1].bodies[0]
    fails('object_body_mismatch',lambda:c.list_topology(**target,kind=kind))


@pytest.mark.parametrize('kind',['face','edge'])
def test_deleted_and_recreated_native_topology_no_reassignment(setup,kind):
    a,d,b,c,target,*_=setup;item=c.list_topology(**target,kind=kind)['items'][0]
    entry,_=d.resolve(target['document_id'],'Основная');ref=c._topology_state(entry)['refs'][item['object_id']];native=a.registry[ref.persistent_id]
    sequence=a.instances[0].bodies[0].faces if kind=='face' else a.instances[0].bodies[0].edges
    sequence.remove(native)
    fails('object_not_in_current_body',lambda:c.get_topology(**target,object_id=item['object_id']))
    sequence.append(native);native.identity=object()
    fails('persistent_reference_mismatch',lambda:c.get_topology(**target,object_id=item['object_id']))


def test_unknown_body_part_reference_wrong_kind_and_foreign_document(setup):
    a,d,b,c,target,ctx,rows,bodies=setup
    fails('component_body_reference_not_found',lambda:c.list_topology(**{**target,'body_id':'part_obj'},kind='face'))
    fails('component_topology_reference_not_found',lambda:c.get_topology(**target,object_id=target['body_id']))
    fails('invalid_topology_kind',lambda:c.list_topology(**target,kind='body'))
    a.models[1].state['document_type']='assembly';doc=d.list()['documents'][1]
    fails('component_reference_not_found',lambda:c.list_topology(**{**target,'document_id':doc['document_id'],'expected_observation_revision':doc['observation_revision']},kind='face'))


def test_referenced_and_assembly_configuration_incarnations_are_checked(setup):
    a,d,b,c,target,*_=setup
    face=c.list_topology(**target,kind='face')['items'][0];a.instances[0].info['referenced_configuration']='Вариант'
    fails('component_reference_context_changed',lambda:c.get_topology(**target,object_id=face['object_id']))
    a.instances[0].info['referenced_configuration']='Основная';a.configurations[a.models[0].identity,'Основная']=object()
    fails('object_configuration_mismatch',lambda:c.get_topology(**target,object_id=face['object_id']))


def test_page_bound_to_whole_instance_transform_body_and_kind(setup):
    a,d,b,c,target,*_=setup;page=c.list_topology(**target,kind='face',limit=1)
    fails('invalid_component_topology_cursor',lambda:c.list_topology(**target,kind='edge',cursor=page['next_cursor']))
    a.instances[0].info['transform']['origin_mm'][0]=1.
    fails('stale_component_topology_cursor',lambda:c.list_topology(**target,kind='face',cursor=page['next_cursor']))


def test_new_face_between_pages_without_stamp_is_detected(setup):
    a,d,b,c,target,*_=setup;page=c.list_topology(**target,kind='face',limit=1)
    body=a.instances[0].bodies[0];obj=SimpleNamespace(identity=object(),persistent_id=b'new_face',body=body,kind='face');body.faces.append(obj);a.registry[obj.persistent_id]=obj
    fails('stale_component_topology_cursor',lambda:c.list_topology(**target,kind='face',cursor=page['next_cursor']))


@pytest.mark.parametrize('change',['face','body','owner','stamp'])
def test_closing_census_rejects_real_changes(setup,change):
    a,d,b,c,target,*_=setup
    def update():
        if a.topology_reads!=2:return
        if change=='face':a.instances[0].bodies[0].faces.pop()
        elif change=='body':a.instances[0].bodies=[]
        elif change=='owner':a.instances[0].bodies[0].faces[0].body=a.instances[1].bodies[0]
        else:a.models[0].state['update_stamp']+=1
    a.on_topology=update
    code={'face':'component_topology_changed_during_read','body':'component_bodies_changed_during_read','owner':'object_body_mismatch','stamp':'document_changed_during_read'}[change]
    fails(code,lambda:c.list_topology(**target,kind='face'))


@pytest.mark.parametrize('kind,summary',[('face',{'area_mm2':float('nan')}),('face',{'area_mm2':True}),('face',{'area_mm2':-1.}),('edge',{'length_mm':float('inf'),'start_mm':[0.,0.,0.],'end_mm':[1.,0.,0.]}),('edge',{'length_mm':1.,'start_mm':[0.,False,0.],'end_mm':[1.,0.,0.]}),('edge',{'length_mm':1.,'start_mm':[0.,0.],'end_mm':[1.,0.,0.]})])
def test_nonfinite_or_malformed_native_summaries_reject(setup,kind,summary):
    a,d,b,c,target,*_=setup;original=a.geometry_summary
    a.geometry_summary=lambda obj,k:deepcopy(summary) if k==kind else original(obj,k)
    fails('invalid_native_topology_summary',lambda:c.list_topology(**target,kind=kind))


@pytest.mark.parametrize('limit',[True,0,201,1.,'2'])
def test_page_limits_before_topology_read(setup,limit):
    a,d,b,c,target,*_=setup;fails('invalid_limit',lambda:c.list_topology(**target,kind='face',limit=limit));assert a.topology_reads==0


def test_duplicate_roster_missing_reference_budget_and_close(setup):
    a,d,b,c,target,*_=setup;body=a.instances[0].bodies[0];body.faces.append(body.faces[0])
    fails('topology_roster_invalid',lambda:c.list_topology(**target,kind='face'));body.faces.pop()
    obj=body.faces[0];old=obj.persistent_id;obj.persistent_id=b''
    fails('persistent_reference_unavailable',lambda:c.list_topology(**target,kind='face'));obj.persistent_id=old
    c.MAX_TOPOLOGY=1;fails('topology_budget_exceeded',lambda:c.list_topology(**target,kind='face'))
    entry,_=d.resolve(target['document_id'],'Основная');d.close();assert entry.geometry=={}


def test_stale_observation_does_not_enumerate_native_topology(setup):
    a,d,b,c,target,*_=setup;fails('observation_revision_mismatch',lambda:c.list_topology(**{**target,'expected_observation_revision':'stale'},kind='face'));assert a.topology_reads==0


def test_runtime_routes_component_and_topology_catalogs_to_same_owned_document(tmp_path):
    from solidworks_mcp.runtime_v2 import Runtime
    from solidworks_mcp.jobs import JobStore
    from test_runtime_v2 import Worker
    a=TopologyAdapter();store=JobStore(tmp_path/'jobs.sqlite');runtime=Runtime(store,worker_factory=Worker,catalog_factory=lambda:DocumentCatalog(a))
    async def exercise():
        doc=(await runtime.read('d','document.list',{}))['result']['documents'][0]
        ctx=dict(document_id=doc['document_id'],configuration='Основная',expected_observation_revision=doc['observation_revision'])
        cid=(await runtime.read('c','component.list',ctx))['result']['items'][0]['component_id']
        bid=(await runtime.read('b','component.bodies',{**ctx,'component_id':cid}))['result']['items'][0]['body_id']
        args={**ctx,'component_id':cid,'body_id':bid,'kind':'edge'}
        listed=await runtime.read('e','component.topology_list',args);assert listed['status']=='succeeded'
        assert await runtime.read('e','component.topology_list',args)==listed
        target={**ctx,'component_id':cid,'body_id':bid,'object_id':listed['result']['items'][0]['object_id']}
        got=await runtime.read('g','component.topology_get',target);assert got['result']['object']==listed['result']['items'][0]
        assert all(job['payload']['mutates'] is False for job in store.list()['items'])
    try:asyncio.run(exercise())
    finally:assert runtime.shutdown() is True;store.close()
