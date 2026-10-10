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


def test_single_hole_census_selects_the_complete_native_reader():
    from test_hole_brep_v2 import plate,read as hole_read
    body=plate()
    assert capture(body)==hole_read(body)
    body.faces[-1].sense=False
    with pytest.raises(PlanarBrepError):capture(body)


def test_multiple_hole_routing_still_rejects_intersection_and_invalid_trims():
    from test_hole_brep_v2 import plate, circles
    from solidworks_mcp.cad_hole_brep import HOLE_BREP_SCOPE
    body = plate(((.2,.5,.05),(.4,.5,.05),(.6,.5,.05)))
    assert capture(body)['scope'] == HOLE_BREP_SCOPE
    circles(body)[-1].trim.UMaxValue /= 2.
    with pytest.raises(PlanarBrepError):
        capture(body)
    with pytest.raises(PlanarBrepError):
        capture(plate(((.3,.5,.2),(.5,.5,.2))))


@pytest.mark.parametrize('value',[True,-1,None,'0',0.])
def test_invalid_census_cannot_select_a_reader(value):
    body = cylinder()
    body.GetVertexCount = lambda:value
    with pytest.raises(PlanarBrepError):
        capture(body)
