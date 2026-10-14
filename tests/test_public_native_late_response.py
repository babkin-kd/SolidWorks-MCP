"""Verifier wait/replay transport contracts; no process, CAD or native oracle."""

import ast
import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest


tree = ast.parse((Path(__file__).resolve().parents[1] / 'scripts/verify_dimension_mcp.py').read_text(encoding='utf-8'))
selected = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
            and node.name in ('response', 'terminal_job', 'call')]


async def immediate_sleep(_):
    return None


namespace = dict(asyncio=SimpleNamespace(sleep=immediate_sleep), uuid=uuid)
exec(compile(ast.Module(body=selected,type_ignores=[]),'public_late_transport','exec'),namespace)
call = namespace['call']


class Client:
    def __init__(self, envelope, pending):
        self.envelope, self.pending, self.calls = envelope, list(pending), []

    async def call_tool(self,name,arguments):
        self.calls.append((name,deepcopy(arguments)))
        if name == 'job_get':
            value = self.pending.pop(0)
        else:
            value = self.envelope
        return SimpleNamespace(isError=False,structuredContent=deepcopy(value))


@pytest.mark.parametrize('operation', ['document_activate_part_native','document_first_save_native','document_open_native','document_save_native'])
def test_late_result_and_terminal_replay_share_envelope_without_repeating_native_dispatch(operation):
    context = dict(document_id='doc_bound',configuration='Основная',expected_revision='rev_bound')
    result = dict(value={'document_id':'doc_final'},verified=True)
    envelope = dict(status='running',operation_id='job_own',context=context,data=None,error=None,diagnostics=[])
    terminal = {**envelope,'status':'succeeded','data':dict(result=result)}
    client = Client(envelope,[{**terminal,'status':'running'},terminal])
    late = asyncio.run(call(client,operation,request_id='same_request',timeout_s=0.,**context))
    replay = Client({**terminal,'data':result},[])
    assert asyncio.run(call(replay,operation,request_id='same_request',timeout_s=0.,**context)) == late
    assert [name for name,args in client.calls] == [operation,'job_get','job_get']
    assert client.calls[0][1]['request_id']=='same_request'
    assert all(args=={'operation_id':'job_own'} for name,args in client.calls[1:])


def test_unknown_late_result_is_preserved_not_fabricated_as_success():
    pending=dict(status='running',operation_id='job_own',context={},data=None,error=None,diagnostics=[])
    unknown={**pending,'status':'unknown','data':{'result':None},'error':{'code':'lost_ack','requires_reconciliation':True}}
    client=Client(pending,[unknown])
    value=asyncio.run(call(client,'document_first_save_native',request_id='request'))
    assert value['status']=='unknown' and value['data'] is None and value['error']['requires_reconciliation'] is True
    assert [name for name,args in client.calls]==['document_first_save_native','job_get']
