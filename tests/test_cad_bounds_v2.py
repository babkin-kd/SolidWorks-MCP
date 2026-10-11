"""Native-shaped support API contracts; no CAD acceptance claimed."""
from types import SimpleNamespace as NS
import pytest
from solidworks_mcp.cad_geometry import CadGeometryMixin
from solidworks_mcp.jobs import ExecutionFailure


@pytest.mark.parametrize('value',[(False,1.,2.,3.),(1,1.,2.,3.),(True,float('nan'),0.,0.),
    (True,True,0.,0.),(True,1.,2.),None,[True,1.,2.,3.]])
def test_invalid_native_extreme_result_is_not_success(value):
    with pytest.raises(ExecutionFailure) as error:
        CadGeometryMixin().measurement_extreme_point(NS(GetExtremePoint=lambda *axis:value),(1.,0.,0.))
    assert error.value.code=='native_extreme_point_unavailable'


def test_direction_and_si_readback_are_passed_without_selection_or_body_box():
    events=[]
    body=NS(GetExtremePoint=lambda *direction:events.append(direction) or (True,-.002,.004,.005))
    assert CadGeometryMixin().measurement_extreme_point(body,(.8,.6,0.))==(-.002,.004,.005)
    assert events==[(.8,.6,0.)]


@pytest.mark.parametrize('kind,mesh',[(True,False),(2,False),(0,True),(0,None)])
def test_nonbrep_or_unconfirmed_body_type_rejected(kind,mesh):
    with pytest.raises(ExecutionFailure):CadGeometryMixin().measurement_body_type(NS(GetType=lambda:kind,IsMeshBody=lambda:mesh))


@pytest.mark.parametrize('kind,name',[(0,'solid'),(1,'surface')])
def test_solid_and_surface_brep_admitted(kind,name):
    assert CadGeometryMixin().measurement_body_type(NS(GetType=lambda:kind,IsMeshBody=lambda:False))==name
