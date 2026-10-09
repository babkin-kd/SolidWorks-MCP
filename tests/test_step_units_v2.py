"""STEP unit roles/references, native formatting, and bounded file validation."""
import pytest

from solidworks_mcp.exports_v2 import ExportOptions, validate_export_file
from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.step_units import MAX_STEP_UNIT_BYTES, declared_step_length_unit


def exchange(unit='SI_UNIT ( .MILLI., .METRE. )', *, extra='', context='((#236,#14,#174))'):
    return ('ISO-10303-21;\nHEADER;ENDSEC;\nDATA;'
            '#14=(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.));'
            '#174=(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT());'
            '#236 =( LENGTH_UNIT ( ) NAMED_UNIT ( * ) ' + unit + ' );'
            '#191=(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNIT_ASSIGNED_CONTEXT' + context +
            "REPRESENTATION_CONTEXT('NONE','WORKSPACE'));" + extra + '\nENDSEC;END-ISO-10303-21;')


@pytest.mark.parametrize('declaration,unit', [
    ('SI_UNIT(.MILLI.,.METRE.)', 'mm'),
    ('SI_UNIT ( .MILLI., .METRE. )', 'mm'),
    ('SI_UNIT\n(\t$ ,\n.METRE.\t)', 'm'),
    ('SI_UNIT /* formatter comment */ ( .MILLI., /* comment */ .METRE. )', 'mm'),
])
def test_realistic_unit_context_accepts_native_formatting(tmp_path, declaration, unit):
    path = tmp_path / 'Контрольная деталь.step'
    path.write_text(exchange(declaration), encoding='ascii')
    facts = validate_export_file(path, ExportOptions('step', path.name))
    assert facts['validation']['units'] == unit
    assert facts['validation']['units_embedded'] is True
    assert facts['bytes'] == path.stat().st_size


@pytest.mark.parametrize('declaration', ['SI_UNIT(.CENTI.,.METRE.)', 'SI_UNIT($,.FOOT.)',
    'SI_UNIT($,.RADIAN.)', "CONVERSION_BASED_UNIT('INCH',#300)"])
def test_unsupported_length_unit_is_not_inferred_from_metric_base(declaration):
    text = exchange(declaration, extra='#300=MEASURE_WITH_UNIT(LENGTH_MEASURE(25.4),#301);'
        '#301=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));')
    with pytest.raises(ValueError):
        declared_step_length_unit(text)


@pytest.mark.parametrize('context', ['((#14,#174))', '((#236,#999))', '((#236,#236,#14))',
    '(#236)', '((#0,#14))', '((#236,#237,#14))'])
def test_missing_ambiguous_or_invalid_length_references_rejected(context):
    text = exchange(context=context, extra='#237=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT($,.METRE.));')
    with pytest.raises(ValueError):
        declared_step_length_unit(text)


def test_conflicting_representation_contexts_rejected():
    text = exchange(extra='#237=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT($,.METRE.));'
        '#192=GLOBAL_UNIT_ASSIGNED_CONTEXT((#237,#14,#174));')
    with pytest.raises(ValueError):
        declared_step_length_unit(text)


def test_matching_representation_contexts_accepted():
    assert declared_step_length_unit(exchange(extra='#192=GLOBAL_UNIT_ASSIGNED_CONTEXT((#236,#14,#174));')) == 'mm'


def test_comments_and_strings_cannot_supply_or_change_unit_declarations():
    text = exchange(extra="/* #237=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT($,.METRE.)); */"
        "#300=DESCRIPTIVE_REPRESENTATION_ITEM('SI_UNIT($,.METRE.)', 'escaped '' quote');")
    assert declared_step_length_unit(text) == 'mm'
    with pytest.raises(ValueError):
        declared_step_length_unit("/* " + exchange() + " */\n#1=LABEL('" + exchange().replace("'", "''") + "');")


@pytest.mark.parametrize('ending', ["'unterminated", '/* unterminated'])
def test_unterminated_tokens_rejected(ending):
    with pytest.raises(ValueError):
        declared_step_length_unit(exchange(extra=ending))


def test_duplicate_entity_identifier_rejected():
    with pytest.raises(ValueError):
        declared_step_length_unit(exchange(extra='#236=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT($,.METRE.));'))


def test_entity_budget_is_enforced(monkeypatch):
    import solidworks_mcp.step_units as parser
    monkeypatch.setattr(parser, 'MAX_UNIT_ENTITIES', 2)
    with pytest.raises(ValueError):
        declared_step_length_unit(exchange())


def test_file_larger_than_unit_validation_limit_rejected(tmp_path):
    path = tmp_path / 'Большой файл.step'
    with path.open('wb') as stream:
        stream.write(exchange().encode('ascii'))
        stream.truncate(MAX_STEP_UNIT_BYTES + 1)
    with pytest.raises(ExecutionFailure) as exc:
        validate_export_file(path, ExportOptions('step', path.name))
    assert exc.value.code == 'step_unit_validation_limit'


@pytest.mark.parametrize('encoding', ['utf8', 'cp1251'])
def test_native_nonascii_quoted_names_do_not_change_unit_syntax(tmp_path, encoding):
    path = tmp_path / 'Русская деталь.step'
    raw = exchange(extra="#300=DESCRIPTIVE_REPRESENTATION_ITEM('Контрольная деталь','имя');").encode(encoding)
    path.write_bytes(raw)
    facts = validate_export_file(path, ExportOptions('step', path.name))
    assert facts['validation']['units'] == 'mm'
    assert path.read_bytes() == raw


def test_nonascii_outside_opaque_strings_is_not_a_unit_identifier():
    with pytest.raises(ValueError):
        declared_step_length_unit(exchange().replace('LENGTH_UNIT', 'ЛENGTH_UNIT'))
