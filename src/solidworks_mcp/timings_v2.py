"""Private bounded timing records. No CAD dependency or job payload storage.

Inclusive phases can overlap/nest; they must never be added to total elapsed.
Exclusive time excludes measured direct children. Uninstrumented work remains
in total elapsed, rather than being mislabelled as COM or rebuild time.
"""

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sqlite3
import statistics
import threading
import time
import uuid


PHASES=frozenset({'queue','prepare','validate','apply_bundle','postconditions',
    'restoration','journal','com','rebuild','await_result','read_bundle'})
KINDS=frozenset({'job','mcp_call','poll'})
OUTCOMES=frozenset({'succeeded','failed','unknown','cancelled','queued','running'})
_current=ContextVar('solidworks_timing_trace',default=None)


@dataclass(frozen=True)
class TimingConfig:
    enabled:bool=False
    max_records:int=1000
    retention_days:int=7
    max_database_bytes:int=16*1024*1024

    def __post_init__(self):
        if (type(self.enabled) is not bool or type(self.max_records) is not int
                or not 1<=self.max_records<=10000 or type(self.retention_days) is not int
                or not 1<=self.retention_days<=31 or type(self.max_database_bytes) is not int
                or not 1024*1024<=self.max_database_bytes<=64*1024*1024):
            raise ValueError('Invalid bounded timing configuration.')


def _percentile(values,q):
    """Linear interpolation; return sample size alongside statistics."""
    ordered=sorted(values);index=(len(ordered)-1)*q;lower=math.floor(index)
    return ordered[lower]+(ordered[math.ceil(index)]-ordered[lower])*(index-lower)


def timing_span(phase):
    trace=_current.get()
    return trace.span(phase) if trace is not None else nullcontext()


def timed_call(phase,function,*args,**kwargs):
    with timing_span(phase):
        return function(*args,**kwargs)


class TimingRecorder:
    def __init__(self,path,*,config=TimingConfig(),build,operations,scenarios=('unclassified_v1',),
                 monotonic=time.perf_counter,wall_clock=time.time):
        if (set(build)!={'package_version','git_sha','source_digest'}
                or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:\.(?:dev|a|b|rc)[0-9]+)?',build['package_version'])
                or not re.fullmatch(r'[0-9a-f]{40}',build['git_sha'])
                or not re.fullmatch(r'[0-9a-f]{64}',build['source_digest'])):
            raise ValueError('Only public build identity belongs in timing records.')
        if any(not re.fullmatch(r'[a-z][a-z0-9_.]{0,127}',op) for op in operations):
            raise ValueError('Timing operations must be server-owned constant names.')
        if any(not re.fullmatch(r'[a-z][a-z0-9_]{0,79}',scope) for scope in scenarios):
            raise ValueError('Timing scenarios must be server-owned constant names.')
        self.config=config;self.build=dict(build);self.operations=frozenset(operations)
        self.scenarios=frozenset(scenarios)
        self.clock=monotonic;self.wall_clock=wall_clock;self._lock=threading.RLock()
        self._db=None;self.storage_failures=0;self.dropped_records=0
        if config.enabled:
            try:
                path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
                self._db=sqlite3.connect(path,timeout=.05,check_same_thread=False)
                self._db.execute('PRAGMA journal_mode=DELETE')
                page_size=self._db.execute('PRAGMA page_size').fetchone()[0]
                allowed_pages=config.max_database_bytes//page_size
                actual_cap=self._db.execute('PRAGMA max_page_count='+str(allowed_pages)).fetchone()[0]
                if actual_cap>allowed_pages:
                    raise ValueError('Existing timing database exceeds the configured size bound.')
                self._db.execute('CREATE TABLE IF NOT EXISTS timings (call_id TEXT PRIMARY KEY, '
                    'finished REAL NOT NULL, record TEXT NOT NULL)')
                self._db.execute('DELETE FROM timings WHERE finished<?',
                    (self.wall_clock()-config.retention_days*86400,))
                self._db.execute('DELETE FROM timings WHERE call_id IN '
                    '(SELECT call_id FROM timings ORDER BY finished DESC,call_id DESC LIMIT -1 OFFSET ?)',
                    (config.max_records,))
                self._db.commit()
            except Exception:
                self.storage_failures+=1
                if self._db is not None:self._db.close()
                self._db=None

    def begin(self,operation,*,kind='job',scenario='unclassified_v1',operation_id=None):
        if not self.config.enabled:return None
        try:
            if (operation not in self.operations or kind not in KINDS
                    or scenario not in self.scenarios
                    or operation_id is not None and not re.fullmatch(r'job_[0-9a-f]{32}',operation_id)):
                raise ValueError('Only server-owned timing metadata is permitted.')
            return TimingTrace(self,operation,kind,scenario,operation_id)
        except Exception:
            self.dropped_records+=1;return None

    def _write(self,record):
        """Best effort only: never shares or weakens the mandatory job journal."""
        with self._lock:
            if self._db is None:self.dropped_records+=1;return
            try:
                encoded=json.dumps(record,allow_nan=False,separators=(',',':'))
                if len(encoded.encode('utf8'))>16384:raise ValueError('Timing record exceeded its fixed bound.')
                cutoff=record['finished_unix']-self.config.retention_days*86400
                with self._db:
                    self._db.execute('DELETE FROM timings WHERE finished<?',(cutoff,))
                    self._db.execute('INSERT INTO timings VALUES (?,?,?)',
                        (record['call_id'],record['finished_unix'],encoded))
                    self._db.execute('DELETE FROM timings WHERE call_id IN '
                        '(SELECT call_id FROM timings ORDER BY finished DESC,call_id DESC LIMIT -1 OFFSET ?)',
                        (self.config.max_records,))
            except Exception:self.storage_failures+=1;self.dropped_records+=1

    def report(self,*,period_s=86400.,operation=None,kind=None):
        if (type(period_s) not in (int,float) or not math.isfinite(period_s)
                or not 0<period_s<=31*86400 or operation is not None and operation not in self.operations
                or kind is not None and kind not in KINDS):
            raise ValueError('Invalid timing filters.')
        result=dict(enabled=self.config.enabled,available=self._db is not None,
            storage_failures=self.storage_failures,dropped_records=self.dropped_records,
            sample_count=0,groups=[],phase_intervals='inclusive_nested_not_additive',
            diagnostic_write_in_total=False,
            com_coverage='selected_explicit_calls_only_not_total_dispatch_count',
            elapsed_scope='dispatch_to_terminal_for_jobs_request_lifetime_for_calls',
            limits=dict(max_records=self.config.max_records,retention_days=self.config.retention_days,
                max_database_bytes=self.config.max_database_bytes),
            effective_period_s=min(period_s,self.config.retention_days*86400))
        if self._db is None:return result
        with self._lock:
            try:
                cutoff=self.wall_clock()-min(period_s,self.config.retention_days*86400)
                with self._db:self._db.execute('DELETE FROM timings WHERE finished<?',
                    (self.wall_clock()-self.config.retention_days*86400,))
                rows=[json.loads(row[0]) for row in self._db.execute(
                    'SELECT record FROM timings WHERE finished>=? ORDER BY finished',(cutoff,))]
            except Exception:
                self.storage_failures+=1;result.update(available=False,storage_failures=self.storage_failures);return result
        try:
            return self._summarize(rows,result,operation,kind)
        except Exception:
            self.storage_failures+=1
            result.update(available=False,storage_failures=self.storage_failures,sample_count=0,groups=[])
            return result

    def _summarize(self,rows,result,operation,kind):
        groups={}
        for row in rows:
            if (not isinstance(row,dict) or not math.isfinite(row['elapsed_s']) or row['elapsed_s']<0
                    or row['operation'] not in self.operations or row['scenario'] not in self.scenarios
                    or row['kind'] not in KINDS or row['outcome'] not in OUTCOMES
                    or set(row['build'])!={'package_version','git_sha','source_digest'}
                    or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:\.(?:dev|a|b|rc)[0-9]+)?',row['build']['package_version'])
                    or not re.fullmatch(r'[0-9a-f]{40}',row['build']['git_sha'])
                    or not re.fullmatch(r'[0-9a-f]{64}',row['build']['source_digest'])):
                raise ValueError('Invalid private timing record.')
            for phase,item in row['phases'].items():
                if (phase not in PHASES or type(item['interval_count']) is not int or item['interval_count']<1
                        or any(not math.isfinite(item[k]) or item[k]<0 for k in ('inclusive_s','exclusive_s'))):
                    raise ValueError('Invalid private timing phase.')
            if (operation is not None and row['operation']!=operation or kind is not None and row['kind']!=kind):continue
            key=(json.dumps(row['build'],sort_keys=True),row['operation'],row['kind'],row['scenario'],row['outcome'])
            groups.setdefault(key,[]).append(row)
        def stats(values):return dict(sample_count=len(values),median_s=statistics.median(values),p95_s=_percentile(values,.95))
        for (_,op,row_kind,scenario,outcome),samples in sorted(groups.items()):
            phases={}
            for phase in PHASES:
                values=[row['phases'][phase]['inclusive_s'] for row in samples if phase in row['phases']]
                if values:
                    phases[phase]={**stats(values), 'exclusive':stats([
                        row['phases'][phase]['exclusive_s'] for row in samples if phase in row['phases']]),
                        'interval_count':sum(row['phases'][phase]['interval_count']
                            for row in samples if phase in row['phases'])}
            result['groups'].append(dict(build=samples[0]['build'],operation=op,kind=row_kind,scenario=scenario,
                outcome=outcome,**stats([row['elapsed_s'] for row in samples]),phases=phases,
                slowest_phases=sorted(phases,key=lambda name:phases[name]['median_s'],reverse=True)))
            result['sample_count']+=len(samples)
        return result

    def close(self):
        with self._lock:
            db,self._db=self._db,None
            if db is not None:
                try:db.close()
                except Exception:self.storage_failures+=1


class TimingTrace:
    def __init__(self,recorder,operation,kind,scenario,operation_id):
        self.recorder=recorder;self.start=recorder.clock();self.phases={};self.stack=[];self.finished=False
        self.metadata=dict(call_id='trace_'+uuid.uuid4().hex,operation_id=operation_id,
            operation=operation,kind=kind,scenario=scenario,build=dict(recorder.build))

    def end_queue(self):
        """Only the owning worker, or a confirmed dispatch failure, ends queue time."""
        if 'queue' in self.phases:return
        try:
            elapsed=self.recorder.clock()-self.start
            if not math.isfinite(elapsed) or elapsed<0:raise ValueError('Invalid queue interval.')
            self.phases['queue']=dict(interval_count=1,inclusive_s=elapsed,exclusive_s=elapsed)
        except Exception:self.recorder.dropped_records+=1

    @contextmanager
    def activate(self):
        token=_current.set(self)
        try:yield self
        finally:_current.reset(token)

    @contextmanager
    def span(self,phase):
        if phase not in PHASES:yield;return
        try:frame=[self.recorder.clock(),0.];self.stack.append(frame)
        except Exception:yield;return
        try:yield
        finally:
            try:
                elapsed=self.recorder.clock()-frame[0]
                if not math.isfinite(elapsed) or elapsed<0:raise ValueError('Non-monotonic timing interval.')
                if self.stack.pop() is not frame:raise ValueError('Timing phases must close in stack order.')
                if self.stack:self.stack[-1][1]+=elapsed
                row=self.phases.setdefault(phase,dict(interval_count=0,inclusive_s=0.,exclusive_s=0.))
                row['interval_count']+=1;row['inclusive_s']+=elapsed;row['exclusive_s']+=max(0.,elapsed-frame[1])
            except Exception:self.recorder.dropped_records+=1

    def finish(self,outcome):
        if self.finished:return
        self.finished=True
        try:
            elapsed=self.recorder.clock()-self.start
            if outcome not in OUTCOMES or self.stack or not math.isfinite(elapsed) or elapsed<0:
                raise ValueError('Incomplete timing trace.')
            self.recorder._write(dict(self.metadata,outcome=outcome,elapsed_s=elapsed,
                finished_unix=self.recorder.wall_clock(),phases=self.phases))
        except Exception:self.recorder.dropped_records+=1
