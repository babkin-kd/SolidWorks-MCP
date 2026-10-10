"""AST checks for ownership/job tracking and engineering proof; no CAD imports."""

import ast
from pathlib import Path
from types import SimpleNamespace as NS


ROOT=Path(__file__).resolve().parents[1]


def test_public_hole_harness_tracks_all_literal_calls_before_sdk_dispatch():
    script=ROOT/'scripts/verify_part_hole_mcp.py'
    tree=ast.parse(script.read_text(encoding='utf8'))
    assignment=next(node for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='TOOL_SPECS' for target in node.targets))
    namespace={'PART_SPECS':{'feature_list':object(),'part_prepare_base_extrusion':object(),
        'part_create_base_extrusion':object()},'ToolSpec':lambda op,mutates,**kw:NS(operation=op,mutates=mutates,**kw)}
    exec(compile(ast.Module(body=[assignment],type_ignores=[]),str(script),'exec'),namespace)
    specs=namespace['TOOL_SPECS']
    called={node.args[1].value for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Name) and node.func.id=='call' and len(node.args)>=2
        and isinstance(node.args[1],ast.Constant)}
    assert called<=specs.keys()
    assert {'document_create_part','part_prepare_base_extrusion','part_create_base_extrusion',
        'part_prepare_through_hole','part_create_through_hole'}<=called
    create=specs['part_create_through_hole']
    assert create.operation=='part.create_through_hole' and create.mutates is True
    assert create.float_arguments==frozenset({'centre_x_mm','centre_y_mm','diameter_mm'})
    assert create.argument_defaults=={'sketch_name':'Эскиз отверстия','feature_name':'Сквозное отверстие'}
    assert create.prewrite_failure_codes==frozenset({'stale_revision'})
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
