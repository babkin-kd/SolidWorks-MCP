"""Actual SQLite/JobStore restart receipts; no CAD/process/native acceptance."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from solidworks_mcp.jobs import JobError, JobStore


spec = importlib.util.spec_from_file_location('_b4_recovery_tests',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_b4_recovery.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

CONTEXT = dict(document_id='own_part', configuration='Основная', expected_revision='rev_before')


@pytest.fixture
def recovered(tmp_path):
    path = tmp_path / 'jobs.sqlite'
    store = JobStore(path)
    try:
        # Real terminal histories and a queued read coexist with one uncertain
        # application mutation, so scope and history checks cannot be vacuous.
        for name, status in (('success', 'succeeded'), ('failure', 'failed')):
            job, _ = store.create(name, 'feature.inspect', {'mode': name})
            store.start(job['operation_id'])
            store.finish(job['operation_id'], status, result={'rows': [name]},
                         error={'code': 'known_rejection'} if status == 'failed' else None)
        cancelled, _ = store.create('cancelled', 'feature.inspect', {})
        store.cancel(cancelled['operation_id'])
        store.create('queued-read', 'feature.inspect', {})
        job, _ = store.create('write', 'dimension.set_value', {'value_mm': 12}, CONTEXT, mutates=True)
        store.start(job['operation_id'])
        store.prepare_mutation(job['operation_id'], connection_epoch='epoch_old', **CONTEXT,
            before_state={'affected_objects': ['feature_pid', 'dimension_pid'],
                          'document_snapshot': {'length_mm': 10, 'neighbor_dirty': True}},
            effect_scope='application')
        store.record_mutation_step(job['operation_id'], name='dimension_set', phase='pending',
                                   evidence={'target': 'dimension_pid', 'value_mm': 12})
        store.record_mutation_step(job['operation_id'], name='dimension_set', phase='returned',
                                   evidence={'ack': True, 'value_mm': 12})
        before = helper.read_journal(path)
    finally:
        store.close()
    after_store = JobStore(path)
    try:
        after = helper.read_journal(path)
        queries = helper.required_hold_queries(before, new_epoch='epoch_new', other_document='other_part')
        observations = [{**query, 'blockers': after_store.mutation_blockers(**query)} for query in queries]
        yield dict(before=before, after=after, hold_observations=observations,
                   new_epoch='epoch_new', other_document='other_part'), after_store, path
    finally:
        after_store.close()


def by_request(rows, request):
    return next(row for row in rows if row['request_id'] == request)


def test_actual_recovery_preserves_exact_scope_ledger_history_and_holds(recovered):
    receipt, store, path = recovered
    proof = helper.validate_restart_receipts(**receipt)
    assert proof['accepted'] is True
    assert proof['native_b4_accepted'] is False
    assert proof['process_stop_authorized'] is False
    assert proof['cad_cleanup_authorized'] is False
    assert proof['job_count'] == 5
    assert len(proof['recovered_operation_ids']) == 2
    assert helper.read_journal(path) == receipt['after']  # The predicate was passive.
    for name in ('success', 'failure', 'cancelled'):
        assert by_request(receipt['before'], name) == by_request(receipt['after'], name)
    write = by_request(receipt['after'], 'write')
    assert write['status'] == 'unknown'
    assert write['mutation']['phase'] == 'unresolved'
    assert len(write['mutation']['verification']['native_steps']) == 2


def test_replay_actual_store_returns_same_unknown_without_new_ledger_or_job(recovered):
    receipt, store, path = recovered
    prior = by_request(receipt['after'], 'write')
    replay, created = store.create('write', 'dimension.set_value', {'value_mm': 12}, CONTEXT, mutates=True)
    assert created is False
    assert replay['operation_id'] == prior['operation_id']
    assert replay['status'] == 'unknown'
    assert store.start(replay['operation_id']) is False
    assert helper.read_journal(path) == receipt['after']
    with pytest.raises(JobError) as error:
        store.create('write', 'dimension.set_value', {'value_mm': 14}, CONTEXT, mutates=True)
    assert error.value.code == 'request_conflict'
    assert helper.validate_restart_receipts(**receipt)['accepted']


@pytest.mark.parametrize('epoch', ['epoch_old', 'epoch_new', 'third_epoch'])
def test_actual_application_hold_rejects_other_document_and_new_request_epoch(recovered, epoch):
    receipt, store, path = recovered
    assert store.mutation_blockers(epoch, 'other_part')
    context = {**CONTEXT, 'document_id': 'other_part'}
    job, _ = store.create('new_request', 'dimension.set_value', {'value_mm': 11}, context, mutates=True)
    store.start(job['operation_id'])
    with pytest.raises(JobError) as error:
        store.prepare_mutation(job['operation_id'], connection_epoch=epoch, **context, before_state={})
    assert error.value.code == 'document_mutation_blocked'
    assert 'mutation' not in store.get(job['operation_id'])
    assert by_request(helper.read_journal(path), 'write') == by_request(receipt['after'], 'write')
    # A new attempted job is outside this finite observation window, even when
    # it was correctly blocked. It cannot be silently excluded from raw rows.
    with pytest.raises(ValueError, match='extra journal'):
        helper.validate_restart_receipts(**{**receipt, 'after': helper.read_journal(path)})


@pytest.mark.parametrize('mutation', [
    'missing_job', 'extra_job', 'duplicate_job', 'duplicate_request', 'missing_digest',
    'payload_change', 'digest_change', 'operation_change', 'request_change',
    'created_at_change', 'status_success', 'status_running', 'status_queued', 'result_change',
    'restart_error_change', 'timestamp_backwards', 'checkpoint_missing', 'checkpoint_scope',
    'checkpoint_configuration', 'checkpoint_revision', 'checkpoint_epoch', 'checkpoint_before',
    'checkpoint_hold_scope', 'checkpoint_affected', 'checkpoint_time', 'checkpoint_phase',
    'checkpoint_verification', 'checkpoint_reconciliation', 'native_replay', 'native_pending_removed',
    'historical_success_status', 'historical_success_result', 'historical_failure_error',
    'historical_cancel_timestamp', 'before_payload_corrupt',
])
def test_adversarial_receipts_are_rejected(recovered, mutation):
    receipt = deepcopy(recovered[0])
    row = by_request(receipt['after'], 'write')
    checkpoint = row['mutation']
    if mutation == 'missing_job': receipt['after'].pop(0)
    elif mutation == 'extra_job':
        extra = deepcopy(receipt['after'][0]); extra.update(operation_id='extra', request_id='extra')
        receipt['after'].append(extra)
    elif mutation == 'duplicate_job': receipt['after'].append(deepcopy(row))
    elif mutation == 'duplicate_request': receipt['after'][0]['request_id'] = 'write'
    elif mutation == 'missing_digest': row.pop('digest')
    elif mutation == 'payload_change': row['payload']['arguments']['value_mm'] = 15
    elif mutation == 'digest_change': row['digest'] = '0' * 64
    elif mutation == 'operation_change': row['operation'] = 'feature.delete'
    elif mutation == 'request_change': row['request_id'] = 'replay_id'
    elif mutation == 'created_at_change': row['created_at'] -= 1
    elif mutation.startswith('status_'): row['status'] = mutation.removeprefix('status_').replace('success', 'succeeded')
    elif mutation == 'result_change': row['result'] = {'assumed_success': True}
    elif mutation == 'restart_error_change': row['error']['message'] = 'safe to retry'
    elif mutation == 'timestamp_backwards': row['updated_at'] = row['created_at'] - 1
    elif mutation == 'checkpoint_missing': row['mutation'] = None
    elif mutation == 'checkpoint_scope': checkpoint['document_id'] = 'other_part'
    elif mutation == 'checkpoint_configuration': checkpoint['configuration'] = 'Другая'
    elif mutation == 'checkpoint_revision': checkpoint['expected_revision'] = 'new_rev'
    elif mutation == 'checkpoint_epoch': checkpoint['connection_epoch'] = 'epoch_new'
    elif mutation == 'checkpoint_before': checkpoint['before_state']['document_snapshot']['length_mm'] = 12
    elif mutation == 'checkpoint_hold_scope': checkpoint['before_state'].pop('_mutation_effect_scope')
    elif mutation == 'checkpoint_affected': checkpoint['before_state']['affected_objects'].pop()
    elif mutation == 'checkpoint_time': checkpoint['updated_at'] += 1
    elif mutation == 'checkpoint_phase': checkpoint['phase'] = 'committed'
    elif mutation == 'checkpoint_verification': checkpoint['verification']['outcome'] = 'committed'
    elif mutation == 'checkpoint_reconciliation': checkpoint['reconciliation'] = {'resolution': 'accept_current_state'}
    elif mutation == 'native_replay': checkpoint['verification']['native_steps'] += deepcopy(checkpoint['verification']['native_steps'])
    elif mutation == 'native_pending_removed': checkpoint['verification']['native_steps'].pop(0)
    elif mutation == 'historical_success_status': by_request(receipt['after'], 'success')['status'] = 'unknown'
    elif mutation == 'historical_success_result': by_request(receipt['after'], 'success')['result'] = None
    elif mutation == 'historical_failure_error': by_request(receipt['after'], 'failure')['error'] = None
    elif mutation == 'historical_cancel_timestamp': by_request(receipt['after'], 'cancelled')['updated_at'] += 1
    elif mutation == 'before_payload_corrupt': by_request(receipt['before'], 'write')['payload']['arguments']['value_mm'] = 9
    else: pytest.fail(mutation)
    with pytest.raises(ValueError):
        helper.validate_restart_receipts(**receipt)


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'duplicate', 'bypass', 'partial', 'wrong_scope', 'forged_epoch'])
def test_mandatory_observed_hold_queries_cannot_be_weakened(recovered, mutation):
    receipt = deepcopy(recovered[0])
    observations = receipt['hold_observations']
    if mutation == 'missing': observations.pop()
    elif mutation == 'extra': observations.append(deepcopy(observations[0]))
    elif mutation == 'duplicate': observations[-1] = deepcopy(observations[0])
    elif mutation == 'bypass': observations[0]['blockers'] = []
    elif mutation == 'partial': observations[0]['blockers'][0].pop('before_state')
    elif mutation == 'wrong_scope': observations[0]['effect_scope'] = 'unsupported'
    elif mutation == 'forged_epoch': receipt['new_epoch'] = 'epoch_old'
    with pytest.raises(ValueError):
        helper.validate_restart_receipts(**receipt)


@pytest.mark.parametrize('scope', ['document', 'application'])
@pytest.mark.parametrize('prepared', [False, True])
def test_unfinished_mutation_without_checkpoint_gets_conservative_unbound_hold(tmp_path, scope, prepared):
    path = tmp_path / 'fallback.sqlite'
    first = JobStore(path)
    try:
        job, _ = first.create('unfinished', 'dimension.set_value', {'value_mm': 12}, CONTEXT, mutates=True)
        if prepared:
            first.start(job['operation_id'])
            first.prepare_mutation(job['operation_id'], connection_epoch='old', **CONTEXT,
                                   before_state={'affected': ['pid']}, effect_scope=scope)
        before = helper.read_journal(path)
    finally:
        first.close()
    second = JobStore(path)
    try:
        after = helper.read_journal(path)
        queries = helper.required_hold_queries(before, new_epoch='new', other_document='other')
        receipt = dict(before=before, after=after, new_epoch='new', other_document='other',
            hold_observations=[{**q, 'blockers': second.mutation_blockers(**q)} for q in queries])
        assert helper.validate_restart_receipts(**receipt)['accepted']
        assert second.mutation_blockers('new', 'other')
        if not prepared:
            assert after[0]['mutation']['before_state'] == {'checkpoint_unavailable': True}
        else:
            same_epoch_other = second.mutation_blockers('old', 'other')
            assert bool(same_epoch_other) == (scope == 'application')
    finally:
        second.close()


def test_raw_dto_is_not_coherent_journal_evidence(recovered):
    receipt, store, _ = recovered
    dtos = [store.get(row['operation_id']) for row in receipt['after']]
    with pytest.raises(ValueError, match='Raw job schema'):
        helper.validate_restart_receipts(**{**receipt, 'after': dtos})


def test_pending_receipt_does_not_grant_process_stop_permission(tmp_path):
    path = tmp_path / 'pending.sqlite'
    first = JobStore(path)
    try:
        job, _ = first.create('pending', 'dimension.set_value', {}, CONTEXT, mutates=True)
        first.start(job['operation_id'])
        first.prepare_mutation(job['operation_id'], connection_epoch='old', **CONTEXT, before_state={})
        first.record_mutation_step(job['operation_id'], name='setter', phase='pending', evidence={'target': 'pid'})
        before = helper.read_journal(path)
    finally:
        first.close()
    second = JobStore(path)
    try:
        after = helper.read_journal(path)
        queries = helper.required_hold_queries(before, new_epoch='new', other_document='other')
        proof = helper.validate_restart_receipts(before=before, after=after, new_epoch='new', other_document='other',
            hold_observations=[{**q, 'blockers': second.mutation_blockers(**q)} for q in queries])
        assert proof['process_stop_authorized'] is False
        assert after[0]['mutation']['verification']['native_steps'][0]['phase'] == 'pending'
    finally:
        second.close()


@pytest.mark.parametrize('status,outcome', [('succeeded', 'committed'), ('failed', 'rolled_back'),
                                         ('failed', 'not_started'), ('unknown', None)])
def test_actual_terminal_mutation_receipts_survive_restart_exactly(tmp_path, status, outcome):
    path = tmp_path / 'terminal.sqlite'
    first = JobStore(path)
    try:
        terminal, _ = first.create('historical', 'dimension.set_value', {'value_mm': 10}, CONTEXT, mutates=True)
        first.start(terminal['operation_id'])
        first.prepare_mutation(terminal['operation_id'], connection_epoch='old', **CONTEXT,
                               before_state={'affected': ['dimension_pid']}, effect_scope='application')
        if outcome:
            first.verify_mutation(terminal['operation_id'], outcome=outcome,
                                  evidence={'independent_readback': {'value_mm': 10}})
        first.finish(terminal['operation_id'], status,
                     result={'verified': True} if status == 'succeeded' else None)
        first.create('unfinished', 'dimension.set_value', {}, CONTEXT, mutates=True)
        before = helper.read_journal(path)
    finally:
        first.close()
    second = JobStore(path)
    try:
        after = helper.read_journal(path)
        queries = helper.required_hold_queries(before, new_epoch='new', other_document='other')
        receipt = dict(before=before, after=after, new_epoch='new', other_document='other',
            hold_observations=[{**q, 'blockers': second.mutation_blockers(**q)} for q in queries])
        proof = helper.validate_restart_receipts(**receipt)
        assert proof['accepted']
        assert proof['unbound_mutation_ids'] == [by_request(after, 'unfinished')['operation_id']]
        assert by_request(before, 'historical') == by_request(after, 'historical')
        forged = deepcopy(receipt)
        by_request(forged['after'], 'historical')['mutation']['verification'] = None
        if outcome:
            with pytest.raises(ValueError, match='terminal historical'):
                helper.validate_restart_receipts(**forged)
    finally:
        second.close()


def test_read_only_restart_cannot_claim_mandatory_mutation_recovery(tmp_path):
    path = tmp_path / 'read-only.sqlite'
    first = JobStore(path)
    try:
        first.create('read', 'feature.inspect', {})
        before = helper.read_journal(path)
    finally:
        first.close()
    second = JobStore(path)
    try:
        after = helper.read_journal(path)
        queries = helper.required_hold_queries(before, new_epoch='new', other_document='other')
        with pytest.raises(ValueError, match='No unfinished mutation'):
            helper.validate_restart_receipts(before=before, after=after, new_epoch='new', other_document='other',
                hold_observations=[{**q, 'blockers': second.mutation_blockers(**q)} for q in queries])
    finally:
        second.close()


@pytest.mark.parametrize('field,value', [('status', []), ('updated_at', True),
                                       ('result', {'bad': float('nan')}),
                                       ('result', {'bad': float('inf')})])
def test_malformed_raw_evidence_raises_validation_error(recovered, field, value):
    receipt = deepcopy(recovered[0])
    by_request(receipt['after'], 'write')[field] = value
    with pytest.raises(ValueError):
        helper.validate_restart_receipts(**receipt)
