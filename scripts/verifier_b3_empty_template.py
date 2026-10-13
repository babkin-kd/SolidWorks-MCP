"""Read original empty-template custody for caller-owned B3 fixture builders.

No connection/creation/registration/naming/cleanup. Caller holds the receipt
before entry and supplies all acknowledged document anchors, its STA admission
and whole-session event watcher. Native reference frames identify input planes;
native names and positions in the tree never select ownership.
"""
from dataclasses import dataclass, field
from threading import get_ident

from solidworks_mcp.part_creation import validated_plane_transform
from verifier_b3_part_fixture import FixtureAnchor, PartFixtureReceipt, EmptyPartBaseline


def require(condition, message):
    if not condition: raise ValueError(message)


@dataclass
class EmptyTemplateReceipt:
    thread_id: int = field(default_factory=get_ident)
    attempted: bool = False
    halted: bool = False
    pending_read: str | None = None
    returned_reads: list = field(default_factory=list)
    features: list = field(default_factory=list)
    configuration: object = None
    complete: bool = False
    accepted: bool = False
    native_acceptance: bool = False
    cleanup_authorized: bool = False


@dataclass(frozen=True)
class EmptyTemplate:
    model_canonical: object
    features: tuple
    plane_frames: tuple

    def xy_baseline(self):
        frame = (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.)
        candidates = [anchor for anchor, transform in self.plane_frames if transform == frame]
        require(len(candidates) == 1, 'Exactly one original model-XY frame required.')
        return EmptyPartBaseline(self.model_canonical, self.features, candidates[0], True)

    def cylinder_baseline(self):
        # Lazy dependency: this independent admission also serves the box setup.
        from verifier_b3_cylinder_fixture import CylinderEmptyBaseline
        candidates = [(anchor, transform) for anchor, transform in self.plane_frames
                      if transform[6] == transform[8] == 0. and abs(transform[7]) == 1.]
        require(len(candidates) == 1, 'Exactly one original model-Y normal plane required.')
        anchor, transform = candidates[0]
        return CylinderEmptyBaseline(self.model_canonical, self.features, anchor, transform, True)


def capture_empty_template(*, receipt, fixture, document, original_documents,
                           adapter, wrap, assert_safe, watch_poll, prior_fixtures=()):
    """Exact original body-free/template proof before builder naming/sketches.

original_documents explicitly includes the newly returned document and every
earlier original own fixture document. Later census differences never adopt
additional models. Pending outer builder admission is permitted; pending native
creation or journal loss is not. All raw getter returns remain private custody.
Earlier documents from a separate completed part/cylinder builder must be
declared through prior_fixtures, not supplied as otherwise unproven anchors.
"""
    require(type(receipt) is EmptyTemplateReceipt and not receipt.attempted,
            'Fresh externally retained empty-template receipt required.')
    require(isinstance(fixture, PartFixtureReceipt) and fixture.attempted is True
            and fixture.halted is False and fixture.journal_lost is False
            and type(fixture.pending_step) is str and fixture.pending_step.endswith(':empty_admission'),
            'Normally returned creation under original pending admission callback required.')
    require(isinstance(document, FixtureAnchor) and document.kind == 'document'
            and any(anchor is document for anchor in fixture.documents.values())
            and type(original_documents) is tuple and 0 < len(original_documents) <= 4
            and all(isinstance(anchor, FixtureAnchor) and anchor.kind == 'document'
                    and anchor.canonical is not None for anchor in original_documents)
            and sum(anchor is document for anchor in original_documents) == 1,
            'Complete explicit original document custody required.')
    require(type(prior_fixtures) is tuple and len(prior_fixtures) <= 3
            and all(isinstance(prior, PartFixtureReceipt) and prior is not fixture
                    and prior.thread_id == fixture.thread_id and prior.setup_complete is True
                    and prior.attempted is True and prior.halted is False
                    and prior.pending_step is None and prior.journal_lost is False
                    and prior.native_returns for prior in prior_fixtures),
            'Earlier original documents require completed acknowledged same-STA fixture receipts.')
    owned = list(fixture.documents.values())
    for prior in prior_fixtures: owned.extend(prior.documents.values())
    require(len(owned) == len(original_documents)
            and all(sum(candidate is anchor for candidate in original_documents) == 1 for anchor in owned),
            'All and only originally acknowledged fixture documents must enter the complete roster.')
    require(receipt.thread_id == fixture.thread_id == get_ident()
            and all(callable(callback) for callback in (wrap, assert_safe, watch_poll)), 'Original STA callbacks required.')
    receipt.attempted = True

    def read(label, function, *args):
        require(get_ident() == receipt.thread_id and not receipt.halted and receipt.pending_read is None
                and len(receipt.returned_reads) < 5000, 'Failed/foreign/over-budget admission cannot dispatch.')
        require(assert_safe(fixture) is True, 'Original whole-session owner admission required.')
        receipt.pending_read = label
        value = function(*args)
        receipt.returned_reads.append((label, value))
        receipt.pending_read = None
        return value

    def identity(obj): return read('canonical', adapter.identity, obj)

    def windows():
        current = read('whole_window_census', adapter.native_close_windows)
        require(type(current) in (tuple, list) and len(current) == len(original_documents),
                'Whole window/model census differs from original returned documents.')
        originals = [identity(anchor.handle) for anchor in original_documents]
        require(all(token == anchor.canonical for token, anchor in zip(originals, original_documents))
                and all(sum(token == other for other in originals) == 1 for token in originals),
                'Every original document incarnation must remain distinct/current.')
        result = []
        for model, info in current:
            token = identity(model)
            require(sum(token == original for original in originals) == 1
                    and type(info) is dict and type(info.get('hwnd')) is int and 0 < info['hwnd'] < 2**63,
                    'Foreign/replaced model or invalid native window prohibited.')
            result.append((token, info['hwnd']))
        require(len({hwnd for _, hwnd in result}) == len(result), 'Unique complete model windows required.')
        require(all(sum(token == original for token, _ in result) == 1 for original in originals),
                'Each original document must have exactly one current window.')
        return result

    def metadata():
        kind = read('document_type', document.handle.GetType)
        require(identity(document.handle) == document.canonical and type(kind) is int and kind == 1
                and read('owned_guard', getattr, adapter._sw, 'CommandInProgress') is True,
                'Exact original part under own application guard required.')
        snapshot = read('metadata', adapter.snapshot, document.handle)
        require(snapshot['path'] == '' and snapshot['document_type'] == 'part'
                and snapshot['needs_save'] is False and len(snapshot['configurations']) == 1
                and snapshot['active_configuration'] == snapshot['configurations'][0],
                'Unsaved clean original single-configuration template required.')
        cfg = read('configuration_interface', wrap,
                   read('configuration_raw', document.handle.GetActiveConfiguration), 'IConfiguration')
        require(cfg is not None, 'Original current configuration interface required.')
        cfg_token = identity(cfg)
        require(cfg_token is not None, 'Strong original configuration canonical required.')
        if receipt.configuration is None:
            receipt.configuration = FixtureAnchor('Исходная конфигурация', 'configuration', cfg, cfg_token)
        require(cfg_token == receipt.configuration.canonical
                and identity(receipt.configuration.handle) == receipt.configuration.canonical,
                'Original configuration incarnation changed during empty admission.')
        context = read('native_mode', adapter.native_close_model_context, document.handle)
        require(context['dependencies'] == [] and context['mode']['editing_sketch'] is False
                and context['mode']['editing_component'] is False and context['mode']['view_only'] is False,
                'Independent dependency/edit-mode admission required.')
        mode = context['mode']
        require(type(mode['read_only_state']) is int and mode['read_only_state'] == 0
                and type(mode['blocking_state']) is int and mode['blocking_state'] in (0, 2),
                'Writable unblocked original fixture document required.')
        part = read('part_interface', wrap, document.handle, 'IPartDoc')
        bodies = read('complete_body_census', part.GetBodies2, -1, False)
        require(bodies is None or type(bodies) in (tuple, list) and len(bodies) == 0,
                'New template must have no normal solid/surface bodies.')
        return snapshot, context, cfg_token

    def features():
        members = read('complete_template_features', adapter.features, document.handle)
        require(type(members) in (tuple, list) and 0 < len(members) <= 100, 'Complete bounded original feature census required.')
        result, frames = [], []
        for handle in members:
            token = identity(handle)
            require(token is not None, 'Strong original template feature canonical required.')
            require(not any(token == anchor.canonical for anchor in result), 'Duplicate original template feature prohibited.')
            anchor = FixtureAnchor('Исходный элемент ' + str(len(result)+1), 'feature', handle, token)
            kind = read('native_feature_kind', handle.GetTypeName2)
            require(type(kind) is str and kind and kind not in ('ProfileFeature', '3DProfileFeature'),
                    'Existing template sketches are outside the empty fixture profile.')
            result.append(anchor)
            if kind == 'RefPlane':
                raw = read('native_plane_frame', adapter.reference_plane_transform, handle)
                frames.append((anchor, validated_plane_transform(raw)))
        require(len(frames) == 3, 'Exactly three original reference planes required.')
        return result, frames

    try:
        event = read('open_events', watch_poll)
        before_windows, before = windows(), metadata()
        original, frames = features()
        receipt.features.extend(original)
        closing, closing_frames = features()
        require(len(original) == len(closing)
                and all(a.canonical == b.canonical for a, b in zip(original, closing))
                and [(a.canonical, frame) for a, frame in frames] == [(a.canonical, frame) for a, frame in closing_frames],
                'Original complete template membership/order/frame changed.')
        require(metadata() == before and windows() == before_windows,
                'Original document/mode/window scope changed during admission.')
        require(read('close_events', watch_poll) == event, 'Whole-session events changed during empty-template admission.')
        receipt.complete = True
        return EmptyTemplate(document.canonical, tuple(original), tuple(frames))
    except BaseException:
        receipt.halted = True
        raise
