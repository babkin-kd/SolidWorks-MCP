"""Verify public harness dispatch coverage without importing or connecting CAD."""

import ast
from pathlib import Path
from types import SimpleNamespace as NS


def test_every_public_harness_operation_is_tracked_before_sdk_lifetime():
    script = Path(__file__).resolve().parents[1]/'scripts/verify_part_revolve_mcp.py'
    tree = ast.parse(script.read_text(encoding='utf8'))
    assignment = next(node for node in tree.body if isinstance(node,ast.Assign)
                      and any(isinstance(target,ast.Name) and target.id=='TOOL_SPECS' for target in node.targets))
    namespace = {'PART_SPECS':{'feature_list':object()},
                 'ToolSpec':lambda operation,mutates,**kw:NS(operation=operation,mutates=mutates,**kw)}
    exec(compile(ast.Module(body=[assignment],type_ignores=[]),str(script),'exec'),namespace)
    specs = namespace['TOOL_SPECS']
    called = {node.args[1].value for node in ast.walk(tree)
              if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='call'
              and len(node.args)>=2 and isinstance(node.args[1],ast.Constant)}
    assert called <= specs.keys()
    assert {'document_list_templates','document_prepare_create_part','document_create_part',
            'part_prepare_base_revolve','part_create_base_revolve'} <= called
    create = specs['document_create_part']
    assert create.mutates and create.operation == 'document.create_part'
    assert create.argument_map == {'application_id':'document_id'}
    assert create.constant_args == {'configuration':''}
    assert create.prewrite_failure_codes == frozenset({'stale_revision'})
