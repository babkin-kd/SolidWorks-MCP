"""Bounded B3 tool route using one live supervisor and exact durable receipts.

No fixtures, COM connection, cancellation or cleanup occur here. The concrete
driver supplies its independent before-dispatch safety check (including initial
bootstrap ownership); an empty supervisor tracker alone is never sufficient.
Queued/running acknowledgements are polled by the same operation_id without
resending the durable call. Session teardown remains with the live supervisor.
"""
from copy import deepcopy
import inspect
import math

import anyio

from verifier_b3_journal import ReceiptIndex, canonical, observe_durable_job
from verifier_b3_public_contract import SPECS


async def _call(callback, *args):
    value = callback(*args)
    return await value if inspect.isawaitable(value) else value


def _envelope(raw):
    if raw.isError is not False or type(raw.structuredContent) is not dict:
        raise ValueError('A structured public response is required.')
    value = raw.structuredContent
    if value.get('status') not in ('queued', 'running', 'succeeded', 'failed', 'unknown', 'cancelled'):
        raise ValueError('Unknown response status.')
    operation_id = value.get('operation_id')
    if type(operation_id) is not str or not operation_id:
        raise ValueError('No exact durable operation acknowledgement.')
    return value


class B3Reader:
    def __init__(self, client, journal_path, *, assert_before_dispatch, persist,
                 poll_interval=.25, pause=anyio.sleep,child_trace=None):
        if not callable(assert_before_dispatch) or not callable(persist) or not callable(pause):
            raise ValueError('Explicit owner safety, persistence and polling callbacks required.')
        if type(poll_interval) not in (int, float) or not math.isfinite(poll_interval) or not 0 < poll_interval <= 10:
            raise ValueError('Finite positive bounded poll interval required.')
        self.client, self.journal_path = client, journal_path
        self.assert_before_dispatch, self.persist = assert_before_dispatch, persist
        self.poll_interval, self.pause = poll_interval, pause
        self.receipts, self.index = [], ReceiptIndex()
        self._retained = False
        self.child_trace=child_trace

    async def read(self, tool, arguments, *, expected_error=None):
        if self._retained:
            raise RuntimeError('Read route retained after unconfirmed observation; no further dispatch.')
        if tool not in SPECS or type(arguments) is not dict:
            raise ValueError('One finite B3 tool and explicit arguments required.')
        args = deepcopy(arguments)
        request_id = args.get('request_id')
        if type(request_id) is not str or not request_id:
            raise ValueError('Caller must provide the original request_id; never auto-retry.')
        payload = SPECS[tool].payload(args)
        await _call(self.assert_before_dispatch)
        record = dict(tool=tool, arguments=args, payload=payload,
                      operation_id=None, state='dispatch_prepared', journal=None)
        self.receipts.append(record)
        # Failed persistence here prevents the RPC entirely.
        await _call(self.persist, deepcopy(self.receipts))
        try:
            value = _envelope(await self.client.call_tool(tool, args))
            operation_id = value['operation_id']
            acknowledgement = deepcopy(value)
            if canonical(value.get('context')) != canonical(payload['context']):
                raise ValueError('Tool acknowledgement differs from explicit request context.')
            record.update(operation_id=operation_id, state='acknowledged', acknowledgement=acknowledgement)
            await _call(self.persist, deepcopy(self.receipts))
            while value['status'] in ('queued', 'running'):
                # An observation timeout/cancellation never resends or cancels CAD.
                value = _envelope(await self.client.call_tool('job_get', {'operation_id': operation_id}))
                if value['operation_id'] != operation_id:
                    raise ValueError('Polling acknowledged a different durable operation.')
                if value['status'] in ('queued', 'running'):
                    await _call(self.pause, self.poll_interval)
            row = await observe_durable_job(self.client, self.journal_path,
                operation_id=operation_id, tool=tool, arguments=args, expected_error=expected_error)
            if acknowledgement['status'] not in ('queued', 'running'):
                if (acknowledgement['status'] != row['status']
                        or canonical(acknowledgement.get('data')) != canonical(row['result'])
                        or canonical(acknowledgement.get('error')) != canonical(row['error'])):
                    raise ValueError('Terminal tool response differs from independent durable result.')
            elif acknowledgement.get('data') is not None or acknowledgement.get('error') is not None:
                raise ValueError('Unfinished acknowledgement unexpectedly publishes a final result/error.')
            if self.child_trace is not None:
                record['child_trace']=self.child_trace.bind(row)
            self.index.add(tool=tool, arguments=args, row=row, expected_error=expected_error)
            record.update(state='journal_bound', journal=row)
            await _call(self.persist, deepcopy(self.receipts))
            # Raw complete row, not a fabricated success/geometry summary.
            return deepcopy(row)
        except BaseException:
            self._retained = True
            self.client.retain('B3 tool acknowledgement/polling/receipt unconfirmed')
            raise
