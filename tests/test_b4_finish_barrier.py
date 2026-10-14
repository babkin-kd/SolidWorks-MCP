"""Real JobStore + Python threads only; not native quiescence acceptance."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from threading import Event, Thread

import pytest

from solidworks_mcp.jobs import JobRunner, JobStore


spec = importlib.util.spec_from_file_location('_b4_finish_barrier_tests',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verifier_b4_finish_barrier.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

CONTEXT = dict(document_id='own_part', configuration='Основная', expected_revision='rev_before')
PAYLOAD = dict(arguments={'dimension_id': 'own_dimension', 'value_mm': 12}, context=CONTEXT, mutates=True)
RESULT = {'verified': True, 'value_mm': 12, 'details': {'owner': 'own_dimension'}}


@pytest.fixture
def prepared(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    for name, status in (('history-success', 'succeeded'), ('history-failure', 'failed')):
        job, _ = store.create(name, 'inspect', {'name': name})
        store.start(job['operation_id'])
        store.finish(job['operation_id'], status, result={'rows': [name]},
                     error={'code': 'rejected'} if status == 'failed' else None)
    job, _ = store.create('target', 'dimension.set_value', PAYLOAD['arguments'], CONTEXT, mutates=True)
    store.start(job['operation_id'])
    store.prepare_mutation(job['operation_id'], connection_epoch='epoch_before', **CONTEXT,
                           before_state={'length_mm': 10, 'neighbor_dirty': True}, effect_scope='application')
    store.record_mutation_step(job['operation_id'], name='own_set', phase='pending', evidence={'value_mm': 12})
    store.record_mutation_step(job['operation_id'], name='own_set', phase='returned', evidence={'ack': True})
    store.verify_mutation(job['operation_id'], outcome='committed', evidence={'length_mm': 12})
    try:
        yield store, job['operation_id'], tmp_path
    finally:
        store.close()


def wrapper(store, persist, **overrides):
    return helper.FinishBarrierStore(store, **{**dict(request_id='target', operation='dimension.set_value',
                                                   payload=PAYLOAD, persist=persist), **overrides})


def launch(function):
    outputs, errors = [], []

    def run():
        try:
            outputs.append(function())
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=run, daemon=True)
    thread.start()
    return thread, outputs, errors


def drain(barrier, thread):
    # Every test releases and joins only its own Python worker, even if an
    # assertion fails. Observation deadlines never release the real barrier.
    if barrier.state == 'waiting':
        barrier.release()
    thread.join(5)
    assert not thread.is_alive(), 'Owned pure worker failed to drain.'


def test_persisted_running_prepared_holds_until_explicit_release(prepared):
    store, oid, path = prepared
    before = helper._read_journal(store.path)
    receipts, finish_calls = [], []
    original = store.finish

    def counted(*args, **kwargs):
        finish_calls.append((args, kwargs))
        return original(*args, **kwargs)

    store.finish = counted  # Instance-only spy; class and executable files untouched.

    def persist(receipt):
        (path / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
        receipts.append(deepcopy(receipt))

    barrier = wrapper(store, persist)
    thread, outputs, errors = launch(lambda: barrier.finish(oid, 'succeeded', result=RESULT))
    try:
        assert barrier.wait_reached(5)
        assert thread.is_alive() and barrier.state == 'waiting'
        assert not outputs and not errors and not finish_calls
        assert helper._read_journal(store.path) == before
        assert store.get(oid)['status'] == 'running'
        assert store.get(oid)['mutation']['phase'] == 'prepared'
        assert store.mutation_blockers('epoch_before', 'other_part')
        assert store.mutation_blockers('epoch_new', 'own_part')
        assert len(receipts) == 1
        receipt = receipts[0]
        assert receipt['journal'] == before
        assert receipt['return_result'] == RESULT
        assert json.loads((path / 'receipt.json').read_text(encoding='utf-8')) == receipt
        assert receipt['python_finish_intercepted'] is True
        for key in ('terminal_finish_called', 'native_b4_accepted', 'process_stop_authorized',
                    'native_quiescence_proven', 'cad_cleanup_authorized'):
            assert receipt[key] is False
        # Returned observations are detached; callers cannot alter release.
        observed = barrier.receipt
        observed['return_result']['verified'] = False
        assert barrier.receipt == receipt
        assert barrier.get(oid) == store.get(oid)
        barrier.release()
    finally:
        drain(barrier, thread)
    assert not errors
    assert len(finish_calls) == len(outputs) == 1
    assert barrier.state == 'finished'
    assert outputs[0]['status'] == 'succeeded'
    assert outputs[0]['mutation']['phase'] == 'committed'
    assert outputs[0]['result'] == RESULT
    assert store.mutation_blockers('epoch_before', 'other_part') == []
    after = helper._read_journal(store.path)
    assert [row for row in after if row['operation_id'] != oid] == [row for row in before if row['operation_id'] != oid]
    assert outputs[0]['mutation']['verification'] == store.get(oid)['mutation']['verification']
    with pytest.raises(helper.FinishBarrierError, match='activated twice'):
        barrier.finish(oid, 'succeeded', result=RESULT)
    with pytest.raises(helper.FinishBarrierError, match='Release requires'):
        barrier.release()
    assert len(finish_calls) == 1


def test_non_target_jobs_and_non_success_finish_delegate(prepared):
    store, oid, _ = prepared
    receipts = []
    barrier = wrapper(store, receipts.append)
    other, _ = barrier.create('other', 'inspect', {})
    barrier.start(other['operation_id'])
    assert barrier.finish(other['operation_id'], 'succeeded', result={'rows': []})['status'] == 'succeeded'
    assert receipts == [] and barrier.state == 'armed'
    # A failure follows ordinary JobStore semantics: no success promotion and
    # committed verification cannot make a failed requested finish successful.
    assert barrier.finish(oid, 'unknown', error={'code': 'observation_lost'})['status'] == 'unknown'
    assert receipts == []
    assert store.get(oid)['mutation']['phase'] == 'unresolved'


@pytest.mark.parametrize('change', ['operation', 'arguments', 'document', 'configuration', 'revision'])
def test_matching_request_cannot_adopt_changed_scope(prepared, change):
    store, oid, _ = prepared
    payload = deepcopy(PAYLOAD)
    operation = 'dimension.set_value'
    if change == 'operation':
        operation = 'feature.delete'
    elif change == 'arguments':
        payload['arguments']['value_mm'] = 14
    else:
        key = {'document': 'document_id', 'configuration': 'configuration', 'revision': 'expected_revision'}[change]
        payload['context'][key] = 'foreign'
    receipts = []
    barrier = wrapper(store, receipts.append, payload=payload, operation=operation)
    before = helper._read_journal(store.path)
    with pytest.raises(helper.FinishBarrierError, match='substitute'):
        barrier.finish(oid, 'succeeded', result=RESULT)
    assert receipts == [] and helper._read_journal(store.path) == before


@pytest.mark.parametrize('result,error', [({}, None), ({'verified': False}, None),
    ({'verified': 1}, None), (None, None), (RESULT, {'code': 'late_error'})])
def test_result_must_be_strictly_verified_and_error_free(prepared, result, error):
    store, oid, _ = prepared
    receipts = []
    barrier = wrapper(store, receipts.append)
    before = helper._read_journal(store.path)
    with pytest.raises(helper.FinishBarrierError, match='verified Python'):
        barrier.finish(oid, 'succeeded', result=result, error=error)
    assert barrier.state == 'failed' and not barrier.wait_reached(.01)
    assert receipts == [] and helper._read_journal(store.path) == before
    with pytest.raises(helper.FinishBarrierError, match='activated twice'):
        barrier.finish(oid, 'succeeded', result=RESULT)


@pytest.mark.parametrize('outcome', ['rolled_back', 'not_started', None])
def test_only_committed_verification_can_reach_barrier(prepared, outcome):
    store, oid, _ = prepared
    if outcome is None:
        with store._lock:
            store._db.execute('UPDATE mutations SET verification=NULL WHERE operation_id=?', (oid,))
    else:
        store.verify_mutation(oid, outcome=outcome, evidence={'known_effect': False})
    receipts = []
    barrier = wrapper(store, receipts.append)
    before = helper._read_journal(store.path)
    with pytest.raises(helper.FinishBarrierError, match='committed postcondition'):
        barrier.finish(oid, 'succeeded', result=RESULT)
    assert barrier.state == 'failed' and receipts == []
    assert helper._read_journal(store.path) == before


def test_persist_failure_is_latched_without_success_or_retry(prepared):
    store, oid, _ = prepared
    before = helper._read_journal(store.path)
    calls = []

    def fail(receipt):
        calls.append(receipt)
        raise OSError('controlled receipt storage failure')

    barrier = wrapper(store, fail)
    with pytest.raises(OSError, match='controlled receipt'):
        barrier.finish(oid, 'succeeded', result=RESULT)
    assert len(calls) == 1 and barrier.state == 'failed'
    assert barrier.receipt is None and not barrier.wait_reached(.01)
    assert helper._read_journal(store.path) == before
    assert store.mutation_blockers('epoch_new', 'other_part')
    for status in ('succeeded', 'unknown'):
        with pytest.raises(helper.FinishBarrierError, match='activated twice'):
            barrier.finish(oid, status, result=RESULT)
    with pytest.raises(helper.FinishBarrierError, match='Release requires'):
        barrier.release()
    assert len(calls) == 1 and helper._read_journal(store.path) == before


def test_repeat_while_waiting_cannot_dispatch_or_persist_again(prepared):
    store, oid, _ = prepared
    receipts = []
    barrier = wrapper(store, receipts.append)
    with pytest.raises(helper.FinishBarrierError, match='Release requires'):
        barrier.release()
    thread, outputs, errors = launch(lambda: barrier.finish(oid, 'succeeded', result=RESULT))
    try:
        assert barrier.wait_reached(5)
        assert barrier.wait_reached(.001)
        with pytest.raises(helper.FinishBarrierError, match='activated twice'):
            barrier.finish(oid, 'succeeded', result=RESULT)
        assert len(receipts) == 1 and store.get(oid)['status'] == 'running'
    finally:
        drain(barrier, thread)
    assert not errors and len(outputs) == 1


def test_persist_mutation_of_receipt_and_caller_payload_cannot_change_finish(prepared):
    store, oid, _ = prepared
    payload, result = deepcopy(PAYLOAD), deepcopy(RESULT)

    def mutate(receipt):
        receipt['return_result']['verified'] = False
        receipt['journal'].clear()

    barrier = wrapper(store, mutate, payload=payload)
    payload['arguments']['value_mm'] = 90
    thread, outputs, errors = launch(lambda: barrier.finish(oid, 'succeeded', result=result))
    try:
        assert barrier.wait_reached(5)
        result['details']['owner'] = 'foreign'
        assert barrier.receipt['return_result'] == RESULT
        assert barrier.receipt['journal']
    finally:
        drain(barrier, thread)
    assert not errors and outputs[0]['result'] == RESULT


def test_checkpoint_changed_after_release_cannot_be_finished(prepared):
    store, oid, _ = prepared
    barrier = wrapper(store, lambda receipt: None)
    thread, outputs, errors = launch(lambda: barrier.finish(oid, 'succeeded', result=RESULT))
    try:
        assert barrier.wait_reached(5)
        store.verify_mutation(oid, outcome='committed', evidence={'unexpected_change': True})
    finally:
        drain(barrier, thread)
    assert outputs == [] and len(errors) == 1
    assert isinstance(errors[0], helper.FinishBarrierError)
    assert barrier.state == 'failed' and store.get(oid)['status'] == 'running'


def test_persist_must_return_before_reached_and_release(prepared):
    store, oid, _ = prepared
    persist_started, allow_persist_return = Event(), Event()

    def persist(receipt):
        persist_started.set()
        assert allow_persist_return.wait(5), 'Owned test persist was not released.'

    barrier = wrapper(store, persist)
    thread, outputs, errors = launch(lambda: barrier.finish(oid, 'succeeded', result=RESULT))
    try:
        assert persist_started.wait(5)
        assert barrier.state == 'capturing' and not barrier.wait_reached(.01)
        assert store.get(oid)['status'] == 'running'
        assert store.get(oid)['mutation']['phase'] == 'prepared'
        with pytest.raises(helper.FinishBarrierError, match='Release requires'):
            barrier.release()
        allow_persist_return.set()
        assert barrier.wait_reached(5)
    finally:
        allow_persist_return.set()
        barrier.wait_reached(5)
        drain(barrier, thread)
    assert not errors and len(outputs) == 1


def test_original_finish_failure_is_not_retried(prepared):
    store, oid, _ = prepared
    calls, receipts = [], []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        raise OSError('controlled final journal failure')

    store.finish = fail
    barrier = wrapper(store, receipts.append)
    before = helper._read_journal(store.path)
    thread, outputs, errors = launch(lambda: barrier.finish(oid, 'succeeded', result=RESULT))
    try:
        assert barrier.wait_reached(5)
    finally:
        drain(barrier, thread)
    assert not outputs and len(errors) == 1 and isinstance(errors[0], OSError)
    assert len(calls) == len(receipts) == 1 and barrier.state == 'failed'
    assert helper._read_journal(store.path) == before
    assert store.mutation_blockers('epoch_new', 'other_part')
    with pytest.raises(helper.FinishBarrierError, match='activated twice'):
        barrier.finish(oid, 'unknown', error={'code': 'fallback'})
    assert len(calls) == 1


def test_async_persist_is_rejected_without_executing_it(prepared):
    store, oid, _ = prepared
    calls = []

    async def async_persist(receipt):
        calls.append(receipt)

    with pytest.raises(helper.FinishBarrierError, match='synchronous persist'):
        wrapper(store, async_persist)
    barrier = wrapper(store, lambda receipt: async_persist(receipt))
    before = helper._read_journal(store.path)
    with pytest.raises(helper.FinishBarrierError, match='complete synchronously'):
        barrier.finish(oid, 'succeeded', result=RESULT)
    assert calls == [] and barrier.state == 'failed' and barrier.receipt is None
    assert helper._read_journal(store.path) == before


@pytest.mark.parametrize('corruption', ['schema', 'orphan'])
def test_shared_reader_rejects_unknown_schema_and_orphan_checkpoint(prepared, corruption):
    store, oid, _ = prepared
    with store._lock:
        if corruption == 'schema':
            store._db.execute('PRAGMA user_version=999')
        else:
            store._db.execute('INSERT INTO mutations SELECT ?,connection_epoch,document_id,configuration,'
                              'expected_revision,before_state,phase,verification,reconciliation,updated_at '
                              'FROM mutations WHERE operation_id=?', ('orphan_job', oid))
    receipts = []
    barrier = wrapper(store, receipts.append)
    with pytest.raises(ValueError, match='schema 3|orphan mutation'):
        barrier.finish(oid, 'succeeded', result=RESULT)
    assert receipts == [] and barrier.state == 'failed' and barrier.receipt is None
    assert not barrier.wait_reached(.01)
    assert store.get(oid)['status'] == 'running'
    assert store.get(oid)['mutation']['phase'] == 'prepared'
    with pytest.raises(helper.FinishBarrierError, match='activated twice'):
        barrier.finish(oid, 'succeeded', result=RESULT)


@pytest.mark.parametrize('change', ['history', 'new_job'])
def test_release_rejects_any_complete_journal_change(prepared, change):
    store, oid, _ = prepared
    barrier = wrapper(store, lambda receipt: None)
    thread, outputs, errors = launch(lambda: barrier.finish(oid, 'succeeded', result=RESULT))
    try:
        assert barrier.wait_reached(5)
        original_target = store.get(oid)
        if change == 'history':
            with store._lock:
                store._db.execute('UPDATE jobs SET result=? WHERE request_id=?',
                                  (json.dumps({'rows': ['changed-history']}), 'history-success'))
        else:
            store.create('unexpected-new-job', 'inspect', {})
        assert store.get(oid) == original_target  # Target-only comparison would pass.
    finally:
        drain(barrier, thread)
    assert outputs == [] and len(errors) == 1
    assert isinstance(errors[0], helper.FinishBarrierError)
    assert 'complete journal changed' in str(errors[0])
    assert barrier.state == 'failed'
    assert store.get(oid)['status'] == 'running'
    assert store.get(oid)['mutation']['phase'] == 'prepared'
    assert store.mutation_blockers('epoch_new', 'other_part')


def test_real_runner_callback_return_precedes_barrier_and_terminal_commit(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    callback_returned = Event()
    receipts = []
    barrier = wrapper(store, receipts.append)
    runner = JobRunner(barrier, worker=None)
    job, _ = store.create('target', 'dimension.set_value', PAYLOAD['arguments'], CONTEXT, mutates=True)
    oid = job['operation_id']

    def function(operation_id):
        store.prepare_mutation(operation_id, connection_epoch='epoch_before', **CONTEXT,
                               before_state={'value_mm': 10}, effect_scope='application')
        store.verify_mutation(operation_id, outcome='committed', evidence={'value_mm': 12})
        callback_returned.set()
        return deepcopy(RESULT)

    thread, outputs, errors = launch(lambda: runner._execute(oid, function, True,
                                                           lambda result: result['verified'], True))
    try:
        assert barrier.wait_reached(5) and callback_returned.is_set()
        assert receipts[0]['return_result'] == RESULT
        assert store.get(oid)['status'] == 'running'
        assert store.mutation_blockers('epoch_new', 'other_part')
    finally:
        drain(barrier, thread)
        store.close()
    assert not errors and outputs == [None]
    assert barrier.state == 'finished'


def test_runner_persist_failure_keeps_unfinished_checkpoint_for_restart(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite')
    receipts = []

    def fail(receipt):
        receipts.append(receipt)
        raise OSError('persist failure')

    barrier = wrapper(store, fail)
    runner = JobRunner(barrier, worker=None)
    job, _ = store.create('target', 'dimension.set_value', PAYLOAD['arguments'], CONTEXT, mutates=True)
    oid = job['operation_id']

    def function(operation_id):
        store.prepare_mutation(operation_id, connection_epoch='epoch_before', **CONTEXT,
                               before_state={'value_mm': 10}, effect_scope='application')
        store.verify_mutation(operation_id, outcome='committed', evidence={'value_mm': 12})
        return RESULT

    thread, outputs, errors = launch(lambda: runner._execute(oid, function, True,
                                                           lambda result: result['verified'], True))
    try:
        thread.join(5)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], helper.FinishBarrierError)
        assert outputs == [] and len(receipts) == 1
        assert store.get(oid)['status'] == 'running'
        assert store.get(oid)['mutation']['phase'] == 'prepared'
        assert store.mutation_blockers('epoch_new', 'other_part')
    finally:
        drain(barrier, thread)
        store.close()
    # Actual JobStore startup recovery, still no process/native claim.
    reopened = JobStore(tmp_path / 'jobs.sqlite')
    try:
        assert reopened.get(oid)['status'] == 'unknown'
        assert reopened.get(oid)['mutation']['phase'] == 'unresolved'
        assert reopened.mutation_blockers('epoch_new', 'other_part')
    finally:
        reopened.close()
