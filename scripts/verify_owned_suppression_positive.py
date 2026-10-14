"""Installed own-feature suppression cycle on the B1 fixture/cleanup driver.

The reused driver creates the original features through their actual domain and
JobRunner, so ownership is real, not reconstructed from a compatibility probe.
No new CAD fixture scenario is duplicated. This positive/replay report alone
does not accept all B2 cases or public MCP. Failed reports are preserved.
"""
import hashlib
import json
from pathlib import Path
import time


def install_hook(driver, report, persist):
    """One root-owned finite callback after the terminal extrusion creation job."""
    from solidworks_mcp.feature_suppression_catalog import FeatureSuppressionCatalog
    from solidworks_mcp.jobs import JobRunner, _json
    from solidworks_mcp.owned_suppression_postconditions import (
        verified_owned_suppression, verified_owned_return)
    original_catalog, original_check = driver.RectangleConstructionCatalog, driver.verified_rectangle_job
    retained = dict(domain=None,called=False)

    class Construction(original_catalog):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            if retained['domain'] is not None: raise AssertionError('One owned construction context required.')
            retained['domain'] = self

    def check(job):
        accepted = original_check(job)
        if not accepted or job['operation'] != 'part.extrude_rectangle' or retained['called']:
            return accepted
        retained['called'] = True  # Never repeat a failed/unknown callback.
        construction = retained['domain']
        assert construction is not None and construction.store.get(job['operation_id'])['status'] == 'succeeded'
        domain = FeatureSuppressionCatalog(construction.documents,construction.store,
            construction.connection_epoch,construction.ownership)
        runner = JobRunner(construction.store,driver.InlineSta())
        value = job['result']['value']
        target, cfg, feature_id = value['document_id'],value['configuration'],value['feature_object_id']
        report.update(phase='suppression_prepare',native_calls_live=True,
            creation_operation_id=job['operation_id'],document_id=target,configuration=cfg,object_id=feature_id)
        persist()
        first = None
        for requested in (True,False):
            args = dict(document_id=target,configuration=cfg,object_id=feature_id,suppressed=requested)
            label = 'suppress' if requested else 'return'
            report['phase'] = label+'_prepare';persist()
            prepared = runner.submit(label+'_prepare','feature.prepare_suppression',args,
                lambda:domain.prepare(**args),context=args)
            report.setdefault('preparations',[]).append(prepared);persist()
            assert prepared['status'] == 'succeeded',prepared['error']
            if first is None: first = prepared['result']['baseline']
            args['expected_revision'] = prepared['result']['revision']
            report['phase'] = label+'_native';persist()
            changed = runner.submit(label+'_job','feature.set_suppressed',args,
                lambda operation_id:domain.set_suppressed(operation_id,**args),context=args,
                mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
            report.setdefault('jobs',[]).append(changed)
            report['native_receipts'] = {key:{
                'journal_failed':context['journal_failed'],'pending_release':context['pending_release'],
                'pending_body_name':context['pending_body_name'],
                'actions':[action.receipt.evidence() for action in context['actions']]}
                for key,context in domain.receipts.items()}
            persist()
            assert changed['status'] == 'succeeded',changed['error']
            mutation = changed['mutation'];result = changed['result'];guard = result['execution_guard']
            assert mutation['phase'] == 'committed' and mutation['verification']['outcome'] == 'committed'
            assert _json(result['after']) == _json(mutation['verification']['evidence']['after'])
            assert guard['guard_released'] is True and guard['pending_release'] is False
            assert guard['journal_failed'] is False and guard['full_release_check'] == 'effect'
            assert result['after']['pending'] is False and result['after']['guard_released'] is True
            oracle = verified_owned_suppression if requested else verified_owned_return
            assert (oracle(first,result['after']['state'],target,construction.ownership.resolve(
                target,cfg,feature_id,connection_epoch=construction.connection_epoch)[0].native_id)
                if requested else oracle(first,result['after']['state'],target))
            replay = runner.submit(label+'_job','feature.set_suppressed',args,
                lambda operation_id:(_ for _ in ()).throw(AssertionError('Native replay is forbidden')),
                context=args,mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
            assert replay == changed and not domain.receipts
            report.setdefault('cases',[]).append(dict(label=label+'_and_replay',passed=True));persist()
        assert not domain.contexts
        report.update(phase='cycle_terminal',positive_cycle_passed=True,native_calls_live=False);persist()
        return accepted

    driver.RectangleConstructionCatalog,driver.verified_rectangle_job = Construction,check
    return retained


def main():
    # The existing CLI performs the exact installed wheel/site-packages/clean SHA
    # preflight before COM connection. This wrapper preserves its command flags.
    import sys
    import verify_rectangle_stages_positive as driver
    args = sys.argv[1:]
    if '--state-dir' not in args: raise ValueError('Explicit fresh private state directory required.')
    state = Path(args[args.index('--state-dir')+1]).resolve()
    if not state.is_relative_to(Path.cwd()/'work') or state.exists():
        raise ValueError('Use a fresh child of private work/.')
    started = time.perf_counter()
    report = dict(scope='installed_owned_suppression_positive_v1',accepted=False,native_b2_accepted=False,
        public_mcp_accepted=False,phase='preflight',positive_cycle_passed=False,native_calls_live=False,
        wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        fixture_driver_sha256=hashlib.sha256(Path(driver.__file__).read_bytes()).hexdigest())
    def persist():
        if state.exists():
            report['elapsed_seconds'] = time.perf_counter()-started
            (state/'suppression-report.json').write_text(json.dumps(report,ensure_ascii=False,
                allow_nan=False,indent=2),encoding='utf8')
    install_hook(driver,report,persist)
    try:
        driver.main()
        fixture = json.loads((state/'report.json').read_text(encoding='utf8'))
        assert fixture['positive_case_passed'] is True and fixture['baseline_restored'] is True
        assert fixture['native_calls_live'] is False and report['positive_cycle_passed'] is True
        report.update(phase='terminal',baseline_restored=True,native_calls_live=False,
            wheel=fixture['wheel'],fixture_report_sha256=hashlib.sha256((state/'report.json').read_bytes()).hexdigest())
    finally:
        persist()


if __name__ == '__main__': main()
