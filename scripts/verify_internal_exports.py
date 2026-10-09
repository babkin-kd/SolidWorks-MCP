"""Installed internal export acceptance on disposable owned native fixtures.

Root executes this verifier; authoring it is not native acceptance. All calls
run synchronously on one initialized main STA. Public MCP exports remain outside
this verifier. Private journal and all outputs (especially uncertain ones) are
retained; no generic output cleanup, replay, cancellation or user CAD save.
"""

import argparse
import asyncio
from concurrent.futures import Future
from contextlib import ExitStack
from importlib import resources
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import uuid

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.cad_exports_v2 import CadExportsAdapter
from solidworks_mcp.cad_planar_brep import PLANAR_BREP_SCOPE
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.exports_v2 import ExportCatalog, ExportOptions
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures
from verifier_fixture_cleanup import InlineFixtureCleanupGate, guarded_inline_submit
from verifier_export_diagnostics import (capture_ui_difference, close_resources_with_gate,
    independent_baseline_check, require_fixture_native_access, ui_snapshot_unmeasured)
from verify_export_operations import (application_preferences, assert_owned_source_facts_unchanged,
    assert_stl_frame_and_units,
    exact_solid, fixture_preferences_baseline, independent_binary_stl, independent_file_facts,
    owned_source_snapshot, ui_snapshot, user_file_metadata)


class InlineWorker:
    """Execute real native callbacks on the verifier's main apartment, once."""

    def __init__(self):
        self.thread = threading.get_ident()
        self.dispatch_count = 0

    def submit(self, function):
        assert threading.get_ident() == self.thread
        self.dispatch_count += 1
        future = Future()
        try:
            future.set_result(function())
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, timeout_s=5):
        assert threading.get_ident() == self.thread
        return True


class InlineJobRunner(JobRunner):
    def __init__(self, store):
        super().__init__(store, InlineWorker())


class ObservedExtension:
    """Delegate one native extension, recording only the SaveAs3 call boundary."""

    def __init__(self, extension, before_saveas):
        self.extension, self.before_saveas = extension, before_saveas

    def __getattr__(self, name):
        return getattr(self.extension, name)

    def SaveAs3(self, *args, **kwargs):
        # Python-only observation: no preference/metadata getters between the
        # parent's complete profile gate and this unchanged native invocation.
        self.before_saveas()
        return self.extension.SaveAs3(*args, **kwargs)


def compact_job_failure(job):
    """Keep assertion output bounded; the full checkpoint remains in SQLite."""
    mutation = job.get('mutation') or {}
    result = job.get('result') or {}
    verification = mutation.get('verification') or {}
    evidence = verification.get('evidence') or {}
    return {'operation_id': job.get('operation_id'), 'status': job.get('status'),
            'error': job.get('error'), 'mutation': {'phase': mutation.get('phase')},
            'execution_guard': result.get('execution_guard') or evidence.get('execution_guard')}


def _diagnostic_code(value):
    # Codes, not arbitrary messages, names, file paths or pointer renderings.
    return value if type(value) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,79}', value) else None


def bounded_exception_chain(error):
    """Inspect only Python exception metadata; never stringify native objects."""
    items, seen = [], set()
    while isinstance(error, BaseException) and len(items) < 8 and id(error) not in seen:
        seen.add(id(error))
        kind = type(error).__name__
        data = BaseException.__getattribute__(error, '__dict__')
        data = data if type(data) is dict else {}
        items.append({'error_type': kind if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', kind) else None,
                      'error_code': _diagnostic_code(data.get('code')),
                      'uncertain': data.get('uncertain') if type(data.get('uncertain')) is bool else None})
        cause = BaseException.__cause__.__get__(error)
        if cause is not None:
            error = cause
        elif not BaseException.__suppress_context__.__get__(error):
            error = BaseException.__context__.__get__(error)
        else:
            error = None
    return {'items': items, 'truncated_or_cycle': isinstance(error, BaseException)}


def record_export_failure_diagnostic(report, *, job=None, error=None, cleanup_allowed=None):
    """Best-effort, bounded Python-only observations before any cleanup gate.

    The job is the already-returned durable snapshot, not a fresh store/CAD read.
    Checkpoint/desired deviation are historical dependencies; this does not
    claim to have measured the current preference after an unconfirmed restore.
    """
    try:
        if error is not None:
            report['operation_exception_chain'] = bounded_exception_chain(error)
        if type(job) is not dict:
            return
        status = job.get('status')
        if type(status) is str and status == 'succeeded' and cleanup_allowed is True:
            return
        mutation = job.get('mutation')
        mutation = mutation if type(mutation) is dict else {}
        before = mutation.get('before_state')
        before = before if type(before) is dict else {}
        source = before.get('source')
        source = source if type(source) is dict else {}
        profile = source.get('export_profile')
        profile = profile if type(profile) is dict else {}
        desired = profile.get('desired_application_preferences')
        desired = desired if type(desired) is dict else {}
        preferences = before.get('preferences')
        preferences = preferences if type(preferences) is dict else {}
        def deviation(values):
            # The installed adapter and durable checkpoint store metres.
            value = values.get('stl_deviation_m')
            return value * 1e6 if type(value) in (float, int) and abs(value) < 1e3 and math.isfinite(value) else None
        verification = mutation.get('verification')
        verification = verification if type(verification) is dict else {}
        evidence = verification.get('evidence')
        evidence = evidence if type(evidence) is dict else {}
        guard = evidence.get('execution_guard')
        result = job.get('result')
        result = result if type(result) is dict else {}
        if type(guard) is not dict:
            guard = result.get('execution_guard')
        guard = guard if type(guard) is dict else {}
        job_error = job.get('error')
        job_error = job_error if type(job_error) is dict else {}
        operation = job.get('operation_id')
        phase = mutation.get('phase')
        facts = {'operation_id': operation if type(operation) is str
                    and re.fullmatch(r'(?:job_|op_)?[0-9a-f]{32}', operation) else None,
            'status': status if type(status) is str and status in ('queued', 'running', 'succeeded', 'failed', 'unknown', 'cancelled') else None,
            'phase': phase if type(phase) is str and phase in ('prepared', 'committed', 'rolled_back', 'not_started', 'unresolved', 'reconciled') else None,
            'error': {'code': _diagnostic_code(job_error.get('code')),
                      'requires_reconciliation': job_error.get('requires_reconciliation')
                          if type(job_error.get('requires_reconciliation')) is bool else None,
                      'message_omitted': True},
            'cleanup_allowed': cleanup_allowed if type(cleanup_allowed) is bool else None,
            'dependencies': {'effect_scope': before.get('_mutation_effect_scope')
                    if type(before.get('_mutation_effect_scope')) is str
                       and before.get('_mutation_effect_scope') in ('application', 'document') else None,
                'revision_scope': _diagnostic_code(before.get('scope')),
                'source_snapshot_present': bool(source), 'checkpoint_preferences_present': bool(preferences),
                'checkpoint_stl_deviation_um': deviation(preferences), 'desired_stl_deviation_um': deviation(desired),
                'current_preferences_measured': False},
            'verification_outcome': _diagnostic_code(verification.get('outcome')),
            'execution_guard': {key: guard.get(key) if type(guard.get(key)) is int and 0 <= guard[key] <= 2 else None
                for key in ('original_state', 'locked_state', 'released_state')}}
        history = report.setdefault('job_failure_diagnostics', [])
        history.append(facts)
        del history[:-8]
    except BaseException:
        # Reporting is not part of the native outcome and cannot replace it.
        try:
            report['failure_diagnostic_formatting_failed'] = True
        except BaseException:
            pass


class ObservedExportsAdapter(CadExportsAdapter):
    """Audit durable hold/UI guard immediately before the actual native export.

    No native response is fabricated or failure injected. Parent implementation
    still performs actual SaveAs3 and native preference restoration.
    """

    def __init__(self, adapter, store, epoch):
        super().__init__(adapter)
        self.store, self.epoch = store, epoch
        self.expected_operation = None
        self.native_calls = []
        self.saveas_attempts = []

    @property
    def saveas_attempt_count(self):
        return len(self.saveas_attempts)

    def _record_saveas_attempt(self):
        # Append immediately before delegation, including raised native calls.
        # Adapter entry and attempted SaveAs3 are deliberately separate facts.
        self.saveas_attempts.append(self.expected_operation)

    def _extension(self, model):
        return ObservedExtension(self.documents_adapter._extension(model), self._record_saveas_attempt)

    def export_part_to_file(self, model, path, options, before):
        assert self.expected_operation, 'Native export lacks verifier operation ownership.'
        checkpoint = self.store.get(self.expected_operation)['mutation']
        assert checkpoint and checkpoint['phase'] == 'prepared'
        assert checkpoint['before_state']['_mutation_effect_scope'] == 'application'
        # Application holds must block other documents and other epochs too.
        for epoch in (self.epoch, 'unrelated-verifier-epoch'):
            blockers = self.store.mutation_blockers(epoch, 'unrelated-verifier-document')
            assert any(row['operation_id'] == self.expected_operation for row in blockers), blockers
        assert int(model.GetBlockingState()) == 2, 'Real UI guard was not acquired.'
        self.native_calls.append(self.expected_operation)
        return super().export_part_to_file(model, path, options, before)


def _provenance():
    package = Path(solidworks_mcp.__file__).resolve().parent
    assert 'site-packages' in package.parts, 'Use an installed wheel, never source PYTHONPATH.'
    assert not os.environ.get('PYTHONPATH'), 'Unset PYTHONPATH before native acceptance.'
    build = json.loads(resources.files('solidworks_mcp').joinpath('build_info.json').read_text(encoding='utf8'))
    actual_digest = source_digest(package)
    assert build.get('package_version') == solidworks_mcp.__version__
    assert build.get('source_digest') == actual_digest, 'Installed build metadata does not match its files.'
    return {'package_version': solidworks_mcp.__version__, 'git_sha': build.get('git_sha'),
            'source_dirty': build.get('source_dirty'), 'installed_source_digest': actual_digest,
            'installed_build_matches_package': True}


def _reject(function, *codes):
    try:
        function()
    except ExecutionFailure as exc:
        assert exc.code in codes, (exc.code, str(exc))
        assert exc.uncertain is False
        return exc.code
    raise AssertionError('Expected a known pre-write rejection.')


def _format_facts(path, manifest, source, units):
    if manifest['format'] == 'stl':
        parsed = independent_binary_stl(path)
        assert_stl_frame_and_units(parsed, source['native_extrema_m'], units)
        assert manifest['units'] == units and manifest['units_embedded'] is False
        return {'triangles': parsed['triangles'], 'native_extrema_and_requested_scale_verified': True,
                'negative_source_coordinates_preserved': True,
                'coordinates': {'min': parsed['min'], 'max': parsed['max']}}
    if manifest['format'] == 'step':
        content = path.read_text(encoding='ascii', errors='replace')
        assert 'ISO-10303-21;' in content[:256] and 'END-ISO-10303-21;' in content[-4096:]
        units_found = re.findall(r'\bSI_UNIT\s*\(\s*(\$|\.MILLI\.)\s*,\s*\.METRE\.\s*\)', content)
        assert units_found and len(set(units_found)) == 1, 'STEP length units are absent or ambiguous.'
        declared = 'mm' if units_found[0] == '.MILLI.' else 'm'
        assert manifest['units'] == declared and manifest['units_embedded'] is True
        return {'exchange_header_verified': True, 'declared_length_units': declared,
                'geometry_roundtrip_verified': False}
    assert manifest['format'] == 'parasolid'
    header = path.read_bytes()[:4096]
    assert header.startswith(b'**') and b'PARASOLID' in header.upper()
    assert manifest['units'] is None and manifest['units_embedded'] is None
    return {'text_transmit_header_verified': True, 'file_units_independently_verified': False,
            'geometry_roundtrip_verified': False}


def cleanup_baseline_flags(readers):
    """Read every independent baseline even if a separate reader fails.

    A failed read produces None, never an invented restoration result. This
    reporting helper does not suppress the verifier's primary exception.
    """
    facts, errors = {}, {}
    for name, (reader, expected) in readers.items():
        try:
            facts[name] = reader() == expected
        except BaseException as exc:
            facts[name] = None
            errors[name] = {'error_type': type(exc).__name__, 'message': str(exc)}
    return {**facts, 'cleanup_baseline_read_errors': errors}


def check(state, output, *, failure_report=None):
    report = {**_provenance(), 'public_mcp_export_acceptance': False,
              'asynchronous_pending_timeout_acceptance': False,
              'fault_injection_rollback_and_crash_acceptance': False,
              'arbitrary_brep_acceptance': False, 'geometry_roundtrip_verified': False}
    original = native_snapshot()
    original_sw, original_module = binding.connect(show=False), binding.module()
    original_preferences = application_preferences(original_sw)
    original_ui = ui_snapshot(original_sw, original_module)
    original_files = user_file_metadata(original)
    confirmed_paths = {}
    results, committed_arguments = [], []
    store = None
    documents = None
    exports = None
    primary_failure = None
    fixture_cleanup_gate = InlineFixtureCleanupGate()
    owned_fixture_count = 0
    resource_cleanup_errors = []

    def close_resources():
        nonlocal documents, store
        closing = [('documents', documents), ('store', store)]
        documents = store = None
        active_error = primary_failure if primary_failure is not None else sys.exc_info()[1]
        close_resources_with_gate(closing, fixture_cleanup_gate, resource_cleanup_errors,
                                  primary_error=active_error)

    try:
        with fixtures(cleanup_gate=fixture_cleanup_gate.can_cleanup) as (session, owned, _), ExitStack() as cleanup:
            owned_fixture_count = len(owned)
            # Release watches/adapter/journal on this STA before fixtures closes
            # its exact owned documents, including every failure path.
            cleanup.callback(close_resources)
            adapter = SolidWorksDocuments()
            sw, module = adapter._sw, binding.module()
            model = owned[1]
            assert adapter.identity(session._model) == adapter.identity(model)
            assert adapter.identity(binding.wrap(sw.ActiveDoc, module.IModelDoc2)) == adapter.identity(model)
            setup_preferences = application_preferences(sw)
            # Edit only the exact second verifier-owned, unsaved source.
            assert str(model.GetPathName()) == ''
            session.delete_feature('Контрольный чужой блок', with_children=True)
            session.add_extruded_profile([[-25, -30], [-20, -30], [-20, -24], [-25, -24]],
                                        7, name='Отрицательный контрольный блок', merge=False)
            for feature in session._iter_features():
                if feature.GetTypeName2() in ('ProfileFeature', '3DProfileFeature'):
                    feature.Name = 'Отрицательный контрольный эскиз'
                    assert feature.Name == 'Отрицательный контрольный эскиз'
            body = exact_solid(model, module)
            body.Name = 'Отрицательное контрольное тело'
            assert body.Name == 'Отрицательное контрольное тело'
            assert model.ForceRebuild3(False)
            model.ClearSelection2(True)
            before_preferences = application_preferences(sw)
            report.update(fixture_preferences_baseline(setup_preferences, before_preferences))
            documents = DocumentCatalog(adapter)
            store = JobStore(state / 'jobs.sqlite')
            epoch = 'internal-exports-' + uuid.uuid4().hex
            exports = ObservedExportsAdapter(adapter, store, epoch)
            catalog = ExportCatalog(documents, store, epoch, output,
                                    adapter=exports, mutation_guard=adapter.mutation_guard)
            runner = InlineJobRunner(store)
            rows = documents.list()['documents']
            target, mixed = [next(row for row in rows if row['title'] == item.GetTitle())
                             for item in (model, owned[0])]
            context = {'document_id': target['document_id'], 'configuration': 'Основная'}
            source = owned_source_snapshot(model, module)
            assert source['selection_count'] == 0 and source['blocking_state'] == 0
            assert source['active_configuration'] == 'Основная'
            assert min(source['native_extrema_m']['min']) < 0
            setup, setup_ui = native_snapshot(), ui_snapshot(sw, module)
            semantic = exports.export_source_snapshot(model)
            assert all(row['boundary_snapshot']['scope'] == PLANAR_BREP_SCOPE for row in semantic['bodies'])

            def unchanged():
                def independent_checks():
                    assert native_snapshot() == setup, 'Export changed native document metadata/active configuration.'
                    observed_ui = capture_ui_difference(lambda: ui_snapshot(sw, module), setup_ui, report,
                                                        'setup_ui_snapshot_difference')
                    assert observed_ui == setup_ui, 'Export changed native selection/UI blocking.'
                    report.update(assert_owned_source_facts_unchanged(
                        source, owned_source_snapshot(model, module)))
                    assert exports.export_source_snapshot(model) == semantic, 'Full supported source boundary changed.'
                    assert application_preferences(sw) == before_preferences, 'Global preferences were not restored.'
                return independent_baseline_check(independent_checks, fixture_cleanup_gate,
                    native_activity=bool(exports.native_calls or exports.saveas_attempt_count))

            def submit(request, arguments):
                def operation(operation_id):
                    exports.expected_operation = operation_id
                    try:
                        return catalog.execute(operation_id, **arguments)
                    except BaseException as operation_error:
                        record_export_failure_diagnostic(report, error=operation_error)
                        raise
                    finally:
                        exports.expected_operation = None
                job = guarded_inline_submit(fixture_cleanup_gate, runner, store,
                    request, 'internal.export_part', arguments, operation,
                    context={key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')},
                    mutates=True, pass_operation_id=True,
                    verify=lambda result: result.get('verified') is True)
                record_export_failure_diagnostic(report, job=job,
                    cleanup_allowed=fixture_cleanup_gate.can_cleanup())
                require_fixture_native_access(fixture_cleanup_gate)
                return job

            _reject(lambda: catalog.prepare('doc_missing', 'Основная', 'stl', 'Неизвестный документ.stl', 'mm'),
                    'document_not_open')
            _reject(lambda: catalog.prepare(mixed['document_id'], 'Основная', 'stl', 'Неактивная часть.stl', 'mm'),
                    'document_not_active')
            _reject(lambda: catalog.prepare(mixed['document_id'], 'Вариант', 'stl', 'Неактивная конфигурация.stl', 'mm'),
                    'configuration_not_active')
            try:
                active, _ = sw.ActivateDoc3(owned[0].GetTitle(), False, 1, 0)
                assert active is not None
                owned[0].ClearSelection2(True)
                _reject(lambda: catalog.prepare(mixed['document_id'], 'Основная', 'stl', 'Смешанные тела.stl', 'mm'),
                        'unsupported_export_body')
            finally:
                active, _ = sw.ActivateDoc3(model.GetTitle(), False, 1, 0)
                assert active is not None
            assert not list(output.iterdir())
            unchanged()

            # Invalidate a token with a direct edit of an exact owned feature.
            stale = catalog.prepare(**context, format='stl', filename='Устаревший экспорт.stl', units='mm')
            native_feature = next(feature for feature in session._iter_features()
                                  if feature.Name == 'Отрицательный контрольный блок')
            native_feature.Name = 'Отрицательный блок после проверки'
            assert native_feature.Name == 'Отрицательный блок после проверки'
            stale_job = submit('stale', {**context, 'expected_revision': stale['revision'],
                              'format': 'stl', 'filename': 'Устаревший экспорт.stl', 'units': 'mm'})
            assert stale_job['status'] == 'failed' and stale_job['error']['code'] == 'stale_revision', compact_job_failure(stale_job)
            assert not exports.native_calls and exports.saveas_attempt_count == 0 and not (output / 'Устаревший экспорт.stl').exists()
            source = owned_source_snapshot(model, module)
            setup, setup_ui = native_snapshot(), ui_snapshot(sw, module)
            semantic = exports.export_source_snapshot(model)
            unchanged()

            # Simulate a destination appearing AFTER prepare, without using any
            # actual user file. Both prepare and execute must refuse overwrite.
            filename = 'Существующий контрольный файл.stl'
            prepared = catalog.prepare(**context, format='stl', filename=filename, units='mm')
            sentinel = output / filename
            with sentinel.open('xb') as stream:
                stream.write(b'verifier-owned-do-not-overwrite')
            confirmed_paths[sentinel] = independent_file_facts(sentinel)
            _reject(lambda: catalog.prepare(**context, format='stl', filename=filename, units='mm'), 'export_file_exists')
            exists = submit('existing', {**context, 'expected_revision': prepared['revision'],
                            'format': 'stl', 'filename': filename, 'units': 'mm'})
            assert exists['status'] == 'failed' and exists['error']['code'] == 'export_file_exists', compact_job_failure(exists)
            assert independent_file_facts(sentinel) == confirmed_paths[sentinel]
            assert not exports.native_calls and exports.saveas_attempt_count == 0
            unchanged()

            formats = [('stl', 'mm', '.stl'), ('stl', 'm', '.stl'), ('stl', 'in', '.stl'),
                       ('step', '', '.step'), ('parasolid', '', '.x_t')]
            for index, (file_format, units, extension) in enumerate(formats):
                filename = f'Контрольный экспорт {index}{extension}'
                prepared = catalog.prepare(**context, format=file_format, filename=filename, units=units)
                assert prepared['source'] == {**semantic, 'export_profile': exports.export_profile(
                    ExportOptions(**prepared['options']).checked())}
                unchanged()
                request = f'export-{index}'
                arguments = {**context, 'expected_revision': prepared['revision'],
                             'format': file_format, 'filename': filename, 'units': units}
                print(json.dumps({'phase': 'before_native_export', 'format': file_format, 'units': units}), flush=True)
                job = submit(request, arguments)
                # Unknown is retained, never retried or converted to success.
                assert job['status'] == 'succeeded', compact_job_failure(job)
                checkpoint, result = job['mutation'], job['result']
                assert checkpoint['phase'] == 'committed'
                assert checkpoint['before_state']['_mutation_effect_scope'] == 'application'
                assert checkpoint['verification']['outcome'] == 'committed'
                assert result['verified'] is True
                assert result['execution_guard'] == {'original_state': 0, 'locked_state': 2, 'released_state': 0}
                manifest = result['value']
                assert manifest['operation_id'] == job['operation_id']
                assert manifest['source_revision'] == prepared['revision']
                assert manifest['revision_scope'] == prepared['revision_scope']
                assert manifest['document_id'] == context['document_id'] and manifest['configuration'] == 'Основная'
                assert manifest['format'] == file_format and manifest['coordinate_frame'] == 'part_model'
                assert manifest['source_unchanged'] is True and manifest['preferences_restored'] is True
                assert manifest['native_errors'] == 0 and manifest['native_warnings'] == 0
                assert manifest['publication'] == 'atomic_no_overwrite_link'
                assert manifest['geometry_roundtrip_verified'] is False
                path = output / filename
                assert Path(manifest['path']).resolve() == path.resolve()
                facts = independent_file_facts(path)
                assert facts['bytes'] == manifest['bytes'] and facts['sha256'] == manifest['sha256']
                confirmed_paths[path] = facts
                format_facts = _format_facts(path, manifest, source, units)
                unchanged()
                calls, saveas_attempts, dispatches = len(exports.native_calls), exports.saveas_attempt_count, runner.worker.dispatch_count
                duplicate = submit(request, arguments)
                assert duplicate['operation_id'] == job['operation_id'] and duplicate['result'] == result
                assert (len(exports.native_calls), exports.saveas_attempt_count, runner.worker.dispatch_count) == (calls, saveas_attempts, dispatches)
                zero_wait = asyncio.run(runner.wait(job['operation_id'], timeout_s=0))
                assert zero_wait['status'] == 'succeeded' and zero_wait['result'] == result
                assert not store.mutation_blockers('different-epoch', 'different-document')
                assert set(output.iterdir()) == set(confirmed_paths), 'Unexpected staging/sidecars retained for investigation.'
                committed_arguments.append((request, arguments, job))
                results.append({'operation_id': job['operation_id'], 'format': file_format,
                    'requested_units': units, 'path': str(path), 'bytes': facts['bytes'], 'sha256': facts['sha256'],
                    'durable_application_checkpoint_and_ui_guard': True, 'same_request_does_not_replay': True,
                    'revision_scope': prepared['revision_scope'], 'analytical_geometry_scope': PLANAR_BREP_SCOPE,
                    **format_facts})
                print(json.dumps({'phase': 'native_export_confirmed', **results[-1]}, ensure_ascii=True), flush=True)
            assert len(exports.native_calls) == 5 and exports.saveas_attempt_count == 5
            unchanged()

            # Real SQLite reopen: committed result/idempotency survives process-
            # lifetime objects. No CAD callback is permitted on historical replay.
            closing_store, store = store, None
            close_resources_with_gate([('historical_store', closing_store)], fixture_cleanup_gate,
                                      resource_cleanup_errors)
            store = JobStore(state / 'jobs.sqlite')
            historical_runner = InlineJobRunner(store)
            for request, arguments, previous in committed_arguments:
                def prohibited(*args):
                    raise AssertionError('A committed operation was replayed after journal reopen.')
                historical = guarded_inline_submit(fixture_cleanup_gate, historical_runner, store,
                    request, 'internal.export_part', arguments, prohibited,
                    context={key: arguments[key] for key in ('document_id', 'configuration', 'expected_revision')},
                    mutates=True, pass_operation_id=True, verify=lambda result: result.get('verified') is True)
                record_export_failure_diagnostic(report, job=historical,
                    cleanup_allowed=fixture_cleanup_gate.can_cleanup())
                require_fixture_native_access(fixture_cleanup_gate)
                assert historical['operation_id'] == previous['operation_id']
                assert historical['result'] == previous['result'] and historical['mutation']['phase'] == 'committed'
            assert historical_runner.worker.dispatch_count == 0
            assert not store.mutation_blockers('another-epoch', 'another-document')
            # No catalog write is attempted after replacing its journal owner.
            def reopened_baselines():
                assert native_snapshot() == setup
                observed_ui = capture_ui_difference(lambda: ui_snapshot(sw, module), setup_ui, report,
                                                    'journal_reopen_ui_snapshot_difference')
                assert observed_ui == setup_ui
                assert application_preferences(sw) == before_preferences
                assert exports.export_source_snapshot(model) == semantic
            independent_baseline_check(reopened_baselines, fixture_cleanup_gate,
                native_activity=bool(exports.native_calls or exports.saveas_attempt_count))
            report.update(native_internal_exports=results, actual_native_export_count=5,
                native_export_adapter_call_count=len(exports.native_calls),
                saveas_attempt_count=exports.saveas_attempt_count,
                independently_confirmed_export_count=len(results),
                internal_native_export_acceptance=True,
                installed_analytical_geometry_scope=PLANAR_BREP_SCOPE,
                stale_revision_rejected=True, wrong_document_and_inactive_targets_rejected=True,
                mixed_solid_surface_source_rejected=True,
                existing_output_unchanged=True, destination_race_before_execution_rejected=True,
                native_source_metadata_extrema_feature_facts_exactly_unchanged=True,
                independent_mass_facts_within_declared_tolerance=True,
                full_supported_source_snapshot_unchanged=True, global_preferences_restored=True,
                exact_supported_source_boundary_check='independent_exact_analytical_snapshot_comparison',
                independent_complete_brep_snapshot_comparison=True,
                ui_guard_and_selection_restored=True, journal_reopen_retains_committed_results=True,
                committed_request_after_reopen_does_not_dispatch=True,
                timeout_zero_reads_already_terminal_job=True, private_outputs_retained=True)
        assert native_snapshot() == original, 'Original user document baseline was not restored.'
        assert application_preferences(original_sw) == original_preferences
        observed_original_ui = capture_ui_difference(lambda: ui_snapshot(original_sw, original_module),
            original_ui, report, 'original_ui_snapshot_difference')
        assert observed_original_ui == original_ui
        assert user_file_metadata(original) == original_files
        for path, facts in confirmed_paths.items():
            assert independent_file_facts(path) == facts
        report.update(original_user_document_baseline_restored=True,
                      original_user_file_metadata_unchanged=True,
                      original_user_file_byte_hashes_checked=False,
                      retained_confirmed_output_count=len(confirmed_paths),
                      owned_fixture_cleanup_allowed=fixture_cleanup_gate.can_cleanup(),
                      owned_fixture_cleanup_retained=False, owned_fixture_cleanup_retained_count=0)
        return report
    except BaseException as exc:
        primary_failure = exc
        raise
    finally:
        try:
            close_resources()
        except BaseException as cleanup_exc:
            if primary_failure is None:
                # Still record independently observed cleanup state before
                # propagating a cleanup failure from an otherwise finished run.
                primary_failure = cleanup_exc
                raise
            if failure_report is not None:
                failure_report['resource_cleanup_error'] = {
                    'error_type': type(cleanup_exc).__name__[:80]}
        finally:
            if primary_failure is not None and failure_report is not None:
                calls = len(exports.native_calls) if exports is not None else 0
                saveas_attempts = exports.saveas_attempt_count if exports is not None else 0
                failure_report.update({key: report[key] for key in (
                    'package_version', 'git_sha', 'source_dirty',
                    'installed_source_digest', 'installed_build_matches_package',
                    'job_failure_diagnostics', 'operation_exception_chain',
                    'failure_diagnostic_formatting_failed',
                    'fixture_setup_stl_deviation',
                    'export_preferences_baseline_captured_after_fixture_setup',
                    'fixture_setup_other_preferences_exactly_unchanged',
                    'approximate_mass_facts_check', 'computed_mass_facts_tolerances',
                    'computed_mass_facts_check_reason', 'independent_nonmass_source_facts_exact',
                    'independent_computed_mass_raw_readings',
                    'computed_mass_facts_used_for_geometry_revision',
                    'setup_ui_snapshot_difference', 'journal_reopen_ui_snapshot_difference',
                    'original_ui_snapshot_difference') if key in report})
                failure_report['resource_cleanup_errors'] = list(resource_cleanup_errors)
                failure_report.update(native_export_adapter_call_count=calls,
                    saveas_attempt_count=saveas_attempts,
                    # An attempted SaveAs3 can fail or return an invalid result;
                    # observation of entry does not prove a successful export.
                    actual_native_export_count=0 if saveas_attempts == 0 else None,
                    actual_native_export_count_basis='no_SaveAs3_attempt' if saveas_attempts == 0
                                                     else 'SaveAs3_attempt_observed_success_not_inferred',
                    independently_confirmed_export_count=len(results),
                    retained_confirmed_output_count=len(confirmed_paths),
                    original_user_file_byte_hashes_checked=False)
                cleanup_allowed = fixture_cleanup_gate.can_cleanup()
                failure_report.update(owned_fixture_cleanup_allowed=cleanup_allowed,
                    owned_fixture_cleanup_retained=not cleanup_allowed,
                    owned_fixture_cleanup_retained_count=0 if cleanup_allowed else owned_fixture_count)
                if cleanup_allowed:
                    failure_report.update(cleanup_baseline_flags({
                        'original_user_document_baseline_restored': (native_snapshot, original),
                        'original_preferences_restored': (
                            lambda: application_preferences(original_sw), original_preferences),
                        'original_ui_blocking_and_selection_restored': (
                            lambda: capture_ui_difference(lambda: ui_snapshot(original_sw, original_module),
                                original_ui, failure_report, 'original_ui_snapshot_difference'), original_ui),
                        'original_user_file_metadata_unchanged': (
                            lambda: user_file_metadata(original), original_files),
                    }))
                else:
                    # Owned open fixtures prove the COMPLETE document baseline
                    # is not restored, even if all original user docs are intact.
                    # Other flags are unmeasured; no native getter follows a hold.
                    failure_report.update(original_user_document_baseline_restored=(
                            False if owned_fixture_count else None),
                        original_preferences_restored=None,
                        original_ui_blocking_and_selection_restored=None,
                        original_user_file_metadata_unchanged=None,
                        cleanup_baseline_read_errors={}, cleanup_baseline_reads_skipped_due_to_hold=True)
                    failure_report['original_ui_snapshot_difference'] = ui_snapshot_unmeasured(original_ui)
        # Every produced path/journal remains private for root's review. Nothing
        # is deleted, especially after an unknown or partially published result.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    state, output, report = (path.absolute() for path in (args.state_dir, args.output_dir, args.report))
    assert not state.exists() and not output.exists() and not report.exists(), 'All verifier paths must be fresh.'
    assert state != output and state not in output.parents and output not in state.parents
    assert report != state and report != output and state not in report.parents and output not in report.parents
    state.mkdir(parents=True)
    output.mkdir(parents=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()
    try:
        failure_facts = {}
        try:
            result = check(state.resolve(), output.resolve(), failure_report=failure_facts)
        except BaseException as exc:
            try:
                exception_chain = bounded_exception_chain(exc)
            except BaseException:
                exception_chain = {'items': [], 'formatting_failed': True}
            failure = {**failure_facts, 'accepted': False, 'internal_native_export_acceptance': False,
                       'public_mcp_export_acceptance': False,
                       'error_type': exception_chain['items'][0]['error_type'] if exception_chain['items'] else None,
                       'error_code': exception_chain['items'][0]['error_code'] if exception_chain['items'] else None,
                       'verifier_exception_chain': exception_chain,
                       'message': 'Verifier failed; inspect bounded diagnostics and the retained private journal.',
                       'private_outputs_and_journal_retained': True,
                       'automatic_replay_or_output_cleanup_attempted': False}
            try:
                with report.open('x', encoding='utf8') as stream:
                    stream.write(json.dumps(failure, ensure_ascii=True, indent=2) + '\n')
            except BaseException as report_exc:
                # Preserve the original native/verifier exception even if the
                # private report itself cannot be written.
                try:
                    print(json.dumps({'failure_report_write_error': type(report_exc).__name__,
                                      'message': 'Private failure report could not be written.'}), file=sys.stderr)
                except BaseException:
                    pass
            raise
        with report.open('x', encoding='utf8') as stream:
            stream.write(json.dumps(result, ensure_ascii=True, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=True, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
