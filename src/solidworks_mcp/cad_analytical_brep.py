"""Dispatch complete supported bodies; a census selects a reader, never proves a shape."""

from .cad_planar_brep import PlanarBrepLimits, _Reader, planar_body_snapshot
from .cad_cylinder_brep import cylinder_body_snapshot
from .cad_hole_brep import hole_body_snapshot


ANALYTICAL_BREP_SCOPE = 'planar_cylinder_or_through_hole_body_set_v2'


def analytical_body_snapshot(body, *, identity, wrap=None, limits=None):
    limits = limits or PlanarBrepLimits()
    reader = _Reader(identity, wrap, limits)
    body = reader.obj(body, 'IBody2')
    census = (reader.count(body, 'GetVertexCount', limits.max_vertices, 0),
              reader.count(body, 'GetEdgeCount', limits.max_edges, 0),
              reader.count(body, 'GetFaceCount', limits.max_faces, 0))
    capture = cylinder_body_snapshot if census == (0, 2, 3) else planar_body_snapshot
    # Every disjoint through hole adds two periodic edges and one wall. The
    # complete reader still proves trims, loops, separation and solid validity.
    holes = census[2] - 6
    if holes >= 1 and census == (8, 12 + 2 * holes, 6 + holes):
        capture = hole_body_snapshot
    return capture(body, identity=identity, wrap=wrap, limits=limits)
