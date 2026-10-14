"""Installed B2 public positive chain; exact internal evidence precedes COM.

This finite N1–N4 route does not accept all B2 requirements or stage 1.
The original B1 native owner controls fixtures, flags, supervised SDK shutdown
and retained STA on uncertainty. Pending COM is never cancelled or repeated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from verify_rectangle_stages_public import HELPERS as B1_HELPERS


HELPERS=('verify_b2_public.py','verifier_b2_public_preflight.py',
    'verifier_b2_public_observation.py','verifier_b2_session_mapping.py',
    'verifier_b2_native_observer.py','verifier_b2_scalar_rename.py',
    'verifier_b2_public_route.py','verifier_b2_public_contract.py',
    'verify_owned_leaf_deletion_positive.py','verify_owned_leaf_deletion_faults.py',
    'verifier_b2_observation_fault.py',*B1_HELPERS)


def require(condition,message):
    if not condition:raise ValueError(message)


def complete_public_positive(report,*,state_comparator=None):
    """The native owner must have actually completed its terminal cleanup."""
    extension=report['after_base_extension']
    require(report['phase']=='terminal' and report['native_calls_live'] is False
        and report['public_rectangle_passed'] is True
        and report.get('lifecycle_hold',False) is False
        and report.get('retained_process',False) is False
        and report['own_cleanup_verified'] is True and report['baseline_restored'] is True
        and report['supervised_cleanup_verified'] is True and report['owned_documents']==[]
        and report['original_baseline']==report['restored_baseline']
        and report['original_application']==report['restored_application']
        and extension['positive_case_passed'] is True and extension['accepted'] is False
        and extension['native_b2_accepted'] is False,
        'Terminal exact public B2 extension and original own cleanup/baseline are required.')
    labels={'B2-public-depth12-full9600','B2-public-Russian-name-same-reference',
        'B2-public-suppress-full-state','B2-public-return-full-state',
        'B2-public-leaf-preview-delete-replay-retired-ID'}
    require(len(extension['cases'])==len(labels)
        and {row['label'] for row in extension['cases']}==labels
        and all(row['passed'] is True for row in extension['cases']),
            'All five finite public B2 cases must have completed.')
    captures=report['captures']
    require(type(captures) is list and bool(captures)
        and all(type(row) is dict and row.get('status')=='returned' for row in captures),
            'Nonempty normally returned native captures are required for public completion.')
    from verifier_b2_public_route import extension_final_state,compare_b2_observed_state
    extension_final_state(extension,report['extrusion_job'],compare_state=
        compare_b2_observed_state if state_comparator is None else state_comparator)
    return dict(accepted=False,native_b2_accepted=False,public_mcp_accepted=False,
                public_positive_case_passed=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks',action='store_true')
    for name in ('positive','faults'):
        parser.add_argument('--'+name+'-report',type=Path,required=True)
        parser.add_argument('--'+name+'-report-sha256',required=True)
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--expected-version',required=True)
    parser.add_argument('--expected-git-sha',required=True)
    args=parser.parse_args(argv)
    require(args.run_solidworks,'Explicit --run-solidworks is required.')
    args.state_dir=args.state_dir.resolve()
    require(args.state_dir.is_relative_to(Path.cwd()/'work') and not args.state_dir.exists(),
            'Use a fresh private work/ directory.')
    args.state_dir.mkdir()
    scripts=Path(__file__).parent
    report=dict(scope='installed_b2_public_positive_only_v1',accepted=False,
        native_b2_accepted=False,public_mcp_accepted=False,public_positive_case_passed=False,
        phase='preflight',cases=[],captures=[],owned_documents=[],native_calls_live=False,
        verifier_hashes={name:hashlib.sha256((scripts/name).read_bytes()).hexdigest() for name in set(HELPERS)})
    started=time.perf_counter()
    def persist():
        report['elapsed_seconds']=time.perf_counter()-started
        (args.state_dir/'report.json').write_text(json.dumps(report,
            ensure_ascii=False,allow_nan=False,indent=2),encoding='utf8')
    try:
        from verifier_b2_public_preflight import preflight
        evidence=preflight(args)
        report['prerequisite_preflight']=evidence
        report.update({key:value for key,value in evidence.items() if key!='scope'})
    except BaseException as error:
        report.update(phase='preflight_failed',error=str(error));persist();raise
    persist()
    # Native dependencies and original fixture lifecycle are entered only here.
    from verify_rectangle_stages_public import _native_run
    from verifier_b2_public_observation import after_base
    from verifier_b2_public_contract import SPECS
    _native_run(args,report,persist,after_base=after_base,tool_specs=SPECS,terminal_acceptance=False)
    report.update(complete_public_positive(report));persist()
    print(json.dumps(dict(scope=report['scope'],public_positive_case_passed=True,
        native_b2_accepted=False,public_mcp_accepted=False)),flush=True)


if __name__=='__main__':main()
