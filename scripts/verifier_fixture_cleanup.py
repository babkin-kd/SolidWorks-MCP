"""Pure cleanup authorization; unknown native effects never authorize cleanup.

This utility performs no CAD calls, cancellation, replay or reconciliation.
Inline verifiers may begin safe before dispatch; every submitted mutation must
provide terminal durable proof before caller-owned fixture cleanup is allowed.
"""


def fixture_cleanup_allowed(cleanup_gate):
    if cleanup_gate is None:
        return True
    try:
        return callable(cleanup_gate) and cleanup_gate() is True
    except BaseException:
        return False


def _released_guard(guard):
    expected = {'original_state': 0, 'locked_state': 2, 'released_state': 0}
    return isinstance(guard, dict) and set(guard) == set(expected) and all(
        type(guard[key]) is int and guard[key] == value for key, value in expected.items())


def inline_job_cleanup_proven(job):
    """Require matching durable terminal verification and genuine guard release."""
    if not isinstance(job, dict) or job.get('status') not in ('succeeded', 'failed', 'cancelled'):
        return False
    status, error, mutation = job['status'], job.get('error'), job.get('mutation')
    if error is not None and (not isinstance(error, dict) or error.get('requires_reconciliation') is not False):
        return False
    if mutation is None:
        # Cancellation before execution has no checkpoint. A failed pre-write
        # requires an explicit trusted non-reconciliation flag, never its code.
        return status == 'cancelled' or (status == 'failed' and isinstance(error, dict)
                                        and error.get('requires_reconciliation') is False)
    if not isinstance(mutation, dict):
        return False
    expected_phases = {'succeeded': ('committed',), 'failed': ('rolled_back', 'not_started')}
    phase, verification = mutation.get('phase'), mutation.get('verification')
    if phase not in expected_phases.get(status, ()) or not isinstance(verification, dict):
        return False
    if verification.get('outcome') != phase:
        return False
    before, evidence = mutation.get('before_state'), verification.get('evidence')
    if not isinstance(before, dict) or before.get('_mutation_effect_scope') != 'application':
        return False
    if not isinstance(evidence, dict) or not _released_guard(evidence.get('execution_guard')):
        return False
    if status == 'failed':
        return isinstance(error, dict) and error.get('requires_reconciliation') is False
    result = job.get('result')
    return isinstance(result, dict) and result.get('verified') is True and _released_guard(result.get('execution_guard'))


class InlineFixtureCleanupGate:
    """Sticky ownership gate: a later known job cannot erase earlier uncertainty."""

    def __init__(self):
        self._allowed = True  # No mutation has been dispatched yet.
        self._held = False

    def can_cleanup(self):
        return self._allowed is True and self._held is False

    def before_submit(self):
        if not self.can_cleanup():
            self._held = True
        self._allowed = False

    def retain(self):
        self._held = True
        self._allowed = False

    def observe_terminal(self, job):
        if not inline_job_cleanup_proven(job):
            self.retain()
        else:
            self._allowed = not self._held


def guarded_inline_submit(gate, runner, store, *arguments, **keywords):
    """Hold before dispatch, then independently reread the same durable job."""
    if not gate.can_cleanup():
        gate.retain()
        raise RuntimeError('Uncertain earlier work prohibits another inline dispatch.')
    gate.before_submit()
    try:
        job = runner.submit(*arguments, **keywords)
        durable = store.get(job['operation_id'])
        blockers = store.mutation_blockers('fixture-cleanup-verifier', 'all-fixture-documents',
                                           effect_scope='application')
        gate.observe_terminal(durable if durable == job and type(blockers) is list and not blockers else None)
        return job
    except BaseException:
        gate.retain()
        raise
