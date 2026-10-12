"""Public L3-P1 supervisor contracts and exact fixture-dimension selection.

No CAD connection or model modification. A dimension is chosen from fully
captured supported rows, never resolved by a guessed name or ordinal.
"""
import math
from verifier_lifecycle import ToolSpec


SPECS = {
    'document_list': ToolSpec('document.list', False),
    'document_get': ToolSpec('document.get', False),
    'document_prepare_activate_part_native': ToolSpec('document.prepare_activate_part_native', False),
    'document_activate_part_native': ToolSpec('document.activate_part_native', True,
        prewrite_failure_codes=frozenset({'stale_revision'})),
    'document_prepare_first_save_native': ToolSpec('document.prepare_first_save_native', False),
    'document_first_save_native': ToolSpec('document.first_save_native', True,
        prewrite_failure_codes=frozenset({'stale_revision', 'first_save_destination_exists'})),
    'document_prepare_close_native': ToolSpec('document.prepare_close_native', False,
        argument_defaults=dict(active_after_document_id='', allowed_hidden_document_ids=[])),
    'document_close_native': ToolSpec('document.close_native', True,
        argument_defaults=dict(active_after_document_id='', allowed_hidden_document_ids=[]),
        prewrite_failure_codes=frozenset({'stale_revision'})),
    'document_prepare_open_native': ToolSpec('document.prepare_open_native', False,
        argument_defaults={'read_only': False}),
    'document_open_native': ToolSpec('document.open_native', True,
        argument_defaults={'read_only': False}, prewrite_failure_codes=frozenset({'stale_revision'})),
    'document_prepare_save_native': ToolSpec('document.prepare_save_native', False),
    'document_save_native': ToolSpec('document.save_native', True,
        prewrite_failure_codes=frozenset({'stale_revision'})),
    'dimension_list': ToolSpec('dimension.list', False, argument_defaults={'limit': 100, 'cursor': ''}),
    'dimension_get': ToolSpec('dimension.get', False),
    'dimension_set_value': ToolSpec('dimension.set_value', True, float_arguments=frozenset({'value'}),
        prewrite_failure_codes=frozenset({'object_reference_not_found', 'dimension_unit_mismatch',
            'invalid_dimension_unit', 'unsupported_signed_dimension', 'dimension_not_writable',
            'document_not_active', 'stale_revision'})),
}


def fixture_depth_dimension(listed, configuration, expected_mm):
    """Require one current writable base length, distinct from sketch dimensions."""
    if (type(listed) is not dict or listed.get('configuration') != configuration
            or listed.get('next_cursor') is not None or type(listed.get('total_count')) is not int
            or listed['total_count'] != 3 or type(listed.get('items')) is not list or len(listed['items']) != 3):
        raise ValueError('Depth selection requires the complete current three-dimension fixture capture.')
    found = []
    for row in listed['items']:
        if (type(row) is not dict or row.get('unit') != 'mm' or type(row.get('owner')) is not dict
                or row['owner'].get('feature_type') not in ('Boss', 'Extrusion')
                or row.get('write_blockers') != [] or row.get('persistent_reference_supported') is not True
                or type(row.get('object_id')) is not str or not row['object_id']):
            continue
        actual = row.get('values', {}).get(configuration)
        if type(actual) in (float, int) and math.isfinite(actual) and math.isclose(actual, expected_mm, rel_tol=0., abs_tol=1e-8):
            found.append(row)
    if len(found) != 1:
        raise ValueError('No unique captured writable base depth; never use a name or ordinal fallback.')
    return found[0]
