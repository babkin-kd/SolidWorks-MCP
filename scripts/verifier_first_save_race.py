"""Detached L3-I3 receipt gate, not an independent CAD/filesystem oracle."""
from verifier_native_first_save import _json, released_first_save_guard


def verified_race_rollback(job, foreign):
    try:
        _json(job)
        _json(foreign)
        mutation = job['mutation']
        verification = mutation['verification']
        before = mutation['before_state']
        after = verification['evidence']['after']
        if (job['status'] != 'failed' or job['operation'] != 'document.first_save_native'
                or job['error']['code'] != 'first_save_publication_failed'
                or job['error']['requires_reconciliation'] is not False
                or mutation['phase'] != 'rolled_back' or verification['outcome'] != 'rolled_back'
                or before.get('_mutation_effect_scope') != 'application'
                or not released_first_save_guard(verification['evidence']['execution_guard'], before)
                or _json(after['semantic']) != _json(before['semantic'])
                or _json(after['snapshots']) != _json(before['snapshots'])
                or _json(after['original_files']) != _json(before['semantic']['files'])
                or any(after[key] is not False for key in ('pending', 'pending_release', 'journal_failed'))
                or after['stage']['empty'] is not True or after['stage']['file'] is not None
                or after['cleanup']['destination_removed'] is not False
                or after['cleanup']['file_removed'] is not True
                or after['published']['status'] != 'conflict'
                or after['published']['pending_publication'] is not False
                or after['published']['uncertain'] is not False
                or after['destination_file']['sha256'] != foreign['sha256']
                or _json(after['destination_file']['identity']) != _json(foreign['identity'])
                or type(foreign['size']) is not int or foreign['size'] <= 0
                or after['destination_file']['bytes'] != foreign['size']):
            return False
        steps = verification['native_steps']
        if type(steps) is not list or not 12 <= len(steps) <= 18 or len(steps) % 2:
            return False
        names = []
        for index in range(0, len(steps), 2):
            pending, returned = steps[index:index+2]
            if (type(pending['sequence']) is not int or pending['sequence'] != index+1
                    or type(returned['sequence']) is not int or returned['sequence'] != index+2
                    or pending['phase'] != 'pending' or returned['phase'] != 'returned'
                    or pending['name'] != returned['name']):
                return False
            names.append(returned['name'])
            evidence = returned['evidence']
            if returned['name'] in ('first_save_copy_native', 'first_save_open_stage_native', 'first_save_close_stage_native'):
                flag = {'first_save_copy_native': 'pending_copy', 'first_save_open_stage_native': 'pending_open',
                        'first_save_close_stage_native': 'pending_close'}[returned['name']]
                if (evidence['native_call_attempted'] is not True or evidence[flag] is not False
                        or evidence['native_call_returned'] is not True or evidence['acknowledgement_valid'] is not True):
                    return False
                if returned['name'] != 'first_save_close_stage_native':
                    if any(type(evidence[key]) is not int or evidence[key] != 0 for key in ('errors', 'warnings')):
                        return False
                if returned['name'] == 'first_save_copy_native' and evidence['success'] is not True:
                    return False
        required = ['first_save_stage_create', 'first_save_copy_native', 'first_save_open_stage_native',
                    'first_save_close_stage_native', 'first_save_publish', 'first_save_cleanup_stage']
        optional = {'first_save_release_survivor_ui', 'first_save_activate_source_native', 'first_save_restore_directory_native'}
        if (len(set(names)) != len(names) or any(name not in required and name not in optional for name in names)
                or [name for name in names if name in required] != required):
            return False
        publication = next(row['evidence']['publication'] for row in steps
                           if row['name'] == 'first_save_publish' and row['phase'] == 'returned')
        return (publication['status'] == 'conflict' and publication['published'] is False
                and publication['destination'] == before['destination']['destination']
                and publication['destination'] == job['payload']['arguments']['filename'])
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, StopIteration):
        return False
