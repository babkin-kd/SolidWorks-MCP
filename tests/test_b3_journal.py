"""B3 coherence against real SQLite JobStore, with no CAD or native claims."""
import asyncio
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import JobStore


scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_journal as helper
finally:
    sys.path.remove(scripts)


@pytest.fixture
def receipt(tmp_path):
    path = tmp_path / 'jobs.sqlite'
    store = JobStore(path)
    tool = 'geometry_get'
    arguments = dict(request_id='explicit-b3', document_id='doc_a', configuration='Основная',
                     object_id='body_a', expected_observation_revision='obs_a')
    spec = helper.SPECS[tool]
    payload = spec.payload(arguments)
    job, _ = store.create(arguments['request_id'], spec.operation, payload['arguments'],
                          payload['context'], mutates=spec.mutates)
    store.start(job['operation_id'])
    store.finish(job['operation_id'], 'succeeded', result={'object': {'native_owner': 'body_a'}})
    dto = store.get(job['operation_id'])
    row = helper.read_journal(path)[0]
    yield NS(store=store, path=path, tool=tool, arguments=arguments, dto=dto, row=row)
    store.close()


def bind(r, **kwargs):
    values = dict(dto=r.dto, row=r.row, tool=r.tool, arguments=r.arguments)
    values.update(kwargs)
    return helper.bind_durable_job(**values)


def test_passive_checkpoint_absence_matches_real_decoder_without_discarding_fields(receipt):
    assert 'mutation' not in receipt.dto
    assert receipt.row['mutation'] is None
    assert bind(receipt) == receipt.row


@pytest.mark.parametrize('field,value', [('status', 'running'), ('request_id', 'other'),
    ('operation', 'geometry.list'), ('digest', '0' * 64), ('extra_private_field', 'hidden')])
def test_changed_or_extra_sql_fields_cannot_be_hidden_by_projection(receipt, field, value):
    row = deepcopy(receipt.row)
    row[field] = value
    with pytest.raises(ValueError):bind(receipt, row=row)


@pytest.mark.parametrize('field', ['operation_id', 'created_at', 'updated_at', 'result', 'payload'])
def test_dto_tampering_is_rejected(receipt, field):
    dto = deepcopy(receipt.dto)
    dto[field] = 'changed'
    with pytest.raises(ValueError):bind(receipt, dto=dto)


def test_wrong_target_with_self_consistent_digest_still_fails_original_payload(receipt):
    row = deepcopy(receipt.row)
    row['payload']['arguments']['document_id'] = 'doc_foreign'
    row['digest'] = hashlib.sha256((row['operation'] + '\n' + helper.canonical(row['payload'])).encode()).hexdigest()
    dto = {k: v for k, v in row.items() if k not in ('digest', 'mutation')}
    with pytest.raises(ValueError):bind(receipt, row=row, dto=dto)


def test_known_read_refusal_requires_explicit_code_and_no_reconciliation(receipt):
    row = deepcopy(receipt.row)
    row.update(status='failed', result=None,
               error={'code': 'object_body_mismatch', 'requires_reconciliation': False})
    dto = {k: v for k, v in row.items() if k not in ('digest', 'mutation')}
    assert bind(receipt, row=row, dto=dto, expected_error='object_body_mismatch') == row
    with pytest.raises(ValueError):bind(receipt, row=row, dto=dto)
    row['error']['requires_reconciliation'] = True
    with pytest.raises(ValueError):bind(receipt, row=row, dto=dto, expected_error='object_body_mismatch')


@pytest.mark.parametrize('status', ['unknown', 'cancelled', 'running', 'queued'])
def test_nonterminal_or_uncertain_outcome_cannot_be_success(receipt, status):
    row = deepcopy(receipt.row)
    row['status'] = status
    dto = {k: v for k, v in row.items() if k not in ('digest', 'mutation')}
    with pytest.raises(ValueError):bind(receipt, row=row, dto=dto)


def test_mass_verified_flag_without_checkpoint_does_not_grant_admission(receipt):
    tool = 'measurement_get_mass'
    args = dict(request_id='mass', document_id='doc_a', configuration='Основная', expected_revision='rev_a')
    payload = helper.SPECS[tool].payload(args)
    row = deepcopy(receipt.row)
    row.update(operation='measurement.mass', request_id='mass', payload=payload, result={'verified': True})
    row['digest'] = hashlib.sha256((row['operation'] + '\n' + helper.canonical(payload)).encode()).hexdigest()
    dto = {k: v for k, v in row.items() if k not in ('digest', 'mutation')}
    with pytest.raises(ValueError, match='checkpoint'):bind(receipt, row=row, dto=dto, tool=tool, arguments=args)


def test_mass_journal_binding_uses_real_checkpoint_and_never_claims_geometry(receipt):
    # Artificial domain evidence exercises SQLite transitions, not native mass.
    tool = 'measurement_get_mass'
    args = dict(request_id='mass', document_id='doc_a', configuration='Основная', expected_revision='rev_a')
    payload = helper.SPECS[tool].payload(args)
    job, _ = receipt.store.create('mass', 'measurement.mass', payload['arguments'], payload['context'], mutates=True)
    operation_id = job['operation_id']
    receipt.store.start(operation_id)
    receipt.store.prepare_mutation(operation_id, connection_epoch='artificial',
        document_id='doc_a', configuration='Основная', expected_revision='rev_a',
        before_state={'artificial_domain': True}, effect_scope='application')
    receipt.store.verify_mutation(operation_id, outcome='committed', evidence={'artificial_domain': True})
    receipt.store.finish(operation_id, 'succeeded', result={'verified': True, 'artificial_domain': True})
    dto = receipt.store.get(operation_id)
    row = next(r for r in helper.read_journal(receipt.path) if r['operation_id'] == operation_id)
    assert bind(receipt, row=row, dto=dto, tool=tool, arguments=args) == row
    row['mutation']['expected_revision'] = 'rev_foreign'
    dto['mutation']['expected_revision'] = 'rev_foreign'
    with pytest.raises(ValueError, match='checkpoint'):bind(receipt, row=row, dto=dto, tool=tool, arguments=args)


def test_missing_sql_checkpoint_column_cannot_be_inferred(receipt):
    row = deepcopy(receipt.row)
    row.pop('mutation')
    with pytest.raises(ValueError, match='schema'):bind(receipt, row=row)


def test_replay_binds_entire_row_not_only_result(receipt):
    index = helper.ReceiptIndex()
    index.add(tool=receipt.tool, arguments=receipt.arguments, row=bind(receipt))
    index.add(tool=receipt.tool, arguments=receipt.arguments, row=bind(receipt))
    row = deepcopy(receipt.row)
    row['operation_id'] = 'replacement_job'
    with pytest.raises(ValueError, match='Replay'):
        index.add(tool=receipt.tool, arguments=receipt.arguments, row=row)


class Client:
    def __init__(self, receipt, *, safe=True, dto=None):
        self.receipt, self.safe = receipt, safe
        self.dto = dto if dto is not None else receipt.dto
        self.calls, self.retained = [], []

    async def observe_once(self):
        return NS(child_can_close=self.safe, fixture_can_cleanup=self.safe)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return NS(isError=False, structuredContent={'status': 'succeeded', 'data': self.dto})

    def retain(self, reason):self.retained.append(reason)


def observe(receipt, client):
    return asyncio.run(helper.observe_durable_job(client, receipt.path,
        operation_id=receipt.row['operation_id'], tool=receipt.tool, arguments=receipt.arguments))


def test_live_observation_binds_independent_coherent_sqlite_snapshot(receipt):
    client = Client(receipt)
    assert observe(receipt, client) == receipt.row
    assert client.calls == [('job_get', {'operation_id': receipt.row['operation_id']})]
    assert client.retained == []


def test_unsafe_supervisor_does_not_poll_or_trigger_new_dispatch(receipt):
    client = Client(receipt, safe=False)
    with pytest.raises(RuntimeError):observe(receipt, client)
    assert client.calls == []


def test_protocol_failure_quarantines_the_live_owner(receipt):
    dto = deepcopy(receipt.dto)
    dto['result'] = {'concealed_difference': True}
    client = Client(receipt, dto=dto)
    with pytest.raises(ValueError):observe(receipt, client)
    assert len(client.retained) == 1
