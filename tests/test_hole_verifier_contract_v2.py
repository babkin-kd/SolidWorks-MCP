"""AST checks for ownership/job tracking and engineering proof; no CAD imports."""

import ast
from pathlib import Path
from types import SimpleNamespace as NS
from copy import deepcopy

import pytest


ROOT=Path(__file__).resolve().parents[1]


def test_hole_editor_prewrite_reject_may_precede_checkpoint():
    tree=ast.parse((ROOT/'scripts/verify_part_hole.py').read_text(encoding='utf8'))
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='prewrite_rejection')
    namespace={}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'hole_prewrite','exec'),namespace)
    check=namespace['prewrite_rejection']
    job={'status':'failed','error':{'code':'hole_outside_material','requires_reconciliation':False}}
    assert check(job,'hole_outside_material')
    assert check({**job,'mutation':{'phase':'not_started'}},'hole_outside_material')
    for phase in ('prepared','applied','committed','unknown','rolled_back'):
        assert not check({**job,'mutation':{'phase':phase}},'hole_outside_material')
    assert not check({**job,'status':'unknown'},'hole_outside_material')
    assert not check({**job,'error':{**job['error'],'requires_reconciliation':True}},'hole_outside_material')
    assert not check(job,'stale_revision')


def internal_record():
    from test_verifier_fixture_cleanup_v2 import utility
    tree=ast.parse((ROOT/'scripts/verify_part_hole.py').read_text(encoding='utf8'))
    function=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='record')
    namespace={'report':{'cases':[]},'catalog':NS(receipts={}),
        'persist':lambda:None,'gate':NS(can_cleanup=lambda:True),'sw':NS(CommandInProgress=False),
        'own_flag':False,'assert_non_stl_preferences':lambda *args:None,'application_preferences':lambda _:None,
        'preferences':{},'untouched_busy_guard':utility['untouched_busy_guard']}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'hole_record','exec'),namespace)
    return namespace


def test_native_record_distinguishes_unacquired_busy_flag_from_released_owned_flag():
    from test_verifier_fixture_cleanup_v2 import terminal
    from test_verifier_application_guard_scopes_v2 import model_guard,busy_guard
    namespace=internal_record()
    busy=terminal('failed','not_started'); busy['error']['code']='application_busy'
    busy['mutation']['verification']['evidence']={'execution_guard':busy_guard(),'native_mutation_started':False}
    namespace['record']('existing_command_flag_not_borrowed',busy,'failed')
    complete=terminal(); complete['mutation']['verification']['evidence']['execution_guard']=model_guard()
    namespace['record']('plate_in_server_created_document_40_20_10',complete)
    assert len(namespace['report']['cases'])==2
    wrong=deepcopy(busy); wrong['mutation']['verification']['evidence']['execution_guard']['acquired']=True
    with pytest.raises(AssertionError): namespace['record']('existing_command_flag_not_borrowed',wrong,'failed')
    wrong=deepcopy(complete); wrong['mutation']['verification']['evidence']['execution_guard']['released']=False
    with pytest.raises(AssertionError): namespace['record']('plate_in_server_created_document_40_20_10',wrong)


def test_public_hole_harness_tracks_all_literal_calls_before_sdk_dispatch():
    script=ROOT/'scripts/verify_part_hole_mcp.py'
    tree=ast.parse(script.read_text(encoding='utf8'))
    assignment=next(node for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='TOOL_SPECS' for target in node.targets))
    namespace={'PART_SPECS':{'feature_list':object(),'part_prepare_base_extrusion':object(),
        'part_create_base_extrusion':object()},'ToolSpec':lambda op,mutates,**kw:NS(operation=op,mutates=mutates,**kw)}
    helper=ast.parse((ROOT/'scripts/verifier_part_pattern_mcp.py').read_text(encoding='utf8'))
    helper_assignment=next(node for node in helper.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='TOOL_SPECS' for target in node.targets))
    exec(compile(ast.Module(body=[helper_assignment],type_ignores=[]),'pattern_specs','exec'),namespace)
    namespace['PATTERN_SPECS']=namespace['TOOL_SPECS']
    fillet=ast.parse((ROOT/'scripts/verifier_part_fillet_mcp.py').read_text(encoding='utf8'))
    fillet_assignment=next(node for node in fillet.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='TOOL_SPECS' for target in node.targets))
    exec(compile(ast.Module(body=[fillet_assignment],type_ignores=[]),'fillet_specs','exec'),namespace)
    namespace['FILLET_SPECS']=namespace['TOOL_SPECS']
    exec(compile(ast.Module(body=[assignment],type_ignores=[]),str(script),'exec'),namespace)
    specs=namespace['TOOL_SPECS']
    called={node.args[1].value for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Name) and node.func.id=='call' and len(node.args)>=2
        and isinstance(node.args[1],ast.Constant)}
    called|={node.args[1].value for node in ast.walk(helper) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Name) and node.func.id=='call' and len(node.args)>=2
        and isinstance(node.args[1],ast.Constant)}
    assert called<=specs.keys()
    fillet_called={node.args[1].value for node in ast.walk(fillet) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Name) and node.func.id=='call' and len(node.args)>=2
        and isinstance(node.args[1],ast.Constant)}
    assert fillet_called<=specs.keys()
    assert specs['part_create_edge_fillet'].argument_defaults=={'feature_name':'Скругление ребра'}
    assert specs['part_create_edge_fillet'].float_arguments==frozenset({'radius_mm'})
    assert specs['body_list'].constant_args=={'kind':'body'}
    assert specs['body_list'].argument_defaults=={'body_type':'all','limit':100,'cursor':''}
    assert specs['edge_list'].constant_args=={'kind':'edge'}
    assert specs['edge_list'].argument_defaults=={'limit':100,'cursor':''}
    assert specs['part_create_linear_hole_pattern'].argument_defaults=={'feature_name':'Линейный массив отверстий'}
    assert {'document_create_part','part_prepare_base_extrusion','part_create_base_extrusion',
        'part_prepare_through_hole','part_create_through_hole'}<=called
    create=specs['part_create_through_hole']
    assert create.operation=='part.create_through_hole' and create.mutates is True
    assert create.float_arguments==frozenset({'centre_x_mm','centre_y_mm','diameter_mm'})
    assert create.argument_defaults=={'sketch_name':'Эскиз отверстия','feature_name':'Сквозное отверстие'}
    assert create.prewrite_failure_codes==frozenset({'stale_revision'})
    edit=specs['part_set_hole_dimension']
    assert edit.operation=='part.set_hole_dimension' and edit.mutates is True
    assert edit.float_arguments==frozenset({'value_mm'})
    assert edit.prewrite_failure_codes==frozenset({'stale_revision'})
    assert specs['dimension_list'].argument_defaults=={'limit':100,'cursor':''}
    document=specs['document_create_part']
    assert document.argument_map=={'application_id':'document_id'} and document.constant_args=={'configuration':''}


def test_both_hole_harnesses_require_native_volume_area_and_full_root_census():
    for suffix in ('','_mcp'):
        text=(ROOT/f'scripts/verify_part_hole{suffix}.py').read_text(encoding='utf8')
        tree=ast.parse(text)
        attributes={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
        assert {'GetMassProperties','GetVertexCount','GetEdgeCount','GetFaceCount'}<=attributes
        assert 'math.pi*3.**2*10.' in text and 'math.pi*3.*10.' in text
        assert 'native_circular_through_hole_d6_x10_y10' in text
        assert '7500.' not in text and '2700.' not in text
        assert 'fixtures_closed' in text and 'gate.can_cleanup()' in text
