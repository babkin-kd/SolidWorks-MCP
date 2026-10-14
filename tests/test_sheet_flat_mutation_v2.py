"""Real durable coordinator on artificial complete sheet-state effects."""

from copy import deepcopy
from types import SimpleNamespace as NS
import uuid

import pytest

from solidworks_mcp.jobs import JobRunner
from solidworks_mcp.sheet_flat_state import SheetFlatStateCatalog
from test_part_construction_mutation_v2 import Worker
from test_part_creation_domain_v2 import setup as part_setup
from test_sheet_flat_domain_v2 import state


@pytest.fixture
def setup(part_setup,monkeypatch):
    adapter,parts,ids,planes=part_setup
    folded,item=state(part_setup,False);flat,_=state(part_setup,True)
    store=parts.dimensions.coordinator.store;catalog=SheetFlatStateCatalog(parts.dimensions);current=deepcopy(folded)
    events=[];target=object();entry=NS(model=object(),features={});fault=dict(value=None)
    class Guard:
        def __enter__(self):
            assert store.get(op_holder['value'])['mutation']['phase']=='prepared'
            events.append('guard');self.evidence=dict(released=False)
            return self
        def __exit__(self,*args):self.evidence=dict(released=True);events.append('released')
    parts.dimensions.mutation_guard=lambda model:Guard()
    def capture(*args,**kw):
        definition,expected_flat,expected_fold=catalog._source(current,'Основная',planes[0])
        return NS(state=(entry,)),target,deepcopy(current),(),definition,expected_flat,expected_fold
    monkeypatch.setattr(catalog,'_capture',capture)
    def change(model,retained,flattened):
        assert retained is target and events[0]=='guard' and events[-1]!='released'
        current.clear();current.update(deepcopy(flat if flattened else folded));events.append('state')
        cut=next(r for r in current['evidence']['members'] if r['role']=='cut_list');cut['name']='Sheet<2>'
        next(r for r in current['semantic']['tree']['features'] if r['native_id']==cut['native_id'])['name']='Sheet<2>'
        current['evidence']['body_name']='Auto body'
        if fault['value']=='foreign':
            current['semantic']['tree']['features'][0]['name']='Чужое изменение';fault['value']=None
            raise RuntimeError('Foreign state after native setter.')
    def names(model,retained,body_name,cut_list_name):
        events.append('names');current['evidence']['body_name']=body_name
        cut=next(r for r in current['evidence']['members'] if r['role']=='cut_list');cut['name']=cut_list_name
        next(r for r in current['semantic']['tree']['features'] if r['native_id']==cut['native_id'])['name']=cut_list_name
        if fault['value']=='known':fault['value']=None;raise RuntimeError('Known failure after complete names/state.')
    adapter.sheet_change_flat_state=change;adapter.sheet_preserve_flat_names=names
    runner=JobRunner(store,Worker());op_holder={}
    def run(revision=None,request=None):
        args=dict(document_id=ids[0],configuration='Основная',base_object_id=planes[0],flattened=True)
        args['expected_revision']=revision or catalog.prepare_flat_state(**args)['revision']
        def execute(op):
            op_holder['value']=op
            return catalog.set_flat_state(op,**args)
        return runner.submit(request or uuid.uuid4().hex,'sheet.set_flat_state',args,execute,
            context={k:args[k] for k in ('document_id','configuration','expected_revision')},mutates=True,
            pass_operation_id=True,verify=lambda v:v['verified'] is True)
    return run,current,folded,events,fault,store


def test_checkpoint_precedes_guard_and_verified_full_transition_preserves_names(setup):
    run,current,before,events,_,store=setup;job=run()
    assert job['status']=='succeeded' and job['mutation']['phase']=='committed'
    assert events==['guard','state','names','released']
    assert current['evidence']['body_name']==before['evidence']['body_name']
    assert SheetFlatStateCatalog._transition(before,current,True)


def test_stale_never_acquires_guard_or_changes_native_state(setup):
    run,current,before,events,_,store=setup;job=run(revision='rev_stale')
    assert job['status']=='failed' and job['error']['code']=='stale_revision'
    assert events==[] and current==before


def test_known_failure_restores_only_original_sheet_state_and_exact_names(setup):
    run,current,before,events,fault,store=setup;fault['value']='known';job=run()
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back'
    assert current==before and events==['guard','state','names','state','names','released']


def test_foreign_changes_do_not_authorize_name_writes_or_scoped_restoration(setup):
    run,current,before,events,fault,store=setup;fault['value']='foreign';job=run()
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved'
    assert events==['guard','state','released'] and current!=before
