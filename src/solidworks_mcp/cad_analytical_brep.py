"""Dispatch complete supported bodies; a census selects a reader, never proves a shape."""

from .cad_planar_brep import PlanarBrepLimits, _Reader, planar_body_snapshot
from .cad_cylinder_brep import cylinder_body_snapshot


ANALYTICAL_BREP_SCOPE = 'planar_or_right_cylinder_body_set_v1'


def analytical_body_snapshot(body, *, identity, wrap=None, limits=None):
    limits = limits or PlanarBrepLimits()
    reader = _Reader(identity, wrap, limits)
    body = reader.obj(body, 'IBody2')
    census = (reader.count(body, 'GetVertexCount', limits.max_vertices, 0),
              reader.count(body, 'GetEdgeCount', limits.max_edges, 0),
              reader.count(body, 'GetFaceCount', limits.max_faces, 0))
    capture = cylinder_body_snapshot if census == (0, 2, 3) else planar_body_snapshot
    return capture(body, identity=identity, wrap=wrap, limits=limits)
