"""Future verifier owner/drain policy; no CAD, process or JobStore dependencies.

SDK contexts must be created outside every body deadline. Wrap their live client
with inside_live_session(), or use open_supervised_session() to shield SDK startup
as well. Use this wrapper for ALL durable tools; a direct raw-client dispatch
cannot be supervised. Only run_body() has an optional body deadline. On missing
acknowledgement/quiescence proof exit deliberately waits, without a hard timeout.

The fresh owned journal is inspected read-only. No job is cancelled, replayed,
reconciled or rewritten here. CleanupGate only authorizes caller-owned cleanup;
this module never closes CAD fixtures, activates a model or restores preferences.
"""

from __future__ import annotations

from collections import deque
from contextlib import asynccontextmanager, closing
from dataclasses import dataclass, field
import inspect
import importlib.util
import json
import math
from pathlib import Path
import sqlite3

import anyio


# Verifiers run both as standalone scripts and through path-based pure test
# loaders. Resolve this passive sibling module independently of cwd/PYTHONPATH.
_open_spec = importlib.util.spec_from_file_location('_native_open_evidence',
    Path(__file__).with_name('verifier_native_open.py'))
_open_evidence = importlib.util.module_from_spec(_open_spec)
_open_spec.loader.exec_module(_open_evidence)
released_open_guard = _open_evidence.released_open_guard
untouched_busy_open_guard = _open_evidence.untouched_busy_open_guard
verified_open_native_steps = _open_evidence.verified_open_native_steps


TERMINAL = frozenset({'succeeded', 'failed', 'cancelled', 'unknown'})
CONTEXT_KEYS = ('document_id', 'configuration', 'expected_observation_revision',
                'expected_revision', 'body_id', 'object_id', 'dimension_id')


def released_execution_guard(guard, *, expected_model_count=1):
    if isinstance(guard, dict) and guard.get('scope') in ('application_document_create_guard_v1','application_model_mutation_guard_v1'):
        keys = {'scope', 'original_command_in_progress', 'acquired', 'released', 'model_guards', 'selection_preserved'}
        return (set(guard) == keys and guard['original_command_in_progress'] is False
                and guard['acquired'] is True and guard['released'] is True and guard['selection_preserved'] is True
                and type(guard['model_guards']) is list
                and (len(guard['model_guards']) <= 1000 if guard['scope']=='application_document_create_guard_v1'
                     else type(expected_model_count) is int and 1 <= expected_model_count <= 5000
                          and len(guard['model_guards'])==expected_model_count)
                and all(isinstance(item, dict) and 'scope' not in item and released_execution_guard(item)
                        for item in guard['model_guards']))
    return isinstance(guard, dict) and set(guard)=={'original_state','locked_state','released_state'} and all(type(guard.get(key)) is int and guard[key] == value
        for key, value in (('original_state', 0), ('locked_state', 2), ('released_state', 0)))


def released_close_guard(guard, before):
    """Exact clean-close scope permits zero survivor locks, never target locks."""
    if not isinstance(guard,dict) or not isinstance(before,dict):return False
    keys={'scope','original_command_in_progress','acquired','released','model_guards','selection_preserved',
          'retiring_document_ids','retiring_targets_locked_during_close','activation_ui_release'}
    if (set(guard)!=keys or guard['scope']!='application_document_close_guard_v1'
            or before.get('scope')!='native_document_close_clean_v1'):return False
    documents=(before.get('semantic') or {}).get('documents')
    impact=before.get('impact') or {}
    ids=[row.get('document_id') for row in documents if isinstance(row,dict)] if isinstance(documents,list) else []
    retiring=impact.get('retiring_document_ids');survivors=impact.get('survivor_document_ids')
    def valid(values,nonempty=False):
        return (isinstance(values,list) and (bool(values) or not nonempty)
                and all(isinstance(value,str) and value for value in values) and len(set(values))==len(values))
    if (not isinstance(documents,list) or len(ids)!=len(documents) or not valid(ids,True) or len(ids)>5000
            or not valid(retiring,True) or not valid(survivors) or set(retiring)&set(survivors)
            or set(ids)!=set(retiring)|set(survivors) or guard['retiring_document_ids']!=retiring
            or impact.get('target_document_id') not in retiring or impact.get('policy')!='require_clean'
            or impact.get('data_unload_claimed') is not False):return False
    release=guard['activation_ui_release']
    release_valid=(isinstance(release,dict) and set(release)=={'attempted','verified'}
        and ((release['attempted'] is False and release['verified'] is False)
             or (release['attempted'] is True and release['verified'] is True and bool(survivors)
                 and impact.get('active_after_document_id') in survivors)))
    return (release_valid and guard['original_command_in_progress'] is False and guard['acquired'] is True
            and guard['released'] is True and guard['selection_preserved'] is True
            and guard['retiring_targets_locked_during_close'] is False
            and type(guard['model_guards']) is list and len(guard['model_guards'])==len(survivors)
            and all(released_execution_guard(item) for item in guard['model_guards']))
DIRECT_QUERIES = frozenset({'system_get_info', 'job_get', 'job_list'})
_HISTORY_SEAL = object()


def untouched_busy_guard(guard):
    expected={'scope':'application_model_mutation_guard_v1','original_command_in_progress':True,
              'acquired':False,'released':False,'model_guards':[],'selection_preserved':False}
    return (isinstance(guard,dict) and set(guard)==set(expected)
            and guard['scope']==expected['scope']
            and all(guard[key] is expected[key] for key in ('original_command_in_progress','acquired','released','selection_preserved'))
            and type(guard['model_guards']) is list and not guard['model_guards'])


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':'))


@dataclass(frozen=True)
class ToolSpec:
    operation: str
    mutates: bool
    argument_map: dict = field(default_factory=dict)
    argument_defaults: dict = field(default_factory=dict)
    float_arguments: frozenset = frozenset()
    constant_args: dict = field(default_factory=dict)
    prewrite_failure_codes: frozenset = frozenset()
    preenqueue_error_codes: frozenset = frozenset()

    def payload(self, arguments):
        inputs = {**self.argument_defaults, **arguments}
        domain = {}
        for key, value in inputs.items():
            if key in ('request_id', 'timeout_s'):
                continue
            target = self.argument_map.get(key, key)
            if target in domain:
                raise ValueError('Input aliases collide before dispatch.')
            domain[target] = value
        if set(domain) & set(self.constant_args):
            raise ValueError('Caller arguments collide with server-owned constants.')
        domain.update(self.constant_args)
        for key in self.float_arguments:
            value = domain.get(key)
            if type(value) in (int, float):
                domain[key] = float(value)  # Explicit schema contract, never bool/string coercion.
        return {'arguments': domain, 'context': {key: domain[key] for key in CONTEXT_KEYS if key in domain},
                'mutates': self.mutates}


@dataclass
class TrackedRequest:
    tool: str
    request_id: str
    arguments: dict
    spec: ToolSpec
    payload: dict
    operation_id: str | None = None
    not_dispatched: bool = False
    send_attempts: int = 0
    rejected_attempts: int = 0
    attempt_arguments: list = field(default_factory=list)


@dataclass(frozen=True)
class CleanupDecision:
    child_can_close: bool
    fixture_can_cleanup: bool
    reasons: tuple[str, ...]


class CleanupGate:
    def __init__(self):
        self.decision = CleanupDecision(False, False, ('no quiescence proof',))

    def can_cleanup(self):
        return self.decision.fixture_can_cleanup


@dataclass(frozen=True, init=False)
class VerifiedHistory:
    """In-memory proof issued only after a previous owner safely drained."""
    _snapshot: str

    def __init__(self, snapshot, seal):
        if seal is not _HISTORY_SEAL:
            raise ValueError('History must come from a verified supervisor, not supplied JSON.')
        object.__setattr__(self, '_snapshot', snapshot)


def read_journal(path):
    """One coherent jobs+mutations snapshot; mode=ro still sees WAL contents."""
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        if db.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise ValueError('Expected journal schema 3.')
        rows = db.execute('SELECT * FROM jobs ORDER BY created_at, operation_id LIMIT 100001').fetchall()
        if len(rows) > 100000:
            raise ValueError('Complete journal observation budget exceeded.')
        mutations = {row['operation_id']: dict(row) for row in db.execute('SELECT * FROM mutations')}
        jobs = []
        for row in rows:
            job = dict(row)
            for key in ('payload', 'result', 'error'):
                job[key] = json.loads(job[key]) if job[key] is not None else None
            mutation = mutations.pop(job['operation_id'], None)
            if mutation:
                for key in ('before_state', 'verification', 'reconciliation'):
                    mutation[key] = json.loads(mutation[key]) if mutation[key] is not None else None
            job['mutation'] = mutation
            jobs.append(job)
        if mutations:
            raise ValueError('Journal contains orphan mutation checkpoints.')
        return jobs


class VerifierSupervisor:
    def __init__(self, client, *, tool_specs, journal_path=None, journal_reader=None,
                 poll_interval=.25, on_hold=None, preenqueue_rejection=None,
                 trusted_history=None, readonly_restart=False):
        if (journal_path is None) == (journal_reader is None):
            raise ValueError('Provide one exact fresh journal path or coherent test reader.')
        if isinstance(poll_interval, bool) or not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError('Observation interval must be finite and positive.')
        self._client = client
        self.tool_specs = dict(tool_specs)
        self._reader = journal_reader if journal_reader is not None else lambda: read_journal(journal_path)
        self.poll_interval, self.on_hold = poll_interval, on_hold
        self.preenqueue_rejection = preenqueue_rejection
        if trusted_history is not None and (not isinstance(trusted_history, VerifiedHistory) or not readonly_restart):
            raise ValueError('Verified history requires an explicitly read-only restart.')
        if readonly_restart and trusted_history is None:
            raise ValueError('A read-only restart requires previous verified history.')
        self._history = trusted_history
        self._history_records = {} if trusted_history is None else {
            row['operation_id']: _json(row) for row in json.loads(trusted_history._snapshot)}
        self._readonly_restart = readonly_restart
        self._approved_snapshot = None
        self.requests = {}
        self.cleanup_gate = CleanupGate()
        self.progress = deque(maxlen=32)
        self._fresh = False
        self._entered = False
        self._stopping = False
        self._tainted = set()

    def __getattr__(self, name):
        # initialize/list_tools/read_resource retain their normal SDK interfaces.
        # Durable CAD work MUST pass through this class's call_tool method.
        return getattr(self._client, name)

    @staticmethod
    def _envelope(raw):
        value = raw if isinstance(raw, dict) else raw.structuredContent
        if not isinstance(value, dict):
            raise ValueError('Missing structured response envelope.')
        return value

    async def call_tool(self, name, arguments=None, **kwargs):
        if name in DIRECT_QUERIES:
            try:
                return await self._client.call_tool(name, arguments or {}, **kwargs)
            except BaseException as exc:
                if not isinstance(exc, anyio.get_cancelled_exc_class()):
                    self._tainted.add('transport lost')
                raise
        if not self._entered or self._stopping:
            raise RuntimeError('Durable dispatch is allowed only inside the live supervisor body.')
        spec = self.tool_specs[name]
        if self._readonly_restart and spec.mutates:
            raise RuntimeError('A historical restart cannot dispatch mutations.')
        if spec.mutates and self._tainted:
            raise RuntimeError('Unconfirmed effects prohibit further mutating dispatch.')
        exact = json.loads(_json(arguments))
        request_id = exact.get('request_id')
        if not isinstance(request_id, str) or not request_id:
            raise ValueError('An explicit request_id must be tracked before dispatch.')
        payload = spec.payload(exact)
        request = self.requests.get(request_id)
        if request is not None and (request.tool != name or _json(request.payload) != _json(payload)):
            raise ValueError('Tracked request_id cannot authorize different work.')
        if request is None:
            request = TrackedRequest(name, request_id, exact, spec, payload)
            self.requests[request_id] = request
        request.send_attempts += 1
        # Every new send creates an uncertainty obligation BEFORE awaiting RPC.
        # Earlier rejected attempts cannot certify this later one as unsent.
        request.not_dispatched = False
        request.attempt_arguments.append(json.loads(_json(exact)))
        # A previous coherent snapshot cannot authorize cleanup of a new RPC.
        # Revoke before handing it to the transport, without tainting normal work.
        self._approved_snapshot = None
        self.cleanup_gate.decision = CleanupDecision(False, False, ('durable dispatch awaiting fresh proof',))
        try:
            raw = await self._client.call_tool(name, json.loads(_json(exact)), **kwargs)
            if self.preenqueue_rejection is not None and self.preenqueue_rejection(name, exact, raw) is True:
                request.rejected_attempts += 1
                request.not_dispatched = (request.operation_id is None
                                          and request.rejected_attempts == request.send_attempts)
                return raw
            value = self._envelope(raw)
            operation_id = value.get('operation_id')
            if operation_id is None and value.get('status') == 'failed':
                error = value.get('error') or {}
                if error.get('code') in spec.preenqueue_error_codes:
                    request.rejected_attempts += 1
                    request.not_dispatched = (request.operation_id is None
                                              and request.rejected_attempts == request.send_attempts)
                    return raw
            if not isinstance(operation_id, str) or not operation_id:
                raise ValueError('Durable call lacks a verified operation acknowledgement.')
            if request.operation_id is not None and operation_id != request.operation_id:
                raise ValueError('Repeated request acknowledged another operation.')
            request.operation_id = operation_id
            request.not_dispatched = False
            return raw  # Preserve the SDK CallToolResult, not an invented success.
        except BaseException as exc:
            if not isinstance(exc, anyio.get_cancelled_exc_class()):
                self._tainted.add('transport or acknowledgement unconfirmed')
            raise

    async def _rows(self):
        rows = self._reader()
        if inspect.isawaitable(rows):
            rows = await rows
        if not isinstance(rows, list):
            raise ValueError('Complete coherent journal snapshot required.')
        _json(rows)  # Even quarantined outcomes require structurally finite JSON.
        return rows

    async def _recover_all_pages(self):
        """Read-only recovery aid; pagination alone never substitutes SQL coherence."""
        rows, arguments, cursors = [], {'limit': 1000}, set()
        for _ in range(10000):
            raw = await self._client.call_tool('job_list', arguments)
            value = self._envelope(raw)
            if value.get('status') != 'succeeded':
                raise ValueError('job_list did not return a complete durable page.')
            page = value['data']
            rows.extend(page['items'])
            cursor = page['next_cursor']
            if cursor is None:
                return rows
            key = _json(cursor)
            if key in cursors:
                raise ValueError('Repeated journal cursor.')
            cursors.add(key)
            arguments = {'limit': 1000, 'before_created_at': cursor['created_at'],
                         'before_operation_id': cursor['operation_id']}
        raise ValueError('Complete pagination budget exceeded.')

    @staticmethod
    def _matches(request, job):
        return (job['request_id'] == request.request_id and job['operation'] == request.spec.operation
                and _json(job['payload']) == _json(request.payload))

    def _bind(self, rows):
        for request in self.requests.values():
            matches = [job for job in rows if job.get('request_id') == request.request_id]
            if len(matches) > 1:
                raise ValueError('Request maps to multiple durable jobs.')
            if matches:
                job = matches[0]
                if request.not_dispatched or not self._matches(request, job):
                    raise ValueError('Durable request identity/payload contradicts acknowledgement.')
                operation_id = job['operation_id']
                if request.operation_id is not None and operation_id != request.operation_id:
                    raise ValueError('Durable operation differs from acknowledged operation.')
                request.operation_id = operation_id

    def _decide(self, rows):
        reasons = list(sorted(self._tainted))
        if not self._fresh:
            return CleanupDecision(False, False, tuple(reasons + ['fresh owned journal not established']))
        if not self.requests:
            return CleanupDecision(False, False, tuple(reasons + ['empty tracker is not dispatch proof']))
        operation_ids = set()
        by_request = {}
        for job in rows:
            if (not isinstance(job['operation_id'], str) or not job['operation_id']
                    or job['operation_id'] in operation_ids or job['request_id'] in by_request
                    or job['status'] not in TERMINAL | {'queued', 'running'}
                    or type(job['payload']['mutates']) is not bool):
                raise ValueError('Malformed durable job snapshot.')
            operation_ids.add(job['operation_id'])
            by_request[job['request_id']] = job
        for operation_id, expected in self._history_records.items():
            current = next((row for row in rows if row['operation_id'] == operation_id), None)
            if current is None or _json(current) != expected:
                return CleanupDecision(False, False, tuple(reasons + ['approved history changed or disappeared']))
        for request in self.requests.values():
            if not request.not_dispatched and request.request_id not in by_request:
                return CleanupDecision(False, False, tuple(reasons + ['unacknowledged/missing durable request']))
        if any(job['status'] in ('queued', 'running') for job in rows):
            return CleanupDecision(False, False, tuple(reasons + ['durable work still queued/running']))
        safe, coherent_terminal = not self._tainted, True
        for job in rows:
            mutation = job.get('mutation')
            error = job.get('error') or {}
            if 'requires_reconciliation' in error and error['requires_reconciliation'] is not False:
                reasons.append('job requires reconciliation')
                safe = False
            if job['status'] == 'unknown':
                self._tainted.add('terminal unknown retains fixtures')
                reasons.append('terminal unknown retains fixtures')
                safe = False
            if not job['payload']['mutates']:
                if mutation:
                    raise ValueError('Read job unexpectedly has a mutation checkpoint.')
                continue
            if job['operation_id'] in self._history_records:
                # Exact snapshot equality above preserves the previous owner's
                # entire safe proof, including explicit pre-checkpoint rejection.
                continue
            request = self.requests.get(job['request_id'])
            if request is None and job['operation_id'] not in self._history_records:
                reasons.append('untracked mutation retains fixtures')
                safe = False
            if mutation is None:
                prewrite = (job['status'] == 'cancelled' or (job['status'] == 'failed' and request is not None
                            and (job.get('error') or {}).get('code') in request.spec.prewrite_failure_codes))
                if not prewrite:
                    reasons.append('mutation lacks confirmed prewrite outcome')
                    safe = False
                continue
            phase = mutation['phase']
            verification = mutation.get('verification') or {}
            expected = {'succeeded': {'committed'}, 'failed': {'not_started', 'rolled_back'}}.get(job['status'], set())
            if phase not in expected or verification.get('outcome') != phase:
                reasons.append('mutation outcome/restoration unresolved')
                safe = False
                if job['status'] != 'unknown':
                    coherent_terminal = False
            if job['status'] == 'succeeded' and (job.get('result') or {}).get('verified') is not True:
                reasons.append('mutation success lacks verified postconditions')
                safe = False
                coherent_terminal = False
            before = mutation.get('before_state') or {}
            if before.get('_mutation_effect_scope') == 'application':
                guard = (verification.get('evidence') or {}).get('execution_guard') or {}
                expected_model_count = 1
                if job['operation']=='document.save_native' and before.get('scope')=='native_document_current_file_save_v1':
                    documents=(before.get('semantic') or {}).get('documents')
                    ids=[row.get('document_id') for row in documents if isinstance(row,dict)] if isinstance(documents,list) else []
                    expected_model_count=(len(ids) if isinstance(documents,list) and len(ids)==len(documents)
                        and all(isinstance(value,str) and value for value in ids) and len(set(ids))==len(ids) else 0)
                untouched_busy = (job['status']=='failed' and phase=='not_started'
                    and (job.get('error') or {}).get('code')=='application_busy'
                    and (verification.get('evidence') or {}).get('native_mutation_started') is False
                    and (untouched_busy_open_guard(guard, before) if job['operation']=='document.open_native'
                         else untouched_busy_guard(guard)))
                close_release=(job['operation']=='document.close_native' and released_close_guard(guard,before))
                released=(released_open_guard(guard, before) if job['operation']=='document.open_native'
                          else close_release if job['operation']=='document.close_native'
                          else released_execution_guard(guard, expected_model_count=expected_model_count))
                if not released and not untouched_busy:
                    reasons.append('UI release unconfirmed')
                    safe = False
                if (job['operation']=='document.open_native' and phase in ('committed','rolled_back')
                        and not verified_open_native_steps(verification, before)):
                    reasons.append('native open step acknowledgements unconfirmed')
                    safe = False
        # A coherent terminal job snapshot permits SDK teardown, while unknown
        # effects/transport loss still prohibit native fixture cleanup.
        return CleanupDecision(coherent_terminal, safe and coherent_terminal, tuple(dict.fromkeys(reasons)))

    async def observe_once(self):
        try:
            rows = await self._rows()
            self._bind(rows)
            decision = self._decide(rows)
            self._approved_snapshot = _json(rows) if decision.child_can_close and decision.fixture_can_cleanup else None
        except BaseException as exc:
            self._tainted.add('journal/protocol observation failed')
            try:
                self._bind(await self._recover_all_pages())
            except BaseException:
                pass
            decision = CleanupDecision(False, False, ('coherent journal proof unavailable', type(exc).__name__))
        self.cleanup_gate.decision = decision
        self.progress.append(decision)
        return decision

    def history_seed(self):
        """Only a completed safe drain may approve exact history for read-only restart."""
        if (not self._stopping or not self.cleanup_gate.can_cleanup()
                or self._approved_snapshot is None):
            raise RuntimeError('History cannot be issued without a completed safe cleanup decision.')
        return VerifiedHistory(self._approved_snapshot, _HISTORY_SEAL)

    def retain(self, reason):
        """Quarantine caller-observed cleanup/independent-proof failures."""
        self._tainted.add(str(reason))
        self._approved_snapshot = None
        prior = self.cleanup_gate.decision
        self.cleanup_gate.decision = CleanupDecision(
            prior.child_can_close, False, tuple(dict.fromkeys((*prior.reasons, str(reason)))))

    async def drain(self):
        self._stopping = True
        with anyio.CancelScope(shield=True):
            while True:
                decision = await self.observe_once()
                if decision.child_can_close:
                    return decision
                if self.on_hold is not None:
                    try:
                        value = self.on_hold(decision)
                        if inspect.isawaitable(value):
                            await value
                    except BaseException as exc:
                        self.progress.append(('hold observer failed', type(exc).__name__))
                try:
                    await anyio.sleep(self.poll_interval)
                except BaseException as exc:
                    self._tainted.add('owner cancellation during drain')
                    self.progress.append(('drain sleep interrupted', type(exc).__name__))

    async def run_body(self, body, *, timeout_s=None):
        if timeout_s is None:
            return await body(self)
        if isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError('Body deadline must be finite and positive.')
        with anyio.fail_after(timeout_s):
            return await body(self)

    @asynccontextmanager
    async def inside_live_session(self):
        """Initialize SDK first, outside body deadlines, so its journal exists.

        The initial journal must be empty, or exactly match a previous owner's
        history_seed() with readonly_restart=True. No arbitrary history bypass.
        """
        if self._entered:
            raise RuntimeError('Supervisor cannot be entered twice.')
        self._entered = True
        with anyio.CancelScope(shield=True):
            try:
                try:
                    initial = await self._rows()
                    self._fresh = (initial == [] if self._history is None
                                   else _json(initial) == self._history._snapshot)
                except BaseException:
                    self._fresh = False
                yield self
            finally:
                await self.drain()


@asynccontextmanager
async def open_supervised_session(session_factory, **kwargs):
    """Shield SDK creation and lifetime before starting any cancellable body."""
    with anyio.CancelScope(shield=True):
        primary = None
        supervisor = None
        try:
            async with session_factory() as client:
                supervisor = VerifierSupervisor(client, **kwargs)
                try:
                    async with supervisor.inside_live_session():
                        yield supervisor
                except BaseException as exc:
                    # Drain already finished. Exit SDK without feeding the body
                    # error into its task group, then rethrow that exact error.
                    primary = exc
        except BaseException as shutdown_error:
            if supervisor is not None:
                supervisor.retain('SDK shutdown unconfirmed')
            if primary is not None:
                raise BaseExceptionGroup('Body error and SDK shutdown error', [primary, shutdown_error])
            raise
        if primary is not None:
            raise primary
