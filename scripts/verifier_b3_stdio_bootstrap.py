"""Installed stdio server with private, same-STA registration evidence only.

No additional public tools or CAD getters. Original results/exceptions remain
unchanged. A missing/failed trace invalidates driver evidence, not the CAD job.
Parent native window/PID/original ownership proofs remain mandatory.
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
    def __init__(self,*args,trace_dir,**kwargs):
        super().__init__(*args,**kwargs)
        self.trace_dir=Path(trace_dir)
        self.trace_sequence=0
        self.trace_bytes=0
        self.trace_error=None
        self.trace_terminal_written=False

    def _record(self,operation,arguments,operation_id,*,result=None,error=None):
        # Diagnostic failure never converts an acknowledged operation to unknown
        # and never retries it. Parent must reject absent/incomplete trace.
        if self.trace_error is not None:return
        try:
            require(self.trace_sequence<256,'Finite B3 trace budget exhausted.')
            catalog=self._catalog
            exports=[]
            if error is None:
                require(catalog is not None,'Normally returned operation needs its actual catalog.')
                catalog._check_thread()
                entries=tuple(catalog._entries)
                require(len(entries)<=32,'Finite actual registration document census required.')
                exports=[export_registered_references(entry,assert_safe=catalog._check_thread) for entry in entries]
                current=tuple(catalog._entries)
                require(len(current)==len(entries) and all(left is right for left,right in zip(current,entries)),
                        'Actual catalog changed during private export.')
            row=dict(scope='private_b3_child_registration_trace_v1',
                sequence=self.trace_sequence+1,operation=operation,arguments=arguments,
                operation_id=operation_id,connection_epoch=self._connection_epoch,
                status='returned' if error is None else 'exception_returned',
                result_sha256=hashlib.sha256(_json(result).encode('utf8')).hexdigest() if error is None else None,
                error=None if error is None else dict(type=type(error).__name__,code=getattr(error,'code',None)),
                registered_references=exports,accepted=False,native_acceptance=False,
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
    server_v2.Runtime=lambda *args,**kwargs:RegistrationTraceRuntime(*args,trace_dir=trace,**kwargs)
    sys.argv=[sys.argv[0],*inherited]
    try:server_v2.main()
    finally:server_v2.Runtime,sys.argv=original_runtime,original_argv


if __name__=='__main__':main()
