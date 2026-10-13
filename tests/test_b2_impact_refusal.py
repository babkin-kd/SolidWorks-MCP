"""Real SQLite refusal/replay binding over artificial jobs; no CAD operation."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest
from solidworks_mcp.jobs import JobStore

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b2_impact_refusal import preview_refusal
    from verifier_lifecycle import read_journal
finally:
    sys.path.remove(scripts)


@pytest.fixture
def evidence(tmp_path):
    path = tmp_path / 'jobs.sqlite'
    store = JobStore(path)
    args = dict(document_id='doc_fixture', configuration='Основная', object_id='feat_' + 'a' * 32)
    try:
        parent, _ = store.create('original-creation', 'part.extrude_rectangle', {})
        store.start(parent['operation_id'])
        store.finish(parent['operation_id'], 'succeeded', result={'original': True})
        before = read_journal(path)
        job, _ = store.create('dependent-preview', 'feature.prepare_leaf_deletion', args, args)
        store.start(job['operation_id'])
        store.finish(job['operation_id'], 'failed', error={
            'code': 'leaf_deletion_unsupported', 'message': 'Native dependent children forbid leaf deletion.'})
        yield dict(public_dto=store.get(job['operation_id']), before=before,
                   after=read_journal(path), request_id='dependent-preview', arguments=args,
                   expected_code='leaf_deletion_unsupported'), store, path
    finally:
        store.close()


def test_refused_preview_and_replay_preserve_real_sql_and_are_not_native_acceptance(evidence):
    values, store, path = evidence
    original = deepcopy(values)
    proof = preview_refusal(**values)
    assert proof['journal_refusal_verified'] is True and proof['replay'] is False
    assert all(proof[key] is False for key in ('accepted', 'native_b2_accepted',
        'public_mcp_accepted', 'cleanup_authorized', 'complete_native_before_after_verified'))
    replay, created = store.create(values['request_id'], 'feature.prepare_leaf_deletion',
                                  values['arguments'], values['arguments'])
    assert created is False and replay == values['public_dto']
    values['before'] = deepcopy(values['after'])
    values['after'] = read_journal(path)
    assert preview_refusal(**values)['replay'] is True
    assert original['public_dto'] == replay
    proof['refused_job']['error']['message'] = 'detached'
    assert store.get(replay['operation_id']) == replay


def test_snapshot_profile_refusal_has_its_own_exact_error_binding(evidence):
    values, store, path = evidence
    args = values['arguments']
    before = read_journal(path)
    row, _ = store.create('equation-preview', 'feature.prepare_leaf_deletion', args, args)
    store.start(row['operation_id'])
    store.finish(row['operation_id'], 'failed', error={
        'code': 'first_save_snapshot_unsupported', 'message': 'Equation context is outside BASE.'})
    actual = dict(public_dto=store.get(row['operation_id']), before=before,
                  after=read_journal(path), request_id='equation-preview', arguments=args,
                  expected_code='first_save_snapshot_unsupported')
    assert preview_refusal(**actual)['journal_refusal_verified'] is True
    actual['expected_code'] = 'leaf_deletion_unsupported'
    with pytest.raises(ValueError): preview_refusal(**actual)


@pytest.mark.parametrize('change', [
    'old_result', 'missing_old', 'extra_job', 'duplicate', 'checkpoint', 'unknown',
    'running', 'succeeded', 'wrong_request', 'wrong_object', 'wrong_digest',
    'changed_public', 'extra_public', 'missing_column', 'wrong_code', 'empty_message',
    'mutating_payload', 'result_present', 'missing_configuration', 'boolean_feature',
])
def test_incomplete_or_changed_evidence_is_rejected(evidence, change):
    values, _, _ = evidence
    values = deepcopy(values)
    row = values['after'][-1]
    if change == 'old_result': values['after'][0]['result']['original'] = False
    elif change == 'missing_old': values['after'].pop(0)
    elif change == 'extra_job':
        extra = deepcopy(row); extra['operation_id'] = 'unrelated'; values['after'].append(extra)
    elif change == 'duplicate': values['after'].append(deepcopy(row))
    elif change == 'checkpoint': row['mutation'] = {'phase': 'not_started'}
    elif change in ('unknown', 'running', 'succeeded'): row['status'] = change
    elif change == 'wrong_request': values['request_id'] = 'different'
    elif change == 'wrong_object': values['arguments']['object_id'] = 'feat_' + 'b' * 32
    elif change == 'wrong_digest': row['digest'] = '0' * 64
    elif change == 'changed_public': values['public_dto']['error']['message'] = 'different'
    elif change == 'extra_public': values['public_dto']['extra'] = True
    elif change == 'missing_column': row.pop('updated_at')
    elif change == 'wrong_code': values['expected_code'] = 'dispatch_failed'
    elif change == 'empty_message': row['error']['message'] = ''
    elif change == 'mutating_payload': row['payload']['mutates'] = True
    elif change == 'result_present': row['result'] = {'delete_authorized': True}
    elif change == 'missing_configuration': values['arguments'].pop('configuration')
    elif change == 'boolean_feature': values['arguments']['object_id'] = True
    with pytest.raises(ValueError): preview_refusal(**values)
