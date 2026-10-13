"""Installed stdio server with private, same-STA registration evidence only.

No additional public tools. Registration-only mode performs no CAD getters.
Optional window mode reads current native model/HWND associations on this STA.
Original results/exceptions remain unchanged; parent native envelope/PID/birth
proofs stay mandatory, including ABA. Failed trace never replaces the CAD job.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from solidworks_mcp.jobs import _json
from solidworks_mcp.runtime_v2 import Runtime
from verifier_b3_registered_references import export_registered_references,require


class RegistrationTraceRuntime(Runtime):
    def __init__(self,*args,trace_dir,expected_window_hwnds=None,**kwargs):
        super().__init__(*args,**kwargs)
        require(expected_window_hwnds is None or (type(expected_window_hwnds) is tuple
            and 0<len(expected_window_hwnds)<=32
            and all(type(hwnd) is int and 0<hwnd<2**63 for hwnd in expected_window_hwnds)
            and len(set(expected_window_hwnds))==len(expected_window_hwnds)),
            'Explicit original unique HWND roster required for window observations.')
        self.expected_window_hwnds=expected_window_hwnds
        self.trace_dir=Path(trace_dir)
        self.trace_sequence=0
        self.trace_bytes=0
        self.trace_error=None
        self.trace_terminal_written=False

    def _window_bindings(self,catalog,entries):
        if self.expected_window_hwnds is None:return None
        catalog._check_thread()
        adapter=catalog.adapter
        require(len(entries)==len(self.expected_window_hwnds),'Complete original window/document roster required.')
        require(len({entry.document_id for entry in entries})==len(entries),'Unique existing catalog IDs required.')
        canonicals=[entry.identity for entry in entries]
        require(all(sum(token==other for other in canonicals)==1 for token in canonicals),
                'Distinct original catalog model incarnations required.')
        current=adapter.documents()
        tokens=[adapter.identity(model) for model in current]
        require(len(tokens)==len(entries) and all(sum(token==original for token in tokens)==1 for original in canonicals),
                'Current complete document census changed; no new model adoption.')
        windows=adapter.native_close_windows()
        require(len(windows)==len(entries),'Exactly one native window per original catalog model required.')
        rows=[]
        for entry in entries:
            require(adapter.identity(entry.model)==entry.identity,'Retained catalog model replaced.')
            matches=[info for model,info in windows if adapter.identity(model)==entry.identity]
            require(len(matches)==1,'One actual native window/model canonical association required.')
            hwnd=matches[0]['hwnd']
            require(type(hwnd) is int and hwnd in self.expected_window_hwnds,'Actual window is outside original HWND roster.')
            rows.append(dict(document_id=entry.document_id,hwnd=hwnd))
        require(len({row['hwnd'] for row in rows})==len(rows)
                and {row['hwnd'] for row in rows}==set(self.expected_window_hwnds),'Complete distinct original HWND roster required.')
        return rows

    def _record(self,operation,arguments,operation_id,*,result=None,error=None):
        # Diagnostic failure never converts an acknowledged operation to unknown
        # and never retries it. Parent must reject absent/incomplete trace.
        if self.trace_error is not None:return
        try:
            require(self.trace_sequence<256,'Finite B3 trace budget exhausted.')
            journal=self.store.list(limit=1000)
            require(journal['next_cursor'] is None,'Complete finite own journal required; no partial job matching.')
            running=[job for job in journal['items'] if job['status']=='running']
            require(len(running)==1,'Exactly one actual owning-STA running job required.')
            job=running[0]
            require(job['operation']==operation and _json(job['payload']['arguments'])==_json(arguments)
                    and (operation_id is None or operation_id==job['operation_id']),
                    'Actual running SQLite job must bind this exact callback and payload.')
            catalog=self._catalog
            exports=[]
            windows=None
            if error is None:
                require(catalog is not None,'Normally returned operation needs its actual catalog.')
                catalog._check_thread()
                entries=tuple(catalog._entries)
                require(len(entries)<=32,'Finite actual registration document census required.')
                windows=self._window_bindings(catalog,entries)
                exports=[export_registered_references(entry,assert_safe=catalog._check_thread) for entry in entries]
                require(self._window_bindings(catalog,entries)==windows,'Current native window bindings changed during export.')
                current=tuple(catalog._entries)
                require(len(current)==len(entries) and all(left is right for left,right in zip(current,entries)),
                        'Actual catalog changed during private export.')
            row=dict(scope='private_b3_child_registration_trace_v1',
                sequence=self.trace_sequence+1,operation=operation,arguments=arguments,
                operation_id=job['operation_id'],request_id=job['request_id'],
                journal_status_at_capture='running',
                journal_payload_sha256=hashlib.sha256(_json(job['payload']).encode('utf8')).hexdigest(),
                connection_epoch=self._connection_epoch,
                status='returned' if error is None else 'exception_returned',
                result_sha256=hashlib.sha256(_json(result).encode('utf8')).hexdigest() if error is None else None,
                error=None if error is None else dict(type=type(error).__name__,code=getattr(error,'code',None)),
                registered_references=exports,document_window_bindings=windows,
                whole_session_native_envelope_verified=False,original_birth_ownership_verified=False,
                accepted=False,native_acceptance=False,
                current_membership_verified=False,cleanup_authorized=False,
                open_gates=['parent_original_model_HWND_bridge','current_PID_owner_roundtrip',
                            'whole_session_native_envelope','coherent_terminal_job_and_exact_driver'])
            raw=json.dumps(row,ensure_ascii=False,allow_nan=False,sort_keys=True).encode('utf8')
            require(len(raw)<=1024*1024,'Complete trace exceeds private per-record budget.')
            require(self.trace_bytes+len(raw)<=16*1024*1024,'Finite whole B3 trace budget exhausted.')
            path=self.trace_dir/f'{row["sequence"]:04d}.json'
            with path.open('xb') as stream:stream.write(raw)
            self.trace_sequence+=1
            self.trace_bytes+=len(raw)
        except Exception as failure:
            self.trace_error=dict(type=type(failure).__name__,message=str(failure))

    def _execute(self,operation,arguments,operation_id=None):
        try:
            result=super()._execute(operation,arguments,operation_id)
        except Exception as error:
            self._record(operation,arguments,operation_id,error=error)
            raise
        self._record(operation,arguments,operation_id,result=result)
        return result

    def shutdown(self,timeout_s=5):
        stopped=super().shutdown(timeout_s=timeout_s)
        # Never inspect native proxies on this caller thread or infer a stopped
        # worker from observation timeout. This is the actual Runtime result.
        if stopped and not self.trace_terminal_written:
            try:
                row=dict(scope='private_b3_child_trace_shutdown_v1',
                    worker_shutdown_confirmed=True,records=self.trace_sequence,
                    bytes=self.trace_bytes,trace_error=self.trace_error,
                    accepted=False,native_acceptance=False,cleanup_authorized=False)
                with (self.trace_dir/'terminal.json').open('x',encoding='utf8') as stream:
                    json.dump(row,stream,ensure_ascii=False,allow_nan=False)
                self.trace_terminal_written=True
            except Exception as failure:
                self.trace_error=dict(type=type(failure).__name__,message=str(failure))
        return stopped


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--trace-dir',type=Path,required=True)
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--expected-version',required=True)
    parser.add_argument('--expected-git-sha',required=True)
    parser.add_argument('--original-window-hwnd',type=int,action='append')
    own,inherited=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    private=Path(__file__).resolve().parents[1]/'work'
    trace=own.trace_dir.resolve()
    require(trace.is_relative_to(private) and trace!=private and not trace.exists(),
            'Fresh private work trace directory required.')
    require('--state-dir' in inherited,'Original server state directory required.')
    state=Path(inherited[inherited.index('--state-dir')+1]).resolve()
    require(state.is_relative_to(private) and state!=private and not state.exists()
            and not trace.is_relative_to(state) and not state.is_relative_to(trace),
            'Fresh separate private server and trace directories required.')
    from verify_wheel_artifact import validate_wheel
    from verify_installed_metadata import installed_identity
    wheel=validate_wheel(own.wheel,expected_version=own.expected_version,expected_git_sha=own.expected_git_sha)
    installed_identity(wheel)
    trace.mkdir(parents=True)
    from solidworks_mcp import server_v2
    original_runtime,original_argv=server_v2.Runtime,sys.argv[:]
    server_v2.Runtime=lambda *args,**kwargs:RegistrationTraceRuntime(*args,trace_dir=trace,
        expected_window_hwnds=None if own.original_window_hwnd is None else tuple(own.original_window_hwnd),**kwargs)
    sys.argv=[sys.argv[0],*inherited]
    try:server_v2.main()
    finally:server_v2.Runtime,sys.argv=original_runtime,original_argv


if __name__=='__main__':main()
