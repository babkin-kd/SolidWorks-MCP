"""One caller-owned B3 part setup path; no CLI, connection or acceptance.

Application baseline -> own paired guard -> two-part fixture -> cylinder ->
original static topology anchors. Caller retains this receipt before entry.
Any unconfirmed result keeps the original owner/guard; no retry/cleanup/SDK
dispatch occurs here. Whole-session baseline and guard handoff remain gates.
"""
from dataclasses import dataclass, field
from threading import get_ident

from verifier_b3_application_admission import (
    ApplicationAdmissionReceipt,capture_empty_application,admit_fixture_application)
from verifier_b3_empty_template import EmptyTemplateReceipt,capture_empty_template
from verifier_b3_part_fixture import PartFixtureReceipt,create_part_fixture
from verifier_b3_cylinder_fixture import create_cylinder_fixture
from verifier_b3_part_anchors import PartAnchorReceipt,retain_part_anchors


def require(condition,message):
    if not condition:raise ValueError(message)


@dataclass
class PartSetupReceipt:
    part_request_id:str
    cylinder_request_id:str
    thread_id:int=field(default_factory=get_ident)
    attempted:bool=False
    halted:bool=False
    phase:str='fresh'
    pending_step:str|None=None
    journal_lost:bool=False
    raw_returns:list=field(default_factory=list)
    initial:object=None
    baseline:object=None
    part:object=None
    cylinder:object=None
    admissions:list=field(default_factory=list)
    templates:list=field(default_factory=list)
    anchor_receipts:dict=field(default_factory=dict)
    original_objects:dict=field(default_factory=dict)
    birth_windows:list=field(default_factory=list)
    guard_returned:bool=False
    guard_acquired:bool=False
    setup_complete:bool=False
    sdk_ready:bool=False
    accepted:bool=False
    native_acceptance:bool=False
    cleanup_authorized:bool=False
    remaining_gates:tuple=('whole_session_baseline','original_guard_handoff','same_wheel_B1_sketch',
                           'assembly_fixtures_and_transitions','SDK_namespace_and_13_groups')


def prepare_part_setup(*,receipt,adapter,template,title_suffix,wrap,assert_safe,recorder,
                       watch_poll,reference_watch,preference_reader):
    """Source orchestration on the existing original STA with explicit requests.

recorder(request_id,label,phase,data) is the parent's durable private recorder;
it must not write these raw COM receipts to public Git or serialize them as job
results. assert_safe(receipt) admits root/process/STA/whole current session.
Returned guard acquisition cannot authorize later release/SDK/cleanup by itself.
"""
    require(type(receipt) is PartSetupReceipt and not receipt.attempted and not receipt.halted
            and receipt.thread_id==get_ident() and receipt.pending_step is None and not receipt.raw_returns
            and not receipt.journal_lost and not receipt.guard_returned and not receipt.guard_acquired
            and receipt.phase=='fresh' and receipt.initial is None and receipt.baseline is None
            and receipt.part is None and receipt.cylinder is None and not receipt.admissions and not receipt.templates
            and not receipt.anchor_receipts and not receipt.original_objects and not receipt.birth_windows
            and not receipt.setup_complete and receipt.accepted is False and receipt.native_acceptance is False
            and receipt.cleanup_authorized is False and receipt.sdk_ready is False,
            'Fresh externally retained original STA setup receipt required.')
    require(all(type(value) is str and value.strip() for value in (receipt.part_request_id,receipt.cylinder_request_id))
            and receipt.part_request_id!=receipt.cylinder_request_id,'Distinct explicit original fixture request IDs required.')
    require(all(callable(callback) for callback in (wrap,assert_safe,recorder,watch_poll,preference_reader))
            and callable(reference_watch.poll),'Explicit owner/read/watch/ledger callbacks required.')
    receipt.attempted=True

    def safe():
        require(get_ident()==receipt.thread_id and not receipt.halted and not receipt.journal_lost,
                'Unconfirmed or foreign setup owner cannot continue.')
        return assert_safe(receipt) is True

    def owned_fixture(fixture):
        require(fixture is receipt.part or fixture is receipt.cylinder,'Only original held fixture receipt allowed.')
        return safe()

    def record_for(fixture):
        return lambda label,phase,data:recorder(fixture.request_id,label,phase,data)

    def application(application,fixture,priors):
        require(application is adapter._sw and owned_fixture(fixture),'Exact original fixture/application owner required.')
        admission=ApplicationAdmissionReceipt()
        receipt.admissions.append(admission)
        return admit_fixture_application(receipt=admission,baseline=receipt.baseline,baseline_receipt=receipt.initial,
            fixture=fixture,prior_fixtures=priors,adapter=adapter,preference_reader=preference_reader,
            assert_safe=safe,watch_poll=watch_poll)

    def empty(document,fixture,role,priors):
        require(owned_fixture(fixture),'Original template caller admission required.')
        admission=EmptyTemplateReceipt()
        receipt.templates.append(admission)
        documents=tuple(anchor for prior in priors for anchor in prior.documents.values())+tuple(fixture.documents.values())
        baseline=capture_empty_template(receipt=admission,fixture=fixture,document=document,
            original_documents=documents,prior_fixtures=priors,adapter=adapter,wrap=wrap,
            assert_safe=owned_fixture,watch_poll=watch_poll)
        windows=[value for label,value in admission.returned_reads if label=='whole_window_census']
        require(windows,'Original admission window returns required before naming.')
        require(safe(),'Original owner admission required before birth window canonical comparisons.')
        event=watch_poll();matched=[]
        for model,info in windows[0]:
            require(safe(),'Original owner admission required before each native canonical comparison.')
            if adapter.identity(model)==document.canonical:matched.append(info)
        require(len(matched)==1,'Original normally current birth window must bind the exact created model.')
        require(safe() and watch_poll()==event,'Original birth window association changed inside owner/event envelope.')
        receipt.birth_windows.append((document,matched[0]['hwnd']))
        return baseline.cylinder_baseline() if fixture is receipt.cylinder else baseline.xy_baseline()

    try:
        require(safe(),'Original caller admission required before any application baseline read.')
        receipt.phase='initial_application'
        receipt.initial=ApplicationAdmissionReceipt()
        receipt.baseline=capture_empty_application(receipt=receipt.initial,adapter=adapter,
            preference_reader=preference_reader,assert_safe=safe,watch_poll=watch_poll)
        require(safe(),'Original owner admission required before guard acquisition.')
        receipt.phase='guard_acquisition';receipt.pending_step='own_guard';receipt.journal_lost=True
        recorder(receipt.part_request_id,'setup:own_guard','pending',dict(value=True))
        receipt.journal_lost=False
        require(safe() and adapter.identity(adapter._sw)==receipt.baseline.canonical
                and adapter._sw.CommandInProgress is False,
                'Original idle owner/guard must still match after pending journal write.')
        value=setattr(adapter._sw,'CommandInProgress',True)
        receipt.raw_returns.append(('setup:own_guard',value))
        receipt.guard_returned=True;receipt.journal_lost=True
        recorder(receipt.part_request_id,'setup:own_guard','returned',dict(normally_returned=True))
        receipt.journal_lost=False;receipt.pending_step=None
        require(safe() and adapter._sw.CommandInProgress is True,'Normally returned own guard readback required.')
        receipt.guard_acquired=True
        receipt.phase='part_fixture'
        receipt.part=PartFixtureReceipt(receipt.part_request_id)
        created=create_part_fixture(receipt=receipt.part,application=adapter._sw,template=template,title_suffix=title_suffix,
            wrap=wrap,identity=adapter.identity,assert_safe=owned_fixture,recorder=record_for(receipt.part),
            admit_application=lambda app,current:application(app,current,()),
            admit_empty_part=lambda doc,current,role:empty(doc,current,role,()))
        require(created is receipt.part and created.setup_complete is True,'Original completed part receipt required.')
        receipt.phase='cylinder_fixture'
        receipt.cylinder=PartFixtureReceipt(receipt.cylinder_request_id)
        created=create_cylinder_fixture(receipt=receipt.cylinder,application=adapter._sw,template=template,title_suffix=title_suffix,
            wrap=wrap,identity=adapter.identity,assert_safe=owned_fixture,recorder=record_for(receipt.cylinder),
            admit_application=lambda app,current:application(app,current,(receipt.part,)),
            admit_empty_part=lambda doc,current,role:empty(doc,current,role,(receipt.part,)))
        require(created is receipt.cylinder and created.setup_complete is True,'Original completed cylinder receipt required.')
        receipt.phase='original_part_topology'
        for role in ('Основная деталь','Сосед'):
            anchors=PartAnchorReceipt();receipt.anchor_receipts[role]=anchors
            receipt.original_objects[role]=retain_part_anchors(receipt=anchors,fixture=receipt.part,model_role=role,
                adapter=adapter,wrap=wrap,watch=reference_watch,assert_safe=owned_fixture)
        require(safe() and adapter._sw.CommandInProgress is True,'Original setup owner/guard must remain held.')
        receipt.phase='setup_complete_guard_held';receipt.setup_complete=True
        return receipt
    except BaseException:
        receipt.halted=True
        raise
