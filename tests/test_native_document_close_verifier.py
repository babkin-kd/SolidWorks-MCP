"""Clean-close checkpoint must prove only the exact survivor guard release."""
from copy import deepcopy
import pytest
from test_verifier_lifecycle import helper,checkpoint,decision,MODEL_GUARD,guard


def close_checkpoint(survivors=1):
    owner,row=checkpoint(census_count=survivors+1,operation='document.close_native',scope='native_document_close_clean_v1')
    before=row['mutation']['before_state']
    before['impact']=dict(target_document_id='doc_0',retiring_document_ids=['doc_0'],
        survivor_document_ids=[f'doc_{index}' for index in range(1,survivors+1)],policy='require_clean',data_unload_claimed=False)
    row['mutation']['verification']['evidence']['execution_guard']=dict(
        scope='application_document_close_guard_v1',original_command_in_progress=False,acquired=True,released=True,
        selection_preserved=True,model_guards=[dict(MODEL_GUARD) for _ in range(survivors)],
        retiring_document_ids=['doc_0'],retiring_targets_locked_during_close=False,
        activation_ui_release=dict(attempted=False,verified=False))
    return owner,row


@pytest.mark.parametrize('survivors',[0,1,4])
def test_exact_survivor_count_allows_cleanup(survivors):
    owner,row=close_checkpoint(survivors)
    assert decision(owner,row).fixture_can_cleanup


@pytest.mark.parametrize('fault',['target_locked','target_ids','extra_guard','missing_guard','scope','other_operation',
                                'overlap','unknown_survivor','missing_target','dirty_policy','unload_claim','release','fallback'])
def test_incomplete_close_evidence_keeps_fixtures(fault):
    owner,row=close_checkpoint();before=row['mutation']['before_state']
    evidence=row['mutation']['verification']['evidence'];g=evidence['execution_guard'];impact=before['impact']
    if fault=='target_locked':g['retiring_targets_locked_during_close']=True
    if fault=='target_ids':g['retiring_document_ids']=['doc_1']
    if fault=='extra_guard':g['model_guards'].append(dict(MODEL_GUARD))
    if fault=='missing_guard':g['model_guards']=[]
    if fault=='scope':before['scope']='other_scope'
    if fault=='other_operation':
        row['operation']='document.save_native'
        assert not owner._decide([row]).fixture_can_cleanup
        return
    if fault=='overlap':impact['survivor_document_ids']=['doc_0']
    if fault=='unknown_survivor':impact['survivor_document_ids']=['doc_foreign']
    if fault=='missing_target':impact['target_document_id']='doc_foreign'
    if fault=='dirty_policy':impact['policy']='discard'
    if fault=='unload_claim':impact['data_unload_claimed']=True
    if fault=='release':g['model_guards'][0]['released_state']=2
    if fault=='fallback':evidence['execution_guard']=guard(1)
    assert not decision(owner,row).fixture_can_cleanup


@pytest.mark.parametrize('release',[{'attempted':True,'verified':False},{'attempted':False,'verified':True},
                                  {'attempted':1,'verified':True},None,{}])
def test_unconfirmed_activation_ui_release_retains_fixtures(release):
    owner,row=close_checkpoint()
    row['mutation']['verification']['evidence']['execution_guard']['activation_ui_release']=release
    assert not decision(owner,row).fixture_can_cleanup


def test_verified_ui_release_bound_to_requested_survivor_allows_cleanup():
    owner,row=close_checkpoint();row['mutation']['before_state']['impact']['active_after_document_id']='doc_1'
    row['mutation']['verification']['evidence']['execution_guard']['activation_ui_release']=dict(attempted=True,verified=True)
    assert decision(owner,row).fixture_can_cleanup
    row['mutation']['before_state']['impact']['active_after_document_id']='doc_foreign'
    assert not decision(owner,row).fixture_can_cleanup
