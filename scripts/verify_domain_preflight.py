"""Installed-wheel native preflight of internal dimensions/export candidates.

Only owned disposable fixtures are used. No dimension setter or export is
called. A brief native UI lock is paired with UnLock in finally and checked.
Report contains fixture diagnostics only, never user CAD titles or paths.
"""

import argparse
import json
from pathlib import Path
import time

import pythoncom
import win32com.client
import solidworks_mcp
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.cad_exports_v2 import CadExportsAdapter
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.ui_guard import ModelUiGuard
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures


class DimensionsAdapter(SolidWorksDocuments):
    pass


def check(focus='all'):
    assert 'site-packages' in solidworks_mcp.__file__
    before = native_snapshot()
    report = {'package_version': solidworks_mcp.__version__, 'checks': {}}
    with fixtures() as (_, owned, _):
        adapter = DimensionsAdapter()
        documents = DocumentCatalog(adapter)
        try:
            model = owned[1]  # One solid and one configuration; already active.
            metadata = adapter.snapshot(model)

            def attempt(name, fn):
                started = time.monotonic()
                try:
                    result = fn()
                    report['checks'][name] = {'ok': True, 'value': result}
                except Exception as exc:
                    report['checks'][name] = {'ok': False, 'error': type(exc).__name__,
                        'code': getattr(exc, 'code', None), 'message': str(exc)}
                report['checks'][name]['seconds'] = round(time.monotonic() - started, 3)
                print(json.dumps({'phase': name, **report['checks'][name]}, ensure_ascii=True), flush=True)

            def ui_lock():
                guard = ModelUiGuard(model)
                with guard:
                    assert int(model.GetBlockingState()) == 2
                assert guard.evidence == {'original_state': 0, 'locked_state': 2, 'released_state': 0}
                return guard.evidence

            def dimension_rows():
                native = adapter.dimensions(model, adapter.features(model))
                rows = []
                anchors = []
                for record in native:
                    value = adapter.dimension_summary(record, ['Основная'])
                    persistent = adapter.persistent_id(model, record.dimension)
                    anchor = adapter.dimension_persistent_id(model, record)
                    roundtrip = False
                    if anchor:
                        restored = adapter.resolve_dimension_id(model, anchor)
                        assert adapter.identity(restored) == adapter.identity(record.dimension), 'Dimension PID resolves a different native object.'
                        assert adapter.dimension_reference_is_current(model, record, anchor)
                        roundtrip = True
                    displays = []
                    for display in record.displays:
                        display_pid = adapter.persistent_id(model, display)
                        display_identity_matches = False
                        if display_pid:
                            raw, status = adapter._extension(model).GetObjectByPersistReference3(adapter._persistent_variant(display_pid))
                            display_identity_matches = status == 0 and raw is not None and adapter.identity(raw) == adapter.identity(display)
                        displays.append({'pid_bytes': len(display_pid), 'native_identity_matches': display_identity_matches})
                    rows.append({'parameter_type': value['parameter_type'], 'unit': value['unit'],
                        'value': value['values']['Основная'], 'owner_type': value['owner']['feature_type'] if value['owner'] else None,
                        'write_blockers': value['write_blockers'], 'native_pid_roundtrip': roundtrip,
                        'dimension_pid_bytes': len(persistent), 'reference_strategy': anchor['strategy'] if anchor else None,
                        'display_reference_diagnostics': displays})
                    if anchor:
                        anchors.append((record, anchor))
                assert rows, 'Fixture dimensions were not enumerated.'
                time.sleep(1.2)
                for record, anchor in anchors:
                    assert adapter.identity(adapter.resolve_dimension_id(model, anchor)) == adapter.identity(record.dimension), 'Dimension identity changed across delayed anchor resolution.'
                return {'dimensions': rows, 'writable_dimension_native_reference_confirmed':
                    any(row['native_pid_roundtrip'] and not row['write_blockers'] for row in rows),
                    'dimension_identity_stable_after_delay': bool(anchors)}

            def body_streams():
                first = adapter.dimension_geometry_snapshot(model)
                second = adapter.dimension_geometry_snapshot(model)
                assert first == second, 'Temporary body serialization is not repeatable.'
                assert first['bodies']
                return first

            exports = CadExportsAdapter(adapter)
            def export_snapshot():
                first = exports.export_source_snapshot(model)
                second = exports.export_source_snapshot(model)
                changed = [key for key in first if first[key] != second.get(key)]
                assert first == second, 'Export snapshot is not repeatable; changed fields: ' + ', '.join(changed)
                return {'body_count': len(first['bodies']), 'analytical_boundary_repeatable': True,
                        'geometry_scope': first['bodies'][0]['boundary_snapshot']['scope']}

            def named_values_diagnostic():
                values = []
                native = adapter.dimensions(model, adapter.features(model))
                for record in native:
                    row = {'owner_type': str(record.owner.GetTypeName2()) if record.owner else None,
                           'current_system_value': float(record.dimension.SystemValue)}
                    inputs = [('current', 1, None), ('named_list', 3, ['Основная']),
                              ('named_string', 3, 'Основная'), ('named_bstr_array', 3,
                               win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, ['Основная']))]
                    for label, option, names in inputs:
                        result = record.dimension.GetSystemValue3(option, names)
                        row[label] = {'python_type': type(result).__name__, 'value': result}
                    row['named_value2'] = float(record.dimension.GetSystemValue2('Основная'))
                    values.append(row)
                return {'dimensions': values, 'extension_has_design_table': bool(adapter._extension(model).HasDesignTable()),
                        'get_design_table_returns_object': model.GetDesignTable() is not None}

            if focus == 'dimensions':
                attempt('named_values_diagnostic', named_values_diagnostic)
            else:
                attempt('ui_lock', ui_lock)
            attempt('dimension_rows_and_pid', dimension_rows)
            attempt('dimension_context', lambda: adapter.dimension_context(model))
            if focus == 'all':
                attempt('temporary_dimension_body_streams', body_streams)
                attempt('export_source_snapshot', export_snapshot)
            assert adapter.snapshot(model) == metadata, 'Read preflight changed owned model metadata.'
        finally:
            documents.close()  # Release all adapter references on this apartment.
    assert native_snapshot() == before
    report['original_document_baseline_restored'] = True
    report['all_checks_passed'] = all(item['ok'] for item in report['checks'].values())
    report['scope'] = 'internal native reads and paired UI lock; no dimension mutation or export acceptance'
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--focus', choices=['all', 'dimensions'], default='all')
    args = parser.parse_args()
    assert not args.report.exists(), 'Use a fresh report path.'
    pythoncom.CoInitialize()
    try:
        result = check(args.focus)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=True) + '\n', encoding='utf8')
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if not result['all_checks_passed']:
            raise SystemExit(1)
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
