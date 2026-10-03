# SolidWorks MCP — Progress log

## Environment (verified 2026-06-25)

- SolidWorks: **2026 (3DEXPERIENCE R2026x)**, file version 34.2.0.0127, COM ProgID
  `SldWorks.Application`, CLSID `{666aaee2-7a21-40fc-b768-2078840a88c3}`.
- Install dir: `C:\Program Files\Dassault Systemes\SOLIDWORKS 3DEXPERIENCE R2026x\SOLIDWORKS\`.
- Typelibs: `sldworks.tlb` (GUID `{83A33D31-27C5-11CE-BFD4-00400513BB57}`, v34.0),
  `swconst.tlb` (constants).
- Python 3.13.7, venv at `.venv`, `pywin32 312`, `mcp 1.28.0`.

## Milestones

### M0 — Connection ✅
`scripts/probe_connection.py`. Attaches via `GetActiveObject`, reads
`RevisionNumber` (34.2.0), reports active doc.

### M1 — Build + measure ✅
`scripts/m1_block.py`. new part → rectangle on first plane → extrude →
`CreateMassProperty`. Block 40×20×10 mm → volume 8000 mm³, area 2800 mm²,
centre of mass (20,10,5) mm, mass 0.008 kg — all match hand calc exactly.

### M2 — Parametric ✅
`scripts/m2_parametric.py`. Change `D1@BlockExtrude` 10→25 mm → rebuild →
volume 8000→20000 mm³ (ratio 2.5). Proves the parametric loop.

### M3 — Full agent loop via MCP server ✅
`scripts/test_mcp_server.py`. Drives the server over stdio (10 tools):
get_status → new_part → add_box → measure → set_dimension → measure →
bounding_box → export STEP (15.8 KB, valid AP203) + STL → screenshot (valid
isometric render) → close_part. All checks pass.

### M4 — non-circular sweep 🚧
`add_swept_profile(profile, path)`: sweep an arbitrary closed cross-section along a
2D path (rails, gaskets, trim, channels). The hard part the CircularProfile trick
avoided -- a profile plane PERPENDICULAR to the path -- is solved with standard
planes: the profile is drawn on the **Right plane** (3rd RefPlane, normal +X) and
the path on the Front plane MUST start at the origin heading +X, so the path's start
tangent equals the Right-plane normal. Marks (cracked empirically): profile = mark 1,
path = mark 4; InsertProtrusionSwept4 with CircularProfile=False. Verified vs Pappus
(volume = profile_area * path_length): rect 20x10 straight 40 = 8000 (a box, exact);
rect 20x10 along an L (R10) = 200 * 55.708 = 11141.59 (exact). Factored
`_draw_path_on_front` (shared with add_swept_pipe) and `_ref_planes`; the +X-start
rule is a pure, unit-tested guard (`_require_path_starts_along_x`). Limitation: the
path must start along +X (a future version could build a perpendicular plane for an
arbitrary start tangent). Works on this build -- not a mirror-style dead-end.

### M4 — free-form spline extrusion 🚧
`add_extruded_spline(points, depth)`: a smooth CLOSED spline through the given points
(organic/aesthetic outlines -- cams, rounded shapes), extruded like
add_extruded_profile. Via `ISketchManager.CreateSpline2(PointData, SimulateNaturalEnds)`
(dispid 69): PointData is a VT_ARRAY|VT_R8 VARIANT of [x,y,z,...] (same marshalling as
CreatePoint); close the curve by repeating the first point (an OPEN spline refuses to
extrude -- verified). Honest limitation: a spline's area is NOT analytic, so unlike
every other feature its volume can't be hand-calc'd exactly -- verified instead by a
24-point circle approximation converging to pi*r^2*h (n=8:-0.12%, 12:-0.03%, 24:-0.01%).
This is where the project's "hard verifiable signal" softens for free-form geometry.

### M5 — end-to-end 3D-print part ✅
`scripts/m5_demo_bracket.py`. Builds a functional mounting bracket through the full
build->measure->verify loop, asserting volume vs a hand calc after EVERY step:
100x80x8 plate -> Ø16 motor bore -> 4-bolt circle (add_circular_pattern)
-> 4 corner counterbores -> R5 corner fillets -> 30x6 cable slot -> fine STL +
screenshot. All 10 checkpoints matched exactly (final 58297.635 mm^3), bbox
[100,80,8]. This is the whole-toolset validation that drove the 3D-print feature
work; it composes 8 tools into one printable part. Gotcha found + fixed in the demo:
a through slot adds tangent z-parallel edges, so add_fillet(edges="z") must run
BEFORE the slot to round only the 4 box corners.

### M6 — Assemblies ✅
Covered by `tests/test_assembly.py` (self-contained blocks). The room demo script
described below was removed in 0.2.1: it needed private sample parts. Nine tools: new/open/save_assembly, insert_component,
list_components, set_component_transform, add_mate, check_interference,
get_assembly_bounding_box; export/screenshot/rebuild/get_mass_properties/close_part
now serve assemblies too. Demo: three saved parts (a walled room + bed + desk)
composed into one assembly, every placement asserted against the geometry —
assembly bbox 3900x2700x2480, both pieces of furniture standing on y=0, a 50 mm
distance mate to the wall read back from the transform (bed origin x=2790), zero
interfering pairs — plus a SLDASM/PNG/STEP write. Verified visually from a plan
view (bed against the far wall with its gap, desk clear of the door).

Four API facts cracked empirically (all four are load-bearing):
1. **AddComponent5 returns None for a part that is not LOADED.** Each component is
   opened with OpenDoc6(swOpenDocOptions_Silent) first and the assembly
   re-activated with ActivateDoc3 before inserting.
2. **AddComponent5's X/Y/Z do not place the part's origin** — it drops the
   component with its bounding-box CENTRE on that point (inserting the room at
   (0,0,0) gave a transform of (-1950,-1250,-1240)). So `insert_component` always
   writes the position as a transform afterwards, and reads it back to compare.
3. **IMathTransform.ArrayData holds the rotation COLUMN-major**: data[0:3] is the
   first COLUMN, i.e. the transpose of the obvious reading. Pinned by rotating a
   component 90° about Y and checking its box (predicted x'=z, z'=-x matched the
   transposed reading exactly, the row-major reading gave the mirror). Pure
   `_rotation_columns` / `_euler_from_columns` are unit-tested, round-trip and
   gimbal-lock included.
4. **A component's faces come back in COMPONENT coordinates** however the
   component is rotated. So a face selector means the part's own face, which is
   the stable thing to name; the selector is pushed through the transform only
   when a mate is measured back in assembly space.

Mates: `AddMate5` with BOTH entities selected at mark 1, align = swMateAlignCLOSEST
(every component is pre-positioned first, so "closest" is deterministic), and
ErrorStatus checked against swAddMateError_NoError = **1**, not 0. A mate that
builds but resolves to the wrong side is a silent geometry error, so after the
rebuild the result is measured back from the geometry — perpendicular distance
between the two planes for coincident/distance, angle between the normals for
parallel/perpendicular — and rejected if it is not what was asked. Proven by
inserting the bed 90 mm off and 25 mm above the floor and letting the mates move
it. `flip` is real and observable: the same 5 mm distance mate lands a block at
x=45 (clear) or x=35 (reaching in), both genuinely 5 mm apart. Only the four
planar mate types are exposed; concentric/tangent would need a cylindrical
selection the planar face picker cannot produce.

Interference: `IAssemblyDoc.InterferenceDetectionManager` with
TreatCoincidenceAsInterference=False, so a bed standing ON the floor is contact,
not a clash. SolidWorks reports each disjoint overlapping lump separately (a bed
frame pushed into the floor gave 2 x 5,000,000 mm³ — one per rail, exactly
25x2000x100 each), so lumps are summed per component pair and counted as
`regions`. Verified against a hand calc: 5x20x10 overlap = 1000 mm³.

Document type is now checked at the choke points every part builder passes through
(`_first_ref_plane` / `_ref_planes` / `_solid_body`), so a part tool called on an
assembly fails at its own root cause instead of much later inside a sketch.

### Face selection on hollow parts — fixed (2026-09-05)
`_planar_face_by_normal` filtered on the normal and kept whichever face came first,
but a normal does NOT identify a face: a shelled box has several planar faces per
direction (for +Z the outer top AND the cavity floor of the opposite wall), so the
choice was effectively the API's listing order. It now picks the EXTREME along the
direction: outermost by default, innermost with a `:inner` suffix on the selector
(`+y:inner`) — which is also the only way to address the inside of a room wall, so
the M6 mates depend on it. Verified on a closed 2 mm shell of a 40x20x10 block:
outer +Z at z=10, inner at z=2, and the existing on-face guard proves which face
was chosen (a point on the cavity floor is rejected by `+z` with "staat -8.000 mm
buiten het vlak" and accepted by `+z:inner`, removing π·2²·2 = 25.13 mm³).

Two adjacent gaps this exposed, both fixed:
- **A rejected on-face point left the sketch open**, so the very next operation's
  InsertSketch CLOSED it instead of opening one and died on `ActiveSketch is None`
  — i.e. one loud failure broke the following call. The sketch is now closed in a
  `finally` (`_open_face_sketch`), and a missing active sketch raises at its own
  root cause.
- **`IAssemblyDoc.GetBox` is stale until the assembly is rebuilt**: after moving a
  component it still reported the previous extents (a component inserted at
  x=100 still measured from -10). `_bounding_box` rebuilds first for assemblies.
  `get_bounding_box` on an assembly also used to return `null` silently (the
  IPartDoc QI failed and the error was swallowed) — it now measures the assembly.

Tests: **124 green** (was 73). The pure layer gained face-selector parsing, the
column-major rotation array, the Euler round-trip incl. gimbal lock, and a
parametrised check that EVERY MCP tool forwards its own parameters, in order, to
a session method that accepts them (parsed from the source with `ast`, so it
needs no COM). A new `tests/test_assembly.py` covers inserting, placement,
rotation, all four mate types plus flip, interference (apart / touching /
overlapping), the assembly bounding box, save+reopen, the doc-type guards both
ways and the outer/inner face fix; its components are two blocks the fixture
builds and saves with the part tools, so the suite stays self-contained and
hand-calculable. `scripts/m5_demo_bracket.py` re-run after the face-selection
fix: identical 58297.635 mm^3, no regression.

### 3D-print features (2026-06-26)
Demand-driven from the bracket demo (research workflow first; HoleWizard rejected as
locale-fragile, same class as the mirror dead-end):
- **add_counterbore_hole**: deterministic = clearance shank THROUGH_ALL + larger
  coaxial pocket BLIND, two FeatureCut4 cuts on +Z (flush cap-head screws / heat-set
  inserts). Factored `_cut_circle_on_z` (now shared with add_hole, the 3rd use).
  Verified: Ø5 through + Ø10x4 cbore removes 431.97 mm^3.
- **export() STL/3MF resolution**: quality 'coarse'|'fine' (default fine), or explicit
  deviation_mm + angle_deg (Custom). Sets swSTLQuality/Deviation/AngleTolerance on
  ISldWorks before SaveAs3 and RESTORES them after (they are global prefs). Verified:
  fine STL > coarse file size; prefs unchanged after export. Mesh-only (stl/3mf).
- Deferred (researched, ranked lower): countersink (needs a revolve about an axis at
  arbitrary (x,y) -- the one real complication) and emboss/engrave text (font/transform
  fragility, medium ROI).

### Hardening (post-review, 2026-06-25)
Adversarial code-review pass (4 dimensions, findings verified). Applied:
- **Call timeout** in `ComWorker.call` — a blocked COM call (modal dialog) now
  surfaces a readable timeout error instead of wedging the server forever.
- **Mass properties fail loud** if SI units can't be forced (`UseSystemUnits`),
  instead of silently returning wrong-scaled numbers.
- **`set_dimension` reads the value back** after rebuild and reports the applied
  value + an `applied` flag, so a driven/equation dimension that ignores the
  write is visible to the agent.
- **Readable COM errors** (extract `excepinfo` description) and a sketch-result
  check in `add_box` (fail at the root cause, not later at the extrude).
- Removed dead code (`DOC_TYPE_NAMES`, unused doc-type constants,
  `deg_to_rad`/`rad_to_deg`). Re-run: M1/M2/MCP all still green.

### M4 — Cut-extrude (hole) + face selection 🚧
`scripts/m4_hole.py`. Kickoff M3 spec: 40x20x10 block with a centred Ø8
through-hole -> volume 7497.345 mm³ (= block - π·4²·10), matches to machine
precision. Added a reusable `_planar_face_by_normal` selection helper (picks a
face by outward normal, e.g. +Z) and an `add_hole` tool; the MCP end-to-end test
now covers it (11 tools).

Lesson (caught by the screenshot check): a cut sketched on a reference plane
coincident with a face fails for *every* direction/end-condition; sketching on
the actual selected face makes the cut unambiguous. The hole runs along the
add_box depth axis (the +Z profile face), i.e. through the plate thickness.

`scripts/m4_fillet.py` + `add_fillet`: rounds all edges with a constant radius
via `_select_all_edges` (extends the selection layer to edges) + FeatureFillet3.
40x20x10 block, r=2 on all 12 edges -> 7770.36 mm³ (matches the hand estimate
~7760; difference is the corner patches). Verified visually.

Fillet lesson: FeatureFillet3 needs `swFeatureFilletUniformRadius` in Options to
use the single R1 radius; without it the API expects a per-edge Radii array and
returns None.

`scripts/m4_chamfer.py` + `add_chamfer`: 45° chamfer on all edges via
`InsertFeatureChamfer`, reusing `_select_all_edges`. 40x20x10, d=2 -> 7482.67 mm³
(removed 517.33, matches the ~500 estimate). Verified visually.

Chamfer lesson: `swChamferEqualDistance` (16) is a silent no-op here (returns a
feature that removes nothing); use `swChamferAngleDistance` (1) with Width +
45° angle. Caught by the volume check (feature built but volume unchanged).

`scripts/m4_select_edges.py` + `_select_edges(body, selector)`: directional edge
selection for fillet/chamfer. `edges='x'|'y'|'z'` selects straight edges parallel
to that world axis (via start/end vertices; curved/closed edges like a hole's
circle have no vertices and never match). Verified: a 40x20x10 box has exactly 4
edges per axis; r=2 fillet removes 137/69/34 mm³ for x/y/z (proportional to the
40/20/10 lengths). Visually confirmed only the depth edges round for 'z'.

### Hardening (M4 review, 2026-06-25)
Adversarial review of the M4 code (8 findings confirmed). Applied:
- **Off-center hole verified**: a hole at (10,6) lands at COM (20.670, 10.268) =
  the prediction, confirming (x,y) really use add_box coordinates (the centred
  test was symmetric and couldn't catch a mirrored frame).
- **Planar-face guard** in `_planar_face_by_normal` (`ISurface.IsPlane`) and
  **line-edge guard** in `_edge_parallel_to` (`ICurve.IsLine`) — so a cylinder
  left by a hole or an arc left by a fillet is never picked as a sketch base /
  axis edge on composed parts.
- Dropped tangent **propagation** on fillet/chamfer so `edges_filleted/chamfered`
  equals exactly what was selected; tightened the direction tolerance to ~2.6°.
- `_finish_feature` helper (DRY across the 4 builders) now also returns
  `rebuild_ok`, mirroring set_dimension. Full M-suite + MCP test still green.

### M4 — Revolve (cylinder) 🚧
`scripts/m4_cylinder.py` + `add_cylinder`: first revolve-based primitive. Sketches
a radius x height rectangle + a single centerline (the axis at x=0) and calls
FeatureRevolve2 with Dir1Type=blind, Dir1Angle=360°. Ø20 x h20 -> 6283.185 mm³
(= π·10²·20) to machine precision; bbox [20,20,20]. Verified visually.

Revolve lesson: a lone centerline in the sketch is auto-detected as the axis
(UseAutoSelect), so no explicit axis selection is needed. The same plumbing
extends to cones (trapezoid profile) and general profiles.

### M4 — inspection, cone, shell, index selection 🚧
- `list_faces` / `list_edges`: read-only geometry inspection (face normal/area/
  centre via IFace2.GetArea + ISurface.IsPlane; edge type/axis/length/midpoint via
  ICurve.IsLine/IsCircle + vertices). Box → 6 planar faces (2800 mm²), 12 lines.
- **Index edge selection**: fillet/chamfer `edges` now also takes indices ("2,5")
  from list_edges, not just an axis.
- `add_cone` (`scripts/m4_cone.py`): trapezoid-profile revolve; top Ø=0 → full
  cone. Frustum 3665.191, full cone 2094.395 mm³ vs formula.
- `add_shell` (`scripts/m4_shell.py`): InsertFeatureShell to a wall thickness,
  removing a chosen planar face (+x/-x/.../-z) or fully closed. 40x20x10 t=2 →
  open 3392 / closed 4544 mm³. Returns no feature object (build dict inline).
All verified + visual; 18 MCP tools; end-to-end green.

### M4 — toolset expansion for AI-driven design 🚧
A long autonomous run adding the capabilities an AI needs for advanced parts:
- **`add_extruded_profile`** (`m4_profile.py`): extrude any closed polygon
  `[[x,y],...]` (CreateLine loop + FeatureExtrusion3). L-bracket = shoelace area
  1800 × 10 = 18000 mm³. The big unlock beyond box/cylinder/cone.
- **`cut_profile`** (`m4_cut.py`): cut a polygon pocket/slot from the +Z face,
  blind or through. 20×10 pocket -> blind 7200 / through 6000 mm³.
- **`save_part` / `open_part`** (`m4_saveopen.py`): SaveAs3 to .sldprt / OpenDoc6;
  build->save->close->open round-trip preserves volume.
- **`set_material`** (`m4_material.py`): IPartDoc.SetMaterialPropertyName2 (DB=""
  finds the default DB). 6061 Alloy -> 2700 kg/m³, mass 0.0216 kg. Mass props now
  include `density_kg_m3`.
- `scripts/demo_plate.py`: full autonomous design (plate + bore + 6-bolt circle +
  rounded corners), spec-verified + exported.

### M4 — review hardening + pytest suite 🚧
Adversarial review of the toolset code (14 findings). Applied the real ones:
- polygon inputs normalised (`_clean_polygon`: drop coincident/closing dups,
  require >= 3 distinct) shared by add_extruded_profile + cut_profile;
- `set_material` verifies via GetMaterialPropertyName2 name read-back (not a
  density heuristic) + returns rebuild_ok;
- `_cylindrical_face_near` now requires ISurface.IsCylinder + a distance floor;
- `_last_feature_name` skips folders/sketches/fillet/chamfer/shell/patterns so the
  default pattern seed is a real boss/cut/hole;
- `save_part`/`export` verify the file's mtime advanced (no stale-file success);
- linear pattern selects the analysed edge directly (Select4+Mark), not by
  coordinate; shared `_select_planar_face` helper for +Z/face selection.

**Tests** (`tests/`, pytest): two layers. 13 pure unit tests (units, selector/
direction parsing, polygon cleaning) run with no SolidWorks in ~0.02s
(`pytest -m "not solidworks"`); 21 integration tests (marker `solidworks`,
auto-skip if absent) verify every feature's volume against a hand calc. 34/34
green. This replaces running the m4_*.py scripts by hand.

### M4 — holes on any face (model→sketch transform) 🚧
`add_hole_on_face(diameter, face, x, y, z)`: drill through any planar face at a 3D
point. `_model_to_sketch_uv` maps a model point to the face-sketch's 2D frame via
`ISketch.ModelToSketchTransform` + `IMathUtility.CreatePoint`/`MultiplyTransform`.
Key gotcha: `CreatePoint` needs a `win32com.client.VARIANT(VT_ARRAY|VT_R8, [...])`
— a plain Python list is mis-marshalled (garbage). Verified: side holes through
the +X (40 mm) and +Y (20 mm) faces; 36 pytest tests green. Unblocks side holes,
pockets on any face, and bolt circles on cylinder end-faces.

### M4 — disc / round flange 🚧
`add_disc(diameter, thickness)`: a circle extruded along +Z (axis Z, centred at
origin). Chosen over reorienting add_cylinder or generalising circular_pattern:
because the disc's flat faces are +Z/-Z, the existing add_hole (+Z) and
add_circular_pattern (Z-axis) compose directly. **Round flange** = add_disc +
centre bore + bolt hole + circular pattern, verified end to end (Ø80x15, Ø20 bore,
6x Ø10 bolts -> 63617.25 mm³). Also a nice sanity check of the line-edge guard:
add_fillet(edges="z") on a disc correctly finds 0 straight edges and raises.

### M4 — slotted hole (first arc-based sketch) 🚧
`cut_slot(length, width, x, y, angle, depth)`: a straight slot/obround cut on the
+Z face. The first sketch using **arcs** rather than only lines/circles, via
`ISketchManager.CreateSketchSlot(CreationType, LengthType, Width, x1,y1,z1,
x2,y2,z2, x3,y3,z3, CenterArcDirection, AddDimension)`. Empirically nailed (a
throwaway `_debug_slot.py`): CreationType=line(0), LengthType=centre-to-centre(0),
the **first two points are the two end-arc centres**, the **third point sits on the
width side** (its perpendicular offset = W/2), and `Width` drives the slot width
directly. We compute the three points from (centre, angle, length, width):
centres at `centre ± (L/2)·(cosθ,sinθ)`, width point at `centre + (W/2)·(-sinθ,cosθ)`.
Box 40x20x10, L=20/W=10 slot 5 mm deep -> removed `(L·W + π(W/2)²)·d` = 1392.70 ->
6607.30 mm³ (matches hand calc). Cut blind or through via the existing FeatureCut4.
This is the building block for rounded profiles generally.

### M4 — general revolve 🚧
`add_revolved_profile(profile, angle)`: revolve any closed `(radius, height)`
polygon about the axis at r=0 (like add_extruded_profile, but spun instead of
extruded). Generalises the cone's revolve plumbing: reuses `_clean_polygon` +
`_draw_polygon_segments`, draws the profile in the (x=r, y=z) plane on Front, adds
a centreline along the axis spanning the profile's z-range, then FeatureRevolve2.
Guards: no negative radius (can't cross the axis), not all-on-axis, angle in
(0,360]. Verified vs hand calc: cylinder r10/h20 = 6283.19, **ring** (profile
offset from axis, outer10/inner5/h2) = 471.24, frustum = 3665.19, **half** (180°)
cylinder = 3141.59. Unlocks turned shafts, vases, rings/torus cross-sections, and
partial revolves -- the cone/cylinder are now just special cases.

### M4 — swept pipe (first sweep) 🚧
`add_swept_pipe(path, diameter, bend_radius)`: sweep a round profile along a 2D
path on the Front plane -> pipes, tubes, rods, wire, bent frames. The first SWEEP
feature, via `IFeatureManager.InsertProtrusionSwept4` (dispid 256, 20 args). Key
unlock: its **CircularProfile + CircularProfileDiameter** options auto-generate the
round profile perpendicular to the path -- so NO separate profile sketch and no
perpendicular-profile-plane gymnastics. We only build the path sketch, select it
(mark 4 = sweep path; mark 1 failed -> None), and sweep. Sharp polyline corners
can't be swept with a tube, so we **compute the rounded path geometry ourselves**
(`_round_polyline`, pure/unit-tested): each interior corner becomes a tangent arc
of bend_radius (setback = R/tan(θ/2), centre on the bisector at R/sin(θ/2), arc
direction from the turn's cross-product sign), drawn with CreateLine + CreateArc
(centre form, dispid 31). Verified vs Pappus (volume = π(d/2)²·path_length):
straight 50mm Ø10 = 3926.99, L-bend (R10) = 4375.29, U-bend (R8) = 7314.63 -- all
exact. Determinism over the native sketch-fillet API (which needs fiddly per-vertex
sketch-point selection). Path is planar (2D) for now; a 3D path is the next step.

### M4 — loft (blend) 🚧
`add_lofted_solid(profiles, heights)`: blend 2+ closed polygon profiles on parallel
planes stacked along +Z. Via `IFeatureManager.InsertProtrusionBlend` (dispid 16, 17
args). Per-profile a plane: profile 0 on Front, the rest on offset planes via
`InsertRefPlane(swRefPlaneReferenceConstraint_Distance=8, distance_m, 0,0,0,0)`.
Selection (the risk the review flagged, cracked empirically): each profile sketch
selected with **mark 1, Append=True**, in stacking order; InsertProtrusionBlend then
blends them. Verified: 2 squares (40->20 over 30) = **28000.00 exact** (ruled
prismatoid h/6*(a^2+(a+b)^2+b^2), no twist for aligned profiles); coaxial circles
(20->10 over 30) = 21990.4 vs 21991.1 frustum (circle tessellation). Note: 3+
profiles blend SMOOTHLY through intermediates (40->20->40 gave 47657, not the
piecewise 56000) -- only the 2-profile ruled case is exactly hand-calcable.
Two gotchas: (1) **InsertRefPlane's return is a generic dispatch without Select2** --
grab the new plane from the tree (`_last_ref_plane`) instead. (2) circles are
already covered by revolve/cone, so loft's niche is NON-rotational transitions.
Unlike mirror, loft works on this 3DEXPERIENCE build (the blocker there was the
mirror-body API, not ref geometry; later found wrong, see Mirror below). Added `_iter_features` generator (DRY for the
new tree walks: `_profile_feature_names`, `_last_ref_plane`).

### Review-hardening pass (2026-06-26)
Multi-agent adversarial review of cut_slot/add_revolved_profile/add_swept_pipe
(24 findings, 18 confirmed). Fixes applied:
- **`_round_polyline` (critical)**: per-corner radius-fit missed two corners SHARING
  a segment -- their setbacks could sum past the shared length, self-overlapping the
  path; SolidWorks then failed opaquely. Now a 3-pass pure function: compute corner
  fillets, validate adjacent-corner setback sums vs the inter-vertex distance, then
  emit (skipping any zero-length connecting line). Fails fast in pure code.
- **`_round_polyline` (foldback)**: split the collinear guard -- theta~pi (straight
  pass) is skipped, theta~0 (180deg fold-back) now RAISES instead of silently
  flattening the excursion.
- **`add_swept_pipe` (2x high)**: (a) now selects the Front ref plane explicitly
  before InsertSketch (every other builder does; it had relied on default selection
  -> silent wrong-plane risk). (b) captures the path sketch via a before/after
  ProfileFeature-name diff instead of `_last_sketch_name` (robust to pre-existing
  sketches; `_last_sketch_name` removed as dead code).
- Tests: 67 green (was 52). Added pure geometry tests (right/obtuse/acute corners,
  S-chain, overlap+foldback raises, 2-pt-ignores-radius) and integration tests
  (S-bend pipe = both arc dirs end-to-end, revolve guards + 360 boundary, diameter
  guard, 45deg slot through).
API args (InsertProtrusionSwept4 / FeatureRevolve2 / CreateArc / CreateSketchSlot)
were re-checked against the typelib -- no mismatches.

### Flaky test note (2026-06-26)
`test_cut_profile_through` failed ONCE in a full 52-test run (got vol 3000 vs 6000)
but passes in isolation and on re-run -- non-deterministic state bleed under rapid
new_part/close_part cycling. The review's flaky-test hypothesis could NOT be
confirmed statically (no concrete root cause), so NO speculative fix was applied to
new_part/close_part. Pre-existing; the `part` fixture already closes each doc.
Revisit only with a reproduction; no sleep/poll band-aids.

### On-face fail-fast guard (2026-06-26)
`add_hole_on_face` / `cut_profile_on_face` document that the supplied (x,y,z) must
LIE on the chosen face, but nothing enforced it: `_model_to_sketch_uv` projected the
point onto the face-sketch plane and dropped the out-of-plane component, so a point a
few mm off the face was silently relocated to the projected spot (an error-masking gap
vs CLAUDE.md fail-fast). Verified empirically (throwaway script): ModelToSketchTransform's
`local[2]` is **exactly 0.0** for an on-face point and **equals the off-face distance**
otherwise (a 5 mm off-face point gave -5.000e-3 m with identical u,v), and the old code
drilled the hole anyway. Fix: `_model_to_sketch_uv` now takes `face` and raises a Dutch
`SolidWorksError` naming the face, point (mm) and measured offset when `abs(local[2])`
exceeds `_ON_FACE_TOLERANCE_MM = 1e-3` (1 um -- ~5000x below a real mistake, absorbs
transform round-off). Tests: 73 green (added off-face raises for both callers; on-face
happy paths unchanged).

## Key API findings (this build)

These were read from the installed typelib (`scripts/introspect_api.py`), not
guessed — and several differ from common web docs:

- `swDefaultTemplatePart = 8` (not 9, as widely stated online).
- `GetActiveObject` returns a dispatch whose `GetTypeInfo()` raises
  `TYPE_E_ELEMENTNOTFOUND` → `EnsureDispatch`/`CastTo` fail → **early binding via
  manual wrapping in generated classes is mandatory** (see `binding.py`).
- `IModelDoc2` has **no** `GetBox`. Part bounding box comes from
  `IPartDoc.GetPartBox(NoConversion=True)` (returns metres).
- `RevisionNumber` resolves as a property under late binding, a method under
  early binding — handle both (`callable` check).
- `FeatureManager.FeatureExtrusion3` takes 23 args; types verified
  (bool/int/double) against the typelib.
- Plane selection by name (`"Front Plane"`) is language-dependent; we walk the
  feature tree for `GetTypeName2() == "RefPlane"` instead.
- `swDefaultTemplateAssembly = 9`; `swAddMateError_NoError = **1**` (not 0, so a
  falsy check on the status would read a success as a failure).
- `IAssemblyDoc.AddComponent5` returns None unless the part is already loaded, and
  its X/Y/Z place the component's bounding-box CENTRE, not the part origin.
- `IMathTransform.ArrayData` stores the 3x3 rotation COLUMN-major (data[0:3] is
  the first column) — the transpose of the obvious reading.
- `IComponent2.GetBox` follows the component transform, but `IAssemblyDoc.GetBox`
  is stale until the assembly is rebuilt.

### M4 — Linear pattern 🚧
`scripts/m4_pattern.py` + `add_linear_pattern`: repeat a feature N times along
+x/-x/+y/... via FeatureLinearPattern. Box + hole -> 3 holes = 6492.036 mm³.
Selection marks (found empirically): **direction edge = mark 1, seed feature =
mark 4** (via SelectByID2 with coords/name). The pattern follows the edge's
p1->p2 direction; we flip it to match the requested axis. seed defaults to the
last feature added (tree walk).

### M4 — Circular pattern (bolt circle) 🚧
`scripts/m4_circular.py` + `add_circular_pattern`: repeat a feature N times around
an axis = the cylindrical face nearest a given centre (so a centre hole's wall is
the axis — no reference-axis creation needed). Plate + centre hole + 6 bolt holes
= 13800.885 mm³. Lessons: select the axis face by ITERATION + Select4 with a Mark
via SelectionManager.CreateSelectData (SelectByID2-by-coordinate did NOT grab the
internal cylinder); marks axis=1, seed=4; FeatureCircularPattern's Spacing is the
PER-INSTANCE angle (360/count), not the total. This Select4+Mark machinery is now
reusable for mirror and other selection-heavy features.

### M4 — Equations 🚧
`scripts/m4_equation.py` + `set_equation`: add a global equation via
IEquationMgr.Add2(count, eq, solve=True). '"D1@BlockExtrude" = 2 * 12.5' drives
depth to 25 -> 20000 mm³ (expression evaluated). Persists a relation, unlike the
one-off set_dimension.

### M4 — Ribs ✅
`add_rib(start, end, toward, thickness, z)`: a straight rib in a plane parallel to
Front at z (offset plane via InsertRefPlane, hidden afterwards like the loft's).
`IFeatureManager.InsertRib(Is2Sided=True, ..., IsNormToSketch=False)` = "parallel
to sketch": the line is extended to the part and the rib is a slab centred on the
plane. Three API facts, cracked empirically:
1. **InsertRib returns void** — the new feature is found in the tree (type "Rib").
2. **The material grows to the RIGHT of start->end** (viewed from +Z);
   ReverseMaterialDir flips it. `toward` decides via a cross product
   (`_rib_material_reversed`, pure/unit-tested), so the end order doesn't matter.
3. **The wrong side fails SILENTLY** — no feature, no error — so add_rib checks
   for the new Rib feature and fails loud.
Verified: L-bracket 60x60x5, 40 deep (23000) + gusset legs 30/30, 4 thick at z=20
-> 24800 exactly (+450*4), for both end orders.

### M4 — Threads ✅
`add_thread(size, x, y, z, length, internal)`: SolidWorks' own Thread feature via
`IFeatureManager.CreateDefinition(swFmSweepThread = 87)` -> IThreadFeatureData ->
CreateFeature. CreateDefinition does work on this build for the thread (87); it
returned None for the mirror types (4 swFmMirrorSolid, 7 swFmMirrorPattern), so
the mirror dead end stands.
- Type 'Metric Die' / 'Metric Tap' resolves to the .sldlfp library path (empty
  string if missing); `ISldWorks.GetConfigurationNames(path)` lists the valid
  sizes (69, e.g. 'M10x1.0', 'M10x1.25', 'M10x1.5', 'M3x0.5').
- **An unknown size is accepted silently** (M10x1.3 -> a 19 mm^3 garbage cut), so
  the size is validated against that list.
- **A tapped thread follows the hole**: an Ø8.5 hole gives a different (oversized)
  thread than the Ø8.376 ISO basic minor diameter, so internal threads require
  D1 = D - 1.0825*P.
- Verified by hand: groove = ISO basic trapezoid swept helically, volume per mm =
  area * 2*pi*r_centroid / P. Die M10x1.5 x 20 mm: 267.969 vs 267.966; tap x 12 mm:
  120.375 vs 120.449 (the tap profile is ~0.06% leaner).
- Dead end first: a hand-built helix (IModelDoc2.InsertHelix, right-handed with
  Clockwised=False, start at +X) + sweep. Small profiles sweep, but the ISO
  trapezoid fails for every option tried (cut/boss, merge, turns, twist, path
  alignment, helix radius); cause not found. The native Thread feature replaced it.

### Mirror ✅ (2026-10-02; shelved 2026-06 on a wrong diagnosis)
The June verdict ("InsertMirrorFeature2 returns None, the call is the snag") was
wrong. `IFeatureManager.InsertMirrorFeature2(BMirrorBody, False, BMerge, False,
swFeatureScope_AllBodies = 0)` works, with selection marks features = 1, mirror
plane = 2, body = 256 (via ISelectData); SelectByID2 or IFeature.Select2, in
either order. The old IPartDoc.MirrorFeature / InsertMirrorFeature do nothing.
What really goes wrong, verified:
- A copy that lands outside the part (an add_box spans x 0..w, so mirroring
  about the Right plane puts the copy at negative x) still gives a Mirror
  feature, with warning 1 and no geometry; rebuild reports success. A seed on
  the plane, whose copy lies on itself, gives the same warning.
- A body mirror whose copy does not touch the original returns None.
- Offset planes: InsertRefPlane(Distance = 8, |offset|) goes along the base
  plane's normal (+z / +y / +x for Front / Top / Right); OptionFlip (256) for a
  negative offset. Its distance is the dimension D1@PlaneN, drivable by an
  equation, e.g. half the block's width.
- Mirrored copies follow their seeds: a resized seed hole resizes its copy.
- `IFeatureManager.CreateDefinition` still returns None for the mirror ids
  (swFmMirrorSolid = 4, swFmMirrorPattern = 7); it is not the route.

### Fully defined sketches ✅
Every tool constrains its sketch (`sketch_constraints.py`: a pure planner plus a
COM executor); the `part` test fixture fails any test that leaves a sketch
under-defined. Verified API facts, each from a live spike:
- `ISketch.GetConstrainedStatus()`: 2 = under, 3 = fully, 4 = over
  (swConstrainedStatus_e).
- Relations via `ISketch.RelationManager.AddRelation(entities, swConstraintType_e)`
  with a `VT_ARRAY|VT_DISPATCH` VARIANT: it returns the relation (None = refused).
  The string API `SketchAddConstraints` returns void; only `sgHORIZONTAL2D`-style
  names work there, so a wrong name fails silently.
- Dimensions: select the entities, then `AddHorizontalDimension2` /
  `AddVerticalDimension2` / `AddDiameterDimension2` (the input-value popup is
  already off, `swInputDimValOnCreate`). Rename via `IDimension.Name`;
  `GetNameForSelection()` gives `width@Sketch1`, which `set_dimension` takes.
- The origin, language-independently: the `OriginProfileFeature`'s sketch point.
  Dimensions to it work from any sketch plane (SolidWorks projects it).
- A 0 mm dimension is impossible: a point on an origin axis gets
  `HORIZPOINTS`/`VERTPOINTS` (25/26) with the origin instead.
- Lines drawn with `AddToDB` still share end points; a centreline drawn onto
  profile corners may keep separate points, so coincident duplicates are tied.
- Each dimension re-solves the sketch: quadratic, 40 points 15 s, 120 points 90 s.
  Pausing `ISketchManager.AutoSolve` and `DisplayWhenAdded` halves it. Hence the
  fixed fallback above 24 points.
- `Fix` on a line or arc still lets its end points slide along it (an open path
  stays under-defined); fixing every point (ends and arc centres) works. A spline
  is fixed as a whole.
- `CreateSketchSlot(..., AddDimension=False)`: constrain the construction
  centreline's ends plus one end arc's diameter; the slot's own relations do the
  rest.

### Hole Wizard ✅ (2026-09-27)
The earlier "locale-fragile" verdict (3D-print features, above) was wrong:
`IFeatureManager.HoleWizard5` takes enums (hole type, standard, fastener type)
and standard size strings (`M3`); only the feature names it generates are
localized, and nothing depends on them. `add_hole_wizard` uses it for ISO holes.
Verified facts:
- Placement: select the face at the model point, `SelectByID2("", "FACE", x, y, z)`
  (SolidWorks' own example). The hole lands ~0.04 mm off the point, in a position
  sketch (a sub-feature with one point) that is under-defined. Edit that sketch
  and dimension the point from the origin with the exact target values.
- The feature walk (`FirstFeature`/`GetNextFeature`) does not visit that sketch;
  check sub-features too (`_under_defined_sketches` does now).
- Value1..Value12 (-1 = the standard's value) are fragile per type: a plain hole
  through all fails unless the unused values are 0; a tapped hole given zeros
  cuts garbage (3345 mm^3 for an M3). Screw fit (close/normal/loose = 0/1/2) is
  Value1 for a plain hole, Value4 for counterbore/countersink.
- Tapped holes: CosmeticThreadType 0 (none) mills the threaded length at the
  MAJOR diameter ("remove thread"); 1 keeps the tap drill. `Diameter` overrides
  the tap drill, which lets a modeled Thread feature follow at the ISO minor.
- The Hole Wizard has no modeled thread (API: only cosmetic types; the docs list
  tap drill / cosmetic thread / remove thread).
- Standard values (ISO, SolidWorks tables): M3 clearance 3.2/3.4/3.6; counterbore
  for ISO 4762 Ø6.5 x 3.4; countersink for ISO 10642 Ø6.72 x 90°; tap drill 2.5,
  thread depth 2 x D; blind holes end in a 118° point, depth from the surface.
- Thread feature ends: the groove matches ISO exactly per mm, but its ends vary
  by up to ~0.5 mm^3 for M4 (a thread run out of a through hole loses 0.34).

### Mesh tools ✅ (2026-09-27)
`mesh_tools.py` (pure Python) reads binary/ASCII STL and 3MF (component files and
transforms, units; `frame='build'` adds the build-item placement) and slices it
into closed loops. Checked on the Bosch adapter's MakerWorld 3MF: the socket
section at y = -10 is 1158.1 mm^2 in the object frame and at z = 50 in the build
frame, as the adapter's own check found. `compare_with_mesh` exports the part as a
fine STL with `swSTLDontTranslateToPositive` (toggle 71) set, so it stays in model
coordinates, and restores the preference.

### Feature history ✅ (2026-10-02)
`list_features`, `delete_feature` and `suppress_feature`. Verified facts:
- The feature walk starts with the folders (CommentsFolder, DocsFolder,
  SurfaceBodyFolder, SolidBodyFolder, EnvFolder, DetailCabinet, EqnFolder,
  MaterialFolder), the three default RefPlanes and the OriginProfileFeature;
  everything after the origin is the modelling history. A sketch is visited just
  before the feature that absorbs it, and again as that feature's sub-feature.
- `FeatureByName` lives on IPartDoc, not on the early-bound IModelDoc2.
- `IFeature.GetChildren()` gives the direct dependents: a block's are the sketch on
  its face, the cut and the fillet; an absorbed sketch's child is its feature.
- `IModelDocExtension.DeleteSelection2`: swDelete_Absorbed (2) takes the absorbed
  sketch along, swDelete_Children (1) every dependent. Without Children the
  dependents stay, broken: the cut's sketch shows a warning and the cut an error
  (`GetErrorCode2()` = (1, warning), swFeatureErrorUnknown), and SolidWorks dropped
  the fillet entirely.
- `SetSuppression2(swSuppressFeature=0, swThisConfiguration=1, None)` suppresses
  the dependents too (absorbed sketches stay unsuppressed). swUnSuppressFeature (1)
  brings back only the feature; swUnSuppressDependent (2) its dependents too.
- `IsSuppressed2(1, None)` returns a one-element tuple, `GetErrorCode2()` a
  (code, is_warning) pair. An empty or fully suppressed part measures volume 0.

### Rounded polygon corners ✅ (2026-10-02)
`corner_radii_mm` on the polygon tools uses SolidWorks' own sketch fillets on
the fully defined polygon. Verified facts:
- `ISketchManager.CreateFillet(radius, swConstrainedCornerKeepGeometry = 1)`
  with the corner points (or the two lines) selected: the corner stays as a
  virtual sharp, so its dimensions and relations stay and the sketch stays fully
  defined. With DeleteGeometry (2) the corner dimensions go and it is
  under-defined.
- Each call adds a driving radius dimension (a RADIUS relation, type 3, whose
  `ISketchRelation.GetDisplayDimension` gives it) and two TANGENT relations per
  arc. Several corners selected in ONE call get one radius dimension plus EQUAL
  relations (type 14), like the UI. A radius dimension added on top of that is
  only driven (reference), so `set_dimension` would do nothing.
- A radius too big for its edges returns None and leaves the sketch untouched;
  the tool checks the setbacks (r / tan(angle / 2)) itself first, for a message
  naming the edge.
- A rounded window cut through all from the Right or Top plane measures
  0.0007 mm^2 per mm of depth short of the hand calculation, at every mass
  property accuracy level, although its sketch is exact and a boss from the same
  profile on the Front plane measures exactly.

### STEP / Parasolid import ✅ (2026-10-02)
`open_part` imports neutral files with `ISldWorks.LoadFile4(path, "r",
GetImportFileData(path), 0)`, which returns (document, errors). Verified:
- With 3D Interconnect on (the default here) the import is one feature of type
  `MBimport` named `<file>.step<1>`, linked to the file; tools add features on
  top of it, fully defined, and volumes come out exact.
- No dialog appears: import diagnostics run automatically
  (swImportAutoRunImportDiagnostics = True here).
- An assembly STEP opens as an assembly plus one `<name>.step.sldprt` document
  per component; `CloseDoc` on the assembly closes them all.
- With 3D Interconnect on, an imported assembly has ONE top-level component: a
  wrapped sub-assembly `<name>.step` holding the parts, so list_components and
  add_mate cannot reach them. swImportDissolveTopLevelAssemblyOnOpen (701) does
  not change that; switching swMultiCAD_Enable3DInterconnect (691) off for the
  call gives a classic import with the parts as top-level components in place.
  `open_assembly` does that and restores the setting.

### Text on a face ✅ (2026-10-02)
`add_text_on_face` (the emboss/engrave text deferred in June). Verified facts:
- `IModelDoc2.InsertSketchText(x, y, 0, text, swTextJustificationLeft = 1, 0, 0,
  100, 100)` in the open face sketch returns the ISketchText; its point is the
  text's lower-left corner. The format comes from `GetTextFormat` (default
  Century Gothic, 3.5 mm here): set `CharHeight` / `TypeFaceName`, then
  `SetTextFormat(False, format)`.
- The sketch then holds one point, the insertion point, and is under-defined;
  dimensioning that point from the origin (SketchDefiner.place_point) makes it
  fully defined, and changing that dimension moves the text.
- An unknown font name is kept and read back as given, but the letters come out
  in a fallback (here Arial): checked against `win32gui.EnumFontFamilies`.
- Engraving and embossing the same text cut and add the same letter area
  (32.86 mm^2 for 'V1.2', 8 mm, within 0.005).
- Orientation (box faces, read from outside, measured by the letter tops): the
  text runs along the face sketch's +u. Upright on +z (along +x, up +y) and -y
  (along +x, up +z); on +x it runs down (-z), on -x up (+z), on +y it is upside
  down. Three ways to turn it failed: `ITextFormat.Escapement` (radians, read
  back as set) moves and merges the letters unpredictably at +/-90 deg; text
  inserted with a construction line selected keeps the sketch's direction (the
  line does make the sketch fully defined); `IModelDocExtension.RotateOrCopy`
  with the text segment selected leaves it unchanged. Open: upright text on
  any face.

### Selftest ✅ (2026-10-02)
`solidworks-mcp --selftest` runs `selftest.CHECKS` on the COM worker, each on a
document of its own. Facts found on the way:
- On 3DEXPERIENCE R2026x the default part template preference is the name
  `~BLANK_PART_TEMPLATE.prtdot`, not a file, so `new_part` falls back to
  `NewPart()`; the assembly template is a real file under
  `%LOCALAPPDATA%\DassaultSystemes\CATTemp\...\Templates\3DEXPERIENCE`.
- `ISldWorks.GetCurrentLanguage()` gives e.g. `english`; a document's length
  unit is `IModelDocExtension.GetUserPreferenceInteger(swUnitsLinear = 47, 0)`
  (swLengthUnit_e). Tools work in SI, but equations are typed in these units.
- An editable install keeps the package metadata of the version it was
  installed at (here 0.1.0, without Project-URLs): reinstall it after changing
  `[project]` in pyproject.toml.

### Quadruped wishes, round 1 ✅ (2026-10-03)

Views and zoom for `screenshot`, exact component boxes, `measure_distance`,
`read_sketch`, `extrude_sketch` / `cut_sketch`, and planes by name. Verified:

- `IComponent2.GetBox` and `IAssemblyDoc.GetBox` are the component's own box
  turned with it: a 20 mm disc turned 45 degrees about Z reads 28.28 wide.
  `IBody2.GetExtremePoint(dx, dy, dz)` returns `(True, x, y, z)` in part
  coordinates; six calls per body give the exact box.
- A part inside a sub-assembly has a `Transform2` relative to the TOP assembly.
  `GetChildren()` is `()` for a part; a sub-assembly and a suppressed component
  have no `GetBodies2`. Setting a component lightweight is refused while its
  part is loaded (`SetSuppression2` leaves state 2), so that path has a unit
  test with a fake instead.
- `IMeasure` on two selected components gives `Distance` (m); when they touch
  or overlap it gives `Distance = -1` and `IsIntersect = True`.
- `ISurface.EvaluateAtPoint` returns the normal first. It points INTO the
  material when `IFace2.FaceInSurfaceSense()` is True, out of it when False
  (8 probes: planes and cylinders, a disc and a hole, both senses).
- `ShowNamedView2("", id)`: front 1, back 2, left 3, right 4, top 5, bottom 6,
  iso 7. `IModelView.Orientation3` maps model to view: the axis facing the
  viewer maps to (0, 0, 1). `ViewZoomTo2` takes two corners in metres;
  `Scale2` grows accordingly (40 mm part fitted 1.51, a 10 mm box 21.6).
- `FeatureExtrusion3`'s Dir flips a boss; `FeatureCut4` with Dir False cuts
  AGAINST the sketch normal: into the part from a face, away from a box
  standing on the Front plane (there it needs Dir True).
- `ISketch.ModelToSketchTransform.Inverse()` maps sketch points back to model
  coordinates; checked on a circle on the +x face.
- `CreateCornerRectangle` adds two construction diagonals on this install (a
  user setting), so sketch readers must skip construction geometry.

## Next

- Assemblies: component patterns, in-context features and configurations are all
  still out of scope; mates are limited to planar faces (concentric/tangent need
  a cylindrical selection the face picker cannot produce).
- Rebuild errors: `list_features` names the failing feature, but SolidWorks mostly
  reports code 1 (unknown), so a readable cause is still missing.
- Drawings and Simulation (FEA) remain untouched.

## Notes

- `OpenDoc6` on a document that is already open returns it but leaves the
  active window as it was. Sketching in a document that is not the active one
  fails at the first relation (`AddRelation` returns None). `_require_model`
  therefore activates the current document (`ActivateDoc3`,
  swDontRebuildActiveDoc) when SolidWorks shows another one.
- Standalone scripts run single-threaded (no COM worker needed); the server
  pins COM to one worker thread.
- Repeated `--keep-open` runs leave untitled parts (Part1, Part2, …) open in
  SolidWorks; harmless, close them manually.
