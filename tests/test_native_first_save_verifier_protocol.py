"""Artificial durable evidence gates; no native CAD/filesystem acceptance."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from test_native_first_save import setup

spec = importlib.util.spec_from_file_location('first_save_protocol',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_native_first_save.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


@pytest.fixture
def evidence(setup):
    x = setup
    job = deepcopy(x.run())
    assert job['status'] == 'succeeded'
    source = job['result']['before']['document_id']
    # The fake adapter intentionally has only a minimal fake guard. Manufacture
    # this detached native-shaped guard for predicate tests, never as CAD proof.
    guard = dict(scope='native_first_save_guard_v1', destination_lease_released=True,
        native_guard=dict(scope='application_document_close_guard_v1',
            original_command_in_progress=False, acquired=True, released=True,
            model_guards=[dict(original_state=0, locked_state=2, released_state=0)],
            selection_preserved=True, retiring_document_ids=[source],
            retiring_targets_locked_during_close=False,
            activation_ui_release=dict(attempted=False, verified=False)))
    job['result']['execution_guard'] = guard
    job['mutation']['verification']['evidence']['execution_guard'] = deepcopy(guard)
    return job


def test_complete_synthetic_positive_requires_protocol_not_bare_verified_flag(evidence):
    assert protocol.verified_committed_first_save(evidence)
    stripped = deepcopy(evidence)
    stripped['mutation']['verification']['native_steps'] = []
    assert not protocol.verified_committed_first_save(stripped)


@pytest.mark.parametrize('fault', ['lease', 'journal_guard', 'source_retirement', 'mapping',
                                 'unknown', 'sequence', 'copy_ack', 'copy_error_type',
                                 'copy_path', 'final_path', 'incomplete', 'final_deleted'])
def test_missing_foreign_unconfirmed_or_type_changed_evidence_is_rejected(evidence, fault):
    job = evidence
    steps = job['mutation']['verification']['native_steps']
    def returned(name):
        return next(row['evidence'] for row in steps if row['name'] == name and row['phase'] == 'returned')
    if fault == 'lease':job['result']['execution_guard']['destination_lease_released'] = False
    elif fault == 'journal_guard':job['mutation']['verification']['evidence']['execution_guard']['native_guard']['released'] = False
    elif fault == 'source_retirement':job['result']['value']['retired_document_ids'] = ['foreign']
    elif fault == 'mapping':job['result']['value']['reference_mapping'][0]['saved_token'] = 'foreign'
    elif fault == 'unknown':job['status'] = 'unknown'
    elif fault == 'sequence':steps[0]['sequence'] = True
    elif fault == 'copy_ack':returned('first_save_copy_native')['pending_copy'] = True
    elif fault == 'copy_error_type':returned('first_save_copy_native')['errors'] = False
    elif fault == 'copy_path':steps[2]['evidence']['filename'] = 'foreign'
    elif fault == 'final_path':job['result']['value']['filename'] = 'foreign'
    elif fault == 'incomplete':steps.pop()
    elif fault == 'final_deleted':job['result']['value']['staging_cleanup']['destination_removed'] = True
    assert not protocol.verified_committed_first_save(job)
