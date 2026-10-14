"""Pure failed-readback boundary diagnostics; no native calls or permission.

Stable endpoints cannot erase ABA/rebuild notifications or explain an earlier
failed/unknown call. Even an entirely stable supplied boundary grants neither
acceptance, cleanup nor retry. Actual unavailable inputs are never baseline-filled.
"""
from copy import deepcopy


METADATA_FIELDS = frozenset(('title', 'path', 'document_type', 'needs_save',
                             'configurations', 'active_configuration', 'update_stamp'))
# Exact PartRevisionWatch.EVENTS, checked against the production source by tests.
# Keep this pure helper free of cad_features/pythoncom imports and native setup.
WATCH_EVENTS = frozenset({
    'OnAddItemNotify', 'OnRenameItemNotify', 'OnDeleteItemNotify', 'OnModifyNotify',
    'OnActiveConfigChangePostNotify', 'OnConfigurationChangeNotify',
    'OnSuppressionStateChangeNotify', 'OnDimensionChangeNotify', 'OnSketchSolveNotify',
    'OnAddCustomPropertyNotify', 'OnChangeCustomPropertyNotify', 'OnDeleteCustomPropertyNotify',
    'OnBodyVisibleChangeNotify', 'OnFeatureManagerTreeRebuildNotify',
    'OnRegenPostNotify', 'OnRegenPostNotify2', 'OnUndoPostNotify', 'OnRedoPostNotify',
    'OnFileSavePostNotify', 'OnFileReloadNotify', 'OnFileReloadPostNotify',
    'OnEquationEditorPostNotify', 'OnCloseDesignTableNotify', 'OnUnitsChangeNotify',
    'OnActiveDisplayStateChangePostNotify', 'OnVisualPropertiesChangeNotify',
    'OnWeldmentCutListUpdatePostNotify', 'OnDestroyNotify', 'OnDestroyNotify2',
})
MAX_OBSERVED_EVENTS = 128


def _metadata(value):
    if (type(value) is not dict or set(value) != METADATA_FIELDS
            or any(type(value[key]) is not str for key in ('title', 'path', 'document_type', 'active_configuration'))
            or type(value['needs_save']) is not bool or type(value['update_stamp']) is not int
            or type(value['configurations']) is not list
            or any(type(cfg) is not str or not cfg for cfg in value['configurations'])
            or len(set(value['configurations'])) != len(value['configurations'])
            or (value['active_configuration'] not in value['configurations']
                if value['configurations'] else value['active_configuration'] != '')):
        raise ValueError('Actual complete typed seven-field opening/closing metadata required.')
    return deepcopy(value)


def diagnose_snapshot_boundary(opening, closing, *, canonical_model_preserved,
                               canonical_configuration_preserved, watch_before,
                               watch_after, observed_events):
    """Explain a supplied failed readback; never infer operation outcome/retry.

Both metadata dictionaries contain exactly DocumentCatalog's seven native
snapshot fields. Canonical preservation flags are strict bools. Watch counters
are actual nonnegative ints. observed_events is a capped list of actual names
from PartRevisionWatch.EVENTS; duplicates/order are retained. Missing/capped
trace evidence never erases a counter change. Malformed data raises ValueError.
"""
    opening, closing = _metadata(opening), _metadata(closing)
    if type(canonical_model_preserved) is not bool or type(canonical_configuration_preserved) is not bool:
        raise ValueError('Actual strict canonical model/configuration preservation booleans required.')
    if type(watch_before) is not int or type(watch_after) is not int or min(watch_before, watch_after) < 0:
        raise ValueError('Actual nonnegative integer revision-watch counters required.')
    if (type(observed_events) is not list or len(observed_events) > MAX_OBSERVED_EVENTS
            or any(type(name) is not str or name not in WATCH_EVENTS for name in observed_events)):
        raise ValueError('Actual capped PartRevisionWatch event-name list required.')
    events = list(observed_events)
    changed = sorted(key for key in METADATA_FIELDS if opening[key] != closing[key])
    delta = watch_after - watch_before
    reasons = []
    if changed:
        reasons.append(dict(kind='metadata', code='opening_closing_metadata_changed', fields=changed))
    if canonical_model_preserved is False:
        reasons.append(dict(kind='model', code='original_canonical_model_changed'))
    if canonical_configuration_preserved is False:
        reasons.append(dict(kind='configuration', code='original_canonical_configuration_changed'))
    if delta != 0:
        reasons.append(dict(kind='watch', code='revision_counter_regressed' if delta < 0 else 'revision_counter_changed'))
    if events:
        reasons.append(dict(kind='watch', code='actual_revision_events_observed'))
    if len(events) > max(delta, 0):
        reasons.append(dict(kind='watch', code='counter_event_trace_inconsistent'))
    elif delta > len(events):
        reasons.append(dict(kind='watch', code='event_trace_incomplete_or_capped'))
    return dict(scope='failed_readback_boundary_diagnostics_v1', opening=opening, closing=closing,
        changed_metadata_fields=changed, event_delta=delta, observed_events=events,
        refusal_reasons=reasons, boundary_violation_observed=bool(reasons),
        equal_metadata_with_revision_evidence=not changed and bool(delta != 0 or events),
        native_accepted=False, cleanup_authorized=False, retry_authorized=False)
