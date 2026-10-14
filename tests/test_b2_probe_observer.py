"""Concrete B2 observer through native-shaped fakes only; no COM initialization."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from test_b2_suppression_probe import receipt, proof, helper as gate


path = Path(__file__).resolve().parents[1] / 'scripts/verifier_b2_probe_observer.py'
spec = importlib.util.spec_from_file_location('b2_probe_observer', path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class Canonical:
    __hash__ = None
    def __init__(self, value): self.value = value
    def __eq__(self, other): return isinstance(other, Canonical) and self.value == other.value


class Feature:
    def __init__(self, row, token):
        self.row = deepcopy(row)
        self.canonical = Canonical('feature:' + str(row['native_id']))
        self.pid = token
        self.calls = []
    def GetID(self): self.calls.append('GetID'); return self.row['native_id']
    def IsSuppressed2(self, option, names):
        self.calls.append(('IsSuppressed2', option, names))
        return (self.row['suppressed'],)
    def SetSuppression2(self, *args): raise AssertionError('Observer cannot mutate suppression.')


@pytest.fixture
def observer(receipt):
    source = deepcopy(receipt)
    base = source['observations'][0]
    owner = source['owner']
    model = NS(canonical=Canonical('model'), name='target')
    neighbor = NS(canonical=Canonical('neighbor'), name='neighbor')
    cfg = Canonical('configuration')
    features = [Feature(row, bytes.fromhex(owner['feature_pid_hex']) if row['native_id'] == 5
                        else bytes([row['native_id'] + 1])) for row in base['feature_summaries']]
    target = next(feature for feature in features if feature.row['native_id'] == 5)
    identities = helper.CanonicalOrdinalPool()
    owner['document_identity_token'] = identities.ordinal(model.canonical)
    owner['configuration_identity_token'] = identities.ordinal(cfg)
    owner['feature_identity_token'] = identities.ordinal(target.canonical)
    sw = NS(CommandInProgress=False)
    state = NS(phase='before', capture_count=0, event=0, watches=[], calls=[],
               fault=None, model=model, neighbor=neighbor, configuration=cfg,
               features=features, source=source, owner=owner, sw=sw)
    def native_identity(obj):
        state.calls.append('identity')
        return obj.canonical
    def watch_part(current):
        state.calls.append(('watch_part', current.name))
        watch = NS(closed=False, poll=lambda: state.event)
        def close(): watch.closed = True
        watch.close = close
        state.watches.append(watch)
        return watch
    def feature_list(current):
        state.calls.append('features')
        if state.fault == 'foreign_feature':
            replacement = Feature(target.row, target.pid)
            replacement.canonical = Canonical('replacement')
            return [replacement if feature is target else feature for feature in features]
        return list(features)
    def raw_resolve(token):
        state.calls.append(('raw_resolve', token))
        if state.fault == 'state2': return target, 2
        if state.fault == 'state_boolean': return target, False
        if state.fault == 'raw_null': return None, 0
        if state.fault == 'raw_alias': return features[0], 0
        return target, 0
    def resolve(current, token, kind):
        state.calls.append(('resolve', token, kind))
        if state.fault == 'resolved_alias': return features[0]
        if state.fault == 'resolved_null': return None
        return target
    def cfg_identity(current, name):
        state.calls.append(('configuration_identity', name))
        return Canonical('changed_cfg') if state.fault == 'configuration_identity' else cfg
    def full_snapshot(current):
        state.calls.append(('full_snapshot', current.name))
        row = deepcopy(base['full_snapshot'])
        if current is model:
            row['clone_state']['features'] = [deepcopy(feature.row) for feature in features]
        if state.fault == 'event_change': state.event += 1
        if state.fault == 'neighbor_geometry' and current is neighbor:
            row['clone_state']['geometry']['bodies'][0]['edges'][0]['coedges'] = []
        if state.fault == 'census_change' and current is neighbor:
            features[0].row['name'] += ' изменён'
        return row
    def geometry(current):
        state.calls.append('geometry')
        if state.fault == 'body_remaining': return deepcopy(base['geometry'])
        return {'representation': 'planar_polyhedral_brep_v1', 'bodies': []}
    adapter = NS(_sw=sw, identity=native_identity, features=feature_list,
                 feature_summary=lambda feature: deepcopy(feature.row), watch_part=watch_part,
                 configuration_identity=cfg_identity, persistent_id=lambda current, feature: feature.pid,
                 _extension=lambda current: NS(GetObjectByPersistReference3=raw_resolve),
                 _persistent_variant=lambda token: token, resolve_persistent_id=resolve,
                 rectangle_construction_snapshot=full_snapshot, dimension_geometry_snapshot=geometry)
    entries = [NS(document_id='target', model=model, identity=model.canonical),
               NS(document_id='neighbor', model=neighbor, identity=neighbor.canonical)]
    def document_resolve(identifier, configuration):
        state.calls.append(('document_resolve', identifier, configuration))
        observed = deepcopy(base['session']['semantic']['documents'][0])
        if state.fault == 'active_configuration': observed['active_configuration'] = 'Другая'
        return entries[0], observed
    documents = NS(adapter=adapter, resolve=document_resolve)
    def capture():
        state.capture_count += 1
        state.calls.append('capture_session')
        semantic = deepcopy(base['session']['semantic'])
        semantic['application'].pop('command_in_progress')  # Real native session shape.
        if state.capture_count % 2 == 0:
            if state.fault == 'session_change': semantic['windows'][1]['title'] += ' изменён'
            if state.fault == 'late_command': sw.CommandInProgress = True
        if state.fault == 'foreign_document':
            semantic['documents'][1]['document_id'] = 'foreign'
            return [entries[0], NS(document_id='foreign', model=neighbor, identity=neighbor.canonical)], semantic
        if state.fault == 'model_alias':
            return [NS(document_id='target', model=model, identity=Canonical('replacement')), entries[1]], semantic
        return entries[:], semantic
    sessions = NS(documents=documents, adapter=adapter, _capture_session=capture)
    pref_calls = []
    def prefs(application):
        assert application is sw
        pref_calls.append('prefs')
        if state.fault == 'preferences_changed' and len(pref_calls) % 2 == 0:
            return {'raw_native_preference': False}
        return deepcopy(base['session']['application_preferences'])
    instance = helper.OwnedSuppressionProbeObserver(documents, sessions, owner=owner,
        model=model, feature=target, document_identity=model.canonical,
        feature_identity=target.canonical, configuration_identity=cfg,
        owned_fixtures={'target': (model, model.canonical), 'neighbor': (neighbor, neighbor.canonical)},
        identity_pool=identities, read_preferences=prefs)
    state.instance, state.target, state.adapter = instance, target, adapter
    def set_phase(phase):
        state.phase = phase
        target.row['suppressed'] = phase == 'suppressed'
    state.set_phase = set_phase
    return state


def test_canonical_pool_retains_unhashable_equal_native_wrappers():
    pool = helper.CanonicalOrdinalPool()
    original = Canonical('native')
    assert pool.ordinal(original) == pool.ordinal(Canonical('native')) == 1
    assert pool._identities[0] is original
    assert pool.ordinal(Canonical('other')) == 2
    with pytest.raises(ValueError): pool.ordinal(None)


def test_three_concrete_phase_receipts_feed_existing_strict_gate(observer):
    rows = []
    for phase in gate.PHASES:
        observer.set_phase(phase)
        result = observer.instance.observe_phase(phase)
        rows.append(result['observation'])
        assert result['receipt_produced'] is True
        assert all(result[key] is False for key in ('accepted', 'native_b2_accepted',
                    'can_dispatch_native', 'cad_cleanup_authorized', 'process_stop_authorized'))
    source = deepcopy(observer.source)
    source['owner'] = deepcopy(observer.owner)
    source['observations'] = rows
    for action in source['actions']:
        for key in ('document_identity_token', 'configuration_identity_token', 'feature_identity_token'):
            action[key] = observer.owner[key]
    assert gate.validate_probe(source)['receipt_validated']
    assert observer.capture_count == 6
    assert all(watch.closed for watch in observer.watches)
    assert observer.target.calls.count(('IsSuppressed2', 1, None)) == 3
    assert ('resolve', bytes.fromhex(observer.owner['feature_pid_hex']), 'feature') in observer.calls


def test_suppressed_phase_uses_empty_native_geometry_not_unsupported_rectangle_oracle(observer):
    observer.set_phase('suppressed')
    result = observer.instance.observe_phase('suppressed')
    assert result['observation']['is_suppressed2'] == [True]
    assert 'full_snapshot' not in result['observation']
    assert 'geometry' in observer.calls
    assert ('full_snapshot', 'target') not in observer.calls
    assert ('full_snapshot', 'neighbor') in observer.calls


def test_output_detaches_receipts_and_does_not_change_native_fake_geometry_or_summary(observer):
    before = deepcopy([feature.row for feature in observer.features])
    result = observer.instance.observe_phase('before')
    result['observation']['feature_summaries'][0]['name'] = 'Изменённый отчёт'
    result['observation']['full_snapshot']['clone_state']['geometry']['bodies'] = []
    assert [feature.row for feature in observer.features] == before
    assert observer.source['observations'][0]['full_snapshot']['solid_body_count'] == 1


def test_owner_model_replacement_rejected_before_any_phase_session_read(observer):
    observer.model.canonical = Canonical('new_native_model')
    with pytest.raises(ValueError): observer.instance.observe_phase('before')
    assert observer.capture_count == 0


@pytest.mark.parametrize('fault', ['state2', 'state_boolean', 'raw_null', 'raw_alias',
    'resolved_alias', 'resolved_null', 'configuration_identity', 'active_configuration',
    'foreign_feature', 'foreign_document', 'model_alias', 'event_change', 'census_change',
    'session_change', 'preferences_changed', 'neighbor_geometry', 'late_command'])
def test_alias_partial_receipts_and_coherence_drift_fail_without_fallback(observer, fault):
    observer.fault = fault
    with pytest.raises(ValueError):
        observer.instance.observe_phase('before')
    assert all(watch.closed for watch in observer.watches)
    if fault in ('state2', 'state_boolean', 'raw_null', 'raw_alias'):
        assert not any(isinstance(call, tuple) and call[0] == 'resolve' for call in observer.calls)


@pytest.mark.parametrize('value', [True, 0, 1, None])
def test_raw_command_flag_rejects_busy_and_coerced_values_before_any_capture(observer, value):
    observer.sw.CommandInProgress = value
    with pytest.raises(ValueError): observer.instance.observe_phase('before')
    assert observer.capture_count == 0 and observer.watches == []


@pytest.mark.parametrize('phase', ['suppressed', 'unknown'])
def test_wrong_phase_state_is_not_fabricated(observer, phase):
    with pytest.raises(ValueError): observer.instance.observe_phase(phase)
    assert all(watch.closed for watch in observer.watches)


def test_remaining_body_rejects_suppression_even_with_true_native_suppression_bit(observer):
    observer.set_phase('suppressed')
    observer.fault = 'body_remaining'
    with pytest.raises(ValueError): observer.instance.observe_phase('suppressed')
    assert all(watch.closed for watch in observer.watches)


def test_input_ownership_is_not_adopted_from_equal_names_or_getid(observer):
    observer.instance.feature_identity = Canonical('foreign_feature_same_name_GetID')
    with pytest.raises(ValueError): observer.instance.observe_phase('before')
    assert all(watch.closed for watch in observer.watches)


@pytest.mark.parametrize('fault', [None, 'null', 'state0', 'state4', 'state6', 'bool_state',
    'raw_alias', 'member_alias', 'duplicate', 'wrong_pid', 'unsuppressed', 'numeric_bool'])
def test_retained_suppressed_pid_prototype_requires_raw_canonical_member(fault):
    from solidworks_mcp.jobs import ExecutionFailure
    model = object()
    feature = NS(canonical=Canonical('owned'), pid=b'\xaa',
                 IsSuppressed2=lambda option, names: [True])
    other = NS(canonical=Canonical('foreign'), pid=b'\xaa')
    raw, state, members = feature, 2, [feature]
    if fault == 'null': raw = None
    elif fault == 'state0': state = 0
    elif fault == 'state4': state = 4
    elif fault == 'state6': state = 6
    elif fault == 'bool_state': state = True
    elif fault == 'raw_alias': raw = other
    elif fault == 'member_alias': members = [other]
    elif fault == 'duplicate': members = [feature, feature]
    elif fault == 'wrong_pid': feature.pid = b'\xbb'
    elif fault == 'unsuppressed': feature.IsSuppressed2 = lambda *args: [False]
    elif fault == 'numeric_bool': feature.IsSuppressed2 = lambda *args: [1]
    def generic(*args):
        raise ExecutionFailure('object_suppressed', 'Actual generic resolver refuses state2.')
    adapter = NS(resolve_persistent_id=generic, identity=lambda item: item.canonical,
        features=lambda current: members, persistent_id=lambda current, item: item.pid,
        _persistent_variant=lambda pid: pid,
        _extension=lambda current: NS(GetObjectByPersistReference3=lambda pid: (raw, state)))
    if fault is None:
        assert helper.resolve_retained_feature_pid(adapter, model, b'\xaa', feature.canonical) is feature
    else:
        with pytest.raises(ValueError):
            helper.resolve_retained_feature_pid(adapter, model, b'\xaa', feature.canonical)


@pytest.mark.parametrize('code', ['object_deleted', 'object_reference_invalid', 'persistent_reference_mismatch'])
def test_other_generic_resolution_errors_never_enter_suppressed_prototype(code):
    from solidworks_mcp.jobs import ExecutionFailure
    def fail(*args): raise ExecutionFailure(code, code)
    adapter = NS(resolve_persistent_id=fail,
        _extension=lambda *args: pytest.fail('No secondary native lookup for another error.'))
    with pytest.raises(ExecutionFailure) as error:
        helper.resolve_retained_feature_pid(adapter, object(), b'\xaa', Canonical('held'))
    assert error.value.code == code
