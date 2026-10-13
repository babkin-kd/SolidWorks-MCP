"""Passive journal proof for a refused leaf preview; never CAD acceptance.

The native owner supplies coherent read-only SQL snapshots and the public DTO.
No connections, native handles, dispatch, retry or cleanup are performed here.
An unsupported extra plane/equation still needs its own complete native oracle.
"""
from copy import deepcopy
import hashlib
import re

from solidworks_mcp.jobs import _json


SCOPE = 'b2_leaf_preview_refusal_journal_v1'
ERROR_CODES = frozenset({'leaf_deletion_unsupported', 'first_save_snapshot_unsupported'})
FIELDS = frozenset({'operation_id', 'request_id', 'digest', 'operation', 'payload',
                    'status', 'created_at', 'updated_at', 'result', 'error', 'mutation'})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _index(rows):
    _require(type(rows) is list and len(rows) <= 100000, 'Complete bounded journal required.')
    indexed = {}
    for row in rows:
        _require(type(row) is dict and set(row) == FIELDS, 'Complete SQL row schema required.')
        _json(row)
        operation_id = row['operation_id']
        _require(type(operation_id) is str and bool(operation_id) and operation_id not in indexed,
                 'Unique durable operation IDs required.')
        indexed[operation_id] = row
    return indexed


def preview_refusal(public_dto, before, after, *, request_id, arguments, expected_code):
    """Bind one failed read-only preview, preserving every earlier durable row.

    Both a first dispatch and an exact replay are allowed. The result only proves
    journal/DTO consistency and absence of a checkpoint, not absence of CAD effects.
    """
    _require(type(request_id) is str and 0 < len(request_id) <= 256 and bool(request_id.strip()),
             'Exact request ID required.')
    _require(type(arguments) is dict and set(arguments) == {'document_id', 'configuration', 'object_id'}
             and all(type(value) is str and bool(value.strip()) for value in arguments.values())
             and re.fullmatch(r'feat_[0-9a-f]{32}', arguments['object_id']) is not None,
             'Exact document/configuration/original feature arguments required.')
    _require(type(expected_code) is str and expected_code in ERROR_CODES,
             'Only the finite unsupported preview refusals are covered.')
    _require(type(public_dto) is dict and 'operation_id' in public_dto,
             'Actual public job DTO required.')
    first, last = _index(before), _index(after)
    operation_id = public_dto['operation_id']
    _require(type(operation_id) is str and operation_id in last,
             'Public job must exist in the coherent SQL snapshot.')
    _require(set(first) <= set(last) and set(last) - set(first) in (set(), {operation_id})
             and all(_json(row) == _json(last[key]) for key, row in first.items()),
             'Preview/replay changed prior evidence or added unrelated jobs.')
    row = last[operation_id]
    payload = dict(arguments=arguments, context=arguments, mutates=False)
    digest = hashlib.sha256(('feature.prepare_leaf_deletion\n' + _json(payload)).encode('utf8')).hexdigest()
    _require(row['operation'] == 'feature.prepare_leaf_deletion' and row['request_id'] == request_id
             and row['digest'] == digest and _json(row['payload']) == _json(payload),
             'SQL operation/payload/request/digest mismatch.')
    _require(row['status'] == 'failed' and row['result'] is None and row['mutation'] is None
             and type(row['error']) is dict and set(row['error']) == {'code', 'message'}
             and row['error']['code'] == expected_code and type(row['error']['message']) is str
             and bool(row['error']['message'].strip()),
             'Expected terminal unsupported preview without a checkpoint required.')
    published = {key: value for key, value in row.items() if key not in ('digest', 'mutation')}
    _require(_json(published) == _json(public_dto), 'Every public DTO field must match actual SQL.')
    return dict(scope=SCOPE, operation_id=operation_id, request_id=request_id,
                journal_refusal_verified=True, replay=operation_id in first,
                refused_job=deepcopy(row), accepted=False, native_b2_accepted=False,
                public_mcp_accepted=False, cleanup_authorized=False,
                complete_native_before_after_verified=False,
                open_gates=['complete_current_native_refusal_oracle',
                            'own_fixture_cleanup_and_original_baseline'])
