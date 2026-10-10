"""Closed equation/reference context for the ongoing full deletion-impact work."""

from copy import deepcopy
import hashlib

from .cad_deletion_context import SCOPE as CAPTURE_SCOPE, EXTERNAL_FIELDS, MAX_TEXT_TOTAL, _count, _text, _boolean, _integer
from .documents import rejected
from .jobs import _json
from .feature_dependency_graph import FeatureGraphRead
from .feature_external_reference_bindings import feature_reference_semantics, enforce_combined_text_budget, outgoing_bindings

SCOPE = 'part_feature_deletion_context_v3'
UNVERIFIED = ('equation_dimension_feature_bindings', 'equation_configuration_membership',
              'other_configuration_feature_states', 'annotations_and_drawings',
              'incoming_external_document_references', 'external_reference_native_feature_bindings',
              'native_deletion_effects_and_restoration')


def _keys(value, keys):
    if (type(value) is not dict or any(type(key) is not str for key in value)
            or set(value) != set(keys)):
        raise rejected('feature_context_capture_invalid', 'Native context schema is incomplete or unexpected.')


def context_semantics(value):
    """Require complete bounded native rows; copy scalars before a second read."""
    _keys(value, ('scope', 'equations', 'external_references', 'auxiliary_references'))
    if type(value['scope']) is not str or value['scope'] != CAPTURE_SCOPE:
        raise rejected('feature_context_capture_invalid', 'Wrong native feature context scope.')
    eq = value['equations']
    _keys(eq, ('enumerated_count', 'disabled_count', 'disabled_definitions_captured', 'properties', 'rows'))
    count, disabled = _count(eq['enumerated_count']), _count(eq['disabled_count'])
    _keys(eq['properties'], ('linked_to_file', 'file_path', 'automatic_rebuild', 'automatic_solve_order', 'angular_equation_units'))
    for field in ('linked_to_file', 'automatic_rebuild', 'automatic_solve_order'):
        _boolean(eq['properties'][field])
    _integer(eq['properties']['angular_equation_units'])
    text_work = len(_text(eq['properties']['file_path']))
    if type(eq['rows']) is not list or len(eq['rows']) != count:
        raise rejected('feature_context_capture_invalid', 'Equation rows and count disagree.')
    for index, row in enumerate(eq['rows']):
        _keys(row, ('row_index', 'expression', 'disabled', 'global_variable', 'configuration_option'))
        if type(row['row_index']) is not int or row['row_index'] != index:
            raise rejected('feature_context_capture_invalid', 'Invalid native equation row index.')
        text_work += len(_text(row['expression']))
        _boolean(row['disabled'])
        _boolean(row['global_variable'])
        _integer(row['configuration_option'])
    if type(eq['disabled_definitions_captured']) is not bool or eq['disabled_definitions_captured'] is not (disabled == 0):
        raise rejected('feature_context_capture_invalid', 'Unavailable disabled definitions cannot be certified as captured.')
    for section, fields in (('external_references', EXTERNAL_FIELDS), ('auxiliary_references', ('feature_name', 'file_path'))):
        table = value[section]
        _keys(table, ('count', 'rows'))
        row_count = _count(table['count'])
        if type(table['rows']) is not list or len(table['rows']) != row_count:
            raise rejected('feature_context_capture_invalid', 'Native reference count and rows disagree.')
        for index, row in enumerate(table['rows']):
            _keys(row, ('row_index', *fields))
            if type(row['row_index']) is not int or row['row_index'] != index:
                raise rejected('feature_context_capture_invalid', 'Invalid reference row index.')
            for field in fields:
                if field in ('status', 'configuration_option'):
                    _integer(row[field])
                else:
                    text_work += len(_text(row[field]))
    if text_work > MAX_TEXT_TOTAL:
        raise rejected('feature_context_budget_exceeded', 'Equation/reference text budget exceeded.')
    return deepcopy(value)


def deletion_context(catalog, document_id, configuration):
    adapter = catalog.adapter
    first = catalog._state(document_id, configuration)
    entry, _, native, semantic, _, _ = first
    frame = FeatureGraphRead(catalog, document_id, configuration, first)
    context = context_semantics(adapter.feature_deletion_context(entry.model))
    references = feature_reference_semantics(adapter.feature_external_references(native), semantic['features'])
    enforce_combined_text_budget(context, references)
    closing_context = context_semantics(adapter.feature_deletion_context(entry.model))
    closing_references = feature_reference_semantics(adapter.feature_external_references(native), semantic['features'])
    enforce_combined_text_budget(closing_context, closing_references)
    frame.capture_second_relations()
    last = catalog._state(document_id, configuration)
    if context != closing_context or references != closing_references:
        raise rejected('document_changed_during_read', 'Nonstructural feature context changed during collection.')
    graph = frame.close(last)
    # The frame has finished every COM check; only typed pure transformations follow.
    bindings = outgoing_bindings(context, references, graph)
    revision = 'rev_' + hashlib.sha256(_json({'scope': SCOPE, 'graph_revision': graph['revision'],
                                            'context': context, 'feature_references': references, 'bindings': bindings}).encode('utf8')).hexdigest()
    blockers = [{'code': 'unverified_impact_scope', 'scope': scope} for scope in UNVERIFIED
                if scope != 'external_reference_native_feature_bindings' or not bindings['complete']]
    blockers.extend(bindings['blockers'])
    if context['equations']['disabled_count']:
        blockers.append({'code': 'disabled_equation_definitions_unavailable',
                         'reported_disabled_count': context['equations']['disabled_count']})
    return {'document_id': document_id, 'configuration': configuration, 'revision_scope': SCOPE,
            'revision': revision, 'dependency_graph': graph, 'native_context': context,
            'native_feature_external_references': references, 'outgoing_reference_bindings': bindings,
            'native_inventory_capture_closed': True, 'native_inventory_read_count': 2,
            'feature_tree_read_count': 2,
            'row_indices_and_names_are_writable_anchors': False,
            'blockers': blockers,
            'deletion_impact_complete': False, 'deletion_authorized': False}
