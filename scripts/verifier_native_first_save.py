"""Detached positive L3 protocol gate; never an independent CAD/file oracle."""
import json

from solidworks_mcp.native_first_save import SCOPE, clone_mapping


def _json(value):
    def check(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError('Only detached JSON keys are allowed.')
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ValueError('Only detached JSON values are allowed.')
    check(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def released_first_save_guard(guard, before):
    """Release of every survivor guard; retiring source has no exit getters."""
    try:
        _json(guard)
        if (before['scope'] != SCOPE or type(guard) is not dict
                or set(guard) != {'scope', 'native_guard', 'destination_lease_released'}
                or guard['scope'] != 'native_first_save_guard_v1'
                or guard['destination_lease_released'] is not True):
            return False
        source = before['document_id']
        ids = [row['document_id'] for row in before['semantic']['documents']]
        if (not 1 <= len(ids) <= 4999 or len(set(ids)) != len(ids)
                or any(type(item) is not str or not item.strip() for item in ids)
                or source not in ids):
            return False
        native = guard['native_guard']
        keys = {'scope', 'original_command_in_progress', 'acquired', 'released', 'model_guards',
                'selection_preserved', 'retiring_document_ids', 'retiring_targets_locked_during_close',
                'activation_ui_release'}
        if (type(native) is not dict or set(native) != keys
                or native['scope'] != 'application_document_close_guard_v1'
                or native['original_command_in_progress'] is not False
                or native['acquired'] is not True or native['released'] is not True
                or native['selection_preserved'] is not True
                or native['retiring_document_ids'] != [source]
                or native['retiring_targets_locked_during_close'] is not False):
            return False
        models, release = native['model_guards'], native['activation_ui_release']
        if (type(models) is not list or len(models) != len(ids) - 1
                or type(release) is not dict or set(release) != {'attempted', 'verified'}):
            return False
        if not ((release['attempted'] is False and release['verified'] is False)
                or (bool(models) and release['attempted'] is True and release['verified'] is True)):
            return False
        return all(type(model) is dict and set(model) == {'original_state', 'locked_state', 'released_state'}
                   and all(type(model[key]) is int and model[key] == expected for key, expected in
                           (('original_state', 0), ('locked_state', 2), ('released_state', 0))) for model in models)
    except (KeyError, TypeError, ValueError):
        return False


def _native_return(name, evidence):
    if name in ('first_save_activate_source_native', 'first_save_activate_final_native'):
        keys = {'native_call_attempted', 'native_call_returned', 'pending_activation', 'native_error'}
        return (set(evidence) == keys and evidence['native_call_attempted'] is True
                and evidence['native_call_returned'] is True and evidence['pending_activation'] is False
                and type(evidence['native_error']) is int and evidence['native_error'] in (0, 2))
    pending = {'first_save_copy_native': 'pending_copy', 'first_save_open_stage_native': 'pending_open',
               'first_save_open_final_native': 'pending_open', 'first_save_close_stage_native': 'pending_close',
               'first_save_close_source_native': 'pending_close',
               'first_save_restore_directory_native': 'pending_directory'}[name]
    keys = {'native_call_attempted', 'native_call_returned', 'acknowledgement_valid', pending}
    if pending == 'pending_copy':
        keys |= {'success', 'errors', 'warnings'}
    elif pending == 'pending_open':
        keys |= {'returned_new_identity', 'errors', 'warnings'}
    elif pending == 'pending_directory':
        keys |= {'setter_succeeded'}
    if (set(evidence) != keys or evidence['native_call_attempted'] is not True
            or evidence['native_call_returned'] is not True or evidence['acknowledgement_valid'] is not True
            or evidence[pending] is not False):
        return False
    if pending in ('pending_copy', 'pending_open'):
        acknowledgement = 'success' if pending == 'pending_copy' else 'returned_new_identity'
        return (evidence[acknowledgement] is True and all(type(evidence[key]) is int
                                                        and evidence[key] == 0 for key in ('errors', 'warnings')))
    return pending != 'pending_directory' or evidence['setter_succeeded'] is True


def verified_committed_first_save(job):
    """Require explicit IDs, complete one-shot ledger, mapping and released guard.

    Passing this gate only validates reported protocol evidence. The native
    supervisor must independently prove final bytes, CAD shape and cleanup.
    """
    try:
        _json(job)
        mutation, result = job['mutation'], job['result']
        before, after, value = result['before'], result['after'], result['value']
        verification = mutation['verification']
        if (job['status'] != 'succeeded' or job['operation'] != 'document.first_save_native'
                or mutation['phase'] != 'committed' or verification['outcome'] != 'committed'
                or result['verified'] is not True or before['scope'] != SCOPE
                or mutation['before_state'].get('_mutation_effect_scope') != 'application'
                or _json(before) != _json({key: item for key, item in mutation['before_state'].items()
                                          if key != '_mutation_effect_scope'})
                or _json(verification['evidence']['execution_guard']) != _json(result['execution_guard'])
                or not released_first_save_guard(result['execution_guard'], before)):
            return False
        source, final = before['document_id'], value['document_id']
        args = job['payload']['arguments']
        if (type(final) is not str or not final.strip() or final == source
                or mutation['document_id'] != source or args['document_id'] != source
                or args['configuration'] != before['configuration']
                or args['expected_revision'] != mutation['expected_revision']
                or value['retired_document_ids'] != [source]
                or value['source_references_retired'] is not True
                or value['resolve_saved_references_again'] is not True
                or value['filename'] != before['destination']['destination']
                or after['destination_file'] != value['file']
                or after['semantic']['active_document_id'] != final
                or after['semantic']['application'] != before['semantic']['application']
                or after['original_files'] != before['semantic']['files']
                or any(after[key] is not False for key in ('pending', 'pending_release', 'journal_failed'))
                or after['stage']['empty'] is not True or after['stage']['file'] is not None
                or after['cleanup'] != value['staging_cleanup']
                or value['staging_cleanup']['destination_removed'] is not False):
            return False
        if _json(clone_mapping(before['snapshots'][source], after['snapshots'][final])) != _json(value['reference_mapping']):
            return False
        steps = verification['native_steps']
        if type(steps) is not list or not 16 <= len(steps) <= 26 or len(steps) % 2:
            return False
        pairs = {}
        for offset in range(0, len(steps), 2):
            pending, returned = steps[offset:offset + 2]
            for index, event in ((offset + 1, pending), (offset + 2, returned)):
                if (type(event) is not dict or set(event) != {'sequence', 'name', 'phase', 'evidence'}
                        or type(event['sequence']) is not int or event['sequence'] != index
                        or type(event['name']) is not str or type(event['evidence']) is not dict):
                    return False
            name = pending['name']
            if (pending['phase'] != 'pending' or returned['phase'] != 'returned'
                    or name != returned['name'] or name in pairs):
                return False
            pairs[name] = (pending['evidence'], returned['evidence'])
            if 'native' in name and not _native_return(name, returned['evidence']):
                return False
        order = ['first_save_stage_create', 'first_save_copy_native', 'first_save_open_stage_native',
                 'first_save_close_stage_native']
        release = result['execution_guard']['native_guard']['activation_ui_release']['verified']
        releases = [name for name in ('first_save_release_survivor_ui', 'first_save_release_final_survivor_ui') if name in pairs]
        if release is not bool(releases) or len(releases) > 1:
            return False
        if 'first_save_release_survivor_ui' in pairs:
            order.append('first_save_release_survivor_ui')
        if 'first_save_activate_source_native' in pairs:
            order.append('first_save_activate_source_native')
        order += ['first_save_publish', 'first_save_cleanup_stage', 'first_save_open_final_native',
                  'first_save_close_source_native']
        if 'first_save_release_final_survivor_ui' in pairs:
            order.append('first_save_release_final_survivor_ui')
        if 'first_save_activate_final_native' in pairs:
            order.append('first_save_activate_final_native')
        if 'first_save_restore_directory_native' in pairs:
            order.append('first_save_restore_directory_native')
        if list(pairs) != order:
            return False
        copy, _ = pairs['first_save_copy_native']
        if copy != dict(document_id=source, filename=pairs['first_save_stage_create'][1]['stage']['filename'],
                        configuration=before['configuration']):
            return False
        for name, readonly in (('first_save_open_stage_native', True), ('first_save_open_final_native', False)):
            evidence = pairs[name][0]
            if (evidence['configuration'] != before['configuration'] or evidence['read_only'] is not readonly
                    or evidence['filename'] != (copy['filename'] if readonly else value['filename'])):
                return False
        if _json(pairs['first_save_publish'][0]['destination']) != _json(before['destination']):
            return False
        close = pairs['first_save_close_source_native'][0]
        if close['document_id'] != source or close['retiring_document_ids'] != [source] or close['source_replacement'] is not True:
            return False
        return True
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return False
