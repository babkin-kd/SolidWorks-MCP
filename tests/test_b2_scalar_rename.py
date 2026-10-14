"""Full fake native capture/BREP and actual production classifiers; no CAD."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from test_owned_leaf_deletion_postconditions import deletion, current_depth, proof

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:
    from verifier_b2_scalar_rename import verified_b2_depth_change, verified_b2_feature_rename
finally: sys.path.remove(str(scripts))


@pytest.fixture
def observations(deletion):
    base,sketch,definition=deletion
    # Original before/after are the actual complete CaptureAdapter fixture,
    # not a verifier-generated geometry or a mass-only boolean certificate.
    created=deepcopy(base)
    object_id='feat_'+'b'*32
    pid=next(row['token'] for row in created['snapshots']['target']['references']
             if row['kind']=='feature' and row['role']=='feature:5')
    job=dict(operation='part.extrude_rectangle',status='succeeded',error=None,mutation=dict(phase='committed'),
        result=dict(verified=True,before=dict(scope='closed_rectangle_blind_extrusion_v1',baseline=deepcopy(sketch),
            definition=vars(definition)),after=dict(state=created),value=dict(document_id='target',configuration='Основная',
            kind='extrusion',object_id=object_id,feature_object_id=object_id,created_native_id=5)))
    args=dict(document_id='target',configuration='Основная',object_id=object_id,feature_native_id=5,
              feature_pid_hex=pid,old_definition=definition,new_definition=definition)
    return deepcopy(base),deepcopy(base),job,args


def resize(observations):
    before,after,job,args=observations
    args['new_definition']=current_depth((after,None,args['old_definition']),12.)
    after['semantic']['documents'][0].update(update_stamp=20,observation_sequence=7,observation_revision='after_depth')


def rename(observations):
    before,after,job,args=observations
    args['new_definition']=BlindRectangleExtrusion.validate(**{**vars(args['old_definition']),
                                                            'feature_name':'Контрольное выдавливание'})
    data=after['snapshots']['target']['clone_state']
    data['features'][5]['name']=args['new_definition'].feature_name
    data['dimensions'][2]['owner']['name']=args['new_definition'].feature_name
    native=after['snapshots']['target']['native_observations']
    next(row for row in native['qualified_dimensions'] if row['role']=='dimension:depth')['full_name']=(
        'Толщина@'+args['new_definition'].feature_name+'@'+native['document_dimension_namespace']+'.Part')
    after['semantic']['documents'][0].update(update_stamp=21,observation_sequence=8,observation_revision='after_rename')


def check(observations,kind):
    before,after,job,args=observations
    predicate=verified_b2_depth_change if kind=='depth' else verified_b2_feature_rename
    return predicate(before,after,job,**args)


def test_n1_only_depth_10_to_12_proves_full_brep_8000_to_9600_without_mutating_observations(observations):
    resize(observations)
    preserved=deepcopy(observations)
    assert check(observations,'depth') is True
    assert observations==preserved
    before,after,_,_=observations
    assert before['snapshots']['target']['clone_state']['parameters']['depth_m']==.01
    assert after['snapshots']['target']['clone_state']['parameters']['depth_m']==.012
    assert len(after['snapshots']['target']['clone_state']['geometry']['bodies'][0]['faces'])==6


def test_n1_optional_actual_mm_values_follow_only_the_measured_depth_record(observations):
    before,after,job,_=observations
    before['snapshots']['target']['clone_state']['dimensions'][2]['values']={'Основная':10.}
    after['snapshots']['target']['clone_state']['dimensions'][2]['values']={'Основная':10.}
    job['result']['after']['state']['snapshots']['target']['clone_state']['dimensions'][2]['values']={'Основная':10.}
    resize(observations)
    after['snapshots']['target']['clone_state']['dimensions'][2]['values']['Основная']=12.
    assert check(observations,'depth') is True
    after['snapshots']['target']['clone_state']['dimensions'][2]['values']['Основная']=120.
    assert check(observations,'depth') is False


@pytest.mark.parametrize('kind',['depth','rename'])
def test_shared_unrecognized_native_fields_are_not_silently_stripped_or_filled(observations,kind):
    (resize if kind=='depth' else rename)(observations)
    for state in observations[:2]:
        state['snapshots']['target']['native_observations']['unproven_membership']='same opaque value'
    assert check(observations,kind) is False


@pytest.mark.parametrize('depth_mm',[10.,12.])
def test_n2_russian_name_only_preserves_depth_body_sketch_pid_refs_and_raw_native_data(observations,depth_mm):
    before,after,_,args=observations
    args['old_definition']=current_depth((before,None,args['old_definition']),depth_mm)
    current_depth((after,None,args['old_definition']),depth_mm)
    rename(observations)
    preserved=deepcopy(observations)
    assert check(observations,'rename') is True
    assert observations==preserved
    assert args['new_definition'].body_name==args['old_definition'].body_name


@pytest.mark.parametrize('kind',['depth','rename'])
@pytest.mark.parametrize('fault',['foreign_object','native_id','feature_pid','configuration','unknown_creation',
    'creation_profile','original_sketch','missing_neighbor','neighbor_material','view','application','selection',
    'feature_pid_changed','sketch_pid_changed','dimension_pid_changed','annotation_pid_changed',
    'new_native_field','native_field_changed','dimension_metadata','annotation','body_material','extra_clone_field',
    'other_feature','borrowed_sketch','units','properties','auxiliary','equation','body_name'])
def test_foreign_missing_or_changed_data_and_incarnations_fail_without_stripping_evidence(observations,kind,fault):
    (resize if kind=='depth' else rename)(observations)
    before,after,job,args=observations
    snapshot=after['snapshots']['target']
    data=snapshot['clone_state']
    if fault=='foreign_object': args['object_id']='feat_'+'f'*32
    elif fault=='native_id': args['feature_native_id']=99
    elif fault=='feature_pid': args['feature_pid_hex']='ff'
    elif fault=='configuration': args['configuration']='Чужая'
    elif fault=='unknown_creation': job['status']='unknown'
    elif fault=='creation_profile': job['result']['after']['state']['snapshots']['target']['clone_state']['geometry']['bodies']=[]
    elif fault=='original_sketch': job['result']['before']['baseline']['snapshots']['target']['clone_state']['sketch']['points'][0]['coordinates_si'][0]=(.1).hex()
    elif fault=='missing_neighbor': after['snapshots'].pop('neighbor')
    elif fault=='neighbor_material': after['snapshots']['neighbor']['clone_state']['material']=['foreign','']
    elif fault=='view': after['semantic']['documents'][0]['view']['matrix'][0]=2
    elif fault=='application': after['semantic']['application']['current_directory']='C:/foreign/'
    elif fault=='selection': snapshot['selection_count']=1
    elif fault in ('feature_pid_changed','sketch_pid_changed','dimension_pid_changed','annotation_pid_changed'):
        target={'feature_pid_changed':('feature','feature:5'),'sketch_pid_changed':('feature','feature:4'),
                'dimension_pid_changed':('dimension','dimension:depth'),
                'annotation_pid_changed':('annotation',data['annotations'][-1]['role'])}[fault]
        next(row for row in snapshot['references'] if (row['kind'],row['role'])==target)['token']='foreign'
    elif fault=='new_native_field': snapshot['native_observations']['unobserved_field']=True
    elif fault=='native_field_changed': snapshot['native_observations']['unavailable_extrusion_auto_select']=not snapshot['native_observations']['unavailable_extrusion_auto_select']
    elif fault=='dimension_metadata': data['dimensions'][2]['read_only']=True
    elif fault=='annotation': data['annotations'][-1]['text']='Unproven measured annotation change'
    elif fault=='body_material': data['body_material']=['foreign','']
    elif fault=='extra_clone_field': data['unobserved']=True
    elif fault=='other_feature': data['features'][0]['name']='Чужая плоскость'
    elif fault=='borrowed_sketch': data['sketch']['relations'][0]['suppressed']=True
    elif fault=='units': data['units'][0]+=1
    elif fault=='properties': data['properties'][''][0]['value']='foreign'
    elif fault=='auxiliary': data['auxiliary_data']['attachments']=1
    elif fault=='equation': data['equation_reference_inventory']['equations']['enumerated_count']=1
    else: data['body']['name']='Чужое тело'
    assert check(observations,kind) is False


@pytest.mark.parametrize('fault',['mass_only','old_brep','false_brep','wrong_depth','changed_names','back_depth',
    'changed_width','annotation_position','missing_si','unit','unexpected_values'])
def test_n1_parameter_or_mass_assertion_cannot_replace_exact_depth_geometry_and_metadata_delta(observations,fault):
    resize(observations)
    before,after,_,args=observations
    data=after['snapshots']['target']['clone_state']
    if fault=='mass_only': data['geometry']={'volume_mm3':9600.}
    elif fault=='old_brep': data['geometry']=deepcopy(before['snapshots']['target']['clone_state']['geometry'])
    elif fault=='false_brep': data['geometry']['bodies'][0]['faces'][0]['normal_opposes_surface']=not data['geometry']['bodies'][0]['faces'][0]['normal_opposes_surface']
    elif fault=='wrong_depth': args['new_definition']=BlindRectangleExtrusion.validate(**{**vars(args['new_definition']),'depth_mm':11.})
    elif fault=='changed_names': data['features'][5]['name']='Другое основание'
    elif fault=='back_depth': data['extrusion']['directions'][1]['depth']=(.012).hex()
    elif fault=='changed_width': data['parameters']['width_m']=.05
    elif fault=='annotation_position': data['annotations'][-1]['position'][0]=(.1).hex()
    elif fault=='missing_si': data['dimensions'][2].pop('values_si')
    elif fault=='unit': data['dimensions'][2]['unit']='m'
    else: data['dimensions'][2]['values']={'Основная':120.}
    assert check(observations,'depth') is False


@pytest.mark.parametrize('fault',['unrequested_name','english','unchanged_name','depth_changed','body_changed',
    'geometry_token','geometry','dimension_name','qualified_width','qualified_namespace','qualified_depth',
    'annotation_position'])
def test_n2_only_requested_russian_feature_and_qualified_depth_owner_name_delta_is_admitted(observations,fault):
    rename(observations)
    _,after,_,args=observations
    data=after['snapshots']['target']['clone_state']
    native=after['snapshots']['target']['native_observations']
    if fault=='unrequested_name': data['features'][5]['name']='Другое основание'
    elif fault=='english': args['new_definition']=BlindRectangleExtrusion(args['old_definition'].sketch_object_id,10.,'English','Тело основания')
    elif fault=='unchanged_name': args['new_definition']=args['old_definition']
    elif fault=='depth_changed': args['new_definition']=BlindRectangleExtrusion.validate(**{**vars(args['new_definition']),'depth_mm':12.})
    elif fault=='body_changed': data['body']['name']='Тело с другим именем'
    elif fault=='geometry_token': next(row for row in after['snapshots']['target']['references'] if row['kind']=='edge')['token']='foreign'
    elif fault=='geometry': data['geometry']['bodies'][0]['vertices'][0][0]=(.1).hex()
    elif fault=='dimension_name': data['dimensions'][2]['name']='D1'
    elif fault=='qualified_width': native['qualified_dimensions'][0]['full_name']='foreign'
    elif fault=='qualified_namespace': native['document_dimension_namespace']='Чужая деталь'
    elif fault=='qualified_depth': next(row for row in native['qualified_dimensions'] if row['role']=='dimension:depth')['full_name']='Толщина@Основание@Контрольная деталь.Part'
    else: data['annotations'][-1]['position'][0]=(.1).hex()
    assert check(observations,'rename') is False
