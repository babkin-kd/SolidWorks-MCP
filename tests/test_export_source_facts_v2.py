"""Pure checks of independent verifier facts; no CAD/package imports."""

import ast
from copy import deepcopy
import math
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_export_operations.py'
tree = ast.parse(SCRIPT.read_text(encoding='utf8'), filename=str(SCRIPT))
nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
         and node.name == 'assert_owned_source_facts_unchanged']
assert len(nodes) == 1
assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(nodes[0]))
namespace = {'math': math}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCRIPT), 'exec'), namespace)
compare = namespace['assert_owned_source_facts_unchanged']

# Artificial readings reproduce the adjacent-double pattern from the private
# dev13 owned-fixture diagnostic; they do not constitute new native evidence.
MASS = (-0.0225, -0.027, 0.0035, 2.1e-7, 0.000214, 2.1e-7,
        1.4874999999999912e-12, 1.295e-12, 1.0674999999999914e-12,
        -2.550473555371837e-28, 2.067951531382568e-29, -3.515517603350368e-28)
SOURCE = {'title': 'Контрольная часть', 'path': '', 'stamp': 180, 'save_flag': True,
          'configurations': ('Основная',), 'active_configuration': 'Основная',
          'blocking_state': 0, 'selection_count': 0,
          'native_extrema_m': {'min': [-.025, -.03, 0.], 'max': [-.02, -.024, .007]},
          'features': ((8, 'Контрольный блок', 'Boss', (0, False)),), 'body_mass_facts': MASS}


def changed_mass(index, value):
    result = deepcopy(SOURCE)
    values = list(result['body_mass_facts'])
    values[index] = value
    result['body_mass_facts'] = tuple(values)
    return result


@pytest.mark.parametrize('index', range(12))
def test_adjacent_float_is_accepted_without_rounding_stored_readings(index):
    after = changed_mass(index, math.nextafter(MASS[index], math.inf))
    saved_before, saved_after = deepcopy(SOURCE), deepcopy(after)
    proof = compare(SOURCE, after)
    assert SOURCE == saved_before and after == saved_after and after != SOURCE
    assert proof['approximate_mass_facts_check'] is True
    assert proof['computed_mass_facts_used_for_geometry_revision'] is False
    assert proof['independent_nonmass_source_facts_exact'] is True
    assert proof['independent_computed_mass_raw_readings'] == {
        'before': list(MASS), 'after': list(after['body_mass_facts'])}
    assert proof['computed_mass_facts_tolerances'] == {
        'relative_tolerance': 1e-12, 'centroid_volume_area_mass_absolute_tolerance': 0.,
        'inertia_absolute_tolerance': 1e-25, 'mass_fact_count': 12, 'raw_readings_rounded': False}


@pytest.mark.parametrize('index', range(12))
def test_material_mass_fact_change_rejected(index):
    # Off-diagonal values are near zero: changes above absolute tolerance must
    # reject too, independently of the small relative reference magnitude.
    value = MASS[index] * 1.000001 if index < 9 else MASS[index] + 1e-24
    with pytest.raises(AssertionError, match='beyond the verifier tolerance'):
        compare(SOURCE, changed_mass(index, value))


def test_near_zero_inertia_cancellation_has_only_explicit_absolute_allowance():
    assert compare(SOURCE, changed_mass(9, MASS[9] + 5e-26))['approximate_mass_facts_check'] is True
    with pytest.raises(AssertionError):
        compare(SOURCE, changed_mass(9, MASS[9] + 2e-25))


def test_zero_centroid_has_no_absolute_tolerance():
    before = changed_mass(0, 0.)
    assert compare(before, deepcopy(before))['approximate_mass_facts_check'] is True
    with pytest.raises(AssertionError):
        compare(before, changed_mass(0, 1e-30))


@pytest.mark.parametrize('index', [0, 3, 6, 11])
@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), True, 1, '1.'])
def test_invalid_or_nonfinite_native_mass_data_rejected_on_either_side(index, value):
    malformed = changed_mass(index, value)
    for before, after in ((SOURCE, malformed), (malformed, SOURCE)):
        with pytest.raises(AssertionError, match='finite native doubles'):
            compare(before, after)


@pytest.mark.parametrize('values', [(), MASS[:-1], MASS + (1.,), None, 'twelvevalues'])
def test_wrong_mass_shape_rejected_on_either_side(values):
    malformed = {**SOURCE, 'body_mass_facts': values}
    for before, after in ((SOURCE, malformed), (malformed, SOURCE)):
        with pytest.raises(AssertionError, match='12 native mass doubles'):
            compare(before, after)


@pytest.mark.parametrize('key,value', [
    ('title', 'Переименованная часть'), ('path', 'Другой файл.sldprt'), ('stamp', 181),
    ('save_flag', False), ('configurations', ('Основная', 'Вариант')),
    ('active_configuration', 'Вариант'), ('blocking_state', 2), ('selection_count', 1),
    ('features', ((8, 'Контрольный блок', 'Boss', (0, True)),)),
    ('native_extrema_m', {'min': [-.025, -.03, 0.],
                         'max': [-.02, -.024, math.nextafter(.007, math.inf)]}),
])
def test_every_nonmass_fact_remains_exact_including_raw_feature_warning_and_extrema(key, value):
    with pytest.raises(AssertionError, match='nonmass source facts changed'):
        compare(SOURCE, {**SOURCE, key: value})


def test_missing_or_added_source_fields_rejected():
    for missing in SOURCE:
        after = {key: value for key, value in SOURCE.items() if key != missing}
        with pytest.raises(AssertionError, match='fact keys changed'):
            compare(SOURCE, after)
    with pytest.raises(AssertionError, match='fact keys changed'):
        compare(SOURCE, {**SOURCE, 'unknown': 0})
    without_mass = {key: value for key, value in SOURCE.items() if key != 'body_mass_facts'}
    with pytest.raises(AssertionError, match='mass facts are missing'):
        compare(without_mass, deepcopy(without_mass))
