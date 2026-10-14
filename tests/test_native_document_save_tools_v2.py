import asyncio
from mcp.server.fastmcp import FastMCP
import pytest
from solidworks_mcp.native_document_save_tools_v2 import register_native_document_save_tools


class Runtime:
    def __init__(self):self.calls=[]
    async def read(self,request_id,operation,args,**kwargs):
        self.calls.append((False,request_id,operation,args,kwargs));return self.result(args)
    async def mutate(self,request_id,operation,args,**kwargs):
        self.calls.append((True,request_id,operation,args,kwargs));return self.result(args)
    def result(self,args):return dict(status='succeeded',operation_id='op',payload={'context':args},result={'verified':True},error=None)


def application():
    app=FastMCP('native-save');runtime=Runtime()
    register_native_document_save_tools(app,runtime,lambda **kwargs:kwargs,lambda exc:pytest.fail(str(exc)))
    return app,runtime


@pytest.mark.parametrize('tool,mutates',[('document_prepare_save_native',False),('document_save_native',True)])
def test_native_save_facade_explicit_durable_context(tool,mutates):
    app,runtime=application();args=dict(request_id='r',document_id='doc',configuration='Основная',timeout_s=0.)
    if mutates:args['expected_revision']='rev'
    asyncio.run(app.call_tool(tool,args));call=runtime.calls[0]
    assert call[0] is mutates and call[1]=='r' and call[3]['document_id']=='doc' and call[4]['timeout_s']==0.
    if mutates:assert call[3]['expected_revision']=='rev'


@pytest.mark.parametrize('bad',[{'timeout_s':True},{'timeout_s':-1.},{'timeout_s':121.},{'expected_revision':None}])
def test_invalid_save_parameters_do_not_dispatch(bad):
    app,runtime=application();args=dict(request_id='r',document_id='doc',configuration='Основная',expected_revision='rev',timeout_s=0.)
    args.update(bad)
    with pytest.raises(Exception):asyncio.run(app.call_tool('document_save_native',args))
    assert not runtime.calls
