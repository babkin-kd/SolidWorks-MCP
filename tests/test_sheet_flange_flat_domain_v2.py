"""Full independent L-source/U/flat material states; not CAD acceptance."""

from copy import deepcopy
from types import SimpleNamespace as NS
import uuid

import pytest

from solidworks_mcp.jobs import ExecutionFailure,JobRunner
from solidworks_mcp.sheet_flange_flat_state import SheetFlangeFlatStateCatalog,flange_flat_arguments,own_u_dimensions_match
from solidworks_mcp.sheet_flat_state import STATE_ROLES
from test_sheet_edge_flange_domain_v2 import effect
from test_part_creation_domain_v2 import setup as part_setup
from test_edge_flange_sketch_v2 import profile
from test_sheet_flange_flat_geometry_v2 import flat_material
from test_planar_brep_v2 import snapshot
from test_part_construction_mutation_v2 import Worker


def u_state(part_setup,profile,flattened=False):
    _,created,d=effect(part_setup,profile);e=deepcopy(created['evidence']['source']);semantic=created['semantic']
    roles=dict(profile='flange_sketch',flange='flange',bend='flange_bend',flat_bend='flange_flat_bend')
    own=[dict(row,role=roles[row['role']],reference_strategy='owned_persistent_feature_v1') for row in created['evidence']['created']['owned']]
    e['members'].extend(own)
    by_role={r['role']:r for r in e['members']}
    parents={'sketch':'base','bend':'base','flat_sketch_1':'flat','flat_sketch_2':'flat',
        'ui_bend':'flat','fold_sketch_folder':'flat','flange_sketch':'flange','flange_bend':'flange','flange_flat_bend':'flat'}
    for row in e['members']:
        if row['role'] in STATE_ROLES:row['suppressed']=not flattened
        if row['role']!='cut_list':row['owner_native_id']=by_role[parents[row['role']]]['native_id'] if row['role'] in parents else None
    by_id={r['native_id']:r for r in e['members']}
    for row in semantic['tree']['features']:
        if row['native_id'] in by_id:
            row['suppressed']=by_id[row['native_id']]['suppressed']
            row['owner_native_id']=by_id[row['native_id']]['owner_native_id']
    height=semantic['dimensions'][-3];sketch=by_id[60]
    height.update(parameter_type=0,owner={k:v for k,v in sketch.items() if k not in ('role','pid_hex','reference_strategy')},
        tolerance=dict(type=0,values_si=[]),display_dimensions=[dict(type=2,linked=False,linked_text='')])
    height['owner'].update(frozen=False,rolled_back=False)
    e.update(flange_profile=deepcopy(created['evidence']['created']['profile']),
        flange_parameters=deepcopy(created['evidence']['created']['parameters']),flattened=flattened)
    if flattened:
        body,length=flat_material();semantic['geometry']['bodies']=[snapshot(body)]
        e['volume_mm3']=length*.002*.030*1e9;e['area_mm2']=2.*(length*.002+length*.030+.002*.030)*1e6
        points=[[x,0.,z] for x in (.040-length,.040) for z in (0.,.030)]
        e['fixed_face'].update(vertices=points,plane_parameters=[0.,-1.,0.]+points[0])
    return dict(semantic=semantic,evidence=e,dimension_revision='rev_native',base_pid_hex='aa',flange_pid_hex='ff'),d


@pytest.mark.parametrize('flattened',[False,True])
def test_full_u_and_flat_source_retains_both_allowances_and_six_dimensions(part_setup,profile,flattened):
    state,d=u_state(part_setup,profile,flattened)
    flat,fold=SheetFlangeFlatStateCatalog._source(state,d,'Основная')
    assert len(state['semantic']['dimensions'])==6 and len(state['evidence']['members'])==16
    assert flat['k_factors']==[.42,.38] and fold['face_count']==22


@pytest.mark.parametrize('fault',['first_k','second_k','radius','angle','height','foreign_dimension','profile_relation',
    'original_relation','owner','member','member_pid','extra_feature','fixed_face','body','volume','configuration','controls'])
def test_unproved_two_bend_source_cannot_prepare_a_state_change(part_setup,profile,fault):
    state,d=u_state(part_setup,profile);e=state['evidence'];s=state['semantic']
    if fault=='first_k':e['sheet_parameters']['k_factor']=.5
    elif fault=='second_k':e['flange_parameters']['k_factor']=.5
    elif fault=='radius':s['dimensions'][-2]['values_si']['Основная']=.003
    elif fault=='angle':s['dimensions'][-1]['values_si']['Основная']=1.5
    elif fault=='height':s['dimensions'][-3]['values_si']['Основная']=.014
    elif fault=='foreign_dimension':s['dimensions'].append(deepcopy(s['dimensions'][0]))
    elif fault=='profile_relation':e['flange_profile']['relations'].pop()
    elif fault=='original_relation':e['sketch']['relations'].pop()
    elif fault=='owner':e['members'][-1]['owner_native_id']=999
    elif fault=='member':e['members'].pop()
    elif fault=='member_pid':e['members'][-1]['pid_hex']=''
    elif fault=='extra_feature':s['tree']['features'].append(dict(s['tree']['features'][-1],native_id=999))
    elif fault=='fixed_face':e['fixed_face']['vertices'][0][0]+=.001
    elif fault=='body':s['geometry']['bodies']*=2
    elif fault=='volume':e['volume_mm3']+=1.
    elif fault=='configuration':s['tree']['document']['configurations'].append('Чужая')
    else:e['controls']['dimension_input']=True
    with pytest.raises(ExecutionFailure):SheetFlangeFlatStateCatalog._source(state,d,'Основная')


def test_only_proved_state_footprint_authorizes_original_name_preservation(part_setup,profile):
    before,d=u_state(part_setup,profile);after,_=u_state(part_setup,profile,True)
    assert SheetFlangeFlatStateCatalog._transition(before,after,True)
    cut=next(r for r in after['evidence']['members'] if r['role']=='cut_list');cut['name']='Автоматическое имя'
    next(r for r in after['semantic']['tree']['features'] if r['native_id']==cut['native_id'])['name']=cut['name']
    after['evidence']['body_name']='Автоматическое тело'
    assert not SheetFlangeFlatStateCatalog._transition(before,after,True)
    assert SheetFlangeFlatStateCatalog._transition(before,after,True,allow_names=True)


@pytest.mark.parametrize('fault',['original_dimension','new_dimension','first_k','second_k','profile','controls','member_pid','owner','body_pid','flange_pid','foreign_name'])
def test_foreign_effect_never_permits_scoped_refolding(part_setup,profile,fault):
    before,_=u_state(part_setup,profile);after,_=u_state(part_setup,profile,True);e=after['evidence'];s=after['semantic']
    if fault=='original_dimension':s['dimensions'][0]['values_si']['Основная']+=.001
    elif fault=='new_dimension':s['dimensions'][-2]['values_si']['Основная']+=.001
    elif fault=='first_k':e['sheet_parameters']['k_factor']=.5
    elif fault=='second_k':e['flange_parameters']['k_factor']=.5
    elif fault=='profile':e['flange_profile']['relations'].pop()
    elif fault=='controls':e['controls']['auto_solve']=not e['controls']['auto_solve']
    elif fault=='member_pid':e['members'][-1]['pid_hex']='aa'
    elif fault=='owner':e['members'][-1]['owner_native_id']=999
    elif fault=='body_pid':e['body_pid_hex']='ee'
    elif fault=='flange_pid':after['flange_pid_hex']='ee'
    else:s['tree']['features'][0]['name']='Чужая правка'
    assert not SheetFlangeFlatStateCatalog._transition(before,after,True,allow_names=True)


@pytest.fixture
def transaction(part_setup,profile,monkeypatch):
    adapter,parts,ids,planes=part_setup;before,d=u_state(part_setup,profile);flat,_=u_state(part_setup,profile,True)
    current=deepcopy(before);events=[];fault=dict(value=None);op={};entry=NS(model=object(),features={})
    catalog=SheetFlangeFlatStateCatalog(parts.dimensions);store=parts.dimensions.coordinator.store;target=object()
    def prepare(*args,**kwargs):
        return dict(revision='rev_prepared'),(NS(state=(entry,)),target,deepcopy(current),(),d,{}, {})
    monkeypatch.setattr(catalog,'_prepare',prepare)
    monkeypatch.setattr(catalog,'_capture',lambda *a,**k:(None,target,deepcopy(current)))
    class Guard:
        def __enter__(self):
            assert store.get(op['id'])['mutation']['phase']=='prepared';events.append('guard');self.evidence=dict(released=False)
        def __exit__(self,*args):events.append('released');self.evidence=dict(released=True)
    parts.dimensions.mutation_guard=lambda model:Guard()
    def write(model,target,flattened):
        events.append('flat' if flattened else 'fold');current.clear();current.update(deepcopy(flat if flattened else before))
        if fault['value']=='foreign' and flattened:
            current['semantic']['tree']['features'][0]['name']='Чужая правка';raise RuntimeError('Foreign effect.')
    def names(*args):
        events.append('names')
        if fault['value']=='known':fault['value']=None;raise RuntimeError('Known completed effect.')
    adapter.sheet_change_flange_flat_state=write;adapter.sheet_preserve_flange_flat_names=names
    runner=JobRunner(store,Worker())
    def run(revision='rev_prepared',request=None):
        args=dict(document_id=ids[0],configuration='Основная',base_object_id=planes[0],flange_object_id='feat_'+'e'*32,
            flattened=True,expected_revision=revision)
        def execute(operation_id):op['id']=operation_id;return catalog.set_flat_state(operation_id,**args)
        return runner.submit(request or uuid.uuid4().hex,'sheet.set_flange_flat_state',args,execute,
            context={k:args[k] for k in ('document_id','configuration','expected_revision')},mutates=True,
            pass_operation_id=True,verify=lambda result:result['verified'] is True)
    return run,current,before,events,fault


def test_durable_checkpoint_precedes_guard_and_native_state_change(transaction):
    run,current,before,events,_=transaction;job=run()
    assert job['status']=='succeeded' and job['mutation']['phase']=='committed' and current!=before
    assert events==['guard','flat','names','released']


def test_known_failure_restores_only_proved_previous_state(transaction):
    run,current,before,events,fault=transaction;fault['value']='known';job=run()
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back' and current==before
    assert events==['guard','flat','names','fold','names','released']


def test_foreign_effect_stays_unknown_without_a_second_write(transaction):
    run,current,before,events,fault=transaction;fault['value']='foreign';job=run()
    assert job['status']=='unknown' and job['mutation']['phase']=='unresolved' and current!=before
    assert 'fold' not in events and events[-1]=='released'


def test_stale_prewrite_never_enters_guard(transaction):
    run,current,before,events,_=transaction;job=run('rev_stale')
    assert job['status']=='failed' and job['error']['code']=='stale_revision' and current==before and events==[]


def test_request_id_does_not_repeat_native_flattening(transaction):
    run,_,_,events,_=transaction;first=run(request='same-u-flat');second=run(request='same-u-flat')
    assert first['operation_id']==second['operation_id'] and events.count('flat')==1
