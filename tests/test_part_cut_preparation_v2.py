"""Internal analytical corner-cut preparation, artificial CAD, no native write."""
from copy import deepcopy
import math
import pytest
from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.part_cut import CornerCut,PartCutCatalog
from test_sketch_dimensions_v2 import setup as sketch_setup


def prepare(setup,**changes):
    _,sketches,_,_,doc,obj,_=setup
    plane=next(row['object_id'] for row in sketches.dimensions.features.list(doc,'Основная')['items'] if row['feature_type']=='RefPlane')
    return PartCutCatalog(sketches).prepare_corner_cut(doc,'Основная',**{
        'object_id':obj,'plane_object_id':plane,'width_mm':10.,'height_mm':5.,**changes})


def test_preparation_binds_original_geometry_exact_plane_and_cut_parameters_without_native_write(sketch_setup):
    adapter=sketch_setup[0]
    old=deepcopy([row.state for row in adapter.models])
    result=prepare(sketch_setup)
    expected=result['expected_geometry']
    assert result['revision_scope']=='single_base_rectangular_corner_through_cut_v1'
    assert result['native_creation_available'] is True
    assert expected['volume_mm3']==pytest.approx(7500.)
    assert expected['surface_area_mm2']==pytest.approx(2700.)
    assert len(expected['vertices_si'])==expected['vertex_count']==12
    assert expected['edge_count']==18 and expected['face_count']==8
    # Independent polygon integration/perimeter verifies both analytic measures.
    polygon=[[float.fromhex(v) for v in row] for row in expected['remaining_profile_si']]
    pairs=list(zip(polygon,polygon[1:]+polygon[:1]))
    area=math.fsum(a[0]*b[1]-a[1]*b[0] for a,b in pairs)/2.
    perimeter=math.fsum(math.dist(a,b) for a,b in pairs)
    assert area*.01*1e9==pytest.approx(expected['volume_mm3'])
    assert (2*area+perimeter*.01)*1e6==pytest.approx(expected['surface_area_mm2'])
    assert old==[row.state for row in adapter.models] and adapter.dimension_writes==[]
    assert prepare(sketch_setup)['revision']==result['revision']
    assert prepare(sketch_setup,width_mm=11.)['revision']!=result['revision']


@pytest.mark.parametrize('changes',[{'width_mm':40.},{'height_mm':20.},{'width_mm':41.},
    {'width_mm':39.9999},{'width_mm':0.},{'height_mm':True},{'height_mm':float('inf')},
    {'sketch_name':'Sketch'},{'feature_name':'Эскиз выреза'},{'feature_name':'Основание'}])
def test_unsafe_or_conflicting_cut_rejected_before_any_native_write(sketch_setup,changes):
    with pytest.raises(ExecutionFailure):prepare(sketch_setup,**changes)
    assert sketch_setup[0].dimension_writes==[]


def test_wrong_explicit_plane_never_adopts_the_base_plane_by_name(sketch_setup):
    _,sketches,_,_,doc,_,_=sketch_setup
    wrong=next(row['object_id'] for row in sketches.dimensions.features.list(doc,'Основная')['items'] if row['feature_type']=='Boss')
    with pytest.raises(ExecutionFailure):prepare(sketch_setup,plane_object_id=wrong)


def test_invalid_reference_rejected_before_native_access(sketch_setup,monkeypatch):
    _,sketches,_,_,doc,obj,_=sketch_setup
    monkeypatch.setattr(sketches,'_capture',lambda *args:pytest.fail('Unexpected CAD access'))
    with pytest.raises(ExecutionFailure):PartCutCatalog(sketches).prepare_corner_cut(doc,'Основная',
        object_id=obj,plane_object_id='Передняя',width_mm=10.,height_mm=5.)


def test_late_plane_getter_event_invalidates_preparation(sketch_setup):
    adapter,sketches,_,_,_,_,_=sketch_setup
    original=adapter.part_creation_controls
    def late(model):
        value=original(model)
        adapter.watches[id(adapter.original(model).identity)].sequence+=1
        return value
    adapter.part_creation_controls=late
    with pytest.raises(ExecutionFailure):prepare(sketch_setup)


def test_model_transform_rotates_complete_expected_vertices_without_relocating_model():
    definition=CornerCut.validate(object_id='feat_'+'a'*32,plane_object_id='feat_'+'b'*32,width_mm=10.,height_mm=5.)
    frame=[0.,1.,0.,-1.,0.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]
    expected=definition.expected_geometry({'width_m':.04,'height_m':.02,'depth_m':.01,'plane_transform':frame})
    vertices=[[float.fromhex(v) for v in row] for row in expected['vertices_si']]
    assert vertices[0]==[-.005,0.,0.] and vertices[1]==[-.005,0.,.01]
