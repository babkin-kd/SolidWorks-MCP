"""Installed metadata-only telemetry storage failure; no CAD dispatch.

A private directory occupies the timing SQLite filename before server startup.
The mandatory job journal remains a separate real SQLite file. This proves only
facade isolation, not native mutation/restoration or the complete B4-N6 gate.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from verify_installed_metadata import installed_identity, verify_metadata
from verify_wheel_artifact import validate_wheel, require
from verify_timings_v2 import envelope


SCOPE = 'installed_metadata_timing_storage_unavailable_v1'


async def exercise(entry, state, wheel):
    params = StdioServerParameters(command=str(entry), args=[
        '--state-dir', str(state), '--enable-timings', '--timings-max-records', '1000',
        '--timings-retention-days', '1', '--timings-max-mib', '16'],
        env={**os.environ, 'PYTHONPATH': '', 'PYTHONNOUSERSITE': '1'})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            info = envelope(await client.call_tool('system_get_info', {}))
            require(info['status'] == 'succeeded', 'Storage failure changed metadata response.')
            verify_metadata((await client.list_tools()).tools, info['data'], wheel)
            missing = envelope(await client.call_tool('job_get', {'operation_id': 'job_missing_storage_fault'}))
            require(missing['status'] == 'failed' and missing['error']['code'] == 'job_not_found',
                    'Telemetry storage failure masked the actual missing-job result.')
            measured = envelope(await client.call_tool('diagnostics_get_timings', {'period_s': 3600.}))
            require(measured['status'] == 'succeeded', 'Unavailable diagnostics query failed unexpectedly.')
            data = measured['data']
            require(data['enabled'] is True and data['available'] is False
                    and data['storage_failures'] >= 1 and data['sample_count'] == 0 and data['groups'] == [],
                    'Unavailable timing storage must be reported explicitly without invented records.')
            invalid = envelope(await client.call_tool('diagnostics_get_timings', {'period_s': -1.}))
            require(invalid['status'] == 'failed' and invalid['error']['code'] == 'invalid_timing_filter',
                    'Storage failure bypassed the declared filter contract.')
            return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    state = args.state_dir.resolve()
    private = Path(__file__).resolve().parents[1] / 'work'
    require(state.is_relative_to(private) and state != private and not state.exists(), 'Fresh private state required.')
    require(not os.environ.get('PYTHONPATH'), 'Use the installed package without source PYTHONPATH.')
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version, expected_git_sha=args.expected_git_sha)
    entry = installed_identity(wheel)
    state.mkdir(parents=True)
    (state / 'timings.sqlite').mkdir()  # Controlled, owned, reversible non-CAD fault.
    report = dict(scope=SCOPE, accepted=False, native_acceptance=False, native_b4_accepted=False,
                  wheel=wheel, verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  cad_tools_called=[], model_mutations=0, fault='timing_sqlite_path_is_own_directory')
    try:
        report['diagnostics'] = asyncio.run(exercise(entry, state, wheel))
        path = state / 'jobs.sqlite'
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            require(db.execute('PRAGMA user_version').fetchone()[0] == 3, 'Actual mandatory journal schema missing.')
            counts = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                      for table in ('jobs', 'mutations')}
        require(counts == {'jobs': 0, 'mutations': 0}, 'Metadata-only probe dispatched a durable CAD job.')
        report.update(accepted=True, sdk_closed=True, mandatory_journal_counts=counts,
                      timing_path_remains_owned_directory=(state / 'timings.sqlite').is_dir())
    except BaseException as error:
        report.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({key: report[key] for key in ('accepted', 'native_acceptance', 'native_b4_accepted',
                                                 'model_mutations', 'mandatory_journal_counts')}))


if __name__ == '__main__':
    main()
