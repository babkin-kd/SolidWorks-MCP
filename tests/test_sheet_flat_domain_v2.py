"""Complete independent sheet-state source and transition proof, not CAD."""

from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.sheet_flat_state import SheetFlatStateCatalog,STATE_ROLES
from test_sheet_profile_domain_v2 import catalog_and_state
from test_part_creation_domain_v2 import setup as part_setup
from test_sheet_flat_geometry_v2 import native_flat,fixed_face
from test_planar_brep_v2 import snapshot


def state(part_setup,flattened=False):
    catalog,item,prepared,before,after=catalog_and_state(part_setup);source=after['created'];semantic=after['semantic']
    members=[dict(row) for row in source['auxiliary']]
    for role,id in (('base',source['base_native_id']),('sketch',source['sketch_native_id'])):
        row=next(row for row in semantic['tree']['features'] if row['native_id']==id)
        members.append(dict(row,role=role,pid_hex='cc',reference_strategy='owned_persistent_feature_v1'))
    for row in members:
        if row['role'] in STATE_ROLES:row['suppressed']=not flattened
    by_id={r['native_id']:r for r in members}
    for row in semantic['tree']['features']:
        if row['native_id'] in by_id:row['suppressed']=by_id[row['native_id']]['suppressed']
    if flattened:semantic['geometry']['bodies']=[snapshot(native_flat())]
    d=52.+3.141592653589793/2.*2.84
    evidence=dict(base_native_id=source['base_native_id'],sketch_native_id=source['sketch_native_id'],sketch=source['sketch'],
        members=members,body_pid_hex='bb',body_name=item.body_name,base_parameters=source['base_parameters'],sheet_parameters=source['sheet_parameters'],
        fixed_face=fixed_face(flattened=flattened),fixed_leg='x',options=dict(MergeFace=True,SimplifyBends=True,ShowSlitInCornerRelief=True),
        controls=prepared['creation_controls'],flattened=flattened,plane_pid_hex=prepared['plane_persistent_id_hex'],plane_transform=prepared['plane_transform'],
        volume_mm3=d*2.*30. if flattened else item.volume_mm3,area_mm2=2.*(d*2.+d*30.+2.*30.) if flattened else item.surface_area_mm2)
    return dict(semantic=semantic,evidence=evidence),item


@pytest.mark.parametrize('flattened',[False,True])
def test_complete_native_state_and_independent_k_material_match(part_setup,flattened):
    capture,item=state(part_setup,flattened)
    definition,flat,fold=SheetFlatStateCatalog._source(capture,'Основная',item.plane_object_id)
    assert definition.k_factor==.42 and flat['fixed_leg']=='x' and fold['face_count']==14


@pytest.mark.parametrize('fault',['k','flat_role','hidden_folder_state','member_error','missing_member','additional_sketch','profile_driver','length_driver','wrong_shape','wrong_mass','wrong_face','readonly','external','configuration','rebuild','controls'])
def test_no_names_mass_or_source_counts_replace_complete_native_proof(part_setup,fault):
    capture,item=state(part_setup,True);e=capture['evidence'];s=capture['semantic']
    if fault=='k':e['sheet_parameters']['k_factor']=.5
    elif fault=='flat_role':next(r for r in e['members'] if r['role']=='flat')['suppressed']=True
    elif fault=='hidden_folder_state':next(r for r in e['members'] if r['role']=='flat_folder')['suppressed']=True
    elif fault=='member_error':e['members'][0]['error_code']=1
    elif fault=='missing_member':e['members'].pop()
    elif fault=='additional_sketch':s['tree']['features'].append(dict(native_id=999,feature_type='ProfileFeature'))
    elif fault=='profile_driver':s['dimensions'][0]['read_only']=True
    elif fault=='length_driver':s['dimensions'][-1]['values_si']['Основная']=.031
    elif fault=='wrong_shape':s['geometry']['bodies']=[snapshot(native_flat(k=.5))]
    elif fault=='wrong_mass':e['volume_mm3']+=1.
    elif fault=='wrong_face':e['fixed_face']=fixed_face('y',flattened=True)
    elif fault=='readonly':s['context']['read_only']=True
    elif fault=='external':s['context']['external_reference_count']=1
    elif fault=='configuration':s['tree']['document']['configurations'].append('Чужая')
    elif fault=='rebuild':s['tree']['needs_rebuild']=True
    elif fault=='controls':e['controls']['add_to_db']=True
    with pytest.raises(ExecutionFailure):SheetFlatStateCatalog._source(capture,'Основная',item.plane_object_id)


def test_transition_preserves_every_existing_node_driver_control_and_name(part_setup):
    before,item=state(part_setup,False);after,_=state(part_setup,True)
    assert SheetFlatStateCatalog._transition(before,after,True)
    cut=next(r for r in after['evidence']['members'] if r['role']=='cut_list');cut['name']='Sheet<2>'
    next(r for r in after['semantic']['tree']['features'] if r['native_id']==cut['native_id'])['name']='Sheet<2>'
    after['evidence']['body_name']='Unfolded body'
    assert not SheetFlatStateCatalog._transition(before,after,True)
    assert SheetFlatStateCatalog._transition(before,after,True,allow_names=True)


@pytest.mark.parametrize('fault',['foreign_name','foreign_suppression','foreign_feature','driver','k','radius','sketch','controls','option','plane','fixed_leg','body_reference','member_reference','owner','missing_member'])
def test_even_name_preservation_cannot_authorize_an_unproved_transition(part_setup,fault):
    before,item=state(part_setup,False);after,_=state(part_setup,True);e=after['evidence'];s=after['semantic']
    if fault=='foreign_name':s['tree']['features'][0]['name']='Изменение извне'
    elif fault=='foreign_suppression':s['tree']['features'][0]['suppressed']=True
    elif fault=='foreign_feature':s['tree']['features'].append(dict(native_id=998))
    elif fault=='driver':s['dimensions'][0]['values_si']['Основная']=.041
    elif fault=='k':e['sheet_parameters']['k_factor']=.5
    elif fault=='radius':e['base_parameters']['BendRadius']=.003
    elif fault=='sketch':e['sketch']['relations'].pop()
    elif fault=='controls':e['controls']['auto_solve']=not e['controls']['auto_solve']
    elif fault=='option':e['options']['MergeFace']=False
    elif fault=='plane':e['plane_pid_hex']='ee'
    elif fault=='fixed_leg':e['fixed_leg']='y'
    elif fault=='body_reference':e['body_pid_hex']='dd'
    elif fault=='member_reference':e['members'][0]['pid_hex']='dd'
    elif fault=='owner':e['members'][0]['owner_native_id']=999
    elif fault=='missing_member':e['members'].pop()
    assert not SheetFlatStateCatalog._transition(before,after,True,allow_names=True)


def test_capture_registers_the_derived_plane_through_actual_feature_catalog_contract(part_setup,monkeypatch):
    current,item=state(part_setup);adapter,parts,ids,planes=part_setup
    catalog=SheetFlatStateCatalog(parts.dimensions);original=parts.dimensions._paired_capture(ids[0],'Основная')
    entry,identity=original.state[:2]
    objects=adapter.features(entry.model)
    for obj in objects:obj.GetTypeName2=lambda obj=obj:obj.state['feature_type']
    monkeypatch.setattr(parts.dimensions,'_capture',lambda *args:original)
    base=objects[0];evidence=deepcopy(current['evidence']);evidence.pop('plane_pid_hex');evidence.pop('plane_transform')
    target=object()
    adapter.sheet_state_target=lambda model,native,retained:(target,object())
    adapter.sheet_state_evidence=lambda model,native:(deepcopy(evidence),())
    # _register and _resolve remain the real FeatureCatalog methods. The
    # synthetic base is the existing strongly referenced plane for this read
    # integration test; shape/source validation is covered independently above.
    monkeypatch.setattr(catalog,'_source',lambda s,c,p:(item,dict(fixed_leg='x'),{}))
    captured=catalog._capture_once(ids[0],'Основная',planes[0])
    assert captured[1] is target and captured[2]['evidence']['plane_transform']==list(parts.adapter.frame)
