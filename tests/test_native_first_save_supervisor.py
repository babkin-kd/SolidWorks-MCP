"""Supervisor admission of complete first-save evidence; no native CAD claim."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

from test_native_first_save_verifier_protocol import evidence, setup


spec = importlib.util.spec_from_file_location('first_save_supervisor_tests',
    Path(__file__).resolve().parents[1] / 'scripts/verifier_lifecycle.py')
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


def decision(job):
    tool = helper.ToolSpec('document.first_save_native', True)
    args = {'request_id': job['request_id'], **job['payload']['arguments']}
    owner = helper.VerifierSupervisor(object(), tool_specs={'save': tool}, journal_reader=lambda: [])
    owner._fresh = True
    owner.requests[job['request_id']] = helper.TrackedRequest(
        'save', job['request_id'], args, tool, deepcopy(job['payload']),
        operation_id=job['operation_id'], send_attempts=1)
    owner._bind([job])
    return owner._decide([job])


def test_full_replacement_publication_and_release_admit_owned_cleanup(evidence):
    result = decision(evidence)
    assert result.child_can_close and result.fixture_can_cleanup and not result.reasons


@pytest.mark.parametrize('fault', ['lease', 'release', 'ledger', 'mapping', 'unknown'])
def test_partial_or_unknown_first_save_never_admits_cleanup(evidence, fault):
    job = deepcopy(evidence)
    if fault == 'lease': job['mutation']['verification']['evidence']['execution_guard']['destination_lease_released'] = False
    if fault == 'release': job['mutation']['verification']['evidence']['execution_guard']['native_guard']['released'] = False
    if fault == 'ledger': job['mutation']['verification']['native_steps'].pop()
    if fault == 'mapping': job['result']['value']['reference_mapping'] = []
    if fault == 'unknown': job.update(status='unknown', result=None); job['mutation']['phase'] = 'unresolved'
    result = decision(job)
    assert not result.fixture_can_cleanup and result.reasons
