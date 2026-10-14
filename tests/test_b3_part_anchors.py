"""Artificial completed-fixture topology only; no SDK registration or native CAD."""
from copy import copy
from pathlib import Path
import sys
from threading import Thread, get_ident
from types import SimpleNamespace as NS

import pytest

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_part_anchors as anchors_module
    from verifier_b3_part_anchors import PartAnchorReceipt, retain_part_anchors
    from verifier_b3_part_bridge import OriginalPartObject
    from verifier_b3_part_fixture import FixtureAnchor, PartFixtureReceipt
finally:
    sys.path.remove(scripts)


class Native:
    def __init__(self, world, kind):
        self.world, self.kind = world, kind
        self.canonical = world.next_token
        world.next_token += 1
        self.pid = self.canonical.to_bytes(4, 'little')
        world.objects[self.pid] = self

    def call(self, operation):
        self.world.log.append((operation, self))

    @property
    def Name(self):
        raise AssertionError('Topology ownership cannot use names')


class Member(Native):
    def __init__(self, world, kind, body):
        super().__init__(world, kind)
        self.body = body

    def GetBody(self):
        self.call('GetBody')
        return self.body


class Body(Native):
    def __init__(self, world, code):
        super().__init__(world, 'body')
        self.code, self.mesh = code, False
        self.faces = [Member(world, 'face', self) for _ in range(6 if code == 0 else 1)]
        self.edges = [Member(world, 'edge', self) for _ in range(12 if code == 0 else 4)]

    def GetType(self):
        self.call('GetType')
        return self.code

    def IsMeshBody(self):
        self.call('IsMeshBody')
        return self.mesh

    def GetFaces(self):
        self.call('GetFaces')
        return self.faces

    def GetEdges(self):
        self.call('GetEdges')
        return self.edges

    def GetFaceCount(self):
        self.call('GetFaceCount')
        return len(self.faces)

    def GetEdgeCount(self):
        self.call('GetEdgeCount')
        return len(self.edges)


class Model(Native):
    def __init__(self, world, bodies):
        super().__init__(world, 'document')
        self.cfg = NS(canonical=world.next_token, Name='Основная')
        world.next_token += 1
        self.active = self.cfg
        self.bodies, self.stamp, self.dirty = bodies, 17, True
        self.censuses = 0
        self.on_census = lambda count: None

    def GetActiveConfiguration(self):
        self.call('GetActiveConfiguration')
        return self.active

    def GetUpdateStamp(self):
        self.call('GetUpdateStamp')
        return self.stamp

    def GetSaveFlag(self):
        self.call('GetSaveFlag')
        return self.dirty

    def GetBodies2(self, code, visible_only):
        self.call('GetBodies2')
        assert code == -1 and visible_only is False
        self.censuses += 1
        self.on_census(self.censuses)
        # A different order must not change acknowledged fixture ownership.
        return list(reversed(self.bodies))


@pytest.fixture
def world():
    x = NS(next_token=1, objects={}, log=[], event=0, polls=0, guards=0)
    first, second, sheet, neighbor = [Body(x, code) for code in (0, 0, 1, 0)]
    x.main, x.neighbor = Model(x, [first, second, sheet]), Model(x, [neighbor])
    x.fixture = PartFixtureReceipt('artificial-original-fixture', attempted=True, setup_complete=True)
    for role, model in [('Основная деталь', x.main), ('Сосед', x.neighbor)]:
        x.fixture.documents[role] = FixtureAnchor(role, 'document', model, model.canonical)
        key = role + '_Основная'
        x.fixture.configurations[key] = FixtureAnchor(key, 'configuration', model.cfg, model.cfg.canonical)
    for role, body in zip(('Первый', 'Второй', 'Поверхность', 'Сосед'), (first, second, sheet, neighbor)):
        x.fixture.bodies[role] = FixtureAnchor(role, 'body', body, body.canonical)
    x.fixture.anchors = [*x.fixture.documents.values(), *x.fixture.configurations.values(), *x.fixture.bodies.values()]
    x.fixture.native_returns = [('original-acknowledged-fixture', x.main)]
    x.receipt = PartAnchorReceipt()

    def identity(obj):
        x.log.append(('identity', obj))
        return obj.canonical

    def persistent_id(model, obj):
        x.log.append(('persistent_id', obj))
        assert model in (x.main, x.neighbor)
        return obj.pid

    def resolve(model, pid, kind):
        x.log.append(('resolve', (model, pid, kind)))
        obj = x.objects.get(pid)
        assert obj is None or obj.kind == kind
        return obj

    def wrap(raw, interface):
        x.log.append(('wrap', interface))
        assert interface in ('IConfiguration', 'IPartDoc', 'IFace2', 'IEdge', 'IBody2')
        return raw

    def safe(fixture):
        assert fixture is x.fixture
        x.guards += 1
        x.log.append(('safe', fixture))
        return True

    def poll():
        x.log.append(('poll', x.event))
        x.polls += 1
        return x.event

    x.adapter = NS(identity=identity, persistent_id=persistent_id, resolve_persistent_id=resolve)
    x.wrap, x.safe, x.watch = wrap, safe, NS(poll=poll)
    return x


def run(x, role='Основная деталь', **overrides):
    kwargs = dict(receipt=x.receipt, fixture=x.fixture, model_role=role,
                  adapter=x.adapter, wrap=x.wrap, watch=x.watch, assert_safe=x.safe)
    kwargs.update(overrides)
    return retain_part_anchors(**kwargs)


def fixture_snapshot(fixture):
    # Copy containers, keeping exact original handles and anchors rather than cloning them.
    return {key: copy(value) for key, value in vars(fixture).items()}


def assert_no_authority(receipt):
    assert receipt.complete is receipt.accepted is receipt.native_acceptance is receipt.cleanup_authorized is False


@pytest.mark.parametrize('role', ['Основная деталь', 'Сосед'])
def test_complete_original_topology_retained_before_any_sdk_registration(world, role):
    x = world
    before = fixture_snapshot(x.fixture)
    expected_bodies = x.main.bodies if role == 'Основная деталь' else x.neighbor.bodies
    result = run(x, role)
    assert type(result) is tuple and tuple(x.receipt.anchors) == result
    assert len(result) == (44 if role == 'Основная деталь' else 19)
    assert all(type(anchor) is OriginalPartObject for anchor in result)
    expected = [(body, body) for body in expected_bodies]
    expected += [(member, body) for body in expected_bodies for member in [*body.faces, *body.edges]]
    assert {id(anchor.handle) for anchor in result} == {id(obj) for obj, _ in expected}
    for obj, body in expected:
        anchor, = [value for value in result if value.handle is obj]
        assert (anchor.kind, anchor.canonical, anchor.persistent_id, anchor.body_canonical) == (
            obj.kind, obj.canonical, obj.pid, body.canonical)
    assert x.receipt.attempted is x.receipt.complete is True
    assert x.receipt.halted is False and x.receipt.pending_read is None
    assert x.receipt.accepted is x.receipt.native_acceptance is x.receipt.cleanup_authorized is False
    assert vars(x.fixture) == before
    assert x.polls == 2 and x.guards > len(result)
    assert [obj.code for obj in expected_bodies] == ([0, 0, 1] if role == 'Основная деталь' else [0])
    # All API-shaped reads, including wrappers and watchers, must follow the owner gate.
    for index, (operation, _) in enumerate(x.log):
        if operation != 'safe':
            assert index and x.log[index - 1][0] == 'safe'


def test_exact_handle_and_pid_are_retained_before_resolver_is_called(world):
    x = world
    original = x.adapter.resolve_persistent_id
    def resolve(model, pid, kind):
        last = x.receipt.anchors[-1]
        assert last.handle is x.objects[pid]
        assert last.persistent_id is pid and last.kind == kind
        assert_no_authority(x.receipt)
        return original(model, pid, kind)
    x.adapter.resolve_persistent_id = resolve
    run(x)


@pytest.mark.parametrize('fault', ['foreign', 'fewer', 'extra', 'duplicate', 'duplicate_original'])
def test_complete_body_census_cannot_adopt_another_body(world, fault):
    x = world
    if fault == 'foreign': x.main.bodies[0] = x.neighbor.bodies[0]
    elif fault == 'fewer': x.main.bodies.pop()
    elif fault == 'extra': x.main.bodies.append(x.neighbor.bodies[0])
    elif fault == 'duplicate': x.main.bodies[1] = x.main.bodies[0]
    else: x.fixture.bodies['Второй'] = x.fixture.bodies['Первый']
    before = fixture_snapshot(x.fixture)
    with pytest.raises(ValueError): run(x)
    assert x.receipt.halted and not x.receipt.anchors
    assert_no_authority(x.receipt)
    assert vars(x.fixture) == before


@pytest.mark.parametrize('raw', [None, {}, 'body-array'])
def test_body_census_requires_an_explicit_complete_native_array(world, raw):
    x = world
    x.main.GetBodies2 = lambda code, visible_only: raw
    with pytest.raises(ValueError, match='bounded native topology array'): run(x)
    assert x.receipt.halted and not x.receipt.anchors
    assert_no_authority(x.receipt)


def test_generator_body_census_cannot_claim_complete_native_membership(world):
    x = world
    x.main.GetBodies2 = lambda code, visible_only: iter(x.main.bodies)
    with pytest.raises(ValueError, match='bounded native topology array'): run(x)
    assert x.receipt.halted and not x.receipt.anchors


def test_unsupported_model_role_is_rejected_before_owner_or_native_reads(world):
    x = world
    with pytest.raises(ValueError, match='Explicit supported original model role'): run(x, 'Вариант')
    assert x.log == [] and not x.receipt.attempted


@pytest.mark.parametrize('inventory,key', [('documents', 'Основная деталь'),
    ('configurations', 'Основная деталь_Основная'), ('bodies', 'Первый')])
def test_untyped_or_wrong_kind_original_anchor_cannot_supply_custody(world, inventory, key):
    x = world
    table = getattr(x.fixture, inventory)
    anchor = table[key]
    table[key] = FixtureAnchor(anchor.role, 'foreign-kind', anchor.handle, anchor.canonical)
    with pytest.raises(ValueError, match='Typed original custody'): run(x)
    assert x.log == [] and not x.receipt.attempted


@pytest.mark.parametrize('kind', ['body', 'face', 'edge'])
@pytest.mark.parametrize('pid', [b'', None, (), [1, 2], bytearray(b'pid'), 'native-pid', 1])
def test_missing_or_nonbytes_native_pid_grants_no_anchor(world, kind, pid):
    x = world
    body = x.main.bodies[0]
    target = {'body': body, 'face': body.faces[0], 'edge': body.edges[0]}[kind]
    target.pid = pid
    with pytest.raises(ValueError, match='native PID bytes'): run(x)
    assert all(anchor.handle is not target for anchor in x.receipt.anchors)
    assert x.receipt.halted
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('kind', ['body', 'face', 'edge'])
@pytest.mark.parametrize('fault', ['none', 'canonical', 'pid'])
def test_roundtrip_requires_original_canonical_and_exact_pid(world, kind, fault):
    x = world
    body = x.main.bodies[0]
    target = {'body': body, 'face': body.faces[0], 'edge': body.edges[0]}[kind]
    original = x.adapter.resolve_persistent_id
    def resolve(model, pid, expected_kind):
        if pid != target.pid: return original(model, pid, expected_kind)
        if fault == 'none': return None
        return NS(canonical=target.canonical if fault == 'pid' else object(),
                  pid=b'wrong' if fault == 'pid' else target.pid)
    x.adapter.resolve_persistent_id = resolve
    with pytest.raises(ValueError, match='exact current canonical'): run(x)
    assert x.receipt.anchors[-1].handle is target
    assert x.receipt.halted and x.receipt.pending_read is None
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('fault', ['model', 'configuration', 'inactive', 'renamed'])
def test_original_model_and_static_main_configuration_custody(world, fault):
    x = world
    if fault == 'model': x.main.canonical = object()
    elif fault == 'configuration': x.main.cfg.canonical = object()
    elif fault == 'inactive': x.main.active = NS(canonical=object(), Name='Основная')
    else: x.main.cfg.Name = 'Вариант'
    with pytest.raises(ValueError): run(x)
    assert x.receipt.halted and not x.receipt.anchors
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('fault', ['mesh', 'mesh_int', 'unsupported', 'boolean_kind', 'none_faces',
    'none_edges', 'generator_faces', 'mapping_edges', 'oversized_faces', 'oversized_edges',
    'empty_faces', 'empty_edges', 'bad_face_count', 'bad_edge_count', 'boolean_count',
    'duplicate_face', 'duplicate_edge', 'foreign_face_owner', 'foreign_edge_owner', 'missing_owner'])
def test_bounded_brep_arrays_counts_and_native_getbody_owner(world, fault):
    x = world; body = x.main.bodies[0]
    if fault == 'mesh': body.mesh = True
    elif fault == 'mesh_int': body.mesh = 0
    elif fault == 'unsupported': body.code = 2
    elif fault == 'boolean_kind': body.code = False
    elif fault == 'none_faces': body.GetFaces = lambda: None
    elif fault == 'none_edges': body.GetEdges = lambda: None
    elif fault == 'generator_faces': body.GetFaces = lambda: iter(body.faces)
    elif fault == 'mapping_edges': body.GetEdges = lambda: {i: edge for i, edge in enumerate(body.edges)}
    elif fault == 'oversized_faces': body.GetFaces = lambda: body.faces * 7
    elif fault == 'oversized_edges': body.GetEdges = lambda: body.edges * 7
    elif fault == 'empty_faces': body.faces = []
    elif fault == 'empty_edges': body.edges = []
    elif fault == 'bad_face_count': body.GetFaceCount = lambda: len(body.faces) - 1
    elif fault == 'bad_edge_count': body.GetEdgeCount = lambda: len(body.edges) + 1
    elif fault == 'boolean_count': body.GetFaceCount = lambda: True
    elif fault == 'duplicate_face': body.faces[1] = body.faces[0]
    elif fault == 'duplicate_edge': body.edges[1] = body.edges[0]
    elif fault == 'foreign_face_owner': body.faces[0].body = x.main.bodies[1]
    elif fault == 'foreign_edge_owner': body.edges[0].body = x.neighbor.bodies[0]
    else: body.faces[0].body = None
    with pytest.raises(ValueError): run(x)
    assert x.receipt.halted and not x.receipt.anchors
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('interface', ['IConfiguration', 'IFace2', 'IEdge', 'IBody2'])
def test_missing_normally_returned_interface_is_not_adopted(world, interface):
    x = world
    original = x.wrap
    x.wrap = lambda raw, name: None if name == interface else original(raw, name)
    with pytest.raises(ValueError): run(x)
    assert x.receipt.halted
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('fault', ['face_membership', 'edge_membership', 'owner', 'body_membership',
    'stamp', 'dirty', 'canonical', 'pid', 'event', 'configuration'])
def test_closing_envelope_rejects_topology_pid_metadata_and_events(world, fault):
    x = world; body = x.main.bodies[0]
    def change(count):
        if count != 2: return
        if fault == 'face_membership': body.faces[0] = Member(x, 'face', body)
        elif fault == 'edge_membership': body.edges[0] = Member(x, 'edge', body)
        elif fault == 'owner': body.faces[0].body = x.neighbor.bodies[0]
        elif fault == 'body_membership': x.main.bodies[0] = x.neighbor.bodies[0]
        elif fault == 'stamp': x.main.stamp += 1
        elif fault == 'dirty': x.main.dirty = False
        elif fault == 'canonical': body.edges[0].canonical = object()
        elif fault == 'pid': body.edges[0].pid = b'changed'
        elif fault == 'event': x.event += 2
        else: x.main.active = NS(canonical=object(), Name='Основная')
    x.main.on_census = change
    with pytest.raises(ValueError): run(x)
    assert x.receipt.halted and len(x.receipt.anchors) == 44
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('attribute,value', [('stamp', True), ('stamp', 17.0), ('dirty', 1), ('dirty', 'true')])
def test_native_metadata_requires_strict_types(world, attribute, value):
    setattr(world.main, attribute, value)
    with pytest.raises(ValueError, match='Strict native metadata'): run(world)
    assert world.receipt.halted
    assert_no_authority(world.receipt)


@pytest.mark.parametrize('failure', ['false', 'none', 'raise'])
def test_owner_admission_failure_prevents_first_read_and_blocks_retry(world, failure):
    x = world
    before = fixture_snapshot(x.fixture)
    def unsafe(fixture):
        if failure == 'raise': raise RuntimeError('Lost original owner')
        return False if failure == 'false' else None
    with pytest.raises((ValueError, RuntimeError)): run(x, assert_safe=unsafe)
    assert x.log == [] and x.receipt.halted and x.receipt.attempted
    assert x.receipt.pending_read is None
    with pytest.raises(ValueError, match='Fresh externally retained'): run(x)
    assert x.log == [] and vars(x.fixture) == before
    assert_no_authority(x.receipt)


def test_owner_loss_after_partial_retention_stops_all_further_dispatch(world):
    x = world
    original = x.safe
    def safe(fixture):
        if x.receipt.anchors: raise RuntimeError('Owner/session unavailable')
        return original(fixture)
    with pytest.raises(RuntimeError, match='Owner/session'): run(x, assert_safe=safe)
    assert len(x.receipt.anchors) == 1 and x.receipt.pending_read is None
    calls = list(x.log)
    with pytest.raises(ValueError): run(x)
    assert x.log == calls and x.receipt.halted
    assert_no_authority(x.receipt)


def test_native_read_exception_keeps_pending_read_and_original_partial_receipt(world):
    x = world
    def unavailable(*args): raise RuntimeError('Unknown read outcome')
    x.adapter.resolve_persistent_id = unavailable
    with pytest.raises(RuntimeError, match='Unknown read outcome'): run(x)
    assert len(x.receipt.anchors) == 1
    assert x.receipt.pending_read == 'PID_roundtrip' and x.receipt.halted
    calls = list(x.log)
    with pytest.raises(ValueError): run(x)
    assert x.log == calls
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('field,value', [('setup_complete', False), ('attempted', False),
    ('halted', True), ('pending_step', 'unknown'), ('journal_lost', True)])
def test_incomplete_failed_or_unacknowledged_fixture_prevents_any_read(world, field, value):
    x = world
    setattr(x.fixture, field, value)
    with pytest.raises(ValueError, match='Completed normally acknowledged'): run(x)
    assert not x.receipt.attempted and x.log == []
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('fresh_in_worker', [False, True])
def test_foreign_thread_cannot_read_original_fixture(world, fresh_in_worker):
    x = world; errors = []
    def worker():
        try: run(x, receipt=PartAnchorReceipt() if fresh_in_worker else x.receipt)
        except Exception as error: errors.append(error)
    thread = Thread(target=worker)
    thread.start(); thread.join(timeout=5)
    assert not thread.is_alive() and len(errors) == 1
    assert isinstance(errors[0], ValueError) and 'STA' in str(errors[0])
    assert x.log == [] and not x.receipt.attempted


def test_foreign_thread_detected_between_reads_latches_receipt(world, monkeypatch):
    x = world; owner = get_ident()
    monkeypatch.setattr(anchors_module, 'get_ident', lambda: owner if not x.polls else owner + 1)
    with pytest.raises(ValueError, match='foreign STA'): run(x)
    assert x.receipt.halted and x.polls == 1
    assert [operation for operation, _ in x.log] == ['safe', 'poll']
    assert_no_authority(x.receipt)


def test_successful_receipt_cannot_be_reused_or_authorize_acceptance(world):
    x = world
    original = run(x)
    calls = list(x.log)
    with pytest.raises(ValueError, match='Fresh externally retained'): run(x)
    assert tuple(x.receipt.anchors) == original and x.log == calls
    assert x.receipt.complete and not x.receipt.accepted and not x.receipt.cleanup_authorized


def test_same_kind_pid_collision_does_not_create_complete_authority(world):
    x = world; body = x.main.bodies[0]
    one, two = body.faces[:2]
    two.pid = one.pid
    # An intentionally hostile resolver follows the last retained handle;
    # canonical equality alone must not admit duplicate persistent IDs.
    x.adapter.resolve_persistent_id = lambda model, pid, kind: x.receipt.anchors[-1].handle
    with pytest.raises(ValueError, match='Unique complete'): run(x)
    assert x.receipt.halted and len(x.receipt.anchors) == 44
    assert_no_authority(x.receipt)


def test_last_closing_pid_read_cannot_replace_members_after_the_previous_census(world):
    x = world
    original = x.adapter.persistent_id
    last = x.main.bodies[-1].edges[-1]
    changed = []
    def pid(model, obj):
        result = original(model, obj)
        if x.receipt.pending_read == 'closing_PID' and obj is last:
            body = x.main.bodies[0]
            body.faces[0] = Member(x, 'face', body)
            changed.append(True)
        return result
    x.adapter.persistent_id = pid
    with pytest.raises(ValueError, match='topology membership changed'): run(x)
    assert changed == [True] and x.receipt.halted and len(x.receipt.anchors) == 44
    assert_no_authority(x.receipt)


def test_canonical_native_aliases_do_not_require_python_wrapper_identity(world):
    x = world
    original = x.adapter.resolve_persistent_id
    def alias(model, pid, kind):
        obj = original(model, pid, kind)
        return NS(canonical=obj.canonical, pid=obj.pid)
    x.adapter.resolve_persistent_id = alias
    body = x.main.bodies[0]
    body.faces[0].GetBody = lambda: NS(canonical=body.canonical)
    assert len(run(x)) == 44 and x.receipt.complete


@pytest.mark.parametrize('phase', ['persistent_id', 'resolved_PID', 'closing_PID'])
@pytest.mark.parametrize('malformed', ['bytearray', 'string', 'none'])
def test_every_pid_phase_requires_exact_nonempty_bytes(world, phase, malformed):
    x = world
    original = x.adapter.persistent_id
    invalid = []
    def pid(model, obj):
        result = original(model, obj)
        if x.receipt.pending_read == phase:
            value = bytearray(result) if malformed == 'bytearray' else result.hex() if malformed == 'string' else None
            invalid.append(value)
            return value
        return result
    x.adapter.persistent_id = pid
    with pytest.raises(ValueError, match='native PID bytes'): run(x)
    assert len(invalid) == 1
    label, returned = x.receipt.returned_reads[-1]
    assert label == phase and returned is invalid[0]
    assert x.receipt.pending_read is None and x.receipt.halted
    assert_no_authority(x.receipt)


@pytest.mark.parametrize('failure', ['edges', 'wrap', 'pid'])
def test_raw_face_array_retained_before_later_getter_wrapper_or_pid_failure(world, failure):
    x = world; body = x.main.bodies[0]
    raw_faces = body.faces
    before = fixture_snapshot(x.fixture)
    def fail(*args):
        assert any(label == 'body_faces' and raw is raw_faces for label, raw in x.receipt.returned_reads)
        raise RuntimeError('Later native-shaped read failed')
    if failure == 'edges': body.GetEdges = fail
    elif failure == 'wrap':
        original = x.wrap
        x.wrap = lambda raw, interface: fail() if interface == 'IFace2' else original(raw, interface)
    else: x.adapter.persistent_id = fail
    with pytest.raises(RuntimeError, match='Later native-shaped'): run(x)
    assert x.receipt.pending_read == {'edges': 'body_edges', 'wrap': 'topology_interface', 'pid': 'persistent_id'}[failure]
    assert any(label == 'body_faces' and raw is raw_faces for label, raw in x.receipt.returned_reads)
    assert x.receipt.halted and not x.receipt.anchors
    assert vars(x.fixture) == before
    assert_no_authority(x.receipt)
    calls = list(x.log)
    with pytest.raises(ValueError, match='Fresh externally retained'): run(x)
    assert x.log == calls


def test_read_budget_exhaustion_dispatches_no_more_owner_or_native_calls(world):
    x = world
    x.receipt.returned_reads = [('earlier-owned-read', None)] * 20000
    with pytest.raises(ValueError, match='read budget exceeded'): run(x)
    assert x.log == [] and len(x.receipt.returned_reads) == 20000
    assert x.receipt.halted and x.receipt.pending_read is None
    assert_no_authority(x.receipt)
