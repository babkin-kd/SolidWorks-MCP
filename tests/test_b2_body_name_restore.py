"""Artificial own-body delta/one-shot proofs; no installed or CAD acceptance."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from test_b2_suppression_probe import receipt, proof

scripts = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('b2_body_name_restore', scripts / 'verifier_b2_body_name_restore.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def case(receipt, monkeypatch):
    monkeypatch.syspath_prepend(str(scripts))
    before, _, restored = deepcopy(receipt['observations'])
    name = before['full_snapshot']['clone_state']['body']['name']
    restored['full_snapshot']['clone_state']['body']['name'] = 'Основание'
    assert name != 'Основание'
    state = NS(writes=0, fault=None, report={}, records=[], before=before, restored=restored,
               sw=NS(CommandInProgress=False))
    class Body:
        identity = object()
        _name = 'Основание'
        @property
        def Name(self):
            return 'Неверное имя' if state.fault == 'readback' and state.writes else self._name
        @Name.setter
        def Name(self, value):
            state.writes += 1
            if state.fault == 'setter': raise RuntimeError('Normally throwing native setter, not retried.')
            self._name = value
    body = Body()
    model, cfg, feature_identity = object(), object(), object()
    feature = NS(identity=feature_identity, IsSuppressed2=lambda *args: [False])
    row = next(r for r in restored['session']['semantic']['documents'] if r['document_id'] == 'target')
    metadata = {k: row[k] for k in ('title','path','document_type','needs_save',
                                  'configurations','active_configuration','update_stamp')}
    token = next(r['token'] for r in before['full_snapshot']['references'] if r['kind'] == 'body')
    class Guard:
        def __enter__(self): state.sw.CommandInProgress=True; return self
        def __exit__(self, *args): state.sw.CommandInProgress=False
    adapter = NS(_sw=state.sw, identity=lambda item: getattr(item, 'identity', item),
        snapshot=lambda current: deepcopy(metadata), configuration_identity=lambda *args: cfg,
        active_document=lambda: model, bodies=lambda *args: [body],
        persistent_id=lambda *args: bytes.fromhex(token),
        resolve_persistent_id=lambda *args: body, mutation_guard=lambda current: Guard())
    observer = NS(owner=deepcopy(receipt['owner']), adapter=adapter, model=model,
        document_identity=model, configuration_identity=cfg, feature_identity=feature_identity,
        resolve_feature=lambda: feature,
        documents=NS(resolve=lambda *args: (NS(identity=model), deepcopy(metadata))))
    def persist(): state.records.append(deepcopy(state.report))
    def release_check(guard, sw):
        assert sw.CommandInProgress is False
        return {'released': True}
    state.observer, state.adapter, state.body, state.name = observer, adapter, body, name
    state.run = lambda: helper.restore_owned_body_name(observer,before,restored,state.report,persist,release_check)
    return state


def test_only_owned_body_name_delta_is_corrected_once_then_requires_independent_capture(case):
    assert case.run() is True and case.writes == 1 and case.body.Name == case.name
    row = case.report['body_name_restoration']
    assert row['native_call_returned'] and row['readback_verified'] and row['pending'] is False
    assert row['execution_guard']['released'] is True and case.report['native_calls_live'] is False
    assert any(r['body_name_restoration']['pending'] is True for r in case.records)
    assert case.restored['full_snapshot']['clone_state']['body']['name'] == 'Основание'


def test_already_exact_restoration_performs_no_native_write(case):
    case.restored['full_snapshot'] = deepcopy(case.before['full_snapshot'])
    assert case.run() is False and case.writes == 0 and case.records == []


@pytest.mark.parametrize('fault', ['material', 'geometry', 'feature', 'neighbor', 'raw_pid',
                                  'canonical', 'body_pid_missing'])
def test_other_observed_delta_refuses_before_guard_or_write(case, fault):
    if fault == 'material': case.restored['full_snapshot']['clone_state']['properties']['foreign'] = 'changed'
    elif fault == 'geometry': case.restored['full_snapshot']['clone_state']['body']['visible'] = False
    elif fault == 'feature': case.restored['full_snapshot']['clone_state']['features'][0]['name'] += ' чужое'
    elif fault == 'neighbor': case.restored['session']['neighbor_snapshots']['neighbor']['clone_state']['body']['name'] += ' чужое'
    elif fault == 'raw_pid': case.restored['resolver']['input_pid_hex'] = 'ff'
    elif fault == 'canonical': case.restored['feature_identity_tokens'][0] += 1
    else: case.before['full_snapshot']['references'] = [r for r in case.before['full_snapshot']['references'] if r['kind'] != 'body']
    with pytest.raises(ValueError): case.run()
    assert case.writes == 0 and case.records == []


@pytest.mark.parametrize('fault', ['metadata', 'model', 'config', 'active', 'body_member', 'body_pid', 'name'])
def test_late_binding_changes_refuse_the_name_write(case, fault):
    if fault == 'metadata': case.adapter.snapshot = lambda *args: {'update_stamp': -1}
    elif fault == 'model': case.observer.document_identity = object()
    elif fault == 'config': case.observer.configuration_identity = object()
    elif fault == 'active': case.adapter.active_document = lambda: object()
    elif fault == 'body_member': case.adapter.bodies = lambda *args: []
    elif fault == 'body_pid': case.adapter.persistent_id = lambda *args: b'\xff'
    else: case.body._name = 'Изменено пользователем'
    with pytest.raises(ValueError): case.run()
    assert case.writes == 0 and case.sw.CommandInProgress is False


@pytest.mark.parametrize('fault,pending', [('setter', True), ('readback', False)])
def test_name_write_failure_never_retries_or_grants_completion(case, fault, pending):
    case.fault = fault
    with pytest.raises((RuntimeError, ValueError)): case.run()
    assert case.writes == 1 and case.sw.CommandInProgress is False
    assert case.report['body_name_restoration']['pending'] is pending
    assert case.report['native_calls_live'] is True
