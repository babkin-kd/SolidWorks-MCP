"""A retained terminal verifier must pump its STA; no native process is run."""
import ast
from pathlib import Path


def test_retained_unknown_loop_services_messages_without_dispatching_another_cad_call():
    path=Path(__file__).resolve().parents[1]/'scripts/verify_rectangle_stages_positive.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    loops=[n for n in ast.walk(tree) if isinstance(n,ast.While) and isinstance(n.test,ast.Constant) and n.test.value is True]
    assert len(loops)==1
    calls=[n for n in ast.walk(loops[0]) if isinstance(n,ast.Call)]
    assert [(n.func.value.id,n.func.attr) for n in calls if isinstance(n.func,ast.Attribute)]==[
        ('pythoncom','PumpWaitingMessages'),('time','sleep')]
    assert len(calls)==2
