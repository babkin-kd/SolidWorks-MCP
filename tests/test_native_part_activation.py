"""Real activation domain/journal with full artificial oracles; no CAD claim."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.native_part_activation import NativePartActivationCatalog, SCOPE
from test_native_first_save import FirstSaveAdapter
from test_native_first_save_full_capture import capture
from test_native_document_close_v2 import Worker


class ActivationAdapter(FirstSaveAdapter):
    def first_save_part_snapshot(self, current):
        self.alive(current)
        self.snapshot_reads += 1
        result = deepcopy(self.complete_snapshot)
        result['selection_count'] = len(current.view['selection'])
        result['configuration'] = current.state['active_configuration']
        result['configurations'] = list(current.state['configurations'])
        namespace = current.state['title']
        old = result['native_observations']['document_dimension_namespace']
        result['native_observations']['document_dimension_namespace'] = namespace
        for row in result['native_observations']['qualified_dimensions']:
            row['full_name'] = row['full_name'].replace('@' + old + '.Part', '@' + namespace + '.Part')
        for row in result['references']:
            row['token'] = namespace + ':' + row['token']
        result['clone_state'].update(deepcopy(self.oracle_states.get(current.identity, {})))
        if self.bad_snapshot:
            result.pop('native_observations')
        return result

    def activate_native_open_document(self, receipt):
        if self.open_fault == 'activation_error':
            assert self.busy and not receipt.native_call_attempted
            assert self.checkpoint_lookup()['mutation']['verification']['native_steps'][-1]['phase'] == 'pending'
            self.activations.append(receipt.model)
            receipt.native_call_attempted, receipt.native_call_returned = True, True
            receipt.pending_activation, receipt.native_error = False, 1
            raise ExecutionFailure('native_open_activation_unconfirmed', 'Artificial normal native error.', uncertain=False)
        super().activate_native_open_document(receipt)
        if self.open_fault == 'geometry_after':
            self.oracle_states[self.neighbor.identity] = {'injected_geometry_change': True}
        elif self.open_fault == 'dirty_after':
            self.neighbor.state['needs_save'] = False
        elif self.open_fault == 'file_after':
            Path(self.neighbor.state['path']).write_bytes(b'artificial foreign bytes')
        elif self.open_fault == 'cwd_after':
            self.app['current_directory'] = str(self.folder / 'foreign')

    def native_open_guard(self, models, document_ids):
        guard = super().native_open_guard(models, document_ids)
        adapter = self

        class OwnedGuard:
            def __enter__(self):
                guard.__enter__()
                return self

            def __exit__(self, *args):
                result = guard.__exit__(*args)
                if adapter.open_fault == 'guard_release_throw':
                    raise RuntimeError('Artificial guard release acknowledgement lost after effect')
                if adapter.open_fault == 'release_after':
                    adapter.neighbor.view['scale'] = 7.
                return result

            def release_baseline_ui_for_activation(self):
                return guard.release_baseline_ui_for_activation()

            @property
            def evidence(self):
                return guard.evidence

        return OwnedGuard()


@pytest.fixture
def setup(tmp_path, capture):
    adapter = ActivationAdapter(tmp_path)
    adapter.complete_snapshot = capture.first_save_part_snapshot(capture.model)
    adapter.snapshot_reads, adapter.bad_snapshot = 0, False
    target = adapter.add('Контрольная пластина')
    neighbor = adapter.add('Рабочая соседняя деталь')
    adapter.neighbor = neighbor
    for current in (target, neighbor):
        current.state.update(configurations=['Основная'], needs_save=True)
    neighbor.view['selection'] = ['Исходное выделение']
    adapter.active = neighbor
    documents = DocumentCatalog(adapter)
    document_id = next(row['document_id'] for row in documents.list()['documents'] if row['title'] == target.state['title'])
    store = JobStore(tmp_path / 'activation.sqlite')
    domain = NativePartActivationCatalog(documents, store, 'epoch-one')
    runner = JobRunner(store, Worker())
    state = SimpleNamespace(adapter=adapter, target=target, neighbor=neighbor, documents=documents,
                            domain=domain, document_id=document_id, store=store, runner=runner)
    yield state
    store.close()


def prepared(x):
    return x.domain.prepare_activation(x.document_id, 'Основная')


def run(x, request_id='activate', revision=None, **changed):
    arguments = dict(document_id=x.document_id, configuration='Основная',
                     expected_revision=revision or prepared(x)['revision'])
    arguments.update(changed)
    x.adapter.checkpoint_lookup = lambda: next(row for row in x.store.list()['items'] if row['request_id'] == request_id)
    job = x.runner.submit(request_id, 'document.activate_part_native',
        arguments, lambda operation_id: x.domain.activate(operation_id, **arguments),
        context=arguments, mutates=True, pass_operation_id=True,
        verify=lambda result: result['verified'] is True)
    return x.store.get(job['operation_id'])


def test_prepare_and_success_preserve_full_data_and_record_post_release_proof(setup):
    x = setup
    before = (deepcopy(x.neighbor.state), deepcopy(x.neighbor.view), Path(x.neighbor.state['path']).read_bytes())
    p = prepared(x)
    assert p['revision_scope'] == SCOPE and p['already_active'] is False
    assert x.adapter.active is x.neighbor and not x.adapter.activations
    result = run(x, revision=p['revision'])
    assert result['status'] == 'succeeded', result
    assert result['mutation']['phase'] == 'committed'
    assert x.adapter.active is x.target and x.adapter.activations == [x.target]
    assert x.adapter.release_calls == 1 and not x.adapter.busy
    assert (x.neighbor.state, x.neighbor.view, Path(x.neighbor.state['path']).read_bytes()) == before
    steps = result['mutation']['verification']['native_steps']
    assert steps[-1]['name'] == 'part_activation_released_check' and steps[-1]['evidence']['verified'] is True
    assert result['result']['execution_guard']['native_guard']['released'] is True
    assert not x.domain.receipts


def test_replay_and_request_conflict_never_repeat_activation(setup):
    x = setup
    revision = prepared(x)['revision']
    first = run(x, revision=revision)
    assert run(x, revision=revision) == first
    from solidworks_mcp.jobs import JobError
    with pytest.raises(JobError, match='different'):
        run(x, revision='rev_different')
    assert x.adapter.activations == [x.target]


def test_already_active_has_verified_noop_and_no_native_activation(setup):
    x = setup
    x.adapter.active = x.target
    assert prepared(x)['already_active'] is True
    result = run(x)
    assert result['status'] == 'succeeded', result
    assert result['result']['value']['native_call_attempted'] is False
    assert not x.adapter.activations and x.adapter.release_calls == 0


@pytest.mark.parametrize('change', ['geometry', 'dirty', 'view', 'file', 'active'])
def test_stale_full_baseline_is_refused_before_activation(setup, change):
    x = setup
    revision = prepared(x)['revision']
    if change == 'geometry': x.adapter.oracle_states[x.neighbor.identity] = {'injected_geometry_change': True}
    if change == 'dirty': x.neighbor.state['needs_save'] = False
    if change == 'view': x.neighbor.view['scale'] = 3.
    if change == 'file': Path(x.neighbor.state['path']).write_bytes(b'changed native bytes')
    if change == 'active': x.adapter.active = x.target
    result = run(x, revision=revision)
    assert result['status'] == 'failed' and result['error']['code'] == 'stale_revision'
    assert not x.adapter.activations and not x.adapter.busy


@pytest.mark.parametrize('fault', ['activation_throw', 'activation_no_effect', 'geometry_after',
                                 'dirty_after', 'file_after', 'cwd_after', 'release_after', 'release_throw',
                                 'release_foreign', 'guard_release_throw'])
def test_unknown_preserves_application_hold_and_does_not_activate_back(setup, fault):
    x = setup
    revision = prepared(x)['revision']
    x.adapter.open_fault = fault
    result = run(x, revision=revision)
    assert result['status'] == 'unknown', result
    assert result['mutation']['phase'] == 'unresolved'
    assert result['error']['requires_reconciliation'] is True
    assert run(x, revision=revision) == result
    count = len(x.adapter.activations)
    held = run(x, request_id='another', revision=revision)
    assert held['error']['code'] == 'document_mutation_blocked'
    assert len(x.adapter.activations) == count <= 1
    assert x.store.mutation_blockers('new-epoch', x.document_id)
    assert result['operation_id'] in x.domain.receipts


def test_normal_native_error_with_full_unchanged_baseline_is_known_no_effect(setup):
    x = setup
    x.adapter.open_fault = 'activation_error'
    result = run(x)
    assert result['status'] == 'failed', result
    assert result['mutation']['phase'] == 'rolled_back'
    assert x.adapter.active is x.neighbor and x.adapter.activations == [x.target]
    assert not x.store.mutation_blockers('epoch-one', x.document_id)
    assert not x.domain.receipts


@pytest.mark.parametrize('name,phase', [('part_activation_native', 'pending'),
                                      ('part_activation_native', 'returned'),
                                      ('part_activation_guard_release', 'returned')])
def test_lost_journal_ack_keeps_hold_and_never_repeats_effect_or_release(setup, monkeypatch, name, phase):
    x = setup
    original = x.store.record_mutation_step
    failures = []

    def record(operation_id, **kwargs):
        original(operation_id, **kwargs)
        if (kwargs['name'], kwargs['phase']) == (name, phase):
            failures.append(True)
            raise OSError('Artificial lost journal acknowledgement after durable write')

    monkeypatch.setattr(x.store, 'record_mutation_step', record)
    result = run(x)
    assert failures == [True] and result['status'] == 'unknown', result
    assert result['mutation']['phase'] == 'unresolved'
    assert len(x.adapter.activations) <= 1
    assert not x.adapter.busy
    retained = x.domain.receipts[result['operation_id']]
    assert retained['guard_release_attempted'] is True and retained['guard_released'] is True
    assert retained['journal_failed'] is True
    assert x.store.mutation_blockers('epoch-one', x.document_id)


@pytest.mark.parametrize('unsupported', ['readonly', 'hidden', 'multiconfig', 'bad_snapshot', 'duplicate_title', 'profile'])
def test_unsupported_profile_never_activates(setup, unsupported):
    x = setup
    if unsupported == 'readonly': x.target.mode['read_only_state'] = 1
    if unsupported == 'hidden': x.adapter.windows = [(m,w) for m,w in x.adapter.windows if m is not x.target]
    if unsupported == 'multiconfig': x.target.state['configurations'].append('Другая')
    if unsupported == 'bad_snapshot': x.adapter.bad_snapshot = True
    if unsupported == 'duplicate_title': x.target.state['title'] = x.neighbor.state['title']
    if unsupported == 'profile': x.adapter.oracle_states[x.target.identity] = {'profile': 'other'}
    with pytest.raises(ExecutionFailure):
        prepared(x)
    assert not x.adapter.activations
