"""Four-axis passive native binding on artificial handles, no CAD acceptance."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import binding
from solidworks_mcp.cad_native_first_save_snapshot import _display_data
from solidworks_mcp.cad_rectangle_annotation_views import rectangle_annotation_view_bindings
from solidworks_mcp.jobs import ExecutionFailure
from test_b2_impact_ancillary import current

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:import verifier_b2_impact_views as helper
finally:sys.path.remove(str(scripts))


@pytest.fixture
def four(current):
    x=current;a=x.adapter
    a._module.IDimension=object;a._module.IDisplayDimension=object
    for index,record in enumerate(a.dimension_rows):
        owner=a.feature_rows[4 if index<2 else 5]
        record.owner=owner;record.owner_tree_identity=a.identity(owner)
        record.GetFeatureOwner=lambda value=owner:value
        record.display_slots=[]
        for display in record.displays:
            display.GetType=lambda:2
            display.GetDimension2=lambda slot,value=record:value if slot==0 else None
            display.GetAnnotation().GetSpecificAnnotation=lambda value=display:value
            record.display_slots.append((display,0))
    original_roles=dict(x.roles)
    display=_display_data(a,a.model,a.feature_rows,[feature.row for feature in a.feature_rows])
    x.original_views=rectangle_annotation_view_bindings(a,a.model,display,original_roles)
    plane=a.register(NS(row=dict(native_id=100,name='Контрольная дочерняя плоскость',feature_type='RefPlane',
        suppressed=False,error_code=0,owner_native_id=None)), 'feature:own_plane')
    a.feature_rows.append(plane)
    annotation=a.register(NS(GetName=lambda:'Размер плоскости',GetType=lambda:4,Visible=1,
        GetPosition=lambda:[0.,0.,.015],AnnotationView=a.annotation_views[1]),'annotation:plane_offset')
    display_dimension=NS(GetAnnotation=lambda:annotation,GetTextFormat=lambda:NS(GetAllValues=lambda:['Arial',.0035,False]),
        Type2=2,GetText=lambda part:'',GetUseDocTextFormat=lambda:True,GetType=lambda:2)
    record=a.register(NS(displays=[display_dimension],display_slots=[(display_dimension,0)],
        owner=plane,owner_tree_identity=a.identity(plane),GetFeatureOwner=lambda:plane,
        summary=dict(name='Смещение',full_name='Смещение@Контрольная дочерняя плоскость@Деталь.Part',
            owner=deepcopy(plane.row),unit='mm',values_si={'Основная':.005},driven_state=2)), 'dimension:plane_offset')
    annotation.GetSpecificAnnotation=lambda:display_dimension
    display_dimension.GetDimension2=lambda slot:record if slot==0 else None
    a.dimension_rows.append(record);a.annotations.append(annotation)
    x.roles[record.summary['full_name']]='plane_offset'
    x.plane=plane;x.offset=record;x.offset_annotation=annotation;x.display_dimension=display_dimension
    def read(**changes):
        args=dict(configuration='Основная',features=a.feature_rows[:],dimensions=a.dimension_rows[:])
        args.update(changes)
        observed=_display_data(a,a.model,a.feature_rows,[feature.row for feature in a.feature_rows])
        return helper.impact_annotation_view_bindings(a,a.model,observed,x.roles,**args)
    x.read_views=read
    return x


def test_four_exact_current_native_dimensions_keep_production_original_view_ids_and_include_plane_offset(four):
    x=four;result=x.read_views()
    assert result['view_ids']==x.original_views['view_ids']
    assert {key:result['dimension_views'][key] for key in ('width','height','depth')}==x.original_views['dimension_views']
    assert set(result['dimension_views'])=={'width','height','depth','plane_offset'}
    assert result==x.read_views()
    assert set(result)=={'scope','view_ids','dimension_views'}


def test_actual_four_dim_ancillary_reuses_unmodified_annotation_getter_including_new_native_annotation(four):
    x=four;refs=deepcopy(x.references)
    result=x.collect();data=result['data']
    assert len(data['annotations'])==4 and len(data['references'])==5 and x.references==refs
    assert data['annotation_view_bindings']['view_ids']==x.original_views['view_ids']
    assert 'plane_offset' in data['annotation_view_bindings']['dimension_views']
    assert result['accepted'] is result['native_b2_accepted'] is result['public_mcp_accepted'] is False


@pytest.mark.parametrize('fault',['foreign_view','missing_view','duplicate_view','nonempty_view','missing_rotation',
    'foreign_annotation','annotation_missing','specific_display_foreign','direct_dimension_foreign',
    'dimension_owner_foreign','owner_tree_foreign','unknown_type','angular_type','boolean_type','nonlinear_offset',
    'duplicate_axis','missing_axis','fifth_dimension','missing_dimension','same_name_replaced_dimension',
    'duplicate_canonical','duplicate_displays','missing_slots','wrong_slot','bool_slot','annotation_type_unknown',
    'display_mixed_views','duplicate_cache_identity','same_dimension_replaced_display_alias'])
def test_unknown_foreign_partial_duplicate_extra_or_replaced_native_membership_is_refused(four,fault):
    x=four;a=x.adapter;values={}
    if fault=='foreign_view':x.offset_annotation.AnnotationView=NS()
    elif fault=='missing_view':a.annotation_views.pop()
    elif fault=='duplicate_view':a.annotation_views[0]=a.annotation_views[1]
    elif fault=='nonempty_view':a.fault='view_nonempty'
    elif fault=='missing_rotation':a.fault='view_rotation_missing'
    elif fault=='foreign_annotation':x.display_dimension.GetAnnotation=lambda:NS(GetType=lambda:4,
        GetSpecificAnnotation=lambda:NS(),AnnotationView=a.annotation_views[1])
    elif fault=='annotation_missing':x.display_dimension.GetAnnotation=lambda:None
    elif fault=='specific_display_foreign':x.offset_annotation.GetSpecificAnnotation=lambda:NS()
    elif fault=='direct_dimension_foreign':x.display_dimension.GetDimension2=lambda slot:NS()
    elif fault=='dimension_owner_foreign':x.offset.GetFeatureOwner=lambda:NS()
    elif fault=='owner_tree_foreign':x.offset.owner_tree_identity=object()
    elif fault in ('unknown_type','angular_type','boolean_type','nonlinear_offset'):
        code={'unknown_type':0,'angular_type':3,'boolean_type':True,'nonlinear_offset':11}[fault]
        x.display_dimension.GetType=lambda:code
    elif fault=='duplicate_axis':x.roles[x.offset.summary['full_name']]='width'
    elif fault=='missing_axis':x.roles.pop(x.offset.summary['full_name'])
    elif fault=='fifth_dimension':a.dimension_rows.append(NS(**vars(x.offset)))
    elif fault=='missing_dimension':a.dimension_rows.pop()
    elif fault=='same_name_replaced_dimension':
        retained=a.dimension_rows[:];a.dimension_rows[-1]=NS(**vars(x.offset));values['dimensions']=retained
    elif fault=='duplicate_canonical':values['dimensions']=[a.dimension_rows[0],a.dimension_rows[0],a.dimension_rows[2],x.offset]
    elif fault=='duplicate_displays':x.offset.displays.append(x.display_dimension);x.offset.display_slots.append((x.display_dimension,0))
    elif fault=='missing_slots':x.offset.display_slots=[]
    elif fault=='wrong_slot':x.offset.display_slots=[(x.display_dimension,1)]
    elif fault=='bool_slot':x.offset.display_slots=[(x.display_dimension,False)]
    elif fault=='annotation_type_unknown':x.offset_annotation.GetType=lambda:0
    elif fault=='display_mixed_views':
        annotation=NS(GetType=lambda:4,AnnotationView=a.annotation_views[0])
        other=NS(GetType=lambda:2,GetDimension2=lambda slot:x.offset,GetAnnotation=lambda:annotation)
        annotation.GetSpecificAnnotation=lambda:other
        x.offset.displays.append(other);x.offset.display_slots.append((other,0))
    elif fault=='same_dimension_replaced_display_alias':
        native=NS(**vars(x.offset));native.displays=[NS(**vars(x.display_dimension))]
        native.display_slots=[(native.displays[0],0)]
        a.dimensions=lambda model,features:[*a.dimension_rows[:3],native]
    else:
        rows=a._rectangle_view_incarnations[0][1];rows.append(rows[0])
    with pytest.raises((ValueError,ExecutionFailure)):
        # All boundary faults must raise; production getter failures remain
        # explicit too, never a replacement observation or accepted flag.
        x.read_views(**values)


@pytest.mark.parametrize('boundary',['view','dimension','annotation','display_type','display_alias'])
def test_current_native_closing_membership_rechecks_detect_replacement_after_initial_read(four,boundary):
    x=four;a=x.adapter
    if boundary=='view':
        original=a.extension.adapter.read
        initial=a.counters.get('views',0)
        def read(name,value):
            if name=='views' and a.counters.get(name,0)>=initial+3:
                from copy import copy
                replacement=copy(a.annotation_views[0]);return [replacement,a.annotation_views[1]]
            return original(name,value)
        a.read=read
    elif boundary=='dimension':
        original=a.dimensions;calls=[]
        def dimensions(model,features):
            calls.append(True);rows=original(model,features)
            if len(calls)>=2:rows[-1]=NS(**vars(rows[-1]))
            return rows
        a.dimensions=dimensions
    elif boundary=='annotation':
        calls=[];original=x.display_dimension.GetAnnotation
        def annotation():
            calls.append(True)
            return NS(**vars(x.offset_annotation)) if len(calls)>=2 else original()
        x.display_dimension.GetAnnotation=annotation
    elif boundary=='display_type':
        calls=[]
        def display_type():calls.append(True);return 3 if len(calls)>=2 else 2
        x.display_dimension.GetType=display_type
    else:
        original=a.dimensions;calls=[]
        def dimensions(model,features):
            calls.append(True);rows=original(model,features)
            if len(calls)>=2:
                current=NS(**vars(x.offset));current.displays=[NS(**vars(x.display_dimension))]
                current.display_slots=[(current.displays[0],0)];rows[-1]=current
            return rows
        a.dimensions=dimensions
    with pytest.raises((ValueError,ExecutionFailure)):x.read_views()
