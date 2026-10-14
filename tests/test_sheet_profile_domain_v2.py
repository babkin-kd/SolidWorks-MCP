"""Full domain postconditions against synthetic independent engineering state."""

from copy import deepcopy
from dataclasses import asdict

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.sheet_profile import SheetProfileCatalog
from solidworks_mcp.sheet_profile_definition import AUXILIARY_SCHEMA
from test_part_creation_domain_v2 import setup as part_setup
from test_sheet_profile_definition_v2 import definition,folded_body,read
from test_sheet_profile_sketch_v2 import network
from test_sheet_profile_parameters_v2 import parameters


def catalog_and_state(part_setup):
    adapter,parts,ids,planes=part_setup
    adapter.sheet_profile_empty_state=lambda model:dict(sheet_folder_present=False,flat_folder_present=False)
    catalog=SheetProfileCatalog(parts.dimensions);item=definition(plane_object_id=planes[0])
    prepared=catalog.prepare_l_profile(ids[0],'Основная',**asdict(item))
    semantic=deepcopy(parts.dimensions._paired_capture(ids[0],'Основная').state[3])
    before=dict(semantic=semantic,creation_controls=prepared['creation_controls'],expected_geometry=prepared['expected_geometry'],
        plane_persistent_id_hex=prepared['plane_persistent_id_hex'],plane_transform=prepared['plane_transform'])
    after=dict(semantic=deepcopy(semantic),created=dict(complete=True,fully_defined=True,controls=prepared['creation_controls'],
        body_name=item.body_name,body_pid_hex='bb',sketch_native_id=26,base_native_id=49,
        volume_mm3=item.volume_mm3,surface_area_mm2=item.surface_area_mm2))
    snapshot,sketch_semantic=network();snapshot['reference_plane']['pid_hex']=prepared['plane_persistent_id_hex']
    after['created']['sketch']=snapshot;after['created']['base_parameters'],after['created']['sheet_parameters']=parameters()
    auxiliary=[];id_map=dict(sheet=37,flat=48,bend=55,flat_sketch_1=46,flat_sketch_2=47,ui_bend=57,
        fold_sketch_folder=56,cut_list=58,sheet_folder=33,flat_folder=44)
    def row(native_id,name,kind,suppressed=False):
        return dict(native_id=native_id,name=name,feature_type=kind,suppressed=suppressed,owner_native_id=None,error_code=0,is_warning=False)
    added=[row(26,item.sketch_name,'ProfileFeature'),row(49,item.feature_name,'SMBaseFlange')]
    for role,(name,kind,suppressed) in AUXILIARY_SCHEMA.items():
        record=row(id_map[role],name,kind,suppressed)
        auxiliary.append(dict(record,role=role,pid_hex='' if role=='fold_sketch_folder' else 'aa',
            reference_strategy='owned_absorption_v1' if role=='fold_sketch_folder' else 'owned_persistent_feature_v1'))
        if role not in ('sheet_folder','flat_folder'):added.append(record)
    after['created']['auxiliary']=auxiliary;after['semantic']['tree']['features'].extend(added)
    length=dict(name='Длина профиля',full_name='length@base',unit='mm',owner=dict(native_id=49,feature_type='SMBaseFlange'),
        driven_state=2,read_only=False,reference=False,linked=False,design_table=False,write_blockers=['owner_type_not_accepted'],
        values_si={'Основная':.03})
    after['semantic']['dimensions']=sketch_semantic['dimensions']+[length]
    after['semantic']['geometry']['bodies']=[read(folded_body())]
    return catalog,item,prepared,before,after


def test_preparation_binds_required_k_plane_and_complete_folded_boundary(part_setup):
    catalog,item,prepared,before,after=catalog_and_state(part_setup)
    assert prepared['revision_scope']=='empty_part_sheet_l_profile_v1'
    assert prepared['expected_geometry']['face_count']==14
    assert catalog._verify(before,after,item,'Основная')
    assert prepared['revision']!=catalog.prepare_l_profile(prepared['document_id'],'Основная',**asdict(definition(
        plane_object_id=item.plane_object_id,k_factor=.5)))['revision']


@pytest.mark.parametrize('fault',['k_default','base_radius','length_driver','length_owner','readonly_length','foreign_feature',
    'lost_baseline','aux_role','aux_name','aux_type','aux_suppression','aux_error','aux_reference','aux_baseline_collision',
    'body_reference','extra_body','wrong_geometry','volume','area','sketch_relation','controls','incomplete'])
def test_no_mass_or_correct_names_can_substitute_for_full_proof(part_setup,fault):
    catalog,item,_,before,after=catalog_and_state(part_setup);evidence=after['created'];semantic=after['semantic']
    if fault=='k_default':evidence['sheet_parameters']['k_factor']=.5
    elif fault=='base_radius':evidence['base_parameters']['BendRadius']=.003
    elif fault=='length_driver':semantic['dimensions'][-1]['values_si']['Основная']=.031
    elif fault=='length_owner':semantic['dimensions'][-1]['owner']['native_id']=999
    elif fault=='readonly_length':semantic['dimensions'][-1]['read_only']=True
    elif fault=='foreign_feature':semantic['tree']['features'].append(deepcopy(semantic['tree']['features'][-1]))
    elif fault=='lost_baseline':semantic['tree']['features'][0]['name']='Чужая замена'
    elif fault.startswith('aux_'):
        row=evidence['auxiliary'][0]
        if fault=='aux_role':row['role']='unproved'
        elif fault=='aux_name':row['name']='Другая операция'
        elif fault=='aux_type':row['feature_type']='Imported'
        elif fault=='aux_suppression':row['suppressed']=True
        elif fault=='aux_error':row['error_code']=1
        elif fault=='aux_reference':row['reference_strategy']='first_named_feature'
        else:row['native_id']=before['semantic']['tree']['features'][0]['native_id']
    elif fault=='body_reference':evidence['body_pid_hex']=''
    elif fault=='extra_body':semantic['geometry']['bodies'].append(deepcopy(semantic['geometry']['bodies'][0]))
    elif fault=='wrong_geometry':semantic['geometry']['bodies']=[read(folded_body(thickness=.003))]
    elif fault=='volume':evidence['volume_mm3']+=1.
    elif fault=='area':evidence['surface_area_mm2']+=1.
    elif fault=='sketch_relation':evidence['sketch']['relations'][0]['suppressed']=True
    elif fault=='controls':evidence['controls']=dict(evidence['controls'],auto_solve=False)
    else:evidence['complete']=False
    assert not catalog._verify(before,after,item,'Основная')


def test_existing_hidden_sheet_template_is_rejected_before_writing(part_setup):
    adapter,parts,ids,planes=part_setup
    adapter.sheet_profile_empty_state=lambda model:dict(sheet_folder_present=True,flat_folder_present=False)
    with pytest.raises(ExecutionFailure) as error:
        SheetProfileCatalog(parts.dimensions).prepare_l_profile(ids[0],'Основная',**asdict(definition(plane_object_id=planes[0])))
    assert error.value.code=='sheet_template_not_empty'
