"""Own-fixture body name correction after a normally completed suppression cycle.

Only an independently captured delta confined to body/name is admitted. This
test-owner bridge is not an installed tool or B2 acceptance. The caller must
capture the complete restored phase again after any write.
"""
from copy import deepcopy

from solidworks_mcp.jobs import _json


def restore_owned_body_name(observer, before, restored, report, persist, release_check):
    from verifier_b2_suppression_probe import _session
    def require(value, message):
        if not value: raise ValueError(message)
    first, current = before['full_snapshot'], restored['full_snapshot']
    if _json(first) == _json(current):
        return False
    name, old_name = first['clone_state']['body']['name'], current['clone_state']['body']['name']
    patched = deepcopy(current)
    patched['clone_state']['body']['name'] = name
    require(name != old_name and _json(patched) == _json(first),
            'Only a fully observed own body/name delta permits this correction.')
    owner = observer.owner
    require(before['feature_identity_tokens'] == restored['feature_identity_tokens']
            and restored['resolver'] == before['resolver'] and restored['is_suppressed2'] == [False],
            'Original feature canonical census/PID must survive unsuppress.')
    require(_json(_session(before['session'], owner['document_id'], owner['configuration'], owner['owned_document_ids']))
            == _json(_session(restored['session'], owner['document_id'], owner['configuration'], owner['owned_document_ids'])),
            'Complete neighbor/session baseline must survive before correction.')
    refs = [r for r in first['references'] if r['kind'] == 'body']
    require(len(refs) == 1 and refs[0]['role'] == 'body:0', 'One original exact body PID required.')
    pid = bytes.fromhex(refs[0]['token'])
    adapter, model = observer.adapter, observer.model
    facts = dict(scope='own_body_name_after_suppression_v1', document_id=owner['document_id'],
        configuration=owner['configuration'], body_pid_hex=pid.hex(),
        previous_name=old_name, restored_name=name, pending=False, native_call_attempted=False,
        native_call_returned=False, readback_verified=False)
    report['body_name_restoration'] = facts
    report.update(phase='restore_owned_body_name', native_calls_live=True); persist()
    guard = adapter.mutation_guard(model)
    with guard:
        entry, observed = observer.documents.resolve(owner['document_id'], owner['configuration'])
        require(entry.identity == observer.document_identity
                and adapter.identity(model) == observer.document_identity
                and adapter.configuration_identity(model, owner['configuration']) == observer.configuration_identity
                and adapter.identity(adapter.active_document()) == observer.document_identity,
                'Exact owned active document/configuration required before body write.')
        captured = next(r for r in restored['session']['semantic']['documents']
                        if r['document_id'] == owner['document_id'])
        metadata = adapter.snapshot(model)
        require(metadata == {key: captured[key] for key in metadata},
                'Owned metadata changed after independent full observation.')
        feature = observer.resolve_feature()
        require(adapter.identity(feature) == observer.feature_identity
                and list(feature.IsSuppressed2(1, None)) == [False],
                'Exact owned feature must remain unsuppressed.')
        body = adapter.resolve_persistent_id(model, pid, 'body')
        members = adapter.bodies(model, 'all')
        require(len(members) == 1 and adapter.identity(members[0]) == adapter.identity(body)
                and adapter.persistent_id(model, body) == pid and body.Name == old_name,
                'One exact current own body and unchanged observed name required.')
        facts.update(native_call_attempted=True, pending=True); persist()
        body.Name = name
        facts.update(native_call_returned=True, pending=False); persist()
        require(body.Name == name, 'Own body name readback failed.')
        facts['readback_verified'] = True; persist()
    facts['execution_guard'] = release_check(guard, adapter._sw)
    report['native_calls_live'] = False; persist()
    return True
