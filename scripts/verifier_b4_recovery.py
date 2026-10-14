"""Passive B4 restart receipt coherence; never a process/CAD safety permit.

Inputs are complete raw ``read_journal`` observations, not public job DTOs.
The native owner separately proves that COM returned before stopping its own
server. This module cannot prove that, stop a process, reconcile or clean CAD.
An accepted receipt is journal evidence only, never native B4 acceptance.
"""
from copy import deepcopy
import hashlib
import importlib.util
import math
from pathlib import Path
import sys

from solidworks_mcp.jobs import JobError, _json


# Import only the existing passive reader, without depending on caller sys.path.
_name = '_b4_passive_lifecycle'
_spec = importlib.util.spec_from_file_location(_name, Path(__file__).with_name('verifier_lifecycle.py'))
_module = importlib.util.module_from_spec(_spec)
_prior = sys.modules.get(_name)
sys.modules[_name] = _module
try:
    _spec.loader.exec_module(_module)
finally:
    if _prior is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _prior
read_journal = _module.read_journal

JOB_KEYS = frozenset(('operation_id', 'request_id', 'digest', 'operation', 'payload',
                     'status', 'created_at', 'updated_at', 'result', 'error', 'mutation'))
MUTATION_KEYS = frozenset(('operation_id', 'connection_epoch', 'document_id',
                          'configuration', 'expected_revision', 'before_state',
                          'phase', 'verification', 'reconciliation', 'updated_at'))
STATUSES = frozenset(('queued', 'running', 'succeeded', 'failed', 'cancelled', 'unknown'))
PHASES = frozenset(('prepared', 'committed', 'rolled_back', 'not_started', 'unresolved', 'reconciled'))
RESTART_MESSAGE = 'Previous runtime stopped before confirming completion; reconcile before retrying.'


def _require(value, message):
    if not value:
        raise ValueError(message)


def _time(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _equal(a, b):
    # JSON also distinguishes forged True from integer sequence/timestamp 1.
    return _json(a) == _json(b)


def _rows(rows):
    _require(type(rows) is list and 0 < len(rows) <= 100000, 'Complete nonempty raw journal required.')
    indexed, requests = {}, set()
    for row in rows:
        _require(type(row) is dict and set(row) == JOB_KEYS, 'Raw job schema/digest required.')
        try:
            _json(row)
        except JobError as exc:
            raise ValueError('Journal must contain finite JSON evidence.') from exc
        for key in ('operation_id', 'request_id', 'operation', 'digest'):
            _require(type(row[key]) is str and row[key], 'Nonempty journal identity required.')
        _require(row['operation_id'] not in indexed and row['request_id'] not in requests,
                 'Duplicate operation/request identity.')
        payload = row['payload']
        _require(type(payload) is dict and set(payload) == {'arguments', 'context', 'mutates'}
                 and type(payload['arguments']) is dict and type(payload['context']) is dict
                 and type(payload['mutates']) is bool, 'Invalid durable payload.')
        digest = hashlib.sha256((row['operation'] + '\n' + _json(payload)).encode('utf-8')).hexdigest()
        _require(row['digest'] == digest, 'Durable payload digest mismatch.')
        _require(type(row['status']) is str and row['status'] in STATUSES
                 and _time(row['created_at']) and _time(row['updated_at'])
                 and row['updated_at'] >= row['created_at'], 'Invalid status/timestamps.')
        mutation = row['mutation']
        if mutation is not None:
            _require(type(mutation) is dict and set(mutation) == MUTATION_KEYS, 'Complete checkpoint required.')
            _require(mutation['operation_id'] == row['operation_id'] and payload['mutates'] is True,
                     'Checkpoint must belong to mutating job.')
            _require(type(mutation['phase']) is str and mutation['phase'] in PHASES
                     and _time(mutation['updated_at']), 'Invalid checkpoint phase/time.')
            _require(type(mutation['before_state']) is dict, 'Raw before-state required.')
            for key in ('connection_epoch', 'document_id', 'expected_revision'):
                _require(type(mutation[key]) is str and mutation[key], 'Explicit checkpoint scope required.')
            _require(type(mutation['configuration']) is str, 'Explicit configuration required.')
            if mutation['connection_epoch'] != 'legacy-unbound':
                _require(all(payload['context'].get(k) == mutation[k]
                             for k in ('document_id', 'configuration', 'expected_revision')),
                         'Checkpoint/request scope mismatch.')
            for key in ('verification', 'reconciliation'):
                _require(mutation[key] is None or type(mutation[key]) is dict, 'Invalid checkpoint evidence.')
        indexed[row['operation_id']] = row
        requests.add(row['request_id'])
    return indexed


def required_hold_queries(before, *, new_epoch, other_document):
    """Finite mandatory blocker probes, including new epoch and other document.

    These describe queries the external observer must actually perform; they
    neither call JobStore nor infer that a process has stopped.
    """
    indexed = _rows(before)
    _require(type(new_epoch) is str and new_epoch and type(other_document) is str and other_document,
             'Fresh epoch and distinct probe document required.')
    mutations = [r['mutation'] for r in indexed.values() if r['mutation'] is not None]
    _require(new_epoch not in {m['connection_epoch'] for m in mutations}, 'Probe epoch must be new.')
    _require(other_document not in {m['document_id'] for m in mutations}, 'Probe document must be distinct.')
    probes = {(new_epoch, other_document, scope) for scope in ('document', 'application')}
    for mutation in mutations:
        for epoch in (mutation['connection_epoch'], new_epoch):
            for document in (mutation['document_id'], other_document):
                for scope in ('document', 'application'):
                    probes.add((epoch, document, scope))
    return [dict(connection_epoch=e, document_id=d, effect_scope=s) for e, d, s in sorted(probes)]


def validate_restart_receipts(*, before, after, hold_observations, new_epoch, other_document):
    """Prove exact recovery changes and observed blockers, without native claims.

    No new jobs or appended native steps are allowed in the bounded observation
    window. Existing terminal rows remain byte-value-equivalent JSON. Unfinished
    rows become unknown; prepared checkpoints become unresolved while their
    entire scope, before-state, pending/returned ledger and evidence survive.
    """
    old, new = _rows(before), _rows(after)
    _require(set(old) == set(new), 'Missing or extra journal jobs across restart.')
    unfinished = [key for key, row in old.items() if row['status'] in ('queued', 'running')]
    _require(unfinished, 'No unfinished job: recovery was not exercised.')
    _require(any(old[key]['payload']['mutates'] is True for key in unfinished),
             'No unfinished mutation: mandatory recovery holds were not exercised.')
    for key, row in old.items():
        observed = new[key]
        if row['status'] not in ('queued', 'running'):
            _require(_equal(row, observed), 'Restart rewrote terminal historical job/checkpoint.')
            continue
        expected = deepcopy(row)
        if row['status'] in ('queued', 'running'):
            _require(observed['updated_at'] >= row['updated_at'], 'Recovery timestamp moved backwards.')
            expected.update(status='unknown', updated_at=observed['updated_at'],
                            error={'code': 'runtime_restarted', 'message': RESTART_MESSAGE})
        mutation = expected['mutation']
        if mutation is not None and mutation['phase'] == 'prepared':
            mutation['phase'] = 'unresolved'
        if mutation is None and expected['status'] == 'unknown' and row['payload']['mutates'] is True:
            # JobStore's conservative fallback is part of recovery, not an
            # invented exact native checkpoint. The marker remains visible.
            context = row['payload']['context']
            actual = observed['mutation']
            _require(type(actual) is dict and actual['updated_at'] >= row['created_at'],
                     'Unbound unknown mutation must retain a conservative hold.')
            expected['mutation'] = dict(operation_id=key, connection_epoch='legacy-unbound',
                document_id=str(context.get('document_id', 'unbound')),
                configuration=str(context.get('configuration', '')),
                expected_revision=str(context.get('expected_revision', 'unavailable')),
                before_state={'checkpoint_unavailable': True}, phase='unresolved',
                verification=None, reconciliation=None, updated_at=actual['updated_at'])
        _require(_equal(expected, observed), 'Restart rewrote identity, payload, history, checkpoint or native ledger.')
    queries = required_hold_queries(before, new_epoch=new_epoch, other_document=other_document)
    _require(type(hold_observations) is list and len(hold_observations) == len(queries),
             'Complete mandatory hold observations required.')
    observations = {}
    for observation in hold_observations:
        _require(type(observation) is dict and set(observation) ==
                 {'connection_epoch', 'document_id', 'effect_scope', 'blockers'}, 'Raw hold query receipt required.')
        key = tuple(observation[k] for k in ('connection_epoch', 'document_id', 'effect_scope'))
        _require(key not in observations, 'Duplicate hold query.')
        _require(type(observation['blockers']) is list, 'Raw blockers required.')
        observations[key] = observation['blockers']
    for query in queries:
        key = tuple(query[k] for k in ('connection_epoch', 'document_id', 'effect_scope'))
        _require(key in observations, 'Missing mandatory hold query.')
        expected = [r['mutation'] for r in new.values() if r['mutation'] is not None
                    and r['mutation']['phase'] in ('prepared', 'unresolved')
                    and (query['effect_scope'] == 'application'
                         or r['mutation']['before_state'].get('_mutation_effect_scope', 'document') != 'document'
                         or r['mutation']['connection_epoch'] != query['connection_epoch']
                         or r['mutation']['document_id'] == query['document_id'])]
        expected.sort(key=lambda m: (m['updated_at'], m['operation_id']))
        _require(_equal(expected, observations[key]), 'Mandatory hold missing, changed, duplicated or bypassed.')
    return dict(scope='b4_passive_restart_journal_v1', accepted=True,
                native_b4_accepted=False, process_stop_authorized=False, cad_cleanup_authorized=False,
                job_count=len(old), recovered_operation_ids=sorted(unfinished),
                unbound_mutation_ids=sorted(key for key in unfinished
                    if old[key]['payload']['mutates'] is True and old[key]['mutation'] is None),
                mandatory_hold_queries=len(queries))
