"""STA-local ownership of exact successfully returned rectangle features.

Registration retains server native handles after domain commit, before JobRunner
may publish its terminal row. Admission rechecks the real terminal JobStore row.
Neither a receipt nor this binding authorizes deletion/suppression or proves a
complete current impact graph/revision. Callers provide those separate gates.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import threading

from .documents import rejected
from .jobs import _json
from .rectangle_snapshot import EMPTY, SKETCH, BASE, validated_rectangle_snapshot
from .retained_feature_resolution import resolve_retained_feature_pid


PROFILES = {
    'sketch.create_rectangle': ('sketch', 'empty_part_rectangle_sketch_v1', EMPTY, SKETCH),
    'part.extrude_rectangle': ('extrusion', 'closed_rectangle_blind_extrusion_v1', SKETCH, BASE),
}
RECEIPT_FIELDS = ('attempted', 'native_call_returned', 'pending_creation',
    'pending_sketch_close', 'sketch_closed', 'selection_uncertain', 'restore_attempted',
    'restored', 'pending_native_step', 'native_step_journal_failed', 'view_state_uncertain')


def _require(condition, message, code='owned_rectangle_binding_unconfirmed'):
    if not condition:
        raise rejected(code, message)


def _detach(value):
    return json.loads(_json(value))


def _canonical(identity):
    # Native canonical IUnknown is retained, deliberately not hashed/serialized.
    _require(identity is not None and type(identity) not in
             (str, int, float, bool, bytes, bytearray, dict, list, tuple, set, frozenset),
             'Retained native canonical identity required; JSON/scalar identity is unsupported.')
    return identity


@dataclass(frozen=True)
class OwnedRectangleFeature:
    creation_operation_id: str
    connection_epoch: str
    document_id: str
    configuration: str
    object_id: str
    kind: str
    persistent_id: bytes
    native_id: int
    model: object
    model_identity: object
    configuration_identity: object
    feature: object
    feature_identity: object
    receipt: object
    _creation_operation: str
    _creation_request_id: str
    _creation_payload: dict
    _creation_result: dict
    _checkpoint_before: dict
    _checkpoint_verification: dict
    _baseline_target_snapshot: dict
    _created_target_snapshot: dict

    @property
    def creation_result(self):
        return deepcopy(self._creation_result)

    @property
    def baseline_target_snapshot(self):
        return deepcopy(self._baseline_target_snapshot)

    @property
    def created_target_snapshot(self):
        return deepcopy(self._created_target_snapshot)


class OwnedRectangleFeatureRegistry:
    """One current connection/apartment; no reconstruction from durable JSON.

    ``check_capacity`` belongs before a construction write. ``register`` belongs
    after MutationCoordinator returns its verified commit; it can still fail.
    A failure at that late boundary must be retained by the caller as unknown,
    never used to trigger another native inverse. ``resolve`` admits only a
    succeeded original creation job and returns (internal binding, feature).
    """

    def __init__(self, documents, store, connection_epoch, *, max_per_document=2, max_documents=32):
        _require(type(connection_epoch) is str and bool(connection_epoch), 'Explicit connection epoch required.')
        _require(type(max_per_document) is int and 1 <= max_per_document <= 2
                 and type(max_documents) is int and 1 <= max_documents <= 32,
                 'Use the bounded one-sketch/one-extrusion ownership budget.')
        self.documents, self.adapter, self.store = documents, documents.adapter, store
        self.connection_epoch = connection_epoch
        self.max_per_document, self.max_documents = max_per_document, max_documents
        self._thread = threading.get_ident()
        self._bindings = {}

    def _check_thread(self):
        _require(threading.get_ident() == self._thread, 'Ownership access requires its owning STA.', 'wrong_apartment')

    def check_capacity(self, document_id):
        self._check_thread()
        _require(type(document_id) is str and bool(document_id), 'Explicit document ID required.')
        docs = {key[0] for key in self._bindings}
        _require(sum(key[0] == document_id for key in self._bindings) < self.max_per_document
                 and (document_id in docs or len(docs) < self.max_documents),
                 'Owned rectangle budget exhausted before construction.', 'owned_rectangle_budget')

    def retire_absent_documents(self):
        """Discard bindings absent from the complete refreshed native roster.

        No close, deletion or job reconciliation occurs. Refresh and every
        canonical comparison finish before changing the registry, so a failed
        census keeps all retained ownership. A replaced model is never adopted.
        """
        self._check_thread()
        self.documents._refresh()
        live = [(entry.document_id, _canonical(entry.identity))
                for entry in self.documents._entries]
        retired = [key for key, binding in self._bindings.items()
                   if not any(document_id == binding.document_id
                              and identity == binding.model_identity
                              for document_id, identity in live)]
        for key in retired:
            del self._bindings[key]
        return len(retired)

    def _row(self, operation_id, document_id, configuration, *, terminal):
        row = self.store.get(operation_id)
        mutation = row.get('mutation')
        _require(row['operation'] in PROFILES and row['payload']['mutates'] is True
                 and type(mutation) is dict, 'Exact supported creation checkpoint required.')
        _require(row['status'] == 'succeeded' if terminal else row['status'] in ('running', 'succeeded'),
                 'Only the terminal succeeded creation can admit a subsequent operation.'
                 if terminal else 'Registration requires domain committed creation.')
        expected_phase = 'committed' if row['status'] == 'succeeded' else 'prepared'
        verification = mutation.get('verification') or {}
        _require(mutation['operation_id'] == operation_id and mutation['phase'] == expected_phase
                 and mutation['connection_epoch'] == self.connection_epoch
                 and mutation['document_id'] == document_id and mutation['configuration'] == configuration
                 and verification.get('outcome') == 'committed'
                 and type(verification.get('evidence')) is dict and bool(verification['evidence'])
                 and mutation['reconciliation'] is None, 'Creation checkpoint scope/outcome changed.')
        for key, value in (('document_id', document_id), ('configuration', configuration),
                           ('expected_revision', mutation['expected_revision'])):
            _require(row['payload']['context'].get(key) == value
                     and row['payload']['arguments'].get(key) == value,
                     'Durable creation payload/context differs from its checkpoint.')
        _require(row['error'] is None, 'Creation error prohibits ownership admission.')
        return row

    def _context(self, document_id, configuration):
        entry, observed = self.documents.resolve(document_id, configuration)
        _require(entry.document_id == document_id and observed.get('document_type') == 'part'
                 and observed.get('path') == '' and observed.get('configurations') == [configuration]
                 and observed.get('active_configuration') == configuration,
                 'Only the exact unsaved active one-configuration part is supported.')
        model_identity = _canonical(self.adapter.identity(entry.model))
        _require(entry.identity == model_identity, 'Document entry/model canonical identity differs.')
        configuration_identity = _canonical(self.adapter.configuration_identity(entry.model, configuration))
        return entry, model_identity, configuration_identity

    @staticmethod
    def _receipt(receipt, kind):
        evidence = {key: getattr(receipt, key, None) for key in RECEIPT_FIELDS}
        _require(evidence['attempted'] is True and evidence['native_call_returned'] is True
                 and (kind != 'sketch' or evidence['sketch_closed'] is True)
                 and all(evidence[key] is False for key in ('pending_creation', 'pending_sketch_close',
                     'selection_uncertain', 'restore_attempted', 'restored', 'native_step_journal_failed',
                     'view_state_uncertain')) and evidence['pending_native_step'] is None,
                 'Original creation receipt has unresolved/restored effects.')
        return evidence

    def register(self, operation_id, *, document_id, configuration, result, receipt):
        self.check_capacity(document_id)
        _require(type(configuration) is str and bool(configuration), 'Explicit configuration required.')
        _require(not any(binding.creation_operation_id == operation_id for binding in self._bindings.values()),
                 'Creation ownership cannot be registered twice.')
        row = self._row(operation_id, document_id, configuration, terminal=False)
        kind, scope, before_profile, after_profile = PROFILES[row['operation']]
        result = _detach(result)
        _require(type(result) is dict and result.get('verified') is True, 'Full committed creation result required.')
        value, before, after = result.get('value'), result.get('before'), result.get('after')
        _require(type(value) is dict and type(before) is dict and type(after) is dict
                 and value.get('document_id') == document_id and value.get('configuration') == configuration
                 and value.get('kind') == kind and before.get('scope') == scope,
                 'Result operation/target profile differs from exact creation.')
        object_id, native_id = value.get('object_id'), value.get('created_native_id')
        alias = 'sketch_object_id' if kind == 'sketch' else 'feature_object_id'
        _require(type(object_id) is str and object_id.startswith('feat_') and len(object_id) == 37
                 and value.get(alias) == object_id and type(native_id) is int,
                 'Returned opaque feature ID and native GetID binding required.')
        _require((document_id, object_id) not in self._bindings, 'Object ownership cannot be replaced.')
        checkpoint = row['mutation']
        _require(_json(checkpoint['before_state']) == _json({**before, '_mutation_effect_scope': 'application'})
                 and _json(checkpoint['verification']['evidence'].get('after')) == _json(after)
                 and _json(checkpoint['verification']['evidence'].get('execution_guard')) ==
                     _json(result.get('execution_guard'))
                 and type(result.get('execution_guard')) is dict and bool(result['execution_guard'])
                 and after.get('pending') is False and after.get('guard_released') is True,
                 'Result and actual committed checkpoint/readback differ.')
        if row['status'] == 'succeeded':
            _require(_json(row['result']) == _json(result), 'Terminal creation result differs.')
        baseline = validated_rectangle_snapshot(before['baseline']['snapshots'][document_id])
        created = validated_rectangle_snapshot(after['state']['snapshots'][document_id])
        _require(baseline['configuration'] == created['configuration'] == configuration
                 and baseline['clone_state']['profile'] == before_profile
                 and created['clone_state']['profile'] == after_profile,
                 'Complete baseline/created target snapshots required.')
        features = created['clone_state']['features']
        matches = [(index, feature) for index, feature in enumerate(features) if feature['native_id'] == native_id]
        _require(len(matches) == 1
                 and native_id not in {feature['native_id'] for feature in baseline['clone_state']['features']},
                 'GetID must name exactly the newly created feature.')
        index, summary = matches[0]
        _require(summary.get('owner_native_id') is None
                 and summary['feature_type'] in (('ProfileFeature',) if kind == 'sketch' else ('Boss', 'Extrusion')),
                 'Only the standalone created sketch/extrusion is supported.')
        tokens = [reference['token'] for reference in created['references']
                  if reference['kind'] == 'feature' and reference['role'] == 'feature:' + str(index)]
        _require(len(tokens) == 1, 'One exact observed created feature-role PID required.')
        try:
            persistent_id = bytes.fromhex(tokens[0])
        except (TypeError, ValueError) as error:
            raise rejected('owned_rectangle_binding_unconfirmed', 'Feature-role PID must be native hex bytes.') from error
        _require(bool(persistent_id), 'Nonempty native feature PID required.')
        receipt_evidence = self._receipt(receipt, kind)
        _require(_json(after.get('receipt')) == _json(receipt_evidence), 'Original receipt and readback differ.')
        entry, model_identity, configuration_identity = self._context(document_id, configuration)
        feature = getattr(receipt, kind, None)
        retained_identity = _canonical(getattr(receipt, kind + '_identity', None))
        _require(feature is not None and receipt.model_identity == model_identity
                 and receipt.configuration_identity == configuration_identity
                 and self.adapter.identity(feature) == retained_identity
                 and not any(identity == retained_identity for identity, _ in receipt.baseline_features),
                 'Original returned model/configuration/feature canonical binding required.')
        resolved = resolve_retained_feature_pid(self.adapter, entry.model, persistent_id, retained_identity)
        current_native_id = resolved.GetID()
        _require(type(current_native_id) is int and current_native_id == native_id,
                 'Current native GetID differs from independently observed created role.')
        closing, closing_model, closing_cfg = self._context(document_id, configuration)
        _require(closing_model == model_identity and closing_cfg == configuration_identity,
                 'Model/configuration changed during ownership registration.')
        binding = OwnedRectangleFeature(operation_id, self.connection_epoch, document_id, configuration,
            object_id, kind, persistent_id, native_id, entry.model, model_identity, configuration_identity,
            feature, retained_identity, receipt, row['operation'], row['request_id'], _detach(row['payload']),
            result, _detach(checkpoint['before_state']),
            _detach(checkpoint['verification']), baseline, created)
        self._bindings[(document_id, object_id)] = binding
        return binding

    def resolve(self, document_id, configuration, object_id, *, connection_epoch):
        self._check_thread()
        _require(connection_epoch == self.connection_epoch, 'Reconnect cannot adopt owned features.')
        binding = self._bindings.get((document_id, object_id))
        _require(binding is not None and binding.configuration == configuration,
                 'Unknown/foreign rectangle ownership binding.', 'owned_rectangle_not_found')
        row = self._row(binding.creation_operation_id, document_id, configuration, terminal=True)
        _require(row['operation'] == binding._creation_operation
                 and row['request_id'] == binding._creation_request_id
                 and _json(row['payload']) == _json(binding._creation_payload)
                 and _json(row['result']) == _json(binding._creation_result)
                 and _json(row['mutation']['before_state']) == _json(binding._checkpoint_before)
                 and _json(row['mutation']['verification']) == _json(binding._checkpoint_verification),
                 'Original terminal creation result/checkpoint changed.')
        self._receipt(binding.receipt, binding.kind)
        entry, model_identity, cfg_identity = self._context(document_id, configuration)
        _require(model_identity == binding.model_identity and cfg_identity == binding.configuration_identity
                 and binding.receipt.model_identity == binding.model_identity
                 and binding.receipt.configuration_identity == binding.configuration_identity
                 and self.adapter.identity(binding.model) == binding.model_identity
                 and self.adapter.identity(binding.feature) == binding.feature_identity
                 and getattr(binding.receipt, binding.kind + '_identity', None) == binding.feature_identity
                 and self.adapter.identity(getattr(binding.receipt, binding.kind)) == binding.feature_identity,
                 'Retained model/configuration/feature incarnation changed.')
        feature = resolve_retained_feature_pid(self.adapter, entry.model, binding.persistent_id, binding.feature_identity)
        native_id = feature.GetID()
        _require(type(native_id) is int and native_id == binding.native_id, 'Current feature GetID changed.')
        _, closing_model, closing_cfg = self._context(document_id, configuration)
        _require(closing_model == binding.model_identity and closing_cfg == binding.configuration_identity,
                 'Target changed during retained feature resolution.')
        return binding, feature

    def forget_document(self, document_id, model_identity):
        """Server-owned retirement only, matching exact retained canonical model.

        Does not close/delete a model or alter durable jobs/holds. Caller proves
        its own close/retirement postconditions before relinquishing bindings.
        """
        self._check_thread()
        _canonical(model_identity)
        keys = [key for key, binding in self._bindings.items()
                if binding.document_id == document_id and binding.model_identity == model_identity]
        for key in keys:
            del self._bindings[key]
        return len(keys)

    def forget_feature(self, binding):
        """Retire one exact held binding after the caller proves native absence.

        Pure in-memory retirement, without querying the now-deleted feature or
        changing the creation history. Borrowed sketch ownership is preserved.
        """
        self._check_thread()
        key=(binding.document_id,binding.object_id)
        _require(self._bindings.get(key) is binding,'Only the exact held feature binding may be retired.')
        del self._bindings[key]
