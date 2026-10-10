"""Revision primitive for the working native sheet-state domain; no MCP tool."""

import hashlib

from .jobs import _json


def flat_state_revision(capture):
    """Bind the complete closed CAD capture, not redundant mass round-off.

The full material BREP, tree/drivers, parameters, fixed-face reference, controls
and native dimension revision are retained. Independent mass/area values must
still be tolerance-checked at capture/postcondition boundaries; they are not
exact native identity or authoritative geometry and cannot enter an exact hash.
"""
    payload={key:value for key,value in capture.items() if key not in ('volume_mm3','area_mm2')}
    return 'rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
