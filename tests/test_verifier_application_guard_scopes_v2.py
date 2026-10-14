"""Cleanup contracts for the new scope; no CAD or weakened release proof."""

from copy import deepcopy

import pytest

from test_verifier_fixture_cleanup_v2 import utility, terminal, GUARD
from test_verifier_lifecycle_v2 import helper


def model_guard():
    return {'scope':'application_model_mutation_guard_v1','original_command_in_progress':False,
        'acquired':True,'released':True,'model_guards':[dict(GUARD)],'selection_preserved':True}


@pytest.mark.parametrize('validator',[utility['_released_guard'],helper.released_execution_guard])
def test_new_model_scope_requires_one_complete_model_lock_and_exact_flag_release(validator):
    assert validator(model_guard())
    for key,value in [('scope','unknown_scope'),('original_command_in_progress',True),('acquired',1),
            ('released',False),('selection_preserved',False),('model_guards',[]),
            ('model_guards',[dict(GUARD),dict(GUARD)]),('model_guards',[{'released_state':0}])]:
        row=model_guard(); row[key]=value
        assert not validator(row)
    row=model_guard(); row['extra']=True
    assert not validator(row)
    assert not validator({**GUARD,'scope':'invented'})


def test_known_terminal_model_scope_allows_fixture_gate_but_unknown_stays_held():
    row=terminal(); row['result']['execution_guard']=model_guard()
    row['mutation']['verification']['evidence']['execution_guard']=model_guard()
    assert utility['inline_job_cleanup_proven'](row)
    row['status']='unknown'
    assert not utility['inline_job_cleanup_proven'](row)


def busy_guard():
    return {'scope':'application_model_mutation_guard_v1','original_command_in_progress':True,
        'acquired':False,'released':False,'model_guards':[],'selection_preserved':False}


@pytest.mark.parametrize('validator',[utility['untouched_busy_guard'],helper.untouched_busy_guard])
def test_unacquired_busy_scope_is_distinct_from_release_and_typed(validator):
    assert validator(busy_guard())
    assert not helper.released_execution_guard(busy_guard())
    for key,value in [('original_command_in_progress',1),('acquired',0),('released',0),
            ('model_guards',()),('model_guards',[dict(GUARD)]),('selection_preserved',True),('scope','unknown')]:
        row=busy_guard(); row[key]=value
        assert not validator(row)


@pytest.mark.parametrize('fault',[None,'status','phase','code','started','reconciliation','guard','missing_error'])
def test_busy_only_proves_no_owned_effect_for_known_failed_not_started_job(fault):
    row=terminal('failed','not_started')
    row['error']['code']='application_busy'
    row['mutation']['verification']['evidence']={'execution_guard':busy_guard(),'native_mutation_started':False}
    if fault=='status': row['status']='unknown'
    if fault=='phase': row['mutation']['phase']=row['mutation']['verification']['outcome']='rolled_back'
    if fault=='code': row['error']['code']='different_failure'
    if fault=='started': row['mutation']['verification']['evidence']['native_mutation_started']=True
    if fault=='reconciliation': row['error']['requires_reconciliation']=True
    if fault=='guard': row['mutation']['verification']['evidence']['execution_guard']['acquired']=True
    if fault=='missing_error': row['error']=None
    assert utility['inline_job_cleanup_proven'](row)==(fault is None)
