"""Source-only N5 hook/CLI on actual artificial registry/coordinator/SQLite."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_rectangle_model_view import RectangleModelView
from solidworks_mcp.cad_rectangle_view_retirement import NativeView,RectangleViewReceipt
from solidworks_mcp.jobs import JobRunner
from solidworks_mcp.native_first_save import SNAPSHOT_SCOPE,validated_part_snapshot
from solidworks_mcp.owned_leaf_deletion_catalog import OwnLeafDeletionCatalog
from solidworks_mcp.rectangle_snapshot import validated_rectangle_snapshot
from test_feature_suppression_domain import InlineWorker
from test_b2_impact_fixture import fixture,leaf,extrusion_proof,proof,case,domain,b2_private_dir,b2_outside_dir
from test_b2_public_preflight import rebind_creations,artifacts,faults,execution,sketch_proof,empty_adapter

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:
    import verify_b2_impact_native as helper
    from verifier_b2_impact_target import B2ImpactTarget
    from verifier_rectangle_stages import verified_rectangle_job
finally:sys.path.remove(str(scripts))


def first_save(current):
    value=deepcopy(current);value['scope']=SNAPSHOT_SCOPE
    value['clone_state'].pop('creation_controls')
    value['native_observations'].pop('annotation_view_bindings')
    return validated_part_snapshot(value)


@pytest.fixture
def native_case(fixture,sketch_proof,b2_private_dir):
    x=fixture;a=x.c.adapter
    # Complete only the unused artificial harness ledger, before fresh real B1
    # coordinator jobs; no native fixture writes have occurred yet.
    x.store.verify_mutation(x.operation_id,outcome='not_started',evidence={'artificial_fixture_not_started':True})
    x.store.finish(x.operation_id,'failed',error=dict(code='test_fixture_unused',message='No native writes.',requires_reconciliation=False))
    creations=rebind_creations(x,sketch_proof)
    receipt=x.binding.receipt
    receipt.annotation_views=RectangleViewReceipt(x.binding.model_identity,
        tuple(NativeView(NS(identity=object()),object(),deepcopy(row))
            for row in x.c.baseline['clone_state']['display_data']['annotation_views']),
        owned=[(NativeView(NS(identity=object()),object(),{'artificial_owned_view':True}),x.binding.feature)],
        binding_attempted=True,bound=True)
    receipt.model_view=RectangleModelView(x.binding.model_identity,object(),{'artificial_current_view':True})
    receipt.borrowed_sketch_snapshot=deepcopy(x.binding.baseline_target_snapshot['clone_state']['sketch'])
    class Application:
        identity=object()
        IsSame=staticmethod(a._sw.IsSame)
        @property
        def CommandInProgress(self):return x.busy
        @CommandInProgress.setter
        def CommandInProgress(self,value):
            x.flag_writes.append(value)
            if x.callback_fault=='handoff' and value is True:raise RuntimeError('Artificial handoff unacknowledged')
            x.busy=value
    x.busy=True;x.flag_writes=[];x.callback_fault=None;x.delegations=[]
    a._sw=Application();x.sw=a._sw
    x.owned=[entry.model for entry in x.entries]
    a.documents=lambda:list(x.owned)
    neighbor=x.entries[1].model;neighbor.GetSaveFlag=lambda:True
    original_rectangle=a.rectangle_construction_snapshot
    def rectangle(model):
        if model is x.binding.model and x.manager.GetCount()>0:
            from solidworks_mcp.documents import rejected
            raise rejected('first_save_snapshot_unsupported','Actual artificial equations are outside BASE.')
        return original_rectangle(model)
    a.rectangle_construction_snapshot=rectangle
    a.first_save_part_snapshot=lambda model:first_save(original_rectangle(model))
    a.sketch_snapshot=lambda model,feature:(deepcopy(x.c.getter_values['sketch']),())
    original=NS(adapter=a,store=x.store,documents=x.ownership.documents,ownership=x.ownership,connection_epoch='epoch',receipts={})
    parent=dict(scope='installed_rectangle_stages_positive_only',accepted=False,artificial_fixture=True,
        phase='owned_cleanup',native_calls_live=False,independent_native_readback_verified=True,package_origin_verified=True,
        wheel={'artificial_candidate':True},independent_volume_mm3=8000.,captures=[{'status':'returned'}],
        independent_base=deepcopy(x.c.baseline),independent_neighbor=a.first_save_part_snapshot(neighbor),
        cases=[dict(label=label,passed=True) for label in ('B1-N1-separate-sketch-and-replay',
            'B1-N1-separate-extrusion-and-replay','B1-N2-N3-exact-native-base-and-neighbor')],
        sketch_job=creations[0],extrusion_job=creations[1])
    (b2_private_dir/'report.json').write_text(json.dumps(parent,ensure_ascii=False),encoding='utf8')
    def retire(sw,module,root,retiring,owned,record):
        assert sw.CommandInProgress is True
        x.delegations.append(root)
        if x.callback_fault=='close_pending':raise RuntimeError('Artificial original CloseDoc unconfirmed')
        owned.remove(root);record(owned)
    driver=NS(RectangleConstructionCatalog=lambda *args:original,retire_owned=retire,
        verified_rectangle_job=verified_rectangle_job,validated_rectangle_snapshot=validated_rectangle_snapshot,
        validated_part_snapshot=validated_part_snapshot,BASE=helper.BASE,InlineSta=InlineWorker)
    # Only current native getter boundaries are artificial. The actual target,
    # session, ownership, domain, JobRunner, journal and postconditions execute.
    def target_reader(held,base):
        return B2ImpactTarget(held,base,ancillary=lambda *args,**current:{'artificial_native_ancillary':True},
            extrusion=lambda adapter,feature:deepcopy(x.c.getter_values['extrusion']),
            topology=lambda adapter,model,body,boundary,references:references.extend(
                deepcopy([row for row in x.c.baseline['references'] if row['kind'] in ('face','edge')])))
    def fixtures(*args,**kwargs):
        kwargs['wrap']=lambda raw,interface:raw
        kwargs['query']=x.helper.query
        return helper.B2ImpactFixtures(*args,**kwargs)
    def hook(kind='child_plane',**kwargs):
        report=dict(scope=helper.SCOPE,fixture_kind=kind,artificial_fixture=True,accepted=False,
            native_b2_accepted=False,public_mcp_accepted=False,native_calls_live=False)
        current=helper.OwnImpactHook(driver,b2_private_dir,report,lambda:None,fixture_kind=kind,
            leaf_factory=OwnLeafDeletionCatalog,runner_factory=JobRunner,fixture_factory=fixtures,target_factory=target_reader,**kwargs)
        current.construction();return current
    x.make_hook=hook;x.parent=parent;x.driver=driver;x.report_path=b2_private_dir/'report.json'
    return x


@pytest.mark.parametrize('kind',helper.KINDS)
def test_source_callback_uses_real_base_prepare_setup_commit_refusal_sql_and_original_cleanup_handoff(native_case,kind):
    x=native_case
    file=None
    if kind=='linked_equation':file=helper.prepare_equation_file(x.report_path.parent)
    hook=x.make_hook(kind,equation_file=file)
    hook.retire(x.sw,None,x.binding.model,[x.binding.model],x.owned,lambda models:None)
    report=hook.report
    assert hook.completed and len(x.delegations)==1 and x.flag_writes==[False,True]
    assert report['base_preparation']['status']=='succeeded'
    assert report['fixture_setup_job']['status']=='succeeded' and report['fixture_setup_job']['mutation']['phase']=='committed'
    assert report['refusal_batch']['domain_calls']=={'preview':1,'execute':1}
    assert all(row['status']=='failed' and 'mutation' not in row for row in report['refusal_batch']['jobs'])
    assert report['original_creation_receipt_before']==report['original_creation_receipt_after']
    assert all(report[key] is False for key in ('accepted','native_b2_accepted','public_mcp_accepted'))
    neighbor=x.owned[0]
    hook.retire(x.sw,None,neighbor,[neighbor],x.owned,lambda models:None)
    assert hook.delegations==2 and x.owned==[]


@pytest.mark.parametrize('fault',['parent_not_admitted','foreign_model','prepare_unknown','setter_pending','setter_null',
    'pending_ledger','after_setup_failure','batch_unknown','handoff','close_pending'])
def test_unconfirmed_ownership_setup_request_or_handoff_never_delegates_or_retries(native_case,fault):
    x=native_case;options={}
    if fault=='parent_not_admitted':
        x.parent['independent_native_readback_verified']=False
        x.report_path.write_text(json.dumps(x.parent,ensure_ascii=False),encoding='utf8')
    elif fault=='foreign_model':x.c.model.identity=object()
    elif fault=='prepare_unknown':
        class Leaf(OwnLeafDeletionCatalog):
            def prepare(self,*args,**kwargs):raise RuntimeError('Artificial uncertain preparation return')
        # Modify the factory only in this artificial hook, never production.
        options['leaf_factory']=Leaf
    elif fault=='setter_pending':x.fault='insert_pending'
    elif fault=='setter_null':x.fault='insert_null'
    elif fault=='pending_ledger':
        original=x.store.record_mutation_step
        def record(operation_id,*,name,phase,evidence):
            if name.endswith('insert_plane') and phase=='returned':raise OSError('Artificial durable receipt missing')
            return original(operation_id,name=name,phase=phase,evidence=evidence)
        x.store.record_mutation_step=record
    elif fault=='after_setup_failure':
        class Session(helper.B2ImpactSession):
            def capture(self,*args,**kwargs):raise ValueError('Actual current observation unavailable')
        options['session_factory']=Session
    elif fault=='batch_unknown':
        def batch(*args,**kwargs):raise RuntimeError('Actual request batch acknowledgement unavailable')
        options['batch']=batch
    else:x.callback_fault=fault
    hook=x.make_hook()
    for key,value in options.items():setattr(hook,key,value)
    with pytest.raises(Exception):hook.retire(x.sw,None,x.binding.model,[x.binding.model],x.owned,lambda models:None)
    writes=list(x.write_calls);delegations=list(x.delegations)
    with pytest.raises(ValueError):hook.retire(x.sw,None,x.binding.model,[x.binding.model],x.owned,lambda models:None)
    assert hook.failed and hook.report['parent_retained_sta_required'] is True
    assert x.write_calls==writes and x.delegations==delegations
    assert len(delegations)==(1 if fault=='close_pending' else 0)
    assert hook.report['accepted'] is hook.report['native_b2_accepted'] is False


def test_neighbor_projection_keeps_all_current_added_data_and_drops_only_declared_comparison_fields(proof):
    _,after,_=proof;current=after['snapshots']['target'];old=first_save(current)
    assert helper._json(helper.neighbor_projection(current,old))==helper._json(current) and current['scope']!=old['scope']
    hostile=deepcopy(current);hostile['clone_state']['material']=['foreign','']
    with pytest.raises(ValueError):helper.neighbor_projection(hostile,old)


def test_terminal_unknown_setup_persists_partial_comparisons_without_dispatching_preview_delete(native_case):
    x=native_case
    x.sw.IsSame=lambda left,right:2
    hook=x.make_hook()
    with pytest.raises(ValueError,match='setup terminal'):
        hook.retire(x.sw,None,x.binding.model,[x.binding.model],x.owned,lambda models:None)
    report=hook.report
    diagnostic=report['fixture_preparation_diagnostic']
    assert diagnostic['returned_plane_retained'] is True
    assert diagnostic['plane_birth_diagnostic']['returned_pid_equals_feature'] is True
    assert diagnostic['plane_birth_diagnostic']['returned_pid_equals_specific'] is True
    assert diagnostic['plane_birth_diagnostic']['native_same_code']==2
    assert diagnostic['plane_birth_diagnostic']['phase']=='native_equality'
    assert diagnostic['accepted'] is diagnostic['deletion_authorized'] is False
    setup=report['fixture_setup_job']
    assert setup['status']=='unknown' and setup['mutation']['phase']=='unresolved'
    assert setup['mutation']['reconciliation'] is None and report['native_calls_live'] is False
    assert len(setup['mutation']['verification']['native_steps'])==6
    assert 'refusal_batch' not in report and x.delegations==[]
    assert x.write_calls==['Select4','InsertRefPlane']


def test_equation_file_is_exclusive_private_and_exact_before_any_cad(b2_private_dir):
    facts=helper.prepare_equation_file(b2_private_dir)
    path=Path(facts['path']);assert helper.sha256(path)==facts['sha256']
    with pytest.raises(FileExistsError):helper.prepare_equation_file(b2_private_dir)


def test_returned_dimension_failure_is_preserved_in_wrapper_without_refusal_or_cleanup(native_case):
    from solidworks_mcp.jobs import ExecutionFailure
    x=native_case
    error=ExecutionFailure('persistent_reference_mismatch',
        'Dimension no longer belongs to the persistent owner feature.')
    failures=[]
    class Session(helper.B2ImpactSession):
        def capture(self,*args,**kwargs):
            def reject(*_):
                failures.append(error)
                raise error
            self.target.adapter.dimension_reference_is_current=reject
            return super().capture(*args,**kwargs)
    hook=x.make_hook(session_factory=Session)
    with pytest.raises(ValueError,match='setup terminal'):
        hook.retire(x.sw,None,x.binding.model,[x.binding.model],x.owned,lambda _:None)
    report=hook.report
    diagnostic=report['dimension_read_failure']
    assert failures==[error]
    assert diagnostic==hook.session.target.dimension_read_failure
    assert diagnostic['stage']=='dimension_reference_is_current'
    assert diagnostic['dimension_role'] in ('width','height','depth')
    assert diagnostic['boundary']=='current_capture'
    assert diagnostic['exception_code']==error.code and diagnostic['exception_message']==str(error)
    assert all(diagnostic[k] is False for k in ('accepted','native_b2_accepted','cleanup_authorized'))
    assert report['independent_read_exception_returned']['message']==str(error)
    assert report['fixture_setup_job']['status']=='unknown'
    assert report['fixture_setup_job']['mutation']['phase']=='unresolved'
    assert report['fixture_setup_job']['mutation']['reconciliation'] is None
    assert 'refusal_batch' not in report and x.delegations==[]


def test_equation_file_creation_outside_work_is_rejected(b2_outside_dir):
    with pytest.raises(ValueError,match='private fixture state'):
        helper.prepare_equation_file(b2_outside_dir)
    assert not (b2_outside_dir/'n5-owned-equations.txt').exists()


@pytest.mark.parametrize('bad',[False,True])
def test_cli_positive_preflight_uses_actual_artifact_sha_fixed_helpers_and_sql_before_native_callback(artifacts,b2_private_dir,bad):
    x=artifacts;state=b2_private_dir/'fresh_native_case';cad=[]
    class StopBeforeCAD(RuntimeError):pass
    driver=NS(RectangleConstructionCatalog=lambda *args:None,retire_owned=lambda *args:None,
        package_evidence=lambda *args,**kwargs:x.package)
    def main():
        state.mkdir()
        driver.package_evidence(NS(state_dir=state),installed=True)
        cad.append('would_initialize_native')
        raise StopBeforeCAD('Artificial driver intentionally stops before CAD')
    driver.main=main
    digest='0'*64 if bad else x.args.positive_report_sha256
    args=['--fixture-kind','linked_equation','--positive-report',str(x.positive_path),
        '--positive-report-sha256',digest,'--state-dir',str(state)]
    with pytest.raises((ValueError,StopBeforeCAD)):helper.main(args,driver=driver,leaf_factory=OwnLeafDeletionCatalog)
    assert cad==([] if bad else ['would_initialize_native'])
    assert (state/'n5-owned-equations.txt').exists() is (not bad)
    report=json.loads((state/'b2-impact-report.json').read_text(encoding='utf8'))
    assert report['accepted'] is False and report['native_b2_accepted'] is False
    assert set(report['verifier_hashes'])==set(helper.HELPERS)


def test_cli_rejects_outside_repo_work_before_driver_or_cad(artifacts,b2_outside_dir):
    x=artifacts;state=b2_outside_dir/'outside_native_case';calls=[]
    driver=NS(RectangleConstructionCatalog=lambda *args:None,retire_owned=lambda *args:None,
        main=lambda:calls.append('driver'),package_evidence=lambda *args,**kwargs:calls.append('package'))
    args=['--fixture-kind','linked_equation','--positive-report',str(x.positive_path),
        '--positive-report-sha256',x.args.positive_report_sha256,'--state-dir',str(state)]
    with pytest.raises(ValueError,match='Fresh private state'):
        helper.main(args,driver=driver,leaf_factory=OwnLeafDeletionCatalog)
    assert calls==[] and not state.exists()


def test_terminal_case_accepts_only_n5_scope_after_actual_terminal_sql_and_fixed_nonstl_baseline(native_case):
    x=native_case;hook=x.make_hook()
    hook.retire(x.sw,None,x.binding.model,[x.binding.model],x.owned,lambda models:None)
    neighbor=x.owned[0];hook.retire(x.sw,None,neighbor,[neighbor],x.owned,lambda models:None)
    preferences=dict(ordinary_toggle=False,stl_units=1)
    baseline=[['31.2.1',True,None,[]],[[],None,False,True],[]]
    parent=dict(phase='terminal',positive_case_passed=True,native_calls_live=False,baseline_restored=True,
        own_cleanup_verified=True,owned_documents=[],original_baseline=baseline,restored_baseline=deepcopy(baseline),
        original_application={'artificial':True},restored_application={'artificial':True},original_preferences=preferences,
        restored_preferences=dict(scope='application_preferences_except_stl_v1',excluded_fields=sorted(helper.DEFERRED_STL_FIELDS),
            snapshot_read=True,scope_exactly_equal=True,stl_preferences_verified=False,cause_inferred=False,
            before=preferences,after={**preferences,'stl_units':2}))
    x.report_path.write_text(json.dumps(parent,ensure_ascii=False),encoding='utf8')
    # This imported artificial fixture keeps its live DB in a nested directory;
    # the native driver stores jobs.sqlite beside report.json.
    with sqlite3.connect(x.report_path.with_name('jobs.sqlite')) as backup:
        x.store._db.backup(backup)
    helper.terminal_case(hook,x.report_path.parent,hook.report)
    assert hook.report['accepted'] is True and hook.report['native_b2_accepted'] is hook.report['public_mcp_accepted'] is False
    parent['restored_preferences']['after']['ordinary_toggle']=True
    x.report_path.write_text(json.dumps(parent,ensure_ascii=False),encoding='utf8')
    with pytest.raises(ValueError):helper.terminal_case(hook,x.report_path.parent,hook.report)
    parent['restored_preferences']['after']['ordinary_toggle']=False
    parent['original_baseline']=parent['restored_baseline']=[]
    x.report_path.write_text(json.dumps(parent,ensure_ascii=False),encoding='utf8')
    with pytest.raises(ValueError):helper.terminal_case(hook,x.report_path.parent,hook.report)
