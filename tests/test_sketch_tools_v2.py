"""Actual MCP schemas/dispatch, artificial runtime; no CAD acceptance."""
import asyncio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest
from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.sketch_tools_v2 import register_sketch_tools
from test_dimension_tools_v2 import Runtime


@pytest.fixture
def setup():
    app,runtime=FastMCP('sketch-test'),Runtime()
    register_sketch_tools(app,runtime,lambda **kw:ResponseEnvelope(diagnostics=[],**kw),lambda error:pytest.fail(str(error)))
    return app,runtime


def args(tool):
    result=dict(request_id='sketch-r',document_id='doc_explicit',configuration='Основная',object_id='feat_explicit',timeout_s=0.)
    if tool!='sketch_get':result.update(dimension_id='dim_explicit',value_mm=45.)
    if tool=='sketch_set_dimension':result['expected_revision']='rev_explicit'
    return result


@pytest.mark.parametrize('tool,method,operation', [('sketch_get','read','sketch.get'),
    ('sketch_prepare_dimension_change','read','sketch.prepare_dimension_change'),
    ('sketch_set_dimension','mutate','sketch.set_dimension')])
def test_exact_targets_reach_runtime_and_timeout_is_not_job_payload(setup,tool,method,operation):
    app,runtime=setup
    _,result=asyncio.run(app.call_tool(tool,args(tool)))
    sent={k:v for k,v in args(tool).items() if k not in ('request_id','timeout_s')}
    assert runtime.calls==[(method,'sketch-r',operation,sent,0.)]
    assert set(result)=={'status','operation_id','context','data','diagnostics','error'}


@pytest.mark.parametrize('tool',['sketch_prepare_dimension_change','sketch_set_dimension'])
@pytest.mark.parametrize('value',[True,'45',float('nan'),float('inf'),0.,.0001,10000001.])
def test_invalid_length_rejected_by_schema_before_runtime(setup,tool,value):
    app,runtime=setup
    payload=args(tool);payload['value_mm']=value
    with pytest.raises(ToolError):asyncio.run(app.call_tool(tool,payload))
    assert runtime.calls==[]
