"""Actual JobStore terminal gate; artificial identities/geometry, no native CAD."""
from copy import deepcopy
from threading import Thread
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_rectangle_construction import NativeRectangleStageReceipt
from solidworks_mcp.jobs import ExecutionFailure, JobStore, _json
from solidworks_mcp.owned_rectangle_feature import OwnedRectangleFeatureRegistry, PROFILES, RECEIPT_FIELDS
from test_rectangle_postconditions import proof as sketch_proof, empty_adapter
from test_rectangle_extrusion_postconditions import proof as extrusion_proof


class Canonical:
    """Unhashable retained native identity analogue, never a JSON ID."""
    __hash__ = None


@pytest.fixture(params=['sketch', 'extrusion'])
def case(request, sketch_proof, extrusion_proof, tmp_path):
    kind = request.param
    baseline, created, definition = deepcopy(sketch_proof if kind == 'sketch' else extrusion_proof)
    operation = 'sketch.create_rectangle' if kind == 'sketch' else 'part.extrude_rectangle'
    scope = PROFILES[operation][1]
    native_id = 4 if kind == 'sketch' else 5
    current_model, cfg, feature_token = Canonical(), Canonical(), Canonical()
    model = NS(identity=current_model)
    feature = NS(identity=feature_token, native_id=native_id, suppressed=False)
    feature.GetID = lambda: feature.native_id
    feature.IsSuppressed2 = lambda *args: [feature.suppressed]
    rows = created['snapshots']['target']['clone_state']['features']
    position = next(index for index, row in enumerate(rows) if row['native_id'] == native_id)
    pid = bytes.fromhex(next(row['token'] for row in created['snapshots']['target']['references']
        if row['kind'] == 'feature' and row['role'] == 'feature:' + str(position)))
    feature.pid = pid
    controls = created['snapshots']['target']['clone_state']['creation_controls']
    receipt = NativeRectangleStageReceipt(current_model, cfg, (), deepcopy(controls))
    receipt.attempted = receipt.native_call_returned = True
    receipt.sketch_closed = kind == 'sketch'
    setattr(receipt, kind, feature)
    setattr(receipt, kind + '_identity', feature_token)
    evidence = {key: getattr(receipt, key) for key in RECEIPT_FIELDS}
    before = dict(scope=scope, baseline=baseline, definition=vars(definition),
        reference_persistent_id_hex='ab', reference_native_id=0 if kind == 'sketch' else 4,
        plane_transform=[1.0] * 16)
    after = dict(state=created, receipt=evidence, original_files=baseline['semantic']['files'],
                 pending=False, guard_released=True)
    guard = dict(scope='rectangle_construction_guard_v1', native_guards=[{'pure_released': True}],
        guard_released=True, pending_release=False, journal_failed=False,
        reference_binding_unconfirmed=False, full_release_check='effect')
    object_id = 'feat_' + ('c' if kind == 'sketch' else 'd') * 32
    value = dict(document_id='target', configuration='Основная', kind=kind,
        created_native_id=native_id, object_id=object_id,
        **{'sketch_object_id' if kind == 'sketch' else 'feature_object_id': object_id})
    result = dict(value=value, before=before, after=after, verified=True, execution_guard=guard)
    observed = dict(document_type='part', path='', configurations=['Основная'], active_configuration='Основная')
    entry = NS(document_id='target', model=model, identity=current_model)
    state = NS(kind=kind, operation=operation, baseline=baseline, created=created, definition=definition,
        model=model, cfg=cfg, feature=feature, receipt=receipt, result=result, entry=entry,
        observed=observed, object_id=object_id, pid=pid, resolve_calls=0, context_calls=0,
        resolved_feature=feature, members=[feature], raw=feature, status=2)
    def context(document_id, configuration):
        state.context_calls += 1
        return state.entry, deepcopy(state.observed)
    def resolve(*args):
        state.resolve_calls += 1
        if feature.suppressed:
            raise ExecutionFailure('object_suppressed', 'Artificial normal resolver refusal.')
        return state.resolved_feature
    adapter = NS(identity=lambda value: value.identity, configuration_identity=lambda *args: state.cfg,
        resolve_persistent_id=resolve, persistent_id=lambda model, value: value.pid,
        features=lambda model: list(state.members), _persistent_variant=lambda value: value,
        _extension=lambda model: NS(GetObjectByPersistReference3=lambda value: (state.raw, state.status)))
    state.adapter = adapter
    store = JobStore(tmp_path / 'owned.sqlite')
    state.store = store
    documents = NS(adapter=adapter, resolve=context)
    state.registry = OwnedRectangleFeatureRegistry(documents, store, 'own_epoch')
    args = dict(document_id='target', configuration='Основная', expected_revision='before', **vars(definition))
    job, _ = store.create('create', operation, args,
        {key: args[key] for key in ('document_id', 'configuration', 'expected_revision')}, mutates=True)
    state.oid = job['operation_id']
    store.start(state.oid)
    store.prepare_mutation(state.oid, connection_epoch='own_epoch', document_id='target',
        configuration='Основная', expected_revision='before', before_state=before, effect_scope='application')
    store.verify_mutation(state.oid, outcome='committed', evidence={'after': after, 'execution_guard': guard})
    yield state
    store.close()


def register(case):
    return case.registry.register(case.oid, document_id='target', configuration='Основная',
                                  result=case.result, receipt=case.receipt)


def publish(case):
    case.store.finish(case.oid, 'succeeded', result=case.result)


def resolve(case, **overrides):
    args = dict(document_id='target', configuration='Основная', object_id=case.object_id,
                connection_epoch='own_epoch')
    return case.registry.resolve(**{**args, **overrides})


def test_registration_is_not_admission_until_actual_terminal_commit(case):
    binding = register(case)
    native_reads = case.resolve_calls, case.context_calls
    with pytest.raises(ExecutionFailure): resolve(case)
    assert (case.resolve_calls, case.context_calls) == native_reads
    publish(case)
    owned, feature = resolve(case)
    assert owned is binding and feature is case.feature
    assert binding.receipt is case.receipt and binding.model is case.model
    assert binding.feature_identity is case.feature.identity
    assert binding.persistent_id == case.pid and binding.native_id == case.feature.native_id
    assert binding.creation_operation_id == case.oid


def test_full_snapshots_and_result_are_detached_but_native_canonical_is_retained(case):
    binding = register(case)
    detached_before, detached_after = binding.baseline_target_snapshot, binding.created_target_snapshot
    detached_before['clone_state']['profile'] = 'forged'
    detached_after['references'].clear()
    exposed_result = binding.creation_result
    exposed_result['after'].clear()
    assert _json(binding.baseline_target_snapshot) == _json(case.baseline['snapshots']['target'])
    assert _json(binding.created_target_snapshot) == _json(case.created['snapshots']['target'])
    assert _json(binding.creation_result) == _json(case.result)
    assert binding.configuration_identity is case.cfg
    case.result['after']['state']['snapshots']['target']['references'].clear()
    assert binding.created_target_snapshot['references']


@pytest.mark.parametrize('status', ['unknown', 'failed', 'cancelled', 'queued'])
def test_non_succeeded_durable_row_forbids_before_native_resolution(case, status):
    register(case)
    if status in ('unknown', 'failed'):
        if status == 'failed':
            case.store.verify_mutation(case.oid, outcome='rolled_back',
                evidence={'after': case.baseline, 'original_error': 'pure known restoration'})
        case.store.finish(case.oid, status, error={'code': 'pure_failure'})
        assert case.store.get(case.oid)['status'] == status
    else:
        with case.store._lock:
            case.store._db.execute('UPDATE jobs SET status=? WHERE operation_id=?', (status, case.oid))
    before = case.resolve_calls, case.context_calls
    with pytest.raises(ExecutionFailure): resolve(case)
    assert (case.resolve_calls, case.context_calls) == before


@pytest.mark.parametrize('roster', ['same', 'closed', 'replacement', 'foreign'])
def test_retirement_uses_complete_roster_and_exact_model_incarnation(case, roster):
    binding = register(case)
    case.registry.documents._refresh = lambda: None
    entries = {'same': [case.entry], 'closed': [],
        'replacement': [NS(document_id='target',identity=Canonical())],
        'foreign': [NS(document_id='foreign',identity=binding.model_identity)]}
    case.registry.documents._entries = entries[roster]
    assert case.registry.retire_absent_documents() == (0 if roster == 'same' else 1)
    assert bool(case.registry._bindings) is (roster == 'same')
    # Retirement never changes the job, closes a model or reconciles a hold.
    assert case.store.get(case.oid)['status'] == 'running'


def test_failed_complete_roster_refresh_preserves_retained_ownership(case):
    binding = register(case)
    def fail(): raise RuntimeError('Native enumeration returned an error; no partial roster.')
    case.registry.documents._refresh = fail
    with pytest.raises(RuntimeError): case.registry.retire_absent_documents()
    assert case.registry._bindings[('target',binding.object_id)] is binding


@pytest.mark.parametrize('field,value', [('phase', 'unresolved'), ('phase', 'prepared'),
    ('connection_epoch', 'reconnected'), ('document_id', 'foreign'), ('configuration', 'Другая')])
def test_exact_checkpoint_gate_is_rechecked_without_native_reads(case, field, value):
    register(case); publish(case)
    with case.store._lock:
        case.store._db.execute('UPDATE mutations SET ' + field + '=? WHERE operation_id=?', (value, case.oid))
    before = case.resolve_calls, case.context_calls
    with pytest.raises(ExecutionFailure): resolve(case)
    assert (case.resolve_calls, case.context_calls) == before


@pytest.mark.parametrize('fault', ['result', 'outcome', 'evidence', 'operation', 'request', 'payload'])
def test_terminal_payload_result_and_committed_evidence_cannot_be_replaced(case, fault):
    register(case); publish(case)
    with case.store._lock:
        if fault == 'result':
            result = deepcopy(case.result); result['value']['object_id'] = 'feat_' + 'f' * 32
            case.store._db.execute('UPDATE jobs SET result=? WHERE operation_id=?', (_json(result), case.oid))
        elif fault in ('outcome', 'evidence'):
            verification = case.store.get(case.oid)['mutation']['verification']
            if fault == 'outcome': verification['outcome'] = 'rolled_back'
            else: verification['evidence']['after']['pending'] = True
            case.store._db.execute('UPDATE mutations SET verification=? WHERE operation_id=?', (_json(verification), case.oid))
        elif fault == 'operation':
            case.store._db.execute('UPDATE jobs SET operation=? WHERE operation_id=?', ('feature.rename', case.oid))
        elif fault == 'request':
            case.store._db.execute('UPDATE jobs SET request_id=? WHERE operation_id=?', ('another', case.oid))
        else:
            payload = case.store.get(case.oid)['payload']; payload['arguments']['sketch_name'] = 'Чужой'
            case.store._db.execute('UPDATE jobs SET payload=? WHERE operation_id=?', (_json(payload), case.oid))
    before = case.resolve_calls, case.context_calls
    with pytest.raises(ExecutionFailure): resolve(case)
    assert (case.resolve_calls, case.context_calls) == before


@pytest.mark.parametrize('override', [dict(connection_epoch='reconnected'), dict(document_id='foreign'),
                                    dict(configuration='Другая'), dict(object_id='feat_' + 'a' * 32)])
def test_foreign_reconnect_or_unowned_scope_never_resolves_native_pid(case, override):
    register(case); publish(case)
    reads = case.resolve_calls, case.context_calls
    with pytest.raises(ExecutionFailure): resolve(case, **override)
    assert (case.resolve_calls, case.context_calls) == reads


@pytest.mark.parametrize('fault', ['model', 'entry', 'configuration', 'feature', 'receipt_model',
    'receipt_cfg', 'receipt_feature', 'pid', 'getid', 'bool_getid', 'foreign_resolved'])
def test_names_getid_pid_and_json_do_not_replace_retained_canonical(case, fault):
    register(case); publish(case)
    if fault == 'model':
        case.entry.model = NS(identity=Canonical()); case.entry.identity = case.entry.model.identity
    elif fault == 'entry': case.entry.identity = Canonical()
    elif fault == 'configuration': case.cfg = Canonical()
    elif fault == 'feature': case.feature.identity = Canonical()
    elif fault == 'receipt_model': case.receipt.model_identity = Canonical()
    elif fault == 'receipt_cfg': case.receipt.configuration_identity = Canonical()
    elif fault == 'receipt_feature': setattr(case.receipt, case.kind + '_identity', Canonical())
    elif fault == 'pid': case.feature.pid = b'foreign'
    elif fault == 'getid': case.feature.native_id += 1
    elif fault == 'bool_getid': case.feature.native_id = True
    else:
        case.resolved_feature = NS(identity=Canonical(), pid=case.pid, GetID=lambda: case.feature.native_id)
    with pytest.raises(ExecutionFailure): resolve(case)


@pytest.mark.parametrize('field,value', [('path', 'C:\\saved.sldprt'), ('document_type', 'assembly'),
    ('configurations', ['Основная', 'Другая']), ('active_configuration', 'Другая')])
def test_current_scope_must_remain_unsaved_oneconfiguration_part(case, field, value):
    register(case); publish(case)
    case.observed[field] = value
    with pytest.raises(ExecutionFailure): resolve(case)


def test_suppressed_retained_pid_uses_bridge_without_granting_mutation(case):
    register(case); publish(case)
    case.feature.suppressed = True
    binding, feature = resolve(case)
    assert feature is case.feature and binding.feature_identity is feature.identity
    assert not hasattr(case.registry, 'delete') and not hasattr(case.registry, 'suppress')


@pytest.mark.parametrize('fault', ['null', 'foreign', 'duplicate'])
def test_suppressed_replacement_cannot_use_name_or_nativeid_fallback(case, fault):
    register(case); publish(case)
    case.feature.suppressed = True
    if fault == 'null': case.raw = None
    elif fault == 'foreign': case.raw = NS(identity=Canonical())
    else: case.members *= 2
    with pytest.raises(ExecutionFailure): resolve(case)


@pytest.mark.parametrize('fault', ['alias', 'value_scope', 'pid_role', 'created_id', 'receipt',
                                   'baseline_partial', 'created_partial', 'before', 'after', 'json_identity'])
def test_registration_requires_exact_server_receipt_full_snapshot_and_observed_feature_role(case, fault):
    if fault == 'alias': case.result['value']['sketch_object_id' if case.kind == 'sketch' else 'feature_object_id'] = 'foreign'
    elif fault == 'value_scope': case.result['value']['document_id'] = 'foreign'
    elif fault == 'pid_role':
        for reference in case.result['after']['state']['snapshots']['target']['references']:
            if reference['kind'] == 'feature' and reference['token'] == case.pid.hex(): reference['token'] = 'deadbeef'
    elif fault == 'created_id': case.result['value']['created_native_id'] = 0
    elif fault == 'receipt': case.receipt.pending_creation = True
    elif fault == 'baseline_partial': case.result['before']['baseline']['snapshots']['target'].pop('native_observations')
    elif fault == 'created_partial': case.result['after']['state']['snapshots']['target'].pop('native_observations')
    elif fault == 'before': case.result['before']['scope'] = 'foreign'
    elif fault == 'after': case.result['after']['guard_released'] = False
    else: case.feature.identity = 'json_identity'; setattr(case.receipt, case.kind + '_identity', 'json_identity')
    with pytest.raises((ExecutionFailure, KeyError)): register(case)
    assert not case.registry._bindings


def test_bounded_prewrite_capacity_and_duplicate_registration_do_not_adopt_receipts(case):
    case.registry.max_per_document = 1
    register(case)
    before = case.resolve_calls, case.context_calls
    with pytest.raises(ExecutionFailure) as error: case.registry.check_capacity('target')
    assert error.value.code == 'owned_rectangle_budget'
    with pytest.raises(ExecutionFailure): register(case)
    assert (case.resolve_calls, case.context_calls) == before
    case.registry.max_per_document = 2
    with pytest.raises(ExecutionFailure): register(case)


def test_document_budget_and_exact_canonical_retirement(case):
    case.registry.max_documents = 1
    binding = register(case)
    with pytest.raises(ExecutionFailure): case.registry.check_capacity('new_document')
    assert case.registry.forget_document('target', Canonical()) == 0
    assert case.registry.forget_document('foreign', binding.model_identity) == 0
    assert case.registry.forget_document('target', binding.model_identity) == 1
    case.registry.check_capacity('new_document')
    with pytest.raises(ExecutionFailure): resolve(case)


def test_owned_registry_cannot_be_rebuilt_from_json_after_reconnect(case):
    register(case); publish(case)
    replacement = OwnedRectangleFeatureRegistry(case.registry.documents, case.store, 'new_epoch')
    with pytest.raises(ExecutionFailure): replacement.resolve('target', 'Основная', case.object_id, connection_epoch='new_epoch')
    assert not replacement._bindings


def test_configuration_replacement_during_pid_read_cannot_admit_prior_capture(case):
    register(case); publish(case)
    def changing_resolution(*args):
        case.cfg = Canonical()
        return case.feature
    case.adapter.resolve_persistent_id = changing_resolution
    with pytest.raises(ExecutionFailure, match='changed during retained'):
        resolve(case)


@pytest.mark.parametrize('per_document,documents', [(True, 32), (0, 32), (3, 32), (2, True), (2, 0), (2, 33)])
def test_registry_budgets_cannot_exceed_finite_owned_profile(case, per_document, documents):
    with pytest.raises(ExecutionFailure):
        OwnedRectangleFeatureRegistry(case.registry.documents, case.store, 'own_epoch',
            max_per_document=per_document, max_documents=documents)


def test_cross_thread_refusal_occurs_before_store_or_native_resolution(case):
    register(case); publish(case)
    errors = []
    def wrong_thread():
        try: resolve(case)
        except ExecutionFailure as error: errors.append(error)
    before = case.resolve_calls, case.context_calls
    thread = Thread(target=wrong_thread); thread.start(); thread.join(5)
    assert len(errors) == 1 and errors[0].code == 'wrong_apartment'
    assert (case.resolve_calls, case.context_calls) == before
