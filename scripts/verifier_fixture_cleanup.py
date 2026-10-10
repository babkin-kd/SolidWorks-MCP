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
    if isinstance(guard, dict) and guard.get('scope') in ('application_document_create_guard_v1','application_model_mutation_guard_v1'):
        keys = {'scope', 'original_command_in_progress', 'acquired', 'released', 'model_guards', 'selection_preserved'}
        return (set(guard) == keys and guard['original_command_in_progress'] is False
                and guard['acquired'] is True and guard['released'] is True and guard['selection_preserved'] is True
                and type(guard['model_guards']) is list and len(guard['model_guards']) <= 1000
                and (guard['scope']!='application_model_mutation_guard_v1' or len(guard['model_guards'])==1)
                and all(isinstance(item, dict) and 'scope' not in item and _released_guard(item)
                        for item in guard['model_guards']))
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
    if not isinstance(evidence, dict):
        return False
    guard = evidence.get('execution_guard')
    if not _released_guard(guard):
        # No owned flag/lock/selection was acquired. The native caller still
        # must verify its live baseline; this does not authorize clearing an
        # external busy flag or closing any foreign model.
        if not (status=='failed' and phase=='not_started' and isinstance(error,dict)
                and error.get('code')=='application_busy'
                and evidence.get('native_mutation_started') is False
                and untouched_busy_guard(guard)):
            return False
    if status == 'failed':
        return isinstance(error, dict) and error.get('requires_reconciliation') is False
    result = job.get('result')
    return isinstance(result, dict) and result.get('verified') is True and _released_guard(result.get('execution_guard'))


def untouched_busy_guard(guard):
    expected={'scope':'application_model_mutation_guard_v1','original_command_in_progress':True,
              'acquired':False,'released':False,'model_guards':[],'selection_preserved':False}
    return (isinstance(guard,dict) and set(guard)==set(expected)
            and guard['scope']==expected['scope']
            and all(guard[key] is expected[key] for key in ('original_command_in_progress','acquired','released','selection_preserved'))
            and type(guard['model_guards']) is list and not guard['model_guards'])


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
