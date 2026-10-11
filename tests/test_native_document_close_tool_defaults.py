"""Verifier payload defaults must equal the real facade's durable arguments."""
import ast,asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest
from solidworks_mcp.native_document_close_tools_v2 import register_native_document_close_tools
from solidworks_mcp.server_v2 import response,failure
from test_verifier_lifecycle import helper


def specs():
    path=Path(__file__).resolve().parents[1]/'scripts/verify_native_document_close.py'
    tree=ast.parse(path.read_text(encoding='utf8'))
    assignment=next(node for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='SPECS' for target in node.targets))
    namespace=dict(ToolSpec=helper.ToolSpec)
    exec(compile(ast.Module(body=[assignment],type_ignores=[]),str(path),'exec'),namespace)
    return namespace['SPECS']


@pytest.mark.parametrize('mutate',[False,True])
@pytest.mark.parametrize('explicit',[False,True])
def test_actual_facade_and_supervisor_payload_match_defaults_and_explicit_policy(mutate,explicit):
    functions={};captured=[]
    class App:
        def tool(self):
            def register(function):functions[function.__name__]=function;return function
            return register
    async def dispatch(request_id,operation,arguments,timeout_s):
        captured.append((request_id,operation,arguments))
        return dict(status='succeeded',operation_id='op',payload={'context':{}},result={},error=None)
    runtime=SimpleNamespace(read=dispatch,mutate=dispatch)
    register_native_document_close_tools(App(),runtime,response,failure)
    tool='document_close_native' if mutate else 'document_prepare_close_native'
    args=dict(request_id='req',document_id='doc_target',configuration='Основная')
    if mutate:args['expected_revision']='rev_exact'
    if explicit:args.update(active_after_document_id='doc_chosen',allowed_hidden_document_ids=['doc_hidden'])
    asyncio.run(functions[tool](**args))
    expected=specs()[tool].payload(args)
    assert captured[0][2]==expected['arguments'] and expected['mutates'] is mutate
    assert expected['arguments']['active_after_document_id']==('doc_chosen' if explicit else '')
    assert expected['arguments']['allowed_hidden_document_ids']==(['doc_hidden'] if explicit else [])
