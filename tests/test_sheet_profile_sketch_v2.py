"""Independent open-profile constraint network; not native CAD acceptance."""

from copy import deepcopy

import pytest

from solidworks_mcp.sheet_profile_definition import sheet_l_sketch_matches
from test_sheet_profile_definition_v2 import definition
from test_part_creation_v2 import IDENTITY


def network():
    point=lambda key,values,implicit=False:dict(key=key,point_type=10 if implicit else 0,
        constraint_status=2,implicit=implicit,coordinates_si=[float(v).hex() for v in values])
    line=lambda key,a,b:dict(key=key,kind='line',construction=False,infinite=False,
        constraint_status=2,start=a,end=b)
    relation=lambda kind,entities,definitions=None,dimension=None,display=None:dict(type=kind,
        suppressed=False,entities=entities,definitions=entities if definitions is None else definitions,
        dimension_full_name=dimension,display_type=display)
    frame=[float(v).hex() for v in IDENTITY]
    snapshot=dict(constraint_status=3,is_3d=False,feature_native_id=26,
        reference_plane=dict(pid_hex='abcd',transform=frame),model_to_sketch=frame,
        model_origin_point=dict(point_type=1,constraint_status=2,coordinates_si=['0x0.0p+0']*3),
        points=[point('top',(0.,.02,0.)),point('corner',(0.,0.,0.)),point('right',(.04,0.,0.)),point('projected',(0.,0.,0.),True)],
        segments=[line('vertical','top','corner'),line('horizontal','corner','right')],
        relations=[relation(5,['vertical']),relation(4,['horizontal']),
            relation(9,['projected','corner'],['model_origin','corner']),
            relation(1,['top','projected'],['top','model_origin'],'height@profile',12),
            relation(1,['right','projected'],['right','model_origin'],'width@profile',11)])
    row=lambda name,full,size:dict(name=name,full_name=full,unit='mm',owner=dict(native_id=26,owner_native_id=49),
        driven_state=2,read_only=False,reference=False,linked=False,design_table=False,
        write_blockers=['sketch_geometry_snapshot_not_implemented'],values_si={'Основная':size})
    semantic=dict(dimensions=[row('Высота полки','height@profile',.02),row('Ширина полки','width@profile',.04)])
    return snapshot,semantic


def matches(snapshot,semantic):
    return sheet_l_sketch_matches(snapshot,semantic,'Основная',definition(),'abcd',IDENTITY,49)


def test_all_native_constraints_and_independent_drivers_are_required():
    snapshot,semantic=network()
    assert matches(snapshot,semantic)
    snapshot['points'].reverse();snapshot['segments'].reverse();snapshot['relations'].reverse();semantic['dimensions'].reverse()
    assert matches(snapshot,semantic)


@pytest.mark.parametrize('fault',['height','z_offset','point_status','implicit_origin','model_origin','second_origin',
    '3d','underdefined','plane_pid','segment_graph','construction','infinite','line_status','suppressed_relation',
    'missing_relation','duplicate_axis','fixed_relation','wrong_axis','wrong_definition','foreign_projection',
    'missing_driver','extra_driver','foreign_owner','reference','read_only','linked','design_table','driven',
    'nonfinite_driver','driver_value','driver_name','driver_unit','blocker','duplicate_point','duplicate_segment'])
def test_extents_or_dimension_names_cannot_substitute_for_the_full_network(fault):
    snapshot,semantic=network();row=semantic['dimensions'][0]
    if fault=='height':snapshot['points'][0]['coordinates_si'][1]=(.021).hex()
    elif fault=='z_offset':snapshot['points'][0]['coordinates_si'][2]=(.001).hex()
    elif fault=='point_status':snapshot['points'][0]['constraint_status']=1
    elif fault=='implicit_origin':snapshot['points'][-1]['point_type']=0
    elif fault=='model_origin':snapshot['model_origin_point']['coordinates_si'][0]=(.001).hex()
    elif fault=='second_origin':snapshot['points'][0]['implicit']=True
    elif fault=='3d':snapshot['is_3d']=True
    elif fault=='underdefined':snapshot['constraint_status']=2
    elif fault=='plane_pid':snapshot['reference_plane']['pid_hex']='different'
    elif fault=='segment_graph':snapshot['segments'][0]['end']='right'
    elif fault in ('construction','infinite'):snapshot['segments'][0][fault]=True
    elif fault=='line_status':snapshot['segments'][0]['constraint_status']=1
    elif fault=='suppressed_relation':snapshot['relations'][0]['suppressed']=True
    elif fault=='missing_relation':snapshot['relations'].pop()
    elif fault=='duplicate_axis':snapshot['relations'][0]=deepcopy(snapshot['relations'][1])
    elif fault=='fixed_relation':snapshot['relations'][0]['type']=17
    elif fault=='wrong_axis':snapshot['relations'][3]['display_type']=11
    elif fault=='wrong_definition':snapshot['relations'][3]['definitions']=['top','corner']
    elif fault=='foreign_projection':snapshot['relations'][3]['entities']=['top','foreign']
    elif fault=='missing_driver':semantic['dimensions'].pop()
    elif fault=='extra_driver':semantic['dimensions'].append(deepcopy(row))
    elif fault=='foreign_owner':row['owner']['owner_native_id']=999
    elif fault in ('reference','read_only','linked','design_table'):row[fault]=True
    elif fault=='driven':row['driven_state']=1
    elif fault=='nonfinite_driver':row['values_si']['Основная']=float('nan')
    elif fault=='driver_value':row['values_si']['Основная']=.021
    elif fault=='driver_name':row['name']='Ширина полки'
    elif fault=='driver_unit':row['unit']='deg'
    elif fault=='blocker':row['write_blockers'].append('external_reference')
    elif fault=='duplicate_point':snapshot['points'].append(deepcopy(snapshot['points'][0]))
    elif fault=='duplicate_segment':snapshot['segments'].append(deepcopy(snapshot['segments'][0]))
    assert not matches(snapshot,semantic)
