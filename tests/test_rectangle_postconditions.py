"""Independent sketch admission with real rectangle classifier and fake SDK."""
from copy import deepcopy

import pytest

from solidworks_mcp import binding
from solidworks_mcp.rectangle_construction import RectangleSketch
from solidworks_mcp.rectangle_postconditions import verified_rectangle_sketch
from solidworks_mcp.rectangle_snapshot import SKETCH
from solidworks_mcp.sketches import rectangle_profile_parameters
from test_rectangle_snapshot import adapter as empty_adapter
from test_native_first_save_full_capture import CaptureAdapter


@pytest.fixture
def proof(empty_adapter, monkeypatch):
    a = empty_adapter
    monkeypatch.setattr(binding, 'queried', lambda raw, interface: raw)
    native = CaptureAdapter()
    sketch_feature = native.feature_rows[4]
    raw, _ = native.sketch_snapshot(native.model, sketch_feature)
    a.point.GetID = lambda: tuple(raw['model_origin_point']['native_id'])
    old = a.rectangle_construction_snapshot(a.model)
    new = deepcopy(old)
    data = new['clone_state']
    data['profile'] = SKETCH
    data['features'].append(dict(native_id=4, feature_type='ProfileFeature', name='Эскиз основания',
                                suppressed=False, error_code=0, owner_native_id=None))
    raw['feature_native_id'] = 4
    data['sketch'] = raw
    dimensions = [native.dimension_summary(d, ['Основная']) for d in native.dimensions(native.model, native.feature_rows)[:2]]
    renames = {}
    for d, name in zip(dimensions, ['Ширина', 'Высота']):
        old_name = d['full_name']
        d['full_name'] = old_name.replace(d['name']+'@', name+'@', 1)
        d['name'] = name
        renames[old_name] = d['full_name']
        d['owner']['owner_native_id'] = None
    for relation in raw['relations']:
        if relation['dimension_full_name'] in renames:
            relation['dimension_full_name'] = renames[relation['dimension_full_name']]
    data['dimensions'] = dimensions
    data['parameters'] = rectangle_profile_parameters(raw, dict(dimensions=dimensions,
        context=data['controls'], geometry=data['geometry']), 'Основная', require_editable=False)
    data['origin']['point_role'] = 'sketch:0/model_origin'
    for row in new['references']:
        if row['role'] == 'origin:point': row['role'] = 'sketch:0/model_origin'
    new['references'].append(dict(kind='feature', role='feature:4', token='abc123'))
    for index, p in enumerate(raw['points']):
        new['references'].append(dict(kind='sketch_point', role='sketch:0/'+p['key'], token='point-'+str(index)))
    for index, s in enumerate(raw['segments']):
        new['references'].append(dict(kind='sketch_segment', role='sketch:0/'+s['key'], token='line-'+str(index)))
    for axis in ['width', 'height']:
        new['references'].append(dict(kind='dimension', role='dimension:'+axis, token='dim-'+axis))
    doc = dict(document_id='target', title='Контрольная деталь', configurations=['Основная'],
        needs_save=True, update_stamp=1, observation_sequence=1, observation_revision='rev_before')
    neighbor = {**doc, 'document_id': 'neighbor', 'title': 'Сосед'}
    semantic = dict(documents=[doc, neighbor], files={'owned': 'bytes'}, windows=[{'document_id':'target'}],
        application={'busy': False}, active_document_id='target', reference_graph=[])
    before = dict(semantic=semantic, snapshots={'target': old, 'neighbor': {'untouched': True}})
    after = deepcopy(before)
    after['snapshots']['target'] = new
    after['semantic']['documents'][0].update(update_stamp=2, observation_sequence=2, observation_revision='rev_after')
    definition = RectangleSketch.validate(plane_object_id='feat_'+'a'*32, width_mm=40., height_mm=20.)
    return before, after, definition


def test_real_classifier_admits_one_exact_rectangle_and_unchanged_supported_baseline(proof):
    before, after, definition = proof
    assert verified_rectangle_sketch(before, after, 'target', definition, 4)


@pytest.mark.parametrize('fault', ['neighbor_data', 'neighbor_dirty', 'file', 'view', 'window',
    'config', 'origin_anchor', 'plane_anchor', 'baseline_name', 'sketch_name',
    'wrong_created_id', 'geometry', 'parameters_only', 'extra_feature', 'unexpected_data', 'missing_entity_anchor'])
def test_changes_outside_the_owned_rectangle_or_false_geometry_are_unverified(proof, fault):
    before, after, definition = proof
    d = after['snapshots']['target']['clone_state']
    created_id = 4
    if fault == 'neighbor_data': after['snapshots']['neighbor']['untouched'] = False
    elif fault == 'neighbor_dirty': after['semantic']['documents'][1]['needs_save'] = False
    elif fault == 'file': after['semantic']['files']['owned'] = 'changed bytes'
    elif fault == 'view': after['semantic']['application']['busy'] = True
    elif fault == 'window': after['semantic']['windows'].append({'document_id':'target'})
    elif fault == 'config': after['semantic']['documents'][0]['configurations'] = ['Другая']
    elif fault == 'origin_anchor':
        next(r for r in after['snapshots']['target']['references'] if r['role']=='sketch:0/model_origin')['token']='foreign-origin'
    elif fault == 'plane_anchor': after['snapshots']['target']['references'][0]['token']='foreign-plane'
    elif fault == 'baseline_name': d['features'][0]['name']='Переименовано'
    elif fault == 'sketch_name': d['features'][-1]['name']='Чужое имя'
    elif fault == 'wrong_created_id': created_id = 0
    elif fault == 'geometry': d['sketch']['points'][0]['coordinates_si'][0] = float(.5).hex()
    elif fault == 'parameters_only': d['parameters']['width_m'] = .05
    elif fault == 'extra_feature': d['features'].append({**d['features'][-1], 'native_id':99})
    elif fault == 'missing_entity_anchor':
        after['snapshots']['target']['references'] = [r for r in after['snapshots']['target']['references'] if r['role']!='dimension:width']
    else: d['controls']['unexpected'] = 'changed'
    assert not verified_rectangle_sketch(before, after, 'target', definition, created_id)


def test_partial_and_nonfinite_proof_never_admit_success(proof):
    before, after, definition = proof
    after['snapshots']['target']['clone_state']['units'].append(float('nan'))
    assert not verified_rectangle_sketch(before, after, 'target', definition, 4)
    after.pop('snapshots')
    assert not verified_rectangle_sketch(before, after, 'target', definition, 4)
