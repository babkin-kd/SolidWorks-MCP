"""Complete intended U-sheet flat boundary, with both explicit native K factors.

This predicts geometry only. It does not establish native identity, fixed-face
membership, or evidence that a physical unfold has been accepted.
"""

from types import SimpleNamespace
import math

from .documents import rejected
from .sheet_edge_flange_definition import EdgeFlangeOnL
from .sheet_flat_geometry import expected_flat_l_geometry,fixed_l_leg_from_face,flat_l_body_matches


def _material_dimensions(definition):
    if not isinstance(definition,EdgeFlangeOnL):
        raise rejected('invalid_sheet_flange_source','A complete explicit two-bend U definition is required.')
    # Passive material dimensions, not an adopted L body or native target.
    source=definition.source
    return SimpleNamespace(developed_length_mm=definition.developed_length_mm,
        thickness_mm=source.thickness_mm,length_mm=source.length_mm,
        leg_x_mm=source.leg_x_mm,leg_y_mm=source.leg_y_mm,bend_radius_mm=source.bend_radius_mm)


def expected_flat_u_geometry(definition,plane_transform):
    """Anchor the free end of the independently proved horizontal fixed leg."""
    expected=expected_flat_l_geometry(_material_dimensions(definition),plane_transform,'x')
    expected['bend_allowances_mm']=[
        math.pi/2.*(definition.source.bend_radius_mm+definition.source.k_factor*definition.source.thickness_mm),
        math.pi/2.*(definition.bend_radius_mm+definition.k_factor*definition.source.thickness_mm)]
    expected['k_factors']=[definition.source.k_factor,definition.k_factor]
    return expected


def fixed_u_leg_from_face(face,definition,plane_transform,*,flattened=False):
    leg=fixed_l_leg_from_face(face,_material_dimensions(definition),plane_transform,flattened=flattened)
    if leg!='x':
        raise rejected('sheet_flange_fixed_face_unsupported','The complete U-sheet fixed face must bind the original horizontal leg.')
    return leg


def flat_u_body_matches(geometry,expected):
    return flat_l_body_matches(geometry,expected)
