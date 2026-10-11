"""Native-open verifier preflight only: extracted AST, no CAD imports or calls."""

import argparse
import ast
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
SOURCE = SCRIPTS / 'verify_native_document_open.py'
WHEEL = dict(package_version='2.0.0.dev86', git_sha='a' * 40,
             source_digest='b' * 64, wheel_sha256='c' * 64)


class NativeBoundaryReached(Exception):
    """An accepted preflight reaches this barrier, never actual CoInitialize."""


def extract_function(name, namespace, *, parent=None):
    tree = ast.parse(SOURCE.read_text(encoding='utf8'))
    if parent:
        tree = next(node for node in tree.body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == parent)
    node = next(node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace[name]


@pytest.fixture
def preflight(monkeypatch, tmp_path):
    events = []
    script = tmp_path / 'scripts' / SOURCE.name
    script.parent.mkdir()
    constants = {}
    tree = ast.parse(SOURCE.read_text(encoding='utf8'))
    names = {'SHARED_LABELS', 'INTERNAL_LABELS', 'PUBLIC_LABELS', 'HASH_FILES'}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in names for target in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), constants)
    for name in constants['HASH_FILES']:
        script.with_name(name).write_bytes((SCRIPTS / name).read_bytes())

    # This helper is passive JSON validation; exclude even its pure imports.
    helper = ast.parse((SCRIPTS / 'verifier_native_open_acceptance.py').read_text(encoding='utf8'))
    helper.body = [node for node in helper.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    validator = dict(json=json, re=re)
    exec(compile(helper, str(SCRIPTS / 'verifier_native_open_acceptance.py'), 'exec'), validator)

    def validate(path, **expected):
        events.append(('wheel', path, expected))
        return dict(WHEEL)

    def installed(wheel):
        events.append(('installed', copy.deepcopy(wheel)))
        return tmp_path / 'site-packages' / 'solidworks-mcp-v2.exe'

    def prior_gate(*args):
        events.append(('internal_report',))
        return validator['validate_internal_report'](*args)

    def native_barrier():
        events.append(('native_boundary',))
        raise NativeBoundaryReached

    def forbidden_connect(*args, **kwargs):
        pytest.fail('Preflight tests must never connect to CAD.')

    namespace = dict(argparse=argparse, Path=Path, os=os, json=json, hashlib=hashlib, time=time,
                     __file__=str(script), validate_wheel=validate, installed_identity=installed,
                     validate_internal_report=prior_gate,
                     pythoncom=SimpleNamespace(CoInitialize=native_barrier),
                     binding=SimpleNamespace(connect=forbidden_connect),
                     **{key: constants[key] for key in names})
    monkeypatch.delenv('PYTHONPATH', raising=False)
    return SimpleNamespace(main=extract_function('main', namespace), namespace=namespace,
                           events=events, root=tmp_path, script=script, private=tmp_path / 'work')


def arguments(preflight, monkeypatch, *, opt_in=True, public=False, prior=None, state=None):
    state = state if state is not None else preflight.private / 'native-once'
    argv = [SOURCE.name, '--wheel', str(preflight.root / 'candidate.whl'),
            '--expected-version', WHEEL['package_version'], '--expected-git-sha', WHEEL['git_sha'],
            '--state-dir', str(state)]
    if opt_in:
        argv.append('--run-solidworks')
    if public:
        argv.append('--public')
    if prior is not None:
        argv.extend(['--internal-report', str(prior)])
    monkeypatch.setattr(sys, 'argv', argv)
    return state


def report(preflight):
    return dict(accepted=True, scope='internal_native_open_resolved_v1', wheel=dict(WHEEL),
                fixtures_closed=True, baseline_restored=True, cleanup_confirmed=True,
                verifier_hashes={name: hashlib.sha256(preflight.script.with_name(name).read_bytes()).hexdigest()
                                 for name in preflight.namespace['HASH_FILES']},
                cases=[dict(label=label, passed=True) for label in preflight.namespace['INTERNAL_LABELS']])


def prior_file(preflight, value):
    path = preflight.root / 'prior.json'
    path.write_text(json.dumps(value), encoding='utf8')
    return path


def test_explicit_opt_in_precedes_wheel_state_and_native(preflight, monkeypatch):
    state = arguments(preflight, monkeypatch, opt_in=False)
    with pytest.raises(SystemExit) as error:
        preflight.main()
    assert error.value.code == 2
    assert preflight.events == [] and not state.exists()


@pytest.mark.parametrize('pythonpath', ['src'])
def test_pythonpath_rejected_before_wheel_or_native(preflight, monkeypatch, pythonpath):
    state = arguments(preflight, monkeypatch)
    monkeypatch.setenv('PYTHONPATH', pythonpath)
    with pytest.raises(AssertionError):
        preflight.main()
    assert preflight.events == [] and not state.exists()


@pytest.mark.parametrize('gate', ['validate_wheel', 'installed_identity'])
def test_candidate_or_installed_identity_rejection_precedes_cad(preflight, monkeypatch, gate):
    state = arguments(preflight, monkeypatch)

    def refuse(*args, **kwargs):
        raise ValueError('Rejected candidate identity')

    preflight.namespace[gate] = refuse
    with pytest.raises(ValueError, match='Rejected candidate identity'):
        preflight.main()
    assert not state.exists()
    assert [event[0] for event in preflight.events] == ([] if gate == 'validate_wheel' else ['wheel'])


@pytest.mark.parametrize('public', [False, True])
def test_valid_modes_bind_exact_candidate_then_create_private_state(preflight, monkeypatch, public):
    prior = prior_file(preflight, report(preflight)) if public else None
    state = arguments(preflight, monkeypatch, public=public, prior=prior)
    with pytest.raises(NativeBoundaryReached):
        preflight.main()
    assert preflight.events[:2] == [
        ('wheel', preflight.root / 'candidate.whl',
         dict(expected_version=WHEEL['package_version'], expected_git_sha=WHEEL['git_sha'])),
        ('installed', WHEEL)]
    assert [event[0] for event in preflight.events[2:]] == (
        ['internal_report', 'native_boundary'] if public else ['native_boundary'])
    assert state.is_dir() and list(state.iterdir()) == []


def test_public_requires_prior_before_state_or_cad(preflight, monkeypatch):
    state = arguments(preflight, monkeypatch, public=True)
    with pytest.raises(AssertionError):
        preflight.main()
    assert not state.exists()
    assert [event[0] for event in preflight.events] == ['wheel', 'installed']


@pytest.mark.parametrize('field', ['wheel_sha256'])
def test_public_other_wheel_identity_rejected_by_real_gate_before_cad(preflight, monkeypatch, field):
    value = report(preflight)
    value['wheel'][field] = ('f' * (40 if field == 'git_sha' else 64)
                            if field != 'package_version' else '2.0.0.dev_old')
    prior = prior_file(preflight, value)
    state = arguments(preflight, monkeypatch, public=True, prior=prior)
    with pytest.raises(ValueError, match='different wheel/source identity'):
        preflight.main()
    assert not state.exists()
    assert [event[0] for event in preflight.events] == ['wheel', 'installed', 'internal_report']


@pytest.mark.parametrize('file', ['verifier_lifecycle.py'])
def test_public_stale_verifier_or_fixture_hash_rejected_before_cad(preflight, monkeypatch, file):
    prior = prior_file(preflight, report(preflight))
    # Simulate a real helper edit after the internal report, not a fixed digest assertion.
    path = preflight.script.with_name(file)
    path.write_bytes(path.read_bytes() + b'\n# changed since internal acceptance\n')
    state = arguments(preflight, monkeypatch, public=True, prior=prior)
    with pytest.raises(ValueError, match='different verifier hashes'):
        preflight.main()
    assert not state.exists() and prior.read_text(encoding='utf8')
    assert [event[0] for event in preflight.events] == ['wheel', 'installed', 'internal_report']


@pytest.mark.parametrize('change', ['incomplete', 'unknown'])
def test_public_incomplete_or_held_report_cannot_authorize_cad(preflight, monkeypatch, change):
    value = report(preflight)
    if change == 'incomplete': value['cases'].pop()
    if change == 'unknown': value['lifecycle_hold'] = True
    prior = prior_file(preflight, value)
    before = prior.read_bytes()
    state = arguments(preflight, monkeypatch, public=True, prior=prior)
    with pytest.raises(ValueError):
        preflight.main()
    assert not state.exists() and prior.read_bytes() == before
    assert [event[0] for event in preflight.events] == ['wheel', 'installed', 'internal_report']


@pytest.mark.parametrize('kind', ['root', 'existing', 'escaped'])
def test_state_must_be_fresh_child_of_private_work(preflight, monkeypatch, kind):
    state = dict(root=preflight.private, existing=preflight.private / 'used',
                 escaped=preflight.private / '..' / 'escaped')[kind]
    if kind == 'existing':
        state.mkdir(parents=True)
        (state / 'keep.json').write_text('prior evidence', encoding='utf8')
    arguments(preflight, monkeypatch, state=state)
    with pytest.raises(AssertionError):
        preflight.main()
    assert [event[0] for event in preflight.events] == ['wheel', 'installed']
    if kind == 'existing':
        assert (state / 'keep.json').read_text(encoding='utf8') == 'prior evidence'
    else:
        assert not state.resolve().exists()


def cleanup_gate(rows, *, released=True, verified=True, blocked=False):
    events = []

    def blockers(*args, **kwargs):
        events.append(('blockers', args, kwargs))
        return ['hold'] if blocked else []

    def proof(name, valid):
        def check(*args):
            events.append((name,))
            return valid
        return check

    namespace = dict(store=SimpleNamespace(list=lambda **kwargs: {'items': rows}, mutation_blockers=blockers),
                     released_open_guard=proof('guard', released),
                     verified_open_native_steps=proof('steps', verified))
    return extract_function('safe', namespace, parent='internal'), events


def mutation_row(status='succeeded', phase='committed'):
    return dict(status=status, payload={'mutates': True}, mutation=dict(
        phase=phase, verification={'evidence': {'execution_guard': {'fake': True}}}, before_state={'fake': True}))


@pytest.mark.parametrize('status', ['unknown'])
def test_unresolved_jobs_refuse_cleanup_without_proof_or_retry(status):
    safe, events = cleanup_gate([mutation_row(status)])
    with pytest.raises(AssertionError):
        asyncio.run(safe())
    assert events == []


@pytest.mark.parametrize('kind', ['pending_step', 'hold'])
def test_cleanup_requires_terminal_phase_released_guard_complete_steps_and_no_hold(kind):
    safe, events = cleanup_gate([mutation_row(phase='pending_native' if kind == 'pending_phase' else 'committed')],
                               released=kind != 'guard_unreleased', verified=kind != 'pending_step',
                               blocked=kind == 'hold')
    with pytest.raises(AssertionError):
        asyncio.run(safe())
    assert [event[0] for event in events] == dict(pending_phase=[], guard_unreleased=['guard'],
        pending_step=['guard', 'steps'], hold=['guard', 'steps', 'blockers'])[kind]


@pytest.mark.parametrize('phase', ['rolled_back'])
def test_terminal_verified_jobs_allow_cleanup_gate_only(phase):
    safe, events = cleanup_gate([mutation_row(status='failed' if phase != 'committed' else 'succeeded', phase=phase)])
    asyncio.run(safe())
    assert [event[0] for event in events] == (['guard', 'blockers'] if phase == 'not_started'
                                           else ['guard', 'steps', 'blockers'])
    assert events[-1][1:] == (('native-open-test', 'any'), {'effect_scope': 'application'})


def test_unknown_submit_is_returned_once_then_cleanup_gate_holds():
    calls = []
    row = mutation_row(status='unknown')

    def submit(request, operation, payload, action, **kwargs):
        calls.append((request, operation, payload, kwargs))
        return {**row, 'operation_id': 'op_unknown', 'result': None, 'error': {'code': 'lost_effect'}}

    namespace = dict(uuid=SimpleNamespace(uuid4=lambda: SimpleNamespace(hex='unused')),
        SPECS={'document_open_native': SimpleNamespace(operation='document.open_native', mutates=True,
                                                       argument_defaults={'read_only': False})},
        docs=SimpleNamespace(list=lambda: None),
        catalog=SimpleNamespace(prepare_open=lambda: None, open=lambda: pytest.fail('No native retry')),
        runner=SimpleNamespace(submit=submit))
    read = extract_function('read', namespace, parent='internal')
    args = dict(request_id='exact_request', document_id='application', configuration='Основная',
                expected_revision='rev', native_file_id='source')
    result = asyncio.run(read('document_open_native', args))
    assert result['status'] == 'unknown' and result['operation_id'] == 'op_unknown'
    assert len(calls) == 1 and calls[0][0] == 'exact_request' and args['request_id'] == 'exact_request'
    safe, events = cleanup_gate([row])
    with pytest.raises(AssertionError):
        asyncio.run(safe())
    assert len(calls) == 1 and events == []


def test_verifier_contains_only_scoped_owned_close_not_global_close_or_exit():
    tree = ast.parse(SOURCE.read_text(encoding='utf8'))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)]
    forbidden = {'CloseAll', 'CloseAllDocuments', 'ExitApp', 'Quit', 'OpenDoc6'}
    assert not any(node.func.attr in forbidden for node in calls)
    closes = [node for node in calls if node.func.attr == 'CloseDoc']
    retire = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'retire_owned')
    assert len(closes) == 1 and closes[0] in list(ast.walk(retire))
    assert len(closes[0].args) == 1 and isinstance(closes[0].args[0], ast.Name) and closes[0].args[0].id == 'title'


@pytest.mark.parametrize('names, expected', [
    (['*Спереди', '*Изометрия', '*Триметрия'], '*Изометрия'),
    (('*Front', '*Isometric'), '*Isometric'),
])
def test_fixture_selects_one_passive_localized_standard_view(names, expected):
    select = extract_function('isometric_view_name', {})
    assert select(names) == expected


@pytest.mark.parametrize('names', [None, '*Isometric', [], [False], [''],
    ['*Front'], ['*Isometric', '*Изометрия'], ['*Isometric', '*Isometric']])
def test_fixture_refuses_unconfirmed_or_ambiguous_model_view_without_native_retry(names):
    select = extract_function('isometric_view_name', {})
    with pytest.raises(AssertionError):
        select(names)


@pytest.mark.parametrize('closed_active, switch_active, activation_throw', [
    (False, False, False), (False, True, False), (True, True, False), (False, True, True)])
def test_owned_drawing_cleanup_restores_surviving_active_once_without_retired_getters(
        closed_active, switch_active, activation_throw):
    class Model:
        def __init__(self, name):
            self.name, self.retired = name, False
        def GetTitle(self):
            assert not self.retired, 'No getter on a retired model'
            return self.name
    neighbor, assembly, drawing = [Model(name) for name in ('Сосед', 'Сборка', 'Чертёж')]
    owned = [neighbor, assembly, drawing]
    sw = SimpleNamespace(ActiveDoc=drawing if closed_active else neighbor)
    events = []
    def identity(model):
        assert not model.retired, 'No identity getter on a retired model'
        return model.name
    def close(title):
        assert title == drawing.name
        events.append('close')
        drawing.retired = True
        if closed_active or switch_active:
            sw.ActiveDoc = assembly
    def activate(application, model, title):
        assert model is neighbor and title == neighbor.name and not model.retired
        events.append('activate')
        if activation_throw:
            raise RuntimeError('one-shot fixture activation unconfirmed')
        application.ActiveDoc = model
    sw.GetDocuments = lambda: [model for model in owned if not model.retired]
    sw.CloseDoc = close
    namespace = dict(native_identity=identity, binding=SimpleNamespace(wrap=lambda raw, interface: raw),
                     activate_owned=activate)
    retire = extract_function('retire_owned', namespace)
    record = lambda models: events.append(('record', [identity(model) for model in models]))
    if activation_throw:
        with pytest.raises(RuntimeError):
            retire(sw, SimpleNamespace(IModelDoc2=object), drawing, [drawing], owned, record)
    else:
        retire(sw, SimpleNamespace(IModelDoc2=object), drawing, [drawing], owned, record)
        assert sw.ActiveDoc is (assembly if closed_active else neighbor)
    assert owned == [neighbor, assembly] and events.count('close') == 1
    assert events.count('activate') == int(switch_active and not closed_active)
    assert events[1] == ('record', ['Сосед', 'Сборка'])
