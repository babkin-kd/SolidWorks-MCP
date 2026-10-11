"""Real facade schema and strict explicit read arguments, artificial runtime."""
import asyncio
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.component_aggregate_probe_tools_v2 import register_component_aggregate_probe_tools
from test_dimension_tools_v2 import Runtime


def setup():
    app=FastMCP('aggregate-probes');runtime=Runtime()
    register_component_aggregate_probe_tools(app,runtime,
        lambda **kwargs:ResponseEnvelope(diagnostics=[],**kwargs),lambda error:pytest.fail(str(error)))
    return app,runtime


@pytest.mark.parametrize('kind,extra',[('point',{'point_mm':[1.,2.,3.]}),
    ('axis',{'axis_origin_mm':[1.,2.,3.],'axis_direction':[0.,1.,0.]})])
def test_explicit_context_defaults_and_read_route(kind,extra):
    app,runtime=setup();args=dict(document_id='doc_exact',configuration='Основная',expected_observation_revision='obs_exact',component_id='cmp_exact',**extra)
    asyncio.run(app.call_tool('measurement_get_component_aggregate_'+kind+'_distance',dict(request_id='probe',timeout_s=0.,**args)))
    assert runtime.calls==[('read','probe','measurement.component_aggregate_'+kind+'_distance',dict(args,frame=None),0.)]


@pytest.mark.parametrize('kind,extra',[('point',{'point_mm':[True,2.,3.]}),
    ('axis',{'axis_origin_mm':[1.,2.,3.],'axis_direction':['1',0.,0.]})])
def test_invalid_vector_schema_never_dispatches(kind,extra):
    app,runtime=setup()
    with pytest.raises(ToolError):
        asyncio.run(app.call_tool('measurement_get_component_aggregate_'+kind+'_distance',dict(request_id='p',document_id='d',configuration='Основная',expected_observation_revision='o',component_id='c',**extra)))
    assert not runtime.calls


def test_missing_explicit_target_never_dispatches():
    app,runtime=setup()
    with pytest.raises(ToolError):
        asyncio.run(app.call_tool('measurement_get_component_aggregate_point_distance',dict(request_id='p',document_id='d',configuration='Основная',expected_observation_revision='o',point_mm=[1.,2.,3.])))
    assert not runtime.calls
