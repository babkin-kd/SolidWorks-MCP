"""The verifier must never serialize or stringify live COM identities."""
import ast
import json
from pathlib import Path

import pytest


def projected_rows():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / 'scripts/verify_native_first_save_rejections.py').read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'owned_document_rows')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'owned_document_projection', 'exec'), namespace)
    return namespace[function.name]


class NativeDoc:
    def __init__(self, kind=1):
        self.kind = kind
    def GetTitle(self):return 'Контрольная деталь'
    def GetPathName(self):return ''
    def GetType(self):return self.kind
    @property
    def _oleobj_(self):
        raise AssertionError('Canonical COM identity must stay outside the JSON projection.')


def test_scalar_projection_does_not_query_canonical_com_and_is_json_serializable():
    rows = projected_rows()([NativeDoc()])
    assert json.loads(json.dumps(rows)) == [{'title': 'Контрольная деталь', 'path': '', 'type': 1}]


@pytest.mark.parametrize('bad_kind', [True, None, object(), 0, 4])
def test_untyped_native_document_kind_cannot_poison_the_report(bad_kind):
    with pytest.raises(ValueError):
        projected_rows()([NativeDoc(bad_kind)])


def test_retired_handles_are_not_queried_after_owned_list_is_empty():
    assert projected_rows()([]) == []
