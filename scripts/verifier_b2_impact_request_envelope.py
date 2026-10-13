"""Whole synchronous finite-refusal event envelope on two original live parts.

No connection, wait, cancellation, CAD cleanup, retry or reconciliation. Watches
span both captures AND dispatch, so equal endpoint snapshots cannot hide ABA.
Actual SQL binding is deliberately the native owner's separate responsibility.
"""
import inspect
import json
import math
import re

from solidworks_mcp.jobs import _json
from verifier_b2_impact_refusal import ERROR_CODES
from verifier_b2_impact_session import same_refused_session


SCOPE='b2_impact_whole_request_event_envelope_v1'
DTO_FIELDS={'operation_id','request_id','operation','payload','status','created_at','updated_at','result','error'}


class RequestEnvelopeGate(ValueError):
    pass


def _require(condition,message):
    if not condition:raise RequestEnvelopeGate(message)


def _detached(value):
    return json.loads(_json(value))


def _finite_job(job,binding,expected_code):
    _require(type(job) is dict and set(job)==DTO_FIELDS,'Actual complete failed DTO without checkpoint/pending/extra fields required.')
    _detached(job)
    _require(type(job['payload']) is dict and set(job['payload'])=={'arguments','context','mutates'}
        and type(job['payload']['arguments']) is dict and type(job['payload']['context']) is dict
        and type(job['payload']['mutates']) is bool,'Exact typed durable arguments/context/mutates required.')
    arguments=dict(document_id=binding.document_id,configuration=binding.configuration,object_id=binding.object_id)
    mutation=job['operation']=='feature.delete_leaf'
    _require(job['operation'] in ('feature.prepare_leaf_deletion','feature.delete_leaf'),
             'Only finite own leaf preview/delete refusals are covered.')
    if mutation:
        revision=job['payload']['arguments'].get('expected_revision')
        _require(type(revision) is str and re.fullmatch(r'rev_[0-9a-f]{64}',revision) is not None,
                 'Mutation refusal requires its valid original BASE revision argument.')
        arguments['expected_revision']=revision
    _require(job['status']=='failed' and job['result'] is None
        and type(job['payload']) is dict and set(job['payload'])=={'arguments','context','mutates'}
        and job['payload']['mutates'] is mutation and _json(job['payload']['arguments'])==_json(arguments)
        and _json(job['payload']['context'])==_json(arguments),
        'Only exact normally returned finite original-target preview/delete refusals without a checkpoint permit an after-read.')
    error=job['error']
    _require(type(error) is dict and set(error)=={'code','message','requires_reconciliation'}
        and error['code']==expected_code and error['requires_reconciliation'] is False
        and type(error['message']) is str and bool(error['message'].strip()),
        'Unknown/uncertain/unsupported error cannot authorize another observation.')
    _require(all(type(job[key]) is str and bool(job[key]) for key in ('operation_id','request_id'))
        and all(type(job[key]) in (int,float) and math.isfinite(job[key]) for key in ('created_at','updated_at')),
        'Actual operation/request IDs and finite durable timestamps required.')
    return _detached(job)


def run_observed_refusal(session,dispatch,*,expected_code,progress=None):
    """Own two watches before capture; one dispatch, then one finite after-read.

progress receives {scope,label,phase}, before/after each synchronous read or
dispatch. A marker exception propagates immediately; no later capture/dispatch
is attempted. Finally closes only locally acquired monitors, even on unknown.
The neighbor configuration is retained from the request-start native getter;
all target binding identities remain the original B1 owner-issued identities.
"""
    _require(type(expected_code) is str and expected_code in ERROR_CODES,'Exact finite refusal code required.')
    _require(callable(dispatch) and not inspect.iscoroutinefunction(dispatch)
        and callable(session.capture) and not inspect.iscoroutinefunction(session.capture),
        'Trusted synchronous owner capture/dispatch callbacks required.')
    _require(progress is None or (callable(progress) and not inspect.iscoroutinefunction(progress)),
             'Optional trusted synchronous progress callback required.')
    adapter=session.adapter;binding=session.target.binding
    models=(binding.model,session.neighbor.model)
    documents=(binding.document_id,session.neighbor.document_id)
    configurations=(binding.configuration,session.before['configuration'])
    original_models=(binding.model_identity,session.neighbor_identity)
    watches=[];starts=[];primary=None;result=None

    def call(label,callback):
        pending_gate()
        if progress is not None:
            receipt=progress(dict(scope=SCOPE,label=label,phase='before'))
            _require(not inspect.isawaitable(receipt),'Progress persistence must synchronously acknowledge the marker.')
        pending_gate()
        value=callback()
        pending_gate()
        _require(not inspect.isawaitable(value),'Synchronous callback returned an awaitable; do not await/retry.')
        if progress is not None:
            receipt=progress(dict(scope=SCOPE,label=label,phase='after'))
            _require(not inspect.isawaitable(receipt),'Progress persistence must synchronously acknowledge the marker.')
        pending_gate()
        return value

    def poll(index,label):
        value=call(label,lambda:watches[index].poll())
        _require(type(value) is int and value>=0,'Live typed native watcher counter required.')
        return value

    def pending_gate():
        fixture=session.target.fixture
        _require(fixture.pending_native_step is None and fixture.journal_failed is False,
                 'Pending native/ledger marker forbids further capture or dispatch.')

    def state(stage):
        identities=[];metadata=[]
        for index,model in enumerate(models):
            identity=call(stage+'_model_'+str(index),lambda model=model:adapter.identity(model))
            configuration_identity=call(stage+'_configuration_'+str(index),
                lambda model=model,index=index:adapter.configuration_identity(model,configurations[index]))
            _require(identity==original_models[index] and configuration_identity==original_configurations[index],
                     'Original model/configuration canonical incarnation changed across the request.')
            identities.append((identity,configuration_identity))
            observed=_detached(call(stage+'_metadata_'+str(index),lambda model=model:adapter.snapshot(model)))
            _require(type(observed) is dict and bool(observed),'Actual current native metadata object is unavailable.')
            metadata.append(observed)
        counters=[poll(index,stage+'_watch_'+str(index)) for index in range(2)]
        _require(counters==starts,'A native event occurred across the request, including an edit-and-undo ABA.')
        return metadata,counters

    try:
        pending_gate()
        # Save each resource before the after-marker: persistence loss must not
        # lose the local watch handle that finally is responsible for closing.
        for index,model in enumerate(models):
            def attach(model=model):
                watch=adapter.watch_part(model)
                watches.append(watch)
                return watch
            call('watch_attach_'+str(index),attach)
            starts.append(poll(index,'watch_start_'+str(index)))
        original_configurations=(binding.configuration_identity,
            call('retain_neighbor_configuration',lambda:adapter.configuration_identity(models[1],configurations[1])))
        _require(all(identity is not None for identity in (*original_models,*original_configurations))
            and original_models[0]!=original_models[1],'Two original retained model/configuration identities required.')
        original_metadata,_=state('opening')
        before=_detached(call('capture_before',session.capture))
        prior_metadata,_=state('before_dispatch')
        _require(_json(prior_metadata)==_json(original_metadata),'Native metadata changed during the first capture.')
        pending_gate()
        job=_finite_job(call('dispatch',dispatch),binding,expected_code)
        # This branch is unreachable after queued/running/unknown, a callback
        # exception, failed marker persistence or any pending native marker.
        pending_gate()
        after=_detached(call('capture_after',session.capture))
        closing_metadata,ends=state('closing')
        pending_gate()
        _require(_json(closing_metadata)==_json(original_metadata),
                 'Original complete native metadata changed across the refused request.')
        _require(same_refused_session(before,after) is True,'Complete refused-session comparison is unconfirmed.')
        result=dict(scope=SCOPE,before=before,after=after,job=job,
            event_envelope=dict(scope=SCOPE,original_model_configuration_canonical_confirmed=True,
                snapshot_metadata_unchanged=True,whole_request_event_counters_unchanged=True,
                documents=[dict(document_id=documents[index],configuration=configurations[index],
                    before_sequence=starts[index],after_sequence=ends[index]) for index in range(2)]),
            accepted=False,native_b2_accepted=False,public_mcp_accepted=False,cleanup_authorized=False,
            full_refusal_context_available=False,
            open_gates=['bound_actual_SQL_refusal_and_replay','terminal_fixture_journal_and_own_cleanup'])
    except BaseException as error:
        primary=error
        raise
    finally:
        errors=[]
        for watch in reversed(watches):
            try:watch.close()
            except BaseException as error:errors.append(error)
        if errors:
            if primary is not None:
                for error in errors:primary.add_note('Owned watch close unconfirmed: '+type(error).__name__)
            else:
                for error in errors[1:]:errors[0].add_note('Additional owned watch close unconfirmed: '+type(error).__name__)
                raise errors[0]
    return result
