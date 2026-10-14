"""Source-only B3 orchestration over reused API-shaped fixtures; no CAD/COM."""
from pathlib import Path
import sys
from threading import Thread, get_ident
from types import SimpleNamespace as NS

import pytest

import test_b3_part_fixture as part_fake
import test_b3_cylinder_fixture as cylinder_fake

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_part_setup as setup
    from verify_export_operations import PREFS
finally:
    sys.path.remove(scripts)


XY = (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.)
X_NORMAL = (0., 1., 0., 0., 0., 1., 1., 0., 0., 0., 0., 0., 1., 0., 0., 0.)


class Application:
    def __init__(self, owner):
        self.owner = owner
        self.canonical = -100
        self._guard = False
        self._active = None

    @property
    def CommandInProgress(self):
        self.owner.check('guard_read')
        return self._guard

    @CommandInProgress.setter
    def CommandInProgress(self, value):
        x = self.owner
        x.check('guard_set')
        assert value is True
        assert x.receipt.pending_step == 'own_guard'
        assert x.events[-1][1:3] == ('setup:own_guard', 'pending')
        if x.setter_unknown:
            raise RuntimeError('guard setter outcome unknown')
        if not x.setter_no_effect:
            self._guard = value
        x.setters.append(value)

    @property
    def ActiveDoc(self):
        self.owner.check('active_read')
        return self._active

    def NewDocument(self, *args):
        x = self.owner
        x.check('NewDocument')
        world = x.cylinder if x.receipt.phase == 'cylinder_fixture' else x.part
        model = world.new_document(*args)
        self._active = model
        original_title = model.SetTitle2

        def title(value):
            x.check('SetTitle2')
            matching = [(anchor, hwnd) for anchor, hwnd in x.receipt.birth_windows if anchor.handle is model]
            assert len(matching) == 1
            assert matching[0][1] == 101 + x.models.index(model)
            assert x.receipt.templates[-1].complete
            return original_title(value)

        model.SetTitle2 = title
        return model

    def GetModeler(self):
        self.owner.check('GetModeler')
        return self.owner.part.modeler


class Harness:
    """Glue only: geometry creation remains in the existing fixture Worlds."""
    def __init__(self):
        self.receipt = setup.PartSetupReceipt('original-part-request', 'original-cylinder-request')
        self.external = self.receipt
        self.part, self.cylinder = part_fake.World(), cylinder_fake.World()
        self.cylinder.next_token = 100000
        self.template = self.part.template
        self.application = Application(self)
        self.safe = True
        self.admissions = 0
        self.log, self.events, self.setters, self.pid_objects = [], [], [], {}
        self.failure = None
        self.setter_unknown = False
        self.setter_no_effect = False
        self.failure_log_length = None
        self.event = 0
        self.read_failure = None
        self.context = dict(user_control=True, visible=True, current_directory='private_source_test', search_folders='')
        values = {'String': '', 'Toggle': False, 'Integer': 0, 'Double': 0.}
        self.prefs = {name: values[kind] for name, (kind, _) in PREFS.items()}
        self.adapter = NS(_sw=self.application, identity=self.identity, documents=self.documents,
            native_close_windows=self.windows, native_close_application_context=self.application_context,
            snapshot=self.snapshot, native_close_model_context=self.model_context,
            features=self.features, reference_plane_transform=self.plane_frame,
            persistent_id=self.persistent_id, resolve_persistent_id=self.resolve)
        self.watch = NS(poll=self.poll)

    @property
    def models(self):
        return [*self.part.models, *self.cylinder.models]

    def check(self, operation):
        assert self.receipt is self.external
        assert self.admissions > 0 and self.safe
        assert self.receipt.thread_id == get_ident()
        assert not self.receipt.halted and not self.receipt.journal_lost
        self.log.append(operation)
        if self.read_failure == operation:
            raise RuntimeError('artificial read outcome unknown: ' + operation)

    def assert_safe(self, receipt):
        assert receipt is self.external
        self.admissions += 1
        return self.safe and self.adapter._sw is self.application

    def identity(self, obj):
        self.check('identity')
        return obj.canonical

    def documents(self):
        self.check('documents')
        return self.models

    def windows(self):
        self.check('windows')
        return [(model, dict(hwnd=101 + i)) for i, model in enumerate(self.models)]

    def application_context(self):
        self.check('application_context')
        return dict(self.context)

    def preferences(self):
        self.check('preferences')
        return dict(self.prefs)

    def poll(self):
        self.check('poll')
        return self.event

    def snapshot(self, model):
        self.check('snapshot')
        return dict(path=model.GetPathName(), document_type='part', needs_save=bool(model.bodies),
                    configurations=list(model.GetConfigurationNames()), active_configuration=model.cfg.Name)

    def model_context(self, model):
        self.check('model_context')
        return dict(dependencies=[], mode=dict(editing_sketch=False, editing_component=False,
                    view_only=False, read_only_state=0, blocking_state=0))

    def features(self, model):
        self.check('features')
        return tuple(model.features)

    def plane_frame(self, feature):
        self.check('plane_frame')
        return (XY, self.cylinder.transform, X_NORMAL)[feature.model.features.index(feature)]

    def wrap(self, raw, interface):
        self.check('wrap')
        return raw

    def persistent_id(self, model, obj):
        self.check('persistent_id')
        assert model in self.part.models
        pid = obj.canonical.to_bytes(8, 'little')
        self.pid_objects[pid] = obj
        return pid

    def resolve(self, model, pid, kind):
        self.check('resolve')
        assert model in self.part.models and kind in ('body', 'face', 'edge')
        return self.pid_objects[pid]

    def recorder(self, request_id, label, phase, data):
        assert self.receipt is self.external and self.receipt.thread_id == get_ident()
        assert request_id in (self.receipt.part_request_id, self.receipt.cylinder_request_id)
        if label == 'setup:own_guard':
            assert request_id == self.receipt.part_request_id
            assert self.receipt.pending_step == 'own_guard' and self.receipt.journal_lost
            if phase == 'returned':
                assert self.receipt.raw_returns == [('setup:own_guard', None)]
                assert self.receipt.guard_returned and not self.receipt.guard_acquired
        else:
            fixture = self.receipt.cylinder if request_id == self.receipt.cylinder_request_id else self.receipt.part
            assert fixture is not None and fixture.request_id == request_id
            assert fixture.thread_id == self.receipt.thread_id
            assert fixture.pending_step == label and fixture.journal_lost
            if phase == 'returned':
                assert fixture.native_returns[-1][1] == label
        self.events.append((request_id, label, phase, dict(data)))
        if self.failure == (label, phase):
            self.failure_log_length = len(self.log)
            raise RuntimeError('durable ledger failed')

    def run(self, **overrides):
        args = dict(receipt=self.receipt, adapter=self.adapter, template=str(self.template),
            title_suffix='source_setup', wrap=self.wrap, assert_safe=self.assert_safe,
            recorder=self.recorder, watch_poll=self.poll, reference_watch=self.watch,
            preference_reader=self.preferences)
        args.update(overrides)
        return setup.prepare_part_setup(**args)


@pytest.fixture
def harness(monkeypatch):
    x = Harness()
    monkeypatch.setattr(Path, 'is_file', lambda path: path == x.template)
    original_body = part_fake.Body.__init__

    def body_init(body, world, bounds, kind):
        original_body(body, world, bounds, kind)
        # Extend API shape for topology reads, keeping the actual created bodies.
        for face in body.faces:
            face.canonical = world.next_token
            world.next_token += 1
        body.edges = []
        for _ in range(12 if kind == 0 else 4):
            member = part_fake.Native(world)
            member.GetBody = lambda body=body: body
            body.edges.append(member)

    monkeypatch.setattr(part_fake.Body, '__init__', body_init)
    monkeypatch.setattr(part_fake.Body, 'IsMeshBody', lambda body: False, raising=False)
    monkeypatch.setattr(part_fake.Body, 'GetFaces', lambda body: body.faces, raising=False)
    monkeypatch.setattr(part_fake.Body, 'GetEdges', lambda body: body.edges, raising=False)
    monkeypatch.setattr(part_fake.Body, 'GetFaceCount', lambda body: len(body.faces), raising=False)
    monkeypatch.setattr(part_fake.Body, 'GetEdgeCount', lambda body: len(body.edges), raising=False)
    monkeypatch.setattr(part_fake.Model, 'GetUpdateStamp', lambda model: 17, raising=False)
    return x


def assert_held_no_authority(receipt):
    assert receipt.setup_complete is False
    assert receipt.sdk_ready is receipt.accepted is receipt.native_acceptance is receipt.cleanup_authorized is False


def assert_retry_blocked(x):
    before = len(x.log), len(x.events), len(x.models), tuple(x.setters), x.admissions
    with pytest.raises(ValueError, match='Fresh'):
        x.run()
    assert before == (len(x.log), len(x.events), len(x.models), tuple(x.setters), x.admissions)


@pytest.mark.parametrize('frame', [cylinder_fake.POSITIVE_FRAME, cylinder_fake.NEGATIVE_FRAME])
def test_actual_empty_baseline_admissions_part_cylinder_and_original_topology(harness, frame):
    x = harness
    x.cylinder.transform = frame
    result = x.run()
    assert result is x.external and result.thread_id == get_ident()
    assert result.initial.complete and result.initial.baseline is result.baseline
    assert result.initial.baseline.application is x.application
    assert [raw for label, raw in result.initial.returned_reads if label == 'initial_documents'] == [[], []]
    assert [raw for label, raw in result.initial.returned_reads if label == 'initial_windows'] == [[], []]
    assert x.setters == [True] and x.application._guard is True
    assert result.raw_returns == [('setup:own_guard', None)]
    assert result.guard_returned and result.guard_acquired and result.setup_complete and result.phase == 'setup_complete_guard_held'
    assert not result.halted and not result.journal_lost and result.pending_step is None
    assert len(x.part.models) == 2 and len(x.cylinder.models) == 1
    assert len(result.admissions) == 2 and all(r.complete for r in result.admissions)
    assert len(result.templates) == 3 and all(r.complete for r in result.templates)
    assert [anchor.handle for anchor, _ in result.birth_windows] == x.models
    assert [hwnd for _, hwnd in result.birth_windows] == [101, 102, 103]
    assert tuple(result.anchor_receipts) == tuple(result.original_objects) == ('Основная деталь', 'Сосед')
    for role, count in [('Основная деталь', 44), ('Сосед', 19)]:
        receipt = result.anchor_receipts[role]
        anchors = result.original_objects[role]
        assert receipt.complete and len(anchors) == count
        assert all(a is b for a, b in zip(anchors, receipt.anchors))
        assert all(x.pid_objects[a.persistent_id] is a.handle for a in anchors)
        roots = x.part.models[role == 'Сосед'].bodies
        expected = [obj for body in roots for obj in [body, *body.faces, *body.edges]]
        assert {id(a.handle) for a in anchors} == {id(obj) for obj in expected}
    for fixture, worlds, labels in [
        (result.part, x.part.models, ('Основная деталь:new_document', 'Сосед:new_document')),
        (result.cylinder, x.cylinder.models, ('cylinder:new_document',)),
    ]:
        assert fixture.thread_id == result.thread_id and fixture.setup_complete
        assert all(next(raw for _, step, raw in fixture.native_returns if step == label) is model
                   for label, model in zip(labels, worlds))
        events = [e for e in x.events if e[0] == fixture.request_id and e[1] != 'setup:own_guard']
        assert len(events) == 2 * len(fixture.native_returns)
        assert all(pending[1] == returned[1] and (pending[2], returned[2]) == ('pending', 'returned')
                   for pending, returned in zip(events[::2], events[1::2]))
    assert result.sdk_ready is result.accepted is result.native_acceptance is result.cleanup_authorized is False
    assert all(r.accepted is r.native_acceptance is r.cleanup_authorized is False
               for r in [result.initial, *result.admissions, *result.templates, *result.anchor_receipts.values(), result.part, result.cylinder])
    assert result.remaining_gates[0:2] == ('whole_session_baseline', 'original_guard_handoff')
    assert_retry_blocked(x)


@pytest.mark.parametrize('field,value', [
    ('part_request_id', ''), ('part_request_id', '  '), ('cylinder_request_id', 1),
    ('cylinder_request_id', 'original-part-request'), ('thread_id', -1),
    ('attempted', True), ('halted', True), ('pending_step', 'unknown'),
    ('journal_lost', True), ('guard_returned', True), ('guard_acquired', True), ('setup_complete', True), ('sdk_ready', True),
    ('accepted', True), ('native_acceptance', True), ('cleanup_authorized', True),
    ('raw_returns', [('previous', None)]),
    ('phase', 'previous'), ('initial', object()), ('baseline', object()),
    ('part', object()), ('cylinder', object()), ('admissions', [object()]),
    ('templates', [object()]), ('anchor_receipts', {'previous': object()}),
    ('original_objects', {'previous': (object(),)}), ('birth_windows', [(object(), 101)]),
])
def test_original_fresh_receipt_and_distinct_explicit_ids_preflight(harness, field, value):
    x = harness
    setattr(x.receipt, field, value)
    with pytest.raises(ValueError):
        x.run()
    assert not x.log and not x.events and not x.models and not x.setters
    assert getattr(x.receipt, field) is value


@pytest.mark.parametrize('callback', ['wrap', 'assert_safe', 'recorder', 'watch_poll', 'preference_reader', 'reference_watch'])
def test_explicit_owner_read_and_ledger_callbacks_required(harness, callback):
    value = NS(poll=None) if callback == 'reference_watch' else None
    with pytest.raises(ValueError):
        harness.run(**{callback: value})
    assert not harness.log and not harness.events and not harness.models


def test_foreign_sta_cannot_start_any_read_or_writer(harness):
    errors = []
    def foreign():
        try:
            harness.run()
        except BaseException as error:
            errors.append(error)
    thread = Thread(target=foreign)
    thread.start()
    thread.join()
    assert len(errors) == 1 and isinstance(errors[0], ValueError)
    assert not harness.log and not harness.events and not harness.models


@pytest.mark.parametrize('dirty', ['guard', 'active', 'models', 'windows'])
def test_initial_census_must_prove_idle_empty_application_before_writer(harness, dirty):
    x = harness
    if dirty == 'guard':
        x.application._guard = True
    elif dirty == 'active':
        x.application._active = NS(canonical=42)
    elif dirty == 'models':
        x.part.models.append(NS(canonical=42))
    else:
        x.adapter.native_close_windows = lambda: [(NS(canonical=42), dict(hwnd=999))]
    with pytest.raises(ValueError):
        x.run()
    assert x.receipt.halted and x.receipt.initial.halted
    assert not x.events and not x.setters and x.receipt.part is None
    assert_held_no_authority(x.receipt)
    assert_retry_blocked(x)


@pytest.mark.parametrize('label', [
    'setup:own_guard', 'application:admission', 'Основная деталь:new_document',
    'Основная деталь:empty_admission', 'Первый:extrude', 'surface:import',
    'Сосед:new_document', 'cylinder:new_document', 'cylinder:empty_admission',
    'cylinder:circle', 'cylinder:extrude',
])
@pytest.mark.parametrize('phase', ['pending', 'returned'])
def test_ledger_failure_retains_original_raw_returns_and_stops_all_followups(harness, label, phase):
    x = harness
    x.failure = label, phase
    with pytest.raises(RuntimeError, match='ledger'):
        x.run()
    r = x.receipt
    assert r.halted and x.events[-1][1:3] == (label, phase)
    assert len(x.log) == x.failure_log_length
    if label == 'setup:own_guard':
        assert r.pending_step == 'own_guard' and r.journal_lost
        assert r.raw_returns == ([('setup:own_guard', None)] if phase == 'returned' else [])
        assert x.setters == ([True] if phase == 'returned' else [])
        assert r.guard_returned == (phase == 'returned') and not r.guard_acquired
        assert r.part is None and not x.models
    else:
        request_id = x.events[-1][0]
        fixture = r.cylinder if request_id == r.cylinder_request_id else r.part
        assert fixture.halted and fixture.journal_lost and fixture.pending_step == label
        retained = [raw for _, step, raw in fixture.native_returns if step == label]
        assert bool(retained) == (phase == 'returned')
        if label.endswith('new_document') and retained:
            assert retained[0] is x.models[-1]
        assert x.application._guard is True and r.raw_returns == [('setup:own_guard', None)]
    assert_held_no_authority(r)
    assert_retry_blocked(x)


def test_normal_guard_setter_return_without_effect_cannot_claim_acquisition(harness):
    x = harness
    x.setter_no_effect = True
    with pytest.raises(ValueError, match='own guard readback'):
        x.run()
    r = x.receipt
    assert r.halted and r.guard_returned and not r.guard_acquired
    assert r.raw_returns == [('setup:own_guard', None)]
    assert not r.journal_lost and r.pending_step is None
    assert x.application._guard is False and x.setters == [True]
    assert r.part is None and not x.models
    assert_held_no_authority(r)
    assert_retry_blocked(x)


@pytest.mark.parametrize('change', ['owner', 'canonical', 'guard', 'application'])
def test_pending_guard_ledger_io_cannot_bypass_original_owner_idle_readback(harness, change):
    x = harness
    original = x.recorder
    def recorder(*args):
        original(*args)
        if args[1:3] == ('setup:own_guard', 'pending'):
            if change == 'owner':
                x.safe = False
            elif change == 'canonical':
                x.application.canonical = -101
            elif change == 'guard':
                x.application._guard = True
            else:
                x.adapter._sw = NS(canonical=x.application.canonical, CommandInProgress=False)
    with pytest.raises(ValueError, match='after pending journal'):
        x.run(recorder=recorder)
    r = x.receipt
    assert r.halted and r.pending_step == 'own_guard' and not r.journal_lost
    assert not r.guard_returned and not r.guard_acquired and r.raw_returns == []
    assert r.part is None and not x.models and not x.setters
    assert_held_no_authority(r)
    assert_retry_blocked(x)


def test_unknown_guard_setter_stays_pending_without_raw_return_or_cleanup(harness):
    x = harness
    x.setter_unknown = True
    with pytest.raises(RuntimeError, match='unknown'):
        x.run()
    r = x.receipt
    assert r.halted and r.pending_step == 'own_guard' and not r.journal_lost
    assert r.raw_returns == [] and not r.guard_acquired and r.part is None
    assert x.events[-1][1:3] == ('setup:own_guard', 'pending')
    assert_held_no_authority(r)
    assert_retry_blocked(x)


@pytest.mark.parametrize('operation', ['documents', 'preferences', 'plane_frame', 'persistent_id', 'resolve'])
def test_read_failure_latches_original_receipts_without_replay(harness, operation):
    x = harness
    x.read_failure = operation
    with pytest.raises(RuntimeError, match='read outcome unknown'):
        x.run()
    assert x.receipt.halted
    if operation in ('documents', 'preferences'):
        assert not x.setters and not x.events
        assert x.receipt.initial.pending_read is not None
    elif operation == 'plane_frame':
        assert len(x.models) == 1 and x.receipt.templates[-1].pending_read == 'native_plane_frame'
        assert not x.part.extrusions and x.models[0].title == 'Деталь'
    else:
        assert len(x.models) == 3 and x.receipt.anchor_receipts['Основная деталь'].pending_read is not None
        assert 'Сосед' not in x.receipt.anchor_receipts
    assert_held_no_authority(x.receipt)
    assert_retry_blocked(x)


@pytest.mark.parametrize('corrupt', ['halted', 'pending', 'journal', 'thread', 'missing_returns', 'replaced_return'])
def test_cylinder_admission_requires_original_completed_acknowledged_part_receipt(harness, monkeypatch, corrupt):
    x = harness
    original = setup.create_part_fixture
    def part(**kwargs):
        result = original(**kwargs)
        if corrupt == 'halted':
            result.halted = True
        elif corrupt == 'pending':
            result.pending_step = 'unknown'
        elif corrupt == 'journal':
            result.journal_lost = True
        elif corrupt == 'thread':
            result.thread_id = -1
        elif corrupt == 'missing_returns':
            result.native_returns.clear()
        else:
            # Replace the acknowledged NewDocument row, retaining its old anchor.
            row = next(i for i, (_, step, _) in enumerate(result.native_returns) if step == 'Основная деталь:new_document')
            index, label, _ = result.native_returns[row]
            result.native_returns[row] = index, label, NS(canonical=-999)
        return result
    monkeypatch.setattr(setup, 'create_part_fixture', part)
    with pytest.raises(ValueError, match='earlier original|earlier model'):
        x.run()
    assert len(x.models) == 2 and not x.cylinder.models
    assert x.receipt.halted and x.application._guard is True
    assert_held_no_authority(x.receipt)
    assert_retry_blocked(x)


@pytest.mark.parametrize('builder', ['create_part_fixture', 'create_cylinder_fixture'])
def test_only_exact_original_builder_receipt_can_complete_the_next_stage(harness, monkeypatch, builder):
    original = getattr(setup, builder)
    def replacement(**kwargs):
        original(**kwargs)
        return setup.PartFixtureReceipt(kwargs['receipt'].request_id, setup_complete=True)
    monkeypatch.setattr(setup, builder, replacement)
    with pytest.raises(ValueError, match='Original completed'):
        harness.run()
    assert harness.receipt.halted and not harness.receipt.anchor_receipts
    assert len(harness.models) == (2 if builder == 'create_part_fixture' else 3)
    assert_held_no_authority(harness.receipt)
    assert_retry_blocked(harness)


def test_root_owner_rejection_blocks_initial_baseline_and_all_writers(harness):
    x = harness
    x.safe = False
    with pytest.raises(ValueError, match='caller admission'):
        x.run()
    assert x.receipt.halted and x.receipt.initial is None
    assert not x.log and not x.events and not x.models and not x.setters
    assert_retry_blocked(x)


def test_owner_loss_after_normal_guard_ack_keeps_held_guard_and_stops_part(harness):
    x = harness
    original = x.recorder
    def recorder(*args):
        original(*args)
        if args[1:3] == ('setup:own_guard', 'returned'):
            x.safe = False
    with pytest.raises(ValueError, match='own guard readback'):
        x.run(recorder=recorder)
    assert x.receipt.halted and x.receipt.guard_returned and not x.receipt.guard_acquired
    assert x.application._guard is True
    assert x.receipt.raw_returns == [('setup:own_guard', None)]
    assert x.receipt.part is None and not x.models
    assert_held_no_authority(x.receipt)
    assert_retry_blocked(x)
