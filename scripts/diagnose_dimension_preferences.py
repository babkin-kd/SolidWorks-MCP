"""Root-only owned native control: locate STL preference drift, not acceptance.

No MCP dispatch, export, preference setter or recovery of historical jobs.
Run only after the operator accepts a fresh native baseline. A failed probe
retains its exact owned fixtures without further native reads or restoration.
The 7 -> 9 -> 7 sequence is a planned experiment, never error-path rollback.
"""

import argparse
import json
import math
import os
from pathlib import Path
import uuid

from verifier_dimension_diagnostics import _snapshot


def changed_fields(before, after):
    return [key for key in sorted(before.keys() | after.keys())
            if key not in before or key not in after
            or type(before[key]) is not type(after[key]) or before[key] != after[key]]


def probe(driver, report, checkpoint):
    """Pure orchestration; the driver owns all native calls and its guard.

    Intermediate STL deviation is the measured variable in this control only.
    All other fields are exact, and the final full profile/geometry must match.
    Neither completion nor an observed change authorizes MCP acceptance.
    """
    report.update(accepted=False, public_mcp_dimension_acceptance=False,
                  diagnostic_completed=False, cause_inferred=False,
                  native_path='direct_SetSystemValue3_then_ForceRebuild3', steps=[])
    driver.assert_context()
    before = _snapshot(driver.preferences())
    assert type(before.get('stl_deviation')) is float and before['stl_deviation'] > 0
    geometry = driver.geometry()
    assert driver.depth() == .007, 'Control must begin at exactly 7 mm.'
    report['initial_preferences'] = before
    report['initial_geometry'] = geometry

    def observe(phase):
        # Observe immediately: no document/geometry getter between the action
        # being investigated and the preference reader. Additional reads get
        # their own phases rather than being attributed to setter/rebuild.
        current = _snapshot(driver.preferences())
        assert type(current.get('stl_deviation')) is float and current['stl_deviation'] > 0
        fields = changed_fields(before, current)
        report['steps'].append({'phase': phase, 'preferences': current,
                                'changed_fields_from_initial': fields})
        checkpoint(report)
        assert set(fields) <= {'stl_deviation'}, 'Control changed another application preference.'

    observe('repeated_read_before_write')
    guard = driver.guard()
    with guard:
        observe('guard_acquired_before_write')
        for value in (.009, .007):
            # Persist intention before native dispatch; never redispatch after
            # a missing acknowledgement, exception or diagnostic I/O failure.
            report['pending_native_action'] = {'operation': 'SetSystemValue3', 'value_si': value}
            checkpoint(report)
            driver.assert_context()
            status = driver.set_depth(value)
            assert type(status) is int and status == 0, 'Native setter did not return status 0.'
            report['pending_native_action'] = None
            observe(f'after_setter_{value}')
            assert driver.depth() == value, 'Named configuration value was not confirmed.'
            observe(f'after_value_read_{value}')
            report['pending_native_action'] = {'operation': 'ForceRebuild3', 'value_si': value}
            checkpoint(report)
            driver.assert_context()
            observe(f'after_context_check_before_rebuild_{value}')
            assert driver.rebuild() is True, 'Native rebuild was not confirmed.'
            report['pending_native_action'] = None
            observe(f'after_rebuild_{value}')
            driver.assert_geometry_depth(value)
            observe(f'after_physical_read_{value}')
    report['execution_guard'] = guard.evidence
    assert guard.evidence == {'original_state': 0, 'locked_state': 2, 'released_state': 0}
    observe('guard_released')
    assert driver.depth() == .007
    assert driver.geometry() == geometry, 'Complete analytical control geometry was not restored.'
    final = _snapshot(driver.preferences())
    report['final_preferences'] = final
    assert not changed_fields(before, final), 'Final full preference profile was not restored exactly.'
    driver.assert_context()
    report.update(diagnostic_completed=True, final_control_geometry_and_preferences_restored=True)
    checkpoint(report)


class PrivateTrace:
    """Exclusive private append-only observations, flushed before native work."""
    def __init__(self, path):
        self.stream = path.open('x', encoding='utf8')

    def __call__(self, report):
        self.stream.write(json.dumps(report, ensure_ascii=True, allow_nan=False) + '\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


def check(report, checkpoint):
    # Native modules are loaded only by explicit execution, never pure tests.
    import pythoncom
    import win32com.client
    from solidworks_mcp import binding
    from solidworks_mcp.cad_documents import SolidWorksDocuments
    from verify_dimension_mcp import _provenance
    from verify_document_reads import native_snapshot
    from verify_export_operations import application_preferences, exact_solid, native_extrema_m, ui_snapshot, user_file_metadata
    from verify_geometry_reads import fixtures

    report.update(_provenance(), request_id=uuid.uuid4().hex,
                  original_document_baseline_restored=False, fixture_retention_required=True)
    allowed = [False]
    original = native_snapshot()
    original_files = user_file_metadata(original)
    adapter = SolidWorksDocuments()
    sw, module = adapter._sw, adapter._module
    original_ui = ui_snapshot(sw, module)
    original_preferences = _snapshot(application_preferences(sw))
    report['original_preferences'] = original_preferences
    with fixtures(cleanup_gate=lambda: allowed[0]) as (session, owned, _):
        report['owned_fixture_document_count'] = len(owned)
        model = owned[1]
        assert not model.GetPathName() and tuple(model.GetConfigurationNames()) == ('Основная',)
        configuration = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
        assert configuration.Name == 'Основная'
        model_identity, config_identity = adapter.identity(model), adapter.identity(configuration)
        setup = native_snapshot()
        others = [row for row in setup[3] if row[0] != model_identity]
        session._model = model
        features = [feature for feature in session._iter_features() if feature.GetTypeName2() == 'Extrusion']
        assert len(features) == 1
        feature = features[0]
        feature_identity = adapter.identity(feature)
        display = binding.wrap(feature.GetFirstDisplayDimension(), module.IDisplayDimension)
        assert display is not None and feature.GetNextDisplayDimension(display) is None
        dimension = binding.wrap(display.GetDimension2(0), module.IDimension)
        assert dimension is not None and int(dimension.GetType()) == 0
        dimension_identity = adapter.identity(dimension)
        owner = binding.wrap(dimension.GetFeatureOwner(), module.IFeature)
        assert owner is not None and adapter.identity(owner) == feature_identity
        names = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, ['Основная'])

        class Driver:
            def assert_context(self):
                current = native_snapshot()
                assert current[2] == model_identity
                assert [row for row in current[3] if row[0] != model_identity] == others
                assert adapter.identity(model) == model_identity and not model.GetPathName()
                active = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
                assert active.Name == 'Основная' and adapter.identity(active) == config_identity
                assert adapter.identity(dimension) == dimension_identity
                assert adapter.identity(feature) == feature_identity
                owner = binding.wrap(dimension.GetFeatureOwner(), module.IFeature)
                assert owner is not None and adapter.identity(owner) == feature_identity

            def preferences(self):
                return application_preferences(sw)

            def geometry(self):
                return adapter.dimension_geometry_snapshot(model)

            def depth(self):
                values = dimension.GetSystemValue3(3, names)
                assert isinstance(values, (tuple, list)) and len(values) == 1
                return float(values[0])

            def guard(self):
                return adapter.mutation_guard(model)

            def set_depth(self, value):
                return dimension.SetSystemValue3(value, 3, names)

            def rebuild(self):
                return model.ForceRebuild3(False) is True and not adapter.pending_rebuild(model)

            def assert_geometry_depth(self, value):
                body = exact_solid(model, module)
                extrema = native_extrema_m(body)
                size = [hi-lo for lo, hi in zip(extrema['min'], extrema['max'])]
                assert all(math.isclose(x, y, abs_tol=1e-10) for x, y in zip(size, (.005, .006, value)))
                assert all(math.isclose(x, 0., abs_tol=1e-10) for x in extrema['min'])
                assert math.isclose(float(body.GetMassProperties(1.)[3]), .005*.006*value, abs_tol=1e-14)

        probe(Driver(), report, checkpoint)
        allowed[0] = True
        report['fixture_retention_required'] = False
    assert native_snapshot() == original and ui_snapshot(sw, module) == original_ui
    assert user_file_metadata(original) == original_files
    final = _snapshot(application_preferences(sw))
    report['original_preferences_after_cleanup'] = final
    assert not changed_fields(original_preferences, final), 'Original application preferences differ after fixture cleanup.'
    report['original_document_baseline_restored'] = True
    checkpoint(report)


def save_summary(path, report, primary_error):
    try:
        with path.open('x', encoding='utf8') as stream:
            json.dump(report, stream, allow_nan=False, ensure_ascii=True, indent=2)
    except BaseException as recording_error:
        if primary_error is None:
            raise
        primary_error.add_note('Private summary recording failed: ' + type(recording_error).__name__[:80])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    private_root = Path(__file__).resolve().parent.parent / 'work'
    state = args.state_dir.resolve()
    assert state.is_relative_to(private_root.resolve()) and not state.exists()
    state.mkdir(parents=True)
    report = {'accepted': False, 'public_mcp_dimension_acceptance': False,
              'diagnostic_completed': False, 'automatic_replay_attempted': False}
    trace = PrivateTrace(state / 'trace.jsonl')
    import pythoncom
    pythoncom.CoInitialize()
    primary_error = None
    try:
        try:
            check(report, trace)
        except BaseException as error:
            primary_error = error
            report['diagnostic_completed'] = False
            report['error_type'] = type(error).__name__[:80]
            try:
                trace(report)
            except BaseException as recording_error:
                error.add_note('Private trace recording failed: ' + type(recording_error).__name__[:80])
            raise
        finally:
            save_summary(state / 'report.json', report, primary_error)
    finally:
        pythoncom.CoUninitialize()
        trace.close()


if __name__ == '__main__':
    main()
