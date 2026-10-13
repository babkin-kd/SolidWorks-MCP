"""API-shaped empty-template custody tests; no CAD, connection or COM."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_cylinder_fixture import CylinderEmptyBaseline
    from verifier_b3_empty_template import EmptyTemplateReceipt, capture_empty_template
    from verifier_b3_part_fixture import EmptyPartBaseline, FixtureAnchor, PartFixtureReceipt
finally:
    sys.path.remove(scripts)


XY = (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.)
POSITIVE_Y = (1., 0., 0., 0., 0., -1., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0.)
NEGATIVE_Y = (1., 0., 0., 0., 0., 1., 0., -1., 0., 0., 0., 0., 1., 0., 0., 0.)
NORMAL_X = (0., 1., 0., 0., 0., 1., 1., 0., 0., 0., 0., 0., 1., 0., 0., 0.)


class Native:
    def __init__(self, world):
        self.world = world
        self.canonical = world.next_token
        world.next_token += 1
        self.Name = 'По умолчанию'


class Feature(Native):
    def __init__(self, world, kind, frame=None):
        super().__init__(world)
        self.kind, self.frame = kind, frame

    def GetTypeName2(self):
        return self.world.call('feature_type', self.kind)


class Model(Native):
    def __init__(self, world):
        super().__init__(world)
        self.kind = 1
        self.cfg = Native(world)
        # Native names are deliberately identical; XY is not the first plane.
        self.features = [Feature(world, 'OriginProfileFeature'),
                         Feature(world, 'RefPlane', POSITIVE_Y),
                         Feature(world, 'RefPlane', NORMAL_X),
                         Feature(world, 'RefPlane', XY)]
        self.bodies = []
        self.snapshot = dict(path='', document_type='part', needs_save=False,
                             configurations=['По умолчанию'], active_configuration='По умолчанию')
        self.context = dict(dependencies=[], mode=dict(editing_sketch=False,
                            editing_component=False, view_only=False,
                            read_only_state=0, blocking_state=0))

    def GetType(self):
        return self.world.call('document_type', self.kind)

    def GetActiveConfiguration(self):
        self.world.call('configuration_raw', self.cfg)
        return self.cfg

    def GetBodies2(self, kind, visible_only):
        assert (kind, visible_only) == (-1, False)
        return self.world.call('bodies', self.bodies)


class Adapter:
    def __init__(self, world):
        self.world = world
        self._sw = NS(CommandInProgress=True)

    def identity(self, handle):
        self.world.call('identity', handle)
        return handle.canonical

    def native_close_windows(self):
        return self.world.call('windows', self.world.windows)

    def snapshot(self, model):
        self.world.call('metadata', model)
        return deepcopy(model.snapshot)

    def native_close_model_context(self, model):
        self.world.call('context', model)
        return deepcopy(model.context)

    def features(self, model):
        self.world.call('features', model)
        return tuple(model.features)

    def reference_plane_transform(self, feature):
        return self.world.call('frame', feature.frame)


class World:
    def __init__(self):
        self.next_token = 1
        self.calls, self.counts, self.hooks = [], {}, {}
        self.safe = True
        self.event = ('unchanged-session',)
        self.receipt = EmptyTemplateReceipt()
        self.fixture = PartFixtureReceipt('explicit-empty-request')
        self.fixture.attempted = True
        self.fixture.pending_step = 'Основная деталь:empty_admission'
        self.model = Model(self)
        self.document = self.own(self.model, 'Основная деталь')
        self.fixture.native_returns.append((1, 'Основная деталь:new_document', self.model))
        self.original_documents = (self.document,)
        self.windows = [(self.model, {'hwnd': 101})]
        self.adapter = Adapter(self)

    def own(self, model, role):
        anchor = FixtureAnchor(role, 'document', model, model.canonical)
        self.fixture.documents[role] = anchor
        return anchor

    def call(self, label, value):
        self.calls.append(label)
        self.counts[label] = self.counts.get(label, 0) + 1
        hook = self.hooks.get((label, self.counts[label]))
        if hook:
            hook()
        return value

    def assert_safe(self, fixture):
        assert fixture is self.fixture
        return self.call('safe', self.safe)

    def wrap(self, raw, interface):
        assert interface in ('IConfiguration', 'IPartDoc')
        return self.call('wrap:' + interface, raw)

    def watch_poll(self):
        self.call('watch', None)
        return self.event

    def run(self, **overrides):
        args = dict(receipt=self.receipt, fixture=self.fixture,
                    document=self.document, original_documents=self.original_documents,
                    adapter=self.adapter, wrap=self.wrap, assert_safe=self.assert_safe,
                    watch_poll=self.watch_poll)
        args.update(overrides)
        return capture_empty_template(**args)


@pytest.fixture
def world():
    return World()


def assert_failed_custody(world):
    assert world.receipt.attempted and world.receipt.halted
    assert not world.receipt.complete
    assert not world.receipt.accepted and not world.receipt.native_acceptance
    assert not world.receipt.cleanup_authorized


@pytest.mark.parametrize('frame', [POSITIVE_Y, NEGATIVE_Y])
@pytest.mark.parametrize('earlier_count', [0, 1, 3])
def test_original_frames_and_prior_owned_windows_yield_only_private_baselines(world, frame, earlier_count):
    world.model.features[1].frame = frame
    earlier = []
    for index in range(earlier_count):
        model = Model(world)
        # Previous fixtures may already have bodies, dirty flags and variants.
        model.bodies = [Native(world)]
        model.snapshot['needs_save'] = True
        model.snapshot['configurations'].append('Вариант')
        earlier.append(world.own(model, 'Ранее ' + str(index)))
        world.windows.insert(0, (model, {'hwnd': 200 + index}))
    world.original_documents = tuple(earlier) + (world.document,)
    fixture_before = dict(world.fixture.documents), world.fixture.pending_step, tuple(world.fixture.native_returns)
    result = world.run()
    xy, cylinder = result.xy_baseline(), result.cylinder_baseline()
    assert isinstance(xy, EmptyPartBaseline) and xy.xy_plane_proven is True
    assert isinstance(cylinder, CylinderEmptyBaseline) and cylinder.plane_proven is True
    assert xy.model_canonical == cylinder.model_canonical == world.document.canonical
    assert xy.features is result.features and cylinder.features is result.features
    assert xy.xy_plane.handle is world.model.features[3]
    assert cylinder.plane.handle is world.model.features[1] and cylinder.transform == frame
    assert [a.handle for a in result.features] == world.model.features
    assert world.receipt.configuration.handle is world.model.cfg
    assert world.receipt.features == list(result.features)
    assert world.receipt.complete and not world.receipt.halted and world.receipt.pending_read is None
    assert not world.receipt.accepted and not world.receipt.native_acceptance and not world.receipt.cleanup_authorized
    assert fixture_before == (world.fixture.documents, world.fixture.pending_step, tuple(world.fixture.native_returns))
    assert all(f.Name == 'По умолчанию' for f in world.model.features)
    assert world.counts['safe'] == len(world.receipt.returned_reads)
    assert next(value for label, value in world.receipt.returned_reads
                if label == 'whole_window_census') is world.windows


@pytest.mark.parametrize('bodies', [None, [], ()])
@pytest.mark.parametrize('blocking', [0, 2])
def test_complete_normal_body_census_empty_variants_and_allowed_blocking_modes(world, bodies, blocking):
    world.model.bodies = bodies
    world.model.context['mode']['blocking_state'] = blocking
    assert world.run().model_canonical == world.document.canonical
    assert world.counts['bodies'] == 2


@pytest.mark.parametrize('change', ['not_attempted', 'halted', 'journal_lost', 'pending_creation',
                                    'pending_none', 'different_thread', 'receipt_thread', 'wrong_document',
                                    'copied_document', 'roster_list', 'empty_roster', 'too_many',
                                    'missing_current', 'duplicate_current', 'missing_callback'])
def test_original_callback_contract_rejects_before_any_getter(world, change):
    overrides = {}
    if change == 'not_attempted':
        world.fixture.attempted = False
    elif change in ('halted', 'journal_lost'):
        setattr(world.fixture, change, True)
    elif change == 'pending_creation':
        world.fixture.pending_step = 'Основная деталь:new_document'
    elif change == 'pending_none':
        world.fixture.pending_step = None
    elif change == 'different_thread':
        world.fixture.thread_id = -1
    elif change == 'receipt_thread':
        world.receipt.thread_id = -1
    elif change == 'wrong_document':
        overrides['document'] = replace(world.document, kind='feature')
    elif change == 'copied_document':
        overrides['document'] = replace(world.document)
    elif change == 'roster_list':
        overrides['original_documents'] = [world.document]
    elif change == 'empty_roster':
        overrides['original_documents'] = ()
    elif change == 'too_many':
        overrides['original_documents'] = (world.document,) + tuple(
            world.own(Model(world), 'Лишний ' + str(i)) for i in range(4))
    elif change == 'missing_current':
        overrides['original_documents'] = (world.own(Model(world), 'Ранее'),)
    elif change == 'duplicate_current':
        overrides['original_documents'] = (world.document, world.document)
    elif change == 'missing_callback':
        overrides['watch_poll'] = None
    with pytest.raises(ValueError):
        world.run(**overrides)
    assert not world.calls and not world.receipt.attempted


@pytest.mark.parametrize('change', ['unowned_extra', 'omitted_earlier', 'weak_document'])
def test_original_roster_must_be_complete_and_strong_fixture_custody(world, change):
    if change == 'unowned_extra':
        foreign = Model(world)
        anchor = FixtureAnchor('Чужая', 'document', foreign, foreign.canonical)
        world.original_documents += (anchor,)
        world.windows.append((foreign, {'hwnd': 202}))
    elif change == 'omitted_earlier':
        world.own(Model(world), 'Ранее')
        # Even a closed/missing earlier original cannot be forgotten by caller.
    else:
        world.model.canonical = None
        world.document = replace(world.document, canonical=None)
        world.fixture.documents['Основная деталь'] = world.document
        world.original_documents = (world.document,)
    with pytest.raises(ValueError):
        world.run()
    assert not world.calls and not world.receipt.attempted


def completed_prior(world):
    prior = PartFixtureReceipt('explicit-previous-request')
    prior.attempted = prior.setup_complete = True
    for index, role in enumerate(('Основная прежняя', 'Прежний сосед')):
        model = Model(world)
        model.bodies = [Native(world)]
        model.snapshot['needs_save'] = True
        anchor = FixtureAnchor(role, 'document', model, model.canonical)
        prior.documents[role] = anchor
        prior.native_returns.append((index + 1, role + ':new_document', model))
        world.windows.insert(0, (model, {'hwnd': 202 + index}))
    world.original_documents = tuple(prior.documents.values()) + (world.document,)
    return prior


def test_explicit_completed_prior_fixture_allows_main_neighbor_and_new_cylinder(world):
    prior = completed_prior(world)
    before = (tuple(prior.documents.items()), tuple(prior.native_returns),
              prior.pending_step, prior.setup_complete)
    result = world.run(prior_fixtures=(prior,))
    assert result.cylinder_baseline().model_canonical == world.document.canonical
    assert before == (tuple(prior.documents.items()), tuple(prior.native_returns),
                      prior.pending_step, prior.setup_complete)
    assert world.receipt.complete and len(world.windows) == 3


@pytest.mark.parametrize('change', ['undeclared', 'incomplete', 'unattempted', 'halted',
                                    'journal_lost', 'pending', 'foreign_sta', 'no_acknowledgment',
                                    'missing_old', 'copied_old', 'same_receipt', 'list', 'duplicate'])
def test_prior_fixture_requires_exact_complete_acknowledged_original_custody(world, change):
    prior = completed_prior(world)
    overrides = {'prior_fixtures': (prior,)}
    if change == 'undeclared':
        overrides['prior_fixtures'] = ()
    elif change == 'incomplete':
        prior.setup_complete = False
    elif change == 'unattempted':
        prior.attempted = False
    elif change in ('halted', 'journal_lost'):
        setattr(prior, change, True)
    elif change == 'pending':
        prior.pending_step = 'previous:unknown_creation'
    elif change == 'foreign_sta':
        prior.thread_id = -1
    elif change == 'no_acknowledgment':
        prior.native_returns.clear()
    elif change == 'missing_old':
        overrides['original_documents'] = world.original_documents[1:]
    elif change == 'copied_old':
        overrides['original_documents'] = (replace(world.original_documents[0]),) + world.original_documents[1:]
    elif change == 'same_receipt':
        overrides['prior_fixtures'] = (world.fixture,)
    elif change == 'list':
        overrides['prior_fixtures'] = [prior]
    else:
        overrides['prior_fixtures'] = (prior, prior)
    with pytest.raises(ValueError):
        world.run(**overrides)
    assert not world.calls and not world.receipt.attempted


@pytest.mark.parametrize('target', ['configuration', 'feature'])
def test_configuration_and_feature_require_strong_original_canonicals(world, target):
    handle = world.model.cfg if target == 'configuration' else world.model.features[0]
    handle.canonical = None
    with pytest.raises(ValueError, match='Strong original'):
        world.run()
    assert_failed_custody(world)


@pytest.mark.parametrize('change', ['duplicate_anchor', 'replaced_anchor', 'foreign_model',
                                    'missing_window', 'duplicate_model', 'duplicate_hwnd'])
def test_exact_original_window_model_roster_rejects_changes(world, change):
    earlier_model = Model(world)
    earlier = world.own(earlier_model, 'Ранее')
    world.original_documents = (earlier, world.document)
    world.windows.append((earlier_model, {'hwnd': 202}))
    if change == 'duplicate_anchor':
        earlier = replace(earlier, canonical=world.document.canonical)
        world.fixture.documents['Ранее'] = earlier
        world.original_documents = (earlier, world.document)
        earlier_model.canonical = world.document.canonical
    elif change == 'replaced_anchor':
        earlier_model.canonical += 10000
    elif change == 'foreign_model':
        world.windows[1] = (Model(world), {'hwnd': 202})
    elif change == 'missing_window':
        world.windows.pop()
    elif change == 'duplicate_model':
        world.windows[1] = (world.model, {'hwnd': 202})
    else:
        world.windows[1] = (earlier_model, {'hwnd': 101})
    with pytest.raises(ValueError):
        world.run()
    assert_failed_custody(world)


@pytest.mark.parametrize('hwnd', [None, True, False, 0, -1, 2**63, 101., '101'])
def test_native_hwnd_requires_bounded_positive_integer(world, hwnd):
    world.windows[0][1]['hwnd'] = hwnd
    with pytest.raises(ValueError, match='window'):
        world.run()
    assert_failed_custody(world)


@pytest.mark.parametrize('field,value', [('editing_sketch', True), ('editing_sketch', 0),
                                        ('editing_component', True), ('editing_component', 0),
                                        ('view_only', True), ('view_only', 0),
                                        ('read_only_state', True), ('read_only_state', False),
                                        ('read_only_state', 1), ('read_only_state', 0.),
                                        ('blocking_state', True), ('blocking_state', False),
                                        ('blocking_state', 1), ('blocking_state', 2.)])
def test_independent_native_mode_admission_uses_exact_bool_and_int_types(world, field, value):
    world.model.context['mode'][field] = value
    with pytest.raises(ValueError):
        world.run()
    assert_failed_custody(world)
    assert not world.receipt.features


@pytest.mark.parametrize('field,value', [('path', 'C:/not-an-empty-template.sldprt'),
                                        ('document_type', 'assembly'), ('needs_save', True),
                                        ('needs_save', 0), ('configurations', []),
                                        ('configurations', ['По умолчанию', 'Вариант']),
                                        ('active_configuration', 'Вариант')])
def test_only_unsaved_clean_single_configuration_part_is_admitted(world, field, value):
    world.model.snapshot[field] = value
    with pytest.raises(ValueError):
        world.run()
    assert_failed_custody(world)


@pytest.mark.parametrize('kind', [True, 1., 2, '1'])
def test_native_document_type_cannot_be_bool_or_coerced(world, kind):
    world.model.kind = kind
    with pytest.raises(ValueError, match='original part'):
        world.run()
    assert_failed_custody(world)


@pytest.mark.parametrize('guard', [False, 1, None])
def test_exact_owned_application_guard_required(world, guard):
    world.adapter._sw.CommandInProgress = guard
    with pytest.raises(ValueError, match='own application guard'):
        world.run()
    assert_failed_custody(world)


@pytest.mark.parametrize('change', ['dependency', 'solid', 'surface', 'body_false',
                                    'profile', '3d_profile', 'duplicate_feature', 'zero_planes',
                                    'two_planes', 'four_planes', 'empty_tree', 'over_budget'])
def test_complete_empty_template_census_rejects_existing_geometry_or_incomplete_scope(world, change):
    if change == 'dependency':
        world.model.context['dependencies'] = ['foreign-reference']
    elif change in ('solid', 'surface'):
        world.model.bodies = [NS(GetType=lambda: 0 if change == 'solid' else 1)]
    elif change == 'body_false':
        world.model.bodies = False
    elif change in ('profile', '3d_profile'):
        world.model.features.append(Feature(world, 'ProfileFeature' if change == 'profile' else '3DProfileFeature'))
    elif change == 'duplicate_feature':
        world.model.features.append(world.model.features[0])
    elif change == 'zero_planes':
        world.model.features = world.model.features[:1]
    elif change == 'two_planes':
        world.model.features.pop()
    elif change == 'four_planes':
        world.model.features.append(Feature(world, 'RefPlane', XY))
    elif change == 'empty_tree':
        world.model.features = []
    else:
        world.model.features += [Feature(world, 'Folder') for _ in range(97)]
    with pytest.raises(ValueError):
        world.run()
    assert_failed_custody(world)


@pytest.mark.parametrize('change', ['offset', 'reflection', 'scale', 'nonorthogonal',
                                    'incomplete', 'bool', 'nan', 'infinity'])
def test_each_original_plane_requires_complete_finite_rigid_origin_frame(world, change):
    frame = list(XY)
    if change == 'offset':
        frame[9] = .001
    elif change == 'reflection':
        frame[0] = -1.
    elif change == 'scale':
        frame[12] = 2.
    elif change == 'nonorthogonal':
        frame[1] = .5
    elif change == 'incomplete':
        frame.pop()
    elif change == 'bool':
        frame[0] = True
    elif change == 'nan':
        frame[13] = float('nan')
    else:
        frame[0] = float('inf')
    world.model.features[3].frame = frame
    with pytest.raises(ExecutionFailure):
        world.run()
    assert_failed_custody(world)


@pytest.mark.parametrize('baseline,change', [('xy', 'duplicate'), ('xy', 'missing'),
                                           ('cylinder', 'duplicate'), ('cylinder', 'missing')])
def test_baseline_requires_unique_actual_frame_instead_of_plane_name_or_index(world, baseline, change):
    if baseline == 'xy':
        world.model.features[2 if change == 'duplicate' else 3].frame = XY if change == 'duplicate' else NORMAL_X
    else:
        world.model.features[2 if change == 'duplicate' else 1].frame = NEGATIVE_Y if change == 'duplicate' else NORMAL_X
    result = world.run()
    with pytest.raises(ValueError, match='Exactly one original'):
        getattr(result, baseline + '_baseline')()
    assert world.receipt.complete and not world.receipt.accepted


def test_configuration_aba_with_same_metadata_cannot_replace_original_incarnation(world):
    original = world.model.cfg
    replacement = Native(world)
    assert replacement.Name == original.Name
    world.hooks['configuration_raw', 2] = lambda: setattr(world.model, 'cfg', replacement)
    with pytest.raises(ValueError, match='configuration incarnation changed'):
        world.run()
    assert world.receipt.configuration.handle is original
    assert world.receipt.configuration.canonical == original.canonical
    assert next(value for label, value in reversed(world.receipt.returned_reads)
                if label == 'configuration_raw') is replacement
    assert_failed_custody(world)


@pytest.mark.parametrize('change', ['feature_order', 'feature_replaced', 'frame', 'body',
                                    'metadata', 'mode', 'window_hwnd', 'events'])
def test_closing_recapture_rejects_tree_geometry_mode_window_or_event_change(world, change):
    if change == 'feature_order':
        world.hooks['features', 2] = lambda: world.model.features.reverse()
    elif change == 'feature_replaced':
        world.hooks['features', 2] = lambda: world.model.features.__setitem__(0, Feature(world, 'OriginProfileFeature'))
    elif change == 'frame':
        world.hooks['features', 2] = lambda: setattr(world.model.features[1], 'frame', NEGATIVE_Y)
    elif change == 'body':
        world.hooks['metadata', 2] = lambda: setattr(world.model, 'bodies', [Native(world)])
    elif change == 'metadata':
        world.hooks['metadata', 2] = lambda: world.model.snapshot.update(title='Same-valid-part-new-title')
    elif change == 'mode':
        world.hooks['context', 2] = lambda: world.model.context['mode'].update(blocking_state=2)
    elif change == 'window_hwnd':
        world.hooks['windows', 2] = lambda: world.windows[0][1].update(hwnd=303)
    else:
        world.hooks['watch', 2] = lambda: setattr(world, 'event', ('new-session-event',))
    with pytest.raises(ValueError):
        world.run()
    assert_failed_custody(world)
    assert len(world.receipt.features) == 4


@pytest.mark.parametrize('safe', [False, 1, None])
def test_owner_admission_rejection_precedes_first_getter_and_latches(world, safe):
    world.safe = safe
    with pytest.raises(ValueError, match='whole-session owner admission'):
        world.run()
    assert world.calls == ['safe'] and world.receipt.returned_reads == []
    assert world.receipt.pending_read is None
    assert_failed_custody(world)


def test_owner_loss_after_raw_getter_return_retains_return_before_next_dispatch(world):
    world.hooks['windows', 1] = lambda: setattr(world, 'safe', False)
    with pytest.raises(ValueError, match='whole-session owner admission'):
        world.run()
    assert world.receipt.returned_reads[-1] == ('whole_window_census', world.windows)
    assert world.receipt.returned_reads[-1][1] is world.windows
    assert world.counts.get('identity', 0) == 0
    assert_failed_custody(world)


def test_thread_change_after_normal_return_prevents_next_dispatch(world, monkeypatch):
    module = sys.modules[capture_empty_template.__module__]
    world.hooks['watch', 1] = lambda: monkeypatch.setattr(module, 'get_ident', lambda: -1)
    with pytest.raises(ValueError, match='foreign'):
        world.run()
    assert world.receipt.returned_reads == [('open_events', world.event)]
    assert world.calls == ['safe', 'watch']
    assert_failed_custody(world)


def test_getter_exception_keeps_pending_read_no_return_and_no_retry(world):
    def fail():
        raise RuntimeError('native read outcome unknown')
    world.hooks['features', 1] = fail
    with pytest.raises(RuntimeError, match='outcome unknown'):
        world.run()
    assert world.receipt.pending_read == 'complete_template_features'
    assert not any(label == 'complete_template_features' for label, _ in world.receipt.returned_reads)
    assert_failed_custody(world)
    before = tuple(world.calls), tuple(world.receipt.returned_reads)
    with pytest.raises(ValueError, match='Fresh'):
        world.run()
    assert before == (tuple(world.calls), tuple(world.receipt.returned_reads))


def test_raw_configuration_frame_and_features_remain_held_after_later_failure(world):
    world.hooks['watch', 2] = lambda: setattr(world, 'event', ('late-change',))
    with pytest.raises(ValueError, match='events changed'):
        world.run()
    reads = world.receipt.returned_reads
    assert next(value for label, value in reads if label == 'configuration_raw') is world.model.cfg
    assert next(value for label, value in reads if label == 'native_plane_frame') is world.model.features[1].frame
    census = next(value for label, value in reads if label == 'complete_template_features')
    assert all(raw is held.handle for raw, held in zip(census, world.receipt.features))
    assert world.receipt.pending_read is None
    assert_failed_custody(world)


def test_successful_receipt_cannot_be_reused_for_new_native_read(world):
    world.run()
    before = tuple(world.calls), tuple(world.receipt.returned_reads)
    with pytest.raises(ValueError, match='Fresh'):
        world.run()
    assert before == (tuple(world.calls), tuple(world.receipt.returned_reads))
