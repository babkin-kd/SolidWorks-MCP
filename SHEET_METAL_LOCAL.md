# Local sheet-metal extension

Legacy development port in this fork: `0.14.0+sheetmetal.3`, based on upstream 0.14.0.
The new `2.0.0.dev1` entry point currently exposes the v2 job contract; these
legacy CAD tools have not yet been migrated into its catalog.
The verification described below applies to the preserved v1 installation.
Native validation of the new port is pending. Application API v2 is planned
in [PLAN.md](PLAN.md); this intermediate port still exposes the legacy tools.

Installed local version: `0.13.0+sheetmetal.2`, based on hjbaard/SolidWorks-MCP
0.13.0. This is a local extension, not an upstream published release. Tested
with SOLIDWORKS Premium 2023 SP2.1 (revision 31.2.1).

## Tools

| Tool | Purpose |
| --- | --- |
| `add_sheet_metal_base` | Closed XY polygon → native flat base flange |
| `add_sheet_metal_profile` | Open XY polyline → native bent L/U/Z base flange |
| `add_sheet_metal_edge_flange` | One native edge flange with length, direction and gap |
| `convert_to_sheet_metal` | Existing uniform-thickness body → native Insert Bends |
| `get_sheet_metal_info` | Actual thickness, radius, K-factor, body bounds and flat-pattern state |
| `set_sheet_metal_flattened` | Flatten/refold the current configuration and verify it |
| `export_sheet_metal_dxf` | Native flat-pattern DXF, with optional bend lines/sketches |

All builders use the existing dedicated COM thread and guarded feature rollback.
Geometry and source sketches are native and editable; no macro or arbitrary code
execution tool is exposed. Generated bend-line/bounding-box sketches are owned by
SolidWorks and may be listed as under-defined by the original history tool.

## Examples

After `new_part`, a rectangular sheet:

```json
{"points_mm":[[0,0],[80,0],[80,40],[0,40]],"thickness_mm":2,"bend_radius_mm":2,"k_factor":0.5}
```

After `new_part`, a U bracket with outer dimensions 80 × 25 × 40 mm:

```json
{"points_mm":[[0,25],[0,0],[80,0],[80,25]],"depth_mm":40,"thickness_mm":2,"bend_radius_mm":2,"k_factor":0.5,"reverse_thickness":true}
```

Profile coordinates describe virtual sharp corners on one material surface.
In SolidWorks 2023, false puts thickness on the right of the directed polyline,
true on the left (verified with the 800x600 hopper U-half). For a U traced down,
right, then up, true keeps the thickness inside the supplied outer profile.
Returned body bounds are the authority for outside dimensions. The closed sheet
uses `reverse_thickness=true` to grow along +Z, false along -Z.

For the previously created extruded bracket, convert using `fixed_face="+y:inner"`.
Thickness is inferred from the existing body. Closed shells need rip cuts first;
arbitrary thick solids, multibody conversion, and conical bends are outside this
conversion tool's scope.

Use `set_sheet_metal_flattened(flattened=true)` then false to fold again.
For perimeter folds and inward returns use `add_sheet_metal_edge_flange` on
current zero-based `list_edges` indices, resolving the next edge after every
operation. It uses material-inside positioning and outer-virtual-sharp length.
The second inward return on the outside top wall edge uses `flip=true`.
SolidWorks generates and controls the flange profile sketches; these can also
be reported as under-defined by the original history tool.
Save the native `.SLDPRT` before `export_sheet_metal_dxf`. Export requires one
sheet-metal body and one flat pattern. `overwrite` is false by default; output is
committed only after a successful export and restoration of the flat-pattern state.

The K-factor is a supplied modelling assumption. Set it to the value calibrated
for the intended material, tooling and bend process before using a DXF in production.

## Activation and recovery

Codex must reconnect the `solidworks` MCP after installation to discover the new
tools; restarting Codex accomplishes this. SolidWorks itself can remain open.

Original edited files are backed up under
`local-backups/before-sheet-metal-2026-10-09`. The extension lives in
`src/solidworks_mcp/sheet_metal.py`, the tool registrations in `server.py`.
Reinstall this local package when changing it; the installed environment is not
editable. Updating from upstream without preserving the extension would remove it.

## Verification

`tests/test_sheet_metal.py` includes pure input validation and real SolidWorks
geometry checks: base-sheet dimensions, native bend radius/K-factor, analytic
flat length, conversion, flatten/refold, unsaved export rejection, DXF export in
both states and protection of existing files. A separate MCP stdio smoke run
verifies discovery and calls the new tools through the actual transport.
