"""Original empty-application baseline and later B3 fixture admission.

No connection, guard setter, creation, replay, reconciliation or cleanup. The
root caller owns the adapter/STA/process and all full-session admission/watch
callbacks. Receipts and actual raw returns remain private caller custody.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from threading import get_ident
import json

from verifier_b3_part_fixture import PartFixtureReceipt, FixtureAnchor
from verifier_dimension_diagnostics import _snapshot, assert_non_stl_preferences
from verify_export_operations import PREFS


def require(condition, message):
    if not condition: raise ValueError(message)


@dataclass
class ApplicationAdmissionReceipt:
    thread_id: int = field(default_factory=get_ident)
    attempted: bool = False
    halted: bool = False
    pending_read: str | None = None
    returned_reads: list = field(default_factory=list)
    preference_evidence: dict = field(default_factory=dict)
    baseline: object = None
    baseline_data: object = None
    complete: bool = False
    accepted: bool = False
    native_acceptance: bool = False
    cleanup_authorized: bool = False


@dataclass(frozen=True)
class EmptyApplicationBaseline:
    application: object
    canonical: object
    context: dict
    preferences: dict
    thread_id: int


class _Read:
    def __init__(self, receipt, assert_safe):
        require(type(receipt) is ApplicationAdmissionReceipt and not receipt.attempted
                and not receipt.halted and receipt.pending_read is None and not receipt.returned_reads
                and not receipt.complete and receipt.accepted is False and receipt.native_acceptance is False
                and receipt.cleanup_authorized is False
                and receipt.thread_id == get_ident() and callable(assert_safe), 'Fresh original STA receipt required.')
        self.r,self.safe=receipt,assert_safe
        receipt.attempted=True

    def call(self, label, fn, *args):
        require(get_ident()==self.r.thread_id and not self.r.halted and self.r.pending_read is None
                and len(self.r.returned_reads)<200, 'Unconfirmed/foreign/over-budget application admission remains held.')
        require(self.safe() is True, 'Original root process/STA/session admission required.')
        self.r.pending_read=label
        value=fn(*args)
        self.r.returned_reads.append((label,value))
        self.r.pending_read=None
        return value


def _preferences(value):
    result=_snapshot(value)
    require(set(result)==set(PREFS), 'Complete declared native application preference inventory required.')
    types={'String':str,'Toggle':bool,'Integer':int,'Double':float}
    require(all(type(result[name]) is types[kind] for name,(kind,_) in PREFS.items()),
            'Each actual native preference must retain its declared strict scalar type.')
    return result


def _context(value):
    require(type(value) is dict and set(value)=={'user_control','visible','current_directory','search_folders'}
            and type(value['user_control']) is type(value['visible']) is bool
            and all(type(value[key]) is str and len(value[key])<=4096
                    for key in ('current_directory','search_folders')), 'Complete typed native application context required.')
    return deepcopy(value)


def capture_empty_application(*, receipt, adapter, preference_reader, assert_safe, watch_poll):
    """Initial state before root's separately recorded own guard acquisition."""
    require(callable(preference_reader) and callable(watch_poll), 'Actual preference/watch readers required.')
    reader=_Read(receipt,assert_safe)
    try:
        event=reader.call('open_events',watch_poll)
        app=adapter._sw
        canonical=reader.call('application_canonical',adapter.identity,app)
        require(canonical is not None,'Strong original application canonical required.')
        def capture():
            require(reader.call('current_application',adapter.identity,app)==canonical
                    and reader.call('initial_guard',getattr,app,'CommandInProgress') is False
                    and reader.call('initial_active',getattr,app,'ActiveDoc') is None,
                    'Initial original application must be idle with no active document.')
            models=reader.call('initial_documents',adapter.documents)
            windows=reader.call('initial_windows',adapter.native_close_windows)
            require(type(models) in (tuple,list) and not models
                    and type(windows) in (tuple,list) and not windows, 'Complete empty native document/window census required.')
            context=_context(reader.call('application_context',adapter.native_close_application_context))
            preferences=_preferences(reader.call('application_preferences',preference_reader))
            return context,preferences
        context,preferences=capture()
        closing_context,closing_preferences=capture()
        require(context==closing_context, 'Original application context changed during initial capture.')
        assert_non_stl_preferences(lambda:closing_preferences,preferences,receipt.preference_evidence,'initial_boundary')
        require(reader.call('close_events',watch_poll)==event,'Original empty application event envelope changed.')
        baseline=EmptyApplicationBaseline(app,canonical,context,preferences,receipt.thread_id)
        receipt.baseline=baseline
        receipt.baseline_data=deepcopy((context,preferences))
        receipt.complete=True
        return baseline
    except BaseException:
        receipt.halted=True
        raise


def admit_fixture_application(*, receipt, baseline, baseline_receipt, fixture, prior_fixtures,
                              adapter, preference_reader, assert_safe, watch_poll):
    """Callback before NewDocument, under root's already acquired own guard.

Every earlier document comes from a completed acknowledged original fixture;
an empty roster is allowed only for the first builder. Active document must be
one of those exact original models (None iff empty), never a name/path match.
This only admits fixture startup; full earlier-model data preservation remains
the caller's whole-session producer and cannot be inferred from window equality.
"""
    require(isinstance(baseline,EmptyApplicationBaseline) and type(baseline_receipt) is ApplicationAdmissionReceipt
            and baseline_receipt.complete is True and baseline_receipt.halted is False
            and baseline_receipt.pending_read is None and baseline.thread_id==get_ident()
            and baseline_receipt.thread_id==baseline.thread_id
            and baseline_receipt.baseline is baseline
            and json.dumps(baseline_receipt.baseline_data,sort_keys=True,allow_nan=False)==
                json.dumps((baseline.context,baseline.preferences),sort_keys=True,allow_nan=False)
            and isinstance(fixture,PartFixtureReceipt) and fixture.attempted is True
            and fixture.thread_id==get_ident() and fixture.halted is False and fixture.journal_lost is False
            and fixture.pending_step=='application:admission' and not fixture.documents,
            'Original completed application baseline and fresh pending fixture admission required.')
    require(type(prior_fixtures) is tuple and len(prior_fixtures)<=3
            and all(isinstance(prior,PartFixtureReceipt) and prior is not fixture
                and prior.thread_id==get_ident() and prior.attempted is True and prior.setup_complete is True
                and prior.halted is False and prior.pending_step is None and prior.journal_lost is False
                and prior.documents and prior.native_returns for prior in prior_fixtures), 'Completed acknowledged earlier original fixtures required.')
    require(callable(preference_reader) and callable(watch_poll), 'Actual preference/watch readers required.')
    originals=[anchor for prior in prior_fixtures for anchor in prior.documents.values()]
    require(len(originals)<=4 and all(isinstance(anchor,FixtureAnchor) and anchor.kind=='document'
            and anchor.canonical is not None for anchor in originals), 'Complete bounded original model custody required.')
    reader=_Read(receipt,assert_safe)
    try:
        event=reader.call('open_events',watch_poll)
        require(adapter._sw is baseline.application,'Exact original application handle required.')
        labels={'Основная деталь':'Основная деталь:new_document','Сосед':'Сосед:new_document',
                'Цилиндр':'cylinder:new_document'}
        for prior in prior_fixtures:
            require(type(prior.native_returns) is list and all(type(row) in (tuple,list) and len(row)==3
                    and type(row[0]) is int and row[0]>0 and type(row[1]) is str for row in prior.native_returns),
                    'Actual normally returned original fixture ledger required.')
            for role,anchor in prior.documents.items():
                require(role in labels,'Only declared original part/cylinder creation roles supported.')
                raw=[row[2] for row in prior.native_returns if row[1]==labels[role]]
                require(len(raw)==1 and raw[0] is not None
                        and reader.call('original_creation_return',adapter.identity,raw[0])==anchor.canonical,
                        'Each earlier model must bind its own normally returned NewDocument handle.')
        def capture():
            require(reader.call('application_canonical',adapter.identity,adapter._sw)==baseline.canonical
                    and reader.call('owned_guard',getattr,adapter._sw,'CommandInProgress') is True,
                    'Original application under caller-owned guard required.')
            context=_context(reader.call('application_context',adapter.native_close_application_context))
            require(context==baseline.context,'Original application settings/search context changed.')
            tokens=[reader.call('original_model',adapter.identity,anchor.handle) for anchor in originals]
            require(all(token==anchor.canonical for token,anchor in zip(tokens,originals))
                    and all(sum(token==other for other in tokens)==1 for token in tokens), 'Distinct current original models required.')
            models=reader.call('current_models',adapter.documents)
            windows=reader.call('current_windows',adapter.native_close_windows)
            require(type(models) in (tuple,list) and type(windows) in (tuple,list)
                    and len(models)==len(windows)==len(originals),'Complete original model/window roster required.')
            current=[reader.call('current_model',adapter.identity,model) for model in models]
            require(all(sum(token==old for token in current)==1 for old in tokens),'Foreign/missing/replaced current model prohibited.')
            bindings=[]
            for model,info in windows:
                token=reader.call('window_model',adapter.identity,model)
                require(type(info) is dict and type(info.get('hwnd')) is int and 0<info['hwnd']<2**63,
                        'Strict normally current window required.')
                bindings.append((token,info['hwnd']))
            require(len({hwnd for _,hwnd in bindings})==len(bindings)
                    and all(sum(token==old for token,_ in bindings)==1 for old in tokens),'Unique exact original window associations required.')
            active=reader.call('active_model',getattr,adapter._sw,'ActiveDoc')
            active_token=reader.call('active_canonical',adapter.identity,active) if active is not None else None
            require((not originals and active is None) or (originals and active is not None
                    and sum(active_token==old for old in tokens)==1),
                    'Active document must be an original current fixture model.')
            prefs=_preferences(reader.call('application_preferences',preference_reader))
            return bindings,prefs
        before,preferences=capture()
        closing,closing_preferences=capture()
        require(before==closing,'Original window association changed during fixture startup admission.')
        assert_non_stl_preferences(lambda:preferences,baseline.preferences,receipt.preference_evidence,'baseline')
        assert_non_stl_preferences(lambda:closing_preferences,preferences,receipt.preference_evidence,'closing')
        require(reader.call('close_events',watch_poll)==event,'Whole original session events changed during admission.')
        receipt.complete=True
        return True
    except BaseException:
        receipt.halted=True
        raise
