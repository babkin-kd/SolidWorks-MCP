"""Durable, idempotent jobs; no COM objects or executable code in the journal.

An operation supplied by the domain layer must validate its own postconditions.
After a crash unfinished jobs are uncertain, never automatically replayed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable
import uuid


TERMINAL = frozenset({'succeeded', 'failed', 'cancelled', 'unknown'})
JOURNAL_SCHEMA_VERSION = 2


class JobError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ExecutionFailure(JobError):
    """Domain-confirmed failure; set uncertain unless unchanged/rollback verified."""

    def __init__(self, code: str, message: str, *, uncertain: bool = True):
        super().__init__(code, message)
        self.uncertain = uncertain


def _json(value) -> str:
    def validate(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise JobError('invalid_payload', 'JSON object keys must be strings.')
            for child in item.values():
                validate(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                validate(child)
    validate(value)
    try:
        # Round-trip also prevents callers retaining mutable references to data.
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise JobError('invalid_payload', 'Job data must be finite JSON values.') from exc


class _OwnerLock:
    """OS-owned lock, released on process death; a stale file is not ownership."""

    def __init__(self, path: Path):
        self.file = path.open('a+b')
        if self.file.seek(0, os.SEEK_END) == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise JobError('journal_in_use', 'Another runtime owns this job journal.') from exc

    def close(self):
        if self.file.closed:
            return
        self.file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.file.close()


class JobStore:
    """One live owner, atomic transitions, thread-safe reads independent of CAD."""

    def __init__(self, path: str | Path):
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._owner = _OwnerLock(path.with_suffix(path.suffix + '.lock'))
        self._db = None
        try:
            self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            self._db.row_factory = sqlite3.Row
            version = self._db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, JOURNAL_SCHEMA_VERSION):
                raise JobError('journal_version', f'Unsupported journal schema {version}.')
            self._db.execute('PRAGMA journal_mode=WAL')
            self._db.execute('PRAGMA synchronous=FULL')
            self._db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS jobs (
                    operation_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    digest TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('queued','running','succeeded','failed','cancelled','unknown')),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    result TEXT,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created_at, operation_id);
                CREATE TABLE IF NOT EXISTS mutations (
                    operation_id TEXT PRIMARY KEY REFERENCES jobs(operation_id),
                    connection_epoch TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    configuration TEXT NOT NULL,
                    expected_revision TEXT NOT NULL,
                    before_state TEXT NOT NULL,
                    phase TEXT NOT NULL CHECK(phase IN
                        ('prepared','committed','rolled_back','not_started','unresolved','reconciled')),
                    verification TEXT,
                    reconciliation TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS mutations_phase ON mutations(phase);
                PRAGMA user_version=2;
                COMMIT;
            ''')
            self._db.execute("UPDATE jobs SET status='unknown', updated_at=?, error=? "
                             "WHERE status IN ('queued','running')", (time.time(), _json({
                'code': 'runtime_restarted',
                'message': 'Previous runtime stopped before confirming completion; reconcile before retrying.'
            })))
            # v1 had no document holds. Import uncertain mutations conservatively:
            # after a reconnect we cannot associate an old opaque ID with a live
            # native document, so such a hold blocks all new writes, never reads.
            self._db.execute("UPDATE mutations SET phase='unresolved' WHERE phase='prepared'")
            for row in self._db.execute("SELECT * FROM jobs WHERE status='unknown'").fetchall():
                payload = json.loads(row['payload'])
                if payload.get('mutates') is not True:
                    continue
                self._record_unbound_mutation(row['operation_id'], payload)
        except BaseException:
            self.close()
            raise

    def _ensure_open(self):
        if self._db is None:
            raise JobError('journal_closed', 'The job journal is closed.')

    def _decode(self, row):
        job = dict(row)
        job.pop('digest')
        for key in ('payload', 'result', 'error'):
            if job[key] is not None:
                job[key] = json.loads(job[key])
        checkpoint = self._db.execute('SELECT * FROM mutations WHERE operation_id=?',
                                      (job['operation_id'],)).fetchone()
        if checkpoint is not None:
            job['mutation'] = self._decode_mutation(checkpoint)
        return job

    @staticmethod
    def _decode_mutation(row):
        value = dict(row)
        for key in ('before_state', 'verification', 'reconciliation'):
            if value[key] is not None:
                value[key] = json.loads(value[key])
        return value

    def _record_unbound_mutation(self, operation_id, payload):
        context = payload.get('context', {})
        self._db.execute('INSERT OR IGNORE INTO mutations VALUES (?,?,?,?,?,?,?,?,?,?)', (
            operation_id, 'legacy-unbound', str(context.get('document_id', 'unbound')),
            str(context.get('configuration', '')), str(context.get('expected_revision', 'unavailable')),
            _json({'checkpoint_unavailable': True}), 'unresolved', None, None, time.time()))

    def mutation_blockers(self, connection_epoch: str, document_id: str) -> list[dict]:
        """Same connection: hold the exact document, across configurations.

        Across connections opaque IDs cannot be re-associated safely. An old
        unresolved hold therefore protects every mutation until reconciliation.
        """
        with self._lock:
            self._ensure_open()
            rows = self._db.execute("SELECT * FROM mutations WHERE phase IN ('prepared','unresolved') "
                                    'AND (connection_epoch<>? OR document_id=?) ORDER BY updated_at,operation_id',
                                    (connection_epoch, document_id)).fetchall()
            return [self._decode_mutation(row) for row in rows]

    def prepare_mutation(self, operation_id: str, *, connection_epoch: str, document_id: str,
                         configuration: str, expected_revision: str, before_state: dict):
        """Server-owned checkpoint: commit to disk BEFORE the first native write."""
        if any(not isinstance(value, str) or not value for value in
               (connection_epoch, document_id, expected_revision)) or not isinstance(configuration, str):
            raise JobError('invalid_mutation_context', 'Explicit connection, document, configuration and revision required.')
        if not isinstance(before_state, dict):
            raise JobError('invalid_checkpoint', 'The before-state must be a JSON object.')
        encoded = _json(before_state)
        with self._lock:
            self._ensure_open()
            self._db.execute('BEGIN IMMEDIATE')
            try:
                job = self.get(operation_id)
                context = job['payload']['context']
                if job['status'] != 'running' or job['payload']['mutates'] is not True:
                    raise JobError('invalid_transition', 'Only a running mutating job can prepare a checkpoint.')
                if any(context.get(key) != value for key, value in (
                        ('document_id', document_id), ('configuration', configuration),
                        ('expected_revision', expected_revision))):
                    raise JobError('mutation_context_mismatch', 'Checkpoint target must match the durable request context.')
                if 'mutation' in job:
                    raise JobError('mutation_already_prepared', 'A mutation checkpoint cannot be replayed.')
                if self.mutation_blockers(connection_epoch, document_id):
                    raise JobError('document_mutation_blocked', 'Reconcile pending/uncertain changes before another write.')
                self._db.execute('INSERT INTO mutations VALUES (?,?,?,?,?,?,?,?,?,?)', (
                    operation_id, connection_epoch, document_id, configuration, expected_revision,
                    encoded, 'prepared', None, None, time.time()))
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK')
                raise

    def verify_mutation(self, operation_id: str, *, outcome: str, evidence: dict):
        """Trusted domain verifier records evidence; a bare failed status cannot unlock."""
        if outcome not in ('committed', 'rolled_back', 'not_started') or not isinstance(evidence, dict) or not evidence:
            raise JobError('invalid_verification', 'An explicit verified outcome and nonempty evidence are required.')
        encoded = _json({'outcome': outcome, 'evidence': evidence})
        with self._lock:
            self._ensure_open()
            changed = self._db.execute("UPDATE mutations SET verification=?,updated_at=? "
                "WHERE operation_id=? AND phase='prepared' AND EXISTS "
                "(SELECT 1 FROM jobs WHERE jobs.operation_id=mutations.operation_id AND status='running')",
                (encoded, time.time(), operation_id)).rowcount
            if changed != 1:
                raise JobError('invalid_transition', 'Only a prepared running mutation can be verified.')

    def reconcile_mutation(self, operation_id: str, *, resolution: str, evidence: dict):
        """Internal domain entry point AFTER observing and verifying native state.

        Not an MCP tool or a client-provided success flag. Historical unknown job
        status remains unknown; separate evidence releases only this exact hold.
        """
        if resolution not in ('accept_current_state', 'restored_before') or not isinstance(evidence, dict) or not evidence:
            raise JobError('invalid_reconciliation', 'Verified current-state evidence and an explicit resolution required.')
        encoded = _json({'resolution': resolution, 'evidence': evidence})
        with self._lock:
            self._ensure_open()
            changed = self._db.execute("UPDATE mutations SET phase='reconciled',reconciliation=?,updated_at=? "
                "WHERE operation_id=? AND phase='unresolved' AND EXISTS "
                "(SELECT 1 FROM jobs WHERE jobs.operation_id=mutations.operation_id AND status='unknown')",
                (encoded, time.time(), operation_id)).rowcount
            if changed != 1:
                raise JobError('invalid_transition', 'Only a terminal unknown mutation can be reconciled.')
            return self.get(operation_id)

    def create(self, request_id: str, operation: str, arguments: dict,
               context: dict | None = None, *, mutates: bool = False):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256:
            raise JobError('invalid_request_id', 'request_id must contain 1–256 characters.')
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 128:
            raise JobError('invalid_operation', 'An operation name is required (up to 128 characters).')
        if not isinstance(arguments, dict) or (context is not None and not isinstance(context, dict)):
            raise JobError('invalid_payload', 'Arguments and context must be JSON objects.')
        if not isinstance(mutates, bool):
            raise JobError('invalid_payload', 'mutates must be a boolean.')
        payload = _json({'arguments': arguments, 'context': context or {}, 'mutates': mutates})
        digest = hashlib.sha256((operation + '\n' + payload).encode('utf-8')).hexdigest()
        with self._lock:
            self._ensure_open()
            self._db.execute('BEGIN IMMEDIATE')
            try:
                prior = self._db.execute('SELECT * FROM jobs WHERE request_id=?', (request_id,)).fetchone()
                if prior:
                    if prior['digest'] != digest:
                        raise JobError('request_conflict', 'request_id was already used with different parameters.')
                    self._db.execute('COMMIT')
                    return self._decode(prior), False
                now = time.time()
                operation_id = 'job_' + uuid.uuid4().hex
                self._db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,NULL,NULL)',
                                 (operation_id, request_id, digest, operation, payload, 'queued', now, now))
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK')
                raise
            return self.get(operation_id), True

    def get(self, operation_id: str) -> dict:
        with self._lock:
            self._ensure_open()
            row = self._db.execute('SELECT * FROM jobs WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None:
                raise JobError('job_not_found', 'No job with this operation_id.')
            return self._decode(row)

    def list(self, *, limit: int = 100, before_created_at: float | None = None,
             before_operation_id: str = '') -> dict:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise JobError('invalid_limit', 'limit must be an integer between 1 and 1000.')
        if before_created_at is None:
            if before_operation_id:
                raise JobError('invalid_cursor', 'Both cursor fields must be supplied together.')
        elif (isinstance(before_created_at, bool) or not isinstance(before_created_at, (int, float))
              or not math.isfinite(before_created_at) or not isinstance(before_operation_id, str)
              or not before_operation_id):
            raise JobError('invalid_cursor', 'A finite timestamp and operation_id are required for pagination.')
        with self._lock:
            self._ensure_open()
            if before_created_at is None:
                rows = self._db.execute('SELECT * FROM jobs ORDER BY created_at DESC, operation_id DESC LIMIT ?',
                                        (limit + 1,)).fetchall()
            else:
                rows = self._db.execute('SELECT * FROM jobs WHERE created_at<? OR '
                                        '(created_at=? AND operation_id<?) '
                                        'ORDER BY created_at DESC, operation_id DESC LIMIT ?',
                                        (before_created_at, before_created_at, before_operation_id, limit + 1)).fetchall()
            items = [self._decode(row) for row in rows[:limit]]
            cursor = None
            if len(rows) > limit:
                cursor = {key: items[-1][key] for key in ('created_at', 'operation_id')}
            return {'items': items, 'next_cursor': cursor}

    def _transition(self, operation_id, expected, status, *, result=None, error=None):
        # Encode before the write: invalid results cannot leave a false success.
        encoded_result = _json(result) if result is not None else None
        encoded_error = _json(error) if error is not None else None
        with self._lock:
            self._ensure_open()
            placeholders = ','.join('?' for _ in expected)
            changed = self._db.execute(
                f'UPDATE jobs SET status=?,updated_at=?,result=?,error=? WHERE operation_id=? AND status IN ({placeholders})',
                (status, time.time(), encoded_result, encoded_error, operation_id, *expected)).rowcount
            self.get(operation_id)  # Unknown IDs fail even if no row changed.
            return bool(changed)

    def start(self, operation_id):
        return self._transition(operation_id, ('queued',), 'running')

    def cancel(self, operation_id):
        changed = self._transition(operation_id, ('queued',), 'cancelled')
        return {**self.get(operation_id), 'cancelled': changed,
                'cancellation_supported': self.get(operation_id)['status'] in ('queued', 'cancelled')}

    def finish(self, operation_id, status, *, result=None, error=None):
        if status not in ('succeeded', 'failed', 'unknown'):
            raise JobError('invalid_transition', 'Completion must be succeeded, failed or unknown.')
        # Terminal status and document hold must change in ONE transaction. A
        # crash between separate updates could permit a write after uncertainty.
        encoded_result = _json(result) if result is not None else None
        encoded_error = _json(error) if error is not None else None
        with self._lock:
            self._ensure_open()
            self._db.execute('BEGIN IMMEDIATE')
            try:
                job = self.get(operation_id)
                if job['status'] != 'running':
                    raise JobError('invalid_transition', 'Only a running job can finish.')
                checkpoint = job.get('mutation')
                if checkpoint is None and status == 'unknown' and job['payload']['mutates'] is True:
                    # Also protect legacy/unbound uncertainty immediately, not
                    # merely after the next restart of the journal owner.
                    self._record_unbound_mutation(operation_id, job['payload'])
                if checkpoint is not None:
                    verification = checkpoint['verification'] or {}
                    outcome = verification.get('outcome')
                    phase = 'unresolved'
                    if status == 'succeeded' and outcome == 'committed':
                        phase = 'committed'
                    elif status == 'failed' and outcome in ('rolled_back', 'not_started'):
                        phase = outcome
                    elif status != 'unknown':
                        status, encoded_result = 'unknown', None
                        encoded_error = _json({'code': 'mutation_confirmation_missing',
                            'message': 'No matching native verification; the document remains blocked.',
                            'requires_reconciliation': True})
                    self._db.execute('UPDATE mutations SET phase=?,updated_at=? WHERE operation_id=?',
                                     (phase, time.time(), operation_id))
                self._db.execute('UPDATE jobs SET status=?,updated_at=?,result=?,error=? WHERE operation_id=?',
                                 (status, time.time(), encoded_result, encoded_error, operation_id))
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK')
                raise
            return self.get(operation_id)

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
            self._owner.close()


class JobRunner:
    """Dispatches whitelisted domain callables to an existing single STA worker.

    Callables are server-owned and never accepted from an MCP client. A mutating
    operation requires an explicit postcondition verifier. This is not rollback:
    an uncertain outcome remains unknown until the document layer reconciles it.
    """

    def __init__(self, store: JobStore, worker):
        self.store = store
        self.worker = worker
        self._lock = threading.RLock()
        self._stopped = False
        self._pending = {}

    def submit(self, request_id: str, operation: str, arguments: dict, function: Callable,
               *, context: dict | None = None, mutates: bool = False,
               verify: Callable | None = None, pass_operation_id: bool = False):
        if not callable(function) or (verify is not None and not callable(verify)):
            raise JobError('invalid_operation', 'Operation and verifier must be server-owned callables.')
        if mutates and verify is None:
            raise JobError('verification_required', 'Mutating jobs require a postcondition verifier.')
        with self._lock:
            if self._stopped:
                raise JobError('runtime_stopped', 'This runtime no longer accepts new jobs.')
            job, created = self.store.create(request_id, operation, arguments, context, mutates=mutates)
            if created:
                job_id = job['operation_id']
                try:
                    future = self.worker.submit(lambda: self._execute(job_id, function, mutates, verify, pass_operation_id))
                    self._pending[job_id] = future
                    future.add_done_callback(lambda done: self._forget(job_id, done))
                except Exception as exc:
                    # Dispatch failed before execution; retain a terminal record.
                    if self.store.start(job_id):
                        self.store.finish(job_id, 'failed', error={'code': 'dispatch_failed', 'message': str(exc)})
            return self.store.get(job['operation_id'])

    def _forget(self, job_id, future):
        if future.cancelled() or future.exception() is not None:
            # A worker failure before _execute started is a verified non-write.
            # Do not overwrite a running/terminal operation (including storage
            # failures after native execution); its uncertainty must be retained.
            if self.store.start(job_id):
                self.store.finish(job_id, 'failed', error={'code': 'dispatch_failed',
                    'message': 'Worker stopped before queued execution.'})
        with self._lock:
            self._pending.pop(job_id, None)

    def _execute(self, job_id, function, mutates, verify, pass_operation_id=False):
        if not self.store.start(job_id):
            return  # Cancellation won the atomic queued -> running race.
        try:
            result = function(job_id) if pass_operation_id else function()
            if isinstance(result, dict) and result.get('ok') is False:
                raise ExecutionFailure('operation_failed', str(result.get('error', 'Operation failed.')),
                                       uncertain=mutates)
            if verify is not None and verify(result) is not True:
                raise ExecutionFailure('postcondition_failed', 'Operation postconditions were not confirmed.')
            self.store.finish(job_id, 'succeeded', result=result)
        except BaseException as exc:
            uncertain = exc.uncertain if isinstance(exc, ExecutionFailure) else mutates
            self.store.finish(job_id, 'unknown' if uncertain else 'failed', error={
                'code': getattr(exc, 'code', 'operation_exception'), 'message': str(exc),
                'requires_reconciliation': bool(uncertain)})

    async def wait(self, operation_id: str, timeout_s: float = 0):
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (float, int)) or not 0 <= timeout_s <= 120:
            raise JobError('invalid_timeout', 'timeout_s must be finite and between 0 and 120.')
        deadline = time.monotonic() + timeout_s
        while True:
            job = self.store.get(operation_id)
            if job['status'] in TERMINAL or time.monotonic() >= deadline:
                return job
            # Polls SQLite, never the COM queue. Cancellation of this await does
            # not cancel the operation or change its durable status.
            await asyncio.sleep(min(0.05, max(0, deadline - time.monotonic())))

    def shutdown(self, timeout_s: float = 5) -> bool:
        with self._lock:
            self._stopped = True
        stopped = self.worker.shutdown(timeout_s=timeout_s)
        if stopped:
            self.store.close()
        # If COM is still running, keep the journal and OS lock alive for late
        # completion. A subsequent runtime cannot steal or reset its jobs.
        return stopped
