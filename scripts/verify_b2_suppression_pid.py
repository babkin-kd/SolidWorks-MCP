"""One-owner dev94 compatibility experiment; never B2/tool acceptance.

Passive preflight precedes COM imports/initialization. A failed/unknown native
step retains this STA, exact receipts and fixtures without retry or Undo.
Only the owning root may opt in and execute this script, sequentially.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import traceback
import uuid


VERSION = '2.0.0.dev94'
GIT_SHA = 'dc52ffcef06e443bea1781062e648c1773e5600f'
WHEEL_SHA = '84c19da6866c80ff3898175622d7843413a41b1894b33ec315abe002c7013bf9'
AUDIT_SHA = '4a050518522a883f80605ad1505c8b09b1118c442fb83fa96453f11ac3005790'
HELPERS = ('verify_b2_suppression_pid.py', 'verifier_b2_suppression_probe.py',
    'verifier_b2_probe_observer.py', 'verify_wheel_artifact.py',
    'verify_installed_metadata.py', 'verify_native_document_open.py',
    'verify_export_operations.py', 'verifier_dimension_diagnostics.py')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_fresh_state(path, root):
    path, private = Path(path).resolve(), (Path(root).resolve() / 'work')
    require(path.is_relative_to(private) and path != private and not path.exists(),
            'Use a fresh child state directory under private work/.')
    return path


def passive_preflight(args, *, root=None, validate=None, installed=None):
    """No COM initialization, CAD connection, MCP process, or file writes."""
    require(args.run_solidworks is True, 'Native probe requires --run-solidworks.')
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    state = private_fresh_state(args.state_dir, root)
    wheel_path, audit_path = Path(args.wheel).resolve(), Path(args.b1_audit).resolve()
    require(digest(wheel_path) == WHEEL_SHA, 'Only the B1 accepted exact dev94 wheel is admissible.')
    require(digest(audit_path) == AUDIT_SHA, 'Exact root-accepted terminal B1 audit hash required.')
    audit = json.loads(audit_path.read_text(encoding='utf8'))
    require(audit['b1_accepted'] is True and audit['full_baseline_verified'] is True,
            'B1 must already be accepted with its full baseline.')
    if validate is None:
        from verify_wheel_artifact import validate_wheel
        validate = validate_wheel
    wheel = validate(wheel_path, expected_version=VERSION, expected_git_sha=GIT_SHA)
    require(wheel == audit['wheel'] and wheel['wheel_sha256'] == WHEEL_SHA,
            'Accepted B1 audit and exact wheel evidence differ.')
    reports, report_hashes, helper_hashes = {}, {}, {}
    for label in ('positive', 'faults', 'public'):
        path = (root / 'work' / f'native-rectangle-dev94-{label}-1' / 'report.json').resolve()
        require(path.is_relative_to(root / 'work'), 'B1 evidence must stay in private work/.')
        report_hashes[label] = digest(path)
        require(report_hashes[label] == audit['report_sha256'][label], 'B1 report hash changed: ' + label)
        row = json.loads(path.read_text(encoding='utf8'))
        require(row['phase'] == 'terminal' and row['native_calls_live'] is False
                and row['baseline_restored'] is True and row['own_cleanup_verified'] is True
                and row['independent_native_readback_verified'] is True and row['wheel'] == wheel,
                'B1 native report is not exact normally completed evidence: ' + label)
        for name, expected in row['verifier_hashes'].items():
            require(Path(name).name == name, 'Unsafe helper basename.')
            actual = digest(root / 'scripts' / name)
            require(actual == expected, 'B1 helper changed since acceptance: ' + name)
            helper_hashes[name] = actual
        reports[label] = str(path)
    for name in HELPERS:
        helper_hashes[name] = digest(root / 'scripts' / name)
    if installed is None:
        from verify_installed_metadata import installed_identity
        installed = installed_identity
    entry = installed(wheel)  # Origin/version/build/source digest; no MCP check().
    import solidworks_mcp
    return dict(state_dir=str(state), wheel=wheel, package_origin_verified=True,
        installed_package_origin=str(Path(solidworks_mcp.__file__).resolve().parent),
        installed_console=str(entry), b1_audit=str(audit_path), b1_audit_sha256=AUDIT_SHA,
        b1_report_paths=reports, b1_report_sha256=report_hashes,
        verifier_hashes=helper_hashes, passive_preflight_verified=True,
        metadata_mcp_launched=False)


def require_free_session(sw):
    require(not sw.GetDocuments() and sw.ActiveDoc is None,
            'An empty session is required; user documents prohibit fixture creation.')
    require(type(sw.CommandInProgress) is bool and sw.CommandInProgress is False
            and sw.UserControl is True, 'Free user-controlled session required; no borrowed command flag.')


def normal_release(guard, sw):
    facts = guard.evidence
    require(facts['original_command_in_progress'] is False and facts['acquired'] is True
            and facts['released'] is True and facts['selection_preserved'] is True
            and all(row == {'original_state': 0, 'locked_state': 2, 'released_state': 0}
                    for row in facts['model_guards'])
            and type(sw.CommandInProgress) is bool and sw.CommandInProgress is False,
            'Own guard normal release/current native False must be independently confirmed.')
    return facts


def exact_action_binding(observer):
    """PID/canonical primary; GetID is only a checked traversal hint."""
    owner, adapter = observer.owner, observer.adapter
    entry, observed = observer.documents.resolve(owner['document_id'], owner['configuration'])
    require(entry.identity == observer.document_identity
            and adapter.identity(entry.model) == observer.document_identity
            and observed['active_configuration'] == owner['configuration']
            and observed['configurations'] == [owner['configuration']]
            and adapter.configuration_identity(observer.model, owner['configuration']) == observer.configuration_identity
            and adapter.identity(adapter.active_document()) == observer.document_identity,
            'Explicit active owned document/configuration changed before native action.')
    observer._census()
    current = adapter.resolve_persistent_id(observer.model, observer.pid, 'feature')
    require(current is not None and adapter.identity(current) == observer.feature_identity
            and adapter.identity(observer.feature) == observer.feature_identity
            and adapter.persistent_id(observer.model, current) == observer.pid,
            'Normal exact PID/canonical member required before native action.')
    return current


def perform_probe(observer, report, persist, *, validate=None):
    """Four one-shot normal calls; any failure prevents every later mutation."""
    if validate is None:
        from verifier_b2_suppression_probe import validate_probe
        validate = validate_probe
    owner, adapter = observer.owner, observer.adapter
    receipt = dict(scope='owned_blind_base_suppression_pid_probe_v1', phase='running',
        native_calls_live=False, owner=owner, observations=[], actions=[], affected_native_ids=[])
    report['probe_receipt'] = receipt
    def observe(phase):
        report.update(phase='observe_' + phase, native_calls_live=True); persist()
        row = observer.observe_phase(phase)['observation']
        receipt['observations'].append(row)
        report['native_calls_live'] = False; persist()
    observe('before')
    for label, method, arguments in (
        ('suppress', 'SetSuppression2', [0, 1, None]),
        ('suppress_rebuild', 'ForceRebuild3', [False]),
        ('unsuppress', 'SetSuppression2', [2, 1, None]),
        ('unsuppress_rebuild', 'ForceRebuild3', [False])):
        report.update(phase=label, native_calls_live=True); persist()
        guard = adapter.mutation_guard(observer.model)
        action = dict(phase=label, method=method, arguments=arguments,
            **{key: owner[key] for key in ('document_id', 'configuration',
                'document_identity_token', 'configuration_identity_token', 'feature_identity_token')},
            native_call_attempted=False, native_call_returned=False, pending=False, return_value=None)
        receipt['actions'].append(action); persist()
        with guard:
            current = exact_action_binding(observer)
            action.update(native_call_attempted=True, pending=True); persist()
            receiver = current if method == 'SetSuppression2' else observer.model
            result = getattr(receiver, method)(*arguments)
            action.update(native_call_returned=True, pending=False, return_value=result); persist()
            require(result is True, 'Native setter/rebuild did not normally return True: ' + label)
        report.setdefault('action_guards', []).append(normal_release(guard, adapter._sw))
        report['native_calls_live'] = False; persist()
        if label == 'suppress_rebuild':
            observe('suppressed')
        elif label == 'unsuppress_rebuild':
            observe('restored')
    before, suppressed, _ = receipt['observations']
    receipt['affected_native_ids'] = [old['native_id'] for old, new in
        zip(before['feature_summaries'], suppressed['feature_summaries'])
        if old['suppressed'] != new['suppressed']]
    receipt.update(phase='terminal', native_calls_live=False)
    report['receipt_gate'] = validate(receipt); persist()
    require(report['receipt_gate']['receipt_validated'] is True,
            'Strict receipt validation required before root cleanup.')
    report['native_normal_completion_verified'] = True; persist()
    return receipt


def run_native(state, report, persist):
    """Called only after passive preflight by the single owning CLI process."""
    import pythoncom
    from solidworks_mcp import binding
    from solidworks_mcp.cad_documents import SolidWorksDocuments
    from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
    from solidworks_mcp.documents import DocumentCatalog
    from solidworks_mcp.jobs import JobStore
    from solidworks_mcp.native_document_open import NativeDocumentOpenCatalog
    from solidworks_mcp.part_creation import BaseRectangle, validated_plane_transform
    from verify_export_operations import activate_owned, application_preferences
    from verify_native_document_open import retire_owned, snapshot
    from verifier_dimension_diagnostics import assert_non_stl_preferences
    from verifier_b2_probe_observer import CanonicalOrdinalPool, OwnedSuppressionProbeObserver
    owned, document_receipts, base_receipts = [], [], []
    pool = CanonicalOrdinalPool()
    store = None
    pythoncom.CoInitialize()
    try:
        adapter = SolidWorksDocuments(); sw, module = adapter._sw, adapter._module
        require_free_session(sw)
        original, app, prefs = snapshot(sw, module), adapter.native_close_application_context(), application_preferences(sw)
        report.update(original_baseline=original, original_application=app, original_preferences=prefs)
        require(sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is False,
                'Configured native dimension input must already be False; no preference write allowed.')
        template = adapter.default_part_template()
        require(template and Path(template).is_file(), 'An existing normal part template is required; no fallback creation.')
        def record(models):
            windows = adapter.native_close_windows()
            rows = []
            for model in models:
                token = adapter.identity(model)
                matches = [window for current, window in windows if adapter.identity(current) == token]
                require(len(matches) == 1, 'Each exact returned owned document must have one live HWND.')
                rows.append(dict(document_identity_token=pool.ordinal(token), window=matches[0], metadata=None))
                report['owned_documents'] = rows; persist()  # HWND/canonical receipt before metadata getters.
                rows[-1]['metadata'] = adapter.snapshot(model)
            require(len(adapter.documents()) == len(models), 'Foreign/missing document appeared; no roster adoption.')
            report['owned_documents'] = rows; persist()
        for name, sizes in (('Контрольная деталь подавления', (40., 20., 10.)),
                            ('Рабочий сосед подавления', (5., 6., 7.))):
            report.update(phase='fixture_creation', native_calls_live=True); persist()
            creation = adapter.new_document_receipt(owned); document_receipts.append(creation)
            guard = adapter.document_creation_guard(owned)
            with guard:
                adapter.create_empty_part_document(creation, template, name, 'Основная')
                require(creation.pending_creation is False and creation.model is not None
                        and creation.identity is not None and adapter.created_document_identity(creation) == creation.identity,
                        'Exact normal document creation binding required.')
                owned.append(creation.model)
                normal = dict(document_identity_token=pool.ordinal(creation.identity),
                    native_call_returned=True, pending_creation=False, window=None)
                report.setdefault('normal_creation_returns', []).append(normal); persist()
                record(owned)  # Exact returned binding + HWND persisted before base calls.
                normal['window'] = report['owned_documents'][-1]['window']; persist()
                normal['unsaved_path'] = creation.model.GetPathName(); persist()
            report.setdefault('creation_guards', []).append(normal_release(guard, sw))
            report['native_calls_live'] = False; persist()
            model = creation.model
            frame = validated_plane_transform((1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.))
            features = adapter.features(model)
            planes = [f for f in features if f.GetTypeName2() == 'RefPlane'
                and validated_plane_transform(adapter.reference_plane_transform(f)) == frame]
            require(len(planes) == 1, 'Exact reference-plane transform required.')
            definition = BaseRectangle.validate(plane_object_id='feat_' + uuid.uuid4().hex,
                width_mm=sizes[0], height_mm=sizes[1], depth_mm=sizes[2])
            base = adapter.new_base_receipt(model, features, adapter.part_creation_controls(model)); base_receipts.append(base)
            report.update(phase='fixture_base_creation', native_calls_live=True); persist()
            guard = adapter.mutation_guard(model)
            with guard:
                adapter.create_base_rectangle(model, planes[0], definition, base)
                require(base.pending_creation is False and base.selection_uncertain is False
                        and base.extrusion is not None and base.extrusion_identity is not None,
                        'Normal owned base creation receipt required.')
                normal = dict(
                    document_identity_token=pool.ordinal(creation.identity),
                    feature_identity_token=pool.ordinal(base.extrusion_identity),
                    native_call_returned=True, pending_creation=False, selection_uncertain=False)
                report.setdefault('normal_base_returns', []).append(normal); persist()
                normal['feature_pid_hex'] = adapter.persistent_id(model, base.extrusion).hex(); persist()
                normal['feature_native_id'] = base.extrusion.GetID(); persist()
                require(model.ForceRebuild3(False) is True and model.GetSaveFlag() is True
                        and model.GetPathName() == '' and list(model.GetConfigurationNames()) == ['Основная'],
                        'Own fixture must be one dirty unsaved normally rebuilt BASE configuration.')
            report.setdefault('creation_guards', []).append(normal_release(guard, sw))
            report['native_calls_live'] = False; record(owned)
        target, neighbor = owned
        activate_owned(sw, target, target.GetTitle())
        documents = DocumentCatalog(adapter); documents.list()
        entries = [next(e for e in documents._entries if e.identity == receipt.identity) for receipt in document_receipts]
        store = JobStore(state / 'jobs.sqlite')
        sessions = NativeDocumentOpenCatalog(documents, store, 'b2_probe_' + uuid.uuid4().hex)
        base = base_receipts[0]; feature = base.extrusion
        census = adapter.features(target)
        positions = [i for i, f in enumerate(census) if adapter.identity(f) == base.extrusion_identity]
        require(len(positions) == 1, 'Exact returned base must be one canonical full census member.')
        owner = dict(document_id=entries[0].document_id, configuration='Основная',
            document_identity_token=pool.ordinal(document_receipts[0].identity),
            configuration_identity_token=pool.ordinal(adapter.configuration_identity(target, 'Основная')),
            feature_identity_token=pool.ordinal(base.extrusion_identity), feature_native_id=feature.GetID(),
            feature_pid_hex=adapter.persistent_id(target, feature).hex(), feature_role='feature:' + str(positions[0]),
            window_hwnd=report['normal_creation_returns'][0]['window']['hwnd'],
            owned_document_ids=[e.document_id for e in entries])
        observer = OwnedSuppressionProbeObserver(documents, sessions, owner=owner,
            model=target, feature=feature, document_identity=document_receipts[0].identity,
            feature_identity=base.extrusion_identity,
            configuration_identity=adapter.configuration_identity(target, 'Основная'),
            owned_fixtures={e.document_id: (receipt.model, receipt.identity)
                for e, receipt in zip(entries, document_receipts)}, identity_pool=pool,
            read_preferences=application_preferences)
        perform_probe(observer, report, persist)
        require(report['native_calls_live'] is False and report['native_normal_completion_verified'] is True,
                'Root requires normal native completion independently of receipt-only validation.')
        report.update(phase='owned_cleanup', native_calls_live=True); persist()
        neighbor_before = report['probe_receipt']['observations'][0]['session']['neighbor_snapshots'][entries[1].document_id]
        retire_owned(sw, module, target, [target], owned, record)
        require(adapter.rectangle_construction_snapshot(neighbor) == neighbor_before,
                'Full independent neighbor oracle must survive target cleanup.')
        retire_owned(sw, module, neighbor, [neighbor], owned, record)
        require_free_session(sw)
        restored = snapshot(sw, module)
        require(restored == original and adapter.native_close_application_context() == app,
                'Independent original global baseline must return after exact own cleanup.')
        assert_non_stl_preferences(lambda: application_preferences(sw), prefs, report, 'restored_preferences')
        report.update(restored_baseline=restored, restored_application=adapter.native_close_application_context(),
            phase='terminal', native_calls_live=False, probe_passed=True,
            baseline_restored=True, own_cleanup_verified=True, deferred_stl_verified=False)
        persist(); store.close()
    except BaseException as error:
        report.update(phase='failed', error=str(error), traceback=traceback.format_exc()); persist()
        if owned or report['native_calls_live'] is not False or any(
                r.pending_creation or r.pending_close or r.model is not None for r in document_receipts):
            report['retained_process'] = True; persist()
            print(json.dumps(dict(retained_process=True, error=str(error)), ensure_ascii=False), flush=True)
            while True:
                pythoncom.PumpWaitingMessages(); time.sleep(.5)
        raise
    finally:
        persist(); pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--state-dir', required=True, type=Path)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--b1-audit', type=Path, default=Path(__file__).resolve().parents[1] / 'work/b1-dev94-final-audit-1.json')
    args = parser.parse_args()
    evidence = passive_preflight(args)
    state = Path(evidence['state_dir']); state.mkdir()
    started = time.perf_counter()
    report = dict(scope='installed_owned_b2_suppression_pid_compatibility_probe_v1',
        accepted=False, native_b2_accepted=False, full_tool_acceptance=False,
        probe_passed=False, native_calls_live=False, phase='preflight', owned_documents=[], **evidence)
    def persist():
        report['elapsed_seconds'] = time.perf_counter() - started
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf8')
    persist()
    run_native(state, report, persist)
    print(json.dumps(dict(probe_passed=report['probe_passed'], native_b2_accepted=False,
        full_tool_acceptance=False, elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
