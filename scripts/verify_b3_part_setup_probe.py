"""Private original-owner B3 part setup compatibility probe, never acceptance.

No SDK/server is started. Successful setup retains the original STA, guard and
documents until an explicit private command runs independently proven same-STA
maintenance. Failure retains the same receipts, including pending/ack-lost calls.
"""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from verify_b3_preflight import validate_metadata
from verify_installed_metadata import installed_identity
from verify_wheel_artifact import validate_wheel


HELPERS = ('verify_b3_part_setup_probe.py', 'verifier_b3_part_setup.py',
           'verifier_b3_application_admission.py', 'verifier_b3_empty_template.py',
           'verifier_b3_part_fixture.py', 'verifier_b3_cylinder_fixture.py',
           'verifier_b3_part_anchors.py', 'verifier_b3_part_bridge.py',
           'verifier_dimension_diagnostics.py', 'verify_export_operations.py',
           'verify_b3_preflight.py', 'verifier_b3_manifest.py',
           'verifier_b3_public_contract.py', 'verify_installed_metadata.py',
           'verify_wheel_artifact.py')
BIRTH_LABELS = frozenset(('Основная деталь:new_document', 'Сосед:new_document',
                          'cylinder:new_document'))
MAINTENANCE_GATE = ('Original receipts and guard remain on the live original STA. '
                    'A separate current ownership/closed-mode/quiescence and '
                    'baseline/non-STL maintenance proof is required before close '
                    'or guard release. No cleanup permission is inferred from setup.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight(args):
    """Only offline checks; do not connect to CAD or repeat metadata SDK work."""
    require(args.run_solidworks is True, 'Explicit --run-solidworks is required.')
    private = Path(__file__).resolve().parents[1] / 'work'
    state = args.state_dir.resolve()
    require(state.is_relative_to(private) and state != private and not state.exists(),
            'Fresh private child directory of work/ required.')
    template = args.part_template
    require(template.is_absolute() and template.is_file()
            and template.suffix.lower() == '.prtdot',
            'Explicit existing absolute .prtdot template required.')
    metadata = args.metadata_report.resolve()
    require(metadata.is_relative_to(private) and metadata.is_file(),
            'Existing private metadata-only report required.')
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version,
                           expected_git_sha=args.expected_git_sha)
    installed_identity(wheel)
    raw = metadata.read_bytes()
    validate_metadata(json.loads(raw), wheel)
    return state, template.resolve(), dict(
        scope='original_b3_part_setup_compatibility_probe_v1', wheel=wheel,
        metadata_report_sha256=hashlib.sha256(raw).hexdigest(),
        verifier_hashes={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                         for name in HELPERS},
        accepted=False, native_acceptance=False, sdk_ready=False,
        probe_passed=False, own_cleanup_verified=False, baseline_restored=False,
        native_calls_live=False, synchronous_setup_returned=False,
        phase='preflight', remaining_gates=[
            'whole_session_baseline', 'original_guard_handoff', 'same_wheel_B1_sketch',
            'assembly_fixtures_and_transitions', 'SDK_namespace_and_13_groups'])


@dataclass
class Owner:
    """Actual custody, never serialized and never reconstructed from names."""
    adapter: object
    receipt: object
    watch: object
    thread_id: int = field(default_factory=threading.get_ident)
    process_id: int = field(default_factory=os.getpid)
    app: object = None
    canonical: object = None
    returned_reads: list = field(default_factory=list)
    pending_read: str | None = None
    admission_count: int = 0
    birth_bindings: list = field(default_factory=list)
    halted: bool = False

    def read(self, label, function, *args):
        require(not self.halted and self.pending_read is None
                and self.thread_id == threading.get_ident() and self.process_id == os.getpid()
                and len(self.returned_reads) < 60000,
                'Original process/STA with finite returned-read custody required.')
        self.pending_read = label
        try:
            result = function(*args)
        except BaseException:
            self.halted = True
            raise
        self.returned_reads.append((label, result))
        self.pending_read = None
        return result

    def births(self):
        result = []
        for fixture in (self.receipt.part, self.receipt.cylinder):
            if fixture is None:
                continue
            require(fixture.thread_id == self.thread_id and not fixture.halted
                    and not fixture.journal_lost,
                    'Only original nonfailed fixture receipts admit further reads.')
            for row in fixture.native_returns:
                require(type(row) is tuple and len(row) == 3 and type(row[0]) is int
                        and row[0] > 0 and type(row[1]) is str,
                        'Actual native return ledger must retain its original shape.')
                if row[1] in BIRTH_LABELS:
                    require(row[2] is not None and row[1] not in [label for label, _ in result],
                            'Sole normal raw NewDocument return for each declared birth required.')
                    result.append((row[1], row[2]))
        require(len(result) <= 3, 'Only the three original probe births are supported.')
        return result

    def safe(self, setup):
        require(setup is self.receipt and not setup.halted and not setup.journal_lost,
                'Exact externally retained nonfailed setup receipt required.')
        self.admission_count += 1
        require(self.admission_count <= 6000, 'Finite owner admission budget exceeded.')
        adapter = self.adapter
        require(adapter._sw is self.app
                and self.read('application_identity', adapter.identity, self.app) == self.canonical,
                'Exact original application identity required.')
        guard = self.read('owned_guard', getattr, self.app, 'CommandInProgress')
        require(type(guard) is bool and guard is bool(setup.guard_returned),
                'Idle baseline or normally returned own guard required; no foreign guard adoption.')
        event = self.watch.poll()
        births = self.births()
        tokens = [self.read('raw_birth_identity', adapter.identity, raw) for _, raw in births]
        require(all(token is not None and sum(token == other for other in tokens) == 1
                    for token in tokens), 'Distinct strong raw original birth canonicals required.')
        models = self.read('complete_models', adapter.documents)
        windows = self.read('complete_windows', adapter.native_close_windows)
        require(type(models) in (tuple, list) and type(windows) in (tuple, list)
                and len(models) == len(windows) == len(tokens),
                'Full current model/window roster must equal the original raw births.')
        current = [self.read('current_identity', adapter.identity, model) for model in models]
        require(all(sum(token == other for other in current) == 1 for token in tokens),
                'Foreign, missing or duplicate current model prohibited.')
        bindings = []
        for model, info in windows:
            require(type(info) is dict and type(info.get('hwnd')) is int
                    and 0 < info['hwnd'] < 2**63,
                    'Strict original current HWND required.')
            token = self.read('window_identity', adapter.identity, model)
            require(sum(token == other for other in tokens) == 1,
                    'Window must belong to a raw normally returned probe birth.')
            bindings.append((token, info['hwnd']))
        require(len({hwnd for _, hwnd in bindings}) == len(bindings)
                and all(sum(token == other for other, _ in bindings) == 1 for token in tokens),
                'Unique complete original window association required.')
        for token, hwnd in self.birth_bindings:
            require(sum(token == other and hwnd == handle for other, handle in bindings) == 1,
                    'Original birth window identity must remain current.')
        for token, hwnd in bindings:
            if not any(token == old for old, _ in self.birth_bindings):
                self.birth_bindings.append((token, hwnd))
        self.watch.admit(births)
        active = self.read('active', getattr, self.app, 'ActiveDoc')
        require((not tokens and active is None) or (tokens and active is not None
                and sum(self.read('active_identity', adapter.identity, active) == token
                        for token in tokens) == 1), 'Active document must be an original current birth.')
        closing = self.watch.poll()
        require(closing[0] == event[0] and closing[1][:len(event[1])] == event[1],
                'Original application/earlier-part events raced owner roster admission.')
        return True


class NativeWatch:
    """Original application and part event sinks, established on the owning STA."""
    REQUIRED = frozenset(('OnFileNewNotify2', 'OnFileOpenPostNotify', 'OnFileCloseNotify', 'OnDestroyNotify'))
    EVENTS = REQUIRED | frozenset(('OnActiveDocChangeNotify', 'OnDocumentLoadNotify2',
                                  'OnFileCloseNotify', 'OnActiveModelDocChangeNotify'))

    def __init__(self, adapter, pythoncom, wrap):
        self.adapter, self.pythoncom, self.wrap = adapter, pythoncom, wrap
        self.thread_id = threading.get_ident()
        self.sequence = 0
        self.alive = True
        self.parts = []
        base = adapter._module.DSldWorksEvents
        registered = set(base._dispid_to_func_.values()) & self.EVENTS
        require(self.REQUIRED <= registered, 'Registered native application events required.')

        def handler(name):
            def notify(sink, *unused):
                self.sequence += 1
                if name == 'OnDestroyNotify':
                    self.alive = False
                return 0
            return notify
        cls = type('B3SetupApplicationSink', (base,), {name: handler(name) for name in registered})
        self.sink = cls(adapter._sw)

    def admit(self, births):
        require(threading.get_ident() == self.thread_id, 'Original event STA required.')
        for label, raw in births:
            if not any(label == old for old, _ in self.parts):
                model = self.wrap(raw, 'IModelDoc2')
                self.parts.append((label, self.adapter.watch_part(model)))

    def poll(self):
        require(threading.get_ident() == self.thread_id, 'Original event STA required.')
        require(self.alive and self.sink is not None, 'Original application event source must remain live.')
        require(not self.pythoncom.PumpWaitingMessages(), 'Native owner received WM_QUIT.')
        return self.sequence, tuple((label, watch.poll()) for label, watch in self.parts)


def write_json(path, data):
    temporary = path.with_suffix('.pending')
    with temporary.open('w', encoding='utf8') as stream:
        json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def validate_maintenance_request(command, report):
    require(type(command) is dict and set(command) == {'operation', 'owner_pid', 'request_token'}
            and command['operation'] == 'close_owned_and_restore_baseline'
            and type(command['owner_pid']) is int and command['owner_pid'] == os.getpid()
            and type(command['request_token']) is str
            and command['request_token'] == report['maintenance_request_token'],
            'Exact one-shot private command for this original live owner required.')
    require(report['phase'] == 'probe_complete_guard_held' and report['probe_passed'] is True
            and report['synchronous_setup_returned'] is True and report['native_calls_live'] is False,
            'Failed, pending or incomplete setup cannot authorize maintenance.')


def maintain_original_owner(owner, wrap, preferences, recorder, report, persist):
    """Same original STA only; never reconstruct custody after owner termination."""
    from verifier_dimension_diagnostics import assert_non_stl_preferences
    setup, adapter, app = owner.receipt, owner.adapter, owner.app
    require(report.get('maintenance_attempted', False) is False
            and report.get('maintenance_pending') is None
            and report.get('maintenance_journal_lost', False) is False,
            'One fresh maintenance attempt only; pending/journal-loss calls cannot be retried.')
    report['maintenance_attempted'] = True
    require(setup.setup_complete is True and setup.halted is False and setup.journal_lost is False
            and setup.pending_step is None and setup.guard_acquired is True and setup.guard_returned is True
            and setup.initial.complete is True and setup.initial.halted is False
            and setup.initial.pending_read is None and setup.initial.baseline is setup.baseline
            and setup.raw_returns == [('setup:own_guard', None)],
            'Original normally acknowledged initial receipt/guard and complete setup required.')
    require(all(fixture.setup_complete is True and fixture.halted is False
                and fixture.pending_step is None and fixture.journal_lost is False
                for fixture in (setup.part, setup.cylinder)),
            'Both original completed acknowledged fixtures required before any maintenance call.')
    require(all(item.complete is True and item.halted is False and item.pending_read is None
                for item in (*setup.admissions, *setup.templates, *setup.anchor_receipts.values())),
            'All original setup admissions and topology reads must have returned normally.')
    require(len(setup.admissions) == 2 and len(setup.templates) == 3
            and set(setup.anchor_receipts) == {'Основная деталь', 'Сосед'},
            'Complete original part/cylinder admission and topology inventory required.')
    require(owner.pending_read is None and owner.halted is False, 'Pending original owner read forbids maintenance.')
    owner.safe(setup)
    births = owner.births()
    require(len(births) == 3 and len(setup.birth_windows) == 3,
            'Exact three original normally created births and before-naming windows required.')
    held = []
    for label, raw in births:
        model = wrap(raw, 'IModelDoc2')
        token = owner.read('maintenance_raw_canonical', adapter.identity, raw)
        require(owner.read('maintenance_typed_canonical', adapter.identity, model) == token,
                'Typed maintenance handle must be the actual original raw birth.')
        matches = [(anchor, hwnd) for anchor, hwnd in setup.birth_windows if anchor.canonical == token]
        require(len(matches) == 1 and owner.read('original_birth_anchor', adapter.identity,
                matches[0][0].handle) == token,
                'Exact before-naming original typed document/window receipt required.')
        require((token, matches[0][1]) in owner.birth_bindings,
                'Current window must still be the original normally returned birth window.')
        held.append((label, model, token, matches[0][1]))

    def closed_capture():
        owner.safe(setup)
        event = owner.watch.poll()
        result = []
        for label, model, token, hwnd in held:
            require(owner.read('maintenance_document_identity', adapter.identity, model) == token,
                    'Original incarnation changed before maintenance.')
            require(owner.read('maintenance_unsaved', model.GetPathName) == ''
                    and owner.read('maintenance_part', model.GetType) == 1,
                    'Only original unsaved controlled parts may be discarded.')
            context = owner.read('maintenance_closed_context', adapter.native_close_model_context, model)
            mode = context['mode']
            require(context['dependencies'] == [] and mode['editing_sketch'] is False
                    and mode['editing_component'] is False and mode['view_only'] is False
                    and type(mode['read_only_state']) is int and mode['read_only_state'] == 0
                    and type(mode['blocking_state']) is int and mode['blocking_state'] in (0, 2),
                    'Independent dependency-free closed writable native modes required.')
            manager = wrap(owner.read('maintenance_sketch_manager', getattr, model, 'SketchManager'), 'ISketchManager')
            require(owner.read('maintenance_add_to_db', getattr, manager, 'AddToDB') is False
                    and owner.read('maintenance_active_sketch', getattr, manager, 'ActiveSketch') is None,
                    'No active sketch or pending owned sketch database mode allowed.')
            title = owner.read('maintenance_current_title', model.GetTitle)
            require(type(title) is str and title.strip(), 'Strict current close routing title required.')
            result.append((label, token, hwnd, title, context))
        require(owner.read('maintenance_application_context', adapter.native_close_application_context) == setup.baseline.context,
                'Original application context must remain unchanged before closing.')
        assert_non_stl_preferences(preferences, setup.baseline.preferences, report, 'before_maintenance_preferences')
        require(owner.watch.poll() == event, 'Native event raced closed-state maintenance capture.')
        return result
    original = closed_capture()
    require(closed_capture() == original and len({row[3] for row in original}) == 3,
            'Two stable closed-state captures and unique current routing titles required.')
    # Close event sinks on their original STA only AFTER all proof and before
    # retiring originals. No getter of a retired model is made below.
    for _, watch in owner.watch.parts:
        watch.close()
    owner.watch.parts.clear()
    remaining = [(token, hwnd) for _, _, token, hwnd in held]

    def roster():
        require(owner.thread_id == threading.get_ident() and owner.process_id == os.getpid()
                and adapter._sw is app and owner.read('maintenance_original_app', adapter.identity, app) == owner.canonical
                and owner.read('maintenance_guard', getattr, app, 'CommandInProgress') is True,
                'Exact original owner/application/held guard required during retirement.')
        models = owner.read('maintenance_remaining_models', adapter.documents)
        windows = owner.read('maintenance_remaining_windows', adapter.native_close_windows)
        require(type(models) in (tuple, list) and type(windows) in (tuple, list)
                and len(models) == len(windows) == len(remaining), 'Complete original survivor roster required.')
        tokens = [owner.read('maintenance_survivor', adapter.identity, model) for model in models]
        require(all(sum(token == current for current in tokens) == 1 for token, _ in remaining),
                'Foreign/missing original survivor prohibits further maintenance.')
        bindings = [(owner.read('maintenance_survivor_window', adapter.identity, model), info['hwnd'])
                    for model, info in windows]
        require(len(bindings) == len(remaining) and all(sum(token == current and hwnd == handle
                    for current, handle in bindings) == 1 for token, hwnd in remaining),
                'Each remaining exact original HWND must still identify its original birth.')

    def call(label, function, *args, recheck=None):
        # Each step takes a new opening boundary: normal notifications from
        # the preceding acknowledged close are already included here. A
        # change during pending journal I/O or current-state rechecks cannot
        # authorize a write merely because an ABA roster looks equal again.
        event = owner.watch.poll()
        step_index = report.get('maintenance_step_count', 0)+1
        report['maintenance_step_count'] = step_index
        report.update(maintenance_pending=label, maintenance_journal_lost=True)
        persist()
        recorder(setup.part_request_id, label, 'pending', {'maintenance': True, 'step_index': step_index})
        roster()
        if recheck is not None:
            recheck()
        report.update(maintenance_journal_lost=False, native_calls_live=True)
        persist()
        try:
            require(owner.watch.poll() == event,
                    'Native application event raced pending maintenance journal/current-state recheck; no write allowed.')
            value = function(*args)
            owner.returned_reads.append((label, value))
        finally:
            report['native_calls_live'] = False
            persist()
        report['maintenance_journal_lost'] = True
        recorder(setup.part_request_id, label, 'returned', {'normally_returned': True, 'maintenance': True,
                                                         'step_index': step_index})
        report.update(maintenance_pending=None, maintenance_journal_lost=False)
        persist()

    for _, token, hwnd, title, context in reversed(original):
        roster()
        model = next(model for _, model, current, _ in held if current == token)
        def recheck():
            require(owner.read('close_current_original', adapter.identity, model) == token
                    and owner.read('close_current_title', model.GetTitle) == title
                    and owner.read('close_current_unsaved', model.GetPathName) == ''
                    and owner.read('close_current_modes', adapter.native_close_model_context, model) == context,
                    'Exact own target/title/closed modes must survive pending journal I/O.')
        call('maintenance:close_original', app.CloseDoc, title, recheck=recheck)
        remaining = [(old, handle) for old, handle in remaining if old != token]
        roster()
    require(owner.read('maintenance_empty_active', getattr, app, 'ActiveDoc') is None
            and owner.read('maintenance_final_context', adapter.native_close_application_context) == setup.baseline.context,
            'Original empty application baseline context required before own guard restore.')
    assert_non_stl_preferences(preferences, setup.baseline.preferences, report, 'restored_preferences')
    call('maintenance:restore_own_guard', setattr, app, 'CommandInProgress', False)
    require(owner.read('maintenance_restored_guard', getattr, app, 'CommandInProgress') is False
            and owner.read('maintenance_final_documents', adapter.documents) == []
            and owner.read('maintenance_final_windows', adapter.native_close_windows) == []
            and owner.read('maintenance_final_active', getattr, app, 'ActiveDoc') is None
            and owner.read('maintenance_restored_context', adapter.native_close_application_context) == setup.baseline.context,
            'Normal guard return and complete empty original baseline must be proven.')
    assert_non_stl_preferences(preferences, setup.baseline.preferences, report, 'final_preferences')
    report.update(phase='terminal', baseline_restored=True, own_cleanup_verified=True,
                  retained_process=False, deferred_stl_verified=False)
    persist()


def run_native(state, template, report):
    """Single original owner. Explicit root must inspect this driver before launch."""
    import pythoncom
    from solidworks_mcp import binding
    from solidworks_mcp.cad_documents import SolidWorksDocuments
    from verifier_b3_part_setup import PartSetupReceipt, prepare_part_setup
    from verify_export_operations import application_preferences

    report_path = state / 'probe-report.json'
    receipt = PartSetupReceipt('b3-part-' + uuid.uuid4().hex, 'b3-cylinder-' + uuid.uuid4().hex)
    owner = None
    recorder = None
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    try:
        adapter = SolidWorksDocuments()
        wrap = lambda raw, interface: binding.wrap(raw, getattr(adapter._module, interface))
        watch = NativeWatch(adapter, pythoncom, wrap)
        owner = Owner(adapter, receipt, watch, app=adapter._sw, canonical=adapter.identity(adapter._sw))
        report.update(owner_pid=os.getpid(), owner_thread=threading.get_ident())
        with (state / 'native-ledger.jsonl').open('x', encoding='utf8') as journal:
            def recorder(request_id, label, phase, data):
                require(phase in ('pending', 'returned'), 'Only paired private native journal phases allowed.')
                journal.write(json.dumps(dict(request_id=request_id, label=label, phase=phase, data=data),
                                         ensure_ascii=False, allow_nan=False) + '\n')
                journal.flush()
                os.fsync(journal.fileno())
                report.update(last_journal=dict(request_id=request_id, label=label, phase=phase),
                              ledger_native_call_pending=phase == 'pending')
                write_json(report_path, report)

            report.update(phase='part_setup', native_calls_live=True)
            write_json(report_path, report)
            try:
                prepare_part_setup(receipt=receipt, adapter=adapter, template=str(template),
                    title_suffix=state.name, wrap=wrap, assert_safe=owner.safe, recorder=recorder,
                    watch_poll=watch.poll, reference_watch=watch,
                    preference_reader=lambda: application_preferences(adapter._sw))
            finally:
                # Synchronous Python stack returned, not proof that an exception
                # cancelled COM or acknowledged a pending native ledger entry.
                report.update(native_calls_live=False, synchronous_setup_returned=True)
                write_json(report_path, report)
        require(receipt.setup_complete is True and not receipt.halted
                and receipt.phase == 'setup_complete_guard_held', 'Normal complete setup required.')
        owner.safe(receipt)
        report.update(phase='probe_complete_guard_held', probe_passed=True,
                      original_birth_count=len(owner.birth_bindings),
                      anchor_counts={role: len(items) for role, items in receipt.original_objects.items()})
    except BaseException as error:
        report.update(phase='failed_owner_held', error_type=type(error).__name__, error=str(error))
    finally:
        report.update(setup_pending=receipt.pending_step, setup_journal_lost=receipt.journal_lost,
                      guard_returned=receipt.guard_returned, guard_acquired=receipt.guard_acquired,
                      fixture_pending={name: fixture.pending_step for name, fixture in
                          (('part', receipt.part), ('cylinder', receipt.cylinder)) if fixture is not None},
                      owner_pending_read=owner.pending_read if owner is not None else None,
                      maintenance_gate=MAINTENANCE_GATE, retained_process=True)
        if receipt.baseline is not None:
            report.update(original_application_context=receipt.baseline.context,
                          original_preferences=receipt.baseline.preferences)
        if owner is not None:
            report.update(owner_read_count=len(owner.returned_reads),
                          event_watch_parts=[label for label, _ in owner.watch.parts])
        if report['phase'] == 'probe_complete_guard_held':
            report.update(maintenance_request_token=uuid.uuid4().hex,
                          maintenance_request_file=str(state/'maintenance-request.json'),
                          maintenance_original_custody=[dict(role=label, ordinal=index+1,
                              hwnd=next(hwnd for token, hwnd in owner.birth_bindings
                                        if token == adapter.identity(raw)),
                              source='original_normally_returned_raw_NewDocument',
                              typed_interface='IModelDoc2', original_sta_retained=True)
                              for index, (label, raw) in enumerate(owner.births())])
        write_json(report_path, report)
    print(json.dumps(dict(phase=report['phase'], probe_passed=report['probe_passed'],
                         accepted=False, native_acceptance=False, retained_process=True)), flush=True)
    # One explicit root command to the LIVE ORIGINAL owner, not a new child or
    # resumed setup. Failure is permanently held; its command is never admitted.
    command_file = state/'maintenance-request.json'
    maintenance_consumed = False
    while True:
        pythoncom.PumpWaitingMessages()
        if not maintenance_consumed and command_file.is_file():
            maintenance_consumed = True
            try:
                validate_maintenance_request(json.loads(command_file.read_text(encoding='utf8')), report)
                require(owner is not None and recorder is not None, 'Original initialized maintenance owner required.')
                # Original setup journal remains immutable. Maintenance uses a
                # separate exclusive private paired recorder on this same STA.
                with (state/'maintenance-ledger.jsonl').open('x', encoding='utf8') as journal:
                    def maintenance_recorder(request_id, label, phase, data):
                        journal.write(json.dumps(dict(request_id=request_id, label=label, phase=phase, data=data),
                                                 ensure_ascii=False, allow_nan=False)+'\n')
                        journal.flush(); os.fsync(journal.fileno())
                    maintain_original_owner(owner, wrap, lambda: application_preferences(adapter._sw),
                        maintenance_recorder, report, lambda: write_json(report_path, report))
                owner.watch.sink.close()
                adapter.close()
                pythoncom.CoUninitialize()
                print(json.dumps(dict(phase='terminal', own_cleanup_verified=True, accepted=False)), flush=True)
                return
            except BaseException as error:
                report.update(phase='maintenance_failed_owner_held', maintenance_error_type=type(error).__name__,
                              maintenance_error=str(error), retained_process=True)
                write_json(report_path, report)
        time.sleep(.5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--state-dir', required=True, type=Path)
    parser.add_argument('--part-template', required=True, type=Path)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--metadata-report', required=True, type=Path)
    args = parser.parse_args(argv)
    state, template, report = preflight(args)
    state.mkdir(parents=True, exist_ok=False)
    write_json(state / 'probe-report.json', report)
    run_native(state, template, report)


if __name__ == '__main__':
    main()
