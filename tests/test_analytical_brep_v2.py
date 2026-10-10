"""Reader routing does not accept a shape from topology counts alone."""

import pytest

from solidworks_mcp.cad_analytical_brep import analytical_body_snapshot
from solidworks_mcp.cad_planar_brep import PlanarBrepError
from test_planar_brep_v2 import make_body, snapshot
from test_cylinder_brep_v2 import cylinder, read


def capture(body):
    return analytical_body_snapshot(body,identity=lambda value:value.ident)


def test_planar_boundary_is_identical_to_existing_complete_reader():
    body = make_body()
    assert capture(body) == snapshot(body)


def test_periodic_boundary_is_identical_to_complete_cylinder_reader():
    body = cylinder()
    assert capture(body) == read(body)


def test_counts_never_accept_a_partial_curve_or_hide_native_reader_failure():
    body = cylinder()
    body.edges[0].trim.UMaxValue /= 2.
    with pytest.raises(PlanarBrepError):
        capture(body)


@pytest.mark.parametrize('value',[True,-1,None,'0',0.])
def test_invalid_census_cannot_select_a_reader(value):
    body = cylinder()
    body.GetVertexCount = lambda:value
    with pytest.raises(PlanarBrepError):
        capture(body)
