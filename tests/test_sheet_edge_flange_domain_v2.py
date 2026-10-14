"""Independent complete L/U and sketch fixtures; these are not CAD acceptance."""

from copy import deepcopy
from types import SimpleNamespace as NS
import uuid

import pytest

from solidworks_mcp.jobs import JobRunner
from solidworks_mcp.sheet_edge_flange import SheetEdgeFlangeCatalog
from solidworks_mcp.sheet_edge_flange_definition import EdgeFlangeOnL
from solidworks_mcp.sheet_edge_flange_parameters import flange_options
from test_part_creation_domain_v2 import setup as part_setup
from test_sheet_parameters_v2 import material_state
from test_edge_flange_sketch_v2 import profile,capture
from test_sheet_edge_flange_definition_v2 import u_body,read
from test_part_construction_mutation_v2 import Worker


def effect(part_setup,profile,phase='completed'):
    before,source=material_state(part_setup)
    definition=EdgeFlangeOnL.validate(source,15.,2.5,.38)
    profile[0].relations[0].definitions=[profile[2] if phase=='input' else profile[1],profile[0].lines[0]]
    sketch,_=capture(profile,'after_factory' if phase=='completed' else 'before_factory')
    sketch['driver_value_si']=float(.013).hex()
    e=deepcopy(before['evidence']);e.pop('fixed_leg')
    semantic=deepcopy(before['semantic'])
    flat=next(r['native_id'] for r in e['members'] if r['role']=='flat')
    own=[]
    roles=[('profile',60,definition.sketch_name,'ProfileFeature',None)] if phase=='input' else [
        ('flange',67,definition.feature_name,'EdgeFlange',None),('profile',60,definition.sketch_name,'ProfileFeature',67),
        ('bend',73,'Сгиб отбортовки','OneBend',67),('flat_bend',75,'Развёртка сгиба отбортовки','UiBend',flat)]
    for role,id,name,kind,owner in roles:
        row=dict(native_id=id,name=name,feature_type=kind,owner_native_id=owner,
            suppressed=False,error_code=0,is_warning=False)
        own.append(dict(row,role=role,pid_hex=bytes([id]).hex()))
        semantic['tree']['features'].append(row)
    relation=next(r for r in sketch['relations'] if r['type']==1)
    semantic['dimensions'].append(dict(name='Вылет от внутреннего ребра',full_name=relation['dimension_full_name'],
        unit='mm',owner=dict(native_id=60,feature_type='ProfileFeature'),driven_state=2,read_only=False,
        reference=False,design_table=False,linked=False,values_si={'Основная':.013}))
    parameters=None
    if phase=='completed':
        parameters=dict(flange_options(definition),allowance_type=2,k_factor=.38,edge_count=1)
        semantic['geometry']['bodies']=[read(u_body())]
        e.update(volume_mm3=definition.volume_mm3,area_mm2=definition.surface_area_mm2)
        bend=next(r for r in semantic['tree']['features'] if r['native_id']==73)
        import math
        for kind,name,value,display_type in ((0,'D1',.0025,5),(1,'D4',math.pi/2.,3)):
            semantic['dimensions'].append(dict(name=name,full_name=name+'@Сгиб отбортовки@Деталь',
                parameter_type=kind,unit='mm' if kind==0 else 'deg',values_si={'Основная':value},
                owner=dict(bend,frozen=False,rolled_back=False),driven_state=2,read_only=False,
                reference=False,design_table=False,linked=False,tolerance=dict(type=0,values_si=[]),
                display_dimensions=[dict(type=display_type,linked=False,linked_text='')]))
    return before,dict(phase=phase,semantic=semantic,evidence=dict(source=e,
        created=dict(complete=True,phase=phase,profile=sketch,owned=own,parameters=parameters))),definition


@pytest.mark.parametrize('phase',['input','completed'])
def test_complete_transition_retains_original_nodes_parameters_and_drivers(part_setup,profile,phase):
    before,after,definition=effect(part_setup,profile,phase)
    assert SheetEdgeFlangeCatalog._transition(before,after,definition,'Основная')


@pytest.mark.parametrize('fault',['source_k','source_driver','source_sketch','foreign_node','foreign_name','controls',
    'body_pid','fixed_face','own_pid','own_owner','own_type','own_error','own_suppression','new_driver',
    'new_readonly','new_relation','radius','second_k','wrong_brep','extra_body','volume','area','incomplete'])
def test_same_mass_or_names_never_prove_foreign_or_incomplete_effect(part_setup,profile,fault):
    before,after,d=effect(part_setup,profile);e=after['evidence'];s=after['semantic'];c=e['created']
    if fault=='source_k':e['source']['sheet_parameters']['k_factor']=.5
    elif fault=='source_driver':s['dimensions'][0]['values_si']['Основная']+=.001
    elif fault=='source_sketch':e['source']['sketch']['relations'].pop()
    elif fault=='foreign_node':s['tree']['features'].append(dict(native_id=999))
    elif fault=='foreign_name':s['tree']['features'][0]['name']='Чужая правка'
    elif fault=='controls':e['source']['controls']['add_to_db']=True
    elif fault=='body_pid':e['source']['body_pid_hex']='ff'
    elif fault=='fixed_face':e['source']['fixed_face']['plane_parameters'][0]=1.
    elif fault=='own_pid':c['owned'][0]['pid_hex']=''
    elif fault=='own_owner':c['owned'][1]['owner_native_id']=999
    elif fault=='own_type':c['owned'][0]['feature_type']='Imported'
    elif fault=='own_error':c['owned'][0]['error_code']=1
    elif fault=='own_suppression':c['owned'][0]['suppressed']=True
    elif fault=='new_driver':s['dimensions'][-1]['values_si']['Основная']=.014
    elif fault=='new_readonly':s['dimensions'][-1]['read_only']=True
    elif fault=='new_relation':c['profile']['relations'].pop()
    elif fault=='radius':c['parameters']['BendRadius']=.003
    elif fault=='second_k':c['parameters']['k_factor']=.4
    elif fault=='wrong_brep':s['geometry']['bodies']=[read(u_body(flange=.016))]
    elif fault=='extra_body':s['geometry']['bodies']*=2
    elif fault=='volume':e['source']['volume_mm3']+=1.
    elif fault=='area':e['source']['area_mm2']+=1.
    else:c['complete']=False
    assert not SheetEdgeFlangeCatalog._transition(before,after,d,'Основная',allow_names=True)


@pytest.mark.parametrize('fault',['missing','duplicate','extra','radius','angle','units','kind','owner',
    'owner_name','readonly','linked','tolerance','display','configuration','driven','frozen','rolled_back'])
def test_owned_bend_dimensions_require_exact_radius_angle_and_complete_control(part_setup,profile,fault):
    before,after,d=effect(part_setup,profile);rows=after['semantic']['dimensions'];radius,angle=rows[-2:]
    if fault=='missing':rows.pop()
    elif fault=='duplicate':rows[-1]=deepcopy(radius)
    elif fault=='extra':rows.append(deepcopy(angle))
    elif fault=='radius':radius['values_si']['Основная']=.003
    elif fault=='angle':angle['values_si']['Основная']+=.1
    elif fault=='units':angle['unit']='mm'
    elif fault=='kind':angle['parameter_type']=True
    elif fault=='owner':radius['owner']['native_id']=999
    elif fault=='owner_name':radius['owner']['name']='Чужой сгиб'
    elif fault=='readonly':radius['read_only']=True
    elif fault=='linked':angle['linked']=True
    elif fault=='tolerance':radius['tolerance']['values_si']=[.0001,.0002]
    elif fault=='display':radius['display_dimensions'][0]['type']=2
    elif fault=='configuration':angle['values_si']['Чужая']=1.5
    elif fault=='driven':angle['driven_state']=1
    elif fault=='frozen':radius['owner']['frozen']=True
    else:angle['owner']['rolled_back']=True
    assert not SheetEdgeFlangeCatalog._transition(before,after,d,'Основная',allow_names=True)


@pytest.fixture
def transaction(part_setup,profile,monkeypatch):
    adapter,parts,ids,planes=part_setup;before,completed,definition=effect(part_setup,profile)
    _,input_state,_=effect(part_setup,profile,'input');current=deepcopy(before)
    catalog=SheetEdgeFlangeCatalog(parts.dimensions);store=parts.dimensions.coordinator.store
    events=[];fault=dict(value=None);op={};entry=NS(model=object(),features={})
    target=object();edge=object();reference=NS(persistent_id=b'edge')
    adapter.identity=id;adapter.same_persistent_id=lambda m,a,b:a==b
    captured=(NS(state=(entry,)),target,before,(),definition.source,{}, {})
    def prepare(*args,**kwargs):
        return dict(revision='rev_prepared',native_change_available=True),captured,definition,edge,reference
    monkeypatch.setattr(catalog,'_prepare_edge_flange',prepare)
    monkeypatch.setattr(catalog,'_capture',lambda *a,**k:captured)
    def inspect(doc,cfg,capture,d,receipt,base):
        if receipt is None or receipt.restored or receipt.sketch is None:return dict(phase='original',state=deepcopy(current))
        return deepcopy(current)
    monkeypatch.setattr(catalog,'_inspect_flange',inspect)
    class Guard:
        def __enter__(self):
            assert store.get(op['id'])['mutation']['phase']=='prepared'
            events.append('guard');self.evidence=dict(released=False)
        def __exit__(self,*args):events.append('released');self.evidence=dict(released=True)
    parts.dimensions.mutation_guard=lambda m:Guard()
    def receipt(*args):
        if fault['value']=='receipt':raise RuntimeError('Read-only receipt creation failed.')
        return NS(restored=False,sketch=None)
    adapter.new_sheet_flange_receipt=receipt
    def write(model,d,r_frame,r):
        events.append('create');r.sketch=object()
        current.clear();current.update(deepcopy(input_state if fault['value']=='input' else completed))
        if fault['value']=='foreign':current['semantic']['tree']['features'][0]['name']='Чужая правка'
        if fault['value'] in ('input','foreign'):raise RuntimeError('Injected creation failure.')
    adapter.create_sheet_edge_flange=write
    def names(*args):
        events.append('names')
        if fault['value']=='known':raise RuntimeError('Known complete effect failure.')
    adapter.sheet_flange_preserve_names=names
    def restore(model,r,*args):
        events.append('restore');r.restored=True;current.clear();current.update(deepcopy(before))
    adapter.restore_sheet_edge_flange=restore
    runner=JobRunner(store,Worker())
    def run(revision='rev_prepared',request=None):
        args=dict(document_id=ids[0],configuration='Основная',base_object_id=planes[0],edge_id='obj_'+'d'*32,
            flange_length_mm=15.,bend_radius_mm=2.5,k_factor=.38,expected_revision=revision)
        def execute(operation_id):op['id']=operation_id;return catalog.create_edge_flange(operation_id,**args)
        return runner.submit(request or uuid.uuid4().hex,'sheet.create_edge_flange',args,execute,
            context={k:args[k] for k in ('document_id','configuration','expected_revision')},mutates=True,
            pass_operation_id=True,verify=lambda result:result['verified'] is True)
    return run,current,before,events,fault


def test_checkpoint_precedes_guard_and_full_effect_commits(transaction):
    run,current,before,events,_=transaction;job=run()
    assert job['status']=='succeeded' and job['mutation']['phase']=='committed'
    assert events==['guard','create','names','released'] and current!=before


def test_stale_revision_never_enters_guard_or_writes(transaction):
    run,current,before,events,_=transaction;job=run('rev_stale')
    assert job['status']=='failed' and job['error']['code']=='stale_revision'
    assert events==[] and current==before


@pytest.mark.parametrize('fault_name',['known','input','receipt'])
def test_only_proved_complete_or_input_effect_is_restored(transaction,fault_name):
    run,current,before,events,fault=transaction;fault['value']=fault_name;job=run()
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back'
    assert current==before and events[-1]=='released'
    assert events.count('restore')==(0 if fault_name=='receipt' else 1)


def test_foreign_effect_stays_unknown_without_deletion(transaction):
    run,current,before,events,fault=transaction;fault['value']='foreign';job=run()
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved'
    assert job['error']['requires_reconciliation'] is True and 'restore' not in events
    assert current!=before and events[-1]=='released'


def test_request_id_deduplicates_the_exact_creation_job(transaction):
    run,_,_,events,_=transaction;first=run(request='same-flange');second=run(request='same-flange')
    assert first['operation_id']==second['operation_id'] and events.count('create')==1


@pytest.mark.parametrize('fault',['none','member','driver','options','mass','body'])
def test_two_closing_captures_bind_profile_members_and_original_source(part_setup,profile,fault):
    from solidworks_mcp.jobs import ExecutionFailure
    before,after,d=effect(part_setup,profile)
    first=NS(state=(NS(model=object()),None,None,deepcopy(after['semantic'])))
    second=NS(state=(first.state[0],None,None,deepcopy(after['semantic'])))
    captures=iter((first,second));evidences=[deepcopy(after['evidence']),deepcopy(after['evidence'])]
    memberships=[(('own point',[1]),),(('own point',[1]),)]
    if fault=='member':memberships[1]=(('own point',[2]),)
    elif fault=='driver':second.state[3]['dimensions'][-1]['values_si']['Основная']=.014
    elif fault=='options':evidences[1]['source']['parameter_options']['base']['ReliefWidth']=.0002
    elif fault=='mass':evidences[1]['source']['volume_mm3']+=1.
    elif fault=='body':evidences[1]['source']['body_pid_hex']='ff'
    reads=iter(zip(evidences,memberships));events=[]
    adapter=NS(sheet_edge_flange_evidence=lambda *args:next(reads))
    dimensions=NS(adapter=adapter,documents=NS(adapter=adapter),features=None,
        _capture=lambda *args:next(captures),_same_capture=lambda a,b:a.state[3]==b.state[3],
        _close_capture_pair=lambda *args:events.append('closed'))
    catalog=SheetEdgeFlangeCatalog(dimensions);receipt=NS(restored=False,sketch=object())
    if fault=='none':
        result=catalog._inspect_flange('doc','Основная',(None,None,before),d,receipt,'base')
        assert result['phase']=='completed' and result['semantic']==after['semantic']
    else:
        with pytest.raises(ExecutionFailure,match='closing flange captures'):
            catalog._inspect_flange('doc','Основная',(None,None,before),d,receipt,'base')
    assert events==['closed']


@pytest.mark.parametrize('flag',['pending_creation','pending_deletion','selection_uncertain'])
def test_missing_returned_sketch_never_erases_an_uncertain_native_receipt(part_setup,flag):
    from solidworks_mcp.jobs import ExecutionFailure
    _,parts,_,_=part_setup;catalog=SheetEdgeFlangeCatalog(parts.dimensions)
    receipt=NS(restored=False,sketch=None,**{flag:True})
    catalog._capture=lambda *args:pytest.fail('An uncertain receipt must not be treated as an original-state capture.')
    with pytest.raises(ExecutionFailure) as failure:
        catalog._inspect_flange('doc','Основная',None,None,receipt,'base')
    assert failure.value.code=='sheet_flange_outcome_unconfirmed'
