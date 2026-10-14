"""Bounded STEP unit metadata validation; not a STEP geometry parser."""
import re


MAX_STEP_UNIT_BYTES = 4 * 1024 * 1024
MAX_UNIT_ENTITIES = 50000


def declared_step_length_unit(text):
    """Resolve every present unit context to one supported SI length unit.

    The caller supplies the complete bounded exchange text. Quoted strings and
    comments cannot contribute declarations. Conversion-based length units are
    explicitly unsupported, even when their base unit happens to be metric.
    """
    cleaned = re.sub(r"/\*[\s\S]*?\*/|'(?:''|[^'])*'", ' ', text)
    if "'" in cleaned or '/*' in cleaned or '*/' in cleaned or not cleaned.isascii():
        raise ValueError('Unterminated or unsupported STEP metadata syntax.')
    entities = {}
    for match in re.finditer(r'#([1-9][0-9]{0,17})\s*=\s*([^;]*);', cleaned):
        identifier, body = match.groups()
        if identifier in entities or len(entities) >= MAX_UNIT_ENTITIES:
            raise ValueError('Duplicate STEP entity or entity budget exceeded.')
        entities[identifier] = body
    units = []
    for body in entities.values():
        if not re.search(r'\bGLOBAL_UNIT_ASSIGNED_CONTEXT\b', body):
            continue
        contexts = re.findall(r'\bGLOBAL_UNIT_ASSIGNED_CONTEXT\s*\(\s*\(([^()]*)\)\s*\)', body)
        if len(contexts) != 1 or not re.fullmatch(
                r'\s*#[1-9][0-9]{0,17}\s*(?:,\s*#[1-9][0-9]{0,17}\s*)*', contexts[0]):
            raise ValueError('Unsupported STEP unit context.')
        references = re.findall(r'#([1-9][0-9]{0,17})', contexts[0])
        if len(set(references)) != len(references) or any(ref not in entities for ref in references):
            raise ValueError('Invalid STEP unit references.')
        lengths = [entities[ref] for ref in references
                   if re.search(r'\bLENGTH_UNIT\s*\(\s*\)', entities[ref])]
        if len(lengths) != 1 or re.search(r'\bCONVERSION_BASED_UNIT\b', lengths[0]):
            raise ValueError('No single supported STEP length unit.')
        declarations = re.findall(
            r'\bSI_UNIT\s*\(\s*(\$|\.[A-Z_]+\.)\s*,\s*(\.[A-Z_]+\.)\s*\)', lengths[0])
        if len(declarations) != 1 or declarations[0] not in (('.MILLI.', '.METRE.'), ('$', '.METRE.')):
            raise ValueError('Unsupported STEP SI length unit.')
        units.append('mm' if declarations[0][0] == '.MILLI.' else 'm')
    if not units or len(set(units)) != 1:
        raise ValueError('Missing or inconsistent STEP length contexts.')
    return units[0]
