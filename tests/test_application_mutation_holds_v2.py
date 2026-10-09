"""Application side effects must not escape holds through another document."""

import pytest

from solidworks_mcp.jobs import JobError, JobStore
from solidworks_mcp.mutations import MutationCoordinator, PreparedMutation
from test_mutation_journal_v2 import context, prepared_job, store


def application_job(store, request='export', document='doc_a'):
    job, _ = store.create(request, 'export.execute', {}, context(document), mutates=True)
    store.start(job['operation_id'])
    store.prepare_mutation(job['operation_id'], connection_epoch='connection_1',
        **context(document), before_state={'preferences': {'stl_units': 0}}, effect_scope='application')
    return job['operation_id']


@pytest.mark.parametrize('terminal', [False, True])
def test_application_hold_blocks_other_document_in_same_connection(store, terminal):
    operation_id = application_job(store)
    if terminal:
        store.finish(operation_id, 'unknown')
    assert store.mutation_blockers('connection_1', 'doc_b')[0]['operation_id'] == operation_id
    assert store.get(operation_id)['mutation']['connection_epoch'] == 'connection_1'
    other, _ = store.create('other', 'feature.rename', {}, context('doc_b'), mutates=True)
    store.start(other['operation_id'])
    with pytest.raises(JobError) as error:
        store.prepare_mutation(other['operation_id'], connection_epoch='connection_1',
            **context('doc_b'), before_state={})
    assert error.value.code == 'document_mutation_blocked'


def test_application_operation_cannot_start_with_existing_other_document_hold(store):
    prepared_job(store, document='doc_b')
    with pytest.raises(JobError) as error:
        application_job(store)
    assert error.value.code == 'document_mutation_blocked'


@pytest.mark.parametrize('status,outcome', [('succeeded', 'committed'), ('failed', 'rolled_back'), ('failed', 'not_started')])
def test_only_verified_terminal_application_outcome_releases_global_hold(store, status, outcome):
    operation_id = application_job(store)
    store.verify_mutation(operation_id, outcome=outcome, evidence={'preferences_verified': True})
    assert store.mutation_blockers('connection_1', 'doc_b')
    store.finish(operation_id, status)
    assert store.mutation_blockers('connection_1', 'doc_b') == []


def test_application_hold_survives_schema_two_migration_and_restart(tmp_path):
    path = tmp_path / 'jobs.sqlite'
    first = JobStore(path)
    operation_id = application_job(first)
    # Existing schema-2 journals have no new columns. Migration preserves rows
    # and bumps the version so old runtimes cannot silently ignore the marker.
    first._db.execute('PRAGMA user_version=2')
    first.close()
    with_store = JobStore(path)
    try:
        assert with_store._db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert with_store.get(operation_id)['status'] == 'unknown'
        assert with_store.mutation_blockers('connection_1', 'doc_b')
        assert with_store.mutation_blockers('new_connection', 'new_document')
        with_store.reconcile_mutation(operation_id, resolution='restored_before',
            evidence={'all_application_preferences_independently_verified': True})
        assert with_store.get(operation_id)['status'] == 'unknown'
        assert with_store.mutation_blockers('connection_1', 'doc_b') == []
    finally:
        with_store.close()


@pytest.mark.parametrize('scope,before', [('invalid', {}), ('document', {'_mutation_effect_scope': 'application'})])
def test_effect_scope_cannot_be_forged_in_domain_before_state(store, scope, before):
    job, _ = store.create('r', 'export.execute', {}, context(), mutates=True)
    store.start(job['operation_id'])
    with pytest.raises(JobError) as error:
        store.prepare_mutation(job['operation_id'], connection_epoch='connection_1',
            **context(), before_state=before, effect_scope=scope)
    assert error.value.code == 'invalid_effect_scope'
    assert 'mutation' not in store.get(job['operation_id'])


def test_coordinator_persists_application_scope_before_first_callback_write(store):
    job, _ = store.create('r', 'export.execute', {}, context(), mutates=True)
    operation_id = job['operation_id']
    store.start(operation_id)
    coordinator = MutationCoordinator(store, 'connection_1')
    before = {'preferences': {'stl_units': 0}}

    def apply(prepared):
        assert store.mutation_blockers('connection_1', 'doc_b')[0]['operation_id'] == operation_id
        assert store.get(operation_id)['mutation']['before_state']['_mutation_effect_scope'] == 'application'
        assert prepared.before == before  # Reserved journal metadata stays out of domain verifiers.
        return {'exported': True}

    result = coordinator.execute(operation_id, **context(),
        prepare=lambda: PreparedMutation('rev_1', before, effect_scope='application'),
        validate=lambda prepared: True, apply=apply, inspect=lambda prepared: before,
        verify=lambda old, after, value: old == after, restore=lambda old, prepared: None,
        verify_restored=lambda old, after: old == after)
    assert result['verified'] is True
    assert store.mutation_blockers('connection_1', 'doc_b')
    store.finish(operation_id, 'succeeded', result=result)
    assert store.mutation_blockers('connection_1', 'doc_b') == []
