"""Native transformation semantics and strict body/suppression binding contracts."""
from types import SimpleNamespace
import pytest
from solidworks_mcp.cad_components import CadComponentsMixin,component_transform
from solidworks_mcp.jobs import ExecutionFailure

IDENTITY=[1.,0.,0.,0.,1.,0.,0.,0.,1.,.05,.01,.02,1.,0.,0.,0.]


def test_native_column_axes_translation_and_mirror_are_explicit():
    values=list(IDENTITY);values[:9]=[0.,1.,0.,-1.,0.,0.,0.,0.,1.]
    got=component_transform(values);assert got['origin_mm']==[50.,10.,20.]
    assert got['axes_in_assembly']==[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]
    assert got['includes_presentation_transform'] is False and got['parity']=='right_handed'
    values[8]=-1.;assert component_transform(values)['parity']=='mirrored'


@pytest.mark.parametrize('values',[None,[],IDENTITY[:15],IDENTITY+[0.],['bad']+IDENTITY[1:],[True]+IDENTITY[1:],[float('nan')]+IDENTITY[1:]])
def test_invalid_transform_not_coerced(values):
    with pytest.raises(ExecutionFailure) as exc:component_transform(values)
    assert exc.value.code=='component_transform_unavailable'


@pytest.mark.parametrize('index,value',[(12,2.),(13,1.),(0,2.),(3,.5)])
def test_nonrigid_transform_rejected(index,value):
    values=list(IDENTITY);values[index]=value
    with pytest.raises(ExecutionFailure) as exc:component_transform(values)
    assert exc.value.code=='unsupported_component_transform'


@pytest.mark.parametrize('value',[None,(),(None,),([],None,None),([object()],[0]),([object()],[]),([],['bad'])])
def test_native_body_info_requires_normal_body_and_matching_census(value):
    c=SimpleNamespace(GetBodies3=lambda kind:value)
    with pytest.raises(ExecutionFailure):CadComponentsMixin().component_bodies(c)


@pytest.mark.parametrize('state',[0,1,4,5,True,2.])
def test_native_state_not_resolved_never_loads_model(state):
    c=SimpleNamespace(GetSuppression2=lambda:state,GetModelDoc2=lambda:pytest.fail('No model getter for unresolved instance'))
    with pytest.raises(ExecutionFailure) as exc:CadComponentsMixin().component_info(c)
    assert exc.value.code=='component_not_resolved'
