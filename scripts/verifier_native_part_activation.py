"""Detached activation receipt/guard/ledger gates; never a native CAD oracle."""

from copy import deepcopy
import hashlib
import json


SCOPE = 'native_rectangular_part_activation_v1'
GUARD_SCOPE = 'native_part_activation_guard_v1'
NATIVE_GUARD_SCOPE = 'application_document_open_guard_v1'


def _json(value):
    def check(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError('Only detached JSON keys are accepted.')
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, int, bool, float):
            raise ValueError('Only detached JSON values are accepted.')
    check(value)
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _baseline_ids(before):
    if type(before) is not dict or before.get('scope') != SCOPE:
        return None
    rows = before.get('semantic', {}).get('documents')
    if type(rows) is not list or not 1 <= len(rows) <= 4999 or any(type(row) is not dict for row in rows):
        return None
    ids = [row.get('document_id') for row in rows]
    if (any(type(item) is not str or not item.strip() for item in ids)
            or len(set(ids)) != len(ids) or before.get('document_id') not in ids):
        return None
    return ids


def _supported_before(before):
    ids = _baseline_ids(before)
    if (ids is None or set(before) != {'scope', 'connection_epoch', 'document_id', 'configuration', 'semantic', 'snapshots'}
            or type(before['connection_epoch']) is not str or not before['connection_epoch']
            or type(before['configuration']) is not str or not before['configuration']
            or type(before['snapshots']) is not dict or set(before['snapshots']) != set(ids)
            or before['semantic'].get('reference_graph') != []):
        return False
    keys = {'scope', 'configuration', 'configurations', 'solid_body_count', 'selection_count',
            'clone_state', 'references', 'native_observations'}
    for row in before['semantic']['documents']:
        snapshot = before['snapshots'][row['document_id']]
        if (row['document_type'] != 'part' or row['visible'] is not True or row['dependencies'] != []
                or type(snapshot) is not dict or set(snapshot) != keys
                or snapshot['scope'] != 'native_first_save_part_snapshot_v1'
                or type(snapshot['configuration']) is not str or not snapshot['configuration']
                or snapshot['configurations'] != [snapshot['configuration']]
                or row['configurations'] != snapshot['configurations']
                or row['active_configuration'] != snapshot['configuration']
                or type(snapshot['solid_body_count']) is not int or snapshot['solid_body_count'] != 1
                or type(snapshot['selection_count']) is not int or not 0 <= snapshot['selection_count'] <= 5000
                or type(snapshot['clone_state']) is not dict
                or snapshot['clone_state'].get('profile') != 'single_rectangular_blind_base_v1'
                or type(snapshot['native_observations']) is not dict
                or type(snapshot['references']) is not list or not 1 <= len(snapshot['references']) <= 5000):
            return False
        roles, tokens = set(), set()
        for ref in snapshot['references']:
            if (type(ref) is not dict or set(ref) != {'kind', 'role', 'token'}
                    or any(type(value) is not str or not value.strip() for value in ref.values())
                    or (ref['kind'], ref['role']) in roles or ref['token'] in tokens):
                return False
            roles.add((ref['kind'], ref['role']))
            tokens.add(ref['token'])
    target = next(row for row in before['semantic']['documents'] if row['document_id'] == before['document_id'])
    return (target['active_configuration'] == before['configuration']
            and type(target['mode']['read_only_state']) is int and target['mode']['read_only_state'] == 0
            and sum(row['document_id'] == before['document_id'] for row in before['semantic']['windows']) == 1)


def released_part_activation_guard(guard, before):
    try:
        _json(guard)
        ids = _baseline_ids(before)
        keys = {'scope', 'native_guard', 'pending_guard_release', 'guard_release_attempted',
                'guard_released', 'full_release_check'}
        if (ids is None or type(guard) is not dict or set(guard) != keys or guard['scope'] != GUARD_SCOPE
                or guard['pending_guard_release'] is not False or guard['guard_release_attempted'] is not True
                or guard['guard_released'] is not True or guard['full_release_check'] not in (None, 'effect', 'restored')):
            return False
        native = guard['native_guard']
        native_keys = {'scope', 'original_command_in_progress', 'acquired', 'released', 'model_guards',
                       'selection_preserved', 'baseline_document_ids', 'activation_ui_release'}
        if (type(native) is not dict or set(native) != native_keys or native['scope'] != NATIVE_GUARD_SCOPE
                or native['original_command_in_progress'] is not False or native['acquired'] is not True
                or native['released'] is not True or native['selection_preserved'] is not True
                or type(native['baseline_document_ids']) is not list
                or any(type(item) is not str for item in native['baseline_document_ids'])
                or len(native['baseline_document_ids']) != len(ids) or set(native['baseline_document_ids']) != set(ids)):
            return False
        # Native guard order is its bound model order, while the census is
        # sorted by opaque IDs. Compare exact membership, not incidental order.
        release, models = native['activation_ui_release'], native['model_guards']
        if (type(release) is not dict or set(release) != {'attempted', 'verified'}
                or not ((release['attempted'] is False and release['verified'] is False)
                        or (release['attempted'] is True and release['verified'] is True))
                or type(models) is not list or len(models) != len(ids)):
            return False
        return all(type(row) is dict and set(row) == {'original_state', 'locked_state', 'released_state'}
                   and all(type(row[key]) is int and row[key] == expected for key, expected in
                           (('original_state', 0), ('locked_state', 2), ('released_state', 0))) for row in models)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def verified_committed_part_activation(job):
    """Positive/no-op protocol only; an independent full CAD readback is mandatory."""
    try:
        _json(job)
        mutation, result = job['mutation'], job['result']
        verification, before, after, value = mutation['verification'], result['before'], result['after'], result['value']
        if (job['operation'] != 'document.activate_part_native' or job['status'] != 'succeeded'
                or job['error'] is not None or job['payload']['mutates'] is not True
                or mutation['phase'] != 'committed' or verification['outcome'] != 'committed'
                or result['verified'] is not True or not _supported_before(before)
                or mutation['before_state'].get('_mutation_effect_scope') != 'application'
                or _json(before) != _json({k: v for k, v in mutation['before_state'].items() if k != '_mutation_effect_scope'})
                or _json(after) != _json(verification['evidence']['after'])
                or _json(result['execution_guard']) != _json(verification['evidence']['execution_guard'])
                or not released_part_activation_guard(result['execution_guard'], before)
                or result['execution_guard']['full_release_check'] != 'effect'):
            return False
        target, cfg = before['document_id'], before['configuration']
        args, context = job['payload']['arguments'], job['payload']['context']
        revision = 'rev_' + hashlib.sha256(_json(before).encode('utf-8')).hexdigest()
        if (mutation['connection_epoch'] != before['connection_epoch']
                or mutation['document_id'] != target or mutation['configuration'] != cfg
                or mutation['expected_revision'] != revision
                or args != {'document_id': target, 'configuration': cfg, 'expected_revision': revision}
                or context != args or value['document_id'] != target or value['configuration'] != cfg
                or value['active_after_document_id'] != target):
            return False
        expected = deepcopy(before['semantic'])
        expected['active_document_id'] = target
        if (_json(after['semantic']) != _json(expected) or _json(after['snapshots']) != _json(before['snapshots'])
                or _json(after['original_files']) != _json(before['semantic']['files'])
                or any(after[key] is not False for key in ('pending_activation', 'pending_release', 'pending_guard_release', 'journal_failed'))):
            return False
        already = before['semantic']['active_document_id'] == target
        native = result['execution_guard']['native_guard']
        if value['already_active'] is not already or value['native_call_attempted'] is not (not already):
            return False
        if native['activation_ui_release'] != {'attempted': not already, 'verified': not already}:
            return False
        names = ([] if already else ['part_activation_release_ui', 'part_activation_native'])
        names += ['part_activation_guard_release', 'part_activation_released_check']
        steps = verification['native_steps']
        if type(steps) is not list or len(steps) != len(names) * 2:
            return False
        pairs = {}
        for index, name in enumerate(names):
            pending, returned = steps[index*2:index*2+2]
            for sequence, row, phase in ((index*2+1, pending, 'pending'), (index*2+2, returned, 'returned')):
                if (type(row) is not dict or set(row) != {'sequence', 'name', 'phase', 'evidence'}
                        or type(row['sequence']) is not int or row['sequence'] != sequence
                        or row['name'] != name or row['phase'] != phase or type(row['evidence']) is not dict):
                    return False
            pairs[name] = pending['evidence'], returned['evidence']
        if (pairs['part_activation_guard_release'][0] != {'document_ids': native['baseline_document_ids']}
                or _json(pairs['part_activation_guard_release'][1]) != _json(native)
                or pairs['part_activation_released_check'][0] != {'document_id': target}
                or pairs['part_activation_released_check'][1].get('verified') is not True
                or _json(pairs['part_activation_released_check'][1]['observed']) != _json(after)):
            return False
        if already:
            return after['receipt'] is None and 'receipt' not in value
        receipt = after['receipt']
        return (pairs['part_activation_release_ui'][0] == {'document_ids': native['baseline_document_ids']}
                and pairs['part_activation_release_ui'][1] == {'verified': True}
                and pairs['part_activation_native'][0] == {'document_id': target, 'configuration': cfg}
                and _json(pairs['part_activation_native'][1]) == _json(receipt)
                and _json(value['receipt']) == _json(receipt)
                and set(receipt) == {'native_call_attempted', 'native_call_returned', 'pending_activation', 'native_error', 'activation_confirmed'}
                and receipt['native_call_attempted'] is True and receipt['native_call_returned'] is True
                and receipt['pending_activation'] is False and receipt['activation_confirmed'] is True
                and type(receipt['native_error']) is int and receipt['native_error'] in (0, 2))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
