"""Pure coverage of the deliberately restricted native-fixture comparator."""
import ast
from pathlib import Path

import pytest


def fixture_signature(name="numeric_global_fixture_signature"):
    source = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_isolated_part_copy.py'
    tree = ast.parse(source.read_text(encoding='utf8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace[function.name]


def test_serialized_fixture_whitespace_does_not_change_quoted_name_or_integer():
    signature = fixture_signature()
    assert signature('"Величина для копирования" = 3') == signature('"Величина для копирования"= 3')
    assert signature('"Отключённая величина"\t=\t5') == ('Отключённая величина', 5)
    assert signature('"А  Б"=3') != signature('"А Б"=3')
    assert signature('"А Б"=3') != signature('"А Б"=5')


@pytest.mark.parametrize('expression', [
    '"D1@Эскиз"=3', '"А"=3mm', '"А"=3.0', '"А"=3 + 0', '"А"=-3',
    '"А"="Б"', '"А"=3=3', '"А\nБ"=3', '"А"\n=3', '""=3', '', None,
    '"' + 'А' * 121 + '"=3', '"А"=' + '3' * 11,
])
def test_unsupported_general_equations_never_pass_the_fixture_oracle(expression):
    with pytest.raises(ValueError):
        fixture_signature()(expression)

@pytest.mark.parametrize('status,invalid,deleted', [(1, True, False), (4, False, True), (5, True, True)])
def test_invalid_reference_is_never_misreported_as_native_deleted(status, invalid, deleted):
    observe = fixture_signature('unavailable_copy_reference_observation')
    result = observe(True, status)
    assert result['persistent_reference_status'] == status
    assert result['native_reference_invalid_bit_verified'] is invalid
    assert result['native_reference_deleted_bit_verified'] is deleted
    assert result['persistent_reference_unavailable_verified'] is True


@pytest.mark.parametrize('is_null,status', [(False, 4), (None, 1), (1, 1), (True, 0),
                                         (True, 2), (True, 6), (True, 8), (True, -1),
                                         (True, True), (True, '1')])
def test_available_suppressed_unknown_and_untyped_references_are_not_deletion_proof(is_null, status):
    with pytest.raises(ValueError):
        fixture_signature('unavailable_copy_reference_observation')(is_null, status)
