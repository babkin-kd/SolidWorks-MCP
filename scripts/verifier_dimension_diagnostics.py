"""Passive private preference evidence; no CAD access, setters or cleanup."""

import json
import math


def _snapshot(values):
    if type(values) is not dict or len(values) > 64:
        raise ValueError('Expected a bounded scalar preference snapshot.')
    result = {}
    for key, value in values.items():
        if type(key) is not str or not 1 <= len(key) <= 80:
            raise ValueError('Invalid preference field.')
        if type(value) not in (str, bool, int, float, type(None)):
            raise ValueError('Preference evidence must contain native scalars only.')
        if type(value) is str and len(value) > 4096:
            raise ValueError('Preference string budget exceeded.')
        if type(value) is float and not math.isfinite(value):
            raise ValueError('Nonfinite preference evidence.')
        result[key] = value
    return result


def assert_preference_snapshot(reader, expected, report, field):
    """Read once, retain exact private evidence, keep a strict typed comparison."""
    before = _snapshot(expected)
    report[field] = {'cause_inferred': False, 'before': before,
                     'after': None, 'snapshot_read': False, 'exactly_equal': False}
    try:
        current = reader()
    except BaseException as error:
        report[field]['snapshot_read_error_type'] = type(error).__name__[:80]
        raise
    report[field]['snapshot_read'] = True
    try:
        after = _snapshot(current)
    except ValueError:
        report[field]['diagnostic_error_type'] = 'invalid_scalar_snapshot'
        raise
    changed = [key for key in sorted(before.keys() | after.keys())
               if key not in before or key not in after
               or type(before[key]) is not type(after[key]) or before[key] != after[key]]
    report[field].update(after=after, changed_fields=changed, exactly_equal=not changed)
    if changed:
        raise AssertionError('Independent application preferences changed; private snapshots retained.')


# Explicit user deferral: never infer exclusions from a prefix or caller input.
DEFERRED_STL_FIELDS = frozenset({
    'stl_units', 'stl_binary', 'stl_dont_translate_to_positive', 'stl_show_info',
    'stl_preview', 'stl_quality', 'stl_deviation', 'stl_angle',
})


def assert_non_stl_preferences(reader, expected, report, field):
    """Retain full raw evidence; require exact equality outside deferred STL."""
    before = _snapshot(expected)
    facts = {'scope': 'application_preferences_except_stl_v1',
             'excluded_fields': sorted(DEFERRED_STL_FIELDS),
             'stl_preferences_verified': False, 'cause_inferred': False,
             'before': before, 'after': None, 'snapshot_read': False,
             'scope_exactly_equal': False, 'all_preferences_exactly_equal': False}
    report[field] = facts
    try:
        after = _snapshot(reader())
    except BaseException as error:
        facts['snapshot_read_error_type'] = type(error).__name__[:80]
        raise
    facts.update(after=after, snapshot_read=True)
    changed = [key for key in sorted(before.keys() | after.keys())
               if key not in before or key not in after
               or type(before[key]) is not type(after[key]) or before[key] != after[key]]
    checked = sorted((before.keys() | after.keys()) - DEFERRED_STL_FIELDS)
    if not checked:
        raise ValueError('Non-STL preference scope must not be empty.')
    scoped_changed = [key for key in changed if key not in DEFERRED_STL_FIELDS]
    facts.update(changed_fields=changed, checked_fields=checked,
                 scope_changed_fields=scoped_changed,
                 scope_exactly_equal=not scoped_changed,
                 all_preferences_exactly_equal=not changed)
    if scoped_changed:
        raise AssertionError('Independent non-STL preferences changed; private snapshots retained.')


def write_failure_report(path, report, primary_error):
    """A failed diagnostic write must not mask the original verifier failure."""
    report.update(accepted=False, public_mcp_dimension_acceptance=False,
                  error_type=type(primary_error).__name__[:80],
                  private_journal_retained=True, automatic_replay_attempted=False)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf8') as stream:
            json.dump(report, stream, ensure_ascii=True, allow_nan=False, indent=2)
            stream.write('\n')
    except BaseException as report_error:
        primary_error.add_note('Private failure report write failed: ' + type(report_error).__name__[:80])
