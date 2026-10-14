"""Validation and native-geometry regression tests for the local sheet-metal tools."""
import math

import pytest

from solidworks_mcp.errors import SolidWorksError
from solidworks_mcp.sheet_metal import check_bend_parameters, positive, profile_points


@pytest.mark.parametrize('value', [0, -1, float('inf'), float('nan'), '2', None])
def test_nonphysical_sizes_are_rejected(value):
    with pytest.raises(SolidWorksError):
        positive(value, 'thickness_mm')


@pytest.mark.parametrize('value', [-0.01, 1.01, float('nan'), float('inf'), None])
def test_invalid_k_factor_is_rejected(value):
    with pytest.raises(SolidWorksError):
        check_bend_parameters(2, value)


@pytest.mark.parametrize('points,closed', [
    ([[0,0],[1,0],[1,0]], False),
    ([[0,0],[1,0],[0,0]], False),
    ([[0,0],[1,1],[0,1],[1,0]], True),
    ([[0,0],[1,0],[2,0]], True),
    ([[0,0,1],[1,0,1],[1,1,1]], True),
    ([[0,0],[1,float('nan')]], False),
    ([[0,0],[2,2],[0,2],[2,0]], False),
])
def test_invalid_profile_rejected_before_com(points,closed):
    with pytest.raises(SolidWorksError):
        profile_points(points,closed)


def test_closed_outline_and_straight_open_strip():
    assert profile_points([[0,0],[2,0],[2,1],[0,0]],True)==[(0,0),(2,0),(2,1)]
    assert profile_points([[0,0],[100,0]],False)==[(0,0),(100,0)]


@pytest.fixture
def sheet_part(sw):
    # SolidWorks owns the generated bend-line/bounding-box sketches; those are
    # allowed to be under-defined. Our source sketch is checked by each builder.
    sw.new_part()
    yield sw
    sw.close_part()


@pytest.mark.solidworks
def test_native_sheet_dimensions_and_closed_outline(sheet_part):
    part=sheet_part
    result=part.run_guarded(part.add_sheet_metal_base,[[0,0],[80,0],[80,40],[0,40]],2,2,.4)
    assert result['fully_defined']
    assert result['mass_properties']['volume_mm3']==pytest.approx(6400)
    assert result['mass_properties']['bounding_box_mm']['min_mm']==pytest.approx([0,0,0])
    assert result['mass_properties']['bounding_box_mm']['size_mm']==pytest.approx([80,40,2])
    info=part.get_sheet_metal_info()
    assert info['is_sheet_metal'] and not info['feature_errors']
    assert info['parameters'][0]['k_factor']==pytest.approx(.4)
    assert info['parameters'][0]['thickness_mm']==pytest.approx(2)
    with pytest.raises(SolidWorksError,match='empty part'):
        part.run_guarded(part.add_sheet_metal_base,[[0,0],[10,0],[10,10]],2)


@pytest.mark.solidworks
def test_bent_profile_flat_size_and_restore(sheet_part):
    part=sheet_part
    made=part.run_guarded(part.add_sheet_metal_profile,[[0,25],[0,0],[80,0],[80,25]],40,2,2,.5)
    assert made['fully_defined']
    folded=made['mass_properties']
    assert folded['bounding_box_mm']['size_mm']==pytest.approx([84,27,40])
    flat=part.run_guarded(part.set_sheet_metal_flattened,True)
    # Outside-material profile: straights 80-2*R + 2*(25-R), plus 2 quarter
    # circles with neutral radius R+t/2. R=2 here (inner), outer=4.
    expected=80-4 + 2*(25-2) + 3*math.pi
    assert sorted(flat['mass_properties']['bounding_box_mm']['size_mm'])==pytest.approx(sorted([expected,2,40]),abs=1e-4)
    assert flat['mass_properties']['volume_mm3']==pytest.approx(folded['volume_mm3'])
    assert not part.run_guarded(part.set_sheet_metal_flattened,True)['changed']
    restored=part.run_guarded(part.set_sheet_metal_flattened,False)
    assert restored['mass_properties']['bounding_box_mm']==folded['bounding_box_mm']
    assert not part.get_sheet_metal_info()['feature_errors']


@pytest.mark.solidworks
def test_existing_body_conversion_and_rejection(sheet_part):
    part=sheet_part
    part.add_extruded_profile([[0,0],[80,0],[80,25],[78,25],[78,2],[2,2],[2,25],[0,25]],40,
                              corner_radii_mm=[4,4,0,0,2,2,0,0])
    converted=part.run_guarded(part.convert_to_sheet_metal,'+y:inner',2,.5)
    assert converted['sheet_metal']['is_sheet_metal']
    assert converted['sheet_metal']['parameters'][0]['thickness_mm']==pytest.approx(2)
    flat=part.run_guarded(part.set_sheet_metal_flattened,True)
    assert sorted(flat['mass_properties']['bounding_box_mm']['size_mm'])==pytest.approx(sorted([114+3*math.pi,2,40]),abs=1e-4)
    before=part.list_features()['features']
    with pytest.raises(SolidWorksError,match='already sheet metal'):
        part.run_guarded(part.convert_to_sheet_metal,'+y:inner')
    assert part.list_features()['features']==before


@pytest.mark.solidworks
def test_dxf_export_preserves_state_and_protects_existing_file(sheet_part,tmp_path):
    part=sheet_part
    part.run_guarded(part.add_sheet_metal_profile,[[0,25],[0,0],[80,0],[80,25]],40,2)
    with pytest.raises(SolidWorksError,match='Save the part'):
        part.run_guarded(part.export_sheet_metal_dxf,str(tmp_path/'before_save.dxf'))
    part.save_part(str(tmp_path/'native_sheet.sldprt'))
    for state in [False,True]:
        part.run_guarded(part.set_sheet_metal_flattened,state)
        destination=tmp_path/f'flat_{state}.dxf'
        result=part.run_guarded(part.export_sheet_metal_dxf,str(destination))
        assert result['bytes']>100 and result['flattened']==state
        assert part.get_sheet_metal_info()['flat_patterns'][0]['flattened']==state
        contents=destination.read_bytes()
        with pytest.raises(SolidWorksError,match='already exists'):
            part.run_guarded(part.export_sheet_metal_dxf,str(destination))
        assert destination.read_bytes()==contents
        assert part.get_sheet_metal_info()['flat_patterns'][0]['flattened']==state
    with pytest.raises(SolidWorksError,match='.dxf'):
        part.run_guarded(part.export_sheet_metal_dxf,str(tmp_path/'invalid.step'))


@pytest.mark.solidworks
def test_double_perimeter_flange_and_volume(sheet_part):
    part=sheet_part
    part.run_guarded(part.add_sheet_metal_base,[[0,0],[120,0],[120,160],[0,160]],1.5,1.5,.5)
    def outside_edge(z):
        candidates=[]
        for e in part.list_edges(min_length_mm=20)['edges']:
            if e['type']!='line' or 'ends_mm' not in e: continue
            a,b=e['ends_mm']
            if any(abs(p[2]-z)>1e-6 for p in (a,b)): continue
            if any(abs(a[i]-v)<1e-6 and abs(b[i]-v)<1e-6 for i,v in [(0,0),(0,120),(1,0),(1,160)]):
                candidates.append(e['index'])
        return candidates[0]
    for z,length,flip in [(1.5,25,False),(25,10,True)]:
        for i in range(4):
            result=part.run_guarded(part.add_sheet_metal_edge_flange,outside_edge(z),length,90,flip,.5,
                                   f'Flange_{length}_{i}')
            assert result['mass_properties']['bounding_box_mm']['size_mm']==pytest.approx([120,160,25])
    folded=part.get_mass_properties()['mass_properties']
    flat=part.run_guarded(part.set_sheet_metal_flattened,True)['mass_properties']
    assert flat['bounding_box_mm']['size_mm']==pytest.approx([180.1372,220.1372,1.5],abs=1e-4)
    assert flat['volume_mm3']==pytest.approx(folded['volume_mm3'],rel=1e-8)
    restored=part.run_guarded(part.set_sheet_metal_flattened,False)
    assert restored['mass_properties']['bounding_box_mm']==folded['bounding_box_mm']
    assert not restored['sheet_metal']['feature_errors']
    history=part.list_features()['features']
    assert len([f for f in history if f['type']=='EdgeFlange'])==8
    with pytest.raises(SolidWorksError,match='edge_index'):
        part.run_guarded(part.add_sheet_metal_edge_flange,100000,10)
    assert part.list_features()['features']==history
