"""Public cleanup decisions on real JobStore jobs and artificial CAD evidence.

The transport is passive: these tests do not start MCP, COM or native CAD.
"""
import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

from test_rectangle_native_verifier import (
    configured, execution, sketch_proof, extrusion_proof, empty_adapter, proof_job,
)
from test_rectangle_restoration_verifier import rollback_job, native_shaped_ledger
from test_rectangle_construction_execution import run


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('_rectangle_public_supervisor_test',
    SCRIPTS / 'verifier_lifecycle.py')
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


@pytest.fixture(autouse=True)
def public_context(configured, monkeypatch):
    """Use the public context whitelist when the actual coordinator journals.

    The shared domain fixture otherwise stores all construction arguments in
    context; the public facade stores only the explicit mutation context keys.
    No result, checkpoint, geometry, revision or ledger is fabricated here.
    """
    submit = configured.runner.submit

    def public_submit(*args, **kwargs):
        kwargs['context'] = {key: value for key, value in kwargs['context'].items()
                             if key in helper.CONTEXT_KEYS}
        return submit(*args, **kwargs)

    monkeypatch.setattr(configured.runner, 'submit', public_submit)


class JournalClient:
    """Acknowledge an existing durable fixture job, then expose its snapshot."""
    def __init__(self, job, tool):
        self.job, self.tool, self.rows = deepcopy(job), tool, []
        self.calls = 0

    async def call_tool(self, name, arguments, **kwargs):
        if name == 'job_list':
            return dict(status='succeeded', data=dict(items=deepcopy(self.rows), next_cursor=None))
        assert name == 'rectangle'
        assert arguments['request_id'] == self.job['request_id']
        assert self.tool.payload(arguments) == self.job['payload']
        self.calls += 1
        self.rows = [deepcopy(self.job)]
        return dict(operation_id=self.job['operation_id'], status=self.job['status'])


def public_decision(job, observed=None, *, hold=None, repair_observation=False):
    """Exercise public dispatch, binding, observation, drain and CleanupGate."""
    async def scenario():
        tool = helper.ToolSpec(job['operation'], True,
            prewrite_failure_codes=frozenset({'stale_revision'}))
        client = JournalClient(job, tool)
        owner = helper.VerifierSupervisor(client, tool_specs={'rectangle': tool},
            journal_reader=lambda: deepcopy(client.rows), poll_interval=.001)
        async with owner.inside_live_session():
            await owner.call_tool('rectangle', dict(request_id=job['request_id'],
                **job['payload']['arguments']))
            if hold:
                owner.retain(hold)
            client.rows = [deepcopy(observed if observed is not None else job)]
            decision = await owner.observe_once()
            if repair_observation:
                # Pending/malformed snapshots cannot drain. Supply the already
                # terminal genuine job for session exit, never for the assertion.
                client.rows = [deepcopy(job)]
        assert client.calls == 1
        return decision, owner
    return asyncio.run(scenario())


def test_committed_full_geometry_admits_public_owned_cleanup(proof_job):
    decision, owner = public_decision(proof_job)
    assert decision.child_can_close and decision.fixture_can_cleanup
    assert not decision.reasons and owner.cleanup_gate.can_cleanup()


def test_exact_owned_rollback_admits_public_cleanup(rollback_job):
    decision, owner = public_decision(rollback_job)
    assert decision.child_can_close and decision.fixture_can_cleanup
    assert not decision.reasons and owner.cleanup_gate.can_cleanup()


def test_native_shaped_finite_rollback_ledger_admits_public_cleanup(rollback_job):
    decision, _ = public_decision(native_shaped_ledger(rollback_job))
    assert decision.child_can_close and decision.fixture_can_cleanup


@pytest.mark.parametrize('fault', [
    'guard', 'generic_guard', 'ledger', 'foreign', 'stale', 'scope', 'effect_scope',
    'missing_effect_scope', 'pending_receipt', 'neighbor', 'files', 'unverified',
])
def test_incomplete_committed_evidence_retains_public_fixtures(proof_job, fault):
    job = deepcopy(proof_job)
    verification = job['mutation']['verification']
    if fault == 'guard':
        verification['evidence']['execution_guard']['native_guards'][0]['model_guards'][0]['released_state'] = 2
    elif fault == 'generic_guard':
        generic = dict(original_state=0, locked_state=2, released_state=0)
        verification['evidence']['execution_guard'] = deepcopy(generic)
        job['result']['execution_guard'] = generic
    elif fault == 'ledger':
        verification['native_steps'].pop()
    elif fault == 'foreign':
        job['mutation']['document_id'] = 'foreign'
    elif fault == 'stale':
        job['mutation']['expected_revision'] = 'rev_stale'
    elif fault == 'scope':
        job['mutation']['before_state']['scope'] = 'foreign_scope'
        job['result']['before']['scope'] = 'foreign_scope'
    elif fault == 'effect_scope':
        job['mutation']['before_state']['_mutation_effect_scope'] = 'document'
    elif fault == 'missing_effect_scope':
        del job['mutation']['before_state']['_mutation_effect_scope']
    elif fault == 'pending_receipt':
        verification['evidence']['after']['receipt']['pending_native_step'] = 'create'
    elif fault == 'neighbor':
        verification['evidence']['after']['state']['snapshots']['neighbor'] = {'foreign': 'change'}
    elif fault == 'files':
        verification['evidence']['after']['original_files'] = {'foreign': 'bytes'}
    else:
        job['result']['verified'] = False
    decision, _ = public_decision(proof_job, job, repair_observation=True)
    assert not decision.fixture_can_cleanup
    assert 'native rectangle evidence unconfirmed' in decision.reasons


@pytest.mark.parametrize('fault', [
    'guard', 'generic_guard', 'ledger', 'foreign', 'stale', 'scope', 'effect_scope',
    'inverse', 'pending_receipt', 'neighbor', 'files', 'reconciliation',
])
def test_incomplete_rollback_evidence_retains_public_fixtures(rollback_job, fault):
    job = deepcopy(rollback_job)
    verification = job['mutation']['verification']
    after = verification['evidence']['after']
    if fault == 'guard':
        verification['evidence']['execution_guard']['native_guards'].pop()
    elif fault == 'generic_guard':
        verification['evidence']['execution_guard'] = dict(original_state=0, locked_state=2, released_state=0)
    elif fault == 'ledger':
        verification['native_steps'][-1]['evidence']['verified'] = False
    elif fault == 'foreign':
        job['mutation']['configuration'] = 'foreign'
    elif fault == 'stale':
        job['mutation']['expected_revision'] = 'rev_stale'
    elif fault == 'scope':
        job['mutation']['before_state']['scope'] = 'foreign_scope'
    elif fault == 'effect_scope':
        job['mutation']['before_state']['_mutation_effect_scope'] = 'document'
    elif fault == 'inverse':
        after['receipt']['restored'] = False
    elif fault == 'pending_receipt':
        after['receipt']['pending_native_step'] = 'delete'
    elif fault == 'neighbor':
        after['state']['snapshots']['neighbor'] = {'foreign': 'change'}
    elif fault == 'files':
        after['original_files'] = {'foreign': 'bytes'}
    else:
        job['error']['requires_reconciliation'] = True
    decision, _ = public_decision(rollback_job, job)
    assert decision.child_can_close and not decision.fixture_can_cleanup
    assert 'native rectangle evidence unconfirmed' in decision.reasons


@pytest.mark.parametrize('status', ['queued', 'running'])
def test_pending_job_holds_child_and_fixtures(proof_job, status):
    job = deepcopy(proof_job)
    job['status'] = status
    decision, _ = public_decision(proof_job, job, repair_observation=True)
    assert not decision.child_can_close and not decision.fixture_can_cleanup
    assert 'durable work still queued/running' in decision.reasons


def test_unknown_taint_survives_later_terminal_observation(proof_job):
    job = deepcopy(proof_job)
    job.update(status='unknown', result=None)
    job['mutation']['phase'] = 'unresolved'
    decision, owner = public_decision(proof_job, job, repair_observation=True)
    assert decision.child_can_close and not decision.fixture_can_cleanup
    assert 'terminal unknown retains fixtures' in decision.reasons
    assert not owner.cleanup_gate.can_cleanup()


@pytest.mark.parametrize('hold', ['transport lost', 'independent fixture proof failed'])
def test_complete_rectangle_evidence_cannot_override_hold(proof_job, hold):
    decision, owner = public_decision(proof_job, hold=hold)
    assert decision.child_can_close and not decision.fixture_can_cleanup
    assert hold in decision.reasons and not owner.cleanup_gate.can_cleanup()


@pytest.mark.parametrize('fault', ['request', 'operation', 'payload', 'acknowledgement'])
def test_foreign_durable_binding_cannot_authorize_cleanup(proof_job, fault):
    job = deepcopy(proof_job)
    if fault == 'request':
        job['request_id'] = 'foreign_request'
    elif fault == 'operation':
        job['operation'] = 'sketch.create_rectangle_alias'
    elif fault == 'payload':
        job['payload']['arguments']['document_id'] = 'foreign'
    else:
        job['operation_id'] = 'foreign_operation'
    decision, _ = public_decision(proof_job, job, repair_observation=True)
    assert not decision.child_can_close and not decision.fixture_can_cleanup


def test_rectangle_guard_never_authorizes_other_operation(proof_job):
    job = deepcopy(proof_job)
    job['operation'] += '_alias'
    decision, _ = public_decision(job)
    assert decision.child_can_close and not decision.fixture_can_cleanup
    assert 'UI release unconfirmed' in decision.reasons


def test_real_stale_precheckpoint_rejection_preserves_existing_prewrite_policy(configured):
    job = run(configured, revision='rev_stale')
    assert job['status'] == 'failed' and job['error']['code'] == 'stale_revision'
    assert job.get('mutation') is None and configured.adapter.dispatches == 0
    decision, _ = public_decision(job)
    assert decision.child_can_close and decision.fixture_can_cleanup
    job['error']['code'] = 'unsupported_refusal'
    decision, _ = public_decision(job)
    assert decision.child_can_close and not decision.fixture_can_cleanup
    assert 'mutation lacks confirmed prewrite outcome' in decision.reasons


def test_guarded_not_started_checkpoint_cannot_use_prewrite_whitelist(configured, monkeypatch):
    prepare = configured.catalog._prepare
    monkeypatch.setattr(configured.catalog, '_prepare', lambda *args, **kwargs:
        {**prepare(*args, **kwargs), 'revision': 'rev_stale_in_guard'})
    job = run(configured)
    assert job['status'] == 'failed' and job['mutation']['phase'] == 'not_started'
    assert configured.adapter.dispatches == configured.adapter.inverses == 0
    decision, _ = public_decision(job)
    assert decision.child_can_close and not decision.fixture_can_cleanup
    assert 'UI release unconfirmed' in decision.reasons


@pytest.mark.parametrize('filename', ['verifier_lifecycle.py', 'verifier_rectangle_restoration.py'])
@pytest.mark.parametrize('mode', ['path', 'standalone'])
def test_passive_sibling_loading_never_changes_sys_path(configured, filename, mode):
    # A fresh interpreter ensures a prior test's imports cannot hide missing
    # siblings. Source dependencies are supplied by the test run's PYTHONPATH.
    code = '''
import importlib.util, pathlib, runpy, sys
path = pathlib.Path(sys.argv[1])
before = list(sys.path)
if sys.argv[2] == 'path':
    spec = importlib.util.spec_from_file_location('_isolated_rectangle_helper', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
else:
    runpy.run_path(str(path), run_name='__main__')
assert sys.path == before
assert str(path.parent) not in sys.path
'''
    result = subprocess.run([sys.executable, '-c', code, str(SCRIPTS / filename), mode],
        cwd=SCRIPTS.parent, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
