"""Owner-invoked finite N5 domain batch; no connection, guard or cleanup.

One full event/state envelope covers preview, its replay, direct execution and
its replay on one fixture. Every job is bound to independently read actual SQL.
The native CLI still must prove wheel provenance and terminal own cleanup.
"""
from solidworks_mcp.jobs import _json
from verifier_b2_impact_fixture import require
from verifier_b2_impact_refusal import preview_refusal, execution_refusal
from verifier_b2_impact_request_envelope import run_observed_refusal
from verifier_b2_public_contract import durable_b2_job, verified_b2_job
from verifier_lifecycle import read_journal


SCOPE = 'b2_impact_internal_refusal_batch_v1'


def run_impact_refusals(leaf, runner, session, base_preparation, *, expected_code, progress=None):
    """Use the exact original registry, real runner and already prepared BASE."""
    target = session.target
    binding = target.binding
    require(leaf.store is runner.store is target.fixture.ownership.store
            and leaf.ownership is target.fixture.ownership
            and leaf.documents is target.fixture.ownership.documents
            and leaf.connection_epoch == binding.connection_epoch,
            'Original live leaf/runner/fixture registry, journal and epoch required.')
    context = dict(document_id=binding.document_id, configuration=binding.configuration,
                   object_id=binding.object_id)
    rows = read_journal(leaf.store.path)
    require(all(row['status'] in ('succeeded', 'failed')
                and (row['mutation'] is None or row['mutation']['phase'] in ('committed', 'rolled_back', 'not_started'))
                for row in rows), 'Terminal fixture setup and absence of unknown/active holds required.')
    matches = [row for row in rows if row['operation_id'] == base_preparation['operation_id']]
    require(len(matches) == 1, 'Actual original BASE preparation SQL required.')
    preparation = durable_b2_job(base_preparation, matches[0])
    require(verified_b2_job(preparation) is True and preparation['operation'] == 'feature.prepare_leaf_deletion'
            and _json(preparation['payload']['arguments']) == _json(context)
            and preparation['result']['creation_operation_id'] == binding.creation_operation_id
            and preparation['result']['feature_pid_hex'] == binding.persistent_id.hex(),
            'Complete original own BASE preparation and exact lineage required.')
    arguments = dict(context, expected_revision=preparation['result']['revision'])
    prefix = 'n5-' + target.fixture.case
    jobs, proofs = [], []
    calls = {'preview': 0, 'execute': 0}

    def preview():
        calls['preview'] += 1
        return leaf.prepare(**context)

    def execute(operation_id):
        calls['execute'] += 1
        return leaf.delete(operation_id, **arguments)

    def forbidden(*args):
        raise AssertionError('A refusal replay must not dispatch native work.')

    def invoke(operation, args, function, *, mutates, replay):
        before = read_journal(leaf.store.path)
        request_id = prefix + ('-execute' if mutates else '-preview')
        options = dict(context=args, mutates=mutates)
        if mutates:
            options.update(pass_operation_id=True, verify=lambda value: value['verified'] is True)
        job = runner.submit(request_id, operation, args, function, **options)
        after = read_journal(leaf.store.path)
        validator = execution_refusal if mutates else preview_refusal
        evidence = validator(job, before, after, request_id=request_id,
                             arguments=args, expected_code=expected_code)
        require(evidence['replay'] is replay, 'Only the expected first dispatch or exact replay is allowed.')
        jobs.append(job); proofs.append(evidence)
        return job

    def dispatch():
        invoke('feature.prepare_leaf_deletion', context, preview, mutates=False, replay=False)
        invoke('feature.prepare_leaf_deletion', context, forbidden, mutates=False, replay=True)
        invoke('feature.delete_leaf', arguments, execute, mutates=True, replay=False)
        last = invoke('feature.delete_leaf', arguments, forbidden, mutates=True, replay=True)
        require(calls == {'preview': 1, 'execute': 1}
                and jobs[0] == jobs[1] and jobs[2] == jobs[3]
                and leaf.store.mutation_blockers(binding.connection_epoch, binding.document_id,
                                                 effect_scope='application') == [],
                'Exact refusal jobs/replays, one domain call each and no hold required.')
        return last

    observation = run_observed_refusal(session, dispatch, expected_code=expected_code, progress=progress)
    return dict(scope=SCOPE, fixture_case=target.fixture.case, jobs=jobs, journal_proofs=proofs,
                observation=observation, domain_calls=calls, refusal_batch_passed=True,
                accepted=False, native_b2_accepted=False, public_mcp_accepted=False,
                cleanup_authorized=False, open_gates=['installed_wheel_native_driver',
                                                     'terminal_own_cleanup_original_baseline'])
