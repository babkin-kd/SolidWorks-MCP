"""One installed N5 fixture/refusal case on the original B1 construction owner.

CLI only: child_plane, unused_equation OR linked_equation per fresh work run.
Native ownership/cleanup remains the unchanged B1 driver's one owning STA.
Unknown/pending failures retain that STA; no cancellation, undo or retry exists.
Terminal accepted means THIS N5 fixture case only, never whole B2/public release.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

from solidworks_mcp.jobs import _json,ExecutionFailure,JobRunner
from solidworks_mcp.features import FeatureCatalog
from solidworks_mcp.native_first_save import SNAPSHOT_SCOPE,validated_part_snapshot
from solidworks_mcp.rectangle_snapshot import SCOPE as RECTANGLE_SCOPE,BASE,validated_rectangle_snapshot
from verifier_b2_impact_fixture import B2ImpactFixtures
from verifier_b2_impact_target import B2ImpactTarget
from verifier_b2_impact_session import B2ImpactSession,same_refused_session
from verifier_b2_impact_internal import run_impact_refusals
from verifier_b2_public_contract import durable_b2_job,verified_b2_job
from verifier_lifecycle import read_journal
from verifier_dimension_diagnostics import DEFERRED_STL_FIELDS
from verify_owned_leaf_deletion_faults import positive_preflight
from verify_owned_leaf_deletion_positive import (
    OwnLeafPositiveHook,require,sha256,detached,receipt_facts,normal_flag_boundary,independent_read)


SCOPE='installed_b2_impact_single_fixture_case_v1'
SETUP_OPERATION='verifier.b2_impact_fixture'
KINDS=('child_plane','unused_equation','linked_equation')
HELPERS=('verify_b2_impact_native.py','verify_owned_leaf_deletion_positive.py','verify_owned_leaf_deletion_faults.py',
    'verifier_b2_impact_fixture.py','verifier_b2_impact_target.py','verifier_b2_impact_session.py',
    'verifier_b2_impact_ancillary.py','verifier_b2_impact_views.py','verifier_b2_impact_internal.py',
    'verifier_b2_impact_request_envelope.py','verifier_b2_impact_refusal.py','verifier_b2_public_contract.py',
    'verifier_lifecycle.py','verifier_rectangle_positive_acceptance.py','verifier_rectangle_public_contract.py',
    'verifier_first_save_public_contract.py','verifier_native_open.py','verifier_native_part_activation.py',
    'verifier_native_first_save.py','verifier_rectangle_restoration.py',
    'verify_rectangle_stages_positive.py','verifier_rectangle_stages.py','probe_native_first_save_domain.py',
    'verify_installed_metadata.py','verify_wheel_artifact.py','verify_bounds_measurements.py',
    'verify_export_operations.py','verify_native_document_open.py','verify_native_first_save_rejections.py',
    'verifier_dimension_diagnostics.py')


def setup_pairs(job,kind):
    """Exact current fixture helper labels under JobStore's finite 32-row cap."""
    names={'child_plane':('set_first_reference_mark','select_face','insert_plane','clear_owned_selection','rebuild','rename_plane'),
        'unused_equation':('add_unused_global','rebuild'),
        'linked_equation':('add_unused_global','set_file_path','link_file','rebuild')}[kind]
    steps=job['mutation']['verification']['native_steps']
    require(type(steps) is list and len(steps)==2*len(names)<=32,'Complete exact fixture ledger required.')
    for index,row in enumerate(steps):
        require(type(row) is dict and set(row)=={'sequence','name','phase','evidence'}
            and type(row['sequence']) is int and row['sequence']==index+1
            and row['name']=='impact_'+kind+'_'+names[index//2]
            and row['phase']==('pending' if index%2==0 else 'returned')
            and type(row['evidence']) is dict and bool(row['evidence']),
            'Exact one-shot normally paired native fixture receipts required.')
    return steps


def neighbor_projection(current,parent):
    """Compare only the two documented rectangle-added fields; retain current.

Production rectangle BASE calls the unchanged first-save getter and adds native
creation_controls and annotation_view_bindings. No parent/baseline observations
are copied into current. All added current data stays in the session/report.
"""
    current=validated_rectangle_snapshot(current)
    parent=validated_part_snapshot(parent)
    projection=deepcopy(current)
    projection['scope']=SNAPSHOT_SCOPE
    projection['clone_state'].pop('creation_controls')
    projection['native_observations'].pop('annotation_view_bindings')
    require(_json(validated_part_snapshot(projection))==_json(parent),
            'Actual full rectangle neighbor differs from the original first-save observation.')
    return current


def prepare_equation_file(state):
    """Exclusive private fresh file, called by preflight before original CAD init."""
    state=Path(state).resolve(strict=True)
    require(state.is_relative_to((Path.cwd()/'work').resolve()) and state!=Path.cwd()/'work',
            'Only the fresh private fixture state may contain an equation file.')
    path=state/'n5-owned-equations.txt'
    raw='"Контрольная независимая величина" = 3'.encode('utf8')
    with path.open('xb') as stream:stream.write(raw)
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


def terminal_rows(store,binding):
    rows=read_journal(store.path)
    require(all(row['status'] in ('succeeded','failed') and (row['mutation'] is None or
        row['mutation']['phase'] in ('committed','rolled_back','not_started')) for row in rows)
        and store.mutation_blockers(binding.connection_epoch,binding.document_id,effect_scope='application')==[],
        'Every fixture/request job must be terminal without an unresolved or active hold.')
    return rows


class OwnImpactHook(OwnLeafPositiveHook):
    def __init__(self,*args,fixture_kind,equation_file=None,fixture_factory=B2ImpactFixtures,
                 target_factory=B2ImpactTarget,session_factory=B2ImpactSession,batch=run_impact_refusals,**kwargs):
        super().__init__(*args,**kwargs)
        require(fixture_kind in KINDS,'One explicit finite N5 fixture kind required.')
        self.kind=fixture_kind;self.equation_file=equation_file
        self.fixture_factory,self.target_factory,self.session_factory=fixture_factory,target_factory,session_factory
        self.batch=batch;self.fixture=None;self.leaf=None;self.session=None

    def _callback(self,sw,target,owned):
        self.started=True
        report,persist=self.report,self.persist
        report.update(callback_attempted=True,callback_passed=False,phase='n5_admission');persist()
        require(len(self.domains)==1,'Singular original construction owner required.')
        original=self.domains[0];a,store=original.adapter,original.store
        require(a.identity(a._sw)==a.identity(sw) and len(owned)==2 and not original.receipts,
                'Exact original application/two native fixtures and released construction receipts required.')
        parent=self._parent();jobs=[parent['sketch_job'],parent['extrusion_job']]
        args=jobs[1]['payload']['arguments']
        document_id,configuration=args['document_id'],args['configuration']
        object_id=jobs[1]['result']['value']['feature_object_id']
        require(args['sketch_object_id']==jobs[0]['result']['value']['sketch_object_id']
            and all(store.get(job['operation_id'])==job and job['status']=='succeeded'
                and job['mutation']['phase']=='committed' for job in jobs),
            'Exact original durable succeeded B1 sketch/extrusion chain required.')
        b,feature=original.ownership.resolve(document_id,configuration,object_id,connection_epoch=original.connection_epoch)
        require(b.kind=='extrusion' and a.identity(target)==b.model_identity
            and a.identity(feature)==b.feature_identity and a.identity(a.active_document())==b.model_identity,
            'Exact active original own model/feature/PID binding required.')
        tokens=[a.identity(model) for model in owned]
        current=a.documents()
        require(len(current)==2 and len(tokens)==2 and tokens[0]!=tokens[1]
            and sum(token==b.model_identity for token in tokens)==1
            and all(sum(a.identity(model)==token for model in current)==1 for token in tokens),
            'Only two exact currently owned model incarnations may enter N5.')
        neighbor=next(model for model in owned if a.identity(model)!=b.model_identity)
        self.neighbor_identity=a.identity(neighbor)
        entry,observed=original.documents.resolve(document_id,configuration)
        require(entry.identity==b.model_identity and observed['document_type']=='part' and observed['path']==''
            and observed['active_configuration']==configuration and observed['configurations']==[configuration],
            'Exact unsaved one-configuration current-epoch native part required.')
        base=validated_rectangle_snapshot(parent['independent_base'])
        require(base['clone_state']['profile']==BASE and base['solid_body_count']==1,'Actual original B1 BASE admission required.')
        current_neighbor=independent_read(lambda:validated_part_snapshot(a.first_save_part_snapshot(neighbor)),
            report,persist,'n5_original_neighbor')
        require(_json(current_neighbor)==_json(parent['independent_neighbor']) and neighbor.GetSaveFlag() is True,
                'Actual original complete dirty neighbor must match parent before setup.')
        facts=receipt_facts(b.receipt)
        report.update(original_creation_jobs=detached(jobs),original_creation_receipt_before=facts,
            explicit_target=dict(document_id=document_id,configuration=configuration,object_id=object_id,
                creation_operation_id=b.creation_operation_id,feature_pid_hex=b.persistent_id.hex(),feature_native_id=b.native_id))
        persist()
        normal_flag_boundary(sw,True,False,report,persist,'n5_parent_owned_guard_release')
        leaf=self.leaf_factory(original.documents,store,original.connection_epoch,original.ownership);self.leaf=leaf
        require(leaf.ownership is original.ownership and leaf.store is store and leaf.documents is original.documents,
                'N5 leaf must retain the exact original owner/SQLite.')
        runner=self.runner_factory(store,self.driver.InlineSta())
        context=dict(document_id=document_id,configuration=configuration,object_id=object_id)
        report.update(phase='n5_original_BASE_preparation',native_calls_live=True);persist()
        prepared=runner.submit('n5-original-BASE-preparation','feature.prepare_leaf_deletion',context,
            lambda:leaf.prepare(**context),context=context)
        report['base_preparation']=detached(store.get(prepared['operation_id']));persist()
        rows={row['operation_id']:row for row in read_journal(store.path)}
        durable=durable_b2_job(prepared,rows[prepared['operation_id']])
        require(verified_b2_job(durable) is True and prepared==report['base_preparation']
            and prepared['result']['baseline']['snapshots'][document_id]==base
            and prepared['result']['creation_operation_id']==b.creation_operation_id
            and prepared['result']['feature_pid_hex']==b.persistent_id.hex(),
            'Actual durable original own BASE preparation required before fixture changes.')
        report['native_calls_live']=False;persist()
        neighbor_rectangle=independent_read(lambda:neighbor_projection(a.rectangle_construction_snapshot(neighbor),
            parent['independent_neighbor']),report,persist,'n5_current_rectangle_neighbor')
        original.documents._refresh()
        neighbors=[item for item in original.documents._entries if item.identity==self.neighbor_identity]
        require(len(neighbors)==1 and neighbors[0].model is not b.model,'Exact current native neighbor entry required.')
        neighbor_entry=neighbors[0]
        setup_args=dict(context,expected_revision=prepared['result']['revision'],fixture_kind=self.kind)
        setup_context={key:setup_args[key] for key in ('document_id','configuration','object_id','expected_revision')}
        report['neighbor_before']=neighbor_rectangle;persist()

        def setup(operation_id):
            store.prepare_mutation(operation_id,connection_epoch=b.connection_epoch,document_id=document_id,
                configuration=configuration,expected_revision=setup_args['expected_revision'],
                before_state=dict(scope=SCOPE,fixture_kind=self.kind,baseline=prepared['result']['baseline']),effect_scope='application')
            def record(name,phase,evidence):
                report.update(phase='n5_'+name+'_'+phase,native_calls_live=True);persist()
                store.record_mutation_step(operation_id,name=name,phase=phase,evidence=evidence)
            fixture=self.fixture_factory(original.ownership,b,FeatureCatalog(original.documents,store,b.connection_epoch),recorder=record)
            self.fixture=fixture
            # Retain original target dimensions/body/features before setup;
            # current unsupported data cannot reconstruct these later.
            target_reader=self.target_factory(fixture,base)
            session=self.session_factory(target_reader,neighbor_entry,neighbor_rectangle,equation_file=self.equation_file)
            self.session=session
            report.update(phase='n5_fixture_setup',native_calls_live=True);persist()
            if self.kind=='child_plane':value=fixture.add_child_plane(base)
            elif self.kind=='unused_equation':value=fixture.add_unused_equation()
            else:
                require(self.equation_file is not None,'Exact owner-created private equation file required.')
                value=fixture.link_equation_file(self.equation_file['path'],expected_sha256=self.equation_file['sha256'])
            require(value['fixture_prepared'] is True and fixture.pending_native_step is None and fixture.journal_failed is False,
                    'Normally returned acknowledged fixture setup required; no pending recovery.')
            first=independent_read(session.capture,report,persist,'n5_setup_first_session')
            second=independent_read(session.capture,report,persist,'n5_setup_second_session')
            require(same_refused_session(first,second) is True and type(sw.CommandInProgress) is bool
                and sw.CommandInProgress is False,'Two equal complete actual fixture sessions and normal False guard required.')
            value=dict(scope=SCOPE,fixture_kind=self.kind,fixture=detached(value),current_session=second,
                setup_verified=True,accepted=False,native_b2_accepted=False,public_mcp_accepted=False)
            current=store.get(operation_id)
            setup_pairs(current,self.kind)
            store.verify_mutation(operation_id,outcome='committed',evidence=value)
            return value

        setup_job=runner.submit('n5-'+self.kind+'-fixture-setup',SETUP_OPERATION,setup_args,setup,context=setup_context,
            mutates=True,pass_operation_id=True,verify=lambda value:value['setup_verified'] is True)
        report['fixture_setup_job']=detached(store.get(setup_job['operation_id']));persist()
        require(setup_job==report['fixture_setup_job'] and setup_job['status']=='succeeded' and setup_job['error'] is None
            and setup_job['mutation']['phase']=='committed' and setup_job['mutation']['verification']['outcome']=='committed'
            and setup_job['mutation']['verification']['evidence']==setup_job['result']
            and self.fixture is not None and self.fixture.pending_native_step is None and self.fixture.journal_failed is False,
            'Actual setup terminal succeeded/committed receipt required before any refusal requests.')
        terminal_rows(store,b)
        report['native_calls_live']=False;persist()
        def progress(marker):
            report.update(phase='n5_request_'+marker['label']+'_'+marker['phase'],
                native_calls_live=marker['phase']=='before');persist()
        expected='leaf_deletion_unsupported' if self.kind=='child_plane' else 'first_save_snapshot_unsupported'
        batch=self.batch(leaf,runner,self.session,prepared,expected_code=expected,progress=progress)
        report['refusal_batch']=detached(batch);persist()
        require(batch['refusal_batch_passed'] is True and not leaf.receipts and not original.receipts,
                'Complete actual refusal batch and empty mutation receipts required.')
        final_first=independent_read(self.session.capture,report,persist,'n5_final_first_session')
        final_second=independent_read(self.session.capture,report,persist,'n5_final_second_session')
        require(same_refused_session(final_first,final_second) is True
            and same_refused_session(batch['observation']['after'],final_second) is True,
            'Full actual session must remain unchanged after all finite refusal jobs/replays.')
        retained,current=original.ownership.resolve(document_id,configuration,object_id,connection_epoch=b.connection_epoch)
        require(retained is b and a.identity(current)==b.feature_identity
            and self.fixture._pid(current,'feature')==b.persistent_id
            and type(sw.CommandInProgress) is bool and sw.CommandInProgress is False,
            'Original extrusion PID/canonical and normal False guard required before own cleanup handoff.')
        terminal=terminal_rows(store,b)
        require(all(store.get(job['operation_id'])==job for job in jobs)
            and receipt_facts(b.receipt)==facts,'Original creation SQL/receipt must stay unchanged.')
        report.update(final_session=final_second,terminal_jobs=terminal,application_hold_clear=True,
            original_creation_jobs_unchanged=True,original_creation_receipt_after=receipt_facts(b.receipt));persist()
        normal_flag_boundary(sw,False,True,report,persist,'n5_parent_owned_guard_reacquire')
        self.completed=True
        report.update(callback_passed=True,phase='delegated_owned_cleanup');persist()


def terminal_case(hook,state,report):
    parent_path=Path(state)/'report.json'
    parent=json.loads(parent_path.read_text(encoding='utf8'))
    require(hook.completed and not hook.failed and hook.delegations==2 and parent['phase']=='terminal'
        and parent['positive_case_passed'] is True and parent['native_calls_live'] is False
        and parent.get('retained_process',False) is False and parent['baseline_restored'] is True
        and parent['own_cleanup_verified'] is True and parent['owned_documents']==[]
        and parent['original_baseline']==parent['restored_baseline']==[]
        and parent['original_application']==parent['restored_application'],
        'Actual terminal parent empty session/original baseline/non-STL preferences proof required.')
    preferences=parent['restored_preferences']
    require(preferences['scope']=='application_preferences_except_stl_v1'
        and preferences['excluded_fields']==sorted(DEFERRED_STL_FIELDS)
        and preferences['snapshot_read'] is True and preferences['scope_exactly_equal'] is True
        and preferences['stl_preferences_verified'] is False and preferences['cause_inferred'] is False
        and _json(preferences['before'])==_json(parent['original_preferences'])
        and _json({key:value for key,value in preferences['before'].items() if key not in DEFERRED_STL_FIELDS})==
            _json({key:value for key,value in preferences['after'].items() if key not in DEFERRED_STL_FIELDS}),
        'Actual fixed non-STL comparison/current preference evidence required.')
    rows=read_journal(Path(state)/'jobs.sqlite')
    require(all(row['status'] in ('succeeded','failed') and (row['mutation'] is None or
        row['mutation']['phase'] in ('committed','rolled_back','not_started')) for row in rows),
        'Closed parent journal must retain only terminal verified fixture/refusal rows.')
    report.update(parent_final_report=parent,parent_final_report_sha256=sha256(parent_path),
        phase='terminal',fixture_case_passed=True,accepted=True,native_b2_accepted=False,public_mcp_accepted=False,
        own_cleanup_verified=True,baseline_restored=True,native_calls_live=False,
        terminal_jobs=rows,open_gates=['whole_B2_release','public_MCP_N5_chain'])


def main(argv=None,*,driver=None,leaf_factory=None,runner_factory=JobRunner):
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--fixture-kind',choices=KINDS,required=True)
    parser.add_argument('--positive-report',type=Path,required=True)
    parser.add_argument('--positive-report-sha256',required=True)
    arguments=list(sys.argv[1:] if argv is None else argv)
    own,inherited=parser.parse_known_args(arguments)
    require('--state-dir' in inherited,'Inherited --state-dir required.')
    state=Path(inherited[inherited.index('--state-dir')+1]).resolve()
    scripts=Path(__file__).resolve().parent
    private=scripts.parent/'work'
    require(state.is_relative_to(private) and state!=private and not state.exists(),'Fresh private state required.')
    require(own.positive_report.resolve(strict=True).is_relative_to(private),'Actual positive report must remain private.')
    if driver is None:
        import verify_rectangle_stages_positive as driver
    if leaf_factory is None:
        from solidworks_mcp.owned_leaf_deletion_catalog import OwnLeafDeletionCatalog
        leaf_factory=OwnLeafDeletionCatalog
    report=dict(scope=SCOPE,fixture_kind=own.fixture_kind,accepted=False,native_b2_accepted=False,
        public_mcp_accepted=False,fixture_case_passed=False,native_calls_live=False,phase='preflight',
        verifier_hashes={name:sha256(scripts/name) for name in HELPERS})
    started=time.perf_counter()
    def persist():
        report['elapsed_seconds']=time.perf_counter()-started
        if state.exists():(state/'b2-impact-report.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf8')
    hook=OwnImpactHook(driver,state,report,persist,fixture_kind=own.fixture_kind,
        leaf_factory=leaf_factory,runner_factory=runner_factory)
    original_package=driver.package_evidence
    def gated_package(args,*,installed):
        evidence=original_package(args,installed=installed)
        report.update(positive_preflight(own.positive_report,own.positive_report_sha256,evidence['wheel'],scripts))
        if own.fixture_kind=='linked_equation':
            hook.equation_file=prepare_equation_file(state);report['equation_file']=hook.equation_file
        persist();return evidence
    original_argv=sys.argv[:]
    driver.package_evidence=gated_package
    driver.RectangleConstructionCatalog,driver.retire_owned=hook.construction,hook.retire
    sys.argv=[sys.argv[0],*inherited]
    try:
        driver.main()
        terminal_case(hook,state,report);persist()
    except BaseException as error:
        report.update(phase='failed',accepted=False,fixture_case_passed=False,error=str(error));persist();raise
    finally:
        driver.package_evidence=original_package
        driver.RectangleConstructionCatalog,driver.retire_owned=hook.original_factory,hook.original_retire
        sys.argv=original_argv
    print(json.dumps(dict(scope=SCOPE,fixture_kind=own.fixture_kind,fixture_case_passed=True,
        accepted=True,native_b2_accepted=False,public_mcp_accepted=False)),flush=True)
    return report


if __name__=='__main__':main()
