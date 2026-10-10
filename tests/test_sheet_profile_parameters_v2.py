"""Native parameter readback semantics; no CAD invocation."""

import pytest

from solidworks_mcp.sheet_profile_definition import sheet_l_native_parameters_match
from test_sheet_profile_definition_v2 import definition,folded_body,read,sheet_l_body_matches,IDENTITY


def parameters():
    return dict(Thickness=.002,BendRadius=.002,D1EndConditionDistance=.03,D1EndConditionType=1,
        ReverseThickness=True,ReverseDirection=False,SymmetricThickness=False,UseDefaultBendAllowance=False,
        UseGaugeTable=False,UseMaterialSheetMetalParameters=False),dict(thickness=.002,radius=.002,
        allowance_type=2,k_factor=.42,use_material=False)


def test_explicit_k_is_proved_separately_from_folded_shape():
    base,sheet=parameters();item=definition()
    assert sheet_l_native_parameters_match(base,sheet,item)
    assert sheet_l_body_matches({'bodies':[read(folded_body())]},item.expected_geometry(IDENTITY))
    sheet['k_factor']=.5
    assert not sheet_l_native_parameters_match(base,sheet,item)
    assert sheet_l_body_matches({'bodies':[read(folded_body())]},item.expected_geometry(IDENTITY))


@pytest.mark.parametrize('key,value',[('Thickness',.003),('BendRadius',.003),('D1EndConditionDistance',.031),
    ('D1EndConditionType',True),('D1EndConditionType',0),('ReverseThickness',False),('ReverseDirection',True),
    ('SymmetricThickness',True),('UseDefaultBendAllowance',True),('UseGaugeTable',True),('UseMaterialSheetMetalParameters',True),
    ('Thickness',True),('BendRadius',float('nan'))])
def test_base_defaults_wrong_directions_or_dimensions_are_rejected(key,value):
    base,sheet=parameters();base[key]=value
    assert not sheet_l_native_parameters_match(base,sheet,definition())


@pytest.mark.parametrize('key,value',[('thickness',.003),('radius',.003),('k_factor',.5),('k_factor',True),
    ('k_factor',float('nan')),('allowance_type',True),('allowance_type',1),('use_material',True),('radius',10**400)])
def test_native_sheet_allowance_cannot_be_inferred_or_defaulted(key,value):
    base,sheet=parameters();sheet[key]=value
    assert not sheet_l_native_parameters_match(base,sheet,definition())
