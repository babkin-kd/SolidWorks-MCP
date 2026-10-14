"""API-shaped application custody tests; no connection, COM or CAD calls."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys

import pytest

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_application_admission import (
        ApplicationAdmissionReceipt, EmptyApplicationBaseline,
        admit_fixture_application, capture_empty_application,
    )
    from verifier_b3_part_fixture import FixtureAnchor, PartFixtureReceipt
    from verify_export_operations import PREFS
finally:
    sys.path.remove(scripts)


STL = frozenset({
    'stl_units', 'stl_binary', 'stl_dont_translate_to_positive', 'stl_show_info',
    'stl_preview', 'stl_quality', 'stl_deviation', 'stl_angle',
})
NON_STL = frozenset({
    'coordinate_system', 'step_ap', 'step_geometry', 'step_curves',
    'step_appearances', 'step_face_edge_props', 'step_configuration_data',
    'step_split_periodic', 'step_atomic_save', 'parasolid_version', 'dimension_input',
})
SCALARS = {'String': 'Система координат', 'Integer': 7, 'Toggle': False, 'Double': .001}


class Native:
    def __init__(self, canonical):
        self.canonical = canonical
        # All models have identical names, paths and apparent geometry.
        self.Name, self.path, self.shape = 'Деталь', '', 'identical-box'


class Application(Native):
    def __init__(self, world):
        super().__init__('original-application')
        self.world, self.guard, self.active = world, False, None

    @property
    def CommandInProgress(self):
        return self.world.call('guard', lambda: self.guard)

    @property
    def ActiveDoc(self):
        return self.world.call('active', lambda: self.active)


class Adapter:
    def __init__(self, world):
        self.world, self._sw = world, Application(world)

    def identity(self, handle):
        return self.world.call('identity', lambda: handle.canonical)

    def documents(self):
        return self.world.call('models', lambda: self.world.models)

    def native_close_windows(self):
        return self.world.call('windows', lambda: self.world.windows)

    def native_close_application_context(self):
        return self.world.call('context', lambda: self.world.context)


class World:
    def __init__(self):
        self.calls, self.counts, self.hooks = [], {}, {}
        self.models, self.windows = [], []
        self.context = dict(user_control=True, visible=True,
                            current_directory='C:/Контроль', search_folders='C:/Библиотека')
        self.preferences = {name: SCALARS[kind] for name, (kind, _) in PREFS.items()}
        self.event, self.safe = ('original-session',), True
        self.adapter = Adapter(self)
        self.receipt = ApplicationAdmissionReceipt()

    def call(self, label, getter):
        self.calls.append(label)
        self.counts[label] = self.counts.get(label, 0) + 1
        hook = self.hooks.get((label, self.counts[label]))
        if hook:
            hook()
        return getter()

    def assert_safe(self):
        return self.call('safe', lambda: self.safe)

    def watch_poll(self):
        return self.call('watch', lambda: self.event)

    def preference_reader(self):
        return self.call('preferences', lambda: self.preferences)

    def capture(self, **overrides):
        args = dict(receipt=self.receipt, adapter=self.adapter,
                    preference_reader=self.preference_reader,
                    assert_safe=self.assert_safe, watch_poll=self.watch_poll)
        args.update(overrides)
        return capture_empty_application(**args)

    def prepare(self, prior_count=0):
        self.baseline = self.capture()
        self.baseline_receipt = self.receipt
        self.receipt = ApplicationAdmissionReceipt()
        self.fixture = PartFixtureReceipt('explicit-next-fixture')
        self.fixture.attempted = True
        self.fixture.pending_step = 'application:admission'
        self.prior_fixtures = []
        for index in range(prior_count):
            prior = PartFixtureReceipt('explicit-prior-' + str(index))
            prior.attempted = prior.setup_complete = True
            model = Native('original-model-' + str(index))
            role = ('Основная деталь', 'Сосед', 'Цилиндр')[index]
            prior.documents[role] = FixtureAnchor(role, 'document', model, model.canonical)
            label = 'cylinder:new_document' if role == 'Цилиндр' else role + ':new_document'
            prior.native_returns.append((1, label, model))
            self.models.append(model)
            self.windows.append((model, {'hwnd': 101 + index}))
            self.prior_fixtures.append(prior)
        self.prior_fixtures = tuple(self.prior_fixtures)
        self.adapter._sw.guard = True
        self.adapter._sw.active = self.models[-1] if self.models else None
        self.calls.clear()
        self.counts.clear()
        self.hooks.clear()

    def admit(self, **overrides):
        args = dict(receipt=self.receipt, baseline=self.baseline,
                    baseline_receipt=self.baseline_receipt, fixture=self.fixture,
                    prior_fixtures=self.prior_fixtures, adapter=self.adapter,
                    preference_reader=self.preference_reader,
                    assert_safe=self.assert_safe, watch_poll=self.watch_poll)
        args.update(overrides)
        return admit_fixture_application(**args)


@pytest.fixture
def world():
    return World()


def held(receipt):
    assert receipt.attempted and receipt.halted and not receipt.complete
    assert not receipt.accepted and not receipt.native_acceptance and not receipt.cleanup_authorized


def change_scalar(value):
    if type(value) is bool:
        return not value
    if type(value) is str:
        return value + ' изменена'
    return value + 1


def test_initial_baseline_captures_complete_typed_registry_and_copied_data(world):
    assert set(PREFS) == STL | NON_STL and len(STL) == 8
    baseline = world.capture()
    receipt = world.receipt
    assert type(baseline) is EmptyApplicationBaseline
    assert baseline.application is world.adapter._sw
    assert baseline.canonical == world.adapter._sw.canonical
    assert receipt.baseline is baseline
    assert baseline.context == world.context and baseline.context is not world.context
    assert baseline.preferences == world.preferences and baseline.preferences is not world.preferences
    assert receipt.baseline_data == (baseline.context, baseline.preferences)
    assert receipt.baseline_data[0] is not baseline.context
    assert receipt.baseline_data[1] is not baseline.preferences
    assert receipt.complete and not receipt.halted and receipt.pending_read is None
    assert not receipt.accepted and not receipt.native_acceptance and not receipt.cleanup_authorized
    assert world.counts['models'] == world.counts['windows'] == world.counts['preferences'] == 2
    assert world.counts['safe'] == len(receipt.returned_reads)
    assert next(raw for label, raw in receipt.returned_reads if label == 'application_preferences') is world.preferences
    facts = receipt.preference_evidence['initial_boundary']
    assert facts['scope_exactly_equal'] and facts['all_preferences_exactly_equal']
    assert set(facts['checked_fields']) == NON_STL
    assert set(facts['excluded_fields']) == STL
    assert not facts['stl_preferences_verified'] and not facts['cause_inferred']
    world.context['visible'] = False
    world.preferences['step_ap'] += 1
    assert baseline.context['visible'] is True and baseline.preferences['step_ap'] == 7


@pytest.mark.parametrize('count', [0, 1, 3])
def test_fixture_startup_under_owned_guard_preserves_prior_receipts_without_creation(world, count):
    world.prepare(count)
    prior_state = deepcopy([(p.request_id, p.pending_step, p.setup_complete) for p in world.prior_fixtures])
    raw_returns = [tuple(p.native_returns) for p in world.prior_fixtures]
    assert world.admit() is True
    assert world.fixture.pending_step == 'application:admission' and world.fixture.documents == {}
    assert prior_state == [(p.request_id, p.pending_step, p.setup_complete) for p in world.prior_fixtures]
    assert raw_returns == [tuple(p.native_returns) for p in world.prior_fixtures]
    assert world.receipt.complete and not world.receipt.halted and world.receipt.pending_read is None
    assert not world.receipt.accepted and not world.receipt.native_acceptance and not world.receipt.cleanup_authorized
    assert world.adapter._sw.guard is True
    assert set(world.receipt.preference_evidence) == {'baseline', 'closing'}
    for facts in world.receipt.preference_evidence.values():
        assert facts['scope_exactly_equal'] and set(facts['checked_fields']) == NON_STL
        assert set(facts['excluded_fields']) == STL and not facts['stl_preferences_verified']
    assert next(raw for label, raw in world.receipt.returned_reads if label == 'current_models') is world.models


@pytest.mark.parametrize('field', sorted(STL))
@pytest.mark.parametrize('boundary', ['initial', 'baseline', 'closing'])
def test_only_eight_explicit_stl_changes_are_deferred_with_full_evidence(world, field, boundary):
    if boundary != 'initial':
        world.prepare()
    occurrence = 1 if boundary == 'baseline' else 2
    world.hooks['preferences', occurrence] = lambda: world.preferences.update(
        {field: change_scalar(world.preferences[field])})
    (world.capture if boundary == 'initial' else world.admit)()
    facts = world.receipt.preference_evidence['initial_boundary' if boundary == 'initial' else boundary]
    assert facts['changed_fields'] == [field] and facts['scope_changed_fields'] == []
    assert facts['scope_exactly_equal'] and not facts['all_preferences_exactly_equal']
    assert not facts['stl_preferences_verified']
    assert facts['before'][field] != facts['after'][field]


@pytest.mark.parametrize('field', sorted(NON_STL))
@pytest.mark.parametrize('boundary', ['initial', 'baseline', 'closing'])
def test_each_non_stl_preference_is_checked_at_both_boundaries(world, field, boundary):
    if boundary != 'initial':
        world.prepare()
    world.hooks['preferences', 1 if boundary == 'baseline' else 2] = lambda: world.preferences.update(
        {field: change_scalar(world.preferences[field])})
    with pytest.raises(AssertionError, match='non-STL'):
        (world.capture if boundary == 'initial' else world.admit)()
    held(world.receipt)
    facts = world.receipt.preference_evidence['initial_boundary' if boundary == 'initial' else boundary]
    assert facts['scope_changed_fields'] == [field] and not facts['scope_exactly_equal']


@pytest.mark.parametrize('field', sorted(PREFS))
@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_every_declared_preference_requires_its_exact_native_scalar_type(world, field, mode):
    if mode == 'admit':
        world.prepare()
    kind = PREFS[field][0]
    world.preferences[field] = {'String': None, 'Integer': True, 'Toggle': 0, 'Double': 1}[kind]
    with pytest.raises(ValueError, match='strict scalar type'):
        (world.capture if mode == 'initial' else world.admit)()
    held(world.receipt)


@pytest.mark.parametrize('change', ['missing_stl', 'missing_non_stl', 'new_stl_name', 'new_field',
                                    'nan', 'infinity', 'nested', 'not_dict'])
@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_preference_inventory_cannot_be_partial_expanded_or_nonfinite(world, change, mode):
    if mode == 'admit':
        world.prepare()
    if change.startswith('missing'):
        world.preferences.pop('stl_angle' if change == 'missing_stl' else 'dimension_input')
    elif change.startswith('new'):
        world.preferences['stl_unreviewed' if change == 'new_stl_name' else 'other'] = False
    elif change in ('nan', 'infinity'):
        world.preferences['stl_deviation'] = float('nan' if change == 'nan' else 'inf')
    elif change == 'nested':
        world.preferences['step_ap'] = {'value': 7}
    else:
        world.preferences = list(world.preferences.items())
    with pytest.raises(ValueError):
        (world.capture if mode == 'initial' else world.admit)()
    held(world.receipt)


@pytest.mark.parametrize('change', ['guard', 'active', 'models', 'windows', 'weak_canonical'])
def test_initial_application_must_be_empty_idle_and_have_strong_identity(world, change):
    if change == 'guard':
        world.adapter._sw.guard = True
    elif change == 'active':
        world.adapter._sw.active = Native('foreign')
    elif change == 'models':
        world.models.append(Native('foreign'))
    elif change == 'windows':
        world.windows.append((Native('foreign'), {'hwnd': 501}))
    else:
        world.adapter._sw.canonical = None
    with pytest.raises(ValueError):
        world.capture()
    held(world.receipt)
    assert world.receipt.baseline is None and world.receipt.baseline_data is None


@pytest.mark.parametrize('guard', [1, None, 'False'])
def test_initial_guard_uses_exact_false(world, guard):
    world.adapter._sw.guard = guard
    with pytest.raises(ValueError, match='idle'):
        world.capture()
    held(world.receipt)


@pytest.mark.parametrize('guard', [False, 1, None, 'True'])
def test_later_guard_uses_exact_caller_owned_true(world, guard):
    world.prepare()
    world.adapter._sw.guard = guard
    with pytest.raises(ValueError, match='caller-owned guard'):
        world.admit()
    held(world.receipt)


@pytest.mark.parametrize('field', ['user_control', 'visible', 'current_directory', 'search_folders'])
@pytest.mark.parametrize('mode', ['initial_closing', 'admit'])
def test_all_application_context_fields_are_preserved(world, field, mode):
    if mode == 'admit':
        world.prepare()
    world.hooks['context', 1 if mode == 'admit' else 2] = lambda: world.context.update(
        {field: change_scalar(world.context[field])})
    with pytest.raises(ValueError, match='context'):
        (world.capture if mode == 'initial_closing' else world.admit)()
    held(world.receipt)


@pytest.mark.parametrize('change', ['bool_as_int', 'directory_not_string', 'search_not_string',
                                    'missing', 'extra', 'over_budget', 'not_dict'])
def test_initial_context_requires_complete_bounded_native_types(world, change):
    if change == 'bool_as_int':
        world.context['user_control'] = 1
    elif change == 'directory_not_string':
        world.context['current_directory'] = None
    elif change == 'search_not_string':
        world.context['search_folders'] = ['C:/library']
    elif change == 'missing':
        world.context.pop('visible')
    elif change == 'extra':
        world.context['extra'] = True
    elif change == 'over_budget':
        world.context['search_folders'] = 'x' * 4097
    else:
        world.context = tuple(world.context.items())
    with pytest.raises(ValueError, match='context'):
        world.capture()
    held(world.receipt)


@pytest.mark.parametrize('change', ['copied_baseline', 'wrong_receipt', 'incomplete', 'halted',
                                    'pending', 'baseline_sta', 'receipt_sta', 'typed_mutation',
                                    'context_mutation', 'partial_data'])
def test_baseline_is_linked_to_original_completed_same_sta_receipt_and_frozen_copy(world, change):
    world.prepare()
    overrides = {}
    if change == 'copied_baseline':
        overrides['baseline'] = replace(world.baseline)
    elif change == 'wrong_receipt':
        overrides['baseline_receipt'] = ApplicationAdmissionReceipt()
    elif change == 'incomplete':
        world.baseline_receipt.complete = False
    elif change == 'halted':
        world.baseline_receipt.halted = True
    elif change == 'pending':
        world.baseline_receipt.pending_read = 'unknown-read'
    elif change == 'baseline_sta':
        changed = replace(world.baseline, thread_id=-1)
        world.baseline_receipt.baseline = changed
        overrides['baseline'] = changed
    elif change == 'receipt_sta':
        world.baseline_receipt.thread_id = -1
    elif change == 'typed_mutation':
        world.baseline.preferences['stl_deviation'] = 0
        world.baseline_receipt.baseline_data[1]['stl_deviation'] = 0.0
    elif change == 'context_mutation':
        world.baseline.context['visible'] = False
    else:
        world.baseline_receipt.baseline_data = (world.baseline.context, {})
    with pytest.raises(ValueError):
        world.admit(**overrides)
    assert world.calls == [] and not world.receipt.attempted


@pytest.mark.parametrize('change', ['unattempted', 'halted', 'lost_journal', 'pending_none',
                                    'pending_creation', 'foreign_sta', 'already_created'])
def test_new_fixture_is_pending_application_admission_before_new_document(world, change):
    world.prepare()
    if change == 'unattempted':
        world.fixture.attempted = False
    elif change == 'halted':
        world.fixture.halted = True
    elif change == 'lost_journal':
        world.fixture.journal_lost = True
    elif change.startswith('pending'):
        world.fixture.pending_step = None if change == 'pending_none' else 'Деталь:new_document'
    elif change == 'foreign_sta':
        world.fixture.thread_id = -1
    else:
        world.fixture.documents['Деталь'] = FixtureAnchor('Деталь', 'document', Native('new'), 'new')
    with pytest.raises(ValueError):
        world.admit()
    assert not world.calls and not world.receipt.attempted


@pytest.mark.parametrize('change', ['unattempted', 'incomplete', 'halted', 'lost_journal', 'pending',
                                    'foreign_sta', 'no_returns', 'list',
                                    'same_receipt', 'too_many', 'wrong_anchor_kind', 'weak_anchor'])
def test_prior_receipt_requires_completed_acknowledged_original_document_custody(world, change):
    world.prepare(1)
    prior = world.prior_fixtures[0]
    overrides = {}
    if change == 'unattempted':
        prior.attempted = False
    elif change == 'incomplete':
        prior.setup_complete = False
    elif change == 'halted':
        prior.halted = True
    elif change == 'lost_journal':
        prior.journal_lost = True
    elif change == 'pending':
        prior.pending_step = 'unknown-native-call'
    elif change == 'foreign_sta':
        prior.thread_id = -1
    elif change == 'no_returns':
        prior.native_returns.clear()
    elif change == 'list':
        overrides['prior_fixtures'] = list(world.prior_fixtures)
    elif change == 'same_receipt':
        overrides['prior_fixtures'] = (world.fixture,)
    elif change == 'too_many':
        overrides['prior_fixtures'] = (prior,) * 4
    else:
        role, anchor = next(iter(prior.documents.items()))
        prior.documents[role] = replace(anchor, **({'kind': 'feature'} if change == 'wrong_anchor_kind' else {'canonical': None}))
    with pytest.raises(ValueError):
        world.admit(**overrides)
    assert not world.calls and not world.receipt.attempted


def test_completed_prior_without_documents_cannot_be_accepted_from_unrelated_normal_return(world):
    world.prepare()
    prior = PartFixtureReceipt('claimed-completed-but-empty')
    prior.attempted = prior.setup_complete = True
    prior.native_returns.append((1, 'unrelated:getter', Native('unowned-return')))
    assert prior.documents == {} and prior.native_returns
    with pytest.raises(ValueError, match='Completed acknowledged earlier original fixtures'):
        world.admit(prior_fixtures=(prior,))
    assert world.calls == [] and not world.receipt.attempted
    assert world.receipt.returned_reads == []
    assert not world.receipt.complete and not world.receipt.accepted


@pytest.mark.parametrize('change', ['wrong_label', 'missing', 'duplicate', 'null', 'foreign_raw',
                                    'not_list', 'bad_row', 'bad_index', 'bool_index', 'bad_label',
                                    'unknown_role'])
def test_previous_creation_must_have_exactly_one_actual_normal_return(world, change):
    world.prepare(1)
    prior = world.prior_fixtures[0]
    row = prior.native_returns[0]
    if change == 'wrong_label':
        prior.native_returns[0] = (1, 'same-shape:new_document', row[2])
    elif change == 'missing':
        prior.native_returns[:] = [(1, 'unrelated:getter', True)]
    elif change == 'duplicate':
        prior.native_returns.append(row)
    elif change == 'null':
        prior.native_returns[0] = (1, row[1], None)
    elif change == 'foreign_raw':
        prior.native_returns[0] = (1, row[1], Native('same-looking-unreturned-model'))
    elif change == 'not_list':
        prior.native_returns = tuple(prior.native_returns)
    elif change == 'bad_row':
        prior.native_returns[0] = (1, row[1])
    elif change in ('bad_index', 'bool_index'):
        prior.native_returns[0] = (0 if change == 'bad_index' else True, row[1], row[2])
    elif change == 'bad_label':
        prior.native_returns[0] = (1, None, row[2])
    else:
        anchor = prior.documents.pop('Основная деталь')
        prior.documents['Та же форма'] = anchor
    with pytest.raises(ValueError):
        world.admit()
    held(world.receipt)
    assert world.receipt.returned_reads[0] == ('open_events', world.event)
    assert 'models' not in world.calls


@pytest.mark.parametrize('field,value', [('thread_id', -1), ('attempted', True), ('halted', True),
                                        ('pending_read', 'unknown'), ('returned_reads', [('held', object())]),
                                        ('complete', True), ('accepted', True), ('native_acceptance', True),
                                        ('cleanup_authorized', True)])
@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_admission_receipt_must_be_fresh_same_sta_and_without_acceptance_flags(world, field, value, mode):
    if mode == 'admit':
        world.prepare()
    setattr(world.receipt, field, value)
    with pytest.raises(ValueError, match='Fresh'):
        (world.capture if mode == 'initial' else world.admit)()
    assert world.calls == []


@pytest.mark.parametrize('change', ['foreign_model', 'missing_model', 'duplicate_model',
                                    'replaced_original', 'missing_window', 'foreign_window',
                                    'duplicate_window_model', 'duplicate_hwnd', 'foreign_active',
                                    'missing_active', 'undeclared_prior', 'duplicate_prior'])
def test_exact_models_windows_active_and_prior_roster_prohibit_shape_or_name_adoption(world, change):
    world.prepare(2)
    original, other = world.models
    foreign = Native('foreign-but-identical-looking')
    assert foreign.Name == original.Name and foreign.shape == original.shape
    overrides = {}
    if change == 'foreign_model':
        world.models[0] = foreign
    elif change == 'missing_model':
        world.models.pop()
    elif change == 'duplicate_model':
        world.models[1] = original
    elif change == 'replaced_original':
        original.canonical = 'new-incarnation'
    elif change == 'missing_window':
        world.windows.pop()
    elif change == 'foreign_window':
        world.windows[0] = (foreign, {'hwnd': 101})
    elif change == 'duplicate_window_model':
        world.windows[1] = (original, {'hwnd': 102})
    elif change == 'duplicate_hwnd':
        world.windows[1] = (other, {'hwnd': 101})
    elif change == 'foreign_active':
        world.adapter._sw.active = foreign
    elif change == 'missing_active':
        world.adapter._sw.active = None
    elif change == 'undeclared_prior':
        overrides['prior_fixtures'] = world.prior_fixtures[:1]
    else:
        overrides['prior_fixtures'] = (world.prior_fixtures[0],) * 2
    with pytest.raises(ValueError):
        world.admit(**overrides)
    held(world.receipt)


@pytest.mark.parametrize('hwnd', [None, True, False, 0, -1, 2**63, 101., '101'])
def test_window_hwnd_is_strict_positive_bounded_native_integer(world, hwnd):
    world.prepare(1)
    world.windows[0][1]['hwnd'] = hwnd
    with pytest.raises(ValueError, match='window'):
        world.admit()
    held(world.receipt)


@pytest.mark.parametrize('target', ['models', 'windows'])
@pytest.mark.parametrize('value', [None, False, {}, ''])
@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_complete_rosters_require_actual_tuple_or_list_even_when_empty(world, target, value, mode):
    if mode == 'admit':
        world.prepare()
    setattr(world, target, value)
    with pytest.raises(ValueError, match='census|roster'):
        (world.capture if mode == 'initial' else world.admit)()
    held(world.receipt)


def test_first_fixture_cannot_adopt_active_document_outside_empty_roster(world):
    world.prepare()
    world.adapter._sw.active = Native('foreign')
    with pytest.raises(ValueError, match='Active document'):
        world.admit()
    held(world.receipt)


def test_current_active_may_be_either_exact_original_and_tuple_rosters_are_supported(world):
    world.prepare(2)
    world.models, world.windows = tuple(world.models), tuple(world.windows)
    world.hooks['active', 2] = lambda: setattr(world.adapter._sw, 'active', world.models[0])
    assert world.admit() is True
    assert world.receipt.complete


@pytest.mark.parametrize('callback', ['preference_reader', 'watch_poll', 'assert_safe'])
@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_missing_required_reader_or_owner_callback_rejects_without_native_dispatch(world, callback, mode):
    if mode == 'admit':
        world.prepare()
    with pytest.raises(ValueError):
        (world.capture if mode == 'initial' else world.admit)(**{callback: None})
    assert not world.calls and not world.receipt.attempted


@pytest.mark.parametrize('change', ['handle', 'canonical'])
def test_application_incarnation_cannot_be_adopted_even_with_same_context(world, change):
    world.prepare()
    if change == 'handle':
        new = Application(world)
        new.guard = True
        assert new.canonical == world.baseline.canonical
        world.adapter._sw = new
    else:
        world.adapter._sw.canonical = 'replacement-application'
    with pytest.raises(ValueError, match='application'):
        world.admit()
    held(world.receipt)


@pytest.mark.parametrize('change', ['guard', 'canonical', 'models', 'windows', 'context', 'events'])
@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_closing_boundary_rejects_session_changes(world, change, mode):
    if mode == 'admit':
        world.prepare(1)
    if change == 'guard':
        world.hooks['guard', 2] = lambda: setattr(world.adapter._sw, 'guard', mode == 'initial')
    elif change == 'canonical':
        world.hooks['guard', 1] = lambda: setattr(world.adapter._sw, 'canonical', 'changed')
    elif change == 'models':
        world.hooks['models', 2] = lambda: world.models.append(Native('foreign'))
    elif change == 'windows':
        world.hooks['windows', 2] = (lambda: world.windows[0][1].update(hwnd=301)) if mode == 'admit' else (
            lambda: world.windows.append((Native('foreign'), {'hwnd': 301})))
    elif change == 'context':
        world.hooks['context', 2] = lambda: world.context.update(visible=False)
    else:
        world.hooks['watch', 2] = lambda: setattr(world, 'event', ('changed-session',))
    with pytest.raises(ValueError):
        (world.capture if mode == 'initial' else world.admit)()
    held(world.receipt)


@pytest.mark.parametrize('safe', [False, 1, None])
@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_owner_rejection_precedes_first_native_read_and_latches(world, safe, mode):
    if mode == 'admit':
        world.prepare()
    world.safe = safe
    with pytest.raises(ValueError, match='root process/STA/session'):
        (world.capture if mode == 'initial' else world.admit)()
    assert world.calls == ['safe'] and not world.receipt.returned_reads
    assert world.receipt.pending_read is None
    held(world.receipt)


@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_owner_loss_after_raw_normal_return_retains_custody_before_next_dispatch(world, mode):
    if mode == 'admit':
        world.prepare(1)
    world.hooks['windows', 1] = lambda: setattr(world, 'safe', False)
    with pytest.raises(ValueError, match='root process/STA/session'):
        (world.capture if mode == 'initial' else world.admit)()
    assert world.receipt.returned_reads[-1][1] is world.windows
    assert world.receipt.pending_read is None
    held(world.receipt)


@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_sta_loss_after_normal_return_stops_before_next_dispatch(world, monkeypatch, mode):
    if mode == 'admit':
        world.prepare()
    module = sys.modules[capture_empty_application.__module__]
    world.hooks['watch', 1] = lambda: monkeypatch.setattr(module, 'get_ident', lambda: -1)
    with pytest.raises(ValueError, match='foreign'):
        (world.capture if mode == 'initial' else world.admit)()
    assert world.calls == ['safe', 'watch']
    assert world.receipt.returned_reads == [('open_events', world.event)]
    held(world.receipt)


@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_unknown_native_read_stays_pending_and_cannot_be_retried(world, mode):
    if mode == 'admit':
        world.prepare()

    def fail():
        raise RuntimeError('read outcome unknown')

    world.hooks['preferences', 1] = fail
    run = world.capture if mode == 'initial' else world.admit
    with pytest.raises(RuntimeError, match='outcome unknown'):
        run()
    assert world.receipt.pending_read == 'application_preferences'
    assert not any(label == 'application_preferences' for label, _ in world.receipt.returned_reads)
    held(world.receipt)
    before = tuple(world.calls), tuple(world.receipt.returned_reads)
    with pytest.raises(ValueError, match='Fresh'):
        run()
    assert before == (tuple(world.calls), tuple(world.receipt.returned_reads))


@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_late_event_failure_keeps_all_raw_returns_without_acceptance(world, mode):
    if mode == 'admit':
        world.prepare(1)
    world.hooks['watch', 2] = lambda: setattr(world, 'event', ('late-event',))
    with pytest.raises(ValueError, match='event'):
        (world.capture if mode == 'initial' else world.admit)()
    reads = world.receipt.returned_reads
    assert next(raw for label, raw in reads if label == 'application_context') is world.context
    assert next(raw for label, raw in reads if label == 'application_preferences') is world.preferences
    assert world.receipt.pending_read is None and reads[-1] == ('close_events', world.event)
    held(world.receipt)


@pytest.mark.parametrize('mode', ['initial', 'admit'])
def test_complete_receipt_cannot_authorize_new_reads(world, mode):
    if mode == 'admit':
        world.prepare()
    run = world.capture if mode == 'initial' else world.admit
    run()
    before = tuple(world.calls), tuple(world.receipt.returned_reads)
    with pytest.raises(ValueError, match='Fresh'):
        run()
    assert before == (tuple(world.calls), tuple(world.receipt.returned_reads))
