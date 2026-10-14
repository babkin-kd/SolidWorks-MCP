"""Native dimension adapter candidate; construct/call/release only on the STA.

Registered SOLIDWORKS 2023 interfaces ground these signatures. Full supported
analytical boundaries fail closed for unsupported geometry; native acceptance
is required before MCP publication.
"""

from dataclasses import dataclass, field
import json
import math

import pythoncom
import win32com.client

from . import binding
from .documents import rejected
from .timings_v2 import timed_call
from .cad_planar_brep import PLANAR_BREP_SCOPE, PlanarBrepError
from .cad_analytical_brep import ANALYTICAL_BREP_SCOPE, analytical_body_snapshot


@dataclass
class NativeDimension:
    dimension: object
    owner: object
    displays: list = field(default_factory=list)
    display_slots: list = field(default_factory=list)
    # Canonical owner identity proven against this enumeration's full feature
    # snapshot. None deliberately means no proof, including manual records.
    owner_tree_identity: object = None


class CadDimensionsMixin:
    def dimension_selection_scope(self, model):
        from .cad_selection_scope import preserved_selection
        return preserved_selection(self, model, label='dimension')

    @staticmethod
    def _named_configuration(configuration):
        # A plain Python list becomes SAFEARRAY(VARIANT), which SW2023 can
        # silently ignore. Both read/write require a typed SAFEARRAY(BSTR).
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, [configuration])

    @staticmethod
    def dimension_object(record):
        return record.dimension

    def _resolve_dimension_anchor_object(self, model, persistent_hex, cls):
        if cls is self._module.IFeature:
            # Owner PIDs share the strict current-member feature contract,
            # including a native RefPlane PID returning its specific interface.
            return self.resolve_persistent_id(model, bytes.fromhex(persistent_hex), 'feature')
        raw, status = self._extension(model).GetObjectByPersistReference3(
            self._persistent_variant(bytes.fromhex(persistent_hex)))
        if status != 0 or raw is None:
            code = ('object_deleted' if status & 4 else 'object_suppressed' if status & 2 else 'object_reference_invalid')
            raise rejected(code, f'Native dimension persistent-reference state is {status}.')
        if cls is self._module.IDisplayDimension:
            try:
                return binding.queried(raw, cls)
            except pythoncom.com_error as error:
                if error.hresult != -2147467262:  # E_NOINTERFACE only, not a failed/lost native call.
                    raise
            annotation=binding.queried(raw,self._module.IAnnotation)
            annotation_type=annotation.GetType()
            if type(annotation_type) is not int or annotation_type!=4:
                raise rejected('object_reference_invalid','Display PID returned another annotation type.')
            display=binding.queried(annotation.GetSpecificAnnotation(),cls)
            if display is None:
                raise rejected('object_reference_invalid','Annotation PID has no underlying display dimension.')
            current_annotation=binding.queried(display.GetAnnotation(),self._module.IAnnotation)
            if (current_annotation is None or self.identity(current_annotation)!=self.identity(annotation)
                    or self.persistent_id(model,display)!=bytes.fromhex(persistent_hex)):
                raise rejected('persistent_reference_mismatch','Annotation/display PID association is not exact.')
            return display
        return binding.wrap(raw, cls)

    def _dimension_anchor_parts(self, model, anchor):
        if anchor['strategy'] == 'direct_dimension_v1':
            dimension = self._resolve_dimension_anchor_object(model, anchor['dimension_pid_hex'], self._module.IDimension)
            return dimension, None
        if anchor['strategy'] != 'display_dimension_v1':
            raise rejected('object_reference_invalid', 'Unsupported native dimension reference strategy.')
        display = self._resolve_dimension_anchor_object(model, anchor['display_pid_hex'], self._module.IDisplayDimension)
        index = anchor['dimension_index']
        display_type = int(display.GetType())
        if (type(index) is not int or index not in (0, 1)
                or display_type != anchor['display_type'] or (display_type != 10 and index != 0)):
            raise rejected('object_reference_invalid', 'Display type/parameter slot changed; no ordinal fallback.')
        dimension = binding.wrap(display.GetDimension2(index), self._module.IDimension)
        if dimension is None:
            raise rejected('object_reference_invalid', 'Persistent display no longer supplies this dimension slot.')
        owner = self._resolve_dimension_anchor_object(model, anchor['owner_pid_hex'], self._module.IFeature)
        actual_owner = binding.wrap(dimension.GetFeatureOwner(), self._module.IFeature)
        if actual_owner is None or self.identity(owner) != self.identity(actual_owner):
            raise rejected('persistent_reference_mismatch', 'Dimension no longer belongs to the persistent owner feature.')
        return dimension, display

    def resolve_dimension_id(self, model, anchor):
        return self._dimension_anchor_parts(model, anchor)[0]

    def dimension_persistent_id(self, model, record):
        """Explicit direct or compound native anchor; never resolve by a name.

        SW2023 can return no PID for IDimension, while its IDisplayDimension
        supports a native PID. A display slot is a documented API parameter,
        not the dimension's position in a traversal.
        """
        if (record.owner is None or record.owner_tree_identity is None
                or self.identity(record.owner) != record.owner_tree_identity):
            return None
        dimension = record.dimension
        direct = self.persistent_id(model, dimension)
        if direct:
            anchor = {'strategy': 'direct_dimension_v1', 'dimension_pid_hex': direct.hex()}
            if self.identity(self.resolve_dimension_id(model, anchor)) != self.identity(dimension):
                raise rejected('persistent_reference_mismatch', 'Direct dimension PID resolves to another native object.')
            return anchor
        owner = record.owner
        owner_pid = self.persistent_id(model, owner) if owner is not None else b''
        if not owner_pid:
            return None
        for display, index in record.display_slots:
            display_pid = self.persistent_id(model, display)
            if not display_pid:
                continue
            anchor = {'strategy': 'display_dimension_v1', 'display_pid_hex': display_pid.hex(),
                      'dimension_index': index, 'display_type': int(display.GetType()),
                      'owner_pid_hex': owner_pid.hex()}
            resolved_dimension, resolved_display = self._dimension_anchor_parts(model, anchor)
            if (self.identity(resolved_dimension) != self.identity(dimension)
                    or self.identity(resolved_display) != self.identity(display)):
                raise rejected('persistent_reference_mismatch', 'Compound dimension PID does not roundtrip to its native display and dimension.')
            return anchor
        return None

    def dimension_same_persistent_id(self, model, left, right):
        if left['strategy'] != right['strategy']:
            return False
        if left['strategy'] == 'direct_dimension_v1':
            return self.same_persistent_id(model, bytes.fromhex(left['dimension_pid_hex']), bytes.fromhex(right['dimension_pid_hex']))
        if left['strategy'] != 'display_dimension_v1':
            return False
        return (left['dimension_index'] == right['dimension_index'] and left['display_type'] == right['display_type']
                and self.same_persistent_id(model, bytes.fromhex(left['display_pid_hex']), bytes.fromhex(right['display_pid_hex']))
                and self.same_persistent_id(model, bytes.fromhex(left['owner_pid_hex']), bytes.fromhex(right['owner_pid_hex'])))

    def dimension_reference_is_current(self, model, record, anchor):
        if (record.owner is None or record.owner_tree_identity is None
                or self.identity(record.owner) != record.owner_tree_identity):
            return False
        dimension, display = self._dimension_anchor_parts(model, anchor)
        if self.identity(dimension) != self.identity(record.dimension):
            return False
        owner = binding.wrap(dimension.GetFeatureOwner(), self._module.IFeature)
        if owner is None or self.identity(owner) != record.owner_tree_identity:
            return False
        if display is None:
            return True
        return any(index == anchor['dimension_index'] and self.identity(current) == self.identity(display)
                   for current, index in record.display_slots)

    def dimensions(self, model, features):
        """Enumerate all feature/subfeature dimensions; include both chamfer values.

        Feature traversal is supplied by the existing bounded adapter. Native
        dimension identity deduplicates absorbed-feature/display aliases; names
        and enumeration indices never resolve a client reference.
        """
        # The caller already supplied the complete bounded feature traversal.
        # Cache canonical identities once; PyIUnknown only needs equality, not
        # hashing. Never repeat COM feature traversal for every reference.
        features = tuple(features)
        feature_identities = tuple(self.identity(feature) for feature in features)
        result, visits = [], 0
        # Only this enumeration owns these strong canonical identities. Linear
        # equality scans stay in Python: never QueryInterface the old records
        # again for each incoming slot, and never hash unhashable IUnknown.
        # Each entry holds dimension identity, record, display identities and
        # (display identity, explicit API slot) memberships.
        canonical_records = []
        for feature in features:
            display = binding.wrap(feature.GetFirstDisplayDimension(), self._module.IDisplayDimension)
            chain = []
            while display is not None:
                visits += 1
                if visits > 20000:
                    raise rejected('dimension_budget_exceeded', 'Display-dimension traversal budget exhausted; no partial revision.')
                display_identity = self.identity(display)
                if any(old == display_identity for old in chain):
                    raise rejected('dimension_traversal_cycle', 'Native display-dimension chain is cyclic.')
                chain.append(display_identity)
                indices = (0, 1) if int(display.GetType()) == 10 else (0,)
                for index in indices:
                    dimension = binding.wrap(display.GetDimension2(index), self._module.IDimension)
                    if dimension is None:
                        raise rejected('dimension_read_failed', 'Display dimension did not provide its model dimension.')
                    identity = self.identity(dimension)
                    canonical = next((entry for entry in canonical_records if entry[0] == identity), None)
                    if canonical is None:
                        if len(result) >= 5000:
                            raise rejected('dimension_budget_exceeded', 'Dimension enumeration budget exhausted.')
                        owner = binding.wrap(dimension.GetFeatureOwner(), self._module.IFeature)
                        prior = NativeDimension(dimension, owner)
                        if owner is not None:
                            owner_identity = self.identity(owner)
                            if any(owner_identity == candidate for candidate in feature_identities):
                                prior.owner_tree_identity = owner_identity
                        result.append(prior)
                        canonical = (identity, prior, [], [])
                        canonical_records.append(canonical)
                    prior, display_identities, slot_identities = canonical[1:]
                    if not any(old == display_identity for old in display_identities):
                        prior.displays.append(display)
                        display_identities.append(display_identity)
                    if not any(slot == index and old == display_identity for old, slot in slot_identities):
                        prior.display_slots.append((display, index))
                        slot_identities.append((display_identity, index))
                display = binding.wrap(feature.GetNextDisplayDimension(display), self._module.IDisplayDimension)
        return result

    def dimension_summary(self, record, configurations):
        dim, owner = record.dimension, record.owner
        kind = int(dim.GetType())  # swDimensionParamType_e, not display enum.
        unit = {0: 'mm', 1: 'deg'}.get(kind)
        values = {}
        for configuration in configurations:
            raw = dim.GetSystemValue3(3, self._named_configuration(configuration))  # swSpecifyConfiguration.
            if raw is None or not isinstance(raw, (tuple, list)) or len(raw) != 1:
                raise rejected('dimension_read_failed', 'Native named-configuration value was not a one-element array.')
            value = float(raw[0])
            if not math.isfinite(value):
                raise rejected('dimension_read_failed', 'Native dimension value is not finite.')
            values[configuration] = value
        display_info = [{'type': int(d.GetType()), 'linked': bool(d.IsLinked),
                         'linked_text': str(d.GetLinkedText() or '')} for d in record.displays]
        display_info.sort(key=lambda row: (row['type'], row['linked'], row['linked_text']))
        driven = int(dim.DrivenState)
        read_only, reference = bool(dim.ReadOnly), bool(dim.IsReference())
        design_table = bool(dim.IsDesignTableDimension())
        linked = any(d['linked'] or d['linked_text'] for d in display_info)
        blockers = []
        if kind not in (0, 1):
            blockers.append('unsupported_parameter_type')
        if driven != 2:
            blockers.append('driven_or_unknown_state')
        for flag, name in [(read_only, 'read_only'), (reference, 'reference'),
                           (design_table, 'design_table'), (linked, 'linked')]:
            if flag:
                blockers.append(name)
        owner_info = None
        owner_stamp = None
        if owner is None:
            blockers.append('owner_unavailable')
        else:
            owner_info = self.feature_summary(owner)
            owner_info.update(frozen=bool(owner.IsFrozen()), rolled_back=bool(owner.IsRolledBack()))
            owner_stamp = int(owner.GetUpdateStamp())
            if owner_info['suppressed'] or owner_info['frozen'] or owner_info['rolled_back']:
                blockers.append('owner_suppressed_frozen_or_rolled_back')
            if owner_info['feature_type'] in ('ProfileFeature', '3DProfileFeature'):
                blockers.append('sketch_geometry_snapshot_not_implemented')
            elif owner_info['feature_type'] not in ('Boss', 'Extrusion', 'Cut', 'Revolve', 'RevolvCut'):
                blockers.append('owner_type_not_accepted')
        # Signed origin coordinates, ordinate, scalar and two-value chamfer
        # dimensions require dedicated semantics. Do not normalize with abs().
        if any(d['type'] not in (2, 3, 4, 5, 6) for d in display_info):
            blockers.append('unsupported_display_semantics')
        tolerance_type = int(dim.GetToleranceType())
        tolerance_raw = dim.GetToleranceValues()
        tolerance_values = [float(v) for v in tolerance_raw] if tolerance_raw is not None else []
        if ((tolerance_type != 0 and len(tolerance_values) != 2)
                or any(not math.isfinite(v) for v in tolerance_values)):
            raise rejected('dimension_read_failed', 'Native dimension tolerances were not fully readable.')
        user_values = {n: (v * 1000 if kind == 0 else math.degrees(v) if kind == 1 else v)
                       for n, v in values.items()}
        return {'full_name': str(dim.FullName), 'name': str(dim.Name), 'parameter_type': kind,
                'unit': unit, 'values_si': values, 'values': user_values,
                'driven_state': driven, 'read_only': read_only, 'reference': reference,
                'design_table': design_table, 'linked': linked, 'display_dimensions': display_info,
                'owner': owner_info, 'owner_update_stamp': owner_stamp,
                'tolerance': {'type': tolerance_type, 'values_si': tolerance_values},
                'write_blockers': blockers}

    def dimension_context(self, model):
        active = binding.wrap(self._sw.ActiveDoc, self._module.IModelDoc2)
        equation = binding.wrap(model.GetEquationMgr(), self._module.IEquationMgr)
        if equation is None:
            raise rejected('dimension_context_unavailable', 'Equation controls could not be inspected.')
        count = int(equation.GetCount())
        if not 0 <= count <= 5000:
            raise rejected('dimension_budget_exceeded', 'Equation control budget exhausted.')
        equations = [{'equation': str(equation.Equation(i)), 'disabled': bool(equation.Disabled(i))}
                     for i in range(count)]
        external_count = int(model.ListExternalFileReferencesCount2())
        if external_count < 0:
            raise rejected('dimension_context_unavailable', 'External-reference count is unavailable.')
        feature_types = [str(feature.GetTypeName2()) for feature in self.features(model)]
        unsafe = sorted({kind for kind in feature_types if kind.casefold() in (
            'macrofeature', 'designTable'.casefold(), 'derivedpart', 'insertpart', 'mirrorpart')})
        configuration_names = list(model.GetConfigurationNames() or ())
        configuration_rebuild = {}
        for name in configuration_names:
            config = binding.wrap(model.GetConfigurationByName(name), self._module.IConfiguration)
            if config is None:
                raise rejected('configuration_not_found', 'Configuration disappeared during dimension control collection.')
            configuration_rebuild[name] = bool(config.NeedsRebuild)
        return {'active_document': active is not None and self.identity(active) == self.identity(model),
                # Only active-configuration bodies are currently captured.
                # Do not claim rollback of unobserved inactive geometry.
                'configuration_geometry_complete': len(configuration_names) == 1,
                'configuration_needs_rebuild': configuration_rebuild,
                'read_only': bool(model.IsOpenedReadOnly()),
                'editing_sketch': model.GetActiveSketch2() is not None,
                'external_reference_count': external_count, 'equation_count': count, 'equations': equations,
                'equations_linked': bool(equation.LinkToFile),
                'equation_file': str(equation.FilePath or ''),
                # GetDesignTable may return an automation object even when no
                # table exists. Query the documented existence API explicitly.
                'design_table': bool(self._extension(model).HasDesignTable()),
                'unsafe_feature_types': unsafe}

    def dimension_geometry_snapshot(self, model):
        """Read the complete supported analytical boundary, without Copy/Save.

        Native serialization of a NEW copy is not canonical on SW2023. Only
        complete planar bodies and unseamed right cylinders are implemented.
        """
        bodies = self.bodies(model, 'all')
        if len(bodies) > 500:
            raise rejected('geometry_budget_exceeded', 'Dimension scope supports at most 500 native bodies.')
        result, total = [], 0
        for body in bodies:
            try:
                snapshot = analytical_body_snapshot(body, identity=self.identity,
                    wrap=lambda raw, name: binding.wrap(raw, getattr(self._module, name)))
            except PlanarBrepError as exc:
                raise rejected(exc.code, str(exc)) from exc
            serialized = json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                allow_nan=False, separators=(',', ':'))
            size = len(serialized.encode('utf8'))
            total += size
            if size <= 0 or size > 64 * 1024 * 1024 or total > 128 * 1024 * 1024:
                raise rejected('geometry_snapshot_unavailable', 'Analytical boundary snapshot exceeds the bounded budget.')
            result.append((serialized, snapshot))
        result.sort(key=lambda row: row[0])
        representation = (PLANAR_BREP_SCOPE if all(row[1]['scope'] == PLANAR_BREP_SCOPE for row in result)
                          else ANALYTICAL_BREP_SCOPE)
        return {'representation': representation, 'bodies': [row[1] for row in result]}

    @staticmethod
    def set_dimension_value(record, value_si, configuration):
        # swSetValue_InSpecificConfigurations=3; never UseCurrentSetting or All.
        return timed_call('com', record.dimension.SetSystemValue3, value_si, 3,
            CadDimensionsMixin._named_configuration(configuration))

    def rebuild_dimension_document(self, model):
        active = binding.wrap(self._sw.ActiveDoc, self._module.IModelDoc2)
        if active is None or self.identity(active) != self.identity(model):
            raise rejected('document_not_active', 'Explicit dimension document stopped being active before rebuild.')
        # SW2023 EditRebuild3 can return True after SetSystemValue3 while the
        # body remains unchanged and NeedsRebuild2 stays set. Recompute this
        # explicit active part, then confirm the pending flag is cleared.
        rebuilt = timed_call('rebuild', timed_call, 'com', model.ForceRebuild3, False)
        return rebuilt is True and self.pending_rebuild(model) is False
