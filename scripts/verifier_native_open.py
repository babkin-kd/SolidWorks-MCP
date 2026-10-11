"""Pure strict open evidence gates; never a CAD effect/rollback oracle.

These predicates only confirm released guards and completed one-shot native
ledger pairs. The supervisor must separately require a final durable domain
outcome and independent full-baseline/file/handle postconditions.
"""

import json


OPEN_SCOPE = 'native_document_open_resolved_v1'
OPEN_GUARD_SCOPE = 'application_document_open_guard_v1'
MAX_BASELINE_MODELS = 4999
STEP_NAMES = {'open_native', 'release_baseline_ui', 'activate_native',
              'rollback_close_native', 'rollback_activate_native'}


def _ids(values, maximum=MAX_BASELINE_MODELS):
    return (type(values) is list and len(values) <= maximum
            and all(type(value) is str and value.strip() for value in values)
            and len(set(values)) == len(values))


def _baseline_ids(before):
    if type(before) is not dict or before.get('scope') != OPEN_SCOPE:
        return None
    semantic = before.get('semantic')
    documents = semantic.get('documents') if type(semantic) is dict else None
    if (type(documents) is not list or len(documents) > MAX_BASELINE_MODELS
            or any(type(row) is not dict for row in documents)):
        return None
    ids = [row.get('document_id') for row in documents]
    return ids if _ids(ids) else None


def _model_released(model):
    return (type(model) is dict and set(model) == {'original_state', 'locked_state', 'released_state'}
            and all(type(model[key]) is int and model[key] == value for key, value in
                    (('original_state', 0), ('locked_state', 2), ('released_state', 0))))


def released_open_guard(guard, before):
    """Exact baseline guards, including zero baseline; no foreign guard scope."""
    ids = _baseline_ids(before)
    keys = {'scope', 'original_command_in_progress', 'acquired', 'released', 'model_guards',
            'selection_preserved', 'baseline_document_ids', 'activation_ui_release'}
    if (ids is None or type(guard) is not dict or set(guard) != keys
            or guard['scope'] != OPEN_GUARD_SCOPE
            or not _ids(guard['baseline_document_ids']) or guard['baseline_document_ids'] != ids):
        return False
    release = guard['activation_ui_release']
    if type(release) is not dict or set(release) != {'attempted', 'verified'}:
        return False
    phase = ((release['attempted'] is False and release['verified'] is False)
             or (bool(ids) and release['attempted'] is True and release['verified'] is True))
    models = guard['model_guards']
    return (phase and guard['original_command_in_progress'] is False
            and guard['acquired'] is True and guard['released'] is True
            and guard['selection_preserved'] is True and type(models) is list
            and len(models) == len(ids) and all(_model_released(model) for model in models))


def untouched_busy_open_guard(guard, before):
    """Only raced foreign CIP, before native work; supervisor checks job phase."""
    ids = _baseline_ids(before)
    keys = {'scope', 'original_command_in_progress', 'acquired', 'released', 'model_guards',
            'selection_preserved', 'baseline_document_ids', 'activation_ui_release'}
    if (ids is None or type(guard) is not dict or set(guard) != keys
            or guard['scope'] != OPEN_GUARD_SCOPE
            or not _ids(guard['baseline_document_ids']) or guard['baseline_document_ids'] != ids):
        return False
    release = guard['activation_ui_release']
    return (guard['original_command_in_progress'] is True and guard['acquired'] is False
            and guard['released'] is False and guard['selection_preserved'] is (len(ids) == 0)
            and type(guard['model_guards']) is list and not guard['model_guards']
            and type(release) is dict and set(release) == {'attempted', 'verified'}
            and release['attempted'] is False and release['verified'] is False)


def _json(value):
    def validate(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError('Journal JSON keys must be strings.')
            for child in item.values():
                validate(child)
        elif type(item) is list:
            for child in item:
                validate(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ValueError('Only detached journal JSON values are evidence.')
    validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':'))


def _open_returned(evidence, outcome):
    flags = {'native_call_attempted', 'native_call_returned', 'pending_open',
             'returned_model_retained', 'returned_new_identity', 'acknowledgement_valid'}
    if (type(evidence) is not dict or set(evidence) != flags | {'errors', 'warnings'}
            or any(type(evidence[key]) is not bool for key in flags)
            or evidence['pending_open'] is not False
            or any(evidence[key] is not None and
                   (type(evidence[key]) is not int or not 0 <= evidence[key] < 2 ** 31)
                   for key in ('errors', 'warnings'))):
        return False
    normal = evidence['native_call_attempted'] is True and evidence['native_call_returned'] is True
    if not normal:
        return (outcome == 'rolled_back' and all(evidence[key] is False for key in flags)
                and evidence['errors'] is None and evidence['warnings'] is None)
    if evidence['returned_new_identity'] and not evidence['returned_model_retained']:
        return False
    if evidence['acknowledgement_valid'] and any(evidence[key] is None for key in ('errors', 'warnings')):
        return False
    if outcome == 'committed':
        return (evidence['returned_model_retained'] is True and evidence['returned_new_identity'] is True
                and evidence['acknowledgement_valid'] is True
                and evidence['errors'] == 0 and evidence['warnings'] == 0)
    # A normally returned malformed ACK may accompany a verified no-effect
    # rollback. Only the independent domain oracle can prove that absence.
    return True


def _activation_returned(evidence, outcome):
    keys = {'native_call_attempted', 'native_call_returned', 'native_error'}
    if (type(evidence) is not dict or set(evidence) != keys
            or type(evidence['native_call_attempted']) is not bool
            or type(evidence['native_call_returned']) is not bool):
        return False
    if evidence['native_call_attempted'] is True and evidence['native_call_returned'] is True:
        return type(evidence['native_error']) is int and evidence['native_error'] in (0, 2)
    return (outcome == 'rolled_back' and evidence['native_call_attempted'] is False
            and evidence['native_call_returned'] is False and evidence['native_error'] is None)


def _close_impact(impact, baseline_ids):
    keys = {'target_document_id', 'native_name', 'retiring_document_ids', 'hidden_document_ids',
            'survivor_document_ids', 'retiring_window_handles', 'active_after_document_id',
            'policy', 'data_unload_claimed'}
    if type(impact) is not dict or set(impact) != keys:
        return False
    retiring, hidden, survivors = (impact[key] for key in
                                  ('retiring_document_ids', 'hidden_document_ids', 'survivor_document_ids'))
    if (not _ids(retiring, 5000) or not retiring or not _ids(hidden, 5000) or not _ids(survivors)
            or type(impact['target_document_id']) is not str or impact['target_document_id'] not in retiring
            or set(hidden) != set(retiring) - {impact['target_document_id']}
            or set(retiring) & set(baseline_ids) or survivors != baseline_ids
            or len(retiring) + len(baseline_ids) > 5000
            or type(impact['native_name']) is not str or not impact['native_name'].strip()
            or impact['policy'] != 'require_clean' or impact['data_unload_claimed'] is not False):
        return False
    active = impact['active_after_document_id']
    if active is not None and (type(active) is not str or active not in baseline_ids):
        return False
    handles = impact['retiring_window_handles']
    return (type(handles) is list and len(handles) <= 5000
            and all(type(value) is int and 0 < value < 2 ** 63 for value in handles)
            and len(set(handles)) == len(handles))


def _steps(verification, before):
    ids = _baseline_ids(before)
    if (ids is None or type(verification) is not dict
            or set(verification) != {'outcome', 'evidence', 'native_steps'}
            or type(verification['outcome']) is not str
            or verification['outcome'] not in ('committed', 'rolled_back')
            or type(verification['evidence']) is not dict):
        return False
    steps, outcome = verification['native_steps'], verification['outcome']
    if type(steps) is not list or not 2 <= len(steps) <= 2 * len(STEP_NAMES) or len(steps) % 2:
        return False
    if (type(before.get('native_file_id')) is not str or not before['native_file_id'].strip()
            or type(before.get('source')) is not dict or not before['source']):
        return False
    active = before['semantic'].get('active_document_id')
    if active is not None and (type(active) is not str or active not in ids):
        return False
    # Finite JSON and type-sensitive equality bind fingerprints (False != 0).
    _json(verification)
    source = _json(before['source'])
    seen = set()
    opened = None
    for offset in range(0, len(steps), 2):
        pending, returned = steps[offset:offset + 2]
        for index, event in ((offset + 1, pending), (offset + 2, returned)):
            if (type(event) is not dict or set(event) != {'sequence', 'name', 'phase', 'evidence'}
                    or type(event['sequence']) is not int or event['sequence'] != index
                    or type(event['name']) is not str or event['name'] not in STEP_NAMES
                    or type(event['evidence']) is not dict or not event['evidence']):
                return False
        name = pending['name']
        if (pending['phase'] != 'pending' or returned['phase'] != 'returned'
                or name != returned['name'] or name in seen
                or (offset == 0 and name != 'open_native')):
            return False
        a, b = pending['evidence'], returned['evidence']
        if name == 'open_native':
            if (offset != 0 or set(a) != {'native_file_id', 'source'}
                    or type(a['native_file_id']) is not str or a['native_file_id'] != before['native_file_id']
                    or type(a['source']) is not dict or _json(a['source']) != source
                    or not _open_returned(b, outcome)):
                return False
            opened = b
        else:
            # Following native steps require an exact normally returned owned
            # root receipt; no roster delta or null/malformed ACK grants it.
            if not all(opened[key] is True for key in ('native_call_attempted', 'native_call_returned',
                       'returned_model_retained', 'returned_new_identity', 'acknowledgement_valid')):
                return False
            if name == 'release_baseline_ui':
                if (not ids or set(a) != {'baseline_document_ids'}
                        or not _ids(a['baseline_document_ids']) or a['baseline_document_ids'] != ids
                        or set(b) != {'verified'} or b['verified'] is not True
                        or 'activate_native' in seen or 'rollback_activate_native' in seen):
                    return False
            elif name in ('activate_native', 'rollback_activate_native'):
                if (set(a) != {'document_id'} or type(a['document_id']) is not str or not a['document_id'].strip()
                        or not _activation_returned(b, outcome)
                        or (ids and 'release_baseline_ui' not in seen)):
                    return False
                if name == 'activate_native':
                    if ('rollback_close_native' in seen or 'rollback_activate_native' in seen
                            or opened['errors'] != 0 or opened['warnings'] != 0
                            or (active is not None and a['document_id'] != active)):
                        return False
                elif (outcome != 'rolled_back' or 'rollback_close_native' not in seen
                      or active is None or a['document_id'] != active):
                    return False
            elif name == 'rollback_close_native':
                if (outcome != 'rolled_back' or set(a) != {'impact'} or not _close_impact(a['impact'], ids)
                        or 'rollback_activate_native' in seen
                        or set(b) != {'native_call_returned', 'acknowledgement_valid'}
                        or b['native_call_returned'] is not True or b['acknowledgement_valid'] is not True):
                    return False
        seen.add(name)
    return True


def verified_open_native_steps(verification, before):
    """Completed exact native pairs only; final domain state is separate proof."""
    try:
        return _steps(verification, before)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return False
