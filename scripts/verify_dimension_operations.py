"""Installed internal dimension-domain acceptance on an exact owned fixture.

This does not assert public MCP dimension availability. No user document is
saved/modified. Source mutation callbacks and the durable runner execute on the
same initialized apartment; independent extrema/volume verify the known box.
"""

import argparse
from concurrent.futures import Future
from contextlib import closing
from importlib import resources
import json
import math
from pathlib import Path
import sqlite3
import time

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures
from verify_export_operations import exact_solid, native_extrema_m, ui_snapshot
from verifier_fixture_cleanup import InlineFixtureCleanupGate, guarded_inline_submit


class Adapter(SolidWorksDocuments):
    def __init__(self):
        super().__init__()
        self.inject_after_write = False
        self.native_write_count = 0
        self.native_rebuild_count = 0

    def set_dimension_value(self, record, value_si, configuration):
        self.native_write_count += 1
        result = super().set_dimension_value(record, value_si, configuration)
        if self.inject_after_write:
            self.inject_after_write = False
            raise RuntimeError('Verifier injection after actual native setter, not a native COM failure.')
        return result

    def rebuild_dimension_document(self, model):
        self.native_rebuild_count += 1
        return super().rebuild_dimension_document(model)


class TimedCatalog(DimensionCatalog):
    """Measure complete captures without changing, caching or replaying them."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.capture_seconds = []

    def _capture(self, *args, **kwargs):
        started = time.monotonic()
        try:
            return super()._capture(*args, **kwargs)
        finally:
            elapsed = round(time.monotonic() - started, 3)
            self.capture_seconds.append(elapsed)
            print(json.dumps({'phase': 'dimension_capture', 'capture': len(self.capture_seconds),
                              'seconds': elapsed}), flush=True)


class Worker:
    def submit(self, function):
        future = Future()
        try:
            future.set_result(function())
        except BaseException as exc:
            future.set_exception(exc)
        return future


def require_inline_cleanup(gate):
    if gate.can_cleanup() is not True:
        raise RuntimeError('Retain owned fixtures without further native reads: job outcome or UI release is unconfirmed.')


def failure_baseline(gate, baseline):
    """Held outcomes are reported from Python only, never by further CAD getters."""
    if gate.can_cleanup() is not True:
        return None
    return native_snapshot() == baseline


def close_inline_resources(documents, store, gate, original):
    """Attempt both closures; failed cleanup never replaces the operation error."""
    errors = []
    for resource in (documents, store):
        try:
            resource.close()
        except BaseException as error:
            gate.retain()
            errors.append(error)
    if original is not None:
        for error in errors:
            original.add_note(f'Verifier resource cleanup failed: {type(error).__name__}')
    elif errors:
        for error in errors[1:]:
            errors[0].add_note(f'Additional resource cleanup failed: {type(error).__name__}')
        raise errors[0]


def check(state, *, cleanup_gate=None, failure_report=None):
    cleanup_gate = cleanup_gate if cleanup_gate is not None else InlineFixtureCleanupGate()
    assert 'site-packages' in solidworks_mcp.__file__
    package = Path(solidworks_mcp.__file__).resolve().parent
    build = json.loads(resources.files('solidworks_mcp').joinpath('build_info.json').read_text(encoding='utf8'))
    assert build['package_version'] == solidworks_mcp.__version__
    assert build['source_digest'] == source_digest(package)
    assert build['source_dirty'] is False
    assert isinstance(build['git_sha'], str) and len(build['git_sha']) == 40
    original = native_snapshot()
    report = {'package_version': solidworks_mcp.__version__, 'public_mcp_dimension_acceptance': False,
              'git_sha': build['git_sha'], 'source_dirty': build['source_dirty'],
              'installed_source_digest': build['source_digest'], 'installed_build_matches_package': True}
    if failure_report is not None:
        failure_report.update(report)
    with fixtures(cleanup_gate=cleanup_gate.can_cleanup) as (_, owned, _):
        adapter = Adapter()
        documents = DocumentCatalog(adapter)
        store = JobStore(state / 'jobs.sqlite')
        primary_error = None
        try:
            model = owned[1]
            sw, module = adapter._sw, binding.module()
            source_ui = ui_snapshot(sw, module)
            other_metadata = adapter.snapshot(owned[0])
            doc = next(row for row in documents.list()['documents'] if row['title'] == model.GetTitle())
            catalog = TimedCatalog(documents, store, 'native_dimensions', mutation_guard=adapter.mutation_guard)
            page = catalog.list(doc['document_id'], 'Основная')
            assert page['total_count'] == 3
            target = next(row for row in page['items'] if row['owner']['feature_type'] == 'Extrusion')
            assert target['object_id'] and not target['write_blockers']
            assert target['reference_anchor']['strategy'] == 'display_dimension_v1'
            assert math.isclose(target['values']['Основная'], 7., abs_tol=1e-10)
            # The successful mutation below must match this same revision in
            # both complete prepare and pre-setter validate captures. A second
            # initial list would duplicate that cross-read consistency proof.
            runner = JobRunner(store, Worker())

            def submit(request, revision, value):
                args = {'document_id': doc['document_id'], 'configuration': 'Основная',
                        'object_id': target['object_id'], 'expected_revision': revision, 'value': value, 'unit': 'mm'}
                job = guarded_inline_submit(cleanup_gate, runner, store, request, 'dimension.set_value', args,
                    lambda operation_id: catalog.set_value(operation_id, **args),
                    context={key: args[key] for key in ('document_id', 'configuration', 'expected_revision')},
                    mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)
                require_inline_cleanup(cleanup_gate)
                return job

            def physical(depth):
                require_inline_cleanup(cleanup_gate)
                try:
                    body = exact_solid(model, module)
                    bounds = native_extrema_m(body)
                    size = [1000 * (b - a) for a, b in zip(bounds['min'], bounds['max'])]
                    assert all(math.isclose(a, b, abs_tol=1e-7) for a, b in zip(size, [5., 6., depth])), size
                    volume = float(body.GetMassProperties(1.)[3]) * 1e9
                    assert math.isclose(volume, 5 * 6 * depth, abs_tol=1e-5), volume
                    assert ui_snapshot(sw, module) == source_ui
                    assert adapter.snapshot(owned[0]) == other_metadata
                    return {'dimensions_mm': size, 'volume_mm3': volume}
                except BaseException:
                    cleanup_gate.retain()
                    raise

            physical(7.)
            changed = submit('change', page['revision'], 9.)
            assert changed['status'] == 'succeeded', changed
            assert changed['mutation']['phase'] == 'committed'
            assert changed['mutation']['before_state']['_mutation_effect_scope'] == 'application'
            assert changed['result']['execution_guard'] == {'original_state': 0, 'locked_state': 2, 'released_state': 0}
            report['changed_geometry'] = physical(9.)
            retry = submit('change', page['revision'], 9.)
            assert retry['operation_id'] == changed['operation_id']
            assert catalog.get(doc['document_id'], 'Основная', target['object_id'])['dimension']['values']['Основная'] == 9.
            stale = submit('stale', page['revision'], 11.)
            assert stale['status'] == 'failed' and stale['error']['code'] == 'stale_revision'
            physical(9.)
            # _state retains its two full captures and all closing proofs.
            # Bind the injected mutation's revision and geometry baseline to
            # this one accepted state, rather than separate list/state reads.
            before_state = catalog._state(doc['document_id'], 'Основная')
            before_geometry = before_state[3]['geometry']
            adapter.inject_after_write = True
            restored = submit('injected', before_state[4], 11.)
            assert restored['status'] == 'failed' and restored['mutation']['phase'] == 'rolled_back', restored
            assert restored['mutation']['verification']['evidence']['execution_guard']['released_state'] == 0
            assert catalog._state(doc['document_id'], 'Основная')[3]['geometry'] == before_geometry
            physical(9.)
            assert store.mutation_blockers('native_dimensions', 'another_document') == []
            assert adapter.native_write_count == 3 and adapter.native_rebuild_count == 2
            report.update(native_typed_configuration_setter=True, actual_native_status=changed['result']['value']['native_status'],
                explicit_dimension_reference_survives_rebuild=True, same_request_does_not_duplicate_write=True,
                stale_revision_rejected=True, verified_scoped_restoration_after_injected_error=True,
                actual_native_error_injected=False, other_owned_document_unchanged=True,
                ui_guard_released_and_durable=True, dimension_revision_scope=page['revision_scope'],
                actual_native_write_count=adapter.native_write_count,
                actual_native_rebuild_count=adapter.native_rebuild_count,
                complete_capture_seconds=catalog.capture_seconds)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                close_inline_resources(documents, store, cleanup_gate, primary_error)
            finally:
                if failure_report is not None:
                    failure_report.update(owned_fixtures_retained=not cleanup_gate.can_cleanup(),
                        retained_owned_fixture_count=len(owned) if not cleanup_gate.can_cleanup() else 0,
                        actual_native_write_count=adapter.native_write_count,
                        actual_native_rebuild_count=adapter.native_rebuild_count,
                        complete_capture_seconds=catalog.capture_seconds if 'catalog' in locals() else [])
    require_inline_cleanup(cleanup_gate)
    assert native_snapshot() == original
    report['original_document_baseline_restored'] = True
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    assert not args.state_dir.exists() and not args.report.exists()
    args.state_dir.mkdir(parents=True)
    pythoncom.CoInitialize()
    try:
        baseline = native_snapshot()
        cleanup_gate = InlineFixtureCleanupGate()
        failure_context = {}
        try:
            result = check(args.state_dir, cleanup_gate=cleanup_gate, failure_report=failure_context)
        except BaseException as exc:
            # Inspect, never reopen/recover with JobStore or replay a failed job.
            journal = args.state_dir / 'jobs.sqlite'
            jobs = []
            try:
                if journal.exists():
                    with closing(sqlite3.connect(journal.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                        jobs = [{'request_id': request, 'status': status, 'mutation_phase': phase,
                                 'error': json.loads(error) if error else None}
                                for request, status, phase, error in db.execute(
                                    'SELECT j.request_id,j.status,m.phase,j.error FROM jobs j '
                                    'LEFT JOIN mutations m USING(operation_id) ORDER BY j.created_at')]
                failure = {'package_version': solidworks_mcp.__version__, 'accepted': False,
                    'public_mcp_dimension_acceptance': False, 'error_type': type(exc).__name__,
                    'jobs': jobs, 'original_document_baseline_restored': failure_baseline(cleanup_gate, baseline),
                    **failure_context, 'private_journal_preserved': True, 'automatic_replay_attempted': False}
                args.report.write_text(json.dumps(failure, indent=2) + '\n', encoding='utf8')
                print(json.dumps(failure, indent=2), flush=True)
            except BaseException as report_error:
                exc.add_note(f'Failure reporting failed: {type(report_error).__name__}; private journal retained.')
            raise
        result['accepted'] = True
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
        print(json.dumps(result, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
