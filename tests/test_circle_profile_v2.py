"""Artificial independent circle constraint networks, not CAD acceptance."""

from copy import deepcopy

import pytest

from solidworks_mcp.circular_sketch import circle_profile_parameters
from solidworks_mcp.jobs import ExecutionFailure
from test_circular_sketch_v2 import CircleSketch,capture
from test_dimension_domain_v2 import Adapter,dimension


def state():
    sketch = CircleSketch()
    snapshot = capture(sketch)[0]
    snapshot['feature_native_id']=10
    rows=[]
    for i,value in enumerate((.01,.01,.006)):
        row=dimension(i,value=value).state
        row.update(full_name=sketch.dimensions[i].FullName,
            owner={'native_id':10,'feature_type':'ProfileFeature'},
            write_blockers=['sketch_geometry_snapshot_not_implemented'],values_si={'Основная':value})
        rows.append(row)
    semantic={'dimensions':rows,'context':deepcopy(Adapter().context),
        'tree':{'needs_rebuild':False,'features':[{'error_code':0}]}}
    return snapshot,semantic


def classify(snapshot,semantic):
    return circle_profile_parameters(snapshot,semantic,'Основная')


def test_three_independent_native_drivers_are_identified_by_entities_and_orientation():
    snapshot,semantic=state()
    original=deepcopy(semantic)
    result=classify(snapshot,semantic)
    assert result['centre_x_m']==result['centre_y_m']==.01
    assert result['radius_m']==.003 and result['diameter_m']==.006
    assert result['axes']=={'centre_x':'Центр X@Эскиз отверстия',
        'centre_y':'Центр Y@Эскиз отверстия','diameter':'Диаметр@Эскиз отверстия'}
    assert semantic==original
    snapshot['relations'].reverse()
    assert classify(snapshot,semantic)==result


def test_display_names_do_not_prove_or_change_driver_roles():
    snapshot,semantic=state()
    for index,row in enumerate(semantic['dimensions']):
        old=row['full_name']
        row['full_name']='Произвольное имя '+str(index)
        next(r for r in snapshot['relations'] if r['dimension_full_name']==old)['dimension_full_name']=row['full_name']
    result=classify(snapshot,semantic)
    assert result['axes']['diameter']=='Произвольное имя 2'


@pytest.mark.parametrize('fault',[
    'linear_scope','3d','underdefined','wrong_origin_type','origin_free','wrong_origin_coordinate',
    'free_centre','extra_regular','missing_projected','wrong_projection_type','wrong_projection_coordinate',
    'signed_x','signed_y','nonplanar_centre','extra_circle','construction','free_circle','centre_alias',
    'seam','too_small_radius','wrong_curve_radius','wrong_curve_centre','wrong_curve_axis','wrong_normal',
    'missing_dimension','extra_dimension','foreign_owner','dimension_alias','suppressed','extra_relation',
    'wrong_relation_type','wrong_display_type','duplicate_axis','wrong_xy_entities','wrong_xy_definitions',
    'wrong_diameter_entities','wrong_diameter_definitions','wrong_x_value','wrong_diameter_value',
    'driven','reference','linked','design_table_dimension','other_blocker','read_only','editing_sketch',
    'external','equations','needs_rebuild','feature_error','inactive','incomplete_config',
])
def test_free_signed_foreign_dependent_or_incomplete_network_is_rejected(fault):
    snapshot,semantic=state()
    circle=snapshot['segments'][0]
    centre=next(point for point in snapshot['points'] if not point['implicit'])
    projected=next(point for point in snapshot['points'] if point['implicit'])
    x=next(row for row in snapshot['relations'] if row['display_type']==11)
    diameter=next(row for row in snapshot['relations'] if row['display_type']==6)
    if fault=='linear_scope': snapshot['scope']='linear_planar_sketch_geometry_v1'
    if fault=='3d': snapshot['is_3d']=True
    if fault=='underdefined': snapshot['constraint_status']=2
    if fault=='wrong_origin_type': snapshot['model_origin_point']['point_type']=0
    if fault=='origin_free': snapshot['model_origin_point']['constraint_status']=0
    if fault=='wrong_origin_coordinate': snapshot['model_origin_point']['coordinates_si'][0]=(.1).hex()
    if fault=='free_centre': centre['constraint_status']=0
    if fault=='extra_regular':
        new=deepcopy(centre);new['key']='point:99:100';snapshot['points'].append(new)
    if fault=='missing_projected': snapshot['points'].remove(projected)
    if fault=='wrong_projection_type': projected['point_type']=0
    if fault=='wrong_projection_coordinate': projected['coordinates_si'][0]=(.1).hex()
    if fault=='signed_x': centre['coordinates_si'][0]=(-.01).hex()
    if fault=='signed_y': centre['coordinates_si'][1]=(-.01).hex()
    if fault=='nonplanar_centre': centre['coordinates_si'][2]=(.001).hex()
    if fault=='extra_circle': snapshot['segments'].append(deepcopy(circle))
    if fault=='construction': circle['construction']=True
    if fault=='free_circle': circle['constraint_status']=0
    if fault=='centre_alias': circle['centre']=projected['key']
    if fault=='seam': circle['start']=circle['end']=centre['key']
    if fault=='too_small_radius': circle['radius_si']=(1e-8).hex()
    if fault=='wrong_curve_radius': circle['circle_parameters_si'][6]=(.004).hex()
    if fault=='wrong_curve_centre': circle['circle_parameters_si'][0]=(.02).hex()
    if fault=='wrong_curve_axis': circle['circle_parameters_si'][3]=1.0.hex()
    if fault=='wrong_normal': circle['normal_si']=[1.0.hex(),0.0.hex(),0.0.hex()]
    if fault=='missing_dimension': semantic['dimensions'].pop()
    if fault=='extra_dimension': semantic['dimensions'].append(deepcopy(semantic['dimensions'][0]))
    if fault=='foreign_owner': semantic['dimensions'][0]['owner']['native_id']=11
    if fault=='dimension_alias': semantic['dimensions'][0]['full_name']=semantic['dimensions'][1]['full_name']
    if fault=='suppressed': x['suppressed']=True
    if fault=='extra_relation': snapshot['relations'].append(deepcopy(x))
    if fault=='wrong_relation_type': x['type']=9
    if fault=='wrong_display_type': diameter['display_type']=5
    if fault=='duplicate_axis': diameter['display_type']=11
    if fault=='wrong_xy_entities': x['entities']=[centre['key'],circle['key']]
    if fault=='wrong_xy_definitions': x['definitions']=[centre['key'],projected['key']]
    if fault=='wrong_diameter_entities': diameter['entities']=[centre['key']]
    if fault=='wrong_diameter_definitions': diameter['definitions']=['model_origin']
    if fault=='wrong_x_value': semantic['dimensions'][0]['values_si']['Основная']=.011
    if fault=='wrong_diameter_value': semantic['dimensions'][2]['values_si']['Основная']=.003
    if fault=='driven': semantic['dimensions'][0]['driven_state']=1
    if fault=='reference': semantic['dimensions'][0]['reference']=True
    if fault=='linked': semantic['dimensions'][0]['linked']=True
    if fault=='design_table_dimension': semantic['dimensions'][0]['design_table']=True
    if fault=='other_blocker': semantic['dimensions'][0]['write_blockers'].append('native_read_only')
    if fault=='read_only': semantic['context']['read_only']=True
    if fault=='editing_sketch': semantic['context']['editing_sketch']=True
    if fault=='external': semantic['context']['external_reference_count']=1
    if fault=='equations': semantic['context']['equation_count']=1
    if fault=='needs_rebuild': semantic['tree']['needs_rebuild']=True
    if fault=='feature_error': semantic['tree']['features'][0]['error_code']=1
    if fault=='inactive': semantic['context']['active_document']=False
    if fault=='incomplete_config': semantic['context']['configuration_geometry_complete']=False
    with pytest.raises(ExecutionFailure): classify(snapshot,semantic)
