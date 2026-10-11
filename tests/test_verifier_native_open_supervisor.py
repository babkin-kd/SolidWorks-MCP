"""Source/fake open journal plus synthetic guard evidence; no CAD/SDK proof."""

from copy import deepcopy

import pytest

from test_native_document_open_v2 import setup
from test_verifier_lifecycle_v2 import helper


def owner_for(row):
    spec = helper.ToolSpec('document.open_native', True, argument_defaults={'read_only': False})
    owner = helper.VerifierSupervisor(object(), tool_specs={'document_open_native': spec},
                                      journal_reader=lambda: [deepcopy(row)])
    owner._fresh = True
    owner.requests[row['request_id']] = helper.TrackedRequest('document_open_native', row['request_id'],
        {'request_id': row['request_id'], **row['payload']['arguments']}, spec, deepcopy(row['payload']),
        operation_id=row['operation_id'])
    return owner


def with_guard(row):
    row = deepcopy(row)
    verification = row['mutation']['verification']
    ids = [item['document_id'] for item in row['mutation']['before_state']['semantic']['documents']]
    release = any(item['name'] == 'release_baseline_ui' for item in verification['native_steps'])
    verification['evidence']['execution_guard'] = dict(scope='application_document_open_guard_v1',
        original_command_in_progress=False, acquired=True, released=True, selection_preserved=True,
        baseline_document_ids=ids,
        model_guards=[dict(original_state=0, locked_state=2, released_state=0) for _ in ids],
        activation_ui_release=dict(attempted=release, verified=release))
    return row


@pytest.mark.parametrize('fault', [None, 'null', 'warning', 'source_config_fallback'])
def test_open_supervisor_accepts_completed_domain_oracle_and_exact_evidence(setup, fault):
    x = setup
    x.a.open_fault = fault
    p = x.c.prepare_open(str(x.source), 'part', 'Вариант')
    row = with_guard(x.run(preparation=p))
    assert row['status'] in ('succeeded', 'failed')
    decision = owner_for(row)._decide([row])
    assert decision.child_can_close and decision.fixture_can_cleanup, decision


@pytest.mark.parametrize('change', ['pending', 'missing', 'unbound_source', 'wrong_guard', 'wrong_baseline'])
def test_coherent_job_with_unproved_open_steps_or_guard_retains_fixtures(setup, change):
    row = with_guard(setup.run())
    verification = row['mutation']['verification']
    if change == 'pending':
        verification['native_steps'].pop()
    elif change == 'missing':
        verification.pop('native_steps')
    elif change == 'unbound_source':
        verification['native_steps'][0]['evidence']['native_file_id'] = 'native_file_foreign'
    elif change == 'wrong_guard':
        verification['evidence']['execution_guard']['scope'] = 'application_document_create_guard_v1'
    else:
        verification['evidence']['execution_guard']['baseline_document_ids'] = ['doc_foreign']
    decision = owner_for(row)._decide([row])
    assert decision.child_can_close and not decision.fixture_can_cleanup, decision


def test_under_guard_prewrite_failure_requires_no_open_ledger(setup):
    x = setup
    x.a.guard_hook = lambda: x.source.write_bytes(b'changed under guard')
    row = x.run()
    assert row['status'] == 'failed' and row['mutation']['phase'] == 'not_started'
    row['mutation']['verification']['native_steps'] = []
    row = with_guard(row)
    decision = owner_for(row)._decide([row])
    assert decision.child_can_close and decision.fixture_can_cleanup, decision
