"""Closed per-feature reference inventories and explicit outgoing bindings.

Native IDs are verified census hints, not writable references. Matching native
records preserves multiplicity and reports ambiguity instead of picking a name.
"""
from collections import defaultdict
from copy import deepcopy

from .cad_deletion_context import EXTERNAL_FIELDS, MAX_TEXT_TOTAL, _count, _integer, _text
from .documents import rejected

CAPTURE_SCOPE = 'native_feature_external_references_v1'
SCOPE = 'part_outgoing_external_reference_bindings_v1'


def _keys(value, fields):
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != set(fields):
        raise rejected('feature_context_capture_invalid', 'Invalid per-feature reference schema.')


def feature_reference_semantics(value, feature_rows):
    _keys(value, ('scope', 'feature_count', 'total_reference_rows', 'features'))
    if type(value['scope']) is not str or value['scope'] != CAPTURE_SCOPE:
        raise rejected('feature_context_capture_invalid', 'Wrong per-feature reference scope.')
    count = _count(value['feature_count'])
    total = _count(value['total_reference_rows'])
    if type(value['features']) is not list or len(value['features']) != count or count != len(feature_rows):
        raise rejected('feature_context_capture_invalid', 'Per-feature census does not cover the feature tree.')
    seen, observed, text_work = set(), 0, 0
    for table, feature in zip(value['features'], feature_rows):
        _keys(table, ('native_id', 'count', 'rows'))
        native_id = _integer(table['native_id'])
        if native_id in seen or native_id != feature['native_id']:
            raise rejected('feature_identity_collision', 'Per-feature reference census identity/order differs from the tree.')
        seen.add(native_id)
        row_count = _count(table['count'])
        if type(table['rows']) is not list or len(table['rows']) != row_count:
            raise rejected('feature_context_capture_invalid', 'Per-feature reference count and rows disagree.')
        observed += row_count
        _count(observed)
        for index, row in enumerate(table['rows']):
            _keys(row, ('row_index', *EXTERNAL_FIELDS))
            if type(row['row_index']) is not int or row['row_index'] != index:
                raise rejected('feature_context_capture_invalid', 'Invalid per-feature reference row index.')
            for field in EXTERNAL_FIELDS:
                if field in ('status', 'configuration_option'):
                    _integer(row[field])
                else:
                    text_work += len(_text(row[field]))
    if observed != total:
        raise rejected('feature_context_capture_invalid', 'Per-feature total reference count is incomplete.')
    if text_work > MAX_TEXT_TOTAL:
        raise rejected('feature_context_budget_exceeded', 'Per-feature reference text budget exceeded.')
    return deepcopy(value)


def enforce_combined_text_budget(context, capture):
    equations = context['equations']
    work = len(equations['properties']['file_path']) + sum(len(row['expression']) for row in equations['rows'])
    reference_rows = context['external_references']['rows'] + [row for table in capture['features'] for row in table['rows']]
    work += sum(len(row[field]) for row in reference_rows for field in EXTERNAL_FIELDS
                if field not in ('status', 'configuration_option'))
    work += sum(len(row['feature_name']) + len(row['file_path']) for row in context['auxiliary_references']['rows'])
    if work > MAX_TEXT_TOTAL:
        raise rejected('feature_context_budget_exceeded', 'Combined equation/reference text budget exceeded.')


def outgoing_bindings(context, capture, graph):
    """Call only with typed captures attached to the same closed native census."""
    by_signature = {}
    def group(row):
        signature = tuple(row[field] for field in EXTERNAL_FIELDS)
        return by_signature.setdefault(signature, {'document_row_indices': [], 'feature_rows': defaultdict(list)})
    for row in context['external_references']['rows']:
        group(row)['document_row_indices'].append(row['row_index'])
    for table, node in zip(capture['features'], graph['nodes']):
        if table['native_id'] != node['native_id']:
            raise rejected('feature_identity_collision', 'Reference census and graph identities differ.')
        for row in table['rows']:
            group(row)['feature_rows'][node['node_index']].append(row['row_index'])
    if len(capture['features']) != len(graph['nodes']):
        raise rejected('feature_context_capture_invalid', 'Reference census and graph coverage differ.')
    nodes = {node['node_index']: node for node in graph['nodes']}
    groups, blockers = [], []
    for value in by_signature.values():
        document_indices = value['document_row_indices']
        refs = [{'node_index': index, 'native_id': nodes[index]['native_id'],
                 'object_id': nodes[index]['object_id'], 'native_reference_row_indices': indices}
                for index, indices in value['feature_rows'].items()]
        native_count = sum(len(ref['native_reference_row_indices']) for ref in refs)
        status = 'bound'
        if len(document_indices) != native_count:
            status = 'inventory_mismatch'
        elif len(refs) != 1:
            status = 'ambiguous'
        elif not refs[0]['object_id']:
            status = 'persistent_target_unavailable'
        item = {'document_row_indices': document_indices, 'feature_rows': refs, 'match_status': status}
        groups.append(item)
        if status != 'bound':
            blockers.append({'code': 'external_reference_' + status, **item})
    return {'revision_scope': SCOPE, 'complete': not blockers, 'native_feature_count': capture['feature_count'],
            'document_reference_row_count': context['external_references']['count'],
            'native_feature_reference_row_count': capture['total_reference_rows'],
            'groups': groups, 'blockers': blockers, 'names_and_indices_are_writable_anchors': False}
