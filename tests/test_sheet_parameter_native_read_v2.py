"""Native definition getter contract; artificial COM stand-ins, no CAD."""

from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_sheet_parameters import CadSheetParametersReadMixin
from solidworks_mcp.sheet_parameters import SheetParameterCatalog
from solidworks_mcp.jobs import ExecutionFailure
from test_sheet_parameters_v2 import options


@pytest.fixture
def reader(monkeypatch):
    from solidworks_mcp import binding
    monkeypatch.setattr(binding,'wrap',lambda value,interface:value)
    expected=options();events=[]
    base=NS(**expected['base']);sheet=NS(**expected['sheet']);data=NS(**expected['template'])
    data.GetUseGaugeTable=lambda:(0,False,'');data.GetCustomBendAllowance=lambda:NS(Type=2,KFactor=.42)
    template=NS(GetDefinition=lambda:data,GetTypeName2=lambda:'TemplateSheetMetal')
    target=NS(base=NS(GetDefinition=lambda:base),members=[NS(role='sheet',feature=NS(GetDefinition=lambda:sheet)),NS(role='sheet_folder',identity=id(template))])
    adapter=CadSheetParametersReadMixin();adapter._module=NS(IBaseFlangeFeatureData=object,ISheetMetalFeatureData=object,
        IModelDocExtension=object,IFeature=object,ICustomBendAllowance=object)
    adapter.identity=id;model=NS(Extension=NS(GetTemplateSheetMetal=lambda:template));adapter.model=model
    def fresh(model,base,retained):
        assert retained is target and base is target.base
        events.append('fresh_native_target');return target,object()
    adapter.sheet_state_target=fresh
    return adapter,target,data,events,expected


def test_independent_getters_use_revalidated_exact_native_member(reader):
    adapter,target,_,events,expected=reader
    result=adapter.sheet_parameter_options(adapter.model,target)
    assert events==['fresh_native_target'] and result==expected
    SheetParameterCatalog._validate_options(result)


@pytest.mark.parametrize('gauge',[None,(),(False,''),(0,False),(0,False,'',object())])
def test_partial_gauge_out_parameters_are_not_silent_defaults(reader,gauge):
    adapter,target,sheet,_,_=reader;sheet.GetUseGaugeTable=lambda:gauge
    with pytest.raises(ExecutionFailure,match='complete'):
        adapter.sheet_parameter_options(adapter.model,target)


@pytest.mark.parametrize('gauge',[(False,False,''),(1,False,''),(0,1,''),(0,True,''),(0,False,1)])
def test_native_error_type_or_table_remains_unsupported(reader,gauge):
    adapter,target,sheet,_,_=reader;sheet.GetUseGaugeTable=lambda:gauge
    result=adapter.sheet_parameter_options(adapter.model,target)
    with pytest.raises(ExecutionFailure):SheetParameterCatalog._validate_options(result)


def test_retained_original_options_read_after_shape_extension_does_not_adopt_new_owners(reader):
    adapter,target,_,events,expected=reader
    target.members.append(NS(role='base',feature=target.base))
    adapter._sheet_state_target_current=lambda m,t:events.append('context')
    adapter._sheet_member_reference=lambda m,r:events.append('member_'+r.role)
    assert adapter.sheet_parameter_options_retained(adapter.model,target)==expected
    assert events==['context','member_base','member_sheet','member_sheet_folder','context']


@pytest.mark.parametrize('defect',['missing','duplicate','replaced_base'])
def test_retained_options_require_original_unique_base_owner(reader,defect):
    adapter,target,_,events,_=reader
    adapter._sheet_state_target_current=lambda m,t:None
    adapter._sheet_member_reference=lambda m,r:None
    if defect!='missing':target.members.append(NS(role='base',feature=target.base if defect!='replaced_base' else object()))
    if defect=='duplicate':target.members.append(NS(role='base',feature=target.base))
    with pytest.raises(ExecutionFailure):adapter.sheet_parameter_options_retained(adapter.model,target)
