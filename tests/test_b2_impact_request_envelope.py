"""Whole-request watches/actual JobRunner on artificial observer handles only."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.documents import rejected
from solidworks_mcp.jobs import ExecutionFailure,JobRunner
from test_feature_suppression_domain import InlineWorker
from test_b2_impact_session import observer,target,fixture,leaf,extrusion_proof,proof,case,domain

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:import verifier_b2_impact_request_envelope as helper
finally:sys.path.remove(str(scripts))


@pytest.fixture
def observed(observer):
    x=observer;a=x.c.adapter;session=x.session_collector
    x.envelope_watches=[];x.envelope_events=[0,0];x.envelope_captures=[];x.envelope_dispatches=[]
    x.envelope_markers=[];x.watch_fault=None;x.close_fault=None
    x.neighbor_configuration=object()
    original_configuration=a.configuration_identity
    a.configuration_identity=lambda model,cfg:original_configuration(model,cfg) if model is x.binding.model else x.neighbor_configuration
    class Watch:
        def __init__(self,index):self.index=index;self.closed=False
        def poll(self):
            assert not self.closed
            if x.watch_fault=='poll':raise RuntimeError('Artificial event monitor lost')
            if x.watch_fault=='bool':return False
            return x.envelope_events[self.index]
        def close(self):
            assert not self.closed
            self.closed=True
            if self.index==x.close_fault:raise RuntimeError('Artificial own monitor close failed')
    original_watch=a.watch_part
    def watch(model):
        # Only the first two monitors are the outer request envelope. Target
        # and FeatureCatalog still use their actual artificial observer watch.
        if len(x.envelope_watches)>=2:return original_watch(model)
        index=0 if model is x.binding.model else 1
        if x.watch_fault=='second_attach' and index==1:raise RuntimeError('Artificial second monitor unavailable')
        value=Watch(index);x.envelope_watches.append(value);return value
    a.watch_part=watch
    capture=session.capture
    def current_capture():
        assert len(x.envelope_watches)==2 and all(not watch.closed for watch in x.envelope_watches)
        x.envelope_captures.append(True)
        return capture()
    session.capture=current_capture
    x.progress=lambda marker:x.envelope_markers.append(deepcopy(marker))
    def dispatch(*,operation='feature.prepare_leaf_deletion',code='first_save_snapshot_unsupported',changed=None,request_id=None):
        x.envelope_dispatches.append(operation)
        arguments=dict(document_id=x.binding.document_id,configuration=x.binding.configuration,object_id=x.binding.object_id)
        if operation=='feature.delete_leaf':arguments['expected_revision']='rev_'+'a'*64
        if changed is not None:changed()
        def refusal():raise rejected(code,'Actual artificial dependent fixture refuses the finite operation.')
        return JobRunner(x.store,InlineWorker()).submit(request_id or 'observed_'+operation,operation,arguments,refusal,
            context=arguments,mutates=operation=='feature.delete_leaf',
            verify=lambda result:pytest.fail('Known finite prewrite refusal cannot reach a postcondition verifier'))
    x.dispatch=dispatch
    return x


@pytest.mark.parametrize('operation',['feature.prepare_leaf_deletion','feature.delete_leaf'])
def test_real_two_model_observer_and_jobrunner_keep_whole_request_events_and_original_data_exact(observed,operation):
    x=observed;writes=list(x.write_calls)
    result=helper.run_observed_refusal(x.session_collector,lambda:x.dispatch(operation=operation),
        expected_code='first_save_snapshot_unsupported',progress=x.progress)
    assert result['before']==result['after'] and result['job']==x.store.get(result['job']['operation_id'])
    assert result['job']['status']=='failed' and 'mutation' not in result['job']
    assert len(x.envelope_captures)==2 and len(x.envelope_dispatches)==1
    assert all(watch.closed for watch in x.envelope_watches) and x.write_calls==writes
    envelope=result['event_envelope']
    assert envelope['whole_request_event_counters_unchanged'] is envelope['snapshot_metadata_unchanged'] is True
    assert [row['document_id'] for row in envelope['documents']]==['target','neighbor']
    assert all(result[key] is False for key in ('accepted','native_b2_accepted','public_mcp_accepted',
        'cleanup_authorized','full_refusal_context_available'))
    assert [marker['phase'] for marker in x.envelope_markers]==['before','after']*(len(x.envelope_markers)//2)
    result['job']['error']['message']='detached'
    assert x.store.get(result['job']['operation_id'])['error']['message']!='detached'


def test_one_event_envelope_covers_explicit_actual_preview_execute_batch_and_same_request_replays(observed):
    x=observed
    def batch():
        preview=x.dispatch(request_id='batch_preview')
        replay=x.dispatch(request_id='batch_preview')
        assert preview==replay
        execute=x.dispatch(operation='feature.delete_leaf',request_id='batch_execute')
        execute_replay=x.dispatch(operation='feature.delete_leaf',request_id='batch_execute')
        assert execute==execute_replay
        return execute_replay
    result=helper.run_observed_refusal(x.session_collector,batch,expected_code='first_save_snapshot_unsupported')
    assert result['job']['operation']=='feature.delete_leaf' and len(x.envelope_captures)==2
    assert all(watch.closed for watch in x.envelope_watches)


@pytest.mark.parametrize('fault',['target_ABA','neighbor_ABA','target_model','neighbor_model','target_configuration',
    'neighbor_configuration','target_metadata','neighbor_metadata','actual_session_data'])
def test_events_identity_metadata_or_current_session_changes_across_dispatch_cannot_be_hidden_by_equal_endpoints(observed,fault):
    x=observed;a=x.c.adapter
    def change():
        if fault=='target_ABA':x.envelope_events[0]+=2
        elif fault=='neighbor_ABA':x.envelope_events[1]+=2
        elif fault=='target_model':x.binding.model.identity=object()
        elif fault=='neighbor_model':x.session_collector.neighbor.model.identity=object()
        elif fault=='target_configuration':x.c.configuration_identity=object()
        elif fault=='neighbor_configuration':x.neighbor_configuration=object()
        elif fault in ('target_metadata','neighbor_metadata'):
            original=a.snapshot
            target_model=x.binding.model if fault=='target_metadata' else x.session_collector.neighbor.model
            a.snapshot=lambda model:{**original(model),'unknown_actual_native_field':1} if model is target_model else original(model)
        else:x.application['current_directory']='C:/changed/'
    with pytest.raises((helper.RequestEnvelopeGate,ExecutionFailure,ValueError)):
        helper.run_observed_refusal(x.session_collector,lambda:x.dispatch(changed=change),
            expected_code='first_save_snapshot_unsupported')
    assert len(x.envelope_dispatches)==1 and all(watch.closed for watch in x.envelope_watches)


@pytest.mark.parametrize('fault',['queued','running','unknown','succeeded','other_code','reconciliation','numeric_reconciliation',
    'mutation','result','extra_pending','wrong_scope','wrong_mutates','invalid_revision','fixture_pending','fixture_journal'])
def test_nonfinite_unsupported_or_pending_return_never_dispatches_after_read_retry_or_cleanup(observed,fault):
    x=observed;writes=list(x.write_calls)
    def dispatch():
        row=x.dispatch(operation='feature.delete_leaf')
        if fault in ('queued','running','unknown','succeeded'):row['status']=fault
        elif fault=='other_code':row['error']['code']='dispatch_failed'
        elif fault=='reconciliation':row['error']['requires_reconciliation']=True
        elif fault=='numeric_reconciliation':row['error']['requires_reconciliation']=0
        elif fault=='mutation':row['mutation']=None
        elif fault=='result':row['result']={}
        elif fault=='extra_pending':row['pending_native_step']='setter'
        elif fault=='wrong_scope':row['payload']['arguments']['object_id']='foreign'
        elif fault=='wrong_mutates':row['payload']['mutates']=False
        elif fault=='invalid_revision':row['payload']['arguments']['expected_revision']='revision_hint'
        elif fault=='fixture_pending':x.helper.pending_native_step='unreturned'
        else:x.helper.journal_failed=True
        return row
    with pytest.raises(helper.RequestEnvelopeGate):helper.run_observed_refusal(x.session_collector,dispatch,
        expected_code='first_save_snapshot_unsupported')
    assert len(x.envelope_captures)==1 and len(x.envelope_dispatches)==1 and x.write_calls==writes
    assert all(watch.closed for watch in x.envelope_watches)


@pytest.mark.parametrize('label,phase',[('watch_attach_0','after'),('watch_start_1','before'),
    ('capture_before','before'),('capture_before','after'),('dispatch','before'),('dispatch','after'),
    ('capture_after','before'),('capture_after','after')])
def test_progress_persistence_exception_stops_at_exact_boundary_and_still_closes_only_owned_monitors(observed,label,phase):
    x=observed
    def progress(marker):
        x.envelope_markers.append(marker)
        if marker['label']==label and marker['phase']==phase:raise OSError('Artificial progress receipt write failed')
    with pytest.raises(OSError):helper.run_observed_refusal(x.session_collector,x.dispatch,
        expected_code='first_save_snapshot_unsupported',progress=progress)
    assert all(watch.closed for watch in x.envelope_watches)
    expected_captures=0 if label.startswith('watch') or (label=='capture_before' and phase=='before') else (
        2 if label=='capture_after' and phase=='after' else 1)
    assert len(x.envelope_captures)==expected_captures
    assert len(x.envelope_dispatches)==(0 if label.startswith('watch') or label=='capture_before'
        or (label=='dispatch' and phase=='before') else 1)


@pytest.mark.parametrize('fault',['second_attach','poll','bool'])
def test_missing_or_untyped_live_event_monitor_prevents_capture_or_dispatch(observed,fault):
    x=observed;x.watch_fault=fault
    with pytest.raises((RuntimeError,helper.RequestEnvelopeGate)):helper.run_observed_refusal(x.session_collector,x.dispatch,
        expected_code='first_save_snapshot_unsupported')
    assert x.envelope_captures==x.envelope_dispatches==[] and all(watch.closed for watch in x.envelope_watches)


def test_callback_throw_and_monitor_close_error_preserve_primary_failure_without_any_after_read(observed):
    x=observed;x.close_fault=0
    def dispatch():raise OSError('Actual dispatch acknowledgement lost')
    with pytest.raises(OSError,match='acknowledgement lost') as error:helper.run_observed_refusal(x.session_collector,dispatch,
        expected_code='first_save_snapshot_unsupported')
    assert len(x.envelope_captures)==1 and all(watch.closed for watch in x.envelope_watches)
    assert any('watch close unconfirmed' in note for note in error.value.__notes__)


def test_failed_watch_close_prevents_return_of_successful_observation_envelope(observed):
    x=observed;x.close_fault=0
    with pytest.raises(RuntimeError,match='monitor close failed'):helper.run_observed_refusal(x.session_collector,x.dispatch,
        expected_code='first_save_snapshot_unsupported')
    assert len(x.envelope_captures)==2 and all(watch.closed for watch in x.envelope_watches)


def test_final_pending_marker_cannot_be_hidden_by_normal_second_capture(observed):
    x=observed;original=x.session_collector.capture
    def capture():
        value=original()
        if len(x.envelope_captures)==2:x.helper.pending_native_step='unreturned_observation'
        return value
    x.session_collector.capture=capture
    with pytest.raises(helper.RequestEnvelopeGate,match='Pending'):
        helper.run_observed_refusal(x.session_collector,x.dispatch,expected_code='first_save_snapshot_unsupported',progress=x.progress)
    assert len(x.envelope_captures)==2 and all(watch.closed for watch in x.envelope_watches)
    assert not any(marker['label'].startswith('closing') for marker in x.envelope_markers)


def test_async_progress_function_is_refused_before_any_native_read_or_dispatch(observed):
    x=observed
    async def progress(marker):pass
    with pytest.raises(helper.RequestEnvelopeGate,match='synchronous progress'):
        helper.run_observed_refusal(x.session_collector,x.dispatch,expected_code='first_save_snapshot_unsupported',progress=progress)
    assert x.envelope_watches==x.envelope_captures==x.envelope_dispatches==[]

