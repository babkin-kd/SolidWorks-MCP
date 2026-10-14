"""Optional local timing diagnostics; this facade never dispatches CAD work."""

from functools import wraps
from contextlib import nullcontext
import asyncio
import inspect

from pydantic import StrictFloat
from .contracts import ResponseEnvelope


class TimingToolRegistrar:
    """Wrap the public tool decorator while preserving signatures and schemas."""
    def __init__(self,app,recorder):
        self.app=app;self.recorder=recorder

    def __getattr__(self,name):
        return getattr(self.app,name)

    def tool(self,*args,**kwargs):
        register=self.app.tool(*args,**kwargs)
        def decorate(function):
            name=kwargs.get('name') or function.__name__
            if self.recorder is not None:
                self.recorder.operations=self.recorder.operations|{name}
            if self.recorder is None or name=='diagnostics_get_timings':
                return register(function)
            # Names come only from server-owned registrations, never arguments.
            kind='poll' if name in ('job_get','job_list') else 'mcp_call'
            @wraps(function)
            async def measured(*call_args,**call_kwargs):
                trace=self.recorder.begin(name,kind=kind)
                outcome='failed'
                try:
                    with trace.activate() if trace is not None else nullcontext():
                        result=function(*call_args,**call_kwargs)
                        if inspect.isawaitable(result):result=await result
                    outcome=getattr(result,'status','succeeded')
                    return result
                except asyncio.CancelledError:
                    outcome='cancelled'
                    raise
                finally:
                    if trace is not None:trace.finish(outcome)
            return register(measured)
        return decorate


def register_timing_tools(app,recorder,response):
    @app.tool()
    async def diagnostics_get_timings(period_s:StrictFloat=86400.,
            operation:str|None=None,kind:str|None=None) -> ResponseEnvelope:
        """Count, median and p95 for completed calls/jobs over a bounded period.

        Local private storage only: no CAD, model edits or job queue. Groups
        separate builds, fixed server scenario, outcome, jobs and job polls.
        Optional collection is disabled unless the operator enables it. Nested
        phase intervals overlap; they cannot be added to total elapsed time.
        The current broad domain scope is unclassified_v1, not a geometry claim.
        """
        try:
            if recorder is None:
                from .runtime_v2 import READ_OPERATIONS, MUTATING_OPERATIONS
                names={tool.name for tool in await app.list_tools()}
                if (not 0<period_s<=31*86400 or operation is not None and operation not in
                        names|set(READ_OPERATIONS)|set(MUTATING_OPERATIONS)
                        or kind not in (None,'job','mcp_call','poll')):
                    raise ValueError('Invalid timing filters or unknown operation.')
                return response(data=dict(enabled=False,available=False,sample_count=0,groups=[]))
            return response(data=recorder.report(period_s=period_s,operation=operation,kind=kind))
        except ValueError as exc:
            return response(status='failed',error=dict(code='invalid_timing_filter',message=str(exc)))
