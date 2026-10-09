"""Native sheet-metal operations, tested against SolidWorks 2023 (revision 31).

Uses the session's COM apartment, feature rollback and language-independent
selection helpers. No macros, shell commands or arbitrary code tool are exposed.
"""

import math
import os
import tempfile

import pythoncom
import win32com.client

from . import binding
from .constants import SW_SUPPRESS_FEATURE, SW_THIS_CONFIGURATION, SW_UNSUPPRESS_DEPENDENT
from .errors import SolidWorksError
from .units import mm_to_m, m_to_mm


def positive(value, label):
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise SolidWorksError(f"{label} must be finite and > 0.")


def check_bend_parameters(radius_mm, k_factor):
    positive(radius_mm, "bend_radius_mm")
    if not isinstance(k_factor, (int, float)) or not math.isfinite(k_factor) or not 0 <= k_factor <= 1:
        raise SolidWorksError("k_factor must be finite and between 0 and 1.")


def profile_points(points_mm, closed):
    """Reject ambiguous/self-intersecting sketches before touching the document."""
    if not isinstance(points_mm, (list, tuple)):
        raise SolidWorksError("points_mm must be a list of [x, y] points.")
    points = []
    for point in points_mm:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise SolidWorksError("Every profile point must have exactly two coordinates [x, y].")
        if any(not isinstance(c, (int, float)) or not math.isfinite(c) for c in point):
            raise SolidWorksError("Profile coordinates must be finite numbers.")
        points.append(tuple(float(c) for c in point))
    if closed and len(points) > 1 and points[-1] == points[0]:
        points.pop()
    if len(points) < (3 if closed else 2):
        raise SolidWorksError("A sheet needs at least 3 points; an open profile needs at least 2.")
    if len(set(points)) != len(points):
        raise SolidWorksError("Profile points must be distinct; an open profile cannot close on itself.")
    segments = list(zip(points, points[1:] + ([points[0]] if closed else [])))
    if any(math.dist(a, b) < 1e-6 for a, b in segments):
        raise SolidWorksError("Profile edges must be at least 0.000001 mm long.")
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    def on_segment(a, b, p):
        return abs(cross(a, b, p)) < 1e-9 and all(min(a[i], b[i])-1e-9 <= p[i] <= max(a[i], b[i])+1e-9 for i in (0, 1))
    for i, (a, b) in enumerate(segments):
        for j, (c, d) in enumerate(segments[i+1:], i+1):
            if j == i+1 or (closed and i == 0 and j == len(segments)-1):
                continue
            ac, ad, ca, cb = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
            if (ac*ad < 0 and ca*cb < 0) or any((on_segment(a,b,c), on_segment(a,b,d), on_segment(c,d,a), on_segment(c,d,b))):
                raise SolidWorksError("The profile must not self-intersect or touch itself.")
    if closed and abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in segments)) < 1e-9:
        raise SolidWorksError("The sheet outline must have nonzero area.")
    return points


class SheetMetalMixin:
    def _sheet_features(self):
        """Include subfeatures (SheetMetal can live in a SheetMetalFolder)."""
        seen = set()
        def walk(feature):
            if feature.Name in seen:
                return
            seen.add(feature.Name)
            yield feature
            for child in self._sub_features(feature):
                yield from walk(child)
        return [candidate for feature in self._iter_features() for candidate in walk(feature)]

    def get_sheet_metal_info(self) -> dict:
        self._require_part()
        features = self._sheet_features()
        parameters, flat_patterns, errors = [], [], []
        for feature in features:
            kind = feature.GetTypeName2()
            suppressed = self._is_suppressed(feature)
            if kind == "SheetMetal" and not suppressed:
                data = binding.wrap(feature.GetDefinition(), self._mod.ISheetMetalFeatureData)
                allowance = binding.wrap(data.GetCustomBendAllowance(), self._mod.ICustomBendAllowance)
                parameters.append({"feature": feature.Name, "thickness_mm": m_to_mm(data.Thickness),
                                   "bend_radius_mm": m_to_mm(data.BendRadius),
                                   "bend_allowance_type": int(allowance.Type) if allowance else None,
                                   "k_factor": float(allowance.KFactor) if allowance and allowance.Type == 2 else None})
            if kind == "FlatPattern":
                flat_patterns.append({"feature": feature.Name, "flattened": not suppressed})
            code, warning = feature.GetErrorCode2()
            if code and not warning and not suppressed:
                errors.append({"feature": feature.Name, "code": int(code)})
        bodies = [{"name": body.Name, "is_sheet_metal": bool(body.IsSheetMetal()),
                   "bounding_box_mm": self._body_box(body)} for body in self._part_bodies()]
        return {"ok": True, "is_sheet_metal": bool(bodies) and all(b["is_sheet_metal"] for b in bodies),
                "parameters": parameters, "flat_patterns": flat_patterns, "bodies": bodies,
                "feature_errors": errors}

    def _checked_sheet_info(self):
        info = self.get_sheet_metal_info()
        if not info["is_sheet_metal"] or not info["parameters"] or not info["flat_patterns"]:
            raise SolidWorksError("SolidWorks did not produce native SheetMetal and FlatPattern features.")
        if info["feature_errors"]:
            raise SolidWorksError(f"Sheet metal failed to rebuild: {info['feature_errors']}.")
        return info

    def _create_sheet_base(self, points_mm, thickness_mm, bend_radius_mm, k_factor,
                           closed, depth_mm, reverse_thickness, name):
        positive(thickness_mm, "thickness_mm")
        check_bend_parameters(bend_radius_mm, k_factor)
        points = profile_points(points_mm, closed)
        if not closed:
            positive(depth_mm, "depth_mm")
        model = self._require_model()
        self._require_part()
        if self._part_bodies():
            raise SolidWorksError("Create a sheet-metal base in an empty part; call new_part first.")
        plane = self._first_ref_plane()
        model.ClearSelection2(True)
        if plane is None or not plane.Select2(False, 0):
            raise SolidWorksError("Could not select the first reference plane.")
        sk = binding.wrap(model.SketchManager, self._mod.ISketchManager)
        sk.InsertSketch(True)
        try:
            lines = self._draw_polyline(sk, [(mm_to_m(x), mm_to_m(y)) for x,y in points], closed=closed)
            sketch = self._define_sketch(sk, lines)
        finally:
            model.ClearSelection2(True)
            sk.InsertSketch(True)
        fm = binding.wrap(model.FeatureManager, self._mod.IFeatureManager)
        allowance = binding.wrap(fm.CreateCustomBendAllowance(), self._mod.ICustomBendAllowance)
        allowance.Type = 2  # swBendAllowanceKFactor
        allowance.KFactor = k_factor
        feature = binding.wrap(fm.InsertSheetMetalBaseFlange2(
            mm_to_m(thickness_mm), reverse_thickness, mm_to_m(bend_radius_mm),
            mm_to_m(depth_mm) if not closed else 0.0, 0.0, reverse_thickness if closed else False,
            0, 0, 1, allowance, False, 2, 0.0001, 0.0001, 0.5, True,
            False, True, True), self._mod.IFeature)
        if feature is None:
            raise SolidWorksError("SolidWorks refused the base flange; check profile, bend radius and thickness.")
        result = self._finish_feature(feature, name, **sketch)
        result["sheet_metal"] = self._checked_sheet_info()
        return result

    def add_sheet_metal_base(self, points_mm: list, thickness_mm: float,
                            bend_radius_mm: float = 2.0, k_factor: float = 0.5,
                            reverse_thickness: bool = True, name: str = "SheetBase") -> dict:
        """Closed polygon on Front XY; true grows along +Z, false along -Z."""
        return self._create_sheet_base(points_mm, thickness_mm, bend_radius_mm, k_factor,
                                       True, None, reverse_thickness, name)

    def add_sheet_metal_profile(self, points_mm: list, depth_mm: float, thickness_mm: float,
                               bend_radius_mm: float = 2.0, k_factor: float = 0.5,
                               reverse_thickness: bool = False, name: str = "SheetProfile") -> dict:
        """Open XY polyline, with native rounded bends, extended along +Z."""
        return self._create_sheet_base(points_mm, thickness_mm, bend_radius_mm, k_factor,
                                       False, depth_mm, reverse_thickness, name)

    def add_sheet_metal_edge_flange(self, edge_index: int, length_mm: float,
                                   angle_deg: float = 90.0, flip: bool = False,
                                   gap_mm: float = 0.5, name: str = "SheetEdgeFlange") -> dict:
        """One native edge flange; rebuild and resolve edges before the next call.

        Based on the documented InsertSketchForEdgeFlange/InsertSheetMetalEdgeFlange2
        workflow. Uses global sheet-metal radius and allowance, material-inside
        positioning, outer-virtual-sharp length and trimming of adjoining side bends.
        """
        positive(length_mm, "length_mm")
        if not isinstance(angle_deg, (int, float)) or not math.isfinite(angle_deg) or not 0 < angle_deg < 180:
            raise SolidWorksError("angle_deg must be finite, greater than 0 and less than 180.")
        if not isinstance(gap_mm, (int, float)) or not math.isfinite(gap_mm) or gap_mm < 0:
            raise SolidWorksError("gap_mm must be finite and nonnegative.")
        info = self._checked_sheet_info()
        if len(info["bodies"]) != 1 or len(info["flat_patterns"]) != 1 or info["flat_patterns"][0]["flattened"]:
            raise SolidWorksError("Edge flanges require one folded sheet-metal body.")
        edges = list(self._solid_body().GetEdges() or ())
        if isinstance(edge_index, bool) or not isinstance(edge_index, int) or not 0 <= edge_index < len(edges):
            raise SolidWorksError("edge_index must be a current zero-based index from list_edges.")
        edge = binding.wrap(edges[edge_index], self._mod.IEdge)
        curve = binding.wrap(edge.GetCurve(), self._mod.ICurve)
        entry = self._edge_entry(edge_index, edge)
        if not curve.IsLine() or entry["length_mm"] <= info["parameters"][0]["thickness_mm"]:
            raise SolidWorksError("Choose a straight boundary edge of a sheet face, not a thickness edge.")
        model = self._require_model()
        model.ClearSelection2(True)
        if not binding.wrap(edge, self._mod.IEntity).Select4(False, None):
            raise SolidWorksError("Could not select the flange edge.")
        angle = math.radians(angle_deg)
        sketch = binding.wrap(model.InsertSketchForEdgeFlange(edge, angle, flip), self._mod.IFeature)
        manager = binding.wrap(model.SketchManager, self._mod.ISketchManager)
        if manager.ActiveSketch is not None:
            manager.InsertSketch(True)
        if sketch is None:
            raise SolidWorksError("SolidWorks could not generate a flange profile on this edge.")
        fm = binding.wrap(model.FeatureManager, self._mod.IFeatureManager)
        edge_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [edge])
        sketch_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [sketch])
        # Default radius (1), relief ratio (64), default relief (128), flip (2).
        options = 1 | 64 | 128 | (2 if flip else 0)
        feature = binding.wrap(fm.InsertSheetMetalEdgeFlange2(
            edge_array, sketch_array, options, angle, 0.0, 1, mm_to_m(length_mm),
            2, 0.5, 0.001, 0.001, 1, None), self._mod.IFeature)
        if feature is None:
            raise SolidWorksError("SolidWorks refused the edge flange; check edge, length and direction.")
        data = binding.wrap(feature.GetDefinition(), self._mod.IEdgeFlangeFeatureData)
        if not data.AccessSelections(model, None):
            raise SolidWorksError("Could not access the new flange definition.")
        modified = False
        try:
            # In 2023 the supplied sketch initially controls a short default length;
            # edit the created feature rather than trusting the insertion argument.
            data.OffsetDistance = mm_to_m(length_mm)
            data.OffsetDimType = 1  # swFlangeDimTypeOuterVirtualSharp
            data.GapDistance = mm_to_m(gap_mm)
            data.UsePositionTrimSideBends = True
            modified = bool(feature.ModifyDefinition(data, model, None))
        finally:
            if not modified:
                data.ReleaseSelectionAccess()
            model.ClearSelection2(True)
        if not modified:
            raise SolidWorksError("SolidWorks refused the requested flange length/gap.")
        result = self._finish_feature(feature, name, edge=edge_index, length_mm=length_mm,
                                      angle_deg=angle_deg, flip=flip, gap_mm=gap_mm)
        actual = binding.wrap(feature.GetDefinition(), self._mod.IEdgeFlangeFeatureData)
        if abs(m_to_mm(actual.OffsetDistance) - length_mm) > 1e-6 or abs(m_to_mm(actual.GapDistance) - gap_mm) > 1e-6:
            raise SolidWorksError("SolidWorks did not apply the requested flange length/gap.")
        result["sheet_metal"] = self._checked_sheet_info()
        return result

    def convert_to_sheet_metal(self, fixed_face: str, bend_radius_mm: float = 2.0,
                              k_factor: float = 0.5, auto_relief: bool = False,
                              relief_ratio: float = 0.5) -> dict:
        check_bend_parameters(bend_radius_mm, k_factor)
        if not isinstance(relief_ratio, (int, float)) or not math.isfinite(relief_ratio) or not 0.05 <= relief_ratio <= 2:
            raise SolidWorksError("relief_ratio must be finite and between 0.05 and 2.")
        part = self._require_part()
        bodies = self._part_bodies()
        if len(bodies) != 1:
            raise SolidWorksError("Conversion supports exactly one uniform-thickness solid body.")
        if bodies[0].IsSheetMetal():
            raise SolidWorksError("This body is already sheet metal; use get_sheet_metal_info.")
        normal, side = self._parse_face_selector(fixed_face)
        self._select_planar_face(bodies[0], normal, fixed_face, side)
        try:
            success = part.InsertBends2(mm_to_m(bend_radius_mm), "", k_factor, -1,
                                        auto_relief, relief_ratio, True)
        finally:
            self._model.ClearSelection2(True)
        if not success:
            raise SolidWorksError("Insert Bends failed. Use an open body with uniform thickness, planar walls "
                                  "and cylindrical bends; closed shells require rip cuts first.")
        rebuilt = bool(self._model.ForceRebuild3(False))
        return {"ok": True, "rebuild_ok": rebuilt, "sheet_metal": self._checked_sheet_info(),
                "mass_properties": self.get_mass_properties()["mass_properties"]}

    def _flat_pattern(self, feature_name=None):
        self._require_part()
        candidates = [f for f in self._sheet_features() if f.GetTypeName2() == "FlatPattern"]
        if feature_name:
            candidates = [f for f in candidates if f.Name == feature_name]
        if len(candidates) != 1:
            raise SolidWorksError("Expected one FlatPattern. Use get_sheet_metal_info and specify feature_name "
                                  "when the part has multiple flat patterns.")
        return candidates[0]

    def _set_flat_state(self, feature, flattened):
        action = SW_UNSUPPRESS_DEPENDENT if flattened else SW_SUPPRESS_FEATURE
        if not feature.SetSuppression2(action, SW_THIS_CONFIGURATION, None):
            raise SolidWorksError(f"SolidWorks refused to change flat pattern '{feature.Name}'.")
        self._model.ForceRebuild3(False)
        if self._is_suppressed(feature) == flattened:
            raise SolidWorksError("Flat-pattern suppression state did not change as requested.")

    def set_sheet_metal_flattened(self, flattened: bool, feature_name: str | None = None) -> dict:
        feature = self._flat_pattern(feature_name)
        before = not self._is_suppressed(feature)
        try:
            if before != flattened:
                self._set_flat_state(feature, flattened)
            info = self._checked_sheet_info()
            mass = self.get_mass_properties()["mass_properties"]
        except Exception:
            self._set_flat_state(feature, before)
            raise
        return {"ok": True, "feature": feature.Name, "flattened": flattened,
                "changed": before != flattened, "sheet_metal": info, "mass_properties": mass}

    def export_sheet_metal_dxf(self, path: str, include_bend_lines: bool = True,
                              include_sketches: bool = False, overwrite: bool = False) -> dict:
        """Atomic DXF export; retain the document's folded/flat state."""
        destination = os.path.abspath(path)
        if os.path.splitext(destination)[1].lower() != ".dxf":
            raise SolidWorksError("Use a .dxf destination for the sheet-metal flat pattern.")
        if os.path.exists(destination) and not overwrite:
            raise SolidWorksError("Destination already exists; choose a new path or set overwrite=True.")
        part = self._require_part()
        info = self._checked_sheet_info()
        if len(info["bodies"]) != 1 or len(info["flat_patterns"]) != 1:
            raise SolidWorksError("DXF export currently supports exactly one sheet-metal body and flat pattern.")
        source = self._model.GetPathName()
        if not source or os.path.splitext(source)[1].lower() != ".sldprt" or not os.path.isfile(source):
            raise SolidWorksError("Save the part as .SLDPRT before exporting a sheet-metal DXF.")
        feature = self._flat_pattern()
        before = not self._is_suppressed(feature)
        parent = os.path.dirname(destination)
        os.makedirs(parent, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".sheet-metal-", suffix=".dxf", dir=parent)
        os.close(handle)
        try:
            self._model.ClearSelection2(True)
            alignment = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0] * 12)
            options = 1 | (4 if include_bend_lines else 0) | (8 if include_sketches else 0)
            try:
                exported = part.ExportToDWG2(temporary, source, 1, True, alignment, False, False, options, None)
            finally:
                if (not self._is_suppressed(feature)) != before:
                    self._set_flat_state(feature, before)
                self._model.ClearSelection2(True)
            if not exported or not os.path.isfile(temporary) or os.path.getsize(temporary) == 0:
                raise SolidWorksError("SolidWorks failed to export a nonempty flat-pattern DXF.")
            # rename without replace refuses a destination created during export.
            if overwrite:
                os.replace(temporary, destination)
            else:
                os.rename(temporary, destination)
            return {"ok": True, "path": destination, "bytes": os.path.getsize(destination),
                    "format": "dxf", "include_bend_lines": include_bend_lines,
                    "include_sketches": include_sketches, "flattened": before}
        finally:
            if os.path.isfile(temporary):
                os.remove(temporary)
