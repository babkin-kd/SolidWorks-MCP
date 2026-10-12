"""Full artificial capture and real classifier; no installed/native CAD claim."""
from copy import deepcopy

import pytest

from solidworks_mcp import binding
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from solidworks_mcp.rectangle_extrusion_postconditions import verified_rectangle_extrusion
from solidworks_mcp.rectangle_snapshot import SCOPE, SKETCH, validated_rectangle_snapshot
from solidworks_mcp.sketches import rectangle_profile_parameters
from test_native_first_save_full_capture import CaptureAdapter
from test_planar_brep_v2 import POINTS, make_body, snapshot


def dependencies(features, *, extruded):
    positions = {row['native_id']:i for i,row in enumerate(features)}
    links = [[positions[0],positions[4]]]
    if extruded: links.append([positions[4],positions[5]])
    absorbed = [[positions[owner],i] for i,row in enumerate(features)
                if (owner := row['owner_native_id']) is not None]
    return dict(scope='native_feature_relation_capture_v1', feature_count=len(features),
        parent_links=links, child_links=deepcopy(links), absorbed_links=absorbed,
        parent_links_without_child_confirmation=[], child_links_without_parent_confirmation=[],
        relations_read=2*len(links)+len(absorbed))


def external(features):
    return dict(scope='native_feature_external_references_v1', feature_count=len(features),
        total_reference_rows=0, features=[dict(native_id=r['native_id'],count=0,rows=[]) for r in features])


@pytest.fixture
def proof(monkeypatch):
    monkeypatch.setattr(binding, 'wrap', lambda raw, interface: raw)
    monkeypatch.setattr(binding, 'queried', lambda raw, interface: raw)
    native = CaptureAdapter()
    for index, (dimension, name) in enumerate(zip(native.dimension_rows, ('Ширина','Высота','Толщина'))):
        row = dimension.summary
        row['full_name'] = name+'@'+row['owner']['name']+'@Контрольная деталь.Part'
        row['name'] = name
        if index < 2: native.sketch.dimensions[index].FullName = row['full_name']
    body = make_body(points=[tuple(v*s for v,s in zip(p,(.04,.02,.01))) for p in POINTS])
    native.geometry = dict(representation='planar_polyhedral_brep_v1', bodies=[snapshot(body)])
    native.edges, native.faces = body.edges, body.faces
    for index, obj in enumerate([*body.edges, *body.faces]): native.register(obj, 'full-topology:'+str(index))
    native.feature_dependencies = lambda features: dependencies([f.row for f in features],extruded=True)
    native.feature_external_references = lambda features: external([f.row for f in features])
    new = native.first_save_part_snapshot(native.model)
    new['scope'] = SCOPE
    new['clone_state']['creation_controls'] = dict(add_to_db=False,auto_solve=True,display_when_added=True,dimension_input=False)
    old = deepcopy(new)
    a = old['clone_state']
    a['profile'] = SKETCH
    a['features'] = [r for r in a['features'] if r['native_id'] != 5]
    a['features'][4]['owner_native_id'] = None
    roles = {'feature:'+str(i):'feature:'+str(i-1) for i in range(6,16)}
    for key in ('feature_pid_hex',):
        role = a['sketch'][key]['reference_role']
        a['sketch'][key]['reference_role'] = roles.get(role,role)
    for key in ('reference_plane','model_origin'):
        role = a['sketch'][key]['pid_hex']['reference_role']
        a['sketch'][key]['pid_hex']['reference_role'] = roles.get(role,role)
    names = {r['role']:r['full_name'] for r in new['native_observations']['qualified_dimensions']}
    a['dimensions'] = a['dimensions'][:2]
    for row in a['dimensions']:
        row['full_name'] = names[row['full_name']['reference_role']]
        row['owner']['owner_native_id'] = None
        row['owner_update_stamp'] = 17
    for relation in a['sketch']['relations']:
        if relation['dimension_full_name'] is not None:
            relation['dimension_full_name'] = names[relation['dimension_full_name']['reference_role']]
    a['geometry'] = dict(representation='planar_polyhedral_brep_v1',bodies=[])
    a['parameters'] = rectangle_profile_parameters(a['sketch'],dict(dimensions=a['dimensions'],context=a['controls'],geometry=a['geometry']), 'Основная',require_editable=False)
    for key in ('extrusion','body','body_material'): a.pop(key)
    a['origin'] = dict(feature_role='feature:3',point_role='sketch:0/model_origin', **a['sketch']['model_origin_point'])
    a['annotations'] = a['annotations'][:2]
    a['dependencies'] = dependencies(a['features'],extruded=False)
    a['feature_external_reference_inventory'] = external(a['features'])
    for plane in a['planes']: plane['role'] = roles.get(plane['role'],plane['role'])
    old['solid_body_count'] = 0
    old['native_observations'] = {'document_dimension_namespace':'Контрольная деталь'}
    old['references'] = [r for r in old['references'] if r['kind'] not in ('body','edge','face')
        and (r['kind'],r['role']) not in {('feature','feature:5'),('dimension','dimension:depth'),('annotation','annotation:Размер 3')}]
    for row in old['references']:
        if row['kind'] == 'feature': row['role'] = roles.get(row['role'],row['role'])
    validated_rectangle_snapshot(old)
    validated_rectangle_snapshot(new)
    doc = dict(document_id='target',title='Контрольная деталь',active_configuration='Основная',
        configurations=['Основная'],needs_save=True,update_stamp=17,observation_sequence=4,observation_revision='before',
        path='', file=None, view={'matrix':[1,0,0]},selection=[])
    neighbor = {**deepcopy(doc),'document_id':'neighbor','title':'Сосед','file':{'hash':'baseline'}}
    semantic = dict(documents=[doc,neighbor],files={'neighbor':'original bytes'},
        windows=[{'document_id':'target','hwnd':100}],application={'busy':False,'cwd':'baseline'},
        active_document_id='target',reference_graph=[])
    before = dict(semantic=semantic,snapshots={'target':old,'neighbor':{'exact':'baseline'}})
    after = deepcopy(before)
    after['snapshots']['target'] = new
    after['semantic']['documents'][0].update(update_stamp=18,observation_sequence=5,observation_revision='after')
    definition = BlindRectangleExtrusion.validate(sketch_object_id='feat_'+'a'*32,depth_mm=10.)
    return before, after, definition


def test_real_full_capture_classifier_admits_exact_new_blind_base(proof):
    before,after,definition = proof
    assert verified_rectangle_extrusion(before,after,'target',definition,5)
    assert 'origin' not in after['snapshots']['target']['clone_state']
    assert all('owner_update_stamp' not in d for d in after['snapshots']['target']['clone_state']['dimensions'])


@pytest.mark.parametrize('fault', ['neighbor_snapshot','neighbor_dirty','files','window','cwd','active',
    'target_path','target_view','target_selection','target_extra','target_observation_type','config',
    'baseline_feature','sketch_name','extrusion_name','body_name','depth_name','sketch_owner','dimension_owner',
    'width_value','relation','point','point_native_id','sketch_opaque_id','origin_id','plane_transform',
    'feature_pid','point_pid','line_pid','dimension_pid','origin_pid','extra_reference','missing_face_pid',
    'qualified_name','qualified_role','unbound_axes','parameter_only','depth_value','unexpected_field',
    'dependency','dependency_baseline','external_reference','annotation','removed_annotation','creation_control',
    'body_material','body_count','extra_body','vertex','edge','edge_line','edge_trim','face','face_plane',
    'partner','face_sense','missing_full_brep','geometry_nonfinite','thin','draft','reverse','two_directions',
    'from_offset','merge','back_depth','wall_thickness','extra_feature','created_id'])
def test_hostile_changed_partial_foreign_and_false_geometry_proofs_fail_closed(proof,fault):
    before,after,definition = proof
    old = before['snapshots']['target']['clone_state']
    snap = after['snapshots']['target']; data = snap['clone_state']; body = data['geometry']['bodies'][0]
    target = after['semantic']['documents'][0]
    created = 5
    if fault == 'neighbor_snapshot': after['snapshots']['neighbor']['exact']='changed'
    elif fault == 'neighbor_dirty': after['semantic']['documents'][1]['needs_save']=False
    elif fault == 'files': after['semantic']['files']['neighbor']='changed bytes'
    elif fault == 'window': after['semantic']['windows'][0]['hwnd']=101
    elif fault == 'cwd': after['semantic']['application']['cwd']='foreign'
    elif fault == 'active': after['semantic']['active_document_id']='neighbor'
    elif fault == 'target_path': target['path']='foreign.sldprt'
    elif fault == 'target_view': target['view']['matrix'][0]=2
    elif fault == 'target_selection': target['selection'].append('foreign')
    elif fault == 'target_extra': target['hidden_effect']=True
    elif fault == 'target_observation_type': target['observation_sequence']=True
    elif fault == 'config': snap['configuration']='Другая'
    elif fault == 'baseline_feature': data['features'][0]['name']='Чужая плоскость'
    elif fault == 'sketch_name': data['features'][4]['name']='Чужой эскиз'
    elif fault == 'extrusion_name': data['features'][5]['name']='Чужое основание'
    elif fault == 'body_name': data['body']['name']='Чужое тело'
    elif fault == 'depth_name': data['dimensions'][2]['name']='D1'
    elif fault == 'sketch_owner': data['features'][4]['owner_native_id']=99
    elif fault == 'dimension_owner': data['dimensions'][0]['owner']['owner_native_id']=99
    elif fault == 'width_value': data['dimensions'][0]['values_si']['Основная']=.05
    elif fault == 'relation': data['sketch']['relations'][0]['suppressed']=True
    elif fault == 'point': data['sketch']['points'][0]['coordinates_si'][0]=(.1).hex()
    elif fault == 'point_native_id': data['sketch']['points'][0]['native_id'][0]+=1
    elif fault == 'sketch_opaque_id': data['sketch']['opaque_identity']='foreign'
    elif fault == 'origin_id': data['sketch']['model_origin_point']['native_id'][0]+=1
    elif fault == 'plane_transform': data['sketch']['reference_plane']['transform'][0]=(0.).hex()
    elif fault in ('feature_pid','point_pid','line_pid','dimension_pid','origin_pid'):
        kind,role = {'feature_pid':('feature','feature:4'),'point_pid':('sketch_point','sketch:0/'+old['sketch']['points'][0]['key']),
            'line_pid':('sketch_segment','sketch:0/'+old['sketch']['segments'][0]['key']),
            'dimension_pid':('dimension','dimension:width'),'origin_pid':('sketch_point','sketch:0/model_origin')}[fault]
        next(r for r in snap['references'] if (r['kind'],r['role'])==(kind,role))['token']='foreign-token'
    elif fault == 'extra_reference': snap['references'].append(dict(kind='body',role='body:foreign',token='foreign'))
    elif fault == 'missing_face_pid': snap['references']=[r for r in snap['references'] if r['kind']!='face']
    elif fault == 'qualified_name': snap['native_observations']['qualified_dimensions'][0]['full_name']='foreign'
    elif fault == 'qualified_role': next(r for r in snap['native_observations']['qualified_dimensions'] if r['role']=='dimension:width')['owner_role']='feature:5'
    elif fault == 'unbound_axes': data['parameters']['axes']['width']={'reference_role':'dimension:depth'}
    elif fault == 'parameter_only': data['parameters']['width_m']=.05
    elif fault == 'depth_value': data['dimensions'][2]['values_si']['Основная']=.02
    elif fault == 'unexpected_field': data['controls']['unexpected']='effect'
    elif fault == 'dependency': data['dependencies']['parent_links'].append([0,5])
    elif fault == 'dependency_baseline': data['dependencies']['child_links'][0]=[1,4]
    elif fault == 'external_reference': data['feature_external_reference_inventory']['features'][0]['rows'].append({'file':'foreign'})
    elif fault == 'annotation': data['annotations'][0]['text']='changed'
    elif fault == 'removed_annotation': data['annotations'].pop(0)
    elif fault == 'creation_control': data['creation_controls']['add_to_db']=True
    elif fault == 'body_material': data['body_material']=None
    elif fault == 'body_count': snap['solid_body_count']=True
    elif fault == 'extra_body': data['geometry']['bodies'].append(deepcopy(body))
    elif fault == 'vertex': body['vertices'][0][0]=(.02).hex()
    elif fault == 'edge': body['edges'][0]['end']=body['edges'][0]['start']
    elif fault == 'edge_line': body['edges'][0]['line_parameters'][0]=(.3).hex()
    elif fault == 'edge_trim': body['edges'][0]['trimmed_curve']['u_max']=body['edges'][0]['trimmed_curve']['u_min']
    elif fault == 'face': body['faces'][0]['loops'][0]['coedges'][0]['end']=7
    elif fault == 'face_plane': body['faces'][0]['plane_parameters'][3]=(.3).hex()
    elif fault == 'partner': body['faces'][0]['loops'][0]['coedges'][0]['partner']=[0,0,0]
    elif fault == 'face_sense': body['faces'][0]['normal_opposes_surface']=not body['faces'][0]['normal_opposes_surface']
    elif fault == 'missing_full_brep': body.pop('vertex_tolerances')
    elif fault == 'geometry_nonfinite': body['vertices'][0][0]='nan'
    elif fault == 'thin': data['extrusion']['thin_feature']=True
    elif fault == 'draft': data['extrusion']['directions'][0]['draft_enabled']=True
    elif fault == 'reverse': data['extrusion']['ReverseDirection']=True
    elif fault == 'two_directions': data['extrusion']['BothDirections']=True
    elif fault == 'from_offset': data['extrusion']['FromOffsetDistance']=(.02).hex()
    elif fault == 'merge': data['extrusion']['Merge']=False
    elif fault == 'back_depth': data['extrusion']['directions'][1]['depth']=(.01).hex()
    elif fault == 'wall_thickness': data['extrusion']['directions'][0]['wall_thickness']=(.01).hex()
    elif fault == 'extra_feature': data['features'].append({**data['features'][5],'native_id':99})
    elif fault == 'created_id': created=4
    assert not verified_rectangle_extrusion(before,after,'target',definition,created)


def test_snapshot_and_receipt_evidence_are_not_mutated(proof):
    before,after,definition = proof
    original=deepcopy((before,after,definition))
    assert verified_rectangle_extrusion(before,after,'target',definition,5)
    assert (before,after,definition)==original


@pytest.mark.parametrize('created',[True,None,'5',4,99])
def test_only_exact_new_integer_native_incarnation_is_admitted(proof,created):
    before,after,definition=proof
    assert not verified_rectangle_extrusion(before,after,'target',definition,created)


def test_partial_session_never_admitted(proof):
    before,after,definition=proof
    after.pop('snapshots')
    assert not verified_rectangle_extrusion(before,after,'target',definition,5)


@pytest.mark.parametrize('place',['sketch','point','dimension','feature','controls'])
def test_opaque_baseline_fields_survive_exactly_and_are_never_stripped(proof,place):
    before,after,definition=proof
    a=before['snapshots']['target']['clone_state']
    b=after['snapshots']['target']['clone_state']
    first,last = {'sketch':(a['sketch'],b['sketch']),
        'point':(a['sketch']['points'][0],b['sketch']['points'][0]),
        'dimension':(a['dimensions'][0],b['dimensions'][0]),
        'feature':(a['features'][0],b['features'][0]),
        'controls':(a['controls'],b['controls'])}[place]
    first['opaque_identity']={'strategy':'exact','token':'baseline-token'}
    last['opaque_identity']=deepcopy(first['opaque_identity'])
    assert verified_rectangle_extrusion(before,after,'target',definition,5)
    last['opaque_identity']['token']='foreign-token'
    assert not verified_rectangle_extrusion(before,after,'target',definition,5)
    last.pop('opaque_identity')
    assert not verified_rectangle_extrusion(before,after,'target',definition,5)


def test_baseline_reference_table_cannot_claim_an_unobserved_old_body(proof):
    before,after,definition=proof
    row=dict(kind='body',role='body:foreign',token='foreign-token')
    before['snapshots']['target']['references'].append(deepcopy(row))
    after['snapshots']['target']['references'].append(row)
    assert not verified_rectangle_extrusion(before,after,'target',definition,5)


@pytest.mark.parametrize('field',['body','extrusion','annotation'])
def test_new_metadata_is_complete_and_within_declared_finite_scope(proof,field):
    before,after,definition=proof
    data=after['snapshots']['target']['clone_state']
    row={'body':data['body'],'extrusion':data['extrusion'],'annotation':data['annotations'][-1]}[field]
    row['unknown_field']='unobserved semantics'
    assert not verified_rectangle_extrusion(before,after,'target',definition,5)


def test_custom_requested_russian_feature_and_body_names_require_exact_readback(proof):
    before,after,_=proof
    definition=BlindRectangleExtrusion.validate(sketch_object_id='feat_'+'a'*32,depth_mm=10.,
        feature_name='Базовое выдавливание',body_name='Основное тело')
    data=after['snapshots']['target']['clone_state']
    data['features'][5]['name']=definition.feature_name
    data['dimensions'][2]['owner']['name']=definition.feature_name
    data['body']['name']=definition.body_name
    qualification=next(r for r in after['snapshots']['target']['native_observations']['qualified_dimensions']
                       if r['role']=='dimension:depth')
    qualification['full_name']='Толщина@'+definition.feature_name+'@Контрольная деталь.Part'
    assert verified_rectangle_extrusion(before,after,'target',definition,5)
    data['body']['name']='Тело основания'
    assert not verified_rectangle_extrusion(before,after,'target',definition,5)
