"""Actual isolated MCP schema/dispatch, fake runtime; no native CAD acceptance."""
import asyncio
from copy import deepcopy
import sqlite3
from types import SimpleNamespace as NS

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import pytest

from solidworks_mcp.contracts import ResponseEnvelope
from solidworks_mcp.jobs import JobError
from solidworks_mcp.owned_leaf_deletion_tools_v2 import register_owned_leaf_deletion_tools


TOOLS=[('feature_prepare_leaf_deletion','feature.prepare_leaf_deletion',False),
       ('feature_delete_leaf','feature.delete_leaf',True)]


class FakeRuntime:
    def __init__(self):
        self.calls=[]
        self.error=None
        self.status='succeeded'
        self.context=dict(document_id='own',configuration='Основная',expected_revision='durable_revision')
        self.data=dict(verified=True,value=dict(deleted_feature_object_ids=['feat_'+'a'*32],
            preserved_sketch_object_id='feat_'+'b'*32,geometry_references_require_refresh=True))
        self.job_error=None

    async def read(self,request_id,operation,arguments,**kwargs):
        return self._dispatch(False,request_id,operation,arguments,kwargs)

    async def mutate(self,request_id,operation,arguments,**kwargs):
        return self._dispatch(True,request_id,operation,arguments,kwargs)

    def _dispatch(self,mutate,request_id,operation,arguments,kwargs):
        self.calls.append((mutate,request_id,operation,deepcopy(arguments),deepcopy(kwargs)))
        if self.error is not None: raise self.error
        return dict(status=self.status,operation_id='job_original',payload={'context':deepcopy(self.context)},
                    result=deepcopy(self.data),error=deepcopy(self.job_error))

    def cancel(self,*args): pytest.fail('Wait timeout must never cancel native work')


@pytest.fixture
def candidate():
    app,runtime,failures=FastMCP('owned-leaf-isolated'),FakeRuntime(),[]
    def response(**kwargs): return ResponseEnvelope(**kwargs)
    def failure(error):
        failures.append(error)
        return response(status='failed',operation_id=None,context={},data=None,
            error=dict(code=error.code if isinstance(error,JobError) else 'journal_unavailable',message=str(error)))
    register_owned_leaf_deletion_tools(app,runtime,response,failure)
    return NS(app=app,runtime=runtime,failures=failures)


def arguments(tool,**changes):
    result=dict(request_id='same_request',document_id='own',configuration='Основная',object_id='feat_'+'a'*32)
    if tool=='feature_delete_leaf': result['expected_revision']='full_revision'
    return {**result,**changes}


def call(candidate,tool,args):
    return asyncio.run(candidate.app.call_tool(tool,args))[1]


def test_registration_discovers_exact_two_explicit_read_write_schemas_without_runtime(candidate):
    assert asyncio.run(FastMCP('unregistered').list_tools())==[]
    by_name={tool.name:tool for tool in asyncio.run(candidate.app.list_tools())}
    assert set(by_name)=={tool for tool,_,_ in TOOLS}
    for name,_,mutates in TOOLS:
        tool=by_name[name]
        schema=tool.inputSchema
        required={'request_id','document_id','configuration','object_id'}
        if mutates: required.add('expected_revision')
        assert set(schema['required'])==required
        assert set(schema['properties'])==required|{'timeout_s'}
        for key in required:
            assert schema['properties'][key]['type']=='string'
            assert 'default' not in schema['properties'][key]
        wait=schema['properties']['timeout_s']
        assert wait['type']=='number' and wait['default']==10.
        assert wait['minimum']==0 and wait['maximum']==120
        assert tool.outputSchema['type']=='object'
        assert {'status','operation_id','data','error'}<=set(tool.outputSchema['required'])
        assert 'Installed native acceptance' in tool.description
        if mutates:
            assert 'preserve its original sketch' in tool.description
            assert 'timeout_s limits waiting, not COM' in tool.description
            assert 'No recursive deletion' in tool.description
        else:
            assert 'Read only' in tool.description and 'current' in tool.description
    assert not candidate.runtime.calls


@pytest.mark.parametrize('tool,operation,mutate',TOOLS)
@pytest.mark.parametrize('timeout',[None,0.,120.,0,120,.25])
def test_exact_domain_context_revision_and_default_or_boundary_wait_dispatch(candidate,tool,operation,mutate,timeout):
    args=arguments(tool)
    if timeout is not None: args['timeout_s']=timeout
    result=call(candidate,tool,args)
    domain_args={key:value for key,value in args.items() if key not in ('request_id','timeout_s')}
    assert candidate.runtime.calls==[(mutate,'same_request',operation,domain_args,
                                    {'timeout_s':10. if timeout is None else float(timeout)})]
    assert result['status']=='succeeded' and result['operation_id']=='job_original'
    assert result['context']==candidate.runtime.context and result['data']==candidate.runtime.data
    assert result['error'] is None and not candidate.failures


@pytest.mark.parametrize('tool,operation,mutate',TOOLS)
@pytest.mark.parametrize('invalid',[True,False,None,'10',-1.,120.0001,float('nan'),float('inf'),-float('inf'),[],{}])
def test_wait_requires_strict_finite_numeric_0_to_120_before_runtime(candidate,tool,operation,mutate,invalid):
    with pytest.raises(ToolError): call(candidate,tool,arguments(tool,timeout_s=invalid))
    assert not candidate.runtime.calls and not candidate.failures


@pytest.mark.parametrize('tool,operation,mutate',TOOLS)
@pytest.mark.parametrize('missing',['request_id','document_id','configuration','object_id'])
def test_explicit_scope_and_request_fields_have_no_defaults(candidate,tool,operation,mutate,missing):
    args=arguments(tool)
    args.pop(missing)
    with pytest.raises(ToolError): call(candidate,tool,args)
    assert not candidate.runtime.calls


@pytest.mark.parametrize('field',['request_id','document_id','configuration','object_id','expected_revision'])
@pytest.mark.parametrize('invalid',[None,1,True,[],{}])
def test_write_scope_and_revision_require_typed_strings_before_runtime(candidate,field,invalid):
    with pytest.raises(ToolError):
        call(candidate,'feature_delete_leaf',arguments('feature_delete_leaf',**{field:invalid}))
    assert not candidate.runtime.calls


def test_write_revision_cannot_be_omitted_or_substituted_by_a_prepare_call(candidate):
    args=arguments('feature_delete_leaf')
    args.pop('expected_revision')
    with pytest.raises(ToolError): call(candidate,'feature_delete_leaf',args)
    assert not candidate.runtime.calls


@pytest.mark.parametrize('tool,operation,mutate',TOOLS)
@pytest.mark.parametrize('status',['queued','running','unknown','failed','cancelled'])
def test_unfinished_unknown_or_failed_rows_forward_actual_envelope_once_without_cancel_or_retry(candidate,tool,operation,mutate,status):
    candidate.runtime.status=status
    candidate.runtime.data=None
    candidate.runtime.job_error=dict(code='native_unconfirmed',message='Application hold') if status=='unknown' else None
    result=call(candidate,tool,arguments(tool,timeout_s=0.))
    assert result['status']==status and result['operation_id']=='job_original'
    assert result['data'] is None and result['error']==candidate.runtime.job_error
    assert result['context']==candidate.runtime.context
    assert len(candidate.runtime.calls)==1 and not candidate.failures


@pytest.mark.parametrize('tool,operation,mutate',TOOLS)
def test_same_request_is_delegated_for_late_result_without_local_cache_or_retry(candidate,tool,operation,mutate):
    candidate.runtime.status='running'
    candidate.runtime.data=None
    args=arguments(tool,timeout_s=0.)
    first=call(candidate,tool,args)
    assert first['status']=='running'
    candidate.runtime.status='succeeded'
    candidate.runtime.data=dict(verified=True,late_native_receipt='actual')
    second=call(candidate,tool,args)
    assert second['status']=='succeeded' and second['operation_id']==first['operation_id']
    assert second['data']==candidate.runtime.data
    assert len(candidate.runtime.calls)==2 and candidate.runtime.calls[0]==candidate.runtime.calls[1]


@pytest.mark.parametrize('tool,operation,mutate',TOOLS)
def test_changed_request_payload_is_rejected_by_runtime_conflict_without_facade_retry(candidate,tool,operation,mutate):
    args=arguments(tool,timeout_s=0.)
    first=call(candidate,tool,args)
    assert call(candidate,tool,args)==first
    candidate.runtime.error=JobError('request_conflict','Same request has a different owned feature.')
    result=call(candidate,tool,{**args,'object_id':'feat_'+'c'*32})
    assert result['status']=='failed' and result['error']['code']=='request_conflict'
    assert len(candidate.runtime.calls)==3
    assert candidate.runtime.calls[-1][1]=='same_request'
    assert candidate.runtime.calls[-1][3]['object_id']=='feat_'+'c'*32


@pytest.mark.parametrize('tool,operation,mutate',TOOLS)
@pytest.mark.parametrize('error',[JobError('unsafe_scope','Original succeeded ownership required.'),
    sqlite3.OperationalError('Private journal unavailable'),sqlite3.IntegrityError('Ledger binding failed')])
def test_expected_domain_and_sqlite_errors_use_shared_failure_envelope_once(candidate,tool,operation,mutate,error):
    candidate.runtime.error=error
    result=call(candidate,tool,arguments(tool))
    assert result['status']=='failed' and result['operation_id'] is None
    assert result['data'] is None and candidate.failures==[error]
    assert len(candidate.runtime.calls)==1


@pytest.mark.parametrize('tool,operation,mutate',TOOLS)
def test_unexpected_error_is_not_fabricated_as_native_success_or_shared_known_refusal(candidate,tool,operation,mutate):
    candidate.runtime.error=RuntimeError('Unclassified internal failure')
    with pytest.raises(ToolError): call(candidate,tool,arguments(tool))
    assert len(candidate.runtime.calls)==1 and not candidate.failures
