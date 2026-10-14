"""Retain complete static I02 topology from the original B3 fixture owner.

No COM connection, mutation, registration, cleanup or acceptance. Caller retains
the receipt before entry, supplies its STA admission/event watcher, and owns all
reads. Body ownership derives from acknowledged fixture handles, never names,
geometry, active documents or a difference of document/body rosters.
"""
from dataclasses import dataclass, field
from threading import get_ident

from verifier_b3_part_fixture import PartFixtureReceipt, FixtureAnchor
from verifier_b3_part_bridge import OriginalPartObject


def require(condition, message):
    if not condition: raise ValueError(message)


@dataclass
class PartAnchorReceipt:
    thread_id: int = field(default_factory=get_ident)
    attempted: bool = False
    halted: bool = False
    pending_read: str | None = None
    returned_reads: list = field(default_factory=list)
    anchors: list = field(default_factory=list)
    complete: bool = False
    accepted: bool = False
    native_acceptance: bool = False
    cleanup_authorized: bool = False


def retain_part_anchors(*, receipt, fixture, model_role, adapter, wrap, watch, assert_safe):
    """Prepare OriginalPartObject inputs before any public SDK registration.

Only completed static part-fixture Main configuration: three original target
bodies or the single original neighbor body. Cylinder/configuration transitions
remain separate profiles. All three object kinds require nonempty native PID,
current canonical roundtrip and native owner membership. Failed read/admission
latches the externally retained receipt; partial anchors grant no authority.
"""
    require(type(receipt) is PartAnchorReceipt and not receipt.attempted,
            'Fresh externally retained topology receipt required.')
    require(isinstance(fixture, PartFixtureReceipt) and fixture.setup_complete is True
            and fixture.attempted is True and fixture.halted is False
            and fixture.pending_step is None and fixture.journal_lost is False,
            'Completed normally acknowledged original fixture required.')
    require(model_role in ('Основная деталь', 'Сосед') and callable(wrap) and callable(assert_safe),
            'Explicit supported original model role and owner callbacks required.')
    require(receipt.thread_id == fixture.thread_id == get_ident(), 'Original fixture STA required.')
    model_anchor = fixture.documents[model_role]
    cfg_anchor = fixture.configurations[model_role + '_Основная']
    roots = [fixture.bodies['Сосед']] if model_role == 'Сосед' else [
        fixture.bodies[role] for role in ('Первый', 'Второй', 'Поверхность')]
    require(all(isinstance(anchor, FixtureAnchor) for anchor in [model_anchor, cfg_anchor, *roots])
            and model_anchor.kind == 'document' and cfg_anchor.kind == 'configuration'
            and all(anchor.kind == 'body' for anchor in roots), 'Typed original custody anchors required.')
    receipt.attempted = True

    def read(label, function, *args):
        require(get_ident() == receipt.thread_id and not receipt.halted and receipt.pending_read is None,
                'Failed or foreign STA topology receipt cannot dispatch another read.')
        require(len(receipt.returned_reads) < 20000, 'Finite original topology read budget exceeded.')
        require(assert_safe(fixture) is True, 'Original full owner/session admission required.')
        receipt.pending_read = label
        result = function(*args)
        # Keep actual raw arrays/interfaces before later wrapping/getters can
        # fail. This private custody list is never a serialized public receipt.
        receipt.returned_reads.append((label, result))
        receipt.pending_read = None
        return result

    def identity(obj): return read('canonical', adapter.identity, obj)

    def persistent_id(label, handle):
        pid = read(label, adapter.persistent_id, model_anchor.handle, handle)
        require(type(pid) is bytes and bool(pid), 'Nonempty actual original native PID bytes required.')
        return pid

    def array(raw, maximum):
        require(type(raw) in (tuple, list) and len(raw) <= maximum,
                'Complete bounded native topology array required; None is not an empty proof.')
        return list(raw)

    def custody():
        require(identity(model_anchor.handle) == model_anchor.canonical
                and identity(cfg_anchor.handle) == cfg_anchor.canonical,
                'Original model/configuration incarnation changed.')
        cfg = read('active_configuration', wrap,
                   read('active_configuration_raw', model_anchor.handle.GetActiveConfiguration), 'IConfiguration')
        require(cfg is not None and identity(cfg) == cfg_anchor.canonical
                and read('configuration_name', getattr, cfg, 'Name') == 'Основная',
                'Static original Main configuration must remain active.')
        stamp = read('update_stamp', model_anchor.handle.GetUpdateStamp)
        dirty = read('needs_save', model_anchor.handle.GetSaveFlag)
        require(type(stamp) is int and type(dirty) is bool, 'Strict native metadata required.')
        return stamp, dirty

    def pid_object(kind, handle, body_canonical):
        canonical = identity(handle)
        pid = persistent_id('persistent_id', handle)
        anchor = OriginalPartObject(kind, handle, canonical, pid, body_canonical)
        # Preserve the exact current handle/PID before subsequent roundtrip reads.
        receipt.anchors.append(anchor)
        current = read('PID_roundtrip', adapter.resolve_persistent_id, model_anchor.handle, pid, kind)
        require(current is not None and identity(current) == canonical
                and persistent_id('resolved_PID', current) == pid,
                'Original topology PID must resolve its exact current canonical object.')
        return anchor

    def census():
        part = read('part_interface', wrap, model_anchor.handle, 'IPartDoc')
        bodies = array(read('all_normal_bodies', part.GetBodies2, -1, False), len(roots))
        require(len(bodies) == len(roots), 'Complete current body roster differs from original fixture.')
        tokens = [identity(raw) for raw in bodies]
        require(all(sum(token == root.canonical for token in tokens) == 1 for root in roots)
                and all(sum(root.canonical == other.canonical for other in roots) == 1 for root in roots),
                'Every original body must be the sole current member of its canonical identity.')
        result = []
        for root in roots:
            require(identity(root.handle) == root.canonical, 'Original body anchor changed.')
            code = read('body_type', root.handle.GetType)
            require(type(code) is int and code in (0, 1)
                    and read('mesh_flag', root.handle.IsMeshBody) is False, 'Only normal solid/surface BREP allowed.')
            faces = array(read('body_faces', root.handle.GetFaces), 40)
            edges = array(read('body_edges', root.handle.GetEdges), 80)
            counts = (read('face_count', root.handle.GetFaceCount), read('edge_count', root.handle.GetEdgeCount))
            require(all(type(count) is int for count in counts) and counts == (len(faces), len(edges))
                    and faces and edges, 'Complete nonempty native topology counts required.')
            members = []
            for kind, raws, interface in (('face', faces, 'IFace2'), ('edge', edges, 'IEdge')):
                seen = []
                for raw in raws:
                    handle = read('topology_interface', wrap, raw, interface)
                    require(handle is not None, 'Normally returned topology interface required.')
                    canonical = identity(handle)
                    require(not any(canonical == old for old in seen), 'Duplicate topology member prohibited.')
                    seen.append(canonical)
                    owner = read('topology_owner_interface', wrap,
                                 read('topology_owner', handle.GetBody), 'IBody2')
                    require(owner is not None and identity(owner) == root.canonical,
                            'Native topology must belong to its exact original body.')
                    members.append((kind, handle, canonical))
            result.append((root, members))
        return result

    def unchanged(opening, current):
        require(len(opening) == len(current), 'Complete original body census changed.')
        for (root, old), (current_root, members) in zip(opening, current):
            require(root is current_root and len(old) == len(members)
                    and all(sum(kind == other_kind and token == other_token
                        for other_kind, _, other_token in members) == 1 for kind, _, token in old),
                    'Full original topology membership changed during anchor capture.')

    try:
        event = read('open_event', watch.poll)
        before = custody()
        opening = census()
        for root, members in opening:
            pid_object('body', root.handle, root.canonical)
            for kind, handle, canonical in members:
                anchor = pid_object(kind, handle, root.canonical)
                require(anchor.canonical == canonical, 'Original topology changed before PID retention.')
        require(len(receipt.anchors) <= 5000
                and all(sum(a.kind == b.kind and a.persistent_id == b.persistent_id
                            for b in receipt.anchors) == 1 for a in receipt.anchors),
                'Unique complete original kind/PID anchors required.')
        closing = census()
        unchanged(opening, closing)
        for anchor in receipt.anchors:
            require(identity(anchor.handle) == anchor.canonical
                    and persistent_id('closing_PID', anchor.handle) == anchor.persistent_id,
                    'Retained original canonical/PID changed during closing census.')
        # PID getters/resolvers are also inside the observation envelope. A
        # membership change during those reads must not escape the final census.
        unchanged(opening, census())
        require(custody() == before, 'Original document/configuration metadata changed during capture.')
        require(read('close_event', watch.poll) == event, 'Owner/session event envelope changed during capture.')
        receipt.complete = True
        return tuple(receipt.anchors)
    except BaseException:
        receipt.halted = True
        raise
