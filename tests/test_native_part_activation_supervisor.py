"""Supervisor cleanup admission for real artificial-domain activation jobs."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

from test_native_part_activation import setup, capture, run
from test_native_part_activation_protocol import native_shaped


spec = importlib.util.spec_from_file_location('part_activation_supervisor_tests',
    Path(__file__).resolve().parents[1] / 'scripts/verifier_lifecycle.py')
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


def decision(job):
    tool = helper.ToolSpec('document.activate_part_native', True)
    args = {'request_id': job['request_id'], **job['payload']['arguments']}
    owner = helper.VerifierSupervisor(object(), tool_specs={'activate': tool}, journal_reader=lambda: [])
    owner._fresh = True
    owner.requests[job['request_id']] = helper.TrackedRequest(
        'activate', job['request_id'], args, tool, deepcopy(job['payload']),
        operation_id=job['operation_id'], send_attempts=1)
    owner._bind([job])
    return owner._decide([job])


@pytest.mark.parametrize('already_active', [False, True])
def test_exact_committed_activation_or_noop_admits_sdk_and_owned_cleanup(setup, already_active):
    if already_active:
        setup.adapter.active = setup.target
    job = native_shaped(run(setup))
    result = decision(job)
    assert result.child_can_close and result.fixture_can_cleanup and not result.reasons


@pytest.mark.parametrize('fault', ['guard', 'ledger', 'revision', 'snapshot', 'unknown'])
def test_unconfirmed_part_activation_never_admits_fixture_cleanup(setup, fault):
    job = native_shaped(run(setup))
    if fault == 'guard': job['mutation']['verification']['evidence']['execution_guard']['guard_released'] = False
    if fault == 'ledger': job['mutation']['verification']['native_steps'].pop()
    if fault == 'revision': job['mutation']['expected_revision'] = 'rev_foreign'
    if fault == 'snapshot': job['result']['after']['snapshots'] = {}
    if fault == 'unknown': job.update(status='unknown', result=None); job['mutation']['phase'] = 'unresolved'
    result = decision(job)
    assert not result.fixture_can_cleanup and result.reasons
