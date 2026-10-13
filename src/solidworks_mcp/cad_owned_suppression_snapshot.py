"""Read-only retained producer for the bounded owned suppressed-base profile.

Construct on the unsuppressed BASE, on its owning STA, retaining ORIGINAL native
dimension records/anchors. This collection is neither mutation authorization nor
native B2/cleanup acceptance. Missing arrays/annotations/materials are explicit
producer gates; no unavailable field is filled from the baseline. No Parameter
name lookup, connection, CoInitialize, setters, activation or rebuild occurs.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import threading

from .documents import rejected
from .jobs import _json
from .owned_rectangle_feature import _canonical
from .rectangle_annotation_views import validated_view_bindings
from .rectangle_inventory import feature_relations, empty_feature_external_inventory
from .rectangle_snapshot import BASE, validated_rectangle_snapshot
from .retained_feature_resolution import resolve_retained_feature_pid


SCOPE = 'native_owned_suppressed_rectangle_snapshot_v1'
PROFILE = 'owned_suppressed_rectangular_blind_base_v1'
ROLES = frozenset(('dimension:width', 'dimension:height', 'dimension:depth'))
DIMENSION_KEYS = frozenset(('full_name', 'name', 'parameter_type', 'unit', 'values_si', 'values',
    'driven_state', 'read_only', 'reference', 'design_table', 'linked', 'display_dimensions',
    'owner', 'owner_update_stamp', 'tolerance', 'write_blockers'))


def _fail(field, message):
    raise rejected('owned_suppression_snapshot_unavailable', field + ': ' + message)


def _require(condition, field, message):
    if not condition:
        _fail(field, message)


def _array(value, field, maximum=128):
    _require(type(value) in (list, tuple) and len(value) <= maximum, field,
             'A complete bounded actual array is required; unavailable is not empty.')
    return list(value)


def _hex(token, field):
    try:
        result = bytes.fromhex(token) if type(token) is str else None
    except ValueError:
        result = None
    _require(type(result) is bytes and bool(result), field, 'Original native PID bytes required.')
    return result


def _detached(value):
    return json.loads(_json(value))


@dataclass(frozen=True)
class _DimensionBinding:
    role: str
    qualified: dict
    record: object
    anchor: dict
    dimension_identity: object
    owner: object
    owner_identity: object
    owner_pid: bytes
    display: object = None
    display_identity: object = None
    displays: tuple = ()


class _RetainedViewAdapter:
    """Use anchored retained records for the existing full annotation-view getter."""
    def __init__(self, adapter, model_identity, records):
        object.__setattr__(self, '_adapter', adapter)
        object.__setattr__(self, '_model_identity', model_identity)
        object.__setattr__(self, '_records', records)

    def __getattr__(self, name):
        return getattr(self._adapter, name)

    def __setattr__(self, name, value):
        setattr(self._adapter, name, value)

    def dimensions(self, model, features):
        _require(self._adapter.identity(model) == self._model_identity, 'annotation_view_bindings',
                 'Retained view reader cannot adopt another model.')
        return list(self._records)


class OwnedSuppressionSnapshot:
    """Server-owned native context; it cannot be reconstructed after reconnect.

    ``getters`` and ``query`` are trusted adapter dependencies for pure tests,
    not client proofs. Default getter imports are lazy. Constructor requires the
    complete validated original BASE; capture returns only actual current fields.
    Domain owner brackets two captures with its complete session/revision oracle.
    """
    def __init__(self, adapter, model, binding, baseline_snapshot, *, getters=None, query=None):
        self.adapter, self.model, self.binding = adapter, model, binding
        self.configuration = binding.configuration
        self._thread = threading.get_ident()
        self._getters = getters
        self._query = query
        self.baseline = validated_rectangle_snapshot(baseline_snapshot)
        _require(self.baseline['clone_state']['profile'] == BASE
                 and self.baseline['configuration'] == self.configuration
                 and binding.kind == 'extrusion', 'baseline', 'Only the owned unsuppressed blind BASE is supported.')
        self.model_identity = _canonical(binding.model_identity)
        self.configuration_identity = _canonical(binding.configuration_identity)
        self.extrusion_identity = _canonical(binding.feature_identity)
        self.extrusion = binding.feature
        self.sketch = binding.receipt.borrowed_sketch
        self.sketch_identity = _canonical(binding.receipt.borrowed_sketch_identity)
        self._opening()
        features, rows = self._features()
        _require(all(row['suppressed'] is False and row['error_code'] == 0 for row in rows),
                 'baseline.features', 'Retain original records before suppression, on a clean unsuppressed BASE.')
        _require(_json(rows) == _json(self.baseline['clone_state']['features']),
                 'baseline.features', 'Current complete feature inventory differs from the original BASE.')
        self._feature_records = tuple((feature, _canonical(adapter.identity(feature)), deepcopy(row))
                                      for feature, row in zip(features, rows))
        self._feature_refs = [deepcopy(row) for row in self.baseline['references'] if row['kind'] == 'feature']
        self._feature_pids = {}
        for reference in self._feature_refs:
            index = self._role_index(reference['role'], len(features))
            pid = _hex(reference['token'], 'baseline.feature_pid')
            feature = features[index]
            identity = self._feature_records[index][1]
            resolve_retained_feature_pid(adapter, model, pid, identity)
            self._feature_pids[index] = pid
        ext = [i for i, (_, identity, _) in enumerate(self._feature_records) if identity == self.extrusion_identity]
        sk = [i for i, (_, identity, _) in enumerate(self._feature_records) if identity == self.sketch_identity]
        _require(len(ext) == len(sk) == 1 and ext[0] in self._feature_pids and sk[0] in self._feature_pids,
                 'baseline.owners', 'Original extrusion and sketch require unique canonical feature/PID membership.')
        self._extrusion_index, self._sketch_index = ext[0], sk[0]
        _require(self._feature_pids[ext[0]] == binding.persistent_id
                 and rows[ext[0]]['native_id'] == binding.native_id
                 and adapter.identity(self.sketch) == self.sketch_identity,
                 'baseline.owners', 'Original retained extrusion/sketch canonical anchors changed.')
        bodies = _array(adapter.bodies(model, 'all'), 'baseline.bodies', 1)
        _require(len(bodies) == 1, 'baseline.bodies', 'Exactly the original single solid must be retained.')
        self._body = bodies[0]
        self._body_identity = _canonical(adapter.identity(self._body))
        body_refs = [row for row in self.baseline['references'] if row['kind'] == 'body' and row['role'] == 'body:0']
        _require(len(body_refs) == 1, 'baseline.body_pid', 'Original body primary PID required.')
        body_pid = _hex(body_refs[0]['token'], 'baseline.body_pid')
        _require(adapter.persistent_id(model, self._body) == body_pid
                 and adapter.identity(adapter.resolve_persistent_id(model, body_pid, 'body')) == self._body_identity,
                 'baseline.body_pid', 'Retained original body must round-trip its own PID before suppression.')
        self._dimensions = self._retain_dimensions(features)
        self._opening()

    @staticmethod
    def _role_index(role, size):
        _require(type(role) is str and role.startswith('feature:'), 'feature_role', 'Exact original feature role required.')
        suffix = role.removeprefix('feature:')
        _require(suffix.isdecimal() and str(int(suffix)) == suffix and int(suffix) < size,
                 'feature_role', 'Feature role is outside the complete original inventory.')
        return int(suffix)

    def _opening(self):
        _require(threading.get_ident() == self._thread, 'apartment', 'Use the original owning STA.')
        a = self.adapter
        _require(a.identity(self.model) == self.model_identity
                 and a.configuration_identity(self.model, self.configuration) == self.configuration_identity
                 and a.identity(self.extrusion) == self.extrusion_identity
                 and a.identity(self.sketch) == self.sketch_identity,
                 'canonical_target', 'Retained model/configuration/extrusion/sketch changed.')
        observed = a.snapshot(self.model)
        _require(observed['document_type'] == 'part' and observed['path'] == ''
                 and observed['configurations'] == [self.configuration]
                 and observed['active_configuration'] == self.configuration,
                 'target', 'Only the original unsaved one-configuration part is supported.')
        return _detached(observed)

    def _features(self):
        features = _array(self.adapter.features(self.model), 'features', 64)
        rows = [self.adapter.feature_summary(feature) for feature in features]
        _require(4 <= len(features) <= 64 and all(type(row) is dict for row in rows)
                 and all(type(row.get('native_id')) is int for row in rows)
                 and all(type(row.get('suppressed')) is bool and type(row.get('error_code')) is int for row in rows)
                 and len({row['native_id'] for row in rows}) == len(rows),
                 'features', 'Complete unique current feature summaries required.')
        return features, rows

    def _retain_dimensions(self, features):
        a, model = self.adapter, self.model
        qualified = self.baseline['native_observations']['qualified_dimensions']
        _require(type(qualified) is list and len(qualified) == 3 and {row['role'] for row in qualified} == ROLES,
                 'baseline.dimensions', 'All three original qualified dimension roles required.')
        references = [row for row in self.baseline['references'] if row['kind'] == 'dimension']
        _require(len(references) == 3 and {row['role'] for row in references} == ROLES,
                 'baseline.dimensions', 'Exactly three PRIMARY original dimension anchor references required.')
        anchors = {}
        for reference in references:
            try:
                anchor = json.loads(reference['token'])
            except (TypeError, ValueError) as error:
                _fail('baseline.dimension_anchor', str(error))
            self._anchor(anchor)
            anchors[reference['role']] = anchor
        records = _array(a.dimensions(model, features), 'baseline.dimensions', 3)
        _require(len(records) == 3, 'baseline.dimensions', 'Retain exactly ORIGINAL three enumerated native records.')
        bound = []
        for record in records:
            original = a.dimension_persistent_id(model, record)
            _require(type(original) is dict, 'baseline.dimension_anchor', 'Native primary anchor unavailable.')
            matches = [role for role, anchor in anchors.items()
                       if a.dimension_same_persistent_id(model, original, anchor) is True
                       and _json(original) == _json(anchor)]
            _require(len(matches) == 1, 'baseline.dimension_anchor', 'Record must bind one original primary anchor; no name/GetID fallback.')
            role = matches[0]
            _require(a.dimension_reference_is_current(model, record, original) is True,
                     'baseline.dimension_anchor', 'Original dimension/owner/display membership is unconfirmed.')
            identity = _canonical(a.identity(a.dimension_object(record)))
            _require(a.identity(a.resolve_dimension_id(model, original)) == identity,
                     'baseline.dimension_anchor', 'Primary dimension anchor resolved another canonical dimension.')
            owner = record.owner
            owner_identity = _canonical(record.owner_tree_identity)
            _require(owner is not None and a.identity(owner) == owner_identity
                     and owner_identity in (self.extrusion_identity, self.sketch_identity),
                     'baseline.dimension_owner', 'Dimension owner must be its original canonical sketch/extrusion.')
            owner_pid = a.persistent_id(model, owner)
            expected_index = self._extrusion_index if role == 'dimension:depth' else self._sketch_index
            _require(owner_identity == self._feature_records[expected_index][1]
                     and owner_pid == self._feature_pids[expected_index],
                     'baseline.dimension_owner', 'Original primary owner PID/canonical binding differs.')
            proof = next(row for row in qualified if row['role'] == role)
            _require(proof['owner_role'] == 'feature:' + str(expected_index),
                     'baseline.dimension_owner', 'Qualified role differs from its PID-bound native owner.')
            display = display_identity = None
            if original['strategy'] == 'display_dimension_v1':
                candidates = [display for display, slot in record.display_slots
                    if type(slot) is int and slot == original['dimension_index']
                    and a.persistent_id(model, display) == _hex(original['display_pid_hex'], role)]
                _require(len(candidates) == 1, role, 'One exact retained PRIMARY display slot required.')
                display = candidates[0]
                display_identity = _canonical(a.identity(display))
            item = _DimensionBinding(role, deepcopy(proof), record, _detached(original),
                identity, owner, owner_identity, owner_pid, display, display_identity,
                tuple(_canonical(a.identity(display)) for display in _array(record.displays, role + '.displays', 8)))
            summary = a.dimension_summary(record, [self.configuration])
            self._summary(item, summary)
            normalized = {key: deepcopy(value) for key, value in summary.items() if key != 'owner_update_stamp'}
            normalized['full_name'] = {'reference_role': role}
            baseline_rows = [row for row in self.baseline['clone_state']['dimensions']
                             if row['full_name'] == {'reference_role': role}]
            _require(len(baseline_rows) == 1 and _json(normalized) == _json(baseline_rows[0]),
                     role + '.baseline', 'Original current dimension metadata/values differ from the supplied current BASE.')
            bound.append(item)
        _require({item.role for item in bound} == ROLES
                 and all(sum(item.dimension_identity == other.dimension_identity for other in bound) == 1 for item in bound),
                 'baseline.dimensions', 'Original dimension canonical records/roles must be bijective.')
        return tuple(bound)

    @staticmethod
    def _anchor(anchor):
        _require(type(anchor) is dict, 'dimension_anchor', 'Typed original primary anchor required.')
        strategy = anchor.get('strategy')
        if strategy == 'direct_dimension_v1':
            _require(set(anchor) == {'strategy', 'dimension_pid_hex'}, 'dimension_anchor', 'Complete direct anchor required.')
            _hex(anchor['dimension_pid_hex'], 'dimension_anchor')
        else:
            _require(strategy == 'display_dimension_v1' and set(anchor) ==
                {'strategy', 'display_pid_hex', 'owner_pid_hex', 'dimension_index', 'display_type'}
                and type(anchor['dimension_index']) is int and anchor['dimension_index'] in (0, 1)
                and type(anchor['display_type']) is int
                and (anchor['dimension_index'] == 0 or anchor['display_type'] == 10),
                'dimension_anchor', 'Complete typed PRIMARY display slot anchor required.')
            _hex(anchor['display_pid_hex'], 'dimension_anchor'); _hex(anchor['owner_pid_hex'], 'dimension_anchor')

    def _queried(self, raw, interface):
        if self._query is not None:
            return self._query(raw, interface)
        from . import binding
        return binding.queried(raw, getattr(self.adapter._module, interface))

    def _membership(self, item):
        a, model, anchor = self.adapter, self.model, item.anchor
        role = item.role
        key = 'dimension_pid_hex' if anchor['strategy'] == 'direct_dimension_v1' else 'display_pid_hex'
        pid = _hex(anchor[key], role)
        raw, status = a._extension(model).GetObjectByPersistReference3(a._persistent_variant(pid))
        _require(type(status) is int and status in (0, 2) and raw is not None,
                 role, 'PRIMARY PID must actually return a retained object with exact state0/2; null is not membership.')
        if key == 'dimension_pid_hex':
            dimension = self._queried(raw, 'IDimension')
        else:
            try:
                display = self._queried(raw, 'IDisplayDimension')
            except Exception as error:
                # Only a normally returned E_NOINTERFACE permits the documented
                # annotation-to-display association; never lost-call fallback.
                if getattr(error, 'hresult', None) != -2147467262:
                    raise
                annotation = self._queried(raw, 'IAnnotation')
                _require(type(annotation.GetType()) is int and annotation.GetType() == 4,
                         role, 'Primary PID returned an unrelated annotation.')
                display = self._queried(annotation.GetSpecificAnnotation(), 'IDisplayDimension')
                current = self._queried(display.GetAnnotation(), 'IAnnotation')
                _require(a.identity(current) == a.identity(annotation), role, 'Annotation/display association changed.')
            _require(display is not None and a.identity(display) == item.display_identity
                     and a.persistent_id(model, display) == pid
                     and type(display.GetType()) is int and display.GetType() == anchor['display_type'],
                     role, 'Raw primary display is not its retained canonical display/type.')
            dimension = self._queried(display.GetDimension2(anchor['dimension_index']), 'IDimension')
        _require(dimension is not None and a.identity(dimension) == item.dimension_identity
                 and a.identity(a.dimension_object(item.record)) == item.dimension_identity
                 and a.identity(item.record.owner) == item.owner_identity
                 and item.record.owner_tree_identity == item.owner_identity,
                 role, 'Current primary PID must retain ORIGINAL IDimension/owner canonical identities.')
        displays = _array(item.record.displays, role + '.displays', 8)
        _require(tuple(a.identity(display) for display in displays) == item.displays,
                 role + '.displays', 'Original retained display inventory changed.')
        owner = self._queried(dimension.GetFeatureOwner(), 'IFeature')
        _require(owner is not None and a.identity(owner) == item.owner_identity,
                 role, 'Actual current IDimension owner differs from its original canonical owner.')
        resolve_retained_feature_pid(a, model, item.owner_pid, item.owner_identity)
        return dict(role=role, primary_pid_state=status, anchor=deepcopy(anchor),
                    original_dimension_canonical_confirmed=True, original_owner_canonical_confirmed=True)

    def _defaults(self):
        # No native imports on module import / pure test discovery.
        from . import binding
        from .cad_native_first_save_snapshot import (_extrusion, _sketch, _properties,
            _configuration, _empty_auxiliary_data, _display_data, _annotations)
        from .cad_rectangle_annotation_views import rectangle_annotation_view_bindings
        return dict(extrusion=_extrusion, sketch=_sketch, properties=_properties,
            configuration_state=_configuration, auxiliary_data=_empty_auxiliary_data,
            display_data=_display_data, annotations=_annotations,
            annotation_view_bindings=rectangle_annotation_view_bindings,
            material=lambda a, model, cfg: binding.wrap(model, a._module.IPartDoc).GetMaterialPropertyName2(cfg),
            selection_count=lambda a, model: binding.wrap(model.SelectionManager,
                a._module.ISelectionMgr).GetSelectedObjectCount2(-1))

    def _read(self, field, *arguments):
        try:
            getters = self._getters if self._getters is not None else self._defaults()
            _require(field in getters and callable(getters[field]), field, 'Concrete native getter missing.')
            value = getters[field](*arguments)
            _require(value is not None, field, 'Native getter returned unavailable data.')
            return value
        except Exception as error:
            _fail(field, str(error))

    @staticmethod
    def _call(field, function, *arguments):
        try:
            return function(*arguments)
        except Exception as error:
            _fail(field, str(error))

    def capture(self):
        opening = self._opening()
        a, model, cfg = self.adapter, self.model, self.configuration
        watch = a.watch_part(model)
        try:
            sequence = watch.poll()
            features, rows = self._features()
            _require(len(features) == len(self._feature_records)
                     and all(a.identity(feature) == original[1] for feature, original in zip(features, self._feature_records)),
                     'features', 'Complete original feature canonical census changed.')
            _require(rows[self._extrusion_index]['suppressed'] is True, 'features.extrusion', 'Owned extrusion must actually be suppressed.')
            references = []
            for index, pid in self._feature_pids.items():
                resolve_retained_feature_pid(a, model, pid, self._feature_records[index][1])
                references.append(dict(kind='feature', role='feature:' + str(index), token=pid.hex()))
            bodies = _array(a.bodies(model, 'all'), 'bodies', 1)
            geometry = self._call('geometry', a.dimension_geometry_snapshot, model)
            _require(bodies == [] and geometry == {'representation': 'planar_polyhedral_brep_v1', 'bodies': []},
                     'geometry', 'Actual complete body and BREP census must be bodyless.')
            memberships, dimensions, stamps = [], [], {}
            for item in self._dimensions:
                memberships.append(self._call(item.role + '.membership', self._membership, item))
                try:
                    summary = a.dimension_summary(item.record, [cfg])
                except Exception as error:
                    _fail(item.role + '.dimension_summary', str(error))
                self._summary(item, summary)
                stamps[item.role] = summary['owner_update_stamp']
                clone = {key: deepcopy(value) for key, value in summary.items() if key != 'owner_update_stamp'}
                clone['full_name'] = {'reference_role': item.role}
                dimensions.append(clone)
                references.append(dict(kind='dimension', role=item.role, token=_json(item.anchor)))
            roles = {row['native_id']: 'feature:' + str(index) for index, row in enumerate(rows)}
            extrusion = self._read('extrusion', a, self.extrusion)
            _require(type(extrusion) is dict and extrusion.get('FeatureScope') is False
                     and type(extrusion.get('AutoSelect')) is bool,
                     'extrusion.AutoSelect', 'Observe the actual unavailable-scope boolean before semantic encoding.')
            raw_auto_select = extrusion['AutoSelect']
            extrusion = deepcopy(extrusion)
            extrusion['AutoSelect'] = {'availability': 'unavailable_feature_scope_disabled_v1'}
            sketch = self._read('sketch', a, model, self.sketch, roles, references)
            context = self._call('controls', a.dimension_context, model)
            _require(type(context) is dict and context, 'controls', 'Complete actual control inventory required.')
            expected_controls = set(self.baseline['clone_state']['controls']) | {'active_document','read_only'}
            _require(set(context) == expected_controls, 'controls', 'No original native control field may be dropped.')
            inventories = self._call('equation_reference_inventory', a.feature_deletion_context, model)
            _require(type(inventories) is dict and {'equations','external_references','auxiliary_references'} <= set(inventories),
                     'equation_reference_inventory', 'Complete enabled/disabled and auxiliary inventories required.')
            equations = inventories['equations']
            _require(type(equations) is dict and {'enumerated_count','disabled_count','disabled_definitions_captured'} <= set(equations)
                     and type(equations['enumerated_count']) is int and type(equations['disabled_count']) is int
                     and equations['disabled_definitions_captured'] is True,
                     'equation_reference_inventory', 'Complete enabled/disabled equation proof required.')
            feature_refs = self._call('feature_external_reference_inventory', a.feature_external_references, features)
            _require(type(feature_refs) is dict and feature_refs, 'feature_external_reference_inventory', 'Actual full feature reference inventory required.')
            display = self._read('display_data', a, model, features, rows)
            records = tuple(item.record for item in self._dimensions)
            annotations = self._read('annotations', a, model, records, references)
            _array(annotations, 'annotations', 128)
            original_annotations = self.baseline['clone_state']['annotations']
            _require(len(annotations) == len(original_annotations)
                     and all(type(row) is dict and set(row) ==
                        {'role','type','visible','position','display_type','text','use_document_format','text_format'}
                        for row in annotations)
                     and {row['role'] for row in annotations} == {row['role'] for row in original_annotations},
                     'annotations', 'Full original display-dimension annotation inventory must actually remain readable.')
            for annotation in annotations:
                actual_refs = [row for row in references if row['kind'] == 'annotation' and row['role'] == annotation['role']]
                old_refs = [row for row in self.baseline['references'] if row['kind'] == 'annotation' and row['role'] == annotation['role']]
                _require(len(actual_refs) == len(old_refs) == 1 and actual_refs[0] == old_refs[0],
                         'annotations.references', 'Every annotation needs its actual exact original PID proof.')
            view_reader = _RetainedViewAdapter(a, self.model_identity, records)
            dimension_roles = {item.qualified['full_name']: item.role.removeprefix('dimension:') for item in self._dimensions}
            views = self._read('annotation_view_bindings', view_reader, model, display, dimension_roles)
            self._call('annotation_view_bindings', validated_view_bindings, display, views, {'width','height','depth'})
            planes = []
            for feature, row in zip(features, rows):
                if row['feature_type'] == 'RefPlane':
                    transform = _array(self._call('planes.transform', a.reference_plane_transform, feature), 'planes.transform', 16)
                    _require(len(transform) == 16 and all(type(v) in (int, float) and math.isfinite(v) for v in transform),
                             'planes.transform', 'All native plane transform values required.')
                    planes.append(dict(role=roles[row['native_id']], transform=[float(v).hex() for v in transform]))
            _require(len(planes) == 3, 'planes', 'All three original planes required.')
            units = _array(self._call('units', model.GetUnits), 'units', 16)
            _require(units and all(type(v) in (int, float, bool) and (type(v) is not float or math.isfinite(v)) for v in units),
                     'units', 'Complete actual finite units array required.')
            material = self._material(self._read('material', a, model, cfg), 'material')
            creation_controls = self._call('creation_controls', a.part_creation_controls, model)
            _require(type(creation_controls) is dict and set(creation_controls) ==
                     {'add_to_db','auto_solve','display_when_added','dimension_input'}
                     and all(type(value) is bool for value in creation_controls.values()),
                     'creation_controls', 'All current native creation controls required.')
            selection_count = self._read('selection_count', a, model)
            _require(type(selection_count) is int and 0 <= selection_count <= 256,
                     'selection_count', 'Complete actual selection census required.')
            parameters = self._parameters(dimensions, sketch, cfg)
            clone = dict(profile=PROFILE, features=rows, dependencies=self._call('dependencies', a.feature_dependencies, features),
                geometry=geometry, dimensions=dimensions, parameters=parameters, extrusion=extrusion, sketch=sketch,
                controls={key: deepcopy(value) for key, value in context.items() if key not in ('active_document','read_only')},
                equation_reference_inventory=inventories, feature_external_reference_inventory=feature_refs,
                planes=planes, properties=self._read('properties', a, model, cfg), units=units, annotations=annotations,
                configuration_state=self._read('configuration_state', a, model, cfg),
                auxiliary_data=self._read('auxiliary_data', a, model, features, rows), display_data=display,
                material=material, creation_controls=creation_controls)
            _require(all(type(clone[key]) is dict and clone[key] for key in ('dependencies','extrusion','sketch',
                'properties','configuration_state','auxiliary_data','display_data')), 'inventories', 'No full inventory may be unavailable.')
            for field in ('extrusion','sketch','properties','configuration_state','auxiliary_data','display_data',
                          'equation_reference_inventory','feature_external_reference_inventory','dependencies'):
                _require(set(clone[field]) == set(self.baseline['clone_state'][field]), field,
                         'The complete declared field inventory must remain observable; no dropped fields.')
            self._call('dependencies', feature_relations, clone)
            self._call('feature_external_reference_inventory', empty_feature_external_inventory, clone)
            for item in self._dimensions:
                self._call(item.role + '.membership', self._membership, item)  # No new enumeration.
            closing_features, closing_rows = self._features()
            _require(all(a.identity(feature) == original[1] for feature, original in zip(closing_features, self._feature_records))
                     and len(closing_features) == len(self._feature_records)
                     and _json(closing_rows) == _json(rows) and a.bodies(model, 'all') == []
                     and self._opening() == opening and watch.poll() == sequence,
                     'closing_boundary', 'Target/configuration/features/bodies/events changed during read-only capture.')
            _require(opening['title'] == self.baseline['native_observations']['document_dimension_namespace'],
                     'document_dimension_namespace', 'Current unsaved namespace differs from the original qualified primary roles.')
            result = dict(scope=SCOPE, configuration=cfg, configurations=[cfg], solid_body_count=0,
                selection_count=selection_count, clone_state=clone,
                references=sorted(references, key=lambda row: (row['kind'],row['role'])),
                native_observations=dict(document_dimension_namespace=opening['title'],
                    qualified_dimensions=deepcopy(self.baseline['native_observations']['qualified_dimensions']),
                    unavailable_extrusion_auto_select=raw_auto_select, annotation_view_bindings=views,
                    retained_dimension_membership=memberships, dimension_owner_update_stamps=stamps,
                    actual_dimension_context=context,
                    body_intrinsics=dict(availability='unavailable_current_body_absent_v1',
                        source='actual_complete_body_census', current_body_count=0),
                    current_body_census_empty=True, current_feature_canonical_census_confirmed=True))
            return _detached(result)
        finally:
            watch.close()

    def _summary(self, item, summary):
        role, cfg = item.role, self.configuration
        _require(type(summary) is dict and set(summary) == DIMENSION_KEYS
                 and summary['full_name'] == item.qualified['full_name'] and summary['name'] == item.qualified['name']
                 and type(summary['parameter_type']) is int and summary['parameter_type'] == 0 and summary['unit'] == 'mm'
                 and type(summary['driven_state']) is int and type(summary['owner_update_stamp']) is int,
                 role + '.metadata', 'Complete CURRENT metadata must bind the original qualified primary role.')
        for key in ('read_only','reference','design_table','linked'):
            _require(type(summary[key]) is bool, role + '.' + key, 'Actual native bool required.')
        for key in ('values_si','values'):
            values = summary[key]
            _require(type(values) is dict and set(values) == {cfg}
                     and type(values[cfg]) in (int,float) and math.isfinite(values[cfg]),
                     role + '.' + key, 'Full finite native named-configuration values required.')
        _array(summary['display_dimensions'], role + '.display_dimensions', 8)
        _array(summary['write_blockers'], role + '.write_blockers', 32)
        tolerance = summary['tolerance']
        _require(type(tolerance) is dict and set(tolerance) == {'type','values_si'}
                 and type(tolerance['type']) is int, role + '.tolerance', 'Full native tolerance outputs required.')
        values = _array(tolerance['values_si'], role + '.tolerance.values_si', 2)
        _require((tolerance['type'] == 0 or len(values) == 2)
                 and all(type(value) in (int,float) and math.isfinite(value) for value in values),
                 role + '.tolerance', 'Native tolerance array unavailable/incomplete.')
        owner = summary['owner']
        index = self._extrusion_index if role == 'dimension:depth' else self._sketch_index
        _require(type(owner) is dict and owner.get('native_id') == self._feature_records[index][2]['native_id'],
                 role + '.owner', 'Summary must describe the already canonical/PID-proven original owner.')

    @staticmethod
    def _material(value, field):
        _require(type(value) in (tuple,list) and len(value) == 2 and all(type(v) is str for v in value),
                 field, 'Complete actual material name/database outputs required.')
        return list(value)

    @staticmethod
    def _parameters(dimensions, sketch, cfg):
        values = {row['full_name']['reference_role']: row['values_si'][cfg] for row in dimensions}
        _require(set(values) == ROLES and all(value >= 1e-6 for value in values.values()),
                 'parameters', 'Current original width/height/depth values required.')
        frame = sketch['reference_plane']['transform']
        _require(type(frame) is list and len(frame) == 16, 'parameters.plane_transform', 'Current native plane frame required.')
        try:
            frame = [float.fromhex(value) for value in frame]
        except (TypeError, ValueError) as error:
            _fail('parameters.plane_transform', str(error))
        _require(all(math.isfinite(value) for value in frame), 'parameters.plane_transform', 'Finite native frame required.')
        return dict(width_m=values['dimension:width'], height_m=values['dimension:height'],
            depth_m=values['dimension:depth'], axes={axis: {'reference_role':'dimension:' + axis} for axis in ('width','height')},
            plane_transform=frame)
