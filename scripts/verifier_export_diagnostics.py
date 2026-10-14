"""Private bounded verifier diagnostics; no CAD getters or source mutations.

UI rows retain canonical interfaces only while comparing identity. Reports use
ephemeral local integers, never native pointers, document names or paths. These
diagnostics do not normalize snapshots, prove restoration or infer a cause.
"""


def ui_snapshot_difference(before, after, *, max_rows=64, max_comparisons=65536):
    if type(max_rows) is not int or not 1 <= max_rows <= 1024:
        raise ValueError('Invalid UI report row budget.')
    if type(max_comparisons) is not int or not 1 <= max_comparisons <= 1_000_000:
        raise ValueError('Invalid UI diagnostic comparison budget.')
    if not isinstance(before, (list, tuple)) or not isinstance(after, (list, tuple)):
        raise ValueError('UI snapshots must be row sequences.')
    identities, comparisons = [], 0
    def rows(snapshot):
        nonlocal comparisons
        result = []
        for index, row in enumerate(snapshot):
            if not isinstance(row, (list, tuple)) or len(row) != 3 or row[0] is None:
                raise ValueError('Invalid UI row.')
            if any(type(value) is not int or value < 0 for value in row[1:]):
                raise ValueError('UI counts must be nonnegative native integers.')
            key = None
            for known_index, known in enumerate(identities):
                comparisons += 1
                if comparisons > max_comparisons:
                    raise ValueError('UI diagnostic comparison budget exceeded.')
                if row[0] == known:
                    key = known_index
                    break
            if key is None:
                key = len(identities)
                identities.append(row[0])  # Strong canonical interfaces, no hash/id surrogate.
            result.append({'row_index': index, 'identity_index': key,
                           'blocking_state': row[1], 'selection_count': row[2]})
        return result
    old, current = rows(before), rows(after)
    old_keys, current_keys = [row['identity_index'] for row in old], [row['identity_index'] for row in current]
    changed = []
    for row in current:
        key = row['identity_index']
        if key in old_keys:
            previous = old[old_keys.index(key)]
            if (previous['blocking_state'], previous['selection_count']) != (row['blocking_state'], row['selection_count']):
                changed.append({'identity_index': key, 'before_row_index': previous['row_index'],
                    'after_row_index': row['row_index'], 'before_blocking_state': previous['blocking_state'],
                    'after_blocking_state': row['blocking_state'],
                    'before_selection_count': previous['selection_count'], 'after_selection_count': row['selection_count']})
    missing = [row['row_index'] for row in old if row['identity_index'] not in current_keys]
    added = [row['row_index'] for row in current if row['identity_index'] not in old_keys]
    return {'scope': 'ordered_canonical_identity_blocking_selection', 'cause_inferred': False,
            'before_row_count': len(old), 'after_row_count': len(current),
            'before_rows': old[:max_rows], 'after_rows': current[:max_rows],
            'identity_order_changed': old_keys != current_keys,
            'missing_before_row_indices': missing[:max_rows], 'added_after_row_indices': added[:max_rows],
            'changed_counts': changed[:max_rows],
            'duplicate_identity_rows': len(set(old_keys)) != len(old_keys) or len(set(current_keys)) != len(current_keys),
            'rows_truncated': max(len(old), len(current), len(changed)) > max_rows,
            'canonical_equality_comparisons': comparisons}


def capture_ui_difference(reader, before, report, field):
    """Capture exactly once; diagnostics never replace the caller's strict check."""
    try:
        after = reader()
    except BaseException as exc:
        report[field] = {'snapshot_read_error_type': type(exc).__name__[:80], 'cause_inferred': False}
        raise
    try:
        report[field] = ui_snapshot_difference(before, after)
    except Exception as exc:
        report[field] = {'diagnostic_error_type': type(exc).__name__[:80], 'cause_inferred': False,
                         'before_row_count': len(before) if isinstance(before, (list, tuple)) else None,
                         'after_row_count': len(after) if isinstance(after, (list, tuple)) else None}
    return after


def ui_snapshot_unmeasured(before, *, max_rows=64):
    """Report retained baseline counts without native identity comparisons/getters."""
    rows = []
    for index, row in enumerate(before[:max_rows]):
        if isinstance(row, (tuple, list)) and len(row) == 3 and all(type(value) is int for value in row[1:]):
            rows.append({'row_index': index, 'blocking_state': row[1], 'selection_count': row[2]})
    return {'cause_inferred': False, 'before_row_count': len(before), 'before_rows': rows,
            'after_row_count': None, 'after_snapshot_read': False,
            'reason': 'fixture_cleanup_hold', 'rows_truncated': len(before) > max_rows}


def close_resources_with_gate(resources, gate, diagnostics, *, primary_error=None):
    """Attempt both closes, retain before fixture cleanup, preserve primary error."""
    first_error = None
    for name, resource in resources:
        if resource is None:
            continue
        try:
            resource.close()
        except BaseException as exc:
            gate.retain()
            if len(diagnostics) < 8:
                diagnostics.append({'resource': name, 'error_type': type(exc).__name__[:80]})
            if first_error is None:
                first_error = exc
    if first_error is not None and primary_error is None:
        raise first_error


def require_fixture_native_access(gate):
    """A held durable execution gate prohibits subsequent direct native work."""
    if gate.can_cleanup() is not True:
        raise RuntimeError('Held fixture execution gate prohibits further native access.')


def independent_baseline_check(checker, gate, *, native_activity):
    """A post-adapter independent failure holds fixtures for manual review."""
    require_fixture_native_access(gate)
    try:
        return checker()
    except BaseException:
        if native_activity is True:
            gate.retain()
        raise
