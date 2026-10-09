"""Installed internal dimension-domain acceptance on an exact owned fixture.

This does not assert public MCP dimension availability. No user document is
saved/modified. Source mutation callbacks and the durable runner execute on the
same initialized apartment; independent extrema/volume verify the known box.
"""

import argparse
from concurrent.futures import Future
import json
import math
from pathlib import Path

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures
from verify_export_operations import exact_solid, native_extrema_m, ui_snapshot


class Adapter(SolidWorksDocuments):
    def __init__(self):
        super().__init__()
        self.inject_after_write = False

    def set_dimension_value(self, record, value_si, configuration):
        result = super().set_dimension_value(record, value_si, configuration)
        if self.inject_after_write:
            self.inject_after_write = False
            raise RuntimeError('Verifier injection after actual native setter, not a native COM failure.')
        return result


class Worker:
    def submit(self, function):
        future = Future()
        try:
            future.set_result(function())
        except BaseException as exc:
            future.set_exception(exc)
        return future


def check(state):
    assert 'site-packages' in solidworks_mcp.__file__
    original = native_snapshot()
    report = {'package_version': solidworks_mcp.__version__, 'public_mcp_dimension_acceptance': False}
    with fixtures() as (_, owned, _):
        adapter = Adapter()
        documents = DocumentCatalog(adapter)
        store = JobStore(state / 'jobs.sqlite')
        try:
            model = owned[1]
            sw, module = adapter._sw, binding.module()
            source_ui = ui_snapshot(sw, module)
            other_metadata = adapter.snapshot(owned[0])
            doc = next(row for row in documents.list()['documents'] if row['title'] == model.GetTitle())
            catalog = DimensionCatalog(documents, store, 'native_dimensions', mutation_guard=adapter.mutation_guard)
            page = catalog.list(doc['document_id'], 'Основная')
            assert page['total_count'] == 3
            target = next(row for row in page['items'] if row['owner']['feature_type'] == 'Extrusion')
            assert target['object_id'] and not target['write_blockers']
            assert target['reference_anchor']['strategy'] == 'display_dimension_v1'
            assert math.isclose(target['values']['Основная'], 7., abs_tol=1e-10)
            assert catalog.list(doc['document_id'], 'Основная')['revision'] == page['revision']
            runner = JobRunner(store, Worker())

            def submit(request, revision, value):
                args = {'document_id': doc['document_id'], 'configuration': 'Основная',
                        'object_id': target['object_id'], 'expected_revision': revision, 'value': value, 'unit': 'mm'}
                return runner.submit(request, 'dimension.set_value', args,
                    lambda operation_id: catalog.set_value(operation_id, **args),
                    context={key: args[key] for key in ('document_id', 'configuration', 'expected_revision')},
                    mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)

            def physical(depth):
                body = exact_solid(model, module)
                bounds = native_extrema_m(body)
                size = [1000 * (b - a) for a, b in zip(bounds['min'], bounds['max'])]
                assert all(math.isclose(a, b, abs_tol=1e-7) for a, b in zip(size, [5., 6., depth])), size
                volume = float(body.GetMassProperties(1.)[3]) * 1e9
                assert math.isclose(volume, 5 * 6 * depth, abs_tol=1e-5), volume
                assert ui_snapshot(sw, module) == source_ui
                assert adapter.snapshot(owned[0]) == other_metadata
                return {'dimensions_mm': size, 'volume_mm3': volume}

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
            fresh = catalog.list(doc['document_id'], 'Основная')
            before_geometry = catalog._state(doc['document_id'], 'Основная')[3]['geometry']
            adapter.inject_after_write = True
            restored = submit('injected', fresh['revision'], 11.)
            assert restored['status'] == 'failed' and restored['mutation']['phase'] == 'rolled_back', restored
            assert restored['mutation']['verification']['evidence']['execution_guard']['released_state'] == 0
            assert catalog._state(doc['document_id'], 'Основная')[3]['geometry'] == before_geometry
            physical(9.)
            assert store.mutation_blockers('native_dimensions', 'another_document') == []
            report.update(native_typed_configuration_setter=True, actual_native_status=changed['result']['value']['native_status'],
                explicit_dimension_reference_survives_rebuild=True, same_request_does_not_duplicate_write=True,
                stale_revision_rejected=True, verified_scoped_restoration_after_injected_error=True,
                actual_native_error_injected=False, other_owned_document_unchanged=True,
                ui_guard_released_and_durable=True, dimension_revision_scope=page['revision_scope'])
        finally:
            documents.close()
            store.close()
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
        result = check(args.state_dir)
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
        print(json.dumps(result, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
