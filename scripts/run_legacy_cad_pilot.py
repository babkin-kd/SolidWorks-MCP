"""Bounded source legacy pilot; reports never count as installed v2 acceptance."""
import argparse
import hashlib
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

import pytest

PILOT_NAMES = (
    'test_box', 'test_set_dimension', 'test_a_negative_size_is_refused',
    'test_a_value_solidworks_keeps_out_is_refused', 'test_a_points_coordinate_takes_its_sign',
    'test_set_dimension_turns_an_angle_in_degrees',
    'test_a_dimension_an_equation_drives_is_refused_by_its_equation',
    'test_cylinder', 'test_cone_frustum', 'test_disc',
    'test_revolve_cylinder', 'test_revolve_ring', 'test_revolve_partial',
    'test_box_width_and_height_are_dimensions', 'test_cylinder_radius_is_a_dimension',
    'test_cone_top_radius_is_a_dimension', 'test_revolved_ring_outer_radius_is_a_dimension',
    'test_profile_gets_one_dimension_per_distinct_edge_position',
    'test_global_variable_drives_a_sketch_dimension', 'test_inspect_counts',
)


class Results:
    def __init__(self): self.items, self.phases = [], []
    def pytest_collection_finish(self, session):
        self.items = [item.nodeid for item in session.items]
    def pytest_runtest_logreport(self, report):
        self.phases.append(dict(nodeid=report.nodeid, phase=report.when,
                                outcome=report.outcome, seconds=report.duration))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('inventory','cleanup-probe','pilot'), required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--cleanup-report', type=Path)
    args = parser.parse_args()
    if args.mode != 'inventory' and not args.run_solidworks:
        parser.error('Native pilot requires explicit --run-solidworks.')
    root = Path(__file__).resolve().parents[1]
    state = args.state_dir.resolve()
    if not state.is_relative_to(root/'work') or state == root/'work' or state.exists():
        parser.error('Use a fresh private state directory under work/.')
    safety_files = [root/'tests/conftest.py',root/'tests/legacy_cad_safety.py',Path(__file__)]
    envelope = {path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
                for path in safety_files}
    import solidworks_mcp
    from solidworks_mcp.build_info import source_digest
    if Path(solidworks_mcp.__file__).resolve().parent != root/'src/solidworks_mcp':
        parser.error('This legacy pilot requires PYTHONPATH=src; installed v2 acceptance is separate.')
    digest = source_digest(root/'src/solidworks_mcp')
    if args.mode == 'pilot':
        if not args.cleanup_report: parser.error('Pilot requires an accepted cleanup-probe report.')
        prior=json.loads(args.cleanup_report.read_text(encoding='utf8'))
        if (prior.get('mode') != 'cleanup-probe' or not prior.get('accepted')
                or prior.get('safety_files_sha256') != envelope or prior.get('source_digest') != digest):
            parser.error('Cleanup probe was not accepted for this exact envelope.')
    state.mkdir(parents=True)
    results=Results(); started=time.perf_counter()
    report=dict(accepted=False,mode=args.mode,scope='legacy_source_cad_pilot_v1',
        source_git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        version=solidworks_mcp.__version__, source_digest=digest,
        source_installation=str(Path(solidworks_mcp.__file__).resolve()),
        safety_files_sha256=envelope,v2_acceptance=False)
    (state/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    argv=['-m','solidworks','-q','--basetemp',str(state/'pytest-temp')]
    if args.mode == 'inventory': argv += ['--collect-only','tests']
    else:
        names=('test_box',) if args.mode == 'cleanup-probe' else PILOT_NAMES
        argv += ['--run-solidworks','--maxfail=1','--legacy-cad-pilot-report',str(state/'safety.json')]
        argv += [f'tests/test_features.py::{name}' for name in names]
    code=int(pytest.main(argv,plugins=[results]))
    report.update(pytest_exit=code,elapsed_seconds=time.perf_counter()-started,
                  items=results.items,phases=results.phases)
    if args.mode == 'inventory':
        report.update(accepted=code==0, groups=dict(Counter(nodeid.split('::')[0] for nodeid in results.items)),
                      native_executed=False, evidence_status='not_confirmed_by_collection')
    else:
        expected=1 if args.mode == 'cleanup-probe' else len(PILOT_NAMES)
        safety_path=state/'safety.json'
        safety=json.loads(safety_path.read_text(encoding='utf8')) if safety_path.exists() else {}
        calls=[row for row in results.phases if row['phase']=='call']
        counts=Counter(row['outcome'] for row in calls)
        counts['failed'] += sum(row['outcome']=='failed' for row in results.phases if row['phase']!='call')
        counts['skipped'] += sum(row['outcome']=='skipped' for row in results.phases if row['phase']!='call')
        report.update(results=dict(counts),not_run=expected-len({row['nodeid'] for row in calls}),
                      unknown=bool(safety.get('cleanup_unknown')),safety_accepted=safety.get('accepted',False),
                      cleanup_seconds=safety.get('cleanup_seconds'),
                      accepted=code==0 and counts['passed']==expected and safety.get('accepted',False))
    (state/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:report.get(k) for k in ('mode','accepted','results','not_run','unknown','elapsed_seconds')}))
    raise SystemExit(0 if report['accepted'] else code or 1)


if __name__ == '__main__': main()
