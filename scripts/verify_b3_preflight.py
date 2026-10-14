"""Offline installed-candidate B3 plan preflight; no CAD/SDK subprocess calls.

Reuses an exact-wheel metadata report instead of repeating its stdio workload.
This proves candidate/catalog/manifest coherence, never native B3 acceptance
or permission to alter an occupied session. The native owner still needs its
independent empty/free baseline and fixture/supervisor proofs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from verifier_b3_manifest import manifest_rows, required_tools
from verifier_b3_public_contract import SPECS
from verify_installed_metadata import installed_identity
from verify_wheel_artifact import validate_wheel


HELPERS = ('verify_b3_preflight.py', 'verifier_b3_manifest.py',
           'verifier_b3_public_contract.py', 'verifier_b3_journal.py',
           'verifier_b3_witnesses.py', 'verifier_b3_reader.py',
           'verifier_lifecycle.py', 'verify_installed_metadata.py', 'verify_wheel_artifact.py')


def validate_metadata(report, wheel):
    if (type(report) is not dict or report.get('accepted') is not True
            or report.get('scope') != 'installed_wheel_console_metadata_v1'
            or report.get('native_acceptance') is not False
            or report.get('cad_tools_called') != [] or report.get('job_tools_called') != []
            or report.get('wheel') != wheel):
        raise ValueError('Successful metadata-only report for the exact wheel required.')
    catalog = report.get('metadata_catalog')
    if type(catalog) is not dict:
        raise ValueError('Complete recorded metadata catalog required.')
    names = catalog.get('tool_names')
    if (type(names) is not list or not all(type(name) is str for name in names)
            or len(names) != len(set(names)) or type(catalog.get('public_tool_count')) is not int
            or catalog['public_tool_count'] != len(names)
            or not required_tools() <= set(names)
            or catalog.get('output_schemas_verified') is not True
            or catalog.get('build_matches_installed_wheel') is not True
            or type(catalog.get('schema_hash')) is not str
            or re.fullmatch(r'[0-9a-f]{64}', catalog['schema_hash']) is None):
        raise ValueError('Recorded exact schemas and complete B3 catalog coverage required.')
    if required_tools() != frozenset(SPECS):
        raise ValueError('B3 manifest/tool contracts differ.')
    return dict(scope='bounded_b3_run_preflight_v1', accepted=True,
                native_acceptance=False, cad_calls_started=False, can_start_native=False,
                wheel=wheel, schema_hash=catalog['schema_hash'],
                manifest=manifest_rows(), required_tools=sorted(required_tools()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--metadata-report', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    # All checks are passive; installed_identity rejects source PYTHONPATH.
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version,
                           expected_git_sha=args.expected_git_sha)
    installed_identity(wheel)
    metadata_bytes = args.metadata_report.read_bytes()
    result = validate_metadata(json.loads(metadata_bytes), wheel)
    result['metadata_report_sha256'] = hashlib.sha256(metadata_bytes).hexdigest()
    result['verifier_hashes'] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                 for name in HELPERS}
    with args.report.open('x', encoding='utf8') as stream:
        json.dump(result, stream, allow_nan=False, indent=2, ensure_ascii=False)
    print(json.dumps(dict(accepted=True, native_acceptance=False,
                          case_groups=len(result['manifest']), tools=len(result['required_tools']))))


if __name__ == '__main__':
    main()
