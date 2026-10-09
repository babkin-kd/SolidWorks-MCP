"""Single-threaded COM execution for SolidWorks.

COM is single-threaded-apartment (STA) and thread-affine: every call must run on
the same thread that CoInitialized the apartment and connected to SolidWorks.
The MCP server runs on an asyncio event loop, and tool handlers may be scheduled
in ways that make "just call it inline" unsafe over time. So we pin ALL COM work
to one dedicated thread and have handlers submit callables to it.

This is how the kickoff principle "one COM session, single-threaded" is actively
enforced inside an async server -- it does not happen by itself.

The worker blocks on a queue (event-driven, no polling) and runs one job at a
time, which also serialises calls exactly as the stateful SolidWorks API wants.

Design constraints to be aware of:
- Event sinks require pump_messages=True. The v2 CAD runtime enables the STA
  message pump; legacy outbound-only clients can keep it disabled. Callbacks
  must only invalidate state, never perform reentrant CAD operations.
- No in-flight cancellation: a COM call cannot be force-aborted once started, so
  `call` enforces a timeout on the *await* (surfacing a readable error) but the
  worker thread itself stays on the blocked call until SolidWorks returns.
"""

import asyncio
import concurrent.futures
import queue
import threading

import pythoncom

from .errors import SolidWorksError

# Most SolidWorks API calls finish in well under a second; a generous ceiling
# turns an unattended hang (e.g. an unsuppressed modal dialog) into a readable
# error instead of an infinite wait that wedges the whole server.
DEFAULT_CALL_TIMEOUT_S = 120.0


class ComWorker:
    """Runs submitted callables on one dedicated STA thread, one at a time."""

    _STOP = object()

    def __init__(self, call_timeout_s: float = DEFAULT_CALL_TIMEOUT_S, *, pump_messages: bool = False) -> None:
        self._call_timeout_s = call_timeout_s
        self._pump_messages = pump_messages
        self._queue: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self._shutting_down = False
        self._state_lock = threading.Lock()
        self._startup_error = None
        self._finalizers = []
        self._shutdown_errors = []
        self._thread = threading.Thread(target=self._run, name="solidworks-com", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=10):
            self._shutting_down = True
            self._queue.put(self._STOP)
            raise SolidWorksError("The COM apartment did not initialise within 10s.")
        if self._startup_error is not None:
            raise SolidWorksError(f"Could not initialise the COM apartment: {self._startup_error}")

    def _run(self) -> None:
        try:
            pythoncom.CoInitialize()  # STA for this thread
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                if self._pump_messages:
                    if pythoncom.PumpWaitingMessages():
                        raise SolidWorksError('The COM apartment received WM_QUIT.')
                try:
                    job = self._queue.get(timeout=0.05 if self._pump_messages else None)
                except queue.Empty:
                    continue
                if job is self._STOP:
                    break
                fn, fut = job
                if not fut.set_running_or_notify_cancel():
                    continue  # awaiter timed out / gave up before we started this job
                try:
                    fut.set_result(fn())
                except BaseException as exc:  # noqa: BLE001 - relay to the caller
                    fut.set_exception(exc)
        except BaseException as exc:
            self._shutdown_errors.append(str(exc))
        finally:
            with self._state_lock:
                self._shutting_down = True
            # Failed apartment/pump: these queued functions have never run. Fail
            # their futures instead of leaving durable jobs queued indefinitely.
            while True:
                try:
                    pending = self._queue.get_nowait()
                except queue.Empty:
                    break
                if pending is self._STOP:
                    continue
                _, future = pending
                if future.set_running_or_notify_cancel():
                    future.set_exception(SolidWorksError('COM apartment stopped before queued execution.'))
            for finalizer in self._finalizers:
                try:
                    finalizer()
                except BaseException as exc:
                    self._shutdown_errors.append(str(exc))
            self._finalizers.clear()
            pythoncom.CoUninitialize()

    def add_finalizer(self, function):
        """Server-owned cleanup, guaranteed before CoUninitialize even after pump failure."""
        with self._state_lock:
            if self._shutting_down:
                raise SolidWorksError('The COM worker is shut down.')
            self._finalizers.append(function)

    def submit(self, fn) -> "concurrent.futures.Future":
        with self._state_lock:
            if self._shutting_down:
                raise SolidWorksError("The COM worker is shut down; no new operations are possible.")
            fut: "concurrent.futures.Future" = concurrent.futures.Future()
            self._queue.put((fn, fut))
            return fut

    async def call(self, fn):
        """Submit `fn` to the COM thread and await its result, with a timeout.

        On timeout the COM call is almost always blocked on a modal dialog. We
        cannot force-abort it, so we raise a clear, actionable error rather than
        hang forever. The job, if not yet started, is skipped when dequeued.
        """
        fut = self.submit(fn)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(fut), self._call_timeout_s)
        except asyncio.TimeoutError:
            raise SolidWorksError(
                f"SolidWorks did not respond within {self._call_timeout_s:.0f}s. "
                "A modal dialog is probably open in SolidWorks. "
                "Close any dialogs; restart the server if it keeps hanging."
            )

    def shutdown(self, timeout_s: float = 5) -> bool:
        with self._state_lock:
            if not self._shutting_down:
                self._shutting_down = True
                self._queue.put(self._STOP)
        self._thread.join(timeout=timeout_s)
        return not self._thread.is_alive()
