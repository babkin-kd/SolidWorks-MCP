"""Exact-template native write protocol using COM stand-ins; not CAD evidence."""

from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_sheet_parameters import CadSheetParametersMixin
from solidworks_mcp.jobs import ExecutionFailure
from test_sheet_profile_definition_v2 import definition


@pytest.fixture
def writer():
    adapter=CadSheetParametersMixin();events=[];fault=dict(value=None);target=object()
    allowance=NS(Type=2,KFactor=.42);data=NS(Thickness=.002,BendRadius=.002)
    def access(model,component):
        assert component is None;events.append('access')
        if fault['value']=='access_exception':raise RuntimeError('Native RPC outcome unknown.')
        return fault['value']!='access_false'
    def set_allowance(value):assert value is allowance;events.append('allowance')
    def release():
        events.append('release')
        if fault['value']=='release_exception':raise RuntimeError('Unconfirmed release.')
    data.AccessSelections=access;data.SetCustomBendAllowance=set_allowance;data.ReleaseSelectionAccess=release
    def modify(value,model,component):
        assert value is data and component is None;events.append('modify')
        if fault['value']=='modify_exception':raise RuntimeError('Native RPC outcome unknown.')
        return fault['value'] not in ('modify_false','release_exception')
    template=NS(ModifyDefinition=modify)
    def rebuild(top_only):assert top_only is False;events.append('rebuild');return fault['value']!='rebuild_false'
    model=NS(ForceRebuild3=rebuild)
    def fresh(model,base,retained):assert retained is target;events.append('fresh');return target,object()
    target=NS(base=object());adapter.sheet_state_target=fresh
    adapter._sheet_parameter_template=lambda model,retained:(template,data,allowance)
    def current(model,retained):assert retained is target;events.append('current')
    adapter._sheet_state_target_current=current
    return adapter,model,target,data,allowance,events,fault


def test_one_exact_template_update_rolls_forward_then_rebuilds(writer):
    adapter,model,target,data,allowance,events,_=writer
    assert adapter.sheet_modify_parameters(model,target,definition(thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38)) is True
    assert events==['fresh','current','access','current','allowance','current','modify','current','rebuild']
    assert (data.Thickness,data.BendRadius,allowance.Type,allowance.KFactor)==(.0025,.0035,2,.38)


def test_exact_noop_never_accesses_selections_or_rebuilds(writer):
    adapter,model,target,_,_,events,_=writer
    assert adapter.sheet_modify_parameters(model,target,definition()) is False
    assert events==['fresh']


@pytest.mark.parametrize('fault_name,code',[('access_false','sheet_parameter_access_failed'),('modify_false','sheet_parameter_modify_failed')])
def test_known_native_rejection_releases_only_own_definition(writer,fault_name,code):
    adapter,model,target,_,_,events,fault=writer;fault['value']=fault_name
    with pytest.raises(ExecutionFailure) as error:
        adapter.sheet_modify_parameters(model,target,definition(thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38))
    assert error.value.code==code and error.value.uncertain is False
    assert events[-1]=='release' and 'rebuild' not in events


@pytest.mark.parametrize('fault_name',['access_exception','modify_exception'])
def test_uncertain_native_call_never_auto_releases_or_repeats(writer,fault_name):
    adapter,model,target,_,_,events,fault=writer;fault['value']=fault_name
    with pytest.raises(ExecutionFailure) as error:
        adapter.sheet_modify_parameters(model,target,definition(thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38))
    assert error.value.uncertain is True
    assert 'release' not in events and 'rebuild' not in events and events.count('access')==1


def test_unconfirmed_release_remains_uncertain(writer):
    adapter,model,target,_,_,events,fault=writer;fault['value']='release_exception'
    with pytest.raises(ExecutionFailure) as error:
        adapter.sheet_modify_parameters(model,target,definition(thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38))
    assert error.value.code=='sheet_parameter_access_unresolved' and error.value.uncertain is True
    assert events[-1]=='release' and 'rebuild' not in events


def test_rebuild_failure_does_not_reopen_already_committed_definition(writer):
    adapter,model,target,_,_,events,fault=writer;fault['value']='rebuild_false'
    with pytest.raises(ExecutionFailure) as error:
        adapter.sheet_modify_parameters(model,target,definition(thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38))
    assert error.value.code=='sheet_parameter_rebuild_failed'
    assert events[-1]=='rebuild' and 'release' not in events
