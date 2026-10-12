"""Independent B3 DTO/SQLite coherence, never geometric or native acceptance.

The caller's live supervisor owns quiescence and guarded mass proofs. This
module binds the public tool/request to the complete independent journal row.
Read DTOs omit an absent mutation; SQL observations explicitly contain None.
No other public field may be silently discarded or inferred.
"""
from copy import deepcopy
import hashlib
import json

import anyio

from verifier_b3_public_contract import SPECS
from verifier_lifecycle import read_journal


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':'))


def bind_durable_job(*, dto, row, tool, arguments, expected_error=None):
    """Bind one terminal observation, leaving CAD assertions to native oracles."""
    spec = SPECS[tool]
    if type(dto) is not dict or type(row) is not dict or type(arguments) is not dict:
        raise ValueError('Complete DTO, coherent SQL row and explicit arguments required.')
    required = {'operation_id', 'request_id', 'operation', 'digest', 'payload',
                'status', 'created_at', 'updated_at', 'result', 'error', 'mutation'}
    if set(row) != required:
        raise ValueError('Complete schema-three journal row required.')
    request_id = arguments.get('request_id')
    if type(request_id) is not str or not request_id:
        raise ValueError('An explicit original request_id is required.')
    payload = spec.payload(arguments)
    digest = hashlib.sha256((spec.operation + '\n' + canonical(payload)).encode('utf8')).hexdigest()
    if (row.get('operation') != spec.operation or row.get('request_id') != request_id
            or canonical(row.get('payload')) != canonical(payload) or row.get('digest') != digest):
        raise ValueError('Tool, original request or payload digest differs from independent journal.')
    projection = deepcopy(row)
    projection.pop('digest')
    if projection.get('mutation') is None:
        projection.pop('mutation', None)  # JobStore._decode omits absent checkpoints.
    if canonical(projection) != canonical(dto):
        raise ValueError('Complete public DTO differs from independent SQL projection.')
    mutation = row.get('mutation')
    if expected_error is None:
        if row.get('status') != 'succeeded' or row.get('error') is not None or row.get('result') is None:
            raise ValueError('A successful terminal journal result is required.')
        if spec.mutates:
            if (type(mutation) is not dict or mutation.get('phase') != 'committed'
                    or type(row['result']) is not dict or row['result'].get('verified') is not True
                    or mutation.get('document_id') != payload['arguments'].get('document_id')
                    or mutation.get('configuration') != payload['arguments'].get('configuration')
                    or mutation.get('expected_revision') != payload['arguments'].get('expected_revision')
                    or (mutation.get('verification') or {}).get('outcome') != 'committed'):
                raise ValueError('Guarded mass lacks its exact committed checkpoint.')
        elif mutation is not None:
            raise ValueError('Passive B3 read unexpectedly has a mutation checkpoint.')
    else:
        error = row.get('error') or {}
        if (type(expected_error) is not str or not expected_error or spec.mutates
                or row.get('status') != 'failed' or row.get('result') is not None
                or mutation is not None or error.get('code') != expected_error
                or error.get('requires_reconciliation') is not False):
            raise ValueError('Only an explicit known passive-read refusal may be admitted.')
    return deepcopy(row)


async def assert_supervisor_safe(client):
    # Observation deadlines/cancellation must not authorize native readback.
    with anyio.CancelScope(shield=True):
        decision = await client.observe_once()
    if decision.child_can_close is not True or decision.fixture_can_cleanup is not True:
        raise RuntimeError('Native/journal quiescence unconfirmed; retain fixtures and live owner.')


async def observe_durable_job(client, journal_path, *, operation_id, tool, arguments,
                              expected_error=None):
    """Fresh supervisor proof, public job_get, then one complete SQLite snapshot."""
    await assert_supervisor_safe(client)
    try:
        raw = await client.call_tool('job_get', {'operation_id': operation_id})
        if raw.isError is not False or type(raw.structuredContent) is not dict:
            raise ValueError('No complete public job_get envelope.')
        envelope = raw.structuredContent
        status = 'succeeded' if expected_error is None else 'failed'
        if envelope.get('status') != status or type(envelope.get('data')) is not dict:
            raise ValueError('Public job_get did not return a complete DTO.')
        dto = envelope['data']
        if (envelope.get('operation_id') != operation_id or dto.get('operation_id') != operation_id
                or envelope.get('status') != dto.get('status')
                or canonical(envelope.get('context')) != canonical((dto.get('payload') or {}).get('context'))
                or canonical(envelope.get('error')) != canonical(dto.get('error'))):
            raise ValueError('Public job_get envelope disagrees with its bound job.')
        matches = [row for row in read_journal(journal_path) if row['operation_id'] == operation_id]
        if len(matches) != 1:
            raise ValueError('One exact operation must occur in the coherent journal.')
        return bind_durable_job(dto=dto, row=matches[0], tool=tool,
                                arguments=arguments, expected_error=expected_error)
    except BaseException:
        client.retain('B3 public DTO/independent journal observation unconfirmed')
        raise


class ReceiptIndex:
    """A replay must bind the same full terminal row, never a new operation."""
    def __init__(self):
        self._requests = {}

    def add(self, *, tool, arguments, row, expected_error=None):
        key = arguments.get('request_id')
        if type(key) is not str or not key:
            raise ValueError('Explicit replay request required.')
        projection = {name: value for name, value in row.items() if name != 'digest'}
        if projection.get('mutation') is None:
            projection.pop('mutation', None)
        bind_durable_job(dto=projection, row=row, tool=tool, arguments=arguments, expected_error=expected_error)
        value = canonical(dict(tool=tool, payload=SPECS[tool].payload(arguments),
                               expected_error=expected_error, row=row))
        if key in self._requests and self._requests[key] != value:
            raise ValueError('Replay changed tool, payload, operation or durable result.')
        self._requests[key] = value
