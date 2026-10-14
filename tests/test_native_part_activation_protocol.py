"""Detached receipt/ledger counterexamples on artificial domain data, not CAD."""

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path

import pytest

from test_native_part_activation import setup, capture, run


spec = importlib.util.spec_from_file_location('activation_protocol',
    Path(__file__).resolve().parents[1] / 'scripts/verifier_native_part_activation.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


def native_shaped(job):
    # Domain data and the real JobStore ledger are used; only the fake guard's
    # sparse release DTO is expanded into manufactured native-shaped evidence.
    job = deepcopy(job)
    before = job['result']['before']
    ids = [row['document_id'] for row in before['semantic']['documents']]
    active = before['semantic']['active_document_id'] == before['document_id']
    native = dict(scope=protocol.NATIVE_GUARD_SCOPE, original_command_in_progress=False,
                  acquired=True, released=True, selection_preserved=True,
                  baseline_document_ids=next(row['evidence']['document_ids'] for row in job['mutation']['verification']['native_steps']
                                             if row['name']=='part_activation_guard_release' and row['phase']=='pending'),
                  activation_ui_release={'attempted': not active, 'verified': not active},
                  model_guards=[dict(original_state=0, locked_state=2, released_state=0) for _ in ids])
    guard = job['result']['execution_guard']
    guard['native_guard'] = native
    job['mutation']['verification']['evidence']['execution_guard'] = deepcopy(guard)
    for row in job['mutation']['verification']['native_steps']:
        if row['name']=='part_activation_guard_release' and row['phase']=='returned':
            row['evidence'] = deepcopy(native)
    return job


def test_committed_activation_matches_exact_target_revision_full_state_and_ledger(setup):
    job = native_shaped(run(setup))
    assert protocol.verified_committed_part_activation(job)


def test_noop_has_no_activation_or_ui_phase_and_still_requires_release_proof(setup):
    setup.adapter.active = setup.target
    job = native_shaped(run(setup))
    assert protocol.verified_committed_part_activation(job)
    job['result']['value']['native_call_attempted'] = True
    assert not protocol.verified_committed_part_activation(job)


@pytest.mark.parametrize('partial', ['missing_snapshot', 'empty_references', 'body_bool'])
def test_consistently_rehashed_partial_checkpoint_still_cannot_pass(setup, partial):
    job = native_shaped(run(setup))
    before = job['result']['before']
    if partial == 'missing_snapshot': before['snapshots'] = {}
    if partial == 'empty_references': next(iter(before['snapshots'].values()))['references'] = []
    if partial == 'body_bool': next(iter(before['snapshots'].values()))['solid_body_count'] = True
    job['mutation']['before_state'] = {**deepcopy(before), '_mutation_effect_scope': 'application'}
    revision = 'rev_' + hashlib.sha256(protocol._json(before).encode('utf-8')).hexdigest()
    job['mutation']['expected_revision'] = revision
    job['payload']['arguments']['expected_revision'] = revision
    job['payload']['context']['expected_revision'] = revision
    job['result']['after']['snapshots'] = deepcopy(before['snapshots'])
    job['mutation']['verification']['evidence']['after'] = deepcopy(job['result']['after'])
    job['mutation']['verification']['native_steps'][-1]['evidence']['observed'] = deepcopy(job['result']['after'])
    assert not protocol.verified_committed_part_activation(job)


@pytest.mark.parametrize('fault', ['status', 'scope', 'guard_scope', 'release_bool', 'guard_membership',
                                  'guard_count', 'guard_order_valid', 'sequence_bool', 'missing_pair',
                                  'duplicate_pair', 'pending', 'receipt_bool', 'native_error',
                                  'other_target', 'revision', 'config', 'after_state', 'snapshot',
                                  'file', 'ledger_observed', 'receipt_vs_value', 'partial_guard'])
def test_unconfirmed_or_mismatched_evidence_never_authorizes_public_cleanup(setup, fault):
    job = native_shaped(run(setup))
    guard = job['result']['execution_guard']
    steps = job['mutation']['verification']['native_steps']
    if fault == 'status': job['status'] = 'unknown'
    if fault == 'scope': job['result']['before']['scope'] = 'other'
    if fault == 'guard_scope': guard['scope'] = 'other'
    if fault == 'release_bool': guard['guard_released'] = 1
    if fault == 'guard_membership': guard['native_guard']['baseline_document_ids'][0] = 'doc_foreign'
    if fault == 'guard_count': guard['native_guard']['model_guards'].pop()
    if fault == 'guard_order_valid':
        # A census is sorted independently of native model order; reordered
        # exact guard membership itself remains valid, but ledger must bind it.
        guard['native_guard']['baseline_document_ids'].reverse()
        assert protocol.released_part_activation_guard(guard, job['result']['before'])
    if fault == 'sequence_bool': steps[0]['sequence'] = True
    if fault == 'missing_pair': del steps[:2]
    if fault == 'duplicate_pair': steps[2:4] = deepcopy(steps[:2])
    if fault == 'pending': job['result']['after']['pending_activation'] = True
    if fault == 'receipt_bool': job['result']['after']['receipt']['native_call_returned'] = 1
    if fault == 'native_error': job['result']['after']['receipt']['native_error'] = True
    if fault == 'other_target': job['result']['value']['active_after_document_id'] = 'doc_foreign'
    if fault == 'revision': job['payload']['arguments']['expected_revision'] = 'rev_foreign'
    if fault == 'config': job['payload']['context']['configuration'] = 'other'
    if fault == 'after_state': job['result']['after']['semantic']['application']['current_directory'] = '/foreign'
    if fault == 'snapshot': next(iter(job['result']['after']['snapshots'].values()))['solid_body_count'] = 2
    if fault == 'file': job['result']['after']['original_files'] = []
    if fault == 'ledger_observed': steps[-1]['evidence']['observed']['semantic']['active_document_id'] = 'doc_foreign'
    if fault == 'receipt_vs_value': job['result']['value']['receipt']['native_error'] = 2
    if fault == 'partial_guard': guard['native_guard'].pop('selection_preserved')
    assert not protocol.verified_committed_part_activation(job)
