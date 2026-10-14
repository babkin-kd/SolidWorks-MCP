"""Read-only, attestation-only retained observer for the finite public B2 route.

The root first verifies the original public B1 journal and HWND creation bridge.
Their role/PID receipts identify the exact original features; names/GetID never
address a model or feature here. This context is NOT production ownership and
cannot authorize mutation, cleanup or native acceptance. No COM connection,
flag/selection setter, activation, rebuild, Undo or replacement is performed.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re
import threading
from types import SimpleNamespace

from solidworks_mcp.cad_owned_suppression_snapshot import (
    OwnedSuppressionSnapshot, PROFILE as SUPPRESSED, SCOPE as SUPPRESSED_SCOPE, ROLES)
from solidworks_mcp.jobs import ExecutionFailure, _json
from solidworks_mcp.native_first_save import SNAPSHOT_KEYS
from solidworks_mcp.owned_rectangle_feature import _canonical
from solidworks_mcp.rectangle_annotation_views import validated_view_bindings
from solidworks_mcp.rectangle_snapshot import BASE, SKETCH, validated_rectangle_snapshot


ROLE_FIELDS = {'document_id', 'configuration', 'object_id', 'kind', 'creation_operation_id',
               'native_id', 'feature_role', 'persistent_id_hex'}
SUPPRESSED_FIELDS = {'profile', 'features', 'dependencies', 'geometry', 'dimensions', 'parameters',
    'extrusion', 'sketch', 'controls', 'equation_reference_inventory',
    'feature_external_reference_inventory', 'planes', 'properties', 'units', 'annotations',
    'configuration_state', 'auxiliary_data', 'display_data', 'material', 'creation_controls'}
SUPPRESSED_NATIVE_FIELDS = {'document_dimension_namespace', 'qualified_dimensions',
    'unavailable_extrusion_auto_select', 'annotation_view_bindings', 'retained_dimension_membership',
    'dimension_owner_update_stamps', 'actual_dimension_context', 'body_intrinsics',
    'current_body_census_empty', 'current_feature_canonical_census_confirmed'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _detach(value):
    return json.loads(_json(value))


def _pid(value):
    _require(type(value) is str and bool(value), 'Nonempty original native PID required.')
    try:
        pid = bytes.fromhex(value)
    except ValueError as error:
        raise ValueError('Canonical lowercase native PID bytes.hex() required.') from error
    _require(bool(pid) and pid.hex() == value, 'Canonical lowercase native PID bytes.hex() required.')
    return pid


def _snapshot(value):
    if type(value) is dict and value.get('scope') == SUPPRESSED_SCOPE:
        _require(set(value) == SNAPSHOT_KEYS and value.get('configurations') == [value.get('configuration')]
            and type(value.get('configuration')) is str and bool(value['configuration'])
            and type(value.get('solid_body_count')) is int and value['solid_body_count'] == 0
            and type(value.get('selection_count')) is int and value['selection_count'] == 0,
            'Complete typed suppressed rectangle observation required.')
        data, native = value.get('clone_state'), value.get('native_observations')
        _require(type(data) is dict and set(data) == SUPPRESSED_FIELDS and data.get('profile') == SUPPRESSED
            and data.get('geometry') == {'representation': 'planar_polyhedral_brep_v1', 'bodies': []}
            and type(native) is dict and set(native) == SUPPRESSED_NATIVE_FIELDS
            and native.get('current_body_census_empty') is True
            and native.get('current_feature_canonical_census_confirmed') is True
            and native.get('body_intrinsics') == dict(availability='unavailable_current_body_absent_v1',
                source='actual_complete_body_census', current_body_count=0),
            'Complete actual bodyless producer inventories required.')
        _require(type(data.get('dimensions')) is list and len(data['dimensions']) == 3
            and {row['full_name']['reference_role'] for row in data['dimensions']} == ROLES,
            'All three actually observed suppressed dimensions required.')
        members = native.get('retained_dimension_membership')
        _require(type(members) is list and len(members) == 3
            and {row.get('role') for row in members} == ROLES
            and all(type(row.get('primary_pid_state')) is int and row['primary_pid_state'] in (0, 2)
                and row.get('original_dimension_canonical_confirmed') is True
                and row.get('original_owner_canonical_confirmed') is True for row in members),
            'Actual original primary dimension PID/canonical membership required.')
        refs = value.get('references')
        _require(type(refs) is list and bool(refs)
            and all(type(row) is dict and set(row) == {'kind', 'role', 'token'} for row in refs)
            and len({(row['kind'], row['role']) for row in refs}) == len(refs)
            and len({row['token'] for row in refs}) == len(refs), 'Complete distinct raw reference inventory required.')
        validated_view_bindings(data['display_data'], native['annotation_view_bindings'], {'width','height','depth'})
        return _detach(value)
    return validated_rectangle_snapshot(value)


def _local_chain(previous, current):
    old_profile, new_profile = previous['clone_state']['profile'], current['clone_state']['profile']
    _require((old_profile, new_profile) in ((BASE, BASE), (BASE, SUPPRESSED), (SUPPRESSED, BASE),
        (SUPPRESSED, SUPPRESSED), (BASE, SKETCH), (SKETCH, SKETCH)), 'Unsupported local B2 profile transition.')
    old = previous['native_observations']['annotation_view_bindings']
    new = current['native_observations']['annotation_view_bindings']
    axes = {'width', 'height'} if new_profile == SKETCH else {'width', 'height', 'depth'}
    old_rows = dict(zip(old['view_ids'], previous['clone_state']['display_data']['annotation_views']))
    new_rows = dict(zip(new['view_ids'], current['clone_state']['display_data']['annotation_views']))
    retained = set(old_rows)
    if old_profile == BASE and new_profile == SKETCH:
        depth_view = old['dimension_views']['depth']
        _require(depth_view not in {old['dimension_views'][axis] for axis in axes},
            'Original depth view must be distinct from borrowed sketch dimension views.')
        retained.remove(depth_view)
    _require(set(new_rows) == retained
        and all(_json(new_rows[key]) == _json(old_rows[key]) for key in retained)
        and all(new['dimension_views'][axis] == old['dimension_views'][axis] for axis in axes),
        'Original local annotation view incarnations/rows/borrowed axis bindings changed.')
    originals = {row['role']: row['token'] for row in previous['references'] if row['kind'] == 'dimension'}
    actual = {row['role']: row['token'] for row in current['references'] if row['kind'] == 'dimension'}
    _require(set(actual) == {'dimension:' + axis for axis in axes}
        and all(actual['dimension:' + axis] == originals['dimension:' + axis] for axis in axes),
        'Original local primary dimension anchors changed.')


def compare_b2_snapshot(actual, expected, *, previous=None):
    """B1 compare_stage_snapshot design, extended to SUPPRESSED without edits.

Only each adapter's av_UUID namespace is factored out. Every full view row,
its multiplicity and its exact width/height/depth partition remain in the
comparison. All other fields, native primary anchors included, remain exact.
Local incarnation preservation is additionally enforced by AttestationOnly.
"""
    def normal_form(value):
        snapshot = _snapshot(value)
        profile = snapshot['clone_state']['profile']
        _require(profile in (BASE, SKETCH, SUPPRESSED), 'Only the finite B2 profiles are admitted.')
        axes = {'width','height'} if profile == SKETCH else {'width','height','depth'}
        display = snapshot['clone_state']['display_data']
        binding = snapshot['native_observations']['annotation_view_bindings']
        validated_view_bindings(display, binding, axes)
        relations = [dict(view=deepcopy(row), axes=sorted(axis for axis, owner in binding['dimension_views'].items()
                                                       if owner == identifier))
                     for identifier, row in zip(binding['view_ids'], display['annotation_views'])]
        relations.sort(key=_json)
        display['annotation_views'] = [row['view'] for row in relations]
        snapshot['native_observations']['annotation_view_bindings'] = dict(scope=binding['scope'], relations=relations)
        return snapshot
    try:
        _require(_json(normal_form(actual)) == _json(normal_form(expected)),
                 'Complete cross-process snapshot/view-row/axis-partition differs.')
        if previous is not None:
            _local_chain(_snapshot(previous), _snapshot(actual))
    except (ExecutionFailure, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Complete typed independent B2 snapshot comparison required: ' + str(error)) from error
    return dict(complete_relation_bijection_verified=True, local_transition_verified=previous is not None,
                accepted=False, native_acceptance=False, cleanup_authorized=False, mutation_authorized=False)


@dataclass(frozen=True)
class _AttestationBinding:
    configuration: str
    kind: str
    model: object
    model_identity: object
    configuration_identity: object
    feature: object
    feature_identity: object
    persistent_id: bytes
    native_id: int
    receipt: object


class AttestationOnly:
    """Retain independent current native handles before any suppression.

``bridge`` is the root's verified original public B1 HWND creation bridge;
``model_identity`` is its already-held canonical IUnknown. The two exact
ROLE_FIELDS receipts come from the original public B1 committed sketch and
extrusion journal snapshots/values, never a name or fresh GetID lookup.
``baseline_snapshot`` is this adapter's independently observed CURRENT BASE
(possibly after root's scalar/rename checks), not a server snapshot substituted
for unavailable data. Only baseline anchors/local views are retained for proof.
Trusted ``getters``/``query`` dependencies are solely pure-test injections into
the actual production OwnedSuppressionSnapshot. No registry is instantiated.
"""
    def __init__(self, adapter, model, baseline_snapshot, *, bridge, model_identity,
                 extrusion_role, sketch_role, getters=None, query=None):
        self.adapter, self.model = adapter, model
        self._thread = threading.get_ident()
        self.model_identity = _canonical(model_identity)
        self.baseline = validated_rectangle_snapshot(baseline_snapshot)
        self.configuration = self.baseline['configuration']
        _require(self.baseline['clone_state']['profile'] == BASE, 'Retain before suppression on an actual BASE.')
        _require(type(bridge) is dict and type(bridge.get('document_id')) is str and bridge['document_id']
            and type(bridge.get('hwnd')) is int and 0 < bridge['hwnd'] < 2**63,
            'Original explicit B1 document/HWND bridge required.')
        self.bridge = _detach(bridge)
        self.document_id = bridge['document_id']
        self.configuration_identity = _canonical(adapter.configuration_identity(model, self.configuration))
        self.roles = {kind: self._role(receipt, kind) for kind, receipt in
                      (('extrusion', extrusion_role), ('sketch', sketch_role))}
        _require(self.roles['extrusion']['object_id'] != self.roles['sketch']['object_id']
            and self.roles['extrusion']['creation_operation_id'] != self.roles['sketch']['creation_operation_id']
            and self.roles['extrusion']['persistent_id_hex'] != self.roles['sketch']['persistent_id_hex'],
            'Original B1 sketch and extrusion roles must be distinct.')
        self._deleted = False
        self._opening()
        self.extrusion, self.extrusion_identity = self._retain(self.roles['extrusion'])
        self.sketch, self.sketch_identity = self._retain(self.roles['sketch'])
        actual = validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(model))
        _require(_json(actual) == _json(self.baseline), 'Current independently captured BASE changed before retention.')
        binding = _AttestationBinding(self.configuration, 'extrusion', model, self.model_identity,
            self.configuration_identity, self.extrusion, self.extrusion_identity,
            _pid(self.roles['extrusion']['persistent_id_hex']), self.roles['extrusion']['native_id'],
            SimpleNamespace(borrowed_sketch=self.sketch, borrowed_sketch_identity=self.sketch_identity))
        self._producer = OwnedSuppressionSnapshot(adapter, model, binding, self.baseline, getters=getters, query=query)
        closing = validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(model))
        _require(_json(closing) == _json(actual), 'Current BASE changed while retaining original native records.')
        self._opening()

    def _role(self, value, kind):
        _require(type(value) is dict and set(value) == ROLE_FIELDS and value.get('kind') == kind
            and value.get('document_id') == self.document_id and value.get('configuration') == self.configuration
            and type(value.get('native_id')) is int
            and type(value.get('object_id')) is str and re.fullmatch(r'feat_[0-9a-f]{32}', value['object_id']) is not None
            and type(value.get('creation_operation_id')) is str and value['creation_operation_id'],
            'Exact original public B1 role receipt required.')
        pid = _pid(value['persistent_id_hex'])
        rows = self.baseline['clone_state']['features']
        matches = [(index, row) for index, row in enumerate(rows) if row['native_id'] == value['native_id']]
        _require(len(matches) == 1 and value['feature_role'] == 'feature:' + str(matches[0][0])
            and matches[0][1]['feature_type'] in (('Boss', 'Extrusion') if kind == 'extrusion' else ('ProfileFeature',))
            and matches[0][1]['suppressed'] is False, 'Original role must bind exact current BASE native feature.')
        refs = [row for row in self.baseline['references']
                if row['kind'] == 'feature' and row['role'] == value['feature_role']]
        _require(len(refs) == 1 and refs[0]['token'] == pid.hex(), 'Original B1 role/PID differs from independent BASE.')
        return _detach(value)

    def _opening(self):
        _require(threading.get_ident() == self._thread, 'Use the original observer owning apartment.')
        a = self.adapter
        _require(a.identity(self.model) == self.model_identity
            and a.configuration_identity(self.model, self.configuration) == self.configuration_identity,
            'Original canonical model/configuration changed.')
        windows = a.native_close_windows()
        _require(type(windows) in (list, tuple) and sum(window['hwnd'] == self.bridge['hwnd']
            and a.identity(current) == self.model_identity for current, window in windows) == 1
            and sum(window['hwnd'] == self.bridge['hwnd'] for current, window in windows) == 1,
            'Original HWND must still bind one exact canonical model.')
        observed = a.snapshot(self.model)
        _require(observed['document_type'] == 'part' and observed['path'] == ''
            and observed['active_configuration'] == self.configuration
            and observed['configurations'] == [self.configuration], 'Original unsaved current configuration required.')
        return _detach(observed)

    def _retain(self, role):
        pid = _pid(role['persistent_id_hex'])
        feature = self.adapter.resolve_persistent_id(self.model, pid, 'feature')
        _require(feature is not None, 'Original current B1 PID must resolve before suppression.')
        identity = _canonical(self.adapter.identity(feature))
        self._current_feature(role, identity)
        return feature, identity

    def _current_feature(self, role, identity):
        a, pid = self.adapter, _pid(role['persistent_id_hex'])
        members = a.features(self.model)
        _require(type(members) in (list, tuple), 'Complete current native feature census required.')
        matches = [feature for feature in members if a.persistent_id(self.model, feature) == pid]
        _require(len(matches) == 1 and a.identity(matches[0]) == identity,
            'Original PID must bind one exact retained canonical current feature.')
        resolved = a.resolve_persistent_id(self.model, pid, 'feature')
        _require(resolved is not None and a.identity(resolved) == identity
            and a.persistent_id(self.model, resolved) == pid, 'Current original native PID roundtrip changed.')
        return dict(persistent_id_hex=pid.hex(), original_canonical_confirmed=True, unique_current_membership=True)

    def _deleted_pid(self):
        a, pid = self.adapter, _pid(self.roles['extrusion']['persistent_id_hex'])
        raw, status = a._extension(self.model).GetObjectByPersistReference3(a._persistent_variant(pid))
        _require(type(status) is int and status in (1, 4) and raw is None,
            'Deleted original PID must normally return typed state1/4 plus null.')
        members = a.features(self.model)
        _require(type(members) in (list, tuple)
            and all(a.persistent_id(self.model, feature) != pid for feature in members),
            'Deleted original PID still occurs in the actual current feature census.')
        return dict(persistent_id_hex=pid.hex(), raw_pid_state=status, raw_object_is_null=True,
                    absent_from_current_feature_census=True)

    def _local_anchors(self, current):
        _local_chain(self.baseline, current)

    def capture(self, profile, *, expected_snapshot=None):
        """Observe SUPPRESSED, returned BASE or deleted SKETCH after terminal calls.

After SKETCH is observed, the old extrusion/producer getters are never called
again. Deletion checks only the OLD RAW PID and CURRENT canonical sketch/census.
The root supplies full session/neighbor/quiescence proofs and public receipts.
"""
        _require(profile in (BASE, SKETCH, SUPPRESSED), 'Explicit finite observed profile required.')
        _require(not self._deleted or profile == SKETCH, 'Deleted retained extrusion cannot be observed or re-adopted.')
        opening = self._opening()
        reader = self._producer.capture if profile == SUPPRESSED else lambda: self.adapter.rectangle_construction_snapshot(self.model)
        first, current = _snapshot(reader()), _snapshot(reader())
        _require(_json(first) == _json(current) and current['clone_state']['profile'] == profile
            and current['configuration'] == self.configuration,
            'Complete current rectangle observation changed or belongs to another profile.')
        self._local_anchors(current)
        sketch = self._current_feature(self.roles['sketch'], self.sketch_identity)
        if profile == SKETCH:
            extrusion = self._deleted_pid()
            self._deleted = True
        elif profile == BASE:
            extrusion = self._current_feature(self.roles['extrusion'], self.extrusion_identity)
        else:
            # Actual production producer re-proves suppressed extrusion state2
            # and retained canonical membership; generic BASE resolver is wrong.
            extrusion = dict(persistent_id_hex=self.roles['extrusion']['persistent_id_hex'],
                             production_retained_suppressed_membership_confirmed=True)
        _require(_json(opening) == _json(self._opening()), 'Read-only observer changed/raced native metadata.')
        comparison = compare_b2_snapshot(current, expected_snapshot) if expected_snapshot is not None else None
        return dict(scope='b2_attestation_only_native_observation_v1', document_id=self.document_id,
            profile=profile, snapshot=current, sketch_membership=sketch, extrusion_membership=extrusion,
            comparison=comparison, accepted=False, native_acceptance=False,
            cleanup_authorized=False, mutation_authorized=False)
