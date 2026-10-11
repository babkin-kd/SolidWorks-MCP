"""Full independently constructed material states for the parameter domain."""

from copy import deepcopy
from dataclasses import replace
import math
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.sheet_parameters import SheetParameterCatalog,parameter_values,parameter_definition,SCOPE
from solidworks_mcp.sheet_flat_state import SheetFlatStateCatalog
from test_part_creation_domain_v2 import setup as part_setup
from test_sheet_flat_domain_v2 import state
from test_sheet_profile_definition_v2 import folded_body,read
from test_sheet_flat_geometry_v2 import POLYGONS
from test_planar_brep_v2 import make_body,snapshot


def options():
    return dict(base=dict(UseDefaultBendRelief=False,UseReliefRatio=True,ReliefRatio=.5,ReliefType=2,ReliefWidth=.0001,ReliefDepth=.0001),
        sheet=dict(AutoReliefType=2,ReliefRatio=.5,UseAutoRelief=True),
        template=dict(AutoReliefType=2,ReliefRatio=.5,UseAutoRelief=True,Thickness=.002,BendRadius=.002,
            UseMaterialSheetMetalParameters=False,AllowanceType=2,KFactor=.42),gauge=dict(result_code=0,enabled=False,file_name=''))


def material_state(part_setup,flattened=False,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42):
    current,original=state(part_setup,flattened);e=current['evidence'];t=thickness_mm/1000.;r=bend_radius_mm/1000.
    definition=replace(original,thickness_mm=thickness_mm,bend_radius_mm=bend_radius_mm,k_factor=k_factor)
    e['parameter_options']=options();e['base_parameters'].update(Thickness=t,BendRadius=r)
    e['parameter_options']['template'].update(Thickness=t,BendRadius=r,KFactor=k_factor)
    e['sheet_parameters'].update(thickness=t,radius=r,k_factor=k_factor)
    developed=.04+.02-2.*(r+t)+math.pi/2.*(r+k_factor*t)
    if flattened:
        points=[(x,y,z) for x in (.04-developed,.04) for y in (0.,t) for z in (0.,.03)]
        body=snapshot(make_body(points,POLYGONS));volume=developed*t*.03;area=2.*(developed*t+developed*.03+t*.03)
    else:
        body=read(folded_body(thickness=t,radius=r))
        section=t*(.04+.02-2.*(r+t))+math.pi/4.*((r+t)**2-r**2)
        perimeter=2.*(.04+.02-2.*(r+t))+2.*t+math.pi/2.*(r+t+r)
        volume=section*.03;area=2.*section+perimeter*.03
    current['semantic']['geometry']['bodies']=[body]
    e['volume_mm3']=volume*1e9;e['area_mm2']=area*1e6
    points=[[x,0.,z] for x in ((.04-developed if flattened else r+t),.04) for z in (0.,.03)]
    e['fixed_face'].update(vertices=points,plane_parameters=[0.,-1.,0.]+points[0])
    return current,definition


@pytest.mark.parametrize('flattened',[False,True])
def test_complete_flat_and_folded_shapes_match_explicit_new_parameters(part_setup,flattened):
    before,_=material_state(part_setup,flattened);after,requested=material_state(part_setup,flattened,2.5,3.5,.38)
    # Both boundaries are validated by the real closed-source engineering proof.
    for current in (before,after):SheetParameterCatalog._source(current,'Основная',requested.plane_object_id)
    assert SheetParameterCatalog._parameter_transition(before,after,requested)
    assert before['semantic']['dimensions']==after['semantic']['dimensions']
    assert before['evidence']['volume_mm3']!=after['evidence']['volume_mm3']


def test_folded_shape_and_mass_do_not_prove_k_change(part_setup):
    before,_=material_state(part_setup);after,requested=material_state(part_setup,k_factor=.38)
    assert before['semantic']['geometry']==after['semantic']['geometry']
    assert before['evidence']['volume_mm3']==after['evidence']['volume_mm3']
    assert SheetParameterCatalog._parameter_transition(before,after,requested)
    assert not SheetParameterCatalog._parameter_transition(before,before,requested)


@pytest.mark.parametrize('fault',['driver','length','sketch','body_pid','fixed_leg','fixed_side','suppression','member_pid','member_owner','foreign_name','foreign_node','relief_width','relief_type','gauge','missing_options','wrong_k','wrong_radius'])
def test_no_parameter_change_authorizes_foreign_definition_or_tree_effects(part_setup,fault):
    before,_=material_state(part_setup);after,requested=material_state(part_setup,False,2.5,3.5,.38);e=after['evidence'];s=after['semantic']
    if fault=='driver':s['dimensions'][0]['values_si']['Основная']=.041
    elif fault=='length':e['base_parameters']['D1EndConditionDistance']=.04
    elif fault=='sketch':e['sketch']['relations'].pop()
    elif fault=='body_pid':e['body_pid_hex']='dd'
    elif fault=='fixed_leg':e['fixed_leg']='y'
    elif fault=='fixed_side':e['fixed_face']['plane_parameters'][:3]=[0.,1.,0.]
    elif fault=='suppression':e['flattened']=True
    elif fault=='member_pid':e['members'][0]['pid_hex']='dd'
    elif fault=='member_owner':e['members'][0]['owner_native_id']=999
    elif fault=='foreign_name':s['tree']['features'][0]['name']='Изменение извне'
    elif fault=='foreign_node':s['tree']['features'].append(dict(native_id=998))
    elif fault=='relief_width':e['parameter_options']['base']['ReliefWidth']=.0002
    elif fault=='relief_type':e['parameter_options']['sheet']['AutoReliefType']=1
    elif fault=='gauge':e['parameter_options']['gauge']['enabled']=True
    elif fault=='missing_options':e.pop('parameter_options')
    elif fault=='wrong_k':e['sheet_parameters']['k_factor']=.5
    elif fault=='wrong_radius':e['sheet_parameters']['radius']=.003
    assert not SheetParameterCatalog._parameter_transition(before,after,requested,allow_names=True)


def test_changed_native_parameters_need_their_full_changed_shape(part_setup):
    before,_=material_state(part_setup);after,item=material_state(part_setup,False,2.5,3.5,.38)
    after['semantic']['geometry']=deepcopy(before['semantic']['geometry'])
    with pytest.raises(ExecutionFailure,match='complete material boundary'):
        SheetParameterCatalog._source(after,'Основная',item.plane_object_id)


def test_names_are_preserved_only_after_other_effects_proved(part_setup):
    before,_=material_state(part_setup);after,item=material_state(part_setup,False,2.5,3.5,.38)
    cut=next(r for r in after['evidence']['members'] if r['role']=='cut_list');cut['name']='Sheet<2>'
    next(r for r in after['semantic']['tree']['features'] if r['native_id']==cut['native_id'])['name']='Sheet<2>'
    after['evidence']['body_name']='Auto body'
    assert not SheetParameterCatalog._parameter_transition(before,after,item)
    assert SheetParameterCatalog._parameter_transition(before,after,item,allow_names=True)


@pytest.mark.parametrize('name,value',[('thickness_mm',True),('thickness_mm',0.),('thickness_mm',float('nan')),
    ('thickness_mm',float('inf')),('bend_radius_mm',-1.),('bend_radius_mm','3'),('bend_radius_mm',1e8),
    ('k_factor',False),('k_factor',float('nan')),('k_factor',float('inf')),('k_factor',-.01),('k_factor',1.01),('k_factor','0.4')])
def test_invalid_requests_cannot_reach_native_capture(name,value):
    values=dict(thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38);values[name]=value
    with pytest.raises(ExecutionFailure):parameter_values(**values)


@pytest.mark.parametrize('fault',['missing','boolean_number','integer_boolean','nan','gauge_error','gauge_flag','gauge_file'])
def test_incomplete_relief_and_gauge_evidence_are_not_adopted(fault):
    current=options()
    if fault=='missing':current['base'].pop('ReliefWidth')
    elif fault=='boolean_number':current['base']['ReliefWidth']=False
    elif fault=='integer_boolean':current['sheet']['UseAutoRelief']=1
    elif fault=='nan':current['sheet']['ReliefRatio']=float('nan')
    elif fault=='gauge_error':current['gauge']['result_code']=1
    elif fault=='gauge_flag':current['gauge']['enabled']=True
    elif fault=='gauge_file':current['gauge']['file_name']=1
    with pytest.raises(ExecutionFailure):SheetParameterCatalog._validate_options(current)


@pytest.mark.parametrize('file_name',[None,'','inactive-table.xlsx'])
def test_disabled_table_filename_is_dormant_but_preserved_in_capture(file_name):
    current=options();current['gauge']['file_name']=file_name
    SheetParameterCatalog._validate_options(current)
    assert current['gauge']['file_name']==file_name


def test_invalid_outer_radius_preserves_straight_leg_boundary(part_setup):
    _,source=material_state(part_setup)
    with pytest.raises(ExecutionFailure,match='outer bend radius'):
        parameter_definition(source,parameter_values(10.,10.,.38))
    old=replace(source,body_name='Library body',feature_name='Library angle',sketch_name='Library profile')
    new=parameter_definition(old,parameter_values(2.5,3.5,.38))
    assert (new.body_name,new.feature_name,new.sketch_name)==(old.body_name,old.feature_name,old.sketch_name)


def test_parameter_revision_binds_requested_values_and_complete_options(part_setup,monkeypatch):
    current,item=material_state(part_setup);adapter,parts,ids,planes=part_setup;catalog=SheetParameterCatalog(parts.dimensions)
    def capture(*args,**kwargs):return NS(),object(),deepcopy(current),(),item,{},{}
    monkeypatch.setattr(catalog,'_capture',capture)
    args=dict(document_id=ids[0],configuration='Основная',base_object_id=planes[0],thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38)
    first=catalog.prepare_parameters(**args);assert first['revision_scope']==SCOPE and first['native_change_available'] is False
    assert catalog.prepare_parameters(**args)['revision']==first['revision']
    assert catalog.prepare_parameters(**{**args,'k_factor':.4})['revision']!=first['revision']
    current['evidence']['parameter_options']['base']['ReliefWidth']=.0002
    assert catalog.prepare_parameters(**args)['revision']!=first['revision']


@pytest.mark.parametrize('late_change',[False,True])
def test_extra_definition_getters_close_the_original_native_event_proof(part_setup,monkeypatch,late_change):
    adapter,parts,ids,planes=part_setup;catalog=SheetParameterCatalog(parts.dimensions)
    original=parts.dimensions._capture(ids[0],'Основная');entry=original.state[0]
    current,item=material_state(part_setup);target=object();events=[];sequence=dict(value=original.event_sequence)
    monkeypatch.setattr(entry.features['watch'],'poll',lambda:sequence['value'])
    monkeypatch.setattr(SheetFlatStateCatalog,'_capture_once',lambda *a,**k:(original,target,deepcopy(current),(),item,{},{}))
    def read_options(model,retained):
        assert retained is target;events.append('native_options')
        if late_change:sequence['value']+=1
        return options()
    adapter.sheet_parameter_options=read_options
    if late_change:
        with pytest.raises(ExecutionFailure) as failure:catalog._capture_once(ids[0],'Основная',planes[0])
        assert failure.value.code=='document_changed_during_read'
    else:
        result=catalog._capture_once(ids[0],'Основная',planes[0])
        assert result[2]['evidence']['parameter_options']==options()
    assert events==['native_options']


def test_unconnected_native_writer_is_rejected_before_preparation_or_guard(part_setup,monkeypatch):
    adapter,parts,ids,planes=part_setup;catalog=SheetParameterCatalog(parts.dimensions)
    parts.dimensions.mutation_guard=lambda model:pytest.fail('guard must not start')
    monkeypatch.setattr(catalog,'_prepare_parameters',lambda **kw:pytest.fail('prepare must not start'))
    with pytest.raises(ExecutionFailure) as failure:
        catalog.set_parameters('op',ids[0],'Основная',planes[0],2.5,3.5,.38,'rev_unused')
    assert failure.value.code=='sheet_parameter_native_unavailable'
