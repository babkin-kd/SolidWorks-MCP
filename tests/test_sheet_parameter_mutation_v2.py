"""Real durable coordinator and independently built parameter effects; no CAD."""

from copy import deepcopy
from types import SimpleNamespace as NS
import uuid

import pytest

from solidworks_mcp.jobs import JobRunner
from solidworks_mcp.sheet_parameters import SheetParameterCatalog
from test_part_construction_mutation_v2 import Worker
from test_part_creation_domain_v2 import setup as part_setup
from test_sheet_parameters_v2 import material_state


@pytest.fixture
def setup(part_setup,monkeypatch):
    adapter,parts,ids,planes=part_setup;before,_=material_state(part_setup);current=deepcopy(before)
    catalog=SheetParameterCatalog(parts.dimensions);store=parts.dimensions.coordinator.store
    events=[];entry=NS(model=object(),features={});retained=object();fault=dict(value=None);op_holder={}
    class Guard:
        def __enter__(self):
            assert store.get(op_holder['value'])['mutation']['phase']=='prepared'
            events.append('guard');self.evidence=dict(released=False);return self
        def __exit__(self,*args):events.append('released');self.evidence=dict(released=True)
    parts.dimensions.mutation_guard=lambda model:Guard()
    def capture(*args,**kwargs):
        catalog._validate_options(current['evidence']['parameter_options'])
        definition,flat,fold=catalog._source(current,'Основная',planes[0])
        return NS(state=(entry,)),retained,deepcopy(current),(),definition,flat,fold
    monkeypatch.setattr(catalog,'_capture',capture)
    def write(model,target,definition):
        assert target is retained and events[0]=='guard' and events[-1]!='released'
        state,_=material_state(part_setup,thickness_mm=definition.thickness_mm,bend_radius_mm=definition.bend_radius_mm,k_factor=definition.k_factor)
        current.clear();current.update(state);events.append('parameters')
        cut=next(r for r in current['evidence']['members'] if r['role']=='cut_list');cut['name']='Sheet<2>'
        next(r for r in current['semantic']['tree']['features'] if r['native_id']==cut['native_id'])['name']='Sheet<2>'
        current['evidence']['body_name']='Auto body'
        if fault['value']=='foreign':
            current['semantic']['tree']['features'][0]['name']='Изменение извне';fault['value']=None
            raise RuntimeError('Foreign tree state after native modifier.')
        if fault['value']=='intermediate':
            state,_=material_state(part_setup,thickness_mm=definition.thickness_mm)
            current.clear();current.update(state);fault['value']=None
            raise RuntimeError('An unproved intermediate parameter set.')
        if fault['value']=='relief':
            current['evidence']['parameter_options']['base']['ReliefWidth']=.0002;fault['value']=None
            raise RuntimeError('Foreign native relief definition.')
    def names(model,target,body_name,cut_list_name):
        events.append('names');current['evidence']['body_name']=body_name
        cut=next(r for r in current['evidence']['members'] if r['role']=='cut_list');cut['name']=cut_list_name
        next(r for r in current['semantic']['tree']['features'] if r['native_id']==cut['native_id'])['name']=cut_list_name
        if fault['value']=='known':fault['value']=None;raise RuntimeError('Known failure after complete parameter/name write.')
    adapter.sheet_modify_parameters=write;adapter.sheet_preserve_flat_names=names
    runner=JobRunner(store,Worker())
    def run(revision=None,request=None):
        args=dict(document_id=ids[0],configuration='Основная',base_object_id=planes[0],thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38)
        args['expected_revision']=revision or catalog.prepare_parameters(**args)['revision']
        def execute(op):op_holder['value']=op;return catalog.set_parameters(op,**args)
        return runner.submit(request or uuid.uuid4().hex,'sheet.set_parameters',args,execute,
            context={k:args[k] for k in ('document_id','configuration','expected_revision')},mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    return run,current,before,events,fault,store


def test_checkpoint_guard_and_complete_parameter_effect_are_durable(setup):
    run,current,before,events,_,_=setup;job=run()
    assert job['status']=='succeeded' and job['mutation']['phase']=='committed'
    assert events==['guard','parameters','names','released']
    assert current['evidence']['body_name']==before['evidence']['body_name']
    assert current['semantic']['dimensions']==before['semantic']['dimensions']
    assert current['evidence']['sheet_parameters']['k_factor']==.38


def test_stale_request_never_acquires_guard_or_stages_parameters(setup):
    run,current,before,events,_,_=setup;job=run('rev_stale')
    assert job['status']=='failed' and job['error']['code']=='stale_revision'
    assert not events and current==before


def test_known_complete_effect_restores_all_original_parameters_and_geometry(setup):
    run,current,before,events,fault,_=setup;fault['value']='known';job=run()
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back'
    assert current==before and events.count('parameters')==2 and events[-1]=='released'


@pytest.mark.parametrize('fault_name',['foreign','intermediate','relief'])
def test_foreign_or_intermediate_state_is_unknown_without_unsafe_restoration(setup,fault_name):
    run,current,before,events,fault,_=setup;fault['value']=fault_name;job=run()
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved'
    assert job['error']['requires_reconciliation'] is True
    assert events.count('parameters')==1 and 'names' not in events and current!=before
