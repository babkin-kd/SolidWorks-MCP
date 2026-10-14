"""Actual domain/runner/SQL refusal batch on artificial native fixture handles."""
from pathlib import Path
import sys

import pytest
from solidworks_mcp.jobs import JobRunner
from test_b2_impact_target import target, fixture, leaf, extrusion_proof, proof, case, domain
from test_b2_impact_refusal import InlineWorker

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b2_impact_internal import run_impact_refusals
    from verifier_b2_impact_session import B2ImpactSession
    from verifier_lifecycle import read_journal
finally:
    sys.path.remove(scripts)


@pytest.fixture
def batch(target):
    x = target
    context = dict(document_id=x.binding.document_id, configuration=x.binding.configuration,
                   object_id=x.binding.object_id)
    x.runner = JobRunner(x.store, InlineWorker())
    x.preparation = x.runner.submit('n5-base-preparation', 'feature.prepare_leaf_deletion', context,
                                    lambda: x.leaf.prepare(**context), context=context)
    assert x.preparation['status'] == 'succeeded'
    created = x.helper.add_child_plane(x.c.baseline)
    x.store.verify_mutation(x.operation_id, outcome='committed', evidence=created)
    x.store.finish(x.operation_id, 'succeeded', result=created)
    neighbor = next(entry for entry in x.entries if entry.document_id == 'neighbor')
    before = x.c.adapter.rectangle_construction_snapshot(neighbor.model)
    x.session = B2ImpactSession(x.collector, neighbor, before)
    return x


def run(x, **changes):
    values = dict(expected_code='leaf_deletion_unsupported')
    values.update(changes)
    return run_impact_refusals(x.leaf, x.runner, x.session, x.preparation, **values)


def test_real_domain_batch_checks_preview_execute_and_identical_replays_under_one_envelope(batch):
    x = batch
    writes = list(x.write_calls)
    result = run(x)
    assert result['domain_calls'] == {'preview': 1, 'execute': 1}
    assert len(result['jobs']) == 4 and len(result['journal_proofs']) == 4
    assert result['jobs'][0] == result['jobs'][1] and result['jobs'][2] == result['jobs'][3]
    assert [row['replay'] for row in result['journal_proofs']] == [False, True, False, True]
    assert all(row['status'] == 'failed' and 'mutation' not in row for row in result['jobs'])
    assert x.write_calls == writes
    assert all(result[key] is False for key in ('accepted', 'native_b2_accepted',
        'public_mcp_accepted', 'cleanup_authorized'))
    assert result['refusal_batch_passed'] is True
    assert len(x.ancillary_calls) == 2  # Full target read once before/after the whole batch.
    assert x.store.mutation_blockers('epoch', x.binding.document_id, effect_scope='application') == []


@pytest.mark.parametrize('fault', ['bad_preparation', 'wrong_error', 'active_setup', 'unknown_execute'])
def test_unconfirmed_job_or_incomplete_setup_cannot_dispatch_a_second_batch_or_after_read(batch, fault):
    x = batch
    if fault == 'bad_preparation': x.preparation['result']['creation_operation_id'] = 'foreign'
    elif fault == 'active_setup':
        x.store.create('uncompleted-setup', 'verifier.incomplete', {}, mutates=True)
    elif fault == 'unknown_execute':
        def fail(*args, **kwargs): raise RuntimeError('Artificial uncertain execution')
        x.leaf.delete = fail
    args = {'expected_code': 'first_save_snapshot_unsupported'} if fault == 'wrong_error' else {}
    writes = list(x.write_calls)
    with pytest.raises((ValueError, AssertionError, RuntimeError)):
        run(x, **args)
    assert x.write_calls == writes
    assert len(x.ancillary_calls) <= 1
    rows = read_journal(x.store.path)
    if fault == 'unknown_execute':
        assert rows[-1]['status'] == 'unknown'
        assert x.store.mutation_blockers('epoch', x.binding.document_id, effect_scope='application')
