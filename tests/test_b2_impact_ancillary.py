"""Actual reused native ancillary getters on artificial handles only, no CAD."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import binding
from solidworks_mcp.cad_part_creation import CadPartCreationMixin
from test_native_first_save_full_capture import CaptureAdapter

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:import verifier_b2_impact_ancillary as helper
finally:sys.path.remove(str(scripts))


@pytest.fixture
def current(monkeypatch):
    monkeypatch.setattr(binding,'wrap',lambda raw,interface:raw)
    monkeypatch.setattr(binding,'queried',lambda raw,interface:raw)
    a=CaptureAdapter()
    for view in a.annotation_views:view.GetAnnotations2=lambda include_hidden,include_dangling:None
    for record in a.dimension_rows:
        for display in record.displays:display.GetAnnotation().AnnotationView=a.annotation_views[1]
    a._module.ISketchManager=object
    a.model.SketchManager=NS(AddToDB=False,AutoSolve=True,DisplayWhenAdded=True)
    a._sw=NS(GetUserPreferenceToggle=lambda code:False)
    a.part_creation_controls=lambda model:CadPartCreationMixin.part_creation_controls(a,model)
    refs=[dict(kind='feature',role='feature:5',token=a.feature_rows[5].pid.hex())]
    roles={row.summary['full_name']:axis for row,axis in zip(a.dimension_rows,('width','height','depth'))}
    state=NS(adapter=a,references=refs,roles=roles)
    def collect(**changes):
        values=dict(configuration='Основная',features=a.features(a.model),
            summaries=[a.feature_summary(feature) for feature in a.feature_rows],
            dimensions=a.dimension_rows[:],dimension_roles=roles,references=refs,body=a.body)
        values.update(changes)
        return helper.collect_impact_ancillary(a,a.model,**values)
    state.collect=collect
    return state


def test_actual_installed_getters_capture_current_ancillary_arrays_annotations_view_bindings_material_controls(current):
    x=current;a=x.adapter;refs=deepcopy(x.references)
    result=x.collect();data=result['data']
    assert set(data)=={'properties','configuration_state','auxiliary_data','display_data','annotations',
        'annotation_view_bindings','material','body_material','body','units','creation_controls','references'}
    assert data['properties'][''][0]['name']=='Описание'
    assert data['configuration_state']['parameters']==[['Параметр','Значение']]
    assert data['auxiliary_data']==dict(attachments=0,comments=0,named_selection_sets=0)
    assert len(data['display_data']['lights'])==4 and len(data['annotations'])==3
    assert set(data['annotation_view_bindings']['dimension_views'])=={'width','height','depth'}
    assert data['material']==data['body_material']==['',''] and data['body']['name']=='Тело основания'
    assert data['creation_controls']==dict(add_to_db=False,auto_solve=True,display_when_added=True,dimension_input=False)
    assert len(data['references'])==4 and x.references==refs
    assert 'cached_property' in a.calls and 'view_count' in a.calls and 'annotation_count' in a.calls
    assert x.collect()['data']==data  # Actual current view incarnation IDs remain stable.
    assert result['accepted'] is result['native_b2_accepted'] is result['public_mcp_accepted'] is False
    assert 'clone_state' not in data and 'cleanup' not in result and 'full_refusal_context_available' not in result


@pytest.mark.parametrize('fixture_kind',['extra_plane','unused_equation'])
def test_collector_reads_current_ancillary_data_without_claiming_base_profile_after_unsupported_fixture(current,fixture_kind):
    x=current;a=x.adapter
    if fixture_kind=='extra_plane':
        plane=a.register(NS(row=dict(native_id=99,name='Контрольная дочерняя плоскость',feature_type='RefPlane',
            suppressed=False,error_code=0,owner_native_id=None)), 'feature:own_child_plane')
        a.feature_rows.append(plane)
    else:
        a.inventory['equations'].update(enumerated_count=1,rows=[{'expression':'"Контрольная величина" = 3'}])
    # Values differ from every prior fixture baseline and must be read now.
    a.model.GetMaterialPropertyName2=lambda cfg:('Сталь 45','private/materials.sldmat')
    a.body.GetMaterialPropertyName=lambda cfg:('Материал тела','private/body.sldmat')
    a.body.Name='Собственное тело';a.body.Visible=False
    a.model.GetUnits=lambda:[1,2,3,4,True,6]
    a.cached_property=lambda name,cached:(0,'Новое значение','Новое значение',True,False)
    a.configuration.GetParameters=lambda:(['Текущий параметр'],['Новое значение'])
    data=x.collect()['data']
    assert data['material']==['Сталь 45','private/materials.sldmat']
    assert data['body_material']==['Материал тела','private/body.sldmat']
    assert data['body']==dict(name='Собственное тело',visible=False) and data['units']==[1,2,3,4,True,6]
    assert data['properties'][''][0]['value']=='Новое значение'
    assert data['configuration_state']['parameters']==[['Текущий параметр','Новое значение']]
    assert 'equation_reference_inventory' not in data  # Root's distinct census owns equations.


@pytest.mark.parametrize('fault,field',[
    ('properties_changed','properties'),('configuration_changed','configuration_state'),
    ('attachments','auxiliary_data'),('comments','auxiliary_data'),('comments_changed','auxiliary_data'),
    ('comment_owner','auxiliary_data'),('lights_missing','display_data'),('lights_changed','display_data'),
    ('light_values_missing','display_data'),('light_values_nonfinite','display_data'),
    ('light_name_mismatch','display_data'),('light_duplicate_name','display_data'),
    ('views_missing','display_data'),('views_changed','display_data'),('view_count_changed','display_data'),
    ('view_nonempty','display_data'),('view_unknown_annotation','display_data'),('view_rotation_missing','display_data'),
    ('annotations_missing','annotations'),('annotations_changed','annotations'),('units_missing','units')])
def test_actual_reused_getters_fail_with_concrete_field_on_missing_changing_or_unknown_native_inventory(current,fault,field):
    x=current;a=x.adapter;a.fault=fault
    if fault=='annotations_changed':a.global_annotations=a.annotations[:]
    original=deepcopy(x.references)
    with pytest.raises(helper.AncillaryGate) as error:x.collect()
    assert error.value.field==field and x.references==original


@pytest.mark.parametrize('fault,field',[
    ('missing_material','material'),('short_material','material'),('unknown_material','material'),
    ('missing_body_material','body_material'),('material_getter_throw','body_material'),
    ('missing_units','units'),('unknown_units','units'),('nonfinite_units','units'),('oversized_units','units'),
    ('unknown_body_visibility','body'),('mesh_body','body'),('boolean_body_type','body'),
    ('missing_controls','creation_controls'),('unknown_controls','creation_controls'),
    ('unknown_annotation','annotations'),('missing_annotation_position','annotations'),('missing_text_format','annotations'),
    ('unknown_view_owner','annotation_view_bindings'),('missing_annotation_view','annotation_view_bindings')])
def test_materials_units_controls_and_live_annotation_membership_are_never_filled_from_baseline(current,fault,field):
    x=current;a=x.adapter
    if fault=='missing_material':a.model.GetMaterialPropertyName2=lambda cfg:None
    elif fault=='short_material':a.model.GetMaterialPropertyName2=lambda cfg:('',)
    elif fault=='unknown_material':a.model.GetMaterialPropertyName2=lambda cfg:('',object())
    elif fault=='missing_body_material':a.body.GetMaterialPropertyName=lambda cfg:None
    elif fault=='material_getter_throw':
        def unavailable(cfg):raise RuntimeError('Actual getter acknowledgement unavailable')
        a.body.GetMaterialPropertyName=unavailable
    elif fault=='missing_units':a.model.GetUnits=lambda:None
    elif fault=='unknown_units':a.model.GetUnits=lambda:[0,object()]
    elif fault=='nonfinite_units':a.model.GetUnits=lambda:[0,float('nan')]
    elif fault=='oversized_units':a.model.GetUnits=lambda:[0]*17
    elif fault=='unknown_body_visibility':a.body.Visible=1
    elif fault=='mesh_body':a.body.IsMeshBody=lambda:True
    elif fault=='boolean_body_type':a.body.GetType=lambda:False
    elif fault=='missing_controls':a.part_creation_controls=lambda model:{'add_to_db':False}
    elif fault=='unknown_controls':a.part_creation_controls=lambda model:dict(add_to_db=0,auto_solve=True,
        display_when_added=True,dimension_input=False)
    elif fault=='unknown_annotation':a.global_annotations=[NS()]
    elif fault=='missing_annotation_position':a.annotations[0].GetPosition=lambda:None
    elif fault=='missing_text_format':a.dimension_rows[0].displays[0].GetTextFormat=lambda:None
    elif fault=='unknown_view_owner':a.annotations[0].AnnotationView=NS()
    else:a.annotations[0].AnnotationView=None
    with pytest.raises(helper.AncillaryGate) as error:x.collect()
    assert error.value.field==field


@pytest.mark.parametrize('fault',['fourth_dimension','fourth_role','missing_role','replaced_same_name_dimension',
                                'prior_annotation_refs','missing_full_name','duplicate_canonical'])
def test_only_three_exact_current_original_dimensions_and_new_annotation_observations_are_supported(current,fault):
    x=current;a=x.adapter;values={}
    if fault=='fourth_dimension':a.dimension_rows.append(deepcopy(a.dimension_rows[0]))
    elif fault=='fourth_role':x.roles['Offset@Контрольная плоскость@Деталь.Part']='plane_offset'
    elif fault=='missing_role':x.roles.pop(next(iter(x.roles)))
    elif fault=='replaced_same_name_dimension':
        original=a.dimensions;calls=[]
        def dimensions(model,features):
            calls.append(True)
            rows=original(model,features)
            if len(calls)>=2:rows[0]=NS(**vars(rows[0]))
            return rows
        a.dimensions=dimensions
    elif fault=='prior_annotation_refs':x.references.append(dict(kind='annotation',role='old_annotation',token='deadbeef'))
    elif fault=='missing_full_name':a.dimension_rows[0].summary.pop('full_name')
    else:values['dimensions']=[a.dimension_rows[0],a.dimension_rows[0],a.dimension_rows[2]]
    with pytest.raises(helper.AncillaryGate):x.collect(**values)


def test_actual_fourth_native_dimension_cannot_be_hidden_by_passing_only_original_records(current):
    x=current;a=x.adapter;original=a.dimension_rows[:]
    extra=deepcopy(original[0]);extra.summary['full_name']='Offset@Контрольная плоскость@Деталь.Part'
    a.dimension_rows.append(extra)
    with pytest.raises(helper.AncillaryGate) as error:x.collect(dimensions=original)
    assert error.value.field=='annotation_view_bindings'
