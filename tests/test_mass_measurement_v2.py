"""Durable public mass scope; synthetic domain proof, not native acceptance."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import JobRunner, JobStore, ExecutionFailure
from solidworks_mcp.mass_measurement import MassMeasurementCatalog, SCOPE
from test_geometry_v2 import setup_geometry
from test_mass_properties_v2 import si
from test_mutation_guards_v2 import InlineWorker


@pytest.fixture
def mass(setup_geometry, tmp_path):
    adapter, documents, geometry, context, listed = setup_geometry
    store = JobStore(tmp_path/'jobs.sqlite')
    events = []
    adapter.selection = [(b'body0', 7)]
    adapter.mass_body_signature = lambda body: list(getattr(body, 'moments', [0.,0.,0.,1e-6,.0007,1e-6,0.,0.,0.,0.,0.,0.]))
    adapter.mass_selection_capture = lambda model: (
        [dict(persistent_id=pid.hex(), mark=mark) for pid,mark in adapter.selection],
        tuple((adapter.registry[pid].identity,mark) for pid,mark in adapter.selection))

    class Guard:
        evidence = dict(scope='application_model_mutation_guard_v1',
            original_command_in_progress=False,acquired=True,released=True,
            model_guards=[dict(original_state=0,locked_state=2,released_state=0)], selection_preserved=True)
        def __enter__(self):
            assert store.list()['items'][0]['mutation']['before_state']['_mutation_effect_scope']=='application'
            events.append('guard'); return self
        def __exit__(self,*exc):
            events.append('release')
            if getattr(adapter,'_mass_selection_reconciliation_required',False):
                raise ExecutionFailure('mass_selection_restore_unconfirmed','Unconfirmed selection.',uncertain=True)
    adapter.mass_read_guard = lambda model: Guard()
    def calculate(model,bodies):
        events.append(('calculate',len(bodies)))
        return si()
    adapter.mass_properties = calculate
    catalog=MassMeasurementCatalog(documents,store,'epoch')
    runner=JobRunner(store,InlineWorker())
    def run(request='mass', *, body_id=None, revision=None):
        prepared=catalog.prepare(**context,body_id=body_id)
        args={**context,'body_id':body_id,'expected_revision':revision or prepared['revision']}
        kwargs=dict(context=args,mutates=True,pass_operation_id=True,verify=lambda value:value['verified'] is True)
        return runner.submit(request,'measurement.mass',args,
            lambda operation_id:catalog.measure(operation_id,**args),**kwargs)
    value=SimpleNamespace(adapter=adapter,documents=documents,geometry=geometry,context=context,
        listed=listed,store=store,events=events,catalog=catalog,runner=runner,run=run)
    try: yield value
    finally: store.close()


def test_prepare_is_read_only_and_binds_selection_and_full_solid_roster(mass):
    first=mass.catalog.prepare(**mass.context)
    assert first['revision_scope']==SCOPE and first['body_count']==1 and not mass.events
    mass.adapter.body()
    second=mass.catalog.prepare(**mass.context)
    assert first['revision']!=second['revision'] and second['body_count']==2
    mass.adapter.selection[0]=(b'body0',8)
    assert mass.catalog.prepare(**mass.context)['revision']!=second['revision']
    assert not mass.events


def test_all_solids_surface_exclusion_checkpoint_and_replay(mass):
    mass.adapter.body()
    result=mass.run()
    assert result['status']=='succeeded' and result['mutation']['phase']=='committed'
    assert result['result']['body_count']==2 and result['result']['model_geometry_modified'] is False
    assert result['result']['mass_properties']['volume_mm3']==2000.
    assert mass.events==['guard',('calculate',2),'release']
    assert mass.run()==result and mass.events==['guard',('calculate',2),'release']
    assert not mass.store.mutation_blockers('new_epoch','new_document')


def test_selected_solid_only(mass):
    mass.adapter.body()
    body=mass.geometry.list(**mass.context,body_type='solid')['items'][0]['object_id']
    result=mass.run(body_id=body)
    assert result['status']=='succeeded' and result['result']['body_id']==body
    assert mass.events==['guard',('calculate',1),'release']


@pytest.mark.parametrize('change',['selection','geometry','members'])
def test_changed_measurement_revision_rejects_before_guard_or_calculation(mass,change):
    revision=mass.catalog.prepare(**mass.context)['revision']
    if change=='selection':mass.adapter.selection[0]=(b'body0',2)
    if change=='geometry':mass.adapter.registry[b'body0'].moments=[0.,0.,0.,2e-6,.0007,1e-6,0.,0.,0.,0.,0.,0.]
    if change=='members':mass.adapter.body()
    result=mass.run(revision=revision)
    assert result['status']=='failed' and result['error']['code']=='stale_revision' and not mass.events


@pytest.mark.parametrize('fault',['surface','foreign','stale','inactive','rebuild','empty','budget'])
def test_preparation_rejects_invalid_explicit_scope(mass,fault):
    args=mass.context.copy()
    if fault=='surface':args['body_id']=mass.geometry.list(**args,body_type='surface')['items'][0]['object_id']
    if fault=='foreign':
        args['body_id']=mass.geometry.list(**args,body_type='solid')['items'][0]['object_id']
        args.update(document_id=mass.listed[1]['document_id'],expected_observation_revision=mass.listed[1]['observation_revision'])
    if fault=='stale':args['expected_observation_revision']='old'
    if fault=='inactive':args['configuration']='Вариант'
    if fault=='rebuild':mass.adapter.needs_rebuild=True
    if fault=='empty':mass.adapter.objects[mass.adapter.models[0].identity]=[]
    if fault=='budget':
        for _ in range(500):mass.adapter.body(faces=0)
    with pytest.raises(ExecutionFailure):mass.catalog.prepare(**args)
    assert not mass.events


def test_known_calculation_error_proves_restored_state_without_retry(mass):
    def reject(model,bodies):
        mass.events.append('reject')
        raise ExecutionFailure('mass_properties_overridden','Override active.',uncertain=False)
    mass.adapter.mass_properties=reject
    result=mass.run()
    assert result['status']=='failed' and result['mutation']['phase']=='rolled_back'
    assert result['error']['code']=='mass_properties_overridden'
    assert mass.events==['guard','reject','release']
    assert not mass.store.mutation_blockers('new_epoch','new_document')


@pytest.mark.parametrize('fault',['selection','geometry','identity','sticky'])
def test_uncertain_read_does_not_write_restore_and_hold_survives_restart(mass,fault):
    def change(model,bodies):
        mass.events.append('change')
        if fault=='selection':mass.adapter.selection[0]=(b'body0',9)
        if fault=='geometry':bodies[0].moments=[0.,0.,0.,2e-6,.0007,1e-6,0.,0.,0.,0.,0.,0.]
        if fault=='identity':bodies[0].identity=object()
        if fault=='sticky':mass.adapter._mass_selection_reconciliation_required=True
        return si()
    mass.adapter.mass_properties=change
    result=mass.run()
    assert result['status']=='unknown' and result['result'] is None
    assert mass.events==['guard','change','release']
    assert mass.store.mutation_blockers('another_epoch','another_document')
    path=mass.store.path
    mass.store.close()
    restarted=JobStore(path)
    try:assert restarted.mutation_blockers('fresh_epoch','fresh_document')
    finally:restarted.close()


def test_change_after_checkpoint_rejected_without_restoring_user_edit(mass,monkeypatch):
    original=mass.store.prepare_mutation
    def checkpoint(*args,**kwargs):
        result=original(*args,**kwargs)
        mass.adapter.selection[0]=(b'body0',12)
        return result
    monkeypatch.setattr(mass.store,'prepare_mutation',checkpoint)
    result=mass.run()
    assert result['status']=='failed' and result['mutation']['phase']=='not_started'
    assert mass.adapter.selection==[(b'body0',12)] and mass.events==['guard','release']


@pytest.mark.parametrize('operation',['measurement.prepare_mass','measurement.mass'])
def test_runtime_exact_routing_and_catalog_release(mass,operation):
    from solidworks_mcp.runtime_v2 import Runtime
    runtime=Runtime(mass.store)
    runtime._catalog=mass.documents
    events=[]
    runtime._measurements=SimpleNamespace(prepare=lambda **kw:events.append(('prepare',kw)) or {},
        measure=lambda job,**kw:events.append(('measure',job,kw)) or {})
    assert runtime._execute(operation,mass.context,'job_explicit')=={}
    assert events==([('prepare',mass.context)] if operation=='measurement.prepare_mass' else [('measure','job_explicit',mass.context)])
    runtime._release_catalog()
    assert runtime._measurements is None


def test_public_facade_uses_guarded_runtime_and_preserves_typed_optional_body(mass):
    import asyncio
    from solidworks_mcp.server_v2 import create_app
    class Runtime:
        def __init__(self):self.calls=[]
        async def read(self,request,operation,args,**kwargs):return await self.dispatch(False,request,operation,args,kwargs)
        async def mutate(self,request,operation,args,**kwargs):return await self.dispatch(True,request,operation,args,kwargs)
        async def dispatch(self,guarded,request,operation,args,kwargs):
            self.calls.append((guarded,request,operation,args,kwargs))
            return dict(status='succeeded',operation_id='job',payload={'context':args},result={'verified':True},error=None)
    runtime=Runtime();app=create_app(mass.store,runtime=runtime)
    async def check():
        for name in ['measurement_prepare_mass','measurement_get_mass']:
            args={**mass.context,'request_id':name,'timeout_s':0.}
            if name=='measurement_get_mass':args['expected_revision']='rev_explicit'
            _,result=await app.call_tool(name,args)
            assert result['status']=='succeeded' and result['data']['verified'] is True
        assert runtime.calls[0][0:3]==(False,'measurement_prepare_mass','measurement.prepare_mass')
        assert runtime.calls[1][0:3]==(True,'measurement_get_mass','measurement.mass')
        assert all(call[3]['body_id'] is None and call[4]=={'timeout_s':0.} for call in runtime.calls)
    asyncio.run(check())
