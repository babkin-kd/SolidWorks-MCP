"""Real suppression catalog/coordinator/runner/SQLite, artificial native state.

Postcondition predicates are not mocked. Shape/reference/name observations come
from changed fake state and the real retained producer. No native CAD acceptance.
"""
from copy import deepcopy
from concurrent.futures import Future
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_rectangle_construction import NativeRectangleStageReceipt
from solidworks_mcp.cad_owned_suppression_snapshot import OwnedSuppressionSnapshot
from solidworks_mcp.documents import rejected
from solidworks_mcp.feature_suppression_catalog import FeatureSuppressionCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.owned_rectangle_feature import OwnedRectangleFeatureRegistry
from solidworks_mcp.owned_suppression_postconditions import verified_owned_suppression, verified_owned_return
from test_cad_owned_suppression_snapshot import case
from test_rectangle_extrusion_postconditions import proof as extrusion_proof


class InlineWorker:
    def submit(self, function):
        future = Future()
        try: future.set_result(function())
        except BaseException as error: future.set_exception(error)
        return future
    def shutdown(self, timeout_s=5): return True


@pytest.fixture
def domain(case, extrusion_proof, tmp_path, monkeypatch):
    c = case
    c.model.GetUnits = lambda:deepcopy(c.baseline['clone_state']['units'])
    c.binding.feature.GetID = lambda:c.binding.native_id
    original_getters = deepcopy(c.getter_values)
    records = list(c.records)
    depth = next(record for record in records if record.summary['name'] == 'Толщина')
    original_depth = deepcopy(depth.summary)
    original_body = c.bodies[0]
    body_pid, body_identity = original_body.pid, original_body.identity
    original_name = c.baseline['clone_state']['body']['name']
    state = NS(c=c, busy=False, calls=[], guard_count=0, releases=0, name_writes=[],
        auto_name='Основание', fault=None, setter_fault_consumed=False, sequence=4,
        corrupt_neighbor=False, forbid_native=False)
    class Body:
        identity, pid = body_identity, body_pid
        def __init__(self): self._name = original_name
        @property
        def Name(self): return self._name
        @Name.setter
        def Name(self, value):
            state.name_writes.append(value); self._name = value
    body = Body(); c.bodies = [body]; c.raw_by_pid[body_pid] = body
    neighbor_model = NS(identity=object())
    neighbor_snapshot = deepcopy(c.baseline)
    target_entry = NS(document_id='target', model=c.model, identity=c.model.identity, geometry={'old_body_ref':object()})
    neighbor_entry = NS(document_id='neighbor', model=neighbor_model, identity=neighbor_model.identity, geometry={})
    row = dict(document_id='target',title=c.observed['title'],path='',document_type='part',
        active_configuration='Основная',configurations=['Основная'],needs_save=True,
        update_stamp=4,observation_sequence=4,observation_revision='obs_4',
        mode={'read_only_state':0},visible=True,dependencies=[],selection=[],view={'matrix':[1,0,0]})
    neighbor_row = {**deepcopy(row),'document_id':'neighbor','title':'Сосед','update_stamp':1,
                    'observation_sequence':1,'observation_revision':'neighbor_1'}
    semantic = dict(documents=[row,neighbor_row],active_document_id='target',
        windows=[{'document_id':'target'},{'document_id':'neighbor'}],reference_graph=[],
        files={'neighbor':'original-private-bytes'},application={'busy':False,'cwd':'baseline'})
    def observed(model):
        if model is c.model: return {**deepcopy(c.observed),'needs_save':True,'update_stamp':state.sequence}
        return dict(document_type='part',path='',configurations=['Основная'],active_configuration='Основная',title='Сосед')
    c.adapter.snapshot = observed
    c.adapter.documents = lambda:[c.model,neighbor_model]
    c.adapter.active_document = lambda:c.model
    c.adapter.application_busy = lambda:state.busy
    def snapshot(model):
        result = deepcopy(c.baseline if model is c.model else neighbor_snapshot)
        if model is c.model:
            result['clone_state']['features'] = [deepcopy(feature.row) for feature in c.features]
            result['clone_state']['body']['name'] = body.Name
            if state.fault == 'foreign_base': result['clone_state']['material'] = ['foreign','']
        elif state.corrupt_neighbor:
            result['clone_state']['material'] = ['foreign','']
        return result
    c.adapter.rectangle_construction_snapshot = snapshot
    def resolve(document_id,configuration):
        if document_id != 'target' or configuration != 'Основная':
            raise rejected('document_not_open','Artificial foreign explicit target.')
        return target_entry,observed(c.model)
    documents = NS(adapter=c.adapter, resolve=resolve,
        _entries=[target_entry,neighbor_entry],_refresh=lambda:None)
    store = JobStore(tmp_path / 'domain.sqlite')
    ownership = OwnedRectangleFeatureRegistry(documents,store,'epoch')
    _, _, definition = extrusion_proof
    old_snapshot = deepcopy(extrusion_proof[0]['snapshots']['target'])
    before_session = dict(semantic=deepcopy(semantic),snapshots={'target':old_snapshot,'neighbor':neighbor_snapshot})
    created_session = dict(semantic=deepcopy(semantic),snapshots={'target':deepcopy(c.baseline),'neighbor':neighbor_snapshot})
    receipt = NativeRectangleStageReceipt(c.model.identity,c.configuration_identity,
        tuple((feature.identity,deepcopy(feature.row)) for feature in c.features if feature is not c.binding.feature),
        deepcopy(c.baseline['clone_state']['creation_controls']))
    receipt.attempted = receipt.native_call_returned = True
    receipt.extrusion, receipt.extrusion_identity = c.binding.feature,c.binding.feature_identity
    receipt.borrowed_sketch,receipt.borrowed_sketch_identity = c.binding.receipt.borrowed_sketch,c.binding.receipt.borrowed_sketch_identity
    receipt_fields = ('attempted','native_call_returned','pending_creation','pending_sketch_close','sketch_closed',
        'selection_uncertain','restore_attempted','restored','pending_native_step','native_step_journal_failed','view_state_uncertain')
    original_args = dict(document_id='target',configuration='Основная',expected_revision='created_before',**vars(definition))
    creation,_ = store.create('original_creation','part.extrude_rectangle',original_args,
        {key:original_args[key] for key in ('document_id','configuration','expected_revision')},mutates=True)
    oid = creation['operation_id']; store.start(oid)
    before = dict(scope='closed_rectangle_blind_extrusion_v1',baseline=before_session,definition=vars(definition),
        reference_persistent_id_hex=receipt.borrowed_sketch.pid.hex(),reference_native_id=4,plane_transform=[0.]*16)
    after = dict(state=created_session,receipt={key:getattr(receipt,key) for key in receipt_fields},
        original_files=semantic['files'],pending=False,guard_released=True)
    guard = dict(scope='rectangle_construction_guard_v1',native_guards=[{'artificial':True}],
        guard_released=True,pending_release=False,journal_failed=False,reference_binding_unconfirmed=False,full_release_check='effect')
    object_id = 'feat_' + 'b'*32
    result = dict(verified=True,before=before,after=after,execution_guard=guard,
        value=dict(document_id='target',configuration='Основная',kind='extrusion',created_native_id=5,
                   object_id=object_id,feature_object_id=object_id))
    store.prepare_mutation(oid,connection_epoch='epoch',document_id='target',configuration='Основная',
        expected_revision='created_before',before_state=before,effect_scope='application')
    store.verify_mutation(oid,outcome='committed',evidence={'after':after,'execution_guard':guard})
    binding = ownership.register(oid,document_id='target',configuration='Основная',result=result,receipt=receipt)
    store.finish(oid,'succeeded',result=result)
    c.binding = binding
    catalog = FeatureSuppressionCatalog(documents,store,'epoch',ownership)
    def census(guarded_ids=()):
        assert bool(guarded_ids) == state.busy
        current = deepcopy(semantic)
        current['documents'][0].update(update_stamp=state.sequence,observation_sequence=state.sequence,
            observation_revision='obs_'+str(state.sequence))
        if state.corrupt_neighbor: current['documents'][1]['needs_save'] = False
        return [target_entry,neighbor_entry],current
    catalog.sessions._capture_session = census
    catalog.sessions.census._disk_files = lambda value:deepcopy(semantic['files'])
    def producer(adapter,model,current_binding,baseline_snapshot):
        return OwnedSuppressionSnapshot(adapter,model,current_binding,baseline_snapshot,
            getters=c.getters,query=c.query)
    monkeypatch.setattr('solidworks_mcp.feature_suppression_catalog.OwnedSuppressionSnapshot',producer)
    class Guard:
        def __init__(self): self.evidence={'scope':'artificial_native_guard','released':False}
        def __enter__(self):
            assert not state.busy
            state.busy=True; state.guard_count+=1
        def __exit__(self,*args):
            state.busy=False; state.releases+=1; self.evidence['released']=True
    c.adapter.native_open_guard = lambda *args:Guard()
    def apply_native(suppressed):
        c.binding.feature.row['suppressed'] = suppressed
        c.bodies = [] if suppressed else [body]
        c.status = 2 if suppressed else 0
        state.sequence += 1
        if suppressed:
            c.getter_values['configuration_state'] = deepcopy(original_getters['configuration_state'])
            c.getter_values['configuration_state']['parameters'].append(['$СОСТОЯНИЕ@'+c.binding.feature.row['name'],'Пог'])
            c.getter_values['configuration_state']['parameters'].sort(key=lambda value:value[0])
            depth.summary['owner']['suppressed']=True
            depth.summary['write_blockers'] = list(original_depth['write_blockers'])+['owner_suppressed_frozen_or_rolled_back']
        else:
            c.getter_values['configuration_state'] = deepcopy(original_getters['configuration_state'])
            depth.summary = deepcopy(original_depth)
            body._name = state.auto_name
    def setter(option,configuration_option,configuration_names):
        assert state.busy and configuration_option == 1 and configuration_names is None
        assert not state.forbid_native
        state.calls.append(('setter',option))
        if state.fault == 'setter_pending': raise RuntimeError('Artificial missing setter acknowledgement')
        if state.fault == 'setter_false_noeffect': return False
        apply_native(option == 0)
        if state.fault == 'setter_false_effect' and not state.setter_fault_consumed:
            state.setter_fault_consumed=True
            return False
        return True
    def rebuild(top_only):
        assert state.busy and top_only is False and not state.forbid_native
        state.calls.append(('rebuild',False))
        if state.fault == 'rebuild_pending': raise RuntimeError('Artificial missing rebuild acknowledgement')
        return True
    c.binding.feature.SetSuppression2 = setter
    c.model.ForceRebuild3 = rebuild
    state.store,state.catalog,state.ownership,state.binding,state.runner = store,catalog,ownership,binding,JobRunner(store,InlineWorker())
    state.entries,state.semantic,state.baseline = [target_entry,neighbor_entry],semantic,created_session
    yield state
    store.close()


def prepare(state,suppressed=True):
    return state.catalog.prepare('target','Основная',state.binding.object_id,suppressed)


def run(state,suppressed=True,*,request='suppression',revision=None,document_id='target',object_id=None):
    arguments = dict(document_id=document_id,configuration='Основная',object_id=object_id or state.binding.object_id,
        suppressed=suppressed,expected_revision=revision or prepare(state,suppressed)['revision'])
    def execute(operation_id): return state.catalog.set_suppressed(operation_id,**arguments)
    job = state.runner.submit(request,'feature.set_suppressed',arguments,execute,context=arguments,
        mutates=True,verify=lambda result:result.get('verified') is True,pass_operation_id=True)
    return state.store.get(job['operation_id'])


def test_real_catalog_suppress_prepare_return_unsuppress_name_repair_and_geometry_refs_retirement(domain):
    state=domain
    suppressed=run(state)
    assert suppressed['status']=='succeeded',suppressed.get('error')
    assert suppressed['mutation']['phase']=='committed'
    assert state.binding.feature.IsSuppressed2(1,None)==[True]
    assert verified_owned_suppression(state.baseline,suppressed['result']['after']['state'],'target',state.binding.native_id)
    assert not any(row['kind'] in ('body','face','edge','vertex') for row in
        suppressed['result']['after']['state']['snapshots']['target']['references'])
    assert state.entries[0].geometry=={}
    returned=run(state,False,request='return')
    assert returned['status']=='succeeded',returned.get('error')
    assert verified_owned_return(state.baseline,returned['result']['after']['state'],'target')
    assert state.name_writes==[state.baseline['snapshots']['target']['clone_state']['body']['name']]
    assert state.guard_count==state.releases==3  # suppress, return, independently justified body-name guard
    assert state.catalog.contexts==state.catalog.receipts=={}
    assert state.calls==[('setter',0),('rebuild',False),('setter',2),('rebuild',False)]


@pytest.mark.parametrize('fault',['stale','neighbor_revision','foreign_document','foreign_object'])
def test_foreign_or_stale_refusal_has_no_checkpointed_native_write(domain,fault):
    state=domain
    revision=prepare(state)['revision']
    if fault=='neighbor_revision': state.corrupt_neighbor=True
    job=run(state,revision='foreign_revision' if fault=='stale' else revision,
        document_id='foreign' if fault=='foreign_document' else 'target',
        object_id='feat_'+'f'*32 if fault=='foreign_object' else None)
    assert job['status']=='failed' and state.calls==[] and state.guard_count==0
    assert state.store.mutation_blockers('epoch','target')==[]


def test_native_false_without_effect_is_known_scoped_rollback_without_inverse(domain):
    state=domain; state.fault='setter_false_noeffect'
    job=run(state)
    assert job['status']=='failed',job.get('error')
    assert job['mutation']['phase']=='rolled_back'
    assert state.calls==[('setter',0)]
    assert state.binding.feature.IsSuppressed2(1,None)==[False]
    assert state.store.mutation_blockers('epoch','target')==[]
    assert not state.busy and state.catalog.receipts=={}


def test_normal_false_after_proved_effect_permits_only_verified_own_inverse(domain):
    state=domain; state.fault='setter_false_effect'
    job=run(state)
    assert job['status']=='failed',job.get('error')
    assert job['mutation']['phase']=='rolled_back'
    assert state.calls==[('setter',0),('setter',2),('rebuild',False)]
    assert verified_owned_return(state.baseline,job['mutation']['verification']['evidence']['after']['state'],'target')
    assert state.store.mutation_blockers('epoch','target')==[]


@pytest.mark.parametrize('fault',['setter_pending','rebuild_pending',
    'journal_setter_pending','journal_setter_returned','journal_rebuild_pending','journal_rebuild_returned'])
def test_pending_native_or_journal_boundaries_remain_unknown_held_without_inverse_or_retry(domain,fault,monkeypatch):
    state=domain
    failures=[]
    if fault.startswith('journal'):
        original=state.store.record_mutation_step
        _,native_step,_=fault.split('_')
        step='set_suppressed' if native_step=='setter' else 'rebuild'
        def record(operation_id,*,name,phase,evidence):
            if name=='suppression_apply_'+step and phase==fault.rsplit('_',1)[1]:
                failures.append((name,phase))
                raise OSError('Artificial native ledger persistence loss')
            return original(operation_id,name=name,phase=phase,evidence=evidence)
        monkeypatch.setattr(state.store,'record_mutation_step',record)
    else: state.fault=fault
    job=run(state)
    if fault.startswith('journal'): assert len(failures)==1
    assert job['status']=='unknown',job.get('error')
    assert job['mutation']['phase']=='unresolved' and state.store.mutation_blockers('epoch','neighbor')
    assert not any(call==('setter',2) for call in state.calls)
    before=list(state.calls)
    replay=run(state,request='suppression',revision=job['payload']['arguments']['expected_revision'])
    assert replay['operation_id']==job['operation_id'] and replay['status']=='unknown'
    assert state.calls==before
    held=run(state,request='new_request',revision=job['payload']['arguments']['expected_revision'])
    assert held['status']=='failed' and held['error']['code']=='document_mutation_blocked'
    assert state.calls==before


@pytest.mark.parametrize('boundary',['domain_commit','terminal_finish'])
def test_late_commit_or_terminal_journal_failure_never_inverts_proved_native_effect(domain,boundary,monkeypatch):
    state=domain
    if boundary=='domain_commit':
        original=state.store.verify_mutation
        def verify(operation_id,*,outcome,evidence):
            if outcome=='committed' and 'execution_guard' in evidence:
                raise OSError('Artificial late domain commit persistence failure')
            return original(operation_id,outcome=outcome,evidence=evidence)
        monkeypatch.setattr(state.store,'verify_mutation',verify)
    else:
        original=state.store.finish
        def finish(operation_id,status,**kwargs):
            if status=='succeeded': raise OSError('Artificial terminal acknowledgement loss')
            return original(operation_id,status,**kwargs)
        monkeypatch.setattr(state.store,'finish',finish)
    job=run(state)
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved'
    assert state.binding.feature.IsSuppressed2(1,None)==[True]
    assert state.calls==[('setter',0),('rebuild',False)]
    assert state.store.mutation_blockers('epoch','neighbor')
    with pytest.raises(ExecutionFailure) as refusal: prepare(state,False)
    assert refusal.value.code in ('suppression_context_missing','suppression_context_unconfirmed')
    assert state.calls==[('setter',0),('rebuild',False)]


def test_actual_terminal_result_must_match_original_committed_retained_context(domain,monkeypatch):
    state=domain
    original=state.store.finish
    def finish(operation_id,status,**kwargs):
        if status=='succeeded':
            changed=deepcopy(kwargs['result'])
            changed['value']['artificial_corrupted_terminal_receipt']=True
            kwargs['result']=changed
        return original(operation_id,status,**kwargs)
    monkeypatch.setattr(state.store,'finish',finish)
    suppressed=run(state)
    assert suppressed['status']=='succeeded' and suppressed['mutation']['phase']=='committed'
    assert suppressed['result']['value']['artificial_corrupted_terminal_receipt'] is True
    with pytest.raises(ExecutionFailure) as refusal: prepare(state,False)
    assert refusal.value.code=='suppression_context_unconfirmed'
    assert state.calls==[('setter',0),('rebuild',False)]


def test_missing_actual_suppressed_inventory_keeps_unknown_without_inverse(domain):
    state=domain
    state.c.getter_values['annotations']=None
    job=run(state)
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved'
    assert state.binding.feature.IsSuppressed2(1,None)==[True]
    assert state.calls==[('setter',0),('rebuild',False)]
    assert state.store.mutation_blockers('epoch','neighbor')
