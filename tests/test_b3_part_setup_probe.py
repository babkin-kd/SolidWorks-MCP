"""Artificial CLI/owner/watch gates only; no CAD, COM, SDK or native proof."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from threading import Thread
from types import SimpleNamespace as NS

import pytest
from test_b3_part_setup import harness

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verify_b3_part_setup_probe as probe
    from verifier_b3_manifest import required_tools
finally:
    sys.path.remove(scripts)


@pytest.fixture
def passive(tmp_path, monkeypatch):
    source = tmp_path / 'scripts' / 'verify_b3_part_setup_probe.py'
    source.parent.mkdir()
    source.write_text('artificial source', encoding='utf8')
    monkeypatch.setattr(probe, '__file__', str(source))
    monkeypatch.setattr(probe, 'HELPERS', (source.name,))
    private = tmp_path / 'work'
    private.mkdir()
    template = tmp_path / 'template.prtdot'
    template.write_bytes(b'artificial template; never opened by CAD')
    wheel = dict(wheel_sha256='a'*64, package_version='artificial', git_sha='b'*40)
    names = sorted(required_tools())
    metadata = dict(accepted=True, scope='installed_wheel_console_metadata_v1',
        native_acceptance=False, cad_tools_called=[], job_tools_called=[], wheel=deepcopy(wheel),
        metadata_catalog=dict(tool_names=names, public_tool_count=len(names), schema_hash='c'*64,
                             output_schemas_verified=True, build_matches_installed_wheel=True))
    report = private / 'metadata.json'
    report.write_text(json.dumps(metadata), encoding='utf8')
    calls = []
    monkeypatch.setattr(probe, 'validate_wheel', lambda *a, **k: calls.append('wheel') or wheel)
    monkeypatch.setattr(probe, 'installed_identity', lambda actual: calls.append('installed')
                        if actual is wheel else pytest.fail('wrong installed identity'))
    args = NS(run_solidworks=True, state_dir=private/'probe', part_template=template,
              metadata_report=report, wheel=private/'candidate.whl',
              expected_version='artificial', expected_git_sha='b'*40)
    return args, calls, metadata


def test_passive_preflight_has_no_acceptance_authority(passive):
    args, calls, _ = passive
    state, template, report = probe.preflight(args)
    assert calls == ['wheel', 'installed']
    assert not state.exists() and template == args.part_template
    for key in ('accepted', 'native_acceptance', 'sdk_ready', 'probe_passed',
                'own_cleanup_verified', 'baseline_restored', 'native_calls_live'):
        assert report[key] is False
    assert len(report['remaining_gates']) == 5
    assert len(report['metadata_report_sha256']) == 64


@pytest.mark.parametrize('fault', ['no_opt_in', 'existing_state', 'work_root', 'outside_work',
    'relative_template', 'missing_template', 'wrong_template', 'outside_metadata', 'missing_metadata'])
def test_cli_paths_and_opt_in_fail_before_identity(passive, fault):
    args, calls, _ = passive
    if fault == 'no_opt_in': args.run_solidworks = False
    elif fault == 'existing_state': args.state_dir.mkdir()
    elif fault == 'work_root': args.state_dir = args.state_dir.parent
    elif fault == 'outside_work': args.state_dir = args.part_template.parent/'outside'
    elif fault == 'relative_template': args.part_template = Path('template.prtdot')
    elif fault == 'missing_template': args.part_template = args.part_template.with_name('missing.prtdot')
    elif fault == 'wrong_template':
        args.part_template = args.part_template.with_suffix('.sldprt')
        args.part_template.write_bytes(b'not template')
    elif fault == 'outside_metadata':
        args.metadata_report = args.part_template.parent/'outside.json'
        args.metadata_report.write_text('{}')
    else: args.metadata_report = args.metadata_report.with_name('missing.json')
    with pytest.raises(ValueError): probe.preflight(args)
    assert calls == []


@pytest.mark.parametrize('fault', ['cad_called', 'wrong_wheel', 'unaccepted', 'native_claim'])
def test_prior_report_must_be_exact_metadata_only(passive, fault):
    args, _, metadata = passive
    if fault == 'cad_called': metadata['cad_tools_called'] = ['document_list']
    elif fault == 'wrong_wheel': metadata['wheel']['git_sha'] = 'd'*40
    elif fault == 'unaccepted': metadata['accepted'] = False
    else: metadata['native_acceptance'] = True
    args.metadata_report.write_text(json.dumps(metadata), encoding='utf8')
    with pytest.raises(ValueError): probe.preflight(args)
    assert not args.state_dir.exists()


def test_installed_failure_prevents_directory_and_dispatch(passive, monkeypatch):
    args, _, _ = passive
    monkeypatch.setattr(probe, 'installed_identity', lambda _: (_ for _ in ()).throw(ValueError('source package')))
    with pytest.raises(ValueError, match='source package'): probe.preflight(args)
    assert not args.state_dir.exists()


def test_main_only_dispatches_after_passive_gates_and_fresh_report(passive, monkeypatch):
    args, _, _ = passive
    seen = []
    def native(state, template, report):
        assert state.is_dir() and (state/'probe-report.json').is_file()
        assert report['accepted'] is report['sdk_ready'] is False
        seen.append((state, template))
    monkeypatch.setattr(probe, 'run_native', native)
    argv = ['--run-solidworks', '--state-dir', str(args.state_dir), '--part-template', str(args.part_template),
            '--wheel', str(args.wheel), '--expected-version', args.expected_version,
            '--expected-git-sha', args.expected_git_sha, '--metadata-report', str(args.metadata_report)]
    probe.main(argv)
    assert seen == [(args.state_dir, args.part_template)]


class Watch:
    def __init__(self): self.births = []
    def admit(self, births): self.births.append(tuple(births))
    def poll(self): return (0, ())


@pytest.fixture
def owner():
    app = NS(canonical='app', CommandInProgress=False, ActiveDoc=None)
    setup = NS(halted=False, journal_lost=False, guard_returned=False, part=None, cylinder=None)
    state = NS(models=[], windows=[])
    adapter = NS(_sw=app, identity=lambda obj: obj.canonical,
                 documents=lambda: list(state.models), native_close_windows=lambda: list(state.windows))
    original = probe.Owner(adapter, setup, Watch(), app=app, canonical='app')
    return original, state


def birth(owner, state, label='Основная деталь:new_document', hwnd=100):
    model = NS(canonical=label)
    fixture = NS(thread_id=owner.thread_id, halted=False, journal_lost=False,
                 native_returns=[(1, label, model)])
    owner.receipt.part = fixture
    state.models = [model]
    state.windows = [(model, {'hwnd': hwnd})]
    owner.app.ActiveDoc = model
    owner.app.CommandInProgress = owner.receipt.guard_returned = True
    return model, fixture


def test_idle_and_normally_returned_guard_are_distinct(owner):
    original, _ = owner
    assert original.safe(original.receipt) is True
    original.app.CommandInProgress = True
    with pytest.raises(ValueError, match='guard'): original.safe(original.receipt)


def test_original_birth_before_anchor_naming_is_custody(owner):
    original, state = owner
    model, _ = birth(original, state)
    assert original.safe(original.receipt) is True
    assert original.birth_bindings == [(model.canonical, 100)]
    assert original.watch.births[-1] == (('Основная деталь:new_document', model),)
    assert original.returned_reads and original.pending_read is None


@pytest.mark.parametrize('fault', ['foreign_model', 'missing_window', 'foreign_window', 'duplicate_window',
    'bool_hwnd', 'zero_hwnd', 'swapped_hwnd', 'missing_model', 'foreign_active', 'wrong_app',
    'replaced_canonical', 'setup_halted', 'journal_lost', 'fixture_halted', 'fixture_journal_lost',
    'wrong_birth_label', 'duplicate_birth', 'null_birth', 'wrong_ledger_shape', 'wrong_fixture_sta'])
def test_owner_admission_rejects_unproven_current_custody(owner, fault):
    original, state = owner
    model, fixture = birth(original, state)
    original.safe(original.receipt)
    foreign = NS(canonical='foreign')
    if fault == 'foreign_model': state.models = [foreign]
    elif fault == 'missing_window': state.windows = []
    elif fault == 'foreign_window': state.windows = [(foreign, {'hwnd': 100})]
    elif fault == 'duplicate_window': state.windows += state.windows
    elif fault == 'bool_hwnd': state.windows = [(model, {'hwnd': True})]
    elif fault == 'zero_hwnd': state.windows = [(model, {'hwnd': 0})]
    elif fault == 'swapped_hwnd': state.windows = [(model, {'hwnd': 200})]
    elif fault == 'missing_model': state.models = []
    elif fault == 'foreign_active': original.app.ActiveDoc = foreign
    elif fault == 'wrong_app': original.adapter._sw = NS(canonical='app')
    elif fault == 'replaced_canonical': original.app.canonical = 'new-app'
    elif fault == 'setup_halted': original.receipt.halted = True
    elif fault == 'journal_lost': original.receipt.journal_lost = True
    elif fault == 'fixture_halted': fixture.halted = True
    elif fault == 'fixture_journal_lost': fixture.journal_lost = True
    elif fault == 'wrong_birth_label': fixture.native_returns = [(1, 'name-adopted:new_document', model)]
    elif fault == 'duplicate_birth': fixture.native_returns *= 2
    elif fault == 'null_birth': fixture.native_returns = [(1, 'Основная деталь:new_document', None)]
    elif fault == 'wrong_ledger_shape': fixture.native_returns = [('bad', 'Основная деталь:new_document', model)]
    else: fixture.thread_id += 1
    with pytest.raises(ValueError): original.safe(original.receipt)


def test_birth_handle_identity_does_not_adopt_same_name(owner):
    original, state = owner
    model, _ = birth(original, state)
    model.title = 'Same name'
    foreign = NS(canonical='another', title='Same name')
    state.models = [foreign]
    state.windows = [(foreign, {'hwnd': 100})]
    original.app.ActiveDoc = foreign
    with pytest.raises(ValueError): original.safe(original.receipt)


def test_native_read_exception_retains_pending_and_latches(owner):
    original, _ = owner
    def unknown(): raise RuntimeError('returned Python exception; native outcome unknown')
    with pytest.raises(RuntimeError): original.read('unknown getter', unknown)
    assert original.pending_read == 'unknown getter' and original.halted
    with pytest.raises(ValueError): original.read('retry', lambda: True)
    assert original.returned_reads == []


@pytest.mark.parametrize('fault', ['foreign_sta', 'foreign_process', 'read_budget', 'admission_budget'])
def test_owner_thread_process_and_budgets(owner, fault):
    original, _ = owner
    if fault == 'foreign_process': original.process_id += 1
    elif fault == 'read_budget': original.returned_reads = [('fake', None)]*60000
    elif fault == 'admission_budget': original.admission_count = 6000
    if fault == 'foreign_sta':
        errors = []
        def attempt():
            try: original.safe(original.receipt)
            except ValueError as error: errors.append(error)
        thread = Thread(target=attempt); thread.start(); thread.join()
        assert len(errors) == 1
    else:
        with pytest.raises(ValueError): original.safe(original.receipt)


def test_declared_normal_hold_never_claims_maintenance_cleanup():
    assert 'separate current ownership/closed-mode/quiescence' in probe.MAINTENANCE_GATE
    assert 'before close or guard release' in probe.MAINTENANCE_GATE


def test_application_watch_rejects_incomplete_registered_events():
    adapter = NS(_module=NS(DSldWorksEvents=NS(_dispid_to_func_={1:'OnFileNewNotify2'})))
    with pytest.raises(ValueError, match='registered native|Registered native'):
        probe.NativeWatch(adapter, NS(), lambda *_: None)


def test_application_and_part_events_are_actual_sink_callbacks():
    class Base:
        _dispid_to_func_ = dict(enumerate(probe.NativeWatch.EVENTS))
        def __init__(self, app): self.app = app
    part = NS(poll=lambda: 7)
    adapter = NS(_module=NS(DSldWorksEvents=Base), _sw=object(), watch_part=lambda _: part)
    watch = probe.NativeWatch(adapter, NS(PumpWaitingMessages=lambda: 0), lambda raw, _: raw)
    model = object()
    watch.admit([('cylinder:new_document', model)])
    watch.admit([('cylinder:new_document', model)])
    assert len(watch.parts) == 1
    watch.sink.OnFileNewNotify2('ignored COM args')
    assert watch.poll() == (1, (('cylinder:new_document', 7),))
    watch.sink.OnDestroyNotify()
    with pytest.raises(ValueError, match='remain live'): watch.poll()


def test_private_report_write_has_no_raw_proxy_serialization(tmp_path):
    path = tmp_path/'probe-report.json'
    probe.write_json(path, {'accepted': False, 'phase': 'artificial'})
    assert json.loads(path.read_text()) == {'accepted': False, 'phase': 'artificial'}
    assert not path.with_suffix('.pending').exists()


@pytest.mark.parametrize('fault', ['operation', 'pid_bool', 'foreign_pid', 'token', 'extra', 'failed', 'pending'])
def test_maintenance_command_cannot_adopt_foreign_or_failed_owner(fault):
    report = dict(maintenance_request_token='exact', phase='probe_complete_guard_held',
                  probe_passed=True, synchronous_setup_returned=True, native_calls_live=False)
    command = dict(operation='close_owned_and_restore_baseline', owner_pid=probe.os.getpid(), request_token='exact')
    if fault == 'operation': command['operation'] = 'retry_setup'
    elif fault == 'pid_bool': command['owner_pid'] = True
    elif fault == 'foreign_pid': command['owner_pid'] += 1
    elif fault == 'token': command['request_token'] = 'foreign'
    elif fault == 'extra': command['adopt_by_title'] = True
    elif fault == 'failed': report['phase'] = 'failed_owner_held'
    else: report['native_calls_live'] = True
    with pytest.raises(ValueError): probe.validate_maintenance_request(command, report)


def test_exact_one_shot_maintenance_command_is_not_b3_acceptance():
    report = dict(maintenance_request_token='exact', phase='probe_complete_guard_held',
                  probe_passed=True, synchronous_setup_returned=True, native_calls_live=False)
    probe.validate_maintenance_request(dict(operation='close_owned_and_restore_baseline',
                                          owner_pid=probe.os.getpid(), request_token='exact'), report)


@pytest.mark.parametrize('fault', ['pending_setup', 'journal_lost', 'unreturned_guard', 'incomplete', 'failed_owner'])
def test_maintenance_fails_before_native_reads_for_unproven_setup(owner, monkeypatch, fault):
    monkeypatch.syspath_prepend(scripts)
    original, _ = owner
    original.receipt.setup_complete = True
    original.receipt.pending_step = None
    original.receipt.guard_acquired = original.receipt.guard_returned = True
    if fault == 'pending_setup': original.receipt.pending_step = 'unknown'
    elif fault == 'journal_lost': original.receipt.journal_lost = True
    elif fault == 'unreturned_guard': original.receipt.guard_returned = False
    elif fault == 'incomplete': original.receipt.setup_complete = False
    else: original.receipt.halted = True
    with pytest.raises(ValueError):
        probe.maintain_original_owner(original, lambda *_: pytest.fail('unexpected wrap'),
            lambda: pytest.fail('unexpected preferences'), lambda *_: pytest.fail('unexpected journal'),
            {}, lambda: pytest.fail('unexpected report'))
    assert original.returned_reads == []


@pytest.fixture
def maintenance_owner(owner, monkeypatch):
    """Artificial same-owner close stack; getters of retired targets fail."""
    monkeypatch.syspath_prepend(scripts)
    original, state = owner
    app, setup = original.app, original.receipt
    context = dict(visible=True, dependencies=[], mode=dict(editing_sketch=False, editing_component=False,
        view_only=False, read_only_state=0, blocking_state=0))
    application_context = dict(user_control=True, visible=True, current_directory='fixture', search_folders='')
    prefs = dict(dimension_input=False, step_ap=214)
    calls, retired, labels = [], [], sorted(probe.BIRTH_LABELS)
    class Model:
        def __init__(self, index, label):
            self.canonical, self.title = label, 'Контрольная '+str(index)
            self.SketchManager = NS(AddToDB=False, ActiveSketch=None)
        def current(self):
            assert self not in retired, 'getter on retired original target'
        def GetTitle(self): self.current(); return self.title
        def GetPathName(self): self.current(); return ''
        def GetType(self): self.current(); return 1
    models = [Model(index, label) for index, label in enumerate(labels)]
    state.models = models[:]
    state.windows = [(model, {'hwnd':100+index}) for index, model in enumerate(models)]
    def close(title):
        match = [model for model in state.models if model.title == title]
        assert len(match) == 1
        model = match[0]
        calls.append(('close', model))
        retired.append(model)
        state.models.remove(model)
        state.windows = [(current, info) for current, info in state.windows if current is not model]
        app.ActiveDoc = state.models[-1] if state.models else None
    app.CloseDoc = close
    app.CommandInProgress = setup.guard_returned = setup.guard_acquired = True
    app.ActiveDoc = models[-1]
    for name, scoped in (('part', models[:2]), ('cylinder', models[2:])):
        fixture = NS(thread_id=original.thread_id, setup_complete=True, halted=False, journal_lost=False,
                     pending_step=None, native_returns=[(index+1, model.canonical, model)
                                                       for index, model in enumerate(scoped)])
        setattr(setup, name, fixture)
    setup.setup_complete = True
    setup.part_request_id = 'artificial-original-part-request'
    setup.pending_step = None
    setup.raw_returns = [('setup:own_guard', None)]
    setup.baseline = NS(context=application_context, preferences=prefs)
    setup.initial = NS(complete=True, halted=False, pending_read=None, baseline=setup.baseline)
    completed = lambda: NS(complete=True, halted=False, pending_read=None)
    setup.admissions = [completed(), completed()]
    setup.templates = [completed(), completed(), completed()]
    setup.anchor_receipts = {role: completed() for role in ('Основная деталь', 'Сосед')}
    setup.birth_windows = [(NS(handle=model, canonical=model.canonical), 100+index)
                           for index, model in enumerate(models)]
    original.birth_bindings = [(model.canonical, 100+index) for index, model in enumerate(models)]
    original.watch.parts = []
    def model_context(model): model.current(); return deepcopy(context)
    original.adapter.native_close_model_context = model_context
    original.adapter.native_close_application_context = lambda: deepcopy(application_context)
    report = dict(accepted=False, native_acceptance=False, sdk_ready=False, baseline_restored=False,
                  own_cleanup_verified=False)
    rows = []
    wrap = lambda value, interface: value
    reader = lambda: deepcopy(prefs)
    recorder = lambda request, label, phase, data: rows.append((request,label,phase,data))
    persist = lambda: None
    return NS(owner=original, state=state, context=context, prefs=prefs, report=report,
              models=models, calls=calls, retired=retired, rows=rows,
              wrap=wrap, reader=reader, recorder=recorder, persist=persist)


def maintenance(value):
    return probe.maintain_original_owner(value.owner, value.wrap, value.reader,
                                         value.recorder, value.report, value.persist)


def test_same_owner_normal_cleanup_checks_baseline_and_never_gets_retired_targets(maintenance_owner):
    value = maintenance_owner
    maintenance(value)
    assert len(value.calls) == len(value.retired) == 3
    assert value.owner.app.CommandInProgress is False
    assert value.state.models == value.state.windows == []
    assert value.report['own_cleanup_verified'] is value.report['baseline_restored'] is True
    assert value.report['accepted'] is value.report['native_acceptance'] is value.report['sdk_ready'] is False
    assert value.report['maintenance_pending'] is None
    assert value.report['phase'] == 'maintenance_complete_owner_held'
    assert value.report['retained_process'] is True
    assert [row[2] for row in value.rows] == ['pending','returned']*4
    assert [row[3]['step_index'] for row in value.rows] == [1,1,2,2,3,3,4,4]
    assert [label for label, _ in value.owner.returned_reads if label.startswith('maintenance:')] == [
        'maintenance:close_original']*3+['maintenance:restore_own_guard']


@pytest.mark.parametrize('fault', ['editing', 'dependency', 'blocking', 'view_only', 'db_mode',
    'saved', 'foreign_window', 'foreign_model', 'changed_preference', 'incomplete_templates',
    'pending_topology', 'wrong_birth_hwnd', 'duplicate_title'])
def test_maintenance_refuses_before_any_close_for_unsafe_current_state(maintenance_owner, fault):
    value = maintenance_owner
    if fault == 'editing': value.context['mode']['editing_sketch'] = True
    elif fault == 'dependency': value.context['dependencies'] = ['foreign.sldprt']
    elif fault == 'blocking': value.context['mode']['blocking_state'] = 4
    elif fault == 'view_only': value.context['mode']['view_only'] = True
    elif fault == 'db_mode': value.models[0].SketchManager.AddToDB = True
    elif fault == 'saved': value.models[0].GetPathName = lambda: 'saved.sldprt'
    elif fault == 'foreign_window': value.state.windows[0] = (value.models[0], {'hwnd':999})
    elif fault == 'foreign_model': value.state.models[0] = NS(canonical='foreign')
    elif fault == 'changed_preference': value.reader = lambda: dict(dimension_input=True, step_ap=214)
    elif fault == 'incomplete_templates': value.owner.receipt.templates.pop()
    elif fault == 'pending_topology': value.owner.receipt.anchor_receipts['Сосед'].pending_read = 'unknown'
    elif fault == 'wrong_birth_hwnd': value.owner.receipt.birth_windows[0] = (value.owner.receipt.birth_windows[0][0],999)
    else: value.models[0].title = value.models[1].title
    with pytest.raises((ValueError, AssertionError)): maintenance(value)
    assert value.calls == value.rows == []
    assert value.owner.app.CommandInProgress is True
    assert value.report['baseline_restored'] is False


@pytest.mark.parametrize('phase', ['pending', 'returned'])
def test_maintenance_journal_loss_never_retries_and_keeps_actual_raw_returns(maintenance_owner, phase):
    value = maintenance_owner
    def recorder(request, label, actual, data):
        value.rows.append((request,label,actual,data))
        if actual == phase: raise OSError('artificial fsync loss')
    value.recorder = recorder
    with pytest.raises(OSError): maintenance(value)
    assert len(value.calls) == (0 if phase == 'pending' else 1)
    raw = [row for row in value.owner.returned_reads if row[0] == 'maintenance:close_original']
    assert len(raw) == (0 if phase == 'pending' else 1)
    assert value.report['maintenance_pending'] == 'maintenance:close_original'
    assert value.report['maintenance_journal_lost'] is True
    assert value.owner.app.CommandInProgress is True


def test_foreign_model_after_pending_journal_prevents_close(maintenance_owner):
    value = maintenance_owner
    original = value.recorder
    def recorder(request, label, phase, data):
        original(request,label,phase,data)
        if phase == 'pending': value.state.models.append(NS(canonical='foreign'))
    value.recorder = recorder
    with pytest.raises(ValueError): maintenance(value)
    assert value.calls == []
    assert value.report['maintenance_pending'] == 'maintenance:close_original'


def test_unknown_close_keeps_pending_without_false_normal_raw_return(maintenance_owner):
    value = maintenance_owner
    value.owner.app.CloseDoc = lambda _: (_ for _ in ()).throw(RuntimeError('unknown close'))
    with pytest.raises(RuntimeError): maintenance(value)
    assert value.report['maintenance_pending'] == 'maintenance:close_original'
    assert value.report['native_calls_live'] is False
    assert not any(row[0]=='maintenance:close_original' for row in value.owner.returned_reads)
    assert value.report['own_cleanup_verified'] is False


def test_unacknowledged_maintenance_is_not_retried_even_when_roster_still_matches(maintenance_owner):
    value = maintenance_owner
    value.recorder = lambda *_: (_ for _ in ()).throw(OSError('pending recorder loss'))
    with pytest.raises(OSError): maintenance(value)
    count = len(value.owner.returned_reads)
    with pytest.raises(ValueError, match='One fresh maintenance attempt'): maintenance(value)
    assert len(value.owner.returned_reads) == count and value.calls == []


def native_application_watch(value):
    """Artificial native event source using the actual generated sink handlers."""
    class Base:
        _dispid_to_func_ = dict(enumerate(probe.NativeWatch.EVENTS))
        def __init__(self, app): self.app = app
    adapter = value.owner.adapter
    adapter._module = NS(DSldWorksEvents=Base)
    adapter.watch_part = lambda _: NS(poll=lambda: 0, close=lambda: None)
    watch = probe.NativeWatch(adapter, NS(PumpWaitingMessages=lambda: 0), value.wrap)
    value.owner.watch = watch
    return watch


@pytest.mark.parametrize('injection', ['pending_recorder', 'target_recheck', 'last_report_persist'])
def test_app_event_aba_inside_maintenance_boundary_prevents_every_close(maintenance_owner, injection):
    value = maintenance_owner
    watch = native_application_watch(value)
    injected = []
    def aba():
        # Foreign document/window arrive and disappear before the roster is
        # inspected. All final getters match; actual application callbacks
        # must still prevent the write.
        foreign = NS(canonical='transient-foreign')
        value.state.models.append(foreign)
        value.state.windows.append((foreign, {'hwnd':999}))
        watch.sink.OnFileOpenPostNotify('ignored native arguments')
        value.state.models.pop()
        value.state.windows.pop()
        watch.sink.OnFileCloseNotify('ignored native arguments')
        injected.append(True)
    if injection == 'pending_recorder':
        original = value.recorder
        def recorder(request, label, phase, data):
            original(request,label,phase,data)
            if phase == 'pending': aba()
        value.recorder = recorder
    elif injection == 'target_recheck':
        original = value.owner.adapter.native_close_model_context
        def context(model):
            result = original(model)
            if value.report.get('maintenance_pending') == 'maintenance:close_original': aba()
            return result
        value.owner.adapter.native_close_model_context = context
    else:
        def persist():
            if value.report.get('native_calls_live') is True: aba()
        value.persist = persist
    with pytest.raises(ValueError, match='event raced pending maintenance'): maintenance(value)
    assert injected == [True]
    assert value.calls == value.retired == []
    assert value.owner.app.CommandInProgress is True
    assert value.report['maintenance_pending'] == 'maintenance:close_original'
    assert value.report['native_calls_live'] is False
    assert value.report['baseline_restored'] is value.report['own_cleanup_verified'] is False
    assert not any(label == 'maintenance:close_original' for label, _ in value.owner.returned_reads)
    count = len(value.owner.returned_reads)
    with pytest.raises(ValueError, match='One fresh maintenance attempt'): maintenance(value)
    assert len(value.owner.returned_reads) == count and value.calls == []


def test_completed_close_events_are_admitted_at_next_step_opening_boundary(maintenance_owner):
    value = maintenance_owner
    watch = native_application_watch(value)
    original = value.owner.app.CloseDoc
    def close(title):
        original(title)
        watch.sink.OnFileCloseNotify('normal own close completed')
    value.owner.app.CloseDoc = close
    maintenance(value)
    assert len(value.calls) == 3 and watch.sequence == 3
    assert value.report['own_cleanup_verified'] is value.report['baseline_restored'] is True
    assert value.owner.app.CommandInProgress is False


def test_event_race_before_guard_restore_keeps_own_guard_held(maintenance_owner):
    value = maintenance_owner
    watch = native_application_watch(value)
    original = value.recorder
    def recorder(request, label, phase, data):
        original(request,label,phase,data)
        if phase == 'pending' and label == 'maintenance:restore_own_guard':
            watch.sink.OnActiveDocChangeNotify('ABA empty active state')
    value.recorder = recorder
    with pytest.raises(ValueError, match='event raced pending maintenance'): maintenance(value)
    assert len(value.calls) == 3 and value.state.models == value.state.windows == []
    assert value.owner.app.CommandInProgress is True
    assert value.report['maintenance_pending'] == 'maintenance:restore_own_guard'
    assert value.report['native_calls_live'] is False
    assert value.report['own_cleanup_verified'] is False
    assert not any(label == 'maintenance:restore_own_guard' for label, _ in value.owner.returned_reads)


def test_terminal_publication_waits_for_original_sink_adapter_and_sta(maintenance_owner):
    value = maintenance_owner
    published = []
    value.persist = lambda: published.append(deepcopy(value.report))
    maintenance(value)
    assert all(row.get('phase') != 'terminal' and row.get('retained_process', True) is True for row in published)
    returned = []
    def callback(label):
        def run():
            assert not any(row.get('phase') == 'terminal' for row in published)
            assert value.report['retained_process'] is True
            assert value.report['shutdown_complete'] is False
            returned.append(label)
            return 'actual artificial return '+label
        return run
    value.owner.watch.sink = NS(close=callback('sink'))
    value.owner.adapter.close = callback('adapter')
    probe.shutdown_original_owner(value.owner, callback('STA'), value.report, value.persist)
    assert returned == ['sink', 'adapter', 'STA']
    assert published[-1]['phase'] == 'terminal' and published[-1]['retained_process'] is False
    assert published[-1]['shutdown_complete'] is True
    assert [row.get('phase') for row in published].count('terminal') == 1
    assert [row for row in value.owner.returned_reads if row[0].startswith('shutdown:')] == [
        ('shutdown:application_sink','actual artificial return sink'),
        ('shutdown:adapter','actual artificial return adapter'),
        ('shutdown:STA','actual artificial return STA')]
    assert value.report['accepted'] is value.report['native_acceptance'] is value.report['sdk_ready'] is False


@pytest.mark.parametrize('failure', ['sink', 'adapter', 'STA'])
def test_shutdown_failure_keeps_held_outcome_and_never_repeats_cleanup(maintenance_owner, failure):
    value = maintenance_owner
    maintenance(value)
    close_count = len(value.calls)
    published, entered = [], []
    value.persist = lambda: published.append(deepcopy(value.report))
    def callback(label):
        def run():
            entered.append(label)
            if label == failure: raise RuntimeError('artificial shutdown outcome unknown')
            return None
        return run
    value.owner.watch.sink = NS(close=callback('sink'))
    value.owner.adapter.close = callback('adapter')
    sta = callback('STA')
    with pytest.raises(RuntimeError): probe.shutdown_original_owner(value.owner, sta, value.report, value.persist)
    order = ['sink','adapter','STA']
    assert entered == order[:order.index(failure)+1]
    assert all(row['phase'] != 'terminal' and row['retained_process'] is True for row in published)
    assert value.report['phase'] == 'shutdown_failed_owner_held'
    assert value.report['shutdown_complete'] is False and value.report['native_calls_live'] is False
    assert value.report['shutdown_pending'] == {
        'sink':'shutdown:application_sink', 'adapter':'shutdown:adapter', 'STA':'shutdown:STA'}[failure]
    assert len(value.report['shutdown_returns']) == order.index(failure)
    assert value.report['baseline_restored'] is value.report['own_cleanup_verified'] is True
    entered_before = entered[:]
    with pytest.raises(ValueError): probe.shutdown_original_owner(value.owner, sta, value.report, value.persist)
    with pytest.raises(ValueError, match='One fresh maintenance attempt'): maintenance(value)
    assert entered == entered_before and len(value.calls) == close_count


def test_shutdown_is_not_admitted_before_maintenance_baseline_proof(maintenance_owner):
    value = maintenance_owner
    value.report['phase'] = 'probe_complete_guard_held'
    with pytest.raises(ValueError):
        probe.shutdown_original_owner(value.owner, lambda: pytest.fail('premature STA release'),
                                      value.report, lambda: pytest.fail('premature terminal report'))
    assert value.calls == [] and 'shutdown_attempted' not in value.report


def test_original_probe_owner_drives_actual_source_setup_with_normal_birth_events(harness):
    # Reuse API-shaped geometry factories; run the real source orchestration
    # with this probe's actual Owner/NativeWatch instead of a generic True gate.
    x=harness
    x.admissions=1  # Enable the reused fake's own diagnostic instrumentation.
    class Base:
        _dispid_to_func_=dict(enumerate(probe.NativeWatch.EVENTS))
        def __init__(self,app):self.app=app
    x.adapter._module=NS(DSldWorksEvents=Base)
    x.adapter.watch_part=lambda model:NS(poll=lambda:0,close=lambda:None)
    watch=probe.NativeWatch(x.adapter,NS(PumpWaitingMessages=lambda:0),x.wrap)
    original=probe.Owner(x.adapter,x.receipt,watch,app=x.application,canonical=x.application.canonical)
    new_document=x.application.NewDocument
    def born(*args):
        model=new_document(*args)
        watch.sink.OnFileNewNotify2('normally returned owned birth')
        return model
    x.application.NewDocument=born
    result=x.run(assert_safe=original.safe,watch_poll=watch.poll,reference_watch=watch)
    assert result is x.receipt and result.setup_complete is True
    assert len(original.birth_bindings)==len(original.births())==watch.sequence==3
    assert [len(result.original_objects[role]) for role in ('Основная деталь','Сосед')]==[44,19]
    assert original.pending_read is None and original.halted is False
    assert original.admission_count>0 and x.application.CommandInProgress is True
    assert result.sdk_ready is result.accepted is result.native_acceptance is False
