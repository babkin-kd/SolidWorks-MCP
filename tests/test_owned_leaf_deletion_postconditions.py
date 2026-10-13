"""Finite fake snapshot proofs; no COM, native mutation or installed acceptance."""
from copy import deepcopy

import pytest

from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from solidworks_mcp.rectangle_extrusion_postconditions import verified_rectangle_extrusion
from test_rectangle_extrusion_postconditions import proof
from test_planar_brep_v2 import POINTS, make_body, snapshot
from solidworks_mcp.owned_leaf_deletion_postconditions import verified_owned_leaf_deletion


@pytest.fixture
def deletion(proof):
    after_sketch, before_base, original_definition = deepcopy(proof)
    neighbor = deepcopy(before_base['snapshots']['target'])
    for state in (before_base, after_sketch):
        state['snapshots']['neighbor'] = deepcopy(neighbor)
        for row in state['semantic']['documents']:
            row.update(title='Контрольная деталь',document_type='part',visible=True,dependencies=[],dependency_files=[],file=None,mode=dict(blocking_state=0,read_only_state=0,editing_sketch=False,editing_component=False,view_only=False,drawing_state=None))
            if row['document_id']=='neighbor':row['path']=''
        state['semantic']['files']=[]
        state['semantic']['application']=dict(user_control=True,visible=True,current_directory='C:/private/',search_folders='')
        for window in state['semantic']['windows']:window['title']='Контрольная деталь'
    after_sketch['semantic']['documents'][0].update(
        update_stamp=19, observation_sequence=6, observation_revision='actual_delete_after')
    return before_base, after_sketch, original_definition


def check(deletion, definition=None, native_id=5):
    before_base, after_sketch, current = deletion
    pid=next(row['token'] for row in before_base['snapshots']['target']['references'] if row['kind']=='feature' and row['role']=='feature:5')
    return verified_owned_leaf_deletion(before_base,after_sketch,document_id='target',configuration='Основная',object_id='feat_'+'a'*32,feature_native_id=native_id,feature_pid_hex=pid,current_definition=definition or current)


def current_depth(deletion, depth_mm):
    base, sketch, old = deletion
    snap = base['snapshots']['target']
    data = snap['clone_state']
    depth_m = depth_mm / 1000.
    data['dimensions'][2]['values_si']['Основная'] = depth_m
    data['parameters']['depth_m'] = depth_m
    data['extrusion']['directions'][0]['depth'] = depth_m.hex()
    body = make_body(points=[tuple(v*s for v,s in zip(p,(.04,.02,depth_m))) for p in POINTS])
    geometry = snapshot(body)
    data['geometry']['bodies'] = [geometry]
    snap['references'] = [row for row in snap['references'] if row['kind'] not in ('edge','face')]
    roles = [('edge', 'body:0/'+_json(sorted([geometry['vertices'][r['start']],geometry['vertices'][r['end']]])))
             for r in geometry['edges']]
    roles += [('face', 'body:0/'+_json(sorted({tuple(geometry['vertices'][c['start']])
              for loop in r['loops'] for c in loop['coedges']}))) for r in geometry['faces']]
    for index, (kind, role) in enumerate(roles):
        snap['references'].append(dict(kind=kind, role=role,
                                      token=('current-topology:'+str(index)).encode().hex()))
    return BlindRectangleExtrusion.validate(**{**vars(old),'depth_mm':depth_mm})


@pytest.mark.parametrize('depth_mm',[10.,12.])
@pytest.mark.parametrize('rename',[False,True])
def test_complete_inverse_delta_accepts_actual_current_depth_and_russian_names(deletion,depth_mm,rename):
    definition = current_depth(deletion,depth_mm)
    if rename:
        definition = BlindRectangleExtrusion.validate(**{**vars(definition),
            'feature_name':'Собственное выдавливание','body_name':'Тело опоры'})
        snap = deletion[0]['snapshots']['target']
        data = snap['clone_state']
        data['features'][5]['name'] = definition.feature_name
        data['dimensions'][2]['owner']['name'] = definition.feature_name
        data['body']['name'] = definition.body_name
        next(row for row in snap['native_observations']['qualified_dimensions']
             if row['role']=='dimension:depth')['full_name'] = 'Толщина@'+definition.feature_name+'@Контрольная деталь.Part'
    saved = deepcopy(deletion)
    result = check(deletion,definition)
    assert result is True
    assert deletion == saved  # No original receipt/state rewrite.


def test_original_creation_definition_cannot_mask_current_depth_edit(deletion):
    current = current_depth(deletion,12.)
    assert check(deletion,current) is True
    assert check(deletion) is False


@pytest.mark.parametrize('fault',[
    'foreign_feature_pid','foreign_sketch_pid','missing_sketch','missing_neighbor',
    'partial_neighbor','sketch_point','sketch_relation','sketch_dimension','sketch_name',
    'remaining_depth','remaining_body_ref','missing_width_ref','reference_graph',
    'target_view','selection','window','application','neighbor_material','neighbor_dirty',
    'external_reference','downstream','native_child_projection','target_saved','target_readonly',
    'target_hidden','after_not_dirty','after_boolean_stamp','after_empty_revision',
])
def test_changed_missing_foreign_or_incomplete_current_proofs_fail_closed(deletion,fault):
    base, sketch, _ = deletion
    after = sketch['snapshots']['target']
    data = after['clone_state']
    current = base['snapshots']['target']['clone_state']
    row = sketch['semantic']['documents'][0]
    if fault == 'foreign_feature_pid':
        next(r for r in after['references'] if (r['kind'],r['role'])==('feature','feature:0'))['token']='foreign'
    elif fault == 'foreign_sketch_pid':
        next(r for r in after['references'] if (r['kind'],r['role'])==('feature','feature:4'))['token']='foreign'
    elif fault == 'missing_sketch': data['features'].pop(4)
    elif fault == 'missing_neighbor': sketch['snapshots'].pop('neighbor')
    elif fault == 'partial_neighbor': sketch['snapshots']['neighbor']={'exact':'baseline'}
    elif fault == 'sketch_point': data['sketch']['points'][0]['coordinates_si'][0]=(.1).hex()
    elif fault == 'sketch_relation': data['sketch']['relations'][0]['suppressed']=True
    elif fault == 'sketch_dimension': data['dimensions'][0]['values_si']['Основная']=.05
    elif fault == 'sketch_name': data['features'][4]['name']='Подменённый эскиз'
    elif fault == 'remaining_depth': data['dimensions'].append(deepcopy(current['dimensions'][2]))
    elif fault == 'remaining_body_ref': after['references'].append(dict(kind='body',role='body:0',token='foreign'))
    elif fault == 'missing_width_ref': after['references']=[r for r in after['references'] if r['role']!='dimension:width']
    elif fault == 'reference_graph': sketch['semantic']['reference_graph'].append(['target','neighbor'])
    elif fault == 'target_view': row['view']['matrix'][0]=2
    elif fault == 'selection': row['selection'].append('foreign')
    elif fault == 'window': sketch['semantic']['windows'][0]['hwnd']=101
    elif fault == 'application': sketch['semantic']['application']['current_directory']='C:/foreign/'
    elif fault == 'neighbor_material': sketch['snapshots']['neighbor']['clone_state']['material']=['foreign','']
    elif fault == 'neighbor_dirty': sketch['semantic']['documents'][1]['needs_save']=False
    elif fault == 'external_reference': current['feature_external_reference_inventory']['total_reference_rows']=1
    elif fault == 'downstream': current['features'].append({**current['features'][5],'native_id':99})
    elif fault == 'native_child_projection':
        links=current['dependencies']
        for key in ('parent_links','child_links'): links[key].append([5,0])
        links['relations_read']+=2
    elif fault == 'target_saved':
        for state in (base,sketch): state['semantic']['documents'][0]['path']='Сохранённая.sldprt'
    elif fault == 'target_readonly': row['mode']['read_only_state']=1
    elif fault == 'target_hidden': row['visible']=False
    elif fault == 'after_not_dirty': row['needs_save']=False
    elif fault == 'after_boolean_stamp': row['update_stamp']=True
    elif fault == 'after_empty_revision': row['observation_revision']=''
    result = check(deletion)
    assert result is False


@pytest.mark.parametrize('native_id',[True,None,'5',4,99])
def test_getid_or_json_is_not_a_substitute_for_actual_held_native_role(deletion,native_id):
    assert check(deletion,native_id=native_id) is False


def test_reverse_oracle_alone_has_asymmetric_actual_after_dirty_validation(deletion):
    base, sketch, definition = deletion
    sketch['semantic']['documents'][0]['needs_save']=False
    assert verified_rectangle_extrusion(sketch,base,'target',definition,5) is True
    assert check(deletion) is False

