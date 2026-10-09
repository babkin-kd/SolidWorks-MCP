"""STA-only native adapter for the deliberately narrow v2 export domain.

SaveAs3 signature and preference IDs are from the registered SW 2023 libraries.
Official references and native acceptance requirements are recorded in the
handoff notes. No document activation, configuration switch, ClearSelection,
rebuild, save-original, or generic Undo is performed.
"""

import math

from . import binding
from .documents import rejected
from .jobs import _json
from .cad_planar_brep import PlanarBrepError, planar_body_snapshot, planar_snapshot_digest


# (application preference kind, SW 2023 swconst enum value). Document-property
# IDs and application-option IDs must not be confused even when numerically equal.
PREFERENCES = {
    'coordinate_system': ('String', 134),  # swExportOutputCoordinateSystem
    'stl_units': ('Integer', 211),  # swExportStlUnits / swLengthUnit_e
    'stl_binary': ('Toggle', 69),
    'stl_positive_translation_disabled': ('Toggle', 71),
    'stl_show_info': ('Toggle', 70),
    'stl_preview': ('Toggle', 191),
    'stl_quality': ('Integer', 78),
    'stl_deviation_m': ('Double', 2),
    'stl_angle_rad': ('Double', 3),
    'step_ap': ('Integer', 75),
    'step_geometry': ('Integer', 142),
    'step_curves': ('Toggle', 497),
    'step_appearances': ('Toggle', 787),
    'step_face_edge_properties': ('Toggle', 397),
    'step_configuration_data': ('Toggle', 403),
    'step_split_periodic': ('Toggle', 396),
    'step_atomic_save': ('Toggle', 786),
    'parasolid_version': ('Integer', 89),
}


def desired_preferences(options):
    result = {'coordinate_system': ''}  # Explicit model frame, not a named frame.
    if options.format == 'stl':
        result.update(stl_units={'mm': 0, 'm': 2, 'in': 3}[options.units], stl_binary=True,
            stl_positive_translation_disabled=True, stl_show_info=False, stl_preview=False,
            stl_quality=3, stl_deviation_m=0.0001, stl_angle_rad=math.radians(10))
    elif options.format == 'step':
        # AP203 geometry-only. Color/configuration/sketch export is intentionally
        # excluded: corresponding metadata needs its own complete revision scope.
        result.update(step_ap=203, step_geometry=0, step_curves=False, step_appearances=False,
            step_face_edge_properties=False, step_configuration_data=False, step_split_periodic=False,
            step_atomic_save=False)
    elif options.format == 'parasolid':
        result['parasolid_version'] = 0  # Latest native kernel version.
    else:
        raise rejected('unsupported_export_format', 'Unsupported native export format.')
    return result


class CadExportsAdapter:
    """Compose with the existing SolidWorksDocuments adapter on its owning STA.

    Composition avoids changing legacy adapter behavior or public registrations.
    References belong to the underlying documents adapter and must be retired on
    that same apartment; no independent application connection is opened here.
    """

    def __init__(self, documents_adapter):
        self.documents_adapter = documents_adapter

    def __getattr__(self, name):
        return getattr(self.documents_adapter, name)

    def export_document_is_active(self, model):
        raw = self._sw.ActiveDoc
        return raw is not None and self.identity(raw) == self.identity(model)

    def _preflight(self, model):
        if int(model.GetType()) != 1 or not self.export_document_is_active(model):
            raise rejected('document_not_active', 'Only the explicitly active part can be exported.')
        if self.pending_rebuild(model):
            raise rejected('document_needs_rebuild', 'Rebuild the source explicitly before export.')
        manager = binding.wrap(model.SelectionManager, self._module.ISelectionMgr)
        if manager.GetSelectedObjectCount2(-1) != 0:
            raise rejected('export_selection_not_empty', 'Clear the selection explicitly before full-part export.')
        # Old documents can retain an obsolete, document-specific output frame.
        # Refuse that case until native compatibility is established; changing
        # this document property would alter the source/dirty state.
        if self._extension(model).GetUserPreferenceString(16, 0):
            raise rejected('unsupported_document_export_frame', 'Document-specific legacy output coordinate system is set.')

    def _body_fingerprint(self, body):
        if int(body.GetType()) != 0 or body.IsMeshBody() or not bool(body.Visible):
            raise rejected('unsupported_export_body', 'Initial export supports visible native solid BREP bodies only.')
        try:
            snapshot = planar_body_snapshot(body, identity=self.identity,
                wrap=lambda raw, name: binding.wrap(raw, getattr(self._module, name)))
        except PlanarBrepError as exc:
            raise rejected(exc.code, str(exc)) from exc
        return {'name': str(body.Name), 'type': 'solid', 'visible': True,
                'boundary_snapshot_sha256': planar_snapshot_digest(snapshot),
                'boundary_snapshot': snapshot}

    def export_source_snapshot(self, model):
        self._preflight(model)
        metadata = self.snapshot(model)
        bodies = self.bodies(model, 'all')
        if not 1 <= len(bodies) <= 256:
            raise rejected('unsupported_export_body_count', 'Export requires 1–256 visible native solid bodies.')
        # Complete analytical boundary/topology for supported planar solids.
        # Native Copy/Save streams are not canonical geometry fingerprints.
        fingerprints = []
        serialized_bytes = 0
        for body in bodies:
            fingerprint = self._body_fingerprint(body)
            serialized_bytes += len(_json(fingerprint).encode('utf8'))
            if serialized_bytes > 64 * 1024 * 1024:
                raise rejected('export_fingerprint_budget_exceeded', 'Total serialized bodies exceed the fingerprint budget.')
            fingerprints.append(fingerprint)
        fingerprints.sort(key=_json)
        features = [self.feature_summary(feature) for feature in self.features(model)]
        self._preflight(model)
        if self.snapshot(model) != metadata:
            raise rejected('document_changed_during_read', 'Document changed during export fingerprinting.')
        return {'document': metadata, 'bodies': fingerprints, 'features': features,
                'needs_rebuild': False, 'selection_count': 0, 'active_document_is_source': True,
                'legacy_output_coordinate_system': '', 'native_brep_unit_system': 'm'}

    def _get_preference(self, name):
        kind, code = PREFERENCES[name]
        method = {'String': 'GetUserPreferenceStringValue', 'Integer': 'GetUserPreferenceIntegerValue',
                  'Toggle': 'GetUserPreferenceToggle', 'Double': 'GetUserPreferenceDoubleValue'}[kind]
        value = getattr(self._sw, method)(code)
        return {'String': str, 'Integer': int, 'Toggle': bool, 'Double': float}[kind](value)

    def _set_preference(self, name, value):
        kind, code = PREFERENCES[name]
        method = {'String': 'SetUserPreferenceStringValue', 'Integer': 'SetUserPreferenceIntegerValue',
                  'Toggle': 'SetUserPreferenceToggle', 'Double': 'SetUserPreferenceDoubleValue'}[kind]
        if getattr(self._sw, method)(code, value) is not True or self._get_preference(name) != value:
            raise rejected('export_preference_write_failed', f'Native preference {name} was not confirmed.')

    def export_preferences(self, options):
        return {name: self._get_preference(name) for name in desired_preferences(options)}

    def export_profile(self, options):
        return {'desired_application_preferences': desired_preferences(options),
                'native_method': 'IModelDocExtension.SaveAs3', 'saveas_version': 0,
                'saveas_options': 3, 'frame': 'part_model', 'bodies': 'all_visible_native_solids',
                'accepted_errors': 0, 'accepted_warnings': 0,
                'verification': 'source_fingerprint_and_file_structure; no_geometry_roundtrip'}

    def export_part_to_file(self, model, path, options, before_preferences):
        desired = desired_preferences(options)
        if self.export_preferences(options) != before_preferences:
            raise rejected('stale_export_preferences', 'Export preferences changed before the native write.')
        self._preflight(model)
        metadata = self.snapshot(model)
        attempts = []
        original = None
        result = None
        try:
            for name, value in desired.items():
                # Earlier native calls can allow an external edit to a setting
                # not yet touched by us. Do not overwrite that newer value or
                # add it to the set of settings we own for restoration.
                if self._get_preference(name) != before_preferences[name]:
                    raise rejected('stale_export_preferences', f'Native preference {name} changed before its setter.')
                # Record before calling the setter: a failing COM call can still
                # apply a native side effect and must be considered for restore.
                attempts.append(name)
                self._set_preference(name, value)
            self._preflight(model)
            if self.snapshot(model) != metadata:
                raise rejected('export_source_changed', 'Source changed while export preferences were applied.')
            extension = self._extension(model)
            # Later setters/native getters can change an earlier preference.
            # Verify the complete exact profile after them, before SaveAs3.
            # This is a bounded readback, not an atomic application snapshot.
            if self.export_preferences(options) != desired:
                raise rejected('export_preference_write_failed', 'Complete native export preference profile was not confirmed before SaveAs3.')
            native = extension.SaveAs3(str(path), 0, 1 | 2, None, None, 0, 0)
            if not isinstance(native, tuple) or len(native) != 3:
                raise rejected('native_export_result_invalid', 'SaveAs3 did not return bool/errors/warnings.')
            success, errors, warnings = native
            result = {'success': bool(success), 'errors': int(errors), 'warnings': int(warnings),
                      'method': 'IModelDocExtension.SaveAs3', 'options': ['silent', 'copy']}
        except Exception as exc:
            original = exc
        finally:
            failures = []
            for name in reversed(attempts):
                try:
                    current = self._get_preference(name)
                    if current not in (before_preferences[name], desired[name]):
                        raise RuntimeError('Preference changed externally; refusing to overwrite a third value.')
                    if current != before_preferences[name]:
                        self._set_preference(name, before_preferences[name])
                    if self._get_preference(name) != before_preferences[name]:
                        raise RuntimeError('Restored value differs from the checkpoint.')
                except Exception as exc:
                    failures.append(f'{name}: {exc}')
            if failures:
                raise rejected('export_preferences_restore_unconfirmed', '; '.join(failures)) from original
        if original is not None:
            raise original
        return result
