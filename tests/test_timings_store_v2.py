"""Real private timing store and independent interval/statistics expectations."""

import json
import sqlite3

import pytest

from solidworks_mcp.timings_v2 import TimingConfig,TimingRecorder,timing_span


BUILD=dict(package_version='2.0.0.dev68',git_sha='a'*40,source_digest='b'*64)


def recorder(tmp_path,**kwargs):
    return TimingRecorder(tmp_path/'private.sqlite',build=BUILD,
        operations=('dimension.set_value','job_get'),**kwargs)


def measured(store,seconds=4.,outcome='succeeded',kind='job'):
    ticks=iter([10.,10.+seconds]);store.clock=lambda:next(ticks)
    trace=store.begin('dimension.set_value',kind=kind);trace.finish(outcome);return trace


def records(tmp_path):
    with sqlite3.connect(tmp_path/'private.sqlite') as db:
        return [json.loads(row[0]) for row in db.execute('SELECT record FROM timings')]


@pytest.mark.parametrize('encoded',['{}','{"elapsed_s":NaN}'])
def test_corrupt_private_record_produces_unavailable_report_without_leaking_record(tmp_path,encoded):
    store=recorder(tmp_path,config=TimingConfig(enabled=True))
    with store._db:
        store._db.execute('INSERT INTO timings VALUES (?,?,?)',('corrupt',store.wall_clock(),encoded))
    result=store.report()
    assert result['available'] is False and result['sample_count']==0 and result['groups']==[]
    assert result['storage_failures']==1
    store.close()


def test_disabled_instrumentation_creates_no_storage_and_does_not_touch_clock(tmp_path):
    store=recorder(tmp_path,monotonic=lambda:pytest.fail('Disabled diagnostics read clock.'))
    assert store.begin('dimension.set_value') is None
    assert store.report()['enabled'] is False
    assert not (tmp_path/'private.sqlite').exists()
    with timing_span('prepare'):pass


def test_nested_inclusive_exclusive_times_and_original_exception_are_preserved(tmp_path):
    ticks=iter([0.,1.,2.,5.,7.,9.])
    store=recorder(tmp_path,config=TimingConfig(enabled=True),monotonic=lambda:next(ticks))
    trace=store.begin('dimension.set_value')
    error=RuntimeError('Original operation error')
    with pytest.raises(RuntimeError) as caught:
        with trace.activate(),timing_span('apply_bundle'):
            with timing_span('rebuild'):raise error
    assert caught.value is error
    trace.finish('failed');row=records(tmp_path)[0]
    assert row['elapsed_s']==9.
    assert row['phases']['apply_bundle']==dict(interval_count=1,inclusive_s=6.,exclusive_s=3.)
    assert row['phases']['rebuild']==dict(interval_count=1,inclusive_s=3.,exclusive_s=3.)
    assert store.report()['phase_intervals']=='inclusive_nested_not_additive'


def test_row_limit_and_age_retention_enforced_even_without_new_writes(tmp_path):
    now=[100.]
    store=recorder(tmp_path,config=TimingConfig(enabled=True,max_records=2,retention_days=1),wall_clock=lambda:now[0])
    for seconds in (1.,2.,3.):
        measured(store,seconds);now[0]+=1.
    assert len(records(tmp_path))==2
    now[0]+=86401.
    assert store.report()['sample_count']==0 and records(tmp_path)==[]


def test_build_outcomes_kinds_and_scenarios_not_mixed_in_statistics(tmp_path):
    store=recorder(tmp_path,config=TimingConfig(enabled=True))
    for seconds in (1.,3.,5.,7.):measured(store,seconds)
    measured(store,100.,'failed');measured(store,200.,kind='poll')
    store.build={**BUILD,'git_sha':'c'*40};measured(store,300.)
    report=store.report()
    assert report['sample_count']==7 and len(report['groups'])==4
    group=next(row for row in report['groups'] if row['sample_count']==4)
    assert group['median_s']==4. and group['p95_s']==pytest.approx(6.7)
    assert store.report(kind='poll')['sample_count']==1
    assert store.report(operation='job_get')['sample_count']==0


def test_same_trace_finished_twice_is_one_record(tmp_path):
    store=recorder(tmp_path,config=TimingConfig(enabled=True))
    trace=measured(store);trace.finish('unknown')
    assert store.report()['sample_count']==1
    assert records(tmp_path)[0]['outcome']=='succeeded'


def test_storage_failure_cannot_raise_through_operation_or_invent_success(tmp_path):
    store=recorder(tmp_path,config=TimingConfig(enabled=True))
    store._db.close()
    measured(store,outcome='unknown')
    assert store.storage_failures==1 and store.dropped_records==1
    report=store.report()
    assert report['available'] is False and report['sample_count']==0


def test_unavailable_storage_initialization_stays_best_effort(tmp_path):
    blocker=tmp_path/'file';blocker.write_text('not a directory')
    store=TimingRecorder(blocker/'timing.sqlite',config=TimingConfig(enabled=True),build=BUILD,
        operations=('dimension.set_value',))
    measured(store)
    assert store.report()['available'] is False and store.storage_failures==1


@pytest.mark.parametrize('kwargs',[
    {'operation_id':'C:/private/model.sldprt'}, {'scenario':'part_model_customer'},
    {'kind':'private CAD params'},
])
def test_client_names_paths_and_unclassified_free_text_are_not_recorded(tmp_path,kwargs):
    store=recorder(tmp_path,config=TimingConfig(enabled=True))
    assert store.begin('dimension.set_value',**kwargs) is None
    assert records(tmp_path)==[]
    assert store.dropped_records==1


def test_record_contains_only_allowlisted_metadata_not_exception_or_arguments(tmp_path):
    store=recorder(tmp_path,config=TimingConfig(enabled=True))
    measured(store,outcome='failed');row=records(tmp_path)[0]
    assert set(row)=={'call_id','operation_id','operation','kind','scenario','build','outcome',
        'elapsed_s','finished_unix','phases'}
    assert not {'request_id','document_id','configuration','payload','error','arguments'} & set(row)


@pytest.mark.parametrize('kwargs',[
    {'enabled':1},{'max_records':0},{'max_records':True},{'retention_days':32},
    {'max_database_bytes':1024},
])
def test_invalid_operator_config_rejected(kwargs):
    with pytest.raises(ValueError):TimingConfig(**kwargs)


def test_database_has_hard_page_cap(tmp_path):
    store=recorder(tmp_path,config=TimingConfig(enabled=True,max_database_bytes=1024*1024))
    page=store._db.execute('PRAGMA page_size').fetchone()[0]
    cap=store._db.execute('PRAGMA max_page_count').fetchone()[0]
    assert page*cap<=1024*1024


def test_lower_record_limit_applies_on_reopen_before_any_new_record(tmp_path):
    store=recorder(tmp_path,config=TimingConfig(enabled=True,max_records=5))
    for _ in range(5):measured(store)
    store.close()
    smaller=recorder(tmp_path,config=TimingConfig(enabled=True,max_records=2))
    assert smaller.report()['sample_count']==2


def test_existing_oversized_database_is_unavailable_without_deleting_history(tmp_path):
    path=tmp_path/'private.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE unrelated(data BLOB)')
        db.execute('INSERT INTO unrelated VALUES (zeroblob(1200000))')
    original_size=path.stat().st_size
    store=recorder(tmp_path,config=TimingConfig(enabled=True,max_database_bytes=1024*1024))
    assert store.report()['available'] is False and store.storage_failures==1
    assert path.stat().st_size==original_size
