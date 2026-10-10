"""Bounded structural candidates for deletion planning, never delete authority.

Parent/child relations and absorbed ownership have different semantics. Their
union can legitimately contain a cycle (an extrusion owns its driving sketch).
Only pure graph analysis occurs here; actual native deletion effects, equations,
other configurations and external references require additional capture/proof.
"""

from collections import deque
from copy import deepcopy
import hashlib

from .documents import rejected
from .feature_dependency_graph import SCOPE as GRAPH_SCOPE, relation_semantics
from .jobs import _json


SCOPE = 'part_feature_deletion_structure_v1'
UNVERIFIED_SCOPES = (
    'other_configurations', 'dimensions_and_equations', 'annotations_and_drawings',
    'external_files_and_in_context_references', 'native_deletion_effects_and_restoration',
)


def validate_request(object_ids, include_children, include_absorbed):
    if (type(object_ids) is not list or not 1 <= len(object_ids) <= 200
            or any(type(value) is not str or not 1 <= len(value) <= 128 for value in object_ids)
            or len(set(object_ids)) != len(object_ids)):
        raise rejected('invalid_feature_targets', 'Provide 1..200 unique persistent feature object_ids.')
    if type(include_children) is not bool or type(include_absorbed) is not bool:
        raise rejected('invalid_delete_options', 'Both child and absorbed options require explicit booleans.')


def _adjacency(count, edges):
    outgoing = [[] for _ in range(count)]
    for left, right in sorted(edges):
        outgoing[left].append(right)
    return outgoing


def _reachable(outgoing, roots):
    reached, queue = set(roots), deque(sorted(roots))
    while queue:
        for dependent in outgoing[queue.popleft()]:
            if dependent not in reached:
                reached.add(dependent)
                queue.append(dependent)
    return reached


def _cycles(count, edges, relevant):
    """Iterative Kosaraju: bounded deep graphs must not recurse in Python."""
    edges = {(left, right) for left, right in edges if left in relevant and right in relevant}
    outgoing = _adjacency(count, edges)
    incoming = _adjacency(count, {(right, left) for left, right in edges})
    visited, order = set(), []
    for root in sorted(relevant):
        if root in visited:
            continue
        visited.add(root)
        stack = [(root, iter(outgoing[root]))]
        while stack:
            node, iterator = stack[-1]
            dependent = next(iterator, None)
            if dependent is None:
                stack.pop()
                order.append(node)
            elif dependent not in visited:
                visited.add(dependent)
                stack.append((dependent, iter(outgoing[dependent])))
    visited, components = set(), []
    for root in reversed(order):
        if root in visited:
            continue
        component, stack = [], [root]
        visited.add(root)
        while stack:
            node = stack.pop()
            component.append(node)
            for dependent in incoming[node]:
                if dependent not in visited:
                    visited.add(dependent)
                    stack.append(dependent)
        if len(component) > 1 or (root, root) in edges:
            components.append(sorted(component))
    return sorted(components)


def structural_candidates(graph, object_ids, include_children, include_absorbed):
    """Conservative structural candidate set from a successfully closed graph.

    This set is not the exact native DeleteSelection2 result. All unverified
    scopes remain explicit blockers; no success-shaped deletion approval exists.
    """
    validate_request(object_ids, include_children, include_absorbed)
    if (type(graph) is not dict or graph.get('revision_scope') != GRAPH_SCOPE
            or graph.get('all_reported_native_relations_captured') is not True
            or type(graph.get('revision')) is not str or len(graph['revision']) != 68
            or not graph['revision'].startswith('rev_')
            or any(value not in '0123456789abcdef' for value in graph['revision'][4:])
            or any(type(graph.get(key)) is not str or not graph[key] for key in ('document_id', 'configuration'))
            or type(graph.get('nodes')) is not list or len(graph['nodes']) > 5000
            or type(graph.get('native_relation_work')) is not list or len(graph['native_relation_work']) != 2
            or any(type(value) is not int or not 0 <= value <= 100000 for value in graph['native_relation_work'])):
        raise rejected('feature_dependency_capture_invalid', 'Expected a complete bounded dependency graph.')
    nodes = graph['nodes']
    ids = {}
    for index, node in enumerate(nodes):
        if (type(node) is not dict or type(node.get('node_index')) is not int or node['node_index'] != index
                or type(node.get('persistent_reference_supported')) is not bool
                or type(node.get('native_id')) is not int or 'owner_native_id' not in node
                or (node['owner_native_id'] is not None and type(node['owner_native_id']) is not int)):
            raise rejected('feature_dependency_capture_invalid', 'Invalid graph node metadata.')
        object_id = node.get('object_id')
        if object_id is not None:
            if (type(object_id) is not str or not 1 <= len(object_id) <= 128 or object_id in ids
                    or node['persistent_reference_supported'] is not True):
                raise rejected('feature_identity_collision', 'Graph persistent targets must be unique and supported.')
            ids[object_id] = index
        elif node['persistent_reference_supported']:
            raise rejected('feature_dependency_capture_invalid', 'Supported node has no persistent reference.')
    if len({node['native_id'] for node in nodes}) != len(nodes):
        raise rejected('feature_identity_collision', 'Graph native ID hints must be unique.')
    raw_relations = graph.get('relations')
    if type(raw_relations) is not dict:
        raise rejected('feature_dependency_capture_invalid', 'Graph relations are missing.')
    # The domain graph intentionally omits a nonsemantic work counter from its
    # relation payload. Restore each independently observed counter for checking.
    for work in graph['native_relation_work']:
        relation_semantics({**raw_relations, 'relations_read': work}, nodes)
    if any(value not in ids for value in object_ids):
        raise rejected('object_reference_not_found', 'A requested persistent feature is absent from this graph.')

    parents = {tuple(edge) for edge in raw_relations['parent_links']}
    children = {tuple(edge) for edge in raw_relations['child_links']}
    absorbed = {tuple(edge) for edge in raw_relations['absorbed_links']}
    if _cycles(len(nodes), absorbed, set(range(len(nodes)))):
        raise rejected('feature_dependency_capture_invalid', 'Absorbed ownership is cyclic.')
    dependencies = parents | children
    roots = {ids[value] for value in object_ids}
    followed = (dependencies if include_children else set()) | (absorbed if include_absorbed else set())
    candidates = _reachable(_adjacency(len(nodes), followed), roots)
    potentially_affected = _reachable(_adjacency(len(nodes), dependencies | absorbed), candidates)
    candidate_rows = []
    reasons = [[] for _ in nodes]
    for left, right in sorted(followed):
        if left in candidates and right in candidates:
            if (left, right) in dependencies and include_children:
                reasons[right].append({'from_node_index': left, 'kind': 'dependent_feature',
                    'parent_confirmed': (left, right) in parents, 'child_confirmed': (left, right) in children})
            if (left, right) in absorbed and include_absorbed:
                reasons[right].append({'from_node_index': left, 'kind': 'absorbed_feature'})
    for index in sorted(candidates):
        candidate_rows.append({**deepcopy(nodes[index]), 'explicitly_requested': index in roots,
                               'included_by': reasons[index]})
    nonreciprocal = sorted(parents ^ children)
    blockers = [{'code': 'unverified_impact_scope', 'scope': scope} for scope in UNVERIFIED_SCOPES]
    if nonreciprocal:
        blockers.append({'code': 'nonreciprocal_native_relations', 'links': [list(edge) for edge in nonreciprocal]})
    unsupported = sorted(index for index in candidates if nodes[index]['object_id'] is None)
    if unsupported:
        blockers.append({'code': 'candidate_persistent_reference_unavailable', 'node_indices': unsupported})
    cycles = _cycles(len(nodes), dependencies, potentially_affected)
    if cycles:
        blockers.append({'code': 'cyclic_feature_dependencies', 'components': cycles})
    options = {'include_children': include_children, 'include_absorbed': include_absorbed}
    revision = 'rev_' + hashlib.sha256(_json({'scope': SCOPE, 'graph_revision': graph['revision'],
                                            'requested_node_indices': sorted(roots), 'options': options}).encode('utf8')).hexdigest()
    return {'document_id': graph['document_id'], 'configuration': graph['configuration'],
            'revision_scope': SCOPE, 'revision': revision, 'dependency_graph_revision': graph['revision'],
            'options': options, 'native_delete_options': int(include_children) | (2 * int(include_absorbed)),
            'requested_node_indices': sorted(roots), 'structural_candidate_nodes': candidate_rows,
            'potentially_affected_survivor_node_indices': sorted(potentially_affected - candidates),
            'dependent_survivor_links': [list(edge) for edge in sorted(dependencies)
                                       if edge[0] in candidates and edge[1] not in candidates],
            'absorbed_survivor_links': [list(edge) for edge in sorted(absorbed)
                                      if edge[0] in candidates and edge[1] not in candidates],
            'cyclic_dependency_components': cycles, 'blockers': blockers,
            'structural_links_complete': True, 'deletion_impact_complete': False,
            'deletion_authorized': False, 'native_deletion_result_predicted': False}
